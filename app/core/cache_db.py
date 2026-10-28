from __future__ import annotations

import sqlite3
from contextlib import closing

from app.utils.config import DB_PATH, ensure_directories

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_pattern_cache (
    domain TEXT PRIMARY KEY,
    pattern TEXT,
    confidence REAL,
    source TEXT,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    mx_valid INTEGER,
    last_checked TEXT
);

CREATE TABLE IF NOT EXISTS email_discovery_cache (
    domain TEXT NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    pattern TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    query_count INTEGER NOT NULL DEFAULT 0,
    sources_json TEXT,
    reason TEXT,
    last_checked TEXT NOT NULL,
    PRIMARY KEY (domain, provider)
);

CREATE TABLE IF NOT EXISTS company_cache (
    domain TEXT PRIMARY KEY,
    company_name TEXT,
    payload_json TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mapping_templates (
    name TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'lead',
    source_signature TEXT NOT NULL DEFAULT '',
    mapping_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name TEXT NOT NULL,
    checkpoint_file TEXT NOT NULL,
    processed_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_trail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_key TEXT,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    confidence REAL,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS campaign_profiles (
    campaign_id TEXT PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    source_root TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaign_tracking (
    campaign_id TEXT PRIMARY KEY,
    allocation INTEGER CHECK(allocation IS NULL OR allocation >= 0),
    start_date TEXT,
    end_date TEXT,
    delivered INTEGER CHECK(delivered IS NULL OR delivered >= 0),
    status TEXT CHECK(status IS NULL OR status IN ('Running', 'Closed', 'Paused')),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_response_cache (
    cache_key TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_type TEXT NOT NULL,
    input_key TEXT NOT NULL,
    output_json TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1,
    approved INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'user',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(knowledge_type, input_key)
);

CREATE TABLE IF NOT EXISTS ai_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_key TEXT,
    field_name TEXT NOT NULL,
    ai_value TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    reason TEXT,
    source_json TEXT,
    model TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    qwen_calls INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'completed',
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate_mapping_templates(conn: sqlite3.Connection) -> None:
    """Bring Phase-1/6 mapping_templates tables forward without losing data."""
    columns = _column_names(conn, "mapping_templates")
    if "kind" not in columns:
        conn.execute("ALTER TABLE mapping_templates ADD COLUMN kind TEXT NOT NULL DEFAULT 'lead'")
    if "source_signature" not in columns:
        conn.execute("ALTER TABLE mapping_templates ADD COLUMN source_signature TEXT NOT NULL DEFAULT ''")


def initialize_database(database=None) -> None:
    if database is None:
        ensure_directories()
    else:
        from pathlib import Path
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database if database is not None else DB_PATH)) as conn:
        conn.executescript(SCHEMA)
        _migrate_mapping_templates(conn)
        conn.commit()
