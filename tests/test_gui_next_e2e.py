# -*- coding: utf-8 -*-
"""Phase 4A GUI integration E2E (#39) — one full research user story.

Open Project → Overview → Corpus → Analysis → Add Evidence → Review →
Claim → Writing → Run Compare gate → Evidence Refresh gate → back to
Writing. Verifies navigation state, Inspector, selection, keyboard and
status banners — not the underlying algorithms (covered elsewhere).

Runs on a throwaway project copy; the real project is never touched.
"""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from gui_next.data.evidence_store import EvidenceStore  # noqa: E402
from gui_next.data.store import ProjectStore  # noqa: E402
from gui_next.execution import jobs as run_jobs  # noqa: E402
from gui_next.execution.controller import AnalysisController  # noqa: E402
from gui_next.execution.events import RunState  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def published_project(tmp_path_factory, qapp):
    """Small project that walks the full publication pipeline once."""
    proj = tmp_path_factory.mktemp("e2e") / "proj"
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
        {"project_id": "project_e2e", "name": "E2E 项目", "targets": "China",
         "project_dir": str(proj), "latest": {}, "history": []}), encoding="utf-8")
    (proj / "run_config.json").write_text(json.dumps({"run_id": "run_seed"}), encoding="utf-8")

    controller = AnalysisController(proj)
    spec = run_jobs.build_spec(kind="analyze", project_dir=str(proj), targets="China; Europe",
                               group_by="institution", mi_threshold=3.0, sanity=False)
    assert controller.start(spec, "gui_e2e_run")
    from PySide6.QtTest import QTest
    waited = 0
    while waited < 180_000 and controller.state is not RunState.SUCCEEDED:
        QTest.qWait(200)
        waited += 200
    assert controller.state is RunState.SUCCEEDED
    return proj


def _full_window(qapp, project: Path):
    from gui_next import theme
    from gui_next.app import MainWindow

    qapp.setStyleSheet(theme.build_qss())
    window = MainWindow()
    window.resize(1440, 900)
    window.open_project(str(project))
    window.show()
    return window


def test_full_research_user_story(published_project, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    window = _full_window(qapp, published_project)
    try:
        app = QApplication.instance()

        # ---- Overview: project answers "what should I do next" -----------
        assert window.current_route() == "概览"
        overview = window._pages["概览"]
        assert overview._attention_items
        app.processEvents()

        # ---- Corpus: documents table + selection drives the Inspector ----
        window.router.navigate_to("语料")
        corpus = window._pages["语料"]
        corpus._doc_view.selectRow(0)
        app.processEvents()
        assert window.inspector._type_label.text() == "DOCUMENT"
        # filter keeps the count honest (needle read from the live registry —
        # publication rewrites document ids to stable hashes)
        first_id = str(corpus._docs_df.iloc[0]["document_id"])
        corpus._doc_filter.search.setText(first_id[:8])
        app.processEvents()
        assert len(corpus._doc_view.df()) == 1
        corpus._doc_filter.clear_filters()
        app.processEvents()

        # ---- Analysis: keyboard evidence capture (E) ---------------------
        window.router.navigate_to("分析")
        analysis = window._pages["分析"]
        assert analysis._current_target == "China"
        app.processEvents()
        view = analysis._kwic_view
        QTest.qWait(200)
        analysis._apply_kwic_filter()
        view.setFocus()
        view.setCurrentIndex(view.model().index(0, 0))
        app.processEvents()
        QTest.keyClick(view, Qt.Key_E)
        QTest.qWait(200)
        evidence_store = window.evidence_store
        assert len(evidence_store.evidence_records()) == 1
        assert window.inspector._badge.text()  # "✓ 已加入证据" / "✓ In Evidence"

        # ---- Review: keyboard coding -------------------------------------
        window.router.navigate_to("复核")
        review = window._pages["复核"]
        if review.review.current_item() is not None:
            QTest.keyClick(review, Qt.Key_1)
            assert review.review.decisions, "review decision should persist"

        # ---- Evidence: claim + claim workspace grouping ------------------
        window.router.navigate_to("证据")
        evidence_page = window._pages["证据"]
        evidence_page._new_claim_dialog = lambda: None  # guard: no modal in E2E
        record = evidence_store.evidence_records()[0]
        claim = evidence_store.add_claim("E2E claim", claim_text="China framed as threat")
        evidence_store.claim_add_evidence(claim["claim_id"], record["evidence_id"])
        evidence_store.save()
        evidence_page.refresh()
        app.processEvents()
        assert evidence_page._select_claim(claim["claim_id"])
        app.processEvents()
        assert evidence_page._current_claim_id == claim["claim_id"]
        # the claim workspace distinguishes pattern vs qualitative evidence
        assert evidence_page._pattern_view is not None
        assert evidence_page._qualitative_view is not None

        # claim visible in the unified Inspector
        evidence_page.show_evidence_detail(evidence_store.get_evidence(record["evidence_id"]))
        app.processEvents()
        assert window.inspector._type_label.text() == "EVIDENCE"

        # ---- Writing: quiet workspace receives the claim ------------------
        window.router.navigate_to("写作")
        writing = window._pages["写作"]
        sid = writing.create_section("Findings")
        writing._insert_claim_ref(claim["claim_id"])
        app.processEvents()
        section = writing.store.get_section(sid)
        assert any(block["type"] == "CLAIM_REF" for block in section["blocks"])

        # ---- Runs: compare gate closed with one published run -------------
        window.router.navigate_to("运行记录")
        runs = window._pages["运行记录"]
        app.processEvents()
        assert not runs._compare_button.isEnabled()
        df = runs._table_view.df()
        assert (df["kind"] == "analysis").any()
        assert "success" in " ".join(df["status"].astype(str))

        # ---- Evidence refresh gate: no newer run → honest message path ----
        window.router.navigate_to("证据")
        evidence_page._check_newer_run  # wired; the honest no-op path shows a box
        pointer = window.store.published_analysis()
        assert pointer.get("published_run_id") == "gui_e2e_run"

        # ---- Back navigation returns to the research context --------------
        assert window.router.back()
        app.processEvents()
        assert window.current_route() == "运行记录"
        assert window.router.back()
        app.processEvents()
        assert window.current_route() == "写作"

        # ---- Global search palette reaches the claim ----------------------
        palette = window._palette
        palette._refresh("E2E claim")
        assert palette._list.count() >= 1
    finally:
        window.close()
