from __future__ import annotations

import json
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Qwen response must be a JSON object")
    return result


def clamp_confidence(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number > 1.0 and number <= 100:
        number /= 100.0
    return max(0.0, min(1.0, number))
