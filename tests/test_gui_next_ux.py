# -*- coding: utf-8 -*-
"""Phase 4A tests: GUI consolidation & UX hardening.

Covers: status vocabulary single-source, shared table/filter/empty-state
primitives, unified Inspector, router history + object focus, global search
palette, lazy writing document creation (read-only project open), regression
fixes from the GUI audit (B1-B9), Overview dashboard semantics (no fake
percentages), and resolution/render smoke.
"""

import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

try:
    # Preload hypothesis: the pytest plugin lazy-imports it at terminal
    # summary, and that late import access-violates on this stack
    # (PySide6 offscreen + Python 3.13). Early import avoids the crash.
    import hypothesis  # noqa: F401
except Exception:  # pragma: no cover
    pass

from gui_next.data.store import ProjectStore  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "01_corpus").mkdir(parents=True)
    pd.DataFrame({
        "document_id": ["doc_a", "doc_b"],
        "title": ["Story A", "Story B"],
        "source_normalized": ["BBC", "VOA"],
        "country": ["UK", "US"],
        "date": ["2021-01-01", ""],
        "word_count_approx": [120, 90],
        "target_hits_total": [2, 1],
        "relative_path": ["BBC/a.txt", "VOA/b.txt"],
    }).to_csv(proj / "01_corpus" / "documents.csv", index=False)
    (proj / "project.json").write_text(
        json.dumps({"name": "测试项目", "targets": "China; threat", "group_by": "institution"}),
        encoding="utf-8",
    )
    corpus_dir = proj / "corpus" / "BBC"
    corpus_dir.mkdir(parents=True)
    (corpus_dir / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\nchina poses a threat to stability.", encoding="utf-8")
    (proj / "run_config.json").write_text(
        json.dumps({"run_id": "run_abc123def456", "targets": "China; threat"}),
        encoding="utf-8",
    )
    from shared.research_output import write_excel_with_readme

    write_excel_with_readme(
        str(proj / "adjectives_phrases.xlsx"),
        {
            "KWIC": pd.DataFrame({
                "Target": ["China", "China", "threat"],
                "Keyword": ["China", "China", "threat"],
                "Full_Context": ["china poses a threat", "china trade talks", "an existential threat"],
                "Source": ["BBC", "VOA", "BBC"],
                "Source_Normalized": ["BBC", "VOA", "BBC"],
                "Group": ["BBC", "VOA", "BBC"],
                "Document_ID": ["doc_a", "doc_b", "doc_a"],
            }),
            "Collocates": pd.DataFrame({
                "Target": ["China"], "Collocate": ["threat"], "Frequency": [5],
                "Doc_Frequency": [3], "MI_Score": [4.8], "Log_Likelihood": [72.4],
                "LL_Significance": ["***"], "POS": ["NOUN"], "Example_Contexts": ["a || b"],
            }),
            "GroupComparison": pd.DataFrame({"Source_Group": ["BBC"], "Group_By": ["institution"]}),
        },
        title="t", description="d",
    )
    return proj


@pytest.fixture()
def window(project_dir: Path, qapp):
    from gui_next import theme
    from gui_next.app import MainWindow

    app = qapp
    app.setStyleSheet(theme.build_qss())
    window = MainWindow()
    window.open_project(str(project_dir))
    yield window
    window.close()


# ---------------------------------------------------------------------------
# Status vocabulary (#17): one display layer, no invented synonyms
# ---------------------------------------------------------------------------

def test_status_vocabulary_covers_all_states():
    from gui_next import status
    from gui_next.data.health import HealthState

    for state in HealthState:
        glyph, text, role = status.health(state)
        assert glyph and text and role in ("ok", "warn", "error", "muted", "primary")

    for state in ("NOT_STARTED", "IN_PROGRESS", "COMPLETE", "STALE"):
        assert status.review(state)[1]

    for state in ("VERIFIED", "SOURCE_UNAVAILABLE", "INTEGRITY_ERROR"):
        assert status.integrity(state)[1]

    for state in ("PREPARING", "RUNNING", "CANCELLING", "ANALYSIS_SUCCEEDED",
                  "PUBLISHING", "SUCCEEDED", "FAILED", "CANCELLED",
                  "PUBLISH_FAILED", "INTERRUPTED", "RECOVERY_REQUIRED"):
        assert status.run(state)[1]

    for level in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE", "NOT_COMPARABLE"):
        assert status.comparison(level)[1]

    # No invented synonyms anywhere in the UI code base.
    banned = ['"Done"', '"Finished"', '"Ready"', '"OK"']
    for page_file in ("pages.py", "evidence_page.py", "writing_page.py",
                      "review_workbench.py", "source_review_panel.py", "app.py"):
        source = (Path("gui_next") / page_file).read_text(encoding="utf-8")
        for word in banned:
            assert word not in source, f"{page_file} invents display state {word}"


# ---------------------------------------------------------------------------
# Shared primitives (#11/#12/#13): one table, one filter bar, empty states
# ---------------------------------------------------------------------------

def test_base_table_view_signals_copy_and_empty_state(qapp):
    from gui_next.widgets import BaseTableView

    view = BaseTableView()
    captured = {}
    view.recordSelected.connect(lambda record: captured.update(selected=record))
    view.recordActivated.connect(lambda record: captured.update(activated=record))

    view.set_empty_state("No data", "调整筛选后重试。")

    df = pd.DataFrame({"ID": ["a", "b"], "Title": ["Alpha", "Beta"]})
    view.set_dataframe(df)
    assert view._empty is not None and view._empty.isHidden()

    view.selectRow(1)
    assert captured["selected"]["ID"] == "b"

    view.set_dataframe(pd.DataFrame({"ID": [], "Title": []}))
    assert view._empty is not None and not view._empty.isHidden()

    # select_by_id + width hints
    view.set_dataframe(df)
    view.set_column_widths({"Title": 240})
    assert view.select_by_id("a")
    assert view.current_record()["Title"] == "Alpha"


def test_filterbar_clear_and_result_count(qapp):
    from PySide6.QtCore import Qt
    from gui_next.widgets import FilterBar

    bar = FilterBar()
    events = []
    bar.changed.connect(lambda: events.append(1))
    bar.add_combo("Type", [("全部", ""), ("KWIC", "kwic")])
    bar.set_result_count(3, 10)

    bar.search.setText("china")
    assert events and bar.is_filtering()
    bar.clear_filters()
    assert not bar.is_filtering()
    assert bar.search.text() == ""
    assert bar.combo_value(0) == ""
    assert "3" in bar._count.text() and "10" in bar._count.text()


def test_every_primary_page_has_empty_state_or_content(project_dir, window):
    """No bare white panels: data pages declare an empty state (#13)."""
    corpus = window._pages["语料"]
    assert corpus._doc_view._empty is not None
    analysis = window._pages["分析"]
    assert analysis._kwic_view._empty is not None
    evidence = window._pages["证据"]
    assert evidence._view._empty is not None
    runs = window._pages["运行记录"]
    assert runs._table_view._empty is not None


# ---------------------------------------------------------------------------
# Unified Inspector (#4): one structure, public API only
# ---------------------------------------------------------------------------

def test_inspector_unified_structure_and_typed_objects(qapp):
    from gui_next.inspector import InspectorPanel

    inspector = InspectorPanel()
    inspector.show_document({"document_id": "doc_a", "title": "Story A"})
    assert inspector._type_label.text() == "DOCUMENT"

    inspector.show_kwic({"Keyword": "China", "Target": "China",
                         "Full_Context": "x china y"})
    assert inspector._type_label.text() == "KWIC"

    inspector.show_collocate("China", {"Collocate": "threat", "Frequency": 5,
                                       "MI_Score": 4.8, "Log_Likelihood": 72.4})
    assert inspector._type_label.text() == "COLLOCATE"

    inspector.show_source({"Source_Merged": "FT", "Country": "UK"})
    assert inspector._type_label.text() == "SOURCE"

    inspector.show_run({"label": "final", "files": [], "corpus_fingerprint": {}}, "run_1")
    assert inspector._type_label.text() == "RUN"

    inspector.show_claim({"claim_id": "c1", "title": "T", "claim_text": "x"}, 2)
    assert inspector._type_label.text() == "CLAIM"

    inspector.show_evidence({"evidence_id": "e1", "evidence_type": "kwic",
                             "captured_snapshot": {"Keyword": "China"},
                             "published_run_id": "gui_run"},
                            state="VERIFIED")
    assert inspector._type_label.text() == "EVIDENCE"
    assert "✓" in inspector._badge.text()

    inspector.show_comparison("gui_run_aaaa", "gui_run_bbbb", {"level": "FULLY_COMPARABLE"})
    assert inspector._type_label.text() == "COMPARISON"

    inspector.show_empty()
    assert inspector._heading.text()


# ---------------------------------------------------------------------------
# Router + global search (#26/#27/#28)
# ---------------------------------------------------------------------------

def test_router_history_and_context_focus(project_dir, window):
    router = window.router
    assert window.current_route() == "概览"

    router.navigate_to("语料", context={"tab": "health"})
    assert window.current_route() == "语料"
    assert window._pages["语料"].tabs.currentIndex() == 2

    router.navigate_to("分析")
    assert window.current_route() == "分析"
    assert router.can_go_back

    assert router.back()
    assert window.current_route() == "语料"
    # context replayed on back
    assert window._pages["语料"].tabs.currentIndex() == 2


def test_object_routes_map_to_pages():
    from gui_next.router import OBJECT_ROUTE, ROUTES

    for kind, route in OBJECT_ROUTE.items():
        assert route in ROUTES


def test_global_search_palette_finds_and_navigates(project_dir, window):
    palette = window._palette
    entries = palette._build_entries()
    kinds = {entry["kind"] for entry in entries}
    assert {"Document", "Target", "Run"} <= kinds

    palette._refresh("doc_a")
    assert palette._list.count() >= 1
    first = palette._list.item(0)
    entry = first.data(0x0100)  # Qt.UserRole
    assert entry["object_id"] == "doc_a"


# ---------------------------------------------------------------------------
# Lazy writing document (#B8): opening a project never writes
# ---------------------------------------------------------------------------

def test_open_project_does_not_create_writing_document(project_dir, window):
    from PySide6.QtWidgets import QApplication

    assert not (window.store.root / "09_writing" / "writing.json").exists()
    window.show()
    window.show_route("写作")
    QApplication.processEvents()
    writing = window._pages["写作"]
    assert not writing.store.has_document
    # empty state offers the explicit next step
    assert writing._empty_state.isVisible()


def test_writing_section_creation_defers_document_write(project_dir, window):
    from gui_next.data.writing_store import WritingStore
    writing = window._pages["写作"]
    writing.store = WritingStore(window.store.root)
    writing.create_section("Introduction")  # non-interactive path (no modal)
    assert writing.store.has_document
    assert (window.store.root / "09_writing" / "writing.json").exists()
    assert writing._empty_state.isVisible() is False


# ---------------------------------------------------------------------------
# Audit regressions B1-B9
# ---------------------------------------------------------------------------

def test_b1_start_analysis_uses_datetime_and_store_root(project_dir, window):
    """app._start_analysis must not crash on missing imports/attributes (B1)."""
    import inspect
    from gui_next.app import MainWindow

    source = inspect.getsource(MainWindow._start_analysis)
    assert "datetime.now()" in source
    assert "self.store.root" in source
    import gui_next.app as app_module
    assert hasattr(app_module, "datetime")


def test_b2_evidence_page_imports_json_and_path():
    import gui_next.evidence_page as module
    assert hasattr(module, "json") and hasattr(module, "Path")


def test_b3_runs_compare_requires_two_selected(project_dir, window):
    runs = window._pages["运行记录"]
    assert not runs._compare_button.isEnabled()
    assert runs._selected_published_run_ids() == []


def test_b4_review_lock_does_not_crash(project_dir):
    from gui_next.data.review_store import SemanticReviewStore
    from gui_next.inspector import InspectorPanel
    from gui_next.review_workbench import SemanticReviewWorkbench

    store = SemanticReviewStore(project_dir)
    workbench = SemanticReviewWorkbench(store, InspectorPanel())
    workbench.set_locked(True)     # B4: used to raise AttributeError
    workbench.set_locked(False)


def test_b4_source_panel_lock_does_not_crash(project_dir):
    from gui_next.data.review_store import SourceCountryReviewStore
    from gui_next.inspector import InspectorPanel
    from gui_next.source_review_panel import SourceReviewPanel

    store = SourceCountryReviewStore(project_dir, documents_df=ProjectStore(project_dir).documents_df)
    panel = SourceReviewPanel(store, InspectorPanel())
    panel.set_locked(True)
    panel.set_locked(False)


def test_b7_source_panel_maps_by_identity_not_row(project_dir, window):
    corpus = window._pages["语料"]
    panel = corpus.source_panel
    if panel is None:
        pytest.skip("no source store in this fixture")
    panel.set_source("VOA")
    assert panel.review.items[panel.index]["source"] == "VOA"


def test_b6_analysis_page_fills_workspace(project_dir, window):
    """B6: duplicate addWidget squeezed the analysis body — now expanded."""
    from PySide6.QtWidgets import QApplication

    analysis = window._pages["分析"]
    window.resize(1400, 800)
    window.show()
    window.show_route("分析")
    QApplication.processEvents()
    # tabs occupy the area right of the ~300px target list
    tabs_width = analysis.tabs.width()
    assert tabs_width > 600, f"analysis tabs too narrow: {tabs_width}px"


def test_b9_runs_row_identity_survives_display_mapping(project_dir, window):
    runs = window._pages["运行记录"]
    df = runs._table_view.df()
    assert "run_id" in df.columns
    assert "证据引用" in df.columns


# ---------------------------------------------------------------------------
# Overview dashboard (#18/#19): states, never fake percentages
# ---------------------------------------------------------------------------

def test_overview_pipeline_states_are_not_percentages(project_dir, window):
    store = window.store
    rows = store.pipeline_status()
    for row in rows:
        state = str(row["state"])
        assert "%" not in state
        assert not state.isdigit() or int(state) <= 100000


def test_overview_attention_and_next_action(project_dir, window):
    overview = window._pages["概览"]
    items = overview._attention_items
    assert items, "fixture project should surface at least one attention item"
    texts = " ".join(item["text"] for item in items)
    assert "语义韵" in texts or "来源" in texts


# ---------------------------------------------------------------------------
# Corpus health tab offers the GUI sanity action
# ---------------------------------------------------------------------------

def test_corpus_health_tab_wires_sanity_route(project_dir, window):
    corpus = window._pages["语料"]
    corpus.tabs.setCurrentIndex(2)
    # the health tab must point GUI users at the in-app sanity run (#audit 3)
    buttons = corpus.findChildren(type(corpus._request_sanity))
    # request routes to the analysis run-config view
    corpus._request_sanity()
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    assert window._stack.currentWidget() is window._pages["分析"]


# ---------------------------------------------------------------------------
# Writing page: quiet design (#24)
# ---------------------------------------------------------------------------

def test_writing_blocks_use_context_menu_not_control_rows(project_dir, window):
    import inspect
    from gui_next.writing_page import WritingPage

    source = inspect.getsource(WritingPage._block_widget)
    assert "Remove from Writing" not in source  # no per-card button rows
    assert hasattr(WritingPage, "_block_menu")


# ---------------------------------------------------------------------------
# Resolution / render smoke (#30/#38): structural, not pixel assertions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("size", [(1366, 768), (1920, 1080)])
def test_pages_render_at_required_resolutions(project_dir, window, size):
    from PySide6.QtWidgets import QApplication

    width, height = size
    window.show()
    window.resize(width, height)
    QApplication.processEvents()

    checks = {
        "概览": lambda page: page.width() > 0,
        "语料": lambda page: page.tabs.widget(0).findChild(type(page._doc_view)) is not None,
        "分析": lambda page: page._target_list.count() > 0,
        "复核": lambda page: page._progress_label is not None,
        "证据": lambda page: page._view is not None,
        "写作": lambda page: page._empty_state is not None,
        "运行记录": lambda page: page._table_view is not None,
        "设置": lambda page: page.layout() is not None,
    }
    for route, check in checks.items():
        window.show_route(route)
        QApplication.processEvents()
        page = window._pages[route]
        assert page.isVisible(), f"{route} not visible at {width}x{height}"
        assert page.height() > 100, f"{route} collapsed at {width}x{height}"
        assert check(page), f"{route} key control missing at {width}x{height}"
        pixmap = window.grab()
        assert not pixmap.isNull()
        assert pixmap.width() >= width - 5


def test_inspector_toggle_collapses_and_expands(project_dir, window):
    from PySide6.QtWidgets import QApplication

    window.show()
    QApplication.processEvents()
    assert window.inspector.isVisible()
    window._toggle_inspector(False)
    QApplication.processEvents()
    assert not window.inspector.isVisible()
    # workspace expands: stack gets the freed width
    stack_width_hidden = window._stack.width()
    window._toggle_inspector(True)
    QApplication.processEvents()
    assert window.inspector.isVisible()
    assert window._stack.width() < stack_width_hidden


def test_sidebar_toggle(project_dir, window):
    from PySide6.QtWidgets import QApplication

    window.show()
    QApplication.processEvents()
    window._toggle_sidebar(False)
    QApplication.processEvents()
    assert not window._sidebar.isVisible()
    window._toggle_sidebar(True)
    QApplication.processEvents()
    assert window._sidebar.isVisible()
