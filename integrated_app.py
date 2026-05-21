# -*- coding: utf-8 -*-
"""
新闻文本分析集成软件
统一主界面，分页切换各工具模块：
  流水线 / 机构合并+国别 / 修饰形容词分析 / 词性+翻译 / KWIC分析 / 自选合并 / JSON转Excel
"""

import json
import os
import re
import threading
import queue
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd


class WorkerMixin:
    def __init__(self):
        self._wq = queue.Queue()

    def _poll_worker(self, widget, interval=120):
        try:
            while True:
                item = self._wq.get_nowait()
                kind = item[0]
                if kind == "progress":
                    self._w_on_progress(*item[1:])
                elif kind == "log":
                    self._w_on_log(item[1])
                elif kind == "done":
                    self._w_on_done(item[1])
                elif kind == "error":
                    self._w_on_error(item[1])
        except queue.Empty:
            pass
        widget.after(interval, lambda: self._poll_worker(widget, interval))

    def _w_put(self, *args):
        self._wq.put(args)

    def _w_on_progress(self, msg, frac):
        pass

    def _w_on_log(self, msg):
        pass

    def _w_on_done(self, msg):
        pass

    def _w_on_error(self, msg):
        pass


class LogPanel(ttk.Frame):
    def __init__(self, master, height=12):
        super().__init__(master)
        self.text = tk.Text(self, height=height, wrap="word", state="normal")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def log(self, msg):
        self.text.insert("end", msg + "\n")
        self.text.see("end")

    def clear(self):
        self.text.delete("1.0", "end")


class FileRow(ttk.Frame):
    def __init__(self, master, label, mode="open", filetypes=None, var=None):
        super().__init__(master)
        self.var = var or tk.StringVar()
        ttk.Label(self, text=label, width=18, anchor="e").pack(side="left", padx=(0, 6))
        ttk.Entry(self, textvariable=self.var).pack(side="left", fill="x", expand=True)
        if mode == "open":
            ttk.Button(self, text="浏览…", width=6, command=self._open).pack(side="left", padx=(6, 0))
        else:
            ttk.Button(self, text="另存…", width=6, command=self._save).pack(side="left", padx=(6, 0))
        self._mode = mode
        self._filetypes = filetypes or [("All", "*.*")]

    def _open(self):
        p = filedialog.askopenfilename(filetypes=self._filetypes)
        if p:
            self.var.set(p)

    def _save(self):
        p = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=self._filetypes)
        if p:
            self.var.set(p)

    def get(self):
        return self.var.get().strip()


