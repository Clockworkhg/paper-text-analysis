# -*- coding: utf-8 -*-
"""Human-review write boundary for gui-next.

This module is the ONLY place gui-next is allowed to write. It stores
reviewer decisions as JSON state files under ``06_review/`` using the
stable ids already defined by the project (``review_id`` from the review
workbooks, ``Source_Merged`` for source/country review).

Rules:
- never touches the corpus, the analysis workbook, run configs, or shared/
  outputs;
- never calls analysis code;
- writes are atomic (tmp file + os.replace); a failed write leaves the
  previous state file untouched and no half-written files behind.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from gui_next.data.contracts import EvidenceRef

SOURCE_STATE_FILE = "source_country_review_state.json"
SEMANTIC_STATE_FILE = "semantic_review_state.json"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON atomically: tmp file in the same dir, then os.replace.

    On any failure the tmp file is removed and the original file (if any)
    stays byte-identical.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _read_state(path: Path, review_type: str) -> Dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if not isinstance(state, dict) or state.get("review_type") != review_type:
        state = {"review_type": review_type, "schema": 1}
    state.setdefault("decisions", {})
    return state


def stable_item_id(*parts: Any) -> str:
    """Deterministic id for items that predate review_id columns."""
    seed = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]


class BaseReviewStore:
    """Shared persistence helpers. Subclasses own domain logic only."""

    review_type = ""
    state_filename = ""

    def __init__(self, project_dir: str | Path):
        self.root = Path(project_dir)
        self.state_path = self.root / "06_review" / self.state_filename
        self.state = _read_state(self.state_path, self.review_type)

    @property
    def decisions(self) -> Dict[str, Dict[str, Any]]:
        return self.state.setdefault("decisions", {})

    def save(self) -> Path:
        self.state["updated_at"] = _now()
        atomic_write_json(self.state_path, self.state)
        return self.state_path


class SourceCountryReviewStore(BaseReviewStore):
    """Reviewer decisions over merged sources and their country labels.

    Items come from ``merged_sources.xlsx`` (WithCountry + RowMapping) when
    available; otherwise the document registry provides the source list so
    country review can proceed before step 3 has ever run.
    """

    review_type = "source_country"
    state_filename = SOURCE_STATE_FILE

    def __init__(self, project_dir: str | Path, documents_df=None):
        self.root = Path(project_dir)
        self.items: List[Dict[str, Any]] = []
        self._load_items(documents_df)
        super().__init__(project_dir)

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
                    items.append({
                        "source": source,
                        "original": raw_by_norm.get(source, ""),
                        "documents": row.get("Count_Sum", ""),
                        "country": "" if pd.isna(row.get("Country")) else str(row.get("Country")),
                        "suggested_country": "" if pd.isna(row.get("Country")) else str(row.get("Country")),
                        "confidence": None if pd.isna(confidence) else confidence,
                        "evidence": self._evidence_lines(row),
                    })
            except Exception:
                items = []

        if not items and documents_df is not None and not documents_df.empty and "source_normalized" in documents_df.columns:
            docs = documents_df.copy()
            docs["source_normalized"] = docs["source_normalized"].fillna("Unknown").astype(str)
            grouped = docs.groupby("source_normalized")
            for source, group in grouped:
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

    def item_by_source(self, source: str) -> Optional[Dict[str, Any]]:
        for item in self.items:
            if item["source"] == source:
                return item
        return None

    def set_decision(self, source: str, decision: str, country: str = "",
                     note: str = "") -> Dict[str, Any]:
        record = {
            "decision": decision,
            "country": country.strip(),
            "note": note.strip(),
            "at": _now(),
            "evidence": EvidenceRef(
                item_type="source_country", item_id=source,
            ).to_dict(),
        }
        self.decisions[source] = record
        return record

    def decided_sources(self) -> List[str]:
        return [source for source in self.decisions if self.item_by_source(source)]

    def progress(self) -> Dict[str, int]:
        total = len(self.items)
        decided = len(self.decided_sources())
        return {"total": total, "decided": decided, "pending": max(total - decided, 0)}

    def next_pending(self, after_index: int) -> int:
        for offset in range(1, len(self.items) + 1):
            index = (after_index + offset) % len(self.items)
            if self.items[index]["source"] not in self.decisions:
                return index
        return (after_index + 1) % len(self.items) if self.items else 0


class SemanticReviewStore(BaseReviewStore):
    """Reviewer coding for semantic-prosody candidates.

    Items come from ``06_review/modifier_semantic_review.xlsx`` (sheet
    SemanticProsodyReview, keyed by the workbook's stable ``review_id``);
    when absent, falls back to the SemanticProsodyCandidates sheet of the
    analysis workbook with deterministic ids.
    """

    review_type = "semantic"
    state_filename = SEMANTIC_STATE_FILE

    CONTEXT_DOC_LIMIT = 3

    def __init__(self, project_dir: str | Path, kwic_df=None, documents_df=None):
        self.root = Path(project_dir)
        self._kwic = kwic_df if kwic_df is not None else pd.DataFrame()
        self._documents = documents_df if documents_df is not None else pd.DataFrame()
        self.items: List[Dict[str, Any]] = []
        self._load_items()
        super().__init__(project_dir)
        cursor = self.state.get("cursor")
        self.cursor = cursor if isinstance(cursor, int) and 0 <= cursor < max(len(self.items), 1) else 0

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
                except Exception:
                    rows = pd.DataFrame()

        for _, row in rows.iterrows():
            review_id = str(row.get("review_id", "") or "")
            document_ids = str(row.get("Document_IDs", "") or "")
            first_doc = document_ids.split(" | ")[0].strip() if document_ids else ""
            if not review_id:
                review_id = stable_item_id(
                    row.get("Corpus_ID", ""), document_ids, row.get("Target", ""),
                    row.get("Kind", ""), row.get("Expression", ""),
                )
            run_id = str(row.get("Run_ID", "") or "")
            items_id = review_id
            self.items.append({
                "item_id": items_id,
                "source_file": source_file,
                "evidence": EvidenceRef(
                    item_type="semantic_candidate",
                    item_id=review_id,
                    document_id=first_doc,
                    run_id=run_id,
                ).to_dict(),
                "target": "" if pd.isna(row.get("Target")) else str(row.get("Target")),
                "kind": "" if pd.isna(row.get("Kind")) else str(row.get("Kind")),
                "expression": "" if pd.isna(row.get("Expression")) else str(row.get("Expression")),
                "suggestion": "" if pd.isna(row.get("Polarity_Candidate")) else str(row.get("Polarity_Candidate")),
                "domain": "" if pd.isna(row.get("Semantic_Domain_Candidate")) else str(row.get("Semantic_Domain_Candidate")),
                "document_id": first_doc,
                "document_ids": document_ids,
                "run_id": run_id,
                "from_workbook": from_workbook,
            })

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

    def _context_lines(self, item: Dict[str, Any]) -> str:
        """Reconstruct extended context from the KWIC sheet for this candidate."""
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
        """Persist a note independently of a decision (notes survive revisits)."""
        note = note.strip()
        notes = self.state.setdefault("notes", {})
        if note:
            notes[item_id] = note
        else:
            notes.pop(item_id, None)

    def note_for(self, item_id: str) -> str:
        decision = self.decisions.get(item_id, {})
        if decision.get("note"):
            return str(decision["note"])
        return str(self.state.get("notes", {}).get(item_id, ""))

    def set_decision(self, item_id: str, decision: str, note: str = "") -> Dict[str, Any]:
        item = next((entry for entry in self.items if entry["item_id"] == item_id), None)
        record = {
            "decision": decision,
            "note": note.strip(),
            "at": _now(),
            "evidence": (item or {}).get("evidence", EvidenceRef(
                item_type="semantic_candidate", item_id=item_id).to_dict()),
        }
        self.decisions[item_id] = record
        return record

    def progress(self) -> Dict[str, int]:
        total = len(self.items)
        coded = sum(1 for item in self.items if item["item_id"] in self.decisions)
        return {"total": total, "coded": coded, "pending": max(total - coded, 0)}
