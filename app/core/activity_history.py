from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from app.core.cache_db import initialize_database
from app.utils.config import DB_PATH


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    id: int
    event_type: str
    summary: str
    details: dict[str, Any]
    created_at: str


def record_activity(event_type: str, summary: str, details: dict[str, Any] | None = None) -> None:
    initialize_database()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO activity_history(event_type, summary, details_json) VALUES (?, ?, ?)",
            (event_type, summary, json.dumps(details or {}, ensure_ascii=False)),
        )
        conn.commit()


def list_activity(limit: int = 500, event_type: str | None = None) -> list[ActivityEvent]:
    initialize_database()
    sql = "SELECT id, event_type, summary, details_json, created_at FROM activity_history"
    params: list[object] = []
    if event_type and event_type != "All":
        sql += " WHERE event_type = ?"
        params.append(event_type)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(5000, int(limit))))
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    events: list[ActivityEvent] = []
    for row in rows:
        try:
            details = json.loads(row[3] or "{}")
        except json.JSONDecodeError:
            details = {"raw": row[3]}
        events.append(ActivityEvent(row[0], row[1], row[2], details, row[4]))
    return events


def list_audit(limit: int = 1000) -> list[dict[str, object]]:
    initialize_database()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, record_key, field_name, old_value, new_value, reason, confidence, changed_at
            FROM audit_trail ORDER BY id DESC LIMIT ?
            """,
            (max(1, min(10000, int(limit))),),
        ).fetchall()
    keys = ("id", "record_key", "field_name", "old_value", "new_value", "reason", "confidence", "changed_at")
    return [dict(zip(keys, row)) for row in rows]
