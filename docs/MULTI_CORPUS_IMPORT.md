# 多语料导入流程

第二阶段平台化改造后，除 LexisNexis DOCX 专用流水线外，也可以把普通 TXT/DOCX 文件夹或 CSV/Excel 文本表导入为统一语料库。

## 导入 TXT/DOCX 文件夹

```powershell
python research_tool.py import -i raw_texts -o output_generic --corpus-type policy -t "risk; responsibility"
```

导入器会递归读取 `.txt`、`.md`、`.docx` 文件，并写入：

- `output_generic/corpus/`
- `output_generic/source_counts.xlsx`
- `output_generic/corpus/import_report.json`
- `output_generic/01_corpus/documents.csv`
- `output_generic/01_corpus/document_registry.xlsx`
- `output_generic/01_corpus/corpus_manifest.json`

## 导入 CSV/Excel 文本表

```powershell
python research_tool.py import `
  -i corpus_table.xlsx `
  -o output_table `
  --corpus-type academic `
  --text-col abstract `
  --title-col title `
  --source-col journal `
  --date-col year `
  -t "AI; governance"
```

至少需要指定文本列 `--text-col`。标题、来源、日期和分组列可以按需要指定；如果不指定，工具会尝试识别常见列名。

## 分析已导入语料

导入后可直接对 `output/corpus/` 执行 KWIC、搭配、修饰语和语义韵候选分析：

```powershell
python research_tool.py analyze -o output_generic -t "risk; responsibility" --corpus-type policy
```

如需继续生成词性和翻译辅助表：

```powershell
python research_tool.py analyze -o output_generic -t "risk; responsibility" --corpus-type policy --pos-translate
```

该流程与 LexisNexis 专用 `run` 命令共享同一套 `document_id`、`corpus_id`、`run_id` 和复核/验证输出。
