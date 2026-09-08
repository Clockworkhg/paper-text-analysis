# -*- coding: utf-8 -*-
"""Transactional publication of analysis outputs (Phase 2B.1).

A finished analysis run never copies files straight into the project.
Instead:

1. ``build_manifest`` enumerates the files the run actually produced (a
   before/after diff of the work copy), filters them through the
   allowlist/owned-output contract, and records path/sha256/size/category;
2. ``validate_manifest`` enforces path safety and content hashes (a work
   output modified after the manifest is rejected);
3. ``execute_publication`` runs the transaction
   PREPARE -> BACKUP -> COMMITTING -> COMMITTED, with ROLLBACK on any
   failure, restoring the complete previous generation;
4. a crash during COMMITTING is recovered on the next startup by
   ``recover_publications``, which rolls back from the transaction backup
   (or flags RECOVERY_REQUIRED when it cannot).

The owned-output set is an allowlist, never a blacklist. ``project.json``
is not part of the publication: identity/config fields must not be
overwritten; the execution layer merges analysis history into it after a
committed publication.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

TransactionLog = Dict[str, Any]


class PublicationError(RuntimeError):
    """Publication failed and was rolled back (or needs manual recovery)."""


class PathSafetyError(PublicationError):
    """A manifest path violates the owned-output contract."""


# ---------------------------------------------------------------------------
# Owned-output contract (allowlist)
# ---------------------------------------------------------------------------

# (category, relative_path) — the complete set of files a GUI analysis run is
# allowed to publish. Anything not listed here is not owned by the execution
# layer and is never published or deleted.
OWNED_OUTPUT_CONTRACT: List[Tuple[str, str]] = [
    ("analysis_workbook", "adjectives_phrases.xlsx"),
    ("pos_translation", "adjectives_final.xlsx"),
    ("run_config", "run_config.json"),
    ("run_config", "00_run_config/run_config.json"),
    ("run_config", "00_run_config/data_model.json"),
    ("run_config", "00_run_config/research_template.json"),
    ("registry", "01_corpus/documents.csv"),
    ("registry", "01_corpus/document_registry.xlsx"),
    ("registry", "01_corpus/corpus_manifest.json"),
    ("country_join", "03_country/source_countries.csv"),
    ("review_template", "06_review/modifier_semantic_review.xlsx"),
    ("review_template", "06_review/source_country_review.xlsx"),
    ("report", "07_reports/validation_report.xlsx"),
    ("report", "07_reports/method_summary.md"),
    ("report", "07_reports/method_limitations.md"),
]

OWNED_PATHS = {rel for _category, rel in OWNED_OUTPUT_CONTRACT}
CATEGORY_BY_PATH = {rel: category for category, rel in OWNED_OUTPUT_CONTRACT}

# Hard denials, for defence in depth on top of the allowlist.
DENIED_PREFIXES = ("corpus/", "runs/", ".zcode", ".git")
DENIED_SUFFIXES = ("_state.json", ".py")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_path_safety(rel_path: str) -> None:
    """Reject anything that is not a plain, contract-listed relative path."""
    if not rel_path or rel_path != rel_path.strip():
        raise PathSafetyError(f"非法路径: {rel_path!r}")
    normal = rel_path.replace("\\", "/")
    if normal.startswith("/") or ":" in normal.split("/")[0]:
        raise PathSafetyError(f"绝对路径不允许: {rel_path!r}")
    parts = normal.split("/")
    if any(part in ("..", ".") or not part for part in parts):
        raise PathSafetyError(f"路径跨越不允许: {rel_path!r}")
    if normal not in OWNED_PATHS:
        raise PathSafetyError(f"路径不属于分析产物契约: {rel_path!r}")
    if normal.startswith(DENIED_PREFIXES) or normal.endswith(DENIED_SUFFIXES):
        raise PathSafetyError(f"路径在禁止清单内: {rel_path!r}")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def build_manifest(*, work_dir: Path, project_dir: Path, run_id: str,
                   corpus_fingerprint: str, params: Dict[str, Any],
                   produced: List[str],
                   previous_record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the publication manifest for a finished analysis run.

    ``produced`` is the runner's before/after file diff of the work copy;
    only produced files that the owned-output contract lists can enter the
    manifest, so stale leftovers can never impersonate new results.
    """
    work_dir = Path(work_dir)
    produced_set = {p.replace("\\", "/") for p in produced}
    files: List[Dict[str, Any]] = []
    excluded: List[str] = []
    for rel in sorted(produced_set):
        # Allowlist first: produced files outside the owned-output contract
        # (e.g. s4's internal _corpus_merged.txt) are simply not ours to
        # publish. Only dangerous paths raise.
        if rel not in OWNED_PATHS:
            excluded.append(rel)
            continue
        check_path_safety(rel)
        src = work_dir / rel
        if not src.exists() or not src.is_file():
            continue
        files.append({
            "relative_path": rel,
            "sha256": _sha256_file(src),
            "size": src.stat().st_size,
            "category": CATEGORY_BY_PATH[rel],
        })

    new_owned = {entry["relative_path"] for entry in files}
    previous_owned: List[str] = list((previous_record or {}).get("owned_paths", []))
    for rel in previous_owned:
        check_path_safety(rel)
    files_to_remove = sorted(rel for rel in previous_owned if rel not in new_owned)

    params_payload = json.dumps(params, ensure_ascii=False, sort_keys=True)
    manifest = {
        "manifest_version": 1,
        "run_id": run_id,
        "corpus_fingerprint": corpus_fingerprint,
        "params_hash": hashlib.sha1(params_payload.encode("utf-8")).hexdigest(),
        "previous_published_run_id": (previous_record or {}).get("published_run_id", ""),
        "generated_at": _now(),
        "files": files,
        "files_to_remove": files_to_remove,
        "excluded": sorted(set(excluded) | (produced_set - new_owned))[:50],
    }
    manifest["manifest_sha256"] = manifest_hash(manifest)
    return manifest


