# -*- coding: utf-8 -*-
"""Writing integrity preflight + Markdown export (Phase 3B).

Read-only helpers: they re-read every Claim/Evidence record from the
EvidenceStore and verify each against its published generation via the
GenerationResolver. Writing blocks only hold references, so numbers shown
or exported can never decouple from their provenance.

Export modes:
- draft: full provenance, researcher notes included (marked private)
- clean: concise evidence representation with [EVD-NNNN] reference numbers
  and an Evidence Appendix; refuses to look normal when integrity issues
  exist (warning header is mandatory).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from gui_next.data.evidence_store import EvidenceStore, item_fingerprint
from gui_next.data.generations import GenerationResolver  # noqa: F401 (type refs)
from gui_next.data.writing_store import (
    BLOCK_CLAIM_REF,
    BLOCK_EVIDENCE_REF,
    BLOCK_RESEARCH_NOTE,
    WritingStore,
)

STATE_ORDER = ("VERIFIED", "SOURCE_UNAVAILABLE", "INTEGRITY_ERROR", "MISSING_REFERENCE")


def _fingerprint_from_snapshot(record: Dict[str, Any]) -> str:
    """Recompute an evidence record's item fingerprint from its snapshot.

    Must mirror add_evidence: the fingerprint is bound to
    evidence_type + published_run_id + the identity parts.
    """
    kind = record.get("evidence_type", "")
    snap = record.get("captured_snapshot", {}) or {}
    parts: List[Any]
    if kind == "kwic":
        parts = [snap.get("Document_ID", ""), snap.get("Target", ""),
                 snap.get("Left_Context", ""), snap.get("Keyword", ""),
                 snap.get("Right_Context", "")]
    elif kind == "collocate_pattern":
        parts = [record.get("target", ""), snap.get("Collocate", "")]
    elif kind == "phrase_pattern":
        parts = [record.get("target", ""), snap.get("Modifier_Phrase", "")]
    elif kind == "group_pattern":
        parts = [record.get("target", ""), snap.get("Kind", ""),
                 snap.get("Expression", ""), snap.get("Group_By", ""),
                 snap.get("Group", "")]
    else:
        parts = []
    return item_fingerprint(kind, record.get("published_run_id", ""), *parts)


def evidence_integrity(record: Dict[str, Any], resolver: GenerationResolver) -> tuple[str, str]:
    """Integrity of one evidence record against its published generation."""
    run_id = record.get("published_run_id", "")
    expected_manifest = record.get("publication_manifest_hash", "")
    expected_artifact = record.get("artifact_hashes") or None

    # Item-level: the captured snapshot must still fingerprint to the same id.
    expected_fp = record.get("item_fingerprint", "")
    if expected_fp and _fingerprint_from_snapshot(record) != expected_fp:
        return "INTEGRITY_ERROR", "captured snapshot fingerprint mismatch"

    archive_manifest = resolver.load_manifest(run_id)
    if archive_manifest is None:
        return "SOURCE_UNAVAILABLE", "已发布代际归档不存在"

    # Publication manifest hash must match the archived record.
    archived_hash = archive_manifest.get("publication_manifest_sha256", "")
    if expected_manifest and archived_hash != expected_manifest:
        return "INTEGRITY_ERROR", "publication manifest 哈希不匹配"

    # Every archived artifact must match its recorded hash.
    for artifact in archive_manifest.get("artifacts", []):
        path = resolver.artifact_path(run_id, artifact["relative_path"])
        if not path.exists():
            return "INTEGRITY_ERROR", f"归档产物缺失: {artifact['relative_path']}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != artifact["sha256"]:
            return "INTEGRITY_ERROR", f"归档产物哈希不匹配: {artifact['relative_path']}"

    if expected_artifact:
        for rel, expected in expected_artifact.items():
            path = resolver.artifact_path(run_id, rel)
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                return "INTEGRITY_ERROR", f"归档产物哈希不匹配: {rel}"

    # Item fingerprint re-derivation already passed; the generation archive
    # itself must still be present (it was checked via load_manifest above).
    return "VERIFIED", ""


def validate_writing(store: WritingStore, evidence_store: EvidenceStore,
                     resolver: GenerationResolver,
                     section_id: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate integrity preflight over the document or one section.

    CLAIM_REF blocks are checked for the claim's existence and then
    recursively for each referenced evidence record.
    """
    sections = ([store.get_section(section_id)] if section_id
                else store.sections())
    counts = {state: 0 for state in STATE_ORDER}
    items: List[Dict[str, Any]] = []
    seen_evidence: set = set()

    for section in [s for s in sections if s]:
        for block in section.get("blocks", []):
            if block.get("type") == BLOCK_CLAIM_REF:
                claim = evidence_store.get_claim(block.get("claim_id", ""))
                if claim is None:
                    counts["MISSING_REFERENCE"] += 1
                    items.append({"section_id": section["section_id"],
                                  "section_title": section["title"],
                                  "block_id": block["block_id"],
                                  "kind": "CLAIM_REF",
                                  "ref": block.get("claim_id", ""),
                                  "state": "MISSING_REFERENCE",
                                  "detail": "Claim 不存在于证据库"})
                    continue
                for evidence_id in claim.get("evidence_ids", []):
                    record = evidence_store.get_evidence(evidence_id)
                    if record is None:
                        counts["MISSING_REFERENCE"] += 1
                        items.append({"section_id": section["section_id"],
                                      "section_title": section["title"],
                                      "block_id": block["block_id"],
                                      "kind": "EVIDENCE_REF",
                                      "ref": evidence_id,
                                      "state": "MISSING_REFERENCE",
                                      "detail": "Claim 引用的证据不存在"})
                        continue
                    if evidence_id in seen_evidence:
                        continue
                    seen_evidence.add(evidence_id)
                    state, detail = evidence_integrity(record, resolver)
                    counts[state] += 1
                    items.append({"section_id": section["section_id"],
                                  "section_title": section["title"],
                                  "block_id": block["block_id"],
                                  "kind": "EVIDENCE_REF",
                                  "ref": evidence_id,
                                  "state": state,
                                  "detail": detail})
            elif block.get("type") == BLOCK_EVIDENCE_REF:
                record = evidence_store.get_evidence(block.get("evidence_id", ""))
                if record is None:
                    counts["MISSING_REFERENCE"] += 1
                    items.append({"section_id": section["section_id"],
                                  "section_title": section["title"],
                                  "block_id": block["block_id"],
                                  "kind": "EVIDENCE_REF",
                                  "ref": block.get("evidence_id", ""),
                                  "state": "MISSING_REFERENCE",
                                  "detail": "证据不存在于证据库"})
                    continue
                if block["evidence_id"] in seen_evidence:
                    continue
                seen_evidence.add(block["evidence_id"])
                state, detail = evidence_integrity(record, resolver)
                counts[state] += 1
                items.append({"section_id": section["section_id"],
                              "section_title": section["title"],
                              "block_id": block["block_id"],
                              "kind": "EVIDENCE_REF",
                              "ref": block["evidence_id"],
                              "state": state,
                              "detail": detail})

    verified = counts["VERIFIED"]
    problems = counts["SOURCE_UNAVAILABLE"] + counts["INTEGRITY_ERROR"] + counts["MISSING_REFERENCE"]
    return {
        "status": "VERIFIED" if problems == 0 and verified > 0 else
                  ("NOT_STARTED" if verified == 0 and problems == 0 else "ISSUES"),
        "verified": verified,
        "source_unavailable": counts["SOURCE_UNAVAILABLE"],
        "integrity_error": counts["INTEGRITY_ERROR"],
        "missing_reference": counts["MISSING_REFERENCE"],
        "items": items,
    }


