# -*- coding: utf-8 -*-
"""Human-review write boundary for gui-next (schema v2, state integrity).

This module is the ONLY place gui-next is allowed to write. It stores
reviewer decisions as JSON state files under ``06_review/``.

State integrity (Phase 2A.1):

- every state file records provenance metadata (schema_version, project
  identity, run_id, corpus fingerprint, candidate/source input fingerprint,
  created_at/updated_at);
- every decision records an ``item_fingerprint`` binding it to the exact
  research object (review_id + document + target + candidate content);
- decisions are only applied when the item fingerprint matches; anything
  else is preserved but marked stale and excluded from progress;
- legacy (schema<2) states never silently re-apply their decisions;
- saves use optimistic single-writer protection: if the file on disk changed
  since this store last read/wrote it, the save is refused;
- recent operations are kept in a persisted history for Ctrl+Z undo.

Rules that never change: no analysis code is called; corpus, analysis
workbooks, run configs and shared outputs are never touched; writes are
atomic (tmp + os.replace) and a failed write leaves no partial file.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from gui_next.data.contracts import EvidenceRef

SOURCE_STATE_FILE = "source_country_review_state.json"
SEMANTIC_STATE_FILE = "semantic_review_state.json"
SCHEMA_VERSION = 2
HISTORY_LIMIT = 50


class ReviewStateConflictError(RuntimeError):
    """Another writer changed the review state since it was loaded."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _file_sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def rows_fingerprint(parts: List[Tuple[str, ...]]) -> str:
    """Deterministic fingerprint over the *content* of a candidate set.

    Content-based, so benign regeneration of an identical candidate set
    does not invalidate decisions, while any content change does.
    """
    digest = hashlib.sha1()
    for line in sorted(";".join("" if p is None else str(p) for p in row) for row in parts):
        digest.update(line.encode("utf-8", errors="ignore"))
        digest.update(b"\n")
    return digest.hexdigest()[:16]


def item_fingerprint(*parts: Any) -> str:
    seed = "|".join("" if p is None else str(p) for p in parts)
    return _sha1(seed)


