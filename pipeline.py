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
import json
import os
import sys
from pathlib import Path

import pandas as pd


STEPS = {
    1: "Lexis DOCX → TXT + 统计报告",
    2: "统计JSON → 机构统计表 Excel",
    3: "机构合并 + 国别识别",
    4: "TX语料 → 修饰形容词/短语统计",
    5: "形容词表 → 词性 + 中文翻译",
}


def s1_docx_to_txt(docx_path, out_dir):
    from docx import Document
    from LexisWordToTxt.app.processor import process_docx, write_report_json, preflight_check
    from LexisWordToTxt.app.constants import DEFAULT_SOURCE_CANONICAL_MAP, DEFAULT_NOISE_KEYWORDS

    docx = Path(docx_path)
    if not docx.exists():
        raise FileNotFoundError(f"输入文件不存在: {docx_path}")

    out = Path(out_dir) / "corpus"
    out.mkdir(parents=True, exist_ok=True)

    doc = Document(docx)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    check = preflight_check(full_text)
    if not check["ok"]:
        print(f"  ⚠ 预检警告: {'; '.join(check['messages'])}")

    count, empty, report = process_docx(
        docx_path=docx,
        out_dir=out,
        write_metadata=True,
        filename_max_len=80,
        group_by_source=True,
        canonical_map=DEFAULT_SOURCE_CANONICAL_MAP,
        noise_keywords=DEFAULT_NOISE_KEYWORDS,
        normalize_source=True,
        log_fn=lambda msg: print(f"  {msg}"),
    )

    report_path = write_report_json(out, report)
    print(f"  文章数: {count}, 空正文: {empty}")
    print(f"  TXT输出: {out}")
    print(f"  报告JSON: {report_path}")
    return {"count": count, "empty": empty, "report_path": str(report_path), "corpus_dir": str(out)}


