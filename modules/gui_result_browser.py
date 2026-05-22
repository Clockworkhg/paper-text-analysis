# -*- coding: utf-8 -*-
"""Result workbook browser and inline review tab for the desktop app."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from modules.gui_support import COLORS, FileRow

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


