# -*- coding: utf-8 -*-
"""Global status vocabulary (Phase 4A #17).

Internal semantics are fixed enums; the *display* layer (glyph, user text,
color role) lives here and nowhere else. Pages must never invent synonyms
("Done", "Ready", "OK") — they map an internal state through this module.

Color roles: "ok" | "warn" | "error" | "muted" | "primary".
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from gui_next import theme
from gui_next.data.health import HealthState

Role = str  # "ok" | "warn" | "error" | "muted" | "primary"


def role_color(role: Role) -> str:
    return {
        "ok": theme.SUCCESS,
        "warn": theme.WARNING,
        "error": theme.ERROR,
        "muted": theme.MUTED,
        "primary": theme.PRIMARY,
    }.get(role, theme.MUTED)


# ---- Corpus health ---------------------------------------------------

HEALTH_DISPLAY: Dict[str, Tuple[str, str, Role]] = {
    "UNKNOWN": ("○", "未检查", "muted"),
    "PASS": ("✓", "通过", "ok"),
    "WARNING": ("⚠", "有警告", "warn"),
    "BLOCKED": ("✕", "已阻塞", "error"),
    "STALE": ("⚠", "已过期", "warn"),
}


def health(state: HealthState) -> Tuple[str, str, Role]:
    return HEALTH_DISPLAY.get(state.value, ("–", state.value, "muted"))


# ---- Review ----------------------------------------------------------

REVIEW_DISPLAY: Dict[str, Tuple[str, str, Role]] = {
    "NOT_STARTED": ("○", "未开始", "muted"),
    "IN_PROGRESS": ("●", "进行中", "primary"),
    "COMPLETE": ("✓", "完成", "ok"),
    "STALE": ("⚠", "已失效", "warn"),
}


def review(status: str) -> Tuple[str, str, Role]:
    return REVIEW_DISPLAY.get(status, ("–", status, "muted"))


# ---- Evidence integrity ---------------------------------------------

INTEGRITY_DISPLAY: Dict[str, Tuple[str, str, Role]] = {
    "VERIFIED": ("✓", "Verified", "ok"),
    "SOURCE_UNAVAILABLE": ("⚠", "Source unavailable", "warn"),
    "INTEGRITY_ERROR": ("✕", "Integrity error", "error"),
}


def integrity(state: str) -> Tuple[str, str, Role]:
    return INTEGRITY_DISPLAY.get(state, ("–", state, "muted"))


# ---- Run lifecycle (execution/events.RunState values) ----------------

RUN_DISPLAY: Dict[str, Tuple[str, str, Role]] = {
    "IDLE": ("○", "Idle", "muted"),
    "PREPARING": ("●", "Preparing", "primary"),
    "RUNNING": ("●", "Running", "primary"),
    "CANCELLING": ("●", "Cancelling…", "warn"),
    "ANALYSIS_SUCCEEDED": ("✓", "Analysis succeeded · publishing", "primary"),
    "PUBLISHING": ("●", "Publishing", "primary"),
    "SUCCEEDED": ("✓", "success", "ok"),
    "FAILED": ("✕", "failed", "error"),
    "CANCELLED": ("○", "cancelled", "muted"),
    "PUBLISH_FAILED": ("✕", "Publish failed", "error"),
    "INTERRUPTED": ("⚠", "interrupted", "warn"),
    "RECOVERY_REQUIRED": ("✕", "Recovery required", "error"),
}


def run(state: str) -> Tuple[str, str, Role]:
    return RUN_DISPLAY.get(state, ("–", state, "muted"))


# ---- Comparison ------------------------------------------------------

COMPARISON_DISPLAY: Dict[str, Tuple[str, str, Role]] = {
    "FULLY_COMPARABLE": ("✓", "Fully comparable", "ok"),
    "PARTIALLY_COMPARABLE": ("⚠", "Partially comparable", "warn"),
    "NOT_COMPARABLE": ("✕", "Not comparable", "error"),
}


def comparison(level: str) -> Tuple[str, str, Role]:
    return COMPARISON_DISPLAY.get(level, ("–", level, "muted"))


def pipeline_glyph(role: Role) -> str:
    """Glyph for an Overview pipeline row role."""
    return {"ok": theme.OK, "warn": theme.WARN, "error": "✕",
            "muted": theme.PENDING, "primary": "●"}.get(role, "–")


def count_progress(done: int, total: int) -> str:
    return f"{done}/{total}"


def apply_state_style(widget, role: Role, *, bold: bool = True) -> None:
    """Color a QLabel by semantic role (colors never carry meaning alone —
    the glyph/text next to it names the state)."""
    widget.setStyleSheet(
        f"color: {role_color(role)}; background: transparent;"
        + ("font-weight: 600;" if bold else ""))


__all__ = [
    "role_color", "health", "review", "integrity", "run", "comparison",
    "pipeline_glyph", "count_progress", "apply_state_style",
]
