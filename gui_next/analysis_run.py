# -*- coding: utf-8 -*-
"""Analysis run UI: the lifecycle panel and the New Analysis Run config view.

RunPanel — live status of the current run: stage, step, elapsed time,
indeterminate progress, latest log line, Cancel / View log / Copy
diagnostics. No fake percentages: the shared pipeline reports stage-level
progress only.

RunConfigView — the New Analysis Run form. Every parameter maps 1:1 onto an
existing shared/ CLI capability (targets, group_by, MI threshold,
POS/translate, sanity gate); pipeline-fixed values (window tokens, phrase
length) are shown read-only instead of being invented as tunables.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme
from gui_next.data.health import HealthState
from gui_next.execution.events import RunState

STATE_COLORS = {
    RunState.IDLE.value: theme.MUTED,
    RunState.PREPARING.value: theme.PRIMARY,
    RunState.RUNNING.value: theme.PRIMARY,
    RunState.CANCELLING.value: theme.WARNING,
    RunState.ANALYSIS_SUCCEEDED.value: theme.PRIMARY,
    RunState.PUBLISHING.value: theme.PRIMARY,
    RunState.SUCCEEDED.value: theme.SUCCESS,
    RunState.PUBLISH_FAILED.value: theme.ERROR,
    RunState.FAILED.value: theme.ERROR,
    RunState.CANCELLED.value: theme.MUTED,
    RunState.INTERRUPTED.value: theme.WARNING,
}

STEP_HINTS = (
    ("国别已回写", "country join"),
    ("合并", "corpus merge"),
    ("检索目标", "modifier extraction"),
    ("分组方式", "grouping"),
    ("复核", "review artifacts"),
    ("方法", "method reports"),
    ("发布", "publishing"),
)


def _step_from_log(line: str) -> str:
    for needle, label in STEP_HINTS:
        if needle in line:
            return label
    return ""


def _fmt_elapsed(seconds: int) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class RunPanel(QFrame):
    """Live lifecycle panel for the current/last analysis run."""

    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._started_on = QTimer(self)
        self._started_on.timeout.connect(self._tick)
        self._elapsed_seconds = 0

        grid = QGridLayout(self)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)

        self._run_label = QLabel("Run –")
        self._run_label.setObjectName("InspectorHeading")
        self._state_label = QLabel("IDLE")
        self._state_label.setStyleSheet(f"color: {theme.MUTED}; font-weight: 600; background: transparent;")

        grid.addWidget(self._run_label, 0, 0)
        grid.addWidget(self._state_label, 0, 1)
        grid.addWidget(QLabel(""), 0, 2)

        self._stage_label = QLabel("阶段:–")
        self._stage_label.setStyleSheet("background: transparent;")
        self._elapsed_label = QLabel("Elapsed 00:00:00")
        self._elapsed_label.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        grid.addWidget(self._stage_label, 1, 0)
        grid.addWidget(self._elapsed_label, 1, 1)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate: stage-level progress only
        self._progress.setVisible(False)
        self._progress.setFixedHeight(12)
        self._step_label = QLabel("")
        self._step_label.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        grid.addWidget(self._progress, 2, 0, 1, 2)
        grid.addWidget(self._step_label, 2, 2)

        self._latest_label = QLabel("Latest –")
        self._latest_label.setStyleSheet(f"color: {theme.MUTED}; background: transparent;")
        grid.addWidget(self._latest_label, 3, 0, 1, 2)

        buttons = QHBoxLayout()
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self.cancel_requested.emit)
        self._log_button = QPushButton("View log")
        self._log_button.clicked.connect(self._show_log)
        self._copy_button = QPushButton("Copy diagnostics")
        self._copy_button.clicked.connect(self._copy_diagnostics)
        self._copy_button.hide()
        buttons.addWidget(self._cancel_button)
        buttons.addWidget(self._log_button)
        buttons.addWidget(self._copy_button)
        buttons.addStretch(1)
        grid.addLayout(buttons, 4, 0, 1, 3)

    # ------------------------------------------------------------------

    def set_run(self, run_id: str, params_summary: str, output_dir: str) -> None:
        self._run_label.setText(f"Run {run_id}")
        self._run_label.setToolTip(params_summary + f"\n输出/工作目录: {output_dir}")

    def set_state(self, state: str, message: str) -> None:
        color = STATE_COLORS.get(state, theme.MUTED)
        self._state_label.setText(state)
        self._state_label.setStyleSheet(
            f"color: {color}; font-weight: 600; background: transparent;")
        self._stage_label.setText(f"阶段:{message or '–'}")

        active = state in (RunState.PREPARING.value, RunState.RUNNING.value, RunState.CANCELLING.value)
        self._progress.setVisible(active)
        self._cancel_button.setVisible(state in (
            RunState.PREPARING.value, RunState.RUNNING.value))
        if state == RunState.CANCELLING.value:
            self._step_label.setText("正在等待当前步骤安全结束……")
        if state in (RunState.SUCCEEDED.value, RunState.FAILED.value,
                     RunState.CANCELLED.value, RunState.INTERRUPTED.value):
            self._started_on.stop()
            self._copy_button.setVisible(state in (RunState.FAILED.value, RunState.INTERRUPTED.value))
        else:
            self._copy_button.hide()

    def begin_elapsed(self) -> None:
        self._elapsed_seconds = 0
        self._elapsed_label.setText("Elapsed 00:00:00")
        self._started_on.start(1000)

    def _tick(self) -> None:
        self._elapsed_seconds += 1
        self._elapsed_label.setText(f"Elapsed {_fmt_elapsed(self._elapsed_seconds)}")

    def append_log(self, line: str) -> None:
        self.logs_last = line
        self.full_log = (self.full_log + "\n" + line)[-200_000:]
        self._latest_label.setText("Latest " + line[:160])
        step = _step_from_log(line)
        if step and self._progress.isVisible():
            self._step_label.setText(f"当前步骤:{step}")

    logs_last = ""
    full_log = ""

    def diagnostics_text(self) -> str:
        return "\n".join([
            f"Run: {self._run_label.text()}",
            f"State: {self._state_label.text()}",
            f"Stage: {self._stage_label.text()}",
            f"Elapsed: {self._elapsed_label.text()}",
            f"Latest: {self._latest_label.text()}",
        ])

    def _copy_diagnostics(self) -> None:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        run_text = self.diagnostics_text()
        extra = getattr(self, "error_detail", "")
        clipboard.setText(run_text + ("\n\n" + extra if extra else ""))

    error_detail = ""

    def _show_log(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("运行日志")
        dialog.resize(760, 520)
        layout = QVBoxLayout(dialog)
        view = QTextBrowser()
        view.setPlainText(getattr(self, "full_log", "") or "(无日志)")
        layout.addWidget(view)
        close = QPushButton("关闭")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()


class RunConfigView(QFrame):
    """New Analysis Run configuration (in-page view, not an immediate start)."""

    start_requested = Signal(dict)     # params dict
    sanity_requested = Signal()
    back_requested = Signal()

    def __init__(self, store, health, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.store = store
        self.health = health

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        title = QLabel("New Analysis Run")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)

        def caption(text: str) -> QLabel:
            label = QLabel(text)
            label.setStyleSheet(f"color: {theme.MUTED}; background: transparent; font-size: 11px;")
            return label

        row = 0
        grid.addWidget(QLabel("Current project defaults"), 0, 0)
        grid.addWidget(QLabel("New run parameters"), 0, 1)

        self._default_targets = QLabel(store.targets and "; ".join(store.targets) or "–")
        self._default_targets.setWordWrap(True)
        self._default_targets.setStyleSheet("background: transparent;")
        self._targets = QLineEdit("; ".join(store.targets))
        grid.addWidget(caption("目标词 (targets)"), 1, 0)
        grid.addWidget(self._default_targets, 2, 0)
        grid.addWidget(self._targets, 2, 1)

        self._default_group = QLabel(store.group_by)
        self._default_group.setStyleSheet("background: transparent;")
        self._group = QComboBox()
        self._group.addItems(("source", "institution", "country", "custom"))
        self._group.setCurrentText(store.group_by)
        grid.addWidget(caption("分组方式 (group_by)"), 3, 0)
        grid.addWidget(self._default_group, 4, 0)
        grid.addWidget(self._group, 4, 1)

        self._default_mi = QLabel("3.0")
        self._default_mi.setStyleSheet("background: transparent;")
        self._mi = QDoubleSpinBox()
        self._mi.setRange(0.0, 10.0)
        self._mi.setSingleStep(0.5)
        self._mi.setValue(3.0)
        grid.addWidget(caption("MI 阈值"), 5, 0)
        grid.addWidget(self._default_mi, 6, 0)
        grid.addWidget(self._mi, 6, 1)

        fixed = QLabel("window=8 tokens · phrase ≤6 tokens(当前流水线固定值,不可调)")
        fixed.setStyleSheet(f"color: {theme.MUTED}; background: transparent; font-size: 11px;")
        grid.addWidget(caption("分析窗口 / 短语长度"), 7, 0)
        grid.addWidget(fixed, 8, 0)

        self._pos = QCheckBox("词性标注 + 中文翻译 (较慢,含联网翻译)")
        grid.addWidget(caption("POS / 翻译"), 9, 0)
        grid.addWidget(self._pos, 10, 0, 1, 2)

        root.addLayout(grid)

        gate = QFrame()
        gate.setObjectName("InspectorBlock")
        gate_layout = QVBoxLayout(gate)
        gate_layout.setContentsMargins(12, 10, 12, 10)
        gate_layout.setSpacing(4)
        state = self.health[0] if self.health else HealthState.UNKNOWN
        detail = self.health[1] if self.health else ""
        self._gate_label = QLabel(f"Corpus health: {state.value} — {detail}")
        self._gate_label.setWordWrap(True)
        self._gate_label.setStyleSheet(f"color: {HEALTH_COLOR(state)}; font-weight: 600; background: transparent;")
        gate_layout.addWidget(self._gate_label)

        self._gate_hint = QLabel("")
        self._gate_hint.setWordWrap(True)
        self._gate_hint.setStyleSheet("background: transparent;")
        gate_layout.addWidget(self._gate_hint)

        sanity_row = QHBoxLayout()
        self._sanity_button = QPushButton("运行 Sanity 检查")
        self._sanity_button.clicked.connect(self.sanity_requested.emit)
        sanity_row.addWidget(self._sanity_button)
        sanity_row.addStretch(1)
        gate_layout.addLayout(sanity_row)
        root.addWidget(gate)

        advanced = QLabel(
            "Advanced:跳过卫生检查(_skip-sanity)会降低研究结果可靠性,不建议用于正式研究。")
        advanced.setStyleSheet(f"color: {theme.MUTED}; background: transparent; font-size: 11px;")
        self._skip_sanity = QCheckBox("跳过卫生检查(Advanced,不推荐)")
        advanced_row = QHBoxLayout()
        advanced_row.addWidget(self._skip_sanity)
        advanced_row.addWidget(advanced, 1)
        root.addLayout(advanced_row)

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(
            f"background: {theme.BG}; border: 1px solid {theme.BORDER}; border-radius: 6px; padding: 10px;")
        root.addWidget(self._summary)

        buttons = QHBoxLayout()
        back = QPushButton("← 返回")
        back.clicked.connect(self.back_requested.emit)
        self._start_button = QPushButton("Start Analysis Run")
        self._start_button.setObjectName("Primary")
        self._start_button.clicked.connect(self._emit_start)
        buttons.addWidget(back)
        buttons.addStretch(1)
        buttons.addWidget(self._start_button)
        root.addLayout(buttons)

        self._targets.textChanged.connect(self._update_summary)
        self._group.currentTextChanged.connect(self._update_summary)
        self._mi.valueChanged.connect(self._update_summary)
        self._pos.stateChanged.connect(self._update_summary)
        self._skip_sanity.stateChanged.connect(self._update_summary)
        self.apply_gate(state, detail)
        self._update_summary()

    # ------------------------------------------------------------------

    def apply_gate(self, state: HealthState, detail: str) -> None:
        self.health = (state, detail)
        self._gate_label.setText(f"Corpus health: {state.value} — {detail}")
        self._gate_label.setStyleSheet(
            f"color: {HEALTH_COLOR(state)}; font-weight: 600; background: transparent;")
        self._sanity_button.setVisible(state in (HealthState.UNKNOWN, HealthState.STALE))
        skip_visible = state != HealthState.UNKNOWN
        self._skip_sanity.setVisible(skip_visible)
        if state is HealthState.PASS or state is HealthState.WARNING:
            hint = "允许运行。" + ("注意存在数据质量警告,详见 语料 → Health。" if state is HealthState.WARNING else "")
            self._start_button.setEnabled(True)
        elif state is HealthState.UNKNOWN:
            hint = "必须先运行 sanity 检查,才能启动分析。"
            self._start_button.setEnabled(False)
        elif state is HealthState.STALE:
            hint = "检查结果已过期,必须重新运行 sanity,不得沿用旧结果。"
            self._start_button.setEnabled(False)
        else:  # BLOCKED
            hint = "语料存在元数据污染,分析被禁止;请用原始 DOCX/干净正文重新导入。"
            self._start_button.setEnabled(False)
        if self._skip_sanity.isChecked() and state is not HealthState.UNKNOWN:
            # Advanced escape hatch (CLI --skip-sanity parity); never for UNKNOWN,
            # where running the sanity check first is mandatory.
            self._start_button.setEnabled(True)
        self._gate_hint.setText(hint)

    def _update_summary(self) -> None:
        skip = "是(⚠ 不建议)" if self._skip_sanity.isChecked() else "否"
        self._summary.setText(
            "即将启动:\n"
            f"  targets: {self._targets.text().strip() or '(空)'}\n"
            f"  group_by: {self._group.currentText()}\n"
            f"  MI 阈值: {self._mi.value():.1f}\n"
            f"  POS/翻译: {'是' if self._pos.isChecked() else '否'}\n"
            f"  sanity gate: {skip}\n"
            "  输出: 隔离工作目录 runs/work_<run_id>/,成功后发布回项目"
        )

    def _emit_start(self) -> None:
        self.start_requested.emit({
            "kind": "analyze",
            "targets": self._targets.text().strip(),
            "group_by": self._group.currentText(),
            "mi_threshold": float(self._mi.value()),
            "pos_translate": self._pos.isChecked(),
            "sanity": not self._skip_sanity.isChecked(),
        })


def HEALTH_COLOR(state: HealthState) -> str:
    return {
        HealthState.PASS: theme.SUCCESS,
        HealthState.WARNING: theme.WARNING,
        HealthState.STALE: theme.WARNING,
        HealthState.BLOCKED: theme.ERROR,
        HealthState.UNKNOWN: theme.MUTED,
    }[state]
