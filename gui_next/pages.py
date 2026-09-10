# -*- coding: utf-8 -*-
"""Primary research pages: Overview / Corpus / Analysis / Runs / Settings.

Phase 4A structure for every page:
    PageHeader (title · purpose · one primary action)
    shared FilterBar where filtering applies
    shared BaseTableView for data
    global Context Inspector for details

Pages never re-render global facts (project name / health / run identity):
those live in the app shell's Project Context Bar.
"""

from __future__ import annotations

import os
import platform
import subprocess
from typing import Any, Dict, List, Optional

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QStyledItemDelegate
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from gui_next import status, theme
from gui_next.data.health import HealthState, extract_corpus_report
from gui_next.data.review_store import SemanticReviewStore, SourceCountryReviewStore
from gui_next.data.store import ProjectStore
from gui_next.models import DataFrameModel
from gui_next.source_review_panel import SourceReviewPanel
from gui_next.widgets import (
    Banner,
    BaseTableView,
    EmptyState,
    FilterBar,
    PageHeader,
    show_toast,
)

STATE_COLORS = {"ok": theme.SUCCESS, "warn": theme.WARNING, "muted": theme.MUTED, "error": theme.ERROR}
HEALTH_COLORS = {
    HealthState.PASS: theme.SUCCESS,
    HealthState.WARNING: theme.WARNING,
    HealthState.STALE: theme.WARNING,
    HealthState.BLOCKED: theme.ERROR,
    HealthState.UNKNOWN: theme.MUTED,
}


def _muted(text: str) -> QLabel:
    """Legacy shared muted-label builder (still used by other pages)."""
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


def _table(df: pd.DataFrame, *, max_height: int = 0) -> BaseTableView:
    """Legacy shared table builder — now the unified BaseTableView."""
    view = BaseTableView()
    view.set_dataframe(df)
    return view


def _prefer_columns(df: pd.DataFrame, preferred: List[str]) -> pd.DataFrame:
    """Reorder columns researcher-first; unknown columns follow unchanged."""
    if df.empty:
        return df
    ordered = [col for col in preferred if col in df.columns]
    ordered += [col for col in df.columns if col not in ordered]
    return df[ordered]


def _card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(theme.SP_16, theme.SP_16, theme.SP_16, theme.SP_16)
    layout.setSpacing(theme.SP_8)
    if title:
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
    return frame, layout


# ======================================================================
# Overview — the research dashboard
# ======================================================================

