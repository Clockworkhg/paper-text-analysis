# 研究级项目方案设计：综合语料研究工作台

## 1. 项目定位

本项目不应被定位为“关键词统计工具”或“情感分析脚本”，而应定位为一个面向多类型文本的 **综合语料研究工作台**。它的核心目标是把新闻、论文、政策文件、社交媒体、访谈材料、教材、企业文本、译文和其他研究语料，转换为可复核、可解释、可比较、可验证的研究证据链，服务于语料库语言学、CADS、CDA、内容分析、语义韵、评价理论、框架分析、文体研究、术语研究和翻译研究。

建议项目名称：

> Corpus-Assisted Discourse Analysis Workbench for Media Representation Studies

中文可称为：

> 综合语料研究与话语分析工作台

更通用的英文名称建议改为：

> Integrated Corpus Research Workbench

项目的研究级价值不在于自动给出“结论”，而在于构建一套从语料采集、元数据整理、KWIC 回读、搭配发现、评价资源识别、主题/框架归纳、人工复核到验证报告的完整方法链。自动化输出只是候选证据，最终解释必须回到语境、语篇结构、文本类型和研究问题。

因此，新闻语料不应是项目边界，而应是一个高价值应用场景。平台底层应保持通用：任何带有文本内容和元数据的语料，都可以进入同一套“构建-检索-统计-解释-复核-验证”的研究闭环。

## 2. 文献理论基础

### 2.1 CADS：从大规模语料中发现可解释模式

Baker、Partington 以及国内 CADS 研究共同支持一个基本立场：语料库方法可以在大规模文本中发现反复出现的语言模式，而话语分析负责解释这些模式如何参与社会意义、身份建构和意识形态生产。本项目中的 DOCX 拆分、词频、KWIC、搭配、短语和分组比较，正是 CADS 路径中的“模式发现”部分。

在方案中，CADS 应承担三项功能：

1. 让研究不只依赖少量例句，而有系统语料作为基础。
2. 让研究者能从频率、搭配和上下文中发现非显性的评价模式。
3. 让定量发现和定性解释之间形成循环，而不是彼此替代。

### 2.2 CDA 与解释性语篇研究：把语言模式放回社会语境

Hardt-Mautner、Fairclough、van Dijk、Wodak 等文献说明，文本不是中性的事实容器，而是制度化的话语实践。新闻报道、政策文本、学术论文、社交媒体帖文、课堂材料、企业公告和访谈叙述中的命名、修饰、搭配、引语、因果组织和框架选择，都会参与对象形象、群体边界、责任归因、知识生产和合法性建构。

因此，本项目的输出不应只回答“某个词出现多少次”，而应进一步追问：

1. 谁在命名研究对象？
2. 研究对象被放入怎样的语义环境？
3. 哪些评价资源被反复用于描述它？
4. 不同来源、机构、作者、体裁、学科、国家或时期的话语模式是否不同？
5. 这些模式如何连接到更大的政治、文化、知识、组织或制度语境？

### 2.3 Sinclair 传统：KWIC、搭配与语义韵

Sinclair、Stubbs、Hunston 以及国内搭配和语义韵研究强调，词项意义不仅来自词典定义，也来自重复共现的语境。项目中的 KWIC、Collocates、Adjectives、Phrases、SemanticProsodyCandidates 正好对应这一理论链条。

本项目应采用以下解释原则：

1. KWIC 是定性解释入口，用于检查目标词在真实语境中的使用。
2. Collocates 用于发现目标词周围的显著共现词。
3. Adjectives 和 Phrases 用于捕捉评价性修饰、称谓和词块。
4. SemanticProsodyCandidates 只标出潜在积极、消极或混合语义韵，不能替代人工判断。

### 2.4 Appraisal、Framing 与内容分析：从局部评价到解释类别

Martin & White 的评价理论可为形容词、判断、鉴赏、情感、强度和立场资源提供编码框架；Entman、Reese、Parmelee 等框架研究可把局部语言资源上升到问题定义、因果解释、道德评价和解决方案建议。

因此，本项目建议采用“双层解释”：

1. 微观层：目标词周围的评价资源，例如 risky、strategic、aggressive、peaceful、controversial。
2. 中观层：这些评价资源聚合成的解释类别，例如新闻框架、政策框架、学术论证模式、组织叙事、身份建构方式或主题类型。

