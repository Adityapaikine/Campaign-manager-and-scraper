from __future__ import annotations

from typing import Any

from app.ai.ai_service import LocalAIService


class AICampaignIntelligence:
    def __init__(self, ai: LocalAIService) -> None:
        self.ai = ai

    def insights(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return self.ai.run_json("campaign_insights", {"metrics": metrics})

    def management_report(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return self.ai.run_json("management_report", {"metrics": metrics})
