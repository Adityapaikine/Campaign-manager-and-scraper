from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from app.core.cache_db import initialize_database
from app.utils.config import DB_PATH


def stable_payload_hash(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8", errors="replace")).hexdigest()


class AIResponseCache:
    def __init__(self) -> None:
        initialize_database()

    def get(self, *, task: str, prompt_version: str, payload: Any, max_age_days: int = 180) -> dict | None:
        payload_hash = stable_payload_hash(payload)
        cache_key = f"{task}:{prompt_version}:{payload_hash}"
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT response_json, updated_at FROM ai_response_cache WHERE cache_key=?",
                (cache_key,),
            ).fetchone()
        if not row:
            return None
        if max_age_days >= 0:
            try:
                updated = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00"))
                if datetime.now(updated.tzinfo) - updated > timedelta(days=max_age_days):
                    return None
            except Exception:
                pass
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    def set(self, *, task: str, prompt_version: str, payload: Any, response: dict, confidence: float = 0.0) -> None:
        payload_hash = stable_payload_hash(payload)
        cache_key = f"{task}:{prompt_version}:{payload_hash}"
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO ai_response_cache(cache_key, task, prompt_version, payload_hash, response_json, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(cache_key) DO UPDATE SET
                    response_json=excluded.response_json,
                    confidence=excluded.confidence,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (cache_key, task, prompt_version, payload_hash, json.dumps(response, ensure_ascii=False), float(confidence)),
            )
            conn.commit()

    def clear(self) -> int:
        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute("SELECT COUNT(*) FROM ai_response_cache").fetchone()[0]
            conn.execute("DELETE FROM ai_response_cache")
            conn.commit()
        return int(count or 0)