### 2.5 Text as Data 与内容分析：可复现、可验证、可审计

Grimmer、Roberts & Stewart 以及 Krippendorff 的内容分析方法提醒我们：自动文本分析必须服务于明确研究问题、测量逻辑和验证流程。本项目已有 run_config、review template、validation_report 等功能，具备向研究级工具升级的基础。

研究级方案必须明确：

1. 每一次运行的参数、版本和输入输出都被记录。
2. 每一种自动结果都有抽样复核。
3. 每一种分类都有编码本和误差说明。
4. 论文中报告的不只是发现，也包括误差、限制和复核过程。

## 3. 平台化研究场景

本项目应设计为“通用语料底座 + 场景化研究模板”。底层功能保持一致，上层根据不同研究材料调整元数据、编码本和解释框架。

| 场景 | 典型语料 | 核心问题 | 对应方法 |
|---|---|---|---|
| 新闻话语研究 | LexisNexis 新闻、报纸、通讯社 | 媒体如何表征国家、群体、事件和议题 | CADS、CDA、框架分析、评价理论 |
| 学术论文研究 | 期刊论文、摘要、引言、结论 | 学科如何构建知识、立场和研究热点 | 术语研究、文体研究、元话语分析 |
| 政策文本研究 | 白皮书、法律、政策报告、声明 | 政策如何定义问题、责任和解决方案 | 内容分析、框架分析、CDA |
| 社交媒体研究 | 帖文、评论、标签、弹幕 | 公众如何表达情绪、立场和身份 | 情感分析、立场分析、话语社群分析 |
| 访谈与质性材料 | 访谈转写、焦点小组、田野笔记 | 受访者如何叙述经验、身份和意义 | 主题分析、叙事分析、质性编码 |
| 翻译与译文研究 | 原文/译文、机器译文、人工译文 | 译文如何偏移、规范化或重构意义 | 平行语料、错误分析、翻译共性研究 |
| 教材与教育语料 | 教材、课堂话语、作文语料 | 知识、价值和能力如何被语言化 | 教育话语分析、词汇/搭配研究 |
| 企业与组织文本 | 年报、ESG 报告、公告、招聘文本 | 组织如何建构形象、责任和风险 | 组织话语分析、内容审计、叙事分析 |

新闻语料仍然可以作为第一条示范路线：

> 英文新闻媒体对“China / Global South / Belt and Road / Ukraine / AI governance”等对象的表征研究：一项基于 CADS 与 CDA 的语料库辅助话语分析

但平台最终应支持更宽的研究题目，例如：

1. 国际组织政策报告中的“风险”与“责任”框架研究。
2. 学术论文摘要中研究贡献表达的跨学科比较。
3. 企业 ESG 报告中的合法性建构与绿色话语研究。
4. 社交媒体中某公共事件的情绪、立场和身份建构研究。
5. 机器译文与人工译文中评价资源偏移的语料库研究。

如果需要形成真正的研究级项目，建议先选择一个清晰对象，而不是同时分析太多主题。最优选择是一个语料类型、一个目标对象和两个比较维度，例如：

1. 语料类型：新闻 / 政策 / 学术论文 / 社媒 / 访谈。
2. 目标对象：China / risk / AI / climate / identity / innovation。
3. 比较维度一：来源、机构、学科、国家、作者群体或平台。
4. 比较维度二：时间阶段、事件阶段、文本体裁或版本差异。

## 4. 通用研究问题设计

### RQ1：命名与可见性

目标对象在语料中被如何命名、指称和聚焦？不同来源、机构、学科、平台、作者群体或时期是否偏好不同的称谓、同义表达或相关实体？

对应工具功能：

1. LexisNexis DOCX 拆分。
2. target terms 设置。
3. KWIC 命中。
4. Source_Group 与来源统计。

### RQ2：搭配与语义韵

目标对象周围最显著的搭配词、修饰语和短语是什么？这些表达形成了怎样的积极、消极、中性或混合语义韵？

对应工具功能：

1. Collocates。
2. Adjectives。
3. Phrases。
4. SemanticProsodyCandidates。
5. KWIC 回读。

### RQ3：评价资源

