# CADS Workbench 快速开始(面向第一次使用者)

本指南面向**使用 CADS Workbench 桌面软件**的研究者,不需要命令行或 Python 知识。

## 0. 启动

双击 `CADS Workbench.exe`(Windows)。

第一次启动会显示欢迎界面(New Project / Open Existing Project)。

## 1. 创建项目(New Project)

向导四步:

1. **Project identity**:项目名称与保存位置;
2. **Research template**:研究模板(新闻语料 news_lexis、政策、学术、访谈、
   社交媒体、翻译、通用),模板决定导入字段解释与输出结构;
3. **Corpus source**:选择语料文件夹(TXT / LexisNexis DOCX)或 CSV / Excel
   表格;也可以先创建空项目,之后再导入;
4. **Analysis defaults**:目标词(分号分隔)与默认分组。

创建完成后自动打开项目。向导**不会**自动开始正式分析。

## 2. 打开已有项目(Open Existing Project)

选择项目目录(含 `project.json` 的文件夹)。最近打开的项目会显示在启动页,
路径失效会标注 Missing(可从列表移除,不会删除项目文件)。

## 3. 界面导览

| 区域 | 内容 |
|---|---|
| 顶部 | 项目名、已发布运行、语料健康、全局搜索(Ctrl+K)、Inspector/侧栏折叠 |
| 左侧 | 研究主链导航:概览 → 语料 → 分析 → 复核 → 证据 → 写作;下方运行记录与设置 |
| 中间 | 当前页面 |
| 右侧 | Context Inspector:选中任何对象显示详情、方法说明与原始语境 |

## 4. 语料健康(Sanity)

分析前需要通过语料卫生检查。路径:分析 → New Analysis Run → 运行 Sanity 检查;
或 语料 → Health。语料 BLOCKED(如正文含元数据标记污染)时必须用干净原始
文档重新导入。

## 5. 运行分析(New Analysis Run)

分析 → **New Analysis Run** → 设置目标词 / 分组 / MI 阈值 → Start Analysis Run。
运行过程显示阶段与日志,可取消。成功后结果**事务化发布**,写入运行记录;
失败或取消不影响既有结果。

## 6. 人工复核(Review)

复核页以单条候选为中心:阅读语境后按 `1/2/3/4` 编码(Positive / Negative /
Neutral / Mixed),`X` 排除,`U` 不确定,`Enter` 保存并下一条。语料 → Sources
提供来源国别人工复核。进度与状态见概览。

## 7. 收集证据(Evidence)

分析页四类结果(Concordance / Collocates / Phrases / Groups)中选中一行,
按 `E` 或 Inspector 中 "Add to Evidence"。证据页可将证据组织进 Claim
(研究论断),支持 Check against newer run 比对新旧已发布运行。

## 8. 写作(Writing)

写作页创建章节,插入正文、Claim 引用与证据卡片。证据数字从对应已发布代际
实时读取(脱钩纪律:半年后仍能追溯每个数值的来源)。支持 Validate Evidence
完整性校验与 Markdown 导出(Draft / Clean 双模式)。

## 9. 运行记录(Runs)

所有 GUI 分析运行的审计记录:参数、语料指纹、状态、产物与证据引用数。
选中两个已发布运行可 Compare(兼容性三级门禁)。

## 10. 数据保存在哪里?

- **研究项目**:项目文件夹内(`corpus/`、分析工作簿、`06_review/`、
  `08_evidence/`、`09_writing/`、`runs/published/` 等);
- **应用状态**(最近项目、窗口布局):用户应用数据目录,不写入研究项目;
- **日志**:`%APPDATA%\CADSWorkbench\logs\`;
- 诊断信息仅在你主动导出时生成(设置 → Export Diagnostics),默认不含
  语料正文与研究内容。本软件**无 telemetry**。
- 本软件不替代系统备份;请定期自行备份项目文件夹。

## 更多

- 键盘快捷键:帮助菜单 / docs/KEYBOARD_SHORTCUTS.md
- 方法论与边界:帮助菜单 / docs/METHODOLOGY.md
- 已知限制:docs/RELEASE_NOTES_v1.0-rc1.md
