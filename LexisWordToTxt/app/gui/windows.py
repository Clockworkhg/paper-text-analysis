# app/gui/windows.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
import json

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.gui.app import App

from app.constants import (
    USER_CANONICAL_MAP_FILE,
    USER_NOISE_KEYWORDS_FILE,
    DEFAULT_SOURCE_CANONICAL_MAP,
    DEFAULT_NOISE_KEYWORDS,
)


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent: "App"):
        super().__init__(parent)
        self.title("设置")
        self.geometry("540x480")
        self.resizable(False, True)

        self.parent = parent
        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        # ===== 输出与分组 =====
        group_box = ttk.Labelframe(frame, text="输出与分组", padding=12)
        group_box.pack(fill="x", pady=(0, 12))

        ttk.Checkbutton(
            group_box,
            text="写入 SOURCE / DATE 到文件头部",
            variable=self.parent.write_meta_var
        ).pack(anchor="w")

        ttk.Checkbutton(
            group_box,
            text="按媒体机构分文件夹输出",
            variable=self.parent.group_by_source_var
        ).pack(anchor="w", pady=(6, 0))

        ttk.Checkbutton(
            group_box,
            text="规范化媒体机构名称（合并 Reuters (UK) / Reuters 等）",
            variable=self.parent.normalize_source_var
        ).pack(anchor="w", pady=(6, 0))

        # ===== 文件命名 =====
        name_box = ttk.Labelframe(frame, text="文件命名", padding=12)
        name_box.pack(fill="x", pady=(0, 12))

        ttk.Label(name_box, text="文件名最大长度：").pack(anchor="w")
        ttk.Spinbox(
            name_box,
            from_=40,
            to=200,
            textvariable=self.parent.max_len_var,
            width=8
        ).pack(anchor="w", pady=(4, 0))

        # ===== 机构识别规则 =====
        rule_box = ttk.Labelframe(frame, text="机构识别规则", padding=12)
        rule_box.pack(fill="x", pady=(0, 12))

        ttk.Button(
            rule_box,
            text="编辑 / 导入机构识别规则…",
            command=self.open_rule_editor
        ).pack(anchor="w")

        # ===== 底部按钮 =====
        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x", pady=(12, 0))

        ttk.Button(
            btn_row,
            text="关闭",
            command=self._close
        ).pack(side="right")

    def _close(self):
        self.parent.save_settings()
        self.destroy()

    def open_rule_editor(self):
        RuleEditorWindow(self.parent)


