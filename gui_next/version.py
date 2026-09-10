# -*- coding: utf-8 -*-
"""Single version / build-metadata source (Phase 4B #31).

VERSION file at the repo root is the source of truth for the product
version. Build metadata (git commit, build timestamp, build mode) is
written by the PyInstaller spec into the bundle (build_meta.json) and
probed from git in source mode. About / logs / diagnostics all read from
here — never from a second hardcoded copy.
"""

from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

APP_NAME = "CADS Workbench"
APP_ID = "CADSWorkbench"
PACKAGE_ID = "cads-workbench"

_ROOT = Path(__file__).resolve().parents[1]


def _read_version_file() -> str:
    try:
        return _ROOT.joinpath("VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-dev"


VERSION = _read_version_file()


def _resource_root() -> Path:
    """Directory holding bundled resources (build_meta.json, docs)."""
    if sys_frozen():
        import sys
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass and Path(meipass).exists():
            return Path(meipass)
        return Path(sys.executable).resolve().parent / "_internal"
    return _ROOT


def sys_frozen() -> bool:
    import sys
    return bool(getattr(sys, "frozen", False))


def python_version() -> str:
    import sys
    return sys.version.split()[0]


def qt_version() -> str:
    try:
        from PySide6 import QtCore
        return QtCore.qVersion()
    except Exception:
        return "–"


@lru_cache(maxsize=1)
def build_metadata() -> dict:
    """version + commit + build timestamp + mode; consistent everywhere."""
    meta = {
        "version": VERSION,
        "app_name": APP_NAME,
        "git_commit": "",
        "build_timestamp": "",
        "build_mode": "source",
    }
    try:
        meta_file = _resource_root() / "build_meta.json"
        if meta_file.exists():
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            meta.update({k: v for k, v in data.items() if v})
            if not sys_frozen():
                meta["version"] = VERSION  # source mode: VERSION file wins
            # packaged mode: the bundled build_meta carries the release version
        return meta
    except Exception:
        pass
    # source mode: probe git for the commit
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_ROOT), capture_output=True, text=True, timeout=5,
        )
        if commit.returncode == 0:
            meta["git_commit"] = commit.stdout.strip()
    except Exception:
        pass
    return meta


def version_line() -> str:
    meta = build_metadata()
    parts = [f"{APP_NAME} {meta['version']}"]
    if meta.get("git_commit"):
        parts.append(f"commit {meta['git_commit']}")
    if meta.get("build_timestamp"):
        parts.append(f"build {meta['build_timestamp']}")
    parts.append(meta.get("build_mode", "source"))
    return " · ".join(parts)


def docs_dir() -> Path:
    """Bundled (packaged) or repository (source) documentation directory."""
    if sys_frozen():
        bundled = _resource_root() / "docs"
        if bundled.exists():
            return bundled
        return Path(__file__).resolve().parent / "docs"
    return _ROOT / "docs"


def repo_root() -> Path:
    return _ROOT
