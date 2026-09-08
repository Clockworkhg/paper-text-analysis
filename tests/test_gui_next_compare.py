# -*- coding: utf-8 -*-
"""Phase 3C tests: Run Compare + Evidence Refresh.

Covers compatibility gate, target/pattern/document comparison, evidence
counterpart search, lineage, replace-in-claim, and immutability guarantees.
"""

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from gui_next.data.evidence_store import EvidenceStore  # noqa: E402
from gui_next.data.generations import GenerationResolver  # noqa: E402
from gui_next.execution import jobs as run_jobs  # noqa: E402
from gui_next.execution.compare import (  # noqa: E402
    FULLY_COMPARABLE,
    NOT_COMPARABLE,
    PARTIALLY_COMPARABLE,
    build_document_mapping,
    compare_overview,
    compare_patterns,
    compare_targets,
    compute_compatibility,
    find_evidence_counterpart,
)
from gui_next.execution.controller import AnalysisController  # noqa: E402
from gui_next.execution.events import RunState  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def published_project(tmp_path: Path, qapp) -> Path:
    proj = tmp_path / "proj"
    (proj / "01_corpus").mkdir(parents=True)
    corpus = proj / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\nChina poses a strategic threat to Europe. "
        "China and Europe negotiate trade terms.", encoding="utf-8")
    pd.DataFrame({
        "document_id": ["doc_a"], "title": ["Story A"], "source_normalized": ["BBC"],
        "source_raw": ["BBC News"], "country": ["UK"], "date": ["2021-03-01"],
        "word_count_approx": [30], "target_hits_total": [4], "relative_path": ["BBC/a.txt"],
    }).to_csv(proj / "01_corpus" / "documents.csv", index=False)
    (proj / "project.json").write_text(json.dumps(
        {"project_id": "project_c", "name": "比较项目", "targets": "China; Europe",
         "project_dir": str(proj), "latest": {}, "history": []}), encoding="utf-8")
    (proj / "run_config.json").write_text(json.dumps({"run_id": "run_seed"}), encoding="utf-8")
    return proj


def _publish(project_dir: Path, run_id: str, targets: str,
             group_by: str = "institution", mi_threshold: float = 3.0):
    controller = AnalysisController(project_dir)
    spec = run_jobs.build_spec(kind="analyze", project_dir=str(project_dir),
                               targets=targets, group_by=group_by,
                               mi_threshold=mi_threshold, sanity=False)
    assert controller.start(spec, run_id)
    from PySide6.QtTest import QTest
    waited = 0
    while waited < 180_000 and controller.state is not RunState.SUCCEEDED:
        QTest.qWait(200)
        waited += 200
    assert controller.state is RunState.SUCCEEDED


# ---------------------------------------------------------------------------
# Compatibility gate (tests 2-4)
# ---------------------------------------------------------------------------


def test_fully_comparable_identical_configs():
    config = {"group_by": "institution", "mi_threshold": 3.0, "pos_translate": False}
    result = compute_compatibility(config, config, "fp1", "fp1", 100, 100,
                                   ["China"], ["China"], "1.0", "1.0", "1.0", "1.0")
    assert result["level"] == FULLY_COMPARABLE


def test_partially_comparable_corpus_changed():
    config = {"group_by": "institution", "mi_threshold": 3.0}
    result = compute_compatibility(config, config, "fp1", "fp2", 198, 194,
                                   ["China"], ["China"], "1.0", "1.0", "1.0", "1.0")
    assert result["level"] == PARTIALLY_COMPARABLE
    assert any(d["field"] == "corpus_fingerprint" for d in result["differences"])


def test_partially_comparable_target_changed():
    config = {"group_by": "institution", "mi_threshold": 3.0}
    result = compute_compatibility(config, config, "fp1", "fp1", 100, 100,
                                   ["China", "EU"], ["China"], "1.0", "1.0", "1.0", "1.0")
    assert result["level"] == PARTIALLY_COMPARABLE
    assert any(d["field"] == "targets" for d in result["differences"])


