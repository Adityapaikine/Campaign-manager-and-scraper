from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.services.search_provider import configured_provider_names
from app.utils.config import CACHE_DIR, CHECKPOINT_DIR, DB_PATH, EXPORT_DIR, LOG_DIR, PROJECT_ROOT, ensure_directories


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    status: str
    detail: str


REQUIRED_PACKAGES = (
    "PySide6", "pandas", "openpyxl", "httpx", "requests", "beautifulsoup4",
    "rapidfuzz", "tldextract", "dnspython", "email-validator", "python-docx",
)


def _dir_check(label: str, path: Path) -> DiagnosticCheck:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".lead_manager_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return DiagnosticCheck(label, "PASS", f"Writable: {path}")
    except Exception as exc:
        return DiagnosticCheck(label, "FAIL", f"{path} — {exc}")


def run_diagnostics(packages: Iterable[str] = REQUIRED_PACKAGES) -> list[DiagnosticCheck]:
    ensure_directories()
    checks: list[DiagnosticCheck] = [
        DiagnosticCheck("Application", "INFO", "B2B Lead Manager — Qt Professional Edition"),
        DiagnosticCheck("Python", "PASS" if sys.version_info >= (3, 10) else "WARN", sys.version.split()[0]),
        DiagnosticCheck("Operating System", "INFO", f"{platform.system()} {platform.release()} ({platform.machine()})"),
        DiagnosticCheck("Project Path", "INFO", str(PROJECT_ROOT)),
    ]
    checks.extend([
        _dir_check("Logs directory", LOG_DIR),
        _dir_check("Exports directory", EXPORT_DIR),
        _dir_check("Cache directory", CACHE_DIR),
        _dir_check("Checkpoints directory", CHECKPOINT_DIR),
    ])
    try:
        with sqlite3.connect(DB_PATH) as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        checks.append(DiagnosticCheck("SQLite database", "PASS" if integrity == "ok" else "FAIL", f"Integrity: {integrity}; tables: {tables}"))
    except Exception as exc:
        checks.append(DiagnosticCheck("SQLite database", "FAIL", str(exc)))

    for package in packages:
        try:
            version = importlib.metadata.version(package)
            checks.append(DiagnosticCheck(f"Package: {package}", "PASS", version))
        except importlib.metadata.PackageNotFoundError:
            checks.append(DiagnosticCheck(f"Package: {package}", "FAIL", "Not installed"))

    providers = configured_provider_names()
    checks.append(DiagnosticCheck(
        "Search providers",
        "INFO",
        ", ".join(providers) if providers else "No API provider configured; local/cached email logic remains available",
    ))
    return checks


def diagnostics_report() -> str:
    checks = run_diagnostics()
    lines = [
        "B2B Lead Manager — Diagnostic Report",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
    ]
    for check in checks:
        lines.append(f"[{check.status}] {check.name}: {check.detail}")
    return "\n".join(lines)


def diagnostics_json() -> str:
    return json.dumps([asdict(item) for item in run_diagnostics()], indent=2, ensure_ascii=False)
