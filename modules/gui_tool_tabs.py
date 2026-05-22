# -*- coding: utf-8 -*-
"""Small standalone tool tabs for the integrated desktop app."""

from __future__ import annotations

import json

import pandas as pd
import tkinter as tk
from tkinter import messagebox, ttk

from modules.gui_support import FileRow, ToolTab

class TabKWIC(ToolTab):
    def __init__(self, master):
        super().__init__(master)
        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        row = 0
        FileRow(self, "KWIC文件:", "open", [("Text", "*.txt"), ("All", "*.*")], self.in_var) \
            .grid(row=row, column=0, sticky="ew", **self._pad); row += 1
        FileRow(self, "导出Excel:", "save", [("Excel", "*.xlsx")], self.out_var) \
            .grid(row=row, column=0, sticky="ew", **self._pad); row += 1
        self.run_btn = ttk.Button(self, text="▶ 开始分析", style="Accent.TButton", command=lambda: self._start(self.run_btn))
        self.run_btn.grid(row=row, column=0, **self._pad)
        self._finish(progress_mode=None, log_height=18)

    def _validate(self):
        if not self.in_var.get() or not self.out_var.get():
            messagebox.showerror("错误", "请选择输入和输出文件。")
            return False
        return True

    def _worker_impl(self):
        try:
            from modules.KWICtoecxl import analyze_kwic
            df = analyze_kwic(self.in_var.get())
            df.to_excel(self.out_var.get(), index=False)
            self._w_put("done", f"完成: {self.out_var.get()}\n形容词数: {len(df)}")
        except Exception as e:
            self._w_put("error", str(e))


class TabColumnMerge(ToolTab):
    def __init__(self, master):
        super().__init__(master)
        pad = self._pad

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.df = None
        self.columns = []
        self.key_vars = {}
        self.sum_vars = {}

        row = 0
        FileRow(self, "输入文件:", "open", [("Excel", "*.xlsx *.xls"), ("CSV", "*.csv"), ("All", "*.*")], self.in_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "导出文件:", "save", [("Excel", "*.xlsx"), ("CSV", "*.csv")], self.out_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1

        bf = ttk.Frame(self)
        bf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Button(bf, text="读取列名", style="Ghost.TButton", command=self.load_columns).pack(side="left")
        self.run_btn = ttk.Button(bf, text="▶ 合并并导出", style="Accent.TButton", command=lambda: self._start(self.run_btn))
        self.run_btn.pack(side="left", padx=12)

        cols_frame = ttk.Frame(self)
        cols_frame.grid(row=row, column=0, sticky="nsew", **pad); row += 1
        self.rowconfigure(row, weight=1)
        cols_frame.columnconfigure(0, weight=1)
        cols_frame.columnconfigure(1, weight=1)

        left = ttk.LabelFrame(cols_frame, text="分组键列（勾选）")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.key_frame = ttk.Frame(left)
        self.key_frame.pack(fill="both", expand=True, padx=8, pady=6)

        right = ttk.LabelFrame(cols_frame, text="求和列（勾选）")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self.sum_frame = ttk.Frame(right)
        self.sum_frame.pack(fill="both", expand=True, padx=8, pady=6)

        self._finish(progress_mode=None, log_height=8)

    def load_columns(self):
        path = self.in_var.get()
        if not path:
            messagebox.showwarning("提示", "请先选择输入文件。")
            return
        try:
            from shared.io_utils import read_table
            self.df = read_table(path)
            self.df.columns = [str(c) for c in self.df.columns]
            self.columns = list(self.df.columns)

            for w in self.key_frame.winfo_children():
                w.destroy()
            for w in self.sum_frame.winfo_children():
                w.destroy()
            self.key_vars.clear()
            self.sum_vars.clear()

            num_like = set()
            for c in self.columns[1:]:
                s = pd.to_numeric(self.df[c], errors="coerce")
                if s.notna().sum() > 0:
                    num_like.add(c)

            for c in self.columns:
                vk = tk.BooleanVar(value=(c == self.columns[0]))
                self.key_vars[c] = vk
                ttk.Checkbutton(self.key_frame, text=c, variable=vk).pack(anchor="w")

                vs = tk.BooleanVar(value=(c in num_like))
                self.sum_vars[c] = vs
                ttk.Checkbutton(self.sum_frame, text=c, variable=vs).pack(anchor="w")

            self.log.log(f"已加载: {len(self.df)}行, {len(self.columns)}列")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _validate(self):
        if not self.in_var.get() or not self.out_var.get():
            messagebox.showerror("错误", "请选择输入和输出文件。")
            return False
        if self.df is None:
            self.load_columns()
        if self.df is None:
            return False
        key_cols = [c for c, v in self.key_vars.items() if v.get()]
        if not key_cols:
            messagebox.showerror("错误", "请至少选择1个分组键列。")
            return False
        sum_cols = [c for c, v in self.sum_vars.items() if v.get()]
        overlap = set(key_cols) & set(sum_cols)
        if overlap:
            messagebox.showerror("错误", f"这些列同时被选为键列和求和列: {', '.join(overlap)}")
            return False
        return True

    def _worker_impl(self):
        try:
            from shared.io_utils import write_table
            key_cols = [c for c, v in self.key_vars.items() if v.get()]
            sum_cols = [c for c, v in self.sum_vars.items() if v.get()]
            df = self.df.copy()
            other_cols = [c for c in df.columns if c not in key_cols and c not in sum_cols]
            agg = {c: "first" for c in other_cols}
            for c in sum_cols:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
                agg[c] = "sum"
            result = df.groupby(key_cols, as_index=False).agg(agg)
            result = result[key_cols + other_cols + sum_cols]
            write_table(result, self.out_var.get())
            self._w_put("done", f"完成: {self.out_var.get()}\n{len(df)}→{len(result)} 行")
        except Exception as e:
            self._w_put("error", str(e))


class TabJSONtoExcel(ToolTab):
    def __init__(self, master):
        super().__init__(master)
        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        row = 0
        FileRow(self, "报告JSON:", "open", [("JSON", "*.json"), ("All", "*.*")], self.in_var) \
            .grid(row=row, column=0, sticky="ew", **self._pad); row += 1
        FileRow(self, "导出Excel:", "save", [("Excel", "*.xlsx"), ("CSV", "*.csv")], self.out_var) \
            .grid(row=row, column=0, sticky="ew", **self._pad); row += 1
        self.run_btn = ttk.Button(self, text="▶ 转换", style="Accent.TButton", command=lambda: self._start(self.run_btn))
        self.run_btn.grid(row=row, column=0, **self._pad)
        self._finish(progress_mode=None, log_height=18)

    def _validate(self):
        if not self.in_var.get() or not self.out_var.get():
            messagebox.showerror("错误", "请选择输入和输出文件。")
            return False
        return True

    def _worker_impl(self):
        try:
            with open(self.in_var.get(), "r", encoding="utf-8") as f:
                data = json.load(f)
            src = data.get("by_source_count", {})
            if not isinstance(src, dict):
                raise ValueError("未找到 by_source_count 字段")
            df = pd.DataFrame([{"Source": k, "Count": v} for k, v in src.items()]).sort_values("Count", ascending=False)
            out = self.out_var.get()
            if out.lower().endswith(".xlsx"):
                df.to_excel(out, index=False)
            else:
                df.to_csv(out, index=False, encoding="utf-8-sig")
            self._w_put("done", f"完成: {out}\n{len(df)} 机构, {df['Count'].sum()} 篇")
        except Exception as e:
            self._w_put("error", str(e))


