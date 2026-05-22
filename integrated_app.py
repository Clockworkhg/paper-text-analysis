# -*- coding: utf-8 -*-
"""
新闻文本分析集成软件
统一主界面，分页切换各工具模块：
  流水线 / 机构合并+国别 / 修饰形容词分析 / 词性+翻译 / KWIC分析 / 自选合并 / JSON转Excel
"""

import json
import logging
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


from modules.gui_support import COLORS, FileRow, LogPanel, ToolTab, set_window_icon
from modules.gui_tool_tabs import TabColumnMerge, TabJSONtoExcel, TabKWIC

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd

logger = logging.getLogger("integrated_app")


class TabPipeline(ToolTab):
    def __init__(self, master):
        super().__init__(master)
        pad = self._pad

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.targets_var = tk.StringVar()
        self.country_var = tk.BooleanVar(value=True)
        self.force_var = tk.BooleanVar(value=False)
        self.step_vars = {i: tk.BooleanVar(value=True) for i in range(1, 6)}

        row = 0
        FileRow(self, "Lexis DOCX:", "open", [("Word", "*.docx"), ("All", "*.*")], self.input_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "输出目录:", "dir", var=self.output_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1

        tf = ttk.Frame(self)
        tf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Label(tf, text="检索目标:", width=18, anchor="e").pack(side="left", padx=(0, 6))
        ttk.Entry(tf, textvariable=self.targets_var, style="Field.TEntry").pack(side="left", fill="x", expand=True)
        ttk.Label(tf, text="(多个用 ; 分隔)").pack(side="left", padx=(6, 0))

        sf = ttk.LabelFrame(self, text="运行步骤")
        sf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        labels = ["1. DOCX→TXT+报告", "2. JSON→机构统计表", "3. 机构合并+国别", "4. 修饰形容词分析", "5. 词性+翻译"]
        for i, lb in enumerate(labels, 1):
            ttk.Checkbutton(sf, text=lb, variable=self.step_vars[i]).grid(row=0, column=i-1, padx=6, pady=4)

        bf = ttk.Frame(self)
        bf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Checkbutton(bf, text="联网推断国别", variable=self.country_var).pack(side="left")
        ttk.Checkbutton(bf, text="强制覆盖已有输出", variable=self.force_var).pack(side="left", padx=16)
        self.run_btn = ttk.Button(bf, text="▶ 运 行 流 水 线", style="Accent.TButton", command=lambda: self._start(self.run_btn))
        self.run_btn.pack(side="right")

        self._finish(progress_mode="indeterminate", log_height=16)

    def _validate(self):
        if not self.input_var.get() or not self.output_var.get():
            messagebox.showerror("错误", "请选择输入文件和输出目录。")
            return False
        if not any(self.step_vars[i].get() for i in range(1, 6)):
            messagebox.showerror("错误", "请至少选择一个步骤。")
            return False
        return True

    def _worker_impl(self):
        try:
            from shared.pipeline_steps import (
                STEPS, s1_docx_to_txt, s2_json_to_excel, s3_merge_and_country,
            )
            from shared.project_workflow import ensure_project, project_analyze

            inp = self.input_var.get()
            out = Path(self.output_var.get())
            out.mkdir(parents=True, exist_ok=True)
            log_fn = lambda m: self._w_put("log", m)
            targets = self.targets_var.get()
            country = self.country_var.get()
            force = self.force_var.get()
            steps = [i for i in range(1, 6) if self.step_vars[i].get()]
            state: Dict[str, Any] = {}

            if 1 in steps:
                self._w_put("log", f"[步骤1] {STEPS[1]} …")
                state["s1"] = s1_docx_to_txt(inp, str(out), log_fn=log_fn)
                self._w_put("log", "  ✅ 步骤1完成")

            if 2 in steps:
                self._w_put("log", f"[步骤2] {STEPS[2]} …")
                rpt = state.get("s1", {}).get("report_path")
                if not rpt:
                    rpts = sorted((out / "corpus").glob("report-*.json"))
                    rpt = str(rpts[-1]) if rpts else ""
                if not rpt:
                    raise FileNotFoundError("未找到步骤1的报告JSON")
                state["s2"] = s2_json_to_excel(rpt, str(out), log_fn=log_fn)
                self._w_put("log", "  ✅ 步骤2完成")

            if 3 in steps:
                self._w_put("log", f"[步骤3] {STEPS[3]} …")
                src = state.get("s2", {}).get("excel_path") or str(out / "source_counts.xlsx")
                state["s3"] = s3_merge_and_country(src, str(out), enable_country=country, log_fn=log_fn)
                self._w_put("log", "  ✅ 步骤3完成")

            # Delegate s4+s5 to project_workflow
            if (4 in steps or 5 in steps) and targets.strip():
                self._w_put("log", f"[步骤4+5] 修饰语分析 …")
                ensure_project(out, corpus_type="news_lexis", targets=targets)
                corpus_dir = state.get("s1", {}).get("corpus_dir") or str(out / "corpus")
                analyze_outputs = project_analyze(
                    out,
                    targets=targets,
                    corpus_type="news_lexis",
                    corpus_dir=corpus_dir,
                    pos_translate=(5 in steps),
                    force=force,
                )
                state["s4"] = {"adj_excel_path": analyze_outputs["analysis_output"]}
                if 5 in steps and "pos_translation_output" in analyze_outputs:
                    state["s5"] = {"final_excel_path": analyze_outputs["pos_translation_output"]}
                self._w_put("log", "  ✅ 修饰语分析完成")

            # Update status bar
            app = self.winfo_toplevel()
            if hasattr(app, "_load_project_status"):
                app.after(0, lambda: app._load_project_status(str(out)))

            self._w_put("done", f"全流程完成！\n输出目录: {out.absolute()}\n复核/验证材料: {out / '06_review'} ; {out / '07_reports'}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._w_put("error", str(e))


class TabMerge(ToolTab):
    def __init__(self, master):
        super().__init__(master)
        pad = self._pad

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.ov_var = tk.StringVar()
        self.threshold_var = tk.IntVar(value=92)
        self.country_var = tk.BooleanVar(value=True)
        self.delay_var = tk.IntVar(value=150)
        self.max_var = tk.IntVar(value=800)
        self.auto_var = tk.DoubleVar(value=0.85)
        self.topn_var = tk.IntVar(value=12)

        row = 0
        FileRow(self, "输入文件:", "open", [("Excel", "*.xlsx"), ("CSV", "*.csv"), ("All", "*.*")], self.in_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "输出文件:", "save", [("Excel", "*.xlsx"), ("CSV", "*.csv")], self.out_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "Overrides(可选):", "open", [("Excel", "*.xlsx"), ("CSV", "*.csv"), ("All", "*.*")], self.ov_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1

        pf = ttk.LabelFrame(self, text="参数")
        pf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        r1 = ttk.Frame(pf); r1.pack(fill="x", padx=8, pady=4)
        ttk.Label(r1, text="模糊合并阈值:").pack(side="left")
        ttk.Scale(r1, from_=70, to=98, variable=self.threshold_var, orient="horizontal", length=200).pack(side="left", padx=6)
        ttk.Label(r1, textvariable=self.threshold_var, width=3).pack(side="left")
        ttk.Checkbutton(r1, text="联网推断国别", variable=self.country_var).pack(side="left", padx=16)
        self.run_btn = ttk.Button(r1, text="▶ 开始", style="Accent.TButton", command=lambda: self._start(self.run_btn))
        self.run_btn.pack(side="right")

        r2 = ttk.Frame(pf); r2.pack(fill="x", padx=8, pady=4)
        ttk.Label(r2, text="请求间隔ms:").pack(side="left")
        ttk.Entry(r2, textvariable=self.delay_var, width=8, style="Field.TEntry").pack(side="left", padx=4)
        ttk.Label(r2, text="最多推断:").pack(side="left", padx=(12, 0))
        ttk.Entry(r2, textvariable=self.max_var, width=8, style="Field.TEntry").pack(side="left", padx=4)
        ttk.Label(r2, text="自动接受阈值:").pack(side="left", padx=(12, 0))
        ttk.Entry(r2, textvariable=self.auto_var, width=6, style="Field.TEntry").pack(side="left", padx=4)
        ttk.Label(r2, text="饼图TopN:").pack(side="left", padx=(12, 0))
        ttk.Entry(r2, textvariable=self.topn_var, width=6, style="Field.TEntry").pack(side="left", padx=4)

        self._finish(progress_mode="determinate", log_height=14)

    def _w_on_progress(self, msg, frac):
        if hasattr(self, "pbar"):
            self.pbar["value"] = max(0, min(100, int(frac * 100)))

    def _validate(self):
        if not self.in_var.get() or not self.out_var.get():
            messagebox.showerror("错误", "请选择输入和输出文件。")
            return False
        return True

    def _worker_impl(self):
        try:
            from config import MergeConfig
            from modules.hebing import run_hebing
            cfg = MergeConfig(
                fuzzy_threshold=self.threshold_var.get(),
                enable_country_lookup=self.country_var.get(),
                request_delay_ms=self.delay_var.get(),
                max_lookup=self.max_var.get(),
                auto_accept_threshold=self.auto_var.get(),
                pie_topn=self.topn_var.get(),
            )
            run_hebing(self.in_var.get(), self.out_var.get(), self.ov_var.get(), cfg, verbose=True)
            self._w_put("done", f"完成: {self.out_var.get()}")
        except Exception as e:
            self._w_put("error", str(e))


class TabAdjectives(ToolTab):
    def __init__(self, master):
        super().__init__(master)
        pad = self._pad

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.tgt_var = tk.StringVar()
        self.split_var = tk.StringVar(value="blanklines")
        self.split_regex_var = tk.StringVar()
        self.win_var = tk.IntVar(value=8)
        self.phr_var = tk.IntVar(value=6)
        self.batch_var = tk.IntVar(value=64)
        self.maxch_var = tk.IntVar(value=200000)

        row = 0
        FileRow(self, "TXT语料:", "open", [("Text", "*.txt"), ("All", "*.*")], self.in_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "导出Excel:", "save", [("Excel", "*.xlsx")], self.out_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1

        tf = ttk.Frame(self)
        tf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Label(tf, text="检索目标:", width=18, anchor="e").pack(side="left", padx=(0, 6))
        ttk.Entry(tf, textvariable=self.tgt_var, style="Field.TEntry").pack(side="left", fill="x", expand=True)
        ttk.Label(tf, text="(; 分隔)").pack(side="left", padx=(6, 0))

        pf = ttk.LabelFrame(self, text="参数")
        pf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        r1 = ttk.Frame(pf); r1.pack(fill="x", padx=8, pady=4)
        ttk.Radiobutton(r1, text="空行分段", variable=self.split_var, value="blanklines").pack(side="left")
        ttk.Radiobutton(r1, text="每行一篇", variable=self.split_var, value="lines").pack(side="left", padx=8)
        ttk.Radiobutton(r1, text="正则/等号线", variable=self.split_var, value="regex").pack(side="left", padx=8)
        ttk.Entry(r1, textvariable=self.split_regex_var, width=18, style="Field.TEntry").pack(side="left", padx=6)
        ttk.Label(r1, text="(等号线填: ====LINE====)").pack(side="left")

        r2 = ttk.Frame(pf); r2.pack(fill="x", padx=8, pady=4)
        ttk.Label(r2, text="窗口tokens:").pack(side="left")
        ttk.Spinbox(r2, from_=3, to=30, textvariable=self.win_var, width=5).pack(side="left", padx=4)
        ttk.Label(r2, text="短语最大tokens:").pack(side="left", padx=(12, 0))
        ttk.Spinbox(r2, from_=2, to=15, textvariable=self.phr_var, width=5).pack(side="left", padx=4)
        ttk.Label(r2, text="spaCy批大小:").pack(side="left", padx=(12, 0))
        ttk.Spinbox(r2, from_=8, to=256, textvariable=self.batch_var, width=5).pack(side="left", padx=4)
        ttk.Label(r2, text="单篇最大字符:").pack(side="left", padx=(12, 0))
        ttk.Spinbox(r2, from_=50000, to=1000000, textvariable=self.maxch_var, width=7).pack(side="left", padx=4)
        self.run_btn = ttk.Button(r2, text="▶ 开始", style="Accent.TButton", command=lambda: self._start(self.run_btn))
        self.run_btn.pack(side="right")

        self._finish(progress_mode="determinate", log_height=14)

    def _w_on_progress(self, msg, frac):
        if hasattr(self, "pbar"):
            self.pbar["value"] = max(0, min(100, int(frac)))

    def _validate(self):
        if not self.in_var.get() or not self.out_var.get() or not self.tgt_var.get():
            messagebox.showerror("错误", "请填写所有必填项。")
            return False
        return True

    def _worker_impl(self):
        try:
            from config import TxtAnalysisConfig
            from modules.txt_modifier_extractor_gui import process_txt, split_targets
            cfg = TxtAnalysisConfig(
                split_mode=self.split_var.get(),
                split_regex=self.split_regex_var.get(),
                window_tokens=self.win_var.get(),
                phrase_max_tokens=self.phr_var.get(),
                nlp_batch_size=self.batch_var.get(),
                max_doc_chars=self.maxch_var.get(),
                use_online_judge=False,
            )
            targets = split_targets(self.tgt_var.get())
            process_txt(
                self.in_var.get(), self.out_var.get(), targets, cfg,
                progress_cb=lambda d, t: self._w_put("progress", "", (d / t) * 100),
                log_cb=lambda m: self._w_put("log", m),
            )
            self._w_put("done", f"完成: {self.out_var.get()}")
        except Exception as e:
            self._w_put("error", str(e))


class TabPOSTranslate(ToolTab):
    def __init__(self, master):
        super().__init__(master)
        pad = self._pad

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.col_var = tk.StringVar(value="Adjective")
        self.trans_var = tk.BooleanVar(value=True)
        self.df = None

        row = 0
        FileRow(self, "输入Excel:", "open", [("Excel", "*.xlsx"), ("CSV", "*.csv"), ("All", "*.*")], self.in_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "导出Excel:", "save", [("Excel", "*.xlsx"), ("CSV", "*.csv")], self.out_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1

        cf = ttk.Frame(self)
        cf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Label(cf, text="词语所在列:", width=18, anchor="e").pack(side="left", padx=(0, 6))
        self.col_combo = ttk.Combobox(cf, textvariable=self.col_var, state="readonly", width=20)
        self.col_combo.pack(side="left", padx=(0, 8))
        ttk.Checkbutton(cf, text="生成中文翻译", variable=self.trans_var).pack(side="left")
        ttk.Button(cf, text="读取列名", style="Ghost.TButton", command=self.load_columns).pack(side="left", padx=12)
        self.run_btn = ttk.Button(cf, text="▶ 开始", style="Accent.TButton", command=lambda: self._start(self.run_btn))
        self.run_btn.pack(side="right")

        pf = ttk.Frame(self)
        pf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Label(pf, text="预览 (前20行):").pack(anchor="w")
        self.preview = tk.Text(pf, height=6, wrap="none")
        self.preview.pack(fill="both", expand=True)

        self._finish(progress_mode="determinate", log_height=6)

    def load_columns(self):
        path = self.in_var.get()
        if not path:
            messagebox.showwarning("提示", "请先选择输入文件。")
            return
        try:
            self.df = pd.read_excel(path) if path.lower().endswith(".xlsx") else pd.read_csv(path, encoding="utf-8-sig")
            cols = list(self.df.columns)
            self.col_combo["values"] = cols
            if "Adjective" in cols:
                self.col_var.set("Adjective")
            elif cols:
                self.col_var.set(cols[0])
            self.preview.delete("1.0", "end")
            self.preview.insert("end", self.df.head(20).to_string(index=False))
            self.log.log(f"已加载: {len(self.df)}行, {len(cols)}列")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _validate(self):
        if not self.in_var.get() or not self.out_var.get() or not self.col_var.get():
            messagebox.showerror("错误", "请填写所有必填项。")
            return False
        if self.df is None:
            self.load_columns()
        return self.df is not None

    def _worker_impl(self):
        try:
            from modules.jiacixing import ensure_nltk_data, guess_pos, Translator
            ensure_nltk_data()
            df = self.df.copy()
            word_col = self.col_var.get()
            out = self.out_var.get()
            words = df[word_col].tolist()
            n = len(words)
            self._w_put("log", f"标注 {n} 词…")

            pos_list = []
            for i, w in enumerate(words, start=1):
                pos_list.append(guess_pos(None if pd.isna(w) else str(w)))
                if i % 20 == 0:
                    self._w_put("progress", "", i / n * 50)

            df["POS"] = pos_list
            zh_list = [""] * n

            if self.trans_var.get():
                self._w_put("log", "并发翻译中…")
                t = Translator(concurrency=5)
                zh_list = t.translate_batch(["" if pd.isna(w) else str(w) for w in words])

            df["中文意思"] = zh_list
            self._w_put("progress", "", 100)

            if out.lower().endswith(".csv"):
                df.to_csv(out, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(out, index=False)

            self._w_put("preview", df.head(20).to_string(index=False))
            self._w_put("done", f"完成: {out}")
        except Exception as e:
            self._w_put("error", str(e))

    def _w_on_preview(self, text):
        self.preview.delete("1.0", "end")
        self.preview.insert("end", text)


class TabResultBrowser(ttk.Frame):
    """Browse adjectives_phrases.xlsx sheets in-app with review annotation support."""

    def __init__(self, master):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._pad = {"padx": 8, "pady": 4}
        self._dfs = {}
        self._review_data = {}
        self._review_mode = False

        # Top bar
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", **self._pad)
        self.file_var = tk.StringVar()
        FileRow(top, "结果文件:", "open", [("Excel", "*.xlsx"), ("All", "*.*")], self.file_var) \
            .pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="加载", style="Accent.TButton", command=self.load_file).pack(side="left", padx=6)
        ttk.Button(top, text="复核模式", style="Ghost.TButton", command=self._toggle_review).pack(side="left", padx=6)
        ttk.Button(top, text="导出复核", style="Ghost.TButton", command=self._export_review).pack(side="left", padx=6)
        ttk.Button(top, text="验证报告", style="Ghost.TButton", command=self._validation_report).pack(side="left", padx=6)
        self.filter_var = tk.StringVar()
        ttk.Label(top, text="筛选:").pack(side="left", padx=(12, 0))
        fe = ttk.Entry(top, textvariable=self.filter_var, width=18, style="Field.TEntry")
        fe.pack(side="left", padx=4)
        fe.bind("<Return>", lambda e: self._apply_filter())
        ttk.Button(top, text="清除", style="Ghost.TButton", command=self._clear_filter).pack(side="left", padx=4)

        # Notebook for sheets
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", **self._pad)

        # Status bar
        self.status = ttk.Label(self, text="请加载 adjectives_phrases.xlsx 或 merged_sources.xlsx", foreground=COLORS["muted"])
        self.status.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))

        self._sheet_trees = {}

    def load_file(self):
        path = self.file_var.get()
        if not path or not Path(path).exists():
            messagebox.showerror("错误", "文件不存在。")
            return
        try:
            xl = pd.ExcelFile(path)
            self._dfs.clear()
            self._review_data.clear()
            self._sheet_trees.clear()
            for tab_id in self.notebook.tabs():
                self.notebook.forget(tab_id)

            review_sheets = {"Adjectives", "Phrases", "SemanticProsodyCandidates", "KWIC", "Collocates", "GroupComparison"}
            for sn in xl.sheet_names:
                if sn == "README":
                    continue
                df = pd.read_excel(path, sheet_name=sn)
                self._dfs[sn] = df
                if sn in review_sheets:
                    self._review_data[sn] = self._init_review_columns(df)
                self._add_sheet_tab(sn, df)

            if self._dfs:
                first = xl.sheet_names[0] if xl.sheet_names[0] != "README" else (xl.sheet_names[1] if len(xl.sheet_names) > 1 else None)
                if first:
                    self.notebook.select(0)
                self.status.config(text=f"已加载: {path}  ({len(self._dfs)} sheets, {sum(len(d) for d in self._dfs.values())} 行)")

            app = self.winfo_toplevel()
            if hasattr(app, "_load_project_status"):
                parent = Path(path).parent
                app._load_project_status(str(parent))
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _init_review_columns(self, df):
        return pd.DataFrame({
            "is_correct": [""] * len(df),
            "error_type": [""] * len(df),
            "notes": [""] * len(df),
        }, index=df.index)

    def _add_sheet_tab(self, name, df):
        frame = ttk.Frame(self.notebook)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        cols = list(df.columns)
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            tree.heading(c, text=c, command=lambda col=c, t=tree: self._sort_tree(t, col, False))
            width = 80 if len(c) < 8 else min(200, max(60, len(str(c)) * 10))
            tree.column(c, width=width, minwidth=40)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self._populate_tree(tree, df)
        tree.bind("<Double-1>", lambda e, sn=name: self._on_row_double_click(sn))
        self._sheet_trees[name] = tree
        self.notebook.add(frame, text=name)

    def _populate_tree(self, tree, df):
        tree.delete(*tree.get_children())
        for i, row in df.iterrows():
            vals = [str(v) if not pd.isna(v) else "" for v in row]
            tree.insert("", "end", iid=str(i), values=vals)

    def _sort_tree(self, tree, col, reverse):
        data = [(tree.set(child, col), child) for child in tree.get_children("")]
        try:
            data.sort(key=lambda x: float(x[0]) if x[0].replace(".", "", 1).replace("-", "", 1).isdigit() else x[0], reverse=reverse)
        except Exception:
            data.sort(key=lambda x: x[0], reverse=reverse)
        for idx, (_, child) in enumerate(data):
            tree.move(child, "", idx)
        tree.heading(col, command=lambda: self._sort_tree(tree, col, not reverse))

    def _on_row_double_click(self, sheet_name):
        tree = self._sheet_trees.get(sheet_name)
        if not tree:
            return
        sel = tree.selection()
        if not sel:
            return
        row_idx = int(sel[0])
        row = self._dfs[sheet_name].iloc[row_idx]

        popup = tk.Toplevel(self, padx=16, pady=12)
        popup.title(f"{sheet_name} — 行 {row_idx}")
        popup.geometry("700x480")
        popup.configure(bg=COLORS["panel"])

        main = ttk.Frame(popup)
        main.pack(fill="both", expand=True)

        txt = tk.Text(main, wrap="word", font=("Microsoft YaHei UI", 10),
                      bg=COLORS["surface"], fg=COLORS["text"], relief="solid", bd=1,
                      highlightthickness=1, highlightbackground=COLORS["border"])
        txt.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(main, orient="vertical", command=txt.yview)
        sb.pack(side="right", fill="y")
        txt.configure(yscrollcommand=sb.set)

        # KWIC sheet: show context prominently
        if sheet_name == "KWIC":
            left = str(row.get("Left_Context", ""))
            node = str(row.get("Node", row.get("Target", "")))
            right = str(row.get("Right_Context", ""))
            src = str(row.get("Source_File", row.get("Source", "")))
            txt.insert("end", f"来源: {src}\n\n", "label")
            txt.insert("end", f"{left} ", "context")
            txt.insert("end", node, "node")
            txt.insert("end", f" {right}", "context")
            txt.tag_configure("node", foreground=COLORS["steel"], font=("Microsoft YaHei UI", 12, "bold"))
            txt.tag_configure("context", font=("Microsoft YaHei UI", 11))
            txt.tag_configure("label", foreground=COLORS["muted"], font=("Microsoft YaHei UI", 9))
        else:
            for col in row.index:
                val = row[col]
                txt.insert("end", f"{col}: ", "label")
                txt.insert("end", f"{val}\n\n", "value")
            txt.tag_configure("label", foreground=COLORS["accent"], font=("Microsoft YaHei UI", 10, "bold"))
            txt.tag_configure("value", font=("Microsoft YaHei UI", 10))

        txt.config(state="disabled")

        # Review panel
        if sheet_name in self._review_data:
            sep = ttk.Separator(popup, orient="horizontal")
            sep.pack(fill="x", pady=(12, 8))

            rf = ttk.Frame(popup)
            rf.pack(fill="x")
            ttk.Label(rf, text="复核标注", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 6))

            r1 = ttk.Frame(rf)
            r1.pack(fill="x", pady=2)
            ttk.Label(r1, text="是否正确:").pack(side="left")
            corr_var = tk.StringVar(value=str(self._review_data[sheet_name].at[row_idx, "is_correct"]))
            corr_combo = ttk.Combobox(r1, textvariable=corr_var, values=["", "1", "0"], width=4, state="readonly")
            corr_combo.pack(side="left", padx=6)

            ttk.Label(r1, text="错误类型:").pack(side="left", padx=(16, 0))
            err_var = tk.StringVar(value=str(self._review_data[sheet_name].at[row_idx, "error_type"]))
            err_combo = ttk.Combobox(r1, textvariable=err_var, width=22, state="readonly",
                                     values=["", "normalization_error", "country_error", "extraction_error",
                                             "polarity_error", "context_error", "other"])
            err_combo.pack(side="left", padx=6)

            r2 = ttk.Frame(rf)
            r2.pack(fill="x", pady=(4, 0))
            ttk.Label(r2, text="备注:").pack(side="left")
            notes_var = tk.StringVar(value=str(self._review_data[sheet_name].at[row_idx, "notes"]))
            ttk.Entry(r2, textvariable=notes_var, style="Field.TEntry").pack(side="left", fill="x", expand=True, padx=6)

            def save_review():
                self._review_data[sheet_name].at[row_idx, "is_correct"] = corr_var.get()
                self._review_data[sheet_name].at[row_idx, "error_type"] = err_var.get()
                self._review_data[sheet_name].at[row_idx, "notes"] = notes_var.get()
                popup.destroy()
                self.status.config(text=f"已保存复核标注: {sheet_name} 行 {row_idx}")

            ttk.Button(rf, text="保存标注", style="Accent.TButton", command=save_review).pack(anchor="e", pady=(8, 0))

    def _toggle_review(self):
        self._review_mode = not self._review_mode
        state = "开" if self._review_mode else "关"
        self.status.config(text=f"复核模式: {state} — 双击任意行打开标注面板")

    def _export_review(self):
        if not self._review_data:
            messagebox.showwarning("提示", "没有复核数据可导出。请先加载包含可复核 sheet 的文件。")
            return
        out = Path(self.file_var.get()).parent / "review_annotations.xlsx"
        out = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="review_annotations.xlsx",
                                           filetypes=[("Excel", "*.xlsx")])
        if not out:
            return
        try:
            sheets = {}
            for sn, rdf in self._review_data.items():
                df = self._dfs[sn].copy()
                for col in ["is_correct", "error_type", "notes"]:
                    df[col] = rdf[col].values
                sheets[sn] = df
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                for sn, df in sheets.items():
                    df.to_excel(writer, index=False, sheet_name=sn[:31])
            self.status.config(text=f"复核导出: {out}")
            messagebox.showinfo("完成", f"已导出: {out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _validation_report(self):
        if not self._review_data:
            messagebox.showwarning("提示", "没有复核数据。请先标注再生成报告。")
            return
        out = Path(self.file_var.get()).parent / "07_reports" / "validation_report.xlsx"
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            rows = []
            for sn, rdf in self._review_data.items():
                reviewed = rdf[rdf["is_correct"].astype(str).str.strip() != ""]
                if reviewed.empty:
                    rows.append({"Sheet": sn, "Reviewed": 0, "Correct": 0, "Accuracy": ""})
                    continue
                correct = pd.to_numeric(reviewed["is_correct"], errors="coerce").fillna(0).astype(int).sum()
                errs = reviewed.loc[pd.to_numeric(reviewed["is_correct"], errors="coerce").fillna(0).astype(int) == 0]
                most_common = ""
                if "error_type" in errs.columns and not errs.empty:
                    counts = errs["error_type"].dropna().astype(str)
                    if not counts.empty and counts.value_counts().size > 0:
                        most_common = counts.value_counts().index[0]
                rows.append({
                    "Sheet": sn, "Reviewed": len(reviewed), "Correct": int(correct),
                    "Accuracy": round(correct / len(reviewed), 4), "Most_Common_Error": most_common,
                })
            summary = pd.DataFrame(rows)
            from shared.research_output import write_excel_with_readme
            write_excel_with_readme(
                str(out), {"ValidationSummary": summary},
                title="Validation report", description="From inline review annotations.",
                fields={"Reviewed": "Rows reviewed", "Correct": "Rows correct", "Accuracy": "Correct/Reviewed"},
            )
            self.status.config(text=f"验证报告: {out}")
            messagebox.showinfo("完成", f"已生成: {out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _apply_filter(self):
        term = self.filter_var.get().strip().lower()
        current = self.notebook.select()
        for sn, tree in self._sheet_trees.items():
            tab_id = [t for t in self.notebook.tabs() if self.notebook.tab(t, "text") == sn]
            if not tab_id or str(tab_id[0]) != str(current):
                continue
            df = self._dfs[sn]
            tree.delete(*tree.get_children())
            if not term:
                self._populate_tree(tree, df)
                return
            mask = pd.Series(False, index=df.index)
            for col in df.columns:
                mask |= df[col].astype(str).str.lower().str.contains(term, na=False)
            filtered = df[mask]
            self._populate_tree(tree, filtered)
            self.status.config(text=f"筛选 '{term}': {len(filtered)}/{len(df)} 行")

    def _clear_filter(self):
        self.filter_var.set("")
        for sn, tree in self._sheet_trees.items():
            self._populate_tree(tree, self._dfs[sn])
        self.status.config(text="筛选已清除")


class TabProjectWorkbench(ToolTab):
    """Project-level research workbench — init, import, analyze, review, report.

    Reuses shared.project_workflow for all logic; GUI only handles
    project selection, parameter input, action dispatch, and status display.
    """

    CORPUS_TYPES = [
        ("generic", "通用语料研究"),
        ("news_lexis", "新闻话语 / LexisNexis"),
        ("policy", "政策文本分析"),
        ("academic", "学术语料分析"),
        ("interview", "访谈与定性语料"),
        ("social_media", "社交媒体话语"),
        ("translation", "翻译语料分析"),
    ]

    OUTPUT_FILES = [
        ("project.json", "项目状态"),
        ("01_corpus/document_registry.xlsx", "文档注册表"),
        ("01_corpus/corpus_manifest.json", "语料清单"),
        ("adjectives_phrases.xlsx", "分析工作簿"),
        ("06_review/modifier_semantic_review.xlsx", "修饰语复核"),
        ("06_review/source_country_review.xlsx", "来源/国别复核"),
        ("07_reports/validation_report.xlsx", "验证报告"),
        ("07_reports/method_summary.md", "方法摘要"),
        ("07_reports/method_limitations.md", "方法局限性"),
        ("07_reports/research_report.md", "研究报告"),
    ]

    def __init__(self, master):
        super().__init__(master)
        self.project_dir = None
        self._pending_action = None

        main = ttk.Frame(self)
        main.grid(row=0, column=0, sticky="nsew", **self._pad)
        self.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.columnconfigure(2, weight=0)

        self._build_left(main)
        self._build_center(main)
        self._build_right(main)

        self._finish(progress_mode="indeterminate", log_height=6)

    # ================================================================
    #  LEFT PANEL — project create/open + status display
    # ================================================================

    def _build_left(self, parent):
        frame = tk.Frame(parent, bg=COLORS["soft"], padx=14, pady=14,
                         highlightthickness=1, highlightbackground=COLORS["border"])
        frame.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        frame.columnconfigure(0, weight=1)

        tk.Label(frame, text="项目面板", bg=COLORS["soft"], fg=COLORS["text"],
                 font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 12))

        # --- New / Open ---
        btn_frame = tk.Frame(frame, bg=COLORS["soft"])
        btn_frame.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        tk.Button(btn_frame, text="+ 新建项目", bg=COLORS["aqua"], fg=COLORS["ink"],
                  font=("Microsoft YaHei UI", 9, "bold"), bd=0, padx=10, pady=4,
                  activebackground=COLORS["mint"], activeforeground=COLORS["ink"],
                  cursor="hand2", command=self._new_project_dialog).pack(side="left", fill="x", expand=True)

        tk.Button(btn_frame, text="📂 打开项目", bg=COLORS["accent_soft"], fg=COLORS["ink"],
                  font=("Microsoft YaHei UI", 9), bd=0, padx=10, pady=4,
                  activebackground=COLORS["aqua"], activeforeground=COLORS["ink"],
                  cursor="hand2", command=self._open_project).pack(side="left", fill="x", expand=True, padx=(4, 0))

        # --- Project path ---
        self._lbl_project_path = tk.Label(frame, text="未打开项目", bg=COLORS["soft"],
                                          fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                                          anchor="w", justify="left", wraplength=220)
        self._lbl_project_path.grid(row=2, column=0, sticky="ew", pady=(8, 12))

        tk.Frame(frame, bg=COLORS["border"], height=1).grid(row=3, column=0, sticky="ew", pady=(0, 12))

        # --- Project info ---
        tk.Label(frame, text="项目信息", bg=COLORS["soft"], fg=COLORS["text"],
                 font=("Microsoft YaHei UI", 9, "bold")).grid(row=4, column=0, sticky="w", pady=(0, 6))

        info_fields = [
            ("corpus_type", "语料类型"),
            ("targets", "目标词"),
            ("documents", "文档数"),
            ("target_hits_total", "目标词命中"),
            ("next_step", "下一步"),
        ]
        self._info_labels = {}
        for i, (key, label) in enumerate(info_fields):
            tk.Label(frame, text=f"{label}:", bg=COLORS["soft"], fg=COLORS["muted"],
                     font=("Microsoft YaHei UI", 8), anchor="w").grid(row=5 + i, column=0, sticky="w", pady=(2, 0))
            lbl = tk.Label(frame, text="--", bg=COLORS["soft"], fg=COLORS["text"],
                           font=("Microsoft YaHei UI", 9), anchor="w", wraplength=220, justify="left")
            lbl.grid(row=5 + i, column=0, sticky="w", pady=(0, 2))
            self._info_labels[key] = lbl

        tk.Frame(frame, bg=COLORS["border"], height=1).grid(row=5 + len(info_fields), column=0, sticky="ew", pady=(8, 12))

        # --- Status lights ---
        tk.Label(frame, text="状态", bg=COLORS["soft"], fg=COLORS["text"],
                 font=("Microsoft YaHei UI", 9, "bold")).grid(row=6 + len(info_fields), column=0, sticky="w", pady=(0, 6))

        status_items = [
            ("has_corpus_manifest", "语料已导入"),
            ("has_analysis", "分析已完成"),
            ("has_review_dir", "复核已生成"),
            ("has_validation_report", "验证报告"),
            ("_has_research_report", "项目报告"),
        ]
        self._status_labels = {}
        for i, (key, label) in enumerate(status_items):
            lbl = tk.Label(frame, text=f"○  {label}", bg=COLORS["soft"], fg=COLORS["muted"],
                           font=("Microsoft YaHei UI", 9), anchor="w")
            lbl.grid(row=7 + len(info_fields) + i, column=0, sticky="w", pady=1)
            self._status_labels[key] = lbl

    # ================================================================
    #  CENTER PANEL — 5 workflow steps
    # ================================================================

    def _build_center(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=1, sticky="nsew", padx=8)
        frame.columnconfigure(0, weight=1)

        # ---- Step 1: Init ----
        self._step1 = ttk.LabelFrame(frame, text="步骤 1 — 初始化项目", padding=(12, 8))
        self._step1.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._step1.columnconfigure(1, weight=1)

        ttk.Label(self._step1, text="项目目录:").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=2)
        self._s1_dir_var = tk.StringVar()
        s1_dir_frame = ttk.Frame(self._step1)
        s1_dir_frame.grid(row=0, column=1, sticky="ew", pady=2)
        s1_dir_frame.columnconfigure(0, weight=1)
        ttk.Entry(s1_dir_frame, textvariable=self._s1_dir_var, style="Field.TEntry").grid(row=0, column=0, sticky="ew")
        ttk.Button(s1_dir_frame, text="浏览…", width=7, style="Ghost.TButton",
                   command=lambda: self._browse_dir(self._s1_dir_var)).grid(row=0, column=1, padx=(4, 0))

        ttk.Label(self._step1, text="名称:").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=2)
        self._s1_name_var = tk.StringVar()
        ttk.Entry(self._step1, textvariable=self._s1_name_var, style="Field.TEntry").grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(self._step1, text="语料类型:").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=2)
        self._s1_type_var = tk.StringVar(value="generic")
        type_combo = ttk.Combobox(self._step1, textvariable=self._s1_type_var,
                                  values=[t[0] for t in self.CORPUS_TYPES], state="readonly", width=22)
        type_combo.grid(row=2, column=1, sticky="w", pady=2)

        ttk.Label(self._step1, text="目标词:").grid(row=3, column=0, sticky="e", padx=(0, 6), pady=2)
        self._s1_targets_var = tk.StringVar()
        ttk.Entry(self._step1, textvariable=self._s1_targets_var, style="Field.TEntry").grid(row=3, column=1, sticky="ew", pady=2)
        ttk.Label(self._step1, text="(分号分隔)", foreground=COLORS["muted"],
                  font=("Microsoft YaHei UI", 8)).grid(row=4, column=1, sticky="w", pady=(0, 4))

        self._s1_status = tk.Label(self._step1, text="", bg=COLORS["panel"], fg=COLORS["muted"],
                                   font=("Microsoft YaHei UI", 8), anchor="w")
        self._s1_status.grid(row=5, column=1, sticky="w", pady=(0, 2))

        s1_btn_frame = ttk.Frame(self._step1)
        s1_btn_frame.grid(row=5, column=1, sticky="e", pady=(0, 2))
        self._s1_btn = ttk.Button(s1_btn_frame, text="初始化项目", style="Accent.TButton",
                                  command=self._do_init)
        self._s1_btn.pack(side="right")

        # ---- Step 2: Import ----
        self._step2 = ttk.LabelFrame(frame, text="步骤 2 — 导入语料", padding=(12, 8))
        self._step2.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self._step2.columnconfigure(1, weight=1)

        ttk.Label(self._step2, text="输入路径:").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=2)
        self._s2_input_var = tk.StringVar()
        s2_input_frame = ttk.Frame(self._step2)
        s2_input_frame.grid(row=0, column=1, sticky="ew", pady=2)
        s2_input_frame.columnconfigure(0, weight=1)
        ttk.Entry(s2_input_frame, textvariable=self._s2_input_var, style="Field.TEntry").grid(row=0, column=0, sticky="ew")
        ttk.Button(s2_input_frame, text="浏览…", width=7, style="Ghost.TButton",
                   command=self._browse_s2_input).grid(row=0, column=1, padx=(4, 0))
        ttk.Label(self._step2, text="(目录、CSV 或 XLSX)", foreground=COLORS["muted"],
                  font=("Microsoft YaHei UI", 8)).grid(row=1, column=1, sticky="w")

        # Table fields
        table_fields_frame = ttk.LabelFrame(self._step2, text="表格列映射 (CSV/XLSX)", padding=(8, 4))
        table_fields_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        table_fields_frame.columnconfigure(1, weight=1)
        table_fields_frame.columnconfigure(3, weight=1)

        ttk.Label(table_fields_frame, text="文本列:").grid(row=0, column=0, sticky="e", padx=(0, 4), pady=1)
        self._s2_text_col = tk.StringVar(value="text")
        ttk.Entry(table_fields_frame, textvariable=self._s2_text_col, style="Field.TEntry", width=12).grid(row=0, column=1, sticky="w", pady=1)

        ttk.Label(table_fields_frame, text="标题列:").grid(row=0, column=2, sticky="e", padx=(12, 4), pady=1)
        self._s2_title_col = tk.StringVar()
        ttk.Entry(table_fields_frame, textvariable=self._s2_title_col, style="Field.TEntry", width=12).grid(row=0, column=3, sticky="w", pady=1)

        ttk.Label(table_fields_frame, text="来源列:").grid(row=1, column=0, sticky="e", padx=(0, 4), pady=1)
        self._s2_source_col = tk.StringVar()
        ttk.Entry(table_fields_frame, textvariable=self._s2_source_col, style="Field.TEntry", width=12).grid(row=1, column=1, sticky="w", pady=1)

        ttk.Label(table_fields_frame, text="日期列:").grid(row=1, column=2, sticky="e", padx=(12, 4), pady=1)
        self._s2_date_col = tk.StringVar()
        ttk.Entry(table_fields_frame, textvariable=self._s2_date_col, style="Field.TEntry", width=12).grid(row=1, column=3, sticky="w", pady=1)

        ttk.Label(table_fields_frame, text="分组列:").grid(row=2, column=0, sticky="e", padx=(0, 4), pady=1)
        self._s2_group_col = tk.StringVar()
        ttk.Entry(table_fields_frame, textvariable=self._s2_group_col, style="Field.TEntry", width=12).grid(row=2, column=1, sticky="w", pady=1)

        # Directory field
        ttk.Label(table_fields_frame, text="默认来源:").grid(row=3, column=0, sticky="e", padx=(0, 4), pady=1)
        self._s2_default_source = tk.StringVar()
        ttk.Entry(table_fields_frame, textvariable=self._s2_default_source, style="Field.TEntry", width=12).grid(row=3, column=1, sticky="w", pady=1)
        ttk.Label(table_fields_frame, text="(文件夹导入时使用)", foreground=COLORS["muted"],
                  font=("Microsoft YaHei UI", 8)).grid(row=3, column=2, columnspan=2, sticky="w", padx=(12, 0), pady=1)

        self._s2_status = tk.Label(self._step2, text="", bg=COLORS["panel"], fg=COLORS["muted"],
                                   font=("Microsoft YaHei UI", 8), anchor="w")
        self._s2_status.grid(row=3, column=1, sticky="w", pady=(4, 0))

        s2_btn_frame = ttk.Frame(self._step2)
        s2_btn_frame.grid(row=3, column=1, sticky="e", pady=(4, 0))
        self._s2_btn = ttk.Button(s2_btn_frame, text="导入语料", style="Accent.TButton",
                                  command=lambda: self._run_step("import"))
        self._s2_btn.pack(side="right")

        # ---- Step 3: Analyze ----
        self._step3 = ttk.LabelFrame(frame, text="步骤 3 — 分析目标词", padding=(12, 8))
        self._step3.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self._step3.columnconfigure(1, weight=1)

        ttk.Label(self._step3, text="目标词:").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=2)
        self._s3_targets_var = tk.StringVar()
        ttk.Entry(self._step3, textvariable=self._s3_targets_var, style="Field.TEntry").grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(self._step3, text="(从项目自动填充)", foreground=COLORS["muted"],
                  font=("Microsoft YaHei UI", 8)).grid(row=1, column=1, sticky="w")

        self._s3_pos_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self._step3, text="词性标注 + 中文翻译 (较慢)", variable=self._s3_pos_var).grid(row=2, column=1, sticky="w", pady=(2, 0))

        self._s3_mi_var = tk.DoubleVar(value=3.0)
        mi_frame = ttk.Frame(self._step3)
        mi_frame.grid(row=3, column=1, sticky="w", pady=(0, 2))
        ttk.Label(mi_frame, text="MI阈值:").pack(side="left")
        ttk.Spinbox(mi_frame, from_=0.0, to=10.0, increment=0.5,
                    textvariable=self._s3_mi_var, width=6).pack(side="left", padx=6)
        ttk.Label(mi_frame, text="(≥3.0 为显著搭配，语料库语言学标准)", foreground=COLORS["muted"],
                  font=("Microsoft YaHei UI", 8)).pack(side="left")

        self._s3_status = tk.Label(self._step3, text="", bg=COLORS["panel"], fg=COLORS["muted"],
                                   font=("Microsoft YaHei UI", 8), anchor="w")
        self._s3_status.grid(row=4, column=1, sticky="w")

        s3_btn_frame = ttk.Frame(self._step3)
        s3_btn_frame.grid(row=4, column=1, sticky="e")
        self._s3_btn = ttk.Button(s3_btn_frame, text="分析目标词", style="Accent.TButton",
                                  command=lambda: self._run_step("analyze"))
        self._s3_btn.pack(side="right")

        # ---- Step 4: Review ----
        self._step4 = ttk.LabelFrame(frame, text="步骤 4 — 生成复核", padding=(12, 8))
        self._step4.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        self._step4.columnconfigure(1, weight=1)

        ttk.Label(self._step4, text="抽样数量:").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=2)
        self._s4_sample_var = tk.IntVar(value=50)
        ttk.Spinbox(self._step4, from_=10, to=500, textvariable=self._s4_sample_var, width=8).grid(row=0, column=1, sticky="w")

        self._s4_dual_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self._step4, text="双编码模式 (生成 Coder A/B 独立复核文件)", variable=self._s4_dual_var).grid(row=0, column=1, sticky="w", padx=(80, 0))

        self._s4_status = tk.Label(self._step4, text="", bg=COLORS["panel"], fg=COLORS["muted"],
                                   font=("Microsoft YaHei UI", 8), anchor="w")
        self._s4_status.grid(row=1, column=1, sticky="w")

        s4_btn_frame = ttk.Frame(self._step4)
        s4_btn_frame.grid(row=1, column=1, sticky="e")
        self._s4_btn = ttk.Button(s4_btn_frame, text="生成复核", style="Accent.TButton",
                                  command=lambda: self._run_step("review"))
        self._s4_btn.pack(side="right")

        # ---- Step 5: Report ----
        self._step5 = ttk.LabelFrame(frame, text="步骤 5 — 生成报告", padding=(12, 8))
        self._step5.grid(row=4, column=0, sticky="ew")
        self._step5.columnconfigure(1, weight=1)

        ttk.Label(self._step5, text="在 07_reports/ 中生成 research_report.md",
                  foreground=COLORS["muted"], font=("Microsoft YaHei UI", 8)).grid(row=0, column=1, sticky="w", pady=(0, 4))

        self._s5_status = tk.Label(self._step5, text="", bg=COLORS["panel"], fg=COLORS["muted"],
                                   font=("Microsoft YaHei UI", 8), anchor="w")
        self._s5_status.grid(row=1, column=1, sticky="w")

        s5_btn_frame = ttk.Frame(self._step5)
        s5_btn_frame.grid(row=1, column=1, sticky="e")
        self._s5_btn = ttk.Button(s5_btn_frame, text="生成报告", style="Accent.TButton",
                                  command=lambda: self._run_step("report"))
        self._s5_btn.pack(side="right")

    # ================================================================
    #  RIGHT PANEL — output files
    # ================================================================

    def _build_right(self, parent):
        frame = tk.Frame(parent, bg=COLORS["soft"], padx=14, pady=14,
                         highlightthickness=1, highlightbackground=COLORS["border"])
        frame.grid(row=0, column=2, sticky="ns", padx=(8, 0))
        frame.columnconfigure(0, weight=1)

        tk.Label(frame, text="输出文件", bg=COLORS["soft"], fg=COLORS["text"],
                 font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 12))

        self._output_rows = []
        for i, (rel_path, description) in enumerate(self.OUTPUT_FILES):
            row_frame = tk.Frame(frame, bg=COLORS["soft"])
            row_frame.grid(row=1 + i, column=0, sticky="ew", pady=1)
            row_frame.columnconfigure(0, weight=1)

            lbl = tk.Label(row_frame, text=f"{description}", bg=COLORS["soft"], fg=COLORS["muted"],
                           font=("Microsoft YaHei UI", 8), anchor="w")
            lbl.grid(row=0, column=0, sticky="w")

            btn = tk.Button(row_frame, text="打开", bg=COLORS["accent_soft"], fg=COLORS["ink"],
                            font=("Microsoft YaHei UI", 8), bd=0, padx=6, pady=1,
                            activebackground=COLORS["aqua"], activeforeground=COLORS["ink"],
                            cursor="hand2", state="disabled",
                            command=lambda p=rel_path: self._open_output_file(p))
            btn.grid(row=0, column=1, sticky="e", padx=(8, 0))

            self._output_rows.append((btn, lbl, rel_path))

        tk.Frame(frame, bg=COLORS["border"], height=1).grid(
            row=1 + len(self.OUTPUT_FILES), column=0, sticky="ew", pady=(12, 12))

        tk.Button(frame, text="打开项目文件夹", bg=COLORS["accent_soft"], fg=COLORS["ink"],
                  font=("Microsoft YaHei UI", 9), bd=0, padx=10, pady=4,
                  activebackground=COLORS["aqua"], activeforeground=COLORS["ink"],
                  cursor="hand2", command=self._open_project_folder).grid(
            row=2 + len(self.OUTPUT_FILES), column=0, sticky="ew")

    # ================================================================
    #  ACTIONS — new / open / init / step dispatch
    # ================================================================

    @staticmethod
    def _browse_dir(var):
        path = filedialog.askdirectory()
        if path:
            var.set(path)

    def _browse_s2_input(self):
        path = filedialog.askopenfilename(
            filetypes=[("All supported", "*.csv *.xlsx *.xls *.txt"),
                       ("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"),
                       ("All files", "*.*")])
        if not path:
            path = filedialog.askdirectory()
        if path:
            self._s2_input_var.set(path)

    def _new_project_dialog(self):
        dialog = tk.Toplevel(self, padx=20, pady=16)
        dialog.title("新建项目")
        dialog.geometry("520x340")
        dialog.configure(bg=COLORS["panel"])
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="创建新研究项目", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", pady=(0, 16))

        # Project directory
        tk.Label(dialog, text="项目目录", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        dir_frame = tk.Frame(dialog, bg=COLORS["panel"])
        dir_frame.pack(fill="x", pady=(2, 8))
        dir_frame.columnconfigure(0, weight=1)
        dir_var = tk.StringVar()
        ttk.Entry(dir_frame, textvariable=dir_var, style="Field.TEntry").grid(row=0, column=0, sticky="ew")
        ttk.Button(dir_frame, text="浏览…", style="Ghost.TButton",
                   command=lambda: self._browse_dir(dir_var)).grid(row=0, column=1, padx=(6, 0))

        # Project name
        tk.Label(dialog, text="项目名称", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        name_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=name_var, style="Field.TEntry").pack(fill="x", pady=(2, 8))

        # Corpus type
        tk.Label(dialog, text="语料类型", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        type_var = tk.StringVar(value="generic")
        combo = ttk.Combobox(dialog, textvariable=type_var,
                             values=[t[0] for t in self.CORPUS_TYPES], state="readonly")
        combo.pack(fill="x", pady=(2, 8))

        # Targets
        tk.Label(dialog, text="目标词 (分号分隔)", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        targets_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=targets_var, style="Field.TEntry").pack(fill="x", pady=(2, 12))

        def on_create():
            d = dir_var.get().strip()
            if not d:
                messagebox.showerror("错误", "请选择项目目录。", parent=dialog)
                return
            try:
                from shared.project_workflow import init_project
                init_project(d, corpus_type=type_var.get(), name=name_var.get().strip() or Path(d).name,
                             targets=targets_var.get().strip())
                dialog.destroy()
                self._load_project(d)
                self._s1_dir_var.set(d)
                self._s1_name_var.set(name_var.get().strip() or Path(d).name)
                self._s1_type_var.set(type_var.get())
                self._s1_targets_var.set(targets_var.get().strip())
                self.log.log(f"项目已初始化: {d}")
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=dialog)

        ttk.Button(dialog, text="创建项目", style="Accent.TButton", command=on_create).pack(side="right")

    def _open_project(self):
        path = filedialog.askdirectory(title="选择项目目录")
        if not path:
            return
        if not Path(path, "project.json").exists():
            messagebox.showerror("错误", f"未找到 project.json:\n{path}\n\n请先初始化项目。")
            return
        self._load_project(path)
        self.log.log(f"项目已打开: {path}")

    def _load_project(self, project_dir):
        from shared.project_workflow import project_status
        self.project_dir = project_dir
        try:
            self._status = project_status(project_dir)
        except Exception as e:
            self._status = {}
            self.log.log(f"警告: 无法加载状态 — {e}")
        self._refresh_ui()

    def _do_init(self):
        d = self._s1_dir_var.get().strip()
        if not d:
            messagebox.showerror("错误", "请选择项目目录。")
            return
        try:
            from shared.project_workflow import init_project
            init_project(d, corpus_type=self._s1_type_var.get(),
                         name=self._s1_name_var.get().strip() or Path(d).name,
                         targets=self._s1_targets_var.get().strip())
            self._load_project(d)
            self.log.log(f"项目已初始化: {d}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _run_step(self, action_name):
        if self.running:
            return
        if not self.project_dir:
            messagebox.showerror("错误", "请先创建或打开项目。")
            return
        self._pending_action = action_name
        # Validate before starting
        if action_name == "import":
            if not self._s2_input_var.get().strip():
                messagebox.showerror("错误", "请选择输入路径。")
                return
        self._start()

    def _validate(self):
        return True

    def _worker_impl(self):
        action = self._pending_action
        pdir = self.project_dir
        try:
            from shared.project_workflow import (
                project_import, project_analyze, project_review, project_report,
            )
            if action == "import":
                self._w_put("log", "正在导入语料…")
                project_import(
                    pdir,
                    input_path=self._s2_input_var.get().strip(),
                    default_source=self._s2_default_source.get().strip(),
                    text_col=self._s2_text_col.get().strip() or "text",
                    title_col=self._s2_title_col.get().strip(),
                    source_col=self._s2_source_col.get().strip(),
                    date_col=self._s2_date_col.get().strip(),
                    group_col=self._s2_group_col.get().strip(),
                )
                self._w_put("done", "语料导入完成。")
            elif action == "analyze":
                self._w_put("log", "正在分析目标词 (可能需要一些时间)…")
                project_analyze(
                    pdir,
                    targets=self._s3_targets_var.get().strip() or None,
                    pos_translate=self._s3_pos_var.get(),
                    mi_threshold=self._s3_mi_var.get(),
                )
                self._w_put("done", "分析完成。")
            elif action == "review":
                self._w_put("log", "正在生成复核文件…")
                project_review(pdir, sample_size=self._s4_sample_var.get(),
                               dual_coder=self._s4_dual_var.get())
                self._w_put("done", "复核文件已生成。")
            elif action == "report":
                self._w_put("log", "正在生成研究报告…")
                project_report(pdir)
                self._w_put("done", "研究报告已生成。")
            else:
                self._w_put("error", f"未知操作: {action}")
                return
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._w_put("error", str(e))

    # ================================================================
    #  UI REFRESH
    # ================================================================

    def _refresh_ui(self):
        s = self._status
        has_project = bool(self.project_dir and s)

        # --- Left panel ---
        if has_project:
            short_path = self.project_dir
            if len(short_path) > 50:
                short_path = "…" + short_path[-47:]
            self._lbl_project_path.config(text=short_path, fg=COLORS["text"])
        else:
            self._lbl_project_path.config(text="未打开项目", fg=COLORS["muted"])

        info_map = {
            "corpus_type": s.get("corpus_type", "--"),
            "targets": s.get("targets", "--") or "--",
            "documents": str(s.get("documents", 0)),
            "target_hits_total": str(s.get("target_hits_total", 0)),
            "next_step": s.get("next_step", "--"),
        }
        for key, lbl in self._info_labels.items():
            val = info_map.get(key, "--")
            if key == "targets" and len(str(val)) > 35:
                val = str(val)[:33] + "…"
            lbl.config(text=str(val))

        # Status lights
        report_path = Path(self.project_dir or "") / "07_reports" / "research_report.md"
        status_checks = {
            "has_corpus_manifest": bool(s.get("has_corpus_manifest")),
            "has_analysis": bool(s.get("has_analysis")),
            "has_review_dir": bool(s.get("has_review_dir")),
            "has_validation_report": bool(s.get("has_validation_report")),
            "_has_research_report": report_path.exists(),
        }
        for key, lbl in self._status_labels.items():
            ok = status_checks.get(key, False)
            lbl.config(text=f"{'●' if ok else '○'}  {lbl.cget('text')[3:]}",
                       fg=COLORS["steel"] if ok else COLORS["muted"])

        # --- Center panel: step statuses and button states ---
        next_step = s.get("next_step", "")
        step_states = {
            "import": ("s1", self._s1_btn, self._s1_status),
            "analyze": ("s2", self._s2_btn, self._s2_status),
            "review": ("s3", self._s3_btn, self._s3_status),
            "inspect_results": ("s4", self._s4_btn, self._s4_status),
        }

        # Reset all
        for btn_tag, btn, status_lbl in [
            ("s1", self._s1_btn, self._s1_status),
            ("s2", self._s2_btn, self._s2_status),
            ("s3", self._s3_btn, self._s3_status),
            ("s4", self._s4_btn, self._s4_status),
        ]:
            status_lbl.config(text="")
            btn.config(state="normal" if has_project or btn_tag == "s1" else "disabled")

        self._s5_btn.config(state="normal" if has_project else "disabled")
        self._s5_status.config(text="")

        if has_project:
            # Step 1
            self._s1_status.config(text="✓ 已初始化", foreground=COLORS["steel"])

            # Mark completed steps and highlight next
            if s.get("has_corpus_manifest"):
                self._s2_status.config(text="✓ 已完成", foreground=COLORS["steel"])
            if s.get("has_analysis"):
                self._s3_status.config(text="✓ 已完成", foreground=COLORS["steel"])
            if s.get("has_review_dir"):
                self._s4_status.config(text="✓ 已完成", foreground=COLORS["steel"])
            if report_path.exists():
                self._s5_status.config(text="✓ 已完成", foreground=COLORS["steel"])

            # Highlight next step
            highlight_map = {
                "import": self._s2_status,
                "analyze": self._s3_status,
                "review": self._s4_status,
                "inspect_results": self._s5_status,
            }
            if next_step in highlight_map:
                lbl = highlight_map[next_step]
                current_text = lbl.cget("text")
                if not current_text.startswith("✓"):
                    lbl.config(text="→ 下一步", foreground=COLORS["aqua"])

            # Auto-fill targets from project
            targets = s.get("targets", "")
            if targets and not self._s3_targets_var.get():
                self._s3_targets_var.set(targets)

        else:
            self._s1_status.config(text="")

        # --- Right panel: output files ---
        for btn, lbl, rel_path in self._output_rows:
            full = Path(self.project_dir or ".") / rel_path
            if full.exists():
                btn.config(state="normal", bg=COLORS["aqua"])
                lbl.config(fg=COLORS["text"])
            else:
                btn.config(state="disabled", bg=COLORS["accent_soft"])
                lbl.config(fg=COLORS["muted"])

        # --- Top status bar ---
        app = self.winfo_toplevel()
        if has_project and hasattr(app, "_update_status_bar"):
            app._update_status_bar(
                project_dir=s.get("name", self.project_dir) or self.project_dir,
                corpus_count=s.get("documents", 0),
                targets=s.get("targets", ""),
                last_run=s.get("latest", {}).get("updated_at", "")[:16] if s.get("latest", {}).get("updated_at") else "",
            )

    # ================================================================
    #  UTILITY
    # ================================================================

    def _open_output_file(self, rel_path):
        full = Path(self.project_dir) / rel_path
        if not full.exists():
            messagebox.showwarning("未找到", f"文件不存在:\n{full}")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(str(full))
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(full)])
            else:
                subprocess.run(["xdg-open", str(full)])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件:\n{e}")

    def _open_project_folder(self):
        if not self.project_dir:
            messagebox.showwarning("提示", "未打开任何项目。")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(str(self.project_dir))
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(self.project_dir)])
            else:
                subprocess.run(["xdg-open", str(self.project_dir)])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹:\n{e}")

    # Intercept _w_on_done to auto-refresh
    def _w_on_done(self, msg):
        super()._w_on_done(msg)
        if self.project_dir:
            self._load_project(self.project_dir)


