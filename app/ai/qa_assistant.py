from __future__ import annotations

from typing import Any

from app.ai.ai_service import LocalAIService


class AIQAAssistant:
    def __init__(self, ai: LocalAIService) -> None:
        self.ai = ai

    def review(self, record: dict[str, str], *, status: str | None = None, reasons: list[str] | None = None, campaign_rules: list[dict] | None = None) -> dict[str, Any]:
        return self.ai.run_json(
            "qa_review",
            {"record": record, "validation_status": status, "validation_reasons": reasons or [], "campaign_rules": campaign_rules or []},
        )

    def explain_validation(self, record: dict[str, str], *, status: str | None, reasons: list[str]) -> dict[str, Any]:
        return self.ai.run_json(
            "validation_explanation",
            {"record": record, "validation_status": status, "validation_reasons": reasons},
        )

    def compare_duplicates(self, left: dict[str, str], right: dict[str, str]) -> dict[str, Any]:
        return self.ai.run_json("duplicate_review", {"record_a": left, "record_b": right})
