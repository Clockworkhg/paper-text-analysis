# -*- coding: utf-8 -*-
"""gui-next application shell (Phase 4A: Global App Shell).

Layout:
    top     Project Context Bar (project · published run · corpus health ·
            global search · execution status)
    left    Primary Navigation (research chain | Runs | Settings)
    center  Workspace (stacked pages)
    right   Context Inspector (collapsible, Ctrl+I)
    bottom  Status bar (transient messages only)

Global info lives here, once — pages never re-render project name, health
or run identity. Session state (inspector/sidebar visibility) persists via
QSettings for the lifetime of the installation.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
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

from gui_next import status, theme
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
from gui_next.pages import AnalysisPage, CorpusPage, OverviewPage, RunsPage, SettingsPage
from gui_next.review_workbench import SemanticReviewWorkbench
from gui_next.router import GlobalSearch, Router
from gui_next.widgets import show_toast

NAV_SECTIONS = [
    ("研究链", ["概览", "语料", "分析", "复核", "证据", "写作"]),
    ("基础设施", ["运行记录"]),
    ("应用", ["设置"]),
]
NAV_ITEMS = [route for _label, routes in NAV_SECTIONS for route in routes]


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
        hint.setObjectName("EmptyHint")
        hint.setAlignment(Qt.AlignCenter)
        button = QPushButton("打开项目目录…")
        button.setObjectName("Primary")
        button.setFixedWidth(180)
        button.clicked.connect(lambda: on_open(""))
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(theme.SP_16)
        layout.addWidget(button, 0, Qt.AlignCenter)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CADS Workbench")
        self.resize(1440, 900)
        self.store: Optional[ProjectStore] = None
        self.controller: Optional[AnalysisController] = None
        self.evidence_store: Optional[EvidenceStore] = None
        self.writing_store: Optional[WritingStore] = None
        self._pages: Dict[str, QWidget] = {}
        self._settings = QSettings("cads-workbench", "gui-next")
        self.router = Router(self)
        self._palette = GlobalSearch(self)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_context_bar())

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        outer.addWidget(self._splitter, 1)

        self._sidebar = self._build_sidebar()
        self._splitter.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._splitter.addWidget(self._stack)

        self.inspector = InspectorPanel()
        self._splitter.addWidget(self.inspector)
        self._splitter.setSizes([240, 860, 340])
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(2, False)

        self.statusBar().showMessage("未打开项目")

        self._empty = EmptyState(self._pick_project)
        self._stack.addWidget(self._empty)
        self._stack.setCurrentWidget(self._empty)

        self._install_global_shortcuts()

    # ------------------------------------------------------------------
    # context bar

    def _build_context_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("ContextBar")
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(theme.SP_16, theme.SP_8, theme.SP_16, theme.SP_8)
        layout.setSpacing(theme.SP_12)

        self._project_label = QLabel("未打开项目")
        self._project_label.setObjectName("ContextProject")
        layout.addWidget(self._project_label)

        self._run_chip = QPushButton("–")
        self._run_chip.setObjectName("ContextChipButton")
        self._run_chip.setCursor(Qt.PointingHandCursor)
        self._run_chip.setToolTip("当前已发布运行(published run) — 点击打开运行记录")
        self._run_chip.clicked.connect(
            lambda: self.router.navigate_to("运行记录"))
        self._run_chip.hide()
        layout.addWidget(self._run_chip)

        self._health_chip = QPushButton("–")
        self._health_chip.setObjectName("ContextChipButton")
        self._health_chip.setCursor(Qt.PointingHandCursor)
        self._health_chip.setToolTip("Corpus health — 点击查看语料卫生详情")
        self._health_chip.clicked.connect(
            lambda: self.router.navigate_to("语料", context={"tab": "health"}))
        self._health_chip.hide()
        layout.addWidget(self._health_chip)

        layout.addStretch(1)

        self._execution_chip = QLabel("")
        self._execution_chip.setObjectName("ContextChip")
        layout.addWidget(self._execution_chip)

        self._back_button = QPushButton("← Back")
        self._back_button.setObjectName("IconOnlyButton")
        self._back_button.setToolTip("返回上一个位置 (Alt+←)")
        self._back_button.clicked.connect(self._go_back)
        self._back_button.hide()
        layout.addWidget(self._back_button)

        search_button = QPushButton("Search…  ⌘K")
        search_button.setObjectName("IconOnlyButton")
        search_button.setToolTip("全局搜索 (Ctrl+K)")
        search_button.clicked.connect(self._palette.open_search)
        layout.addWidget(search_button)

        inspector_toggle = QPushButton("Inspector")
        inspector_toggle.setObjectName("IconOnlyButton")
        inspector_toggle.setToolTip("显示/隐藏右侧 Inspector (Ctrl+I)")
        inspector_toggle.setCheckable(True)
        inspector_toggle.setChecked(True)
        inspector_toggle.toggled.connect(self._toggle_inspector)
        self._inspector_toggle = inspector_toggle
        layout.addWidget(inspector_toggle)

        sidebar_toggle = QPushButton("Sidebar")
        sidebar_toggle.setObjectName("IconOnlyButton")
        sidebar_toggle.setToolTip("显示/隐藏左侧导航 (Ctrl+B)")
        sidebar_toggle.setCheckable(True)
        sidebar_toggle.setChecked(True)
        sidebar_toggle.toggled.connect(self._toggle_sidebar)
        self._sidebar_toggle = sidebar_toggle
        layout.addWidget(sidebar_toggle)
        return bar

    # ------------------------------------------------------------------
    # sidebar

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, theme.SP_16, 0, theme.SP_16)
        layout.setSpacing(theme.SP_8)

        brand = QLabel("  CADS WORKBENCH")
        brand.setObjectName("SidebarTitle")
        layout.addWidget(brand)

        self._nav = QListWidget()
        self._nav.setObjectName("Nav")
        self._nav_routes: List[Optional[str]] = []
        for section_label, routes in NAV_SECTIONS:
            caption = QListWidgetItem(f"  {section_label}")
            caption.setFlags(Qt.NoItemFlags)
            from PySide6.QtGui import QFont as _QFont
            caption.setFont(_QFont())
            self._nav.addItem(caption)
            self._nav_routes.append(None)
            for route in routes:
                QListWidgetItem(route, self._nav)
                self._nav_routes.append(route)
        self._nav.currentRowChanged.connect(self._on_nav)
        layout.addWidget(self._nav, 1)

        open_button = QPushButton("打开项目…")
        open_button.clicked.connect(self._pick_project)
        layout.addWidget(open_button, 0, Qt.AlignLeft | Qt.AlignAbsolute)
        return sidebar

    def _on_nav(self, row: int) -> None:
        route = self._nav_routes[row] if 0 <= row < len(self._nav_routes) else None
        if route is not None:
            self.show_route(route)

    # ------------------------------------------------------------------
    # global shortcuts + session toggles

    def _install_global_shortcuts(self) -> None:
        self._bind("Ctrl+K", self._palette.open_search)
        self._bind("Ctrl+I", lambda: self._inspector_toggle.toggle())
        self._bind("Ctrl+B", lambda: self._sidebar_toggle.toggle())
        self._bind("Alt+Left", self._go_back)
        self._bind("Ctrl+S", self._save_current_context)
        self._bind("Ctrl+F", self._focus_current_filter)

    def _bind(self, keys: str, handler: Callable) -> None:
        shortcut = QShortcut(QKeySequence(keys), self)
        shortcut.setContext(Qt.ApplicationShortcut)
        shortcut.activated.connect(handler)

    def _toggle_inspector(self, visible: bool) -> None:
        self.inspector.setVisible(visible)
        self._settings.setValue("inspector_visible", visible)

    def _toggle_sidebar(self, visible: bool) -> None:
        self._sidebar.setVisible(visible)
        self._settings.setValue("sidebar_visible", visible)

    def _go_back(self) -> None:
        if not self.router.back():
            self.statusBar().showMessage("没有更早的导航位置。", 3000)

    def _save_current_context(self) -> None:
        page = self._stack.currentWidget()
        saver = getattr(page, "save_context", None)
        if saver is not None and saver():
            show_toast(self, "已保存")

    def _focus_current_filter(self) -> None:
        page = self._stack.currentWidget()
        focuser = getattr(page, "focus_filter", None)
        if focuser is not None:
            focuser()
        else:
            self._palette.open_search()

    def _restore_session_state(self) -> None:
        inspector_visible = self._settings.value("inspector_visible", True, type=bool)
        sidebar_visible = self._settings.value("sidebar_visible", True, type=bool)
        self._inspector_toggle.setChecked(inspector_visible)
        self._sidebar_toggle.setChecked(sidebar_visible)

    # ------------------------------------------------------------------
    # routing

    def current_route(self) -> str:
        widget = self._stack.currentWidget()
        for route, page in self._pages.items():
            if page is widget:
                return route
        return ""

    def show_route(self, route: str) -> None:
        page = self._pages.get(route)
        if page is None:
            return
        self._stack.setCurrentWidget(page)
        if route in NAV_ITEMS:
            self._nav.blockSignals(True)
            self._nav.setCurrentRow(self._nav_routes.index(route))
            self._nav.blockSignals(False)
        self._back_button.setVisible(self.router.can_go_back)

    def _navigate(self, key: str) -> None:
        """Legacy in-app page switch (no history push)."""
        if key in self._pages:
            self.show_route(key)

    # ------------------------------------------------------------------
    # project lifecycle

    def _pick_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择项目目录")
        if path:
            self.open_project(path)

    def open_project(self, project_dir: str) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage("正在打开项目…")
        QApplication.processEvents()
        try:
            self._open_project_impl(project_dir)
        finally:
            QApplication.restoreOverrideCursor()

    def _open_project_impl(self, project_dir: str) -> None:
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
        self.evidence_store = EvidenceStore(store.root)
        resolver = GenerationResolver(store.root)

        # Writing workspace (independent write boundary at 09_writing/).
        # Document creation is lazy: opening a project must not write.
        self.writing_store = WritingStore(store.root)

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
                router=self.router,
            ),
            "语料": CorpusPage(
                store, self.inspector, source_store=source_review, health=health,
                router=self.router,
            ),
            "分析": AnalysisPage(store, self.inspector, health=health,
                                 evidence_store=self.evidence_store,
                                 router=self.router),
            "复核": SemanticReviewWorkbench(semantic_review, self.inspector),
            "证据": EvidencePage(self.evidence_store, resolver,
                                 lambda: store.published_analysis() if self.store else {},
                                 self.inspector, self._navigate),
            "写作": WritingPage(self.writing_store, self.evidence_store, resolver,
                                lambda: store.published_analysis() if self.store else {},
                                self.inspector, self._navigate, router=self.router),
            "运行记录": RunsPage(store, self.inspector, evidence_store=self.evidence_store,
                                 router=self.router),
            "设置": SettingsPage(store),
        }
        for key in NAV_ITEMS:
            self._stack.addWidget(self._pages[key])
        self.inspector.show_empty()
        self.router.notify_location("概览")
        self.show_route("概览")
        self.project_dir = str(store.root)
        self._health = health

        # Context bar: global facts live here, once.
        self._project_label.setText(store.name)
        published = store.published_analysis()
        if published.get("published_run_id"):
            self._run_chip.setText(f"Published run #{published['published_run_id'][-6:]}")
            self._run_chip.show()
        else:
            self._run_chip.hide()
        glyph, text, _role = status.health(health[0])
        self._health_chip.setText(f"Corpus {glyph} {text}")
        self._health_chip.show()
        self._restore_session_state()

        # Analysis execution controller (Phase 2B). Never recreate while a run
        # is active — the running subprocess belongs to this window.
        if self.controller is not None and self.controller.state in (
                RunState.PREPARING, RunState.RUNNING, RunState.CANCELLING):
            self._wire_run_panel()
            self._set_execution_busy(self.controller.run_id)
            return
        if self.controller is not None:
            self.controller.deleteLater()
        self.controller = AnalysisController(store.root)
        self.controller.state_changed.connect(self._on_run_state)
        self.controller.log_line.connect(self._on_run_log)
        self.controller.finished.connect(self._on_run_finished)
        self._wire_run_panel()
        self._set_execution_idle()

        self.statusBar().showMessage(
            f"{store.name} · {len(store.documents_df)} documents · run #{store.run_id[-6:] or '–'}"
            f" · corpus health {health[0].value}"
        )

    def _set_execution_busy(self, run_id: str) -> None:
        self._execution_chip.setText(f"● 执行中 {run_id}")
        self._execution_chip.setStyleSheet(
            f"color: {theme.PRIMARY}; background: transparent; font-weight: 600;")

    def _set_execution_idle(self) -> None:
        self._execution_chip.setText("○ 空闲")
        self._execution_chip.setStyleSheet(
            f"color: {theme.MUTED}; background: transparent;")

    def _wire_run_panel(self) -> None:
        page = self._pages.get("分析")
        if page is None or self.controller is None:
            return
        page.run_panel.cancel_requested.connect(self.controller.cancel)
        page._run_config_view.start_requested.connect(self._start_analysis)
        page._run_config_view.sanity_requested.connect(self._start_sanity)
        page._run_config_view.back_requested.connect(page.show_normal_view)

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
        spec = run_jobs.build_spec(kind="analyze", project_dir=str(self.store.root), **params)
        if self.controller.start(spec, run_id):
            page = self._pages["分析"]
            summary = (f"targets: {params.get('targets', '')} · group_by: {params.get('group_by')} · "
                       f"MI: {params.get('mi_threshold')} · sanity: {'on' if params.get('sanity') else 'SKIPPED'}")
            page.run_panel.set_run(run_id, summary, str(self.store.root / "runs" / f"work_{run_id}"))
            page.run_panel.begin_elapsed()
            page.show_run_panel()
            self._set_execution_busy(run_id)

    def _start_sanity(self) -> None:
        if self.controller is None or self.controller.state in (
                RunState.PREPARING, RunState.RUNNING, RunState.CANCELLING):
            return
        run_id = "san_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        spec = run_jobs.build_spec(kind="sanity", project_dir=str(self.store.root))
        if self.controller.start(spec, run_id):
            page = self._pages["分析"]
            page.run_panel.set_run(run_id, "corpus sanity check", "")
            page.run_panel.begin_elapsed()
            page.show_run_panel()
            self._set_execution_busy(run_id)

    def _on_run_state(self, state_value: str, message: str) -> None:
        state = RunState(state_value)
        page = self._pages.get("分析")
        if page is not None:
            page.run_panel.set_state(state_value, message)
        active = state in (RunState.PREPARING, RunState.RUNNING, RunState.CANCELLING)
        self._set_review_lock(active)
        if active and self.controller is not None:
            self._set_execution_busy(self.controller.run_id)

    def _on_run_log(self, line: str) -> None:
        page = self._pages.get("分析")
        if page is not None:
            page.run_panel.append_log(line)

    def _on_run_finished(self, state_value: str) -> None:
        self._set_review_lock(False)
        self._set_execution_idle()
        if state_value == RunState.SUCCEEDED.value and self.project_dir:
            # Refresh Analysis/Overview/Runs against the published outputs.
            # Corpus Health keeps its factual state (recomputed on reload).
            self.open_project(self.project_dir)
            self._log_status("分析完成:Analysis/Overview/Runs 已刷新。")
            show_toast(self, "分析运行完成,项目视图已刷新。")
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
            show_toast(self, "分析运行失败 — 详情见 Analysis 页运行面板。")


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
