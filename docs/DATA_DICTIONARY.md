# 数据字典

本文档解释项目主要输出文件和字段的研究含义。

## 统一语料模型输出

第一阶段平台化改造新增了一层稳定的 corpus/document/run 数据模型。旧输出仍然保留在输出根目录，新的规范化元数据写入：

| 文件 | 含义 |
|---|---|
| `00_run_config/data_model.json` | 统一数据模型说明，定义 corpus、document、analysis_run、review_item 等实体。 |
| `01_corpus/corpus_manifest.json` | 当前语料库清单，记录 `corpus_id`、`run_id`、语料类型、文档数、近似词数、目标词命中数。 |
| `01_corpus/documents.csv` | 机器友好的文档级元数据表。 |
| `01_corpus/document_registry.xlsx` | 研究者友好的文档级元数据表，附 README sheet。 |

核心字段：

| 字段 | 含义 |
|---|---|
| `corpus_id` | 稳定语料库 ID，用于把同一语料的文档、分析和复核结果关联起来。 |
| `run_id` | 本次 pipeline 运行 ID，用于记录一次带参数的分析执行。 |
| `document_id` | 稳定文档 ID，是后续 KWIC、搭配、编码和复核结果的统一连接键。 |
| `corpus_type` | 语料类型/模板，例如 `news_lexis`、`policy`、`academic`、`interview`、`social_media`。 |
| `source_raw` | 从文本头部或导入源中解析的原始来源。 |
| `source_normalized` | 规范化后的来源或分组标签。 |
| `group_label` | 默认比较分组变量，可对应媒体、机构、学科、平台、说话人角色等。 |
| `country` | 来源机构所属国家/地区，由步骤 3 的国别结果回流合并得到（精确→归一化→模糊匹配）；属于辅助变量，需人工复核。 |
| `relative_path` | 文档在旧 `corpus/` 目录中的相对路径。 |
| `word_count_approx` | 近似词数。 |
| `target_hits_total` | 当前目标词列表的总命中数。 |
| `target_hits_json` | 各目标词命中次数的 JSON 字段。 |

研究用途：这层模型是后续综合语料平台的地基。新闻语料仍可使用旧流程，但新的多语料导入、跨语料比较、编码复核和报告导出都应优先连接到 `document_id`、`corpus_id` 和 `run_id`。

## `source_counts.xlsx`

| 字段 | 含义 |
|---|---|
| `Source` | 从 LexisNexis 报告中提取的原始来源机构名称。 |
| `Count` | 该来源机构在语料中的文章数量。 |

研究用途：描述语料来源分布，为后续来源机构合并和国别比较提供输入。

## `merged_sources.xlsx`

| Sheet | 含义 |
|---|---|
| `WithCountry` | 规范化后的来源机构、文章数量和国别识别结果。 |
| `CountrySummary` | 按国家汇总的文章数量。 |
| `SuggestedOverrides` | 自动国别候选、置信度和证据。 |
| `AutoOverrides` | 达到阈值后自动采纳的国别结果。 |
| `RowMapping` | 原始来源名到规范来源名的映射。 |

常见字段：

| 字段 | 含义 |
|---|---|
| `Source_Merged` | 合并后的规范来源机构名。 |
| `Count_Sum` | 合并后的文章数量。 |
| `Country` | 来源机构所属国家/地区。 |
| `Suggested_Country` | 自动推断的候选国家/地区。 |
| `Confidence` | 自动推断置信度，需结合证据和人工复核解释。 |
| `Evidence_Top3` | 规则或外部知识库证据摘要。 |

研究用途：支持按媒体来源和国别分析话语差异。国别识别属于辅助变量，不应未经复核直接作为无误差事实。

## `adjectives_phrases.xlsx`

| Sheet | 含义 |
|---|---|
| `Adjectives` | 目标词附近提取的形容词及频次。 |
| `Phrases` | 目标词附近提取的短语/词块及频次。 |
| `KWIC` | 目标词左右上下文，用于人工语境化阅读。 |
| `Collocates` | 目标词窗口内的内容词共现候选，含近似关联强度指标。 |
| `SemanticProsodyCandidates` | 基于评价种子词的语义韵候选标签，必须人工复核。 |
| `GroupComparison` | 按可选分组变量（`Group_By`）聚合的候选表达频次，用于后续来源/国别/自定义维度比较。 |
| `Meta` | 输入文件、目标词、分组方式和参数。 |

