# -*- coding: utf-8 -*-
"""
TXT语料：形容词/修饰语检索统计工具（GUI）

功能：
1) 可视化窗口：选择导入TXT、导出Excel、输入多个目标（支持 ; 和 ； 分隔）
2) 抽取针对目标的形容词（频次/篇次/规范化频次/规范化篇次）与修饰性短语（频次/篇次）
3) 支持大语料：按分隔线/空行/每行切分为“篇”，避免spaCy超长文本报错
4) 可选联网推理过滤（OpenAI API）判断修饰关系（更准，需API Key）

依赖：
pip install spacy pandas openpyxl
python -m spacy download en_core_web_sm
(可选) pip install openai
"""

import os
import re
import threading
import queue
from typing import List, Tuple, Dict, Set

import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from config import TxtAnalysisConfig

from shared.normalization import normalize_word

try:
    import spacy
except ImportError:
    spacy = None


# =========================
# Helpers
# =========================

def normalize_target(s: str) -> str:
    return normalize_word(s)

def split_targets(s: str) -> List[str]:
    # 同时支持英文 ; 和中文 ；
    s = s.replace("；", ";")
    parts = [normalize_target(x) for x in s.split(";")]
    return [p for p in parts if p]

def clean_phrase(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" ,.;:!?()[]{}\"'")
    return s

def token_count_approx(text: str) -> int:
    if not isinstance(text, str):
        text = str(text)
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+|[^\s]", text)
    return len(words)

def load_spacy_model():
    if spacy is None:
        raise RuntimeError("未安装 spacy。请先 pip install spacy 并下载模型。")
    try:
        nlp = spacy.load("en_core_web_sm")
    except Exception as e:
        raise RuntimeError("无法加载 en_core_web_sm。请先运行：python -m spacy download en_core_web_sm") from e

    # 保险：允许更长输入（但我们仍会切分/分块，避免内存暴涨）
    nlp.max_length = 10_000_000
    return nlp


# =========================
# TXT splitting
# =========================

def split_corpus(text: str, mode: str, custom_pattern: str = "") -> List[str]:
    """
    mode:
      - "blanklines": 空行分段（默认）
      - "lines": 每行一篇
      - "regex": 正则分隔（re.split，默认开启 MULTILINE）
        特殊：若 custom_pattern == "====LINE===="
              则按“整行等号分隔线”切分：\\n=+\\n
    """
    if mode == "lines":
        return [p.strip() for p in text.splitlines() if p.strip()]

    if mode == "regex":
        pat = (custom_pattern or "").strip()

        # ✅ 你这种：用一整行 "======" 分隔
        if pat == "====LINE====":
            chunks = [c.strip() for c in re.split(r"\n=+\n", text) if c.strip()]
            return chunks

        # 普通正则：开启 MULTILINE，^ $ 才能按行匹配
        if pat:
            chunks = [c.strip() for c in re.split(pat, text, flags=re.M) if c.strip()]
            return chunks

        # pat 为空就回退空行
        mode = "blanklines"

    # 默认空行分段
    return [c.strip() for c in re.split(r"\n\s*\n+", text) if c.strip()]


def chunk_long_docs(docs: List[str], max_chars: int = 200000) -> List[str]:
    """
    保险：如果某一篇/段落特别长，进一步按句号/换行粗切成多个块，
    防止spaCy parser内存暴涨。
    """
    new_docs = []
    for d in docs:
        if len(d) <= max_chars:
            new_docs.append(d)
            continue

        parts = re.split(r"(?<=[.!?])\s+|\n+", d)
        buf = ""
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if len(buf) + len(p) + 1 <= max_chars:
                buf = (buf + " " + p) if buf else p
            else:
                if buf:
                    new_docs.append(buf)
                buf = p
        if buf:
            new_docs.append(buf)
    return new_docs


# =========================
# Extraction core
# =========================

Config = TxtAnalysisConfig  # alias for backward compatibility


def find_targets_in_doc(doc, targets: List[str]) -> List[Tuple[int, int, str]]:
    text_low = doc.text.lower()
    hits = []
    for t in targets:
        t_low = t.lower()
        for m in re.finditer(re.escape(t_low), text_low):
            span = doc.char_span(m.start(), m.end(), alignment_mode="expand")
            if span is None:
                continue
            hits.append((span.start, span.end, t))
    return hits


