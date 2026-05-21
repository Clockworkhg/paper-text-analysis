import os
import re
import sys
import csv
import threading
import subprocess
from collections import Counter
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText


class RNNTaggerGUI:
    NOUN_TAGS = {"NN", "NNS", "NNP", "NNPS"}
    ADJ_TAGS = {"JJ", "JJR", "JJS"}

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.base_dir = Path(__file__).resolve().parent
        self.cmd_dir = self.base_dir / "cmd"
        self.languages = self.find_languages()
        self.current_output_text = ""
        self.current_rows = []

        self.root.title("RNNTagger 可视化助手")
        self.root.geometry("1080x760")
        self.root.minsize(900, 650)

        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar(value=str(self.base_dir / "output.txt"))
        self.language_var = tk.StringVar(value=self.languages[0] if self.languages else "english")
        self.status_var = tk.StringVar(value="就绪")
        self.filter_var = tk.StringVar(value="全部")

        self.build_ui()
        self.refresh_languages()

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        file_frame = ttk.LabelFrame(outer, text="文件与模型", padding=10)
        file_frame.pack(fill="x")
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="输入文本：").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(file_frame, textvariable=self.input_path_var).grid(row=0, column=1, sticky="ew", padx=6, pady=4)
        ttk.Button(file_frame, text="选择文件", command=self.choose_input_file).grid(row=0, column=2, pady=4)

        ttk.Label(file_frame, text="输出结果：").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(file_frame, textvariable=self.output_path_var).grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        ttk.Button(file_frame, text="另存为", command=self.choose_output_file).grid(row=1, column=2, pady=4)

        ttk.Label(file_frame, text="语言模型：").grid(row=2, column=0, sticky="w", pady=4)
        self.language_combo = ttk.Combobox(file_frame, textvariable=self.language_var, state="readonly")
        self.language_combo.grid(row=2, column=1, sticky="w", padx=6, pady=4)
        ttk.Button(file_frame, text="刷新模型列表", command=self.refresh_languages).grid(row=2, column=2, pady=4)

        action_frame = ttk.LabelFrame(outer, text="操作", padding=10)
        action_frame.pack(fill="x", pady=(10, 0))

        ttk.Button(action_frame, text="一键标注", command=self.run_tagger).pack(side="left", padx=(0, 8))
        ttk.Button(action_frame, text="打开输出目录", command=self.open_output_dir).pack(side="left", padx=8)
        ttk.Button(action_frame, text="提取名词", command=lambda: self.apply_filter("名词")).pack(side="left", padx=8)
        ttk.Button(action_frame, text="提取形容词", command=lambda: self.apply_filter("形容词")).pack(side="left", padx=8)
        ttk.Button(action_frame, text="显示全部", command=lambda: self.apply_filter("全部")).pack(side="left", padx=8)
        ttk.Button(action_frame, text="导出词频 CSV", command=self.export_word_frequency).pack(side="left", padx=8)

        info_frame = ttk.Frame(outer)
        info_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(info_frame, textvariable=self.status_var).pack(side="left")
        ttk.Label(info_frame, text="筛选：").pack(side="right")
        ttk.Label(info_frame, textvariable=self.filter_var).pack(side="right")

        preview_frame = ttk.LabelFrame(outer, text="结果预览", padding=10)
        preview_frame.pack(fill="both", expand=True, pady=(10, 0))

        self.preview = ScrolledText(preview_frame, wrap="none", font=("Consolas", 11))
        self.preview.pack(fill="both", expand=True)

        tip = (
            "说明：将本程序放在 RNNTagger 根目录中使用。\n"
            "输入文件建议为 UTF-8 或 ANSI 纯文本；如遇乱码，可先用记事本另存为 UTF-8。\n"
            "“导出词频 CSV”会基于当前筛选结果统计 lemma 词频。"
        )
        tip_frame = ttk.LabelFrame(outer, text="提示", padding=10)
        tip_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(tip_frame, text=tip, justify="left").pack(anchor="w")

    def find_languages(self):
        langs = []
        if self.cmd_dir.exists():
            for file in self.cmd_dir.glob("rnn-tagger-*.bat"):
                m = re.match(r"rnn-tagger-(.+)\.bat$", file.name, flags=re.IGNORECASE)
                if m:
                    langs.append(m.group(1))
        return sorted(langs) or ["english"]

    def refresh_languages(self) -> None:
        self.languages = self.find_languages()
        self.language_combo["values"] = self.languages
        if self.language_var.get() not in self.languages:
            self.language_var.set(self.languages[0])
        self.status_var.set(f"已检测到 {len(self.languages)} 个语言模型")

    def choose_input_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要标注的文本文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialdir=str(self.base_dir),
        )
        if path:
            self.input_path_var.set(path)
            default_output = Path(path).with_name(Path(path).stem + "_tagged.txt")
            self.output_path_var.set(str(default_output))

    def choose_output_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择输出文件",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialdir=str(self.base_dir),
        )
        if path:
            self.output_path_var.set(path)

    def get_bat_path(self) -> Path:
        return self.cmd_dir / f"rnn-tagger-{self.language_var.get()}.bat"

    def run_tagger(self) -> None:
        input_path = Path(self.input_path_var.get().strip())
        output_path = Path(self.output_path_var.get().strip())
        bat_path = self.get_bat_path()

        if not input_path.exists():
            messagebox.showerror("错误", "输入文件不存在。")
            return
        if not bat_path.exists():
            messagebox.showerror("错误", f"未找到脚本：{bat_path}")
            return

        self.status_var.set("正在运行，请稍候……")
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, "正在调用 RNNTagger，请稍候……\n")

        thread = threading.Thread(
            target=self._run_tagger_worker,
            args=(input_path, output_path, bat_path),
            daemon=True,
        )
        thread.start()

    def _run_tagger_worker(self, input_path: Path, output_path: Path, bat_path: Path) -> None:
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["CUDA_VISIBLE_DEVICES"] = ""

            command = ["cmd", "/c", str(bat_path.relative_to(self.base_dir)), str(input_path)]
            result = subprocess.run(
                command,
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            stdout_text = (result.stdout or "").replace("\r\n", "\n")
            stderr_text = (result.stderr or "").replace("\r\n", "\n")

            if result.returncode != 0:
                raise RuntimeError(f"返回码：{result.returncode}\n\n错误信息：\n{stderr_text or '无'}")

            if not stdout_text.strip():
                combined = stderr_text.strip() or "程序执行完成，但没有得到输出。请检查输入文件编码或模型脚本。"
                raise RuntimeError(combined)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(stdout_text, encoding="utf-8")

            self.current_output_text = stdout_text
            self.current_rows = self.parse_output(stdout_text)
            self.root.after(0, lambda: self._update_success(output_path, stderr_text))
        except Exception as exc:
            self.root.after(0, lambda: self._update_error(str(exc)))

    def _update_success(self, output_path: Path, stderr_text: str) -> None:
        self.filter_var.set("全部")
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, self.current_output_text)
        suffix = ""
        stderr_lines = stderr_text.strip().splitlines()
        if stderr_lines:
            suffix = f"；附加信息：{stderr_lines[0]}"
        self.status_var.set(f"完成：已保存到 {output_path}{suffix}")

    def _update_error(self, message: str) -> None:
        self.status_var.set("运行失败")
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, message)
        messagebox.showerror("运行失败", message)

    def parse_output(self, text: str):
        rows = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parts = re.split(r"\s+", stripped)
            if len(parts) >= 3:
                token = parts[0]
                pos = parts[1]
                lemma = parts[2]
                rows.append((token, pos, lemma))
        return rows

    def apply_filter(self, mode: str) -> None:
        if not self.current_rows:
            messagebox.showinfo("提示", "当前没有可筛选的结果，请先运行标注。")
            return

        if mode == "全部":
            rows = self.current_rows
        elif mode == "名词":
            rows = [row for row in self.current_rows if row[1] in self.NOUN_TAGS]
        elif mode == "形容词":
            rows = [row for row in self.current_rows if row[1] in self.ADJ_TAGS]
        else:
            rows = self.current_rows

        self.filter_var.set(mode)
        self.preview.delete("1.0", tk.END)
        if rows:
            lines = [f"{tok}\t{pos}\t{lemma}" for tok, pos, lemma in rows]
            self.preview.insert(tk.END, "\n".join(lines))
            self.status_var.set(f"当前显示 {mode}：{len(rows)} 条")
        else:
            self.preview.insert(tk.END, f"没有筛选到{mode}结果。")
            self.status_var.set(f"当前显示 {mode}：0 条")

    def export_word_frequency(self) -> None:
        if not self.current_rows:
            messagebox.showinfo("提示", "当前没有结果可导出，请先运行标注。")
            return

        mode = self.filter_var.get()
        if mode == "名词":
            rows = [row for row in self.current_rows if row[1] in self.NOUN_TAGS]
        elif mode == "形容词":
            rows = [row for row in self.current_rows if row[1] in self.ADJ_TAGS]
        else:
            rows = self.current_rows

        if not rows:
            messagebox.showinfo("提示", "当前筛选结果为空，无法导出词频。")
            return

        save_path = filedialog.asksaveasfilename(
            title="导出词频 CSV",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            initialdir=str(self.base_dir),
        )
        if not save_path:
            return

        counter = Counter(lemma for _, _, lemma in rows)
        with open(save_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["lemma", "frequency"])
            for lemma, freq in counter.most_common():
                writer.writerow([lemma, freq])

        self.status_var.set(f"词频已导出：{save_path}")
        messagebox.showinfo("完成", f"词频已导出到：\n{save_path}")

    def open_output_dir(self) -> None:
        output_path = Path(self.output_path_var.get().strip() or self.base_dir)
        target = output_path.parent if output_path.suffix else output_path
        target = target if target.exists() else self.base_dir
        os.startfile(str(target))


def main() -> None:
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    app = RNNTaggerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
