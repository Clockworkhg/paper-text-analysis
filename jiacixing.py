import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import time
import concurrent.futures
import threading
import queue

import pandas as pd
import requests

import nltk
from nltk.corpus import wordnet as wn

from shared.normalization import normalize_word


def ensure_nltk_data():
    resources = [
        ("corpora/wordnet", "wordnet"),
        ("corpora/omw-1.4", "omw-1.4"),
        ("taggers/averaged_perceptron_tagger", "averaged_perceptron_tagger"),
        ("tokenizers/punkt", "punkt"),
    ]
    for path, name in resources:
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(name, quiet=True)


def guess_pos(word: str) -> str:
    word = normalize_word(word)
    if not word:
        return ""

    synsets = wn.synsets(word)
    if synsets:
        p = synsets[0].pos()
        mapping = {"n": "NOUN", "v": "VERB", "a": "ADJ", "s": "ADJ", "r": "ADV"}
        return mapping.get(p, p.upper())

    try:
        from nltk import pos_tag, word_tokenize
        sent = f"I see {word} today."
        tokens = word_tokenize(sent)
        tags = pos_tag(tokens)
        for tok, tag in tags:
            if tok.lower() == word.lower():
                if tag.startswith("NN"):
                    return "NOUN"
                if tag.startswith("VB"):
                    return "VERB"
                if tag.startswith("JJ"):
                    return "ADJ"
                if tag.startswith("RB"):
                    return "ADV"
                return tag
    except Exception as e:
        import sys
        print(f"[guess_pos] fallback failed for '{word}': {e}", file=sys.stderr)

    return "UNKNOWN"


