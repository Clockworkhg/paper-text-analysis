# POST_V1_ROADMAP(v1.0 之后的功能候想池)

Phase 4B 纪律:RC 阶段发现的功能请求一律**记录在本文件,不实现**。
此列表不代表承诺,仅防止范围蔓延并保留方向记忆。

## 写作与输出

- DOCX 导出(带样式映射)、PDF 导出;
- 引文管理器(Zotero/BibTeX)集成;
- 写作模板库与自定义样式。

## 分析与研究能力

- 中文语料的分词与语境处理验证;
- 更大 spaCy 模型(en_core_web_md/lg)作为可选依赖;
- 新统计指标与效应量;
- 语义韵 reconciliation / migration 的 GUI 化(当前仅状态提示);
- Country 推断的在线(Wikidata)能力公开化 + 明确的联网确认 UI。

## 平台与分发

- Consider repository rename to `cads-workbench` at v1.0 Stable (RC release
  URLs, tag and doc references are stable for now; renaming is a
  Stable-era decision, not an RC one).

- 安装器(MSI/NSIS)、代码签名、自动更新通道;
- 文件关联(.cadsproj);
- onefile 构建优化;
- macOS / Linux 打包评估。

## 协作与规模

- 多项目库视图;
- 项目归档/恢复工具;
- 更细粒度的可靠性(IRR)报告 UI。

## 已知内部债

- `_review_progress` 全工作簿解析的增量缓存;
- Inspector heading 15px 并入字号体系;
- packaged 模式的启动耗时进一步剖析(cold/warm 拆分)。
