# -*- coding: utf-8 -*-
"""gui-next application shell: sidebar navigation + pages + Context Inspector.

Layout: 240px sidebar | main canvas | 340px inspector, plus a status bar
answering "how big is the corpus, which run, is it healthy".
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.data.health import corpus_health
from gui_next.data.review_store import SemanticReviewStore, SourceCountryReviewStore
from gui_next.data.store import ProjectStore
from gui_next.inspector import InspectorPanel
from gui_next.pages import AnalysisPage, CorpusPage, OverviewPage, RunsPage
from gui_next.review_workbench import SemanticReviewWorkbench

NAV_ITEMS = ["概览", "语料", "分析", "复核", "运行记录"]


class EmptyState(QWidget):
    """Shown when no project is open."""

    def __init__(self, on_open: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        title = QLabel("CADS Workbench — 研究证据工作台")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel("打开一个项目目录(project.json 所在目录)开始研究。")
        hint.setObjectName("Muted")
        hint.setAlignment(Qt.AlignCenter)
        button = QPushButton("打开项目目录…")
        button.setObjectName("Primary")
        button.setFixedWidth(180)
        button.clicked.connect(lambda: on_open(""))
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(16)
        layout.addWidget(button, 0, Qt.AlignCenter)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CADS Workbench")
        self.resize(1440, 900)
        self.store: Optional[ProjectStore] = None
        self._pages: Dict[str, QWidget] = {}

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(self._splitter, 1)

        self._sidebar = self._build_sidebar()
        self._splitter.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._splitter.addWidget(self._stack)

        self.inspector = InspectorPanel()
        self._splitter.addWidget(self.inspector)
        self._splitter.setSizes([240, 860, 340])
        self._splitter.setCollapsible(0, False)

        self.statusBar().showMessage("未打开项目")

        self._empty = EmptyState(self._pick_project)
        self._stack.addWidget(self._empty)
        self._stack.setCurrentWidget(self._empty)

    # ------------------------------------------------------------------
    # sidebar

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(8)

        brand = QLabel("  CADS WORKBENCH")
        brand.setObjectName("SidebarTitle")
        layout.addWidget(brand)

        self._nav = QListWidget()
        self._nav.setObjectName("Nav")
        self._nav_group = QButtonGroup(self)
        for item in NAV_ITEMS:
            QListWidgetItem(item, self._nav)
        self._nav.currentRowChanged.connect(self._on_nav)
        layout.addWidget(self._nav, 1)

        open_button = QPushButton("打开项目…")
        open_button.clicked.connect(self._pick_project)
        layout.addWidget(open_button, 0, Qt.AlignLeft | Qt.AlignAbsolute)
        margin = QHBoxLayout()
        margin.setContentsMargins(12, 0, 12, 0)
        return sidebar

    def _on_nav(self, row: int) -> None:
        key = NAV_ITEMS[row] if 0 <= row < len(NAV_ITEMS) else ""
        page = self._pages.get(key)
        if page is not None:
            self._stack.setCurrentWidget(page)

    # ------------------------------------------------------------------
    # project lifecycle

    def _pick_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择项目目录")
        if path:
            self.open_project(path)

    def open_project(self, project_dir: str) -> None:
        store = ProjectStore(project_dir)
        if not store.is_project:
            self.statusBar().showMessage(f"未找到 project.json:{project_dir}")
            return
        self.store = store

        # Review stores (the only write-enabled components in gui-next).
        source_review = SourceCountryReviewStore(store.root, documents_df=store.documents_df)
        semantic_review = SemanticReviewStore(
            store.root, kwic_df=store.kwic_df, documents_df=store.documents_df,
        )

        # Corpus health state machine (read-only fingerprint computation).
        from shared.corpus_sanity import corpus_fingerprint as _fingerprint
        try:
            fingerprint = _fingerprint(store.root / "corpus")
        except Exception:
            fingerprint = None
        health = corpus_health(store.root, store.sanity_report, fingerprint)

        # Rebuild pages for this project.
        for existing in list(self._pages.values()):
            self._stack.removeWidget(existing)
            existing.deleteLater()
        self._pages = {
            "概览": OverviewPage(
                store, self.inspector, self._navigate,
                health=health, source_store=source_review, semantic_store=semantic_review,
            ),
            "语料": CorpusPage(
                store, self.inspector, source_store=source_review, health=health,
            ),
            "分析": AnalysisPage(store, self.inspector),
            "复核": SemanticReviewWorkbench(semantic_review, self.inspector),
            "运行记录": RunsPage(store, self.inspector),
        }
        for key in NAV_ITEMS:
            self._stack.addWidget(self._pages[key])
        self.inspector.show_empty()
        self._nav.setCurrentRow(0)

        self.statusBar().showMessage(
            f"{store.name} · {len(store.documents_df)} documents · run #{store.run_id[-6:] or '–'}"
            f" · corpus health {health[0].value}"
        )

    def _navigate(self, key: str) -> None:
        if key in self._pages:
            self._nav.setCurrentRow(NAV_ITEMS.index(key))


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    app = QApplication(args)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(theme.build_qss())

    window = MainWindow()
    project = args[0] if args else ""
    if project and (Path(project) / "project.json").exists():
        window.open_project(project)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
