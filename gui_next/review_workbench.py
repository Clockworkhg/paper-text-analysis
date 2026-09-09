# -*- coding: utf-8 -*-
"""Semantic Review Workbench: single-candidate keyboard coding UI.

Fixed shortcuts (active whenever the note field is not being edited):

    1 Positive   2 Negative   3 Neutral   4 Mixed
    X Exclude    U Uncertain
    Enter        Save + Next (immediately advances, no confirmation)
    Shift+Enter  Previous
    O            Open the full source document
    F2           focus the note field; Esc returns focus to coding

Saving writes through SemanticReviewStore (the only write boundary) and
moves to the next uncoded item.
"""

from __future__ import annotations

import os
import platform
import subprocess
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.data.contracts import (
    DECISION_EXCLUDED,
    DECISION_MIXED,
    DECISION_NEGATIVE,
    DECISION_NEUTRAL,
    DECISION_POSITIVE,
    DECISION_UNCERTAIN,
)
from gui_next.data.review_store import SemanticReviewStore

DECISION_LABELS = {
    DECISION_POSITIVE: "1 Positive",
    DECISION_NEGATIVE: "2 Negative",
    DECISION_NEUTRAL: "3 Neutral",
    DECISION_MIXED: "4 Mixed",
    DECISION_EXCLUDED: "X Exclude",
    DECISION_UNCERTAIN: "U Uncertain",
}
DECISION_COLORS = {
    DECISION_POSITIVE: theme.SUCCESS,
    DECISION_NEGATIVE: theme.ERROR,
    DECISION_NEUTRAL: theme.MUTED,
    DECISION_MIXED: theme.WARNING,
    DECISION_EXCLUDED: theme.MUTED,
    DECISION_UNCERTAIN: theme.PRIMARY,
}


def _highlight(context: str, *needles: str) -> str:
    """Escape-free simple highlighter: bold the candidate and target."""
    import html

    text = html.escape(context)
    for needle in filter(None, needles):
        escaped = html.escape(needle)
        lower, esc_lower = text.lower(), escaped.lower()
        start = 0
        parts = []
        while True:
            index = lower.find(esc_lower, start)
            if index < 0:
                parts.append(text[start:])
                break
            parts.append(text[start:index])
            parts.append(f'<b style="color:{theme.PRIMARY}">{text[index:index + len(escaped)]}</b>')
            start = index + len(escaped)
        text = "".join(parts)
        if len(text) > 20000:
            break
    return text


