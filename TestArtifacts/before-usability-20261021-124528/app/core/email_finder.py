from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, replace
from typing import Callable, Iterable

from run_support import RunMetrics
from app.constants import MISSING_VALUE
from app.core.batch_control import BatchCancelled, BatchControl
from app.core.email_pattern import generate_email, infer_best_pattern
from app.core.email_pattern_cache import EmailPatternCache, EmailPatternCacheEntry
from app.core.email_pattern_discovery import PatternDiscoveryResult, PublicEmailPatternDiscoverer
from app.core.website_email_lookup import WebsiteEmailLookup
from scraper_engine import lookup_budget
from app.services.search_provider import create_search_provider
from app.core.normalizer import (
    clean_text,
    is_generic_email_domain,
    is_valid_domain,
    is_valid_email,
    normalize_domain,
    normalize_email,
)


@dataclass(frozen=True, slots=True)
class EmailFindingResult:
    row_index: int
    status: str
    candidate: str = MISSING_VALUE
    confidence: int = 0
    pattern: str | None = None
    source: str = ""
    evidence_count: int = 0
    reason: str = ""
    applied: bool = False
    discovery_status: str = ""
    discovery_provider: str = ""
    web_query_count: int = 0
    evidence_sources: tuple[str, ...] = ()
    discovery_cached: bool = False