def test_not_comparable_no_shared_targets():
    config = {"group_by": "institution", "mi_threshold": 3.0}
    result = compute_compatibility(config, config, "fp1", "fp2", 100, 100,
                                   ["China"], ["Brexit"], "1.0", "2.0", "1.0", "2.0")
    assert result["level"] == NOT_COMPARABLE


def test_not_comparable_corpus_and_algorithm_both_changed():
    config = {"group_by": "institution", "mi_threshold": 3.0}
    result = compute_compatibility(config, config, "fp1", "fp2", 100, 100,
                                   ["China"], ["China"], "1.0", "2.0", "1.0", "2.0")
    assert result["level"] == NOT_COMPARABLE


# ---------------------------------------------------------------------------
# Target comparison (test 5)
# ---------------------------------------------------------------------------


def test_target_added_removed_changed(published_project: Path):
    _publish(published_project, "gui_a", "China; Europe")
    _publish(published_project, "gui_b", "China; Brexit")

    targets_a = ["China", "Europe"]
    targets_b = ["China", "Brexit"]
    results = compare_targets(published_project, "gui_a", "gui_b", targets_a, targets_b)
    by_target = {r["target"]: r for r in results}
    assert by_target["China"]["status"] in ("changed", "unchanged")
    assert by_target["Europe"]["status"] == "removed"
    assert by_target["Brexit"]["status"] == "added"


# ---------------------------------------------------------------------------
# Pattern comparison (tests 6-8)
# ---------------------------------------------------------------------------


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_collocate_pattern_diff(published_project: Path):
    _publish(published_project, "gui_a", "China")
    _publish(published_project, "gui_b", "China", mi_threshold=2.0)

    results = compare_patterns(published_project, "gui_a", "gui_b", "Collocates",
                               key_fields=["Target", "Collocate"],
                               metric_fields=["Frequency", "MI_Score", "Log_Likelihood"])
    assert isinstance(results, list)
    for entry in results:
        assert "Target" in entry and "Collocate" in entry
        assert "Frequency_a" in entry and "Frequency_b" in entry


def test_phrase_diff(published_project: Path):
    _publish(published_project, "gui_a", "China")
    _publish(published_project, "gui_b", "China")

    results = compare_patterns(published_project, "gui_a", "gui_b", "Phrases",
                               key_fields=["Target", "Modifier_Phrase"],
                               metric_fields=["Frequency"])
    assert isinstance(results, list)


def test_group_diff(published_project: Path):
    _publish(published_project, "gui_a", "China")
    _publish(published_project, "gui_b", "China")

    results = compare_patterns(published_project, "gui_a", "gui_b", "GroupComparison",
                               key_fields=["Source_Group", "Target", "Kind", "Expression"],
                               metric_fields=["Frequency"])
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Document mapping (tests 9-12)
# ---------------------------------------------------------------------------


def test_exact_id_mapping(published_project: Path):
    _publish(published_project, "gui_a", "China")
    _publish(published_project, "gui_b", "China")

    mapping = build_document_mapping(published_project, "gui_a", "gui_b")
    # document_ids are content hashes that change per generation (corpus_id
    # differs per work copy); EXACT_ID only fires when ids happen to match.
    levels = [m["level"] for m in mapping]
    assert "EXACT_ID" in levels or "CONTENT_MATCH" in levels


def test_content_match_mapping(published_project: Path):
    # Same content but different document_id (registry rebuilt).
    _publish(published_project, "gui_a", "China")
    _publish(published_project, "gui_b", "China")

    mapping = build_document_mapping(published_project, "gui_a", "gui_b")
    # If doc ids match across runs → EXACT_ID (highest confidence).
    # If they don't match but content does → CONTENT_MATCH.
    levels = [m["level"] for m in mapping]
    assert "EXACT_ID" in levels or "CONTENT_MATCH" in levels
    # METADATA_MATCH never used as exact
    for m in mapping:
        if m["level"] == "METADATA_MATCH":
            pytest.fail("METADATA_MATCH cannot masquerade as exact match")