class OverviewPage(QWidget):
    """Answers: what is this project, where is it, what's blocking me,
    what should I do next. Not a dump of every page's statistics."""

    def __init__(self, store: ProjectStore, inspector, navigate, *,
                 health=None, source_store=None, semantic_store=None,
                 router=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector
        self.navigate = navigate
        self.router = router
        self.health = health
        self.source_store = source_store
        self.semantic_store = semantic_store

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        content = QWidget()
        content.setObjectName("Page")
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(theme.SP_24, theme.SP_24, theme.SP_24, theme.SP_24)
        root.setSpacing(theme.SP_16)

        header = PageHeader(store.name, self.store.manifest.get("corpus_type", "") or "CADS 研究项目")
        root.addWidget(header)

        # Stat chips: registry-level values render immediately; the two
        # counts that require the big analysis sheets fill in after first
        # paint (#35 — Launcher/Overview must not wait on Analysis data).
        self._chip_values: Dict[str, QLabel] = {}
        chips_row = QHBoxLayout()
        chips_row.setSpacing(theme.SP_8)
        from gui_next.execution.publication import read_published_pointer
        published = read_published_pointer(store.root)
        cheap = [
            ("文档", str(len(store.documents_df))),
            ("KWIC 命中", "…"),
            ("搭配候选", "…"),
            ("目标词", str(len(store.targets))),
            ("分组", store.group_by),
            ("当前结果", (f"Run #{published['published_run_id'][-6:]}"
                          if published.get("published_run_id") else "–")),
        ]
        for label, value in cheap:
            frame = QFrame()
            frame.setObjectName("Card")
            box = QVBoxLayout(frame)
            box.setContentsMargins(theme.SP_16, theme.SP_12, theme.SP_16, theme.SP_12)
            box.setSpacing(0)
            value_label = QLabel(value)
            value_label.setObjectName("StatValue")
            label_label = QLabel(label)
            label_label.setObjectName("StatLabel")
            box.addWidget(value_label)
            box.addWidget(label_label)
            self._chip_values[label] = value_label
            chips_row.addWidget(frame, 1)
        root.addLayout(chips_row)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._fill_heavy_stats)

        # Banners: only facts that block or warn.
        self._banner = Banner()
        root.addWidget(self._banner)
        self._show_health_banner()

        # Research pipeline: stage states, never fake percentages.
        pipeline_card, pipeline_layout = _card("研究流程 RESEARCH PIPELINE")
        country_pending, country_total = self._country_pending()
        for row in store.pipeline_status(
            health=self.health,
            source_progress=self.source_store.progress() if self.source_store else None,
            country_pending=country_pending,
            country_total=country_total,
            semantic_progress=self.semantic_store.progress() if self.semantic_store else None,
        ):
            glyph, role = self._pipeline_role(row["state"])
            line = QHBoxLayout()
            line.setSpacing(theme.SP_12)
            stage = QLabel(str(row["stage"]))
            stage.setFixedWidth(150)
            glyph_label = QLabel(glyph)
            glyph_label.setFixedWidth(18)
            status.apply_state_style(glyph_label, role)
            detail = QLabel(str(row["detail"]))
            detail.setObjectName("Muted")
            detail.setWordWrap(True)
            line.addWidget(stage)
            line.addWidget(glyph_label)
            line.addWidget(detail, 1)
            pipeline_layout.addLayout(line)
        pipeline_layout.addStretch(1)
        root.addWidget(pipeline_card, 1)

        # Attention + next action.
        self._attention_items = self._compute_attention(country_pending)
        if self._attention_items:
            attention_card, attention_layout = _card("需要关注 ATTENTION")
            for item in self._attention_items:
                line = QHBoxLayout()
                line.setSpacing(theme.SP_12)
                glyph_label = QLabel(item["glyph"])
                glyph_label.setFixedWidth(18)
                status.apply_state_style(glyph_label, item["role"])
                text = QLabel(item["text"])
                text.setWordWrap(True)
                line.addWidget(glyph_label)
                line.addWidget(text, 1)
                attention_layout.addLayout(line)
            root.addWidget(attention_card)

            next_item = self._attention_items[0]
            next_card, next_layout = _card("下一步 NEXT ACTION")
            next_layout.addWidget(QLabel(next_item["text"]))
            action_row = QHBoxLayout()
            if next_item.get("action_text") and next_item.get("route"):
                button = QPushButton(next_item["action_text"])
                button.setObjectName("Primary")
                button.clicked.connect(
                    lambda _checked=False, r=next_item["route"], c=next_item.get("context"):
                    self.router.navigate_to(r, context=c) if self.router else self.navigate(r))
                action_row.addWidget(button)
                action_row.addStretch(1)
            next_layout.addLayout(action_row)
            root.addWidget(next_card)
        else:
            done = QLabel("✓ 当前没有阻塞项。")
            done.setStyleSheet(f"color: {theme.SUCCESS}; font-weight: 600; background: transparent;")
            root.addWidget(done)

    def _fill_heavy_stats(self) -> None:
        if self._chip_values.get("KWIC 命中") is None:
            return
        try:
            self._chip_values["KWIC 命中"].setText(f"{len(self.store.kwic_df):,}")
            self._chip_values["搭配候选"].setText(f"{len(self.store.collocates_df):,}")
        except Exception:
            self._chip_values["KWIC 命中"].setText("–")
            self._chip_values["搭配候选"].setText("–")

    # ------------------------------------------------------------------

    @staticmethod
    def _pipeline_role(state: Any) -> tuple[str, str]:
        text = str(state)
        if text in ("✓", "PASS"):
            return "✓", "ok"
        if text in ("⚠", "WARNING", "STALE"):
            return "⚠", "warn"
        if text in ("BLOCKED",):
            return "✕", "error"
        if text in ("○", "–", "", "UNKNOWN", "None"):
            return "○", "muted"
        return "●", "primary"

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

    def _show_health_banner(self) -> None:
        state = self.health[0] if self.health else HealthState.UNKNOWN
        detail = self.health[1] if self.health else ""
        if state is HealthState.BLOCKED:
            self._banner.show_banner(
                "error", "Analysis blocked — 语料卫生检查未通过", detail,
                action_text="查看语料 Health",
                action=lambda: self.router.navigate_to("语料", context={"tab": "health"})
                if self.router else self.navigate("语料"))
        elif state is HealthState.STALE:
            self._banner.show_banner(
                "warning", "Corpus health: STALE — 卫生检查结果已过期",
                f"{detail}。请重新运行 sanity,再继续分析或复核。",
                action_text="查看语料 Health",
                action=lambda: self.router.navigate_to("语料", context={"tab": "health"})
                if self.router else self.navigate("语料"))
        elif not self.store.has_analysis():
            self._banner.show_banner(
                "info", "下一步:运行第一次分析",
                "语料已导入但尚未运行分析。确保卫生检查通过后,从分析页启动 New Analysis Run。",
                action_text="前往分析",
                action=lambda: self.router.navigate_to("分析") if self.router else self.navigate("分析"))

    def _compute_attention(self, country_pending: int) -> List[Dict[str, Any]]:
        """Ordered attention list; the first item becomes NEXT ACTION."""
        items: List[Dict[str, Any]] = []
        state = self.health[0] if self.health else HealthState.UNKNOWN
        if state is HealthState.BLOCKED:
            items.append({"glyph": "✕", "role": "error", "route": "语料",
                          "context": {"tab": "health"},
                          "action_text": "查看语料 Health",
                          "text": "语料卫生 BLOCKED — 分析被禁止,需重新导入干净语料。"})
        elif state is HealthState.STALE:
            items.append({"glyph": "⚠", "role": "warn", "route": "语料",
                          "context": {"tab": "health"},
                          "action_text": "查看语料 Health",
                          "text": "语料卫生 STALE — 卫生检查已过期,重新运行后才能继续分析。"})
        elif state is HealthState.UNKNOWN and self.store.has_analysis() is False:
            items.append({"glyph": "○", "role": "muted", "route": "语料",
                          "context": {"tab": "health"},
                          "action_text": "查看语料 Health",
                          "text": "语料卫生尚未检查 — 运行 sanity 检查以解锁分析门禁。"})
        source_progress = self.source_store.progress() if self.source_store else None
        if source_progress and source_progress.get("pending"):
            items.append({"glyph": "●", "role": "primary", "route": "语料",
                          "context": {"tab": "sources"},
                          "action_text": "开始来源复核",
                          "text": f"来源规范化复核 {source_progress['decided']}/"
                                  f"{source_progress['total']} — 待复核 "
                                  f"{source_progress['pending']} 个来源。"})
        if self.source_store is not None and country_pending:
            items.append({"glyph": "⚠", "role": "warn", "route": "语料",
                          "context": {"tab": "sources"},
                          "action_text": "开始来源复核",
                          "text": f"复核 {country_pending} 条来源国别建议(自动推断的辅助变量)。"})
        semantic_progress = self.semantic_store.progress() if self.semantic_store else None
        if semantic_progress and semantic_progress.get("pending"):
            items.append({"glyph": "⚠", "role": "warn", "route": "复核",
                          "context": {},
                          "action_text": "继续复核",
                          "text": f"复核 {semantic_progress['pending']} 条语义韵候选"
                                  f"(已编码 {semantic_progress['coded']}/{semantic_progress['total']})。"})
        if self.semantic_store is not None and self.semantic_store.status() == "STALE":
            items.append({"glyph": "⚠", "role": "warn", "route": "复核",
                          "context": {},
                          "action_text": "打开复核",
                          "text": "语义韵复核状态 STALE — 旧结果已保留未计入,需要 reconciliation。"})
        published = self.store.published_analysis()
        if self.store.has_analysis() and not published.get("published_run_id"):
            items.append({"glyph": "○", "role": "muted", "route": "分析",
                          "context": {},
                          "action_text": "New Analysis Run",
                          "text": "尚无已发布的 GUI 运行 — 证据只能绑定已 COMMITTED 的已发布代际。"})
        review_files = self.store.review_files()
        coder_files = [item for item in review_files if "coder" in item["name"]]
        has_final = any("FINAL" in item["name"] for item in review_files)
        if coder_files and not has_final:
            items.append({"glyph": "○", "role": "muted", "route": "概览",
                          "context": {},
                          "action_text": "",
                          "text": f"{len(coder_files)} 份编码文件待调和(生成 FINAL 工作簿)。"})
        return items


