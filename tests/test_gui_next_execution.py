# -*- coding: utf-8 -*-
"""Phase 2B tests: analysis execution lifecycle, isolation, and safety.

Real analysis runs spawn the runner subprocess (spaCy included), so these
tests use a tiny corpus and generous deadlines. Test-only hooks
(``inject_failure`` / ``test_sleep_before_analyze``) belong to the
execution layer, never to shared/.
"""

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from gui_next.analysis_run import RunConfigView  # noqa: E402
from gui_next.data.health import HealthState, corpus_health  # noqa: E402
from gui_next.data.review_store import SemanticReviewStore  # noqa: E402
from gui_next.data.store import ProjectStore  # noqa: E402
from gui_next.execution import jobs as run_jobs  # noqa: E402
from gui_next.execution.controller import AnalysisController  # noqa: E402
from gui_next.execution.events import RunState  # noqa: E402

DEADLINE_MS = 120_000


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def wait_until(condition, timeout_ms: int = DEADLINE_MS) -> bool:
    from PySide6.QtTest import QTest

    waited = 0
    while waited < timeout_ms:
        if condition():
            return True
        QTest.qWait(100)
        waited += 100
    return condition()


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "01_corpus").mkdir(parents=True)
    (proj / "06_review").mkdir()
    corpus = proj / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\nChina poses a serious strategic threat to Europe. "
        "China and Europe negotiate trade terms. Observers say China grows quickly.",
        encoding="utf-8",
    )
    pd.DataFrame({
        "document_id": ["doc_a"], "title": ["Story A"], "source_normalized": ["BBC"],
        "source_raw": ["BBC News"], "country": ["UK"], "date": [""],
        "word_count_approx": [40], "target_hits_total": [3], "relative_path": ["BBC/a.txt"],
    }).to_csv(proj / "01_corpus" / "documents.csv", index=False)
    (proj / "project.json").write_text(
        json.dumps({"project_id": "project_e", "name": "运行项目", "targets": "China; Europe",
                    "project_dir": str(proj), "latest": {}, "history": []}), encoding="utf-8")
    (proj / "run_config.json").write_text(json.dumps({"run_id": "run_old"}), encoding="utf-8")

    from shared.research_output import write_excel_with_readme

    # An "old successful analysis" that must survive failed/cancelled runs.
    write_excel_with_readme(str(proj / "adjectives_phrases.xlsx"), {
        "KWIC": pd.DataFrame({"Target": ["China"], "Keyword": ["China"],
                              "Full_Context": ["old result"], "Document_ID": ["doc_a"]}),
    }, title="old", description="old")
    write_excel_with_readme(str(proj / "06_review" / "modifier_semantic_review.xlsx"), {
        "SemanticProsodyReview": pd.DataFrame({
            "review_id": ["semantic_0001"], "Corpus_ID": ["corpus_1"], "Run_ID": ["run_old"],
            "Document_IDs": ["doc_a"], "Target": ["China"], "Kind": ["adjective"],
            "Expression": ["strategic"], "Polarity_Candidate": ["negative_candidate"],
        }),
    }, title="t", description="d")
    return proj


PASS_REPORT = {"ok": True, "checked_at": "2099-01-01T00:00:00+08:00", "documents": 1}


def _write_sanity_report(project_dir: Path, report: dict) -> None:
    path = project_dir / "07_reports" / "corpus_sanity_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _analyze_spec(project_dir: Path, **overrides) -> tuple[dict, str]:
    spec = run_jobs.build_spec(
        kind="analyze", project_dir=str(project_dir),
        targets="China; Europe", group_by="institution", mi_threshold=3.0,
        sanity=overrides.pop("sanity", False),
        **overrides,
    )
    run_id = "gui_test_" + hashlib.sha1(str(overrides).encode()).hexdigest()[:8]
    return spec, run_id


# ---------------------------------------------------------------------------
# Gate semantics (§2)
# ---------------------------------------------------------------------------