TOOL_DEFINITIONS = [
    {
        "key": "project_workbench",
        "title": "项目工作台",
        "subtitle": "项目级研究流程: 初始化、导入、分析、复核、报告",
        "params": ["project.json", "Corpus type", "Targets", "Sample size"],
        "outputs": ["project.json", "adjectives_phrases.xlsx", "review artifacts", "research_report.md"],
        "group": "研究流程",
    },
    {
        "key": "pipeline",
        "title": "全流程运行",
        "subtitle": "从 LexisNexis DOCX 到复核材料和方法报告",
        "params": ["Lexis DOCX", "输出目录", "检索目标", "运行步骤", "国别推断"],
        "outputs": ["corpus/*.txt", "source_counts.xlsx", "adjectives_phrases.xlsx", "06_review/", "07_reports/"],
        "group": "研究流程",
    },
    {
        "key": "merge",
        "title": "机构合并+国别",
        "subtitle": "合并来源机构并补充国家/地区识别",
        "params": ["输入表格", "Overrides", "模糊阈值", "联网推断", "饼图 TopN"],
        "outputs": ["merged_sources.xlsx", "source_country_review.xlsx", "pie chart"],
        "group": "语料分析",
    },
    {
        "key": "adjectives",
        "title": "修饰语分析",
        "subtitle": "提取目标词附近的形容词、短语和语义韵候选",
        "params": ["TXT 语料", "检索目标", "分段方式", "窗口 tokens", "短语长度"],
        "outputs": ["KWIC", "Adjectives", "Phrases", "Collocates", "SemanticProsodyCandidates"],
        "group": "语料分析",
    },
    {
        "key": "pos",
        "title": "词性+翻译",
        "subtitle": "为候选词表补充 POS 和中文释义",
        "params": ["输入 Excel", "词语所在列", "是否翻译", "导出文件"],
        "outputs": ["POS", "中文意思", "增强后的候选词表"],
        "group": "语料分析",
    },
    {
        "key": "kwic",
        "title": "KWIC 分析",
        "subtitle": "将 KWIC 文本整理为可复核的 Excel 表",
        "params": ["KWIC 文件", "导出 Excel"],
        "outputs": ["KWIC rows", "形容词候选"],
        "group": "辅助工具",
    },
    {
        "key": "column_merge",
        "title": "自选列合并",
        "subtitle": "按指定键列分组，并对数值列求和",
        "params": ["输入表格", "分组键列", "求和列", "导出文件"],
        "outputs": ["合并后表格", "行数变化日志"],
        "group": "辅助工具",
    },
    {
        "key": "json_excel",
        "title": "JSON 转 Excel",
        "subtitle": "从报告 JSON 提取来源统计表",
        "params": ["报告 JSON", "导出 Excel/CSV"],
        "outputs": ["Source", "Count"],
        "group": "辅助工具",
    },
    {
        "key": "results",
        "title": "结果浏览与复核",
        "subtitle": "加载结果表, 按 sheet 浏览、筛选、标注复核",
        "params": ["adjectives_phrases.xlsx", "merged_sources.xlsx"],
        "outputs": ["Treeview 浏览", "复核标注", "验证报告"],
        "group": "结果与复核",
    },
]