# ======================================================================
# Corpus
# ======================================================================

class CorpusPage(QWidget):
    """Documents / Sources / Health — what the data is and whether it is clean."""

    def __init__(self, store: ProjectStore, inspector, *, source_store=None,
                 health=None, router=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector
        self.source_store = source_store
        self.health = health
        self.router = router

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SP_24, theme.SP_24, theme.SP_24, theme.SP_16)
        root.setSpacing(theme.SP_12)
        header = PageHeader("语料", "数据是什么、是否干净")
        root.addWidget(header)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_documents()
        self._build_sources()
        self._build_health()
        self.tabs.setCurrentIndex(0)

    def focus_object(self, object_id: str, context: Dict[str, Any]) -> None:
        """Router entry: context {'tab': 'documents'|'sources'|'health'}."""
        tab = str(context.get("tab", "documents"))
        index = {"documents": 0, "sources": 1, "health": 2}.get(tab, 0)
        self.tabs.setCurrentIndex(index)

    # -- Documents -----------------------------------------------------

    def _build_documents(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(theme.SP_12, theme.SP_12, theme.SP_12, theme.SP_12)
        layout.setSpacing(theme.SP_8)

        self._doc_filter = FilterBar()
        self._doc_filter.set_search_placeholder("搜索标题 / 来源 / 国别… (Ctrl+F)")
        self._doc_filter.changed.connect(self._apply_doc_filter)
        layout.addWidget(self._doc_filter)

        docs = self.store.documents_df
        columns = [
            col for col in (
                "document_id", "title", "source_normalized", "country",
                "date", "word_count_approx", "target_hits_total",
            ) if col in docs.columns
        ]
        self._docs_df = docs[columns] if columns else docs
        self._doc_view = BaseTableView(stretch_last=False)
        self._doc_view.set_dataframe(self._docs_df)
        self._doc_view.set_column_widths({
            "document_id": 110, "title": 320, "source_normalized": 150,
            "country": 90, "date": 110, "word_count_approx": 90,
            "target_hits_total": 90,
        })
        self._doc_view.recordSelected.connect(self.inspector.show_document)
        self._doc_view.recordActivated.connect(self._open_document_file)
        self._doc_view.set_empty_state(
            "无语料文档" if self._docs_df.empty else "没有匹配的文档",
            "导入语料以开始构建研究语料库。" if self._docs_df.empty
            else "调整搜索词或清除筛选。")
        layout.addWidget(self._doc_view, 1)
        self._doc_filter.set_result_count(len(self._doc_view.df()), len(self._docs_df))
        self.tabs.addTab(container, "Documents")

    def _apply_doc_filter(self) -> None:
        needle = self._doc_filter.search.text().strip().lower()
        if not needle:
            self._doc_view.set_dataframe(self._docs_df)
        else:
            mask = pd.Series(False, index=self._docs_df.index)
            for col in ("document_id", "title", "source_normalized", "country"):
                if col in self._docs_df.columns:
                    mask |= self._docs_df[col].astype(str).str.lower().str.contains(
                        needle, regex=False, na=False)
            self._doc_view.set_dataframe(self._docs_df[mask].reset_index(drop=True))
        self._doc_filter.set_result_count(len(self._doc_view.df()), len(self._docs_df))

    def _open_document_file(self, row: Dict[str, Any]) -> None:
        """Double-click opens the corpus text (read-only)."""
        relative = str(row.get("relative_path") or "")
        path = self.store.root / "corpus" / relative
        if not relative or not path.exists():
            self.inspector.show_empty(f"未找到文档全文:{row.get('document_id', '')}")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(str(path))  # noqa: S606
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except OSError as exc:
            self.inspector.show_empty(f"无法打开文档:{exc}")

    def focus_filter(self) -> None:
        self._doc_filter.focus_search()

    # -- Sources -------------------------------------------------------

    def _build_sources(self) -> None:
        sources = self._source_rows()
        view = BaseTableView(stretch_last=True)
        view.set_dataframe(sources)
        view.set_column_widths({
            "source": 200, "documents": 90, "country": 90, "suggested": 110,
            "confidence": 90, "decision": 100,
        })
        header = view.horizontalHeader()
        for column, name in enumerate(sources.columns):
            if name in ("original", "evidence"):
                header.setSectionHidden(column, True)

        self.source_panel = SourceReviewPanel(self.source_store, self.inspector) \
            if self.source_store is not None else None

        from PySide6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._wrap(view, "来源清单;选中行在右侧复核(不修改原始语料)"))
        if self.source_panel is not None:
            splitter.addWidget(self.source_panel)
            splitter.setSizes([560, 380])
            view.recordSelected.connect(self._on_source_selected)
            view.recordActivated.connect(self._on_source_selected)
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

    def _on_source_selected(self, record: Dict[str, Any]) -> None:
        if self.source_panel is not None:
            # Map by source identity, never by view row (sort-safe).
            self.source_panel.set_source(str(record.get("source", "")))

    # -- Health --------------------------------------------------------

    def _build_health(self) -> None:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(theme.SP_16, theme.SP_16, theme.SP_16, theme.SP_16)
        layout.setSpacing(theme.SP_8)

        report = extract_corpus_report(self.store.sanity_report) if self.store.sanity_report else {}
        state = self.health[0] if self.health else HealthState.UNKNOWN
        detail = self.health[1] if self.health else "未评估"
        glyph, text, role = status.health(state)
        heading = QLabel(f"Corpus health: {glyph} {text} ({state.value})")
        heading.setStyleSheet(
            f"color: {HEALTH_COLORS.get(state, theme.MUTED)}; font-weight: 600; font-size: 16px;")
        layout.addWidget(heading)
        layout.addWidget(QLabel(detail))

        if state in (HealthState.UNKNOWN, HealthState.STALE) and self.router is not None:
            hint = QHBoxLayout()
            sanity_button = QPushButton("运行 Sanity 检查")
            sanity_button.setObjectName("Primary")
            sanity_button.clicked.connect(self._request_sanity)
            hint.addWidget(sanity_button)
            hint.addStretch(1)
            layout.addLayout(hint)

        if report:
            for kind, rows in (("失败", report.get("failures", {})),
                               ("警告", report.get("warnings", {}))):
                for name, info in rows.items():
                    count = info.get("count", info.get("groups", info.get("total", 0)))
                    if not count:
                        continue
                    examples = "; ".join(info.get("examples", [])[:2])
                    text_line = f"{kind} · {name}: {count}"
                    if examples:
                        text_line += f" — 例: {examples}"
                    layout.addWidget(QLabel(text_line))
            checked = QLabel(f"检查时间:{report.get('checked_at', '–')}")
            checked.setObjectName("Muted")
            layout.addWidget(checked)
        elif not report:
            empty = EmptyState()
            empty.configure(
                "尚未运行语料卫生检查",
                "Sanity 检查通过后才能运行分析(研究门禁)。",
                "运行 Sanity 检查" if self.router is not None else "",
                self._request_sanity if self.router is not None else None)
            layout.addWidget(empty, 1)
        self.tabs.addTab(frame, "Health")

    def _request_sanity(self) -> None:
        if self.router is not None:
            # Route through the app shell: the sanity job needs the execution
            # controller, which lives with the Analysis page wiring.
            self.router.navigate_to("分析", context={"view": "run_config"})

    @staticmethod
    def _wrap(widget: QWidget, hint: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(theme.SP_12, theme.SP_12, theme.SP_12, theme.SP_12)
        layout.setSpacing(theme.SP_8)
        layout.addWidget(_muted(hint))
        layout.addWidget(widget, 1)
        return container


# ======================================================================
# Analysis
# ======================================================================

class KwicDelegate(QStyledItemDelegate):
    """KWIC emphasis: NODE bold/primary, run metadata muted (#21)."""

    def __init__(self, bold_columns: List[str], muted_columns: List[str], parent=None):
        super().__init__(parent)
        self._bold = set(bold_columns)
        self._muted = set(muted_columns)

    def initStyleOption(self, option, index) -> None:  # noqa: N802 (Qt naming)
        super().initStyleOption(option, index)
        try:
            name = str(index.model().headerData(index.column(), Qt.Horizontal))
        except RuntimeError:
            return
        if name in self._bold:
            option.font.setBold(True)
        elif name in self._muted:
            option.palette.setColor(QPalette.ColorRole.Text, QColor(theme.MUTED))


class AnalysisPage(QWidget):
    """Target-term centered analysis: term → concordance → collocates → groups."""

    METHOD_NOTE = "ⓘ MI / G² 用于发现和排序候选模式,不自动构成话语解释结论。"

    def __init__(self, store: ProjectStore, inspector, *, health=None,
                 evidence_store=None, router=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector
        self.health = health
        self.evidence = evidence_store
        self.router = router
        self._collocate_filter = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SP_24, theme.SP_24, theme.SP_24, theme.SP_16)
        root.setSpacing(theme.SP_12)

        header = PageHeader("分析", "发现重复出现的语言模式")
        self._new_run_button = QPushButton("＋ New Analysis Run")
        self._new_run_button.setObjectName("Primary")
        header.add_primary(self._new_run_button)
        root.addWidget(header)

        # Stacked: normal analysis view (0) / run lifecycle (1) / run config (2)
        from PySide6.QtWidgets import QStackedWidget
        self._view_stack = QStackedWidget()
        root.addWidget(self._view_stack, 1)

        normal = QWidget()
        normal_v = QVBoxLayout(normal)
        normal_v.setContentsMargins(0, 0, 0, 0)
        normal_v.setSpacing(theme.SP_12)
        body = QHBoxLayout()
        body.setSpacing(theme.SP_12)

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

        # Right: result tabs
        self.tabs = QTabWidget()
        body.addWidget(self.tabs, 1)
        normal_v.addLayout(body)
        self._view_stack.addWidget(normal)

        # Concordance: the core KWIC view (#21)
        self._kwic_model = DataFrameModel(pd.DataFrame(), self)
        self._kwic_view = BaseTableView(stretch_last=False)
        self._kwic_view.setModel(self._kwic_model)
        self._kwic_view.setItemDelegate(KwicDelegate(
            bold_columns=["Keyword"],
            muted_columns=["Source", "Source_Normalized", "Group", "Date",
                           "Target", "Document_ID", "Title"]))
        self._kwic_view.recordActivated.connect(
            lambda row: self.inspector.show_kwic(row))
        self._kwic_view.recordSelected.connect(self._kwic_selected)
        self._kwic_filter = FilterBar()
        self._kwic_filter.set_search_placeholder("在语境中筛选(来源/词形包含…)")
        self._kwic_filter.search.textChanged.connect(self._apply_kwic_filter)
        self._kwic_view.set_empty_state(
            "没有匹配的 KWIC 行",
            "调整目标词或清除语境筛选。")
        concordance = self._tab_wrap(self._kwic_filter, self._kwic_view,
                                     self.METHOD_NOTE)
        self.tabs.addTab(concordance, "Concordance")

        self._collocate_model = DataFrameModel(pd.DataFrame(), self)
        self._collocate_view = BaseTableView(stretch_last=False)
        self._collocate_view.setModel(self._collocate_model)
        self._collocate_view.recordActivated.connect(
            lambda row: self.inspector.show_collocate(self._current_target, row))
        self._collocate_view.set_empty_state("没有搭配候选", "调整 MI 阈值或目标词后重新运行分析。")
        self.tabs.addTab(self._tab_wrap(None, self._collocate_view), "Collocates")

        self._phrase_model = DataFrameModel(pd.DataFrame(), self)
        self._phrase_view = BaseTableView(stretch_last=False)
        self._phrase_view.setModel(self._phrase_model)
        self._phrase_view.set_empty_state("没有短语候选", "该目标词下未提取到修饰短语。")
        self.tabs.addTab(self._tab_wrap(None, self._phrase_view), "Phrases")

        self._group_model = DataFrameModel(store.group_df, self)
        self._group_view = BaseTableView(stretch_last=False)
        self._group_view.setModel(self._group_model)
        self._group_view.set_empty_state("没有分组比较数据", "分组比较需要分析时设置 group_by。")
        self.tabs.addTab(self._tab_wrap(None, self._group_view), "Groups")

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

        # Evidence capture (Phase 3A): E key + unified Inspector action.
        self.tabs.currentChanged.connect(lambda _i: self._apply_kwic_filter())
        for view in (self._kwic_view, self._collocate_view, self._phrase_view, self._group_view):
            view.installEventFilter(self)

        self._data_loaded = False
        self._current_target = ""
        if store.targets:
            self._target_list.setCurrentRow(0)
            self._target_list.currentRowChanged.connect(self._on_target_changed)
            self._on_target_changed(0)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """First show loads the analysis sheets (off the open-project path)."""
        super().showEvent(event)
        if not self._data_loaded:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._load_analysis_data)

    def _load_analysis_data(self) -> None:
        if self._data_loaded:
            return
        self._data_loaded = True
        # target hit counts
        kwic = self.store.kwic_df
        counts = kwic["Target"].value_counts() if not kwic.empty and "Target" in kwic.columns else pd.Series(dtype=int)
        for index, target in enumerate(self.store.targets):
            if index < self._target_list.count():
                self._target_list.item(index).setText(
                    f"{target}  ({int(counts.get(target, 0)):,})")
        self._apply_kwic_filter()
        row = max(0, self._target_list.currentRow())
        self._on_target_changed(row)

    # ------------------------------------------------------------------
    # views / routing

    def _show_run_config(self) -> None:
        self._view_stack.setCurrentWidget(self._run_config_view)

    def show_run_panel(self) -> None:
        self._view_stack.setCurrentWidget(self.run_panel)

    def show_normal_view(self) -> None:
        self._view_stack.setCurrentIndex(0)

    def focus_object(self, object_id: str, context: Dict[str, Any]) -> None:
        """Router entry: select a target, or open the run-config view."""
        if context.get("view") == "run_config":
            self._show_run_config()
            return
        if object_id and object_id in self.store.targets:
            self._target_list.setCurrentRow(self.store.targets.index(object_id))

    def focus_filter(self) -> None:
        self._kwic_filter.focus_search()

    @property
    def _kwic_search(self) -> QLineEdit:
        """Legacy attribute: the concordance filter input."""
        return self._kwic_filter.search

    @staticmethod
    def _tab_wrap(above: Optional[QWidget], main: QWidget,
                  below: Optional[str] = None) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(theme.SP_12, theme.SP_12, theme.SP_12, theme.SP_12)
        layout.setSpacing(theme.SP_8)
        if above is not None:
            layout.addWidget(above)
        layout.addWidget(main, 1)
        if below:
            note = QLabel(below)
            note.setObjectName("Muted")
            layout.addWidget(note)
        return container

    def _on_target_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.store.targets):
            return
        self._current_target = self.store.targets[row]
        if not self._data_loaded:
            return  # sheets load on first show of the page (#35)
        self._apply_kwic_filter()
        collocates = self.store.collocates_df
        if not collocates.empty and "Target" in collocates.columns:
            subset = collocates[collocates["Target"] == self._current_target]
            subset = subset.drop(columns=["Target"], errors="ignore")
            subset = _prefer_columns(subset, [
                "Collocate", "Frequency", "Doc_Frequency", "MI_Score",
                "Log_Likelihood", "LL_Significance", "POS",
            ])
            self._collocate_view.set_dataframe(subset.reset_index(drop=True))
            self._collocate_view.set_column_widths({
                "Collocate": 140, "Frequency": 80, "Doc_Frequency": 80,
                "MI_Score": 80, "Log_Likelihood": 90, "LL_Significance": 90,
            })
        phrases = self.store.phrases_df
        if not phrases.empty and "Target" in phrases.columns:
            subset = phrases[phrases["Target"] == self._current_target]
            subset = subset.drop(columns=["Target"], errors="ignore")
            subset = _prefer_columns(subset, [
                "Modifier_Phrase", "Frequency", "Doc_Frequency", "MI_Score",
                "Log_Likelihood",
            ])
            self._phrase_view.set_dataframe(subset.reset_index(drop=True))
            self._phrase_view.set_column_widths({
                "Modifier_Phrase": 260, "Frequency": 80, "Doc_Frequency": 80,
                "MI_Score": 80,
            })
        self._collocate_view.set_empty_state("没有搭配候选",
                                             f"目标词“{self._current_target}”下无搭配候选。")

    # ------------------------------------------------------------------
    # evidence capture (Phase 3A)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt naming)
        from PySide6.QtCore import QEvent, Qt as QtConst

        if event.type() == QEvent.KeyPress and \
                event.key() == QtConst.Key_E and not event.modifiers():
            obj_to_kind = {
                id(self._kwic_view): "kwic",
                id(self._collocate_view): "collocate_pattern",
                id(self._phrase_view): "phrase_pattern",
                id(self._group_view): "group_pattern",
            }
            kind = obj_to_kind.get(id(obj))
            if kind:
                self._capture_evidence(kind)
                return True
        return super().eventFilter(obj, event)

    def _kwic_selected(self, row: Dict[str, Any]) -> None:
        """Single click: KWIC detail + Evidence action in the Inspector."""
        if not row:
            return
        self.inspector.show_kwic(row)
        self.inspector.set_actions([("Add to Evidence (E)", self._capture_evidence)])

    def _capture_evidence(self, kind: Optional[str] = None) -> None:
        """Add the current tab's selected row to the Evidence Inbox."""
        if self.evidence is None:
            self.inspector.show_empty("证据库未初始化。")
            return
        pointer = self.store.published_analysis()
        if not pointer.get("published_run_id"):
            self.inspector.show_empty(
                "当前结果不属于任何已 COMMITTED 的 GUI 发布代际,不能作为正式研究证据。"
                "请先通过 New Analysis Run 完成一次分析并发布。")
            return
        tab_index = self.tabs.currentIndex()
        source_by_tab = {
            0: ("kwic", self._kwic_view),
            1: ("collocate_pattern", self._collocate_view),
            2: ("phrase_pattern", self._phrase_view),
            3: ("group_pattern", self._group_view),
        }
        evidence_type, view = source_by_tab[tab_index]
        if kind and evidence_type != kind:
            # direct key-capture on a specific view: switch to that tab first
            for idx, (tab_kind, _v) in source_by_tab.items():
                if tab_kind == kind:
                    self.tabs.setCurrentIndex(idx)
                    break
            evidence_type, view = kind, source_by_tab[self.tabs.currentIndex()][1]
        index = view.currentIndex()
        if not index.isValid():
            self.inspector.show_empty("请先在表中选择一行。")
            return
        row = view.model().row(index)

        fingerprint_map = {
            "kwic": [row.get("Document_ID", ""), row.get("Target", ""),
                     row.get("Left_Context", ""), row.get("Keyword", ""),
                     row.get("Right_Context", "")],
            "collocate_pattern": [row.get("Collocate", "")],
            "phrase_pattern": [row.get("Modifier_Phrase", "")],
            "group_pattern": [row.get("Target", ""), row.get("Kind", ""),
                              row.get("Expression", ""), row.get("Group_By", ""),
                              row.get("Source_Group", "")],
        }
        from gui_next.data.evidence_store import item_fingerprint
        fingerprint = item_fingerprint(evidence_type, pointer["published_run_id"],
                                       *fingerprint_map[evidence_type])
        already_in = any(
            r["item_fingerprint"] == fingerprint and
            r["evidence_type"] == evidence_type and
            r["published_run_id"] == pointer["published_run_id"]
            for r in self.evidence.evidence_records())
        snapshot = {k: ("" if pd.isna(v) else v) for k, v in row.items()}
        record = self.evidence.add_evidence(
            evidence_type=evidence_type,
            published_run_id=pointer["published_run_id"],
            publication_manifest_hash=pointer.get("manifest_sha256", ""),
            corpus_fingerprint=pointer.get("corpus_fingerprint", ""),
            parameters_hash=pointer.get("params_hash", ""),
            captured_snapshot=snapshot,
            fingerprint_parts=fingerprint_map[evidence_type],
            document_id=str(row.get("Document_ID", "") or ""),
            target=str(row.get("Target", "") or self._current_target),
            locator={"sheet": {"kwic": "KWIC", "collocate_pattern": "Collocates",
                               "phrase_pattern": "Phrases",
                               "group_pattern": "GroupComparison"}[evidence_type],
                     "row_index": int(index.row())},
        )
        self.evidence.save()
        if evidence_type == "kwic":
            self.inspector.show_kwic(row)
        self.inspector.set_badge(
            "✓ In Evidence" if already_in else "✓ 已加入证据(Add to Evidence)",
            theme.SUCCESS)
        self.inspector.set_actions([("Add to Evidence (E)", self._capture_evidence)])

    def _apply_kwic_filter(self) -> None:
        kwic = self.store.kwic_df
        if kwic.empty:
            self._kwic_view.set_dataframe(kwic)
            self._kwic_filter.set_result_count(0, 0)
            return
        mask = pd.Series(True, index=kwic.index)
        if "Target" in kwic.columns:
            mask &= kwic["Target"] == self._current_target
        needle = self._kwic_filter.search.text().strip().lower()
        if needle:
            context_mask = pd.Series(False, index=kwic.index)
            for col in ("Full_Context", "Source", "Source_Normalized", "Group"):
                if col in kwic.columns:
                    context_mask |= kwic[col].astype(str).str.lower().str.contains(needle, regex=False, na=False)
            mask &= context_mask
        filtered = kwic[mask].reset_index(drop=True)
        # Concordance-first column order: the language context leads (#21);
        # run metadata trails at low visual weight.
        preferred = [
            col for col in (
                "Keyword", "Left_Context", "Right_Context", "Source",
                "Source_Normalized", "Group", "Date", "Target", "Full_Context",
                "Title", "Document_ID",
            ) if col in filtered.columns
        ]
        filtered = filtered[preferred + [col for col in filtered.columns if col not in preferred]]
        self._kwic_view.set_dataframe(filtered)
        self._kwic_view.set_column_widths({
            "Keyword": 90, "Left_Context": 320, "Right_Context": 320,
            "Source": 130, "Source_Normalized": 130, "Group": 120,
            "Date": 100, "Target": 90, "Document_ID": 110,
        })
        self._kwic_filter.set_result_count(len(filtered), len(kwic))

    def view_collocate_in_concordance(self, collocate: str) -> None:
        """Cross-jump: collocate → all its KWIC lines (Sinclair: jump to context)."""
        self.tabs.setCurrentIndex(0)
        self._kwic_filter.search.setText(collocate)


