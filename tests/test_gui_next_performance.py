# -*- coding: utf-8 -*-
"""Phase 4A performance smoke (#37) — 11k-KWIC-scale interaction budget.

Not microbenchmarks: each operation must stay clearly below the 500ms
"noticeable freeze" threshold (target: page switches feel immediate).
Data is a synthetic frame at real research scale (11,105 KWIC rows,
6,101 collocates).
"""

import os
import time

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

KWIC_ROWS = 11_105
COLLOCATE_ROWS = 6_101
HARD_LIMIT_MS = 500


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _big_kwic() -> pd.DataFrame:
    rng = pd.DataFrame({
        "Target": ["China"] * (KWIC_ROWS // 2) + ["Europe"] * (KWIC_ROWS - KWIC_ROWS // 2),
        "Keyword": ["China"] * (KWIC_ROWS // 2) + ["Europe"] * (KWIC_ROWS - KWIC_ROWS // 2),
        "Left_Context": [f"context token {i} before the node" for i in range(KWIC_ROWS)],
        "Right_Context": [f"after the node token {i}" for i in range(KWIC_ROWS)],
        "Full_Context": [f"full context sentence number {i} with content" for i in range(KWIC_ROWS)],
        "Source": [f"Source {i % 24}" for i in range(KWIC_ROWS)],
        "Source_Normalized": [f"src_{i % 24}" for i in range(KWIC_ROWS)],
        "Group": [f"grp {i % 6}" for i in range(KWIC_ROWS)],
        "Date": ["2021-01-01"] * KWIC_ROWS,
        "Document_ID": [f"doc_{i % 198:04d}" for i in range(KWIC_ROWS)],
        "Title": [f"Title {i}" for i in range(KWIC_ROWS)],
    })
    return rng


def _big_collocates() -> pd.DataFrame:
    return pd.DataFrame({
        "Target": ["China"] * COLLOCATE_ROWS,
        "Collocate": [f"word_{i}" for i in range(COLLOCATE_ROWS)],
        "Frequency": [10 + (i % 90) for i in range(COLLOCATE_ROWS)],
        "Doc_Frequency": [5 + (i % 40) for i in range(COLLOCATE_ROWS)],
        "MI_Score": [3.0 + (i % 60) / 10 for i in range(COLLOCATE_ROWS)],
        "Log_Likelihood": [50.0 + i / 100 for i in range(COLLOCATE_ROWS)],
        "LL_Significance": ["***"] * COLLOCATE_ROWS,
        "POS": ["NOUN"] * COLLOCATE_ROWS,
    })


def _ms(start) -> float:
    return (time.perf_counter() - start) * 1000


def test_kwic_load_and_filter_at_full_scale(qapp):
    from PySide6.QtTest import QTest
    from gui_next.widgets import BaseTableView

    view = BaseTableView()
    view.set_empty_state("x", "y")

    start = time.perf_counter()
    view.set_dataframe(_big_kwic())
    load_ms = _ms(start)
    assert view.model().rowCount() == KWIC_ROWS

    start = time.perf_counter()
    view.set_dataframe(_big_kwic().iloc[:50])
    narrow_ms = _ms(start)

    start = time.perf_counter()
    view.selectRow(10)
    view.current_record()
    select_ms = _ms(start)

    print(f"\n[perf] 11k KWIC set_dataframe: {load_ms:.0f} ms, "
          f"narrow update: {narrow_ms:.0f} ms, select: {select_ms:.0f} ms")
    assert load_ms < HARD_LIMIT_MS, f"KWIC load froze UI for {load_ms:.0f} ms"
    assert narrow_ms < HARD_LIMIT_MS
    assert select_ms < HARD_LIMIT_MS


def test_kwic_text_filter_at_full_scale(qapp):
    """The concordance filter path (per keystroke) must stay responsive."""
    from gui_next.pages import AnalysisPage  # noqa: F401 — importable

    kwic = _big_kwic()
    needle = "number 42"

    start = time.perf_counter()
    mask = kwic["Full_Context"].astype(str).str.lower().str.contains(
        needle.lower(), regex=False, na=False)
    _ = kwic[mask]
    elapsed = _ms(start)
    print(f"\n[perf] context filter over {KWIC_ROWS} rows: {elapsed:.0f} ms")
    assert elapsed < HARD_LIMIT_MS


def test_collocates_target_switch_at_scale(qapp):
    from gui_next.widgets import BaseTableView

    view = BaseTableView()
    df = _big_collocates()
    view.set_dataframe(df)

    start = time.perf_counter()
    subset = df[df["Target"] == "China"].reset_index(drop=True)
    view.set_dataframe(subset)
    elapsed = _ms(start)
    print(f"\n[perf] collocates target switch ({COLLOCATE_ROWS} rows): {elapsed:.0f} ms")
    assert elapsed < HARD_LIMIT_MS


def test_sort_11k_rows(qapp):
    from gui_next.widgets import BaseTableView

    view = BaseTableView()
    view.set_dataframe(_big_kwic())
    start = time.perf_counter()
    view.model().sort(0)
    elapsed = _ms(start)
    print(f"\n[perf] sort 11k rows: {elapsed:.0f} ms")
    assert elapsed < HARD_LIMIT_MS
