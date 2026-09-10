# CADS Workbench v1.0-rc1 Release Notes

发布日期:2026-09-10 · 基线 commit:`f24c820`(gui-v1.0-rc-base)

## What is included

- **Project Hub**:新建 / 打开项目、最近项目、研究模板向导;
- **Corpus**:语料导入(TXT / LexisNexis DOCX / CSV / Excel)、文档登记表、
  来源规范化与国别人工复核、语料健康五态门禁;
- **Analysis**:目标词中心的 Concordance / Collocates / Phrases / Groups;
- **Review**:语义韵键盘编码工作台 + 复核状态完整性(指纹溯源、STALE 语义);
- **Published Runs**:隔离执行、取消、崩溃恢复、运行审计记录(manifest、
  指纹、参数、产物);
- **Evidence Trail**:证据绑定已发布代际,Claim → Pattern → KWIC →
  Document → Published Run 全链可追溯;
- **Claims**:研究论断组织(不自动判定真假),证据多对多引用;
- **Writing Workspace**:章节 + 正文 + Claim/证据引用卡片、完整性校验;
- **Run Compare**:两个已发布运行的兼容性门禁与描述性差异;
- **Evidence Refresh**:在新发布运行中定位对应证据,由研究者决定补充或替换;
- **Markdown Export**:写作导出(Draft / Clean 双模式 + Evidence Appendix);
- **Transactional publication**:分析产物要么完整发布、要么完整回滚,
  绝不混合新旧结果。

## 当前能力细节

- **研究主链**:Project → Corpus → Analysis → Review → Evidence → Writing,
  Runs 作为可审计的执行基础设施;
- **Project Hub**:启动即用的新建 / 打开项目流程,最近项目列表(应用级状态,
  不写入研究项目);
- **New Project Wizard**:项目身份 / 研究模板 / 语料导入(TXT、LexisNexis
  DOCX、CSV / Excel)/ 分析默认值,四步创建;全部调用既有初始化与导入能力;
- **分析运行**:隔离工作副本、取消、崩溃恢复、**事务化发布**(成功或完整
  回滚,绝不混合新旧结果)、运行审计记录(Runs);
- **人工复核**:语义韵键盘编码工作台、来源国别复核、复核状态完整性
  (指纹溯源,内容变化自动 STALE);
- **证据链**:Claim → Pattern → KWIC → Document → Published Run;证据绑定
  已发布代际的 manifest 指纹;历史代际证据永久可追溯;
- **写作**:结构化章节 + 正文 + Claim/证据引用卡片,完整性校验,Markdown
  导出(Draft / Clean);
- **Run Compare**:两个已发布运行的兼容性门禁与描述性差异;
- **可审计性**:Research Run Manifest、publication manifest(allowlist 契约、
  逐文件 sha256)、Evidence 完整性三态、全局异常记录、诊断包导出。

## 已知限制(请务必阅读)

1. **主要面向英文语料**;中文语境处理未经系统验证;
2. 分析模型为 spaCy **en_core_web_sm(small)**——精度边界由模型决定;
3. **MI / G² 用于发现和排序候选模式,不自动构成话语解释结论**;
4. Semantic Prosody 结果是**候选 + 人工复核**,软件不自动判定语义韵;
5. 来源**国别为自动推断的辅助变量**,使用前必须人工复核;
6. 写作导出为 **Markdown**;本版本**无 DOCX / PDF / 引文管理**;
7. 软件**不自动撰写研究结论**;Writing 只组织证据,论断由研究者作出;
8. 运行对比的差异是**描述性**的,不直接建立实质性话语变化命题;
9. 一个窗口一次打开一个项目;分析运行中不支持后台化退出;
10. 未提供文件关联(.cadsproj 等)与安装器;当前发行形式为 onedir ZIP;
11. **无 AI 自动研究结论**;软件不代替研究者作出解释;
12. **无 telemetry / analytics / crash upload**;
11. 无 telemetry;诊断信息仅用户主动导出时生成。

## 支持环境

- Windows 10/11 x64(100% / 125% / 150% 显示缩放已验证);
- 屏幕分辨率 1366×768 起(Inspector / 侧栏可折叠);
- 中文 / 空格 / 括号路径支持。

## 数据安全声明

- 分析内核与语料文件在 GUI 全部常规操作中字节不变(自动测试以 421-file
  byte baseline 验证);
- 复核、证据、写作分别有独立写边界与原子写入;发布具备事务回滚;
- 诊断包默认**不包含**语料正文、KWIC 内容、Evidence 备注与 Writing 文本。

## 升级与兼容

- v1.0-rc1 直接打开 Phase 1–4A 创建的项目;无数据模型迁移。
