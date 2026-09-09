# GUI Design System(gui-next · Phase 4A)

本文档是 gui-next 视觉与结构的**唯一规范**。新增界面必须复用本文的令牌与
组件,禁止再创造第六套组件风格。令牌实现于 `gui_next/theme.py`,组件实现于
`gui_next/widgets.py`,状态词汇实现于 `gui_next/status.py`。

## 1. 设计令牌(Tokens)

| 令牌 | 值 | 用途 |
|---|---|---|
| BG | `#F6F7F9` | 应用背景 |
| SURFACE | `#FFFFFF` | 卡片 / 表格 / Inspector |
| TEXT | `#20242A` | 正文 |
| MUTED | `#68707D` | 次要文字、说明 |
| BORDER | `#DDE1E7` | 全部边框 |
| PRIMARY | `#315E8A` | 唯一主色(主按钮、选中、强调) |
| SELECTED | `#EAF1F8` | 选中行背景 |
| SUCCESS / WARNING / ERROR | `#267A57` / `#A86916` / `#B33A3A` | 语义色 |
| WARNING_BG / ERROR_BG / INFO_BG | `#FBF3E6` / `#F9ECEC` / `#EDF2F8` | 横幅底色 |

规则:页面代码不得出现裸十六进制颜色;动态配色一律经 `status.role_color()`
或 theme 常量。派生色(WARNING_BG 等)只存在于 theme。

## 2. 字体(Typography)

字体栈:`"Segoe UI", "Microsoft YaHei UI"`(Windows 自带,不引入字体依赖)。

| 层级 | 规格 | objectName |
|---|---|---|
| Page Title | 24px / 600 | `#PageTitle` |
| Page Purpose | 13px / MUTED | `#PagePurpose` |
| Section Title | 16px / 600 | `#SectionTitle` |
| Body / Table | 13px | 默认 |
| Metadata | 12px | `#ContextChip` 等 |
| Caption(大写小标) | 11px / 600 / MUTED | `#InspectorSectionCaption`、`#StatLabel` |

同一层级只允许一个规格;禁止 14/15/18 混入标题体系(Inspector heading 15px
是唯一例外,历史保留)。

## 3. 间距(Spacing)

只允许 `4 / 8 / 12 / 16 / 24 / 32`(`theme.SP_*`)。卡片内边距 16,页面
外边距 24,同组控件 8,分组之间 12–16,区块之间 24。禁止 7/10/11/13/18 等
随手值(存量违规已在 Phase 4A 清理)。

## 4. 圆角 / 边框 / 阴影

- 圆角统一 `6px`(`theme.RADIUS`);
- 层级靠 spacing + border + surface 建立,卡片用 1px BORDER 轻边框;
- 阴影只允许出现在真正浮层(toast、dialog、menu);主工作区不用阴影。

## 5. 按钮(Toolbar 层级)

| 层级 | 样式 | 每页数量 |
|---|---|---|
| Primary | `#Primary`(蓝底白字) | **最多 1 个**(Corpus=Recheck、Analysis=New Analysis Run、Review=开始/继续、Evidence=New Claim、Writing=New Section/Export、Runs=Compare) |
| Secondary | 默认按钮 | 0–3 |
| Tertiary | `#Flat`(无边框,蓝字) / `#IconOnlyButton` | 不限 |

一排同视觉权重按钮是规范违规。

## 6. 表格(BaseTableView)

所有研究数据表(KWIC、Documents、Collocates、Phrases、Groups、Evidence、
Runs、Compare)使用 `widgets.BaseTableView`,统一:

- 行高 28、表头高 32、无编辑、行选择、可排序;
- `recordSelected(dict)` 单击/键盘/程序化选择统一发出(联动 Inspector);
- `recordActivated(dict)` 双击/Enter 发出(打开详情/文档);
- `Ctrl+C` 复制选中行(TSV 含表头);
- `set_empty_state(title, hint, action_text, action)` 空态覆盖层;
- `set_column_widths({...})` 列宽提示(每次数据更新后自动应用);
- 列顺序研究者优先(语境列先于运行元数据),内部列(Corpus_ID/Run_ID)
  不进入主视图;
- 状态禁止只靠颜色;KWIC NODE 列加粗(`KwicDelegate`),运行元数据列降灰。

## 7. 筛选(FilterBar)

`widgets.FilterBar` = 搜索框 + 类型下拉 + Clear filters + 结果计数
(`N results` / `N / M results`)。禁止页面自拼 QLabel+QComboBox。

## 8. 状态词汇(Status Vocabulary)

内部枚举固定,显示层唯一来源是 `gui_next/status.py`:

