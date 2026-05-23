# -*- coding: utf-8 -*-
"""Legacy compatibility entry point for the CADS pipeline.

Prefer the unified CLI:
    python research_tool.py run -i corpus.docx -o output/ -t "China; India"
"""

from __future__ import annotations

import argparse
import logging

from shared.cli_pipeline import run_cli_pipeline

logger = logging.getLogger("pipeline")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the legacy LexisNexis corpus analysis pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py -i corpus.docx -o output/
  python pipeline.py -i corpus.docx -o output/ -t "China; India; Global South"
  python pipeline.py -i corpus.docx -o output/ --no-country
  python pipeline.py -i corpus.docx -o output/ --skip 5
  python pipeline.py -i corpus.docx -o output/ --only 3,4
  python pipeline.py -i corpus.docx -o output/ --force
        """,
    )
    parser.add_argument("-i", "--input", required=True, help="Input LexisNexis DOCX file")
    parser.add_argument("-o", "--output", required=True, help="Output directory")
    parser.add_argument("--corpus-type", default="news_lexis", help="Corpus template/type for normalized metadata")
    parser.add_argument("-t", "--targets", default="", help="Target terms separated by semicolons")
    parser.add_argument("--country", action="store_true", default=True, dest="country", help="Enable country inference")
    parser.add_argument("--no-country", action="store_false", dest="country", help="Disable country inference")
    parser.add_argument("--skip", default="", help="Pipeline steps to skip, e.g. 4,5")
    parser.add_argument("--only", default="", help="Pipeline steps to run, e.g. 1,2,3")
    parser.add_argument("--force", action="store_true", help="Force rerun existing outputs")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print("pipeline.py is deprecated; use the unified CLI instead:")
    print("   python research_tool.py run -i <input> -o <output> -t <targets>")
    print("   python research_tool.py project run -p <project_dir> -i <input> -t <targets>")
    print()

    if args.quiet:
        logger.setLevel(logging.WARNING)

    return run_cli_pipeline(args)


if __name__ == "__main__":
    raise SystemExit(main())
