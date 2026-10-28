from __future__ import annotations

from typing import Any

from app.ai.ai_service import LocalAIService
from app.ai.structured_output import clamp_confidence
from app.services.search_provider import SearchProvider


class AIResearchAssistant:
    """Optional web-assisted evidence collector using the existing SearchProvider.

    Only search snippets/URLs are sent to local Qwen; Qwen does not browse itself.
    """

    def __init__(self, ai: LocalAIService, provider: SearchProvider) -> None:
        self.ai = ai
        self.provider = provider

    def research_company(self, record: dict[str, str], *, max_results: int = 6) -> dict[str, Any]:
        company = str(record.get("Company Name") or "").strip()
        city = str(record.get("City") or "").strip()
        country = str(record.get("Country") or "").strip()
        if not company or company == "-":
            return {"suggestions": {}, "reason": "Company Name is required"}
        query = " ".join(part for part in (company, city if city != "-" else "", country if country != "-" else "", "company official website industry employees revenue") if part)
        results = self.provider.search(query, count=max_results)
        evidence = [
            {"title": r.title, "url": r.url, "snippet": r.snippet, "provider": r.provider}
            for r in results
        ]
        response = self.ai.run_json("research_company", {"record": record, "search_evidence": evidence})
        suggestions = response.get("suggestions") if isinstance(response.get("suggestions"), dict) else {}
        for item in suggestions.values():
            if isinstance(item, dict):
                item["confidence"] = clamp_confidence(item.get("confidence"))
        response["search_evidence"] = evidence
        return response
