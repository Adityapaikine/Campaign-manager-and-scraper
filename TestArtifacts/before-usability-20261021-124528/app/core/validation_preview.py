from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.core.validator import ValidationEngine


@dataclass(slots=True)
class ValidationPreviewResult:
    total: int
    status_counts: dict[str, int] = field(default_factory=dict)
    reason_counts: dict[str, int] = field(default_factory=dict)
    sample_failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return int(self.status_counts.get("Valid", 0) + self.status_counts.get("Valid - Email Generated", 0))

    def to_metrics(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "pass": self.pass_count,
            "statuses": dict(self.status_counts),
            "top_reasons": dict(sorted(self.reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]),
        }


class ValidationPreviewService:
    def simulate(self, records: list[dict[str, str]], validator: ValidationEngine, *, sample_limit: int = 30) -> ValidationPreviewResult:
        # Operate on a snapshot and the same deterministic validator used by production.
        results = validator.validate_records(records)
        statuses: Counter = Counter()
        reasons: Counter = Counter()
        samples: list[dict[str, Any]] = []
        for index, result in enumerate(results):
            statuses[result.final_status] += 1
            for reason in result.reasons:
                reasons[reason] += 1
            if result.final_status not in {"Valid", "Valid - Email Generated"} and len(samples) < sample_limit:
                samples.append({"row": index + 1, "status": result.final_status, "reasons": list(result.reasons)})
        return ValidationPreviewResult(len(records), dict(statuses), dict(reasons), samples)