def manifest_hash(manifest: Dict[str, Any]) -> str:
    payload = json.dumps(
        {k: v for k, v in manifest.items() if k != "manifest_sha256"},
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_manifest(manifest: Dict[str, Any], work_dir: Path) -> None:
    """Full PREPARE validation: path safety + content hash verification."""
    for entry in manifest.get("files", []):
        rel = entry["relative_path"]
        check_path_safety(rel)
        src = Path(work_dir) / rel
        if not src.exists():
            raise PublicationError(f"manifest 文件缺失: {rel}")
        actual = _sha256_file(src)
        if actual != entry["sha256"]:
            raise PublicationError(
                f"哈希校验失败: {rel}(manifest {entry['sha256'][:12]} ≠ 实际 {actual[:12]})——"
                "工作副本产物在 manifest 生成后被修改,拒绝发布。")
    for rel in manifest.get("files_to_remove", []):
        check_path_safety(rel)


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------

STAGE_PREPARE = "PREPARE"
STAGE_BACKUP = "BACKUP"
STAGE_COMMITTING = "COMMITTING"
STAGE_COMMITTED = "COMMITTED"
STAGE_ROLLED_BACK = "ROLLED_BACK"
STAGE_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


def _tx_dir(project_dir: Path, run_id: str) -> Path:
    return Path(project_dir) / "runs" / f"pub_{run_id}"


def _write_journal(tx_dir: Path, journal: TransactionLog) -> None:
    tx_dir.mkdir(parents=True, exist_ok=True)
    tmp = tx_dir / "journal.json.tmp"
    tmp.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, tx_dir / "journal.json")


