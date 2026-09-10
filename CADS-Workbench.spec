# -*- mode: python ; coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""PyInstaller spec for the CADS Workbench v1.0 RC (Phase 4B #8/#9/#31/#33).

onedir + windowed build of the PySide6 product GUI:

    dist/CADS-Workbench-1.0.0-rc1/
        CADS Workbench.exe     (product entry; also the analysis runner
                                via the hidden --gui-next-runner flag)
        _internal/...
        build_meta.json        (version / commit / timestamp / mode)
        docs/                  (user-facing documentation)
        README.txt / LICENSE

Built via `python build_exe.py --workbench`.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821 — provided by PyInstaller

VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
APP_NAME = "CADS Workbench"

# ---- build metadata (#31) -------------------------------------------
try:
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
        capture_output=True, text=True, timeout=10).stdout.strip()
except Exception:
    commit = ""
import platform as _platform
import sys as _sys

def _pkg_version(name: str) -> str:
    try:
        from importlib import metadata
        return metadata.version(name)
    except Exception:
        return ""

_tag = ""
try:
    _tag = subprocess.run(
        ["git", "describe", "--tags", "--exact-match", "HEAD"], cwd=str(ROOT),
        capture_output=True, text=True, timeout=10).stdout.strip()
except Exception:
    pass

build_meta = {
    "version": VERSION,
    "app_name": APP_NAME,
    "git_commit": commit,
    "git_tag": _tag,
    "build_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "build_mode": "packaged",
    "python_version": _sys.version.split()[0],
    "pyinstaller_version": _pkg_version("pyinstaller"),
    "qt_version": _pkg_version("PySide6"),
    "spacy_version": _pkg_version("spacy"),
    "model_version": _pkg_version("en-core-web-sm") or _pkg_version("en_core_web_sm"),
    "platform": f"{_platform.system()} {_platform.machine()}",
}
(ROOT / "build" / "build_meta.json").parent.mkdir(parents=True, exist_ok=True)
(ROOT / "build" / "build_meta.json").write_text(
    json.dumps(build_meta, ensure_ascii=False, indent=2), encoding="utf-8")

datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "build" / "build_meta.json"), "."),
    (str(ROOT / "VERSION"), "."),
    (str(ROOT / "docs" / "QUICKSTART_GUI.md"), "docs"),
    (str(ROOT / "docs" / "KEYBOARD_SHORTCUTS.md"), "docs"),
    (str(ROOT / "docs" / "METHODOLOGY.md"), "docs"),
    (str(ROOT / "docs" / "DATA_DICTIONARY.md"), "docs"),
    (str(ROOT / "docs" / "RELEASE_NOTES_v1.0-rc1.md"), "docs"),
]

# The spaCy model must ship as plain package data: hiddenimports alone does
# not collect its data files, and spacy.load needs the package on sys.path.
try:
    import en_core_web_sm as _model  # noqa: F401
    import importlib.metadata as _md

    _MODEL_DIR = Path(_model.__file__).resolve().parent
    datas.append((str(_MODEL_DIR), "en_core_web_sm"))
    # spacy.util.is_package resolves via importlib.metadata: the model's
    # dist-info must ship too, or spacy.load(name) raises E050 in frozen
    # builds.
    _DIST = Path(_md.distribution("en_core_web_sm")._path)  # type: ignore[attr-defined]
    datas.append((str(_DIST), _DIST.name))
except Exception:
    _MODEL_DIR = None

hiddenimports = [
    # analysis subprocess (reached through the --gui-next-runner flag)
    "gui_next.execution.runner",
    # analysis runtime
    "spacy",
    "en_core_web_sm",
    "en_core_web_lg",
    "nltk",
    "rapidfuzz",
    "tldextract",
    "matplotlib",
    "matplotlib.backends.backend_agg",
    "openpyxl",
    "docx",
    # Qt plugins are auto-detected; be explicit about the platform ones
    "PySide6.QtSvg",
    # the analysis pipeline imports modules.txt_modifier_extractor_gui,
    # which imports tkinter at module level (dev parity requires it)
    "tkinter",
]

a = Analysis(
    [str(ROOT / "gui_next" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch", "tensorflow", "keras", "cv2", "pygame", "sympy", "mpmath",
        "onnxruntime", "onnx", "transformers", "tokenizers", "safetensors",
        "caffe2", "caffe", "jupyter", "ipykernel", "ipython", "notebook",
        "nbformat", "sqlalchemy", "MySQLdb", "pymysql", "psycopg2",
        "boto3", "botocore", "s3transfer", "cryptography", "bcrypt",
        "paramiko", "wx", "PyQt5", "PyQt6", "PySide2", "pytest", "pluggy",
        "babel", "black", "flake8", "ruff", "pylint", "mypy", "_pytest",
        "pytest_asyncio",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "assets" / "icon.ico")] if (ROOT / "assets" / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=f"CADS-Workbench-{VERSION}",
)
