from __future__ import annotations

import re
from scraper_engine import lookup_budget
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

import dns.resolver

from app.constants import MISSING_VALUE
from app.core.batch_control import BatchControl
from app.core.email_discovery_cache import EmailDiscoveryCache, EmailDiscoveryCacheEntry
from app.core.email_pattern_cache import EmailPatternCache, EmailPatternCacheEntry
from app.core.normalizer import clean_text, is_valid_domain, normalize_domain
from app.services.search_provider import SearchProvider, SearchProviderError, SearchResult
from app.utils.logger import logger


@dataclass(frozen=True, slots=True)
class PatternEvidence:
    pattern: str
    source_url: str
    source_title: str
    query: str
    provider: str


@dataclass(frozen=True, slots=True)
class PatternDiscoveryResult:
    domain: str
    status: str
    pattern: str | None = None
    confidence: int = 0
    provider: str = ""
    evidence_count: int = 0
    query_count: int = 0
    sources: tuple[str, ...] = ()
    reason: str = ""
    cached: bool = False
    mx_valid: bool | None = None


# Deliberately favor explicit format notation. Loose prose like "first last" is
# not enough evidence to infer an email convention safely.
_PATTERN_REGEXES: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    ("{first}.{last}", (
        re.compile(r"(?:\[|\{|<)?first(?:name)?(?:\]|\}|>)?\s*\.\s*(?:\[|\{|<)?last(?:name)?(?:\]|\}|>)?", re.I),
        re.compile(r"first\s*name\s*\.\s*last\s*name", re.I),
    )),
    ("{first}_{last}", (
        re.compile(r"(?:\[|\{|<)?first(?:name)?(?:\]|\}|>)?\s*_\s*(?:\[|\{|<)?last(?:name)?(?:\]|\}|>)?", re.I),
    )),
    ("{first}-{last}", (
        re.compile(r"(?:\[|\{|<)?first(?:name)?(?:\]|\}|>)?\s*-\s*(?:\[|\{|<)?last(?:name)?(?:\]|\}|>)?", re.I),
    )),
    ("{first}{last}", (
        re.compile(r"(?:\[first\]|\{first\}|<first>|firstname)\s*(?:\[last\]|\{last\}|<last>|lastname)", re.I),
        re.compile(r"first\s*name\s*\+\s*last\s*name", re.I),
    )),
    ("{f}.{last}", (
        re.compile(r"(?:first\s*initial|\[f\]|\{f\}|<f>)\s*\.\s*(?:last(?:name)?|\[last\]|\{last\}|<last>)", re.I),
        re.compile(r"f\s*\.\s*last", re.I),
    )),
    ("{f}{last}", (
        re.compile(r"(?:first\s*initial|\[f\]|\{f\}|<f>)\s*(?:last(?:name)?|\[last\]|\{last\}|<last>)", re.I),
        re.compile(r"\bflast\b", re.I),
    )),
    ("{first}.{l}", (
        re.compile(r"(?:first(?:name)?|\[first\]|\{first\}|<first>)\s*\.\s*(?:last\s*initial|\[l\]|\{l\}|<l>)", re.I),
    )),
    ("{first}{l}", (
        re.compile(r"(?:first(?:name)?|\[first\]|\{first\}|<first>)\s*(?:last\s*initial|\[l\]|\{l\}|<l>)", re.I),
    )),
    ("{last}.{first}", (
        re.compile(r"(?:last(?:name)?|\[last\]|\{last\}|<last>)\s*\.\s*(?:first(?:name)?|\[first\]|\{first\}|<first>)", re.I),
    )),
    ("{last}{first}", (
        re.compile(r"(?:\[last\]|\{last\}|<last>|lastname)\s*(?:\[first\]|\{first\}|<first>|firstname)", re.I),
    )),
    ("{last}{f}", (
        re.compile(r"(?:last(?:name)?|\[last\]|\{last\}|<last>)\s*(?:first\s*initial|\[f\]|\{f\}|<f>)", re.I),
    )),
    ("{first}", (
        re.compile(r"(?:email\s+format|pattern)\s*(?:is|:)\s*(?:\[first\]|\{first\}|<first>|firstname)\s*@", re.I),
    )),
    ("{last}", (
        re.compile(r"(?:email\s+format|pattern)\s*(?:is|:)\s*(?:\[last\]|\{last\}|<last>|lastname)\s*@", re.I),
    )),
)


def extract_patterns_from_text(text: str) -> tuple[str, ...]:
    haystack = " ".join(str(text or "").split())
    found: list[str] = []
    for pattern, regexes in _PATTERN_REGEXES:
        if any(regex.search(haystack) for regex in regexes):
            found.append(pattern)
    return tuple(found)


def check_mx(domain: str) -> bool | None:
    normalized = normalize_domain(domain)
    if normalized == MISSING_VALUE or not is_valid_domain(normalized):
        return False
    try:
        answers = dns.resolver.resolve(normalized, "MX", lifetime=lookup_budget.timeout(4.0))
        return bool(list(answers))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False
    except Exception:
        # DNS may be blocked by a corporate network; unknown must not be treated
        # as a failed company domain.
        return None


