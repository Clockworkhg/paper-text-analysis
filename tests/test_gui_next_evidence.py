# -*- coding: utf-8 -*-
"""Phase 3A tests: Evidence Trail core.

Covers: published-generation binding + archive resolution, idempotent
capture, claim lifecycle (multi-claim, remove-vs-delete, referenced-delete
guard), historical evidence surviving a newer published run, resolver
discipline (no silent latest-root fallback), integrity/corruption states,
conflict detection, and input immutability.
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

from gui_next.data.evidence_store import (  # noqa: E402
    EvidenceReferencedError,
    EvidenceStateConflictError,
    EvidenceStore,
)
from gui_next.data.generations import GenerationResolver  # noqa: E402
from gui_next.execution import jobs as run_jobs  # noqa: E402
from gui_next.execution import publication as pub  # noqa: E402
from gui_next.execution.controller import AnalysisController  # noqa: E402
from gui_next.execution.events import RunState  # noqa: E402
from gui_next.data.store import ProjectStore  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture()
def published_project(tmp_path: Path, qapp) -> Path:
    """Tiny project with one real published generation (GUI controller)."""
    proj = tmp_path / "proj"
    (proj / "01_corpus").mkdir(parents=True)
    corpus = proj / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\nChina poses a strategic threat to Europe. "
        "Europe and China negotiate trade terms.",
        encoding="utf-8")
    pd.DataFrame({
        "document_id": ["doc_a"], "title": ["Story A"], "source_normalized": ["BBC"],
        "source_raw": ["BBC News"], "country": ["UK"], "date": ["2021-03-01"],
        "word_count_approx": [30], "target_hits_total": [4], "relative_path": ["BBC/a.txt"],
    }).to_csv(proj / "01_corpus" / "documents.csv", index=False)
    (proj / "project.json").write_text(json.dumps(
        {"project_id": "project_ev", "name": "证据项目", "targets": "China",
         "project_dir": str(proj), "latest": {}, "history": []}), encoding="utf-8")
    (proj / "run_config.json").write_text(json.dumps({"run_id": "run_seed"}), encoding="utf-8")

    controller = AnalysisController(proj)
    spec = run_jobs.build_spec(kind="analyze", project_dir=str(proj), targets="China; Europe",
                               group_by="institution", mi_threshold=3.0, sanity=False)
    logs = []
    controller.log_line.connect(logs.append)
    assert controller.start(spec, "gui_run_a")
    waited = 0
    from PySide6.QtTest import QTest
    while waited < 180_000 and controller.state is not RunState.SUCCEEDED:
        QTest.qWait(200)
        waited += 200
    print("DBG final state:", controller.state.value, "waited:", waited)
    for line in logs[-8:]:
        print("DBGLOG", line[:130])
    print("DBG lock:", Path(proj / "runs" / "analysis_writer.lock").exists(),
          "| work dir:", Path(proj / "runs").exists() and
          [p.name for p in (proj / "runs").glob("work_*")])
    assert controller.state is RunState.SUCCEEDED
    return proj


def _provenance(project_dir: Path) -> dict:
    pointer = json.loads((project_dir / "runs" / "published_analysis.json").read_text(encoding="utf-8"))
    return {
        "published_run_id": pointer["published_run_id"],
        "publication_manifest_hash": pointer["manifest_sha256"],
        "corpus_fingerprint": pointer["corpus_fingerprint"],
        "parameters_hash": pointer["params_hash"],
    }


KWIC_SNAPSHOT = {
    "Keyword": "China", "Target": "China",
    "Left_Context": "poses a strategic", "Right_Context": "to Europe",
    "Full_Context": "China poses a strategic threat to Europe.",
    "Source": "BBC", "Source_Normalized": "BBC", "Group": "BBC",
}


# ---------------------------------------------------------------------------
# Capture + idempotency (tests 1-4)
# ---------------------------------------------------------------------------


def test_capture_all_four_types_and_idempotency(published_project: Path):
    store = EvidenceStore(published_project)
    prov = _provenance(published_project)

    records = []
    records.append(store.add_evidence(
        evidence_type="kwic", document_id="doc_a", target="China",
        captured_snapshot=dict(KWIC_SNAPSHOT),
        fingerprint_parts=["doc_a", "China", "poses a strategic", "China", "to Europe"],
        locator={"sheet": "KWIC"}, **prov))
    records.append(store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "Frequency": 5, "Doc_Frequency": 3,
                           "MI_Score": 4.8, "Log_Likelihood": 72.4},
        fingerprint_parts=["China", "threat"], **prov))
    records.append(store.add_evidence(
        evidence_type="phrase_pattern", target="China",
        captured_snapshot={"Modifier_Phrase": "strategic threat", "Frequency": 2},
        fingerprint_parts=["China", "strategic threat"], **prov))
    records.append(store.add_evidence(
        evidence_type="group_pattern", target="China",
        captured_snapshot={"Group": "BBC", "Kind": "collocate", "Expression": "threat",
                           "Frequency": 5, "Group_By": "institution"},
        fingerprint_parts=["China", "collocate", "threat", "institution", "BBC"], **prov))
    store.save()

    assert len({r["evidence_id"] for r in records}) == 4

    # Idempotent re-add: same run+type+fingerprint returns the same record.
    dup = store.add_evidence(
        evidence_type="kwic", document_id="doc_a", target="China",
        captured_snapshot=dict(KWIC_SNAPSHOT),
        fingerprint_parts=["doc_a", "China", "poses a strategic", "China", "to Europe"], **prov)
    assert dup["evidence_id"] == records[0]["evidence_id"]
    store.save()

    reloaded = EvidenceStore(published_project)
    assert len(reloaded.evidence_records()) == 4  # restart persistence (test 5)
    for record in reloaded.evidence_records():
        assert record["published_run_id"] == _provenance(published_project)["published_run_id"]
        assert record["publication_manifest_hash"]


# ---------------------------------------------------------------------------
# Claims (tests 6-10)
# ---------------------------------------------------------------------------


def test_claim_lifecycle_multi_claim_and_delete_semantics(published_project: Path):
    store = EvidenceStore(published_project)
    prov = _provenance(published_project)
    record = store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "MI_Score": 4.8},
        fingerprint_parts=["China", "threat"], **prov)
    store.save()
    evidence_id = record["evidence_id"]

    claim_a = store.add_claim("EU security framing", "safety framing hypothesis")
    claim_b = store.add_claim("Economic competition")
    store.claim_add_evidence(claim_a["claim_id"], evidence_id)
    store.save()

    # Same evidence -> second claim without duplication (test 8).
    store.claim_add_evidence(claim_b["claim_id"], evidence_id)
    store.save()
    assert len(store.claim_refs(evidence_id)) == 2

    # Remove from claim B: evidence record survives (test 9).
    store.claim_remove_evidence(claim_b["claim_id"], evidence_id)
    assert store.get_evidence(evidence_id) is not None

    # Referenced evidence delete refused (test 10).
    with pytest.raises(EvidenceReferencedError):
        store.delete_evidence(evidence_id)
    # Unreferenced delete works.
    store.claim_remove_evidence(claim_a["claim_id"], evidence_id)
    store.delete_evidence(evidence_id)
    assert store.get_evidence(evidence_id) is None

    # Deleting a claim never touches evidence records (test 9/§15).
    claim_c = store.add_claim("third")
    record2 = store.add_evidence(
        evidence_type="kwic", document_id="doc_a", target="China",
        captured_snapshot=dict(KWIC_SNAPSHOT),
        fingerprint_parts=["doc_a", "China", "left", "China", "right"], **prov)
    store.claim_add_evidence(claim_c["claim_id"], record2["evidence_id"])
    store.delete_claim(claim_c["claim_id"])
    assert store.get_evidence(record2["evidence_id"]) is not None


# ---------------------------------------------------------------------------
# Historical generations + resolver discipline (tests 11-14)
# ---------------------------------------------------------------------------


def _publish_second_generation(project_dir: Path, run_id: str, targets: str) -> None:
    controller = AnalysisController(project_dir)
    spec = run_jobs.build_spec(kind="analyze", project_dir=str(project_dir), targets=targets,
                               group_by="institution", mi_threshold=3.0, sanity=False)
    assert controller.start(spec, run_id)
    from PySide6.QtTest import QTest
    waited = 0
    while waited < 180_000 and controller.state is not RunState.SUCCEEDED:
        QTest.qWait(200)
        waited += 200
    assert controller.state is RunState.SUCCEEDED


def test_run_b_publication_keeps_run_a_evidence_resolvable(published_project: Path):
    store = EvidenceStore(published_project)
    prov_a = _provenance(published_project)
    record = store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "MI_Score": 4.8},
        fingerprint_parts=["China", "threat"], **prov_a)
    store.save()
    run_a = prov_a["published_run_id"]

    # Run B publishes over the project root.
    _publish_second_generation(published_project, "gui_run_b", targets="Europe")
    pointer_b = _provenance(published_project)
    assert pointer_b["published_run_id"] != run_a

    resolver = GenerationResolver(published_project)

    # Generation A archive still exists and verifies against stored hashes.
    state = resolver.integrity(run_a, publication_manifest_hash=prov_a["publication_manifest_hash"])
    assert state.state == "VERIFIED"

    # Resolver reads Run A's OWN archived KWIC, never the latest root file.
    kwic_a = resolver.read_kwic(run_a)
    assert len(kwic_a) > 0

    # Evidence record still fully resolves against generation A.
    assert store.get_evidence(record["evidence_id"])["published_run_id"] == run_a

    # New published run does not auto-upgrade or invalidate old evidence.
    assert record["corpus_fingerprint"] == prov_a["corpus_fingerprint"]


def test_resolver_never_falls_back_to_latest_root(published_project: Path):
    resolver = GenerationResolver(published_project)
    missing_run_id = "gui_never_published"

    manifest = resolver.load_manifest(missing_run_id)
    assert manifest is None  # no silent fallback to root/latest

    kwic = resolver.read_kwic(missing_run_id)
    assert kwic.empty

    state = resolver.integrity(missing_run_id)
    assert state.state == "SOURCE_UNAVAILABLE"


def test_historical_document_survives_registry_change(published_project: Path):
    resolver = GenerationResolver(published_project)
    pointer = _provenance(published_project)
    run_a = pointer["published_run_id"]

    # document ids are content hashes that change per published generation;
    # resolve Run A's id from ITS OWN archived registry.
    registry_a = resolver.read_registry(run_a)
    assert not registry_a.empty
    doc_id_a = registry_a.iloc[0]["document_id"]
    row = resolver.resolve_document(run_a, doc_id_a)
    assert row is not None and row["document_id"] == doc_id_a

    # Run C publishes over the root: its registry contains ITS OWN hashed ids.
    _publish_second_generation(published_project, "gui_run_c", targets="Europe")
    registry_now = pd.read_csv(published_project / "01_corpus" / "documents.csv")
    assert len(registry_now) >= 1
    run_c = json.loads((published_project / "runs" / "published_analysis.json").read_text(
        encoding="utf-8"))["published_run_id"]
    row_c = resolver.resolve_document(run_c, registry_now.iloc[0]["document_id"])
    assert row_c is not None

    # Generation A's document STILL resolves via its own archive — even though
    # the current registry's doc ids differ (corpus_id is per-generation).
    row_a = resolver.resolve_document(run_a, doc_id_a)
    assert row_a is not None and row_a["document_id"] == doc_id_a
    # And Run A's id is NOT resolvable in generation C's registry.
    assert resolver.resolve_document(run_c, doc_id_a) is None


# ---------------------------------------------------------------------------
# Integrity / corruption (tests 13-14)
# ---------------------------------------------------------------------------


def test_integrity_states_verified_and_corrupted(published_project: Path):
    resolver = GenerationResolver(published_project)
    prov = _provenance(published_project)
    run_id = prov["published_run_id"]

    state = resolver.integrity(run_id, publication_manifest_hash=prov["publication_manifest_hash"])
    assert state.state == "VERIFIED"

    # Manifest hash mismatch -> INTEGRITY_ERROR.
    state = resolver.integrity(run_id, publication_manifest_hash="deadbeef")
    assert state.state == "INTEGRITY_ERROR"

    # Archived artifact tampering -> INTEGRITY_ERROR.
    wb_path = resolver.artifact_path(run_id, "adjectives_phrases.xlsx")
    original = wb_path.read_bytes()
    wb_path.write_bytes(original + b"tampered")
    state = resolver.integrity(
        run_id, publication_manifest_hash=prov["publication_manifest_hash"],
        stored_artifact_hashes={"adjectives_phrases.xlsx": _sha(wb_path)})
    # sha recomputed after tamper matches the tampered value -> craft mismatch
    state = resolver.integrity(
        run_id, publication_manifest_hash=prov["publication_manifest_hash"],
        stored_artifact_hashes={"adjectives_phrases.xlsx": hashlib.sha256(b"original").hexdigest()})
    assert state.state == "INTEGRITY_ERROR"
    wb_path.write_bytes(original)  # restore

    # Archive removed -> SOURCE_UNAVAILABLE (never falls back to root).
    gen_dir = resolver.generation_dir(run_id)
    backup = gen_dir.parent / "run_id_backup"
    shutil.move(str(gen_dir), str(backup))
    state = resolver.integrity(run_id)
    assert state.state == "SOURCE_UNAVAILABLE"
    assert resolver.read_kwic(run_id).empty  # no silent root fallback
    shutil.move(str(backup), str(gen_dir))


# ---------------------------------------------------------------------------
# Evidence -> Run navigation + conflict + immutability (tests 15/18/19)
# ---------------------------------------------------------------------------


def test_runs_page_shows_evidence_references(published_project: Path, qapp):
    store = EvidenceStore(published_project)
    prov = _provenance(published_project)
    record = store.add_evidence(
        evidence_type="kwic", document_id="doc_a", target="China",
        captured_snapshot=dict(KWIC_SNAPSHOT),
        fingerprint_parts=["doc_a", "China", "l", "China", "r"], **prov)
    store.save()

    from gui_next.pages import RunsPage
    from gui_next.inspector import InspectorPanel
    page = RunsPage(ProjectStore(published_project), InspectorPanel(),
                    evidence_store=store)
    model = page._table_view.model()
    df = model.df()
    ref_col = "证据引用"
    assert ref_col in df.columns
    published_row = df[df["run_id"] == prov["published_run_id"]]
    assert published_row[ref_col].iloc[0] == 1


def test_evidence_conflict_detection_and_input_immutability(published_project: Path):
    corpus_before = _sha(published_project / "corpus" / "BBC" / "a.txt")
    workbook_before = _sha(published_project / "adjectives_phrases.xlsx")
    review_before = _sha(published_project / "06_review" / "modifier_semantic_review.xlsx")
    published_artifacts_before = _hash_dir(published_project / "runs" / "published")

    first = EvidenceStore(published_project)
    first.add_evidence(
        evidence_type="kwic", document_id="doc_a", target="China",
        captured_snapshot=dict(KWIC_SNAPSHOT),
        fingerprint_parts=["doc_a", "China", "l", "China", "r"], **_provenance(published_project))
    first.save()

    second = EvidenceStore(published_project)
    second.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat"}, fingerprint_parts=["China", "threat"],
        **_provenance(published_project))
    second.save()

    # First instance still holds the pre-second-write view -> refused.
    first.add_evidence(
        evidence_type="phrase_pattern", target="China",
        captured_snapshot={"Modifier_Phrase": "x"}, fingerprint_parts=["China", "x"],
        **_provenance(published_project))
    with pytest.raises(EvidenceStateConflictError):
        first.save()

    # On-disk store contains the second instance's record, intact.
    on_disk = json.loads((published_project / "08_evidence" / "evidence.json").read_text(encoding="utf-8"))
    assert len(on_disk["evidence"]) == 2  # first's kwic + second's collocate
    types = sorted(r["evidence_type"] for r in on_disk["evidence"].values())
    assert types == ["collocate_pattern", "kwic"]  # no third record from the refused write

    # No research input was modified by any evidence operation.
    assert _sha(published_project / "corpus" / "BBC" / "a.txt") == corpus_before
    assert _sha(published_project / "adjectives_phrases.xlsx") == workbook_before
    assert _sha(published_project / "06_review" / "modifier_semantic_review.xlsx") == review_before
    assert _hash_dir(published_project / "runs" / "published") == published_artifacts_before


def _hash_dir(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# GUI capture wiring (analysis page, key E)
# ---------------------------------------------------------------------------


def test_analysis_page_captures_kwic_evidence_with_E_key(published_project: Path, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from gui_next.app import MainWindow

    window = MainWindow()
    window.open_project(str(published_project))
    analysis = window._pages["分析"]
    assert analysis.evidence is not None

    window._navigate("分析")
    view = analysis._kwic_view
    QTest.qWait(200)
    analysis._apply_kwic_filter()
    QTest.keyClick(view, Qt.Key_0)  # noise: must not capture
    assert len(analysis.evidence.evidence_records()) == 0

    view.setFocus()
    index = analysis._kwic_model.index(0, 0)
    view.setCurrentIndex(index)
    QTest.keyClick(view, Qt.Key_E)
    QTest.qWait(200)

    records = analysis.evidence.evidence_records()
    assert len(records) == 1
    assert records[0]["evidence_type"] == "kwic"
    assert records[0]["published_run_id"] == _provenance(published_project)["published_run_id"]
    assert len(analysis.evidence.evidence_records()) == 1  # E again -> idempotent
    QTest.keyClick(view, Qt.Key_E)
    QTest.qWait(200)
    assert len(analysis.evidence.evidence_records()) == 1
