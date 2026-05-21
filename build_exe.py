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

ROOT = Path(__file__).resolve().parent


def clean():
    for d in ["build", "dist"]:
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)


def build_cli():
    import PyInstaller.__main__

    args = [
        str(ROOT / "research_tool.py"),
        "--name=cads",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        "--add-data", f"{ROOT / 'assets'};assets",
        "--hidden-import", "shared",
        "--hidden-import", "modules",
        "--hidden-import", "LexisWordToTxt",
    ]
    PyInstaller.__main__.run(args)


def build_gui():
    import PyInstaller.__main__

    args = [
        str(ROOT / "integrated_app.py"),
        "--name=cads-gui",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--add-data", f"{ROOT / 'assets'};assets",
        "--icon", str(ROOT / "assets" / "icon.ico"),
        "--hidden-import", "shared",
        "--hidden-import", "modules",
        "--hidden-import", "LexisWordToTxt",
    ]
    PyInstaller.__main__.run(args)


def main():
    parser = argparse.ArgumentParser(description="Build cads-workbench standalone executables")
    parser.add_argument("--cli", action="store_true", help="Build CLI only")
    parser.add_argument("--gui", action="store_true", help="Build GUI only")
    parser.add_argument("--clean", action="store_true", help="Remove build/dist before building")
    args = parser.parse_args()

    if args.clean:
        clean()
        print("Cleaned build/ and dist/")

    build_all = not args.cli and not args.gui

    if build_all or args.cli:
        print("Building cads.exe (CLI)...")
        build_cli()
        print("  Done.")

    if build_all or args.gui:
        print("Building cads-gui.exe (GUI)...")
        build_gui()
        print("  Done.")

    print(f"\nOutput: {ROOT / 'dist'}")


if __name__ == "__main__":
    main()