def extract_for_hit(doc, hit_span: Tuple[int, int, str], cfg: Config) -> Tuple[Set[str], Set[str]]:
    start_i, end_i, _ = hit_span
    target_tokens = doc[start_i:end_i]
    head = target_tokens.root

    adjs: Set[str] = set()
    phrases: Set[str] = set()

    # 1) amod：形容词直接修饰
    for child in head.lefts:
        if child.dep_ == "amod" and child.pos_ == "ADJ":
            adjs.add(child.lemma_.lower())
            phrase_tokens = []
            for c2 in child.lefts:
                if c2.dep_ == "advmod" and c2.pos_ == "ADV":
                    phrase_tokens.append(c2)
            phrase_tokens.append(child)
            ph = clean_phrase(" ".join([t.text for t in phrase_tokens])).lower()
            if len(ph.split()) >= 2:
                phrases.add(ph)

    # 2) 系表：target is ADJ
    if head.dep_ in ("nsubj", "nsubjpass"):
        verb = head.head
        for child in verb.rights:
            if child.dep_ == "acomp" and child.pos_ == "ADJ":
                adjs.add(child.lemma_.lower())
                phrase_tokens = []
                for c2 in child.lefts:
                    if c2.dep_ == "advmod" and c2.pos_ == "ADV":
                        phrase_tokens.append(c2)
                phrase_tokens.append(child)
                ph = clean_phrase(" ".join([t.text for t in phrase_tokens])).lower()
                if len(ph.split()) >= 2:
                    phrases.add(ph)

    # 3) 窗口补充
    left = max(0, start_i - cfg.window_tokens)
    right = min(len(doc), end_i + cfg.window_tokens)
    window = doc[left:right]
    for tok in window:
        if tok.pos_ == "ADJ" and not (start_i <= tok.i < end_i):
            adjs.add(tok.lemma_.lower())

    # 4) 目标前 ADV/ADJ 连续短语
    pre_left = max(0, start_i - cfg.phrase_max_tokens)
    pre_tokens = list(doc[pre_left:start_i])
    buf = []
    for t in reversed(pre_tokens):
        if t.is_punct or t.text in (",", ";", ":", "—", "-", "(", ")"):
            break
        if t.pos_ in ("ADV", "ADJ"):
            buf.append(t)
        else:
            break
    if buf:
        ph = clean_phrase(" ".join([t.text for t in reversed(buf)])).lower()
        if len(ph.split()) >= 2:
            phrases.add(ph)

    return adjs, phrases


# =========================
# Optional online judge
# =========================

def online_judge_pairs(pairs: List[Tuple[str, str, str]], cfg: Config) -> List[bool]:
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("你启用了联网推理，但未安装 openai。请 pip install openai") from e
    if not cfg.openai_api_key.strip():
        raise RuntimeError("你启用了联网推理，但未填写 OpenAI API Key。")

    client = OpenAI(api_key=cfg.openai_api_key.strip())
    results: List[bool] = []

    import json
    for i in range(0, len(pairs), cfg.online_batch_size):
        batch = pairs[i:i + cfg.online_batch_size]
        lines = []
        for idx, (sent, target, cand) in enumerate(batch, start=1):
            lines.append(f"{idx}. sentence: {sent}\n   target: {target}\n   modifier: {cand}")

        system = (
            "You are a precise linguistics assistant. "
            "Decide whether the modifier truly describes/modifies the target in the sentence. "
            "Return only a JSON array of booleans in order, no extra text."
        )
        user = "\n\n".join(lines)

        resp = client.chat.completions.create(
            model=cfg.openai_model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0
        )
        content = resp.choices[0].message.content.strip()
        try:
            arr = json.loads(content)
            if not isinstance(arr, list) or len(arr) != len(batch):
                raise ValueError("Bad JSON")
            results.extend([bool(x) for x in arr])
        except Exception:
            # 解析失败：保守不过滤
            results.extend([True] * len(batch))

    return results


# =========================
# Main processing for TXT
# =========================

