# -*- coding: utf-8 -*-
"""Navigation router + global search (Phase 4A #26/#27/#28).

Cross-page jumps go through Router.navigate_to(route, object_id, context);
pages register focus handlers so a jump selects the object, not just the
page. A session history stack powers Back (Alt+Left) so研究者 never lose
their research context after following Evidence → Run or Writing → Claim.

Global search (Ctrl+K) is deliberately light: documents, targets, evidence,
claims, writing sections, runs — never the full KWIC contents.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Page routes (the frozen primary navigation)
ROUTES = ["概览", "语料", "分析", "复核", "证据", "写作", "运行记录", "设置"]

# Object routes: object kind -> page route
OBJECT_ROUTE = {
    "document": "语料",
    "source": "语料",
    "target": "分析",
    "kwic": "分析",
    "collocate": "分析",
    "phrase": "分析",
    "group": "分析",
    "review_item": "复核",
    "evidence": "证据",
    "claim": "证据",
    "writing_section": "写作",
    "run": "运行记录",
    "comparison": "运行记录",
}


class Router:
    """Session navigation with history. Owned by MainWindow."""

    def __init__(self, window):
        self._window = window
        self._history: List[tuple] = []
        self._current: Optional[tuple] = None

    # ------------------------------------------------------------------

    def navigate_to(self, route: str, object_id: Optional[str] = None,
                    context: Optional[Dict[str, Any]] = None) -> None:
        """route: page route or object kind (mapped via OBJECT_ROUTE)."""
        page_route = OBJECT_ROUTE.get(route, route)
        if page_route not in ROUTES:
            return
        self._push_history()
        self._window.show_route(page_route)
        self._focus(page_route, object_id, context)
        self._current = (page_route, object_id, context or None)

    def navigate(self, key: str) -> None:
        """Legacy pages.navigate(key) — switches page only."""
        self.navigate_to(key)

    def back(self) -> bool:
        if not self._history:
            return False
        route, object_id, context = self._history.pop()
        self._window.show_route(route)
        self._focus(route, object_id, context)
        self._current = (route, object_id, context or None)
        return True

    def _focus(self, page_route: str, object_id: Optional[str],
               context: Optional[Dict[str, Any]]) -> None:
        """Context-only jumps (e.g. {'tab': 'health'}) also route focus."""
        if object_id is None and not context:
            return
        page = self._window._pages.get(page_route)
        focus = getattr(page, "focus_object", None)
        if focus is not None:
            focus(object_id, context or {})

    @property
    def can_go_back(self) -> bool:
        return bool(self._history)

    def _push_history(self) -> None:
        current = self._current or (self._window.current_route(), None, None)
        if self._history and self._history[-1] == current:
            return  # no duplicate entries for repeated navigation
        self._history.append(current)
        if len(self._history) > 50:
            self._history.pop(0)

    def notify_location(self, route: str, object_id: Optional[str] = None) -> None:
        """Pages call this when in-page navigation changes the location."""
        self._current = (route, object_id, None)


class GlobalSearch(QDialog):
    """Ctrl+K command/search palette over research objects."""

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.setWindowTitle("Global Search")
        self.resize(520, 440)
        self._window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("搜索 Documents / Targets / Evidence / Claims / Writing / Runs…")
        self._input.textChanged.connect(self._refresh)
        layout.addWidget(self._input)

        self._list = QListWidget()
        self._list.setObjectName("PaletteList")
        self._list.itemActivated.connect(self._activate)
        layout.addWidget(self._list, 1)

        hint = QLabel("Enter 打开 · Esc 关闭")
        hint.setProperty("class", "Muted")
        layout.addWidget(hint)

        QShortcut(QKeySequence(Qt.Key_Escape), self, self.reject)
        self._entries: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------

    def open_search(self) -> None:
        self._input.clear()
        self._refresh("")
        self._input.setFocus()
        self.show()
        self.raise_()

    def _refresh(self, query: str) -> None:
        self._entries = self._build_entries()
        needle = query.strip().lower()
        self._list.clear()
        shown = 0
        for entry in self._entries:
            hay = f"{entry['label']} {entry.get('detail', '')}".lower()
            if needle and needle not in hay:
                continue
            item = QListWidgetItem(f"{entry['kind']}  ·  {entry['label']}")
            if entry.get("detail"):
                item.setToolTip(entry["detail"])
            item.setData(Qt.UserRole, entry)
            self._list.addItem(item)
            shown += 1
            if shown >= 60:
                break
        if self._list.count():
            self._list.setCurrentRow(0)

    def _build_entries(self) -> List[Dict[str, Any]]:
        window = self._window
        store = window.store
        entries: List[Dict[str, Any]] = []
        if store is None:
            return entries

        for document_id in list(store.documents_df.get("document_id", []))[:500]:
            entries.append({"kind": "Document", "route": "document",
                            "object_id": str(document_id), "label": str(document_id)})
        for target in store.targets:
            entries.append({"kind": "Target", "route": "target",
                            "object_id": target, "label": target})
        evidence_store = getattr(window, "evidence_store", None)
        if evidence_store is not None:
            for record in evidence_store.evidence_records():
                entries.append({
                    "kind": "Evidence", "route": "evidence",
                    "object_id": record["evidence_id"],
                    "label": f"{record.get('target', '')} · {record.get('evidence_type', '')}"})
            for claim in evidence_store.claims():
                entries.append({"kind": "Claim", "route": "claim",
                                "object_id": claim["claim_id"], "label": claim.get("title", "")})
        writing_store = getattr(window, "writing_store", None)
        if writing_store is not None and writing_store.has_document:
            for section in writing_store.sections():
                entries.append({"kind": "Section", "route": "writing_section",
                                "object_id": section["section_id"],
                                "label": section.get("title", "")})
        from gui_next.execution.jobs import load_journal
        for entry_ in load_journal(store.root):
            entries.append({"kind": "Run", "route": "run",
                            "object_id": entry_.get("run_id", ""),
                            "label": f"{entry_.get('run_id', '')} · {entry_.get('status', '')}"})
        for row in store.runs_index():
            entries.append({"kind": "Run", "route": "run",
                            "object_id": row["run_id"], "label": row["run_id"]})
        return entries

    def _activate(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.UserRole) or {}
        self.accept()
        self._window.router.navigate_to(entry.get("route", ""),
                                        entry.get("object_id"))
