"""Exercise dependencies, Excel, Qt and optionally the bundled browser in isolation."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def check(browser=False, launch_ui=False):
    root = Path(__file__).resolve().parent
    # Never open, write or prune the user's live database/profile during checks.
    with tempfile.TemporaryDirectory(prefix="lead-workspace-check-", ignore_cleanup_errors=True) as work:
        os.environ["LEAD_WORKSPACE_DATA_DIR"] = str(Path(work) / "Data")
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from suite_bootstrap import configure
        configure()
        import Scraper
        import pandas as pd
        import ssl
        import win32com.client
        from openpyxl import load_workbook
        from PySide6.QtWidgets import QApplication
        from app.constants import STANDARD_HEADERS
        from app.ui_qt.main_window import MainWindow
        from app.ui_qt.controller import ApplicationController
        from app.ai.qwen_runtime import QwenRuntimeManager
        assert list(STANDARD_HEADERS) == Scraper.HEADERS
        path = Path(work) / "check.xlsx"
        pd.DataFrame([{"First Name": "Portable", "Last Name": "Check", "Zip Code": "00123"}]).to_excel(path, index=False)
        book = load_workbook(path)
        assert book.active["C2"].value == "00123"
        book.close()
        ssl.create_default_context()
        qt = QApplication.instance() or QApplication([])
        controller = ApplicationController()
        assert controller.settings.email_website_lookup
        report = {"python": sys.version.split()[0], "python_home": sys.prefix,
                  "runtime_is_local": Path(sys.prefix).is_relative_to(root),
                  "spreadsheet": "passed", "qt": "passed", "dependencies": "passed"}
        if report["runtime_is_local"]:
            assert all(Path(p).resolve().is_relative_to(root) for p in sys.path if p), sys.path
            report["isolated_from_installed_python"] = True
        if launch_ui:
            from unittest.mock import patch
            with patch.object(MainWindow, "_offer_recovery"), patch.object(MainWindow, "refresh_qwen_status"):
                window = MainWindow()
                window.show()
                qt.processEvents()
                assert window.stack.currentWidget() == window.scraper_page
                for name in window.pages:
                    window.navigate(name)
                    qt.processEvents()
                window.close()
                qt.processEvents()
            report["app_pages"] = "passed"
        qwen = QwenRuntimeManager().discover(probe=False)
        report["qwen_assets"] = bool(qwen.executable and qwen.model)
        if browser:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                # Deliberately use bundled Chromium, never this PC's Chrome.
                browser_path = Path(pw.chromium.executable_path)
                assert browser_path.is_relative_to(root / "runtime" / "browsers")
                with pw.chromium.launch(headless=True, chromium_sandbox=True) as chromium:
                    page = chromium.new_page()
                    page.set_content("<h1>Portable browser check</h1>")
                    assert page.locator("h1").inner_text() == "Portable browser check"
            report["bundled_browser"] = "passed"
        import gc
        gc.collect()
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--ui", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.browser, args.ui), indent=2))
        print("Lead Workspace is ready on this computer.")
    except Exception:
        import traceback
        traceback.print_exc()
        print("Check failed. Keep this output and confirm that the entire portable folder was copied.")
        raise SystemExit(1)
