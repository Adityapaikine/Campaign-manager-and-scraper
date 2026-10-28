from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.constants import MISSING_VALUE
from app.core.cache_db import initialize_database
from app.core.normalizer import normalize_domain
from app.utils.config import DB_PATH


@dataclass(frozen=True, slots=True)
class EmailDiscoveryCacheEntry:
    domain: str
    provider: str
    status: str
    pattern: str | None = None
    confidence: int = 0
    evidence_count: int = 0
    query_count: int = 0
    sources: tuple[str, ...] = ()
    reason: str = ""
    last_checked: str | None = None

    def is_fresh(self, max_age_days: int) -> bool:
        if not self.last_checked:
            return False
        try:
            checked = datetime.fromisoformat(self.last_checked.replace("Z", "+00:00"))
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return datetime.now(timezone.utc) - checked <= timedelta(days=max(0, max_age_days))


class EmailDiscoveryCache:
    """Persistent positive and negative cache for Phase-5 web discovery."""

    def __init__(self) -> None:
        initialize_database()

    def get(self, domain: object, provider: str) -> EmailDiscoveryCacheEntry | None:
        normalized = normalize_domain(domain)
        if normalized == MISSING_VALUE:
            return None
        provider_key = (provider or "Unknown").strip()
        with closing(sqlite3.connect(DB_PATH)) as conn, conn:
            row = conn.execute(
                """
                SELECT domain, provider, status, pattern, confidence, evidence_count,
                       query_count, sources_json, reason, last_checked
                FROM email_discovery_cache
                WHERE domain = ? AND provider = ?
                """,
                (normalized, provider_key),
            ).fetchone()
        if not row:
            return None
        try:
            sources = tuple(json.loads(row[7] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            sources = ()
        return EmailDiscoveryCacheEntry(
            domain=row[0],
            provider=row[1],
            status=row[2],
            pattern=row[3],
            confidence=int(round(float(row[4] or 0))),
            evidence_count=int(row[5] or 0),
            query_count=int(row[6] or 0),
            sources=sources,
            reason=row[8] or "",
            last_checked=row[9],
        )

    def upsert(self, entry: EmailDiscoveryCacheEntry) -> EmailDiscoveryCacheEntry:
        normalized = normalize_domain(entry.domain)
        if normalized == MISSING_VALUE:
            raise ValueError("A valid domain is required for discovery cache")
        provider = (entry.provider or "Unknown").strip()
        checked = entry.last_checked or datetime.now(timezone.utc).isoformat(timespec="seconds")
        confidence = max(0, min(100, int(round(entry.confidence))))
        sources_json = json.dumps(list(dict.fromkeys(entry.sources)), ensure_ascii=False)
        with closing(sqlite3.connect(DB_PATH)) as conn, conn:
            conn.execute(
                """
                INSERT INTO email_discovery_cache
                    (domain, provider, status, pattern, confidence, evidence_count,
                     query_count, sources_json, reason, last_checked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain, provider) DO UPDATE SET
                    status=excluded.status,
                    pattern=excluded.pattern,
                    confidence=excluded.confidence,
                    evidence_count=excluded.evidence_count,
                    query_count=excluded.query_count,
                    sources_json=excluded.sources_json,
                    reason=excluded.reason,
                    last_checked=excluded.last_checked
                """,
                (
                    normalized,
                    provider,
                    entry.status,
                    entry.pattern,
                    confidence,
                    max(0, int(entry.evidence_count)),
                    max(0, int(entry.query_count)),
                    sources_json,
                    entry.reason,
                    checked,
                ),
            )
            conn.commit()
        return EmailDiscoveryCacheEntry(
            domain=normalized,
            provider=provider,
            status=entry.status,
            pattern=entry.pattern,
            confidence=confidence,
            evidence_count=max(0, int(entry.evidence_count)),
            query_count=max(0, int(entry.query_count)),
            sources=tuple(dict.fromkeys(entry.sources)),
            reason=entry.reason,
            last_checked=checked,
        )

    def clear_domain(self, domain: object) -> None:
        normalized = normalize_domain(domain)
        if normalized == MISSING_VALUE:
            return
        with closing(sqlite3.connect(DB_PATH)) as conn, conn:
            conn.execute("DELETE FROM email_discovery_cache WHERE domain = ?", (normalized,))
            conn.commit()
