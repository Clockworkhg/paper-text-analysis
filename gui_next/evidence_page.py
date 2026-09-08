# -*- coding: utf-8 -*-
"""Evidence page: Inbox / Claims / Evidence list / Claim workspace.

Claim -> Pattern -> KWIC -> Document -> Published Run. All evidence resolves
against immutable published generations (runs/published/<run_id>/) via
GenerationResolver — never against the current project root.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QTextEdit,
    QTreeView,
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
from gui_next.models import DataFrameModel
from gui_next.pages import _muted, _table  # shared builders

TYPE_LABELS = {
    "kwic": "KWIC",
    "collocate_pattern": "Pattern · Collocate",
    "phrase_pattern": "Pattern · Phrase",
    "group_pattern": "Pattern · Group",
}


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
        layout.addWidget(_muted("以下 KWIC 行来自该证据绑定的已发布代际(非当前最新运行)。"
                                "选择行后点击下方按钮加入证据。"))
        self.table = _table(rows.reset_index(drop=True))
        self.table.setSelectionBehavior(QTableView.SelectRows)
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

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("证据")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._new_claim_button = QPushButton("＋ New Claim (N)")
        self._new_claim_button.setObjectName("Primary")
        self._new_claim_button.clicked.connect(self._new_claim_dialog)
        self._export_button = QPushButton("Export Claim Evidence Packet")
        self._export_button.clicked.connect(self._export_packet)
        header.addWidget(self._export_button)
        header.addWidget(self._new_claim_button)
        root.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        # ---- Left: Inbox / Claims ------------------------------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("")
        self._tree.setObjectName("Nav")
        self._tree.itemSelectionChanged.connect(self._on_tree_selection)
        left_layout.addWidget(self._tree, 1)
        claim_buttons = QHBoxLayout()
        up = QPushButton("↑")
        up.setFixedWidth(34)
        up.clicked.connect(lambda: self._move_claim(-1))
        down = QPushButton("↓")
        down.setFixedWidth(34)
        down.clicked.connect(lambda: self._move_claim(+1))
        delete_claim = QPushButton("Delete Claim")
        delete_claim.clicked.connect(self._delete_claim)
        claim_buttons.addWidget(up)
        claim_buttons.addWidget(down)
        claim_buttons.addWidget(delete_claim, 1)
        left_layout.addLayout(claim_buttons)
        splitter.addWidget(left)

        # ---- Center: filters + evidence table -------------------------
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索:target / source / country / 自由文本… (Ctrl+F)")
        self._search.textChanged.connect(self._refresh_table)
        self._type_combo = QComboBox()
        self._type_combo.addItem("全部类型", "")
        for key, label in TYPE_LABELS.items():
            self._type_combo.addItem(label, key)
        self._type_combo.currentIndexChanged.connect(self._refresh_table)
        self._run_combo = QComboBox()
        self._run_combo.currentIndexChanged.connect(self._refresh_table)
        filters.addWidget(self._search, 2)
        filters.addWidget(self._type_combo, 1)
        filters.addWidget(self._run_combo, 1)
        center_layout.addLayout(filters)

        self._model = DataFrameModel(pd.DataFrame(), self)
        self._view = QTableView()
        self._view.setModel(self._model)
        self._view.setAlternatingRowColors(False)
        self._view.verticalHeader().setVisible(False)
        self._view.horizontalHeader().setStretchLastSection(True)
        self._view.setSelectionBehavior(QTableView.SelectRows)
        self._view.setEditTriggers(QTableView.NoEditTriggers)
        self._view.setSortingEnabled(True)
        self._view.setWordWrap(False)
        self._view.doubleClicked.connect(lambda index: self._open_evidence(index.row()))
        center_layout.addWidget(self._view, 1)

        self._claim_header = QLabel("")
        self._claim_header.setWordWrap(True)
        self._claim_header.setStyleSheet("background: transparent;")
        center_layout.addWidget(self._claim_header)
        splitter.addWidget(center)
        splitter.setSizes([240, 860])

        root.addWidget(_muted(
            "快捷键:E=加入证据(分析页) · N=新建 Claim · Enter=打开选中证据 · "
            "Delete=从当前 Claim 移除 · Ctrl+F=搜索。证据只能绑定已 COMMITTED 的已发布代际。"
        ))

        # ---- Keyboard --------------------------------------------------
        for keys, handler in (
            ("N", self._new_claim_dialog),
            ("Return", self._open_selected),
            ("Delete", self._delete_selected),
            ("Ctrl+F", self._focus_search),
        ):
            shortcut = QKeySequence(keys)
            from PySide6.QtGui import QShortcut
            sc = QShortcut(shortcut, self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(handler)

        self.refresh()

    # ------------------------------------------------------------------
    # data access

    def _pointer(self) -> Dict[str, Any]:
        return self.published_provider() or {}

    def _integrity_for(self, record: Dict[str, Any]) -> str:
        artifact_hashes = {
            entry["relative_path"]: entry["sha256"]
            for entry in (self.resolver.load_manifest(
                record.get("published_run_id", "")) or {}).get("artifacts", [])
        } if False else None
        return "VERIFIED"

    def _integrity(self, record: Dict[str, Any]) -> tuple[str, str]:
        """(state, detail) via the resolver; never falls back to latest."""
        provenance = {
            "publication_manifest_hash": record.get("publication_manifest_hash", ""),
        }
        result = self.resolver.integrity(
            record.get("published_run_id", ""),
            publication_manifest_hash=provenance["publication_manifest_hash"],
            stored_artifact_hashes=record.get("artifact_hashes") or None,
        )
        return result.state, result.detail

    # ------------------------------------------------------------------
    # rendering

    def refresh(self) -> None:
        self._refresh_tree()
        self._refresh_table()
        self._refresh_claim_header()

    def _refresh_tree(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        progress = self.evidence.progress() if hasattr(self.evidence, "progress") else None
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

    def _on_tree_selection(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.UserRole) or ("inbox", None)
        kind, claim_id = data
        self._current_claim_id = claim_id if kind == "claim" else None
        self._refresh_table()
        self._refresh_claim_header()

    def _refresh_claim_header(self) -> None:
        claim = self.evidence.get_claim(self._current_claim_id) if self._current_claim_id else None
        if claim:
            self._claim_header.setText(
                f"Claim:“{claim['title']}”\n{claim.get('claim_text', '')}\n"
                f"备注:{claim.get('researcher_note') or '–'} · "
                f"证据 {len(claim['evidence_ids'])} 条")
        else:
            self._claim_header.setText("")

    def _refresh_table(self) -> None:
        records = self.evidence.evidence_records()
        type_filter = self._type_combo.currentData() or ""
        run_filter = self._run_combo.currentData() or ""
        needle = self._search.text().strip().lower()

        runs = sorted({r.get("published_run_id", "") for r in records}, reverse=True)
        current_runs = [self._run_combo.itemData(i) for i in range(self._run_combo.count())]
        if runs != [r for r in current_runs if r]:
            self._run_combo.blockSignals(True)
            self._run_combo.clear()
            self._run_combo.addItem("全部运行", "")
            for run_id in runs:
                self._run_combo.addItem(f"#{run_id[-8:]}", run_id)
            self._run_combo.blockSignals(False)
            run_filter = ""

        rows = []
        for record in records:
            if type_filter and record.get("evidence_type") != type_filter:
                continue
            if run_filter and record.get("published_run_id") != run_filter:
                continue
            if self._current_claim_id:
                claim = self.evidence.get_claim(self._current_claim_id) or {}
                if record["evidence_id"] not in claim.get("evidence_ids", []):
                    continue
            hay = " ".join([
                record.get("target", ""), record.get("document_id", ""),
                json.dumps(record.get("captured_snapshot", {}), ensure_ascii=False),
            ]).lower()
            if needle and needle not in hay:
                continue
            refs = self.evidence.claim_refs(record["evidence_id"])
            claim_titles = ", ".join(
                (self.evidence.get_claim(cid) or {}).get("title", cid) for cid in refs)
            rows.append({
                "Type": TYPE_LABELS.get(record["evidence_type"], record["evidence_type"]),
                "Evidence": evidence_summary(record),
                "Run": f"#{record.get('published_run_id', '')[-8:]}",
                "Target": record.get("target", ""),
                "Claims": claim_titles or "Inbox",
                "Integrity": self._integrity(record)[0],
                "Created": record.get("created_at", ""),
                "ID": record["evidence_id"],
            })
        self._model.set_dataframe(pd.DataFrame(rows))
        self._view.resizeColumnsToContents()

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
        if QMessageBox.question(
                self, "Delete Claim",
                f"删除 Claim“{claim.get('title', '')}”?\n证据记录本身不会被删除。") != QMessageBox.Yes:
            return
        self.evidence.delete_claim(self._current_claim_id)
        self._current_claim_id = None
        self.evidence.save()
        self.refresh()

    # ------------------------------------------------------------------
    # evidence actions

    def _selected_record(self) -> Optional[Dict[str, Any]]:
        index = self._view.currentIndex()
        if not index.isValid():
            return None
        row = self._model.df().iloc[index.row()]
        return self.evidence.get_evidence(self._lookup_id(row))

    def _lookup_id(self, row: pd.Series) -> str:
        return str(row.get("ID", ""))

    def _open_selected(self) -> None:
        record = self._selected_record()
        if record:
            self.show_evidence_detail(record)

    def _open_evidence(self, row_index: int) -> None:
        row = self._model.df().iloc[row_index]
        evidence_id = self._lookup_id(row)
        record = self.evidence.get_evidence(evidence_id)
        if record:
            self.show_evidence_detail(record)

    def show_evidence_detail(self, record: Dict[str, Any]) -> None:
        state, detail = self._integrity(record)
        snap = record.get("captured_snapshot", {}) or {}
        if record["evidence_type"] == "kwic":
            context = (f"{snap.get('Left_Context', '')} [{snap.get('Keyword', '')}] "
                       f"{snap.get('Right_Context', '')}")
            self.inspector.show_kwic({
                "Keyword": snap.get("Keyword", ""),
                "Target": record.get("target", ""),
                "Left_Context": snap.get("Left_Context", ""),
                "Right_Context": snap.get("Right_Context", ""),
                "Full_Context": snap.get("Full_Context", context),
                "Document_ID": record.get("document_id", ""),
                "Source": snap.get("Source", ""),
                "Source_Normalized": snap.get("Source_Normalized", ""),
                "Group": snap.get("Group", ""),
            })
        else:
            self.inspector.show_empty(evidence_summary(record))

        # RUN PROVENANCE block (Evidence -> Run)
        from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
        block = QFrame()
        block.setObjectName("InspectorBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        for key, value in (
            ("Published Run", f"#{record.get('published_run_id', '')[-8:]}"),
            ("Corpus fingerprint", record.get("corpus_fingerprint", "")),
            ("Parameters hash", record.get("parameters_hash", "")),
            ("Manifest", "Verified" if state == "VERIFIED" else f"{state}: {detail}"),
        ):
            key_label = QLabel(key)
            key_label.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px; background: transparent;")
            value_label = QLabel(str(value))
            value_label.setWordWrap(True)
            value_label.setStyleSheet("background: transparent;")
            layout.addWidget(key_label)
            layout.addWidget(value_label)
        self.inspector._body_layout.insertWidget(0, block)

        refs = self.evidence.claim_refs(record["evidence_id"])
        actions = [("Open Run", lambda: self.navigate("运行记录"))]
        if record["evidence_type"] in ("collocate_pattern", "phrase_pattern"):
            actions.append(("View supporting KWIC", lambda: self._view_supporting_kwic(record)))
        self.inspector.show_actions(actions)
        self.inspector.set_badge(f"Integrity: {state}", theme.SUCCESS if state == "VERIFIED" else theme.ERROR)

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
        self.inspector.set_badge(f"已加入 {added} 条 supporting KWIC", theme.SUCCESS)

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

    def _focus_search(self) -> None:
        self._search.setFocus()

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
                 f"## Researcher note", claim.get("researcher_note", "") or "(空)", ""]
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
        default = root_dir = str(self.evidence.root / "08_evidence" /
                                 f"claim_{claim_id}_packet.md")
        path, _ = QFileDialog.getSaveFileName(self, "Export Claim Evidence Packet",
                                              default, "Markdown (*.md)")
        if not path:
            return
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        QMessageBox.information(self, "Export", f"已导出:{path}")


from PySide6.QtCore import Signal  # noqa: E402