def test_ambiguous_detection(published_project: Path):
    _publish(published_project, "gui_a", "China")
    _publish(published_project, "gui_b", "China")

    mapping = build_document_mapping(published_project, "gui_a", "gui_b")
    # AMBIGUOUS entries must not be auto-paired (no doc_id_b assigned)
    for m in mapping:
        if m["level"] == "AMBIGUOUS":
            assert "doc_id_b" not in m


# ---------------------------------------------------------------------------
# Evidence counterpart + lineage (tests 14-18)
# ---------------------------------------------------------------------------


def test_evidence_counterpart_search(published_project: Path):
    _publish(published_project, "gui_a", "China")
    store = EvidenceStore(published_project)
    pointer = _provenance(published_project)
    record = store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "MI_Score": 4.81},
        fingerprint_parts=["China", "threat"], **pointer)
    store.save()

    # Run B (same corpus, same targets → counterpart should exist)
    _publish(published_project, "gui_b", "China")
    result = find_evidence_counterpart(published_project, "gui_b", record)
    assert result["state"] in ("CANDIDATE_MATCH", "NO_MATCH")  # depends on analysis output


def test_candidate_does_not_auto_create_evidence(published_project: Path):
    _publish(published_project, "gui_a", "China")
    store = EvidenceStore(published_project)
    pointer = _provenance(published_project)
    record = store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat"},
        fingerprint_parts=["China", "threat"], **pointer)
    store.save()
    count_before = len(store.evidence_records())

    _publish(published_project, "gui_b", "China")
    result = find_evidence_counterpart(published_project, "gui_b", record)

    # Even if candidate found, no evidence record auto-created
    assert len(EvidenceStore(published_project).evidence_records()) == count_before


def test_add_new_counterpart_and_lineage(published_project: Path):
    _publish(published_project, "gui_a", "China")
    store = EvidenceStore(published_project)
    prov_a = _provenance(published_project)
    old_record = store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat"},
        fingerprint_parts=["China", "threat"], **prov_a)
    store.save()

    _publish(published_project, "gui_b", "China")
    pointer_b = _provenance(published_project)
    new_record = store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "MI_Score": 4.62},
        fingerprint_parts=["China", "threat"], **pointer_b)
    link = store.add_lineage_link(old_record["evidence_id"],
                                  new_record["evidence_id"],
                                  comparison_run_pair="gui_a__gui_b")
    store.save()

    assert link["relationship"] == "UPDATED_COUNTERPART"
    assert store.newer_counterpart(old_record["evidence_id"]) == new_record["evidence_id"]
    # Old evidence preserved
    assert store.get_evidence(old_record["evidence_id"]) is not None


def test_replace_in_claim_preserves_old_evidence(published_project: Path):
    _publish(published_project, "gui_a", "China")
    store = EvidenceStore(published_project)
    prov_a = _provenance(published_project)
    old_rec = store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat"},
        fingerprint_parts=["China", "threat"], **prov_a)
    claim = store.add_claim("framing")
    store.claim_add_evidence(claim["claim_id"], old_rec["evidence_id"])
    store.save()

    _publish(published_project, "gui_b", "China")
    pointer_b = _provenance(published_project)
    new_rec = store.add_evidence(
        evidence_type="collocate_pattern", target="China",
        captured_snapshot={"Collocate": "threat", "MI_Score": 4.62},
        fingerprint_parts=["China", "threat"], **pointer_b)
    store.add_lineage_link(old_rec["evidence_id"], new_rec["evidence_id"])
    store.replace_in_claim(claim["claim_id"], old_rec["evidence_id"],
                           new_rec["evidence_id"])
    store.save()

    # Claim now references new evidence only
    updated_claim = store.get_claim(claim["claim_id"])
    assert new_rec["evidence_id"] in updated_claim["evidence_ids"]
    assert old_rec["evidence_id"] not in updated_claim["evidence_ids"]
    # Old evidence record still exists (never deleted)
    assert store.get_evidence(old_rec["evidence_id"]) is not None


