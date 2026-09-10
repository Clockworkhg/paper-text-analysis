# CADS Workbench

[English](README.md) | 简体中文

**语料库辅助话语研究工作台（Corpus-Assisted Discourse Studies Research Workspace）**

CADS Workbench 是一款运行于 Windows 的桌面研究软件，面向语料库辅助话语研究
（Corpus-Assisted Discourse Studies, CADS）：导入新闻语料，运行可复现的语言
分析，人工复核候选结果，把证据组织为研究论断（Claim），并在完整溯源之下完成
写作——全部在一个应用程序内完成，无需安装 Python。

Windows x64 · v1.0.0-rc1（Release Candidate 候选版本） · MIT License · 无需安装 Python

**[下载 Latest RC](https://github.com/Clockworkhg/paper-text-analysis/releases)** ·
[快速开始](docs/QUICKSTART_GUI.md) ·
[Release Notes](docs/RELEASE_NOTES_v1.0-rc1.md) ·
[English](README.md)

下载文件：`CADS-Workbench-1.0.0-rc1-win-x64.zip` — 完整解压后运行
`CADS Workbench.exe`。

---

## 研究工作流 Research Workflow

```
语料 Corpus → 分析 Analysis → 复核 Review → 证据 Evidence → 论断 Claim → 写作 Writing → 运行比较 Run Compare
```

每一次分析结果都会发布为不可变的 **Published Run（已发布运行）**，附带完整
manifest（语料指纹、参数、逐文件哈希）。证据（Evidence）绑定到该代际——因此
即使在多年之后，写作中的任何一个数字仍然可以追溯到它的来源。

## 为什么是 CADS Workbench

- 它不只是生成统计表——自动结果是**候选证据**，不是最终结论
- 分析结果固化为可审计的 **Published Run**
- 证据绑定到具体的已发布代际，并带有当时捕获的语境快照
- 研究论断（Claim）与写作始终可以追溯到其背后的 KWIC 行、模式与运行
- 可以比较新旧运行，但**不会**静默替换旧证据
- 人工复核（语义韵、来源/国别）在设计上就是工作流的一部分

## 主要功能

- **Project Hub（项目中心）** — 新建/打开项目、最近项目列表、四步新建向导
  （研究模板、语料导入、分析默认值）
- **语料 Corpus** — LexisNexis DOCX / TXT / CSV / Excel 导入、文档登记表、
  来源与国别人工复核、语料健康（sanity）门禁
- **KWIC / Concordance（索引行/语境一览）** — 以目标词为中心的语境检索、
  筛选与语境查看
- **搭配 Collocates** — 基于窗口共现的候选排序（MI / G²）
- **短语 Phrases** — 修饰短语与词束候选
- **分组比较 Group Comparison** — 跨来源、机构、国别或自定义组比较模式分布
- **来源/国别复核 Source / Country Review** — 对规范化名称与推断国别的
  人工复核，证据就地展示
- **语义韵复核 Semantic Prosody Review** — 面向语义韵候选的键盘编码工作台
- **Published Runs（已发布运行）** — 可审计的执行历史：取消、崩溃恢复、
  事务化发布
- **证据链 Evidence Trail** — 把 KWIC/模式捕获为证据，绑定到它来源的
  已发布代际
- **研究论断 Claims** — 把证据组织为研究论断（多引用、完整性校验、
  系统不自动判定真假）
- **写作 Writing** — 章节化工作区，含研究论断/证据引用卡片
- **运行比较 Run Compare** — 两个已发布运行之间的兼容性门禁比较
- **Markdown 导出** — 带证据附录的研究草稿（draft 与 clean 两种模式）

## 快速开始

1. 下载并**完整解压** `CADS-Workbench-<version>-win-x64.zip`
2. 双击 **`CADS Workbench.exe`**（无需安装 Python）
3. **New Project（新建项目）** — 跟随四步向导（名称、研究模板、语料、目标词）
4. **导入语料** — LexisNexis DOCX、TXT 文件夹或 CSV/Excel
5. 运行 **sanity（语料健康）检查**，然后 **New Analysis Run（新建分析运行）**
6. **复核**编码候选，收集**证据**，组织为**研究论断**
7. 在**写作**页使用实时证据卡片撰写，并**导出** Markdown 草稿
8. 随时关闭并重新打开——项目与最近列表都会恢复

完整用户指南见 [docs/QUICKSTART_GUI.md](docs/QUICKSTART_GUI.md)。
更偏好命令行？经典 CLI 仍然可用——见
[docs/WORKFLOW.md](docs/WORKFLOW.md)。

## 数据安全与可复现性

- 分析执行与正式发布分离：只有发布事务完整提交后，新结果才成为正式
  Published Run——失败会完全回滚，绝不出现“半新半旧”
- 证据绑定到不可变的已发布代际，可追溯至语料指纹、分析参数、发布 manifest、
  文档/KWIC/模式溯源
- 自动输出是候选证据，不是最终解释；人工复核在设计上就是工作流的一部分
- 无 telemetry、无 analytics、无 crash upload。诊断信息仅在用户主动导出时
  生成，且不包含语料正文与研究内容
- 应用程序不修改你的语料；所有写入都有明确边界，具备原子保存与回滚
- 本软件不替代系统备份——请自行定期备份项目文件夹

## 方法边界 Methodological Boundaries

- MI / G² 用于**模式发现与排序**——它们本身不构成显著性证明或话语结论
- 语义韵候选需要**人工复核**
- 来源/国别推断是**辅助变量**，必须人工确认
- 自动统计不能替代对语境的细读
- CADS Workbench **不会**自动生成实质性的话语研究结论

以上边界与
[docs/METHODOLOGY.md](docs/METHODOLOGY.md)
及 [Release Notes](docs/RELEASE_NOTES_v1.0-rc1.md) 保持一致。

## 已知限制 Known Limitations

完整清单见 [Release Notes](docs/RELEASE_NOTES_v1.0-rc1.md)。要点：

- **当前主要面向英文语料**
- NLP 模型：spaCy `en_core_web_sm`（small 模型，精度受模型规模限制）
- MI / G² **不是“结论显著性证明”**
- 语义韵（semantic prosody）候选需要人工复核
- 国别（country）标签需要人工确认
- 写作导出为 Markdown；暂无 DOCX/PDF
- **当前没有 AI 自动写结论或自动论文写作**
- **当前不完整支持中文 NLP 分析**：界面、路径、项目名、研究论断与写作支持
  中文；核心 NLP 分析目前主要面向英文语料
- 一个窗口一次打开一个项目；无文件关联；以目录 ZIP 形式发行（暂无安装器）

## 仓库结构（面向贡献者）

| 路径 | 用途 |
|---|---|
| `gui_next/` | **当前** PySide6 研究工作台（CADS Workbench 产品本体） |
| `shared/`、`modules/`、`LexisWordToTxt/` | 冻结的分析管线（导入、提取、分组、复核产物） |
| `research_tool.py` | 统一 CLI（`cads`） |
| `pipeline.py` | **Legacy** 兼容 CLI |
| `integrated_app.py` | **Legacy** Tkinter GUI（`cads-gui-legacy`） |
| `docs/` | 产品、方法学与工程文档 |
| `tests/` | 测试套件（单元、GUI、E2E） |

构建说明：[docs/BUILDING.md](docs/BUILDING.md)。
发布检查清单：[docs/RELEASE_CHECKLIST_V1.md](docs/RELEASE_CHECKLIST_V1.md)。

## 许可证 License

MIT — 见 [LICENSE](LICENSE)。
