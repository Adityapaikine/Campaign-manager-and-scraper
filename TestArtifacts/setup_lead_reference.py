"""One-time local setup and verification; prints counts only, never lead values."""
from collections import Counter
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from suite_bootstrap import configure
configure()
from app.constants import STANDARD_HEADERS
from app.core.lead_reference import LeadReferenceStore, _has_content, _value, company_key, prospect_key
from app.core.workspace_store import WorkspaceStore
from app.utils.config import DB_PATH


workspace = WorkspaceStore()
paths = sorted(workspace.folder.glob("*/worksheet.json.gz"))
before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup = ROOT / "TestArtifacts" / f"database-before-lookup-{stamp}.sqlite3"
with closing(sqlite3.connect(DB_PATH)) as db, closing(sqlite3.connect(backup)) as target:
    db.backup(target)
    old_tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    old_counts = {table: db.execute('SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0] for table in old_tables}
store = LeadReferenceStore()
info = store.seed_workspaces(workspace)
source_rows = []
for path in paths:
    source_rows.extend(workspace.load(path.parent.name)["records"])
with closing(sqlite3.connect(DB_PATH)) as db:
    columns = [r[1] for r in db.execute("PRAGMA table_info(lead_reference)")]
    saved = list(db.execute("SELECT * FROM lead_reference"))
    expected = Counter(tuple(_value(row.get(column)) for column in columns) for row in source_rows if _has_content(row))
    copied = Counter(saved)
    counts_unchanged = all(db.execute('SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0] == count for table, count in old_counts.items())
    integrity = db.execute("PRAGMA quick_check").fetchone()[0]
report = {
    "database": str(DB_PATH), "table": "lead_reference", "backup": str(backup),
    "saved_workspaces": len(paths), "source_rows": len(source_rows), "reference_rows": info.count,
    "inserted": info.added, "columns": len(columns), "standard_headers_match": columns[:len(STANDARD_HEADERS)] == list(STANDARD_HEADERS),
    "all_saved_rows_match": expected == copied,
    "worksheet_files_unchanged": before == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
    "existing_table_counts_unchanged": counts_unchanged, "sqlite_quick_check": integrity,
    "usable_prospect_keys": sum(prospect_key(row.get("Prospect LinkedIn Link")) is not None for row in source_rows),
    "usable_company_keys": sum(company_key(row.get("Company Website")) is not None for row in source_rows),
}
report_path = ROOT / "TestArtifacts" / "lead_reference_setup.json"
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
assert report["all_saved_rows_match"] and report["worksheet_files_unchanged"]
assert report["existing_table_counts_unchanged"] and integrity == "ok"