# ---------------------------------------------------------------------------
# Immutability (tests 19/22/25/26)
# ---------------------------------------------------------------------------


def test_compare_operations_leave_all_inputs_untouched(published_project: Path):
    _publish(published_project, "gui_a", "China")
    store = EvidenceStore(published_project)
    prov = _provenance(published_project)
    store.add_evidence(
        evidence_type="kwic", document_id="doc_a", target="China",
        captured_snapshot=dict(KWIC_SNAPSHOT),
        fingerprint_parts=["doc_a", "China", "l", "China", "r"], **prov)
    store.save()
    claim = store.add_claim("framing")
    record = store.evidence_records()[0]
    store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
    store.save()

    before = {
        "corpus": _sha(published_project / "corpus" / "BBC" / "a.txt"),
        "workbook": _sha(published_project / "adjectives_phrases.xlsx"),
        "review": _sha(published_project / "06_review" / "modifier_semantic_review.xlsx"),
        "evidence": _sha(published_project / "08_evidence" / "evidence.json"),
        "archive_wb": _sha(GenerationResolver(published_project).artifact_path(
            store.evidence_records()[0]["published_run_id"], "adjectives_phrases.xlsx")),
    }

    compare_overview(published_project,
                     store.evidence_records()[0]["published_run_id"],
                     store.evidence_records()[0]["published_run_id"])
    compare_targets(published_project,
                    store.evidence_records()[0]["published_run_id"],
                    store.evidence_records()[0]["published_run_id"],
                    ["China"], ["China"])
    build_document_mapping(published_project,
                           store.evidence_records()[0]["published_run_id"],
                           store.evidence_records()[0]["published_run_id"])

    assert _sha(published_project / "corpus" / "BBC" / "a.txt") == before["corpus"]
    assert _sha(published_project / "adjectives_phrases.xlsx") == before["workbook"]
    assert _sha(published_project / "06_review" / "modifier_semantic_review.xlsx") == before["review"]
    assert _sha(published_project / "08_evidence" / "evidence.json") == before["evidence"]
    assert _sha(GenerationResolver(published_project).artifact_path(
        store.evidence_records()[0]["published_run_id"], "adjectives_phrases.xlsx")) == before["archive_wb"]


def test_shared_tree_unchanged_by_compare(published_project: Path):
    import hashlib

    def shared_hash():
        digest = hashlib.sha256()
        repo = Path(__file__).resolve().parents[1]
        for path in sorted((repo / "shared").rglob("*.py")):
            digest.update(str(path).encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        return digest.hexdigest()

    before = shared_hash()
    _publish(published_project, "gui_c", "China")
    compare_overview(published_project, *_run_ids(published_project))
    assert shared_hash() == before


def _run_ids(project_dir: Path):
    runs = run_jobs.load_journal(project_dir)
    ids = [r["run_id"] for r in runs]
    return ids if len(ids) >= 2 else (ids + ids)


KWIC_SNAPSHOT = {
    "Keyword": "China", "Target": "China",
    "Left_Context": "poses a", "Right_Context": "threat to Europe",
    "Full_Context": "China poses a threat to Europe.",
    "Source": "BBC", "Source_Normalized": "BBC", "Group": "BBC",
}


def _provenance(project_dir: Path) -> dict:
    pointer = json.loads(
        (project_dir / "runs" / "published_analysis.json").read_text(encoding="utf-8"))
    return {
        "published_run_id": pointer["published_run_id"],
        "publication_manifest_hash": pointer["manifest_sha256"],
        "corpus_fingerprint": pointer["corpus_fingerprint"],
        "parameters_hash": pointer["params_hash"],
    }
