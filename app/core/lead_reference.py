"""Local, exact-key lead lookups. Reference data never changes during population."""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote, urlsplit

from app.constants import MISSING_VALUE, STANDARD_HEADERS
from app.core.normalizer import clean_text, is_valid_domain, normalize_domain
from app.utils.config import DB_PATH


TABLE_NAME = "lead_reference"
PROSPECT_KEY = "Prospect LinkedIn Link"
COMPANY_KEY = "Company Website"
PROSPECT_FIELDS = (
    "Business Email ID", "Job Title", "Job Level", "Job Function", "Address", "City",
    "State", "Zip Code", "Address Link", "Country", "Phone Number", "Phone Number Link",
)
COMPANY_FIELDS = (
    "Company Name", "Company Website", "Industry", "Company Size", "Industry Link",
    "Revenue", "Revenue Link", "SIC Code", "NAICS Code", "SIC/NAICS Code Link",
)
POPULATABLE_FIELDS = PROSPECT_FIELDS + COMPANY_FIELDS


def _url(value):
    text = clean_text(value)
    if text == MISSING_VALUE:
        return None
    try:
        parsed = urlsplit(text if "://" in text else "https://" + text.removeprefix("//"))
        if parsed.scheme.casefold() not in {"http", "https"} or parsed.username or parsed.password:
            return None
        _ = parsed.port  # Reject invalid ports instead of accidentally matching a host.
        return parsed
    except ValueError:
        return None


def prospect_key(value):
    parsed = _url(value)
    if parsed is None:
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    path = unquote(parsed.path).rstrip("/")
    if (host == "linkedin.com" or host.endswith(".linkedin.com")) and re.fullmatch(r"/in/[^/\s]+", path, re.I):
        return path.casefold()
    return None


def company_key(value):
    parsed = _url(value)
    if parsed is None:
        return None
    domain = normalize_domain(parsed.hostname)
    return domain if is_valid_domain(domain) else None


def _quote(name):
    if not isinstance(name, str) or not name.strip() or "\x00" in name:
        raise ValueError("The reference database contains an invalid column name.")
    return '"' + name.replace('"', '""') + '"'


def _value(value):
    # Preserve text such as leading zeroes in postal/SIC/NAICS codes.
    return MISSING_VALUE if clean_text(value) == MISSING_VALUE else str(value)


def _has_content(record):
    metadata = {"Date", "Source File Name", "QA Status", "Primary Reason", "Audited Date", "QA Name"}
    return any(clean_text(value) != MISSING_VALUE for key, value in record.items() if key not in metadata)


@dataclass
class ReferenceInfo:
    path: Path | str
    count: int | None
    added: int = 0
    skipped: int = 0
    label: str = "Local database"
    table: str = TABLE_NAME
    available_fields: tuple[str, ...] = POPULATABLE_FIELDS


@dataclass
class PopulationPlan:
    workspace_key: str
    records: list[dict[str, str]]
    columns: tuple[str, ...]
    row_indices: tuple[int, ...]
    overwrite: bool
    edits: dict[tuple[int, str], str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=lambda: {
        "existing": 0, "invalid_key": 0, "unmatched": 0, "empty_source": 0,
        "conflict": 0, "unchanged": 0,
    })
    issues: list[str] = field(default_factory=list)

    @property
    def updated_rows(self):
        return len({row for row, _ in self.edits})

    def summary(self):
        return f"Populated {len(self.edits):,} cells in {self.updated_rows:,} of {len(self.row_indices):,} leads."

    def details(self):
        labels = {
            "existing": "Existing values kept", "invalid_key": "Missing or invalid match key",
            "unmatched": "No matching database record", "empty_source": "No saved value for this column",
            "conflict": "Conflicting database values", "unchanged": "Already the same value",
        }
        lines = ["Columns: " + ", ".join(self.columns), "", "Cells left unchanged:"]
        lines.extend(f"{label}: {self.counts[key]:,}" for key, label in labels.items())
        if self.issues:
            lines.extend(["", "Skipped cells (first 200):", *self.issues])
        return "\n".join(lines)


