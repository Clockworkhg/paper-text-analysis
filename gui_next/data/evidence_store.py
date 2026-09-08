# -*- coding: utf-8 -*-
"""Evidence write boundary (Phase 3A): claims + evidence records.

The single place gui-next is allowed to write Evidence Trail data, stored
independently at ``08_evidence/evidence.json``. This store is NOT part of
the analysis owned-output contract — publication never touches it.

Guarantees carried over from the review store: schema version, provenance
metadata, atomic writes (tmp + os.replace), optimistic single-writer
conflict detection, and preservation of prior state on failure.

Evidence identity: a record is unique per
``published_run_id + evidence_type + item_fingerprint``; adding the same
item twice returns the existing record (idempotent). Evidence binds strictly
to a COMMITTED published generation — the caller passes full provenance
(published_run_id, publication_manifest_hash, corpus_fingerprint,
parameters_hash); the store records it verbatim.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EVIDENCE_STATE_FILE = "evidence.json"
SCHEMA_VERSION = 1
HISTORY_LIMIT = 100

EVIDENCE_TYPES = ("kwic", "collocate_pattern", "phrase_pattern", "group_pattern")


class EvidenceStateConflictError(RuntimeError):
    """Another writer changed the evidence store since it was loaded."""


class EvidenceReferencedError(RuntimeError):
    """The evidence record is still referenced by claims (delete refused)."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_json(path: Path, data: Dict[str, Any]) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_name(path.name + ".tmp")
    try:
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


def item_fingerprint(*parts: Any) -> str:
    seed = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]


