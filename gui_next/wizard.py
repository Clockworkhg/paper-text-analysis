# -*- coding: utf-8 -*-
"""New Project Wizard (Phase 4B #4).

Four steps, every capability delegated to the existing frozen shared APIs
— no re-implemented project init or import:

    1. Project identity   (name, location)
    2. Research template  (from shared.research_templates.list_templates)
    3. Corpus source      (folder / CSV / Excel via project_import, or empty)
    4. Analysis defaults  (targets, default group_by)

The wizard NEVER starts an analysis on its own; on finish the project is
created (and corpus imported if provided) and the app opens it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from gui_next import theme
from gui_next.version import APP_NAME


class IdentityPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 1 · Project identity")
        layout = QFormLayout(self)
        layout.setSpacing(theme.SP_8)
        self.name = QLineEdit()
        self.name.setPlaceholderText("例如:中欧媒体话语研究")
        self.location = QLineEdit()
        self.location.setPlaceholderText("选择一个空文件夹作为项目位置…")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        location_row = QVBoxLayout()
        location_row.setSpacing(theme.SP_4)
        location_row.addWidget(self.location)
        location_row.addWidget(browse)
        self.registerField("project_name*", self.name)
        layout.addRow("项目名称", self.name)
        layout.addRow("位置", location_row)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择项目位置")
        if path:
            self.location.setText(path)

    def project_dir(self) -> Path:
        base = Path(self.location.text().strip())
        name = self.name.text().strip()
        return base / name if base.name != name else base

    def validatePage(self) -> bool:
        if not self.name.text().strip() or not self.location.text().strip():
            self.setSubTitle("请填写项目名称并选择位置。")
            return False
        target = self.project_dir()
        if target.exists() and any(target.iterdir()):
            self.setSubTitle("目标文件夹已存在且非空,请更换名称或位置。")
            return False
        return True


class TemplatePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 2 · Research template")
        subtitle = QLabel("模板决定导入时的字段解释与研究输出结构(来自现有研究模板定义)。")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        self.combo = QComboBox()
        from shared.research_templates import list_templates
        self._template_ids = []
        for template in list_templates():
            self.combo.addItem(f"{template['label']} — {template['description']}",
                               template["template_id"])
            self._template_ids.append(template["template_id"])
        layout = QVBoxLayout(self)
        layout.setSpacing(theme.SP_8)
        layout.addWidget(subtitle)
        layout.addWidget(self.combo)

    def template_id(self) -> str:
        return self.combo.currentData() or "generic"


class CorpusPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 3 · Corpus source")
        subtitle = QLabel("支持现有导入能力:文件夹(TXT / LexisNexis DOCX)、CSV / Excel 表格;"
                          "也可以先创建空项目,之后再导入。")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        self.path = QLineEdit()
        self.path.setPlaceholderText("留空 = 创建空项目(稍后导入)")
        browse = QPushButton("选择语料…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        self.hint = QLabel("")
        self.hint.setObjectName("Muted")
        layout = QVBoxLayout(self)
        layout.setSpacing(theme.SP_8)
        layout.addWidget(subtitle)
        layout.addLayout(row)
        layout.addWidget(self.hint)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择语料文件(CSV / Excel)", "", "Data (*.csv *.xlsx)")
        if path:
            self.path.setText(path)
            self.hint.setText("")
            return
        folder = QFileDialog.getExistingDirectory(self, "选择语料文件夹(TXT / DOCX)")
        if folder:
            self.path.setText(folder)

    def source_path(self) -> str:
        return self.path.text().strip()

    def validatePage(self) -> bool:
        source = self.source_path()
        if not source:
            return True  # empty project allowed
        path = Path(source)
        if not path.exists():
            self.hint.setText("路径不存在,请重新选择。")
            return False
        if path.is_file() and path.suffix.lower() not in (".csv", ".xlsx"):
            self.hint.setText("表格语料仅支持 CSV / Excel;文件夹支持 TXT / DOCX。")
            return False
        return True


class DefaultsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 4 · Analysis defaults")
        subtitle = QLabel("目标词与默认分组;之后可在应用内通过 New Analysis Run 调整。")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        self.targets = QLineEdit()
        self.targets.setPlaceholderText("例如:China; Europe(分号分隔)")
        self.group_by = QComboBox()
        self.group_by.addItems(["source", "institution", "country", "custom"])
        form = QFormLayout(self)
        form.setSpacing(theme.SP_8)
        form.addRow(subtitle)
        form.addRow("目标词 (targets)", self.targets)
        form.addRow("默认分组 (group_by)", self.group_by)

    def targets_text(self) -> str:
        return self.targets.text().strip()

    def group_value(self) -> str:
        return self.group_by.currentText()


class NewProjectWizard(QWizard):
    """Creates the project via shared.project_workflow (init + import)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"New Project — {APP_NAME}")
        self.resize(640, 480)
        self.identity = IdentityPage()
        self.template = TemplatePage()
        self.corpus = CorpusPage()
        self.defaults = DefaultsPage()
        for page in (self.identity, self.template, self.corpus, self.defaults):
            self.addPage(page)

    # ------------------------------------------------------------------

    def create(self) -> Path:
        """Run the frozen init/import APIs; returns the project directory."""
        from shared.project_workflow import init_project, project_import

        project_dir = self.identity.project_dir()
        corpus_type = self.template.template_id()
        targets = self.defaults.targets_text()
        init_project(project_dir, corpus_type=corpus_type,
                     name=self.identity.name.text().strip(), targets=targets)
        source = self.corpus.source_path()
        if source:
            project_import(project_dir, input_path=source,
                           corpus_type=corpus_type, targets=targets)
        return project_dir