class ContextPanel(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=COLORS["soft"], padx=18, pady=18)
        self.columnconfigure(0, weight=1)

        tk.Label(
            self,
            text="当前模块",
            bg=COLORS["soft"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self.title_label = tk.Label(
            self,
            bg=COLORS["soft"],
            fg=COLORS["text"],
            font=("Microsoft YaHei UI", 14, "bold"),
            wraplength=245,
            justify="left",
        )
        self.title_label.grid(row=1, column=0, sticky="ew", pady=(8, 2))

        self.subtitle_label = tk.Label(
            self,
            bg=COLORS["soft"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
            wraplength=245,
            justify="left",
        )
        self.subtitle_label.grid(row=2, column=0, sticky="ew", pady=(0, 18))

        self.params_frame = self._section("关键参数", 3)
        self.outputs_frame = self._section("结果输出", 5)
        self.rowconfigure(6, weight=1)

    def _section(self, title, row):
        tk.Label(
            self,
            text=title,
            bg=COLORS["soft"],
            fg=COLORS["text"],
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=(0, 8))
        frame = tk.Frame(self, bg=COLORS["panel"], highlightthickness=1, highlightbackground=COLORS["border"])
        frame.grid(row=row + 1, column=0, sticky="ew", pady=(0, 18))
        frame.columnconfigure(0, weight=1)
        return frame

    def _fill_items(self, frame, items):
        for child in frame.winfo_children():
            child.destroy()
        for i, item in enumerate(items):
            tk.Label(
                frame,
                text=f"• {item}",
                bg=COLORS["panel"],
                fg=COLORS["text"],
                font=("Microsoft YaHei UI", 9),
                anchor="w",
                justify="left",
                padx=12,
                pady=6,
                wraplength=220,
            ).grid(row=i, column=0, sticky="ew")

    def show_tool(self, tool):
        self.title_label.config(text=tool["title"])
        self.subtitle_label.config(text=tool["subtitle"])
        self._fill_items(self.params_frame, tool["params"])
        self._fill_items(self.outputs_frame, tool["outputs"])


class IntegratedApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("新闻文本分析集成平台")
        set_window_icon(self)
        self.geometry("1240x760")
        self.minsize(1080, 640)
        self._setup_styles()
        self._build_layout()

    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(bg=COLORS["bg"])
        style.configure(".", font=("Microsoft YaHei UI", 9))
        style.configure("TFrame", background=COLORS["panel"])
        style.configure("App.TFrame", background=COLORS["bg"])
        style.configure("Workspace.TFrame", background=COLORS["panel"])
        style.configure("Header.TFrame", background=COLORS["bg"])
        style.configure("TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"])
        style.configure("AppTitle.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 17, "bold"))
        style.configure("Section.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("ContextTitle.TLabel", background=COLORS["soft"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold"))
        style.configure(
            "TButton",
            padding=(10, 5),
            foreground=COLORS["text"],
            background=COLORS["accent_soft"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["surface"],
            darkcolor=COLORS["border"],
            relief="solid",
        )
        style.map(
            "TButton",
            background=[("disabled", "#D6E8EC"), ("active", COLORS["aqua"]), ("pressed", COLORS["steel"])],
            bordercolor=[("focus", COLORS["aqua"]), ("active", COLORS["aqua"])],
            foreground=[("disabled", COLORS["muted"]), ("active", COLORS["ink"])],
        )
        style.configure(
            "Ghost.TButton",
            padding=(10, 5),
            foreground=COLORS["ink"],
            background=COLORS["surface"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["surface"],
            darkcolor=COLORS["border"],
            relief="solid",
        )
        style.map(
            "Ghost.TButton",
            background=[("disabled", "#E7F2F4"), ("active", COLORS["accent_soft"]), ("pressed", COLORS["aqua"])],
            bordercolor=[("focus", COLORS["aqua"]), ("active", COLORS["aqua"])],
            foreground=[("active", COLORS["ink"])],
        )
        style.configure(
            "Accent.TButton",
            padding=(12, 6),
            foreground=COLORS["ink"],
            background=COLORS["aqua"],
            bordercolor=COLORS["aqua"],
            lightcolor=COLORS["mint"],
            darkcolor=COLORS["steel"],
            relief="solid",
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", "#BBD9DF"), ("active", COLORS["mint"]), ("pressed", COLORS["steel"])],
            foreground=[("disabled", COLORS["muted"]), ("pressed", "#ffffff"), ("active", COLORS["ink"])],
        )
        style.configure(
            "Field.TEntry",
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            insertcolor=COLORS["accent"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["surface"],
            darkcolor=COLORS["border"],
            relief="solid",
            padding=(5, 3),
        )
        style.map(
            "Field.TEntry",
            fieldbackground=[("disabled", "#E7F2F4"), ("focus", "#ffffff")],
            bordercolor=[("focus", COLORS["aqua"]), ("active", COLORS["aqua"])],
        )
        style.configure(
            "TEntry",
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            insertcolor=COLORS["accent"],
            bordercolor=COLORS["border"],
            padding=(5, 3),
        )
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["surface"],
            background=COLORS["accent_soft"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["ink"],
            bordercolor=COLORS["border"],
            padding=(5, 3),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["surface"]), ("focus", "#ffffff")],
            bordercolor=[("focus", COLORS["aqua"]), ("active", COLORS["aqua"])],
        )
        style.configure(
            "TSpinbox",
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["ink"],
            bordercolor=COLORS["border"],
            padding=(4, 2),
        )
        style.configure(
            "TScale",
            background=COLORS["panel"],
            troughcolor=COLORS["accent_soft"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["mint"],
            darkcolor=COLORS["steel"],
        )
        style.configure(
            "TCheckbutton",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            indicatorbackground=COLORS["surface"],
            indicatorforeground=COLORS["ink"],
            indicatorcolor=COLORS["aqua"],
            focuscolor=COLORS["aqua"],
        )
        style.map(
            "TCheckbutton",
            background=[("active", COLORS["panel"])],
            foreground=[("active", COLORS["ink"])],
            indicatorbackground=[("selected", COLORS["aqua"]), ("active", COLORS["accent_soft"])],
            indicatorcolor=[("selected", COLORS["aqua"])],
        )
        style.configure("TRadiobutton", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("TLabelframe", background=COLORS["panel"], bordercolor=COLORS["border"], relief="solid")
        style.configure("TLabelframe.Label", background=COLORS["panel"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"], foreground=COLORS["text"])
        style.configure("Treeview.Heading", background=COLORS["accent_soft"], foreground=COLORS["ink"], font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", COLORS["aqua"])], foreground=[("selected", COLORS["ink"])])
        style.configure("TNotebook", background=COLORS["panel"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 6), foreground=COLORS["muted"])
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["accent_soft"]), ("active", COLORS["surface"])],
            foreground=[("selected", COLORS["ink"]), ("active", COLORS["text"])],
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=COLORS["accent_soft"],
            background=COLORS["progress"],
            bordercolor=COLORS["accent_soft"],
            lightcolor=COLORS["mint"],
            darkcolor=COLORS["aqua"],
        )

    def _build_layout(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, style="Header.TFrame", padding=(22, 16, 22, 10))
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="新闻文本分析集成平台", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="语料导入、分析、复核与报告生成", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.status_frame = tk.Frame(header, bg=COLORS["soft"], padx=14, pady=8, highlightthickness=1, highlightbackground=COLORS["border"])
        self.status_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.status_labels = {}
        for i, key in enumerate(["project", "corpus", "targets", "last_run"]):
            lbl = tk.Label(
                self.status_frame,
                text="",
                bg=COLORS["soft"],
                fg=COLORS["muted"],
                font=("Microsoft YaHei UI", 8),
                padx=12,
            )
            lbl.pack(side="left")
            self.status_labels[key] = lbl
        self._update_status_bar()

        nav = tk.Frame(self, bg=COLORS["nav"], padx=12, pady=16)
        nav.grid(row=1, column=0, sticky="ns")
        self.nav_buttons = {}

        group_order = ["研究流程", "语料分析", "结果与复核", "辅助工具"]
        for g_idx, group_name in enumerate(group_order):
            group_tools = [t for t in TOOL_DEFINITIONS if t.get("group") == group_name]
            if not group_tools:
                continue
            if g_idx > 0:
                tk.Frame(nav, bg=COLORS["nav"], height=8).pack(fill="x")
            tk.Label(
                nav,
                text=group_name,
                bg=COLORS["nav"],
                fg=COLORS["muted"],
                font=("Microsoft YaHei UI", 8, "bold"),
            ).pack(anchor="w", pady=(0, 6))
            for tool in group_tools:
                btn = tk.Button(
                    nav,
                    text=f"  {tool['title']}",
                    anchor="w",
                    width=18,
                    bd=0,
                    padx=12,
                    pady=8,
                    cursor="hand2",
                    bg=COLORS["nav"],
                    fg=COLORS["nav_text"],
                    activebackground=COLORS["nav_hover"],
                    activeforeground=COLORS["nav_active_text"],
                    font=("Microsoft YaHei UI", 9),
                    command=lambda key=tool["key"]: self._show_tool(key),
                )
                btn.pack(fill="x", pady=1)
                self.nav_buttons[tool["key"]] = btn

        self.workspace = ttk.Frame(self, style="Workspace.TFrame", padding=(20, 16, 18, 16))
        self.workspace.grid(row=1, column=1, sticky="nsew")
        self.workspace.columnconfigure(0, weight=1)
        self.workspace.rowconfigure(0, weight=1)

        self.context_panel = ContextPanel(self)
        self.context_panel.grid(row=1, column=2, sticky="nsew")
        self.columnconfigure(2, minsize=260)

        self.pages = {
            "project_workbench": TabProjectWorkbench(self.workspace),
            "pipeline": TabPipeline(self.workspace),
            "merge": TabMerge(self.workspace),
            "adjectives": TabAdjectives(self.workspace),
            "pos": TabPOSTranslate(self.workspace),
            "kwic": TabKWIC(self.workspace),
            "column_merge": TabColumnMerge(self.workspace),
            "json_excel": TabJSONtoExcel(self.workspace),
            "results": TabResultBrowser(self.workspace),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self.current_tool = None
        self._show_tool(TOOL_DEFINITIONS[0]["key"])
        self._theme_tk_widgets(self)

    def _theme_tk_widgets(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Text):
                child.configure(
                    bg=COLORS["surface"],
                    fg=COLORS["text"],
                    relief="solid",
                    bd=1,
                    highlightthickness=1,
                    highlightbackground=COLORS["border"],
                    insertbackground=COLORS["accent"],
                    font=("Consolas", 9),
                )
            elif isinstance(child, tk.Listbox):
                child.configure(
                    bg=COLORS["panel"],
                    fg=COLORS["text"],
                    selectbackground=COLORS["accent"],
                    selectforeground="#ffffff",
                    relief="solid",
                    bd=1,
                    highlightthickness=1,
                    highlightbackground=COLORS["border"],
                    font=("Microsoft YaHei UI", 9),
                )
            self._theme_tk_widgets(child)

    def _show_tool(self, key):
        if key == self.current_tool:
            return
        tool = next(item for item in TOOL_DEFINITIONS if item["key"] == key)
        self.pages[key].tkraise()
        self.context_panel.show_tool(tool)
        for tool_key, button in self.nav_buttons.items():
            active = tool_key == key
            button.configure(
                bg=COLORS["nav_active"] if active else COLORS["nav"],
                fg=COLORS["nav_active_text"] if active else COLORS["nav_text"],
                font=("Microsoft YaHei UI", 9, "bold" if active else "normal"),
            )
        self.current_tool = key

    def _update_status_bar(self, project_dir="", corpus_count=0, targets="", last_run=""):
        self.status_labels["project"].configure(
            text=f"项目: {project_dir or '未设置'}",
            fg=COLORS["text"] if project_dir else COLORS["muted"],
        )
        self.status_labels["corpus"].configure(
            text=f"语料: {f'{corpus_count} 篇' if corpus_count else '--'}",
            fg=COLORS["text"] if corpus_count else COLORS["muted"],
        )
        self.status_labels["targets"].configure(
            text=f"目标词: {targets or '--'}",
            fg=COLORS["text"] if targets else COLORS["muted"],
        )
        self.status_labels["last_run"].configure(
            text=f"上次运行: {last_run or '--'}",
            fg=COLORS["text"] if last_run else COLORS["muted"],
        )

    def _load_project_status(self, output_dir=""):
        if not output_dir:
            self._update_status_bar()
            return
        config_path = Path(output_dir) / "run_config.json"
        if not config_path.exists():
            self._update_status_bar(project_dir=output_dir)
            return
        try:
            import json as _json
            cfg = _json.loads(config_path.read_text(encoding="utf-8"))
            s1 = cfg.get("state", {}).get("s1", {})
            self._update_status_bar(
                project_dir=cfg.get("output", output_dir),
                corpus_count=s1.get("count", 0),
                targets=cfg.get("targets", ""),
                last_run=cfg.get("created_at", "")[:16] if cfg.get("created_at") else "",
            )
        except Exception:
            self._update_status_bar(project_dir=output_dir)


def main():
    IntegratedApp().mainloop()


if __name__ == "__main__":
    main()
