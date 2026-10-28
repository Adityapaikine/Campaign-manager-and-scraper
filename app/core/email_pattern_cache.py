from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

from app.constants import MISSING_VALUE
from app.core.cache_db import initialize_database
from app.core.normalizer import normalize_domain
from app.utils.config import DB_PATH


@dataclass(frozen=True, slots=True)
class EmailPatternCacheEntry:
    domain: str
    pattern: str
    confidence: int
    source: str
    evidence_count: int = 0
    mx_valid: bool | None = None
    last_checked: str | None = None


class EmailPatternCache:
    def __init__(self, *, database=None) -> None:
        self.database = database if database is not None else DB_PATH
        initialize_database(self.database)

    def get_many(self, domains):
        keys = list(dict.fromkeys(normalize_domain(domain) for domain in domains))
        results = {key: None for key in keys}
        with closing(sqlite3.connect(self.database)) as conn:
            for offset in range(0, len(keys), 500):
                batch = keys[offset:offset+500]
                placeholders = ','.join('?' for _ in batch)
                for row in conn.execute(f'SELECT domain,pattern,confidence,source,evidence_count,mx_valid,last_checked FROM email_pattern_cache WHERE domain IN ({placeholders})', batch):
                    if row[1]:
                        results[row[0]] = EmailPatternCacheEntry(row[0], row[1], int(round(float(row[2] or 0))),
                            row[3] or 'Cached pattern', int(row[4] or 0), None if row[5] is None else bool(row[5]), row[6])
        return results

    def get(self, domain: object) -> EmailPatternCacheEntry | None:
        normalized = normalize_domain(domain)
        if normalized == MISSING_VALUE:
            return None
        with closing(sqlite3.connect(self.database)) as conn, conn:
            row = conn.execute(
                """
                SELECT domain, pattern, confidence, source, evidence_count, mx_valid, last_checked
                FROM email_pattern_cache WHERE domain = ?
                """,
                (normalized,),
            ).fetchone()
        if not row or not row[1]:
            return None
        mx_value = None if row[5] is None else bool(row[5])
        return EmailPatternCacheEntry(
            domain=row[0],
            pattern=row[1],
            confidence=int(round(float(row[2] or 0))),
            source=row[3] or "Cached pattern",
            evidence_count=int(row[4] or 0),
            mx_valid=mx_value,
            last_checked=row[6],
        )

    def upsert(self, entry: EmailPatternCacheEntry) -> EmailPatternCacheEntry:
        normalized = normalize_domain(entry.domain)
        if normalized == MISSING_VALUE:
            raise ValueError("A valid domain is required for email-pattern cache")
        checked = entry.last_checked or datetime.now(timezone.utc).isoformat(timespec="seconds")
        confidence = max(0, min(100, int(round(entry.confidence))))
        mx_value = None if entry.mx_valid is None else int(bool(entry.mx_valid))
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.execute(
                """
                INSERT INTO email_pattern_cache
                    (domain, pattern, confidence, source, evidence_count, mx_valid, last_checked)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    pattern=excluded.pattern,
                    confidence=excluded.confidence,
                    source=excluded.source,
                    evidence_count=excluded.evidence_count,
                    mx_valid=excluded.mx_valid,
                    last_checked=excluded.last_checked
                """,
                (
                    normalized,
                    entry.pattern,
                    confidence,
                    entry.source,
                    max(0, int(entry.evidence_count)),
                    mx_value,
                    checked,
                ),
            )
            conn.commit()
        return EmailPatternCacheEntry(
            domain=normalized,
            pattern=entry.pattern,
            confidence=confidence,
            source=entry.source,
            evidence_count=max(0, int(entry.evidence_count)),
            mx_valid=entry.mx_valid,
            last_checked=checked,
        )

    def clear_domain(self, domain: object) -> None:
        normalized = normalize_domain(domain)
        if normalized == MISSING_VALUE:
            return
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.execute("DELETE FROM email_pattern_cache WHERE domain = ?", (normalized,))
            conn.commit()
