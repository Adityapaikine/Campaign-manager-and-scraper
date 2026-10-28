from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.constants import MISSING_VALUE
from app.core.normalizer import (
    normalize_company_name,
    normalize_domain,
    normalize_email,
    normalize_linkedin_url,
    normalize_name,
)
from app.core.reference_lists import ReferenceData


@dataclass(frozen=True, slots=True)
class SuppressionResult:
    status: str
    reason: str
    matched_value: str = MISSING_VALUE
    score: float | None = None
    source_type: str = ""
    source_file: str = ""

    @property
    def is_suppressed(self) -> bool:
        return self.status.startswith("Suppressed -")

    @property
    def is_possible(self) -> bool:
        return self.status == "Possible Suppression Match"


class SuppressionValidator:
    """Suppression matching with deterministic exact-match priority.

    Priority: Email -> LinkedIn -> Domain -> Company -> exact Prospect Name.
    Fuzzy company/name matches never auto-suppress; they are manual-review signals.
    """

    def __init__(
        self,
        data: ReferenceData,
        *,
        company_fuzzy_threshold: float = 94.0,
        name_fuzzy_threshold: float = 96.0,
        fuzzy_enabled: bool = True,
    ) -> None:
        if data.kind != "suppression":
            raise ValueError("SuppressionValidator requires ReferenceData(kind='suppression').")
        self.data = data
        self.company_fuzzy_threshold = float(company_fuzzy_threshold)
        self.name_fuzzy_threshold = float(name_fuzzy_threshold)
        self.fuzzy_enabled = bool(fuzzy_enabled)
        self.emails: set[str] = set()
        self.linkedin_urls: set[str] = set()
        self.domains: set[str] = set()
        self.companies: set[str] = set()
        self.names: set[str] = set()
        self.name_only_suppressions: set[str] = set()
        self.company_buckets: dict[str, set[str]] = defaultdict(set)
        self.name_buckets: dict[str, set[str]] = defaultdict(set)
        self._build_indexes()

    @staticmethod
    def _full_name(first: object, last: object) -> str:
        first_n = normalize_name(first)
        last_n = normalize_name(last)
        parts = [part for part in (first_n, last_n) if part != MISSING_VALUE]
        return " ".join(parts) if parts else MISSING_VALUE

    def _build_indexes(self) -> None:
        for row in self.data.records:
            email = normalize_email(row.get("Email"))
            linkedin = normalize_linkedin_url(row.get("LinkedIn URL"))
            domain = normalize_domain(row.get("Domain"))
            company = normalize_company_name(row.get("Company Name"))
            prospect_name = normalize_name(row.get("Prospect Name"))
            if prospect_name == MISSING_VALUE:
                prospect_name = self._full_name(row.get("First Name"), row.get("Last Name"))

            if email != MISSING_VALUE:
                self.emails.add(email)
            if linkedin != MISSING_VALUE:
                self.linkedin_urls.add(linkedin.casefold())
            if domain != MISSING_VALUE:
                self.domains.add(domain)
            if company != MISSING_VALUE:
                self.companies.add(company)
                self.company_buckets[company.split(" ", 1)[0][:3]].add(company)
            if prospect_name != MISSING_VALUE:
                self.names.add(prospect_name)
                self.name_buckets[prospect_name.split(" ", 1)[0][:3]].add(prospect_name)
                if all(value == MISSING_VALUE for value in (email, linkedin, domain, company)):
                    self.name_only_suppressions.add(prospect_name)

    def match(self, record: dict[str, str]) -> SuppressionResult:
        email = normalize_email(record.get("Business Email ID"))
        if email != MISSING_VALUE and email in self.emails:
            return SuppressionResult("Suppressed - Email", f"Suppression: exact email match ({email})", email, 100.0)

        linkedin = normalize_linkedin_url(record.get("Prospect LinkedIn Link"))
        if linkedin != MISSING_VALUE and linkedin.casefold() in self.linkedin_urls:
            return SuppressionResult("Suppressed - LinkedIn", "Suppression: exact LinkedIn profile match", linkedin, 100.0)

        domain = normalize_domain(record.get("Company Website"))
        if domain != MISSING_VALUE and domain in self.domains:
            return SuppressionResult("Suppressed - Domain", f"Suppression: company domain match ({domain})", domain, 100.0)

        company = normalize_company_name(record.get("Company Name"))
        if company != MISSING_VALUE and company in self.companies:
            return SuppressionResult("Suppressed - Company", f"Suppression: normalized company match ({company})", company, 100.0)

        full_name = self._full_name(record.get("First Name"), record.get("Last Name"))
        if full_name != MISSING_VALUE and full_name in self.names:
            if full_name in self.name_only_suppressions:
                return SuppressionResult(
                    "Suppressed - Prospect Name",
                    f"Suppression: exact prospect-name match from a name-only suppression record ({full_name})",
                    full_name,
                    100.0,
                )
            return SuppressionResult(
                "Possible Suppression Match",
                f"Suppression: exact prospect-name match ({full_name}) but stronger identifiers did not match; manual review required",
                full_name,
                100.0,
            )

        # Conservative fuzzy matching: only a review signal, never suppression.
        if self.fuzzy_enabled and company != MISSING_VALUE and self.companies:
            bucket = company.split(" ", 1)[0][:3]
            choices = self.company_buckets.get(bucket) or self.companies
            fuzzy = process.extractOne(
                company,
                choices,
                scorer=fuzz.token_set_ratio,
                score_cutoff=self.company_fuzzy_threshold,
            )
            if fuzzy:
                matched, score, _ = fuzzy
                return SuppressionResult(
                    "Possible Suppression Match",
                    f"Suppression: possible company match ({matched}, {score:.0f}% similarity)",
                    matched,
                    float(score),
                )

        if self.fuzzy_enabled and full_name != MISSING_VALUE and self.names:
            bucket = full_name.split(" ", 1)[0][:3]
            choices = self.name_buckets.get(bucket) or self.names
            fuzzy = process.extractOne(
                full_name,
                choices,
                scorer=fuzz.ratio,
                score_cutoff=self.name_fuzzy_threshold,
            )
            if fuzzy:
                matched, score, _ = fuzzy
                return SuppressionResult(
                    "Possible Suppression Match",
                    f"Suppression: possible prospect-name match ({matched}, {score:.0f}% similarity); manual review required",
                    matched,
                    float(score),
                )

        return SuppressionResult("Not Suppressed", "Suppression: no match")
