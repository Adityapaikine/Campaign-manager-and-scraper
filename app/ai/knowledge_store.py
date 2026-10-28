from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.core.cache_db import initialize_database
from app.utils.config import DB_PATH


class LocalKnowledgeStore:
    """Small SQLite knowledge store for human-approved mappings.

    It intentionally avoids embeddings/vector databases to keep the desktop app light.
    Exact normalized keys are fast, deterministic and suitable for approved mappings.
    """

    def __init__(self, *, database=None) -> None:
        self.database = database if database is not None else DB_PATH
        initialize_database(self.database)

    @staticmethod
    def _key(value: object) -> str:
        return " ".join(str(value or "").strip().casefold().split())

    def get(self, knowledge_type: str, input_value: object) -> dict[str, Any] | None:
        key = self._key(input_value)
        with sqlite3.connect(self.database) as conn:
            row = conn.execute(
                "SELECT output_json, confidence, approved, source FROM ai_knowledge WHERE knowledge_type=? AND input_key=?",
                (knowledge_type, key),
            ).fetchone()
        if not row or not row[2]:
            return None
        try:
            output = json.loads(row[0])
        except json.JSONDecodeError:
            output = {"value": row[0]}
        output.setdefault("confidence", float(row[1] or 0))
        output.setdefault("source", row[3])
        output["knowledge_hit"] = True
        return output

    def save(self, knowledge_type: str, input_value: object, output: dict[str, Any], *, confidence: float = 1.0, source: str = "user", approved: bool = True) -> None:
        key = self._key(input_value)
        with sqlite3.connect(self.database) as conn:
            conn.execute(
                """
                INSERT INTO ai_knowledge(knowledge_type, input_key, output_json, confidence, approved, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(knowledge_type, input_key) DO UPDATE SET
                    output_json=excluded.output_json,
                    confidence=excluded.confidence,
                    approved=excluded.approved,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (knowledge_type, key, json.dumps(output, ensure_ascii=False), float(confidence), int(bool(approved)), source),
            )
            conn.commit()

    def list(self, knowledge_type: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        sql = "SELECT id, knowledge_type, input_key, output_json, confidence, approved, source, updated_at FROM ai_knowledge"
        params: tuple[Any, ...] = ()
        if knowledge_type:
            sql += " WHERE knowledge_type=?"
            params = (knowledge_type,)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params += (int(limit),)
        with sqlite3.connect(self.database) as conn:
            rows = conn.execute(sql, params).fetchall()
        result = []
        for row in rows:
            try:
                output = json.loads(row[3])
            except json.JSONDecodeError:
                output = {"value": row[3]}
            result.append({"id": row[0], "type": row[1], "input": row[2], "output": output, "confidence": row[4], "approved": bool(row[5]), "source": row[6], "updated_at": row[7]})
        return result