| 域 | 内部状态 |
|---|---|
| Corpus | UNKNOWN / PASS / WARNING / BLOCKED / STALE |
| Review | NOT_STARTED / IN_PROGRESS / COMPLETE / STALE |
| Evidence | VERIFIED / SOURCE_UNAVAILABLE / INTEGRITY_ERROR |
| Runs | PREPARING / RUNNING / CANCELLING / ANALYSIS_SUCCEEDED / PUBLISHING / SUCCEEDED / FAILED / CANCELLED / PUBLISH_FAILED / INTERRUPTED / RECOVERY_REQUIRED |
| Comparison | FULLY_COMPARABLE / PARTIALLY_COMPARABLE / NOT_COMPARABLE |

`status.health/review/integrity/run/comparison(state)` 返回
`(glyph, 用户文案, color role)`。UI 禁止发明 Done/Finished/Ready/OK 等同义词。
状态显示 = glyph + 文字 + 颜色(不只靠颜色,可访问性)。

## 9. 横幅(Banner)

`widgets.Banner`,`level="info" | "warning" | "error"`,常驻直到解除:

- error:Corpus BLOCKED、RECOVERY_REQUIRED、导出失败——**不得**用会消失的
  Toast;
- warning:Corpus STALE、Review STALE、Evidence integrity、Older published
  run、Partial comparability;
- info:引导性说明(如"运行第一次分析")。

## 10. 空态 / 加载 / 错误

- **EmptyState**:`发生了什么 + 下一步 + [主行动按钮]`。所有数据页必须声明
  (`view.set_empty_state(...)`);Writing 无文档、Evidence 空、Runs 空等。
- **Loading**:打开项目 = 等待光标 + 状态栏提示;分析运行 = RunPanel 不定进度
  条(诚实语义,无假百分比);大结果集显示结果计数。
- **Error**:横幅/运行面板内 persistent 呈现 + Copy diagnostics;技术
  traceback 不进主工作区。

## 11. 反馈(Toast)

成功类瞬时反馈(已加入证据、已导出、已保存)用 `widgets.show_toast`,可带
"打开文件夹"动作。错误一律 Banner/面板,禁止 Toast。

## 12. Inspector 统一结构

`inspector.InspectorPanel.show_object(object_type, heading, identity,
details, context_blocks, provenance, actions, note, badge)`:

```
OBJECT TYPE(INSPECTOR 标题行)
heading
── IDENTITY ──        命名对象的最小键值对
── DETAILS ──         指标 / 状态 / 参数
── CONTEXT / EVIDENCE ──  原始语境块(make_block)
── PROVENANCE ──      run / 指纹 / manifest
[ACTIONS]             真实按钮(Focus 可达)
[badge]               持久状态行(如 "✓ In Evidence")
```

对象类型枚举:DOCUMENT / SOURCE / KWIC / COLLOCATE / PHRASE / GROUP /
REVIEW_ITEM / EVIDENCE / CLAIM / WRITING_BLOCK / RUN / COMPARISON。
页面只允许公开 API,不得触碰内部布局。

## 13. 页面骨架(Page Header)

每页第一行 = `widgets.PageHeader`:标题 + 一行 purpose + 右侧
(secondary…primary)。页面不重复渲染全局信息(项目名 / published run /
corpus health / 执行状态属于顶部 Project Context Bar)。

## 14. 导航 / 路由

一级导航固定:概览 · 语料 · 分析 · 复核 · 证据 · 写作 | 运行记录 | 设置。
跨页跳转一律 `router.navigate_to(route, object_id, context)`(对象类路由见
`router.OBJECT_ROUTE`);会话历史支持 `Alt+←` Back;页面通过实现
`focus_object(object_id, context)` 接收定位。禁止直接操纵其他页面的控件。

## 15. 全局 Shell

顶部 Project Context Bar:项目名 · published run chip · corpus health chip ·
执行状态 · Search(Ctrl+K)· Inspector 折叠 · Sidebar 折叠。左 240px 导航;
中央 Workspace;右 340px Inspector(可折叠,Ctrl+I);底部状态栏只放瞬时消息。

## 16. 可访问性底线

- 所有 action 用真实 QPushButton(键盘可达);
- 状态 = 图标 + 文字 + 颜色三者,不只颜色;
- 表格全键盘可用(方向键 / Enter / Ctrl+C);
- 对话框不超屏,按钮不截字,中文文案完整。

## 17. 禁止清单

- 新增硬编码颜色 / 非法间距值;
- 页面私有表格 / 私有右栏 / 私有详情面板;
- QMessageBox 打断常规流程(仅破坏性确认、必要配置、显式导出、阻塞冲突);
- 假百分比进度;
- 打开项目产生任何写盘(写作文档惰性创建)。
