from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.core.cache_db import initialize_database
from app.utils.config import DB_PATH


class SettingsService:
    """Persist application preferences in the local SQLite database.

    Values are JSON encoded so booleans/integers are restored with their original
    types. The service never stores API secrets; provider keys remain in .env.
    """

    def __init__(self) -> None:
        initialize_database()

    def get(self, key: str, default: Any = None) -> Any:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return row[0]

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, payload),
            )
            conn.commit()

    def update_many(self, values: dict[str, Any]) -> None:
        if not values:
            return
        rows = [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()]
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            conn.commit()

    def all(self) -> dict[str, Any]:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT key, value FROM app_settings ORDER BY key").fetchall()
        result: dict[str, Any] = {}
        for key, value in rows:
            try:
                result[key] = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                result[key] = value
        return result

    def delete(self, key: str) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
            conn.commit()