def process_txt(
    input_path: str,
    output_path: str,
    targets: List[str],
    cfg: Config,
    progress_cb=None,
    log_cb=None,
):
    if not os.path.exists(input_path):
        raise FileNotFoundError("输入文件不存在")

    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
        corpus = f.read()

    docs = split_corpus(corpus, cfg.split_mode, cfg.split_regex)
    if not docs:
        raise ValueError("未能从文本中切分出任何文档/段落。请换切分方式。")

    # 保险：超长文档分块
    docs = chunk_long_docs(docs, max_chars=cfg.max_doc_chars)

    total_docs = len(docs)
    if log_cb:
        log_cb(f"切分方式: {cfg.split_mode}")
        log_cb(f"分隔正则/模式: {cfg.split_regex}")
        log_cb(f"切分得到文档/段落数: {total_docs}")
        log_cb(f"目标: {targets}")

    nlp = load_spacy_model()

    adj_freq: Dict[str, Dict[str, int]] = {t: {} for t in targets}
    adj_docs: Dict[str, Dict[str, Set[int]]] = {t: {} for t in targets}
    phrase_freq: Dict[str, Dict[str, int]] = {t: {} for t in targets}
    phrase_docs: Dict[str, Dict[str, Set[int]]] = {t: {} for t in targets}

    total_tokens_corpus = 0

    online_pairs: List[Tuple[str, str, str]] = []
    online_meta: List[Tuple[str, str, str, int]] = []  # kind, target, cand, docid

    # spacy.pipe 提速
    for i, doc in enumerate(nlp.pipe(docs, batch_size=cfg.nlp_batch_size), start=0):
        if progress_cb:
            progress_cb(i + 1, total_docs)

        text = doc.text
        total_tokens_corpus += token_count_approx(text)

        hits = find_targets_in_doc(doc, targets)
        if not hits:
            continue

        docid = i
        for hit in hits:
            _, _, t = hit
            adjs, phrases = extract_for_hit(doc, hit, cfg)

            for a in adjs:
                if not a:
                    continue
                adj_freq[t][a] = adj_freq[t].get(a, 0) + 1
                adj_docs[t].setdefault(a, set()).add(docid)

                if cfg.use_online_judge:
                    online_pairs.append((text, t, a))
                    online_meta.append(("adj", t, a, docid))

            for p in phrases:
                p = clean_phrase(p).lower()
                if not p or len(p.split()) < 2:
                    continue
                phrase_freq[t][p] = phrase_freq[t].get(p, 0) + 1
                phrase_docs[t].setdefault(p, set()).add(docid)

                if cfg.use_online_judge:
                    online_pairs.append((text, t, p))
                    online_meta.append(("phrase", t, p, docid))

    # 联网过滤
    if cfg.use_online_judge and online_pairs:
        if log_cb:
            log_cb(f"联网推理过滤候选中… 共 {len(online_pairs)} 条（会产生调用费用）")
        keep = online_judge_pairs(online_pairs, cfg)

        remove_set: Dict[str, Dict[str, int]] = {t: {} for t in targets}

        for flag, (kind, t, cand, docid) in zip(keep, online_meta):
            if flag:
                continue
            if kind == "adj":
                remove_set[t][cand] = remove_set[t].get(cand, 0) + 1
                if cand in adj_docs[t] and docid in adj_docs[t][cand]:
                    adj_docs[t][cand].discard(docid)
                    if not adj_docs[t][cand]:
                        del adj_docs[t][cand]
            else:
                remove_set[t][cand] = remove_set[t].get(cand, 0) + 1
                if cand in phrase_docs[t] and docid in phrase_docs[t][cand]:
                    phrase_docs[t][cand].discard(docid)
                    if not phrase_docs[t][cand]:
                        del phrase_docs[t][cand]

        for t in targets:
            for cand, delta in remove_set[t].items():
                if cand in adj_freq[t]:
                    adj_freq[t][cand] = max(0, adj_freq[t][cand] - delta)
                    if adj_freq[t][cand] == 0:
                        del adj_freq[t][cand]
                if cand in phrase_freq[t]:
                    phrase_freq[t][cand] = max(0, phrase_freq[t][cand] - delta)
                    if phrase_freq[t][cand] == 0:
                        del phrase_freq[t][cand]

    # 输出表
    adj_rows = []
    for t in targets:
        for adj, f in sorted(adj_freq[t].items(), key=lambda x: (-x[1], x[0])):
            dfreq = len(adj_docs[t].get(adj, set()))
            norm_f = (f / total_tokens_corpus * cfg.norm_freq_per) if total_tokens_corpus else 0
            norm_df = (dfreq / total_docs * cfg.norm_doc_per) if total_docs else 0
            adj_rows.append({
                "Target": t,
                "Adjective": adj,
                "Frequency": f,
                "Doc_Frequency": dfreq,
                f"Norm_Freq_per_{cfg.norm_freq_per}_words": norm_f,
                f"Norm_DocFreq_per_{cfg.norm_doc_per}_docs": norm_df,
            })

    phrase_rows = []
    for t in targets:
        for ph, f in sorted(phrase_freq[t].items(), key=lambda x: (-x[1], x[0])):
            dfreq = len(phrase_docs[t].get(ph, set()))
            phrase_rows.append({
                "Target": t,
                "Modifier_Phrase": ph,
                "Frequency": f,
                "Doc_Frequency": dfreq,
            })

    df_adj = pd.DataFrame(adj_rows)
    df_phrase = pd.DataFrame(phrase_rows)

    if not output_path.lower().endswith(".xlsx"):
        output_path += ".xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_adj.to_excel(writer, index=False, sheet_name="Adjectives")
        df_phrase.to_excel(writer, index=False, sheet_name="Phrases")
        meta = pd.DataFrame([{
            "Input": input_path,
            "Split_Mode": cfg.split_mode,
            "Split_Regex_or_Mode": cfg.split_regex,
            "Total_Docs": total_docs,
            "Total_Tokens_Approx": total_tokens_corpus,
            "Targets": "; ".join(targets),
            "Online_Judge": cfg.use_online_judge,
            "Window_Tokens": cfg.window_tokens,
            "Phrase_Max_Tokens": cfg.phrase_max_tokens,
            "SpaCy_BatchSize": cfg.nlp_batch_size,
            "Max_Doc_Chars": cfg.max_doc_chars
        }])
        meta.to_excel(writer, index=False, sheet_name="Meta")

    if log_cb:
        log_cb(f"完成 ✅ 导出：{output_path}")
        log_cb(f"形容词条目：{len(df_adj)}；短语条目：{len(df_phrase)}")


