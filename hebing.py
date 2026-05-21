# -*- coding: utf-8 -*-
"""
机构合并 + 国别识别（论文稳健版）
- 导入 CSV/XLSX（至少两列：Source, Count）
- 机构名清洗 + 规则归一 + 模糊聚类合并
- 国别识别：overrides(可选) > 强规则 > 启发式(国名/国籍形容词/城市) > Wikidata SPARQL(媒体类型约束)
- 自动生成 SuggestedOverrides（带置信度与证据）
- 支持自动接受阈值：>=阈值的建议自动写入 AutoOverrides 并在本次结果中生效
- 导出 XLSX：WithCountry / CountrySummary / SuggestedOverrides / AutoOverrides / RowMapping
- 导出 PNG：国别扇形图
"""

import re
import time
import json
import threading
import queue
from typing import Dict, List, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz, process

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from config import MergeConfig
from shared.normalization import normalize_basic, strip_variants
from shared.hand_rules import apply_hand_rules, heuristic_country_infer, rule_country_guess
from shared.wikidata import sparql_candidates, pick_best_country
from shared.io_utils import load_overrides, read_table
from shared.pie_chart import save_pie
from shared.gui_base import BaseApp


# =========================
# 合并 + 国别推断 + 建议 overrides
# =========================

def merge_sources(df: pd.DataFrame, source_col: str, count_col: str, cfg: MergeConfig, progress_cb=None):
    df = df.copy()
    df[count_col] = pd.to_numeric(df[count_col], errors="coerce").fillna(0).astype(int)

    df["_source_raw"] = df[source_col].astype(str)
    df["_source_norm"] = df["_source_raw"].apply(normalize_basic).apply(strip_variants)
    df["_work_name"] = df["_source_norm"].apply(apply_hand_rules)

    uniq = df["_work_name"].dropna().unique().tolist()
    canonicals: List[str] = []
    cmap: Dict[str, str] = {}

    for i, name in enumerate(uniq):
        if not canonicals:
            canonicals.append(name)
            cmap[name] = name
        else:
            m = process.extractOne(name, canonicals, scorer=fuzz.token_sort_ratio,
                                   score_cutoff=cfg.fuzzy_threshold)
            if m:
                cmap[name] = m[0]
            else:
                canonicals.append(name)
                cmap[name] = name

        if progress_cb and i % 80 == 0:
            progress_cb(f"Fuzzy merge {i+1}/{len(uniq)}", i / max(1, len(uniq)))

    df["Source_Merged"] = df["_work_name"].map(lambda x: cmap.get(x, x))

    merged = (
        df.groupby("Source_Merged", as_index=False)[count_col]
        .sum()
        .sort_values(count_col, ascending=False)
        .rename(columns={count_col: "Count_Sum"})
    )
    return merged, df


