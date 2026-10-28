from __future__ import annotations

from collections import OrderedDict
from typing import Any, Iterable

from app.ai.ai_service import LocalAIService
from app.ai.structured_output import clamp_confidence


class AINormalizationAgent:
    """Normalize unique values in small batches to keep local Qwen efficient."""

    def __init__(self, ai: LocalAIService, *, batch_size: int = 24) -> None:
        self.ai = ai
        self.batch_size = max(4, min(int(batch_size), 50))

    def normalize_unique(self, field_name: str, values: Iterable[object], *, limit: int = 5000) -> dict[str, dict[str, Any]]:
        unique: OrderedDict[str, str] = OrderedDict()
        for value in values:
            raw = str(value or "").strip()
            if not raw or raw == "-":
                continue
            key = " ".join(raw.casefold().split())
            unique.setdefault(key, raw)
            if len(unique) >= limit:
                break

        result: dict[str, dict[str, Any]] = {}
        knowledge_type = f"normalize:{field_name.casefold()}"
        pending: list[str] = []
        for raw in unique.values():
            known = self.ai.knowledge.get(knowledge_type, raw)
            if known:
                result[raw] = known
            else:
                pending.append(raw)

        for start in range(0, len(pending), self.batch_size):
            batch = pending[start : start + self.batch_size]
            response = self.ai.run_json("normalize_value", {"field": field_name, "values": batch})
            items = response.get("items") if isinstance(response.get("items"), list) else []
            mapped = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                raw = str(item.get("input") or "").strip()
                if not raw:
                    continue
                item = dict(item)
                item["confidence"] = clamp_confidence(item.get("confidence"))
                mapped[" ".join(raw.casefold().split())] = item
            # Explicit fallback entries make missing model outputs visible instead of silently disappearing.
            for raw in batch:
                key = " ".join(raw.casefold().split())
                result[raw] = mapped.get(key, {
                    "input": raw,
                    "normalized_value": raw,
                    "confidence": 0.0,
                    "reason": "Qwen did not return a structured mapping for this value.",
                    "job_level": "-",
                    "job_function": "-",
                })
        return result
