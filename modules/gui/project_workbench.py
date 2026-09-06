# -*- coding: utf-8 -*-
"""Project workbench tab for the integrated desktop app."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from modules.gui.support import COLORS, ToolTab

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

    GROUPING_MODES = [
        ("source", "原始来源表头"),
        ("institution", "媒体机构 (规范来源)"),
        ("country", "国别 (需先运行国别推断)"),
        ("custom", "自定义映射 (立场等)"),
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

        ttk.Label(self._step3, text="分组方式:").grid(row=4, column=0, sticky="e", padx=(0, 6), pady=2)
        self._s3_group_var = tk.StringVar(value="source")
        group_frame = ttk.Frame(self._step3)
        group_frame.grid(row=4, column=1, sticky="w", pady=2)
        ttk.Combobox(group_frame, textvariable=self._s3_group_var, state="readonly", width=26,
                     values=[m[0] for m in self.GROUPING_MODES]).pack(side="left")
        ttk.Label(group_frame, text="(对比表的分组变量)", foreground=COLORS["muted"],
                  font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(6, 0))

        self._s3_status = tk.Label(self._step3, text="", bg=COLORS["panel"], fg=COLORS["muted"],
                                   font=("Microsoft YaHei UI", 8), anchor="w")
        self._s3_status.grid(row=5, column=1, sticky="w")

        s3_btn_frame = ttk.Frame(self._step3)
        s3_btn_frame.grid(row=5, column=1, sticky="e")
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
                    group_by=self._s3_group_var.get(),
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

            # Restore the saved grouping mode
            valid_modes = [m[0] for m in self.GROUPING_MODES]
            if s.get("group_by") in valid_modes:
                self._s3_group_var.set(s["group_by"])

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
        "params": ["project.json", "Corpus type", "Targets", "分组方式", "Sample size"],
        "outputs": ["project.json", "adjectives_phrases.xlsx", "review artifacts", "research_report.md"],
        "group": "研究流程",
    },
    {
        "key": "pipeline",
        "title": "全流程运行",
        "subtitle": "从 LexisNexis DOCX 到复核材料和方法报告",
        "params": ["Lexis DOCX", "输出目录", "检索目标", "运行步骤", "国别推断", "分组方式"],
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