def build_countries_and_suggestions(merged: pd.DataFrame,
                                   cfg: MergeConfig,
                                   base_overrides: Dict[str, str],
                                   progress_cb=None):
    merged = merged.copy()
    merged["Country"] = "Unknown"

    for i, r in merged.iterrows():
        org = r["Source_Merged"]
        if org in base_overrides:
            merged.at[i, "Country"] = base_overrides[org]

    suggested_rows = []
    auto_overrides: Dict[str, str] = {}

    if not cfg.enable_country_lookup:
        sug = pd.DataFrame(columns=["Source_Merged","Suggested_Country","Confidence","Evidence_Top3"])
        return merged, sug, pd.DataFrame(columns=["Source_Merged","Country"])

    unknown_orgs = merged.loc[merged["Country"] == "Unknown", "Source_Merged"].tolist()
    limit = min(len(unknown_orgs), cfg.max_lookup)

    for idx, org in enumerate(unknown_orgs[:limit]):
        if progress_cb:
            progress_cb(f"Country infer {idx+1}/{limit}", idx / max(1, limit))

        rg = rule_country_guess(org)
        if rg:
            country, conf, evidence = rg
            suggested_rows.append({
                "Source_Merged": org,
                "Suggested_Country": country,
                "Confidence": round(conf, 3),
                "Evidence_Top3": evidence,
            })
            if conf >= cfg.auto_accept_threshold:
                auto_overrides[org] = country
            continue

        hg = heuristic_country_infer(org)
        if hg:
            country, conf, evidence = hg
            suggested_rows.append({
                "Source_Merged": org,
                "Suggested_Country": country,
                "Confidence": round(conf, 3),
                "Evidence_Top3": evidence,
            })
            if conf >= cfg.auto_accept_threshold:
                auto_overrides[org] = country
            continue

        try:
            cands = sparql_candidates(org)
        except Exception:
            cands = []

        country, conf, top3 = pick_best_country(org, cands)
        tops = []
        for sc, ct, cand in top3:
            tops.append(
                f"{ct}({sc:.1f})|{cand.get('qid','')}|{cand.get('label','')}|{cand.get('type','')}"
                f"|web={1 if cand.get('website') else 0}|parent={cand.get('parent','')}"
            )
        evidence = "; ".join(tops) if tops else "no_media_typed_candidate_from_wikidata_sparql"

        suggested_rows.append({
            "Source_Merged": org,
            "Suggested_Country": country,
            "Confidence": round(conf, 3),
            "Evidence_Top3": evidence,
        })

        if country != "Unknown" and conf >= cfg.auto_accept_threshold:
            auto_overrides[org] = country

        time.sleep(cfg.request_delay_ms / 1000.0)

    for org in unknown_orgs[limit:]:
        suggested_rows.append({
            "Source_Merged": org,
            "Suggested_Country": "Unknown",
            "Confidence": 0.0,
            "Evidence_Top3": f"skipped_due_to_max_lookup={cfg.max_lookup}",
        })

    suggested = pd.DataFrame(suggested_rows).sort_values(["Confidence","Source_Merged"], ascending=[False, True])

    auto_df = pd.DataFrame([{"Source_Merged": k, "Country": v} for k, v in auto_overrides.items()]) \
        .sort_values(["Country","Source_Merged"])

    if len(auto_overrides) > 0:
        merged["Country"] = merged["Source_Merged"].map(auto_overrides).fillna(merged["Country"])

    return merged, suggested, auto_df


def country_summary(with_country: pd.DataFrame):
    cs = (
        with_country.groupby("Country", as_index=False)["Count_Sum"]
        .sum()
        .sort_values("Count_Sum", ascending=False)
        .rename(columns={"Count_Sum": "Country_Count_Sum"})
    )
    return cs


# =========================
# GUI
# =========================

