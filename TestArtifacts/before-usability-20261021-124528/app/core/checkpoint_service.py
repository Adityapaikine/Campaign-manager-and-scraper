from __future__ import annotations

import gzip
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.config import CHECKPOINT_DIR, DB_PATH, ensure_directories
from app.utils.logger import logger


@dataclass(frozen=True, slots=True)
class CheckpointSnapshot:
    path: Path
    payload: dict[str, Any]

    @property
    def clean_shutdown(self) -> bool:
        return bool(self.payload.get("clean_shutdown", False))

    @property
    def record_count(self) -> int:
        return len(self.payload.get("records") or [])

    @property
    def job(self) -> dict[str, Any]:
        value = self.payload.get("job")
        return value if isinstance(value, dict) else {}


class CheckpointService:
    """Atomic compressed session checkpoints for crash recovery.

    The service intentionally stores only user-owned worksheet/reference/settings
    state. Derived validation objects are recomputed after recovery so checkpoint
    files stay version-tolerant across application upgrades.
    """

    VERSION = 1

    def __init__(self, keep_last: int = 5) -> None:
        ensure_directories()
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        self.keep_last = max(2, int(keep_last))
        self.session_id = uuid.uuid4().hex
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def save(
        self,
        *,
        records: list[dict[str, str]],
        custom_columns: list[str] | None = None,
        row_states: dict[int, str] | None = None,
        validation_reasons: dict[int, list[str]] | None = None,
        references: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
        job: dict[str, Any] | None = None,
        clean_shutdown: bool = False,
        reason: str = "autosave",
    ) -> Path:
        with self._lock:
            created_at = self._now()
            filename = f"session_{created_at.replace(':', '').replace('+', '_')}_{self.session_id[:8]}.json.gz"
            final_path = CHECKPOINT_DIR / filename
            temp_path = final_path.with_suffix(final_path.suffix + ".tmp")
            payload: dict[str, Any] = {
                "version": self.VERSION,
                "session_id": self.session_id,
                "created_at": created_at,
                "clean_shutdown": bool(clean_shutdown),
                "reason": reason,
                "records": records,
                "custom_columns": list(custom_columns or []),
                "row_states": {str(k): v for k, v in (row_states or {}).items()},
                "validation_reasons": {
                    str(k): list(v) for k, v in (validation_reasons or {}).items()
                },
                "references": references or {},
                "settings": settings or {},
                "job": job or {},
            }
            with gzip.open(temp_path, "wt", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            os.replace(temp_path, final_path)
            self._record_db(final_path, len(records), reason)
            self._prune()
            logger.info(
                "Checkpoint saved | file=%s | records=%s | clean=%s | reason=%s",
                final_path.name,
                len(records),
                clean_shutdown,
                reason,
            )
            return final_path

    def _record_db(self, path: Path, count: int, reason: str) -> None:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO session_checkpoints(session_name, checkpoint_file, processed_count) VALUES (?, ?, ?)",
                    (reason, str(path), int(count)),
                )
                conn.commit()
        except Exception:
            # The checkpoint file is the source of truth; DB history is optional.
            logger.exception("Could not record checkpoint history")

    def _prune(self) -> None:
        files = sorted(
            CHECKPOINT_DIR.glob("session_*.json.gz"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in files[self.keep_last :]:
            try:
                path.unlink()
            except OSError:
                logger.warning("Could not prune checkpoint: %s", path)

    @staticmethod
    def load(path: Path) -> CheckpointSnapshot:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        if int(payload.get("version", 0)) != CheckpointService.VERSION:
            raise ValueError("Unsupported checkpoint version")
        return CheckpointSnapshot(path=path, payload=payload)

    def latest(self) -> CheckpointSnapshot | None:
        files = sorted(
            CHECKPOINT_DIR.glob("session_*.json.gz"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in files:
            try:
                return self.load(path)
            except Exception:
                logger.exception("Could not read checkpoint: %s", path)
        return None

    def latest_recoverable(self) -> CheckpointSnapshot | None:
        latest = self.latest()
        if latest is None or latest.clean_shutdown or latest.record_count <= 0:
            return None
        return latest

    def mark_current_session_clean(
        self,
        *,
        records: list[dict[str, str]],
        row_states: dict[int, str] | None = None,
        validation_reasons: dict[int, list[str]] | None = None,
        references: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> Path:
        return self.save(
            records=records,
            row_states=row_states,
            validation_reasons=validation_reasons,
            references=references,
            settings=settings,
            clean_shutdown=True,
            reason="clean-shutdown",
        )