文本通过哪些评价维度描述目标对象？这些评价主要涉及能力、道德、合法性、风险、威胁、发展、合作、冲突、责任、创新、身份，还是其他维度？

对应工具功能：

1. Adjectives 与 Phrases 候选表。
2. 人工复核表。
3. review_annotations。
4. validation_report。

### RQ4：话语框架

这些评价资源如何聚合为更高层的话语框架、主题类别、叙事模式或论证结构？不同来源、体裁或时期是否呈现不同组合？

对应工具功能：

1. GroupComparison。
2. Source/Country 分组。
3. 归一化频率。
4. 人工编码字段。

### RQ5：差异与解释

不同国家、机构、媒体、学科、平台、作者群体或时间阶段的话语差异如何解释？这些差异是否与制度环境、专业规范、体裁约束、事件阶段、平台机制或组织目标有关？

对应工具功能：

1. merged_sources.xlsx。
2. CountrySummary。
3. Source_Group。
4. run_config 与方法记录。

## 5. 数据与语料库建设

### 5.1 数据来源

当前工具可以以 LexisNexis 导出的新闻 DOCX 作为第一类主数据源，但综合语料研究工作台应支持更多输入形态，包括 TXT、DOCX、PDF OCR 后文本、CSV/Excel 文本列、JSONL、访谈转写稿和网页抓取文本。每次导入必须记录：

1. 数据库名称。
2. 检索式。
3. 时间范围。
4. 语言。
5. 来源范围。
6. 地区范围。
7. 纳入与排除标准。
8. 去重规则。
9. 最终文章数和总词数。

### 5.2 语料分层

建议建立三个层级的语料结构：

1. 全语料：所有符合条件的文本。
2. 目标语料：包含目标词、主题词、实体或编码条件的文本。
3. 对比子语料：按来源、国家、地区、机构、学科、平台、体裁、作者群体或时间阶段划分。

### 5.3 元数据字段

每篇文章至少保留：

1. document_id。
2. title。
3. date。
4. source_raw。
5. source_merged。
6. corpus_type。
7. group_label。
8. word_count。
9. target_hits。
10. original_file。

如果是新闻语料，可继续使用 country_candidate、country_reviewed、media_type、news_agency 等字段。如果是学术论文，可使用 discipline、journal、author_affiliation、section 等字段。如果是访谈语料，可使用 participant_id、speaker_role、interview_round 等字段。

当前项目已经支持 source_counts、merged_sources、CountrySummary、RowMapping，这些可以作为元数据规范化的基础；后续应抽象成通用 metadata mapping，而不只服务媒体来源。

## 6. 分析流程

### Step 1：语料预处理

使用项目 pipeline 将 LexisNexis DOCX 拆分为 TXT，并提取来源、文章与基础统计。输出包括 corpus 文本、source_counts.xlsx 和 run_config.json。

研究级要求：

1. 保留原始输入。
2. 保留每次运行参数。
3. 对拆分失败或异常文本建立 error log。
4. 对重复文本进行说明。

### Step 2：来源与元数据规范化

使用机构合并与国别识别功能，生成 merged_sources.xlsx。

研究级要求：

1. 高频来源必须人工复核。
2. 自动推断字段只能作为候选变量。
3. 论文中报告 metadata normalization 的准确率或复核比例。
4. 对跨国媒体、通讯社、转载内容、多作者机构、平台转发、访谈说话人等复杂来源单独标注。

### Step 3：目标词 KWIC 检索

围绕目标词生成 KWIC 表，用于观察目标词的局部语境。

研究级要求：

1. 目标词列表应由理论与先导阅读共同确定。
2. 同义词、缩写、变体需要记录。
3. KWIC 样本需要人工阅读，形成初步主题和框架备忘录。

### Step 4：搭配、修饰语与短语提取

使用 Adjectives、Phrases、Collocates 输出发现目标词周围的语言模式。

研究级要求：

1. 同时报告 Frequency 和 Document_Frequency。
2. 尽量使用归一化频率进行来源比较。
3. MI 和 Log-Likelihood 只作为排序指标。
4. 高频表达必须回到 KWIC 检查是否真实修饰目标对象。

### Step 5：语义韵与评价资源编码

先使用 SemanticProsodyCandidates 生成候选取向，再由研究者进行人工编码。

