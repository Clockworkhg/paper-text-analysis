import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import spacy
from collections import defaultdict
import os

try:
    nlp = spacy.load("en_core_web_sm")
except:
    raise RuntimeError("请先运行：python -m spacy download en_core_web_sm")


def _is_header_line(parts: list, line_index: int) -> bool:
    if line_index > 0:
        return False
    if len(parts) < 3:
        return False
    header_keywords = {"left", "right", "hit", "file", "context", "keyword", "node"}
    first_col = parts[0].strip().lower()
    second_col = parts[1].strip().lower() if len(parts) > 1 else ""
    return first_col in header_keywords or second_col in header_keywords


def _find_syntactic_head(doc, start_i: int, end_i: int):
    span_tokens = list(doc[start_i:end_i])
    if not span_tokens:
        return span_tokens[-1]
    candidates = [tok for tok in span_tokens if tok.dep_ in ("ROOT", "head")]
    if not candidates:
        candidates = [tok for tok in span_tokens if tok.head.i < start_i or tok.head.i >= end_i]
    if not candidates:
        candidates = [tok for tok in span_tokens if tok.pos_ not in ("DET", "ADP", "PART")]
    if not candidates:
        return span_tokens[-1]
    return candidates[-1]


def analyze_kwic(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    total_tokens = 0
    total_docs = 0

    adj_frequency = defaultdict(int)
    adj_range = defaultdict(set)

    start_line = 1
    if lines:
        first_parts = lines[0].strip().split("\t")
        if _is_header_line(first_parts, 0):
            start_line = 1
        else:
            start_line = 0

    data_lines = lines[start_line:]

    records = []
    for line in data_lines:
        parts = line.strip().split("\t")
        if len(parts) < 4:
            continue
        file_name = parts[0]
        left = parts[1]
        hit = parts[2].strip()
        right = parts[3]
        full_text = left + " " + hit + " " + right
        records.append((file_name, hit.lower().split(), full_text))

    texts = [r[2] for r in records]
    for (file_name, hit_tokens, full_text), doc in zip(records, nlp.pipe(texts, batch_size=128)):
        total_docs += 1
        total_tokens += len(doc)

        for i in range(len(doc) - len(hit_tokens) + 1):
            match = True
            for j in range(len(hit_tokens)):
                if doc[i + j].text.lower() != hit_tokens[j]:
                    match = False
                    break

            if match:
                head_token = _find_syntactic_head(doc, i, i + len(hit_tokens))

                for child in head_token.children:
                    if child.pos_ == "ADJ" and child.dep_ == "amod":
                        adj = child.lemma_.lower()
                        adj_frequency[adj] += 1
                        adj_range[adj].add(file_name)

    results = []
    for adj in adj_frequency:
        freq = adj_frequency[adj]
        doc_count = len(adj_range[adj])

        norm_freq = freq / total_tokens * 1_000_000 if total_tokens > 0 else 0
        norm_range = doc_count / total_docs if total_docs > 0 else 0

        results.append({
            "Adjective": adj,
            "Frequency": freq,
            "Range(篇次)": doc_count,
            "NormFreq(每百万词)": round(norm_freq, 2),
            "NormRange(篇次比例)": round(norm_range, 4)
        })

    df = pd.DataFrame(results)
    df = df.sort_values(by="Frequency", ascending=False)

    return df


def run_gui():
    root = tk.Tk()
    root.title("KWIC 修饰形容词分析工具")
    root.geometry("550x300")

    selected_file = tk.StringVar()
    output_path = tk.StringVar()

    def choose_file():
        file = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if file:
            selected_file.set(file)

    def choose_output():
        file = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            filetypes=[("Excel Files", "*.xlsx")])
        if file:
            output_path.set(file)

    def start_analysis():
        if not selected_file.get():
            messagebox.showerror("错误", "请选择输入文件")
            return

        if not output_path.get():
            messagebox.showerror("错误", "请选择导出路径")
            return

        try:
            df = analyze_kwic(selected_file.get())
            df.to_excel(output_path.get(), index=False)
            messagebox.showinfo("完成", "分析完成，已导出Excel文件！")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    tk.Label(root, text="选择KWIC文件:").pack(pady=5)
    tk.Entry(root, textvariable=selected_file, width=70).pack()
    tk.Button(root, text="浏览文件", command=choose_file).pack(pady=5)

    tk.Label(root, text="选择导出位置:").pack(pady=5)
    tk.Entry(root, textvariable=output_path, width=70).pack()
    tk.Button(root, text="选择保存位置", command=choose_output).pack(pady=5)

    tk.Button(root, text="开始分析", command=start_analysis,
              bg="#4CAF50", fg="white").pack(pady=20)

    root.mainloop()


if __name__ == "__main__":
    run_gui()
