from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IS_FROZEN = bool(getattr(sys, "frozen", False))
APPLICATION_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else PROJECT_ROOT

# Development keeps runtime files beside the source for easy inspection. A
# packaged Windows build writes mutable state to the user's profile so an EXE
# installed under Program Files never needs administrator write access.
if os.getenv("LEAD_MANAGER_DATA_DIR", "").strip():
    DATA_DIR = Path(os.environ["LEAD_MANAGER_DATA_DIR"]).expanduser().resolve()
elif IS_FROZEN:
    DATA_DIR = Path(user_data_dir("B2B Lead Manager", "Apex Axis Solutions"))
else:
    DATA_DIR = PROJECT_ROOT / "app" / "data"

if IS_FROZEN:
    CONFIG_DIR = Path(user_config_dir("B2B Lead Manager", "Apex Axis Solutions"))
else:
    CONFIG_DIR = PROJECT_ROOT

LOG_DIR = DATA_DIR / "logs"
EXPORT_DIR = DATA_DIR / "exports"
CACHE_DIR = DATA_DIR / "cache"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
CAMPAIGN_DIR = DATA_DIR / "campaigns"
DB_PATH = CACHE_DIR / "lead_manager.sqlite3"

# Search-provider secrets are intentionally outside source code. In packaged
# builds the preferred location is the per-user config directory; a portable
# .env beside the EXE is also supported.
ENV_CANDIDATES = tuple(dict.fromkeys([
    CONFIG_DIR / ".env",
    APPLICATION_DIR / ".env",
    PROJECT_ROOT / ".env",
]))


def ensure_directories() -> None:
    for path in (DATA_DIR, LOG_DIR, EXPORT_DIR, CACHE_DIR, CHECKPOINT_DIR, CAMPAIGN_DIR, CONFIG_DIR):
        path.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class AppConfig:
    autosave_interval_seconds: int = 60
    autosave_record_interval: int = 100
    max_workers: int = 8
    request_timeout_seconds: int = 15
    retries: int = 2
    minimum_email_confidence: int = 75
