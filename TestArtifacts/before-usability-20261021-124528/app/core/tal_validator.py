from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.constants import MISSING_VALUE
from app.core.normalizer import normalize_company_name, normalize_domain
from app.core.reference_lists import ReferenceData


@dataclass(frozen=True, slots=True)
class TALResult:
    status: str
    reason: str
    matched_company: str = MISSING_VALUE
    matched_domain: str = MISSING_VALUE
    score: float | None = None

    @property
    def is_match(self) -> bool:
        return self.status in {"Exact Match", "Domain Match", "Company Match"}


class TALValidator:
    """Fast TAL/account matching using exact indexes plus conservative fuzzy fallback."""

    def __init__(
        self,
        data: ReferenceData,
        *,
        fuzzy_threshold: float = 92.0,
        fuzzy_enabled: bool = True,
    ) -> None:
        if data.kind != "tal":
            raise ValueError("TALValidator requires ReferenceData(kind='tal').")
        self.data = data
        self.fuzzy_threshold = float(fuzzy_threshold)
        self.fuzzy_enabled = bool(fuzzy_enabled)
        self.domains: set[str] = set()
        self.companies: set[str] = set()
        self.domain_to_company: dict[str, str] = {}
        self.company_to_domain: dict[str, str] = {}
        self.company_domain_pairs: set[tuple[str, str]] = set()
        self.company_buckets: dict[str, set[str]] = defaultdict(set)
        self._build_indexes()

    def _build_indexes(self) -> None:
        for row in self.data.records:
            raw_company = row.get("Company Name", MISSING_VALUE)
            raw_domain = row.get("Domain", MISSING_VALUE)
            company = normalize_company_name(raw_company)
            domain = normalize_domain(raw_domain)
            if company != MISSING_VALUE:
                self.companies.add(company)
                bucket = company.split(" ", 1)[0][:3]
                self.company_buckets[bucket].add(company)
            if domain != MISSING_VALUE:
                self.domains.add(domain)
            if domain != MISSING_VALUE and company != MISSING_VALUE:
                self.domain_to_company.setdefault(domain, company)
                self.company_to_domain.setdefault(company, domain)
                self.company_domain_pairs.add((company, domain))

    def match(self, record: dict[str, str]) -> TALResult:
        company = normalize_company_name(record.get("Company Name"))
        domain = normalize_domain(record.get("Company Website"))
        domain_match = domain != MISSING_VALUE and domain in self.domains
        company_match = company != MISSING_VALUE and company in self.companies

        if domain_match and company_match and (company, domain) in self.company_domain_pairs:
            return TALResult(
                "Exact Match",
                "TAL: exact normalized company and domain match",
                matched_company=company,
                matched_domain=domain,
                score=100.0,
            )
        if domain_match:
            return TALResult(
                "Domain Match",
                f"TAL: domain match ({domain})",
                matched_company=self.domain_to_company.get(domain, MISSING_VALUE),
                matched_domain=domain,
                score=100.0,
            )
        if company_match:
            return TALResult(
                "Company Match",
                f"TAL: normalized company match ({company})",
                matched_company=company,
                matched_domain=self.company_to_domain.get(company, MISSING_VALUE),
                score=100.0,
            )

        if self.fuzzy_enabled and company != MISSING_VALUE and self.companies:
            bucket = company.split(" ", 1)[0][:3]
            choices = self.company_buckets.get(bucket) or self.companies
            fuzzy = process.extractOne(
                company,
                choices,
                scorer=fuzz.token_set_ratio,
                score_cutoff=self.fuzzy_threshold,
            )
            if fuzzy:
                matched, score, _ = fuzzy
                return TALResult(
                    "Possible Match",
                    f"TAL: possible company match ({matched}, {score:.0f}% similarity)",
                    matched_company=matched,
                    matched_domain=self.company_to_domain.get(matched, MISSING_VALUE),
                    score=float(score),
                )

        return TALResult("Not in TAL", "TAL: no matching account/domain found")
