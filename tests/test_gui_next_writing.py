# -*- coding: utf-8 -*-
"""Phase 3B tests: Evidence-aware Writing Workspace.

Covers the WritingStore document/section/block model, reference semantics
(claims/evidence are never copied or deleted through writing), integrity
preflight, Draft/Clean Markdown export with Evidence Appendix, atomic-write
safety, conflict detection, and input immutability.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from gui_next.data.evidence_store import EvidenceStore  # noqa: E402
from gui_next.data.generations import GenerationResolver  # noqa: E402
from gui_next.data.writing_export import export_markdown, validate_writing  # noqa: E402
from gui_next.data.writing_store import (  # noqa: E402
    BLOCK_CLAIM_REF,
    BLOCK_EVIDENCE_REF,
    BLOCK_PROSE,
    BLOCK_RESEARCH_NOTE,
    WritingSectionNotEmptyError,
    WritingStateConflictError,
    WritingStore,
)
from gui_next.execution import jobs as run_jobs  # noqa: E402
from gui_next.execution.controller import AnalysisController  # noqa: E402
from gui_next.execution.events import RunState  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            digest.update(str(path).encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _provenance(project_dir: Path) -> dict:
    pointer = json.loads(
        (project_dir / "runs" / "published_analysis.json").read_text(encoding="utf-8"))
    return {
        "published_run_id": pointer["published_run_id"],
        "publication_manifest_hash": pointer["manifest_sha256"],
        "corpus_fingerprint": pointer["corpus_fingerprint"],
        "parameters_hash": pointer["params_hash"],
    }


@pytest.fixture()
def published_project(tmp_path: Path, qapp) -> Path:
    """Tiny project with one real published generation."""
    proj = tmp_path / "proj"
    (proj / "01_corpus").mkdir(parents=True)
    (proj / "06_review").mkdir()
    corpus = proj / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\nChina poses a serious strategic threat to Europe. "
        "China and Europe negotiate trade terms.", encoding="utf-8")
    pd.DataFrame({
        "document_id": ["doc_a"], "title": ["Story A"], "source_normalized": ["BBC"],
        "source_raw": ["BBC News"], "country": ["UK"], "date": ["2021-03-01"],
        "word_count_approx": [30], "target_hits_total": [4], "relative_path": ["BBC/a.txt"],
    }).to_csv(proj / "01_corpus" / "documents.csv", index=False)
    (proj / "project.json").write_text(json.dumps(
        {"project_id": "project_w", "name": "写作项目", "targets": "China",
         "project_dir": str(proj), "latest": {}, "history": []}), encoding="utf-8")
    (proj / "run_config.json").write_text(json.dumps({"run_id": "run_seed"}), encoding="utf-8")

    controller = AnalysisController(proj)
    spec = run_jobs.build_spec(kind="analyze", project_dir=str(proj), targets="China",
                               group_by="institution", mi_threshold=3.0, sanity=False)
    assert controller.start(spec, "gui_run_a")
    from PySide6.QtTest import QTest
    waited = 0
    while waited < 180_000 and controller.state is not RunState.SUCCEEDED:
        QTest.qWait(200)
        waited += 200
    assert controller.state is RunState.SUCCEEDED
    return proj


@pytest.fixture()
def populated_project(published_project: Path) -> Path:
    """Published project with a claim + evidence bound to Run A."""
    from shared.research_output import write_excel_with_readme

    workbook = published_project / "adjectives_phrases.xlsx"
    kwic = pd.read_excel(workbook, sheet_name="KWIC")
    row = kwic.iloc[0]
    store = EvidenceStore(published_project)
    prov = _provenance(published_project)
    store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "Frequency": 10, "Doc_Frequency": 5,
                           "MI_Score": 4.81, "Log_Likelihood": 72.4},
        fingerprint_parts=["China", "threat"], **prov)
    store.add_evidence(
        evidence_type="kwic", target=str(row["Target"]),
        captured_snapshot={k: ("" if pd.isna(v) else v) for k, v in row.items()
                           if k in ("Keyword", "Target", "Left_Context", "Right_Context",
                                    "Full_Context", "Source", "Source_Normalized", "Group")},
        fingerprint_parts=[row["Document_ID"], row["Target"], row["Left_Context"],
                           row["Keyword"], row["Right_Context"]],
        document_id=str(row["Document_ID"]), **prov)
    claim = store.add_claim("EU security framing", "safety framing of China in later samples")
    for record in store.evidence_records():
        store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
    store.save()
    return published_project


# ---------------------------------------------------------------------------
# Document + section model (tests 1-3)
# ---------------------------------------------------------------------------


def test_new_document_creates_skeleton(published_project: Path):
    store = WritingStore(published_project)
    result = store.new_document()

    assert result["document_id"].startswith("wdoc_")
    assert store.has_document
    titles = [s["title"] for s in store.sections()]
    assert titles == ["Introduction", "Literature Review", "Methodology",
                      "Findings", "Discussion"]
    info = store.document_info()
    assert info["created_at"] and info["updated_at"]
    store.save()

    # Second new_document refused (one draft per project, Phase 3B scope).
    with pytest.raises(WritingStateConflictError):
        store.new_document()


def test_section_crud_hierarchy_and_order(published_project: Path):
    store = WritingStore(published_project)
    store.new_document()

    findings = store.sections()[3]["section_id"]
    sub = store.add_section("Security framing", parent_id=findings)
    sub2 = store.add_section("Economic competition", parent_id=findings)
    store.rename_section(sub, "Security framing (2021+)")
    store.save()

    titles = [s["title"] for s in store.sections()]
    assert "Security framing (2021+)" in titles
    assert store.get_section(sub)["parent_id"] == findings

    # Subsection ordering within the parent.
    numbers = {s["section_id"]: s.get("order", 0) for s in store.sections()
               if s.get("parent_id") == findings}
    assert numbers[sub2] > numbers[sub]

    # Deleting a subsection with no blocks works.
    store.delete_section(sub2)

    # Deleting a section with blocks requires force.
    store.add_block(findings, "PROSE", text="content")
    with pytest.raises(WritingSectionNotEmptyError):
        store.delete_section(findings)
    removed = store.delete_section(findings, force=True)
    assert removed >= 1


# ---------------------------------------------------------------------------
# Blocks + references (tests 4-10)
# ---------------------------------------------------------------------------


def test_prose_persists_across_restart(published_project: Path):
    store = WritingStore(published_project)
    store.new_document()
    sid = store.sections()[3]["section_id"]
    block = store.add_block(sid, "PROSE", text="从搭配结果来看,安全相关表达在…")
    store.save()

    reloaded = WritingStore(published_project)
    blocks = reloaded.blocks(sid)
    assert blocks[0]["text"] == "从搭配结果来看,安全相关表达在…"
    assert blocks[0]["block_id"] == block["block_id"]


def test_claim_and_evidence_refs(published_project: Path):
    evidence_store = EvidenceStore(published_project)
    prov = _provenance(published_project)
    record = evidence_store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "MI_Score": 4.81},
        fingerprint_parts=["China", "threat"], **prov)
    claim = evidence_store.add_claim("EU security framing")
    evidence_store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
    evidence_store.save()

    store = WritingStore(published_project)
    store.new_document()
    sid = store.sections()[3]["section_id"]
    store.add_block(sid, "PROSE", text="从搭配结果来看…")
    store.add_block(sid, BLOCK_CLAIM_REF, claim_id=claim["claim_id"])
    store.add_block(sid, BLOCK_EVIDENCE_REF, evidence_id=record["evidence_id"])
    store.save()

    reloaded = WritingStore(published_project)
    blocks = reloaded.blocks(sid)
    assert [b["type"] for b in blocks] == ["PROSE", "CLAIM_REF", "EVIDENCE_REF"]
    # References, never copies: block holds ids only.
    assert "MI" not in json.dumps(blocks)
    assert blocks[1]["claim_id"] == claim["claim_id"]
    assert blocks[2]["evidence_id"] == record["evidence_id"]


def test_same_claim_and_evidence_in_multiple_sections(published_project: Path):
    evidence_store = EvidenceStore(published_project)
    prov = _provenance(published_project)
    record = evidence_store.add_evidence(
        evidence_type="kwic", document_id="doc_a", target="China",
        captured_snapshot=dict(KWIC_SNAPSHOT),
        fingerprint_parts=["doc_a", "China", "l", "China", "r"], **prov)
    claim = evidence_store.add_claim("framing")
    evidence_store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
    evidence_store.save()

    store = WritingStore(published_project)
    store.new_document()
    sections = store.sections()
    findings_id = sections[3]["section_id"]
    discussion_id = sections[4]["section_id"]
    store.add_block(findings_id, BLOCK_CLAIM_REF, claim_id=claim["claim_id"])
    store.add_block(findings_id, BLOCK_EVIDENCE_REF, evidence_id=record["evidence_id"])
    store.add_block(discussion_id, BLOCK_CLAIM_REF, claim_id=claim["claim_id"])
    store.add_block(discussion_id, BLOCK_EVIDENCE_REF, evidence_id=record["evidence_id"])
    store.save()

    # Same record referenced twice — evidence count in store unchanged.
    assert len(evidence_store.evidence_records()) == 1


def test_removing_block_never_deletes_claim_or_evidence(published_project: Path):
    evidence_store = EvidenceStore(published_project)
    prov = _provenance(published_project)
    record = evidence_store.add_evidence(
        evidence_type="kwic", document_id="doc_a", target="China",
        captured_snapshot=dict(KWIC_SNAPSHOT),
        fingerprint_parts=["doc_a", "China", "l", "China", "r"], **prov)
    claim = evidence_store.add_claim("framing")
    evidence_store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
    evidence_store.save()

    store = WritingStore(published_project)
    store.new_document()
    sid = store.sections()[0]["section_id"]
    block = store.add_block(sid, BLOCK_CLAIM_REF, claim_id=claim["claim_id"])
    block2 = store.add_block(sid, BLOCK_EVIDENCE_REF, evidence_id=record["evidence_id"])
    store.save()

    store.remove_block(sid, block["block_id"])
    store.remove_block(sid, block2["block_id"])
    store.save()

    # Claim and evidence record remain fully intact in the evidence store.
    assert evidence_store.get_claim(claim["claim_id"]) is not None
    assert evidence_store.get_evidence(record["evidence_id"]) is not None


def test_writing_renders_updated_claim_content(published_project: Path):
    """Blocks store references, so claim edits are reflected automatically."""
    evidence_store = EvidenceStore(published_project)
    prov = _provenance(published_project)
    record = evidence_store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "MI_Score": 4.81},
        fingerprint_parts=["China", "threat"], **prov)
    claim = evidence_store.add_claim("old title")
    evidence_store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
    evidence_store.save()

    store = WritingStore(published_project)
    store.new_document()
    sid = store.sections()[0]["section_id"]
    store.add_block(sid, BLOCK_CLAIM_REF, claim_id=claim["claim_id"])

    evidence_store.update_claim(claim["claim_id"], title="new title",
                                researcher_note="revised")
    evidence_store.save()

    claim_now = evidence_store.get_claim(claim["claim_id"])
    assert claim_now["title"] == "new title"  # writing re-reads, not copies


# ---------------------------------------------------------------------------
# Integrity preflight / freshness / broken evidence (tests 11-14)
# ---------------------------------------------------------------------------


def _preflight(published_project: Path, writing_store: WritingStore,
               evidence_store: EvidenceStore) -> dict:
    resolver = GenerationResolver(published_project)
    return validate_writing(writing_store, evidence_store, resolver)


KWIC_SNAPSHOT = {
    "Keyword": "China", "Target": "China",
    "Left_Context": "poses a", "Right_Context": "threat to Europe",
    "Full_Context": "China poses a threat to Europe.",
    "Source": "BBC", "Source_Normalized": "BBC", "Group": "BBC",
}


def _populate_writing_with_refs(published_project: Path):
    store = WritingStore(published_project)
    store.new_document()
    sid = store.sections()[0]["section_id"]
    evidence_store = EvidenceStore(published_project)
    prov = _provenance(published_project)

    record = evidence_store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "MI_Score": 4.81},
        fingerprint_parts=["China", "threat"], **prov)
    claim = evidence_store.add_claim("framing")
    evidence_store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
    evidence_store.save()

    store.add_block(sid, BLOCK_CLAIM_REF, claim_id=claim["claim_id"])
    store.add_block(sid, BLOCK_EVIDENCE_REF, evidence_id=record["evidence_id"])
    store.save()
    return store, evidence_store, sid, record, claim


def test_preflight_all_verified_on_valid_generation(published_project: Path):
    store, evidence_store, _sid, _record, _claim = _populate_writing_with_refs(
        published_project)
    report = _preflight(published_project, store, evidence_store)
    assert report["status"] == "VERIFIED"
    # Both blocks reference the SAME evidence record — deduplicated to 1.
    assert report["verified"] == 1
    assert report["missing_reference"] == 0


def test_missing_reference_detected(published_project: Path):
    store, evidence_store, _sid, _record, _claim = _populate_writing_with_refs(
        published_project)
    store.add_block(store.sections()[0]["section_id"], "CLAIM_REF",
                    claim_id="claim_deleted")
    store.add_block(store.sections()[0]["section_id"], "EVIDENCE_REF",
                    evidence_id="ev_deleted")

    report = _preflight(published_project, store, evidence_store)
    assert report["missing_reference"] == 2
    assert report["status"] == "ISSUES"


def test_older_published_run_is_verified_not_stale(published_project: Path):
    store, evidence_store, _sid, _record, _claim = _populate_writing_with_refs(
        published_project)
    run_a = _provenance(published_project)["published_run_id"]

    # Publish Run B on top.
    controller = AnalysisController(published_project)
    spec = run_jobs.build_spec(kind="analyze", project_dir=str(published_project),
                               targets="Europe", group_by="institution",
                               mi_threshold=3.0, sanity=False)
    assert controller.start(spec, "gui_run_b")
    from PySide6.QtTest import QTest
    waited = 0
    while waited < 180_000 and controller.state is not RunState.SUCCEEDED:
        QTest.qWait(200)
        waited += 200
    assert controller.state is RunState.SUCCEEDED

    # Old evidence still VERIFIED against its own generation.
    report = _preflight(published_project, store, evidence_store)
    assert report["verified"] >= 1
    assert report["integrity_error"] == 0
    assert report["source_unavailable"] == 0


def test_source_unavailable_and_integrity_error(published_project: Path):
    store, evidence_store, _sid, _record, _claim = _populate_writing_with_refs(
        published_project)
    resolver = GenerationResolver(published_project)
    run_id = _provenance(published_project)["published_run_id"]
    gen_dir = resolver.generation_dir(run_id)
    backup = gen_dir.parent / "gen_backup"

    # Archive missing -> SOURCE_UNAVAILABLE.
    shutil.move(str(gen_dir), str(backup))
    report = _preflight(published_project, store, evidence_store)
    assert any(i["state"] == "SOURCE_UNAVAILABLE" for i in report["items"])
    shutil.move(str(backup), str(gen_dir))

    # Artifact hash corruption -> INTEGRITY_ERROR.
    wb = resolver.artifact_path(run_id, "adjectives_phrases.xlsx")
    original = wb.read_bytes()
    wb.write_bytes(original + b"CORRUPTED")
    report = _preflight(published_project, store, evidence_store)
    assert report["integrity_error"] >= 1
    wb.write_bytes(original)
    report = _preflight(published_project, store, evidence_store)
    assert report["status"] == "VERIFIED"


# ---------------------------------------------------------------------------
# Markdown export (tests 16-19)
# ---------------------------------------------------------------------------


def test_draft_export_contains_prose_claim_notes_and_provenance(published_project: Path):
    store, evidence_store, _sid, _record, _claim = _populate_writing_with_refs(
        published_project)
    sid = store.sections()[3]["section_id"]
    store.add_block(sid, "PROSE", text="从搭配结果来看,安全相关表达在……")
    store.add_block(sid, "RESEARCH_NOTE", text="这里还要检查 2020 年前后差异。")
    store.save()

    result = export_markdown(store, evidence_store, GenerationResolver(published_project),
                             published_project, mode="draft")
    content = Path(result["path"]).read_text(encoding="utf-8")

    assert "从搭配结果来看,安全相关表达在……" in content
    assert "framing" in content  # claim title from the evidence store
    assert "[Private research note]" in content  # draft includes notes
    assert "MI: 4.81" in content
    assert "Manifest hash" in content
    assert content.startswith("# ")


def test_clean_export_uses_evd_numbers_and_excludes_notes(published_project: Path):
    store, evidence_store, _sid, _record, _claim = _populate_writing_with_refs(
        published_project)
    sid = store.sections()[3]["section_id"]
    store.add_block(sid, "RESEARCH_NOTE", text="private process note")
    store.save()

    result = export_markdown(store, evidence_store, GenerationResolver(published_project),
                             published_project, mode="clean", include_notes=False)
    content = Path(result["path"]).read_text(encoding="utf-8")

    assert "[EVD-0001]" in content
    assert "Evidence Appendix" in content
    assert "private process note" not in content  # notes excluded from clean
    assert "WARNING" not in content  # no integrity issues in this fixture


def test_evidence_appendix_contains_provenance(published_project: Path):
    store, evidence_store, _sid, _record, _claim = _populate_writing_with_refs(
        published_project)
    result = export_markdown(store, evidence_store, GenerationResolver(published_project),
                             published_project, mode="clean")
    content = Path(result["path"]).read_text(encoding="utf-8")
    prov = _provenance(published_project)

    assert "## Evidence Appendix" in content
    assert f"`{prov['published_run_id']}`" in content
    assert f"`{prov['publication_manifest_hash']}`" in content
    assert f"`{prov['corpus_fingerprint']}`" in content
    assert "MI" in content


def test_broken_evidence_export_carries_warning(published_project: Path):
    store, evidence_store, _sid, _record, _claim = _populate_writing_with_refs(
        published_project)
    resolver = GenerationResolver(published_project)
    run_id = _provenance(published_project)["published_run_id"]

    # Corrupt the archived workbook -> INTEGRITY_ERROR at preflight.
    wb = resolver.artifact_path(run_id, "adjectives_phrases.xlsx")
    original = wb.read_bytes()
    wb.write_bytes(original + b"CORRUPTED")

    result = export_markdown(store, evidence_store, resolver,
                             published_project, mode="clean")
    content = Path(result["path"]).read_text(encoding="utf-8")
    assert content.startswith("WARNING: Evidence integrity issues are present.")

    draft = export_markdown(store, evidence_store, resolver,
                            published_project, mode="draft")
    assert Path(draft["path"]).read_text(encoding="utf-8").startswith(
        "WARNING: Evidence integrity issues are present.")

    wb.write_bytes(original)  # restore


# ---------------------------------------------------------------------------
# Store safety (tests 20-22)
# ---------------------------------------------------------------------------


def test_atomic_write_failure_does_not_corrupt(published_project: Path, monkeypatch):
    store = WritingStore(published_project)
    store.new_document()
    sid = store.sections()[0]["section_id"]
    store.add_block(sid, "PROSE", text="keep me")
    store.save()
    good = _sha(store.state_path)

    import gui_next.data.writing_store as ws

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(ws.os, "replace", broken_replace)
    store.add_block(sid, "PROSE", text="more")
    with pytest.raises(OSError):
        store.save()

    assert _sha(store.state_path) == good  # previous version intact
    assert not store.state_path.with_name(store.state_path.name + ".tmp").exists()


def test_writing_conflict_detected_between_instances(published_project: Path):
    first = WritingStore(published_project)
    first.new_document()
    first.save()

    second = WritingStore(published_project)
    second.set_title("Session B title")
    second.save()

    first.set_title("Session A title")
    with pytest.raises(WritingStateConflictError):
        first.save()

    # On-disk document keeps Session B's write, intact.
    assert json.loads(first.state_path.read_text(encoding="utf-8"))["title"] == \
        "Session B title"

    first.reload()
    first.set_title("Session A title")
    first.save()
    assert json.loads(first.state_path.read_text(encoding="utf-8"))["title"] == \
        "Session A title"


def test_writing_ops_leave_research_inputs_untouched(published_project: Path):
    evidence_store = EvidenceStore(published_project)
    prov = _provenance(published_project)
    record = evidence_store.add_evidence(
        evidence_type="kwic", document_id="doc_a", target="China",
        captured_snapshot=dict(KWIC_SNAPSHOT),
        fingerprint_parts=["doc_a", "China", "l", "China", "r"], **prov)
    claim = evidence_store.add_claim("framing")
    evidence_store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
    evidence_store.save()

    before = {
        "corpus": _sha(published_project / "corpus" / "BBC" / "a.txt"),
        "workbook": _sha(published_project / "adjectives_phrases.xlsx"),
        "review": _sha(published_project / "06_review" / "modifier_semantic_review.xlsx"),
        "archive_wb": _sha(GenerationResolver(published_project).artifact_path(
            "gui_run_a", "adjectives_phrases.xlsx")),
        "evidence_json": _sha(published_project / "08_evidence" / "evidence.json"),
    }

    store = WritingStore(published_project)
    store.new_document()
    sid = store.sections()[3]["section_id"]
    store.add_block(sid, "PROSE", text="prose")
    store.add_block(sid, BLOCK_CLAIM_REF, claim_id=claim["claim_id"])
    store.add_block(sid, BLOCK_EVIDENCE_REF, evidence_id=record["evidence_id"])
    store.save()
    export_markdown(store, evidence_store, GenerationResolver(published_project),
                    published_project, mode="clean")

    assert _sha(published_project / "corpus" / "BBC" / "a.txt") == before["corpus"]
    assert _sha(published_project / "adjectives_phrases.xlsx") == before["workbook"]
    assert _sha(published_project / "06_review" / "modifier_semantic_review.xlsx") == before["review"]
    assert _sha(GenerationResolver(published_project).artifact_path(
        "gui_run_a", "adjectives_phrases.xlsx")) == before["archive_wb"]
    assert _sha(published_project / "08_evidence" / "evidence.json") == before["evidence_json"]


def test_shared_tree_unchanged_by_writing_operations(published_project: Path):
    import hashlib

    def shared_tree_hash():
        digest = hashlib.sha256()
        repo = Path(__file__).resolve().parents[1]
        for path in sorted((repo / "shared").rglob("*.py")):
            digest.update(str(path).encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        return digest.hexdigest()

    before = shared_tree_hash()

    store = WritingStore(published_project)
    store.new_document()
    sid = store.sections()[0]["section_id"]
    store.add_block(sid, "PROSE", text="prose")
    store.save()
    validate_writing(store, EvidenceStore(published_project),
                     GenerationResolver(published_project))

    assert shared_tree_hash() == before


KWIC_SNAPSHOT = {
    "Keyword": "China", "Target": "China",
    "Left_Context": "poses a", "Right_Context": "threat to Europe",
    "Full_Context": "China poses a threat to Europe.",
    "Source": "BBC", "Source_Normalized": "BBC", "Group": "BBC",
}