class App(tk.Tk, BaseApp):
    def __init__(self):
        tk.Tk.__init__(self)
        BaseApp.__init__(self)
        self.title("机构合并 + 国别识别 + SuggestedOverrides + 扇形图（论文稳健版）")
        self.geometry("980x640")

        self.in_path = tk.StringVar()
        self.out_path = tk.StringVar()
        self.overrides_path = tk.StringVar()

        self.threshold = tk.IntVar(value=92)
        self.enable_country = tk.BooleanVar(value=True)
        self.delay_ms = tk.IntVar(value=150)
        self.max_lookup = tk.IntVar(value=800)
        self.auto_accept = tk.DoubleVar(value=0.85)
        self.pie_topn = tk.IntVar(value=12)

        self.status = tk.StringVar(value="等待输入…")

        self._build_ui()
        self.setup_polling(self, 120)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=12, pady=12)

        lf1 = ttk.LabelFrame(frm, text="1) 输入文件（CSV / XLSX）")
        lf1.pack(fill="x", **pad)
        ttk.Entry(lf1, textvariable=self.in_path).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(lf1, text="浏览…", command=self.pick_in).pack(side="left", padx=8, pady=8)

        lf2 = ttk.LabelFrame(frm, text="2) 输出文件（XLSX / CSV）")
        lf2.pack(fill="x", **pad)
        ttk.Entry(lf2, textvariable=self.out_path).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(lf2, text="浏览…", command=self.pick_out).pack(side="left", padx=8, pady=8)

        lf3 = ttk.LabelFrame(frm, text="3) 可选：加载 overrides（两列：Source_Merged, Country）")
        lf3.pack(fill="x", **pad)
        ttk.Entry(lf3, textvariable=self.overrides_path).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(lf3, text="浏览…", command=self.pick_overrides).pack(side="left", padx=8, pady=8)

        lf4 = ttk.LabelFrame(frm, text="4) 参数")
        lf4.pack(fill="x", **pad)

        ttk.Label(lf4, text="模糊合并阈值：").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Scale(lf4, from_=70, to=98, orient="horizontal",
                  command=lambda v: self.threshold.set(int(float(v))), length=240) \
            .grid(row=0, column=1, sticky="w", padx=6, pady=6)
        ttk.Label(lf4, textvariable=self.threshold, width=4).grid(row=0, column=2, sticky="w", padx=6, pady=6)

        ttk.Checkbutton(lf4, text="联网推断国别（Wikidata SPARQL, 媒体类型约束）", variable=self.enable_country) \
            .grid(row=0, column=3, sticky="w", padx=18, pady=6)

        ttk.Label(lf4, text="请求间隔(ms)：").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(lf4, textvariable=self.delay_ms, width=8).grid(row=1, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(lf4, text="最多推断机构数：").grid(row=1, column=2, sticky="w", padx=8, pady=6)
        ttk.Entry(lf4, textvariable=self.max_lookup, width=10).grid(row=1, column=3, sticky="w", padx=6, pady=6)

        ttk.Label(lf4, text="自动接受阈值(0-1)：").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(lf4, textvariable=self.auto_accept, width=8).grid(row=2, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(lf4, text="扇形图 Top N：").grid(row=2, column=2, sticky="w", padx=8, pady=6)
        ttk.Entry(lf4, textvariable=self.pie_topn, width=8).grid(row=2, column=3, sticky="w", padx=6, pady=6)

        lf5 = ttk.LabelFrame(frm, text="5) 运行")
        lf5.pack(fill="x", **pad)
        self.pbar = ttk.Progressbar(lf5, length=700, mode="determinate")
        self.pbar.pack(side="left", padx=8, pady=10)
        ttk.Button(lf5, text="开始", command=self.start).pack(side="left", padx=10, pady=10)

        lf6 = ttk.LabelFrame(frm, text="日志")
        lf6.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(lf6, height=14)
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)
        self._log("导出 XLSX：WithCountry / CountrySummary / SuggestedOverrides / AutoOverrides / RowMapping")
        self._log("导出 PNG：*_country_pie.png")

        ttk.Label(frm, textvariable=self.status).pack(anchor="w", padx=14, pady=(4, 0))

    def _log(self, msg: str):
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")

    def pick_in(self):
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"), ("All", "*.*")])
        if p:
            self.in_path.set(p)

    def pick_out(self):
        p = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if p:
            self.out_path.set(p)

    def pick_overrides(self):
        p = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls"), ("CSV", "*.csv"), ("All", "*.*")])
        if p:
            self.overrides_path.set(p)

    def start(self):
        in_path = self.in_path.get().strip()
        out_path = self.out_path.get().strip()
        if not in_path or not out_path:
            messagebox.showerror("错误", "请先选择输入文件和输出路径。")
            return

        cfg = MergeConfig(
            fuzzy_threshold=int(self.threshold.get()),
            enable_country_lookup=bool(self.enable_country.get()),
            request_delay_ms=int(self.delay_ms.get()),
            max_lookup=int(self.max_lookup.get()),
            auto_accept_threshold=float(self.auto_accept.get()),
            pie_topn=int(self.pie_topn.get()),
        )

        self.pbar["value"] = 0
        self.status.set("运行中…")
        self._log(f"开始：threshold={cfg.fuzzy_threshold}, country={cfg.enable_country_lookup}, "
                  f"delay={cfg.request_delay_ms}ms, max={cfg.max_lookup}, auto_accept>={cfg.auto_accept_threshold}")

        threading.Thread(target=self._worker, args=(in_path, out_path, self.overrides_path.get().strip(), cfg), daemon=True).start()

    def _worker(self, in_path: str, out_path: str, overrides_path: str, cfg: MergeConfig):
        try:
            df = read_table(in_path)

            self.put_log(f"读取 {len(df)} 行，列：{list(df.columns)}")

            cols_lower = {c.lower().strip(): c for c in df.columns}
            source_col = cols_lower.get("source") or cols_lower.get("来源") or df.columns[0]
            count_col = cols_lower.get("count") or cols_lower.get("篇数") or df.columns[1]
            self.put_log(f"使用列：Source={source_col}, Count={count_col}")

            base_overrides = load_overrides(overrides_path)
            if base_overrides:
                self.put_log(f"加载 overrides 条目数：{len(base_overrides)}")
            else:
                self.put_log("未加载 overrides（或为空）")

            merged, rowmap = merge_sources(
                df, source_col, count_col, cfg,
                progress_cb=lambda msg, frac: self.put_progress(msg, frac),
            )
            self.put_log(f"合并后机构数：{len(merged)}")

            with_country, suggested, auto_df = build_countries_and_suggestions(
                merged, cfg, base_overrides,
                progress_cb=lambda msg, frac: self.put_progress(msg, frac),
            )
            cs = country_summary(with_country)

            base = out_path
            if out_path.lower().endswith(".csv"):
                base = re.sub(r"\.csv$", "", out_path, flags=re.IGNORECASE)
            else:
                base = re.sub(r"\.xlsx$", "", out_path, flags=re.IGNORECASE)

            png_path = base + "_country_pie.png"
            save_pie(cs, png_path, top_n=cfg.pie_topn)

            if out_path.lower().endswith(".csv"):
                with_country.to_csv(out_path, index=False, encoding="utf-8-sig")
                cs.to_csv(base + "_country_summary.csv", index=False, encoding="utf-8-sig")
                suggested.to_csv(base + "_suggested_overrides.csv", index=False, encoding="utf-8-sig")
                auto_df.to_csv(base + "_auto_overrides.csv", index=False, encoding="utf-8-sig")
                rowmap.to_csv(base + "_row_mapping.csv", index=False, encoding="utf-8-sig")
            else:
                with pd.ExcelWriter(out_path, engine="openpyxl") as w:
                    with_country.to_excel(w, index=False, sheet_name="WithCountry")
                    cs.to_excel(w, index=False, sheet_name="CountrySummary")
                    suggested.to_excel(w, index=False, sheet_name="SuggestedOverrides")
                    auto_df.to_excel(w, index=False, sheet_name="AutoOverrides")
                    rowmap.to_excel(w, index=False, sheet_name="RowMapping")

            self.put_log(f"扇形图：{png_path}")
            self.put_done(f"导出完成：{out_path}\n扇形图：{png_path}")

        except Exception as e:
            self.put_error(str(e))

    def on_progress(self, msg: str, frac: float):
        self.status.set(msg)
        self.pbar["value"] = max(0, min(100, int(frac * 100)))

    def on_log(self, msg: str):
        self._log(msg)

    def on_done(self, msg: str):
        self.status.set(msg)
        self.pbar["value"] = 100
        messagebox.showinfo("完成", msg)

    def on_error(self, msg: str):
        self.status.set("出错")
        messagebox.showerror("出错", msg)


def run_hebing(in_path: str, out_path: str, overrides_path: str = "",
               cfg: MergeConfig = None, verbose: bool = True):
    if cfg is None:
        cfg = MergeConfig()

    df = read_table(in_path)
    if verbose:
        print(f"读取 {len(df)} 行，列：{list(df.columns)}")

    cols_lower = {c.lower().strip(): c for c in df.columns}
    source_col = cols_lower.get("source") or cols_lower.get("来源") or df.columns[0]
    count_col = cols_lower.get("count") or cols_lower.get("篇数") or df.columns[1]
    if verbose:
        print(f"使用列：Source={source_col}, Count={count_col}")

    base_overrides = load_overrides(overrides_path)
    if verbose and base_overrides:
        print(f"加载 overrides 条目数：{len(base_overrides)}")

    merged, rowmap = merge_sources(df, source_col, count_col, cfg)
    if verbose:
        print(f"合并后机构数：{len(merged)}")

    with_country, suggested, auto_df = build_countries_and_suggestions(
        merged, cfg, base_overrides,
        progress_cb=lambda msg, frac: print(f"  {msg}") if verbose else None,
    )
    cs = country_summary(with_country)

    base = out_path
    if out_path.lower().endswith(".csv"):
        base = re.sub(r"\.csv$", "", out_path, flags=re.IGNORECASE)
    else:
        base = re.sub(r"\.xlsx$", "", out_path, flags=re.IGNORECASE)

    png_path = base + "_country_pie.png"
    save_pie(cs, png_path, top_n=cfg.pie_topn)

    config_path = base + "_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        cfg_dict = {
            "fuzzy_threshold": cfg.fuzzy_threshold,
            "enable_country_lookup": cfg.enable_country_lookup,
            "request_delay_ms": cfg.request_delay_ms,
            "max_lookup": cfg.max_lookup,
            "auto_accept_threshold": cfg.auto_accept_threshold,
            "pie_topn": cfg.pie_topn,
        }
        json.dump(cfg_dict, f, ensure_ascii=False, indent=2)

    if out_path.lower().endswith(".csv"):
        with_country.to_csv(out_path, index=False, encoding="utf-8-sig")
        cs.to_csv(base + "_country_summary.csv", index=False, encoding="utf-8-sig")
        suggested.to_csv(base + "_suggested_overrides.csv", index=False, encoding="utf-8-sig")
        auto_df.to_csv(base + "_auto_overrides.csv", index=False, encoding="utf-8-sig")
        rowmap.to_csv(base + "_row_mapping.csv", index=False, encoding="utf-8-sig")
    else:
        with pd.ExcelWriter(out_path, engine="openpyxl") as w:
            with_country.to_excel(w, index=False, sheet_name="WithCountry")
            cs.to_excel(w, index=False, sheet_name="CountrySummary")
            suggested.to_excel(w, index=False, sheet_name="SuggestedOverrides")
            auto_df.to_excel(w, index=False, sheet_name="AutoOverrides")
            rowmap.to_excel(w, index=False, sheet_name="RowMapping")

    if verbose:
        print(f"扇形图：{png_path}")
        print(f"配置：{config_path}")
        print(f"导出完成：{out_path}")


