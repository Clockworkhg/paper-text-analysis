# -*- coding: utf-8 -*-
"""Phase 2A.1 tests: review state integrity.

Covers: provenance metadata, per-item fingerprints (same id + changed
content must NOT restore), corpus/input change -> STALE, stale decisions
excluded from progress, decoupled reconciliation/reliability rows,
single-writer conflict refusal, Ctrl+Z undo consistency, and byte-level
immutability of corpus/analysis/review inputs.
"""

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from gui_next.data.review_store import (  # noqa: E402
    SCHEMA_VERSION,
    ReviewStateConflictError,
    SemanticReviewStore,
    SourceCountryReviewStore,
)
from gui_next.data.store import ProjectStore  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "01_corpus").mkdir(parents=True)
    (proj / "06_review").mkdir()

    corpus = proj / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\nchina poses a threat to stability.", encoding="utf-8"
    )
    pd.DataFrame({
        "document_id": ["doc_a"], "title": ["Story A"], "source_normalized": ["BBC"],
        "source_raw": ["BBC News"], "country": ["UK"], "date": [""],
        "word_count_approx": [120], "target_hits_total": [2], "relative_path": ["BBC/a.txt"],
    }).to_csv(proj / "01_corpus" / "documents.csv", index=False)
    (proj / "project.json").write_text(
        json.dumps({"project_id": "project_x", "name": "完整性", "targets": "China"}), encoding="utf-8")
    (proj / "run_config.json").write_text(json.dumps({"run_id": "run_r1"}), encoding="utf-8")

    from shared.research_output import write_excel_with_readme

    write_excel_with_readme(str(proj / "adjectives_phrases.xlsx"), {
        "KWIC": pd.DataFrame({"Target": ["China"], "Keyword": ["China"],
                              "Full_Context": ["china poses a threat"], "Document_ID": ["doc_a"]}),
    }, title="t", description="d")
    write_excel_with_readme(str(proj / "06_review" / "modifier_semantic_review.xlsx"), {
        "SemanticProsodyReview": pd.DataFrame({
            "review_id": ["semantic_0001", "semantic_0002"],
            "Corpus_ID": ["corpus_1", "corpus_1"],
            "Run_ID": ["run_r1", "run_r1"],
            "Document_IDs": ["doc_a", "doc_a"],
            "Target": ["China", "China"],
            "Kind": ["adjective", "adjective"],
            "Expression": ["strategic", "growing"],
            "Polarity_Candidate": ["negative_candidate", "positive_candidate"],
        }),
    }, title="t", description="d")
    return proj


def _hash_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_state(project_dir: Path, name: str) -> dict:
    return json.loads((project_dir / "06_review" / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Provenance metadata + per-item fingerprints
# ---------------------------------------------------------------------------


def test_state_file_records_provenance_metadata(project_dir: Path):
    store = SemanticReviewStore(project_dir)
    store.set_decision("semantic_0001", "negative")
    store.save()

    raw = _read_state(project_dir, "semantic_review_state.json")
    assert raw["schema_version"] == SCHEMA_VERSION
    assert raw["project_id"] == "project_x"
    assert raw["run_id"] == "run_r1"
    assert raw["corpus_fingerprint"]
    assert raw["input_fingerprint"]
    assert raw["input_provenance"]["input_file"] == "modifier_semantic_review.xlsx"
    assert raw["input_provenance"]["input_file_sha256"]
    assert raw["created_at"] and raw["updated_at"]
    assert raw["decisions"]["semantic_0001"]["item_fingerprint"]

    source_store = SourceCountryReviewStore(
        project_dir, documents_df=pd.read_csv(project_dir / "01_corpus" / "documents.csv"))
    source_store.set_decision("BBC", "accepted", country="UK")
    source_store.save()
    raw = _read_state(project_dir, "source_country_review_state.json")
    assert raw["input_fingerprint"] and raw["corpus_fingerprint"]
    assert raw["decisions"]["BBC"]["item_fingerprint"]


def test_same_review_id_changed_content_does_not_restore(project_dir: Path):
    store = SemanticReviewStore(project_dir)
    store.set_decision("semantic_0001", "negative")
    store.save()

    # Candidate set regenerated: same sequential ids, different content.
    path = project_dir / "06_review" / "modifier_semantic_review.xlsx"
    df = pd.read_excel(path, sheet_name="SemanticProsodyReview")
    df.loc[df["review_id"] == "semantic_0001", "Expression"] = "hostile"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="SemanticProsodyReview", index=False)

    reloaded = SemanticReviewStore(project_dir)
    assert reloaded.status() == "STALE"
    # The old decision must NOT silently apply to the changed candidate.
    assert "semantic_0001" in reloaded.stale_decision_ids
    assert "semantic_0001" not in reloaded.decisions
    assert reloaded.progress()["coded"] == 0
    # Unchanged sibling still restores (content fingerprint matches).
    assert "semantic_0002" not in reloaded.decisions  # never coded anyway
    store2 = SemanticReviewStore(project_dir)
    store2.set_decision("semantic_0002", "positive")
    store2.save()
    third = SemanticReviewStore(project_dir)
    assert third.decisions["semantic_0002"]["decision"] == "positive"


def test_legacy_schema_state_is_stale_and_not_applied(project_dir: Path):
    # Hand-craft a legacy (schema<2) state that only has sequential ids.
    legacy = {
        "review_type": "semantic",
        "schema": 1,
        "decisions": {"semantic_0001": {"decision": "positive", "note": "", "at": "2026-01-01"}},
    }
    (project_dir / "06_review" / "semantic_review_state.json").write_text(
        json.dumps(legacy), encoding="utf-8")

    store = SemanticReviewStore(project_dir)
    assert store.status() == "STALE"
    assert any("迁移" in reason for reason in store.stale_summary().split(";"))
    assert store.progress()["coded"] == 0  # legacy decisions never auto-apply
    # Preserved for future reconciliation/migration.
    assert "semantic_0001" in store.state["decisions"]


def test_corpus_change_makes_review_stale(project_dir: Path):
    store = SemanticReviewStore(project_dir)
    store.set_decision("semantic_0001", "negative")
    store.save()

    # Corpus re-import: file content changes -> corpus fingerprint changes.
    corpus_file = project_dir / "corpus" / "BBC" / "a.txt"
    corpus_file.write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\nchina poses a serious threat to stability.",
        encoding="utf-8",
    )

    reloaded = SemanticReviewStore(project_dir)
    assert "corpus_changed" in reloaded.stale_reasons
    assert reloaded.status() == "STALE"
    assert reloaded.progress()["coded"] == 0
    assert "semantic_0001" in reloaded.state["decisions"]  # preserved


