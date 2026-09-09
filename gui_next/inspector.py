# -*- coding: utf-8 -*-
"""Context Inspector: the right-hand panel (Phase 4A #4 — unified structure).

Every object type (DOCUMENT, SOURCE, KWIC, COLLOCATE, PHRASE, GROUP,
REVIEW_ITEM, EVIDENCE, CLAIM, WRITING_BLOCK, RUN, COMPARISON) renders through
one structure:

    OBJECT TYPE (header caption)
    heading
    ── IDENTITY ──      key/value pairs that name the object
    ── DETAILS ──       metrics / state / parameters
    ── CONTEXT / EVIDENCE ──  raw context, examples, snapshots
    ── PROVENANCE ──    run / fingerprint / hashes
    [actions]           real buttons (focusable, keyboard reachable)
    [badge]             persistent status line (e.g. "✓ In Evidence")

Pages must use the public API (show_object / typed helpers); they never
reach into internal layouts.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui_next import theme

Caption = str
Pairs = List[Tuple[str, Any]]
Actions = List[Tuple[str, Callable]]


def make_block(title: str, body: str) -> QFrame:
    """A titled Inspector block (used for CONTEXT/PROVENANCE content)."""
    frame = QFrame()
    frame.setObjectName("InspectorBlock")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(theme.SP_8, theme.SP_8, theme.SP_8, theme.SP_8)
    layout.setSpacing(theme.SP_4)
    heading = QLabel(title)
    heading.setObjectName("InspectorSectionCaption")
    text = QLabel(body)
    text.setWordWrap(True)
    text.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(heading)
    layout.addWidget(text)
    return frame


def _section_caption(text: str) -> QLabel:
    caption = QLabel(text)
    caption.setObjectName("InspectorSectionCaption")
    return caption


class InspectorPanel(QWidget):
    """Context-dependent detail panel. Pages call the typed show_* methods."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Inspector")
        self.setMinimumWidth(280)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.SP_12, theme.SP_12, theme.SP_12, theme.SP_12)
        outer.setSpacing(theme.SP_8)

        self._type_label = QLabel("INSPECTOR")
        self._type_label.setObjectName("InspectorTitle")
        outer.addWidget(self._type_label)

        self._heading = QLabel("未选择对象")
        self._heading.setObjectName("InspectorHeading")
        self._heading.setWordWrap(True)
        outer.addWidget(self._heading)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(theme.SP_8)
        self._body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._body)
        outer.addWidget(scroll, 1)

        # Actions row: real buttons (keyboard reachable, screen-reader visible).
        self._actions = QWidget()
        self._actions_layout = QHBoxLayout(self._actions)
        self._actions_layout.setContentsMargins(0, theme.SP_4, 0, 0)
        self._actions_layout.setSpacing(theme.SP_8)
        outer.addWidget(self._actions)

        self._badge = QLabel("")
        self._badge.setStyleSheet("background: transparent;")
        self._badge.setWordWrap(True)
        outer.addWidget(self._badge)

    # ------------------------------------------------------------------
    # unified entry point

    def show_object(
        self,
        object_type: str,
        heading: str,
        *,
        identity: Optional[Pairs] = None,
        details: Optional[Pairs] = None,
        context_blocks: Optional[List[QFrame]] = None,
        provenance: Optional[Pairs] = None,
        actions: Optional[Actions] = None,
        note: str = "",
        badge: Tuple[str, str] = ("", ""),
    ) -> None:
        """badge: (text, color-role-or-hex)."""
        self._type_label.setText(object_type)
        self._heading.setText(heading)
        self._clear_body()

        identity = [pair for pair in (identity or []) if _has_value(pair[1])]
        details = [pair for pair in (details or []) if _has_value(pair[1])]
        provenance_pairs = [pair for pair in (provenance or []) if _has_value(pair[1])]

        if identity:
            self._body_layout.addWidget(_section_caption("IDENTITY"))
            _kv_rows(self._body_layout, identity)
        if details:
            self._body_layout.addWidget(_section_caption("DETAILS"))
            _kv_rows(self._body_layout, details)
        for block in context_blocks or []:
            self._body_layout.addWidget(block)
        if provenance_pairs:
            self._body_layout.addWidget(_section_caption("PROVENANCE"))
            _kv_rows(self._body_layout, provenance_pairs)
        if note:
            note_label = QLabel(note)
            note_label.setWordWrap(True)
            note_label.setStyleSheet(
                f"color: {theme.MUTED}; font-size: 11px; background: transparent;")
            self._body_layout.addWidget(note_label)
        self._body_layout.addStretch(1)
        self.set_actions(actions or [])
        self.set_badge(badge[0], badge[1])

    # ------------------------------------------------------------------
    # actions / badge

    def set_actions(self, actions: Actions) -> None:
        """Replace the action buttons under the detail blocks."""
        while self._actions_layout.count():
            item = self._actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for label, handler in actions:
            button = QPushButton(label)
            button.setObjectName("Flat")
            button.clicked.connect(lambda _checked=False, h=handler: h())
            self._actions_layout.addWidget(button)
        self._actions_layout.addStretch(1)
        self._actions.setVisible(bool(actions))

    # Backwards-compatible alias used by earlier pages.
    def show_actions(self, actions: Actions) -> None:
        self.set_actions(actions)

    def clear_actions(self) -> None:
        self.set_actions([])
        self.set_badge("")

    def set_badge(self, text: str, color: str = "") -> None:
        """Small persistent status line (e.g. '✓ In Evidence')."""
        self._badge.setText(text)
        if color and not color.startswith("#"):
            from gui_next import status as _status
            color = _status.role_color(color)
        self._badge.setStyleSheet(
            f"color: {color or theme.MUTED}; background: transparent; font-weight: 600;")

    # ------------------------------------------------------------------
    # internals

    def _clear_body(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Detach immediately: deleteLater alone leaves the old widget
                # visible for one frame (visible ghosting on fast selections).
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    # ------------------------------------------------------------------
    # typed helpers (legacy API preserved; new types added)

    def show_empty(self, hint: str = "在左侧选择一个对象查看其详情、方法说明与原始语境。") -> None:
        self._type_label.setText("INSPECTOR")
        self._heading.setText(hint)
        self._clear_body()
        self._body_layout.addStretch(1)
        self.set_actions([])
        self.set_badge("")

    def show_document(self, row: Dict[str, Any]) -> None:
        heading = str(row.get("title") or row.get("document_id") or "(无标题)")
        self.show_object(
            "DOCUMENT",
            heading,
            identity=[
                ("Document ID", row.get("document_id")),
                ("标题", row.get("title")),
            ],
            details=[
                ("来源(规范)", row.get("source_normalized")),
                ("来源(原始)", row.get("source_raw")),
                ("国别", row.get("country")),
                ("日期", row.get("date")),
                ("近似词数", row.get("word_count_approx")),
                ("目标词命中", row.get("target_hits_total")),
            ],
            provenance=[("路径", row.get("relative_path"))],
        )

    def show_kwic(self, row: Dict[str, Any]) -> None:
        keyword = str(row.get("Keyword") or row.get("Target") or "")
        context = str(row.get("Full_Context") or "")
        context_block = make_block("FULL CONTEXT", context) if context else None
        self.show_object(
            "KWIC",
            f"目标词:{row.get('Target', '')}",
            identity=[("NODE", keyword), ("Document ID", row.get("Document_ID"))],
            details=[
                ("来源(原始)", row.get("Source")),
                ("来源(规范)", row.get("Source_Normalized")),
                ("分组", row.get("Group")),
                ("日期", row.get("Date")),
                ("标题", row.get("Title")),
            ],
            context_blocks=[context_block] if context_block else [],
            provenance=[
                ("左语境", row.get("Left_Context")),
                ("右语境", row.get("Right_Context")),
            ],
            note="ⓘ 自动提取的语境行。最终解释需人工阅读并复核。",
        )

    def show_collocate(self, target: str, row: Dict[str, Any]) -> None:
        stats = (
            f"共现 {row.get('Frequency', '?')} 次 · {row.get('Doc_Frequency', '?')} 篇文档 · "
            f"MI {row.get('MI_Score', '–')} · G² {row.get('Log_Likelihood', '–')} "
            f"({row.get('LL_Significance', '')}) · 窗口 [-5, +5]"
        )
        blocks = [make_block("STATISTICS", stats)]
        examples = str(row.get("Example_Contexts") or "")
        if examples:
            blocks.append(make_block("EXAMPLE CONTEXTS", examples.replace(" || ", "\n———\n")))
        self.show_object(
            "COLLOCATE",
            f"{row.get('Collocate', '')} × {target}",
            identity=[("Collocate", row.get("Collocate")), ("Target", target)],
            details=[("词性", row.get("POS"))],
            context_blocks=blocks,
            note="ⓘ MI / G² 用于发现和排序候选模式,不自动构成话语解释结论。",
        )

    def show_source(self, row: Dict[str, Any]) -> None:
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
        self.show_object(
            "SOURCE",
            str(row.get("Source_Merged") or ""),
            identity=[("合并来源名", row.get("Source_Merged"))],
            details=[("文章数", row.get("Count_Sum"))],
            context_blocks=[make_block("COUNTRY EVIDENCE", "\n".join(evidence_lines))],
        )

    def show_review_item(self, item: Dict[str, Any], decision: Dict[str, Any]) -> None:
        """REVIEW_ITEM: one semantic-prosody candidate in coding context."""
        decision_text = decision.get("decision") or "未编码"
        self.show_object(
            "REVIEW_ITEM",
            str(item.get("expression") or item.get("item_id", "")),
            identity=[
                ("Item", item.get("item_id")),
                ("Target", item.get("target")),
                ("Document", item.get("document_id")),
            ],
            details=[("当前决定", decision_text),
                     ("备注", decision.get("note") or "–")],
            context_blocks=[make_block("CONTEXT", item.get("context", "") or "(无)")],
        )

    def show_claim(self, claim: Dict[str, Any], evidence_count: int = 0) -> None:
        self.show_object(
            "CLAIM",
            claim.get("title", ""),
            identity=[("Claim ID", claim.get("claim_id"))],
            details=[
                ("论断", claim.get("claim_text", "")),
                ("证据数", evidence_count),
                ("备注", claim.get("researcher_note") or "–"),
            ],
            provenance=[
                ("Created", claim.get("created_at")),
                ("Updated", claim.get("updated_at")),
            ],
        )

    def show_evidence(self, record: Dict[str, Any], *, state: str = "",
                      state_detail: str = "", claims: str = "") -> None:
        """EVIDENCE object with provenance; integrity states come from status.py."""
        from gui_next import status as _status
        snap = record.get("captured_snapshot", {}) or {}
        if record.get("evidence_type") == "kwic":
            heading = f"{record.get('target', '')}: {snap.get('Keyword', '')}"
            context = (f"{snap.get('Left_Context', '')} [{snap.get('Keyword', '')}] "
                       f"{snap.get('Right_Context', '')}")
        else:
            heading = evidence_heading(record)
            context = snap_summary(snap)
        glyph, text, role = _status.integrity(state) if state else ("", "", "muted")
        self.show_object(
            "EVIDENCE",
            heading,
            identity=[
                ("Evidence ID", record.get("evidence_id")),
                ("Type", record.get("evidence_type")),
                ("Target", record.get("target")),
            ],
            details=[
                ("Document", record.get("document_id")),
                ("Claims", claims or "Inbox"),
                ("Note", record.get("researcher_note") or "–"),
            ],
            context_blocks=[make_block("CAPTURED SNAPSHOT", context)] if context else [],
            provenance=[
                ("Published Run", record.get("published_run_id")),
                ("Manifest", record.get("publication_manifest_hash")),
                ("Corpus fingerprint", record.get("corpus_fingerprint")),
            ],
            note=(f"{glyph} {text}: {state_detail}" if state else ""),
            badge=(f"{glyph} {text}" if state else "", role),
        )

    def show_run(self, manifest: Dict[str, Any], run_id: str) -> None:
        fingerprint = manifest.get("corpus_fingerprint", {}) or {}
        nlp = manifest.get("nlp_environment", {}) or {}
        parameters = manifest.get("parameters", {}) or {}
        self.show_object(
            "RUN",
            manifest.get("label") or run_id,
            identity=[("运行 ID", run_id)],
            details=[
                ("目标词", parameters.get("targets")),
                ("分组方式", parameters.get("group_by")),
                ("文件数", len(manifest.get("files", [])) or None),
                ("固化时间", manifest.get("frozen_at")),
            ],
            context_blocks=[
                make_block(
                    "ENVIRONMENT",
                    f"git {manifest.get('git_commit', '–')} · spaCy {nlp.get('spacy', '–')} · "
                    f"en_core_web_sm {nlp.get('en_core_web_sm', '–')} · "
                    f"algorithm {manifest.get('algorithm_version', '–')} · "
                    f"rules {manifest.get('hand_rules_version', '–')}",
                ),
                make_block(
                    "CORPUS FINGERPRINT",
                    f"{fingerprint.get('sha256', '–')}\n"
                    f"{fingerprint.get('files', '?')} 篇 · {fingerprint.get('bytes', 0)} bytes",
                ),
            ],
        )

    def show_comparison(self, run_a: str, run_b: str, compatibility: Dict[str, Any]) -> None:
        from gui_next import status as _status
        level = compatibility.get("level", "")
        glyph, text, role = _status.comparison(level)
        differences = compatibility.get("differences", [])
        diff_text = "\n".join(f"{d['field']}: {d['a']} → {d['b']}" for d in differences) \
            or "No parameter differences detected."
        self.show_object(
            "COMPARISON",
            f"{_short_run(run_a)} ↔ {_short_run(run_b)}",
            identity=[("Run A", run_a), ("Run B", run_b)],
            context_blocks=[make_block("PARAMETER DIFFERENCES", diff_text)],
            note=f"{glyph} {text} — Run differences describe changes in corpus/output "
                 "under the recorded analysis configurations. They do not by themselves "
                 "establish substantive discourse change.",
            badge=(f"{glyph} {text}", role),
        )


def _short_run(run_id: str) -> str:
    return f"#{run_id[-8:]}" if run_id else "–"


def _has_value(value: Any) -> bool:
    return not (value is None or str(value).strip() in ("", "nan", "None"))


def evidence_heading(record: Dict[str, Any]) -> str:
    snap = record.get("captured_snapshot", {}) or {}
    kind = record.get("evidence_type", "")
    if kind == "collocate_pattern":
        return f"{record.get('target', '')} × {snap.get('Collocate', '')}"
    if kind == "phrase_pattern":
        return f"{record.get('target', '')} + “{snap.get('Modifier_Phrase', '')}”"
    if kind == "group_pattern":
        return f"{record.get('target', '')} · {snap.get('Group', '')} · {snap.get('Expression', '')}"
    return record.get("evidence_id", "")


def snap_summary(snap: Dict[str, Any]) -> str:
    parts = [f"{key}: {value}" for key, value in snap.items()
             if str(value).strip() not in ("", "nan", "None")]
    return "\n".join(parts[:12])


def _kv_rows(layout: QVBoxLayout, rows: Pairs) -> None:
    for key, value in rows:
        key_label = QLabel(str(key))
        key_label.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 11px; background: transparent;")
        value_label = QLabel(str(value))
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value_label.setStyleSheet("background: transparent;")
        layout.addWidget(key_label)
        layout.addWidget(value_label)
