# -*- coding: utf-8 -*-
"""Context Inspector: the right-hand panel that answers "why is this row here".

Selecting any object (document, KWIC line, collocate, source, run) shows its
detail here instead of opening modal dialogs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme


def _kv_rows(layout: QVBoxLayout, rows: List[tuple[str, str]]) -> None:
    for key, value in rows:
        if value is None or str(value).strip() in ("", "nan", "None"):
            continue
        key_label = QLabel(str(key))
        key_label.setProperty("class", "Muted")
        key_label.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px; background: transparent;")
        value_label = QLabel(str(value))
        value_label.setWordWrap(True)
        value_label.setStyleSheet("background: transparent;")
        layout.addWidget(key_label)
        layout.addWidget(value_label)


def _block(title: str, body: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("InspectorBlock")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(4)
    heading = QLabel(title)
    heading.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px; font-weight: 600; background: transparent;")
    text = QLabel(body)
    text.setWordWrap(True)
    text.setStyleSheet("background: transparent;")
    layout.addWidget(heading)
    layout.addWidget(text)
    return frame


class InspectorPanel(QWidget):
    """Context-dependent detail panel. Pages call show_* methods."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Inspector")
        self.setFixedWidth(340)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        self._title = QLabel("INSPECTOR")
        self._title.setObjectName("InspectorTitle")
        outer.addWidget(self._title)

        self._heading = QLabel("未选择对象")
        self._heading.setObjectName("InspectorHeading")
        self._heading.setWordWrap(True)
        outer.addWidget(self._heading)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(8)
        self._body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._body)
        outer.addWidget(scroll, 1)

    def _clear_body(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _set(self, kind: str, heading: str, blocks: List[QFrame], pairs: List[tuple[str, str]]) -> None:
        self._title.setText(kind)
        self._heading.setText(heading)
        self._clear_body()
        for block in blocks:
            self._body_layout.addWidget(block)
        _kv_rows(self._body_layout, pairs)
        self._body_layout.addStretch(1)

    # ------------------------------------------------------------------

    def show_empty(self, hint: str = "在左侧选择一个对象查看其详情、方法说明与原始语境。") -> None:
        self._set("INSPECTOR", hint, [], [])

    def show_document(self, row: Dict[str, Any]) -> None:
        heading = str(row.get("title") or row.get("document_id") or "(无标题)")
        pairs = [
            ("Document ID", row.get("document_id")),
            ("来源(规范)", row.get("source_normalized")),
            ("来源(原始)", row.get("source_raw")),
            ("国别", row.get("country")),
            ("日期", row.get("date")),
            ("近似词数", row.get("word_count_approx")),
            ("目标词命中", row.get("target_hits_total")),
            ("路径", row.get("relative_path")),
        ]
        self._set("DOCUMENT", heading, [], pairs)

    def show_kwic(self, row: Dict[str, Any]) -> None:
        keyword = str(row.get("Keyword") or row.get("Target") or "")
        node = QLabel(keyword)
        node.setObjectName("NodeText")
        node.setAlignment(Qt.AlignLeft)
        node.setWordWrap(True)

        context = str(row.get("Full_Context") or "")
        blocks = [_block("FULL CONTEXT", context)] if context else []
        pairs = [
            ("Document ID", row.get("Document_ID")),
            ("来源(原始)", row.get("Source")),
            ("来源(规范)", row.get("Source_Normalized")),
            ("分组", row.get("Group")),
            ("日期", row.get("Date")),
            ("标题", row.get("Title")),
            ("左语境", row.get("Left_Context")),
            ("右语境", row.get("Right_Context")),
        ]
        self._clear_body()
        self._title.setText("KWIC")
        self._heading.setText(f"目标词:{row.get('Target', '')}")
        self._body_layout.addWidget(node)
        for block in blocks:
            self._body_layout.addWidget(block)
        _kv_rows(self._body_layout, pairs)
        note = QLabel("ⓘ 自动提取的语境行。最终解释需人工阅读并复核。")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px; background: transparent;")
        self._body_layout.addWidget(note)
        self._body_layout.addStretch(1)

    def show_collocate(self, target: str, row: Dict[str, Any]) -> None:
        heading = f"{row.get('Collocate', '')} × {target}"
        stats = (
            f"共现 {row.get('Frequency', '?')} 次 · {row.get('Doc_Frequency', '?')} 篇文档\n"
            f"MI {row.get('MI_Score', '–')} · G² {row.get('Log_Likelihood', '–')} "
            f"({row.get('LL_Significance', '')})\n窗口 [-5, +5]"
        )
        blocks = [_block("STATISTICS", stats)]
        examples = str(row.get("Example_Contexts") or "")
        if examples:
            blocks.append(_block("EXAMPLE CONTEXTS", examples.replace(" || ", "\n———\n")))
        pairs = [("词性", row.get("POS"))]
        self._set("COLLOCATE", heading, blocks, pairs)

    def show_source(self, row: Dict[str, Any]) -> None:
        heading = str(row.get("Source_Merged") or "")
        country = str(row.get("Country") or "")
        confidence = row.get("Confidence")
        evidence_lines = []
        if country and country.lower() not in ("unknown", "nan"):
            evidence_lines.append(f"✓ 国别:{country}")
        else:
            evidence_lines.append("△ 国别未识别")
        if confidence is not None and str(confidence) not in ("nan", ""):
            evidence_lines.append(f"△ 置信度:{confidence}(来自自动推断)")
        evidence_lines.append("△ 国别为辅助变量,使用前需人工复核")
        blocks = [_block("COUNTRY EVIDENCE", "\n".join(evidence_lines))]
        pairs = [("文章数", row.get("Count_Sum")), ("合并来源名", row.get("Source_Merged"))]
        self._set("SOURCE", heading, blocks, pairs)

    def show_run(self, manifest: Dict[str, Any], run_id: str) -> None:
        heading = manifest.get("label") or run_id
        fingerprint = manifest.get("corpus_fingerprint", {}) or {}
        nlp = manifest.get("nlp_environment", {}) or {}
        parameters = manifest.get("parameters", {}) or {}
        blocks = [
            _block(
                "CORPUS FINGERPRINT",
                f"{fingerprint.get('sha256', '–')}\n{fingerprint.get('files', '?')} 篇 · {fingerprint.get('bytes', 0)} bytes",
            ),
            _block(
                "ENVIRONMENT",
                f"git {manifest.get('git_commit', '–')}\nspaCy {nlp.get('spacy', '–')} · "
                f"en_core_web_sm {nlp.get('en_core_web_sm', '–')}\n"
                f"algorithm {manifest.get('algorithm_version', '–')} · rules {manifest.get('hand_rules_version', '–')}",
            ),
        ]
        pairs = [
            ("运行 ID", run_id),
            ("固化时间", manifest.get("frozen_at")),
            ("目标词", parameters.get("targets")),
            ("分组方式", parameters.get("group_by")),
            ("文件数", len(manifest.get("files", [])) or None),
        ]
        self._set("RUN", heading, blocks, pairs)
