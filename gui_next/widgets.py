# -*- coding: utf-8 -*-
"""Shared UI primitives (Phase 4A consolidation).

One table experience, one filter bar, one empty state, one banner, one toast.
Pages compose these instead of hand-building QLabel+QTableView stacks.

All visual tokens come from gui_next.theme; all state wording from
gui_next.status.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.models import DataFrameModel


# ======================================================================
# BaseTableView — the single research table experience
# ======================================================================

class BaseTableView(QTableView):
    """Unified table for all research data pages.

    - fixed row/header heights, row selection, no edit, sortable;
    - recordSelected(dict) on click/keyboard selection, recordActivated(dict)
      on double-click or Enter;
    - Ctrl+C copies the selection as TSV;
    - overlay empty state (title/hint/action) when the model is empty;
    - optional per-column width hints applied after each set_dataframe.
    """

    recordSelected = Signal(dict)
    recordActivated = Signal(dict)

    def __init__(self, *, stretch_last: bool = False, parent=None):
        super().__init__(parent)
        self._model = DataFrameModel(pd.DataFrame(), self)
        self.setModel(self._model)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(theme.ROW_HEIGHT)
        self.horizontalHeader().setFixedHeight(theme.HEADER_HEIGHT)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(stretch_last)
        self.horizontalHeader().setMinimumSectionSize(48)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.SingleSelection)
        self.setEditTriggers(QTableView.NoEditTriggers)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self._width_hints: Dict[str, int] = {}
        self._empty: Optional[EmptyState] = None
        self.doubleClicked.connect(self._emit_activated)

    # -- data ----------------------------------------------------------

    def set_dataframe(self, df: pd.DataFrame, *, preserve_selection: bool = False) -> None:
        model = self.model()
        previous_id = None
        if preserve_selection and self.currentIndex().isValid():
            previous_id = self.current_record().get("ID")
        if isinstance(model, DataFrameModel):
            model.set_dataframe(df)
        self._apply_width_hints()
        self._update_empty()
        if previous_id is not None:
            self.select_by_id(previous_id)
        record = self.current_record()
        if record:
            self.recordSelected.emit(record)

    def df(self) -> pd.DataFrame:
        model = self.model()
        return model.df() if isinstance(model, DataFrameModel) else pd.DataFrame()

    def model(self) -> DataFrameModel:  # type: ignore[override]
        return super().model()  # type: ignore[return-value]

    def current_record(self) -> Dict[str, Any]:
        model = self.model()
        return model.row(self.currentIndex()) if isinstance(model, DataFrameModel) else {}

    def select_by_id(self, object_id: str, id_column: str = "ID") -> bool:
        model = self.model()
        if not isinstance(model, DataFrameModel):
            return False
        columns = list(model.df().columns)
        col = None
        for name in ("ID", "evidence_id", "document_id", "run_id", id_column):
            if name in columns:
                col = columns.index(name)
                break
        if col is None:
            return False
        for row in range(model.rowCount()):
            if str(model.df().iat[row, col]) == str(object_id):
                self.selectRow(row)
                return True
        return False

    def set_column_widths(self, hints: Dict[str, int]) -> None:
        """Column width hints by header name; applied after each data set."""
        self._width_hints = dict(hints)
        self._apply_width_hints()

    def _apply_width_hints(self) -> None:
        header = self.horizontalHeader()
        model = self.model()
        if not isinstance(model, DataFrameModel):
            return
        columns = list(model.df().columns)
        for index, name in enumerate(columns):
            if name in self._width_hints:
                self.setColumnWidth(index, self._width_hints[name])

    # -- empty state -----------------------------------------------------

    def set_empty_state(self, title: str, hint: str = "",
                        action_text: str = "", action: Optional[Callable] = None) -> None:
        if self._empty is None:
            self._empty = EmptyState(self)
            self._empty.setGeometry(self.viewport().geometry())
        self._empty.configure(title, hint, action_text, action)
        self._update_empty()

    def _update_empty(self) -> None:
        if self._empty is None:
            return
        empty = self.model().rowCount() == 0
        self._empty.setVisible(empty)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if self._empty is not None:
            self._empty.setGeometry(self.viewport().geometry())

    # -- interaction -----------------------------------------------------

    def currentChanged(self, current, previous) -> None:  # noqa: N802 (Qt naming)
        """Single notification point for selection: mouse, keyboard, and
        programmatic (router focus) all land here."""
        super().currentChanged(current, previous)
        if current.isValid():
            record = self.current_record()
            if record:
                self.recordSelected.emit(record)

    def _emit_activated(self, index) -> None:
        record = self.model().row(index)
        if record:
            self.recordActivated.emit(record)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers():
            record = self.current_record()
            if record:
                self.recordActivated.emit(record)
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_selection(self) -> None:
        selection = self.selectionModel()
        model = self.model()
        if selection is None or not selection.hasSelection() or not isinstance(model, DataFrameModel):
            return
        df = model.df()
        rows = sorted({index.row() for index in selection.selectedRows()})
        columns = list(df.columns)
        lines = ["\t".join(str(c) for c in columns)]
        for row in rows:
            lines.append("\t".join("" if pd.isna(df.iat[row, col]) else str(df.iat[row, col])
                                   for col in range(len(columns))))
        QGuiApplication.clipboard().setText("\n".join(lines))


# ======================================================================
# EmptyState — what happened + what to do next
# ======================================================================

class EmptyState(QWidget):
    """'Nothing here yet' panel: title, one-line hint, optional action."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyState")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(theme.SP_8)
        self._title = QLabel("")
        self._title.setObjectName("EmptyTitle")
        self._title.setAlignment(Qt.AlignCenter)
        self._hint = QLabel("")
        self._hint.setObjectName("EmptyHint")
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setWordWrap(True)
        self._action = QPushButton("")
        self._action.setObjectName("Primary")
        self._action.setFixedWidth(200)
        self._action.clicked.connect(self._run_action)
        self._action.hide()
        layout.addWidget(self._title)
        layout.addWidget(self._hint)
        layout.addSpacing(theme.SP_8)
        layout.addWidget(self._action, 0, Qt.AlignCenter)
        self._handler: Optional[Callable] = None

    def configure(self, title: str, hint: str = "",
                  action_text: str = "", action: Optional[Callable] = None) -> None:
        self._title.setText(title)
        self._title.setVisible(bool(title))
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))
        self._handler = action
        self._action.setText(action_text or "")
        self._action.setVisible(bool(action_text and action))

    def _run_action(self) -> None:
        if self._handler is not None:
            self._handler()


