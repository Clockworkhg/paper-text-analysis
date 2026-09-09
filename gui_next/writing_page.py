# -*- coding: utf-8 -*-
"""Writing page: Research Draft workspace (Phase 3B).

Left: document/section tree. Center: block editor (PROSE editors,
CLAIM/EVIDENCE reference cards, private research notes). Right: Evidence
Rail (Claims / Evidence / Inspector tabs) for inserting references.

Data discipline: PROSE is the researcher's own writing; CLAIM_REF and
EVIDENCE_REF blocks store only references and always re-read their content
from the EvidenceStore and the published generation. RESEARCH_NOTE blocks
are private process notes, excluded from Clean export.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.data.evidence_store import EvidenceStore
from gui_next.data.generations import GenerationResolver
from gui_next.widgets import EmptyState
from gui_next.data.writing_store import (
    BLOCK_CLAIM_REF,
    BLOCK_EVIDENCE_REF,
    BLOCK_PROSE,
    BLOCK_RESEARCH_NOTE,
    WritingSectionNotEmptyError,
    WritingStore,
    WritingStateConflictError,
)


def _section_numbers(store: WritingStore) -> Dict[str, str]:
    numbers: Dict[str, str] = {}

    def walk(parent_id: Optional[str], prefix: str = "") -> None:
        for i, section in enumerate(store._children(parent_id), start=1):
            sid = section["section_id"]
            numbers[sid] = f"{prefix}{i}"
            walk(sid, f"{prefix}{i}.")

    walk(None)
    return numbers


def _summary_line(store: WritingStore, evidence_store: EvidenceStore,
                  resolver: GenerationResolver, section_id: str) -> str:
    from gui_next.data.writing_export import section_summary
    s = section_summary(store, evidence_store, resolver, section_id)
    integrity = s["integrity"]
    color = theme.SUCCESS if integrity == "VERIFIED" else (
        theme.WARNING if integrity in ("ISSUES",) else theme.MUTED)
    return (f"Claims: {s['claims']} · Evidence: {s['evidence']} · "
            f"Runs: {', '.join(s['runs']) or '–'} · "
            f"Integrity: {integrity}")


class WritingPage(QWidget):
    def __init__(self, store: WritingStore, evidence_store: EvidenceStore,
                 resolver: GenerationResolver, published_provider,
                 inspector, navigate, parent=None, router=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.evidence = evidence_store
        self.resolver = resolver
        self.published_provider = published_provider
        self.inspector = inspector
        self.navigate = navigate
        self.router = router
        self._current_section_id: Optional[str] = None
        self._editors: Dict[str, QPlainTextEdit] = {}
        self._save_timers: Dict[str, QTimer] = {}
        self._building = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        self._title_label = QLabel("Writing")
        self._title_label.setObjectName("PageTitle")
        header.addWidget(self._title_label)
        header.addStretch(1)
        self._validate_button = QPushButton("Validate Evidence")
        self._validate_button.clicked.connect(self._validate)
        self._export_draft_button = QPushButton("Export Draft")
        self._export_draft_button.clicked.connect(lambda: self._export("draft"))
        self._export_clean_button = QPushButton("Export Clean")
        self._export_clean_button.clicked.connect(lambda: self._export("clean"))
        for button in (self._validate_button, self._export_draft_button,
                       self._export_clean_button):
            header.addWidget(button)
        root.addLayout(header)

        self._preflight_label = QLabel("")
        self._preflight_label.setWordWrap(True)
        self._preflight_label.setStyleSheet("background: transparent;")
        root.addWidget(self._preflight_label)

        self.splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self.splitter, 1)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Sections")
        self._tree.setObjectName("Nav")
        self._tree.itemSelectionChanged.connect(self._on_section_selected)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._section_menu)
        self.splitter.addWidget(self._tree)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(12, 12, 12, 12)
        center_layout.setSpacing(8)
        self._section_title_label = QLabel("–")
        self._section_title_label.setObjectName("SectionTitle")
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        center_layout.addWidget(self._section_title_label)
        center_layout.addWidget(self._summary_label)

        self._blocks_host = QVBoxLayout()
        self._blocks_host.setSpacing(10)
        center_layout.addLayout(self._blocks_host, 1)

        block_buttons = QHBoxLayout()
        for label, handler in (
                ("+ Prose", lambda: self._add_block(BLOCK_PROSE)),
                ("+ Research Note", lambda: self._add_block(BLOCK_RESEARCH_NOTE)),
                ("Insert Claim (Ctrl+Shift+C)", self._insert_claim_dialog),
                ("Insert Evidence", self._insert_evidence_dialog)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            block_buttons.addWidget(button)
        block_buttons.addStretch(1)
        center_layout.addLayout(block_buttons)
        self.splitter.addWidget(center)

        # ---- Evidence Rail --------------------------------------------
        rail = QTabWidget()
        self._rail_claims = QListWidget()
        self._rail_claims.itemDoubleClicked.connect(self._insert_claim_from_rail)
        self._rail_claims.itemClicked.connect(self._show_rail_claim)
        rail.addTab(self._rail_claims, "Claims")
        self._rail_evidence_list = QListWidget()
        self._rail_evidence_list.itemDoubleClicked.connect(self._insert_evidence_from_rail)
        self._rail_evidence_list.itemClicked.connect(self._show_rail_evidence)
        rail.addTab(self._rail_evidence_list, "Evidence")
        self.splitter.addWidget(rail)

        self.splitter.setSizes([220, 760, 320])

        # ---- Keyboard ---------------------------------------------------
        insert_claim_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        insert_claim_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        insert_claim_shortcut.activated.connect(self._insert_claim_dialog)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(800)
        self._autosave_timer.timeout.connect(self._flush_pending_edit)

        self._pending_edit: Optional[tuple[str, str]] = None

        self._ensure_document()
        self._empty_state = EmptyState(self)
        self._empty_state.configure(
            "No writing sections yet",
            "创建第一个章节开始写作。Evidence/Claim 引用随后可插入任意章节。",
            "New Section", self._new_section)
        root.addWidget(self._empty_state)
        self._refresh_tree()
        self._update_empty_visibility()

    # ------------------------------------------------------------------
    # document bootstrap

    def _ensure_document(self) -> None:
        """No auto-creation: opening a project must stay read-only.

        The writing document is created on the researcher's first explicit
        action (new section / add block), never on page open.
        """
        self._title_label.setText(
            f"Writing — {self.store.state.get('title', 'Research Draft')}"
            if self.store.has_document else "Writing")

    # ------------------------------------------------------------------
    # section tree

    def _refresh_tree(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        numbers = _section_numbers(self.store)

        def add_children(parent_id: Optional[str], tree_parent: QTreeWidget or QTreeWidgetItem):
            for section in self.store._children(parent_id):
                sid = section["section_id"]
                item = QTreeWidgetItem([f"{numbers.get(sid, '')} {section['title']}".strip()])
                item.setData(0, Qt.UserRole, sid)
                tree_parent.addTopLevelItem(item)
                add_children(sid, item)

        add_children(None, self._tree)
        self._tree.expandAll()
        self._tree.blockSignals(False)
        if self._current_section_id:
            matches = self._tree.findItems(
                numbers.get(self._current_section_id, "§"), Qt.MatchStartsWith)
            if matches:
                self._tree.setCurrentItem(matches[0])
        self._title_label.setText(
            f"Writing — {self.store.state.get('title', 'Research Draft')}"
            if self.store.has_document else "Writing")
        self._update_empty_visibility()

    def _update_empty_visibility(self) -> None:
        has_document = self.store.has_document
        self._empty_state.setVisible(not has_document)
        self.splitter.setVisible(has_document)

    def _selected_section_id(self) -> Optional[str]:
        items = self._tree.selectedItems()
        return items[0].data(0, Qt.UserRole) if items else self._current_section_id

    def _on_section_selected(self) -> None:
        self._flush_pending_edit()
        sid = self._selected_section_id()
        if sid:
            self._render_section(sid)

    # ------------------------------------------------------------------
    # section CRUD

    def _new_section(self, parent_id: Optional[str] = None) -> None:
        title, ok = QInputDialog.getText(self, "New Section", "章节标题:")
        if not ok or not title.strip():
            return
        self.create_section(title, parent_id=parent_id)

    def create_section(self, title: str, parent_id: Optional[str] = None) -> str:
        """Non-interactive section creation (the single document-write entry)."""
        if not self.store.has_document:
            self.store.new_document(skeleton=False)
            self._update_empty_visibility()
        sid = self.store.add_section(title, parent_id=parent_id)
        self.store.save()
        self._refresh_tree()
        self._current_section_id = sid
        self._render_section(sid)
        return sid

    def _new_subsection(self) -> None:
        sid = self._selected_section_id()
        self._new_section(parent_id=sid)

    def _rename_section(self) -> None:
        sid = self._selected_section_id()
        section = self.store.get_section(sid) if sid else None
        if not section:
            return
        title, ok = QInputDialog.getText(self, "Rename Section", "章节标题:",
                                         text=section["title"])
        if ok and title.strip():
            self.store.rename_section(sid, title)
            self.store.save()
            self._refresh_tree()
            self._render_section(sid)

    def _delete_section(self) -> None:
        sid = self._selected_section_id()
        section = self.store.get_section(sid) if sid else None
        if not section:
            return
        try:
            removed = self.store.delete_section(sid)
        except WritingSectionNotEmptyError as exc:
            if QMessageBox.question(
                    self, "Delete Section",
                    f"{exc}\n确定删除该章节及其全部内容/子章节?") != QMessageBox.Yes:
                return
            self.store.delete_section(sid, force=True)
        else:
            if removed == 0 and QMessageBox.question(
                    self, "Delete Section", "删除该章节?") != QMessageBox.Yes:
                return
        if self._current_section_id == sid:
            self._current_section_id = None
            self._clear_blocks()
        self.store.save()
        self._refresh_tree()

    def _move_section(self, direction: int) -> None:
        sid = self._selected_section_id()
        if sid:
            self.store.move_section(sid, direction)
            self.store.save()
            self._refresh_tree()

    def _section_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("New Section", lambda: self._new_section())
        menu.addAction("New Subsection", lambda: self._new_subsection())
        menu.addAction("Rename", lambda: self._rename_section())
        menu.addSeparator()
        menu.addAction("Move ↑", lambda: self._move_section(-1))
        menu.addAction("Move ↓", lambda: self._move_section(+1))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self._delete_section())
        menu.exec(self._tree.mapToGlobal(pos))

    # ------------------------------------------------------------------
    # block rendering

    def _clear_blocks(self) -> None:
        while self._blocks_host.count():
            item = self._blocks_host.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def save_context(self) -> bool:
        """Ctrl+S: flush the debounced prose edit immediately."""
        if not self.store.has_document:
            return False
        self._flush_pending_edit()
        return True

    def _flush_pending_edit(self) -> None:
        if not self._pending_edit:
            return
        section_id, block_id = self._pending_edit
        editor = self._editors.get(block_id)
        if editor is None:
            self._pending_edit = None
            return
        try:
            self.store.update_block_text(section_id, block_id,
                                         editor.toPlainText())
            self.store.save()
        except WritingStateConflictError as exc:
            self._conflict_dialog(exc)
        self._pending_edit = None

    def _on_prose_changed(self, section_id: str, block_id: str) -> None:
        self._pending_edit = (section_id, block_id)
        self._autosave_timer.start()  # debounced autosave

    def _render_section(self, section_id: str) -> None:
        self._current_section_id = section_id
        section = self.store.get_section(section_id)
        if section is None:
            return
        self._flush_pending_edit()
        self._clear_blocks()
        self._editors.clear()
        self._section_title_label.setText(section["title"])
        self._summary_label.setText(_summary_line(
            self.store, self.evidence, self.resolver, section_id))

        for block in section.get("blocks", []):
            self._blocks_host.addWidget(self._block_widget(section_id, block))
        self._blocks_host.addStretch(1)

    def _block_widget(self, section_id: str, block: Dict[str, Any]) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        block_id = block["block_id"]

        if block["type"] in (BLOCK_PROSE, BLOCK_RESEARCH_NOTE):
            if block["type"] == BLOCK_RESEARCH_NOTE:
                label_text = "Private research note(过程备注,不进入 Clean 导出)"
                color = theme.WARNING
            else:
                label_text = "PROSE"
                color = theme.MUTED
            caption = QLabel(label_text)
            caption.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent;")
            layout.addWidget(caption)
            editor = QPlainTextEdit(block.get("text", ""))
            editor.setFixedHeight(96 if block["type"] == BLOCK_RESEARCH_NOTE else 140)
            editor.setObjectName("ProseEditor")
            layout.addWidget(editor)
            self._editors[block_id] = editor
            timer = QTimer(frame)
            timer.setSingleShot(True)
            timer.setInterval(800)
            timer.timeout.connect(lambda: self._on_prose_changed(section_id, block_id))
            editor.textChanged.connect(timer.start)
            editor.textChanged.connect(lambda: self._on_prose_changed(section_id, block_id))
        elif block["type"] == BLOCK_CLAIM_REF:
            claim = self.evidence.get_claim(block.get("claim_id", "")) or {}
            caption = QLabel("CLAIM")
            caption.setStyleSheet(f"color: {theme.PRIMARY}; font-size: 11px; font-weight: 600;")
            layout.addWidget(caption)
            body = QLabel(
                f"“{claim.get('title', block.get('claim_id', ''))}”\n"
                f"{claim.get('claim_text', '')}\n"
                f"Evidence: {len(claim.get('evidence_ids', []))} items")
            body.setWordWrap(True)
            body.setStyleSheet("background: transparent;")
            layout.addWidget(body)
            runs = sorted({
                e.get("published_run_id", "")
                for eid in claim.get("evidence_ids", [])
                for e in [self.evidence.get_evidence(eid) or {}]
            })
            runs_label = QLabel("Runs: " + ", ".join("#" + r[-8:] for r in runs))
            runs_label.setStyleSheet(f"color: {theme.MUTED}; background: transparent; font-size: 11px;")
            layout.addWidget(runs_label)
            open_button = QPushButton("Open Claim")
            open_button.setFlat(True)
            open_button.clicked.connect(
                lambda _checked=False, cid=claim.get("claim_id", ""):
                self.router.navigate_to("证据", cid, {"kind": "claim"})
                if self.router is not None else self.navigate("证据"))
            layout.addWidget(open_button, 0, Qt.AlignLeft)
        elif block["type"] == BLOCK_EVIDENCE_REF:
            record = self.evidence.get_evidence(block.get("evidence_id", "")) or {}
            snap = record.get("captured_snapshot", {}) or {}
            integrity, detail = self._evidence_integrity(record)
            caption = QLabel("EVIDENCE CARD")
            caption.setStyleSheet(f"color: {theme.PRIMARY}; font-size: 11px; font-weight: 600;")
            layout.addWidget(caption)
            if record.get("evidence_type") == "kwic":
                body = QLabel(
                    f"{snap.get('Source', '')} / {snap.get('Source_Normalized', '')}\n"
                    f"{snap.get('Left_Context', '')} [{snap.get('Keyword', '')}] "
                    f"{snap.get('Right_Context', '')}\n"
                    f"document_id: {record.get('document_id', '')}")
            else:
                body = QLabel(f"{record.get('target', '')} · {snap.get('Collocate',
                              snap.get('Modifier_Phrase', snap.get('Expression', '')))}\n"
                              f"Freq {snap.get('Frequency', '–')} · "
                              f"MI {snap.get('MI_Score', '–')} · G² {snap.get('Log_Likelihood', '–')}")
            body.setWordWrap(True)
            body.setStyleSheet("background: transparent;")
            layout.addWidget(body)
            state_line = "✓ Verified"
            color = theme.SUCCESS
            if record.get("published_run_id", "") != (self.published_provider() or {}).get(
                    "published_run_id", "") and integrity == "VERIFIED":
                state_line = "✓ Verified · Older published run"
            if integrity != "VERIFIED":
                state_line = f"⚠ {integrity}: {detail}"
                color = theme.ERROR
            state_label = QLabel(state_line)
            state_label.setStyleSheet(f"color: {color}; background: transparent; font-size: 11px;")
            layout.addWidget(state_label)
            run_label = QLabel(f"Run #{record.get('published_run_id', '')[-8:]}")
            run_label.setStyleSheet(f"color: {theme.MUTED}; background: transparent; font-size: 11px;")
            layout.addWidget(run_label)

        # Block controls live in a context menu — the prose stays the visual
        # first class (#24).
        frame.setContextMenuPolicy(Qt.CustomContextMenu)
        frame.customContextMenuRequested.connect(
            lambda pos, s=section_id, b=block_id: self._block_menu(frame, s, b, frame.mapToGlobal(pos)))
        return frame

    def _block_menu(self, frame, section_id: str, block_id: str, global_pos) -> None:
        menu = QMenu(self)
        menu.addAction("上移 ↑", lambda: self._move_block(section_id, block_id, -1))
        menu.addAction("下移 ↓", lambda: self._move_block(section_id, block_id, +1))
        menu.addSeparator()
        menu.addAction("Remove from Writing", lambda: self._remove_block(section_id, block_id))
        menu.exec(global_pos)

    def _evidence_integrity(self, record: Dict[str, Any]) -> tuple[str, str]:
        from gui_next.data.writing_export import evidence_integrity
        return evidence_integrity(record, self.resolver)

    def _move_block(self, section_id: str, block_id: str, direction: int) -> None:
        self._flush_pending_edit()
        self.store.move_block(section_id, block_id, direction)
        self.store.save()
        self._render_section(section_id)

    def _remove_block(self, section_id: str, block_id: str) -> None:
        """Removing a block only unlinks the writing reference — the claim or
        evidence record itself stays in the Evidence store."""
        removed = self.store.remove_block(section_id, block_id)
        self.store.save()
        self._render_section(section_id)

    def _add_block(self, block_type: str) -> None:
        sid = self._current_section_id
        if not sid:
            QMessageBox.information(self, "Writing", "请先选择一个章节。")
            return
        block = self.store.add_block(sid, block_type, text="")
        self.store.save()
        self._render_section(sid)
        if block["type"] in (BLOCK_PROSE, BLOCK_RESEARCH_NOTE):
            self._editors[block["block_id"]].setFocus()

    # ------------------------------------------------------------------
    # insert claim / evidence

    def _insert_claim_dialog(self) -> None:
        claims = self.evidence.claims()
        if not claims:
            QMessageBox.information(self, "Insert Claim", "尚无 Claim;先在证据页创建。")
            return
        items = [f"{c['title']}  ({len(c['evidence_ids'])} evidence)" for c in claims]
        choice, ok = QInputDialog.getItem(self, "Insert Claim", "选择 Claim:", items, 0, False)
        if not ok:
            return
        index = items.index(choice)
        self._insert_claim_ref(claims[index]["claim_id"])

    def _insert_claim_ref(self, claim_id: str) -> None:
        sid = self._current_section_id
        if not sid:
            sid = self.store.sections()[0]["section_id"] if self.store.sections() else None
        if not sid:
            QMessageBox.information(self, "Insert Claim", "请先创建章节。")
            return
        block = self.store.add_block(sid, BLOCK_CLAIM_REF, claim_id=claim_id)
        self.store.save()
        if self._current_section_id == sid:
            self._render_section(sid)
        else:
            self._render_section(sid)

    def _insert_evidence_ref(self, evidence_id: str) -> None:
        sid = self._current_section_id
        if not sid:
            sid = self.store.sections()[0]["section_id"] if self.store.sections() else None
        if not sid:
            QMessageBox.information(self, "Insert Evidence", "请先创建章节。")
            return
        self.store.add_block(sid, BLOCK_EVIDENCE_REF, evidence_id=evidence_id)
        self.store.save()
        if self._current_section_id == sid:
            self._render_section(sid)

    def _insert_claim_from_rail(self, item: QListWidgetItem) -> None:
        claim_id = item.data(Qt.UserRole)
        if claim_id:
            self._insert_claim_ref(claim_id)

    def _insert_evidence_from_rail(self, item: QListWidgetItem) -> None:
        evidence_id = item.data(Qt.UserRole)
        if evidence_id:
            self._insert_evidence_ref(evidence_id)

    def _show_rail_evidence(self, item: QListWidgetItem) -> None:
        evidence_id = item.data(Qt.UserRole)
        record = self.evidence.get_evidence(evidence_id) if evidence_id else None
        if record:
            from gui_next.data.writing_export import evidence_integrity
            state, detail = evidence_integrity(record, self.resolver)
            self.inspector.show_evidence(record, state=state, state_detail=detail)

    def _show_rail_claim(self, item: QListWidgetItem) -> None:
        claim_id = item.data(Qt.UserRole)
        claim = self.evidence.get_claim(claim_id) if claim_id else None
        if claim:
            self.inspector.show_claim(claim, len(claim.get("evidence_ids", [])))

    def _insert_evidence_dialog(self) -> None:
        records = self.evidence.evidence_records()
        if not records:
            QMessageBox.information(self, "Insert Evidence", "证据箱为空;先在分析页添加证据。")
            return
        items = [f"{r.get('target', '')} · {r.get('evidence_type', '')} · "
                 f"#{r.get('published_run_id', '')[-8:]} · {r.get('evidence_id', '')[:13]}"
                 for r in records]
        choice, ok = QInputDialog.getItem(self, "Insert Evidence", "选择证据:", items, 0, False)
        if ok:
            index = items.index(choice)
            self._insert_evidence_ref(records[index]["evidence_id"])

    # ------------------------------------------------------------------
    # rail

    def _refresh_rail(self) -> None:
        section = self.store.get_section(self._current_section_id) if self._current_section_id else None
        in_section_claims = set()
        if section:
            for block in section.get("blocks", []):
                if block.get("type") == BLOCK_CLAIM_REF:
                    in_section_claims.add(block.get("claim_id"))
        self._rail_claims.clear()
        for claim in self.evidence.claims():
            if claim["claim_id"] in in_section_claims:
                continue
            item = QListWidgetItem(
                f"{claim['title']}  ({len(claim['evidence_ids'])} evidence) — 双击插入本章节")
            item.setData(Qt.UserRole, claim["claim_id"])
            self._rail_claims.addItem(item)

        self._rail_evidence_list.clear()
        for record in self.evidence.evidence_records():
            integrity, _ = self._evidence_integrity(record)
            state_text = "✓" if integrity == "VERIFIED" else "⚠"
            item = QListWidgetItem(
                f"{state_text} {record.get('evidence_type', '')} · "
                f"{record.get('target', '')} · #{record.get('published_run_id', '')[-8:]} "
                f"— 双击插入本章节")
            item.setData(Qt.UserRole, record["evidence_id"])
            self._rail_evidence_list.addItem(item)

    # ------------------------------------------------------------------
    # validation + export

    def _validate(self) -> None:
        if not self.store.has_document:
            QMessageBox.information(self, "Validate Evidence",
                                    "尚无写作文档;创建章节后即可校验证据完整性。")
            return
        from gui_next.data.writing_export import validate_writing
        report = validate_writing(self.store, self.evidence, self.resolver,
                                  section_id=self._current_section_id)
        self._preflight_label.setText(
            f"Writing integrity — ✓ {report['verified']} evidence verified · "
            f"⚠ {report['source_unavailable']} source unavailable · "
            f"✕ {report['integrity_error']} integrity error · "
            f"⚠ {report['missing_reference']} missing reference")
        if report["items"]:
            details = "; ".join(
                f"{item['kind']}[{item['ref'][:14]}]={item['state']}"
                for item in report["items"] if item["state"] != "VERIFIED") or "全部 VERIFIED"
            self._preflight_label.setToolTip(details)

    def _export(self, mode: str) -> None:
        if not self.store.has_document:
            QMessageBox.information(self, "Export",
                                    "尚无写作文档;创建章节后即可导出。")
            return
        from gui_next.data.writing_export import export_markdown
        try:
            self._flush_pending_edit()
            result = export_markdown(self.store, self.evidence, self.resolver,
                                     self.store.root, mode=mode,
                                     section_id=self._current_section_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        preflight = result["preflight"]
        issues = preflight["source_unavailable"] + preflight["integrity_error"] + \
            preflight["missing_reference"]
        message = (f"已导出({mode}):\n{result['path']}\n\n"
                   f"Evidence Appendix: {result['evidence_appendix']} 条\n"
                   f"Integrity: ✓ {preflight['verified']} verified")
        if issues:
            message += (f"\n⚠ {issues} 项完整性问题(详见文件顶部 WARNING)。"
                        if mode == "clean" else
                        f"\n⚠ {issues} 项完整性问题已随 Draft 记录。")
        QMessageBox.information(self, "Export", message)

    # ------------------------------------------------------------------
    # conflict

    def _conflict_dialog(self, exc: Exception) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Writing conflict")
        box.setText("Writing document changed in another session.\n"
                    f"{exc}\n\nReload 以载入另一会话的更改?")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        if box.exec() == QMessageBox.Yes:
            self.store.reload()
            self._refresh_tree()
            if self._current_section_id:
                self._render_section(self._current_section_id)

    # called by app when the project is refreshed
    def refresh(self) -> None:
        self._refresh_tree()
        self._refresh_rail()
        if self._current_section_id:
            self._render_section(self._current_section_id)