class TabPipeline(ttk.Frame, WorkerMixin):
    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        WorkerMixin.__init__(self)

        pad = {"padx": 8, "pady": 4}
        self.columnconfigure(0, weight=1)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.targets_var = tk.StringVar()
        self.country_var = tk.BooleanVar(value=True)
        self.force_var = tk.BooleanVar(value=False)
        self.step_vars = {i: tk.BooleanVar(value=True) for i in range(1, 6)}
        self.running = False

        row = 0
        FileRow(self, "Lexis DOCX:", "open", [("Word", "*.docx"), ("All", "*.*")], self.input_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "输出目录:", "open", var=self.output_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1

        tf = ttk.Frame(self)
        tf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Label(tf, text="检索目标:", width=18, anchor="e").pack(side="left", padx=(0, 6))
        ttk.Entry(tf, textvariable=self.targets_var).pack(side="left", fill="x", expand=True)
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
        self.run_btn = ttk.Button(bf, text="▶ 运 行 流 水 线", command=self.run)
        self.run_btn.pack(side="right")

        self.pbar = ttk.Progressbar(self, mode="indeterminate")
        self.pbar.grid(row=row, column=0, sticky="ew", **pad); row += 1

        self.log = LogPanel(self, height=16)
        self.log.grid(row=row, column=0, sticky="nsew", **pad); row += 1
        self.rowconfigure(row - 1, weight=1)

        self._poll_worker(self)

    def _w_on_log(self, msg):
        self.log.log(msg)

    def _w_on_done(self, msg):
        self.pbar.stop()
        self.run_btn.config(state="normal")
        self.running = False
        self.log.log(msg)
        messagebox.showinfo("完成", msg)

    def _w_on_error(self, msg):
        self.pbar.stop()
        self.run_btn.config(state="normal")
        self.running = False
        self.log.log(f"❌ 错误: {msg}")
        messagebox.showerror("错误", msg)

    def run(self):
        if self.running:
            return
        inp = self.input_var.get()
        out = self.output_var.get()
        if not inp or not out:
            messagebox.showerror("错误", "请选择输入文件和输出目录。")
            return

        steps = [i for i in range(1, 6) if self.step_vars[i].get()]
        if not steps:
            messagebox.showerror("错误", "请至少选择一个步骤。")
            return

        self.running = True
        self.run_btn.config(state="disabled")
        self.log.clear()
        self.pbar.start(10)

        args = (inp, out, self.targets_var.get(), self.country_var.get(), self.force_var.get(), steps)
        threading.Thread(target=self._worker, args=args, daemon=True).start()

    def _worker(self, inp, out_dir, targets, country, force, steps):
        try:
            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)

            if 1 in steps:
                self._w_put("log", "[步骤1] DOCX → TXT + 报告 JSON …")
                from docx import Document
                from LexisWordToTxt.app.processor import process_docx, write_report_json, preflight_check
                from LexisWordToTxt.app.constants import DEFAULT_SOURCE_CANONICAL_MAP, DEFAULT_NOISE_KEYWORDS

                corpus_dir = out / "corpus"
                docx_path = Path(inp)
                doc = Document(docx_path)
                full_text = "\n".join(p.text for p in doc.paragraphs)
                check = preflight_check(full_text)
                if not check["ok"]:
                    self._w_put("log", f"  ⚠ 预检: {'; '.join(check['messages'])}")

                count, empty, report = process_docx(
                    docx_path=docx_path, out_dir=corpus_dir,
                    write_metadata=True, filename_max_len=80,
                    group_by_source=True,
                    canonical_map=DEFAULT_SOURCE_CANONICAL_MAP,
                    noise_keywords=DEFAULT_NOISE_KEYWORDS,
                    normalize_source=True,
                    log_fn=lambda m: self._w_put("log", f"  {m}"),
                )
                report_path = write_report_json(corpus_dir, report)
                self._w_put("log", f"  文章数: {count}, 空正文: {empty}")
                self._w_put("log", f"  ✅ 步骤1完成: {corpus_dir}")

            if 2 in steps:
                self._w_put("log", "[步骤2] 报告 JSON → 机构统计表 …")
                corpus_dir = out / "corpus"
                rpts = sorted(corpus_dir.glob("report-*.json"))
                if not rpts:
                    raise FileNotFoundError("未找到步骤1的报告JSON")
                rp = rpts[-1]
                with open(rp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sources = data.get("by_source_count", {})
                df = pd.DataFrame([{"Source": k, "Count": v} for k, v in sources.items()]).sort_values("Count", ascending=False)
                src_excel = out / "source_counts.xlsx"
                df.to_excel(str(src_excel), index=False)
                self._w_put("log", f"  机构数: {len(df)}")
                self._w_put("log", f"  ✅ 步骤2完成: {src_excel}")

            if 3 in steps:
                self._w_put("log", "[步骤3] 机构合并 + 国别识别 …")
                from config import MergeConfig
                from hebing import run_hebing
                src_excel = out / "source_counts.xlsx"
                if not src_excel.exists():
                    raise FileNotFoundError(f"未找到: {src_excel}")
                merged_path = out / "merged_sources.xlsx"
                cfg = MergeConfig(
                    fuzzy_threshold=92,
                    enable_country_lookup=country,
                    request_delay_ms=150,
                    max_lookup=800,
                    auto_accept_threshold=0.85,
                    pie_topn=12,
                )
                run_hebing(str(src_excel), str(merged_path), "", cfg, verbose=True)
                self._w_put("log", f"  ✅ 步骤3完成: {merged_path}")

            if 4 in steps and targets.strip():
                self._w_put("log", "[步骤4] TXT语料 → 修饰形容词/短语 …")
                from config import TxtAnalysisConfig
                from txt_modifier_extractor_gui import process_txt, split_targets
                corpus_dir = out / "corpus"
                all_txt = list(corpus_dir.rglob("*.txt"))
                if not all_txt:
                    raise FileNotFoundError(f"语料目录 {corpus_dir} 下无 TXT 文件")
                merged_txt = out / "_corpus_merged.txt"
                with open(merged_txt, "w", encoding="utf-8") as f:
                    for tf in all_txt:
                        f.write(tf.read_text(encoding="utf-8", errors="ignore"))
                        f.write("\n\n==========\n\n")
                self._w_put("log", f"  合并 {len(all_txt)} 个 TXT")

                tgt_list = split_targets(targets)
                cfg = TxtAnalysisConfig(split_mode="regex", split_regex="====LINE====",
                                        window_tokens=8, phrase_max_tokens=6,
                                        nlp_batch_size=64, max_doc_chars=200000, use_online_judge=False)
                adj_excel = out / "adjectives_phrases.xlsx"
                process_txt(str(merged_txt), str(adj_excel), tgt_list, cfg,
                            log_cb=lambda m: self._w_put("log", f"  {m}"))
                self._w_put("log", f"  ✅ 步骤4完成: {adj_excel}")

            if 5 in steps and targets.strip():
                self._w_put("log", "[步骤5] 词性标注 + 中文翻译 …")
                from jiacixing import ensure_nltk_data, guess_pos, Translator
                adj_excel = out / "adjectives_phrases.xlsx"
                if not adj_excel.exists():
                    self._w_put("log", "  ⚠ 形容词表不存在，跳过")
                else:
                    ensure_nltk_data()
                    df_adj = pd.read_excel(str(adj_excel), sheet_name="Adjectives")
                    translator = Translator(concurrency=5)
                    words = df_adj["Adjective"].tolist()
                    self._w_put("log", f"  标注 {len(words)} 词…")
                    df_adj["POS"] = [guess_pos(None if pd.isna(w) else str(w)) for w in words]
                    df_adj["中文意思"] = translator.translate_batch(["" if pd.isna(w) else str(w) for w in words])
                    final_path = out / "adjectives_final.xlsx"
                    df_adj.to_excel(str(final_path), index=False)
                    self._w_put("log", f"  ✅ 步骤5完成: {final_path}")

            self._w_put("done", f"全流程完成！\n输出目录: {out.absolute()}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._w_put("error", str(e))


class TabMerge(ttk.Frame, WorkerMixin):
    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        WorkerMixin.__init__(self)
        pad = {"padx": 8, "pady": 4}
        self.columnconfigure(0, weight=1)

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.ov_var = tk.StringVar()
        self.threshold_var = tk.IntVar(value=92)
        self.country_var = tk.BooleanVar(value=True)
        self.delay_var = tk.IntVar(value=150)
        self.max_var = tk.IntVar(value=800)
        self.auto_var = tk.DoubleVar(value=0.85)
        self.topn_var = tk.IntVar(value=12)
        self.running = False

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
        self.run_btn = ttk.Button(r1, text="▶ 开始", command=self.run)
        self.run_btn.pack(side="right")

        r2 = ttk.Frame(pf); r2.pack(fill="x", padx=8, pady=4)
        ttk.Label(r2, text="请求间隔ms:").pack(side="left")
        ttk.Entry(r2, textvariable=self.delay_var, width=8).pack(side="left", padx=4)
        ttk.Label(r2, text="最多推断:").pack(side="left", padx=(12, 0))
        ttk.Entry(r2, textvariable=self.max_var, width=8).pack(side="left", padx=4)
        ttk.Label(r2, text="自动接受阈值:").pack(side="left", padx=(12, 0))
        ttk.Entry(r2, textvariable=self.auto_var, width=6).pack(side="left", padx=4)
        ttk.Label(r2, text="饼图TopN:").pack(side="left", padx=(12, 0))
        ttk.Entry(r2, textvariable=self.topn_var, width=6).pack(side="left", padx=4)

        self.pbar = ttk.Progressbar(self, mode="determinate")
        self.pbar.grid(row=row, column=0, sticky="ew", **pad); row += 1

        self.log = LogPanel(self, height=14)
        self.log.grid(row=row, column=0, sticky="nsew", **pad); row += 1
        self.rowconfigure(row - 1, weight=1)

        self._poll_worker(self)

    def _w_on_progress(self, msg, frac):
        self.pbar["value"] = max(0, min(100, int(frac * 100)))

    def _w_on_log(self, msg):
        self.log.log(msg)

    def _w_on_done(self, msg):
        self.pbar["value"] = 100
        self.run_btn.config(state="normal")
        self.running = False
        self.log.log(msg)
        messagebox.showinfo("完成", msg)

    def _w_on_error(self, msg):
        self.run_btn.config(state="normal")
        self.running = False
        self.log.log(f"❌ {msg}")
        messagebox.showerror("错误", msg)

    def run(self):
        if self.running:
            return
        inp, out = self.in_var.get(), self.out_var.get()
        if not inp or not out:
            messagebox.showerror("错误", "请选择输入和输出文件。")
            return
        self.running = True
        self.run_btn.config(state="disabled")
        self.pbar["value"] = 0
        self.log.clear()

        from config import MergeConfig
        from hebing import run_hebing
        cfg = MergeConfig(
            fuzzy_threshold=self.threshold_var.get(),
            enable_country_lookup=self.country_var.get(),
            request_delay_ms=self.delay_var.get(),
            max_lookup=self.max_var.get(),
            auto_accept_threshold=self.auto_var.get(),
            pie_topn=self.topn_var.get(),
        )

        def worker():
            try:
                run_hebing(inp, out, self.ov_var.get(), cfg, verbose=True)
                self._w_put("done", f"完成: {out}")
            except Exception as e:
                self._w_put("error", str(e))

        threading.Thread(target=worker, daemon=True).start()


class TabAdjectives(ttk.Frame, WorkerMixin):
    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        WorkerMixin.__init__(self)
        pad = {"padx": 8, "pady": 4}
        self.columnconfigure(0, weight=1)

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.tgt_var = tk.StringVar()
        self.split_var = tk.StringVar(value="blanklines")
        self.split_regex_var = tk.StringVar()
        self.win_var = tk.IntVar(value=8)
        self.phr_var = tk.IntVar(value=6)
        self.batch_var = tk.IntVar(value=64)
        self.maxch_var = tk.IntVar(value=200000)
        self.running = False

        row = 0
        FileRow(self, "TXT语料:", "open", [("Text", "*.txt"), ("All", "*.*")], self.in_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "导出Excel:", "save", [("Excel", "*.xlsx")], self.out_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1

        tf = ttk.Frame(self)
        tf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Label(tf, text="检索目标:", width=18, anchor="e").pack(side="left", padx=(0, 6))
        ttk.Entry(tf, textvariable=self.tgt_var).pack(side="left", fill="x", expand=True)
        ttk.Label(tf, text="(; 分隔)").pack(side="left", padx=(6, 0))

        pf = ttk.LabelFrame(self, text="参数")
        pf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        r1 = ttk.Frame(pf); r1.pack(fill="x", padx=8, pady=4)
        ttk.Radiobutton(r1, text="空行分段", variable=self.split_var, value="blanklines").pack(side="left")
        ttk.Radiobutton(r1, text="每行一篇", variable=self.split_var, value="lines").pack(side="left", padx=8)
        ttk.Radiobutton(r1, text="正则/等号线", variable=self.split_var, value="regex").pack(side="left", padx=8)
        ttk.Entry(r1, textvariable=self.split_regex_var, width=18).pack(side="left", padx=6)
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
        self.run_btn = ttk.Button(r2, text="▶ 开始", command=self.run)
        self.run_btn.pack(side="right")

        self.pbar = ttk.Progressbar(self, mode="determinate")
        self.pbar.grid(row=row, column=0, sticky="ew", **pad); row += 1

        self.log = LogPanel(self, height=14)
        self.log.grid(row=row, column=0, sticky="nsew", **pad); row += 1
        self.rowconfigure(row - 1, weight=1)

        self._poll_worker(self)

    def _w_on_progress(self, msg, frac):
        self.pbar["value"] = max(0, min(100, int(frac)))

    def _w_on_log(self, msg):
        self.log.log(msg)

    def _w_on_done(self, msg):
        self.run_btn.config(state="normal")
        self.running = False
        self.log.log(msg)
        messagebox.showinfo("完成", msg)

    def _w_on_error(self, msg):
        self.run_btn.config(state="normal")
        self.running = False
        self.log.log(f"❌ {msg}")
        messagebox.showerror("错误", msg)

    def run(self):
        if self.running:
            return
        inp, out, tgts = self.in_var.get(), self.out_var.get(), self.tgt_var.get()
        if not inp or not out or not tgts:
            messagebox.showerror("错误", "请填写所有必填项。")
            return
        self.running = True
        self.run_btn.config(state="disabled")
        self.pbar["value"] = 0
        self.log.clear()

        from config import TxtAnalysisConfig
        from txt_modifier_extractor_gui import process_txt, split_targets

        cfg = TxtAnalysisConfig(
            split_mode=self.split_var.get(),
            split_regex=self.split_regex_var.get(),
            window_tokens=self.win_var.get(),
            phrase_max_tokens=self.phr_var.get(),
            nlp_batch_size=self.batch_var.get(),
            max_doc_chars=self.maxch_var.get(),
            use_online_judge=False,
        )
        targets = split_targets(tgts)

        def worker():
            try:
                process_txt(
                    inp, out, targets, cfg,
                    progress_cb=lambda d, t: self._w_put("progress", "", (d / t) * 100),
                    log_cb=lambda m: self._w_put("log", m),
                )
                self._w_put("done", f"完成: {out}")
            except Exception as e:
                self._w_put("error", str(e))

        threading.Thread(target=worker, daemon=True).start()


class TabPOSTranslate(ttk.Frame, WorkerMixin):
    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        WorkerMixin.__init__(self)
        pad = {"padx": 8, "pady": 4}
        self.columnconfigure(0, weight=1)

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.col_var = tk.StringVar(value="Adjective")
        self.trans_var = tk.BooleanVar(value=True)
        self.df = None
        self.running = False

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
        ttk.Button(cf, text="读取列名", command=self.load_columns).pack(side="left", padx=12)
        self.run_btn = ttk.Button(cf, text="▶ 开始", command=self.run)
        self.run_btn.pack(side="right")

        self.pbar = ttk.Progressbar(self, mode="determinate")
        self.pbar.grid(row=row, column=0, sticky="ew", **pad); row += 1

        pf = ttk.Frame(self)
        pf.grid(row=row, column=0, sticky="ew", **pad); row += 1
        ttk.Label(pf, text="预览 (前20行):").pack(anchor="w")
        self.preview = tk.Text(pf, height=6, wrap="none")
        self.preview.pack(fill="both", expand=True)

        self.log = LogPanel(self, height=6)
        self.log.grid(row=row, column=0, sticky="nsew", **pad); row += 1
        self.rowconfigure(row - 1, weight=1)

        self._poll_worker(self)

    def load_columns(self):
        path = self.in_var.get()
        if not path:
            messagebox.showwarning("提示", "请先选择输入文件。")
            return
        try:
            if path.lower().endswith(".xlsx"):
                self.df = pd.read_excel(path)
            else:
                self.df = pd.read_csv(path, encoding="utf-8-sig")
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

    def _w_on_progress(self, msg, frac):
        self.pbar["value"] = max(0, min(100, int(frac)))

    def _w_on_log(self, msg):
        self.log.log(msg)

    def _w_on_done(self, msg):
        self.run_btn.config(state="normal")
        self.running = False
        self.pbar["value"] = 100
        self.log.log(msg)
        messagebox.showinfo("完成", msg)

    def _w_on_error(self, msg):
        self.run_btn.config(state="normal")
        self.running = False
        self.log.log(f"❌ {msg}")
        messagebox.showerror("错误", msg)

    def run(self):
        if self.running:
            return
        inp, out = self.in_var.get(), self.out_var.get()
        word_col = self.col_var.get()
        if not inp or not out or not word_col:
            messagebox.showerror("错误", "请填写所有必填项。")
            return
        if self.df is None:
            self.load_columns()
        if self.df is None:
            return

        self.running = True
        self.run_btn.config(state="disabled")
        self.pbar["value"] = 0
        self.log.clear()

        df = self.df.copy()
        do_trans = self.trans_var.get()

        def worker():
            try:
                from jiacixing import ensure_nltk_data, guess_pos, Translator
                ensure_nltk_data()
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

                if do_trans:
                    self._w_put("log", "并发翻译中…")
                    t = Translator(concurrency=5)
                    zh_list = t.translate_batch(["" if pd.isna(w) else str(w) for w in words])

                df["中文意思"] = zh_list
                self._w_put("progress", "", 100)

                if out.lower().endswith(".csv"):
                    df.to_csv(out, index=False, encoding="utf-8-sig")
                else:
                    df.to_excel(out, index=False)

                self.preview.delete("1.0", "end")
                self.preview.insert("end", df.head(20).to_string(index=False))
                self._w_put("done", f"完成: {out}")
            except Exception as e:
                self._w_put("error", str(e))

        threading.Thread(target=worker, daemon=True).start()


class TabKWIC(ttk.Frame):
    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        pad = {"padx": 8, "pady": 4}
        self.columnconfigure(0, weight=1)

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()

        row = 0
        FileRow(self, "KWIC文件:", "open", [("Text", "*.txt"), ("All", "*.*")], self.in_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "导出Excel:", "save", [("Excel", "*.xlsx")], self.out_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1

        ttk.Button(self, text="▶ 开始分析", command=self.run) \
            .grid(row=row, column=0, **pad); row += 1

        self.log = LogPanel(self, height=18)
        self.log.grid(row=row, column=0, sticky="nsew", **pad); row += 1
        self.rowconfigure(row - 1, weight=1)

    def run(self):
        inp, out = self.in_var.get(), self.out_var.get()
        if not inp or not out:
            messagebox.showerror("错误", "请选择输入和输出文件。")
            return
        self.log.clear()
        self.log.log("分析中…")

        def worker():
            try:
                from KWICtoecxl import analyze_kwic
                df = analyze_kwic(inp)
                df.to_excel(out, index=False)
                self.log.log(f"✅ 完成: {out}")
                self.log.log(f"形容词数: {len(df)}")
                messagebox.showinfo("完成", f"已导出: {out}")
            except Exception as e:
                self.log.log(f"❌ {e}")
                messagebox.showerror("错误", str(e))

        threading.Thread(target=worker, daemon=True).start()


class TabColumnMerge(ttk.Frame):
    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        pad = {"padx": 8, "pady": 4}

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
        ttk.Button(bf, text="读取列名", command=self.load_columns).pack(side="left")
        ttk.Button(bf, text="▶ 合并并导出", command=self.run).pack(side="left", padx=12)

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

        self.log = LogPanel(self, height=8)
        self.log.grid(row=row, column=0, sticky="ew", **pad); row += 1

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

    def run(self):
        inp, out = self.in_var.get(), self.out_var.get()
        if not inp or not out:
            messagebox.showerror("错误", "请选择输入和输出文件。")
            return
        if self.df is None:
            self.load_columns()
        if self.df is None:
            return

        key_cols = [c for c, v in self.key_vars.items() if v.get()]
        sum_cols = [c for c, v in self.sum_vars.items() if v.get()]
        if not key_cols:
            messagebox.showerror("错误", "请至少选择1个分组键列。")
            return

        overlap = set(key_cols) & set(sum_cols)
        if overlap:
            messagebox.showerror("错误", f"这些列同时被选为键列和求和列: {', '.join(overlap)}")
            return

        try:
            from shared.io_utils import write_table
            df = self.df.copy()
            other_cols = [c for c in df.columns if c not in key_cols and c not in sum_cols]
            agg = {c: "first" for c in other_cols}
            for c in sum_cols:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
                agg[c] = "sum"

            result = df.groupby(key_cols, as_index=False).agg(agg)
            result = result[key_cols + other_cols + sum_cols]
            write_table(result, out)
            self.log.log(f"✅ 完成: {out}")
            self.log.log(f"原始: {len(df)}行 → 合并后: {len(result)}行")
            messagebox.showinfo("完成", f"已导出: {out}\n{len(df)}→{len(result)} 行")
        except Exception as e:
            messagebox.showerror("错误", str(e))


class TabJSONtoExcel(ttk.Frame):
    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        pad = {"padx": 8, "pady": 4}
        self.columnconfigure(0, weight=1)

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()

        row = 0
        FileRow(self, "报告JSON:", "open", [("JSON", "*.json"), ("All", "*.*")], self.in_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1
        FileRow(self, "导出Excel:", "save", [("Excel", "*.xlsx"), ("CSV", "*.csv")], self.out_var) \
            .grid(row=row, column=0, sticky="ew", **pad); row += 1

        ttk.Button(self, text="▶ 转换", command=self.run) \
            .grid(row=row, column=0, **pad); row += 1

        self.log = LogPanel(self, height=18)
        self.log.grid(row=row, column=0, sticky="nsew", **pad); row += 1
        self.rowconfigure(row - 1, weight=1)

    def run(self):
        inp, out = self.in_var.get(), self.out_var.get()
        if not inp or not out:
            messagebox.showerror("错误", "请选择输入和输出文件。")
            return
        self.log.clear()
        try:
            with open(inp, "r", encoding="utf-8") as f:
                data = json.load(f)
            src = data.get("by_source_count", {})
            if not isinstance(src, dict):
                raise ValueError("未找到 by_source_count 字段")
            df = pd.DataFrame([{"Source": k, "Count": v} for k, v in src.items()]).sort_values("Count", ascending=False)
            if out.lower().endswith(".xlsx"):
                df.to_excel(out, index=False)
            else:
                df.to_csv(out, index=False, encoding="utf-8-sig")
            self.log.log(f"✅ 完成: {out}")
            self.log.log(f"机构数: {len(df)}, 总篇数: {df['Count'].sum()}")
            messagebox.showinfo("完成", f"已导出: {out}\n{len(df)} 个机构")
        except Exception as e:
            self.log.log(f"❌ {e}")
            messagebox.showerror("错误", str(e))


class IntegratedApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("新闻文本分析集成平台")
        self.geometry("1050x720")
        self.minsize(900, 600)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=6)

        self.tab_pipeline = TabPipeline(self.notebook)
        self.tab_merge = TabMerge(self.notebook)
        self.tab_adj = TabAdjectives(self.notebook)
        self.tab_pos = TabPOSTranslate(self.notebook)
        self.tab_kwic = TabKWIC(self.notebook)
        self.tab_colmerge = TabColumnMerge(self.notebook)
        self.tab_json2xlsx = TabJSONtoExcel(self.notebook)

        self.notebook.add(self.tab_pipeline, text=" 流水线 ")
        self.notebook.add(self.tab_merge, text=" 机构合并+国别 ")
        self.notebook.add(self.tab_adj, text=" 修饰形容词分析 ")
        self.notebook.add(self.tab_pos, text=" 词性+翻译 ")
        self.notebook.add(self.tab_kwic, text=" KWIC分析 ")
        self.notebook.add(self.tab_colmerge, text=" 自选列合并 ")
        self.notebook.add(self.tab_json2xlsx, text=" JSON→Excel ")


if __name__ == "__main__":
    IntegratedApp().mainloop()
