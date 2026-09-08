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
from gui_next.data.evidence_store import EvidenceStore
from gui_next.data.generations import GenerationResolver
from gui_next.data.health import corpus_health
from gui_next.data.review_store import SemanticReviewStore, SourceCountryReviewStore
from gui_next.data.store import ProjectStore
from gui_next.data.writing_store import WritingStore
from gui_next.evidence_page import EvidencePage
from gui_next.writing_page import WritingPage
from gui_next.execution import jobs as run_jobs
from gui_next.execution.controller import AnalysisController
from gui_next.execution.events import RunState
from gui_next.inspector import InspectorPanel
from gui_next.pages import AnalysisPage, CorpusPage, OverviewPage, RunsPage
from gui_next.review_workbench import SemanticReviewWorkbench

NAV_ITEMS = ["概览", "语料", "分析", "复核", "证据", "写作", "运行记录"]


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
        self.controller: Optional[AnalysisController] = None
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

        # Crash recovery: publication transactions first (rollback to the
        # previous generation), then run-journal states.
        from gui_next.execution.publication import recover_publications, recovery_required

        for record in recover_publications(store.root):
            self._log_status(f"发布事务已回滚恢复: {record.get('run_id', '')} ({record.get('state')})")
        recovered = run_jobs.recover_interrupted_runs(store.root)
        for entry in recovered:
            if entry.get("status") == "PUBLISH_FAILED":
                self._log_status(f"运行 {entry.get('run_id', '')} 的发布被会话中断,已回滚并标记 PUBLISH_FAILED。")
            else:
                self._log_status(f"上次会话的运行 {entry.get('run_id', '')} 未完成,已标记为 INTERRUPTED(现场保留)。")
        pending_recovery = recovery_required(store.root)
        if pending_recovery:
            self._log_status(
                f"⚠ 存在 RECOVERY_REQUIRED 发布事务({len(pending_recovery)} 个),新的分析发布已被禁止,直至完整性解决。")

        # Review stores (the only review-write components in gui-next).
        source_review = SourceCountryReviewStore(store.root, documents_df=store.documents_df)
        semantic_review = SemanticReviewStore(
            store.root, kwic_df=store.kwic_df, documents_df=store.documents_df,
        )

        # Evidence Trail: independent write boundary + published-generation
        # resolver (historical artifacts, never the live project root).
        evidence_store = EvidenceStore(store.root)
        resolver = GenerationResolver(store.root)

        # Writing workspace (independent write boundary at 09_writing/).
        writing_store = WritingStore(store.root)

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
            "分析": AnalysisPage(store, self.inspector, health=health,
                                 evidence_store=evidence_store),
            "复核": SemanticReviewWorkbench(semantic_review, self.inspector),
            "证据": EvidencePage(evidence_store, resolver,
                                 lambda: self.store.published_analysis() if self.store else {},
                                 self.inspector, self._navigate),
            "写作": WritingPage(writing_store, evidence_store, resolver,
                                lambda: self.store.published_analysis() if self.store else {},
                                self.inspector, self._navigate),
            "运行记录": RunsPage(store, self.inspector, evidence_store=evidence_store),
        }
        for key in NAV_ITEMS:
            self._stack.addWidget(self._pages[key])
        self.inspector.show_empty()
        self._nav.setCurrentRow(0)
        self.project_dir = str(store.root)

        # Analysis execution controller (Phase 2B). Never recreate while a run
        # is active — the running subprocess belongs to this window.
        if self.controller is not None and self.controller.state in (
                RunState.PREPARING, RunState.RUNNING, RunState.CANCELLING):
            self._wire_run_panel()
            self.statusBar().showMessage(
                f"{store.name} · 分析运行中({self.controller.run_id})")
            return
        if self.controller is not None:
            self.controller.deleteLater()
        self.controller = AnalysisController(store.root)
        self.controller.state_changed.connect(self._on_run_state)
        self.controller.log_line.connect(self._on_run_log)
        self.controller.finished.connect(self._on_run_finished)
        self._wire_run_panel()

        self.statusBar().showMessage(
            f"{store.name} · {len(store.documents_df)} documents · run #{store.run_id[-6:] or '–'}"
            f" · corpus health {health[0].value}"
        )

    def _wire_run_panel(self) -> None:
        page = self._pages.get("分析")
        if page is None or self.controller is None:
            return
        page.run_panel.cancel_requested.connect(self.controller.cancel)
        page._run_config_view.start_requested.connect(self._start_analysis)
        page._run_config_view.sanity_requested.connect(self._start_sanity)

    # ------------------------------------------------------------------
    # analysis execution (Phase 2B)

    def _log_status(self, message: str) -> None:
        if hasattr(self, "statusBar"):
            try:
                self.statusBar().showMessage(message)
            except RuntimeError:
                pass

    def _review_pages(self):
        workbench = self._pages.get("复核")
        corpus = self._pages.get("语料")
        return workbench, getattr(corpus, "source_panel", None)

    def _set_review_lock(self, locked: bool) -> None:
        workbench, panel = self._review_pages()
        if workbench is not None:
            workbench.set_locked(locked)
        if panel is not None:
            panel.set_locked(locked)

    def _start_analysis(self, params: dict) -> None:
        if self.controller is None or self.store is None:
            return
        writer = self.controller.analysis_writer_active()
        if writer:
            self.inspector.show_empty(
                "该项目已有正在运行的分析任务(另一实例或窗口),已拒绝启动新的分析。\n"
                f"writer: {writer.get('run_id', '?')}")
            return
        run_id = "gui_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        spec = jobs.build_spec(kind="analyze", project_dir=str(self.root), **params)
        if self.controller.start(spec, run_id):
            page = self._pages["分析"]
            summary = (f"targets: {params.get('targets', '')} · group_by: {params.get('group_by')} · "
                       f"MI: {params.get('mi_threshold')} · sanity: {'on' if params.get('sanity') else 'SKIPPED'}")
            page.run_panel.set_run(run_id, summary, str(self.root / "runs" / f"work_{run_id}"))
            page.run_panel.begin_elapsed()
            page.show_run_panel()

    def _start_sanity(self) -> None:
        if self.controller is None or self.controller.state in (
                RunState.PREPARING, RunState.RUNNING, RunState.CANCELLING):
            return
        run_id = "san_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        spec = jobs.build_spec(kind="sanity", project_dir=str(self.root))
        if self.controller.start(spec, run_id):
            page = self._pages["分析"]
            page.run_panel.set_run(run_id, "corpus sanity check", "")
            page.run_panel.begin_elapsed()
            page.show_run_panel()

    def _on_run_state(self, state_value: str, message: str) -> None:
        state = RunState(state_value)
        page = self._pages.get("分析")
        if page is not None:
            page.run_panel.set_state(state_value, message)
        active = state in (RunState.PREPARING, RunState.RUNNING, RunState.CANCELLING)
        self._set_review_lock(active)

    def _on_run_log(self, line: str) -> None:
        page = self._pages.get("分析")
        if page is not None:
            page.run_panel.append_log(line)

    def _on_run_finished(self, state_value: str) -> None:
        self._set_review_lock(False)
        if state_value == RunState.SUCCEEDED.value and self.project_dir:
            # Refresh Analysis/Overview/Runs against the published outputs.
            # Corpus Health keeps its factual state (recomputed on reload).
            self.open_project(self.project_dir)
            self._log_status("分析完成:Analysis/Overview/Runs 已刷新。")
        elif state_value == RunState.FAILED.value:
            page = self._pages.get("分析")
            controller = self.controller
            if page is not None and controller is not None and controller.last_error:
                page.run_panel.error_detail = (
                    f"failed step/stage: {controller.state.value}\n"
                    f"exception: {controller.last_error.get('type', '')}\n"
                    f"message: {controller.last_error.get('message', '')}\n"
                    f"work dir: {controller.work_dir}\n"
                    f"params: {controller.params}\n\n"
                    f"traceback (tail):\n{controller.last_error.get('traceback_tail', '')}"
                )
            self._log_status("分析失败:详情见 分析 页(Copy diagnostics / View log)。")

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
