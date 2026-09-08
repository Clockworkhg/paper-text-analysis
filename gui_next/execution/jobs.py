# -*- coding: utf-8 -*-
"""Run job specs, the GUI run journal, writer locking, and crash recovery.

Everything here is project-local and lives under ``runs/``:

- ``runs/gui_runs.json``      run journal (one entry per GUI-launched run)
- ``runs/analysis_writer.lock``  active analysis writer lock
- ``runs/work_<run_id>/``     isolated work copy for a running analysis

The journal is the audit trail for the Runs page and drives crash recovery:
entries stuck in an active state whose owning process is gone become
INTERRUPTED ("Previous application session ended before this run
completed."), keeping their work directory and logs for inspection.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from gui_next.execution.events import ACTIVE_STATES, RunState

JOURNAL_FILE = "gui_runs.json"
WRITER_LOCK = "analysis_writer.lock"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def pid_alive(pid: Optional[int]) -> bool:
    if not pid or int(pid) <= 0:
        return False
    pid = int(pid)
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        ERROR_ACCESS_DENIED = 5
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return kernel32.GetLastError() == ERROR_ACCESS_DENIED
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


def journal_path(project_dir: str | Path) -> Path:
    return Path(project_dir) / "runs" / JOURNAL_FILE


def load_journal(project_dir: str | Path) -> List[Dict[str, Any]]:
    data = _read_json(journal_path(project_dir), {"schema": 1, "runs": []})
    runs = data.get("runs", []) if isinstance(data, dict) else []
    return [entry for entry in runs if isinstance(entry, dict)]


def save_journal(project_dir: str | Path, runs: List[Dict[str, Any]]) -> Path:
    path = journal_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema": 1, "runs": runs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def append_run(project_dir: str | Path, entry: Dict[str, Any]) -> None:
    runs = load_journal(project_dir)
    runs.append(entry)
    save_journal(project_dir, runs)


def update_run(project_dir: str | Path, run_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    runs = load_journal(project_dir)
    for entry in reversed(runs):
        if entry.get("run_id") == run_id:
            entry.update(fields)
            save_journal(project_dir, runs)
            return entry
    return None


def get_run(project_dir: str | Path, run_id: str) -> Optional[Dict[str, Any]]:
    for entry in load_journal(project_dir):
        if entry.get("run_id") == run_id:
            return entry
    return None


# ---------------------------------------------------------------------------
# Writer lock (single analysis writer per project)
# ---------------------------------------------------------------------------


def writer_lock_path(project_dir: str | Path) -> Path:
    return Path(project_dir) / "runs" / WRITER_LOCK


def acquire_writer_lock(project_dir: str | Path, run_id: str) -> bool:
    """Create the writer lock; False when another analysis writer is active."""
    path = writer_lock_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    try:
        path.write_text(
            json.dumps({"run_id": run_id, "pid": os.getpid(), "acquired_at": _now()}),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def release_writer_lock(project_dir: str | Path, run_id: str) -> None:
    path = writer_lock_path(project_dir)
    try:
        if path.exists():
            info = _read_json(path, {})
            if not info or info.get("run_id") in (run_id, None):
                path.unlink(missing_ok=True)
    except OSError:
        pass


def active_writer(project_dir: str | Path) -> Optional[Dict[str, Any]]:
    """Return the active writer info if the lock exists and its process lives."""
    path = writer_lock_path(project_dir)
    if not path.exists():
        return None
    info = _read_json(path, {})
    if info and not pid_alive(info.get("pid")):
        # Stale lock from a dead session; startup recovery normally clears it.
        return None
    return info or {"run_id": "unknown"}


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------


def recover_interrupted_runs(project_dir: str | Path) -> List[Dict[str, Any]]:
    """Mark journal entries stuck in active states (dead process) INTERRUPTED.

    Keeps work directories and logs in place; clears writer locks owned by
    the interrupted runs. Returns the entries that were recovered.
    """
    runs = load_journal(project_dir)
    recovered: List[Dict[str, Any]] = []
    changed = False
    for entry in runs:
        state = entry.get("status", "")
        if state not in {s.value for s in ACTIVE_STATES}:
            continue
        if pid_alive(entry.get("pid")):
            continue
        if state in (RunState.ANALYSIS_SUCCEEDED.value, RunState.PUBLISHING.value):
            entry["status"] = RunState.PUBLISH_FAILED.value
            entry["note"] = ("Publication interrupted by session end; the publication "
                             "transaction was rolled back on next startup.")
        else:
            entry["status"] = RunState.INTERRUPTED.value
            entry["note"] = "Previous application session ended before this run completed."
        entry["finished_at"] = _now()
        recovered.append(entry)
        changed = True
        release_writer_lock(project_dir, entry.get("run_id"))
    if changed:
        save_journal(project_dir, runs)
    return recovered


# ---------------------------------------------------------------------------
# Work directory
# ---------------------------------------------------------------------------

# Inputs the analysis needs from the real project. Derived analysis outputs
# from previous runs are deliberately NOT copied: a stale file must never be
# able to impersonate a fresh result in the publication manifest.
WORK_COPY_INPUT_FILES = [
    "merged_sources.xlsx",                    # input for the country join
    Path("01_corpus") / "group_overrides.xlsx",  # input for custom grouping
]


def make_work_dir(project_dir: str | Path, run_id: str) -> Path:
    """Build an isolated, minimal work copy for one analysis run.

    Contains only run inputs (corpus, project identity, overrides). The
    copy's ``project.json`` is repointed at the work copy itself:
    ``project_analyze`` locates the project root through that field, so
    without this step every write would bypass isolation and land in the
    real project.
    """
    root = Path(project_dir)
    work = root / "runs" / f"work_{run_id}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copytree(root / "corpus", work / "corpus")
    for rel in WORK_COPY_INPUT_FILES:
        src = root / rel
        if src.exists():
            dst = work / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    info = _read_json(root / "project.json", {})
    info["project_dir"] = str(work)
    (work / "project.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return work


def snapshot_files(root: str | Path) -> set:
    """Relative paths of every file under a directory (for produced diffs)."""
    root = Path(root)
    if not root.exists():
        return set()
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*") if p.is_file()
    }


# ---------------------------------------------------------------------------
# Job spec
# ---------------------------------------------------------------------------


def build_spec(*, kind: str, project_dir: str, targets: str = "", group_by: str = "source",
               mi_threshold: float = 3.0, pos_translate: bool = False, sanity: bool = True,
               test_sleep_before_analyze: float = 0.0, inject_failure: bool = False) -> Dict[str, Any]:
    """Build a runner job spec. Parameters map 1:1 onto existing shared APIs.

    ``test_sleep_before_analyze`` / ``inject_failure`` are test-only hooks of
    the execution layer itself (never shared/).
    """
    return {
        "kind": kind,
        "project_dir": str(project_dir),
        "targets": targets,
        "group_by": group_by,
        "mi_threshold": float(mi_threshold),
        "pos_translate": bool(pos_translate),
        "sanity": bool(sanity),
        "test_sleep_before_analyze": float(test_sleep_before_analyze),
        "inject_failure": bool(inject_failure),
        "created_at": _now(),
    }
