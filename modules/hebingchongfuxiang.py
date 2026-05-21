import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd

from shared.io_utils import read_table, write_table


class ScrollableCheckList(ttk.Frame):
    def __init__(self, master, title=""):
        super().__init__(master)
        self.vars = {}

        ttk.Label(self, text=title).pack(anchor="w", padx=6, pady=(6, 2))

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, highlightthickness=0)
        vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=vbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def set_columns(self, cols, preselect=None):
        for w in self.inner.winfo_children():
            w.destroy()
        self.vars.clear()

        preselect = set(preselect or [])
        for c in cols:
            v = tk.BooleanVar(value=(c in preselect))
            self.vars[c] = v
            ttk.Checkbutton(self.inner, text=c, variable=v).pack(anchor="w", padx=6, pady=2)

    def get_selected(self):
        return [c for c, v in self.vars.items() if v.get()]

    def select_all(self):
        for v in self.vars.values():
            v.set(True)

    def clear_all(self):
        for v in self.vars.values():
            v.set(False)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("自选合并列 + 自选相加列（不乱行）")
        self.geometry("980x620")

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()

        self.df = None
        self.columns = []

        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="导入文件：").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.input_path).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="选择…", command=self.choose_input).grid(row=0, column=2)

        ttk.Label(top, text="导出地址：").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.output_path).grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(top, text="选择…", command=self.choose_output).grid(row=1, column=2, pady=(8, 0))

        ttk.Button(top, text="读取列名", command=self.load_columns).grid(row=0, column=3, padx=(10, 0))
        ttk.Button(top, text="开始合并并导出", command=self.run).grid(row=1, column=3, padx=(10, 0), pady=(8, 0))

        top.columnconfigure(1, weight=1)

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(mid)
        left.pack(side="left", fill="both", expand=True)

        right = ttk.Frame(mid)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.keys_list = ScrollableCheckList(left, "① 选择【合并列 / 分组列】（同一组会合并为一行）")
        self.keys_list.pack(fill="both", expand=True)

        keys_btns = ttk.Frame(left)
        keys_btns.pack(fill="x", pady=6)
        ttk.Button(keys_btns, text="全选", command=self.keys_list.select_all).pack(side="left")
        ttk.Button(keys_btns, text="全不选", command=self.keys_list.clear_all).pack(side="left", padx=6)

        self.sum_list = ScrollableCheckList(right, "② 选择【相加列 / 求和列】（这些列会在组内求和）")
        self.sum_list.pack(fill="both", expand=True)

        sum_btns = ttk.Frame(right)
        sum_btns.pack(fill="x", pady=6)
        ttk.Button(sum_btns, text="全选", command=self.sum_list.select_all).pack(side="left")
        ttk.Button(sum_btns, text="全不选", command=self.sum_list.clear_all).pack(side="left", padx=6)

        bottom = ttk.Frame(self)
        bottom.pack(fill="both", expand=False, padx=10, pady=(0, 10))

        ttk.Label(bottom, text="预览（前 20 行）：").pack(anchor="w")
        self.preview = tk.Text(bottom, height=10)
        self.preview.pack(fill="both", expand=True)

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=(0, 10))

    def choose_input(self):
        path = filedialog.askopenfilename(
            title="选择要导入的文件",
            filetypes=[
                ("Excel files", "*.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.input_path.set(path)
            self.df = None
            self.columns = []
            self.preview.delete("1.0", tk.END)

    def choose_output(self):
        path = filedialog.asksaveasfilename(
            title="选择导出地址",
            defaultextension=".xlsx",
            filetypes=[
                ("Excel files", "*.xlsx"),
                ("CSV files", "*.csv"),
            ],
        )
        if path:
            self.output_path.set(path)

    def load_columns(self):
        in_path = self.input_path.get().strip()
        if not in_path:
            messagebox.showwarning("提示", "请先选择导入文件。")
            return

        try:
            df = read_table(in_path)
            if df.empty:
                messagebox.showwarning("提示", "表格是空的。")
                return

            df.columns = [str(c) for c in df.columns]
            self.df = df
            self.columns = list(df.columns)

            default_key = [self.columns[0]]

            numeric_like = []
            for c in self.columns[1:]:
                s = pd.to_numeric(df[c], errors="coerce")
                if s.notna().sum() > 0:
                    numeric_like.append(c)

            self.keys_list.set_columns(self.columns, preselect=default_key)
            self.sum_list.set_columns(self.columns, preselect=numeric_like)

            self._preview_df(df)
        except Exception as e:
            messagebox.showerror("读取失败", f"无法读取文件：\n{e}")

    def _preview_df(self, df):
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, df.head(20).to_string(index=False))

    def run(self):
        in_path = self.input_path.get().strip()
        out_path = self.output_path.get().strip()

        if not in_path:
            messagebox.showwarning("提示", "请先选择导入文件。")
            return
        if not out_path:
            messagebox.showwarning("提示", "请先选择导出地址。")
            return

        try:
            self.progress.start(10)

            if self.df is None:
                self.df = read_table(in_path)
                self.df.columns = [str(c) for c in self.df.columns]
                self.columns = list(self.df.columns)

            df = self.df.copy()
            if df.empty:
                raise ValueError("表格为空，无法处理。")

            key_cols = self.keys_list.get_selected()
            sum_cols = self.sum_list.get_selected()

            if not key_cols:
                raise ValueError("请至少选择 1 个【合并列/分组列】。")

            overlap = set(key_cols) & set(sum_cols)
            if overlap:
                raise ValueError(f"这些列同时被选为合并列和相加列：{', '.join(overlap)}。请取消其中一种。")

            for c in key_cols + sum_cols:
                if c not in df.columns:
                    raise ValueError(f"找不到列：{c}")

            other_cols = [c for c in df.columns if c not in key_cols and c not in sum_cols]

            agg = {}
            for c in other_cols:
                agg[c] = "first"

            for c in sum_cols:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
                agg[c] = "sum"

            out = df.groupby(key_cols, as_index=False).agg(agg)
            out = out[key_cols + other_cols + sum_cols]

            write_table(out, out_path)
            self._preview_df(out)

            messagebox.showinfo(
                "完成",
                f"已合并并导出：\n{out_path}\n\n原始行数：{len(df)}\n合并后行数：{len(out)}"
            )
        except Exception as e:
            messagebox.showerror("处理失败", str(e))
        finally:
            self.progress.stop()


if __name__ == "__main__":
    app = App()
    app.mainloop()
