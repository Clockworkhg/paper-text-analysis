# gui-next:研究证据工作台(Phase 1)

`gui_next/` 是新一代 PySide6 桌面前端,按"研究证据工作台"的信息架构设计:
一级导航回答研究者的问题,而不是罗列程序功能。分析内核(`shared/`、算法、
输出定义)完全冻结;本 GUI **只读**现有项目输出,不写任何文件。

启动:

```powershell
python -m pip install -e ".[gui]"      # PySide6
python -m gui_next projects/systemic_competitor
# 或 editable 安装后: cads-gui-next <项目目录>
```

## 产品模型

```
Project → Corpus → Analysis → Review → Evidence → Writing
```

Phase 1 一级导航(自左侧 240px 侧栏进入):

| 导航 | 回答的问题 | 内容 |
|---|---|---|
| 概览 Overview | 我的研究做到哪了 | 统计卡(文档/KWIC/搭配/目标词/分组/运行)、研究流程状态表、语料污染时的 **Analysis blocked** 横幅 |
| 语料 Corpus | 数据是什么、干不干净 | Documents(登记表,双击看 Inspector)/ Sources(合并+国别+证据)/ Health(卫生检查详情) |
| 分析 Analysis | 我发现了什么模式 | 以目标词为中心:目标词列表(带命中数)→ Concordance(11k 行虚拟化表格,语境筛选)→ Collocates(MI/G²)→ Groups;搭配双击可跳回全部相关 KWIC 行(Sinclair 式互跳) |
| 复核 Review | 哪些结果需要我判断 | 各编码文件进度(百分比进度条)+ 候选条目表(只读;键盘编码在 Phase 2 接入) |
| 运行记录 Runs | 结论怎么算出来的 | 固化运行列表,双击查看 Research Run Manifest(参数、语料指纹、模型/规则/算法版本、文件哈希) |

右侧 340px **Context Inspector**:选中任何对象(文档/KWIC 行/搭配/来源/运行)
在右侧显示其详情、方法说明与原始语境,代替弹窗。底部状态栏:
项目 · 文档数 · 运行号 · 语料健康(✓/⚠/–)。

## 方法边界进入界面

- Collocates 页底部常驻:ⓘ MI / G² 用于发现和排序候选模式,不自动构成话语解释结论;
- Inspector 的 KWIC 详情注明:自动提取的语境行,最终解释需人工阅读复核;
- Sources 的国别证据面板标注:辅助变量,使用前需人工复核。

## 设计系统

学术研究软件 × 现代 IDE × 数据工作台:单主色 `#315E8A`,背景 `#F6F7F9`,
表面 `#FFFFFF`,文字 `#20242A`/`#68707D`,边框 `#DDE1E7`,语义色
Success `#267A57` / Warning `#A86916` / Error `#B33A3A`;Segoe UI +
Microsoft YaHei UI,正文 13px;间距只用 4/8/12/16/24/32;圆角 6px。
全部令牌集中在 `gui_next/theme.py`。

## 阶段规划

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | Overview / Corpus / Analysis(KWIC)/ Review 只读 + Inspector + Runs | ✅ |
| Phase 2A | **Human Review Workbench**:Source/Country 复核(证据面板 + Accept/Change/Uncertain/Exclude)、语义韵键盘编码工作台、Overview 状态拆分、语料健康状态机、写边界 `review_store.py` | ✅ |
| Phase 2B | 分析运行接入、Evidence 面板细化(Wikidata/域名/规则分级) | 待做 |
| Phase 3 | Evidence Trail(证据篮 → Claim→Pattern→KWIC→Document→Run 导出)、Run Compare、Report | 待做 |
| 收尾 | 旧 Tkinter GUI 移除(CLI 永久保留) | 待做 |

## Phase 2A:Human Review Workbench

两条人工复核写入链路,全部经 `gui_next/data/review_store.py`(唯一写边界,
原子写入 tmp+os.replace,失败不产生半写文件,不触碰语料与分析产物):

### 1. Source/Country 复核(语料 → Sources)

- 来源清单:`merged_sources.xlsx` 优先;未运行机构合并时回退登记表来源清单;
- 右侧复核面板:original / normalized / suggested country / confidence / evidence 拆分展示,
  常驻"ⓘ 国别为自动推断的辅助变量,使用前必须人工复核";
- 操作:Accept (A) / Change (C,填写国别) / Uncertain (U) / Exclude (X);
  Enter = Save & Next(修改过国别即记为 Change,否则 Accept);Shift+Enter 上一条;
  F2 国别框、F3 备注;
- 顶部显示 总数 / 已复核 / 待复核;决定写入 `06_review/source_country_review_state.json`,
  每条决定内嵌 EvidenceRef(item_type/item_id/document_id/run_id,为 Phase 3 预留)。

### 2. 语义韵复核工作台(复核页)

单条候选为中心的键盘编码界面:顶部进度 + target/candidate/document;中央大面积
KWIC/扩展语境(候选词与目标词高亮,来自工作簿 KWIC 上下文重建);编码区 +
研究备注。固定快捷键(备注框内字母数字照常输入,F2/Esc 进出):

```
1 Positive   2 Negative   3 Neutral   4 Mixed
X Exclude    U Uncertain
Enter        保存并下一条(立即生效,无确认框)
Shift+Enter  上一条
O            打开全文文档
```

候选清单来自 `06_review/modifier_semantic_review*.xlsx` 的 SemanticProsodyReview
(沿用其稳定 `review_id`),决定与备注写入 `06_review/semantic_review_state.json`;
重启后进度与光标原位恢复。

### 3. Overview 状态语义(拆分)

复核不再是一个笼统百分比,拆为:语料导入 / 语料卫生(五态)/ 来源规范化复核(x/y)/
国别复核(待复核 n 条建议;无建议时明确显示"国别推断未运行")/ 分析 / 语义韵复核
(x/y)/ 编码者调和(FINAL 与编码文件)/ 编码者信度(**显示统计量与值**,如
"Cohen's κ = 0.83 (is_correct, n=50)",无数据时明示"尚无数据",绝不把统计值表述为
方法学通过)/ 最终运行固化。

### 4. 语料健康状态机(全 GUI 统一)

```
UNKNOWN  无语料,或卫生检查未运行
PASS     检查通过、无警告、语料未变化
WARNING  检查通过但有数据质量警告
BLOCKED  存在元数据标记污染(分析门禁阻止)
STALE    检查结果已过期:语料指纹与报告不一致(旧报告回退为
         mtime/文档数比对),不得沿用旧 PASS/WARNING
```

状态显示于概览状态行、顶部横幅(BLOCKED/STALE 有专属横幅)与底部状态栏。

### 测试与写入安全

- `tests/test_gui_next_review.py`:两类决定的持久化与重启恢复、快捷键映射
  (QTest 真实按键)、Enter 精确前进一条、五态健康机、进度计算、原子写失败
  不产生半写文件;
- **写入安全保证**:所有复核操作前后,`corpus/`、`adjectives_phrases.xlsx`、
  复核工作簿原件、run_config/project.json 的字节哈希完全不变(测试与真实项目
  副本 E2E 均已验证);
- 分析内核 `shared/` 在 Phase 2A **零改动**。
