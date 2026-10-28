"""Atomic, portable worksheet snapshots, isolated by campaign."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile

from app.utils.config import DATA_DIR


class WorkspaceStore:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder is not None else DATA_DIR / "workspaces"

    @staticmethod
    def key(campaign_id=None):
        return "general" if not campaign_id else "campaign-" + hashlib.sha256(str(campaign_id).encode()).hexdigest()[:20]

    def directory(self, key):
        if key != "general" and (not key.startswith("campaign-") or len(key) != 29 or not all(c in "0123456789abcdef" for c in key[9:])):
            raise ValueError("Invalid workspace identifier")
        return self.folder / key

    def load(self, key):
        path = self.directory(key) / "worksheet.json.gz"
        if not path.exists():
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            if payload.get("version") != 1 or not isinstance(payload.get("records"), list):
                raise ValueError("Invalid workspace data")
            if not all(isinstance(row, dict) for row in payload["records"]):
                raise ValueError("Invalid worksheet rows")
            return payload
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise ValueError("This saved workspace could not be opened. Its existing files have been preserved.") from exc

    def save(self, key, payload):
        folder = self.directory(key)
        folder.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="worksheet-", suffix=".tmp", dir=folder)
        os.close(descriptor)
        temporary = Path(name)
        try:
            with gzip.open(temporary, "wt", encoding="utf-8") as stream:
                json.dump({"version": 1, **payload}, stream, ensure_ascii=False)
            temporary.replace(folder / "worksheet.json.gz")
        finally:
            temporary.unlink(missing_ok=True)