def run_cli():
    import argparse
    parser = argparse.ArgumentParser(
        description="机构合并 + 国别识别（论文稳健版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python hebing.py -i sources.csv -o result.xlsx
  python hebing.py -i sources.xlsx -o result.csv --no-country
  python hebing.py -i data.xlsx -o out.xlsx --threshold 90 --delay 200 --max 500 --auto-accept 0.9
  python hebing.py -i data.xlsx -o out.xlsx --overrides manual_overrides.xlsx
        """,
    )
    parser.add_argument("-i", "--input", required=True, help="输入文件路径 (CSV/XLSX)")
    parser.add_argument("-o", "--output", required=True, help="输出文件路径 (XLSX/CSV)")
    parser.add_argument("--overrides", default="", help="可选的 overrides 文件路径")
    parser.add_argument("--threshold", type=int, default=92, help="模糊合并阈值 (70-98, 默认 92)")
    parser.add_argument("--no-country", action="store_true", help="禁用联网国别推断")
    parser.add_argument("--delay", type=int, default=150, help="请求间隔 ms (默认 150)")
    parser.add_argument("--max", dest="max_lookup", type=int, default=800, help="最多推断机构数 (默认 800)")
    parser.add_argument("--auto-accept", type=float, default=0.85, help="自动接受阈值 (默认 0.85)")
    parser.add_argument("--pie-topn", type=int, default=12, help="扇形图 Top N (默认 12)")
    parser.add_argument("-q", "--quiet", action="store_true", help="安静模式")

    args = parser.parse_args()

    cfg = MergeConfig(
        fuzzy_threshold=args.threshold,
        enable_country_lookup=not args.no_country,
        request_delay_ms=args.delay,
        max_lookup=args.max_lookup,
        auto_accept_threshold=args.auto_accept,
        pie_topn=args.pie_topn,
    )

    run_hebing(args.input, args.output, args.overrides, cfg, verbose=not args.quiet)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run_cli()
    else:
        App().mainloop()
