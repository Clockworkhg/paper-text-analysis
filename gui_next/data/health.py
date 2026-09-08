# -*- coding: utf-8 -*-
"""Corpus health state machine for the gui-next workbench.

States (official vocabulary across Overview, status bar, Corpus→Health):

- UNKNOWN  no corpus, or sanitation never ran
- PASS     sanitation ran, passed, no warnings, corpus unchanged since
- WARNING  sanitation passed but reported data-quality warnings
- BLOCKED  sanitation reported marker contamination (analysis is gated)
- STALE    the sanitation result predates the current corpus state
           (fingerprint mismatch, or — for legacy reports without a stored
           fingerprint — corpus files modified/added/removed after the check)

STALE never inherits an old PASS/WARNING: a stale result must be re-run
before it can be trusted again. BLOCKED dominates STALE.
"""

from __future__ import annotations

import enum
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class HealthState(str, enum.Enum):
    UNKNOWN = "UNKNOWN"
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    STALE = "STALE"


def _parse_iso(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _corpus_changed_since(corpus_dir: Path, checked_at: Optional[datetime],
                          expected_documents: Optional[int]) -> bool:
    """Legacy-report fallback: detect corpus changes by mtime and file count.

    ``checked_at`` is second-truncated, so mtimes within a small grace window
    after it are treated as unchanged (avoids false STALE for corpora created
    in the same second as the check).
    """
    files = sorted(corpus_dir.rglob("*.txt")) if corpus_dir.exists() else []
    if expected_documents is not None and len(files) != expected_documents:
        return True
    if checked_at is None:
        return False
    grace = timedelta(seconds=2)
    for path in files:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
        except OSError:
            continue
        if mtime > checked_at + grace:
            return True
    return False


def extract_corpus_report(report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize a sanity report to its corpus-check section.

    Reports written by ``project_sanity`` / the GUI sanity job nest the
    corpus check under ``corpus`` (with a sibling ``registry``); some older
    flows wrote the corpus fields at the top level. All health consumers
    must read through this helper so BLOCKED never degrades into PASS.
    """
    if not isinstance(report, dict):
        return {}
    corpus = report.get("corpus")
    if isinstance(corpus, dict):
        merged = dict(corpus)
        merged.setdefault("checked_at", report.get("checked_at"))
        return merged
    return report


def corpus_health(project_dir: str | Path, sanity_report: Optional[Dict[str, Any]],
                  corpus_fingerprint: Optional[Dict[str, Any]] = None) -> Tuple[HealthState, str]:
    """Classify corpus health.

    ``corpus_fingerprint`` may be provided by the caller (computed fresh via
    shared.corpus_sanity.corpus_fingerprint); when absent and the report
    stores one, only the mtime/count fallback runs.
    """
    root = Path(project_dir)
    corpus_dir = root / "corpus"
    has_corpus = corpus_dir.exists() and any(corpus_dir.rglob("*.txt"))
    if not has_corpus:
        return HealthState.UNKNOWN, "语料目录为空或不存在"

    if not sanity_report:
        return HealthState.UNKNOWN, "尚未运行语料卫生检查(project sanity)"

    report = extract_corpus_report(sanity_report)
    failures = report.get("failures", {}) or {}
    contaminated = (
        failures.get("marker_lines_in_body", {}).get("count", 0)
        + failures.get("header_tags_in_body", {}).get("count", 0)
    )
    if contaminated:
        return HealthState.BLOCKED, f"{contaminated} 篇文档存在元数据标记污染,分析已被门禁阻止"

    # Freshness: compare against the corpus state the report described.
    report_fp = report.get("corpus_fingerprint") or sanity_report.get("corpus_fingerprint") or {}
    if report_fp.get("sha256"):
        current = corpus_fingerprint or {}
        if current and current.get("sha256") != report_fp.get("sha256"):
            return HealthState.STALE, "语料指纹与卫生检查结果不一致,检查结果已过期"
    else:
        checked_at = _parse_iso(report.get("checked_at"))
        if _corpus_changed_since(corpus_dir, checked_at, report.get("documents")):
            return HealthState.STALE, "语料在卫生检查之后发生了变化,检查结果已过期"

    warnings = report.get("warnings", {}) or {}
    warning_hits = sum(
        1 for info in warnings.values()
        if info.get("count") or info.get("total") or info.get("groups")
    )
    if warning_hits:
        return HealthState.WARNING, f"卫生检查通过,但存在 {warning_hits} 类数据质量警告"
    return HealthState.PASS, "卫生检查通过,未发现数据质量问题"