class Translator:
    def __init__(self, min_interval=0.6, timeout=6, retries=2, concurrency=5):
        self.cache = {}
        self.last_call = 0.0
        self.min_interval = min_interval
        self.timeout = timeout
        self.retries = retries
        self.concurrency = concurrency
        self.session = requests.Session()
        self._lock = threading.Lock()

    def translate_to_zh(self, text: str) -> str:
        text = normalize_word(text)
        if not text:
            return ""
        if text in self.cache:
            return self.cache[text]

        now = time.time()
        wait = self.min_interval - (now - self.last_call)
        if wait > 0:
            time.sleep(wait)

        zh = ""
        url = "https://api.mymemory.translated.net/get"
        params = {"q": text, "langpair": "en|zh-CN"}

        for _ in range(self.retries + 1):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                zh = (data.get("responseData") or {}).get("translatedText") or ""
                zh = normalize_word(zh)
                break
            except Exception:
                zh = ""
                time.sleep(0.3)

        self.last_call = time.time()
        self.cache[text] = zh
        return zh

    def _translate_single(self, text: str) -> str:
        text = normalize_word(text)
        if not text:
            return ""
        if text in self.cache:
            return self.cache[text]

        zh = ""
        url = "https://api.mymemory.translated.net/get"
        params = {"q": text, "langpair": "en|zh-CN"}

        for _ in range(self.retries + 1):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                zh = (data.get("responseData") or {}).get("translatedText") or ""
                zh = normalize_word(zh)
                break
            except Exception:
                zh = ""
                time.sleep(0.1)

        with self._lock:
            self.cache[text] = zh
        return zh

    def translate_batch(self, texts: list) -> list:
        uncached = [(i, t) for i, t in enumerate(texts) if normalize_word(t) and normalize_word(t) not in self.cache]
        results = [self.cache.get(normalize_word(t), "") for t in texts]

        if not uncached:
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {executor.submit(self._translate_single, t): idx for idx, t in uncached}
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception:
                    results[idx] = ""

        return results


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("词性 + 中文意思（插入到 NormRange 后，不卡 UI）")
        self.geometry("860x480")

        self.df = None
        self.file_path = None
        self.translator = Translator()

        self.worker_thread = None
        self.msg_queue = queue.Queue()
        self.stop_flag = threading.Event()

        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self):
        pad = 10

        frm_top = ttk.Frame(self)
        frm_top.pack(fill="x", padx=pad, pady=(pad, 6))
        self.lbl_file = ttk.Label(frm_top, text="未选择文件")
        self.lbl_file.pack(side="left", fill="x", expand=True)
        ttk.Button(frm_top, text="选择导入文件", command=self.load_file).pack(side="right", padx=(6, 0))

        frm_mid = ttk.Frame(self)
        frm_mid.pack(fill="x", padx=pad, pady=6)

        ttk.Label(frm_mid, text="词语所在列：").pack(side="left")
        self.col_var = tk.StringVar()
        self.col_combo = ttk.Combobox(frm_mid, textvariable=self.col_var, state="readonly", width=35, values=[])
        self.col_combo.pack(side="left", padx=(6, 12))

        self.use_translate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm_mid, text="生成中文意思（联网；慢/失败会跳过）", variable=self.use_translate_var).pack(side="left")

        frm_btn = ttk.Frame(self)
        frm_btn.pack(fill="x", padx=pad, pady=6)

        self.btn_start = ttk.Button(frm_btn, text="开始处理并导出", command=self.process_and_export)
        self.btn_start.pack(side="right")

        self.btn_preview = ttk.Button(frm_btn, text="预览前 20 行", command=self.preview)
        self.btn_preview.pack(side="right", padx=(0, 8))

        self.btn_stop = ttk.Button(frm_btn, text="停止", command=self.request_stop, state="disabled")
        self.btn_stop.pack(side="right", padx=(0, 8))

        frm_prog = ttk.Frame(self)
        frm_prog.pack(fill="x", padx=pad, pady=6)
        self.prog = ttk.Progressbar(frm_prog, length=420, mode="determinate")
        self.prog.pack(side="left")
        self.status = ttk.Label(frm_prog, text="就绪")
        self.status.pack(side="left", padx=(10, 0))

        frm_prev = ttk.Frame(self)
        frm_prev.pack(fill="both", expand=True, padx=pad, pady=(6, pad))
        self.txt = tk.Text(frm_prev, wrap="none")
        self.txt.pack(fill="both", expand=True)

    def set_status(self, s: str):
        self.status.config(text=s)
        self.update_idletasks()

    def load_file(self):
        path = filedialog.askopenfilename(
            title="选择 CSV 或 XLSX 文件",
            filetypes=[("Excel Files", "*.xlsx"), ("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            if path.lower().endswith(".xlsx"):
                df = pd.read_excel(path)
            else:
                try:
                    df = pd.read_csv(path, encoding="utf-8")
                except Exception:
                    df = pd.read_csv(path, encoding="gbk")

            if df.empty:
                messagebox.showerror("错误", "文件读取成功，但表格为空。")
                return

            self.df = df
            self.file_path = path
            self.lbl_file.config(text=f"已选择：{os.path.basename(path)}   （共 {len(df)} 行，{len(df.columns)} 列）")

            cols = list(df.columns)
            self.col_combo["values"] = cols
            self.col_var.set("Type" if "Type" in cols else cols[0])

            self.set_status("文件已载入")
            self.txt.delete("1.0", "end")
            self.txt.insert("end", '点击"预览前 20 行"查看内容。\n')
        except Exception as e:
            messagebox.showerror("读取失败", f"无法读取该文件：\n{e}")

    def preview(self):
        if self.df is None:
            messagebox.showinfo("提示", "请先选择导入文件。")
            return
        show = self.df.head(20)
        self.txt.delete("1.0", "end")
        self.txt.insert("end", show.to_string(index=False))

    def request_stop(self):
        self.stop_flag.set()
        self.set_status("正在停止…（会在本条处理结束后停止）")

    def process_and_export(self):
        if self.df is None:
            messagebox.showinfo("提示", "请先选择导入文件。")
            return

        word_col = self.col_var.get()
        if not word_col or word_col not in self.df.columns:
            messagebox.showerror("错误", '请选择正确的"词语所在列"。')
            return

        out_path = filedialog.asksaveasfilename(
            title="选择导出位置",
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx"), ("CSV Files", "*.csv")]
        )
        if not out_path:
            return

        self.btn_start.config(state="disabled")
        self.btn_preview.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.stop_flag.clear()

        args = (self.df.copy(deep=True), word_col, out_path, bool(self.use_translate_var.get()))
        self.worker_thread = threading.Thread(target=self._worker, args=args, daemon=True)
        self.worker_thread.start()
        self.set_status("处理中…（后台运行，不会卡死）")

    def _worker(self, df: pd.DataFrame, word_col: str, out_path: str, do_translate: bool):
        try:
            ensure_nltk_data()
        except Exception as e:
            self.msg_queue.put(("warn", f"NLTK 资源下载/加载可能失败：{e}"))

        for c in ["POS", "中文意思"]:
            if c in df.columns:
                df.drop(columns=[c], inplace=True)

        words = df[word_col].tolist()
        n = len(words)
        self.msg_queue.put(("init", n))

        pos_list = []
        BATCH_SIZE = 50

        if do_translate:
            normalized = [normalize_word(w) for w in words]
            pos_list = [guess_pos(ww) for ww in normalized]

            cache_zh = self.translator.cache
            uncached_idxs = [i for i, nw in enumerate(normalized) if nw and nw not in cache_zh]
            zh_list = [cache_zh.get(nw, "") for nw in normalized]

            for batch_start in range(0, len(uncached_idxs), BATCH_SIZE):
                if self.stop_flag.is_set():
                    self.msg_queue.put(("stopped", None))
                    return

                batch_idxs = uncached_idxs[batch_start:batch_start + BATCH_SIZE]
                batch_texts = [(i, normalized[i]) for i in batch_idxs]
                results = self.translator.translate_batch([t for _, t in batch_texts])
                for (orig_idx, _), zh in zip(batch_texts, results):
                    zh_list[orig_idx] = zh

                done = batch_start + len(batch_idxs)
                total_uncached = len(uncached_idxs)
                self.msg_queue.put(("progress", (done, total_uncached)))
        else:
            for i, w in enumerate(words, start=1):
                if self.stop_flag.is_set():
                    self.msg_queue.put(("stopped", None))
                    return
                pos_list.append(guess_pos(normalize_word(w)))
                if i % 5 == 0 or i == n:
                    self.msg_queue.put(("progress", (i, n)))
            zh_list = [""] * n

        if "NormRange" in df.columns:
            insert_at = list(df.columns).index("NormRange") + 1
        else:
            insert_at = len(df.columns)

        df.insert(insert_at, "POS", pos_list)
        df.insert(insert_at + 1, "中文意思", zh_list)

        try:
            if out_path.lower().endswith(".csv"):
                df.to_csv(out_path, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(out_path, index=False)
        except Exception as e:
            self.msg_queue.put(("error", f"导出失败：{e}"))
            return

        self.msg_queue.put(("done", (out_path, df.head(20))))

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind, payload = msg

                if kind == "init":
                    n = payload
                    self.prog["maximum"] = max(n, 1)
                    self.prog["value"] = 0
                    self.set_status(f"开始处理：共 {n} 行")

                elif kind == "progress":
                    i, n = payload
                    self.prog["value"] = i
                    self.set_status(f"处理中… {i}/{n}")

                elif kind == "warn":
                    messagebox.showwarning("警告", payload)

                elif kind == "error":
                    messagebox.showerror("错误", payload)
                    self._reset_buttons()
                    self.set_status("失败")
                    return

                elif kind == "stopped":
                    self._reset_buttons()
                    self.set_status("已停止")
                    messagebox.showinfo("已停止", "已按你的要求停止处理。")
                    return

                elif kind == "done":
                    out_path, head20 = payload
                    self._reset_buttons()
                    self.set_status("完成 ✅")
                    messagebox.showinfo("完成", f"处理完成并已导出：\n{out_path}")
                    self.txt.delete("1.0", "end")
                    self.txt.insert("end", head20.to_string(index=False))
                    return

        except queue.Empty:
            pass

        self.after(120, self._poll_queue)

    def _reset_buttons(self):
        self.btn_start.config(state="normal")
        self.btn_preview.config(state="normal")
        self.btn_stop.config(state="disabled")


if __name__ == "__main__":
    App().mainloop()
