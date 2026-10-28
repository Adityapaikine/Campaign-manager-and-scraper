"""Durable completed-row results, keyed by input and search settings rather than row position."""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from app.utils.config import CACHE_DIR


class EmailRunStore:
    def __init__(self, path=None):
        self.path = Path(path or CACHE_DIR / "email_runs.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS completed (key TEXT PRIMARY KEY, result TEXT NOT NULL, expires REAL NOT NULL)")
            db.execute("DELETE FROM completed WHERE expires < ?", (time.time(),))

    @staticmethod
    def key(record, settings, blocked_status=None):
        fields = ("First Name", "Last Name", "Company Name", "Company Website", "Prospect LinkedIn Link", "Business Email ID", "Email Status")
        payload = {"version": 2, "record": [str(record.get(k, "")).strip() for k in fields],
                   "settings": settings, "blocked": blocked_status}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def get_many(self, keys):
        output = {}
        keys = list(dict.fromkeys(keys))
        with closing(sqlite3.connect(self.path, timeout=15)) as db:
            for offset in range(0, len(keys), 500):
                batch = keys[offset:offset+500]
                placeholders = ",".join("?" for _ in batch)
                for key, payload in db.execute(f"SELECT key,result FROM completed WHERE key IN ({placeholders}) AND expires > ?", [*batch, time.time()]):
                    try:
                        output[key] = json.loads(payload)
                    except (ValueError, TypeError):
                        continue
        return output

    def save(self, key, result):
        # Failed or disabled requests are unfinished work, never a negative result.
        if result.discovery_status in {"Search Error", "Search Disabled", "Timed Out"} or result.status == "Timed Out":
            return
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.execute("INSERT OR REPLACE INTO completed VALUES (?,?,?)", (key, json.dumps(asdict(result)), time.time() + 86400))