def section_summary(store: WritingStore, evidence_store: EvidenceStore,
                    resolver: GenerationResolver, section_id: str) -> Dict[str, Any]:
    """Light navigation summary for one section (claims/evidence/runs)."""
    section = store.get_section(section_id)
    if section is None:
        return {"claims": 0, "evidence": 0, "runs": [], "integrity": "NOT_STARTED"}
    claim_ids: List[str] = []
    evidence_ids: List[str] = []
    for block in section.get("blocks", []):
        if block.get("type") == BLOCK_CLAIM_REF:
            if block.get("claim_id") and block["claim_id"] not in claim_ids:
                claim_ids.append(block["claim_id"])
        elif block.get("type") == BLOCK_EVIDENCE_REF:
            if block.get("evidence_id") and block["evidence_id"] not in evidence_ids:
                evidence_ids.append(block["evidence_id"])
    for claim_id in claim_ids:
        claim = evidence_store.get_claim(claim_id) or {}
        for evidence_id in claim.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
    runs: List[str] = []
    for evidence_id in evidence_ids:
        record = evidence_store.get_evidence(evidence_id) or {}
        run_id = record.get("published_run_id", "")
        if run_id and run_id not in runs:
            runs.append(run_id)
    validation = validate_writing(store, evidence_store, resolver, section_id=section_id)
    return {
        "claims": len(claim_ids),
        "evidence": len(evidence_ids),
        "runs": [f"#{r[-8:]}" for r in runs],
        "integrity": validation["status"],
    }


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def _evidence_card_lines(record: Dict[str, Any], evd_number: int,
                         integrity: str, resolver: GenerationResolver,
                         mode: str) -> List[str]:
    snap = record.get("captured_snapshot", {}) or {}
    evd_tag = f"[EVD-{evd_number:04d}]"
    lines: List[str] = []
    kind = record.get("evidence_type", "")
    if kind == "kwic":
        node = str(snap.get("Keyword", ""))
        left = str(snap.get("Left_Context", ""))
        right = str(snap.get("Right_Context", ""))
        lines.append(f"- {evd_tag} **KWIC** — {left} **[{node}]** {right}")
        if mode == "draft":
            lines.append(f"  - Source: {snap.get('Source', '')} | "
                         f"Normalized: {snap.get('Source_Normalized', '')} | "
                         f"Group: {snap.get('Group', '')}")
        lines.append(f"  - Document: `{record.get('document_id', '')}` · "
                     f"Run: `{record.get('published_run_id', '')}` · Integrity: {integrity}")
    elif kind == "collocate_pattern":
        lines.append(f"- {evd_tag} **COLLOCATE PATTERN** — "
                     f"{record.get('target', '')} × {snap.get('Collocate', '')}")
        lines.append(f"  - Frequency: {snap.get('Frequency', '–')} · "
                     f"Doc freq: {snap.get('Doc_Frequency', '–')} · "
                     f"MI: {snap.get('MI_Score', '–')} · G²: {snap.get('Log_Likelihood', '–')}")
        lines.append(f"  - Run: `{record.get('published_run_id', '')}` · Integrity: {integrity}")
    elif kind == "phrase_pattern":
        lines.append(f"- {evd_tag} **PHRASE PATTERN** — "
                     f"{record.get('target', '')} + “{snap.get('Modifier_Phrase', '')}”")
        lines.append(f"  - Frequency: {snap.get('Frequency', '–')} · "
                     f"Doc freq: {snap.get('Doc_Frequency', '–')}")
        lines.append(f"  - Run: `{record.get('published_run_id', '')}` · Integrity: {integrity}")
    elif kind == "group_pattern":
        lines.append(f"- {evd_tag} **GROUP PATTERN** — {snap.get('Group', '')}: "
                     f"{snap.get('Kind', '')} {snap.get('Expression', '')} "
                     f"(freq {snap.get('Frequency', '–')})")
        lines.append(f"  - Run: `{record.get('published_run_id', '')}` · Integrity: {integrity}")
    return lines