# ======================================================================
# Runs
# ======================================================================

class RunsPage(QWidget):
    """Research audit center: GUI analysis runs + frozen runs + manifests.

    The table shows what a researcher needs (run/date/status/corpus/
    grouping/targets/evidence refs); technical manifest and hashes live in
    the Inspector (#25).
    """

    def __init__(self, store: ProjectStore, inspector, *, evidence_store=None,
                 router=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.inspector = inspector
        self.router = router

        from gui_next.execution.jobs import load_journal
        evidence_counts: Dict[str, int] = {}
        if evidence_store is not None:
            for record in evidence_store.evidence_records():
                run_id = record.get("published_run_id", "")
                evidence_counts[run_id] = evidence_counts.get(run_id, 0) + 1

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SP_24, theme.SP_24, theme.SP_24, theme.SP_16)
        root.setSpacing(theme.SP_12)
        header = PageHeader("运行记录", "结论怎么算出来的(执行基础设施)")
        self._compare_button = QPushButton("Compare Published Runs")
        self._compare_button.setObjectName("Primary")
        self._compare_button.setEnabled(False)
        self._compare_button.setToolTip("选择两个已发布的运行后可比较")
        self._compare_button.clicked.connect(self._open_compare)
        header.add_primary(self._compare_button)
        root.addWidget(header)

        rows = []
        for entry in load_journal(store.root):
            glyph, text, _role = status.run(entry.get("status", ""))
            rows.append({
                "run_id": entry.get("run_id", ""),
                "kind": "analysis" if entry.get("kind") == "analyze" else entry.get("kind", ""),
                "status": f"{glyph} {text}",
                "started": entry.get("started_at", ""),
                "group_by": (entry.get("params") or {}).get("group_by", ""),
                "targets": len((entry.get("params") or {}).get("targets", "").split(";")) if (entry.get("params") or {}).get("targets") else 0,
                "corpus_fp": (entry.get("corpus_fingerprint", "") or "")[:10],
                "证据引用": evidence_counts.get(entry.get("run_id", ""), 0),
                "note": entry.get("note", ""),
            })
        for row in store.runs_index():
            rows.append({
                "run_id": row["run_id"],
                "kind": "frozen",
                "status": "🔒 frozen" if row["frozen"] else "current",
                "started": row["at"],
                "group_by": "",
                "targets": 0,
                "corpus_fp": "",
                "证据引用": evidence_counts.get(row["run_id"], 0),
                "note": row.get("label", ""),
            })
        df = pd.DataFrame(rows)
        self._rows = rows
        self._table_view = BaseTableView(stretch_last=True)
        self._table_view.set_dataframe(df)
        self._table_view.set_column_widths({
            "run_id": 160, "kind": 80, "status": 180, "started": 150,
            "group_by": 90, "targets": 70, "corpus_fp": 110, "证据引用": 80,
        })
        self._table_view.setSelectionMode(BaseTableView.ExtendedSelection)
        self._table_view.recordSelected.connect(self._on_select)
        self._table_view.recordActivated.connect(self._on_select)
        self._table_view.selectionModel().selectionChanged.connect(self._on_multi_select)
        self._table_view.set_empty_state(
            "没有运行记录",
            "运行一次分析后,这里显示可审计的执行历史。",
            "前往分析" if store.has_analysis() else "",
            lambda: self.router.navigate_to("分析") if self.router else None)
        root.addWidget(self._table_view, 1)

        root.addWidget(_muted(
            "单击查看运行详情(参数、指纹、产物可用性);双击冻结运行查看 Research Run Manifest。"
            "\nⓘ Run differences describe changes in corpus/output under the recorded "
            "analysis configurations. They do not by themselves establish substantive discourse change."))

    # ------------------------------------------------------------------

    def focus_object(self, object_id: str, context: Dict[str, Any]) -> None:
        if object_id:
            self._table_view.select_by_id(object_id, id_column="run_id")

    def _on_select(self, row: Dict[str, Any]) -> None:
        if not row:
            return
        if row.get("kind") == "frozen":
            self.inspector.show_run(self.store.run_manifest(str(row.get("run_id", ""))),
                                    str(row.get("run_id", "")))
        elif row.get("kind") == "analysis":
            glyph, text, role = status.run(self._status_word(str(row.get("status", ""))))
            self.inspector.show_object(
                "RUN",
                str(row.get("run_id", "")),
                identity=[("Run ID", row.get("run_id"))],
                details=[
                    ("状态", text),
                    ("group_by", row.get("group_by")),
                    ("targets", row.get("targets")),
                    ("备注", row.get("note") or "–"),
                ],
                provenance=[("Corpus fingerprint", row.get("corpus_fp"))],
            )
        else:
            self.inspector.show_empty("当前运行尚未固化;project freeze 后此处显示 manifest。")

    @staticmethod
    def _status_word(display: str) -> str:
        text = display.replace("✓", "").replace("✕", "").replace("⚠", "").replace("●", "").strip()
        return {"success": "SUCCEEDED", "failed": "FAILED", "cancelled": "CANCELLED",
                "interrupted": "INTERRUPTED", "publish failed": "PUBLISH_FAILED",
                "Preparing": "PREPARING", "Running": "RUNNING",
                "Cancelling…": "CANCELLING", "Publishing": "PUBLISHING",
                "Analysis succeeded · publishing": "ANALYSIS_SUCCEEDED",
                }.get(text, text.upper().replace(" ", "_"))

    def _on_multi_select(self, *_args) -> None:
        """Compare gate (#25): enabled only with exactly two published runs."""
        published = self._selected_published_run_ids()
        self._compare_button.setEnabled(len(published) == 2)
        if len(published) == 2:
            self._compare_button.setToolTip(
                f"比较 {published[0][-8:]} ↔ {published[1][-8:]}")
        else:
            self._compare_button.setToolTip("选择两个已发布的运行后可比较")

    def _selected_published_run_ids(self) -> List[str]:
        selection = self._table_view.selectionModel()
        if selection is None:
            return []
        indexes = selection.selectedRows()
        ids = []
        for index in indexes:
            row = self._table_view.model().row(index)
            kind = row.get("kind", "")
            status_text = str(row.get("status", ""))
            if kind == "analysis" and "success" in status_text:
                ids.append(str(row.get("run_id", "")))
            elif kind == "frozen" and "frozen" in status_text:
                ids.append(str(row.get("run_id", "")))
        return ids

    def _open_compare(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        from gui_next.execution.compare import compare_overview

        runs = self._selected_published_run_ids()
        if len(runs) != 2:
            QMessageBox.information(self, "Compare",
                                    "需要恰好选择两个已成功发布的运行才能进行比较。")
            return
        run_a, run_b = runs[0], runs[1]

        dialog = QDialog(self)
        dialog.setWindowTitle("Compare Published Runs")
        dialog.resize(900, 640)
        layout = QVBoxLayout(dialog)

        overview = compare_overview(self.store.root, run_a, run_b)
        compat = overview["compatibility"]
        glyph, text, _role = status.comparison(compat["level"])

        banner = Banner()
        banner.show_banner("info" if "FULLY" in compat["level"] else "warning",
                           f"{glyph} {text}",
                           "; ".join(d["field"] for d in compat.get("differences", []))
                           or "No parameter differences detected.")
        layout.addWidget(banner)

        text_browser = QTextBrowser()
        md_lines = [
            f"<h3>Run A: <code>{run_a}</code></h3>",
            f"<h3>Run B: <code>{run_b}</code></h3>",
            "<table border='1' cellpadding='4' cellspacing='0'>",
            "<tr><th>Field</th><th>Run A</th><th>Run B</th></tr>",
            f"<tr><td>Documents</td><td>{overview['documents_a']}</td><td>{overview['documents_b']}</td></tr>",
            f"<tr><td>KWIC rows</td><td>{overview['kwic_count_a']}</td><td>{overview['kwic_count_b']}</td></tr>",
            f"<tr><td>Collocates</td><td>{overview['collocate_count_a']}</td><td>{overview['collocate_count_b']}</td></tr>",
            f"<tr><td>Phrases</td><td>{overview['phrase_count_a']}</td><td>{overview['phrase_count_b']}</td></tr>",
            f"<tr><td>group_by</td><td>{overview['group_by_a']}</td><td>{overview['group_by_b']}</td></tr>",
            f"<tr><td>MI threshold</td><td>{overview['mi_a']}</td><td>{overview['mi_b']}</td></tr>",
            "</table>",
            "<p style='color:gray'>ⓘ Run differences describe changes in corpus/output "
            "under the recorded analysis configurations. They do not by themselves "
            "establish substantive discourse change.</p>",
        ]
        text_browser.setHtml("".join(md_lines))
        layout.addWidget(text_browser, 1)

        buttons = QHBoxLayout()
        export_button = QPushButton("Export Comparison Markdown")
        export_button.clicked.connect(lambda: self._export_compare(dialog, run_a, run_b))
        close = QPushButton("关闭")
        close.clicked.connect(dialog.accept)
        buttons.addWidget(export_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        dialog.exec()

    def _export_compare(self, dialog: QDialog, run_a: str, run_b: str) -> None:
        from gui_next.execution.compare import export_comparison_markdown
        path = export_comparison_markdown(self.store.root, run_a, run_b)
        show_toast(self, f"已导出 Comparison Markdown",
                   action_text="打开文件夹",
                   action=lambda: _open_folder(str(path)))


def _open_folder(path: str) -> None:
    folder = str(path)
    if platform.system() == "Windows":
        subprocess.run(["explorer", "/select,", folder], check=False)
    elif platform.system() == "Darwin":
        subprocess.run(["open", "-R", folder], check=False)
    else:
        subprocess.run(["xdg-open", str(os.path.dirname(folder))], check=False)


# ======================================================================
# Settings
# ======================================================================

class SettingsPage(QWidget):
    """Application-level information and pointers. Not a research page."""

    def __init__(self, store: Optional[ProjectStore] = None, parent=None,
                 window=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._window = window
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SP_24, theme.SP_24, theme.SP_24, theme.SP_16)
        root.setSpacing(theme.SP_12)
        header = PageHeader("设置", "应用信息、诊断与文档入口")
        root.addWidget(header)

        from gui_next.version import build_metadata, python_version, qt_version
        meta = build_metadata()
        card, layout = _card("ABOUT")
        rows = [
            ("应用", f"{meta.get('app_name', 'CADS Workbench')} · "
                     f"Version {meta.get('version', '')}"),
            ("Build", f"commit {meta.get('git_commit', '–')} · "
                      f"{meta.get('build_timestamp', '–')} · "
                      f"{meta.get('build_mode', '')}"),
            ("运行时", f"Python {python_version()} · Qt {qt_version()}"),
            ("项目", store.name if store else "未打开"),
            ("项目路径", str(store.root) if store else "–"),
            ("界面缩放", "跟随 Windows 显示缩放(100%/125%/150% 已验证)"),
        ]
        for key, value in rows:
            line = QHBoxLayout()
            key_label = QLabel(key)
            key_label.setFixedWidth(90)
            key_label.setObjectName("Muted")
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            line.addWidget(key_label)
            line.addWidget(value_label, 1)
            layout.addLayout(line)
        root.addWidget(card)

        diag_card, diag_layout = _card("DIAGNOSTICS")
        diag_layout.addWidget(_muted(
            "诊断包含版本/环境/日志/项目结构摘要与已发布运行标识;"
            "不包含语料正文、KWIC 内容、Evidence 备注或 Writing 文本。"
            "本应用不含 telemetry:诊断仅在你主动导出时生成。"))
        diag_row = QHBoxLayout()
        export_btn = QPushButton("Export Diagnostics")
        export_btn.setObjectName("Primary")
        export_btn.clicked.connect(self._export_diagnostics)
        logs_btn = QPushButton("打开日志文件夹")
        logs_btn.clicked.connect(self._open_logs)
        diag_row.addWidget(export_btn)
        diag_row.addWidget(logs_btn)
        diag_row.addStretch(1)
        diag_layout.addLayout(diag_row)
        root.addWidget(diag_card)

        docs_card, docs_layout = _card("HELP / DOCUMENTATION")
        for name, description in (
            ("QUICKSTART_GUI.md", "快速开始(面向第一次使用者)"),
            ("KEYBOARD_SHORTCUTS.md", "全局与页面快捷键"),
            ("METHODOLOGY.md", "方法论与边界"),
            ("RELEASE_NOTES_v1.0-rc1.md", "本版本能力与已知限制"),
            ("GUI_DESIGN_SYSTEM.md", "设计令牌、组件与页面结构规范"),
        ):
            line = QHBoxLayout()
            label = QLabel(f"{description} — docs/{name}")
            label.setWordWrap(True)
            open_doc = QPushButton("打开")
            open_doc.setObjectName("Flat")
            open_doc.clicked.connect(
                lambda _checked=False, n=name: self._open_doc(n))
            line.addWidget(label, 1)
            line.addWidget(open_doc)
            docs_layout.addLayout(line)
        root.addWidget(docs_card)
        root.addStretch(1)

    # ------------------------------------------------------------------

    def _export_diagnostics(self) -> None:
        if self._window is not None and hasattr(self._window, "_export_diagnostics"):
            self._window._export_diagnostics()

    def _open_logs(self) -> None:
        from gui_next.appdata import logs_dir
        _open_folder(str(logs_dir()))

    @staticmethod
    def _open_doc(name: str) -> None:
        import os
        import platform
        import subprocess

        from gui_next.version import docs_dir
        path = docs_dir() / name
        target = str(path if path.exists() else docs_dir())
        try:
            if platform.system() == "Windows":
                os.startfile(target)  # noqa: S606
            elif platform.system() == "Darwin":
                subprocess.run(["open", target], check=False)
            else:
                subprocess.run(["xdg-open", target], check=False)
        except OSError:
            pass


def _open_folder(path: str) -> None:
    try:
        if platform.system() == "Windows":
            os.startfile(path)  # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except OSError:
        pass
