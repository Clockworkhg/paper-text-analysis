import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import json


def load_json_safely(path: str):
    """Load JSON with better error messages; optionally auto-fix backslashes."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        # Read raw text to show context
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        # Try to show a small snippet around the error position
        pos = e.pos
        start = max(0, pos - 60)
        end = min(len(text), pos + 60)
        snippet = text[start:end].replace("\n", "\\n")

        msg = (
            f"JSON 解析失败：{e.msg}\n"
            f"位置：第 {e.lineno} 行，第 {e.colno} 列（char {e.pos}）\n\n"
            f"错误附近片段：\n{snippet}\n\n"
            f"常见原因：字符串里包含未转义的反斜杠 \\（例如 Windows 路径 C:\\Users\\...）\n\n"
            f"是否尝试自动修复？（将所有 \\ 替换为 \\\\ 后重试）"
        )

        if messagebox.askyesno("JSON 格式错误", msg):
            fixed_text = text[:pos] + "\\\\" + text[pos:]
            try:
                return json.loads(fixed_text)
            except json.JSONDecodeError as e2:
                messagebox.showerror(
                    "自动修复失败",
                    f"自动修复后仍无法解析：{e2.msg}\n"
                    f"位置：第 {e2.lineno} 行，第 {e2.colno} 列"
                )
                return None
        else:
            return None
    except UnicodeDecodeError:
        messagebox.showerror(
            "编码错误",
            "文件编码可能不是 UTF-8。请用编辑器另存为 UTF-8 后再试。"
        )
        return None


def process_file():
    input_file = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
    if not input_file:
        return

    data = load_json_safely(input_file)
    if data is None:
        return

    if "by_source_count" not in data or not isinstance(data["by_source_count"], dict):
        messagebox.showerror(
            "JSON 结构不符合预期",
            "找不到 by_source_count 字段，或它不是一个对象(dict)。"
        )
        return

    source_counts = data["by_source_count"]
    flattened_data = [{"Source": source, "Count": count} for source, count in source_counts.items()]
    df = pd.DataFrame(flattened_data).sort_values("Count", ascending=False)

    output_file = filedialog.asksaveasfilename(
        defaultextension=".xlsx",
        filetypes=[("Excel Files", "*.xlsx"), ("CSV Files", "*.csv")]
    )
    if not output_file:
        return

    try:
        if output_file.endswith(".xlsx"):
            df.to_excel(output_file, index=False)
        else:
            df.to_csv(output_file, index=False, encoding="utf-8-sig")
    except Exception as ex:
        messagebox.showerror("导出失败", str(ex))
        return

    result_label.config(text=f"File saved to {output_file}")
    messagebox.showinfo("完成", f"已导出：\n{output_file}")


root = tk.Tk()
root.title("JSON to Table Exporter")

label = tk.Label(root, text="Select a JSON file to process and export it as a CSV or Excel file.")
label.pack(pady=10)

process_button = tk.Button(root, text="Select JSON File", command=process_file)
process_button.pack(pady=10)

result_label = tk.Label(root, text="")
result_label.pack(pady=10)

root.mainloop()