# -*- coding: utf-8 -*-
"""Corpus sanity checks (Step 0): run before any analysis.

The checks catch research-data pollution that would silently distort
collocation statistics and candidate ranking, most importantly:

- metadata markers left inside document bodies (``----- BODY -----``,
  ``<SOURCE>:`` etc.) after a workbench-format TXT was re-imported as if
  it were raw text ("double wrapping");
- empty or suspiciously short documents;
- exact duplicate bodies / duplicate document ids;
- encoding anomalies (U+FFFD replacement characters).

Marker contamination is a *failure* (analysis is blocked); data-quality
issues are *warnings* (analysis proceeds, researcher should review).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from shared.corpus_model import parse_text_document
from shared.research_output import now_iso

# A standalone "----- WORD -----" divider line inside a document body.
MARKER_LINE = re.compile(r"^\s*-{3,}\s*[A-Za-z][A-Za-z _-]{0,40}\s*-{3,}\s*$", re.MULTILINE)
# A workbench metadata header tag inside a document body.
HEADER_TAG = re.compile(r"^\s*<(?:SOURCE|SOURCE_NORM|TITLE|DATE|DOCUMENT_ID|CORPUS_ID|RUN_ID)>:", re.MULTILINE)


def _examples(items: List[str], limit: int = 3) -> List[str]:
    return sorted(items)[:limit]


def check_corpus_sanity(
    corpus_dir: str | Path,
    *,
    short_body_chars: int = 200,
    max_examples: int = 3,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Validate every TXT under a corpus directory; returns a report dict.

    ``report["ok"]`` is False only for marker/header-tag contamination —
    the kind of pollution that changes collocate token frequencies.
    """
    corpus = Path(corpus_dir)
    files = sorted(corpus.rglob("*.txt")) if corpus.exists() else []

    marker_files: List[str] = []
    tag_files: List[str] = []
    empty_files: List[str] = []
    short_files: List[str] = []
    replacement_hits = 0
    body_hashes: Dict[str, List[str]] = {}

    for path in files:
        parsed = parse_text_document(path)
        body = parsed["body"]
        rel = path.relative_to(corpus).as_posix() if corpus in path.parents else path.name

        if MARKER_LINE.search(body):
            marker_files.append(rel)
        if HEADER_TAG.search(body):
            tag_files.append(rel)
        if not body.strip():
            empty_files.append(rel)
        elif len(body) < short_body_chars:
            short_files.append(rel)
        replacement_hits += body.count("\ufffd")
        digest = hashlib.sha1(body.encode("utf-8", errors="ignore")).hexdigest()
        body_hashes.setdefault(digest, []).append(rel)

    duplicate_groups = [paths for paths in body_hashes.values() if len(paths) > 1]

    report: Dict[str, Any] = {
        "checked_at": now_iso(),
        "corpus_dir": str(corpus),
        "documents": len(files),
        "ok": not marker_files and not tag_files,
        "failures": {
            "marker_lines_in_body": {
                "count": len(marker_files),
                "examples": _examples(marker_files, max_examples),
                "hint": "正文中发现 '----- xxx ----- ' 分隔线；通常是中间格式 TXT 被二次导入。",
            },
            "header_tags_in_body": {
                "count": len(tag_files),
                "examples": _examples(tag_files, max_examples),
                "hint": "正文中发现 '<SOURCE>:' 等头部标签；同理为二次包装残留。",
            },
        },
        "warnings": {
            "empty_body": {"count": len(empty_files), "examples": _examples(empty_files, max_examples)},
            "short_body": {
                "count": len(short_files),
                "examples": _examples(short_files, max_examples),
                "threshold_chars": short_body_chars,
            },
            "replacement_chars": {"total": replacement_hits},
            "duplicate_bodies": {
                "groups": len(duplicate_groups),
                "documents": sum(len(g) for g in duplicate_groups),
                "example_groups": [sorted(g) for g in duplicate_groups[:max_examples]],
            },
        },
    }
    if log_fn:
        if report["ok"]:
            log_fn(f"语料卫生检查通过: {len(files)} 篇文档，未发现元数据标记污染。")
        else:
            log_fn(f"⚠ 语料卫生检查发现问题: {len(marker_files)} 篇含分隔线标记, {len(tag_files)} 篇含头部标签。")
        for warning, info in report["warnings"].items():
            if info.get("count") or info.get("total") or info.get("groups"):
                log_fn(f"  ⚠ {warning}: {info.get('count', info.get('groups', info.get('total')))}")
    return report


def check_registry_sanity(out_dir: str | Path) -> Dict[str, Any]:
    """Validate 01_corpus/documents.csv: duplicate ids, missing corpus files."""
    out = Path(out_dir)
    docs_path = out / "01_corpus" / "documents.csv"
    if not docs_path.exists():
        return {"ok": True, "checked": False, "reason": "registry_missing"}

    import pandas as pd

    docs = pd.read_csv(docs_path)
    issues: Dict[str, Any] = {}
    if "document_id" in docs.columns:
        dup_ids = docs[docs["document_id"].duplicated(keep=False)]
        if not dup_ids.empty:
            issues["duplicate_document_ids"] = {
                "count": int(dup_ids["document_id"].nunique()),
                "examples": sorted(dup_ids["document_id"].astype(str).unique().tolist())[:3],
            }
    if "relative_path" in docs.columns and (out / "corpus").exists():
        missing = [
            rel for rel in docs["relative_path"].astype(str)
            if rel and not (out / "corpus" / rel).exists()
        ]
        if missing:
            issues["missing_corpus_files"] = {"count": len(missing), "examples": sorted(missing)[:3]}

    return {"ok": not issues, "checked": True, "documents": int(len(docs)), "issues": issues}


def corpus_fingerprint(corpus_dir: str | Path) -> Dict[str, Any]:
    """Deterministic sha256 fingerprint of a corpus directory.

    Hashes the sorted (relative path, file content) pairs, so any change to
    file names or bodies changes the fingerprint. Stored in run configs and
    frozen-run manifests to pin exactly which corpus a result belongs to.
    """
    corpus = Path(corpus_dir)
    digest = hashlib.sha256()
    files = sorted(corpus.rglob("*.txt")) if corpus.exists() else []
    total_bytes = 0
    for path in files:
        rel = path.relative_to(corpus).as_posix()
        content = path.read_bytes()
        total_bytes += len(content)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\n")
        digest.update(hashlib.sha256(content).digest())
        digest.update(b"\n")
    return {
        "algorithm": "sha256(relpath + file-sha256)",
        "files": len(files),
        "bytes": total_bytes,
        "sha256": digest.hexdigest(),
    }
