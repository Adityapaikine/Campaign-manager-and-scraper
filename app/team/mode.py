"""Explicit cutover marker; no database access is needed to select the launcher."""
from pathlib import Path


def shared_mode_requested(database,arguments,environment):
    # Compatibility for all existing shortcuts: there is one authenticated UI.
    return True


def enable_shared_mode(database):
    marker=Path(database).with_suffix('.team-mode')
    marker.write_text('One authenticated Lead Workspace includes research and shared operations.\n',encoding='utf-8')