常见字段：

| 字段 | 含义 |
|---|---|
| `Target` | 研究目标词。 |
| `Corpus_ID` | 稳定语料库 ID，用于把分析结果连接回 `01_corpus/corpus_manifest.json`。 |
| `Run_ID` | 稳定分析运行 ID，用于追溯本次参数化分析。 |
| `Document_ID` | KWIC 等单条语境证据所在的稳定文档 ID。 |
| `Document_IDs` | 聚合候选项涉及的稳定文档 ID 列表，用 ` | ` 分隔。 |
| `Adjective` | 自动提取的候选形容词。 |
| `Phrase` | 自动提取的候选短语或词块。 |
| `Frequency` | 候选表达出现次数。 |
| `Document_Frequency` | 出现该表达的文档数量。 |
| `Norm_Freq` | 标准化频率，如每万词频次。 |
| `Left_Context` | KWIC 左侧上下文。 |
| `Keyword` | 命中的目标词文本。 |
| `Right_Context` | KWIC 右侧上下文。 |
| `Full_Context` | 合并后的上下文，供人工复核。 |
| `Collocate` | 目标词窗口内的内容词共现候选。 |
| `MI_Score_Approx` | 近似互信息分数，用于观察目标词和共现词关联强度。 |
| `Log_Likelihood_Approx` | 近似 log-likelihood 分数，用于观察目标词和共现词关联强度。 |
| `Polarity_Candidate` | 种子词表给出的积极/消极/混合/未编码候选标签，不是最终判断。 |
| `Source` | 从语料 TXT 头部 `<SOURCE>` 解析出的原始来源（可能为多机构拼接的原始字符串）。 |
| `Source_Normalized` | 从文档登记表注入的规范化机构名（`<SOURCE_NORM>` 表头），与来源文件夹一致。 |
| `Group` | 该文档在当前分组方式（`group_by`）下的分组标签。 |
| `Source_Group` | GroupComparison 行的分组标签，含义由同表的 `Group_By` 决定。 |
| `Group_By` | GroupComparison 使用的分组变量：`source`（原始表头）、`institution`（媒体机构）、`country`（国别）、`custom`（自定义映射）。 |

### 分组方式（group_by）

`GroupComparison` 的分组变量可通过 `--group-by` / GUI「分组方式」选择，并记录在 `run_config.json` 与 `Meta` 表中：

| 模式 | 分组依据 | 数据来源 |
|---|---|---|
| `source`（默认） | 语料 TXT 头部原始 `<SOURCE>` 值 | 语料文件本身 |
| `institution` | 规范化机构名（`source_normalized`） | `01_corpus/documents.csv` |
| `country` | 来源机构国别（未匹配文档回退为机构分组） | 登记表 `country` 列（由 `merged_sources.xlsx` 回流，需人工复核） |
| `custom` | 研究者自定义标签（如立场/倾向类别） | `01_corpus/group_overrides.xlsx`（`python research_tool.py project groups -p …` 生成模板，编辑 `group` 列） |

研究用途：同一语料可在不同理论维度下重跑步骤 4 得到对应分组比较，每次运行的分组方式随 run 配置存档。

研究用途：作为搭配、语义韵和评价资源分析的候选证据。所有高价值条目应回到上下文人工复核。

## `adjectives_final.xlsx`

| 字段 | 含义 |
|---|---|
| `Adjective` | 候选形容词。 |
| `POS` | 自动词性识别结果。 |
| `中文意思` | 自动翻译或辅助理解字段。 |

研究用途：辅助研究者理解候选评价词，不应替代人工语义判断。

## `run_config.json`

| 字段 | 含义 |
|---|---|
| `created_at` | 运行时间。 |
| `input` | 输入文件绝对路径。 |
| `output` | 输出目录绝对路径。 |
| `targets` | 目标词设置。 |
| `country_lookup_enabled` | 是否启用联网国别推断。 |
| `group_by` | 本次运行的分组方式（source/institution/country/custom）。 |
| `steps_requested` | 用户请求的步骤。 |
| `steps_to_run` | 实际运行步骤。 |
| `environment` | Python、依赖版本和 git commit。 |
| `method_note` | 自动输出的解释边界说明。 |

研究用途：保证每次分析可以复现和审计。