def export_markdown(store: WritingStore, evidence_store: EvidenceStore,
                    resolver: GenerationResolver, project_dir: str | Path,
                    *, mode: str = "draft", include_notes: Optional[bool] = None,
                    section_id: Optional[str] = None,
                    out_path: Optional[Path] = None) -> Dict[str, Any]:
    """Export the writing document (or one section) to Markdown.

    Draft mode: full provenance, private notes included by default.
    Clean mode: concise evidence lines with [EVD-NNNN] reference numbers and
    an Evidence Appendix; integrity problems force a prominent warning.
    """
    preflight = validate_writing(store, evidence_store, resolver, section_id=section_id)
    issues = preflight["source_unavailable"] + preflight["integrity_error"] + preflight["missing_reference"]
    if include_notes is None:
        include_notes = mode == "draft"

    sections = ([store.get_section(section_id)] if section_id else store.sections())
    title = store.state.get("title", "Research Draft")
    if section_id:
        title = (store.get_section(section_id) or {}).get("title", title)

    lines: List[str] = []
    if issues:
        lines += ["WARNING: Evidence integrity issues are present.",
                  f"({preflight['source_unavailable']} source unavailable, "
                  f"{preflight['integrity_error']} integrity error, "
                  f"{preflight['missing_reference']} missing reference)", ""]
    lines.append(f"# {title}")
    lines.append("")

    # Evidence numbering follows first appearance.
    evd_order: List[str] = []

    def evd_number(evidence_id: str) -> int:
        if evidence_id not in evd_order:
            evd_order.append(evidence_id)
        return evd_order.index(evidence_id) + 1

    def numbering_map() -> Dict[str, str]:
        numbers: Dict[str, str] = {}
        counter = 0

        def walk(parent_id: Optional[str]) -> None:
            nonlocal counter
            kids = store._children(parent_id)
            for i, section in enumerate(kids, start=1):
                counter += 1
                numbers[section["section_id"]] = str(i) if parent_id is None else \
                    numbers.get(section.get("parent_id", ""), "") + f".{i}"
                walk(section["section_id"])

        walk(None)
        return numbers

    numbers = numbering_map()
    section_list = sections if sections else []

    def section_heading(section: Dict[str, Any]) -> str:
        depth = 0
        pid = section.get("parent_id")
        while pid:
            depth += 1
            pid = (store.get_section(pid) or {}).get("parent_id")
        number = numbers.get(section["section_id"], "")
        prefix = "#" * min(depth + 2, 6)
        return f"{prefix} {number} {section['title']}".strip()

    def render_claim(claim_id: str) -> List[str]:
        claim = evidence_store.get_claim(claim_id)
        if claim is None:
            return [f"> ⚠ MISSING REFERENCE: claim `{claim_id}` 不存在。", ""]
        runs = sorted({(evidence_store.get_evidence(eid) or {}).get("published_run_id", "")
                       for eid in claim.get("evidence_ids", [])})
        out = [f"> **CLAIM**: “{claim.get('title', '')}”", ">",
               f"> {claim.get('claim_text', '')}", ">",
               f"> Evidence: {len(claim.get('evidence_ids', []))} items · "
               f"Runs: {', '.join('#' + r[-8:] for r in runs) or '–'} · "
               f"Integrity: {integrity_for_claim(claim_id)}", ""]
        return out

    evidence_in_claims: Dict[str, str] = {}

    def integrity_for_claim(claim_id: str) -> str:
        claim = evidence_store.get_claim(claim_id) or {}
        states = []
        for evidence_id in claim.get("evidence_ids", []):
            record = evidence_store.get_evidence(evidence_id)
            if record is None:
                states.append("MISSING_REFERENCE")
                continue
            state, _ = evidence_integrity(record, resolver)
            states.append(state)
        if "INTEGRITY_ERROR" in states:
            return "INTEGRITY_ERROR"
        if "SOURCE_UNAVAILABLE" in states or "MISSING_REFERENCE" in states:
            return "ISSUES"
        return "VERIFIED" if states else "NOT_STARTED"

    def render_evidence(evidence_id: str) -> List[str]:
        record = evidence_store.get_evidence(evidence_id)
        if record is None:
            return [f"> ⚠ MISSING REFERENCE: evidence `{evidence_id}` 不存在。", ""]
        state, detail = evidence_integrity(record, resolver)
        number = evd_number(evidence_id)
        evidence_in_claims[evidence_id] = str(number)
        return _evidence_card_lines(record, number,
                                    state if state != "VERIFIED" else
                                    f"✓ Verified{' (older published run)' if is_older(record) else ''}",
                                    resolver, mode) + [""]

    def is_older(record: Dict[str, Any]) -> bool:
        current = read_current_published(project_dir)
        return bool(current) and record.get("published_run_id", "") != current

    current = read_current_published(project_dir)

    for section in section_list:
        lines.append(section_heading(section))
        lines.append("")
        for block in section.get("blocks", []):
            btype = block.get("type")
            if btype == "PROSE":
                lines.append(block.get("text", ""))
                lines.append("")
            elif btype == "RESEARCH_NOTE":
                if include_notes:
                    lines.append(f"> **[Private research note]** {block.get('text', '')}")
                    lines.append("")
            elif btype == "CLAIM_REF":
                lines += render_claim(block.get("claim_id", ""))
            elif btype == BLOCK_EVIDENCE_REF:
                lines += render_evidence(block.get("evidence_id", ""))

    # Evidence appendix (clean mode mandatory; draft keeps it too for audit).
    lines.append("## Evidence Appendix")
    lines.append("")
    for evidence_id in evd_order:
        record = evidence_store.get_evidence(evidence_id)
        if record is None:
            continue
        state, detail = evidence_integrity(record, resolver)
        snap = record.get("captured_snapshot", {}) or {}
        number = evd_number(evidence_id)
        lines.append(f"### [EVD-{number:04d}] {record.get('evidence_type', '')} — "
                     f"{record.get('target', '')}")
        lines.append(f"- Evidence ID: `{record.get('evidence_id', '')}`")
        lines.append(f"- Document ID: `{record.get('document_id', '')}`")
        lines.append(f"- Source: {snap.get('Source', '')} / {snap.get('Source_Normalized', '')}")
        lines.append(f"- Published Run: `{record.get('published_run_id', '')}`")
        lines.append(f"- Manifest hash: `{record.get('publication_manifest_hash', '')}`")
        lines.append(f"- Corpus fingerprint: `{record.get('corpus_fingerprint', '')}`")
        lines.append(f"- Integrity: {state} {detail}".rstrip())
        if record.get("evidence_type") == "collocate_pattern":
            lines.append(f"- Metrics: Freq {snap.get('Frequency', '–')} · "
                         f"Doc freq {snap.get('Doc_Frequency', '–')} · "
                         f"MI {snap.get('MI_Score', '–')} · G² {snap.get('Log_Likelihood', '–')}")
        if record.get("evidence_type") == "kwic":
            lines.append(f"- Context: {snap.get('Full_Context', '')}")
        lines.append("")

    content = "\n".join(lines)

    written_path = Path(out_path) if out_path else \
        Path(project_dir) / "09_writing" / f"draft_{mode}.md"
    written_path.parent.mkdir(parents=True, exist_ok=True)
    written_path.write_text(content, encoding="utf-8")
    return {
        "path": str(written_path),
        "mode": mode,
        "preflight": preflight,
        "evidence_appendix": len(evd_order),
        "warnings": (["Evidence integrity issues are present."] if issues else []),
    }


def read_current_published(project_dir: str | Path) -> str:
    from gui_next.execution.publication import read_published_pointer
    return read_published_pointer(project_dir).get("published_run_id", "")
