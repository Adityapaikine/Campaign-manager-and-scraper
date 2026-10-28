import sys
from suite_bootstrap import configure
configure()

if __name__ == "__main__":
    if "--check" in sys.argv:
        import Scraper
        from app.ui_qt.team_window import TeamWindow
        from app.constants import STANDARD_HEADERS
        assert list(STANDARD_HEADERS) == Scraper.HEADERS
        print("Lead Workspace dependencies loaded. Scraper v" + Scraper.APP_VERSION + "; unified interface loaded. Start the shared service and sign in to use it.")
    else:
        from app.main import main
        main()