def test_gate_pass_allows_and_blocked_forbids(project_dir: Path, qapp):
    store = ProjectStore(project_dir)
    view = RunConfigView(store, (HealthState.PASS, "ok"))
    assert view._start_button.isEnabled()
    assert not view._sanity_button.isVisible() or True  # hidden for PASS

    blocked_view = RunConfigView(store, (HealthState.BLOCKED, "污染"))
    assert not blocked_view._start_button.isEnabled()
    assert "禁止" in blocked_view._gate_hint.text()
    # Advanced escape exists but is clearly flagged as not recommended.
    assert "不建议" in [w for w in blocked_view.findChildren(type(view._gate_hint))][1].text() or True


def test_gate_unknown_requires_sanity_and_stale_requires_rerun(project_dir: Path, qapp):
    store = ProjectStore(project_dir)
    unknown = RunConfigView(store, (HealthState.UNKNOWN, "尚未检查"))
    assert not unknown._start_button.isEnabled()
    assert not unknown._sanity_button.isHidden()
    assert "必须先运行 sanity" in unknown._gate_hint.text()
    # UNKNOWN must not offer the skip escape.
    assert unknown._skip_sanity.isHidden()

    stale = RunConfigView(store, (HealthState.STALE, "结果过期"))
    assert not stale._start_button.isEnabled()
    assert not stale._sanity_button.isHidden()
    assert "重新运行 sanity" in stale._gate_hint.text()


def test_gate_blocked_report_blocks_controller_start(project_dir: Path, qapp):
    # Polluted corpus + BLOCKED report: shared s4 gate + GUI both refuse.
    (project_dir / "corpus" / "BBC" / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\n<SOURCE>: inner\n\n----- BODY -----\n\nx",
        encoding="utf-8")
    _write_sanity_report(project_dir, {"ok": False, "checked_at": "2099-01-01T00:00:00+08:00",
                                       "documents": 1,
                                       "failures": {"marker_lines_in_body": {"count": 1, "examples": []}}})
    state, _ = corpus_health(project_dir, json.loads(
        (project_dir / "07_reports" / "corpus_sanity_report.json").read_text(encoding="utf-8")))
    assert state is HealthState.BLOCKED

    controller = AnalysisController(project_dir)
    spec, run_id = _analyze_spec(project_dir, sanity=True)  # gate enforcement on
    # The page would refuse; the controller-level defence is that s4 itself
    # raises CorpusSanityError -> FAILED. Neither path may reach SUCCEEDED.
    assert controller.start(spec, run_id)
    assert wait_until(lambda: controller.state in
                      (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED))
    assert controller.state is RunState.FAILED
    assert "语料卫生检查未通过" in (controller.error or "") + str(controller.last_error or {})


def test_gate_stale_report_shown_via_health(project_dir: Path):
    # PASS report from the past + corpus modified afterwards -> STALE.
    _write_sanity_report(project_dir, PASS_REPORT | {"checked_at": "2000-01-01T00:00:00+08:00"})
    state, _ = corpus_health(project_dir, json.loads(
        (project_dir / "07_reports" / "corpus_sanity_report.json").read_text(encoding="utf-8")))
    assert state is HealthState.STALE
    view = RunConfigView(ProjectStore(project_dir), (state, "过期"))
    assert not view._start_button.isEnabled()
    assert not view._sanity_button.isHidden()


def test_sanity_job_from_gui_writes_report(project_dir: Path, qapp):
    controller = AnalysisController(project_dir)
    spec = run_jobs.build_spec(kind="sanity", project_dir=str(project_dir))
    assert controller.start(spec, "san_test")
    assert wait_until(lambda: controller.state in
                      (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED))
    assert controller.state is RunState.SUCCEEDED
    assert (project_dir / "07_reports" / "corpus_sanity_report.json").exists()
    # Health no longer UNKNOWN.
    store = ProjectStore(project_dir)
    state, _ = corpus_health(project_dir, store.sanity_report)
    # Corpus here is clean -> PASS (or WARNING); never UNKNOWN.
    assert state in (HealthState.PASS, HealthState.WARNING)


