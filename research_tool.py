# -*- coding: utf-8 -*-
"""Unified CLI for the research text-analysis toolkit."""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "0.0.0"

logger = logging.getLogger("research_tool")


def cmd_run(args):
    from shared.cli_pipeline import run_cli_pipeline

    if args.quiet:
        logger.setLevel(logging.WARNING)

    return run_cli_pipeline(args)



def cmd_review(args):
    from shared.project_workflow import ensure_project, project_review

    ensure_project(args.output_dir)
    paths = project_review(args.output_dir, sample_size=args.sample_size,
                           dual_coder=args.dual_coder)
    for name, path in paths.items():
        print(f"{name}: {path}")
    if args.dual_coder:
        print("\nDual-coder review files generated. After both coders complete their annotations, run:")
        print(f"  python research_tool.py review {args.output_dir}")
        print("The validation report will include an InterraterReliability sheet.")
    return 0


def cmd_import(args):
    from shared.project_workflow import ensure_project, project_import

    ensure_project(args.output, corpus_type=args.corpus_type, targets=args.targets)
    paths = project_import(
        args.output,
        input_path=args.input,
        corpus_type=args.corpus_type,
        targets=args.targets,
        default_source=args.default_source,
        text_col=args.text_col,
        title_col=args.title_col,
        source_col=args.source_col,
        date_col=args.date_col,
        group_col=args.group_col,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


def cmd_analyze(args):
    from shared.project_workflow import ensure_project, project_analyze

    ensure_project(args.output, corpus_type=args.corpus_type, targets=args.targets)
    outputs = project_analyze(
        args.output,
        targets=args.targets,
        corpus_type=args.corpus_type,
        corpus_dir=args.corpus_dir,
        pos_translate=args.pos_translate,
        force=args.force,
    )
    print(f"analysis_output: {outputs['analysis_output']}")
    return 0


def cmd_ocr(args):
    import subprocess

    command = [sys.executable, str(ROOT / "tools" / "ocr_scanned_pdfs.py")]
    if args.out:
        command.extend(["--out", args.out])
    if args.scale:
        command.extend(["--scale", str(args.scale)])
    completed = subprocess.run(command, cwd=str(ROOT))
    return completed.returncode


def cmd_docs(_args):
    docs = [
        ROOT / "docs" / "WORKFLOW.md",
        ROOT / "docs" / "METHODOLOGY.md",
        ROOT / "docs" / "DATA_DICTIONARY.md",
        ROOT / "docs" / "MULTI_CORPUS_IMPORT.md",
        ROOT / "docs" / "PROJECT_WORKFLOW.md",
        ROOT / "docs" / "RESEARCH_TEMPLATES.md",
        ROOT / "docs" / "VALIDATION.md",
        ROOT / "docs" / "literature_notes" / "00_INDEX.md",
        ROOT / "literature_md" / "00_INDEX.md",
    ]
    for path in docs:
        print(path)
    return 0


def cmd_templates(_args):
    from shared.research_templates import list_templates

    for template in list_templates():
        print(f"{template['template_id']}: {template['label']} - {template['description']}")
    return 0


def cmd_lit(args):
    from shared.literature_index import build_index_md, scan_literature, search_literature

    if args.lit_command == "list":
        entries = scan_literature()
        if args.category:
            entries = [e for e in entries if e["category"] == args.category]
        by_cat: dict = {}
        for e in entries:
            by_cat.setdefault(e["category_label"], []).append(e)
        for cat, cat_entries in by_cat.items():
            print(f"\n=== {cat} ({len(cat_entries)} notes) ===")
            for e in cat_entries:
                print(f"  [{e['filename']}] {e['title']}")
        print(f"\nTotal: {len(entries)} notes")
    elif args.lit_command == "search":
        results = search_literature(args.query)
        if not results:
            print(f"No matches for '{args.query}'.")
        else:
            print(f"\n=== {len(results)} matches for '{args.query}' ===\n")
            for r in results:
                print(f"## {r['title']}  [{r['category_label']}]")
                print(f"   {r['path']}")
                for s in r["snippets"]:
                    print(f"   ...{s}...")
                print()
    elif args.lit_command == "index":
        md = build_index_md()
        print(md)
    return 0


def cmd_project(args):
    from shared.project_workflow import (
        init_project,
        project_analyze,
        project_import,
        project_review,
        project_report,
        project_run,
        project_status,
    )

    if args.project_command == "init":
        result = init_project(args.project, corpus_type=args.corpus_type, name=args.name, targets=args.targets)
    elif args.project_command == "import":
        result = project_import(
            args.project,
            input_path=args.input,
            corpus_type=args.corpus_type,
            targets=args.targets,
            default_source=args.default_source,
            text_col=args.text_col,
            title_col=args.title_col,
            source_col=args.source_col,
            date_col=args.date_col,
            group_col=args.group_col,
        )
    elif args.project_command == "analyze":
        result = project_analyze(
            args.project,
            targets=args.targets,
            corpus_type=args.corpus_type,
            corpus_dir=args.corpus_dir,
            pos_translate=args.pos_translate,
            force=args.force,
            mi_threshold=getattr(args, "mi_threshold", 3.0),
        )
    elif args.project_command == "review":
        result = project_review(args.project, sample_size=args.sample_size,
                                dual_coder=getattr(args, "dual_coder", False))
    elif args.project_command == "run":
        result = project_run(
            args.project,
            input_path=args.input,
            corpus_type=args.corpus_type,
            targets=args.targets,
            default_source=args.default_source,
            text_col=args.text_col,
            title_col=args.title_col,
            source_col=args.source_col,
            date_col=args.date_col,
            group_col=args.group_col,
            pos_translate=args.pos_translate,
            mi_threshold=getattr(args, "mi_threshold", 3.0),
        )
    elif args.project_command == "status":
        result = project_status(args.project)
    elif args.project_command == "report":
        result = project_report(args.project, filename=args.filename)
    else:
        raise ValueError(f"Unknown project command: {args.project_command}")

    if isinstance(result, dict):
        for key, value in result.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for sub_key, sub_value in value.items():
                    print(f"  {sub_key}: {sub_value}")
            else:
                print(f"{key}: {value}")
    else:
        print(result)
    return 0


def cmd_test(_args):
    import pytest
    return pytest.main(["-p", "no:cacheprovider", str(ROOT / "tests")])


def build_parser():
    parser = argparse.ArgumentParser(
        description="Research text-analysis workbench: run pipeline, generate review artifacts, OCR literature, and inspect docs."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the full LexisNexis corpus analysis pipeline")
    run.add_argument("-i", "--input", required=True, help="Input LexisNexis DOCX")
    run.add_argument("-o", "--output", required=True, help="Output directory")
    run.add_argument("--corpus-type", default="news_lexis", help="Corpus template/type for normalized metadata")
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
    review.add_argument("--dual-coder", action="store_true", help="Generate separate review files for coder A and B")
    review.set_defaults(func=cmd_review)

    imp = sub.add_parser("import", help="Import TXT/DOCX folders or CSV/Excel text tables into a normalized corpus")
    imp.add_argument("-i", "--input", required=True, help="Input folder, CSV, or Excel file")
    imp.add_argument("-o", "--output", required=True, help="Output directory")
    imp.add_argument("--corpus-type", default="generic", help="Corpus template/type, e.g. policy, academic, interview")
    imp.add_argument("-t", "--targets", default="", help="Optional target terms separated by semicolons")
    imp.add_argument("--default-source", default="", help="Source label for file-folder imports")
    imp.add_argument("--text-col", default="text", help="Text column for CSV/Excel imports")
    imp.add_argument("--title-col", default="", help="Optional title column for CSV/Excel imports")
    imp.add_argument("--source-col", default="", help="Optional source column for CSV/Excel imports")
    imp.add_argument("--date-col", default="", help="Optional date column for CSV/Excel imports")
    imp.add_argument("--group-col", default="", help="Optional grouping column for CSV/Excel imports")
    imp.set_defaults(func=cmd_import)

    analyze = sub.add_parser("analyze", help="Analyze an existing normalized corpus directory")
    analyze.add_argument("-o", "--output", required=True, help="Output directory containing corpus/")
    analyze.add_argument("--corpus-dir", default="", help="Corpus directory; defaults to OUTPUT/corpus")
    analyze.add_argument("--corpus-type", default="generic", help="Corpus template/type for normalized metadata")
    analyze.add_argument("-t", "--targets", required=True, help="Target terms separated by semicolons")
    analyze.add_argument("--pos-translate", action="store_true", help="Also run POS/translation enrichment")
    analyze.add_argument("--force", action="store_true", help="Record force flag in run config")
    analyze.set_defaults(func=cmd_analyze)

    ocr = sub.add_parser("ocr", help="OCR configured scanned literature PDFs")
    ocr.add_argument("--out", default="", help="OCR output directory")
    ocr.add_argument("--scale", type=float, default=2.0, help="PDF render scale")
    ocr.set_defaults(func=cmd_ocr)

    docs = sub.add_parser("docs", help="Print key documentation paths")
    docs.set_defaults(func=cmd_docs)

    templates = sub.add_parser("templates", help="List available research templates")
    templates.set_defaults(func=cmd_templates)

    lit = sub.add_parser("lit", help="Search and browse the literature knowledge base")
    lit_sub = lit.add_subparsers(dest="lit_command", required=True)
    lit_list = lit_sub.add_parser("list", help="List all literature notes by category")
    lit_list.add_argument("-c", "--category", default="", help="Filter by category (e.g. 01_core_must_read)")
    lit_list.set_defaults(func=cmd_lit)
    lit_search = lit_sub.add_parser("search", help="Full-text search literature notes")
    lit_search.add_argument("query", help="Search term(s)")
    lit_search.set_defaults(func=cmd_lit)
    lit_index = lit_sub.add_parser("index", help="Print auto-generated 00_INDEX.md")
    lit_index.set_defaults(func=cmd_lit)

    project = sub.add_parser("project", help="Project-level workflow commands")
    project_sub = project.add_subparsers(dest="project_command", required=True)

    p_init = project_sub.add_parser("init", help="Initialize a corpus research project")
    p_init.add_argument("-p", "--project", required=True, help="Project directory")
    p_init.add_argument("--name", default="", help="Optional project name")
    p_init.add_argument("--corpus-type", default="generic", help="Research template/corpus type")
    p_init.add_argument("-t", "--targets", default="", help="Default target terms")
    p_init.set_defaults(func=cmd_project)

    p_import = project_sub.add_parser("import", help="Import files or a table into a project corpus")
    p_import.add_argument("-p", "--project", required=True, help="Project directory")
    p_import.add_argument("-i", "--input", required=True, help="Input folder, CSV, or Excel file")
    p_import.add_argument("--corpus-type", default=None, help="Override project corpus type")
    p_import.add_argument("-t", "--targets", default=None, help="Override project target terms")
    p_import.add_argument("--default-source", default="", help="Source label for file-folder imports")
    p_import.add_argument("--text-col", default="text", help="Text column for CSV/Excel imports")
    p_import.add_argument("--title-col", default="", help="Optional title column for CSV/Excel imports")
    p_import.add_argument("--source-col", default="", help="Optional source column for CSV/Excel imports")
    p_import.add_argument("--date-col", default="", help="Optional date column for CSV/Excel imports")
    p_import.add_argument("--group-col", default="", help="Optional grouping column for CSV/Excel imports")
    p_import.set_defaults(func=cmd_project)

    p_analyze = project_sub.add_parser("analyze", help="Analyze the project corpus")
    p_analyze.add_argument("-p", "--project", required=True, help="Project directory")
    p_analyze.add_argument("-t", "--targets", default=None, help="Override project target terms")
    p_analyze.add_argument("--corpus-type", default=None, help="Override project corpus type")
    p_analyze.add_argument("--corpus-dir", default="", help="Corpus directory; defaults to PROJECT/corpus")
    p_analyze.add_argument("--pos-translate", action="store_true", help="Also run POS/translation enrichment")
    p_analyze.add_argument("--mi-threshold", type=float, default=3.0, help="MI threshold for significant collocation (default 3.0)")
    p_analyze.add_argument("--force", action="store_true", help="Record force flag in run config")
    p_analyze.set_defaults(func=cmd_project)

    p_review = project_sub.add_parser("review", help="Generate project review templates and validation report")
    p_review.add_argument("-p", "--project", required=True, help="Project directory")
    p_review.add_argument("--sample-size", type=int, default=50, help="Rows to sample per review sheet")
    p_review.add_argument("--dual-coder", action="store_true", help="Generate separate review files for coder A and B")
    p_review.set_defaults(func=cmd_project)

    p_run = project_sub.add_parser("run", help="Import, analyze, and generate review artifacts in one command")
    p_run.add_argument("-p", "--project", required=True, help="Project directory")
    p_run.add_argument("-i", "--input", required=True, help="Input folder, CSV, or Excel file")
    p_run.add_argument("--corpus-type", default=None, help="Override project corpus type")
    p_run.add_argument("-t", "--targets", default=None, help="Override project target terms")
    p_run.add_argument("--default-source", default="", help="Source label for file-folder imports")
    p_run.add_argument("--text-col", default="text", help="Text column for CSV/Excel imports")
    p_run.add_argument("--title-col", default="", help="Optional title column for CSV/Excel imports")
    p_run.add_argument("--source-col", default="", help="Optional source column for CSV/Excel imports")
    p_run.add_argument("--date-col", default="", help="Optional date column for CSV/Excel imports")
    p_run.add_argument("--group-col", default="", help="Optional grouping column for CSV/Excel imports")
    p_run.add_argument("--pos-translate", action="store_true", help="Also run POS/translation enrichment")
    p_run.add_argument("--mi-threshold", type=float, default=3.0, help="MI threshold for significant collocation (default 3.0)")
    p_run.set_defaults(func=cmd_project)

    p_status = project_sub.add_parser("status", help="Show project status and suggested next step")
    p_status.add_argument("-p", "--project", required=True, help="Project directory")
    p_status.set_defaults(func=cmd_project)

    p_report = project_sub.add_parser("report", help="Generate a Markdown project research report")
    p_report.add_argument("-p", "--project", required=True, help="Project directory")
    p_report.add_argument("--filename", default="research_report.md", help="Report filename inside 07_reports/")
    p_report.set_defaults(func=cmd_project)

    test = sub.add_parser("test", help="Run the test suite")
    test.set_defaults(func=cmd_test)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
