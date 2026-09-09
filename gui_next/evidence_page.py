# -*- coding: utf-8 -*-
"""Evidence page: Inbox / Claims / Evidence list / Claim workspace.

Claim -> Pattern -> KWIC -> Document -> Published Run. All evidence resolves
against immutable published generations (runs/published/<run_id>/) via
GenerationResolver — never against the current project root.

Phase 4A: one table experience (BaseTableView), one filter bar, unified
Inspector (show_evidence), distinct Inbox vs Claim workspace (PATTERN /
QUALITATIVE grouping), integrity results cached per (run, manifest).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.data.evidence_store import (
    EvidenceReferencedError,
    EvidenceStateConflictError,
    EvidenceStore,
)
from gui_next.data.generations import GenerationResolver
from gui_next.widgets import BaseTableView, FilterBar, PageHeader, show_toast

TYPE_LABELS = {
    "kwic": "QUALITATIVE · KWIC",
    "collocate_pattern": "PATTERN · Collocate",
    "phrase_pattern": "PATTERN · Phrase",
    "group_pattern": "PATTERN · Group",
}
PATTERN_TYPES = {"collocate_pattern", "phrase_pattern", "group_pattern"}
QUALITATIVE_TYPES = {"kwic"}


def evidence_summary(record: Dict[str, Any]) -> str:
    snap = record.get("captured_snapshot", {}) or {}
    kind = record.get("evidence_type", "")
    if kind == "kwic":
        node = snap.get("Keyword") or record.get("target", "")
        left = str(snap.get("Left_Context", ""))[-30:]
        right = str(snap.get("Right_Context", ""))[:30]
        return f"{left} [{node}] {right}"
    if kind == "collocate_pattern":
        return (f"{record.get('target', '')} × {snap.get('Collocate', '')} · "
                f"MI {snap.get('MI_Score', '–')}, G² {snap.get('Log_Likelihood', '–')}")
    if kind == "phrase_pattern":
        return f"{record.get('target', '')} + “{snap.get('Modifier_Phrase', '')}”"
    if kind == "group_pattern":
        return (f"{record.get('target', '')} · {snap.get('Group', '')} · "
                f"{snap.get('Kind', '')} {snap.get('Expression', '')} ({snap.get('Frequency', '')})")
    return record.get("evidence_id", "")


class SupportingKwicDialog(QDialog):
    """Pick supporting KWIC lines from the evidence's own published run."""

    def __init__(self, rows: pd.DataFrame, parent=None):
        super().__init__(parent)
        self.setWindowTitle("View supporting KWIC (published generation)")
        self.resize(860, 520)
        layout = QVBoxLayout(self)
        note = QLabel("以下 KWIC 行来自该证据绑定的已发布代际(非当前最新运行)。"
                      "选择行后点击下方按钮加入证据。")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = BaseTableView(stretch_last=True)
        self.table.set_dataframe(rows.reset_index(drop=True))
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        add_selected = QPushButton("Add selected to Evidence")
        add_selected.setObjectName("Primary")
        add_selected.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(add_selected)
        layout.addLayout(buttons)

    def selected_rows(self) -> List[Dict[str, Any]]:
        rows = []
        for index in self.table.selectionModel().selectedRows():
            rows.append(self.table.model().row(index))
        return rows


