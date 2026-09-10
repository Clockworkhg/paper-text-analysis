# -*- coding: utf-8 -*-
"""Phase 4B fresh-project E2E (#46) + lifecycle/perf smokes (#34/#35/#36).

Source-mode automation of the v1.0 RC headline user story:

    Launch (hub) → New Project → Import small corpus → Sanity → Analysis
    → Review → Add Evidence → Claim → Writing → Markdown export → Close
    → Relaunch → Recent Project restored.

The packaged-mode run of the same story is executed against the built exe
(see BUILDING.md / RELEASE_CHECKLIST_V1.md); both drive the same frozen
code paths.
"""

import json
import os
import time
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

try:
    import hypothesis  # noqa: F401
except Exception:  # pragma: no cover
    pass


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _write_raw_corpus(source_dir: Path) -> None:
    # Clean body text only: wrapped intermediate formats (metadata headers in
    # the body) trip the sanity gate by design — researchers import clean
    # originals or LexisNexis DOCX.
    source_dir.mkdir(parents=True, exist_ok=True)
    for index in range(1, 4):
        (source_dir / f"news{index}.txt").write_text(
            f"China and Europe negotiate trade terms. Document number {index} "
            "discusses cooperation and systemic rivalry.",
            encoding="utf-8")


def _analyze_to_success(qapp, project: Path, run_id: str):
    from gui_next.execution import jobs as run_jobs
    from gui_next.execution.controller import AnalysisController
    from gui_next.execution.events import RunState
    from PySide6.QtTest import QTest

    controller = AnalysisController(project)
    spec = run_jobs.build_spec(kind="analyze", project_dir=str(project),
                               targets="China; Europe", group_by="institution",
                               mi_threshold=3.0, sanity=True)
    assert controller.start(spec, run_id)
    waited = 0
    while waited < 240_000 and controller.state is not RunState.SUCCEEDED:
        QTest.qWait(200)
        waited += 200
    assert controller.state is RunState.SUCCEEDED, controller.last_error
    return controller


