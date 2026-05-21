# -*- coding: utf-8 -*-
"""Unified CLI for the research text-analysis toolkit."""

import argparse
import subprocess
import sys
from pathlib import Path

from shared.validation import generate_validation_artifacts


ROOT = Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "0.0.0"


def run_subprocess(args):
    completed = subprocess.run(args, cwd=str(ROOT))
    return completed.returncode


def cmd_run(args):
    command = [
        sys.executable,
        str(ROOT / "pipeline.py"),
        "-i",
        args.input,
        "-o",
        args.output,
    ]
    if args.targets:
        command.extend(["-t", args.targets])
    if args.no_country:
        command.append("--no-country")
    if args.skip:
        command.extend(["--skip", args.skip])
    if args.only:
        command.extend(["--only", args.only])
    if args.force:
        command.append("--force")
    if args.quiet:
        command.append("--quiet")
    return run_subprocess(command)


def cmd_review(args):
    paths = generate_validation_artifacts(Path(args.output_dir), sample_size=args.sample_size)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


def cmd_ocr(args):
    command = [sys.executable, str(ROOT / "tools" / "ocr_scanned_pdfs.py")]
    if args.out:
        command.extend(["--out", args.out])
    if args.scale:
        command.extend(["--scale", str(args.scale)])
    return run_subprocess(command)


def cmd_docs(_args):
    docs = [
        ROOT / "docs" / "WORKFLOW.md",
        ROOT / "docs" / "METHODOLOGY.md",
        ROOT / "docs" / "DATA_DICTIONARY.md",
        ROOT / "docs" / "VALIDATION.md",
        ROOT / "docs" / "literature_notes" / "00_INDEX.md",
    ]
    for path in docs:
        print(path)
    return 0


def cmd_test(_args):
    return run_subprocess([sys.executable, "-m", "pytest"])


def build_parser():
    parser = argparse.ArgumentParser(
        description="Research text-analysis workbench: run pipeline, generate review artifacts, OCR literature, and inspect docs."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the full LexisNexis corpus analysis pipeline")
    run.add_argument("-i", "--input", required=True, help="Input LexisNexis DOCX")
    run.add_argument("-o", "--output", required=True, help="Output directory")
    run.add_argument("-t", "--targets", default="", help="Target terms separated by semicolons")
    run.add_argument("--no-country", action="store_true", help="Disable online country inference")
    run.add_argument("--skip", default="", help="Pipeline steps to skip, e.g. 3,4")
    run.add_argument("--only", default="", help="Pipeline steps to run, e.g. 1,2")
    run.add_argument("--force", action="store_true", help="Force rerun existing outputs")
    run.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")
    run.set_defaults(func=cmd_run)

    review = sub.add_parser("review", help="Generate review templates, validation report, and method text outputs")
    review.add_argument("output_dir", help="Pipeline output directory")
    review.add_argument("--sample-size", type=int, default=50, help="Rows to sample per review sheet")
    review.set_defaults(func=cmd_review)

    ocr = sub.add_parser("ocr", help="OCR configured scanned literature PDFs")
    ocr.add_argument("--out", default="", help="OCR output directory")
    ocr.add_argument("--scale", type=float, default=2.0, help="PDF render scale")
    ocr.set_defaults(func=cmd_ocr)

    docs = sub.add_parser("docs", help="Print key documentation paths")
    docs.set_defaults(func=cmd_docs)

    test = sub.add_parser("test", help="Run the test suite")
    test.set_defaults(func=cmd_test)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