def _read_journal(tx_dir: Path) -> Optional[TransactionLog]:
    path = tx_dir / "journal.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def execute_publication(manifest: Dict[str, Any], work_dir: Path, project_dir: Path,
                        run_id: str,
                        progress_cb: Optional[Callable[[str, str], None]] = None,
                        fault_injection: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run the publication transaction; returns the committed publication record.

    Fault injection keys (execution-layer test hooks only):
    ``fail_entry_index``: raise when committing the Nth entry (0-based).
    """
    work_dir = Path(work_dir)
    root = Path(project_dir)
    tx_dir = _tx_dir(root, run_id)
    if tx_dir.exists():
        shutil.rmtree(tx_dir)
    staging = tx_dir / "staging"
    backup = tx_dir / "backup"

    def report(stage: str, message: str) -> None:
        if progress_cb:
            progress_cb(stage, message)

    # ---- PREPARE: validate manifest + source hashes -------------------
    report(STAGE_PREPARE, f"校验 manifest({len(manifest.get('files', []))} 个文件)")
    validate_manifest(manifest, work_dir)

    entries: List[Dict[str, Any]] = []
    for entry in manifest["files"]:
        rel = entry["relative_path"]
        staged = staging / rel
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(work_dir / rel, staged)
        if _sha256_file(staged) != entry["sha256"]:
            raise PublicationError(f"staging 哈希不一致: {rel}")
        target = root / rel
        action = "replace" if target.exists() else "create"
        entries.append({"action": action, "relative_path": rel,
                        "staged": str(staged), "sha256": entry["sha256"]})

    # ---- BACKUP: preserve the previous generation ----------------------
    report(STAGE_BACKUP, "备份将被替换/删除的旧 owned outputs")
    for rel in manifest.get("files_to_remove", []):
        target = root / rel
        if target.exists():
            kept = backup / rel
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, kept)
    for entry in entries:
        if entry["action"] == "replace":
            target = root / entry["relative_path"]
            kept = backup / entry["relative_path"]
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, kept)

    journal: TransactionLog = {
        "journal_version": 1,
        "run_id": run_id,
        "manifest_sha256": manifest["manifest_sha256"],
        "state": STAGE_COMMITTING,
        "started_at": _now(),
        "entries": entries,
        "removals": list(manifest.get("files_to_remove", [])),
    }
    tx_dir.mkdir(parents=True, exist_ok=True)
    _write_journal(tx_dir, journal)
    report(STAGE_COMMITTING, f"提交 {len(entries)} 个新文件,删除 {len(journal['removals'])} 个过期 owned output")

    fail_at = (fault_injection or {}).get("fail_entry_index")
    crash_after = (fault_injection or {}).get("crash_after_commit")
    sleep_in_publish = float((fault_injection or {}).get("sleep_in_publish") or 0)
    committed = 0
    try:
        for index, entry in enumerate(entries):
            if fail_at is not None and index == int(fail_at):
                raise PublicationError(f"[fault injection] 提交第 {index} 个文件时失败")
            if sleep_in_publish:
                import time
                time.sleep(sleep_in_publish)
            target = root / entry["relative_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(entry["staged"], target)
            committed += 1
            if crash_after is not None and committed >= int(crash_after):
                # Simulate a hard process death mid-COMMITTING: no rollback,
                # no journal update — recovery must restore the generation.
                sys.stderr.write("[test hook] simulated crash during COMMITTING\n")
                sys.stderr.flush()
                os._exit(70)
        for rel in journal["removals"]:
            target = root / rel
            if target.exists():
                if fault_injection and fault_injection.get("fail_removal"):
                    raise PublicationError("[fault injection] 删除过期 owned output 时失败")
                target.unlink()
    except Exception as exc:
        # ---- ROLLBACK: restore the complete previous generation ----------
        report(STAGE_ROLLED_BACK, f"发布失败,回滚: {exc}")
        _rollback(tx_dir, root, journal)
        journal["state"] = STAGE_ROLLED_BACK
        journal["error"] = str(exc)
        journal["finished_at"] = _now()
        _write_journal(tx_dir, journal)
        raise PublicationError(f"发布事务失败并已回滚: {exc}") from exc

    journal["state"] = STAGE_COMMITTED
    journal["finished_at"] = _now()
    _write_journal(tx_dir, journal)

    record = {
        "publication_version": 1,
        "published_run_id": run_id,
        "manifest_sha256": manifest["manifest_sha256"],
        "manifest": manifest,
        "corpus_fingerprint": manifest.get("corpus_fingerprint", ""),
        "params_hash": manifest.get("params_hash", ""),
        "owned_paths": [entry["relative_path"] for entry in entries],
        "completed_at": _now(),
        "transaction": {"state": STAGE_COMMITTED, "committed": committed,
                        "removed": len(journal["removals"])},
    }
    # COMMITTED: staging/backup may now be cleaned; the manifest record and
    # transaction trail live in the publication record.
    record_path = root / "runs" / f"publication_{run_id}.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(tx_dir, ignore_errors=True)
    write_published_pointer(root, record)
    archive_published_generation(root, record, progress_cb=progress_cb)
    merge_project_json(work_dir, root, progress_cb=progress_cb)
    report(STAGE_COMMITTED, f"已提交 {committed} 个文件")
    return record


def merge_project_json(work_dir: Path, project_dir: Path,
                       progress_cb: Optional[Callable[[str, str], None]] = None) -> None:
    """Merge analysis-owned fields of project.json after a committed publish.

    The work copy's project.json carries the analysis history entry and the
    refreshed ``latest`` pointers. Only those analysis-owned fields are
    merged into the real project.json — identity/config fields (project_id,
    name, project_dir, template, frozen_runs, ...) are never touched.
    Best-effort and additive: a failure here never rolls back committed files.
    """
    work_info = _read_json(Path(work_dir) / "project.json", {})
    root_path = Path(project_dir) / "project.json"
    root_info = _read_json(root_path, {})
    if not work_info or not root_info:
        return
    known = {(h.get("event"), h.get("at")) for h in root_info.get("history", [])}
    added = 0
    for entry in work_info.get("history", []):
        if entry.get("event") != "analyze":
            continue
        if (entry.get("event"), entry.get("at")) in known:
            continue
        root_info.setdefault("history", []).append(entry)
        added += 1
    latest = root_info.setdefault("latest", {})
    for key in ("analysis_output", "run_id", "corpus_id", "corpus_manifest",
                "documents_csv", "research_template", "validation_report", "group_by"):
        if key in work_info.get("latest", {}):
            latest[key] = work_info["latest"][key]
    root_info["updated_at"] = _now()
    root_path.write_text(json.dumps(root_info, ensure_ascii=False, indent=2), encoding="utf-8")
    if progress_cb:
        progress_cb("MERGED", f"project.json 合并 {added} 条分析历史(身份字段未改动)")


def _rollback(tx_dir: Path, root: Path, journal: TransactionLog) -> None:
    backup = tx_dir / "backup"
    for entry in journal.get("entries", []):
        target = root / entry["relative_path"]
        kept = backup / entry["relative_path"]
        if kept.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(kept, target)
        elif entry["action"] == "create" and target.exists():
            target.unlink()
    for rel in journal.get("removals", []):
        kept = backup / rel
        target = root / rel
        if kept.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(kept, target)


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------


def recover_publications(project_dir: str | Path) -> List[Dict[str, Any]]:
    """Find COMMITTING transactions from dead sessions and roll them back.

    Returns the recovery records. A transaction that cannot be restored is
    flagged RECOVERY_REQUIRED and the caller must refuse new publications.
    """
    root = Path(project_dir)
    recovered: List[Dict[str, Any]] = []
    if not (root / "runs").exists():
        return recovered
    for tx_dir in sorted((root / "runs").glob("pub_*/")):
        journal = _read_journal(tx_dir)
        if not journal or journal.get("state") != STAGE_COMMITTING:
            continue
        backup = tx_dir / "backup"
        try:
            _rollback(tx_dir, root, journal)
            journal["state"] = STAGE_ROLLED_BACK
            journal["recovery_note"] = ("Crash during COMMITTING; previous generation restored "
                                        "on next startup.")
            journal["recovered_at"] = _now()
            _write_journal(tx_dir, journal)
            recovered.append({"run_id": journal.get("run_id", tx_dir.name),
                              "state": STAGE_ROLLED_BACK})
        except Exception as exc:  # noqa: BLE001 - keep the scene, flag for humans
            journal["state"] = STAGE_RECOVERY_REQUIRED
            journal["recovery_error"] = str(exc)
            _write_journal(tx_dir, journal)
            recovered.append({"run_id": journal.get("run_id", tx_dir.name),
                              "state": STAGE_RECOVERY_REQUIRED})
    return recovered


def recovery_required(project_dir: str | Path) -> List[Dict[str, Any]]:
    root = Path(project_dir)
    pending: List[Dict[str, Any]] = []
    tx_root = root / "runs"
    if not tx_root.exists():
        return pending
    for tx_dir in sorted(tx_root.glob("pub_*/")):
        journal = _read_journal(tx_dir)
        if journal and journal.get("state") == STAGE_RECOVERY_REQUIRED:
            pending.append({"run_id": journal.get("run_id", tx_dir.name),
                            "dir": str(tx_dir)})
    return pending


# ---------------------------------------------------------------------------
# Published generation identity
# ---------------------------------------------------------------------------

PUBLISHED_POINTER = "published_analysis.json"


def published_pointer_path(project_dir: str | Path) -> Path:
    return Path(project_dir) / "runs" / PUBLISHED_POINTER


def write_published_pointer(project_dir: str | Path, record: Dict[str, Any]) -> Path:
    path = published_pointer_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    pointer = {
        "published_run_id": record.get("published_run_id", ""),
        "manifest_sha256": record.get("manifest_sha256", ""),
        "corpus_fingerprint": record.get("corpus_fingerprint", ""),
        "params_hash": record.get("params_hash", ""),
        "completed_at": record.get("completed_at", ""),
    }
    path.write_text(json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_published_pointer(project_dir: str | Path) -> Dict[str, Any]:
    path = published_pointer_path(project_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def last_publication_record(project_dir: str | Path) -> Optional[Dict[str, Any]]:
    """Latest COMMITTED publication record (the previous generation)."""
    root = Path(project_dir)
    runs_dir = root / "runs"
    if not runs_dir.exists():
        return None
    records = sorted(runs_dir.glob("publication_*.json"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    for path in records:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if record.get("transaction", {}).get("state") == STAGE_COMMITTED:
            return record
    return None


# ---------------------------------------------------------------------------
# Published generation archive (Phase 3A: Evidence Trail source of truth)
# ---------------------------------------------------------------------------

# Evidence only needs the analysis outputs it can resolve — never the raw
# corpus. Every archived artifact is hashed so INTEGRITY can be verified.
ARCHIVE_ARTIFACTS = [
    "adjectives_phrases.xlsx",
    "adjectives_final.xlsx",
    "01_corpus/documents.csv",
    "01_corpus/corpus_manifest.json",
    "run_config.json",
    "00_run_config/research_template.json",
    "07_reports/method_summary.md",
    "07_reports/method_limitations.md",
]


def published_dir(project_dir: str | Path, run_id: str) -> Path:
    return Path(project_dir) / "runs" / "published" / run_id


def archive_published_generation(project_dir: str | Path, record: Dict[str, Any],
                                 progress_cb: Optional[Callable[[str, str], None]] = None) -> Path:
    """Archive the immutable artifact set of one published generation.

    Layout: runs/published/<run_id>/publication_manifest.json + artifacts/<rel>.
    Read-only by convention: the Evidence layer resolves historical evidence
    here instead of the live project root.
    """
    root = Path(project_dir)
    run_id = record.get("published_run_id", "")
    gen_dir = published_dir(root, run_id)
    if gen_dir.exists():
        shutil.rmtree(gen_dir)  # re-publishing the same run id re-archives
    artifacts = gen_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    archived: List[Dict[str, Any]] = []
    for rel in ARCHIVE_ARTIFACTS:
        src = root / rel
        if not src.exists():
            continue
        dst = artifacts / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        archived.append({
            "relative_path": rel,
            "sha256": _sha256_file(dst),
            "size": dst.stat().st_size,
        })

    manifest_doc = {
        "archive_version": 1,
        "published_run_id": run_id,
        "publication_manifest_sha256": record.get("manifest_sha256", ""),
        "corpus_fingerprint": record.get("corpus_fingerprint", ""),
        "params_hash": record.get("params_hash", ""),
        "completed_at": record.get("completed_at", ""),
        "artifacts": archived,
        "archived_at": _now(),
    }
    (gen_dir / "publication_manifest.json").write_text(
        json.dumps(manifest_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    if progress_cb:
        progress_cb("ARCHIVED", f"已归档 {len(archived)} 个正式产物到 runs/published/{run_id}")
    return gen_dir
