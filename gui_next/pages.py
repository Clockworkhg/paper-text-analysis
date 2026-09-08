# -*- coding: utf-8 -*-
"""Main pages of the research workbench: Overview / Corpus / Analysis / Review / Runs.

Pages are read-only in Phase 1: they render existing project outputs and
delegate all detail display to the shared InspectorPanel.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.data.health import HealthState
from gui_next.data.review_store import SemanticReviewStore, SourceCountryReviewStore
from gui_next.data.store import ProjectStore
from gui_next.models import DataFrameModel
from gui_next.source_review_panel import SourceReviewPanel

STATE_COLORS = {"ok": theme.SUCCESS, "warn": theme.WARNING, "muted": theme.MUTED, "error": theme.ERROR}
HEALTH_COLORS = {
    HealthState.PASS: theme.SUCCESS,
    HealthState.WARNING: theme.WARNING,
    HealthState.STALE: theme.WARNING,
    HealthState.BLOCKED: theme.ERROR,
    HealthState.UNKNOWN: theme.MUTED,
}


def _table(df: pd.DataFrame, *, max_height: int = 0) -> QTableView:
    view = QTableView()
    model = DataFrameModel(df, view)
    view.setModel(model)
    view.setAlternatingRowColors(False)
    view.verticalHeader().setVisible(False)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    view.horizontalHeader().setStretchLastSection(True)
    view.setSelectionBehavior(QTableView.SelectRows)
    view.setEditTriggers(QTableView.NoEditTriggers)
    view.setSortingEnabled(True)
    view.setWordWrap(False)
    return view


def _card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)
    if title:
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
    return frame, layout


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


# ======================================================================
# Overview
# ======================================================================

class OverviewPage(QWidget):
    """The research home page: what is this study, where is it, what's wrong."""

    def __init__(self, store: ProjectStore, inspector, navigate, *,
                 health=None, source_store=None, semantic_store=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector
        self.navigate = navigate  # callable(page_key) for cross-page jumps
        self.health = health  # (HealthState, detail) tuple
        self.source_store = source_store
        self.semantic_store = semantic_store

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel(store.name)
        title.setObjectName("PageTitle")
        root.addWidget(title)
        subtitle = QLabel(self.store.manifest.get("corpus_type", "") or "CADS 研究项目")
        subtitle.setObjectName("Muted")
        root.addWidget(subtitle)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        for chip in store.stat_chips():
            frame = QFrame()
            frame.setObjectName("Card")
            box = QVBoxLayout(frame)
            box.setContentsMargins(16, 10, 16, 10)
            box.setSpacing(0)
            value = QLabel(chip["value"])
            value.setObjectName("StatValue")
            label = QLabel(chip["label"])
            label.setObjectName("StatLabel")
            box.addWidget(value)
            box.addWidget(label)
            chips_row.addWidget(frame, 1)
        root.addLayout(chips_row)

        self._callout = QFrame()
        self._callout_layout = QVBoxLayout(self._callout)
        self._callout_layout.setContentsMargins(16, 12, 16, 12)
        self._callout_layout.setSpacing(4)
        root.addWidget(self._callout)
        self._build_callout()

        status_card, status_layout = _card("研究流程")
        country_pending, country_total = self._country_pending()
        for row in store.pipeline_status(
            health=self.health,
            source_progress=self.source_store.progress() if self.source_store else None,
            country_pending=country_pending,
            country_total=country_total,
            semantic_progress=self.semantic_store.progress() if self.semantic_store else None,
        ):
            line = QHBoxLayout()
            line.setSpacing(12)
            stage = QLabel(row["stage"])
            stage.setFixedWidth(130)
            state = QLabel(str(row["state"]))
            state.setFixedWidth(80)
            detail = QLabel(str(row["detail"]))
            detail.setObjectName("Muted")
            detail.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
            line.addWidget(stage)
            line.addWidget(state)
            line.addWidget(detail, 1)
            status_layout.addLayout(line)
        status_layout.addStretch(1)
        root.addWidget(status_card, 1)

    def _country_pending(self) -> tuple[int, int]:
        """(pending, total) country suggestions without a decision."""
        if self.source_store is None:
            return 0, 0
        pending = total = 0
        for item in self.source_store.items:
            if not str(item.get("suggested_country") or "").strip():
                continue
            total += 1
            if item["source"] not in self.source_store.decisions:
                pending += 1
        return pending, total

    def _build_callout(self) -> None:
        while self._callout_layout.count():
            item = self._callout_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        state = self.health[0] if self.health else HealthState.UNKNOWN
        detail = self.health[1] if self.health else ""
        if state is HealthState.BLOCKED:
            self._callout.setObjectName("CalloutBlocked")
            heading = QLabel("Analysis blocked — corpus sanitation failed")
            heading.setStyleSheet(f"color: {theme.ERROR}; background: transparent; font-weight: 600;")
            body = QLabel(detail)
            body.setWordWrap(True)
            body.setStyleSheet("background: transparent;")
            action = QLabel("→ 前往 语料 → Health 查看详情;用原始 DOCX/干净正文重新导入后重跑分析。")
            action.setStyleSheet("background: transparent;")
            for widget in (heading, body, action):
                self._callout_layout.addWidget(widget)
            self._callout.setVisible(True)
        elif state is HealthState.STALE:
            self._callout.setObjectName("Callout")
            heading = QLabel("Corpus health: STALE — 卫生检查结果已过期")
            heading.setStyleSheet(f"color: {theme.WARNING}; background: transparent; font-weight: 600;")
            body = QLabel(f"{detail}。请重新运行 project sanity,再继续分析或复核。")
            body.setWordWrap(True)
            body.setStyleSheet("background: transparent;")
            self._callout_layout.addWidget(heading)
            self._callout_layout.addWidget(body)
            self._callout.setVisible(True)
        elif not self.store.has_analysis():
            self._callout.setObjectName("Callout")
            heading = QLabel("下一步")
            heading.setObjectName("CalloutTitle")
            heading.setStyleSheet(f"color: {theme.WARNING}; background: transparent; font-weight: 600;")
            body = QLabel("语料已导入但尚未运行分析(确保卫生检查通过后:project analyze --group-by institution)。")
            body.setWordWrap(True)
            body.setStyleSheet("background: transparent;")
            self._callout_layout.addWidget(heading)
            self._callout_layout.addWidget(body)
            self._callout.setVisible(True)
        else:
            self._callout.setVisible(False)


# ======================================================================
# Corpus
# ======================================================================

class CorpusPage(QWidget):
    """Documents / Sources / Health — what the data is and whether it is clean."""

    def __init__(self, store: ProjectStore, inspector, *, source_store=None,
                 health=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector
        self.source_store = source_store
        self.health = health

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)
        title = QLabel("语料")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_documents()
        self._build_sources()
        self._build_health()

    def _build_documents(self) -> None:
        docs = self.store.documents_df
        columns = [
            col for col in (
                "document_id", "title", "source_normalized", "country",
                "date", "word_count_approx", "target_hits_total",
            ) if col in docs.columns
        ]
        view = _table(docs[columns] if columns else docs)
        view.doubleClicked.connect(
            lambda index: self.inspector.show_document(view.model().row(index))
        )
        self.tabs.addTab(self._wrap(view, "点击行查看文档详情"), "Documents")

    def _build_sources(self) -> None:
        sources = self._source_rows()
        view = _table(sources)
        header = view.horizontalHeader()
        for column, name in enumerate(sources.columns):
            if name in ("original", "evidence"):
                header.setSectionHidden(column, True)

        self.source_panel = SourceReviewPanel(self.source_store, self.inspector) \
            if self.source_store is not None else None

        from PySide6.QtWidgets import QSplitter
        from PySide6.QtCore import Qt as QtConst
        splitter = QSplitter(QtConst.Horizontal)
        splitter.addWidget(self._wrap(view, "来源清单;选中行在右侧复核(不修改原始语料)"))
        if self.source_panel is not None:
            splitter.addWidget(self.source_panel)
            splitter.setSizes([560, 380])
            view.clicked.connect(self._on_source_selected)
            self.source_panel.refresh()
        self.tabs.addTab(splitter, "Sources")

    def _source_rows(self) -> pd.DataFrame:
        """Source list: merged_sources.xlsx when present, registry fallback."""
        if self.source_store is not None and self.source_store.items:
            rows = []
            for item in self.source_store.items:
                decision = self.source_store.decisions.get(item["source"], {})
                rows.append({
                    "source": item["source"],
                    "original": item.get("original", ""),
                    "documents": item.get("documents", ""),
                    "country": item.get("country", ""),
                    "suggested": item.get("suggested_country", ""),
                    "confidence": item.get("confidence"),
                    "decision": decision.get("decision", ""),
                    "evidence": " | ".join(item.get("evidence", [])),
                })
            return pd.DataFrame(rows)
        return self.store.sources_df

    def _on_source_selected(self, index) -> None:
        if self.source_panel is not None:
            self.source_panel.set_index(index.row())

    def _build_health(self) -> None:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        from gui_next.data.health import extract_corpus_report

        report = extract_corpus_report(self.store.sanity_report) if self.store.sanity_report else {}
        state = self.health[0] if self.health else HealthState.UNKNOWN
        detail = self.health[1] if self.health else "未评估"
        heading = QLabel(f"Corpus health: {state.value}")
        heading.setStyleSheet(f"color: {HEALTH_COLORS.get(state, theme.MUTED)}; font-weight: 600; font-size: 15px;")
        layout.addWidget(heading)
        layout.addWidget(QLabel(detail))

        if report:
            for kind, rows in (("失败", report.get("failures", {})), ("警告", report.get("warnings", {}))):
                for name, info in rows.items():
                    count = info.get("count", info.get("groups", info.get("total", 0)))
                    if not count:
                        continue
                    examples = "; ".join(info.get("examples", [])[:2])
                    text = f"{kind} · {name}: {count}"
                    if examples:
                        text += f" — 例: {examples}"
                    layout.addWidget(QLabel(text))
            checked = QLabel(f"检查时间:{report.get('checked_at', '–')}")
            checked.setObjectName("Muted")
            checked.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
            layout.addWidget(checked)
        else:
            layout.addWidget(_muted("运行:python research_tool.py project sanity -p <项目目录>"))
        layout.addStretch(1)
        self.tabs.addTab(frame, "Health")

    @staticmethod
    def _wrap(widget: QWidget, hint: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(_muted(hint))
        layout.addWidget(widget, 1)
        return container


# ======================================================================
# Analysis
# ======================================================================

class AnalysisPage(QWidget):
    """Target-term centered analysis: term → concordance → collocates → groups."""

    METHOD_NOTE = "ⓘ MI / G² 用于发现和排序候选模式,不自动构成话语解释结论。"

    def __init__(self, store: ProjectStore, inspector, *, health=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector
        self.health = health
        self._collocate_filter = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("分析")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._new_run_button = QPushButton("＋ New Analysis Run")
        self._new_run_button.setObjectName("Primary")
        header.addWidget(self._new_run_button)
        root.addLayout(header)

        # Stacked: normal analysis view (0) / New Analysis Run config (1)
        from PySide6.QtWidgets import QStackedWidget
        self._view_stack = QStackedWidget()
        root.addWidget(self._view_stack, 1)

        normal = QWidget()
        normal_v = QVBoxLayout(normal)
        normal_v.setContentsMargins(0, 0, 0, 0)
        normal_v.setSpacing(12)
        body = QHBoxLayout()
        body.setSpacing(12)

        # Left: target terms with hit counts
        targets_card, targets_layout = _card("目标词")
        self._target_list = QListWidget()
        self._target_list.setObjectName("Nav")
        kwic = store.kwic_df
        counts = kwic["Target"].value_counts() if not kwic.empty and "Target" in kwic.columns else pd.Series(dtype=int)
        for target in store.targets:
            count = int(counts.get(target, 0))
            QListWidgetItem(f"{target}  ({count:,})", self._target_list)
        targets_layout.addWidget(self._target_list, 1)
        body.addWidget(targets_card, 0)

        # Right: tabs
        self.tabs = QTabWidget()
        body.addWidget(self.tabs, 1)

        self._kwic_model = DataFrameModel(pd.DataFrame(), self)
        self._kwic_view = QTableView()
        self._setup_table(self._kwic_view, self._kwic_model)
        self._kwic_view.doubleClicked.connect(
            lambda index: self.inspector.show_kwic(self._kwic_model.row(index))
        )
        self._kwic_search = QLineEdit()
        self._kwic_search.setPlaceholderText("在语境中筛选(来源/词形包含…)")
        self._kwic_search.textChanged.connect(self._apply_kwic_filter)
        concordance = self._page_wrap(self._kwic_search, self._kwic_view)
        self.tabs.addTab(concordance, "Concordance")

        self._collocate_model = DataFrameModel(pd.DataFrame(), self)
        self._collocate_view = QTableView()
        self._setup_table(self._collocate_view, self._collocate_model)
        self._collocate_view.doubleClicked.connect(
            lambda index: self.inspector.show_collocate(self._current_target, self._collocate_model.row(index))
        )
        self.tabs.addTab(self._page_wrap(None, self._collocate_view), "Collocates")

        self._group_model = DataFrameModel(store.group_df, self)
        self._group_view = QTableView()
        self._setup_table(self._group_view, self._group_model)
        self.tabs.addTab(self._page_wrap(None, self._group_view), "Groups")

        note = QLabel(self.METHOD_NOTE)
        note.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        body.addWidget(targets_card, 0)
        body.addWidget(self.tabs, 1)
        normal_v.addLayout(body)
        normal_v.addWidget(note)
        self._view_stack.addWidget(normal)

        # Run lifecycle panel (Phase 2B)
        from gui_next.analysis_run import RunPanel
        self.run_panel = RunPanel()
        self.run_panel.setVisible(False)
        self._view_stack.addWidget(self.run_panel)

        # New Analysis Run config view (Phase 2B)
        from gui_next.analysis_run import RunConfigView
        self._run_config_view = RunConfigView(store, health)
        self._view_stack.addWidget(self._run_config_view)

        self._new_run_button.clicked.connect(self._show_run_config)

        self._current_target = ""
        if store.targets:
            self._target_list.setCurrentRow(0)
            self._target_list.currentRowChanged.connect(self._on_target_changed)
            self._on_target_changed(0)

    def _show_run_config(self) -> None:
        self._view_stack.setCurrentWidget(self._run_config_view)

    def show_run_panel(self) -> None:
        self._view_stack.setCurrentWidget(self.run_panel)

    def show_normal_view(self) -> None:
        self._view_stack.setCurrentIndex(0)

    def _setup_table(self, view: QTableView, model: DataFrameModel) -> None:
        view.setModel(model)
        view.setAlternatingRowColors(False)
        view.verticalHeader().setVisible(False)
        view.horizontalHeader().setStretchLastSection(True)
        view.setSelectionBehavior(QTableView.SelectRows)
        view.setEditTriggers(QTableView.NoEditTriggers)
        view.setSortingEnabled(True)
        view.setWordWrap(False)

    @staticmethod
    def _page_wrap(above: Optional[QWidget], main: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        if above is not None:
            layout.addWidget(above)
        layout.addWidget(main, 1)
        return container

    def _on_target_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.store.targets):
            return
        self._current_target = self.store.targets[row]
        self._apply_kwic_filter()
        collocates = self.store.collocates_df
        if not collocates.empty and "Target" in collocates.columns:
            subset = collocates[collocates["Target"] == self._current_target]
            subset = subset.drop(columns=["Target"], errors="ignore")
            self._collocate_model.set_dataframe(subset.reset_index(drop=True))

    def _apply_kwic_filter(self) -> None:
        kwic = self.store.kwic_df
        if kwic.empty:
            self._kwic_model.set_dataframe(kwic)
            return
        mask = pd.Series(True, index=kwic.index)
        if "Target" in kwic.columns:
            mask &= kwic["Target"] == self._current_target
        needle = self._kwic_search.text().strip().lower()
        if needle:
            context_mask = pd.Series(False, index=kwic.index)
            for col in ("Full_Context", "Source", "Source_Normalized", "Group"):
                if col in kwic.columns:
                    context_mask |= kwic[col].astype(str).str.lower().str.contains(needle, regex=False, na=False)
            mask &= context_mask
        filtered = kwic[mask].reset_index(drop=True)
        # Concordance-first column order: contexts before run metadata.
        preferred = [
            col for col in (
                "Source", "Source_Normalized", "Group", "Date", "Target",
                "Left_Context", "Keyword", "Right_Context", "Full_Context",
                "Title", "Document_ID",
            ) if col in filtered.columns
        ]
        filtered = filtered[preferred + [col for col in filtered.columns if col not in preferred]]
        self._kwic_model.set_dataframe(filtered)

    def view_collocate_in_concordance(self, collocate: str) -> None:
        """Cross-jump: collocate → all its KWIC lines (Sinclair: jump to context)."""
        self.tabs.setCurrentIndex(0)
        self._kwic_search.setText(collocate)


# ======================================================================
# Runs
# ======================================================================

class RunsPage(QWidget):
    """Research audit center: GUI analysis runs + frozen runs + manifests."""

    def __init__(self, store: ProjectStore, inspector, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector

        from gui_next.execution.jobs import load_journal

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)
        title = QLabel("运行记录")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        status_labels = {
            "SUCCEEDED": "✓ success", "FAILED": "✕ failed", "CANCELLED": "○ cancelled",
            "INTERRUPTED": "⚠ interrupted", "RUNNING": "● running",
            "PREPARING": "● preparing", "CANCELLING": "● cancelling",
            "ANALYSIS_SUCCEEDED": "✓ analysis ok / publishing",
            "PUBLISHING": "● publishing", "PUBLISH_FAILED": "✕ publish failed",
        }
        rows = []
        for entry in load_journal(store.root):
            rows.append({
                "run_id": entry.get("run_id", ""),
                "kind": "analysis" if entry.get("kind") == "analyze" else entry.get("kind", ""),
                "status": status_labels.get(entry.get("status"), entry.get("status", "")),
                "started": entry.get("started_at", ""),
                "finished": entry.get("finished_at", ""),
                "group_by": (entry.get("params") or {}).get("group_by", ""),
                "targets": len((entry.get("params") or {}).get("targets", "").split(";")) if (entry.get("params") or {}).get("targets") else 0,
                "corpus_fp": (entry.get("corpus_fingerprint", "") or "")[:10],
                "output": "work+published" if entry.get("status") == "SUCCEEDED" else
                          ("work dir kept" if entry.get("work_dir") else "–"),
                "note": entry.get("note", ""),
            })
        for row in store.runs_index():
            rows.append({
                "run_id": row["run_id"],
                "kind": "frozen",
                "status": "🔒 frozen" if row["frozen"] else "current",
                "started": row["at"],
                "finished": "",
                "group_by": "",
                "targets": 0,
                "corpus_fp": "",
                "output": "runs/<run_id>" if row["frozen"] else "project root",
                "note": row.get("label", ""),
            })
        df = pd.DataFrame(rows)
        self._table_view = _table(df)
        self._table_view.doubleClicked.connect(self._on_select)
        root.addWidget(self._table_view, 1)
        root.addWidget(_muted(
            "双击冻结运行查看 Research Run Manifest;GUI 运行的 success/failed/cancelled/"
            "interrupted 状态、参数与输出可用性直接在表中显示。"))
        self._rows = rows

    def _on_select(self, index) -> None:
        row = self._rows[index.row()]
        if row["kind"] == "frozen":
            self.inspector.show_run(self.store.run_manifest(row["run_id"]), row["run_id"])
        elif row["kind"] == "analysis":
            self.inspector.show_empty(
                f"GUI 运行 {row['run_id']}\n状态:{row['status']}\n"
                f"输出:{row['output']}\n{row['note']}")
        else:
            self.inspector.show_empty("当前运行尚未固化;project freeze 后此处显示 manifest。")