class RuleEditorWindow(tk.Toplevel):
    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.title("机构识别规则")
        self.geometry("760x560")
        self.resizable(True, True)
        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="权威映射表（JSON 对象：{别名: 统一名}）").pack(anchor="w")
        self.map_text = tk.Text(frame, height=14, wrap="none")
        self.map_text.pack(fill="both", expand=True)
        self.map_text.insert("1.0", json.dumps(self.app.source_canonical_map, ensure_ascii=False, indent=2))

        ttk.Label(frame, text="非核心机构/噪音关键词（JSON 数组：[\"Newstex\", \"Narrowed by\", ...]）").pack(anchor="w", pady=(10, 0))
        self.noise_text = tk.Text(frame, height=8, wrap="none")
        self.noise_text.pack(fill="both", expand=True)
        self.noise_text.insert("1.0", json.dumps(self.app.source_noise_keywords, ensure_ascii=False, indent=2))

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(10, 0))

        ttk.Button(btns, text="使用默认规则", command=self.use_default).pack(side="left")
        ttk.Button(btns, text="导入 JSON 文件…", command=self.import_json).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="导出当前规则…", command=self.export_json).pack(side="left", padx=(8, 0))

        ttk.Button(btns, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="保存并应用", command=self.save_apply).pack(side="right", padx=(0, 8))

    def use_default(self):
        self.map_text.delete("1.0", "end")
        self.map_text.insert("1.0", json.dumps(DEFAULT_SOURCE_CANONICAL_MAP, ensure_ascii=False, indent=2))
        self.noise_text.delete("1.0", "end")
        self.noise_text.insert("1.0", json.dumps(DEFAULT_NOISE_KEYWORDS, ensure_ascii=False, indent=2))

    def save_apply(self):
        try:
            canonical_map = json.loads(self.map_text.get("1.0", "end").strip() or "{}")
            noise_keywords = json.loads(self.noise_text.get("1.0", "end").strip() or "[]")

            if not isinstance(canonical_map, dict):
                raise ValueError("映射表必须是 JSON 对象（dict）")
            if not isinstance(noise_keywords, list) or not all(isinstance(x, str) for x in noise_keywords):
                raise ValueError("噪音关键词必须是 JSON 数组（list[str]）")

            # 保存到文件
            with open(USER_CANONICAL_MAP_FILE, "w", encoding="utf-8") as f:
                json.dump(canonical_map, f, ensure_ascii=False, indent=2)
            with open(USER_NOISE_KEYWORDS_FILE, "w", encoding="utf-8") as f:
                json.dump(noise_keywords, f, ensure_ascii=False, indent=2)

            # 立即应用到当前运行的 App
            self.app.source_canonical_map = canonical_map
            self.app.source_noise_keywords = noise_keywords

            messagebox.showinfo("成功", "规则已保存并生效。")
            self.destroy()

        except Exception as e:
            messagebox.showerror("规则保存失败", f"请检查 JSON 格式：\n{e}")

    def import_json(self):
        path = filedialog.askopenfilename(
            title="选择 JSON 规则文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return

        kind = self.ask_import_kind()
        if kind is None:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 允许一种“总配置”格式：{"canonical_map": {...}, "noise_keywords": [...]}
            if isinstance(data, dict) and ("canonical_map" in data or "noise_keywords" in data):
                if kind == "map":
                    cm = data.get("canonical_map", None)
                    if cm is None:
                        raise ValueError("该文件不包含 canonical_map。")
                    if not isinstance(cm, dict):
                        raise ValueError("canonical_map 必须是 JSON 对象（dict）。")
                    self.map_text.delete("1.0", "end")
                    self.map_text.insert("1.0", json.dumps(cm, ensure_ascii=False, indent=2))
                else:
                    nk = data.get("noise_keywords", None)
                    if nk is None:
                        raise ValueError("该文件不包含 noise_keywords。")
                    if not isinstance(nk, list) or not all(isinstance(x, str) for x in nk):
                        raise ValueError("noise_keywords 必须是 JSON 数组（list[str]）。")
                    self.noise_text.delete("1.0", "end")
                    self.noise_text.insert("1.0", json.dumps(nk, ensure_ascii=False, indent=2))

                messagebox.showinfo("导入成功", "已导入到编辑框（尚未保存并应用）。")
                return

            if kind == "map":
                if not isinstance(data, dict):
                    raise ValueError("你选择了“映射表”，但该 JSON 不是对象（dict）。")
                self.map_text.delete("1.0", "end")
                self.map_text.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
                messagebox.showinfo("导入成功", "已导入映射表到上方编辑框（尚未保存并应用）。")
                return

            if kind == "noise":
                if not (isinstance(data, list) and all(isinstance(x, str) for x in data)):
                    raise ValueError("你选择了“噪音词”，但该 JSON 不是字符串数组（list[str]）。")
                self.noise_text.delete("1.0", "end")
                self.noise_text.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
                messagebox.showinfo("导入成功", "已导入噪音关键词到下方编辑框（尚未保存并应用）。")
                return

        except Exception as e:
            messagebox.showerror("导入失败", f"导入的 JSON 不合法或结构不匹配：\n{e}")

    def export_json(self):
        path = filedialog.asksaveasfilename(
            title="导出规则到 JSON",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")]
        )
        if not path:
            return

        try:
            canonical_map = json.loads(self.map_text.get("1.0", "end").strip() or "{}")
            noise_keywords = json.loads(self.noise_text.get("1.0", "end").strip() or "[]")

            if not isinstance(canonical_map, dict):
                raise ValueError("上方映射表必须是 JSON 对象（dict）")
            if not isinstance(noise_keywords, list) or not all(isinstance(x, str) for x in noise_keywords):
                raise ValueError("下方噪音关键词必须是 JSON 数组（list[str]）")

            data = {
                "canonical_map": canonical_map,
                "noise_keywords": noise_keywords
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            messagebox.showinfo("导出成功", f"已导出到：\n{path}")

        except Exception as e:
            messagebox.showerror("导出失败", f"导出失败：\n{e}")

    def ask_import_kind(self) -> str | None:
        win = tk.Toplevel(self)
        win.title("选择导入类型")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        kind_var = tk.StringVar(value="map")

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="这份 JSON 你要导入为：").pack(anchor="w", pady=(0, 8))
        ttk.Radiobutton(frame, text="权威映射表（别名 → 统一名）", value="map", variable=kind_var).pack(anchor="w")
        ttk.Radiobutton(frame, text="非核心机构/噪音关键词列表", value="noise", variable=kind_var).pack(anchor="w", pady=(6, 0))

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(12, 0))

        result = {"value": None}

        def ok():
            result["value"] = kind_var.get()
            win.destroy()

        def cancel():
            result["value"] = None
            win.destroy()

        ttk.Button(btns, text="取消", command=cancel).pack(side="right")
        ttk.Button(btns, text="确定", command=ok).pack(side="right", padx=(0, 8))

        self.wait_window(win)
        return result["value"]


