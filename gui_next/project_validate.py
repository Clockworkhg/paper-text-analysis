# -*- coding: utf-8 -*-
"""Project folder validation (Phase 4B #3).

Selecting a folder must never produce a raw Python exception. The Hub and
Open-Project flow classify the folder first:

    VALID_PROJECT        project.json parses; corpus + registry present
    LEGACY_PROJECT       project.json parses; corpus present, but the
                         document registry / GUI-era artifacts are missing
                         (pre-corpus-model era) — openable read-only
    INCOMPLETE_PROJECT   project.json exists but is unreadable/incomplete,
                         or required directories are missing
    NOT_A_PROJECT        no project.json at all
    UNSUPPORTED_VERSION  schema_version newer than this build understands
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

KNOWN_SCHEMA_VERSION = 1


@dataclass
class ProjectValidation:
    state: str                      # the five vocabulary states
    path: Path
    display_name: str = ""
    missing: List[str] = field(default_factory=list)
    detail: str = ""

    @property
    def openable(self) -> bool:
        return self.state in ("VALID_PROJECT", "LEGACY_PROJECT")


def validate_project(path: str | Path) -> ProjectValidation:
    root = Path(path)
    if not root.exists() or not root.is_dir():
        return ProjectValidation("NOT_A_PROJECT", root,
                                 missing=["目录不存在"])
    project_file = root / "project.json"
    if not project_file.exists():
        return ProjectValidation("NOT_A_PROJECT", root,
                                 missing=["project.json"])

    data = {}
    try:
        data = json.loads(project_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ProjectValidation("INCOMPLETE_PROJECT", root,
                                 missing=["project.json 无法解析"],
                                 detail=str(exc))
    except OSError as exc:
        return ProjectValidation("INCOMPLETE_PROJECT", root,
                                 missing=["project.json 无法读取"],
                                 detail=str(exc))
    if not isinstance(data, dict) or not data:
        return ProjectValidation("INCOMPLETE_PROJECT", root,
                                 missing=["project.json 内容为空或不是对象"])

    schema = data.get("schema_version")
    if schema is not None and schema != KNOWN_SCHEMA_VERSION:
        return ProjectValidation("UNSUPPORTED_VERSION", root,
                                 detail=f"schema_version={schema}")

    missing: List[str] = []
    corpus_dir = root / "corpus"
    registry = root / "01_corpus" / "documents.csv"
    has_corpus = corpus_dir.exists() and any(corpus_dir.rglob("*.txt"))
    if not has_corpus:
        missing.append("corpus/ 语料目录(含 .txt 文档)")
    if not registry.exists():
        missing.append("01_corpus/documents.csv 文档登记表")

    if not has_corpus:
        return ProjectValidation("INCOMPLETE_PROJECT", root,
                                 display_name=str(data.get("name", root.name)),
                                 missing=missing,
                                 detail=str(data.get("project_dir", "")))

    state = "VALID_PROJECT" if registry.exists() else "LEGACY_PROJECT"
    return ProjectValidation(state, root,
                             display_name=str(data.get("name", root.name)),
                             missing=missing)