class SemanticReviewWorkbench(QWidget):
    """Keyboard-driven coding of semantic-prosody candidates."""

    def __init__(self, store: SemanticReviewStore, inspector, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.review = store
        self.inspector = inspector
        self._locked = False
        self.setFocusPolicy(Qt.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 16)
        root.setSpacing(12)

        # --- Header: progress + item metadata -------------------------
        header = QFrame()
        header.setObjectName("Card")
        header_layout = QGridLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setHorizontalSpacing(24)
        header_layout.setVerticalSpacing(2)

        self._progress_label = QLabel("0 / 0")
        self._progress_label.setObjectName("StatValue")
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(220)
        self._progress_bar.setFormat("已编码 %p%")

        self._stale_banner = QLabel("")
        self._stale_banner.setWordWrap(True)
        self._stale_banner.setStyleSheet(
            f"color: {theme.WARNING}; background: transparent; font-weight: 600;"
        )
        self._stale_banner.hide()

        self._target_label = QLabel("–")
        self._candidate_label = QLabel("–")
        self._candidate_label.setStyleSheet(f"color: {theme.PRIMARY}; font-weight: 600; background: transparent;")
        self._source_label = QLabel("–")
        self._doc_label = QLabel("–")

        def _cell(row: int, col: int, caption: str, widget: QLabel) -> None:
            caption_label = QLabel(caption)
            caption_label.setObjectName("StatLabel")
            header_layout.addWidget(caption_label, row, col)
            header_layout.addWidget(widget, row + 1, col)

        header_layout.addWidget(self._progress_label, 0, 0)
        header_layout.addWidget(self._progress_bar, 1, 0)
        _cell(0, 1, "TARGET", self._target_label)
        _cell(0, 2, "CANDIDATE", self._candidate_label)
        _cell(0, 3, "SOURCE / DOCUMENT", self._source_label)
        header_layout.setColumnStretch(3, 1)
        header_layout.addWidget(self._stale_banner, 2, 0, 1, 4)
        root.addWidget(header)

        # --- Center: extended context ---------------------------------
        self._context = QLabel("（无上下文）")
        self._context.setWordWrap(True)
        self._context.setTextFormat(Qt.RichText)
        self._context.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._context.setStyleSheet(
            f"background: {theme.SURFACE}; border: 1px solid {theme.BORDER};"
            f"border-radius: 6px; padding: 20px; font-size: 14px; line-height: 150%;"
        )
        context_scroll = QScrollArea()
        context_scroll.setWidgetResizable(True)
        context_scroll.setFrameShape(QFrame.NoFrame)
        context_scroll.setWidget(self._context)
        root.addWidget(context_scroll, 1)

        # --- Right column would crowd; coding row below context -------
        coding = QFrame()
        coding.setObjectName("Card")
        coding_layout = QHBoxLayout(coding)
        coding_layout.setContentsMargins(16, 12, 16, 12)
        coding_layout.setSpacing(8)

        self._buttons: Dict[str, QPushButton] = {}
        for decision, label in DECISION_LABELS.items():
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, d=decision: self._apply_decision(d))
            self._buttons[decision] = button
            coding_layout.addWidget(button)

        coding_layout.addStretch(1)
        open_button = QPushButton("打开全文 (O)")
        open_button.clicked.connect(self._open_document)
        coding_layout.addWidget(open_button)
        root.addWidget(coding)

        # --- Note row --------------------------------------------------
        note_row = QHBoxLayout()
        note_caption = QLabel("研究备注")
        note_caption.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        self._note = QLineEdit()
        self._note.setObjectName("NoteInput")
        self._note.setPlaceholderText("可选;Enter 保存并跳下一条;Esc 退出备注框")
        self._note.installEventFilter(self)
        self._note_caption = note_caption
        note_row.addWidget(note_caption)
        note_row.addWidget(self._note, 1)
        root.addLayout(note_row)

        help_row = QHBoxLayout()
        self._summary_hint = QLabel("1/2/3/4 编码 · X Exclude · U Uncertain · Enter 下一条")
        self._summary_hint.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        help_button = QPushButton("键盘快捷键 (? 或 F1)")
        help_button.setObjectName("Flat")
        help_button.clicked.connect(self.show_keyboard_help)
        help_row.addWidget(self._summary_hint, 1)
        help_row.addWidget(help_button)
        root.addLayout(help_row)

        # Coding/text keys are handled in keyPressEvent (so they can still be
        # typed inside the note field); no QShortcut for text keys.
        self._shortcuts = []

        self.refresh()

    # ------------------------------------------------------------------
    # key handling

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        key, mods = event.key(), event.modifiers()
        if mods & Qt.ControlModifier and key == Qt.Key_Z:
            self.undo_last()
            event.accept()
            return
        if mods & Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            self.previous()
            event.accept()
            return
        if mods & Qt.ShiftModifier:
            super().keyPressEvent(event)
            return
        decisions = {
            Qt.Key_1: DECISION_POSITIVE,
            Qt.Key_2: DECISION_NEGATIVE,
            Qt.Key_3: DECISION_NEUTRAL,
            Qt.Key_4: DECISION_MIXED,
            Qt.Key_X: DECISION_EXCLUDED,
            Qt.Key_U: DECISION_UNCERTAIN,
        }
        if key in decisions:
            self._apply_decision(decisions[key])
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.save_and_next()
            event.accept()
            return
        if key == Qt.Key_O:
            self._open_document()
            event.accept()
            return
        if key == Qt.Key_F2:
            self._focus_note()
            event.accept()
            return
        if key == Qt.Key_F1 or key == Qt.Key_Question:
            self.show_keyboard_help()
            event.accept()
            return
        super().keyPressEvent(event)

    def show_keyboard_help(self) -> None:
        """Keyboard reference popup — visible on demand, never in the way (#22)."""
        from PySide6.QtWidgets import QDialog
        dialog = QDialog(self)
        dialog.setWindowTitle("复核键盘快捷键")
        dialog.setMinimumSize(420, 300)
        layout = QVBoxLayout(dialog)
        help_text = QLabel(
            "<b>编码</b><br>"
            "1 Positive &nbsp; 2 Negative &nbsp; 3 Neutral &nbsp; 4 Mixed<br>"
            "X Exclude &nbsp; U Uncertain<br><br>"
            "<b>导航</b><br>"
            "Enter 保存并下一条 &nbsp; Shift+Enter 上一条<br><br>"
            "<b>其他</b><br>"
            "O 打开全文 &nbsp; F2 备注框(Esc 退出)<br>"
            "Ctrl+Z 撤销上一次编码<br><br>"
            "备注框内字母数字照常输入。"
        )
        help_text.setWordWrap(True)
        help_text.setTextFormat(Qt.RichText)
        layout.addWidget(help_text)
        close = QPushButton("关闭 (Esc)")
        close.setObjectName("Primary")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignRight)
        dialog.exec()

    def eventFilter(self, obj, event) -> bool:
        """In the note field: Enter saves, Esc leaves; everything else types."""
        from PySide6.QtCore import QEvent

        if obj is self._note and event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            editing = event.type() == QEvent.FocusIn
            self._note_caption.setText("研究备注(编辑中)" if editing else "研究备注")
            self._note_caption.setStyleSheet(
                f"color: {theme.PRIMARY}; font-weight: 600; background: transparent;"
                if editing else f"color: {theme.MUTED}; background: transparent;")
        if obj is self._note and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    self.previous()
                else:
                    self.save_and_next()
                return True
            if event.key() == Qt.Key_Escape:
                self._unfocus_note()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # rendering

    def set_locked(self, locked: bool) -> None:
        """Analysis-run lock: review writes are disabled while a run is active."""
        self._locked = locked
        for button in self._buttons.values():
            button.setEnabled(not locked)
        self._note.setEnabled(not locked)
        if locked:
            self._stale_banner.setText("🔒 分析运行中,复核写入已锁定(候选集即将更新)。")
            self._stale_banner.setStyleSheet(
                f"color: {theme.WARNING}; background: transparent; font-weight: 600;")
            self._stale_banner.show()
        else:
            self._stale_banner.hide()
            self.refresh()

    def refresh(self) -> None:
        progress = self.review.progress()
        self._progress_label.setText(f"{progress['coded']} / {progress['total']}")
        self._progress_bar.setMaximum(max(progress['total'], 1))
        self._progress_bar.setValue(progress["coded"])

        if self.review.status() == "STALE":
            self._stale_banner.setText(
                f"⚠ 复核状态 STALE({self.review.stale_summary()})——"
                "旧人工结果已保留但未计入当前进度,需要 reconciliation/migration;新编码正常写入。"
            )
            self._stale_banner.show()
        else:
            self._stale_banner.hide()

        item = self.review.current_item()
        if item is None:
            self._target_label.setText("–")
            self._candidate_label.setText("–")
            self._source_label.setText("–")
            self._doc_label.setText("")
            self._context.setText("没有可复核的候选条目。先运行 project review 生成复核工作簿。")
            return

        self._target_label.setText(item["target"] or "–")
        self._candidate_label.setText(f"{item['kind']}: {item['expression']}" if item["kind"] else item["expression"])
        self._source_label.setText(item["document_id"] or "–")

        decision = self.review.decisions.get(item["item_id"], {})
        self._note.setText(self.review.note_for(item["item_id"]))

        context = self.review.context_for(item)
        if not context:
            context = "(该候选的 KWIC 语境未取样 — 请在分析页 Concordance 中按 Document_ID 查找)"
        needle = item["expression"] or item["target"]
        self._context.setText(_highlight(context, needle, item["target"]))

        for key, button in self._buttons.items():
            active = decision.get("decision") == key
            color = DECISION_COLORS[key]
            button.setStyleSheet(
                f"font-weight: 600; {'background:' + theme.SELECTED + '; color:' + color + '; border-color:' + color};"
                if active else ""
            )

    # ------------------------------------------------------------------
    # actions

    def _apply_decision(self, decision: str) -> None:
        item = self.review.current_item()
        if item is None or self._locked:
            return
        self.review.set_decision(item["item_id"], decision, note=self._note.text())
        self.review.set_cursor(self.review.cursor + 1)
        self.review.save()
        self.refresh()

    def save_and_next(self) -> None:
        """Persist note/cursor and advance (no confirmation dialog)."""
        item = self.review.current_item()
        if item is None or self._locked:
            return
        if item["item_id"] in self.review.decisions:
            self.review.set_decision(item["item_id"],
                                     self.review.decisions[item["item_id"]]["decision"],
                                     note=self._note.text())
        else:
            self.review.set_note(item["item_id"], self._note.text())
        self.review.set_cursor(self.review.cursor + 1)
        self.review.save()
        self.refresh()

    def previous(self) -> None:
        self.review.set_cursor(self.review.cursor - 1)
        self.review.save()
        self.refresh()

    def undo_last(self) -> None:
        """Ctrl+Z: undo the most recent decision/note change (session + persisted)."""
        item_id = self.review.undo()
        if item_id is None:
            self.inspector.show_empty("没有可撤销的操作。")
            return
        self.refresh()

    def _open_document(self) -> None:
        item = self.review.current_item()
        if item is None:
            return
        path = self.review.document_path(item)
        if path is None:
            self.inspector.show_empty(f"未找到文档全文:{item.get('document_id', '')}")
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

    def _focus_note(self) -> None:
        self._note.setFocus()

    def _unfocus_note(self) -> None:
        self._note.clearFocus()
        self.setFocus()
