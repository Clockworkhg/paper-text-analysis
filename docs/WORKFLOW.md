# 标准研究流程

本流程将现有脚本组织为一套可复现的语料库辅助话语研究工作流。

## 1. 准备语料

从 LexisNexis 导出 DOCX 文件。记录检索式、时间范围、媒体范围、语言、纳入和排除标准。

## 2. 运行 pipeline

```powershell
python research_tool.py run -i corpus.docx -o output -t "China; India" --no-country
```

常用参数：

- `--skip 3,4`：跳过指定步骤。
- `--only 1,2`：只运行指定步骤。
- `--force`：已有输出时强制重跑。
- `--no-country`：关闭联网国别推断。

## 3. 检查运行记录

每次运行会生成：

- `output/run_config.json`
- `output/00_run_config/run_config.json`

运行记录包含输入、输出、目标词、步骤、参数、git commit 和依赖版本。

## 4. 检查来源分布

查看 `source_counts.xlsx` 和 `merged_sources.xlsx`：

1. 检查来源机构是否被正确合并。
2. 检查国别候选是否可信。
3. 对高频来源进行人工复核。

## 5. 检查目标词上下文和候选表达

查看 `adjectives_phrases.xlsx`：

1. 先看高频形容词和短语。
2. 回到原文或 KWIC 上下文确认是否真实修饰目标词。
3. 查看 `Collocates` 工作表，结合 `MI_Score_Approx` 和 `Log_Likelihood_Approx` 判断哪些共现词值得进入解释。
4. 查看 `SemanticProsodyCandidates` 工作表，把自动标签当作候选线索而不是最终结论。
5. 查看 `GroupComparison` 工作表，初步比较不同来源组的表达差异。
6. 将候选表达归入语义韵、评价资源或话语框架类别。

## 6. 人工复核

建议至少抽样复核：

- 来源机构合并。
- 国别识别。
- 修饰语/短语提取。
- 评价或框架分类。

复核结果应记录 `is_correct`、`error_type` 和 `notes`。

## 7. 写作输出

论文方法部分可按以下顺序写：

1. 语料来源与筛选标准。
2. CADS/CDA 理论框架。
3. 语料预处理与来源规范化。
4. KWIC、搭配、语义韵和评价资源分析。
5. 参数、运行环境和复现记录。
6. 人工复核与方法限制。

## 8. 统一 CLI

推荐日常只记一个入口：

```powershell
python research_tool.py --help
```

常用命令：

- `python research_tool.py run ...`：运行完整研究流程。
- `python research_tool.py review output`：刷新复核模板、验证报告和方法文本。
- `python research_tool.py ocr`：对配置好的扫描文献执行 OCR。
- `python research_tool.py docs`：列出关键文档。
- `python research_tool.py test`：运行测试。
