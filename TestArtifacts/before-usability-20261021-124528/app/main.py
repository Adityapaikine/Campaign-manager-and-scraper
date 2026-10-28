from __future__ import annotations

import os
import sys

from suite_bootstrap import configure
configure()

from app.core.cache_db import initialize_database
from app.utils.config import ensure_directories


def main() -> None:
    """Launch the PySide6/Qt professional desktop interface.

    The core application services remain UI-agnostic. Qt is now the production UI;
    the historical CustomTkinter code is retained in ``app.ui`` only as migration
    reference/fallback source and is not imported during normal startup.
    """
    ensure_directories()
    initialize_database()

    # Reduce noisy Qt plugin logging in packaged Windows builds.
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from app.ui_qt.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Lead Workspace — Scraper & Lead Manager")
    app.setOrganizationName("Apex Axis Solutions")
    app.setStyle("Fusion")
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
