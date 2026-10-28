from __future__ import annotations

import sqlite3

from app.core.cache_db import initialize_database
from app.utils.config import DB_PATH


def record_audit_change(
    *,
    record_key: str,
    field_name: str,
    old_value: str,
    new_value: str,
    reason: str,
    confidence: float | None = None,
) -> None:
    initialize_database()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO audit_trail
                (record_key, field_name, old_value, new_value, reason, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (record_key, field_name, old_value, new_value, reason, confidence),
        )
        conn.commit()
