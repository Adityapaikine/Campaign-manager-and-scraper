"""Render the worksheet in an isolated workspace and record usable table space."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["LEAD_WORKSPACE_DATA_DIR"] = tempfile.mkdtemp(prefix="lead-spacing-")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from suite_bootstrap import configure
configure()
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QFrame
from app.ui_qt.main_window import MainWindow

qt = QApplication([])
for filename in ("segoeui.ttf", "segoeuib.ttf"):
    QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / filename))
qt.setStyle("Fusion")
stage = sys.argv[1]
measurements = []
with patch.object(MainWindow, "_offer_recovery"), patch.object(MainWindow, "refresh_qwen_status"):
    window = MainWindow()
    try:
        window.controller.settings.appearance_mode = "Light"
        window.controller.settings.color_scheme = "Professional Blue"
        window.apply_theme()
        for i in range(40):
            window.controller.data_manager.append_record({
                "First Name": "Sample", "Last Name": f"Lead {i + 1}",
                "Company Name": "Example Company", "Company Website": "example.com",
                "Campaign Name": "Q4 Campaign", "Agent Name": "Aisha Khan", "Calling Agent Name": "Aisha Khan",
                "Business Email ID": f"sample{i}@example.com", "Phone Number": f"+1 202-555-{100+i:04}",
                "Dispo": ("Connected", "Follow Up", "Not Interested")[i % 3],
                "Comment": "Synthetic preview record.", "Date": "21-Oct-2026",
            }, source_name="Isolated layout preview")
        window._refresh_all()
        page = window.leads_page
        page.view_selector.setCurrentText("Lead overview")
        window.navigate("leads"); window.show()
        page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(0, 0)))
        for width, height in ((1680, 960), (1366, 800), (1120, 740)):
            window.resize(width, height)
            for _ in range(4):
                qt.processEvents()
            toolbar = page.findChild(QFrame, "toolbarCard")
            item = {"window": [window.width(), window.height()], "toolbar_height": toolbar.height(),
                    "table_top": page.table.mapTo(window, QPoint(0, 0)).y(),
                    "viewport": [page.table.viewport().width(), page.table.viewport().height()],
                    "row_height": page.table.verticalHeader().defaultSectionSize(),
                    "visible_rows": page.table.viewport().height() // page.table.verticalHeader().defaultSectionSize(),
                    "font_pt": page.table.font().pointSizeF(),
                    "details_visible": page.details_panel.isVisible()}
            measurements.append(item)
            window.grab().save(str(ROOT / "TestArtifacts" / f"spacing_{stage}_{width}.png"))
    finally:
        window.close(); qt.processEvents()
(ROOT / "TestArtifacts" / f"spacing_{stage}.json").write_text(json.dumps(measurements, indent=2), encoding="utf-8")
print(json.dumps(measurements, indent=2))