class EvidencePage(QWidget):
    """Evidence Inbox + Claims workspace."""

    def __init__(self, store: EvidenceStore, resolver: GenerationResolver,
                 published_provider, inspector, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.evidence = store
        self.resolver = resolver
        self.published_provider = published_provider  # callable -> pointer dict
        self.inspector = inspector
        self.navigate = navigate
        self._current_claim_id: Optional[str] = None
        self._integrity_cache: Dict[tuple, tuple] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 16, 16)
        root.setSpacing(theme.SP_12)

        header = PageHeader("证据", "组织研究论证:Claim → Pattern → KWIC → Run")
        self._check_newer_button = QPushButton("Check against newer run")
        self._export_button = QPushButton("Export Claim Evidence Packet")
        self._new_claim_button = QPushButton("＋ New Claim (N)")
        self._new_claim_button.setObjectName("Primary")
        self._check_newer_button.clicked.connect(self._check_newer_run)
        self._export_button.clicked.connect(self._export_packet)
        self._new_claim_button.clicked.connect(self._new_claim_dialog)
        header.add_secondary(self._check_newer_button)
        header.add_secondary(self._export_button)
        header.add_secondary(self._new_claim_button)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        # ---- Left: Inbox / Claims ------------------------------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(theme.SP_8)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setObjectName("Nav")
        self._tree.itemSelectionChanged.connect(self._on_tree_selection)
        left_layout.addWidget(self._tree, 1)
        claim_buttons = QHBoxLayout()
        up = QPushButton("↑")
        up.setFixedWidth(34)
        up.setToolTip("上移 Claim")
        up.clicked.connect(lambda: self._move_claim(-1))
        down = QPushButton("↓")
        down.setFixedWidth(34)
        down.setToolTip("下移 Claim")
        down.clicked.connect(lambda: self._move_claim(+1))
        delete_claim = QPushButton("Delete Claim")
        delete_claim.clicked.connect(self._delete_claim)
        claim_buttons.addWidget(up)
        claim_buttons.addWidget(down)
        claim_buttons.addWidget(delete_claim, 1)
        left_layout.addLayout(claim_buttons)
        splitter.addWidget(left)

        # ---- Center: Inbox / Claim workspace --------------------------
        from PySide6.QtWidgets import QStackedWidget
        self._center = QStackedWidget()
        self._center.addWidget(self._build_inbox_view())      # index 0
        self._center.addWidget(self._build_claim_workspace())  # index 1
        splitter.addWidget(self._center)
        splitter.setSizes([240, 860])

        # ---- Keyboard --------------------------------------------------
        for keys, handler in (
            ("N", self._new_claim_dialog),
            ("Return", self._open_selected),
            ("Delete", self._delete_selected),
            ("Ctrl+F", self.focus_filter),
        ):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(handler)

        self.refresh()

    # ------------------------------------------------------------------
    # center views

    def _build_inbox_view(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SP_8)
        self._filter = FilterBar()
        self._filter.set_search_placeholder("搜索:target / source / 自由文本… (Ctrl+F)")
        self._filter.add_combo("Type", [("全部类型", "")] + [
            (label, key) for key, label in TYPE_LABELS.items()])
        self._filter.add_combo("Run", [("全部运行", "")])
        self._filter.changed.connect(self._refresh_table)
        layout.addWidget(self._filter)
        self._view = BaseTableView(stretch_last=True)
        self._view.set_column_widths({
            "Type": 150, "Evidence": 360, "Run": 100, "Target": 110,
            "Claims": 160, "Integrity": 110, "Created": 140, "ID": 240,
        })
        self._view.recordActivated.connect(lambda row: self._open_row(row))
        self._view.recordSelected.connect(self._on_row_selected)
        self._view.set_empty_state(
            "No evidence collected",
            "从 Analysis 页添加 KWIC 或语言模式;证据只能绑定已 COMMITTED 的已发布代际。",
            "前往分析", lambda: self.navigate("分析"))
        layout.addWidget(self._view, 1)
        return container

    def _build_claim_workspace(self) -> QWidget:
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(theme.SP_8)

        self._claim_header = QLabel("")
        self._claim_header.setWordWrap(True)
        self._claim_header.setStyleSheet(
            f"background: {theme.SELECTED}; border: 1px solid {theme.BORDER};"
            f"border-radius: 6px; padding: 12px;")
        outer.addWidget(self._claim_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(theme.SP_12)

        pattern_caption = QLabel("PATTERN EVIDENCE(搭配 / 短语 / 分组模式)")
        pattern_caption.setObjectName("SectionTitle")
        body_layout.addWidget(pattern_caption)
        self._pattern_view = BaseTableView(stretch_last=True)
        self._pattern_view.set_column_widths({
            "Evidence": 420, "Run": 100, "Target": 110, "Integrity": 110, "ID": 240,
        })
        self._pattern_view.recordActivated.connect(lambda row: self._open_row(row))
        self._pattern_view.recordSelected.connect(self._on_row_selected)
        self._pattern_view.set_empty_state(
            "该 Claim 尚无 Pattern 证据",
            "从 Analysis 页添加搭配、短语或分组模式,或在证据刷新中加入对应模式。")
        body_layout.addWidget(self._pattern_view, 2)

        qualitative_caption = QLabel("QUALITATIVE EVIDENCE(KWIC 语境)")
        qualitative_caption.setObjectName("SectionTitle")
        body_layout.addWidget(qualitative_caption)
        self._qualitative_view = BaseTableView(stretch_last=True)
        self._qualitative_view.set_column_widths({
            "Evidence": 420, "Run": 100, "Target": 110, "Integrity": 110, "ID": 240,
        })
        self._qualitative_view.recordActivated.connect(lambda row: self._open_row(row))
        self._qualitative_view.recordSelected.connect(self._on_row_selected)
        self._qualitative_view.set_empty_state(
            "该 Claim 尚无 KWIC 证据",
            "从 Analysis 页 Concordance 添加 KWIC 语境行,或从 Pattern 证据查看 supporting KWIC。")
        body_layout.addWidget(self._qualitative_view, 2)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        return container

    # ------------------------------------------------------------------
    # data access

    def _pointer(self) -> Dict[str, Any]:
        return self.published_provider() or {}

    def _integrity(self, record: Dict[str, Any]) -> tuple[str, str]:
        """(state, detail) via the resolver; cached per (run, manifest hash)."""
        key = (record.get("published_run_id", ""),
               record.get("publication_manifest_hash", ""))
        cached = self._integrity_cache.get(key)
        if cached is None:
            result = self.resolver.integrity(
                record.get("published_run_id", ""),
                publication_manifest_hash=record.get("publication_manifest_hash", ""),
                stored_artifact_hashes=record.get("artifact_hashes") or None,
            )
            cached = (result.state, result.detail)
            self._integrity_cache[key] = cached
        return cached

    def focus_filter(self) -> None:
        if self._current_claim_id is None:
            self._filter.focus_search()

    def focus_object(self, object_id: str, context: Dict[str, Any]) -> None:
        """Router entry: select a claim (tree) or an evidence row."""
        if context.get("kind") == "claim" or (
                object_id in {c["claim_id"] for c in self.evidence.claims()}):
            self._select_claim(object_id)
            return
        self._tree.clearSelection()
        self._current_claim_id = None
        self._center.setCurrentIndex(0)
        self._view.select_by_id(object_id)

    # ------------------------------------------------------------------
    # rendering

    def refresh(self) -> None:
        self._refresh_tree()
        self._apply_view_mode()
        self._refresh_table()
        self._refresh_claim_header()

    def _apply_view_mode(self) -> None:
        self._center.setCurrentIndex(0 if self._current_claim_id is None else 1)

    def _refresh_tree(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        unassigned = [r for r in self.evidence.evidence_records()
                      if not self.evidence.claim_refs(r["evidence_id"])]
        inbox = QTreeWidgetItem([f"Inbox  ({len(unassigned)})"])
        inbox.setData(0, Qt.UserRole, ("inbox", None))
        self._tree.addTopLevelItem(inbox)
        claims_item = QTreeWidgetItem([f"Claims  ({len(self.evidence.claims())})"])
        claims_item.setData(0, Qt.UserRole, ("claims_all", None))
        self._tree.addTopLevelItem(claims_item)
        for claim in self.evidence.claims():
            child = QTreeWidgetItem([f"{claim['title']}  ({len(claim['evidence_ids'])})"])
            child.setData(0, Qt.UserRole, ("claim", claim["claim_id"]))
            claims_item.addChild(child)
        self._tree.expandAll()
        self._tree.blockSignals(False)

    def _select_claim(self, claim_id: str) -> bool:
        claims_item = self._tree.topLevelItem(1)
        if claims_item is None:
            return False
        for index in range(claims_item.childCount()):
            child = claims_item.child(index)
            if child.data(0, Qt.UserRole) == ("claim", claim_id):
                self._tree.setCurrentItem(child)
                return True
        return False

    def _on_tree_selection(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.UserRole) or ("inbox", None)
        kind, claim_id = data
        self._current_claim_id = claim_id if kind == "claim" else None
        self._apply_view_mode()
        self._refresh_table()
        self._refresh_claim_header()

    def _refresh_claim_header(self) -> None:
        if self._current_claim_id is None:
            self._claim_header.setText("")
            return
        claim = self.evidence.get_claim(self._current_claim_id) or {}
        self._claim_header.setText(
            f"CLAIM:“{claim.get('title', '')}”\n{claim.get('claim_text', '')}\n"
            f"备注:{claim.get('researcher_note') or '–'} · "
            f"证据 {len(claim.get('evidence_ids', []))} 条")

    def _table_records(self) -> List[Dict[str, Any]]:
        """Records for the active view (inbox / claim), filtered."""
        records = self.evidence.evidence_records()
        type_filter = self._filter.combo_value(0) if hasattr(self, "_filter") else ""
        run_filter = self._filter.combo_value(1) if hasattr(self, "_filter") else ""
        needle = self._filter.search.text().strip().lower() if hasattr(self, "_filter") else ""

        rows = []
        for record in records:
            if self._current_claim_id is not None:
                claim = self.evidence.get_claim(self._current_claim_id) or {}
                if record["evidence_id"] not in claim.get("evidence_ids", []):
                    continue
            if type_filter and record.get("evidence_type") != type_filter:
                continue
            if run_filter and record.get("published_run_id") != run_filter:
                continue
            if needle:
                hay = " ".join([
                    record.get("target", ""), record.get("document_id", ""),
                    json.dumps(record.get("captured_snapshot", {}), ensure_ascii=False),
                ]).lower()
                if needle not in hay:
                    continue
            rows.append(record)
        return rows

    def _records_df(self, records: List[Dict[str, Any]]) -> pd.DataFrame:
        rows = []
        for record in records:
            refs = self.evidence.claim_refs(record["evidence_id"])
            claim_titles = ", ".join(
                (self.evidence.get_claim(cid) or {}).get("title", cid) for cid in refs)
            state, _detail = self._integrity(record)
            rows.append({
                "Type": TYPE_LABELS.get(record["evidence_type"], record["evidence_type"]),
                "Evidence": evidence_summary(record),
                "Run": f"#{record.get('published_run_id', '')[-8:]}",
                "Target": record.get("target", ""),
                "Claims": claim_titles or "Inbox",
                "Integrity": state,
                "Created": record.get("created_at", ""),
                "ID": record["evidence_id"],
            })
        return pd.DataFrame(rows)

    def _refresh_table(self) -> None:
        records = self._table_records()

        # keep the run combo choices current
        runs = sorted({r.get("published_run_id", "") for r in self.evidence.evidence_records()},
                      reverse=True)
        combo = self._filter._fields[1][1] if len(self._filter._fields) > 1 else None
        if combo is not None:
            values = [combo.itemData(i) for i in range(combo.count())]
            if runs != [v for v in values if v]:
                combo.blockSignals(True)
                combo.clear()
                combo.addItem("全部运行", "")
                for run_id in runs:
                    combo.addItem(f"#{run_id[-8:]}", run_id)
                combo.blockSignals(False)

        if self._current_claim_id is None:
            df = self._records_df(records)
            self._view.set_dataframe(df)
            self._filter.set_result_count(len(df), len(self.evidence.evidence_records()))
        else:
            pattern = self._records_df(
                [r for r in records if r["evidence_type"] in PATTERN_TYPES])
            qualitative = self._records_df(
                [r for r in records if r["evidence_type"] in QUALITATIVE_TYPES])
            self._pattern_view.set_dataframe(pattern)
            self._qualitative_view.set_dataframe(qualitative)

    def _open_row(self, row: Dict[str, Any]) -> None:
        record = self.evidence.get_evidence(str(row.get("ID", "")))
        if record:
            self.show_evidence_detail(record)

    def _on_row_selected(self, row: Dict[str, Any]) -> None:
        record = self.evidence.get_evidence(str(row.get("ID", "")))
        if record:
            self.show_evidence_detail(record)

    # ------------------------------------------------------------------
    # evidence detail (unified Inspector)

    def show_evidence_detail(self, record: Dict[str, Any]) -> None:
        state, detail = self._integrity(record)
        refs = self.evidence.claim_refs(record["evidence_id"])
        claim_titles = ", ".join(
            (self.evidence.get_claim(cid) or {}).get("title", cid) for cid in refs)
        self.inspector.show_evidence(
            record, state=state, state_detail=detail, claims=claim_titles or "Inbox")
        actions: list[tuple[str, Any]] = [("Open Run", lambda: self.navigate("运行记录"))]
        if record["evidence_type"] in PATTERN_TYPES:
            actions.append(("View supporting KWIC", lambda: self._view_supporting_kwic(record)))
        if self.evidence.newer_counterpart(record["evidence_id"]):
            actions.append(("Replace in Claim", self._replace_in_claim))
        actions.append(("Delete", self._delete_selected))
        self.inspector.set_actions(actions)

    # ------------------------------------------------------------------
    # claims

    def _new_claim_dialog(self) -> None:
        title, ok = QInputDialog.getText(self, "New Claim", "Claim 标题:")
        if not ok or not title.strip():
            return
        text, ok2 = QInputDialog.getMultiLineText(self, "New Claim", "Claim 内容(研究论断,系统不做真假判定):")
        self.evidence.add_claim(title, claim_text=text if ok2 else "")
        self.evidence.save()
        self.refresh()

    def _move_claim(self, direction: int) -> None:
        if not self._current_claim_id:
            return
        ids = [c["claim_id"] for c in self.evidence.claims()]
        index = ids.index(self._current_claim_id)
        swap = index + direction
        if 0 <= swap < len(ids):
            ids[index], ids[swap] = ids[swap], ids[index]
            self.evidence.reorder_claims(ids)
            self.evidence.save()
            self.refresh()

    def _delete_claim(self) -> None:
        if not self._current_claim_id:
            return
        claim = self.evidence.get_claim(self._current_claim_id) or {}
        title = claim.get('title', '')
        if QMessageBox.question(
                self, "Delete Claim",
                f"删除 Claim“{title}”?\n证据记录本身不会被删除。") != QMessageBox.Yes:
            return
        self.evidence.delete_claim(self._current_claim_id)
        self._current_claim_id = None
        self.evidence.save()
        self.refresh()

    # ------------------------------------------------------------------
    # Evidence Refresh (Phase 3C)

    def _check_newer_run(self) -> None:
        """Find counterpart evidence in a newer published run."""
        pointer = self._pointer()
        current_run = pointer.get("published_run_id", "")
        record = self._selected_record()
        if record is None or not current_run:
            QMessageBox.information(self, "Check newer run", "请先选择一条证据。")
            return
        old_run = record.get("published_run_id", "")
        if old_run == current_run:
            QMessageBox.information(self, "Check newer run", "该证据已绑定当前最新发布运行。")
            return
        from gui_next.execution.compare import find_evidence_counterpart
        result = find_evidence_counterpart(self.evidence.root, current_run, record)
        if result["state"] == "CANDIDATE_MATCH":
            counterpart = result["counterpart"]
            summary = counterpart.get("Collocate", counterpart.get("Keyword", ""))
            msg = (f"Possible updated counterpart in Run #{current_run[-8:]}\n\n"
                   f"Old (Run #{old_run[-8:]}): {record.get('target', '')} / {summary}\n\n"
                   "Add Run B as additional evidence + link as UPDATED_COUNTERPART?")
            if QMessageBox.question(self, "Evidence Refresh", msg) == QMessageBox.Yes:
                new_rec = self.evidence.add_evidence(
                    evidence_type=record["evidence_type"],
                    published_run_id=current_run,
                    publication_manifest_hash=pointer.get("manifest_sha256", ""),
                    corpus_fingerprint=pointer.get("corpus_fingerprint", ""),
                    parameters_hash=pointer.get("params_hash", ""),
                    captured_snapshot={k: ("" if pd.isna(v) else v)
                                       for k, v in counterpart.items()},
                    fingerprint_parts=[counterpart.get("Target", ""),
                                       counterpart.get("Collocate",
                                                       counterpart.get("Keyword", ""))],
                    document_id=str(counterpart.get("Document_ID", "")),
                    target=str(counterpart.get("Target", "")),
                    locator={"sheet": "published_generation",
                             "published_run_id": current_run})
                self.evidence.add_lineage_link(record["evidence_id"],
                                               new_rec["evidence_id"],
                                               comparison_run_pair=f"{old_run}__{current_run}")
                self.evidence.log_refresh({
                    "claim_id": "", "old_evidence_id": record["evidence_id"],
                    "old_run": old_run, "new_evidence_id": new_rec["evidence_id"],
                    "new_run": current_run, "decision": "add_new_counterpart"})
                self.evidence.save()
                self.refresh()
        else:
            QMessageBox.information(self, "Evidence Refresh",
                                    f"在 Run #{current_run[-8:]} 中未找到对应证据。")

    def _replace_in_claim(self) -> None:
        """Replace an older evidence reference in a claim with its newer counterpart."""
        record = self._selected_record()
        if record is None:
            return
        evidence_id = record["evidence_id"]
        newer_id = self.evidence.newer_counterpart(evidence_id)
        if not newer_id:
            QMessageBox.information(self, "Replace in Claim",
                                    "该证据没有已链接的 newer counterpart;先运行 Check against newer run。")
            return
        refs = self.evidence.claim_refs(evidence_id)
        if not refs:
            QMessageBox.information(self, "Replace in Claim", "该证据未被任何 Claim 引用。")
            return
        claim_id = refs[0]
        self.evidence.replace_in_claim(claim_id, evidence_id, newer_id)
        self.evidence.log_refresh({
            "claim_id": claim_id, "old_evidence_id": evidence_id,
            "old_run": record.get("published_run_id", ""),
            "new_evidence_id": newer_id,
            "new_run": (self.evidence.get_evidence(newer_id) or {}).get("published_run_id", ""),
            "decision": "replace_in_claim"})
        self.evidence.save()
        self.refresh()

    # ------------------------------------------------------------------
    # evidence actions

    def _selected_record(self) -> Optional[Dict[str, Any]]:
        view = self._pattern_view if self._current_claim_id is not None else self._view
        index = view.currentIndex()
        if not index.isValid():
            return None
        row = view.model().row(index)
        return self.evidence.get_evidence(str(row.get("ID", "")))

    def _open_selected(self) -> None:
        record = self._selected_record()
        if record:
            self.show_evidence_detail(record)

    def _view_supporting_kwic(self, record: Dict[str, Any]) -> None:
        run_id = record.get("published_run_id", "")
        kwic = self.resolver.read_kwic(run_id)
        if kwic.empty:
            QMessageBox.information(self, "Supporting KWIC", "该已发布代际未归档 KWIC 数据。")
            return
        snap = record.get("captured_snapshot", {}) or {}
        needle = str(snap.get("Collocate") or snap.get("Modifier_Phrase") or "").lower()
        mask = pd.Series(True, index=kwic.index)
        if record.get("target") and "Target" in kwic.columns:
            mask &= kwic["Target"].astype(str) == record["target"]
        if needle and "Full_Context" in kwic.columns:
            mask &= kwic["Full_Context"].astype(str).str.lower().str.contains(needle, regex=False, na=False)
        rows = kwic[mask]
        if rows.empty:
            QMessageBox.information(self, "Supporting KWIC", "该已发布代际中没有匹配的 KWIC 行。")
            return
        dialog = SupportingKwicDialog(rows, self)
        if dialog.exec() != QDialog.Accepted:
            return
        pointer = self._pointer()
        added = 0
        for row in dialog.selected_rows():
            record_new = self.evidence.add_evidence(
                evidence_type="kwic",
                published_run_id=run_id,
                publication_manifest_hash=pointer.get("manifest_sha256", ""),
                corpus_fingerprint=pointer.get("corpus_fingerprint", ""),
                parameters_hash=pointer.get("params_hash", ""),
                captured_snapshot={k: ("" if pd.isna(v) else v) for k, v in row.items()
                                   if k in ("Keyword", "Target", "Left_Context", "Right_Context",
                                            "Full_Context", "Source", "Source_Normalized",
                                            "Document_ID", "Group")},
                fingerprint_parts=[row.get("Document_ID", ""), row.get("Target", ""),
                                   row.get("Left_Context", ""), row.get("Keyword", ""),
                                   row.get("Right_Context", "")],
                document_id=str(row.get("Document_ID", "")),
                target=str(row.get("Target", "")),
                locator={"sheet": "KWIC", "published_run_id": run_id},
            )
            if self._current_claim_id:
                self.evidence.claim_add_evidence(self._current_claim_id, record_new["evidence_id"])
            added += 1
        self.evidence.save()
        self.refresh()
        show_toast(self, f"已加入 {added} 条 supporting KWIC")

    # ------------------------------------------------------------------
    # delete / remove

    def _delete_selected(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        evidence_id = record["evidence_id"]
        refs = self.evidence.claim_refs(evidence_id)
        if refs:
            titles = ", ".join((self.evidence.get_claim(c) or {}).get("title", c) for c in refs)
            if QMessageBox.question(
                    self, "Evidence referenced",
                    f"该证据仍被 {len(refs)} 个 Claim 引用({titles})。\n"
                    "确定要连同引用一起删除证据记录吗?(Claim 本身保留)") != QMessageBox.Yes:
                return
            self.evidence.delete_evidence(evidence_id, force=True)
        else:
            if QMessageBox.question(self, "Delete Evidence", "删除该证据记录?") != QMessageBox.Yes:
                return
            self.evidence.delete_evidence(evidence_id)
        try:
            self.evidence.save()
        except EvidenceStateConflictError as exc:
            QMessageBox.warning(self, "写入冲突", str(exc))
            return
        self.refresh()
        show_toast(self, "Evidence 已删除")

    # ------------------------------------------------------------------

    def _export_packet(self) -> None:
        claim_id = self._current_claim_id
        if not claim_id:
            QMessageBox.information(self, "Export", "请先在左侧选择一个 Claim。")
            return
        claim = self.evidence.get_claim(claim_id) or {}
        lines = [f"# Claim: {claim.get('title', '')}", "",
                 f"- Claim ID: `{claim_id}`",
                 f"- Created: {claim.get('created_at', '')}",
                 "", "## Claim text", claim.get("claim_text", "") or "(空)", "",
                 "## Researcher note", claim.get("researcher_note", "") or "(空)", ""]
        for evidence_id in claim.get("evidence_ids", []):
            record = self.evidence.get_evidence(evidence_id)
            if not record:
                continue
            lines += [
                f"## Evidence {record['evidence_id']}",
                f"- Type: {TYPE_LABELS.get(record['evidence_type'], record['evidence_type'])}",
                f"- Target: {record.get('target', '')}",
                f"- Published Run: `{record.get('published_run_id', '')}`",
                f"- Manifest hash: `{record.get('publication_manifest_hash', '')}`",
                f"- Corpus fingerprint: `{record.get('corpus_fingerprint', '')}`",
                f"- Parameters hash: `{record.get('parameters_hash', '')}`",
                f"- Document: {record.get('document_id', '')}",
                f"- Note: {record.get('researcher_note', '')}",
                "",
                "```json",
                json.dumps(record.get("captured_snapshot", {}), ensure_ascii=False, indent=2),
                "```", "",
            ]
        default = str(self.evidence.root / "08_evidence" /
                      f"claim_{claim_id}_packet.md")
        path, _ = QFileDialog.getSaveFileName(self, "Export Claim Evidence Packet",
                                              default, "Markdown (*.md)")
        if not path:
            return
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        show_toast(self, f"Exported to {path}", action_text="打开文件夹",
                   action=lambda: self._reveal(path))

    @staticmethod
    def _reveal(path: str) -> None:
        import os
        import platform
        import subprocess
        folder = str(Path(path).parent)
        try:
            if platform.system() == "Windows":
                os.startfile(folder)  # noqa: S606
            elif platform.system() == "Darwin":
                subprocess.run(["open", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        except OSError:
            pass