def test_identical_regeneration_is_not_stale(project_dir: Path):
    store = SemanticReviewStore(project_dir)
    store.set_decision("semantic_0001", "negative")
    store.save()

    # Byte-level rewrite of the same logical candidate set.
    path = project_dir / "06_review" / "modifier_semantic_review.xlsx"
    df = pd.read_excel(path, sheet_name="SemanticProsodyReview")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="SemanticProsodyReview", index=False)

    reloaded = SemanticReviewStore(project_dir)
    assert reloaded.status() == "IN_PROGRESS"
    assert reloaded.decisions["semantic_0001"]["decision"] == "negative"


def test_status_vocabulary_not_started_in_progress_complete(project_dir: Path):
    store = SemanticReviewStore(project_dir)
    assert store.status() == "NOT_STARTED"
    store.set_decision("semantic_0001", "negative")
    assert store.status() == "IN_PROGRESS"
    store.set_decision("semantic_0002", "positive")
    assert store.status() == "COMPLETE"


def test_stale_decisions_excluded_from_progress_but_preserved(project_dir: Path):
    store = SemanticReviewStore(project_dir)
    store.set_decision("semantic_0001", "negative")
    store.save()

    path = project_dir / "06_review" / "modifier_semantic_review.xlsx"
    df = pd.read_excel(path, sheet_name="SemanticProsodyReview")
    df.loc[df["review_id"] == "semantic_0001", "Expression"] = "hostile"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="SemanticProsodyReview", index=False)

    reloaded = SemanticReviewStore(project_dir)
    progress = reloaded.progress()
    assert progress["status"] == "STALE"
    assert progress["coded"] == 0
    assert progress["stale_count"] == 1
    assert reloaded.state["decisions"]["semantic_0001"]["decision"] == "negative"  # preserved


# ---------------------------------------------------------------------------
# Reconciliation / reliability decoupling
# ---------------------------------------------------------------------------


def test_reconciliation_and_reliability_reported_independently(project_dir: Path):
    from gui_next.data.health import HealthState

    store = ProjectStore(project_dir)
    rows = {row["stage"]: row for row in store.pipeline_status(
        health=(HealthState.PASS, "ok"),
        source_progress={"total": 2, "decided": 0, "pending": 2, "status": "NOT_STARTED"},
        country_pending=0, country_total=0,
        semantic_progress={"total": 2, "coded": 1, "pending": 1, "status": "IN_PROGRESS"},
    )}
    # No FINAL/coder files -> honest "none", independent of reliability.
    assert "无双编码文件" in rows["编码者调和"]["detail"]
    # No IRR data -> only factual wording, never an inference about reconciliation.
    assert rows["编码者信度"]["detail"] in ("判定字段信度:尚无数据", "信度报告尚未生成")
    assert "未调和" not in rows["编码者信度"]["detail"]
    assert rows["语义韵复核"]["state"] == "1/2"


