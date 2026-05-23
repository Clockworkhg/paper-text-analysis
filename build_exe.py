# -*- coding: utf-8 -*-
"""PyInstaller build script for cads-workbench standalone executables.

Usage:
    python build_exe.py          # build both CLI and GUI
    python build_exe.py --cli    # CLI only
    python build_exe.py --gui    # GUI only
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parent

PYINSTALLER_EXCLUDES = [
    "torch", "torchvision", "torchaudio", "torchgen",
    "tensorflow", "keras",
    "cv2", "opencv_python", "opencv_contrib_python",
    "pygame",
    "sympy", "mpmath",
    "onnxruntime", "onnx",
    "transformers", "tokenizers", "safetensors",
    "caffe2", "caffe",
    "jupyter", "ipykernel", "ipython", "notebook", "nbformat",
    "sqlalchemy", "MySQLdb", "pymysql", "psycopg2",
    "boto3", "botocore", "s3transfer",
    "cryptography", "bcrypt", "paramiko",
    "wx", "PyQt5", "PyQt6", "PySide2", "PySide6",
    "pytest", "pluggy",
    "babel",
    "black", "flake8", "ruff", "pylint", "mypy",
    "_pytest", "pytest_asyncio",
]


def configure_tcl_tk_env() -> None:
    """Help PyInstaller find Tcl/Tk data files in venv-based Python installs."""
    tcl_root = Path(sys.base_prefix) / "tcl"
    tcl_dir = tcl_root / "tcl8.6"
    tk_dir = tcl_root / "tk8.6"
    if tcl_dir.exists():
        os.environ.setdefault("TCL_LIBRARY", str(tcl_dir))
    if tk_dir.exists():
        os.environ.setdefault("TK_LIBRARY", str(tk_dir))


def clean() -> None:
    for d in ["build", "dist"]:
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)


def add_data_arg(source: Path, destination: str) -> str:
    return f"{source}{os.pathsep}{destination}"


def extend_excludes(args: List[str], excludes: Iterable[str]) -> None:
    for module_name in excludes:
        args.extend(["--exclude-module", module_name])


def pyinstaller_args(
    *,
    entry: Path,
    name: str,
    windowed: bool,
    onefile: bool,
    icon: Path | None = None,
    extra_data: Iterable[tuple[Path, str]] = (),
) -> List[str]:
    args = [
        str(entry),
        f"--name={name}",
        "--onefile" if onefile else "--onedir",
        "--windowed" if windowed else "--console",
        "--clean",
        "--noconfirm",
        "--log-level=WARN",
    ]
    for source, destination in extra_data:
        if source.exists():
            args.extend(["--add-data", add_data_arg(source, destination)])
    if icon and icon.exists():
        args.extend(["--icon", str(icon)])
    extend_excludes(args, PYINSTALLER_EXCLUDES)
    return args


def run_pyinstaller(args: List[str], *, dry_run: bool = False) -> None:
    if dry_run:
        print("PyInstaller command:")
        print("  pyinstaller " + " ".join(args))
        return

    import PyInstaller.__main__

    PyInstaller.__main__.run(args)


def build_cli(*, onefile: bool, dry_run: bool) -> None:
    args = pyinstaller_args(
        entry=ROOT / "research_tool.py",
        name="cads",
        windowed=False,
        onefile=onefile,
        extra_data=[
            (ROOT / "VERSION", "."),
            (ROOT / "assets", "assets"),
        ],
    )
    run_pyinstaller(args, dry_run=dry_run)


def build_gui(*, onefile: bool, dry_run: bool, console: bool = False) -> None:
    args = pyinstaller_args(
        entry=ROOT / "integrated_app.py",
        name="cads-gui-console" if console else "cads-gui",
        windowed=not console,
        onefile=onefile,
        icon=ROOT / "assets" / "icon.ico",
        extra_data=[
            (ROOT / "assets", "assets"),
        ],
    )
    run_pyinstaller(args, dry_run=dry_run)


def main():
    configure_tcl_tk_env()

    parser = argparse.ArgumentParser(description="Build cads-workbench standalone executables")
    parser.add_argument("--cli", action="store_true", help="Build CLI only")
    parser.add_argument("--gui", action="store_true", help="Build GUI only")
    parser.add_argument("--clean", action="store_true", help="Remove build/dist before building")
    parser.add_argument("--onedir", action="store_true", help="Build folder-based apps instead of one-file executables")
    parser.add_argument("--dry-run", action="store_true", help="Print PyInstaller commands without running them")
    parser.add_argument("--debug-console", action="store_true", help="Build the GUI with a console window for debugging")
    args = parser.parse_args()

    if args.clean:
        clean()
        print("Cleaned build/ and dist/")

    onefile = not args.onedir
    build_all = not args.cli and not args.gui

    if build_all or args.cli:
        print("Building cads (CLI)...")
        build_cli(onefile=onefile, dry_run=args.dry_run)
        print("  Done." if not args.dry_run else "  Dry run complete.")

    if build_all or args.gui:
        print("Building cads-gui (GUI)...")
        build_gui(onefile=onefile, dry_run=args.dry_run, console=args.debug_console)
        print("  Done." if not args.dry_run else "  Dry run complete.")

    print(f"\nOutput: {ROOT / 'dist'}")


if __name__ == "__main__":
    main()
