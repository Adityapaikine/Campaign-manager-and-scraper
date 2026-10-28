"""Exercise the portable code without touching the user's saved workspace."""
import os
from pathlib import Path
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
(ROOT / "TestArtifacts").mkdir(exist_ok=True)
TEST_DATA = Path(tempfile.mkdtemp(prefix="reference-check-", dir=ROOT / "TestArtifacts"))
os.environ["LEAD_WORKSPACE_DATA_DIR"] = str(TEST_DATA)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from suite_bootstrap import configure
configure()


@pytest.fixture(autouse=True)
def isolate_reference_lists(monkeypatch, tmp_path):
    import app.core.reference_list_store as store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "workspace")
    # This is the isolated test database configured above, never the live workspace.
    import sqlite3
    from app.core.cache_db import initialize_database
    from app.utils.config import DB_PATH
    initialize_database()
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM app_settings")
        connection.execute("DELETE FROM campaign_profiles")
        connection.execute("DELETE FROM campaign_tracking")
        connection.execute("DELETE FROM mapping_templates")
    yield
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM campaign_profiles")


@pytest.fixture(scope="session")
def qt():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase
    application = QApplication.instance() or QApplication([])
    # The offscreen Qt plugin does not discover Windows system fonts by itself.
    for filename in ("segoeui.ttf", "segoeuib.ttf"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    application.setStyle("Fusion")
    return application