# ---------------------------------------------------------------------------
# Single-writer protection
# ---------------------------------------------------------------------------


def test_second_instance_conflict_is_refused_and_file_intact(project_dir: Path):
    first = SemanticReviewStore(project_dir)
    first.set_decision("semantic_0001", "negative")
    first.save()

    second = SemanticReviewStore(project_dir)  # reads the same state
    second.set_decision("semantic_0002", "positive")
    second.save()  # second instance now ahead on disk

    first.set_decision("semantic_0001", "excluded")  # stale view of disk
    with pytest.raises(ReviewStateConflictError):
        first.save()

    # The on-disk file still reflects the second instance's write, intact.
    on_disk = _read_state(project_dir, "semantic_review_state.json")
    assert on_disk["decisions"]["semantic_0002"]["decision"] == "positive"
    assert on_disk["decisions"]["semantic_0001"]["decision"] == "negative"

    # Reload resolves the conflict; the refused decision was NOT written.
    first.reload()
    assert first.decisions["semantic_0002"]["decision"] == "positive"
    assert first.decisions["semantic_0001"]["decision"] == "negative"


# ---------------------------------------------------------------------------
# Undo (Ctrl+Z)
# ---------------------------------------------------------------------------


def test_undo_restores_decision_progress_cursor_and_note(project_dir: Path, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    store = SemanticReviewStore(project_dir)
    from gui_next.inspector import InspectorPanel
    from gui_next.review_workbench import SemanticReviewWorkbench

    workbench = SemanticReviewWorkbench(store, InspectorPanel())
    workbench.show()
    QTest.qWait(10)

    QTest.keyClick(workbench, Qt.Key_2)          # 0001 negative, cursor -> 1
    assert store.decisions["semantic_0001"]["decision"] == "negative"
    assert store.cursor == 1
    assert len(store.state["history"]) == 1      # persisted op history

    QTest.keyClick(workbench, Qt.Key_Z, Qt.ControlModifier)
    assert "semantic_0001" not in store.decisions   # decision removed
    assert store.cursor == 0                        # cursor restored
    assert store.progress()["coded"] == 0           # progress consistent
    assert store.state["history"] == []             # undo consumed the op

    # Redo path: code again works normally.
    QTest.keyClick(workbench, Qt.Key_1)
    assert store.decisions["semantic_0001"]["decision"] == "positive"


def test_undo_persists_across_restart(project_dir: Path, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    store = SemanticReviewStore(project_dir)
    from gui_next.inspector import InspectorPanel
    from gui_next.review_workbench import SemanticReviewWorkbench

    workbench = SemanticReviewWorkbench(store, InspectorPanel())
    QTest.keyClick(workbench, Qt.Key_3)
    assert store.progress()["coded"] == 1

    reloaded = SemanticReviewStore(project_dir)
    assert reloaded.undo() == "semantic_0001"
    assert reloaded.progress()["coded"] == 0
    assert reloaded.cursor == 0


# ---------------------------------------------------------------------------
# Immutability of inputs
# ---------------------------------------------------------------------------


def test_inputs_byte_identical_across_all_review_state_operations(project_dir: Path):
    before = {
        "corpus": _hash_file(project_dir / "corpus" / "BBC" / "a.txt"),
        "analysis": _hash_file(project_dir / "adjectives_phrases.xlsx"),
        "review_wb": _hash_file(project_dir / "06_review" / "modifier_semantic_review.xlsx"),
        "run_config": _hash_file(project_dir / "run_config.json"),
        "registry": _hash_file(project_dir / "01_corpus" / "documents.csv"),
    }

    semantic = SemanticReviewStore(project_dir)
    semantic.set_decision("semantic_0001", "mixed", note="n1")
    semantic.save()
    semantic.undo()
    semantic.set_decision("semantic_0002", "uncertain")
    semantic.save()
    source = SourceCountryReviewStore(project_dir)
    source.set_decision("BBC", "changed", country="United Kingdom")
    source.save()

    assert _hash_file(project_dir / "corpus" / "BBC" / "a.txt") == before["corpus"]
    assert _hash_file(project_dir / "adjectives_phrases.xlsx") == before["analysis"]
    assert _hash_file(project_dir / "06_review" / "modifier_semantic_review.xlsx") == before["review_wb"]
    assert _hash_file(project_dir / "run_config.json") == before["run_config"]
    assert _hash_file(project_dir / "01_corpus" / "documents.csv") == before["registry"]
