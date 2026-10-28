from __future__ import annotations

from suite_bootstrap import configure
configure()


def main() -> None:
    """Every desktop shortcut opens the same authenticated application."""
    from app.ui_qt.team_main import main as workspace_main
    workspace_main()


if __name__ == "__main__":
    main()
