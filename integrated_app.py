# -*- coding: utf-8 -*-
"""
新闻文本分析集成软件
统一主界面，分页切换各工具模块：
  流水线 / 机构合并+国别 / 修饰形容词分析 / 词性+翻译 / KWIC分析 / 自选合并 / JSON转Excel
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict


from modules.gui_support import COLORS, FileRow, LogPanel, ToolTab, set_window_icon
from modules.gui_project_workbench import TabProjectWorkbench
from modules.gui_result_browser import TabResultBrowser
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
