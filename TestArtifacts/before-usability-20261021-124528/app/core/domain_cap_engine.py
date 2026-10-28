from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from app.constants import MISSING_VALUE
from app.core.normalizer import normalize_domain


@dataclass(frozen=True, slots=True)
class CapResult:
    domain: str
    cap: int | None
    current_count: int
    remaining: int | None
    reached: bool


class DomainCapEngine:
    """Deterministic account/domain cap tracking.

    Qwen may help interpret cap instructions, but counting/enforcement stays here.
    """

    def __init__(self, caps: dict[str, int] | None = None, default_cap: int | None = None) -> None:
        self.caps = {normalize_domain(k): int(v) for k, v in (caps or {}).items() if normalize_domain(k) != MISSING_VALUE and int(v) >= 0}
        self.default_cap = int(default_cap) if default_cap is not None else None

    def cap_for(self, domain: object) -> int | None:
        key = normalize_domain(domain)
        if key == MISSING_VALUE:
            return None
        return self.caps.get(key, self.default_cap)

    def counts(self, records: Iterable[dict[str, str]], *, eligible_statuses: set[str] | None = None, statuses: dict[int, str] | None = None) -> Counter:
        counts: Counter = Counter()
        eligible_statuses = eligible_statuses or {"Valid", "Valid - Email Generated", "Warning", "Manual Review"}
        for index, record in enumerate(records):
            if statuses is not None and statuses.get(index) not in eligible_statuses:
                continue
            domain = normalize_domain(record.get("Company Website"))
            if domain != MISSING_VALUE:
                counts[domain] += 1
        return counts

    def evaluate(self, record: dict[str, str], current_count: int) -> CapResult:
        domain = normalize_domain(record.get("Company Website"))
        cap = self.cap_for(domain)
        if domain == MISSING_VALUE or cap is None:
            return CapResult(domain, cap, current_count, None, False)
        remaining = max(0, cap - current_count)
        return CapResult(domain, cap, current_count, remaining, current_count >= cap)