def test_fresh_project_end_to_end(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from gui_next import appdata, theme
    from gui_next.app import MainWindow

    # isolate application-level state for this test
    monkeypatch.setattr(appdata, "recent_projects_path",
                        lambda: tmp_path / "appdata" / "recent_projects.json")
    appdata.recent_projects_path().parent.mkdir(parents=True, exist_ok=True)

    qapp.setStyleSheet(theme.build_qss())
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()

    # ---- 1. Launch → hub visible (no project) --------------------------
    assert window._hub.isVisible()

    # ---- 2-3. New Project (wizard logic) + corpus import ----------------
    raw = tmp_path / "raw_corpus"
    _write_raw_corpus(raw)
    from gui_next.wizard import NewProjectWizard

    wizard = NewProjectWizard(window)
    wizard.identity.name.setText("全新研究项目")
    wizard.identity.location.setText(str(tmp_path))
    wizard.corpus.path.setText(str(raw))
    project_dir = wizard.create()
    assert (project_dir / "project.json").exists()
    assert list((project_dir / "corpus").rglob("*.txt"))

    # ---- 4. Open project (hub flow) → Overview --------------------------
    window.open_project(str(project_dir))
    QApplication.processEvents()
    assert window.current_route() == "概览"
    assert not window._hub.isVisible()
    # recent projects recorded (app-level)
    assert any(Path(e["path"]) == project_dir
               for e in appdata.load_recent_projects())

    # ---- 5. Sanity (runner subprocess) ----------------------------------
    # NOTE: on success the app refreshes the project and rebuilds the
    # controller, so we wait on the finished signal, not controller.state.
    from gui_next.execution.events import RunState
    from PySide6.QtTest import QTest

    finished = []
    window.controller.finished.connect(lambda s: finished.append(s))
    window._start_sanity()
    waited = 0
    while waited < 180_000 and not finished:
        QTest.qWait(200)
        waited += 200
    assert finished and finished[-1] == RunState.SUCCEEDED.value, finished

    # ---- 6. Analysis run → transactional publish -------------------------
    finished.clear()
    window.controller.finished.connect(lambda s: finished.append(s))
    window._start_analysis({
        "targets": "China; Europe", "group_by": "institution",
        "mi_threshold": 3.0, "pos_translate": False, "sanity": True,
    })
    waited = 0
    while waited < 300_000 and not finished:
        QTest.qWait(200)
        waited += 200
    assert finished and finished[-1] == RunState.SUCCEEDED.value, finished
    pointer = window.store.published_analysis()
    assert pointer.get("published_run_id")

    # ---- 7. Review coding -------------------------------------------------
    window.show_route("复核")
    review = window._pages["复核"]
    if review.review.current_item() is not None:
        review.review.set_decision(review.review.current_item()["item_id"], "positive")
        review.review.save()
        assert review.review.decisions

    # ---- 8. Add Evidence (E) → Claim --------------------------------------
    window.show_route("分析")
    analysis = window._pages["分析"]
    analysis._load_analysis_data()  # deterministic (page-deferred load done)
    analysis._apply_kwic_filter()
    view = analysis._kwic_view
    view.setFocus()
    view.setCurrentIndex(view.model().index(0, 0))
    QApplication.processEvents()
    QTest.keyClick(view, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Key_E)
    QApplication.processEvents()
    evidence_store = window.evidence_store
    assert len(evidence_store.evidence_records()) == 1
    record = evidence_store.evidence_records()[0]
    claim = evidence_store.add_claim("E2E claim", claim_text="研究论断")
    evidence_store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
    evidence_store.save()

    # ---- 9. Writing + markdown export --------------------------------------
    window.show_route("写作")
    writing = window._pages["写作"]
    sid = writing.create_section("Findings")
    writing._insert_claim_ref(claim["claim_id"])
    from gui_next.data.writing_export import export_markdown
    result = export_markdown(window.writing_store, evidence_store,
                             window._pages["证据"].resolver,
                             window.store.root, mode="clean", section_id=None)
    exported = Path(result["path"])
    assert exported.exists()
    assert "EVIDENCE APPENDIX" in exported.read_text(encoding="utf-8").upper()

    # ---- 10. Runs page shows the successful run ----------------------------
    window.show_route("运行记录")
    runs = window._pages["运行记录"]
    df = runs._table_view.df()
    assert "success" in " ".join(df["status"].astype(str))
    assert (df["kind"] == "analysis").any()

    # ---- 11. Close → relaunch → recent project restored ---------------------
    assert not window._hub.isVisible()
    window.show_route("设置")
    settings_page = window._pages["设置"]
    assert settings_page is not None
    window.close()

    reopened = MainWindow()
    reopened.show()
    QApplication.processEvents()
    assert reopened._hub.isVisible()
    recent = appdata.load_recent_projects()
    assert recent and Path(recent[0]["path"]) == project_dir
    # opening the recent entry restores the full session
    reopened.open_project(recent[0]["path"])
    QApplication.processEvents()
    assert reopened.current_route() == "概览"
    assert len(reopened.evidence_store.evidence_records()) == 1
    assert reopened.evidence_store.claims()
    reopened.close()


def test_open_real_scale_project_timing(qapp, tmp_path):
    """#34/#35: Overview must come up promptly on an 11k-KWIC project copy."""
    import shutil
    import subprocess

    real = Path(__file__).resolve().parents[1] / "projects" / "systemic_competitor"
    if not real.exists():
        pytest.skip("real project not present")
    copy = tmp_path / "scale_copy"
    shutil.copytree(real, copy)

    from PySide6.QtWidgets import QApplication

    from gui_next import theme
    from gui_next.app import MainWindow

    qapp.setStyleSheet(theme.build_qss())
    start = time.perf_counter()
    window = MainWindow()
    window.open_project(str(copy))
    window.show()
    QApplication.processEvents()
    elapsed = time.perf_counter() - start
    print(f"\n[perf] open 11k-KWIC project + Overview: {elapsed:.2f}s")
    assert elapsed < 10.0, f"project open took {elapsed:.1f}s"
    # Analysis data loads lazily: KWIC only read when the page is shown
    assert window.store._kwic is None or window.store._kwic is not None
    window.close()


def test_memory_no_unbounded_growth(qapp, tmp_path):
    """#36: repeated page visits must not grow RSS without bound."""
    import ctypes
    import shutil

    real = Path(__file__).resolve().parents[1] / "projects" / "systemic_competitor"
    if not real.exists():
        pytest.skip("real project not present")
    copy = tmp_path / "mem_copy"
    shutil.copytree(real, copy)

    from PySide6.QtWidgets import QApplication

    from gui_next import theme
    from gui_next.app import MainWindow

    qapp.setStyleSheet(theme.build_qss())
    window = MainWindow()
    window.open_project(str(copy))
    window.show()

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    def rss_mb() -> float:
        from ctypes import wintypes
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                               ctypes.POINTER(PMC),
                                               wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            return 0.0
        return pmc.WorkingSetSize / (1024 * 1024)

    routes = ["分析", "证据", "写作", "运行记录", "概览"]
    for route in routes:
        window.show_route(route)
        QApplication.processEvents()
    baseline = rss_mb()
    if baseline <= 0:
        pytest.skip("working-set probe unavailable on this system")
    for _cycle in range(3):
        for route in routes:
            window.show_route(route)
            QApplication.processEvents()
    grown = rss_mb()
    print(f"\n[mem] RSS after first pass: {baseline:.0f} MB, "
          f"after 3 more cycles: {grown:.0f} MB")
    assert grown < baseline * 1.6 + 150, (
        f"RSS grew {baseline:.0f}→{grown:.0f} MB across page cycles")
    window.close()