class EvidenceStore:
    """Claims + evidence records for one project (single write boundary)."""

    def __init__(self, project_dir: str | Path):
        self.root = Path(project_dir)
        self.state_path = self.root / "08_evidence" / "evidence.json"
        self.state, self._disk_hash = self._load_state()
        self.claims_order: List[str] = list(self.state.get("claims_order", []))

    # ------------------------------------------------------------------
    # persistence

    def _fresh_state(self) -> Dict[str, Any]:
        return {
            "store": "evidence",
            "schema_version": SCHEMA_VERSION,
            "project_id": "",
            "decisions": {},
            "evidence": {},
            "claims": {},
            "claims_order": [],
            "history": [],
        }

    def _load_state(self) -> Tuple[Dict[str, Any], Optional[str]]:
        if not self.state_path.exists():
            return self._fresh_state(), None
        raw = self.state_path.read_bytes()
        try:
            state = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._fresh_state(), None
        if not isinstance(state, dict) or state.get("store") != "evidence":
            return self._fresh_state(), None
        state.setdefault("evidence", {})
        state.setdefault("claims", {})
        state.setdefault("claims_order", [])
        state.setdefault("history", [])
        project = self._read_project()
        state.setdefault("project_id", project.get("project_id", ""))
        return state, hashlib.sha256(raw).hexdigest()

    def _read_project(self) -> Dict[str, Any]:
        try:
            return json.loads((self.root / "project.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def reload(self) -> None:
        fresh = EvidenceStore(self.root)
        self.state, self._disk_hash = fresh.state, fresh._disk_hash
        self.claims_order = fresh.claims_order

    def save(self) -> Path:
        current = None
        if self.state_path.exists():
            current = hashlib.sha256(self.state_path.read_bytes()).hexdigest()
        if current != self._disk_hash:
            raise EvidenceStateConflictError(
                "证据库已被另一个实例修改(evidence.json)。为避免覆盖他人更改,"
                "本次写入被拒绝;请刷新后重试。")
        state = dict(self.state)
        state["schema_version"] = SCHEMA_VERSION
        state["project_id"] = self.state.get("project_id") or self._read_project().get("project_id", "")
        state["updated_at"] = _now()
        payload = json.dumps(state, ensure_ascii=False, indent=2)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(self.state_path.name + ".tmp")
        try:
            with open(tmp, "wb") as handle:
                handle.write(payload.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.state_path)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        self._disk_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.state = state
        return self.state_path

    # ------------------------------------------------------------------
    # evidence

    def evidence_records(self) -> List[Dict[str, Any]]:
        return list(self.state.get("evidence", {}).values())

    def get_evidence(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        return self.state.get("evidence", {}).get(evidence_id)

    def add_evidence(self, *, evidence_type: str, published_run_id: str,
                     publication_manifest_hash: str, corpus_fingerprint: str,
                     parameters_hash: str, captured_snapshot: Dict[str, Any],
                     fingerprint_parts: List[Any], document_id: str = "",
                     target: str = "", locator: Optional[Dict[str, Any]] = None,
                     researcher_note: str = "") -> Dict[str, Any]:
        """Idempotent capture: same run+type+fingerprint returns the record."""
        if evidence_type not in EVIDENCE_TYPES:
            raise ValueError(f"Unknown evidence type: {evidence_type}")
        fingerprint = item_fingerprint(evidence_type, published_run_id, *fingerprint_parts)
        for record in self.state.get("evidence", {}).values():
            if record["item_fingerprint"] == fingerprint and \
                    record["evidence_type"] == evidence_type and \
                    record["published_run_id"] == published_run_id:
                return record
        evidence_id = "ev_" + uuid.uuid4().hex[:12]
        record = {
            "evidence_id": evidence_id,
            "evidence_type": evidence_type,
            "published_run_id": published_run_id,
            "publication_manifest_hash": publication_manifest_hash,
            "corpus_fingerprint": corpus_fingerprint,
            "parameters_hash": parameters_hash,
            "document_id": document_id,
            "target": target,
            "locator": locator or {},
            "item_fingerprint": fingerprint,
            "captured_snapshot": captured_snapshot,
            "researcher_note": researcher_note,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.state.setdefault("evidence", {})[evidence_id] = record
        return record

    def update_note(self, evidence_id: str, note: str) -> None:
        record = self.get_evidence(evidence_id)
        if record is None:
            raise KeyError(evidence_id)
        record["researcher_note"] = note
        record["updated_at"] = _now()

    def claim_refs(self, evidence_id: str) -> List[str]:
        return [claim_id for claim_id, claim in self.state.get("claims", {}).items()
                if evidence_id in claim.get("evidence_ids", [])]

    def delete_evidence(self, evidence_id: str, *, force: bool = False) -> None:
        refs = self.claim_refs(evidence_id)
        if refs and not force:
            raise EvidenceReferencedError(
                f"该证据仍被 {len(refs)} 个 Claim 引用;请先从 Claim 移除,或确认强制删除。")
        self.state.get("evidence", {}).pop(evidence_id, None)
        for claim in self.state.get("claims", {}).values():
            claim["evidence_ids"] = [e for e in claim.get("evidence_ids", []) if e != evidence_id]

    # ------------------------------------------------------------------
    # claims

    def claims(self) -> List[Dict[str, Any]]:
        order = [cid for cid in self.claims_order if cid in self.state.get("claims", {})]
        tail = [cid for cid in self.state.get("claims", {}) if cid not in order]
        return [self.state["claims"][cid] for cid in order + tail]

    def get_claim(self, claim_id: str) -> Optional[Dict[str, Any]]:
        return self.state.get("claims", {}).get(claim_id)

    def add_claim(self, title: str, claim_text: str = "", researcher_note: str = "") -> Dict[str, Any]:
        claim_id = "claim_" + uuid.uuid4().hex[:12]
        claim = {
            "claim_id": claim_id,
            "title": title.strip() or "Untitled claim",
            "claim_text": claim_text,
            "researcher_note": researcher_note,
            "evidence_ids": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.state.setdefault("claims", {})[claim_id] = claim
        self.claims_order.append(claim_id)
        self.state["claims_order"] = list(self.claims_order)
        return claim

    def update_claim(self, claim_id: str, *, title: Optional[str] = None,
                     claim_text: Optional[str] = None,
                     researcher_note: Optional[str] = None) -> None:
        claim = self.get_claim(claim_id)
        if claim is None:
            raise KeyError(claim_id)
        if title is not None:
            claim["title"] = title.strip() or claim["title"]
        if claim_text is not None:
            claim["claim_text"] = claim_text
        if researcher_note is not None:
            claim["researcher_note"] = researcher_note
        claim["updated_at"] = _now()

    def delete_claim(self, claim_id: str) -> None:
        """Delete a claim and its links — never the evidence records."""
        self.state.get("claims", {}).pop(claim_id, None)
        self.claims_order = [cid for cid in self.claims_order if cid != claim_id]
        self.state["claims_order"] = list(self.claims_order)

    def reorder_claims(self, ordered_ids: List[str]) -> None:
        self.claims_order = list(ordered_ids)
        self.state["claims_order"] = list(ordered_ids)

    def claim_add_evidence(self, claim_id: str, evidence_id: str) -> None:
        claim = self.get_claim(claim_id)
        record = self.get_evidence(evidence_id)
        if claim is None or record is None:
            raise KeyError(claim_id if claim is None else evidence_id)
        if evidence_id not in claim.setdefault("evidence_ids", []):
            claim["evidence_ids"].append(evidence_id)
            claim["updated_at"] = _now()

    def claim_remove_evidence(self, claim_id: str, evidence_id: str) -> None:
        claim = self.get_claim(claim_id)
        if claim is None:
            raise KeyError(claim_id)
        claim["evidence_ids"] = [e for e in claim.get("evidence_ids", []) if e != evidence_id]
        claim["updated_at"] = _now()

    def evidence_claims_grouped(self) -> Dict[str, Dict[str, Any]]:
        return self.state.get("claims", {})