# ======================================================================
# Banner — Info / Warning / Error, one visual system
# ======================================================================

class Banner(QFrame):
    """Persistent, non-modal status banner.

    level: "info" | "warning" | "error". Errors must stay until resolved —
    do not use Toast for failures.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Banner")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(theme.SP_16, theme.SP_12, theme.SP_16, theme.SP_12)
        self._layout.setSpacing(theme.SP_12)
        self._glyph = QLabel("")
        self._title = QLabel("")
        self._title.setObjectName("BannerTitle")
        self._body = QLabel("")
        self._body.setWordWrap(True)
        self._action = QPushButton("")
        self._action.clicked.connect(self._run_action)
        self._layout.addWidget(self._glyph, 0, Qt.AlignTop)
        self._layout.addWidget(self._title, 0, Qt.AlignTop)
        self._layout.addWidget(self._body, 1)
        self._layout.addWidget(self._action, 0, Qt.AlignTop)
        self.hide()
        self._handler: Optional[Callable] = None

    def show_banner(self, level: str, title: str, body: str = "",
                    action_text: str = "", action: Optional[Callable] = None,
                    glyph: str = "") -> None:
        self.setProperty("level", level)
        self._title.setProperty("level", level)
        glyphs = {"info": "ⓘ", "warning": "⚠", "error": "✕"}
        self._glyph.setText(glyph or glyphs.get(level, ""))
        self._glyph.setStyleSheet(f"color: {status_role_color(level)}; font-weight: 600;")
        self._title.setText(title)
        self._title.setVisible(bool(title))
        self._body.setText(body)
        self._body.setVisible(bool(body))
        self._handler = action
        self._action.setText(action_text or "")
        self._action.setVisible(bool(action_text and action))
        # QSS property selectors need a style re-evaluation.
        for widget in (self, self._title):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.show()

    def _run_action(self) -> None:
        if self._handler is not None:
            self._handler()


def status_role_color(level: str) -> str:
    return {"info": theme.PRIMARY, "warning": theme.WARNING,
            "error": theme.ERROR}.get(level, theme.MUTED)


# ======================================================================
# FilterBar — one filter/search experience
# ======================================================================

class FilterBar(QWidget):
    """Search + typed filter combos + Clear + result count."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SP_8)
        self._search = QLineEdit()
        self._search.setObjectName("FilterInput")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_changed)
        layout.addWidget(self._search, 2)
        self._fields: List[Tuple[str, QWidget]] = []
        self._clear = QPushButton("Clear filters")
        self._clear.setObjectName("Flat")
        self._clear.clicked.connect(self.clear_filters)
        self._clear.hide()
        layout.addWidget(self._clear)
        self._count = QLabel("")
        self._count.setObjectName("Muted")
        layout.addWidget(self._count)

    @property
    def search(self) -> QLineEdit:
        return self._search

    def set_search_placeholder(self, text: str) -> None:
        self._search.setPlaceholderText(text)

    def add_combo(self, label: str, items: Sequence[Tuple[str, str]],
                  changed_slot=None) -> QWidget:
        """items: [(display, data)]. Returns the combo for later reads."""
        from PySide6.QtWidgets import QComboBox
        combo = QComboBox()
        for display, data in items:
            combo.addItem(display, data)
        combo.currentIndexChanged.connect(self._on_changed)
        if changed_slot is not None:
            combo.currentIndexChanged.connect(changed_slot)
        self._fields.append((label, combo))
        # insert before Clear + count
        self.layout().insertWidget(len(self._fields) + 0, combo, 1)
        return combo

    def combo_value(self, index: int) -> str:
        combo = self._fields[index][1]
        return combo.currentData()

    def _on_changed(self, *_args) -> None:
        self._clear.setVisible(self.is_filtering())
        self.changed.emit()

    def is_filtering(self) -> bool:
        if self._search.text().strip():
            return True
        return any((combo.currentData() or "") for _label, combo in self._fields)

    def clear_filters(self) -> None:
        self._search.clear()
        for _label, combo in self._fields:
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._clear.setVisible(False)
        self.changed.emit()

    def set_result_count(self, shown: int, total: Optional[int] = None) -> None:
        if total is not None and shown != total:
            self._count.setText(f"{shown:,} / {total:,} results")
        else:
            self._count.setText(f"{shown:,} results")

    def focus_search(self) -> None:
        self._search.setFocus()


