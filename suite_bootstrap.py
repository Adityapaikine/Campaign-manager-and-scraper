"""Paths belonging exclusively to this combined copy."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent


def configure():
    engine = str(ROOT / "scraper_engine")
    if engine not in sys.path:
        sys.path.insert(0, engine)
    # These explicit suite variables also allow isolated automated test runs.
    data = Path(os.environ.get("LEAD_WORKSPACE_DATA_DIR", ROOT / "Data")).resolve()
    os.environ["LEAD_MANAGER_DATA_DIR"] = str(data / "LeadManager")
    os.environ["SCRAPER_DATA_DIR"] = os.environ.get('LEAD_USER_SCRAPER_DIR', str(data / "Scraper"))
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / "runtime" / "browsers")
    for folder in (data, ROOT / "Output", ROOT / "Logs"):
        folder.mkdir(parents=True, exist_ok=True)
    return data