class EmailFinder:
    """Business-email engine with Phase-5 public pattern discovery.

    Local/known organization evidence remains the first priority. Optional company
    page checks and API search share a bounded company lookup. The desktop enables
    company pages by default; broader API search is a separate setting.
    """

    def __init__(self, cache: EmailPatternCache | None = None) -> None:
        self.cache = cache or EmailPatternCache()
        self.last_discovery_results: dict[str, PatternDiscoveryResult] = {}
        self.last_run_cancelled = False

    @staticmethod
    def _learned_confidence(evidence_count: int, agreement_ratio: float) -> int:
        # A single supplied address is evidence of a format, but not proof that the
        # same format applies universally. Confidence rises with repeated agreement.
        base = {1: 72, 2: 82, 3: 89, 4: 93}.get(evidence_count, 96)
        if agreement_ratio < 1.0:
            base -= round((1.0 - agreement_ratio) * 25)
        return max(50, min(98, base))

    def learn_patterns(self, records: Iterable[dict[str, str]]) -> dict[str, EmailPatternCacheEntry]:
        observations: dict[str, list[str]] = defaultdict(list)
        for record in records:
            # Never let the engine's own generated/possible addresses become new
            # evidence on a later run. Learn only from user/imported or externally
            # validated organization emails.
            email_status = clean_text(record.get("Email Status"))
            if email_status.lower().startswith(("generated", "possible")) or email_status in {"Not Found", "Missing Name", "Missing Domain", "Invalid Domain"}:
                continue
            domain = normalize_domain(record.get("Company Website"))
            email = normalize_email(record.get("Business Email ID"))
            if domain == MISSING_VALUE or email == MISSING_VALUE:
                continue
            if not is_valid_domain(domain) or is_generic_email_domain(domain) or not is_valid_email(email):
                continue
            if email.rsplit("@", 1)[-1] != domain:
                continue
            pattern = infer_best_pattern(
                record.get("First Name"),
                record.get("Last Name"),
                email,
                domain,
            )
            if pattern:
                observations[domain].append(pattern)

        learned: dict[str, EmailPatternCacheEntry] = {}
        for domain, patterns in observations.items():
            counts = Counter(patterns)
            pattern, count = counts.most_common(1)[0]
            total = sum(counts.values())
            agreement = count / total if total else 0.0
            entry = EmailPatternCacheEntry(
                domain=domain,
                pattern=pattern,
                confidence=self._learned_confidence(count, agreement),
                source="Learned from existing organization emails",
                evidence_count=count,
            )
            # Do not downgrade a stronger existing cache entry unless the newly
            # learned evidence is at least as strong.
            existing = self.cache.get(domain)
            if existing and (
                (existing.pattern == entry.pattern and existing.confidence >= entry.confidence and existing.evidence_count >= entry.evidence_count)
                or
                existing.confidence > entry.confidence
                or (
                    existing.confidence == entry.confidence
                    and existing.evidence_count > entry.evidence_count
                )
            ):
                learned[domain] = existing
            else:
                learned[domain] = self.cache.upsert(entry)
        return learned

    @staticmethod
    def _missing_name(record: dict[str, str]) -> bool:
        return (
            clean_text(record.get("First Name")) == MISSING_VALUE
            or clean_text(record.get("Last Name")) == MISSING_VALUE
        )

    def find_for_record(
        self,
        row_index: int,
        record: dict[str, str],
        *,
        minimum_confidence: int = 75,
        revalidate_existing: bool = False,
        allow_fallback_candidate: bool = True,
        blocked_status: str | None = None,
        pattern_entry: EmailPatternCacheEntry | None = None,
        pattern_lookup_done: bool = False,
        discovery_result: PatternDiscoveryResult | None = None,
    ) -> EmailFindingResult:
        existing_raw = clean_text(record.get("Business Email ID"))
        existing = normalize_email(existing_raw)
        domain = normalize_domain(record.get("Company Website"))

        if blocked_status in {"Suppressed", "Outside TAL", "Duplicate"}:
            return EmailFindingResult(
                row_index=row_index,
                status="Suppressed" if blocked_status == "Suppressed" else "Manual Review",
                source="Phase-3 validation",
                reason=f"Email generation skipped because record status is {blocked_status}.",
            )

        if existing_raw != MISSING_VALUE and not revalidate_existing:
            return EmailFindingResult(
                row_index=row_index,
                status=clean_text(record.get("Email Status")) if clean_text(record.get("Email Status")) != MISSING_VALUE else "Existing",
                candidate=existing,
                confidence=100 if is_valid_email(existing) else 0,
                source="User-provided value",
                reason="Existing Business Email ID preserved; Revalidate Existing Emails is disabled.",
                applied=False,
            )

        if self._missing_name(record):
            return EmailFindingResult(
                row_index=row_index,
                status="Missing Name",
                source="Phase-4 validation",
                reason="First Name and Last Name are required to generate an email candidate.",
            )
        if domain == MISSING_VALUE:
            return EmailFindingResult(
                row_index=row_index,
                status="Missing Domain",
                source="Phase-4 validation",
                reason="Company Website / Domain is missing.",
            )
        if not is_valid_domain(domain) or is_generic_email_domain(domain):
            return EmailFindingResult(
                row_index=row_index,
                status="Invalid Domain",
                source="Phase-4 validation",
                reason="Company Website does not contain an acceptable business domain.",
            )

        if existing_raw != MISSING_VALUE and revalidate_existing:
            if not is_valid_email(existing):
                return EmailFindingResult(
                    row_index=row_index,
                    status="Manual Review",
                    candidate=existing,
                    source="Existing email validation",
                    reason="Existing Business Email ID has invalid syntax/domain.",
                )
            if existing.rsplit("@", 1)[-1] != domain:
                return EmailFindingResult(
                    row_index=row_index,
                    status="Manual Review",
                    candidate=existing,
                    confidence=60,
                    source="Existing email validation",
                    reason="Existing Business Email ID domain does not match Company Website.",
                )
            pattern = infer_best_pattern(
                record.get("First Name"), record.get("Last Name"), existing, domain
            )
            return EmailFindingResult(
                row_index=row_index,
                status="Pattern Match" if pattern else "Manual Review",
                candidate=existing,
                confidence=90 if pattern else 70,
                pattern=pattern,
                source="Existing organization email",
                evidence_count=1 if pattern else 0,
                reason=(
                    "Existing email is syntactically valid and matches the company domain/pattern."
                    if pattern
                    else "Existing email is valid and matches the company domain, but its pattern could not be inferred."
                ),
                applied=False,
            )

        cache_entry = pattern_entry if pattern_lookup_done else self.cache.get(domain)
        if cache_entry:
            candidate = generate_email(
                cache_entry.pattern,
                record.get("First Name"),
                record.get("Last Name"),
                domain,
            )
            confidence = min(99, cache_entry.confidence + (3 if is_valid_email(candidate) else 0))
            applied = bool(candidate != MISSING_VALUE and confidence >= minimum_confidence)
            discovery_note = ""
            if discovery_result and discovery_result.status:
                discovery_note = f" Phase-5 discovery: {discovery_result.status}."
            return EmailFindingResult(
                row_index=row_index,
                status="Generated" if applied else "Possible",
                candidate=candidate,
                confidence=confidence,
                pattern=cache_entry.pattern,
                source=cache_entry.source,
                evidence_count=cache_entry.evidence_count,
                reason=(
                    f"Candidate generated from cached organization pattern {cache_entry.pattern}."
                    + discovery_note
                    + ("" if applied else f" Confidence is below the {minimum_confidence}% auto-fill threshold.")
                ),
                applied=applied,
                discovery_status=discovery_result.status if discovery_result else "",
                discovery_provider=discovery_result.provider if discovery_result else "",
                web_query_count=discovery_result.query_count if discovery_result else 0,
                evidence_sources=discovery_result.sources if discovery_result else (),
                discovery_cached=discovery_result.cached if discovery_result else False,
            )

        if discovery_result and discovery_result.status in {"Timed Out", "Search Error", "Search Disabled", "Not Found"}:
            return EmailFindingResult(
                row_index=row_index, status=discovery_result.status, source=discovery_result.provider or "Public web search",
                reason=discovery_result.reason, applied=False,
                discovery_status=discovery_result.status, discovery_provider=discovery_result.provider,
                web_query_count=discovery_result.query_count,
                evidence_sources=discovery_result.sources,
            )

        # Phase 4 can show a conservative fallback candidate, but does not auto-fill
        # it at normal confidence thresholds because there is no organization-specific
        # pattern evidence yet. Phase 5 will search public sources for that evidence.
        if allow_fallback_candidate:
            pattern = "{first}.{last}"
            candidate = generate_email(
                pattern, record.get("First Name"), record.get("Last Name"), domain
            )
            discovery_reason = ""
            if discovery_result:
                discovery_reason = f" Phase-5 discovery: {discovery_result.status} — {discovery_result.reason}"
            return EmailFindingResult(
                row_index=row_index,
                status="Possible",
                candidate=candidate,
                confidence=35,
                pattern=pattern,
                source="Fallback candidate — no organization-specific evidence",
                evidence_count=0,
                reason="No learned/cached email pattern exists for this domain; candidate was not auto-filled." + discovery_reason,
                applied=False,
                discovery_status=discovery_result.status if discovery_result else "",
                discovery_provider=discovery_result.provider if discovery_result else "",
                web_query_count=discovery_result.query_count if discovery_result else 0,
                evidence_sources=discovery_result.sources if discovery_result else (),
                discovery_cached=discovery_result.cached if discovery_result else False,
            )

        return EmailFindingResult(
            row_index=row_index,
            status="Not Found",
            source="Phase-4 cache",
            reason="No organization email pattern is available for this domain.",
        )

    def find_missing(
        self, records: list[dict[str, str]], *, minimum_confidence: int = 75,
        revalidate_existing: bool = False, blocked_statuses: dict[int, str] | None = None,
        enable_web_search: bool = False, search_provider_name: str = "Auto",
        max_workers: int = 4, request_timeout_seconds: int = 15, retries: int = 2,
        discovery_cache_days: int = 30, force_discovery_refresh: bool = False,
        progress_callback=None, row_progress_callback=None, control: BatchControl | None = None,
        progress_interval: int = 1, result_callback=None, run_store=None,
        enable_website_lookup: bool = False,
    ) -> list[EmailFindingResult]:
        """Resolve cheap/local rows first, then stream bounded domain completions.

        Only the coordinator applies/persists results. At most four domains are
        submitted at once; cancellation never leaves an unbounded executor queue.
        """
        self.last_run_cancelled = False
        self.last_discovery_results = {}
        self.metrics = RunMetrics()
        results = {}
        provider = None
        blocked_statuses = dict(blocked_statuses or {})
        total_rows = len(records)
        interval = max(1, int(progress_interval))
        settings = {"confidence": minimum_confidence, "revalidate": revalidate_existing,
                    "web": enable_web_search, "provider": search_provider_name,
                    "cache_days": discovery_cache_days, "website": enable_website_lookup}
        try:
            if control: control.checkpoint()
            with self.metrics.measure("local_evidence"):
                self.learn_patterns(records)
                domains = {normalize_domain(r.get("Company Website")) for r in records}
                domains = {d for d in domains if is_valid_domain(d) and not is_generic_email_domain(d)}
                entries = self.cache.get_many(domains) if isinstance(self.cache, EmailPatternCache) else {d: self.cache.get(d) for d in domains}
            keys = [run_store.key(r, {**settings, "evidence": str(entries.get(normalize_domain(r.get("Company Website"))))}, blocked_statuses.get(i))
                    for i, r in enumerate(records)] if run_store else []
            saved = run_store.get_many(keys) if run_store and not force_discovery_refresh else {}

            def emit(index, discovery=None, restored=None, published=None):
                row = records[index]
                domain = normalize_domain(row.get("Company Website"))
                result = restored or published or self.find_for_record(index, row,
                    minimum_confidence=minimum_confidence, revalidate_existing=revalidate_existing,
                    blocked_status=blocked_statuses.get(index), pattern_entry=entries.get(domain),
                    pattern_lookup_done=True, discovery_result=discovery)
                results[index] = result
                if run_store and not restored:
                    with self.metrics.measure("save_completed_rows"):
                        run_store.save(keys[index], result)
                if result_callback: result_callback(result)
                self.metrics.count("completed_rows")
                if result.applied: self.metrics.count("emails_added")
                if not result.applied and clean_text(row.get("Business Email ID")) == MISSING_VALUE:
                    self.metrics.count("blank_rows")
                if result.status == "Timed Out" or result.discovery_status in {"Search Error", "Search Disabled", "Timed Out"}:
                    self.metrics.count("retryable_rows")
                if row_progress_callback and (len(results) == total_rows or len(results) % interval == 0):
                    row_progress_callback(len(results), total_rows)

            pending_domains = defaultdict(list)
            with self.metrics.measure("local_rows"):
                for index, row in enumerate(records):
                    if control: control.checkpoint()
                    if run_store and keys[index] in saved:
                        restored = dict(saved[keys[index]])
                        restored["row_index"] = index
                        restored["evidence_sources"] = tuple(restored.get("evidence_sources", ()))
                        emit(index, restored=EmailFindingResult(**restored))
                        self.metrics.count("resumed_rows")
                        continue
                    domain = normalize_domain(row.get("Company Website"))
                    entry = entries.get(domain)
                    local = (not (enable_web_search or enable_website_lookup) or self._missing_name(row)
                             or domain not in entries
                             or blocked_statuses.get(index) in {"Suppressed", "Outside TAL", "Duplicate"}
                             or clean_text(row.get("Business Email ID")) != MISSING_VALUE
                             or (entry and entry.confidence >= minimum_confidence and not force_discovery_refresh))
                    if local:
                        disabled = None
                        if not (enable_web_search or enable_website_lookup) and not entry:
                            disabled = PatternDiscoveryResult(domain, "Search Disabled",
                                reason="Only saved results were checked. Enable company website checks in Settings → Email Discovery to look for published emails.")
                        emit(index, disabled)
                        if entry: self.metrics.count("pattern_cache_rows")
                    else:
                        pending_domains[domain].append(index)
            if not pending_domains:
                return [results[i] for i in sorted(results)]
            if control: control.checkpoint()
            provider = create_search_provider(search_provider_name if enable_web_search else "Disabled",
                                              timeout_seconds=request_timeout_seconds, retries=retries)
            provider.control = control
            provider.metrics = self.metrics
            total = len(pending_domains)
            self.metrics.count("unique_domains_searched", total)
            self.metrics.count("company_lookups_reused", sum(len(v)-1 for v in pending_domains.values()))
            if progress_callback: progress_callback(0, total, "", "Searching domains")
            if not provider.configured and not enable_website_lookup:
                for domain, indices in pending_domains.items():
                    if control: control.checkpoint()
                    discovery = PatternDiscoveryResult(domain=domain, status="Search Disabled", provider=provider.name,
                        reason="No configured search provider/API key is available.")
                    self.last_discovery_results[domain] = discovery
                    for index in indices: emit(index, discovery)
                return [results[i] for i in sorted(results)]
            discoverer = PublicEmailPatternDiscoverer(provider, pattern_cache=self.cache, cache_days=discovery_cache_days)
            website = WebsiteEmailLookup(metrics=self.metrics, control=control,
                timeout_seconds=request_timeout_seconds) if enable_website_lookup else None
            workers = max(1, min(int(max_workers), 4, total))
            self.metrics.count("worker_limit", workers)
            remaining = iter(pending_domains)
            futures = {}
            done_domains = 0
            def discover(domain):
                with self.metrics.measure("public_discovery"), lookup_budget.budget(15):
                    pages = None
                    if website:
                        with self.metrics.measure("company_website"):
                            pages = website.discover(domain, force_refresh=force_discovery_refresh)
                        if all(pages.matches(records[i]) for i in pending_domains[domain]):
                            return PatternDiscoveryResult(domain, "Found", provider="Company website",
                                reason="Published addresses matched on official company pages."), pages
                    if not provider.configured:
                        status = pages.status if pages else "Search Disabled"
                        reason = pages.reason if pages else "No search API is configured."
                        if enable_web_search and status == "Not Found":
                            status = "Search Disabled"
                            reason += " Broader web search needs a configured search API in Settings."
                        return PatternDiscoveryResult(domain, status, provider="Company website" if pages else provider.name,
                            reason=reason, sources=tuple(d.url for d in pages.documents) if pages else ()), pages
                    kwargs = {"force_refresh": force_discovery_refresh}
                    if control is not None: kwargs["control"] = control
                    try:
                        lookup_budget.timeout(1)
                        result = discoverer.discover(domain, clean_text(records[pending_domains[domain][0]].get("Company Name")), **kwargs)
                    except lookup_budget.LookupTimeout:
                        result = PatternDiscoveryResult(domain, "Timed Out", reason="15-second lookup budget reached; retry is available.")
                    if pages and pages.status in {"Search Error", "Timed Out"} and result.status == "Not Found":
                        result = replace(result, status=pages.status, reason=pages.reason)
                    return result, pages
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pattern-search") as pool:
                try:
                    exhausted = False
                    while futures or not exhausted:
                        if control and control.cancelled:
                            self.last_run_cancelled = True
                            exhausted = True
                        while not exhausted and len(futures) < workers:
                            if control: control.checkpoint()
                            domain = next(remaining, None)
                            if domain is None:
                                exhausted = True
                                break
                            futures[pool.submit(discover, domain)] = domain
                        if not futures: break
                        completed, _ = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
                        for future in completed:
                            domain = futures.pop(future)
                            try:
                                discovery, pages = future.result()
                            except BatchCancelled:
                                self.last_run_cancelled = True
                                continue
                            except Exception as exc:
                                discovery = PatternDiscoveryResult(domain=domain, status="Search Error", provider=provider.name, reason=str(exc))
                                pages = None
                            self.last_discovery_results[domain] = discovery
                            entries[domain] = self.cache.get(domain)
                            self.metrics.count("cached_discoveries" if discovery.cached else "search_queries", 1 if discovery.cached else discovery.query_count)
                            for index in pending_domains[domain]:
                                facts = pages.matches(records[index]) if pages else []
                                published = None
                                if facts:
                                    published = EmailFindingResult(index, "Found online (unverified)",
                                        candidate=facts[0]["email"], confidence=95, source="Official company website",
                                        evidence_count=len({fact["url"] for fact in facts}), applied=95 >= minimum_confidence,
                                        reason="The person's name and email are published together on an official company page. Mailbox delivery has not been verified."
                                               + ("" if minimum_confidence <= 95 else " Below the configured auto-fill threshold."),
                                        discovery_status="Found", discovery_provider="Company website",
                                        evidence_sources=tuple(dict.fromkeys(fact["url"] for fact in facts)),
                                        discovery_cached=pages.cached)
                                emit(index, discovery, published=published)
                            done_domains += 1
                            if progress_callback: progress_callback(done_domains, total, domain, discovery.status)
                finally:
                    for future in futures: future.cancel()
        except BatchCancelled:
            self.last_run_cancelled = True
        finally:
            close = getattr(provider, "close", None)
            if close: close()
            self.last_metrics = self.metrics.snapshot()
            self.last_metrics["cancelled"] = self.last_run_cancelled
            self.last_metrics["total_rows"] = total_rows
            self.last_metrics["unfinished_rows"] = total_rows - len(results) + self.metrics.counts.get("retryable_rows", 0)
        return [results[i] for i in sorted(results)]
