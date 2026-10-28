"""Windowless launcher with a persistent error report."""
from pathlib import Path
import ctypes
import sys
import traceback

root = Path(__file__).resolve().parent
log_dir = root / "Logs"
log_dir.mkdir(exist_ok=True)
with (log_dir / "launcher.log").open("a", encoding="utf-8", buffering=1) as log:
    sys.stdout = sys.stderr = log
    try:
        from app.main import main
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(None, f"The application could not start.\n\nSee {log_dir / 'launcher.log'}", "Lead Workspace", 16)
