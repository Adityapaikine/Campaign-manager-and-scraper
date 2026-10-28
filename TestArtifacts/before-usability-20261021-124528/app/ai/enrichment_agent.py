from __future__ import annotations

from typing import Any

from app.ai.ai_service import LocalAIService
from app.ai.structured_output import clamp_confidence
from app.constants import MISSING_VALUE


class AIEnrichmentAgent:
    """Evidence-bound local inference. No external facts are fabricated."""

    CANDIDATE_FIELDS = ("Job Level", "Job Function", "Industry", "Company Size", "Revenue", "City", "State", "Country", "SIC Code", "NAICS Code")

    def __init__(self, ai: LocalAIService) -> None:
        self.ai = ai

    def suggest(self, record: dict[str, str]) -> dict[str, dict[str, Any]]:
        missing = [field for field in self.CANDIDATE_FIELDS if str(record.get(field, MISSING_VALUE)).strip() in {"", MISSING_VALUE}]
        if not missing:
            return {}
        evidence = {k: v for k, v in record.items() if str(v).strip() not in {"", MISSING_VALUE} and k in {
            "First Name", "Last Name", "Job Title", "Company Name", "Company Website", "Industry", "Company Size", "Revenue", "Address", "City", "State", "Country"
        }}
        response = self.ai.run_json("enrich_record", {"missing_fields": missing, "evidence": evidence})
        suggestions = response.get("suggestions") if isinstance(response.get("suggestions"), dict) else {}
        clean: dict[str, dict[str, Any]] = {}
        for field, item in suggestions.items():
            if field not in missing or not isinstance(item, dict):
                continue
            value = str(item.get("value") or "-").strip() or "-"
            if value == "-":
                continue
            clean[field] = {
                "value": value,
                "confidence": clamp_confidence(item.get("confidence")),
                "reason": str(item.get("reason") or ""),
                "evidence": item.get("evidence"),
            }
        return clean
