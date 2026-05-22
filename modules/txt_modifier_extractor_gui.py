# -*- coding: utf-8 -*-
"""Legacy Tkinter GUI wrapper for TXT modifier extraction.

Core analysis functions live in ``modules.txt_modifier_extractor``. This module
keeps the historical import path and the standalone GUI class for compatibility.
"""

import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from config import TxtAnalysisConfig
from modules.txt_modifier_extractor import (
    Config,
    _chi2_p_value,
    _is_valid_modifier,
    _ll_significance_stars,
    chunk_long_docs,
    clean_phrase,
    context_text,
    extract_for_hit,
    find_targets_in_doc,
    iter_collocates,
    load_spacy_model,
    log_likelihood_2x2,
    normalize_target,
    online_judge_pairs,
    parse_doc_metadata,
    polarity_candidate,
    process_txt,
    split_corpus,
    split_targets,
    token_count_approx,
)

# =========================
# GUI
# =========================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TXT corpus modifier analysis")
        self.geometry("900x640")

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.targets_text = tk.StringVar()

        self.split_mode = tk.StringVar(value="regex")
        # 鉁?榛樿缁欎綘鈥滅瓑鍙峰垎闅旂嚎妯″紡鈥?
        # 鐢ㄦ硶锛氭妸杩欓噷淇濇寔涓?"====LINE====" 鍗冲彲鎸?\n=+\n 鍒囧垎
        self.split_regex = tk.StringVar(value="====LINE====")

        self.window_tokens = tk.IntVar(value=8)
        self.phrase_max_tokens = tk.IntVar(value=6)
        self.spacy_batch = tk.IntVar(value=64)
        self.max_doc_chars = tk.IntVar(value=200000)

        self.use_online = tk.BooleanVar(value=False)
        self.api_key = tk.StringVar()
        self.model_name = tk.StringVar(value="gpt-4o-mini")

        self.progress_val = tk.DoubleVar(value=0)
        self.msg_queue = queue.Queue()
        self.worker_thread = None

        self._build_ui()
        self.after(120, self._poll_queue)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=12, pady=12)

        # input
        r1 = ttk.Frame(root); r1.pack(fill="x", **pad)
        ttk.Label(r1, text="Input TXT corpus:").pack(side="left")
        ttk.Entry(r1, textvariable=self.input_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(r1, text="Choose...", command=self.pick_input).pack(side="left")

        # output
        r2 = ttk.Frame(root); r2.pack(fill="x", **pad)
        ttk.Label(r2, text="Output Excel (.xlsx):").pack(side="left")
        ttk.Entry(r2, textvariable=self.output_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(r2, text="Choose...", command=self.pick_output).pack(side="left")

        # targets
        r3 = ttk.Frame(root); r3.pack(fill="x", **pad)
        ttk.Label(r3, text="Targets (separate multiple terms with ;):").pack(side="left")
        ttk.Entry(r3, textvariable=self.targets_text).pack(side="left", fill="x", expand=True, padx=8)

        # split mode
        box_split = ttk.LabelFrame(root, text="Document splitting")
        box_split.pack(fill="x", **pad)

        rs = ttk.Frame(box_split); rs.pack(fill="x", padx=10, pady=6)
        ttk.Radiobutton(rs, text="Blank lines", variable=self.split_mode, value="blanklines").pack(side="left")
        ttk.Radiobutton(rs, text="One line per doc", variable=self.split_mode, value="lines").pack(side="left", padx=14)
        ttk.Radiobutton(rs, text="Regex/separator", variable=self.split_mode, value="regex").pack(side="left")

        rs2 = ttk.Frame(box_split); rs2.pack(fill="x", padx=10, pady=6)
        ttk.Label(rs2, text="Separator/regex:").pack(side="left")
        ttk.Entry(rs2, textvariable=self.split_regex).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(rs2, text="Use ====LINE==== for lines made of equals signs.").pack(side="left")

        # params
        box_param = ttk.LabelFrame(root, text="Parameters")
        box_param.pack(fill="x", **pad)
        rp = ttk.Frame(box_param); rp.pack(fill="x", padx=10, pady=6)

        ttk.Label(rp, text="Window tokens:").pack(side="left")
        ttk.Spinbox(rp, from_=3, to=30, textvariable=self.window_tokens, width=6).pack(side="left", padx=8)

        ttk.Label(rp, text="Max phrase tokens:").pack(side="left", padx=(16, 0))
        ttk.Spinbox(rp, from_=2, to=15, textvariable=self.phrase_max_tokens, width=6).pack(side="left", padx=8)

        ttk.Label(rp, text="spaCy batch:").pack(side="left", padx=(16, 0))
        ttk.Spinbox(rp, from_=8, to=256, textvariable=self.spacy_batch, width=6).pack(side="left", padx=8)

        ttk.Label(rp, text="Max chars per doc:").pack(side="left", padx=(16, 0))
        ttk.Spinbox(rp, from_=50000, to=1000000, textvariable=self.max_doc_chars, width=8).pack(side="left", padx=8)

        # online
        box_online = ttk.LabelFrame(root, text="Optional online judging")
        box_online.pack(fill="x", **pad)

        ro = ttk.Frame(box_online); ro.pack(fill="x", padx=10, pady=6)
        ttk.Checkbutton(ro, text="Use online model to filter modifier relations", variable=self.use_online).pack(side="left")

        ro2 = ttk.Frame(box_online); ro2.pack(fill="x", padx=10, pady=6)
        ttk.Label(ro2, text="OpenAI API Key:").pack(side="left")
        ttk.Entry(ro2, textvariable=self.api_key, show="*", width=48).pack(side="left", padx=8)
        ttk.Label(ro2, text="Model:").pack(side="left", padx=(10, 0))
        ttk.Entry(ro2, textvariable=self.model_name, width=14).pack(side="left")

        # progress & buttons
        r6 = ttk.Frame(root); r6.pack(fill="x", **pad)
        ttk.Progressbar(r6, variable=self.progress_val, maximum=100).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Button(r6, text="Start", command=self.start).pack(side="left")
        ttk.Button(r6, text="Exit", command=self.destroy).pack(side="left", padx=(8, 0))

        # log
        box_log = ttk.LabelFrame(root, text="Run log")
        box_log.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(box_log, height=14, wrap="word")
        self.log.pack(fill="both", expand=True, padx=10, pady=8)

        self._log("Tip: ====LINE==== splits on separator lines made of equals signs.")

    def _log(self, s: str):
        self.log.insert("end", s + "\n")
        self.log.see("end")

    def pick_input(self):
        path = filedialog.askopenfilename(
            title="Choose TXT corpus",
            filetypes=[("Text", "*.txt"), ("All", "*.*")]
        )
        if path:
            self.input_path.set(path)

    def pick_output(self):
        path = filedialog.asksaveasfilename(
            title="Choose output location",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if path:
            self.output_path.set(path)

    def start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Running", "A run is already in progress.")
            return

        in_path = self.input_path.get().strip()
        out_path = self.output_path.get().strip()
        targets_raw = self.targets_text.get().strip()

        if not in_path:
            messagebox.showerror("Error", "Choose an input TXT file."); return
        if not out_path:
            messagebox.showerror("Error", "Choose an output path."); return
        if not targets_raw:
            messagebox.showerror("Error", "Enter at least one target term."); return

        targets = split_targets(targets_raw)
        if not targets:
            messagebox.showerror("Error", "No target terms parsed. Use ; as the separator."); return

        cfg = Config(
            window_tokens=int(self.window_tokens.get()),
            phrase_max_tokens=int(self.phrase_max_tokens.get()),
            split_mode=self.split_mode.get(),
            split_regex=self.split_regex.get(),
            nlp_batch_size=int(self.spacy_batch.get()),
            max_doc_chars=int(self.max_doc_chars.get()),
            use_online_judge=bool(self.use_online.get()),
            openai_api_key=self.api_key.get().strip(),
            openai_model=self.model_name.get().strip() or "gpt-4o-mini",
        )

        if cfg.use_online_judge and not cfg.openai_api_key:
            if not messagebox.askyesno("Confirm", "Online judging is enabled without an API key. Continue with local analysis?"):
                return
            cfg.use_online_judge = False

        self.progress_val.set(0)
        self._log("=" * 60)
        self._log("Starting...")

        def progress_cb(done, total):
            pct = (done / total) * 100 if total else 0
            self.msg_queue.put(("progress", pct))

        def log_cb(msg):
            self.msg_queue.put(("log", msg))

        def worker():
            try:
                process_txt(in_path, out_path, targets, cfg, progress_cb=progress_cb, log_cb=log_cb)
                self.msg_queue.put(("done", "done"))
            except Exception as e:
                self.msg_queue.put(("error", str(e)))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _poll_queue(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    self.progress_val.set(item[1])
                elif kind == "log":
                    self._log(item[1])
                elif kind == "done":
                    self.progress_val.set(100)
                    self._log("All done.")
                    messagebox.showinfo("Done", "Processing complete; Excel exported.")
                elif kind == "error":
                    self._log("Error: " + item[1])
                    messagebox.showerror("Error", item[1])
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)


if __name__ == "__main__":
    App().mainloop()