建议编码字段：

1. polarity：positive / negative / neutral / ambivalent。
2. appraisal_type：affect / judgement / appreciation / graduation / engagement。
3. evaluation_dimension：capacity / morality / legitimacy / threat / risk / development / cooperation / conflict / responsibility。
4. target_relation：direct / indirect / ambiguous / irrelevant。
5. evidence_context：KWIC 或原文证据。
6. coder_note：编码理由。

### Step 6：框架、主题或类别归纳

把评价资源进一步聚合为话语框架、主题类别、叙事结构、论证模式或术语类别。不同语料场景可使用不同归纳层级。

新闻、政策和组织文本可使用以下框架类别：

1. 安全/威胁框架。
2. 经济/发展框架。
3. 地缘政治框架。
4. 道德/合法性框架。
5. 科技/能力框架。
6. 人道主义框架。
7. 合作/多边主义框架。
8. 冲突/竞争框架。
9. 文化/文明框架。
10. 责任归因框架。

学术论文语料可改用研究动作类别，例如提出问题、界定概念、回顾不足、说明方法、声明贡献、承认限制。访谈语料可改用主题分析类别，例如经验叙述、身份定位、情感表达、制度评价、行动策略。每个类别都必须有定义、包含标准、排除标准和例句。

### Step 7：分组比较

使用 GroupComparison、Source_Group、CountrySummary 比较不同来源的话语模式。

研究级要求：

1. 不直接比较原始频次，优先比较归一化频率。
2. 小样本来源不单独做强结论。
3. 需要区分通讯社文本与报纸原创文本。
4. 对显著差异进行 KWIC 质性回读。

## 7. 编码本设计

### 7.1 语义取向编码

| 编码 | 定义 | 示例判断 |
|---|---|---|
| positive | 明确正向评价、赞许、能力肯定或合作倾向 | responsible, constructive, innovative |
| negative | 明确负向评价、风险、威胁、失败或道德指责 | aggressive, coercive, controversial |
| neutral | 主要为事实描述，无明显评价 | bilateral, regional, annual |
| ambivalent | 同一语境中包含正负混合或转折 | rising but risky |
| irrelevant | 自动提取结果与目标对象没有真实评价关系 | 误提取、跨句错误 |

### 7.2 评价维度编码

| 维度 | 定义 |
|---|---|
| capacity | 能力、效率、实力、技术、治理能力 |
| morality | 道德性、正当性、诚信、责任 |
| legitimacy | 法律、制度、国际规则、授权 |
| threat_risk | 威胁、风险、不稳定、安全问题 |
| development | 发展、增长、现代化、基础设施 |
| cooperation | 合作、伙伴关系、多边机制 |
| conflict | 冲突、竞争、对抗、制裁 |
| identity | 文明、文化、民族、身份边界 |

### 7.3 框架编码

| 框架 | 核心问题 |
|---|---|
| security_frame | 是否把对象建构为安全威胁或稳定因素？ |
| economic_frame | 是否围绕贸易、增长、投资和发展解释对象？ |
| geopolitical_frame | 是否把对象放入大国竞争、联盟和地区秩序？ |
| moral_frame | 是否强调责任、道德、伤害、公正或不公？ |
| governance_frame | 是否强调制度、治理、规则、合法性？ |
| humanitarian_frame | 是否强调平民、人权、灾难、援助？ |
| technology_frame | 是否强调科技能力、创新、监控、AI 或数字基础设施？ |

## 8. 验证与质量控制

### 8.1 自动处理验证

至少抽样验证四类结果：

1. source merging accuracy：来源机构合并是否正确。
2. country identification accuracy：国别候选是否正确。
3. extraction precision：形容词、短语、搭配是否真实关联目标词。
4. semantic coding accuracy：语义韵候选是否与人工判断一致。

当前项目已有 `research_tool.py review`、`06_review`、`07_reports` 和 `validation_report.xlsx`，应把它们作为正式研究流程的一部分，而不是附属功能。

### 8.2 人工编码一致性

如果有两名以上编码者：

1. 先共同编码 50 到 100 条样本。
2. 讨论分歧并修订编码本。
3. 再独立编码正式样本。
4. 报告 Cohen's kappa 或 Krippendorff's alpha。