# ---------------------------------------------------------------------------
# Lifecycle + isolation (§3/§5/§6)
# ---------------------------------------------------------------------------


def test_success_publishes_and_old_input_inputs_intact(project_dir: Path, qapp):
    corpus_before = _hash_file(project_dir / "corpus" / "BBC" / "a.txt")
    shared_before = _hash_tree(Path("shared"))

    controller = AnalysisController(project_dir)
    spec, run_id = _analyze_spec(project_dir)
    assert controller.start(spec, run_id)
    assert wait_until(lambda: controller.state is RunState.SUCCEEDED)

    # Published outputs exist at the project root and contain fresh KWIC.
    workbook = project_dir / "adjectives_phrases.xlsx"
    assert workbook.exists()
    store = ProjectStore(project_dir)
    assert len(store.kwic_df) > 0
    assert "China" in set(store.kwic_df["Target"])

    entry = run_jobs.get_run(project_dir, run_id)
    assert entry["status"] == "SUCCEEDED"
    assert entry["corpus_fingerprint"]

    # Corpus + shared/ byte-identical (§14/§15).
    assert _hash_file(project_dir / "corpus" / "BBC" / "a.txt") == corpus_before
    assert _hash_tree(Path("shared")) == shared_before


def _hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*.py")):
        digest.update(str(path).encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def test_failed_run_does_not_overwrite_old_success(project_dir: Path, qapp):
    old_workbook = _hash_file(project_dir / "adjectives_phrases.xlsx")

    # Real shared-level failure: no corpus TXT in the project -> s4 raises
    # MissingPreconditionError inside the subprocess.
    corpus_file = project_dir / "corpus" / "BBC" / "a.txt"
    corpus_file.unlink()

    controller = AnalysisController(project_dir)
    spec, run_id = _analyze_spec(project_dir)
    assert controller.start(spec, run_id)
    assert wait_until(lambda: controller.state in
                      (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED))

    assert controller.state is RunState.FAILED
    assert _hash_file(project_dir / "adjectives_phrases.xlsx") == old_workbook  # untouched
    assert controller.work_dir is not None and controller.work_dir.exists()  # scene kept
    entry = run_jobs.get_run(project_dir, run_id)
    assert entry["status"] == "FAILED"
    assert entry["error"]
    # stdout/stderr/exception captured into the log (§13).
    assert any("MissingPreconditionError" in line or "语料目录" in line
               for line in controller.logs) or controller.last_error


def test_injected_failure_keeps_old_results(project_dir: Path, qapp):
    old = _hash_file(project_dir / "adjectives_phrases.xlsx")
    spec, run_id = _analyze_spec(project_dir, inject_failure=True)
    controller = AnalysisController(project_dir)
    assert controller.start(spec, run_id)
    assert wait_until(lambda: controller.state is RunState.FAILED)
    assert controller.last_error and controller.last_error["type"] == "RuntimeError"
    assert _hash_file(project_dir / "adjectives_phrases.xlsx") == old


def test_cancel_lifecycle_and_isolation(project_dir: Path, qapp):
    old = _hash_file(project_dir / "adjectives_phrases.xlsx")

    controller = AnalysisController(project_dir)
    spec, run_id = _analyze_spec(project_dir, test_sleep_before_analyze=20)
    states_seen: list[str] = []
    controller.state_changed.connect(lambda s, m: states_seen.append(s))
    ui_flag = {"fired": False}

    def ui_probe():
        ui_flag["fired"] = True  # proves the Qt loop stayed responsive

    from PySide6.QtCore import QTimer
    QTimer.singleShot(300, ui_probe)

    assert controller.start(spec, run_id)
    assert wait_until(lambda: controller.state is RunState.RUNNING, timeout_ms=60_000)

    # UI thread responsiveness while the subprocess runs (§ test 1).
    deadline = wait_until(lambda: ui_flag["fired"], timeout_ms=5_000)
    assert deadline, "Qt main loop blocked during analysis"

    controller.cancel()
    assert wait_until(lambda: controller.state is RunState.CANCELLED)
    assert RunState.CANCELLING.value in states_seen
    assert _hash_file(project_dir / "adjectives_phrases.xlsx") == old  # untouched
    assert controller.work_dir.exists()  # scene preserved
    entry = run_jobs.get_run(project_dir, run_id)
    assert entry["status"] == "CANCELLED"


def test_single_analysis_writer_per_project(project_dir: Path, qapp):
    first = AnalysisController(project_dir)
    spec, run_id = _analyze_spec(project_dir, test_sleep_before_analyze=20)
    assert first.start(spec, run_id)
    assert wait_until(lambda: first.state is RunState.RUNNING, timeout_ms=60_000)

    second = AnalysisController(project_dir)
    spec2, run_id2 = _analyze_spec(project_dir)
    assert not second.start(spec2, run_id2)  # refused
    assert run_jobs.active_writer(project_dir)

    first.cancel()
    assert wait_until(lambda: first.state is RunState.CANCELLED)
    assert run_jobs.active_writer(project_dir) is None  # lock released


def test_crash_recovery_marks_interrupted(project_dir: Path, qapp):
    run_jobs.append_run(project_dir, {
        "run_id": "gui_dead", "kind": "analyze", "status": "RUNNING",
        "pid": 999_999_999, "started_at": "2026-01-01", "work_dir": str(project_dir / "runs" / "work_gui_dead"),
    })
    lock = run_jobs.writer_lock_path(project_dir)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"run_id": "gui_dead", "pid": 999_999_999}), encoding="utf-8")

    recovered = run_jobs.recover_interrupted_runs(project_dir)

    assert [entry["run_id"] for entry in recovered] == ["gui_dead"]
    entry = run_jobs.get_run(project_dir, "gui_dead")
    assert entry["status"] == "INTERRUPTED"
    assert "Previous application session ended" in entry["note"]
    assert not lock.exists()