class PublicEmailPatternDiscoverer:
    def __init__(
        self,
        provider: SearchProvider,
        *,
        pattern_cache: EmailPatternCache | None = None,
        discovery_cache: EmailDiscoveryCache | None = None,
        cache_days: int = 30,
        max_queries_per_domain: int = 3,
        results_per_query: int = 10,
    ) -> None:
        self.provider = provider
        self.pattern_cache = pattern_cache or EmailPatternCache()
        self.discovery_cache = discovery_cache or EmailDiscoveryCache()
        self.cache_days = max(0, int(cache_days))
        self.max_queries_per_domain = max(1, min(int(max_queries_per_domain), 5))
        self.results_per_query = max(3, min(int(results_per_query), 20))

    @staticmethod
    def _queries(domain: str, company_name: object) -> list[str]:
        company = clean_text(company_name)
        company_part = "" if company == MISSING_VALUE else f' "{company}"'
        return [
            f'"email format" "{domain}"{company_part}',
            f'"email pattern" "{domain}"{company_part}',
            f'"@{domain}" "email format"',
        ]

    @staticmethod
    def _evidence_from_results(
        results: Iterable[SearchResult], query: str
    ) -> list[PatternEvidence]:
        evidence: list[PatternEvidence] = []
        for result in results:
            combined = f"{result.title} {result.snippet}"
            for pattern in extract_patterns_from_text(combined):
                evidence.append(
                    PatternEvidence(
                        pattern=pattern,
                        source_url=result.url,
                        source_title=result.title,
                        query=query,
                        provider=result.provider,
                    )
                )
        return evidence

    @staticmethod
    def _has_sufficient_agreeing_evidence(evidence: list[PatternEvidence]) -> bool:
        unique_pairs = {(item.source_url, item.pattern) for item in evidence if item.source_url}
        if not unique_pairs:
            return False
        counts = Counter(pattern for _url, pattern in unique_pairs)
        if not counts:
            return False
        _pattern, best_count = counts.most_common(1)[0]
        return best_count >= 2 and best_count == sum(counts.values())

    @staticmethod
    def _public_confidence(best_count: int, total_count: int, unique_sources: int) -> int:
        if best_count <= 0:
            return 0
        base = {1: 68, 2: 82, 3: 89, 4: 93}.get(unique_sources, 95)
        agreement = best_count / total_count if total_count else 0.0
        if agreement < 1.0:
            base -= round((1.0 - agreement) * 30)
        return max(45, min(95, base))

    @staticmethod
    def _combine_with_existing(
        existing: EmailPatternCacheEntry | None,
        pattern: str,
        public_confidence: int,
        public_evidence_count: int,
        mx_valid: bool | None,
    ) -> tuple[int, int, str]:
        confidence = public_confidence
        evidence_count = public_evidence_count
        source = "Public web evidence"
        if existing and existing.pattern == pattern:
            evidence_count += existing.evidence_count
            # Agreement between independent internal and public evidence deserves
            # a meaningful confidence increase, but still never implies mailbox
            # existence or verification.
            confidence = max(confidence, existing.confidence) + 6
            source = f"{existing.source} + public web evidence"
        elif existing and existing.pattern != pattern and existing.confidence >= public_confidence:
            return existing.confidence, existing.evidence_count, existing.source
        if mx_valid is True:
            confidence += 2
        elif mx_valid is False:
            confidence -= 8
        return max(0, min(98, confidence)), evidence_count, source

    def discover(self, domain, company_name="", *, force_refresh=False, control=None):
        with lookup_budget.budget(15):
            return self._discover(domain, company_name, force_refresh=force_refresh, control=control)

    def _discover(
        self,
        domain: object,
        company_name: object = MISSING_VALUE,
        *,
        force_refresh: bool = False,
        control: BatchControl | None = None,
    ) -> PatternDiscoveryResult:
        if control is not None:
            control.checkpoint()
        normalized = normalize_domain(domain)
        provider_name = self.provider.name
        if normalized == MISSING_VALUE or not is_valid_domain(normalized):
            return PatternDiscoveryResult(
                domain=normalized,
                status="Invalid Domain",
                provider=provider_name,
                reason="Domain is missing or invalid.",
            )
        if not self.provider.configured:
            return PatternDiscoveryResult(
                domain=normalized,
                status="Search Disabled",
                provider=provider_name,
                reason="No configured Phase-5 search provider/API key is available.",
            )

        cached = self.discovery_cache.get(normalized, provider_name)
        if cached and cached.status not in {"Timed Out", "Search Error"} and not force_refresh and cached.is_fresh(self.cache_days):
            if cached.pattern and cached.status == "Found":
                existing = self.pattern_cache.get(normalized)
                # A cached public result may restore/upgrade a weaker cache entry,
                # but must not overwrite stronger conflicting evidence that was
                # learned or validated after the web cache was created.
                if not existing or existing.confidence < cached.confidence:
                    self.pattern_cache.upsert(
                        EmailPatternCacheEntry(
                            domain=normalized,
                            pattern=cached.pattern,
                            confidence=cached.confidence,
                            source=f"Cached public evidence via {provider_name}",
                            evidence_count=cached.evidence_count,
                        )
                    )
            return PatternDiscoveryResult(
                domain=normalized,
                status=cached.status,
                pattern=cached.pattern,
                confidence=cached.confidence,
                provider=provider_name,
                evidence_count=cached.evidence_count,
                query_count=cached.query_count,
                sources=cached.sources,
                reason=cached.reason,
                cached=True,
            )

        all_evidence: list[PatternEvidence] = []
        query_count = 0
        search_errors: list[str] = []
        timed_out = False
        for query in self._queries(normalized, company_name)[: self.max_queries_per_domain]:
            if control is not None:
                control.checkpoint()
            query_count += 1
            try:
                lookup_budget.timeout(1)
                results = self.provider.search(query, count=self.results_per_query)
            except lookup_budget.LookupTimeout:
                timed_out = True
                break
            except SearchProviderError as exc:
                search_errors.append(str(exc))
                logger.warning("Pattern search failed | domain=%s | query=%s | error=%s", normalized, query, exc)
                continue
            all_evidence.extend(self._evidence_from_results(results, query))
            # Stop spending API requests once at least two independent sources agree
            # on one explicit format with no conflict.
            if self._has_sufficient_agreeing_evidence(all_evidence):
                break

        timed_out = timed_out or lookup_budget.remaining() <= 0.02
        if timed_out and not all_evidence:
            return PatternDiscoveryResult(domain=normalized, status="Timed Out", provider=provider_name,
                query_count=query_count, reason="15-second search budget reached; retry is available.")
        if not all_evidence:
            reason = "No explicit organization email-format evidence was found in search result titles/snippets."
            if search_errors and len(search_errors) == query_count:
                reason = "All public-search queries failed: " + search_errors[-1]
                status = "Search Error"
            else:
                # Partial failed searches also remain retryable.
                status = "Search Error" if search_errors else "Not Found"
            if status == "Not Found":
                self.discovery_cache.upsert(
                    EmailDiscoveryCacheEntry(
                        domain=normalized, provider=provider_name, status=status,
                        query_count=query_count, reason=reason,
                    )
                )
            return PatternDiscoveryResult(
                domain=normalized,
                status=status,
                provider=provider_name,
                query_count=query_count,
                reason=reason,
            )

        # Count one vote per unique source URL/pattern pair so duplicated snippets do
        # not inflate evidence strength.
        unique_pairs = {(e.source_url, e.pattern): e for e in all_evidence if e.source_url}
        evidence = list(unique_pairs.values()) or all_evidence
        counts = Counter(item.pattern for item in evidence)
        pattern, best_count = counts.most_common(1)[0]
        total_count = sum(counts.values())
        best_sources = tuple(
            dict.fromkeys(item.source_url for item in evidence if item.pattern == pattern and item.source_url)
        )
        public_confidence = self._public_confidence(best_count, total_count, len(best_sources))
        mx_valid = check_mx(normalized)
        existing = self.pattern_cache.get(normalized)
        confidence, evidence_count, source = self._combine_with_existing(
            existing, pattern, public_confidence, len(best_sources), mx_valid
        )

        # If a stronger existing pattern conflicts with public evidence, preserve it
        # and mark this discovery as conflicting rather than silently replacing it.
        if existing and existing.pattern != pattern and existing.confidence >= public_confidence:
            result_pattern = existing.pattern
            status = "Conflict"
            reason = (
                f"Public evidence suggested {pattern}, but stronger cached evidence "
                f"supports {existing.pattern}; existing pattern was preserved."
            )
            sources = best_sources
        else:
            result_pattern = pattern
            status = "Found"
            reason = (
                f"Public search found {len(best_sources)} unique source(s) supporting {pattern}. "
                "This supports an organization format only; it does not verify that a specific mailbox exists."
            )
            sources = best_sources
            self.pattern_cache.upsert(
                EmailPatternCacheEntry(
                    domain=normalized,
                    pattern=pattern,
                    confidence=confidence,
                    source=f"{source} via {provider_name}",
                    evidence_count=evidence_count,
                    mx_valid=mx_valid,
                )
            )

        cache_entry = self.discovery_cache.upsert(
            EmailDiscoveryCacheEntry(
                domain=normalized,
                provider=provider_name,
                status=status,
                pattern=result_pattern,
                confidence=confidence,
                evidence_count=evidence_count,
                query_count=query_count,
                sources=sources,
                reason=reason,
            )
        )
        return PatternDiscoveryResult(
            domain=normalized,
            status=status,
            pattern=result_pattern,
            confidence=confidence,
            provider=provider_name,
            evidence_count=evidence_count,
            query_count=query_count,
            sources=cache_entry.sources,
            reason=reason,
            cached=False,
            mx_valid=mx_valid,
        )
