# -*- coding: utf-8 -*-
"""Headless tests for the gui-next research workbench (Phase 1, read-only).

Rendering happens offscreen; these tests verify the read-only data store and
that the full window builds and wires up against a synthetic project.
"""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from gui_next.data.store import ProjectStore  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


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
        "<SOURCE>: BBC\n\n----- BODY -----\n\nchina poses a threat to stability.", encoding="utf-8"
    )
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
        title="t",
        description="d",
    )
    return proj


def test_store_reads_project_outputs(project_dir: Path):
    store = ProjectStore(project_dir)

    assert store.is_project
    assert store.name == "测试项目"
    assert store.targets == ["China", "threat"]
    assert store.group_by == "institution"
    assert len(store.documents_df) == 2
    assert len(store.kwic_df) == 3
    assert len(store.collocates_df) == 1

    chips = {chip["label"]: chip["value"] for chip in store.stat_chips()}
    assert chips["文档"] == "2"
    assert chips["分组"] == "institution"


def test_store_runs_index_and_status(project_dir: Path):
    store = ProjectStore(project_dir)

    rows = store.runs_index()
    assert rows[0]["run_id"] == "run_abc123def456"
    assert rows[0]["frozen"] is False

    status = {row["stage"]: row for row in store.pipeline_status()}
    assert status["语料导入"]["state"] == 1
    assert status["分析"]["state"] == "✓"
    assert status["最终运行固化"]["state"] == "○"


def test_main_window_builds_and_wires_pages(project_dir: Path, qapp):
    from gui_next.app import MainWindow

    window = MainWindow()
    window.open_project(str(project_dir))

    assert window.current_route() == "概览"
    assert set(window._pages) == {"概览", "语料", "分析", "复核", "证据",
                                  "写作", "运行记录", "设置"}

    for key in ("语料", "分析", "复核", "运行记录", "概览"):
        window._navigate(key)
        assert window._stack.currentWidget() is window._pages[key]


def test_analysis_page_target_filter_and_collocate_jump(project_dir: Path, qapp):
    from gui_next.app import MainWindow

    window = MainWindow()
    window.open_project(str(project_dir))
    analysis = window._pages["分析"]

    assert analysis._current_target == "China"

    analysis._kwic_search.setText("china")
    assert len(analysis._kwic_model.df()) == 2

    analysis.view_collocate_in_concordance("threat")
    assert analysis.tabs.currentIndex() == 0
    assert len(analysis._kwic_model.df()) == 1


def test_inspector_renders_details(project_dir: Path, qapp):
    from gui_next.app import MainWindow

    window = MainWindow()
    window.open_project(str(project_dir))

    window.inspector.show_document({"document_id": "doc_a", "title": "Story A", "source_normalized": "BBC"})
    window.inspector.show_kwic({"Keyword": "China", "Target": "China", "Full_Context": "x china y"})
    window.inspector.show_collocate("China", {"Collocate": "threat", "Frequency": 5, "MI_Score": 4.8})
    window.inspector.show_source({"Source_Merged": "FT", "Country": "UK"})
    window.inspector.show_run({"label": "final", "files": []}, "run_1")
    window.inspector.show_empty()