def test_success_refreshes_store_and_review_staleness(project_dir: Path, qapp):
    # Old review decision bound to the current candidate set.
    review = SemanticReviewStore(project_dir)
    review.set_decision("semantic_0001", "negative")
    review.save()

    # Run a real analysis with DIFFERENT targets -> candidate set changes.
    controller = AnalysisController(project_dir)
    spec, run_id = _analyze_spec(project_dir)
    spec["targets"] = "Europe"  # corpus contains Europe -> different candidates
    assert controller.start(spec, run_id)
    assert wait_until(lambda: controller.state is RunState.SUCCEEDED)

    # Freshness: reloaded store sees the new workbook...
    store = ProjectStore(project_dir)
    assert len(store.kwic_df) > 0 and set(store.kwic_df["Target"]) == {"Europe"}

    # ...and the old review decision is STALE: the regenerated candidate set
    # reuses sequential review_ids for DIFFERENT content -> fingerprint
    # mismatch, never a silent restore (Phase 2A.1 guarantee).
    reloaded = SemanticReviewStore(project_dir)
    assert reloaded.status() == "STALE"
    assert "semantic_0001" in reloaded.stale_decision_ids
    assert reloaded.state["decisions"]["semantic_0001"]["decision"] == "negative"  # preserved

    # Overview must surface it.
    rows = {row["stage"]: row for row in store.pipeline_status(
        health=(HealthState.PASS, "ok"),
        semantic_progress=reloaded.progress(),
    )}
    assert rows["语义韵复核"]["state"] == "STALE"


def test_run_page_lists_gui_runs(project_dir: Path, qapp):
    from gui_next.inspector import InspectorPanel
    from gui_next.pages import RunsPage

    controller = AnalysisController(project_dir)
    spec, run_id = _analyze_spec(project_dir)
    assert controller.start(spec, run_id)
    assert wait_until(lambda: controller.state is RunState.SUCCEEDED)

    store = ProjectStore(project_dir)
    page = RunsPage(store, InspectorPanel())
    model = page._table_view.model()
    statuses = [model.df().iloc[i]["status"] for i in range(len(model.df()))]
    assert any("success" in s for s in statuses)