# ======================================================================
# Toast — transient success feedback
# ======================================================================

def show_toast(parent: QWidget, text: str, *, action_text: str = "",
               action: Optional[Callable] = None, seconds: int = 3) -> None:
    """Bottom-center transient confirmation (success feedback only).

    Errors must use Banner/ErrorPanel — never a toast that disappears.
    """
    window = parent.window()
    toast = QFrame(window)
    toast.setObjectName("Toast")
    layout = QHBoxLayout(toast)
    layout.setContentsMargins(theme.SP_16, theme.SP_8, theme.SP_16, theme.SP_8)
    layout.setSpacing(theme.SP_12)
    label = QLabel(text)
    layout.addWidget(label)
    if action_text and action:
        button = QPushButton(action_text)
        button.setCursor(Qt.PointingHandCursor)

        def run_and_close() -> None:
            action()
            toast.close()

        button.clicked.connect(run_and_close)
        layout.addWidget(button)
    window_min = min(window.width(), 720)
    toast.adjustSize()
    x = window.x() + (window.width() - toast.width()) // 2
    y = window.y() + window.height() - toast.height() - 48
    toast.move(max(window.x() + (window.width() - window_min) // 2, x), y)
    toast.show()
    toast.raise_()
    QTimer.singleShot(seconds * 1000, toast.close)


# ======================================================================
# PageHeader — title / purpose / one primary action
# ======================================================================

class PageHeader(QWidget):
    """Standard first row of every primary page.

    Page title (24/600) + one-line purpose; right side hosts exactly one
    Primary action plus optional secondary controls.
    """

    def __init__(self, title: str, purpose: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SP_12)
        text_col = QVBoxLayout()
        text_col.setSpacing(theme.SP_4)
        self._title = QLabel(title)
        self._title.setObjectName("PageTitle")
        self._purpose = QLabel(purpose)
        self._purpose.setObjectName("PagePurpose")
        text_col.addWidget(self._title)
        text_col.addWidget(self._purpose)
        layout.addLayout(text_col, 1)
        self._secondary = QHBoxLayout()
        self._secondary.setSpacing(theme.SP_8)
        layout.addLayout(self._secondary)

    def add_secondary(self, widget: QWidget) -> None:
        self._secondary.addWidget(widget)

    def add_primary(self, widget: QWidget) -> None:
        self._secondary.addWidget(widget)
