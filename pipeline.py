# -*- coding: utf-8 -*-
"""
全流程串联脚本
  python pipeline.py -i corpus.docx -o output/ -t "China; India" --country
  python pipeline.py -i corpus.docx -o output/ --skip 3,4        # 跳过步骤3和4
  python pipeline.py -i corpus.docx -o output/ --only 1,2        # 只运行步骤1和2
  python pipeline.py -i corpus.docx -o output/ --force           # 强制覆盖已有输出

Steps:
  1. Lexis DOCX → TXT语料 + report JSON
  2. report JSON → sources.xlsx（机构统计表）
  3. 机构合并 + 国别识别 → merged.xlsx
  4. TXT语料 → 修饰形容词/短语统计（合并所有TXT为单个语料分析）
  5. 形容词表 → 词性识别 + 中文翻译
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
from shared.validation import generate_validation_artifacts

logger = logging.getLogger("pipeline")


def _print_log(msg: str) -> None:
    print(msg)


def _parse_step_args(args: argparse.Namespace):
    skip_set = {int(s.strip()) for s in args.skip.split(",") if s.strip()}
    only_set = {int(s.strip()) for s in args.only.split(",") if s.strip()}
    if only_set:
        steps_to_run = sorted(only_set & set(STEPS.keys()))
    else:
        steps_to_run = sorted(s for s in STEPS.keys() if s not in skip_set)
    return steps_to_run


def _filter_by_targets(steps: List[int], targets: str) -> List[int]:
    if not targets:
        print("⚠ 未指定 -t 目标关键词，步骤4/5将跳过。")
        return [s for s in steps if s not in (4, 5)]
    return steps


def _filter_by_force(steps: List[int], out_dir: Path, force: bool) -> List[int]:
    run_steps: List[int] = []
    for s in steps:
        if not force and check_step_done(s, str(out_dir)):
            print(f"[步骤{s}] {STEPS[s]} — 已有输出，跳过 (--force 强制重跑)")
            continue
        run_steps.append(s)
    return run_steps


def main():
    parser = argparse.ArgumentParser(
        description="新闻语料文本分析全流程串联",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python pipeline.py -i corpus.docx -o output/
  python pipeline.py -i corpus.docx -o output/ -t "China; India; Global South"
  python pipeline.py -i corpus.docx -o output/ --no-country
  python pipeline.py -i corpus.docx -o output/ --skip 5
  python pipeline.py -i corpus.docx -o output/ --only 3,4
  python pipeline.py -i corpus.docx -o output/ --force
        """,
    )
    parser.add_argument("-i", "--input", required=True, help="LexisNexis 导出的 DOCX 文件")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    parser.add_argument("-t", "--targets", default="", help="检索目标关键词，多个用 ; 分隔（步骤4需要）")
    parser.add_argument("--country", action="store_true", default=True, dest="country",
                        help="联网推断国别（默认开启）")
    parser.add_argument("--no-country", action="store_false", dest="country",
                        help="禁联网国别推断")
    parser.add_argument("--skip", default="", help="跳过的步骤编号，逗号分隔 (例: 4,5)")
    parser.add_argument("--only", default="", help="只运行的步骤编号，逗号分隔 (例: 1,2,3)")
    parser.add_argument("--force", action="store_true", help="强制覆盖已有输出")
    parser.add_argument("-q", "--quiet", action="store_true", help="安静模式")

    args = parser.parse_args()

    if args.quiet:
        logger.setLevel(logging.WARNING)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    steps_to_run = _parse_step_args(args)
    steps_to_run = _filter_by_targets(steps_to_run, args.targets)
    run_steps = _filter_by_force(steps_to_run, out_dir, args.force)

    run_config = build_run_config(args, steps_to_run, run_steps)
    run_config_path = write_run_config(out_dir, run_config)

    if not run_steps:
        run_config["status"] = "skipped"
        run_config["reason"] = "all requested outputs already exist"
        write_run_config(out_dir, run_config)
        print("所有步骤已完成，无需运行。")
        return

    print(f"={' 全流程串联 ':=^60}")
    print(f"输入: {args.input}")
    print(f"输出: {out_dir.absolute()}")
    print(f"步骤: {run_steps}")
    print(f"目标: {args.targets or '(跳过修饰分析)'}")
    print(f"国别: {'开启' if args.country else '关闭'}")
    print(f"运行记录: {run_config_path}")
    print(f"{'='*60}\n")

    state: Dict[str, Any] = {}
    failed = False

    try:
        if 1 in run_steps:
            print(f"[步骤1] {STEPS[1]}")
            state["s1"] = s1_docx_to_txt(args.input, str(out_dir), log_fn=_print_log)
            print()

        if 2 in run_steps:
            print(f"[步骤2] {STEPS[2]}")
            report_path: Optional[str] = state.get("s1", {}).get("report_path")
            if not report_path:
                report_files = sorted((out_dir / "corpus").glob("report-*.json"))
                if report_files:
                    report_path = str(report_files[-1])
            if not report_path:
                raise FileNotFoundError("未找到步骤1的报告JSON，请确保步骤1已完成")
            state["s2"] = s2_json_to_excel(report_path, str(out_dir), log_fn=_print_log)
            print()

        if 3 in run_steps:
            print(f"[步骤3] {STEPS[3]}")
            source_excel: str = state.get("s2", {}).get("excel_path") or str(out_dir / "source_counts.xlsx")
            state["s3"] = s3_merge_and_country(source_excel, str(out_dir), enable_country=args.country, log_fn=_print_log)
            print()

        if 4 in run_steps:
            print(f"[步骤4] {STEPS[4]}")
            corpus_dir: str = state.get("s1", {}).get("corpus_dir") or str(out_dir / "corpus")
            state["s4"] = s4_extract_adjectives(corpus_dir, str(out_dir), args.targets, log_fn=_print_log)
            print()

        if 5 in run_steps:
            adj_path: str = state.get("s4", {}).get("adj_excel_path") or str(out_dir / "adjectives_phrases.xlsx")
            if Path(adj_path).exists():
                print(f"[步骤5] {STEPS[5]}")
                state["s5"] = s5_pos_and_translate(adj_path, str(out_dir), log_fn=_print_log)
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
        sys.exit(1)
    else:
        validation_paths = generate_validation_artifacts(out_dir)
        state["validation"] = validation_paths
        run_config["status"] = "completed"
        run_config["state"] = state
        write_run_config(out_dir, run_config)
        print(f"{'='*60}")
        print(f"✅ 全流程完成！输出目录: {out_dir.absolute()}")
        print(f"复核/验证材料: {out_dir / '06_review'} ; {out_dir / '07_reports'}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