def atomic_write_json(path: Path, data: Dict[str, Any]) -> str:
    """Write JSON atomically; returns the sha256 of the written bytes.

    tmp file in the same directory + os.replace; on any failure the tmp file
    is removed and any existing file stays byte-identical.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_name(path.name + ".tmp")
    try:
        # Binary mode: newline translation would make the on-disk bytes
        # differ from the returned hash used for single-writer detection.
        with open(tmp, "wb") as handle:
            handle.write(payload.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class BaseReviewStore:
    """Shared provenance, conflict detection, status and undo plumbing."""

    review_type = ""
    state_filename = ""

    def __init__(self, project_dir: str | Path):
        self.root = Path(project_dir)
        self.project = _read_json(self.root / "project.json")
        self.run_config = _read_json(self.root / "run_config.json")
        self.state_path = self.root / "06_review" / self.state_filename
        self.state, self._disk_hash = self._load_state()
        self._corpus_fp_current = self._current_corpus_fingerprint()
        self.cursor = int(self.state.get("cursor") or 0)
        self.stale_reasons: List[str] = self._state_level_stale_reasons()
        self.applied_decisions: Dict[str, Dict[str, Any]] = {}
        self.stale_decision_ids: List[str] = []

    # -- loading -------------------------------------------------------

    def _load_state(self) -> Tuple[Dict[str, Any], Optional[str]]:
        raw = None
        if self.state_path.exists():
            try:
                raw = self.state_path.read_bytes()
            except OSError:
                raw = None
        if raw is None:
            return self._fresh_state(), None
        try:
            state = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._fresh_state(), None
        if not isinstance(state, dict) or state.get("review_type") != self.review_type:
            return self._fresh_state(), None
        state.setdefault("decisions", {})
        state.setdefault("notes", {})
        state.setdefault("history", [])
        return state, hashlib.sha256(raw).hexdigest()

    def _fresh_state(self) -> Dict[str, Any]:
        return {
            "review_type": self.review_type,
            "schema_version": SCHEMA_VERSION,
            "decisions": {},
            "notes": {},
            "history": [],
        }

    def reload(self) -> None:
        """Re-read state from disk (e.g. after a conflict error)."""
        fresh = type(self)(self.root, **self._reload_kwargs())
        self.state, self._disk_hash = fresh.state, fresh._disk_hash
        self.stale_reasons = fresh.stale_reasons
        self.applied_decisions = fresh.applied_decisions
        self.stale_decision_ids = fresh.stale_decision_ids
        self._post_reload(fresh)

    def _reload_kwargs(self) -> Dict[str, Any]:
        return {}

    def _post_reload(self, fresh: "BaseReviewStore") -> None:
        return None

    # -- provenance ------------------------------------------------------

    def input_fingerprint(self) -> str:
        raise NotImplementedError

    def input_provenance(self) -> Dict[str, Any]:
        return {}

    def _current_corpus_fingerprint(self) -> str:
        corpus = self.root / "corpus"
        if not corpus.exists() or not any(corpus.rglob("*.txt")):
            return ""
        try:
            from shared.corpus_sanity import corpus_fingerprint
            return corpus_fingerprint(corpus)["sha256"]
        except Exception:
            return ""

    def _state_level_stale_reasons(self) -> List[str]:
        reasons: List[str] = []
        has_decisions = bool(self.state.get("decisions"))
        if has_decisions and int(self.state.get("schema_version") or 0) < SCHEMA_VERSION:
            reasons.append("legacy_schema")
        state_corpus = self.state.get("corpus_fingerprint")
        if has_decisions and state_corpus and self._corpus_fp_current \
                and state_corpus != self._corpus_fp_current:
            reasons.append("corpus_changed")
        return reasons

    # -- decision application -------------------------------------------

    def _apply_state_decisions(self) -> None:
        """Apply only fingerprint-verified decisions to the current items."""
        self.applied_decisions = {}
        self.stale_decision_ids = []
        if self.stale_reasons:
            return
        for item_id, record in self.state.get("decisions", {}).items():
            item = self.item_by_id(item_id)
            if item is None:
                continue  # candidate removed from the set: dormant, kept
            if record.get("item_fingerprint") == item.get("item_fingerprint"):
                self.applied_decisions[item_id] = record
            else:
                self.stale_decision_ids.append(item_id)

    def item_by_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    # -- status ----------------------------------------------------------

    def status(self) -> str:
        """NOT_STARTED / IN_PROGRESS / COMPLETE / STALE."""
        if self.stale_reasons or self.stale_decision_ids:
            return "STALE"
        total = len(self.items)
        coded = len(self.applied_decisions)
        if total == 0 or coded == 0:
            return "NOT_STARTED"
        return "COMPLETE" if coded >= total else "IN_PROGRESS"

    def stale_summary(self) -> str:
        parts = []
        if "legacy_schema" in self.stale_reasons:
            parts.append("旧版 state(schema<2)需迁移")
        if "corpus_changed" in self.stale_reasons:
            parts.append("语料指纹已变化")
        if self.stale_decision_ids:
            parts.append(f"{len(self.stale_decision_ids)} 条旧决定与当前候选不一致")
        return ";".join(parts)

    # -- writing ---------------------------------------------------------

    def _metadata(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project.get("project_id", ""),
            "project_name": self.project.get("name", ""),
            "run_id": self.run_config.get("run_id", ""),
            "corpus_fingerprint": self._corpus_fp_current,
            "input_fingerprint": self.input_fingerprint(),
            "input_provenance": self.input_provenance(),
            "created_at": self.state.get("created_at") or _now(),
            "updated_at": _now(),
        }

    def _check_single_writer(self) -> None:
        current = _file_sha256(self.state_path) if self.state_path.exists() else None
        if current != self._disk_hash:
            raise ReviewStateConflictError(
                f"复核状态文件已被另一个实例修改({self.state_path.name})。"
                "为避免覆盖他人更改,本次写入被拒绝;请调用 reload() 后重试。"
            )

    def save(self) -> Path:
        self._check_single_writer()
        self.state.update(self._metadata())
        self._disk_hash = atomic_write_json(self.state_path, self.state)
        return self.state_path

    # -- undo ------------------------------------------------------------

    def _push_history(self, entry: Dict[str, Any]) -> None:
        history: List[Dict[str, Any]] = self.state.setdefault("history", [])
        history.append(entry)
        del history[:-HISTORY_LIMIT]

    def _record_decision_change(self, item_id: str) -> None:
        self._push_history({
            "kind": "decision",
            "item_id": item_id,
            "before": self.state["decisions"].get(item_id),
            "cursor_before": self.cursor,
            "at": _now(),
        })

    def _record_note_change(self, item_id: str) -> None:
        self._push_history({
            "kind": "note",
            "item_id": item_id,
            "before": self.state.get("notes", {}).get(item_id, ""),
            "cursor_before": self.cursor,
            "at": _now(),
        })

    def undo(self) -> Optional[str]:
        """Undo the most recent decision/note change; returns its item id."""
        history: List[Dict[str, Any]] = self.state.setdefault("history", [])
        if not history:
            return None
        entry = history.pop()
        item_id = entry["item_id"]
        before = entry.get("before")
        if entry["kind"] == "decision":
            if before is None:
                self.state["decisions"].pop(item_id, None)
                self.applied_decisions.pop(item_id, None)
            else:
                self.state["decisions"][item_id] = before
                item = self.item_by_id(item_id)
                if item is not None and before.get("item_fingerprint") == item.get("item_fingerprint"):
                    self.applied_decisions[item_id] = before
                else:
                    self.applied_decisions.pop(item_id, None)
        else:
            notes = self.state.setdefault("notes", {})
            if before:
                notes[item_id] = before
            else:
                notes.pop(item_id, None)
        self.set_cursor(int(entry.get("cursor_before", self.cursor)))
        self.save()
        return item_id


class SourceCountryReviewStore(BaseReviewStore):
    """Reviewer decisions over merged sources and their country labels.

    Items come from ``merged_sources.xlsx`` (WithCountry + RowMapping) when
    available; otherwise the document registry provides the source list.
    """

    review_type = "source_country"
    state_filename = SOURCE_STATE_FILE

    def __init__(self, project_dir: str | Path, documents_df=None):
        self.root = Path(project_dir)
        self.items: List[Dict[str, Any]] = []
        self._input_file = ""
        self._input_file_sha256 = None
        self._load_items(documents_df)
        super().__init__(project_dir)
        self._apply_state_decisions()

    # ------------------------------------------------------------------

    def _load_items(self, documents_df=None) -> None:
        root = self.root
        merged_path = root / "merged_sources.xlsx"
        items: List[Dict[str, Any]] = []
        if merged_path.exists():
            try:
                with_country = pd.read_excel(merged_path, sheet_name="WithCountry")
                mapping = pd.DataFrame()
                try:
                    mapping = pd.read_excel(merged_path, sheet_name="RowMapping")
                except Exception:
                    mapping = pd.DataFrame()
                raw_by_norm: Dict[str, str] = {}
                if not mapping.empty:
                    norm_col = next((c for c in mapping.columns if "norm" in c.lower()), None)
                    raw_col = next((c for c in mapping.columns if "raw" in c.lower()), None)
                    if norm_col and raw_col:
                        for _, row in mapping.iterrows():
                            key = str(row[norm_col] or "").strip()
                            if key:
                                raw_by_norm.setdefault(key, str(row[raw_col] or ""))
                for _, row in with_country.iterrows():
                    source = str(row.get("Source_Merged", "") or "").strip()
                    if not source:
                        continue
                    confidence = row.get("Confidence")
                    country = "" if pd.isna(row.get("Country")) else str(row.get("Country"))
                    items.append({
                        "source": source,
                        "original": raw_by_norm.get(source, ""),
                        "documents": row.get("Count_Sum", ""),
                        "country": country,
                        "suggested_country": country,
                        "confidence": None if pd.isna(confidence) else confidence,
                        "evidence": self._evidence_lines(row),
                    })
            except Exception:
                items = []
            self._input_file = merged_path.name
            self._input_file_sha256 = _file_sha256(merged_path)

        if not items and documents_df is not None and not documents_df.empty and "source_normalized" in documents_df.columns:
            docs = documents_df.copy()
            docs["source_normalized"] = docs["source_normalized"].fillna("Unknown").astype(str)
            for source, group in docs.groupby("source_normalized"):
                country = ""
                if "country" in group.columns:
                    values = group["country"].dropna().astype(str)
                    country = values.mode().iat[0] if not values.empty and values.mode().iat[0] != "Unknown" else ""
                originals = (
                    group["source_raw"].dropna().astype(str)
                    if "source_raw" in group.columns else pd.Series(dtype=str)
                )
                items.append({
                    "source": source,
                    "original": originals.iloc[0] if not originals.empty else "",
                    "documents": len(group),
                    "country": country,
                    "suggested_country": country,
                    "confidence": None,
                    "evidence": ["来源清单来自文档登记表(merged_sources.xlsx 尚未生成)"],
                })
            registry = root / "01_corpus" / "documents.csv"
            self._input_file = "01_corpus/documents.csv"
            self._input_file_sha256 = _file_sha256(registry)

        for item in items:
            item["item_fingerprint"] = item_fingerprint(
                item["source"], item.get("original", ""), item.get("suggested_country", ""),
            )
        items.sort(key=lambda item: -float(item.get("documents") or 0))
        self.items = items

    @staticmethod
    def _evidence_lines(row: pd.Series) -> List[str]:
        lines: List[str] = []
        country = row.get("Country")
        if not pd.isna(country) and str(country):
            lines.append(f"合并国别结果: {country}")
        confidence = row.get("Confidence")
        if not pd.isna(confidence):
            lines.append(f"置信度: {confidence}")
        return lines or ["(无自动证据记录)"]

    # ------------------------------------------------------------------

    def input_fingerprint(self) -> str:
        return rows_fingerprint([
            (item["source"], item.get("original", ""), item.get("suggested_country", ""))
            for item in self.items
        ])

    def input_provenance(self) -> Dict[str, Any]:
        return {"input_file": self._input_file, "input_file_sha256": self._input_file_sha256}

    def item_by_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self.item_by_source(item_id)

    def item_by_source(self, source: str) -> Optional[Dict[str, Any]]:
        for item in self.items:
            if item["source"] == source:
                return item
        return None

    @property
    def decisions(self) -> Dict[str, Dict[str, Any]]:
        """Fingerprint-verified decisions currently in effect."""
        return self.applied_decisions

    def set_decision(self, source: str, decision: str, country: str = "",
                     note: str = "") -> Dict[str, Any]:
        item = self.item_by_source(source)
        record = {
            "decision": decision,
            "country": country.strip(),
            "note": note.strip(),
            "at": _now(),
            "item_fingerprint": item["item_fingerprint"] if item else "",
            "evidence": EvidenceRef(item_type="source_country", item_id=source).to_dict(),
        }
        self._record_decision_change(source)
        self.state["decisions"][source] = record
        if item is not None and record["item_fingerprint"]:
            self.applied_decisions[source] = record
        return record

    def decided_sources(self) -> List[str]:
        return [source for source in self.applied_decisions if self.item_by_source(source)]

    def progress(self) -> Dict[str, Any]:
        total = len(self.items)
        decided = len(self.decided_sources())
        return {
            "total": total,
            "decided": decided,
            "pending": max(total - decided, 0),
            "status": self.status(),
            "stale_count": len(self.stale_decision_ids),
        }

    def next_pending(self, after_index: int) -> int:
        for offset in range(1, len(self.items) + 1):
            index = (after_index + offset) % len(self.items)
            if self.items[index]["source"] not in self.applied_decisions:
                return index
        return (after_index + 1) % len(self.items) if self.items else 0


class SemanticReviewStore(BaseReviewStore):
    """Reviewer coding for semantic-prosody candidates.

    Items come from ``06_review/modifier_semantic_review*.xlsx`` (sheet
    SemanticProsodyReview, keyed by the workbook's stable ``review_id``);
    falls back to the analysis workbook's SemanticProsodyCandidates sheet.
    """

    review_type = "semantic"
    state_filename = SEMANTIC_STATE_FILE
    CONTEXT_DOC_LIMIT = 3

    def __init__(self, project_dir: str | Path, kwic_df=None, documents_df=None):
        self.root = Path(project_dir)
        self._kwic = kwic_df if kwic_df is not None else pd.DataFrame()
        self._documents = documents_df if documents_df is not None else pd.DataFrame()
        self.items: List[Dict[str, Any]] = []
        self._input_file = ""
        self._input_file_sha256 = None
        self._load_items()
        super().__init__(project_dir)
        self._apply_state_decisions()
        cursor = self.state.get("cursor")
        self.cursor = cursor if isinstance(cursor, int) and 0 <= cursor < max(len(self.items), 1) else 0

    def _reload_kwargs(self) -> Dict[str, Any]:
        return {"kwic_df": self._kwic, "documents_df": self._documents}

    def _post_reload(self, fresh: "SemanticReviewStore") -> None:
        self.cursor = fresh.cursor

    # ------------------------------------------------------------------

    def _load_items(self) -> None:
        review_path = self._find_review_workbook()
        rows = pd.DataFrame()
        source_file = ""
        if review_path:
            try:
                rows = pd.read_excel(review_path, sheet_name="SemanticProsodyReview")
                source_file = review_path.name
            except Exception:
                rows = pd.DataFrame()
        from_workbook = not rows.empty
        if rows.empty:
            analysis = self.root / "adjectives_phrases.xlsx"
            if analysis.exists():
                try:
                    rows = pd.read_excel(analysis, sheet_name="SemanticProsodyCandidates")
                    source_file = analysis.name
                except Exception:
                    rows = pd.DataFrame()

        for _, row in rows.iterrows():
            review_id = str(row.get("review_id", "") or "")
            document_ids = str(row.get("Document_IDs", "") or "")
            first_doc = document_ids.split(" | ")[0].strip() if document_ids else ""
            corpus_id = "" if pd.isna(row.get("Corpus_ID")) else str(row.get("Corpus_ID"))
            run_id = "" if pd.isna(row.get("Run_ID")) else str(row.get("Run_ID"))
            target = "" if pd.isna(row.get("Target")) else str(row.get("Target"))
            kind = "" if pd.isna(row.get("Kind")) else str(row.get("Kind"))
            expression = "" if pd.isna(row.get("Expression")) else str(row.get("Expression"))
            polarity = "" if pd.isna(row.get("Polarity_Candidate")) else str(row.get("Polarity_Candidate"))
            if not review_id:
                review_id = "anon_" + item_fingerprint(corpus_id, document_ids, target, kind, expression, polarity)
            self.items.append({
                "item_id": review_id,
                "item_fingerprint": item_fingerprint(
                    review_id, corpus_id, document_ids, target, kind, expression, polarity,
                ),
                "source_file": source_file,
                "evidence": EvidenceRef(
                    item_type="semantic_candidate",
                    item_id=review_id,
                    document_id=first_doc,
                    run_id=run_id,
                ).to_dict(),
                "target": target,
                "kind": kind,
                "expression": expression,
                "suggestion": polarity,
                "domain": "" if pd.isna(row.get("Semantic_Domain_Candidate")) else str(row.get("Semantic_Domain_Candidate")),
                "document_id": first_doc,
                "document_ids": document_ids,
                "run_id": run_id,
                "from_workbook": from_workbook,
            })
        if review_path:
            self._input_file = source_file
            self._input_file_sha256 = _file_sha256(review_path) if from_workbook else _file_sha256(self.root / source_file)

    def _find_review_workbook(self) -> Optional[Path]:
        review_dir = self.root / "06_review"
        if not review_dir.exists():
            return None
        for name in (
            "modifier_semantic_review_FINAL.xlsx",
            "modifier_semantic_review.xlsx",
        ):
            path = review_dir / name
            if path.exists():
                return path
        coder_files = sorted(review_dir.glob("modifier_semantic_review_coder_*.xlsx"))
        return coder_files[-1] if coder_files else None

    def input_fingerprint(self) -> str:
        return rows_fingerprint([
            (
                item["item_id"], item["document_ids"], item["target"],
                item["kind"], item["expression"], item["suggestion"],
            )
            for item in self.items
        ])

    def input_provenance(self) -> Dict[str, Any]:
        return {"input_file": self._input_file, "input_file_sha256": self._input_file_sha256}

    def item_by_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        return next((item for item in self.items if item["item_id"] == item_id), None)

    @property
    def decisions(self) -> Dict[str, Dict[str, Any]]:
        """Fingerprint-verified decisions currently in effect."""
        return self.applied_decisions

    def _context_lines(self, item: Dict[str, Any]) -> str:
        kwic = self._kwic
        if kwic.empty:
            return ""
        mask = pd.Series(True, index=kwic.index)
        if item["document_id"] and "Document_ID" in kwic.columns:
            mask &= kwic["Document_ID"].astype(str) == item["document_id"]
        if item["target"] and "Target" in kwic.columns:
            mask &= kwic["Target"].astype(str) == item["target"]
        matches = kwic[mask]
        lines: List[str] = []
        for _, row in matches.head(self.CONTEXT_DOC_LIMIT).iterrows():
            text = str(row.get("Full_Context", "")).strip()
            if text:
                lines.append(text)
        return "\n———\n".join(lines)

    def context_for(self, item: Dict[str, Any]) -> str:
        if "context" not in item:
            item["context"] = self._context_lines(item)
        return item["context"]

    def document_path(self, item: Dict[str, Any]) -> Optional[Path]:
        if not item.get("document_id") or self._documents.empty:
            return None
        docs = self._documents
        if "document_id" not in docs.columns or "relative_path" not in docs.columns:
            return None
        match = docs[docs["document_id"].astype(str) == item["document_id"]]
        if match.empty:
            return None
        rel = str(match.iloc[0]["relative_path"]).replace("\\", "/")
        path = self.root / "corpus" / rel
        return path if path.exists() else None

    # ------------------------------------------------------------------

    def current_item(self) -> Optional[Dict[str, Any]]:
        if not self.items:
            return None
        return self.items[min(self.cursor, len(self.items) - 1)]

    def set_cursor(self, index: int) -> None:
        if self.items:
            self.cursor = max(0, min(index, len(self.items) - 1))
            self.state["cursor"] = self.cursor

    def set_note(self, item_id: str, note: str) -> None:
        """Persist a note independently of a decision."""
        note = note.strip()
        self._record_note_change(item_id)
        notes = self.state.setdefault("notes", {})
        if note:
            notes[item_id] = note
        else:
            notes.pop(item_id, None)

    def note_for(self, item_id: str) -> str:
        decision = self.applied_decisions.get(item_id, {})
        if decision.get("note"):
            return str(decision["note"])
        return str(self.state.get("notes", {}).get(item_id, ""))

    def set_decision(self, item_id: str, decision: str, note: str = "") -> Dict[str, Any]:
        item = self.item_by_id(item_id)
        record = {
            "decision": decision,
            "note": note.strip(),
            "at": _now(),
            "item_fingerprint": item["item_fingerprint"] if item else "",
            "evidence": (item or {}).get("evidence", EvidenceRef(
                item_type="semantic_candidate", item_id=item_id).to_dict()),
        }
        self._record_decision_change(item_id)
        self.state["decisions"][item_id] = record
        if item is not None and record["item_fingerprint"]:
            self.applied_decisions[item_id] = record
        return record

    def progress(self) -> Dict[str, Any]:
        total = len(self.items)
        coded = len(self.applied_decisions)
        return {
            "total": total,
            "coded": coded,
            "pending": max(total - coded, 0),
            "status": self.status(),
            "stale_count": len(self.stale_decision_ids),
        }
