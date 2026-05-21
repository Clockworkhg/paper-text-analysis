# -*- coding: utf-8 -*-
"""Unified CLI for the research text-analysis toolkit."""

import argparse
import logging
import sys
from pathlib import Path

from shared.validation import generate_validation_artifacts

ROOT = Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "0.0.0"

logger = logging.getLogger("research_tool")


def cmd_run(args):
    from shared.pipeline_steps import (
        STEPS,
        check_step_done,
        s1_docx_to_txt,
        s2_json_to_excel,
        s3_merge_and_country,
        s4_extract_adjectives,
        s5_pos_and_translate,
    )
    from shared.research_output import build_run_config, write_run_config

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.quiet:
        logger.setLevel(logging.WARNING)

    skip_set = {int(s.strip()) for s in args.skip.split(",") if s.strip()}
    only_set = {int(s.strip()) for s in args.only.split(",") if s.strip()}

    if only_set:
        steps_to_run = sorted(only_set & set(STEPS.keys()))
    else:
        steps_to_run = sorted(s for s in STEPS.keys() if s not in skip_set)

    if not args.targets:
        print("⚠ 未指定 -t 目标关键词，步骤4/5将跳过。")
        steps_to_run = [s for s in steps_to_run if s not in (4, 5)]

    run_steps = []
    for s in steps_to_run:
        if s in skip_set:
            continue
        if not args.force and check_step_done(s, str(out_dir)):
            print(f"[步骤{s}] {STEPS[s]} — 已有输出，跳过 (--force 强制重跑)")
            continue
        run_steps.append(s)

    run_config = build_run_config(args, steps_to_run, run_steps)
    write_run_config(out_dir, run_config)

    if not run_steps:
        run_config["status"] = "skipped"
        run_config["reason"] = "all requested outputs already exist"
        write_run_config(out_dir, run_config)
        print("所有步骤已完成，无需运行。")
        return 0

    def _log(msg: str) -> None:
        print(msg)

    print(f"={' 全流程串联 ':=^60}")
    print(f"输入: {args.input}")
    print(f"输出: {out_dir.absolute()}")
    print(f"步骤: {run_steps}")
    print(f"目标: {args.targets or '(跳过修饰分析)'}")
    print(f"国别: {'开启' if args.country else '关闭'}")
    print(f"{'='*60}\n")

    state = {}
    failed = False

    try:
        if 1 in run_steps:
            print(f"[步骤1] {STEPS[1]}")
            state["s1"] = s1_docx_to_txt(args.input, str(out_dir), log_fn=_log)
            print()

        if 2 in run_steps:
            print(f"[步骤2] {STEPS[2]}")
            report_path = state.get("s1", {}).get("report_path")
            if not report_path:
                report_files = sorted((out_dir / "corpus").glob("report-*.json"))
                if report_files:
                    report_path = str(report_files[-1])
            if not report_path:
                raise FileNotFoundError("未找到步骤1的报告JSON，请确保步骤1已完成")
            state["s2"] = s2_json_to_excel(report_path, str(out_dir), log_fn=_log)
            print()

        if 3 in run_steps:
            print(f"[步骤3] {STEPS[3]}")
            source_excel = state.get("s2", {}).get("excel_path") or str(out_dir / "source_counts.xlsx")
            state["s3"] = s3_merge_and_country(source_excel, str(out_dir), enable_country=args.country, log_fn=_log)
            print()

        if 4 in run_steps:
            print(f"[步骤4] {STEPS[4]}")
            corpus_dir = state.get("s1", {}).get("corpus_dir") or str(out_dir / "corpus")
            state["s4"] = s4_extract_adjectives(corpus_dir, str(out_dir), args.targets, log_fn=_log)
            print()

        if 5 in run_steps:
            adj_path = state.get("s4", {}).get("adj_excel_path") or str(out_dir / "adjectives_phrases.xlsx")
            if Path(adj_path).exists():
                print(f"[步骤5] {STEPS[5]}")
                state["s5"] = s5_pos_and_translate(adj_path, str(out_dir), log_fn=_log)
                print()
            else:
                print("[步骤5] 跳过 — 形容词表不存在，请先运行步骤4")

    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断")
        failed = True
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        failed = True

    if failed:
        run_config["status"] = "failed"
        run_config["state"] = state
        write_run_config(out_dir, run_config)
        print(f"\n{'='*60}")
        print("流程中断，部分结果已保存到上一步。")
        return 1
    else:
        validation_paths = generate_validation_artifacts(out_dir)
        state["validation"] = validation_paths
        run_config["status"] = "completed"
        run_config["state"] = state
        write_run_config(out_dir, run_config)
        print(f"{'='*60}")
        print(f"✅ 全流程完成！输出目录: {out_dir.absolute()}")
        return 0


def cmd_review(args):
    paths = generate_validation_artifacts(Path(args.output_dir), sample_size=args.sample_size)
    for name, path in paths.items():
        print(f"{name}: {path}")
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
        ROOT / "docs" / "VALIDATION.md",
        ROOT / "docs" / "literature_notes" / "00_INDEX.md",
    ]
    for path in docs:
        print(path)
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
