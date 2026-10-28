from __future__ import annotations

from typing import Any

from app.ai.ai_service import LocalAIService
from app.ai.structured_output import clamp_confidence
from app.core.campaign_models import CampaignRule, RuleSource


class AIRuleBuilder:
    def __init__(self, ai: LocalAIService) -> None:
        self.ai = ai

    def build(self, instruction: str) -> list[CampaignRule]:
        result = self.ai.run_json("rule_builder", {"instruction": instruction})
        rules: list[CampaignRule] = []
        for item in result.get("rules", []) if isinstance(result.get("rules"), list) else []:
            if not isinstance(item, dict) or not str(item.get("field") or "").strip():
                continue
            confidence = clamp_confidence(item.get("confidence"))
            review = bool(item.get("review_required", False)) or confidence < self.ai.config.minimum_confidence
            rules.append(
                CampaignRule(
                    category=str(item.get("category") or "AI Rule Builder"),
                    field=str(item.get("field")),
                    operator=str(item.get("operator") or "equals"),
                    value=item.get("value"),
                    confidence=confidence,
                    status="Needs Review" if review else "Extracted",
                    notes=str(item.get("reason") or "Generated from user instruction"),
                    sources=[RuleSource("Manual AI Rule Builder", "User instruction", instruction[:500])],
                )
            )
        return rules
