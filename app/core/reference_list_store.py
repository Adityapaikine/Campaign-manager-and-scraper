"""Keep mapped reference rows with the workspace, independent of the upload file."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from app.core.reference_lists import ReferenceData, available_fields
from app.constants import MISSING_VALUE
from app.utils.config import DATA_DIR


class ReferenceListStore:
    def __init__(self, folder: Path | None = None):
        self.folder = Path(folder) if folder is not None else DATA_DIR / "reference_lists"

    def _path(self, kind: str) -> Path:
        if kind not in {"tal", "suppression"}:
            raise ValueError("Unknown reference list type")
        return self.folder / f"{kind}.json"

    def save(self, data: ReferenceData) -> None:
        target = self._path(data.kind)
        payload = asdict(data)
        # Never depend on the original PC's file location when restoring a list.
        payload.pop("source_path")
        payload["version"] = 1
        payload["uploaded_at"] = datetime.now(timezone.utc).isoformat()
        self.folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.folder,
                                         prefix=data.kind + "-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            try:
                json.dump(payload, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            except Exception:
                handle.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def load(self, kind: str) -> ReferenceData | None:
        path = self._path(kind)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["version"] != 1 or payload["kind"] != kind:
                raise ValueError("Unsupported reference data")
            records = payload["records"]
            fields = set(available_fields(kind))
            if not isinstance(records, list) or not records:
                raise ValueError("Empty reference data")
            for record in records:
                if (not isinstance(record, dict) or not set(record) <= fields
                        or not all(isinstance(value, str) for value in record.values())
                        or not any(value.strip() not in {"", MISSING_VALUE} for value in record.values())):
                    raise ValueError("Invalid reference row")
            if (not isinstance(payload["source_name"], str)
                    or not isinstance(payload["mapping"], dict)
                    or not isinstance(payload["columns"], list)):
                raise ValueError("Invalid reference metadata")
            return ReferenceData(kind=kind, source_path=str(path), source_name=payload["source_name"],
                                 columns=tuple(payload["columns"]), mapping=payload["mapping"],
                                 records=tuple(records))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Saved {kind.upper()} list could not be loaded. Upload that list again before validating.") from exc

    def uploaded_at(self, kind):
        path = self._path(kind)
        if not path.exists():
            return ""
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%d %b %Y, %H:%M")

    def remove(self, kind):
        path = self._path(kind)
        if path.exists():
            archive = self.folder / "removed"
            archive.mkdir(exist_ok=True)
            path.replace(archive / f"{kind}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json")
