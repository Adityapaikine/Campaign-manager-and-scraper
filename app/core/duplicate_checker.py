from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from app.constants import MISSING_VALUE
from app.core.normalizer import (
    is_valid_domain,
    is_valid_email,
    normalize_company_name,
    normalize_domain,
    normalize_email,
    normalize_linkedin_url,
    normalize_name,
)


@dataclass(frozen=True, slots=True)
class DuplicateResult:
    status: str
    duplicate_rows: tuple[int, ...] = ()
    matched_on: str = ""

    @property
    def is_exact(self) -> bool:
        return self.status == "Exact Duplicate"

    @property
    def is_possible(self) -> bool:
        return self.status == "Possible Duplicate"


class DuplicateChecker:
    """Two-pass duplicate detection with deterministic priority.

    Exact matches are checked in this order:
    1) Business Email ID
    2) Prospect LinkedIn Link
    3) First Name + Last Name + Company Domain

    A conservative possible-duplicate signal is then used for rows sharing a
    normalized person name + company name when no exact key is available.
    """

    def check(self, records: list[dict[str, str]]) -> list[DuplicateResult]:
        results = [DuplicateResult("Unique") for _ in records]

        exact_groups: list[tuple[str, dict[object, list[int]]]] = [
            ("Business Email ID", self._group(records, self._email_key)),
            ("Prospect LinkedIn Link", self._group(records, self._linkedin_key)),
            ("Name + Company Domain", self._group(records, self._person_domain_key)),
        ]

        assigned: set[int] = set()
        for label, groups in exact_groups:
            for indices in groups.values():
                if len(indices) < 2:
                    continue
                for index in indices:
                    if index in assigned:
                        continue
                    others = tuple(i for i in indices if i != index)
                    results[index] = DuplicateResult("Exact Duplicate", others, label)
                    assigned.add(index)

        possible_groups = self._group(records, self._person_company_key)
        for indices in possible_groups.values():
            if len(indices) < 2:
                continue
            for index in indices:
                if index in assigned:
                    continue
                others = tuple(i for i in indices if i != index)
                results[index] = DuplicateResult(
                    "Possible Duplicate",
                    others,
                    "Name + Company Name",
                )
        return results

    @staticmethod
    def _group(records: list[dict[str, str]], key_func) -> dict[object, list[int]]:
        groups: dict[object, list[int]] = defaultdict(list)
        for index, record in enumerate(records):
            key = key_func(record)
            if key is not None:
                groups[key].append(index)
        return groups

    @staticmethod
    def _email_key(record: dict[str, str]) -> str | None:
        email = normalize_email(record.get("Business Email ID"))
        if email == MISSING_VALUE or not is_valid_email(email):
            return None
        return email

    @staticmethod
    def _linkedin_key(record: dict[str, str]) -> str | None:
        linkedin = normalize_linkedin_url(record.get("Prospect LinkedIn Link"))
        return None if linkedin == MISSING_VALUE else linkedin.casefold()

    @staticmethod
    def _person_domain_key(record: dict[str, str]) -> tuple[str, str, str] | None:
        first = normalize_name(record.get("First Name"))
        last = normalize_name(record.get("Last Name"))
        domain = normalize_domain(record.get("Company Website"))
        if MISSING_VALUE in {first, last, domain} or not is_valid_domain(domain):
            return None
        return first, last, domain

    @staticmethod
    def _person_company_key(record: dict[str, str]) -> tuple[str, str, str] | None:
        first = normalize_name(record.get("First Name"))
        last = normalize_name(record.get("Last Name"))
        company = normalize_company_name(record.get("Company Name"))
        if MISSING_VALUE in {first, last, company}:
            return None
        return first, last, company
