# -*- coding: utf-8 -*-
"""Run lifecycle states and the JSON-line event protocol for gui-next runs.

Lifecycle: IDLE -> PREPARING -> RUNNING -> (CANCELLING ->) SUCCEEDED |
FAILED | CANCELLED. A run found alive-in-journal but without a live
process after an app restart becomes INTERRUPTED.
"""

from __future__ import annotations

import json
from enum import Enum


class RunState(str, Enum):
    IDLE = "IDLE"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


ACTIVE_STATES = {RunState.PREPARING, RunState.RUNNING, RunState.CANCELLING}
TERMINAL_STATES = {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED, RunState.INTERRUPTED}


def encode(event: dict) -> str:
    """One JSON line (child -> parent protocol)."""
    return json.dumps(event, ensure_ascii=False)


def parse(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        event = json.loads(line)
    except Exception:
        # Non-protocol output (e.g. library prints) is still valuable log text.
        return {"event": "log", "line": line}
    if isinstance(event, dict) and "event" in event:
        return event
    return {"event": "log", "line": line.strip()}


def stage_event(stage: str, message: str = "") -> dict:
    return {"event": "stage", "stage": stage, "message": message}


def log_event(line: str) -> dict:
    return {"event": "log", "line": line}


def error_event(exc: BaseException) -> dict:
    import traceback

    tb = traceback.format_exc()
    return {
        "event": "error",
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback_tail": tb[-2000:],
    }


def result_event(outputs: dict) -> dict:
    return {"event": "result", "outputs": outputs}