如果只有一名编码者：

1. 至少进行两轮间隔复核。
2. 保留修改记录。
3. 报告抽样复核比例和主要错误类型。

### 8.3 误差分类

建议在复核表中使用以下 error_type：

1. source_merge_error。
2. country_error。
3. target_match_error。
4. pos_tagging_error。
5. extraction_error。
6. context_window_error。
7. polarity_error。
8. frame_coding_error。
9. duplicate_or_reprint。

## 9. 项目功能与研究环节映射

| 项目功能 | 研究环节 | 研究级解释 |
|---|---|---|
| LexisNexis DOCX 拆分 | 语料库构建 | 把原始新闻文档转换为可分析语料 |
| TXT/DOCX/PDF/CSV 导入 | 通用语料构建 | 支持新闻、论文、政策、访谈、社媒等多类型文本 |
| 来源统计 | 语料描述 | 描述来源结构、样本构成和潜在偏向 |
| 机构合并 | 元数据清洗 | 将同一来源、机构、作者或平台的不同写法规范化 |
| 国别识别 | 分组变量构建 | 支持跨国来源比较，但需复核 |
| 通用元数据映射 | 分组变量构建 | 支持学科、体裁、平台、作者群体、时间阶段等比较维度 |
| KWIC | 定性语境阅读 | 检查目标词真实语境和解释证据 |
| Adjectives | 评价资源发现 | 捕捉修饰性、判断性和态度性表达 |
| Phrases | 词块与命名模式 | 捕捉固定表达、标签和短语框架 |
| Collocates | 搭配模式 | 发现目标词周围的重复共现环境 |
| SemanticProsodyCandidates | 语义韵候选 | 提供积极/消极/混合线索 |
| GroupComparison | 分组比较 | 比较不同来源或时期的话语模式 |
| review templates | 人工复核 | 将自动输出转化为可审计证据 |
| validation_report | 方法透明度 | 报告准确率、误差和研究限制 |
| run_config.json | 可复现性 | 记录参数、版本、输入和输出 |

## 10. 平台模块架构

### 10.1 数据导入层

支持多来源文本进入同一套语料结构：

1. LexisNexis DOCX。
2. 普通 TXT / DOCX。
3. OCR 后 PDF 文本。
4. CSV / Excel 文本列。
5. JSON / JSONL。
6. 网页文本或社交媒体导出。
7. 访谈转写文本。

### 10.2 语料管理层

提供统一的 corpus registry：

1. corpus_id。
2. corpus_type。
3. document_id。
4. source metadata。
5. time metadata。
6. group metadata。
7. cleaning log。
8. version log。

### 10.3 分析层

保留当前项目已有强项，并扩展为通用分析能力：

1. KWIC / concordance。
2. frequency list。
3. collocation。
4. adjectives / modifiers。
5. phrases / lexical bundles。
6. semantic prosody candidates。
7. group comparison。
8. time comparison。
9. corpus subset comparison。

### 10.4 解释编码层

不同研究场景使用不同 coding schema：

1. 新闻/政策：frame_code、evaluation_dimension、polarity。
2. 学术论文：research_move、stance_marker、contribution_type。
3. 访谈：theme_code、speaker_position、narrative_function。
4. 翻译：error_type、shift_type、evaluation_shift。
5. 企业文本：legitimacy_strategy、risk_frame、responsibility_claim。

### 10.5 复核验证层

所有自动输出都应能进入人工复核：

1. 抽样模板生成。
2. 人工编码字段。
3. 准确率统计。
4. 一致性统计。
5. 错误类型统计。
6. 方法限制自动摘要。

### 10.6 报告导出层

面向论文、课题和审计报告导出：

1. corpus profile。
2. method summary。
3. data dictionary。
4. validation report。
5. key pattern tables。
6. KWIC evidence appendix。
7. coding book。
8. reproducibility package。

## 11. 论文/报告结构建议

### 第一章：研究问题与背景

说明研究对象、语料场景、理论意义和现实意义。

### 第二章：文献综述

建议按以下顺序组织：

1. 研究对象所属领域文献，例如新闻话语、政策传播、学术写作、社媒舆论、翻译研究。
2. CADS 与语料库辅助研究。
3. KWIC、搭配、语义韵和词块研究。
4. 评价理论、框架分析、内容分析或主题分析。
5. 自动文本分析的可复现性和验证问题。

