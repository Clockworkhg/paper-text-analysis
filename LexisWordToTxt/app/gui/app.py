# app/gui/app.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime
import queue
import threading

from docx import Document  # 你 run() 里用到了

from app.constants import (
    APP_TITLE,
    USAGE_TEXT,
    USER_CANONICAL_MAP_FILE,
    USER_NOISE_KEYWORDS_FILE,
    DEFAULT_SOURCE_CANONICAL_MAP,
    DEFAULT_NOISE_KEYWORDS,
)
from app.rules import load_user_json
from app.processor import preflight_check, process_docx, write_report_json
from app.settings_store import SettingsStore, add_recent_run
from app.gui.windows import SettingsWindow, ReportViewerWindow, RecentRunsWindow

# 项目根目录：.../LexisWordToTxt
BASE_DIR = Path(__file__).resolve().parents[2]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)

        # store + settings
        self.store = SettingsStore()
        self.settings = self.store.load()

        self.geometry("920x620")

        # icon（相对路径不稳定，改为基于项目根）
        icon_path = BASE_DIR / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        # ===== 主界面变量 =====
        self.docx_path_var = tk.StringVar(value="")
        self.docx_paths: list[Path] = []
        self.out_dir_var = tk.StringVar(value="")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.last_report_path_var = tk.StringVar(value="")
        self.last_docx_dir_var = tk.StringVar(value="")
        self.last_out_dir_var = tk.StringVar(value="")
        self.recent_runs: list[dict] = []

        # ===== 设置相关变量 =====
        self.write_meta_var = tk.BooleanVar(value=True)
        self.group_by_source_var = tk.BooleanVar(value=True)
        self.normalize_source_var = tk.BooleanVar(value=True)
        self.max_len_var = tk.IntVar(value=80)

        # ===== 运行状态 =====
        self._worker_thread = None
        self._log_queue = queue.Queue()

        # 从 settings.json 恢复
        self.load_settings()

        # 加载规则文件（用户规则不存在就用默认）
        self.source_canonical_map = load_user_json(
            USER_CANONICAL_MAP_FILE,
            DEFAULT_SOURCE_CANONICAL_MAP
        )
        self.source_noise_keywords = load_user_json(
            USER_NOISE_KEYWORDS_FILE,
            DEFAULT_NOISE_KEYWORDS
        )

        self._build_ui()
        self._poll_log_queue()

    # ---------------- settings 存取（薄封装） ----------------
    def load_settings(self):
        s = self.settings or {}

        self.last_report_path_var.set(s.get("last_report_path", ""))
        self.last_docx_dir_var.set(s.get("last_docx_dir", ""))
        self.last_out_dir_var.set(s.get("last_out_dir", ""))

        self.write_meta_var.set(bool(s.get("write_metadata", True)))
        self.group_by_source_var.set(bool(s.get("group_by_source", True)))
        self.normalize_source_var.set(bool(s.get("normalize_source", True)))
        try:
            self.max_len_var.set(int(s.get("filename_max_len", 80)))
        except Exception:
            self.max_len_var.set(80)

        self.recent_runs = list(s.get("recent_runs", []) or [])

    def save_settings(self):
        self.settings = self.settings or {}
        self.settings.update({
            "last_report_path": self.last_report_path_var.get(),
            "last_docx_dir": self.last_docx_dir_var.get(),
            "last_out_dir": self.last_out_dir_var.get(),
            "write_metadata": bool(self.write_meta_var.get()),
            "group_by_source": bool(self.group_by_source_var.get()),
            "normalize_source": bool(self.normalize_source_var.get()),
            "filename_max_len": int(self.max_len_var.get()),
            "recent_runs": self.recent_runs,
        })
        self.store.save(self.settings)

    def add_recent_run(self, item: dict):
        self.settings = self.settings or {}
        self.settings = add_recent_run(self.settings, item)
        self.recent_runs = self.settings.get("recent_runs", [])
    # --------------------------------------------------------

    def on_close(self):
        self.save_settings()
        self.destroy()

    def open_settings(self):
        SettingsWindow(self)

    def open_last_report(self):
        path = (self.last_report_path_var.get() or "").strip()
        if not path:
            messagebox.showinfo("提示", "还没有生成过报告。请先运行一次处理。")
            return

        p = Path(path)
        if not p.exists():
            messagebox.showwarning("找不到报告", f"上次报告文件不存在：\n{p}\n\n可能被移动或删除了。")
            return

        ReportViewerWindow(self, p)

    def open_recent_runs(self):
        RecentRunsWindow(self)

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # 顶部：文件选择区
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")

        row1 = ttk.Frame(top)
        row1.pack(fill="x", pady=(0, 8))
        ttk.Label(row1, text="DOCX 文件：", width=10).pack(side="left")
        ttk.Entry(row1, textvariable=self.docx_path_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row1, text="选择 DOCX 文件", command=self.choose_docx).pack(side="left")

        row2 = ttk.Frame(top)
        row2.pack(fill="x")
        ttk.Label(row2, text="输出文件夹：", width=10).pack(side="left")
        ttk.Entry(row2, textvariable=self.out_dir_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row2, text="选择输出文件夹", command=self.choose_out_dir).pack(side="left")

        # 中部：选项区
        opts = ttk.Labelframe(self, text="选项", padding=12)
        opts.pack(fill="x", padx=12, pady=(0, 8))

        opt_row = ttk.Frame(opts)
        opt_row.pack(fill="x")

        ttk.Checkbutton(
            opt_row,
            text="写入 SOURCE / DATE 到 txt 文件头部",
            variable=self.write_meta_var
        ).pack(side="left")

        ttk.Label(opt_row, text="文件名最大长度：").pack(side="left", padx=(18, 6))

        spin = ttk.Spinbox(
            opt_row,
            from_=40,
            to=200,
            textvariable=self.max_len_var,
            width=6
        )
        spin.pack(side="left")

        # 操作区
        action = ttk.Frame(self, padding=(12, 0, 12, 4))
        action.pack(fill="x")

        self.run_btn = ttk.Button(action, text="开始处理", command=self.run)
        self.run_btn.pack(side="left")

        ttk.Button(action, text="设置", command=self.open_settings).pack(side="left", padx=(8, 0))
        ttk.Button(action, text="查看上次报告", command=self.open_last_report).pack(side="left", padx=(8, 0))
        ttk.Button(action, text="最近使用记录", command=self.open_recent_runs).pack(side="left", padx=(8, 0))

        # 进度条
        progress_row = ttk.Frame(self, padding=(12, 0, 12, 8))
        progress_row.pack(fill="x")
        self.progress = ttk.Progressbar(progress_row, mode="indeterminate")
        self.progress.pack(fill="x")

        # 下部：说明 + 日志（左右分栏）
        bottom = ttk.Frame(self, padding=12)
        bottom.pack(fill="both", expand=True)

        left = ttk.Labelframe(bottom, text="说明", padding=10)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        usage = tk.Text(left, wrap="word", height=18)
        usage.insert("1.0", USAGE_TEXT)
        usage.configure(state="disabled")
        usage.pack(fill="both", expand=True)

        right = ttk.Labelframe(bottom, text="运行日志", padding=10)
        right.pack(side="left", fill="both", expand=True)

        self.log_text = tk.Text(right, wrap="word", height=18)
        self.log_text.pack(fill="both", expand=True)

        footer = ttk.Frame(self, padding=(12, 0, 12, 10))
        footer.pack(fill="x")
        ttk.Label(footer, text="版本：v1.0 ｜ 作者：Hershel ｜ 用途：科研文本处理").pack(anchor="w")

    def choose_docx(self):
        init_dir = (self.last_docx_dir_var.get() or "").strip()
        if init_dir and not Path(init_dir).exists():
            init_dir = ""

        paths = filedialog.askopenfilenames(
            title="选择 Lexis 导出的 DOCX 文件（可多选）",
            initialdir=init_dir or None,
            filetypes=[("Word 文件", "*.docx")]
        )
        if not paths:
            return

        self.docx_paths = [Path(p) for p in paths]

        # 记录上次打开目录
        try:
            self.last_docx_dir_var.set(str(self.docx_paths[0].parent))
            self.save_settings()
        except Exception:
            pass

        if len(self.docx_paths) == 1:
            self.docx_path_var.set(str(self.docx_paths[0]))
        else:
            self.docx_path_var.set(f"已选择 {len(self.docx_paths)} 个 DOCX 文件（点击可重新选择）")

    def choose_out_dir(self):
        init_dir = (self.last_out_dir_var.get() or "").strip()
        if init_dir and not Path(init_dir).exists():
            init_dir = ""

        path = filedialog.askdirectory(
            title="选择 TXT 输出文件夹",
            initialdir=init_dir or None
        )
        if not path:
            return

        self.out_dir_var.set(path)

        self.last_out_dir_var.set(path)
        self.save_settings()

    def log(self, msg: str):
        self._log_queue.put(msg)

    def _poll_log_queue(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.after(120, self._poll_log_queue)

    def _set_running(self, running: bool):
        if running:
            self.run_btn.configure(state="disabled")
            self.progress.start(10)
        else:
            self.run_btn.configure(state="normal")
            self.progress.stop()

    def run(self):
        out_dir = self.out_dir_var.get().strip()
        docx_list = list(self.docx_paths)

        if not docx_list:
            messagebox.showwarning("缺少输入", "请先选择 DOCX 文件（可多选）。")
            return

        if not out_dir:
            messagebox.showwarning("缺少输出", "请先选择输出文件夹。")
            return

        p_out = Path(out_dir)

        bad = [p for p in docx_list if (not p.exists()) or (p.suffix.lower() != ".docx")]
        if bad:
            messagebox.showerror(
                "输入无效",
                "以下文件不存在或不是 .docx：\n\n" + "\n".join(str(x) for x in bad[:20])
            )
            return

        try:
            max_len = int(self.max_len_var.get())
            if max_len < 40 or max_len > 200:
                raise ValueError
        except Exception:
            messagebox.showerror("参数无效", "文件名最大长度建议在 40–200 之间。")
            return

        write_meta = bool(self.write_meta_var.get())
        group_by_source = bool(self.group_by_source_var.get())

        self.log_text.delete("1.0", "end")
        self.log("启动任务…")

        # ===== 多文件预检 =====
        precheck_results = []
        for p_docx in docx_list:
            try:
                doc = Document(p_docx)
                full_text = "\n".join(p.text for p in doc.paragraphs)
            except Exception as e:
                messagebox.showerror("读取失败", f"无法读取 DOCX：\n{p_docx}\n\n{e}")
                return

            check = preflight_check(full_text)
            precheck_results.append((p_docx, check))

        bad_count = sum(1 for _, c in precheck_results if not c.get("ok", False))
        warn_count = sum(1 for _, c in precheck_results if c.get("level") == "warn")
        self.log(f"预检完成：共 {len(docx_list)} 个文件 | 不通过 {bad_count} | 警告 {warn_count}")

        need_confirm = any((not c.get("ok", False)) or (c.get("level") == "warn") for _, c in precheck_results)
        if need_confirm:
            lines = []
            shown = 0
            for p, c in precheck_results:
                if (not c.get("ok", False)) or (c.get("level") == "warn"):
                    shown += 1
                    head = "ERROR" if not c.get("ok", False) else "WARN"
                    lines.append(f"[{head}] {p.name}")
                    for m in (c.get("messages") or [])[:3]:
                        lines.append(f"  - {m}")
                    if shown >= 6:
                        break
            if shown < (bad_count + warn_count):
                lines.append(f"……（还有 {bad_count + warn_count - shown} 个文件存在提示，已省略）")

            msg = "检测到部分文件可能不是标准 Lexis 格式。\n\n" + "\n".join(lines) + "\n\n仍然继续处理所有文件吗？"
            go_on = messagebox.askyesno("格式检测提示", msg)
            if not go_on:
                return

        self._set_running(True)

        def worker():
            report_path = None
            try:
                started_at = datetime.now()

                total_files = len(docx_list)
                total_articles_all = 0
                total_empty_all = 0

                merged_by_source = {}
                merged_unknown_examples = []
                per_file = []

                for i, p_docx in enumerate(docx_list, start=1):
                    self.log(f"=== 处理文件 {i}/{total_files}：{p_docx.name} ===")

                    count, empty_body, file_report = process_docx(
                        docx_path=p_docx,
                        out_dir=p_out,
                        write_metadata=write_meta,
                        filename_max_len=max_len,
                        group_by_source=group_by_source,
                        canonical_map=self.source_canonical_map,
                        noise_keywords=self.source_noise_keywords,
                        normalize_source=bool(self.normalize_source_var.get()),
                        log_fn=self.log
                    )

                    total_articles_all += int(count)
                    total_empty_all += int(empty_body)

                    per_file.append({
                        "input_docx": str(p_docx),
                        "stats": (file_report.get("stats") or {}),
                        "by_source_count": (file_report.get("by_source_count") or {}),
                    })

                    by_source = file_report.get("by_source_count") or {}
                    for k, v in by_source.items():
                        merged_by_source[k] = merged_by_source.get(k, 0) + int(v)

                    unk = file_report.get("unknown_examples") or []
                    for item in unk:
                        if len(merged_unknown_examples) >= 30:
                            break
                        merged_unknown_examples.append(item)

                finished_at = datetime.now()

                merged_report = {
                    "generated_at": finished_at.isoformat(timespec="seconds"),
                    "batch": {
                        "started_at": started_at.isoformat(timespec="seconds"),
                        "finished_at": finished_at.isoformat(timespec="seconds"),
                        "input_files_count": int(total_files),
                        "input_files": [str(p) for p in docx_list],
                    },
                    "output_dir": str(p_out),
                    "options": {
                        "write_metadata": bool(write_meta),
                        "group_by_source": bool(group_by_source),
                        "normalize_source": bool(self.normalize_source_var.get()),
                        "filename_max_len": int(max_len),
                    },
                    "stats": {
                        "total_articles": int(total_articles_all),
                        "empty_body_count": int(total_empty_all),
                        "sources_total": int(len(merged_by_source)),
                        "unknown_source_count": int(merged_by_source.get("Unknown_Source", 0)),
                    },
                    "by_source_count": dict(sorted(merged_by_source.items(), key=lambda x: (-x[1], x[0]))),
                    "unknown_examples": merged_unknown_examples,
                    "rules": {
                        "canonical_map_size": len(self.source_canonical_map or {}),
                        "noise_keywords_size": len(self.source_noise_keywords or []),
                    },
                    "per_file_summary": per_file
                }

                report_path = write_report_json(p_out, merged_report)

                self.last_report_path_var.set(str(report_path))
                self.add_recent_run({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "input_files_count": int(total_files),
                    "total_articles": int(total_articles_all),
                    "empty_body_count": int(total_empty_all),
                    "output_dir": str(p_out),
                    "report_path": str(report_path),
                })
                self.save_settings()
                self.last_out_dir_var.set(str(p_out))

                self.log(f"📄 已生成总处理报告：{Path(report_path).name}")
                self.log("🎉 全部完成。")

                msg = (
                    f"处理完成！\n\n"
                    f"共处理 {total_files} 个 DOCX 文件。\n"
                    f"总计生成 {total_articles_all} 个 TXT 文件。\n"
                    f"输出目录：\n{p_out}\n\n"
                    f"处理报告：\n{report_path}"
                )
                if total_empty_all:
                    msg += f"\n\n注意：总计有 {total_empty_all} 篇未识别到 Body（仍已输出文件，正文为空）。"

                self.after(0, lambda m=msg: messagebox.showinfo("完成", m))

            except Exception as e:
                self.log(f"❌ 失败：{e}")
                self.after(0, lambda err=e: messagebox.showerror("错误", f"处理失败：\n{err}"))

            finally:
                self.after(0, lambda: self._set_running(False))

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()
