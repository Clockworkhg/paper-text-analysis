# 论文文本分析工具集

这是一个面向新闻/论文语料的语料库辅助话语研究工具集。它支持 LexisNexis DOCX 拆分、来源机构统计、机构合并与国别识别、KWIC、搭配/共现、修饰语与短语提取、语义韵候选、人工复核和验证报告。

项目的方法定位是：

> Corpus-Assisted Discourse Studies (CADS) + Critical Discourse Analysis (CDA) + KWIC/Collocation/Semantic Prosody + Appraisal/Framing Analysis

## 快速开始

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

运行完整研究流程：

```powershell
python research_tool.py run -i corpus.docx -o output -t "China; India; Global South" --no-country
```

刷新人工复核模板和验证报告：

```powershell
python research_tool.py review output --sample-size 50
```

查看关键文档：

```powershell
python research_tool.py docs
```

运行测试：

```powershell
python research_tool.py test
```

更多示例见 [examples/QUICKSTART.md](examples/QUICKSTART.md)。

## 主要入口

- `research_tool.py`：统一 CLI，推荐日常使用。
- `integrated_app.py`：集成式 Tkinter 图形界面。
- `pipeline.py`：底层全流程命令行脚本。
- `tools/generate_validation_artifacts.py`：单独生成复核模板与验证报告。
- `tools/ocr_scanned_pdfs.py`：对配置好的扫描版文献 PDF 进行 OCR。

## 核心输出

完整运行后，输出目录会包含：

```text
output/
├── run_config.json
├── 00_run_config/
├── 06_review/
├── 07_reports/
├── source_counts.xlsx
├── merged_sources.xlsx
├── adjectives_phrases.xlsx
└── adjectives_final.xlsx
```

其中 `adjectives_phrases.xlsx` 是核心研究工作簿：

- `KWIC`：目标词左右上下文。
- `Adjectives`：目标词附近形容词候选。
- `Phrases`：目标词附近短语/词块候选。
- `Collocates`：目标词窗口内共现词及近似关联强度。
- `SemanticProsodyCandidates`：语义韵/评价倾向候选标签。
- `GroupComparison`：按来源组比较候选表达。
- `README`：字段和方法说明。

## 研究文档

- [docs/METHODOLOGY.md](docs/METHODOLOGY.md)：方法论说明。
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md)：输出字段字典。
- [docs/WORKFLOW.md](docs/WORKFLOW.md)：标准研究流程。
- [docs/VALIDATION.md](docs/VALIDATION.md)：人工复核与验证说明。
- [docs/LITERATURE_CLASSIFICATION.md](docs/LITERATURE_CLASSIFICATION.md)：文献分类。
- [docs/literature_notes/00_INDEX.md](docs/literature_notes/00_INDEX.md)：逐篇文献笔记索引。

## 注意事项

- 自动输出是候选证据，不是最终解释。关键结论应回到 KWIC/原文上下文复核。
- 国别识别是辅助变量，建议对高频来源进行人工检查。
- 语义韵候选标签基于种子词表，只能作为线索。
- `文献/`、`.ocr_deps/`、`.cache/`、输出目录和本地缓存默认不会进入 git。