def s2_json_to_excel(report_path, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    excel_path = out / "source_counts.xlsx"

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "by_source_count" not in data or not isinstance(data["by_source_count"], dict):
        raise ValueError("JSON 缺少 by_source_count 字段")

    sources = data["by_source_count"]
    df = pd.DataFrame(
        [{"Source": k, "Count": v} for k, v in sources.items()]
    ).sort_values("Count", ascending=False)

    df.to_excel(str(excel_path), index=False)
    print(f"  机构数: {len(df)}")
    print(f"  输出: {excel_path}")
    return {"excel_path": str(excel_path), "source_count": len(df)}


def s3_merge_and_country(source_excel_path, out_dir, enable_country=True):
    from config import MergeConfig
    from hebing import run_hebing

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    merged_path = out / "merged_sources.xlsx"

    cfg = MergeConfig(
        fuzzy_threshold=92,
        enable_country_lookup=enable_country,
        request_delay_ms=150,
        max_lookup=800,
        auto_accept_threshold=0.85,
        pie_topn=12,
    )

    run_hebing(
        in_path=source_excel_path,
        out_path=str(merged_path),
        overrides_path="",
        cfg=cfg,
        verbose=True,
    )

    print(f"  合并+国别输出: {merged_path}")
    return {"merged_path": str(merged_path)}


def s4_extract_adjectives(corpus_dir, out_dir, targets):
    from config import TxtAnalysisConfig
    from txt_modifier_extractor_gui import process_txt, split_targets

    corpus = Path(corpus_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    all_txt_files = list(corpus.rglob("*.txt"))
    if not all_txt_files:
        raise FileNotFoundError(f"语料目录 {corpus_dir} 下未找到 TXT 文件")

    merged_txt = out / "_corpus_merged.txt"
    with open(merged_txt, "w", encoding="utf-8") as f:
        for tf in all_txt_files:
            try:
                content = tf.read_text(encoding="utf-8", errors="ignore")
                f.write(content)
                f.write("\n\n==========\n\n")
            except Exception as e:
                print(f"  ⚠ 跳过 {tf.name}: {e}")

    print(f"  合并 {len(all_txt_files)} 个TXT → {merged_txt}")

    target_list = split_targets(targets)
    print(f"  检索目标: {target_list}")

    adj_excel = out / "adjectives_phrases.xlsx"
    cfg = TxtAnalysisConfig(
        split_mode="regex",
        split_regex="====LINE====",
        window_tokens=8,
        phrase_max_tokens=6,
        nlp_batch_size=64,
        max_doc_chars=200000,
        use_online_judge=False,
    )

    process_txt(
        input_path=str(merged_txt),
        output_path=str(adj_excel),
        targets=target_list,
        cfg=cfg,
        log_cb=lambda msg: print(f"  {msg}"),
    )

    print(f"  形容词/短语输出: {adj_excel}")
    return {"adj_excel_path": str(adj_excel)}


def s5_pos_and_translate(adj_excel_path, out_dir):
    from jiacixing import ensure_nltk_data, guess_pos, Translator

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    final_excel = out / "adjectives_final.xlsx"

    ensure_nltk_data()

    df_adj = pd.read_excel(adj_excel_path, sheet_name="Adjectives")
    translator = Translator(concurrency=5)

    words = df_adj["Adjective"].tolist()
    print(f"  词性标注 {len(words)} 词...")
    pos_list = [guess_pos(None if pd.isna(w) else str(w)) for w in words]

    print(f"  中文翻译 {len(words)} 词（并发）...")
    zh_list = translator.translate_batch(
        ["" if pd.isna(w) else str(w) for w in words]
    )

    df_adj["POS"] = pos_list
    df_adj["中文意思"] = zh_list

    df_adj.to_excel(str(final_excel), index=False)
    print(f"  输出: {final_excel}")
    return {"final_excel_path": str(final_excel)}


def check_step_done(step_num, out_dir):
    out = Path(out_dir)
    checks = {
        1: lambda: (out / "corpus").exists() and any((out / "corpus").rglob("*.txt")),
        2: lambda: (out / "source_counts.xlsx").exists(),
        3: lambda: (out / "merged_sources.xlsx").exists(),
        4: lambda: (out / "adjectives_phrases.xlsx").exists(),
        5: lambda: (out / "adjectives_final.xlsx").exists(),
    }
    return checks[step_num]()


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
    out_dir = Path(args.output)

    skip_set = {int(s.strip()) for s in args.skip.split(",") if s.strip()}
    only_set = {int(s.strip()) for s in args.only.split(",") if s.strip()}

    if only_set:
        steps_to_run = sorted(only_set & set(STEPS.keys()))
    else:
        steps_to_run = sorted(s for s in STEPS.keys() if s not in skip_set)

    if args.targets:
        pass
    else:
        print("⚠ 未指定 -t 目标关键词，步骤4将跳过。")
        steps_to_run = [s for s in steps_to_run if s != 4 and s != 5]

    run_steps = []
    for s in steps_to_run:
        if s in skip_set:
            continue
        if not args.force and check_step_done(s, out_dir):
            print(f"[步骤{s}] {STEPS[s]} — 已有输出，跳过 (--force 强制重跑)")
            continue
        run_steps.append(s)

    if not run_steps:
        print("所有步骤已完成，无需运行。")
        return

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
            state["s1"] = s1_docx_to_txt(args.input, out_dir)
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
            state["s2"] = s2_json_to_excel(report_path, out_dir)
            print()

        if 3 in run_steps:
            print(f"[步骤3] {STEPS[3]}")
            source_excel = state.get("s2", {}).get("excel_path") or str(out_dir / "source_counts.xlsx")
            state["s3"] = s3_merge_and_country(source_excel, out_dir, enable_country=args.country)
            print()

        if 4 in run_steps:
            if not args.targets:
                print("[步骤4] 跳过 — 未指定 -t 目标关键词")
            else:
                print(f"[步骤4] {STEPS[4]}")
                corpus_dir = state.get("s1", {}).get("corpus_dir") or str(out_dir / "corpus")
                state["s4"] = s4_extract_adjectives(corpus_dir, out_dir, args.targets)
                print()

        if 5 in run_steps:
            adj_path = state.get("s4", {}).get("adj_excel_path") or str(out_dir / "adjectives_phrases.xlsx")
            if Path(adj_path).exists():
                print(f"[步骤5] {STEPS[5]}")
                state["s5"] = s5_pos_and_translate(adj_path, out_dir)
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
        print(f"\n{'='*60}")
        print("流程中断，部分结果已保存到上一步。")
        sys.exit(1)
    else:
        print(f"{'='*60}")
        print(f"✅ 全流程完成！输出目录: {out_dir.absolute()}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
