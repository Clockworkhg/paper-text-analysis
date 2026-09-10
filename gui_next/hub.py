# -*- coding: utf-8 -*-
"""Project Hub — the product launcher (Phase 4B #2/#5/#26).

Shown instead of an empty shell when the app starts without a project
argument. First run: welcome + New/Open. Later runs: recent project cards
(path / document count / last opened — never research content), with
Missing state and Remove-from-recent for stale paths.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.appdata import load_recent_projects, project_missing, remove_recent_project
from gui_next.project_validate import ProjectValidation, validate_project
from gui_next.version import APP_NAME, VERSION

STATE_TEXT = {
    "VALID_PROJECT": ("✓", "可用", theme.SUCCESS),
    "LEGACY_PROJECT": ("△", "旧版项目(只读兼容)", theme.WARNING),
    "INCOMPLETE_PROJECT": ("✕", "不完整", theme.ERROR),
    "NOT_A_PROJECT": ("✕", "不是 CADS 项目", theme.ERROR),
    "UNSUPPORTED_VERSION": ("✕", "版本不受支持", theme.ERROR),
}


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(theme.SP_16, theme.SP_16, theme.SP_16, theme.SP_16)
    layout.setSpacing(theme.SP_8)
    return frame, layout


class ProjectCard(QFrame):
    """One recent project; click opens, ✕ removes from the list only."""

    open_requested = Signal(str)

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.path = entry.get("path", "")
        missing = project_missing(entry)
        validation: Optional[ProjectValidation] = None
        if not missing:
            validation = validate_project(self.path)

        row = QHBoxLayout(self)
        row.setContentsMargins(theme.SP_16, theme.SP_12, theme.SP_12, theme.SP_12)
        row.setSpacing(theme.SP_12)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(entry.get("display_name") or Path(self.path).name)
        title.setStyleSheet("font-weight: 600; font-size: 14px; background: transparent;")
        detail_bits = [self.path]
        if entry.get("last_opened"):
            detail_bits.append(f"上次打开 {str(entry['last_opened'])[:16].replace('T', ' ')}")
        detail = QLabel(" · ".join(detail_bits))
        detail.setObjectName("Muted")
        detail.setStyleSheet("font-size: 12px; background: transparent;")
        detail.setFixedWidth(380)
        font_metrics = detail.fontMetrics()
        detail.setText(font_metrics.elidedText(
            " · ".join(detail_bits), Qt.ElideMiddle, 380))
        text.addWidget(title)
        text.addWidget(detail)

        if missing:
            state_glyph, state_text, state_color = "✕", "Missing", theme.ERROR
        elif validation is not None:
            state_glyph, state_text, state_color = STATE_TEXT.get(
                validation.state, ("–", validation.state, theme.MUTED))
            if validation.state == "INCOMPLETE_PROJECT":
                detail.setText(" · ".join(
                    [self.path, "缺少:" + "、".join(validation.missing)]))
        else:
            state_glyph, state_text, state_color = "–", "未知", theme.MUTED
        state_label = QLabel(state_glyph + " " + state_text)
        state_label.setStyleSheet(
            f"color: {state_color}; font-weight: 600; background: transparent;")
        if missing:
            state_label.setToolTip("项目路径已失效;可从最近列表移除(不会删除项目文件)。")
        row.addLayout(text, 1)
        row.addWidget(state_label, 0, Qt.AlignTop)

        remove = QPushButton("✕")
        remove.setFixedWidth(28)
        remove.setToolTip("从最近列表移除(不删除项目文件)")
        remove.clicked.connect(self._remove)
        row.addWidget(remove, 0, Qt.AlignTop)
        self._remove_button = remove

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.button() == Qt.LeftButton:
            self.open_requested.emit(self.path)
        super().mousePressEvent(event)

    def _remove(self) -> None:
        remove_recent_project(self.path)
        self.deleteLater()


class ProjectHub(QWidget):
    """Welcome / Recent projects launcher."""

    open_project_requested = Signal(str)   # existing, validated path
    new_project_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._validate_before_open = True

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
        root.setContentsMargins(theme.SP_32, theme.SP_32, theme.SP_32, theme.SP_32)
        root.setSpacing(theme.SP_16)
        root.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        title = QLabel(f"Welcome to {APP_NAME}")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Corpus-assisted discourse research workspace")
        subtitle.setObjectName("Muted")
        subtitle.setAlignment(Qt.AlignCenter)
        root.addWidget(title)
        root.addWidget(subtitle)

        buttons = QHBoxLayout()
        buttons.setSpacing(theme.SP_12)
        new_button = QPushButton("New Project")
        new_button.setObjectName("Primary")
        new_button.setFixedWidth(200)
        new_button.clicked.connect(self.new_project_requested.emit)
        open_button = QPushButton("Open Existing Project")
        open_button.setFixedWidth(200)
        open_button.clicked.connect(self._pick_project)
        buttons.addStretch(1)
        buttons.addWidget(new_button)
        buttons.addWidget(open_button)
        buttons.addStretch(1)
        root.addLayout(buttons)

        chain = QLabel("Corpus → Analysis → Review → Evidence → Writing")
        chain.setObjectName("Muted")
        chain.setAlignment(Qt.AlignCenter)
        root.addWidget(chain)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(
            f"color: {theme.ERROR}; background: transparent; font-weight: 600;")
        self._error_label.setAlignment(Qt.AlignCenter)
        self._error_label.hide()
        root.addWidget(self._error_label)

        recent_caption = QLabel("RECENT PROJECTS")
        recent_caption.setObjectName("InspectorTitle")
        recent_caption.setAlignment(Qt.AlignCenter)
        root.addSpacing(theme.SP_16)
        root.addWidget(recent_caption)
        self._recent_host = QVBoxLayout()
        self._recent_host.setSpacing(theme.SP_8)
        root.addLayout(self._recent_host)

        footer = QLabel(f"{APP_NAME} {VERSION}")
        footer.setObjectName("Muted")
        footer.setAlignment(Qt.AlignCenter)
        root.addSpacing(theme.SP_24)
        root.addWidget(footer)
        self.refresh_recent()

    # ------------------------------------------------------------------

    def refresh_recent(self) -> None:
        while self._recent_host.count():
            item = self._recent_host.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        entries = load_recent_projects()
        if not entries:
            empty = QLabel("尚无最近项目 — 从上方开始,或打开已有项目目录。")
            empty.setObjectName("Muted")
            empty.setAlignment(Qt.AlignCenter)
            self._recent_host.addWidget(empty)
            return
        for entry in entries[:10]:
            card = ProjectCard(entry)
            card.open_requested.connect(self._try_open)
            self._recent_host.addWidget(card)
        self._recent_host.addStretch(1)

    def show_validation_error(self, validation: ProjectValidation) -> None:
        self._error_label.setText(
            f"This folder is not a CADS Workbench project.\n{validation.path}\n"
            + (f"缺失:{'、'.join(validation.missing)}" if validation.missing
               else validation.detail))
        self._error_label.show()

    def _try_open(self, path: str) -> None:
        if self._validate_before_open:
            validation = validate_project(path)
            if not validation.openable:
                self.show_validation_error(validation)
                return
        self.open_project_requested.emit(path)

    def _pick_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择项目目录(project.json 所在目录)")
        if not path:
            return
        self._try_open(path)


def open_project_dialog(parent: QWidget) -> str:
    """Standalone open dialog used by the File menu; returns '' on cancel."""
    return QFileDialog.getExistingDirectory(
        parent, "选择项目目录(project.json 所在目录)")
