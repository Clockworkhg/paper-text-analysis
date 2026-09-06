# -*- coding: utf-8 -*-
"""Pipeline and analysis tool tabs for the integrated desktop app."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd
import tkinter as tk
from tkinter import messagebox, ttk

from modules.gui.support import FileRow, ToolTab

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

        gf = ttk.Frame(self)
        gf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Label(gf, text="分组方式:", width=18, anchor="e").pack(side="left", padx=(0, 6))
        self.group_var = tk.StringVar(value="source")
        ttk.Combobox(gf, textvariable=self.group_var, state="readonly", width=22,
                     values=("source", "institution", "country", "custom")).pack(side="left")
        ttk.Label(gf, text="(对比表分组: 原始表头/媒体机构/国别/自定义)").pack(side="left", padx=(6, 0))

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
                    group_by=self.group_var.get(),
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

