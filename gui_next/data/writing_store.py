# -*- coding: utf-8 -*-
"""Writing write boundary (Phase 3B): Research Draft document model.

Single write boundary for the Writing workspace, stored at
``09_writing/writing.json``. Carries the same research-grade guarantees as
the other stores: schema version, provenance metadata, atomic writes
(tmp + os.replace), optimistic single-writer conflict detection, and
preservation of the previous state on any failure.

Structure: one Writing Document -> ordered Sections (stable ids, optional
parent) -> ordered Blocks. Block types:

    PROSE          researcher-written text
    CLAIM_REF      reference to an EvidenceStore claim (never a copy)
    EVIDENCE_REF   reference to an EvidenceStore evidence record
    RESEARCH_NOTE  private process note (excluded from formal exports)

Blocks store REFERENCES only — metrics/context are always re-read from the
EvidenceStore and the published generation at render/export time, so stored
numbers can never decouple from their provenance.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WRITING_STATE_FILE = "writing.json"
SCHEMA_VERSION = 1

BLOCK_PROSE = "PROSE"
BLOCK_CLAIM_REF = "CLAIM_REF"
BLOCK_EVIDENCE_REF = "EVIDENCE_REF"
BLOCK_RESEARCH_NOTE = "RESEARCH_NOTE"
BLOCK_TYPES = (BLOCK_PROSE, BLOCK_CLAIM_REF, BLOCK_EVIDENCE_REF, BLOCK_RESEARCH_NOTE)

DEFAULT_SECTION_TITLES = ["Introduction", "Literature Review", "Methodology",
                          "Findings", "Discussion"]


class WritingStateConflictError(RuntimeError):
    """Another writer changed the writing document since it was loaded."""


class WritingSectionNotEmptyError(RuntimeError):
    """The section still contains blocks or child sections."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex[:12]


