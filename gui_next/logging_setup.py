# -*- coding: utf-8 -*-
"""Application logging (Phase 4B #17).

Two rotating log files under AppData/CADSWorkbench/logs/:

    application.log — GUI lifecycle, user-visible errors, diagnostics info
    execution.log   — analysis subprocess lifecycle (written by the runner)

Rotation: 1 MB per file, 9 backups — bounded disk use, no unbounded growth.
Corpus contents are never logged (#40): only paths, counts and identities.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from gui_next.appdata import logs_dir
from gui_next.version import build_metadata

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_BYTES = 1_000_000
BACKUPS = 9

_app_handler: Optional[RotatingFileHandler] = None
_exec_handler: Optional[RotatingFileHandler] = None


def _build_handler(name: str) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        logs_dir() / name, maxBytes=MAX_BYTES, backupCount=BACKUPS,
        encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return handler


def setup_app_logging(level: int = logging.INFO) -> str:
    """Install the application log once; returns the log file path."""
    global _app_handler
    if _app_handler is None:
        _app_handler = _build_handler("application.log")
        root = logging.getLogger()
        root.setLevel(level)
        root.addHandler(_app_handler)
        meta = build_metadata()
        logging.getLogger("app").info(
            "CADS Workbench start — %s · Python runtime · mode=%s commit=%s",
            meta["version"], meta["build_mode"], meta.get("git_commit", ""))
    return str(_app_handler.baseFilename)


def setup_execution_logging(level: int = logging.INFO) -> str:
    """Install the execution log (used by the runner subprocess)."""
    global _exec_handler
    if _exec_handler is None:
        _exec_handler = _build_handler("execution.log")
        handler = _exec_handler
        logging.getLogger("execution").addHandler(handler)
        logging.getLogger("execution").setLevel(level)
    return str(_exec_handler.baseFilename)


def execution_logger() -> logging.Logger:
    return logging.getLogger("execution")
