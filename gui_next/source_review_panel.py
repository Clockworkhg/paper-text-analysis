# -*- coding: utf-8 -*-
"""Source/Country review panel: evidence inspection + Accept/Change/Uncertain/Exclude.

Embedded beside the Sources table on the Corpus page. Keyboard-first:

    A Accept · C Change (focus country field) · U Uncertain · X Exclude
    Enter Save & Next · Shift+Enter Previous · F2 country · F3 note

Letters typed inside the country/note fields behave as normal text; Enter
inside them commits and advances. Decisions persist via
SourceCountryReviewStore (the only write boundary) — the corpus itself is
never modified.
"""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.data.contracts import (
    SOURCE_ACCEPT,
    SOURCE_CHANGE,
    SOURCE_EXCLUDE,
    SOURCE_UNCERTAIN,
)

DECISION_TITLES = {
    SOURCE_ACCEPT: "✓ 已接受",
    SOURCE_CHANGE: "✎ 已修改",
    SOURCE_UNCERTAIN: "? 不确定",
    SOURCE_EXCLUDE: "✕ 已排除",
}


class SourceReviewPanel(QWidget):
    """Evidence + decision panel for one source at a time."""

    def __init__(self, review_store, inspector, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.review = review_store
        self.inspector = inspector
        self.index = 0
        self.setFocusPolicy(Qt.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self._progress = QLabel("0 / 0")
        self._progress.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        root.addWidget(self._progress)

        self._heading = QLabel("–")
        self._heading.setObjectName("InspectorHeading")
        self._heading.setWordWrap(True)
        root.addWidget(self._heading)

        self._meta = QLabel("–")
        self._meta.setWordWrap(True)
        self._meta.setStyleSheet("background: transparent;")
        root.addWidget(self._meta)

        self._evidence = QLabel("")
        self._evidence.setWordWrap(True)
        self._evidence.setTextFormat(Qt.RichText)
        self._evidence.setStyleSheet(
            f"background: {theme.BG}; border: 1px solid {theme.BORDER};"
            f"border-radius: 6px; padding: 12px;"
        )
        root.addWidget(self._evidence, 1)

        boundary = QLabel("ⓘ 国别为自动推断的辅助变量,使用前必须人工复核;此处决定写入复核记录,不修改原始语料。")
        boundary.setWordWrap(True)
        boundary.setStyleSheet(f"color: {theme.WARNING}; background: transparent; font-size: 11px;")
        root.addWidget(boundary)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        country_caption = QLabel("国别 (F2)")
        country_caption.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        self._country = QLineEdit()
        self._country.setPlaceholderText("修改国别时填写")
        self._country.installEventFilter(self)
        note_caption = QLabel("备注 (F3)")
        note_caption.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        self._note = QLineEdit()
        self._note.setPlaceholderText("可选")
        self._note.installEventFilter(self)
        grid.addWidget(country_caption, 0, 0)
        grid.addWidget(self._country, 1, 0, 1, 2)
        grid.addWidget(note_caption, 2, 0)
        grid.addWidget(self._note, 3, 0, 1, 2)
        root.addLayout(grid)

        buttons = QHBoxLayout()
        self._buttons: Dict[str, QPushButton] = {}
        for key, label in (
            (SOURCE_ACCEPT, "Accept (A)"),
            (SOURCE_CHANGE, "Change (C)"),
            (SOURCE_UNCERTAIN, "Uncertain (U)"),
            (SOURCE_EXCLUDE, "Exclude (X)"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, d=key: self._apply(d))
            self._buttons[key] = button
            buttons.addWidget(button)
        root.addLayout(buttons)

        nav = QHBoxLayout()
        prev_button = QPushButton("← 上一条 (Shift+Enter)")
        prev_button.clicked.connect(self.previous)
        next_button = QPushButton("Save & Next (Enter)")
        next_button.setObjectName("Primary")
        next_button.clicked.connect(self.save_and_next)
        nav.addWidget(prev_button)
        nav.addWidget(next_button, 1)
        root.addLayout(nav)

        self._decision_label = QLabel("")
        self._decision_label.setStyleSheet("background: transparent; font-weight: 600;")
        root.addWidget(self._decision_label)

        self.refresh()

    # ------------------------------------------------------------------

    def set_locked(self, locked: bool) -> None:
        """Analysis-run lock: review writes are disabled while a run is active."""
        for button in self._buttons.values():
            button.setEnabled(not locked)
        self._country.setEnabled(not locked)
        self._note.setEnabled(not locked)
        if locked:
            self._decision_label.setText("🔒 分析运行中,复核写入已锁定(来源表/候选集即将更新)。")
            self._decision_label.setStyleSheet(
                f"background: transparent; color: {theme.WARNING}; font-weight: 600;")

    def refresh(self) -> None:
        progress = self.review.progress()
        text = f"总数 {progress['total']} · 已复核 {progress['decided']} · 待复核 {progress['pending']}"
        if progress.get("status") == "STALE":
            text += f" · ⚠ STALE({self.review.stale_summary()})——旧结果已保留未计入,需 reconciliation/migration"
        self._progress.setText(text)
        items = self.review.items
        if not items:
            self._heading.setText("无来源数据")
            self._meta.setText("导入语料或运行机构合并后,这里显示来源清单。")
            self._evidence.setText("")
            return
        self.index = max(0, min(self.index, len(items) - 1))
        item = items[self.index]
        decision = self.review.decisions.get(item["source"], {})

        self._heading.setText(item["source"])
        original = item.get("original") or "–"
        self._meta.setText(
            f"original: {original}\nnormalized: {item['source']}\ndocuments: {item.get('documents', '–')}"
        )

        lines = [f"<b>Suggested country:</b> {item.get('suggested_country') or '(无)'}"]
        if item.get("confidence") is not None:
            lines.append(f"<b>Confidence:</b> {item['confidence']}")
        lines.append("<b>Evidence:</b>")
        evidence_lines = item.get("evidence") or ["(无自动证据记录)"]
        for line in evidence_lines:
            lines.append(f"&nbsp;&nbsp;• {line}")
        self._evidence.setText("<br>".join(lines))

        self._country.setText(str(decision.get("country", "")) or str(item.get("suggested_country") or ""))
        self._note.setText(str(decision.get("note", "")))
        if decision:
            color = theme.SUCCESS if decision.get("decision") == SOURCE_ACCEPT else theme.PRIMARY
            self._decision_label.setText(f"当前决定:{DECISION_TITLES.get(decision.get('decision'), decision.get('decision'))}")
            self._decision_label.setStyleSheet(f"background: transparent; font-weight: 600; color: {color};")
        else:
            self._decision_label.setText("当前决定:未复核")
            self._decision_label.setStyleSheet(f"background: transparent; color: {theme.MUTED};")

        for key, button in self._buttons.items():
            active = decision.get("decision") == key
            button.setStyleSheet(
                f"font-weight: 600; border-color: {theme.PRIMARY}; color: {theme.PRIMARY};" if active else ""
            )

    def set_index(self, index: int) -> None:
        if self.review.items:
            self.index = max(0, min(index, len(self.review.items) - 1))
            self.refresh()

    # ------------------------------------------------------------------

    def _apply(self, decision: str) -> None:
        items = self.review.items
        if not items:
            return
        source = items[self.index]["source"]
        self.review.set_decision(source, decision, country=self._country.text(), note=self._note.text())
        self.review.save()
        self.refresh()

    def save_and_next(self) -> None:
        """Commit: a changed country means Change; otherwise Accept; then advance."""
        items = self.review.items
        if not items:
            return
        item = items[self.index]
        source = item["source"]
        country = self._country.text().strip()
        suggested = str(item.get("suggested_country") or "").strip()
        existing = self.review.decisions.get(source, {})
        if country and country != suggested:
            decision = SOURCE_CHANGE
        elif existing.get("decision"):
            decision = existing["decision"]
        else:
            decision = SOURCE_ACCEPT
        self.review.set_decision(source, decision, country=country, note=self._note.text())
        self.review.save()
        self.set_index(self.index + 1)

    def previous(self) -> None:
        self.set_index(self.index - 1)

    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        key, mods = event.key(), event.modifiers()
        if mods & Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            self.previous()
            event.accept()
            return
        if mods & Qt.ShiftModifier:
            super().keyPressEvent(event)
            return
        actions = {
            Qt.Key_A: SOURCE_ACCEPT,
            Qt.Key_C: SOURCE_CHANGE,
            Qt.Key_U: SOURCE_UNCERTAIN,
            Qt.Key_X: SOURCE_EXCLUDE,
        }
        if key in actions:
            if key == Qt.Key_C:
                self._country.setFocus()
                event.accept()
                return
            self._apply(actions[key])
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.save_and_next()
            event.accept()
            return
        if key == Qt.Key_F2:
            self._country.setFocus()
            event.accept()
            return
        if key == Qt.Key_F3:
            self._note.setFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if obj in (self._country, self._note) and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    self.previous()
                else:
                    self.save_and_next()
                return True
            if event.key() == Qt.Key_Escape:
                self.setFocus()
                return True
        return super().eventFilter(obj, event)
