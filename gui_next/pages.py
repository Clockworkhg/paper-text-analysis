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
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.data.store import ProjectStore
from gui_next.models import DataFrameModel

STATE_COLORS = {"ok": theme.SUCCESS, "warn": theme.WARNING, "muted": theme.MUTED, "error": theme.ERROR}


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

    def __init__(self, store: ProjectStore, inspector, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector
        self.navigate = navigate  # callable(page_key) for cross-page jumps

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
        for row in store.pipeline_status():
            line = QHBoxLayout()
            line.setSpacing(12)
            stage = QLabel(row["stage"])
            stage.setFixedWidth(110)
            state = QLabel(str(row["state"]))
            state.setFixedWidth(24)
            detail = QLabel(str(row["detail"]))
            detail.setObjectName("Muted")
            detail.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
            line.addWidget(stage)
            line.addWidget(state)
            line.addWidget(detail, 1)
            status_layout.addLayout(line)
        status_layout.addStretch(1)
        root.addWidget(status_card, 1)

    def _build_callout(self) -> None:
        while self._callout_layout.count():
            item = self._callout_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        blocked = self.store.analysis_blocked_reason()
        if blocked:
            self._callout.setObjectName("CalloutBlocked")
            heading = QLabel("Analysis blocked")
            heading.setObjectName("CalloutTitle")
            heading.setStyleSheet(f"color: {theme.ERROR}; background: transparent; font-weight: 600;")
            body = QLabel(blocked)
            body.setWordWrap(True)
            body.setStyleSheet("background: transparent;")
            action = QLabel("→ 前往 Corpus → Health 查看详情;用原始语料重新导入后重跑分析。")
            action.setStyleSheet("background: transparent;")
            for widget in (heading, body, action):
                self._callout_layout.addWidget(widget)
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

    def __init__(self, store: ProjectStore, inspector, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector

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
        sources = self.store.sources_df
        columns = [col for col in ("Source_Merged", "Count_Sum", "Country", "Confidence") if col in sources.columns]
        view = _table(sources[columns] if columns else sources)
        view.doubleClicked.connect(
            lambda index: self.inspector.show_source(view.model().row(index))
        )
        self.tabs.addTab(self._wrap(view, "来源合并与国别(辅助变量,需人工复核);双击查看证据"), "Sources")

    def _build_health(self) -> None:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        report = self.store.sanity_report
        if not report:
            layout.addWidget(QLabel("尚未运行语料卫生检查"))
            layout.addWidget(_muted("运行:python research_tool.py project sanity -p <项目目录>"))
        else:
            ok = report.get("ok")
            heading = QLabel("✓ 卫生检查通过" if ok else "⚠ 卫生检查未通过")
            heading.setStyleSheet(
                f"color: {theme.SUCCESS if ok else theme.ERROR}; font-weight: 600; background: transparent;"
            )
            layout.addWidget(heading)
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

    def __init__(self, store: ProjectStore, inspector, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector
        self._collocate_filter = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)
        title = QLabel("分析")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

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
        root.addWidget(note)

        self._current_target = ""
        if store.targets:
            self._target_list.setCurrentRow(0)
            self._target_list.currentRowChanged.connect(self._on_target_changed)
            self._on_target_changed(0)

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
# Review (read-only in Phase 1)
# ======================================================================

class ReviewPage(QWidget):
    """Review workbench (Phase 1 read-only): progress and candidate listing."""

    def __init__(self, store: ProjectStore, inspector, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)
        title = QLabel("复核")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        files = store.review_files()
        if files:
            best = files[0]
            progress_card, progress_layout = _card(f"{best['name']} · {best.get('sheet', '')}")
            bar = QProgressBar()
            bar.setValue(int(best["percent"]))
            bar.setFormat(f"{best['coded']} / {best['rows']} 条已编码({best['percent']}%)")
            progress_layout.addWidget(bar)
            others = "、".join(item["name"] for item in files[1:]) or "无"
            progress_layout.addWidget(_muted(f"编码文件:{others}"))
            root.addWidget(progress_card)

            table_card, table_layout = _card(f"候选条目 · {best['sheet']}")
            df = pd.read_excel(best["path"], sheet_name=best.get("sheet") or 0)
            view = _table(df)
            view.doubleClicked.connect(
                lambda index: self._show_candidate(view.model().row(index))
            )
            table_layout.addWidget(view, 1)
            root.addWidget(table_card, 1)

            note = QLabel("ⓘ Phase 1 为只读视图;键盘编码(1/2/3/4 + Enter)在 Phase 2 接入。")
            note.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
            root.addWidget(note)
        else:
            empty, empty_layout = _card("无复核文件")
            empty_layout.addWidget(_muted("运行 project review 生成复核模板后,这里显示编码进度与候选条目。"))
            root.addWidget(empty)
            root.addStretch(1)

    def _show_candidate(self, row: Dict[str, Any]) -> None:
        context = next(
            (str(row[key]) for key in ("Full_Context", "Context", "Sentence", " KWIC") if key in row and str(row[key]) != "nan"),
            "",
        )
        pairs = [
            (key, str(value)) for key, value in row.items()
            if key not in ("Full_Context", "Context") and str(value) not in ("nan", "")
        ][:10]
        self.inspector._set("REVIEW CANDIDATE", context[:80] or "候选条目", [], pairs)


# ======================================================================
# Runs
# ======================================================================

class RunsPage(QWidget):
    """Research audit center: frozen runs and their manifests."""

    def __init__(self, store: ProjectStore, inspector, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)
        title = QLabel("运行记录")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        rows = store.runs_index()
        df = pd.DataFrame([
            {
                "运行": row["run_id"],
                "标签": row["label"],
                "状态": "🔒 frozen" if row["frozen"] else "current",
                "时间": row["at"],
                "文件数": row["files"],
            }
            for row in rows
        ])
        self._table_view = _table(df)
        self._table_view.doubleClicked.connect(self._on_select)
        root.addWidget(self._table_view, 1)
        root.addWidget(_muted("双击查看 Research Run Manifest(参数、语料指纹、模型/规则/算法版本、文件哈希)。"))
        self._rows = rows

    def _on_select(self, index) -> None:
        row = self._rows[index.row()]
        if row["frozen"]:
            self.inspector.show_run(self.store.run_manifest(row["run_id"]), row["run_id"])
        else:
            self.inspector.show_empty("当前运行尚未固化;project freeze 后此处显示 manifest。")
