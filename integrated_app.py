# -*- coding: utf-8 -*-
"""
新闻文本分析集成软件
统一主界面，分页切换各工具模块：
  流水线 / 机构合并+国别 / 修饰形容词分析 / 词性+翻译 / KWIC分析 / 自选合并 / JSON转Excel
"""

import logging
import re
import sys
from pathlib import Path


from modules.gui_support import COLORS, set_window_icon
from modules.gui_project_workbench import TabProjectWorkbench
from modules.gui_pipeline_tabs import TabAdjectives, TabMerge, TabPipeline, TabPOSTranslate
from modules.gui_result_browser import TabResultBrowser
from modules.gui_tool_tabs import TabColumnMerge, TabJSONtoExcel, TabKWIC

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

logger = logging.getLogger("integrated_app")


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