class LeadLookup:
    def plan(self, records, columns, row_indices, *, workspace_key, overwrite=False):
        records = [dict(record) for record in records]
        columns = tuple(dict.fromkeys(columns))
        if not columns or any(column not in POPULATABLE_FIELDS for column in columns):
            raise ValueError("Choose at least one supported prospect or company column to populate.")
        indices = tuple(sorted(set(row_indices)))
        if not indices or any(not isinstance(i, int) or i < 0 or i >= len(records) for i in indices):
            raise ValueError("Choose existing leads to populate.")
        plan = PopulationPlan(workspace_key, records, columns, indices, bool(overwrite))
        groups = ((PROSPECT_KEY, prospect_key, PROSPECT_FIELDS), (COMPANY_KEY, company_key, COMPANY_FIELDS))
        maps = {}
        with self.read_session() as read_rows:
            for key_column, normalizer, fields in groups:
                selected = [column for column in columns if column in fields]
                if not selected:
                    continue
                wanted = {normalizer(records[i].get(key_column)) for i in indices} - {None}
                lookup = {}
                query_columns = list(dict.fromkeys([key_column, *selected]))
                for values in read_rows(query_columns):
                    source = dict(zip(query_columns, values))
                    key = normalizer(source[key_column])
                    if key not in wanted:
                        continue
                    candidates = lookup.setdefault(key, {column: {} for column in selected})
                    for column in selected:
                        value = clean_text(source[column])
                        if value != MISSING_VALUE:
                            comparison = company_key(value) if column == COMPANY_KEY else value.casefold()
                            candidates[column].setdefault(comparison, value)
                maps[key_column] = lookup
        for row in indices:
            record = records[row]
            for column in columns:
                current = clean_text(record.get(column))
                if not overwrite and current != MISSING_VALUE:
                    plan.counts["existing"] += 1
                    continue
                key_column, normalizer, _ = groups[0 if column in PROSPECT_FIELDS else 1]
                key = normalizer(record.get(key_column))
                candidates = maps[key_column].get(key)
                reason = None
                if key is None:
                    reason = "invalid_key"
                elif candidates is None:
                    reason = "unmatched"
                elif not candidates[column]:
                    reason = "empty_source"
                elif len(candidates[column]) > 1:
                    reason = "conflict"
                if reason:
                    plan.counts[reason] += 1
                    if len(plan.issues) < 200:
                        plan.issues.append(f"Lead row {row + 1} · {column}: " + {
                            "invalid_key": f"missing or invalid {key_column}",
                            "unmatched": f"no {key_column} match", "empty_source": "saved value is empty",
                            "conflict": "multiple different saved values; review the reference database",
                        }[reason])
                    continue
                value = next(iter(candidates[column].values()))
                if current == value:
                    plan.counts["unchanged"] += 1
                else:
                    plan.edits[row, column] = value
        return plan


class LeadReferenceStore(LeadLookup):
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DB_PATH

    @staticmethod
    def _headers(connection):
        return [row[1] for row in connection.execute('PRAGMA table_info("lead_reference")')]

    def _ensure_schema(self, connection, headers=()):
        requested = list(STANDARD_HEADERS)
        seen = {name.casefold() for name in requested}
        for name in headers:
            _quote(name)
            if name.casefold() not in seen:
                requested.append(name)
                seen.add(name.casefold())
        definitions = ", ".join(f"{_quote(name)} TEXT DEFAULT '-'" for name in requested)
        connection.execute(f'CREATE TABLE IF NOT EXISTS "{TABLE_NAME}" ({definitions})')
        existing = {name.casefold() for name in self._headers(connection)}
        for name in requested:
            if name.casefold() not in existing:
                connection.execute(f'ALTER TABLE "{TABLE_NAME}" ADD COLUMN {_quote(name)} TEXT DEFAULT \'-\'')
        connection.execute('CREATE TABLE IF NOT EXISTS lead_reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    def _insert(self, connection, records, *, deduplicate):
        headers = self._headers(connection)
        names = ", ".join(map(_quote, headers))
        existing = set()
        if deduplicate:
            existing = {tuple(_value(v) for v in row) for row in connection.execute(f'SELECT {names} FROM "{TABLE_NAME}"')}
        added = skipped = 0
        sql = f'INSERT INTO "{TABLE_NAME}" ({names}) VALUES ({", ".join("?" for _ in headers)})'
        for record in records:
            if not _has_content(record):
                skipped += 1
                continue
            folded = {key.casefold(): value for key, value in record.items()}
            values = tuple(_value(folded.get(name.casefold())) for name in headers)
            if deduplicate and values in existing:
                skipped += 1
                continue
            connection.execute(sql, values)
            existing.add(values)
            added += 1
        total = connection.execute(f'SELECT COUNT(*) FROM "{TABLE_NAME}"').fetchone()[0]
        return ReferenceInfo(self.path, total, added, skipped)

    def seed_workspaces(self, workspace_store, *, active_key=None, active_records=None, active_headers=()):
        """Copy saved worksheets once, atomically. Retain any existing reference rows."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=20)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_schema(connection, active_headers)
            if connection.execute("SELECT 1 FROM lead_reference_meta WHERE key='workspace_seed_v1'").fetchone():
                return ReferenceInfo(self.path, connection.execute(f'SELECT COUNT(*) FROM "{TABLE_NAME}"').fetchone()[0])
            records, headers = [], list(active_headers)
            if workspace_store.folder.exists():
                for folder in sorted(workspace_store.folder.iterdir()):
                    if not folder.is_dir() or not (folder / "worksheet.json.gz").exists():
                        continue
                    if folder.name == active_key and active_records is not None:
                        continue
                    payload = workspace_store.load(folder.name)
                    records.extend(payload["records"])
                    headers.extend(payload.get("custom_columns", []))
            if active_records is not None:
                records.extend(active_records)
            self._ensure_schema(connection, headers)
            has_rows = bool(connection.execute(f'SELECT 1 FROM "{TABLE_NAME}" LIMIT 1').fetchone())
            info = self._insert(connection, records, deduplicate=has_rows)
            connection.execute("INSERT INTO lead_reference_meta(key,value) VALUES ('workspace_seed_v1',datetime('now'))")
            return info

    def add_records(self, records, headers=()):
        """Explicit, additive copy. Never replace a saved reference value silently."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=20)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_schema(connection, headers)
            return self._insert(connection, records, deduplicate=True)

    @contextmanager
    def read_session(self):
        # Read-only connections cannot accidentally create an empty source database.
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=20)) as connection:
            connection.execute("BEGIN")
            def read_rows(columns):
                return connection.execute(f'SELECT {", ".join(map(_quote, columns))} FROM "{TABLE_NAME}"')
            yield read_rows
