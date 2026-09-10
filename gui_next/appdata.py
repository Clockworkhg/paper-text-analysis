# -*- coding: utf-8 -*-
"""Application-level state (Phase 4B #5/#6/#17).

Everything here lives in the user's application-data directory
(QStandardPaths.AppDataLocation/CADSWorkbench) — NEVER inside a research
project:

    AppData/CADSWorkbench/
        recent_projects.json     (path / display_name / last_opened only)
        logs/application.log     (rotating)
        logs/execution.log       (rotating)
        session_crashed.flag     (crash-on-start notice, #20)

Application settings (window geometry, panel visibility) go through
QSettings; project research state stays in the project. GUI state must not
be written into project.json.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QStandardPaths

from gui_next.version import APP_ID

MAX_RECENT = 10


def app_data_dir() -> Path:
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation)
    # e.g. .../CADSWorkbench/CADSWorkbench — collapse to one level
    root = Path(base)
    if root.name == APP_ID and root.parent.name == APP_ID:
        root = root.parent
    root.mkdir(parents=True, exist_ok=True)
    return root


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def recent_projects_path() -> Path:
    return app_data_dir() / "recent_projects.json"


def crash_flag_path() -> Path:
    return app_data_dir() / "session_crashed.flag"


# ---- recent projects (#5) -------------------------------------------

def load_recent_projects() -> List[Dict[str, str]]:
    try:
        data = json.loads(recent_projects_path().read_text(encoding="utf-8"))
        entries = data.get("projects", [])
        if isinstance(entries, list):
            return [e for e in entries if isinstance(e, dict) and e.get("path")]
    except Exception:
        pass
    return []


def remember_project(project_dir: str | Path, display_name: str = "") -> None:
    """Record a project open (application-level state only)."""
    path = Path(project_dir)
    entries = [e for e in load_recent_projects()
               if Path(e.get("path", "")) != path]
    entries.insert(0, {
        "path": str(path),
        "display_name": display_name or path.name,
        "last_opened": datetime.now().isoformat(timespec="seconds"),
    })
    save_recent_projects(entries[:MAX_RECENT])


def remove_recent_project(project_dir: str | Path) -> None:
    """Remove from the recent list. Never touches the project files (#5)."""
    path = Path(project_dir)
    save_recent_projects([e for e in load_recent_projects()
                          if Path(e.get("path", "")) != path])


def save_recent_projects(entries: List[Dict[str, Any]]) -> None:
    recent_projects_path().parent.mkdir(parents=True, exist_ok=True)
    recent_projects_path().write_text(
        json.dumps({"projects": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def project_missing(entry: Dict[str, str]) -> bool:
    return not Path(entry.get("path", "")).exists()


# ---- crash notice (#20) ---------------------------------------------

def mark_session_crashed() -> None:
    try:
        crash_flag_path().write_text(
            datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    except OSError:
        pass


def clear_crash_flag() -> None:
    try:
        crash_flag_path().unlink(missing_ok=True)
    except OSError:
        pass


def previous_session_crashed() -> bool:
    return crash_flag_path().exists()