### 第三章：数据与方法

说明语料来源、检索策略、预处理、目标词、分析指标、编码体系、人工复核和验证流程。

### 第四章：总体语料与来源分布

报告来源机构、国家、时间段、文章数、词数和目标词命中情况。

### 第五章：搭配、语义韵与评价资源

围绕高频搭配、修饰语、短语和 KWIC 证据，分析目标对象如何被评价。

### 第六章：框架与来源差异

比较不同来源、机构、国家、平台、学科、体裁或时间阶段的话语框架/主题类别。

### 第七章：讨论

把语言模式放回相应制度、专业规范、平台机制、知识生产、组织目标和社会语境中解释。

### 第八章：结论与限制

总结发现，报告方法限制、自动化误差、样本限制和后续研究方向。

## 12. 最小可行研究实施路线

### 阶段一：研究对象定题

产出：

1. 明确研究对象。
2. 明确目标词列表。
3. 明确时间范围。
4. 明确来源范围。
5. 明确比较维度。

### 阶段二：语料库构建

产出：

1. 原始 DOCX。
2. 拆分后的 TXT 语料。
3. source_counts.xlsx。
4. merged_sources.xlsx。
5. run_config.json。

### 阶段三：候选模式发现

产出：

1. KWIC。
2. Adjectives。
3. Phrases。
4. Collocates。
5. SemanticProsodyCandidates。
6. GroupComparison。

### 阶段四：人工编码与验证

产出：

1. source_country_review.xlsx。
2. modifier_semantic_review.xlsx。
3. review_annotations.xlsx。
4. validation_report.xlsx。
5. method_limitations.md。

### 阶段五：解释与写作

产出：

1. 高频模式表。
2. 典型 KWIC 证据表。
3. 框架分布表。
4. 来源差异表。
5. 方法章节。
6. 研究发现章节。

## 13. 后续功能升级建议

### 高优先级

1. 为每篇文章生成稳定 article_id。
2. 把 article_id 升级为通用 document_id。
3. 在所有输出表中保留 document_id、date、source_merged、group_label、corpus_type。
4. 增加通用语料导入器，支持 TXT、DOCX、PDF OCR、CSV/Excel 文本列。
5. 增加 metadata mapping 配置，允许用户自定义分组字段。
6. 增加归一化频率字段，例如每万词频次。
7. 支持按时间段分组的 GroupComparison。
8. 在 GUI 复核模式中加入 polarity、appraisal_type、frame_code、theme_code 等可配置字段。

### 中优先级

1. 增加目标词变体管理，例如别名、缩写、大小写、复数。
2. 增加不同语料类型的项目模板。
3. 增加通讯社/转载识别字段。
4. 增加共现网络导出。
5. 增加典型 KWIC 自动抽样。
6. 增加编码本模板导出。
7. 增加平行语料和对齐语料支持。

### 低优先级

1. 自动主题模型。
2. 大模型辅助摘要。
3. 自动框架分类。

这些可以作为辅助功能，但不应替代当前项目的核心优势：可复核的语料库辅助话语证据链。

## 14. 最终研究级标准

一个真正研究级的项目，应达到以下标准：

1. 理论上明确：语料库方法负责发现模式，具体领域理论负责解释意义，评价理论、框架分析、内容分析或主题分析负责连接局部语言资源与中观解释类别。
2. 数据上透明：语料来源、采集方式、纳入排除标准、样本规模和元数据清楚可查。
3. 方法上可复现：所有参数、版本、输出和人工修正都有记录。
4. 解释上可复核：关键结论必须有 KWIC、原文语境和编码依据。
5. 结果上可比较：不同来源、国家、时间阶段的差异建立在归一化指标和人工复核基础上。
6. 限制上诚实：自动识别、词性标注、国别判断、语义韵候选和框架编码都报告误差来源。

如果按这个方案推进，本项目可以从“文本处理工具合集”升级为一个可用于论文、课题、内容审计和可发表研究的综合语料研究平台。新闻语料只是第一条成熟路线，学术论文、政策文本、社交媒体、访谈、翻译、教材和组织文本都可以成为同一平台上的研究对象。
