from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from app.core.cache_db import initialize_database
from app.utils.config import DB_PATH
from app.utils.text_utils import normalize_header


@dataclass(frozen=True, slots=True)
class MappingTemplate:
    name: str
    kind: str
    mapping: dict[str, str]
    source_signature: str
    updated_at: str


class MappingTemplateService:
    """Persistent mapping templates for lead, TAL and suppression imports."""

    VALID_KINDS = {"lead", "tal", "suppression"}

    def __init__(self) -> None:
        initialize_database()

    @staticmethod
    def signature(columns: list[str]) -> str:
        return "|".join(sorted(normalize_header(column) for column in columns if str(column).strip()))

    def save(
        self,
        *,
        name: str,
        kind: str,
        mapping: dict[str, str],
        source_columns: list[str] | None = None,
    ) -> None:
        name = name.strip()
        kind = kind.strip().lower()
        if not name:
            raise ValueError("Template name is required.")
        if kind not in self.VALID_KINDS:
            raise ValueError(f"Unsupported template kind: {kind}")
        if not mapping:
            raise ValueError("A mapping template cannot be empty.")
        existing = self.get(name)
        if existing is not None and existing.kind != kind:
            raise ValueError(
                f"Template name '{name}' is already used for {existing.kind}. "
                "Choose a different name for this mapping type."
            )
        signature = self.signature(source_columns or list(mapping))
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO mapping_templates(name, kind, source_signature, mapping_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    kind = excluded.kind,
                    source_signature = excluded.source_signature,
                    mapping_json = excluded.mapping_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, kind, signature, json.dumps(mapping, ensure_ascii=False, sort_keys=True)),
            )
            conn.commit()

    def get(self, name: str) -> MappingTemplate | None:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT name, kind, source_signature, mapping_json, updated_at FROM mapping_templates WHERE name = ?",
                (name,),
            ).fetchone()
        if row is None:
            return None
        return MappingTemplate(
            name=row[0],
            kind=row[1] or "lead",
            source_signature=row[2] or "",
            mapping=json.loads(row[3]),
            updated_at=row[4] or "",
        )

    def list(self, kind: str | None = None) -> list[MappingTemplate]:
        sql = "SELECT name, kind, source_signature, mapping_json, updated_at FROM mapping_templates"
        params: tuple[str, ...] = ()
        if kind:
            sql += " WHERE kind = ?"
            params = (kind.lower(),)
        sql += " ORDER BY name COLLATE NOCASE"
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(sql, params).fetchall()
        result: list[MappingTemplate] = []
        for row in rows:
            try:
                mapping = json.loads(row[3])
            except json.JSONDecodeError:
                continue
            result.append(
                MappingTemplate(
                    name=row[0],
                    kind=row[1] or "lead",
                    source_signature=row[2] or "",
                    mapping=mapping,
                    updated_at=row[4] or "",
                )
            )
        return result

    def best_match(self, *, kind: str, columns: list[str]) -> MappingTemplate | None:
        signature = self.signature(columns)
        for template in self.list(kind):
            if template.source_signature and template.source_signature == signature:
                return template
        return None

    def delete(self, name: str) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM mapping_templates WHERE name = ?", (name,))
            conn.commit()

    def rename(self, old_name: str, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Template name is required.")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE mapping_templates SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?", (new_name, old_name))
            conn.commit()