class WritingStore:
    def __init__(self, project_dir: str | Path):
        self.root = Path(project_dir)
        self.state_path = self.root / "09_writing" / "writing.json"
        self.state, self._disk_hash = self._load_state()

    # ------------------------------------------------------------------
    # persistence

    def _fresh_state(self) -> Dict[str, Any]:
        return {
            "store": "writing",
            "schema_version": SCHEMA_VERSION,
            "project_id": "",
            "document_id": "",
            "title": "Research Draft",
            "sections": {},
            "order": [],
            "created_at": _now(),
            "updated_at": _now(),
        }

    def _load_state(self) -> Tuple[Dict[str, Any], Optional[str]]:
        if not self.state_path.exists():
            return self._fresh_state(), None
        raw = self.state_path.read_bytes()
        try:
            state = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._fresh_state(), None
        if not isinstance(state, dict) or state.get("store") != "writing":
            return self._fresh_state(), None
        state.setdefault("sections", {})
        state.setdefault("order", [])
        project = self._read_project()
        state.setdefault("project_id", project.get("project_id", ""))
        return state, hashlib.sha256(raw).hexdigest()

    def _read_project(self) -> Dict[str, Any]:
        try:
            return json.loads((self.root / "project.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def reload(self) -> None:
        fresh = WritingStore(self.root)
        self.state, self._disk_hash = fresh.state, fresh._disk_hash

    def save(self) -> Path:
        current = None
        if self.state_path.exists():
            current = hashlib.sha256(self.state_path.read_bytes()).hexdigest()
        if current != self._disk_hash:
            raise WritingStateConflictError(
                "Writing document changed in another session. "
                "Reload to pick up the other session's changes (reload() ).")
        state = dict(self.state)
        state["schema_version"] = SCHEMA_VERSION
        state["project_id"] = state.get("project_id") or self._read_project().get("project_id", "")
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
    # document / sections

    @property
    def has_document(self) -> bool:
        return bool(self.state.get("document_id"))

    def new_document(self, title: str = "Research Draft",
                     skeleton: bool = True) -> Dict[str, Any]:
        """Create the writing document. A default thesis-style section
        skeleton is generated unless ``skeleton`` is False."""
        if self.has_document:
            raise WritingStateConflictError("Writing document already exists.")
        self.state["document_id"] = _new_id("wdoc")
        self.state["title"] = title or "Research Draft"
        self.state.setdefault("created_at", _now())
        previous = None
        for section_title in (DEFAULT_SECTION_TITLES if skeleton else []):
            previous = self.add_section(section_title, parent_id=None,
                                        after_id=None if previous is None else previous)
        self.state["updated_at"] = _now()
        self.save()
        return {"document_id": self.state["document_id"], "title": self.state["title"]}

    def document_info(self) -> Dict[str, Any]:
        return {
            "document_id": self.state.get("document_id", ""),
            "title": self.state.get("title", ""),
            "sections": len(self.state.get("sections", {})),
            "created_at": self.state.get("created_at", ""),
            "updated_at": self.state.get("updated_at", ""),
        }

    def set_title(self, title: str) -> None:
        self.state["title"] = title.strip() or self.state.get("title", "Research Draft")

    def sections(self) -> List[Dict[str, Any]]:
        """All sections ordered as a flat list (tree order, depth-first)."""
        roots = self._children(None)
        ordered: List[Dict[str, Any]] = []

        def walk(parent_id: Optional[str]) -> None:
            for section_id in self._child_ids(parent_id):
                section = self.state["sections"].get(section_id)
                if section is None:
                    continue
                ordered.append(section)
                walk(section_id)

        walk(None)
        return ordered

    def _children(self, parent_id: Optional[str]) -> List[Dict[str, Any]]:
        kids = [s for s in self.state.get("sections", {}).values()
                if s.get("parent_id") == parent_id]
        return sorted(kids, key=lambda s: s.get("order", 0))

    def _child_ids(self, parent_id: Optional[str]) -> List[str]:
        return [s["section_id"] for s in self._children(parent_id)]

    def get_section(self, section_id: str) -> Optional[Dict[str, Any]]:
        return self.state.get("sections", {}).get(section_id)

    def add_section(self, title: str, parent_id: Optional[str] = None,
                    after_id: Optional[str] = None) -> str:
        if parent_id is not None and parent_id not in self.state.get("sections", {}):
            raise KeyError(parent_id)
        section_id = _new_id("sec")
        siblings = self._child_ids(parent_id)
        if after_id is not None and after_id in self.state.get("sections", {}):
            order = self.state["sections"][after_id].get("order", 0) + 1
        else:
            order = len(siblings)
        # shift later siblings
        for sibling_id in siblings:
            sibling = self.state["sections"][sibling_id]
            if sibling.get("order", 0) >= order:
                sibling["order"] = sibling.get("order", 0) + 1
        self.state.setdefault("sections", {})[section_id] = {
            "section_id": section_id,
            "parent_id": parent_id,
            "title": title.strip() or "Untitled section",
            "order": order,
            "blocks": [],
        }
        if section_id not in self.state.setdefault("order", []):
            self.state["order"].append(section_id)
        self.state["updated_at"] = _now()
        return section_id

    def rename_section(self, section_id: str, title: str) -> None:
        section = self.get_section(section_id)
        if section is None:
            raise KeyError(section_id)
        section["title"] = title.strip() or section["title"]
        self.state["updated_at"] = _now()

    def delete_section(self, section_id: str, *, force: bool = False) -> int:
        """Delete a section (and any subtree). Refuses when the section or its
        subtree still contains blocks unless ``force`` is set. Returns the
        number of removed blocks."""
        section = self.get_section(section_id)
        if section is None:
            raise KeyError(section_id)
        to_remove: List[str] = [section_id]

        def collect(pid: str) -> None:
            for child in self._children(pid):
                to_remove.append(child["section_id"])
                collect(child["section_id"])

        collect(section_id)
        block_count = sum(len(self.state["sections"][sid].get("blocks", []))
                          for sid in to_remove if sid in self.state["sections"])
        if block_count and not force:
            raise WritingSectionNotEmptyError(
                f"Section still contains {block_count} block(s); confirm deletion.")
        # any child section with children? covered by collect; child sections
        # that themselves contain sub-sections are included via collect.
        for sid in to_remove:
            self.state.get("sections", {}).pop(sid, None)
            if sid in self.state.get("order", []):
                self.state["order"].remove(sid)
        self._renumber(section.get("parent_id"))
        self.state["updated_at"] = _now()
        return block_count

    def move_section(self, section_id: str, direction: int) -> None:
        section = self.get_section(section_id)
        if section is None:
            return
        siblings = self._child_ids(section.get("parent_id"))
        index = siblings.index(section_id)
        swap = index + direction
        if 0 <= swap < len(siblings):
            siblings[index], siblings[swap] = siblings[swap], siblings[index]
            for order, sid in enumerate(siblings):
                self.state["sections"][sid]["order"] = order
            self.state["updated_at"] = _now()

    def _renumber(self, parent_id: Optional[str]) -> None:
        for order, sid in enumerate(self._child_ids(parent_id)):
            self.state["sections"][sid]["order"] = order

    # ------------------------------------------------------------------
    # blocks

    def blocks(self, section_id: str) -> List[Dict[str, Any]]:
        section = self.get_section(section_id)
        return list(section.get("blocks", [])) if section else []

    def add_block(self, section_id: str, block_type: str, *,
                  text: str = "", claim_id: str = "", evidence_id: str = "",
                  after_block_id: Optional[str] = None) -> Dict[str, Any]:
        if block_type not in BLOCK_TYPES:
            raise ValueError(f"Unknown block type: {block_type}")
        section = self.get_section(section_id)
        if section is None:
            raise KeyError(section_id)
        if block_type == BLOCK_CLAIM_REF and not claim_id:
            raise ValueError("CLAIM_REF requires claim_id")
        if block_type == BLOCK_EVIDENCE_REF and not evidence_id:
            raise ValueError("EVIDENCE_REF requires evidence_id")
        block: Dict[str, Any] = {"block_id": _new_id("blk"), "type": block_type}
        if block_type in (BLOCK_PROSE, BLOCK_RESEARCH_NOTE):
            block["text"] = text
        if block_type == BLOCK_CLAIM_REF:
            block["claim_id"] = claim_id
        if block_type == BLOCK_EVIDENCE_REF:
            block["evidence_id"] = evidence_id
        blocks = section.setdefault("blocks", [])
        insert_at = len(blocks)
        if after_block_id:
            for i, existing in enumerate(blocks):
                if existing.get("block_id") == after_block_id:
                    insert_at = i + 1
                    break
        blocks.insert(insert_at, block)
        self.state["updated_at"] = _now()
        return block

    def update_block_text(self, section_id: str, block_id: str, text: str) -> None:
        section = self.get_section(section_id)
        if section is None:
            raise KeyError(section_id)
        for block in section.get("blocks", []):
            if block.get("block_id") == block_id:
                if block["type"] not in (BLOCK_PROSE, BLOCK_RESEARCH_NOTE):
                    raise ValueError("Only PROSE/RESEARCH_NOTE blocks hold text")
                block["text"] = text
                self.state["updated_at"] = _now()
                return
        raise KeyError(block_id)

    def remove_block(self, section_id: str, block_id: str) -> Dict[str, Any]:
        """Remove a block reference from the writing document.

        This only removes the WRITING reference — claims and evidence records
        themselves are managed (and deleted) in the Evidence store.
        """
        section = self.get_section(section_id)
        if section is None:
            raise KeyError(section_id)
        for i, block in enumerate(section.get("blocks", [])):
            if block.get("block_id") == block_id:
                removed = section["blocks"].pop(i)
                self.state["updated_at"] = _now()
                return removed
        raise KeyError(block_id)

    def move_block(self, section_id: str, block_id: str, direction: int) -> None:
        section = self.get_section(section_id)
        if section is None:
            return
        blocks = section.setdefault("blocks", [])
        for i, block in enumerate(blocks):
            if block.get("block_id") == block_id:
                swap = i + direction
                if 0 <= swap < len(blocks):
                    blocks[i], blocks[swap] = blocks[swap], blocks[i]
                    self.state["updated_at"] = _now()
                return