# =========================
# GUI
# =========================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TXT语料：形容词/修饰语检索统计工具")
        self.geometry("900x640")

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.targets_text = tk.StringVar()

        self.split_mode = tk.StringVar(value="regex")
        # ✅ 默认给你“等号分隔线模式”
        # 用法：把这里保持为 "====LINE====" 即可按 \n=+\n 切分
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
        ttk.Label(r1, text="导入 TXT 语料库:").pack(side="left")
        ttk.Entry(r1, textvariable=self.input_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(r1, text="选择…", command=self.pick_input).pack(side="left")

        # output
        r2 = ttk.Frame(root); r2.pack(fill="x", **pad)
        ttk.Label(r2, text="导出 Excel(.xlsx):").pack(side="left")
        ttk.Entry(r2, textvariable=self.output_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(r2, text="选择…", command=self.pick_output).pack(side="left")

        # targets
        r3 = ttk.Frame(root); r3.pack(fill="x", **pad)
        ttk.Label(r3, text="检索目标（多个用 ; 或 ； 分隔）:").pack(side="left")
        ttk.Entry(r3, textvariable=self.targets_text).pack(side="left", fill="x", expand=True, padx=8)

        # split mode
        box_split = ttk.LabelFrame(root, text="篇次计算：如何把大 txt 切成“篇/文档”（非常关键）")
        box_split.pack(fill="x", **pad)

        rs = ttk.Frame(box_split); rs.pack(fill="x", padx=10, pady=6)
        ttk.Radiobutton(rs, text="按空行分段", variable=self.split_mode, value="blanklines").pack(side="left")
        ttk.Radiobutton(rs, text="每行一篇", variable=self.split_mode, value="lines").pack(side="left", padx=14)
        ttk.Radiobutton(rs, text="按分隔线/正则分隔（推荐）", variable=self.split_mode, value="regex").pack(side="left")

        rs2 = ttk.Frame(box_split); rs2.pack(fill="x", padx=10, pady=6)
        ttk.Label(rs2, text="分隔模式/正则：").pack(side="left")
        ttk.Entry(rs2, textvariable=self.split_regex).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(rs2, text="（用等号线切分请填：====LINE====）").pack(side="left")

        # params
        box_param = ttk.LabelFrame(root, text="参数（影响召回/噪声 & 速度）")
        box_param.pack(fill="x", **pad)
        rp = ttk.Frame(box_param); rp.pack(fill="x", padx=10, pady=6)

        ttk.Label(rp, text="窗口tokens:").pack(side="left")
        ttk.Spinbox(rp, from_=3, to=30, textvariable=self.window_tokens, width=6).pack(side="left", padx=8)

        ttk.Label(rp, text="短语最大tokens:").pack(side="left", padx=(16, 0))
        ttk.Spinbox(rp, from_=2, to=15, textvariable=self.phrase_max_tokens, width=6).pack(side="left", padx=8)

        ttk.Label(rp, text="spaCy批大小:").pack(side="left", padx=(16, 0))
        ttk.Spinbox(rp, from_=8, to=256, textvariable=self.spacy_batch, width=6).pack(side="left", padx=8)

        ttk.Label(rp, text="单篇最大字符(超出自动分块):").pack(side="left", padx=(16, 0))
        ttk.Spinbox(rp, from_=50000, to=1000000, textvariable=self.max_doc_chars, width=8).pack(side="left", padx=8)

        # online
        box_online = ttk.LabelFrame(root, text="可选：联网推理过滤（更准，但需要 API Key 且产生费用）")
        box_online.pack(fill="x", **pad)

        ro = ttk.Frame(box_online); ro.pack(fill="x", padx=10, pady=6)
        ttk.Checkbutton(ro, text="启用联网推理（过滤“是否真的修饰目标”）", variable=self.use_online).pack(side="left")

        ro2 = ttk.Frame(box_online); ro2.pack(fill="x", padx=10, pady=6)
        ttk.Label(ro2, text="OpenAI API Key:").pack(side="left")
        ttk.Entry(ro2, textvariable=self.api_key, show="*", width=48).pack(side="left", padx=8)
        ttk.Label(ro2, text="模型:").pack(side="left", padx=(10, 0))
        ttk.Entry(ro2, textvariable=self.model_name, width=14).pack(side="left")

        # progress & buttons
        r6 = ttk.Frame(root); r6.pack(fill="x", **pad)
        ttk.Progressbar(r6, variable=self.progress_val, maximum=100).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Button(r6, text="开始", command=self.start).pack(side="left")
        ttk.Button(r6, text="退出", command=self.destroy).pack(side="left", padx=(8, 0))

        # log
        box_log = ttk.LabelFrame(root, text="运行日志")
        box_log.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(box_log, height=14, wrap="word")
        self.log.pack(fill="both", expand=True, padx=10, pady=8)

        self._log("提示：你用的分隔线是整行 '====='，已默认设置为 ====LINE==== 切分模式。")

    def _log(self, s: str):
        self.log.insert("end", s + "\n")
        self.log.see("end")

    def pick_input(self):
        path = filedialog.askopenfilename(
            title="选择 TXT 语料库",
            filetypes=[("Text", "*.txt"), ("All", "*.*")]
        )
        if path:
            self.input_path.set(path)

    def pick_output(self):
        path = filedialog.asksaveasfilename(
            title="选择导出位置",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if path:
            self.output_path.set(path)

    def start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("提示", "正在运行中，请等待完成。")
            return

        in_path = self.input_path.get().strip()
        out_path = self.output_path.get().strip()
        targets_raw = self.targets_text.get().strip()

        if not in_path:
            messagebox.showerror("错误", "请选择导入 TXT 文件。"); return
        if not out_path:
            messagebox.showerror("错误", "请选择导出地址。"); return
        if not targets_raw:
            messagebox.showerror("错误", "请输入至少一个检索目标（用 ; 或 ； 分隔）。"); return

        targets = split_targets(targets_raw)
        if not targets:
            messagebox.showerror("错误", "目标解析为空，请检查分隔符是否为 ; 或 ；"); return

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
            if not messagebox.askyesno("确认", "你启用了联网推理但没填 API Key，是否继续（将自动改为本地推理）？"):
                return
            cfg.use_online_judge = False

        self.progress_val.set(0)
        self._log("=" * 60)
        self._log("开始处理…")

        def progress_cb(done, total):
            pct = (done / total) * 100 if total else 0
            self.msg_queue.put(("progress", pct))

        def log_cb(msg):
            self.msg_queue.put(("log", msg))

        def worker():
            try:
                process_txt(in_path, out_path, targets, cfg, progress_cb=progress_cb, log_cb=log_cb)
                self.msg_queue.put(("done", "完成"))
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
                    self._log("全部完成 ✅")
                    messagebox.showinfo("完成", "处理完成，已导出 Excel。")
                elif kind == "error":
                    self._log("❌ 出错：" + item[1])
                    messagebox.showerror("出错", item[1])
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)


if __name__ == "__main__":
    App().mainloop()