class ReportViewerWindow(tk.Toplevel):
    CN = {
        "generated_at": "生成时间",
        "input_docx": "输入 DOCX",
        "output_dir": "输出目录",
        "options": "运行选项",
        "write_metadata": "写入 SOURCE/DATE",
        "group_by_source": "按机构分文件夹",
        "normalize_source": "规范化机构名",
        "filename_max_len": "文件名最大长度",
        "stats": "统计信息",
        "total_articles": "总文章数",
        "empty_body_count": "空正文数",
        "sources_total": "机构数量",
        "unknown_source_count": "未知机构数",
        "by_source_count": "按机构统计（篇数）",
        "unknown_examples": "未知机构样例",
        "rules": "规则信息",
        "canonical_map_size": "映射表条目数",
        "noise_keywords_size": "噪音词条目数",
    }

    def __init__(self, parent: "App", report_path: Path):
        super().__init__(parent)
        self.title("上次处理报告（中文展示）")
        self.geometry("760x560")
        self.report_path = report_path

        self._build_ui()
        self._load_and_render()

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="报告文件：").pack(side="left")
        self.path_entry = ttk.Entry(top)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.path_entry.insert(0, str(self.report_path))
        self.path_entry.configure(state="readonly")

        ttk.Button(top, text="刷新", command=self._load_and_render).pack(side="left", padx=(0, 6))
        ttk.Button(top, text="打开所在文件夹", command=self._open_folder).pack(side="left")

        body = ttk.Frame(self, padding=(10, 0, 10, 10))
        body.pack(fill="both", expand=True)

        self.text = tk.Text(body, wrap="word")
        self.text.pack(fill="both", expand=True)

    def _open_folder(self):
        try:
            import os
            os.startfile(str(self.report_path.parent))
        except Exception as e:
            messagebox.showwarning("无法打开", f"无法打开文件夹：\n{e}")

    def _load_and_render(self):
        try:
            with open(self.report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("读取失败", f"无法读取报告：\n{e}")
            return

        out = self._to_cn_text(data)

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", out)
        self.text.configure(state="disabled")

    def _t(self, key: str) -> str:
        return self.CN.get(key, key)

    def _to_cn_text(self, data: dict) -> str:
        lines = []

        lines.append(f"{self._t('generated_at')}：{data.get('generated_at', '')}")

        # 兼容 batch 报告：优先展示 batch 摘要，否则回退单文件字段
        batch = data.get("batch") or {}
        if batch:
            lines.append(f"批处理文件数：{batch.get('input_files_count', '')}")
        else:
            lines.append(f"{self._t('input_docx')}：{data.get('input_docx', '')}")

        lines.append(f"{self._t('output_dir')}：{data.get('output_dir', '')}")
        lines.append("")

        stats = data.get("stats", {}) or {}
        lines.append(f"【{self._t('stats')}】")
        lines.append(f"- {self._t('total_articles')}：{stats.get('total_articles', '')}")
        lines.append(f"- {self._t('empty_body_count')}：{stats.get('empty_body_count', '')}")
        lines.append(f"- {self._t('sources_total')}：{stats.get('sources_total', '')}")
        lines.append(f"- {self._t('unknown_source_count')}：{stats.get('unknown_source_count', '')}")
        lines.append("")

        opts = data.get("options", {}) or {}
        lines.append(f"【{self._t('options')}】")
        lines.append(f"- {self._t('write_metadata')}：{opts.get('write_metadata', '')}")
        lines.append(f"- {self._t('group_by_source')}：{opts.get('group_by_source', '')}")
        lines.append(f"- {self._t('normalize_source')}：{opts.get('normalize_source', '')}")
        lines.append(f"- {self._t('filename_max_len')}：{opts.get('filename_max_len', '')}")
        lines.append("")

        rules = data.get("rules", {}) or {}
        lines.append(f"【{self._t('rules')}】")
        lines.append(f"- {self._t('canonical_map_size')}：{rules.get('canonical_map_size', '')}")
        lines.append(f"- {self._t('noise_keywords_size')}：{rules.get('noise_keywords_size', '')}")
        lines.append("")

        by_source = data.get("by_source_count", {}) or {}
        lines.append(f"【{self._t('by_source_count')}】")
        if not by_source:
            lines.append("（无）")
        else:
            for i, (k, v) in enumerate(by_source.items()):
                if i >= 50:
                    lines.append(f"……（已截断，仅显示前 50 个机构；总计 {len(by_source)}）")
                    break
                lines.append(f"- {k}：{v}")
        lines.append("")

        unknown = data.get("unknown_examples", []) or []
        lines.append(f"【{self._t('unknown_examples')}】")
        if not unknown:
            lines.append("（无）")
        else:
            for item in unknown:
                title = item.get("title", "")
                raw_sources = item.get("raw_sources", [])
                lines.append(f"- 标题：{title}")
                lines.append(f"  原始 SOURCE：{' | '.join(raw_sources)}")
        lines.append("")

        return "\n".join(lines)


class RecentRunsWindow(tk.Toplevel):
    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.title("最近使用记录")
        self.geometry("860x420")
        self._build_ui()
        self._render()

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Button(top, text="刷新", command=self._render).pack(side="left")
        ttk.Button(top, text="打开报告", command=self.open_selected_report).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="打开输出目录", command=self.open_selected_outdir).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="删除选中", command=self.delete_selected).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="清空全部", command=self.clear_all).pack(side="left", padx=(8, 0))

        cols = ("time", "files", "articles", "empty", "out_dir", "report")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=14)
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tree.heading("time", text="时间")
        self.tree.heading("files", text="文件数")
        self.tree.heading("articles", text="文章数")
        self.tree.heading("empty", text="空正文")
        self.tree.heading("out_dir", text="输出目录")
        self.tree.heading("report", text="报告路径")

        self.tree.column("time", width=140, anchor="w")
        self.tree.column("files", width=70, anchor="center")
        self.tree.column("articles", width=80, anchor="center")
        self.tree.column("empty", width=70, anchor="center")
        self.tree.column("out_dir", width=220, anchor="w")
        self.tree.column("report", width=240, anchor="w")

        self.tree.bind("<Double-1>", lambda e: self.open_selected_report())

    def _render(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for idx, r in enumerate(self.app.recent_runs):
            self.tree.insert(
                "", "end", iid=str(idx),
                values=(
                    r.get("time", ""),
                    r.get("input_files_count", ""),
                    r.get("total_articles", ""),
                    r.get("empty_body_count", ""),
                    r.get("output_dir", ""),
                    r.get("report_path", ""),
                )
            )

    def _get_selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        i = int(sel[0])
        if i < 0 or i >= len(self.app.recent_runs):
            return None
        return self.app.recent_runs[i]

    def open_selected_report(self):
        r = self._get_selected()
        if not r:
            messagebox.showinfo("提示", "请先选择一条记录。")
            return
        p = Path(r.get("report_path", ""))
        if not p.exists():
            messagebox.showwarning("找不到报告", f"报告文件不存在：\n{p}")
            return
        ReportViewerWindow(self.app, p)

    def open_selected_outdir(self):
        r = self._get_selected()
        if not r:
            messagebox.showinfo("提示", "请先选择一条记录。")
            return
        p = Path(r.get("output_dir", ""))
        if not p.exists():
            messagebox.showwarning("找不到目录", f"输出目录不存在：\n{p}")
            return
        try:
            import os
            os.startfile(str(p))
        except Exception as e:
            messagebox.showwarning("无法打开", str(e))

    def delete_selected(self):
        r = self._get_selected()
        if not r:
            messagebox.showinfo("提示", "请先选择一条记录。")
            return
        sel = self.tree.selection()
        i = int(sel[0])
        del self.app.recent_runs[i]
        self.app.save_settings()
        self._render()

    def clear_all(self):
        if not messagebox.askyesno("确认", "确定清空所有最近使用记录吗？"):
            return
        self.app.recent_runs = []
        self.app.save_settings()
        self._render()
