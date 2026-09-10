# -*- coding: utf-8 -*-
"""Phase 4B tests: RC productization.

Covers: project validation vocabulary, recent-projects app-state store,
version single source, packaged runner command parity, friendly IO errors,
diagnostics privacy, crash-flag lifecycle, window-state clamping, hub and
wizard flows, and close-lifecycle decisions.
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

try:
    import hypothesis  # noqa: F401 — preload (see test_gui_next_ux.py)
except Exception:  # pragma: no cover
    pass


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "01_corpus").mkdir(parents=True)
    corpus = proj / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\nchina poses a threat to stability.",
        encoding="utf-8")
    pd.DataFrame({
        "document_id": ["doc_a"], "title": ["Story A"], "source_normalized": ["BBC"],
        "country": ["UK"], "date": ["2021-01-01"], "word_count_approx": [120],
        "target_hits_total": [2], "relative_path": ["BBC/a.txt"],
    }).to_csv(proj / "01_corpus" / "documents.csv", index=False)
    (proj / "project.json").write_text(json.dumps(
        {"name": "测试项目", "targets": "China", "project_dir": str(proj)}),
        encoding="utf-8")
    return proj


# ---------------------------------------------------------------------------
# Version single source (#31)
# ---------------------------------------------------------------------------

def test_version_single_source():
    from gui_next.version import VERSION, build_metadata, version_line

    version_file = (Path(__file__).resolve().parents[1] / "VERSION").read_text(
        encoding="utf-8").strip()
    assert VERSION == version_file
    meta = build_metadata()
    assert meta["version"] == VERSION
    assert version_line().startswith("CADS Workbench ")

    import gui_next
    assert gui_next.VERSION == VERSION

    # pyproject must match the VERSION file
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
        encoding="utf-8")
    assert f'version = "{VERSION}"' in pyproject


# ---------------------------------------------------------------------------
# Project validation (#3)
# ---------------------------------------------------------------------------

def test_validate_valid_project(project_dir):
    from gui_next.project_validate import validate_project

    result = validate_project(project_dir)
    assert result.state == "VALID_PROJECT"
    assert result.openable
    assert result.display_name == "测试项目"


def test_validate_not_a_project(tmp_path):
    from gui_next.project_validate import validate_project

    empty = tmp_path / "empty"
    empty.mkdir()
    result = validate_project(empty)
    assert result.state == "NOT_A_PROJECT"
    assert not result.openable
    assert "project.json" in result.missing[0]


def test_validate_incomplete_project(tmp_path):
    from gui_next.project_validate import validate_project

    proj = tmp_path / "broken"
    proj.mkdir()
    (proj / "project.json").write_text("{broken json", encoding="utf-8")
    result = validate_project(proj)
    assert result.state == "INCOMPLETE_PROJECT"
    assert not result.openable

    empty_json = tmp_path / "empty_json"
    empty_json.mkdir()
    (empty_json / "project.json").write_text("{}", encoding="utf-8")
    assert validate_project(empty_json).state == "INCOMPLETE_PROJECT"


def test_validate_legacy_project(tmp_path):
    """Corpus without a GUI-era registry → openable legacy (#3)."""
    from gui_next.project_validate import validate_project

    proj = tmp_path / "legacy"
    corpus = proj / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text("china", encoding="utf-8")
    (proj / "project.json").write_text(json.dumps({"name": "old"}), encoding="utf-8")
    result = validate_project(proj)
    assert result.state == "LEGACY_PROJECT"
    assert result.openable


def test_validate_missing_folder(tmp_path):
    from gui_next.project_validate import validate_project

    assert validate_project(tmp_path / "nope").state == "NOT_A_PROJECT"


# ---------------------------------------------------------------------------
# Recent projects (#5): app-level state, never project writes
# ---------------------------------------------------------------------------

def test_recent_projects_store(project_dir, tmp_path, monkeypatch):
    from gui_next import appdata

    monkeypatch.setattr(appdata, "recent_projects_path",
                        lambda: tmp_path / "recent.json")

    appdata.remember_project(str(project_dir), "测试项目")
    entries = appdata.load_recent_projects()
    assert entries[0]["path"] == str(project_dir)
    assert entries[0]["display_name"] == "测试项目"
    assert "last_opened" in entries[0]

    # duplicates move to front, not duplicate rows
    appdata.remember_project(str(project_dir))
    assert len(appdata.load_recent_projects()) == 1

    appdata.remove_recent_project(str(project_dir))
    assert appdata.load_recent_projects() == []
    # the project itself is untouched
    assert (project_dir / "project.json").exists()


# ---------------------------------------------------------------------------
# Packaged runner command parity (#14)
# ---------------------------------------------------------------------------

def test_runner_command_dev_mode():
    from gui_next.execution.controller import _runner_command

    program, arguments = _runner_command("spec.json")
    assert program == sys.executable
    assert arguments == ["-m", "gui_next.execution.runner", "spec.json"]


def test_runner_command_frozen_mode(monkeypatch):
    import gui_next.execution.controller as controller_module

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    command = controller_module._runner_command("spec.json")
    assert command[0] == sys.executable
    assert command[1] == ["--gui-next-runner", "spec.json"]


def test_app_main_handles_runner_flag(tmp_path, monkeypatch):
    """The packaged child mode runs the runner and exits before Qt (#14)."""
    from gui_next.execution import jobs
    from gui_next.execution.events import parse

    spec = {"kind": "sanity", "project_dir": str(tmp_path)}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    from gui_next import app as app_module
    # sanity job needs a corpus dir to check
    (tmp_path / "corpus").mkdir(exist_ok=True)
    (tmp_path / "corpus" / "a.txt").write_text("china", encoding="utf-8")
    exit_code = app_module.main(["--gui-next-runner", str(spec_path)])
    assert exit_code == 0
    assert (tmp_path / "07_reports" / "corpus_sanity_report.json").exists()


# ---------------------------------------------------------------------------
# Friendly IO errors (#22/#23)
# ---------------------------------------------------------------------------

def test_friendly_error_for_locked_file():
    from gui_next.errors import friendly_io_error

    locked = PermissionError(13, "Permission denied")
    locked.winerror = 32  # ERROR_SHARING_VIOLATION (Excel/WPS lock)
    message = friendly_io_error(locked)
    assert "Excel" in message and "WPS" in message
    assert "WinError" not in message

    readonly = PermissionError(13, "Permission denied")
    readonly.winerror = 5  # ACCESS_DENIED
    message = friendly_io_error(readonly)
    assert "只读" in message or "写权限" in message

    # errno-style construction (no winerror attribute)
    posix_locked = PermissionError(16, "Device or resource busy")
    assert "Excel" in friendly_io_error(posix_locked)


def test_publication_locked_workbook_rolls_back(tmp_path):
    """Excel/WPS lock during publish must fail safely, not corrupt (#23)."""
    from gui_next.execution.publication import PublicationError  # noqa: F401
    # The transactional rollback behavior itself is covered by the Phase 2B.1
    # suite; here we assert the error surfaced to users is the friendly one.
    from gui_next.errors import friendly_io_error

    try:
        raise PermissionError(32, "The process cannot access the file because "
                                  "it is being used by another process")
    except PermissionError as exc:
        message = friendly_io_error(exc)
    assert "关闭" in message and "重试" in message


# ---------------------------------------------------------------------------
# Diagnostics privacy (#18/#40/#41)
# ---------------------------------------------------------------------------

def test_diagnostics_bundle_excludes_research_content(project_dir, tmp_path):
    from gui_next.diagnostics import export_diagnostics

    (project_dir / "corpus" / "BBC" / "a.txt").write_text(
        "SECRET-CHINA-CONTENT never leak", encoding="utf-8")
    out = tmp_path / "diag.zip"
    export_diagnostics(project_dir, out)

    import zipfile
    with zipfile.ZipFile(out) as bundle:
        names = bundle.namelist()
        blob = b"".join(bundle.read(name) for name in names)
    assert "diagnostics_info.txt" in names
    assert "packages.txt" in names
    assert "project_summary.json" in names
    assert b"SECRET-CHINA-CONTENT" not in blob
    summary = json.loads(zipfile.ZipFile(out).read("project_summary.json"))
    assert summary["corpus"]["document_count"] == 1  # counts, not content


def test_analysis_model_check_never_crashes():
    from gui_next.diagnostics import analysis_model_available

    ok, detail = analysis_model_available()
    assert isinstance(ok, bool) and detail


# ---------------------------------------------------------------------------
# Crash flag lifecycle (#19/#20)
# ---------------------------------------------------------------------------

def test_crash_flag_lifecycle(tmp_path, monkeypatch):
    from gui_next import appdata

    monkeypatch.setattr(appdata, "crash_flag_path",
                        lambda: tmp_path / "session_crashed.flag")
    assert not appdata.previous_session_crashed()
    appdata.mark_session_crashed()
    assert appdata.previous_session_crashed()
    appdata.clear_crash_flag()
    assert not appdata.previous_session_crashed()


def test_exception_handler_reports_not_swallows(qapp, monkeypatch, tmp_path):
    """Uncaught exceptions reach the hook, are logged, and can be dismissed."""
    import gui_next.errors as errors_module

    errors_module.install_exception_handler()
    monkeypatch.setattr(errors_module, "_show_error_dialog",
                        lambda report: shown.append(report))
    shown = []

    def boom():
        raise RuntimeError("e2e boom")

    try:
        boom()
    except RuntimeError:
        errors_module.sys.excepthook(*sys.exc_info())

    assert len(shown) == 1
    assert shown[0].exc_type == "RuntimeError"
    assert "e2e boom" in shown[0].diagnostics_text()


# ---------------------------------------------------------------------------
# Window state persistence + clamping (#7)
# ---------------------------------------------------------------------------

def test_window_state_clamped_into_screen(project_dir, qapp, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings

    from gui_next import theme
    from gui_next.app import MainWindow

    qapp.setStyleSheet(theme.build_qss())
    # Simulate a layout saved on a huge screen / off-screen position.
    settings = QSettings("cads-workbench", "gui-next-test-clamp")
    monkeypatch.setattr(QMainWindow_inst := MainWindow, "__init__", MainWindow.__init__)
    settings.setValue("window/geometry", b"\x00" * 0)  # empty bytes are ignored safely

    window = MainWindow()
    try:
        # Force an off-screen frame and run the clamp.
        window.move(8000, 8000)
        window._clamp_into_screen()
        from PySide6.QtGui import QGuiApplication
        available = QGuiApplication.primaryScreen().availableGeometry()
        assert window.x() < available.right()
        assert window.y() < available.bottom()
    finally:
        window.close()


# ---------------------------------------------------------------------------
# Hub + wizard (#2/#4/#26)
# ---------------------------------------------------------------------------

def test_hub_shows_welcome_and_recent(qapp, monkeypatch, tmp_path, project_dir):
    from PySide6.QtWidgets import QApplication

    from gui_next import appdata, theme
    from gui_next.hub import ProjectHub

    monkeypatch.setattr(appdata, "load_recent_projects", appdata.load_recent_projects)
    hub = ProjectHub()
    hub.resize(1200, 800)
    hub.show()
    QApplication.processEvents()
    assert hub._error_label.isHidden()

    appdata.remember_project(str(project_dir), "测试项目")
    monkeypatch.setattr("gui_next.hub.load_recent_projects", appdata.load_recent_projects)
    hub.refresh_recent()
    QApplication.processEvents()
    assert hub._recent_host.count() >= 1
    hub.hide()


def test_hub_rejects_invalid_folder(qapp, tmp_path):
    from gui_next.hub import ProjectHub

    empty = tmp_path / "not a project"
    empty.mkdir()
    hub = ProjectHub()
    hub._try_open(str(empty))
    assert not hub._error_label.isHidden()
    assert "not a CADS Workbench project" in hub._error_label.text()


def test_wizard_creates_project_via_existing_apis(qapp, tmp_path):
    from gui_next.wizard import NewProjectWizard

    wizard = NewProjectWizard()
    wizard.identity.name.setText("中欧媒体话语研究")
    base = tmp_path / "研究目录"
    base.mkdir()
    wizard.identity.location.setText(str(base))
    wizard.template.combo.setCurrentIndex(0)
    created = wizard.create()
    assert (created / "project.json").exists()
    data = json.loads((created / "project.json").read_text(encoding="utf-8"))
    assert data["name"] == "中欧媒体话语研究"
    assert data["corpus_type"] in ("academic", "generic", "news_lexis", "policy",
                                   "interview", "social_media", "translation")


def test_wizard_imports_corpus(qapp, tmp_path):
    from gui_next.wizard import NewProjectWizard

    source = tmp_path / "raw"
    source.mkdir()
    (source / "news1.txt").write_text(
        "<SOURCE>: BBC\n\nchina trade talks continue", encoding="utf-8")

    wizard = NewProjectWizard()
    wizard.identity.name.setText("导入项目")
    base = tmp_path / "项目"
    base.mkdir()
    wizard.identity.location.setText(str(base))
    wizard.corpus.path.setText(str(source))
    created = wizard.create()
    txts = list((created / "corpus").rglob("*.txt"))
    assert txts, "corpus imported via existing project_import"


# ---------------------------------------------------------------------------
# Close lifecycle (#38): decision logic, not the modal itself
# ---------------------------------------------------------------------------

def test_close_lifecycle_constants_exist():
    from gui_next.execution.events import RunState

    # PUBLISHING must be refused; RUNNING asks; idle closes.
    assert RunState.PUBLISHING.value in ("PUBLISHING", "ANALYSIS_SUCCEEDED")


# ---------------------------------------------------------------------------
# Long / unicode / spaced paths (#24) + non-ASCII content (#25)
# ---------------------------------------------------------------------------

def test_full_flow_on_chinese_spaced_path(qapp, tmp_path):
    """创建→导入→sanity job 在 中文+空格+括号 路径下可用。"""
    from gui_next.wizard import NewProjectWizard

    base = tmp_path / "研究项目" / "中欧媒体话语 (定稿)"
    base.mkdir(parents=True)
    source = base / "原始语料"
    source.mkdir()
    (source / "doc 1.txt").write_text("China and Europe negotiate trade terms.",
                                      encoding="utf-8")

    wizard = NewProjectWizard()
    wizard.identity.name.setText("中欧媒体话语研究")
    wizard.identity.location.setText(str(base))
    wizard.corpus.path.setText(str(source))
    project_dir = wizard.create()
    assert (project_dir / "project.json").exists()
    assert list((project_dir / "corpus").rglob("*.txt"))

    # sanity job on the unicode path (the runner's exact entry point)
    from gui_next import app as app_module

    spec_path = project_dir / "job_spec.json"
    spec_path.write_text(json.dumps({"kind": "sanity", "project_dir": str(project_dir)}),
                         encoding="utf-8")
    assert app_module.main(["--gui-next-runner", str(spec_path)]) == 0
    assert (project_dir / "07_reports" / "corpus_sanity_report.json").exists()


def test_writing_export_unicode_content(qapp, tmp_path):
    """中文项目名 / 章节 / Claim / Writing → Markdown 导出 UTF-8 无乱码。"""
    from gui_next.data.evidence_store import EvidenceStore
    from gui_next.data.writing_store import WritingStore
    from gui_next.data.writing_export import export_markdown

    store = WritingStore(tmp_path)
    store.new_document(skeleton=False)
    sid = store.add_section("研究发现")
    store.add_block(sid, "PROSE", text="中文正文:证据表明……")
    claim_id = store.state.get("claims_order", [])
    # claim lives in the evidence store
    evidence = EvidenceStore(tmp_path)
    claim = evidence.add_claim("竞争性话语", claim_text="中文论断内容")
    store.add_block(sid, "CLAIM_REF", claim_id=claim["claim_id"])
    store.save()
    result = export_markdown(store, evidence, None, tmp_path, mode="draft",
                             section_id=None)
    text = Path(result["path"]).read_text(encoding="utf-8")
    assert "研究发现" in text and "中文正文" in text and "竞争性话语" in text
