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
| Phase 1 | Overview / Corpus / Analysis(KWIC)/ Review 只读 + Inspector + Runs | ✅ 本分支 |
| Phase 2 | 分析运行接入、Source/Country Review(证据面板 + 接受/修改)、语义韵键盘编码(1/2/3/4 + Enter) | 待做 |
| Phase 3 | Evidence Trail(证据篮 → Claim→Pattern→KWIC→Document→Run 导出)、Run Compare、Report | 待做 |
| 收尾 | 旧 Tkinter GUI 移除(CLI 永久保留) | 待做 |

测试:`tests/test_gui_next.py`(无头 offscreen);数据层一律只读,
复用 `shared/` 的文件布局约定但不调用任何会写文件的接口。
