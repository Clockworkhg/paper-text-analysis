# 研究模板

第三阶段加入了研究模板注册表。模板不会改变底层语料格式，而是为不同语料类型提供默认元数据字段、人工编码字段、错误类型、方法摘要和限制说明。

查看可用模板：

```powershell
python research_tool.py templates
```

当前内置模板：

| 模板 | 用途 |
|---|---|
| `generic` | 通用语料研究。 |
| `news_lexis` | 新闻话语、媒体表征、LexisNexis 语料。 |
| `policy` | 政策、法律、白皮书、机构报告。 |
| `academic` | 学术论文、摘要、章节、学科写作。 |
| `interview` | 访谈、焦点小组、质性材料。 |
| `social_media` | 帖文、评论、标签、平台导出。 |
| `translation` | 原文/译文、机器翻译、翻译偏移与错误分析。 |

使用模板：

```powershell
python research_tool.py import -i policy_docs -o output_policy --corpus-type policy -t "risk; responsibility"
python research_tool.py analyze -o output_policy --corpus-type policy -t "risk; responsibility"
```

模板会写入：

- `00_run_config/research_template.json`
- `01_corpus/corpus_manifest.json` 的 `research_template` 字段
- `06_review/modifier_semantic_review.xlsx` 的模板化编码列
- `07_reports/method_summary.md`
- `07_reports/method_limitations.md`

例如，`academic` 模板会在复核表中加入 `research_move`、`stance_marker`、`contribution_type` 等字段；`policy` 模板会加入 `problem_definition`、`responsibility_type`、`solution_frame` 等字段。
