from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.core.cache_db import initialize_database
from app.utils.config import DB_PATH


class AIEvidenceStore:
    def __init__(self, *, database=None) -> None:
        self.database = database if database is not None else DB_PATH
        initialize_database(self.database)

    def add(self, *, record_key: str | None, field_name: str, ai_value: object, confidence: float, reason: str, sources: Any = None, model: str = "local-qwen", prompt_version: str = "") -> None:
        with sqlite3.connect(self.database) as conn:
            conn.execute(
                """
                INSERT INTO ai_evidence(record_key, field_name, ai_value, confidence, reason, source_json, model, prompt_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (record_key, field_name, str(ai_value), float(confidence), reason, json.dumps(sources, ensure_ascii=False, default=str), model, prompt_version),
            )
            conn.commit()

    def for_record(self, record_key: str, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.database) as conn:
            rows = conn.execute(
                "SELECT field_name, ai_value, confidence, reason, source_json, model, prompt_version, created_at FROM ai_evidence WHERE record_key=? ORDER BY id DESC LIMIT ?",
                (record_key, int(limit)),
            ).fetchall()
        result = []
        for row in rows:
            try:
                sources = json.loads(row[4]) if row[4] else None
            except json.JSONDecodeError:
                sources = row[4]
            result.append({"field": row[0], "value": row[1], "confidence": row[2], "reason": row[3], "sources": sources, "model": row[5], "prompt_version": row[6], "created_at": row[7]})
        return result
