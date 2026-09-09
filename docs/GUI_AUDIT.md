# GUI Audit(Phase 4A 起点)

日期:2026-09-09。审计方式:**offscreen 实际运行** gui-next(项目副本
`projects/systemic_competitor` → 1440×900 与 1366×768 逐页截图,存
`.zcode/tmp/audit_shots/`)+ 全量源码走读。研究内核与数据语义冻结;本文档
只描述 GUI 现状问题,作为 Phase 4A 收束工作的依据。

## 0. 运行时缺陷(截图运行中发现,必须先修)

| # | 位置 | 问题 | 触发条件 |
|---|---|---|---|
| B1 | `app.py _start_analysis` | `datetime` 未 import;`self.root` 不存在(应为 `self.store.root`) | 启动任何 New Analysis Run → NameError |
| B2 | `evidence_page.py` | `json`、`pathlib.Path` 均未 import;`_refresh_table` 对每条证据调 `json.dumps` | 证据箱 ≥1 条记录 → NameError(页面崩) |
| B3 | `pages.py RunsPage._open_compare` | `QMessageBox` 未 import | <2 个成功运行时点 Compare → NameError |
| B4 | `review_workbench.py set_locked` | 引用不存在的 `self._latest_label` | 分析运行期间锁定复核 → AttributeError |
| B5 | `evidence_page.py` | `_pointer`/`_check_newer_run`/`_replace_in_claim` 各定义两次,前份成死代码;`_integrity_for` 含 `if False` 死代码;文件尾孤立 `Signal` import | 维护性/正确性风险 |
| B6 | `pages.py AnalysisPage.__init__` | `body.addWidget(targets_card)` 与 `body.addWidget(self.tabs)` **各执行两次**(L408/446、L411/447) | 分析页整体挤在左侧 ~500px,右侧 2/3 空白(截图 02_分析*.png) |
| B7 | `source_review_panel.set_index` | 表格排序后 `index.row()` 不再等于 `review_store.items` 顺序,面板显示错条目 | Sources 表点击列头排序后点行 |
| B8 | `writing_store.new_document` | 打开项目即写 `09_writing/writing.json`(GUI 打开≠用户创建文档) | 对正式项目只读 smoke 与 421-file Gate 冲突;必须惰性创建 |
| B9 | `models.py sort` + 各页 | `sort()` 原地重排 df,视图行↔df 行隐式耦合;唯一稳定的对象 id(`document_id`/`evidence_id`)没有标准化取行 API,Sources 面板因此错位(B7),后续任何"排序后取行"的新调用都会重蹈 | 结构性风险 |

B6 直接破坏核心页面;B1/B2/B3/B4 是潜伏崩溃;B8 阻塞正式项目安全 Gate。
全部在 Phase 4A 第一批修复。

## 1. App Shell / 全局

**现状**:240px 侧栏(QListWidget 7 项)+ 中央 QStackedWidget + 340px 固定
Inspector + 底部状态栏。无顶部 Project Context Bar;项目名/文档数/当前
run/健康度只出现在状态栏一行小字。无 global search;无 navigation history;
Inspector 不可折叠(340px 在 1366 宽下中央仅剩 ~780px);侧栏不可折叠;
"打开项目…"按钮孤悬侧栏底部;无 Settings/Tools 归宿(旧 Tkinter 工具不在
本 GUI,导航也无处安放未来 Utilities)。

**问题**:全局信息(执行状态、corpus health、published run)每页各自为政:
Overview 用 stat chip + callout,状态栏一行,Analysis gate 里又一份 health。
Inspector 固定 340px 不可收起。导航顺序 = 开发顺序,Runs 挤在 Writing 之后,
没有"研究主链 / 基础设施"分层。

## 2. Overview

- 目的:研究首页。现状=项目名 + 6 个 stat chip + 研究流程 9 行文本 + 条件横幅。
- **缺 ATTENTION / NEXT ACTION 区块**;未回答"下一步做什么"(仅无分析时一条提示)。
- stat chip 把配置值(`分组=source`)当统计;`当前结果 –` 语义未解释(无
  published pointer 时应引导运行分析)。
- 流程行使用 ✓/○/⚠ 字形,offscreen 下成 tofu(Windows 正常);状态词
  UNKNOWN/STALE 等内部枚举直接裸露,无用户友好文案映射。
- 右侧 Inspector 全程空白,浪费 340px;Overview 是唯一不用 Inspector 的页面,
  却也没把空间让给内容。
- 复核进度 `0/24`、`0/50` 无单位说明(24 来源/50 候选)。
- 无 loading:打开项目时 KWIC(11k 行)/工作簿同步读,UI 冻结无提示。

## 3. Corpus

- Documents:表列宽默认挤压(`urce_normalize`、`rd_count_appr` 截断);
  `stretchLastSection` 让 `target_hits_total` 独占近半宽;单击不更新 Inspector
  (仅双击);无筛选/搜索;198 行无计数显示;无导出。
- Sources:复核面板嵌在 tab 内右侧,与全局 Inspector 并存形成"第二右栏";
  面板的证据框固定拉伸占 ~400px 高,内容 3 行,大量空白;进度行 `总数 24 ·
  已复核 0 · 待复核 24` 无 STALE 时隐藏细节;B7 排序错位;决策按钮 4 个同权重。
- Health:几乎全空的巨大卡片 3 行文字;空态让用户去 CLI 跑 sanity,但 GUI
  的 New Analysis Run 配置页明明有"运行 Sanity 检查"能力——同一能力两处入口、
  互相不指引;无"检查历史/最近检查时间"结构化展示。
- 无页面 purpose 行;无 primary action(建议:Import/Recheck corpus)。

## 4. Analysis(含 KWIC 专项)

- **B6 布局破坏**:中央 tabs 挤在左半屏,tab 栏出现 ◄► 溢出箭头。
- 目标词列表带命中数(好),但选中目标后 KWIC 表列顺序为
  `Source, Source_Normalized, Group, Date, Target, Left_Context…`——研究者的
  Left/Node/Right 在水平滚动最右侧,首屏看不到任何语境(截图 02_分析_kwic_row)。
  Collocates 表先显示 `Corpus_ID/Run_ID/Document_ID` 等内部列,MI/G² 在最右。
- Inspector:KWIC 详情结构好(NODE 徽标 + FULL CONTEXT + kv);但单击不联动,
  只有双击;四类结果(Concordance/Collocates/Phrases/Groups)的 Add to Evidence
  位置在页头(固定)而非 Inspector(与其余 action 冲突)。
- `Add to Evidence (E)` 与 `＋ New Analysis Run` 并列页头,主行动不突出;
  E 键走 eventFilter 依赖 `id(obj)` 映射, tab 顺序耦合。
- 语境筛选只有 Concordance 有;Collocates/Phrases/Groups 无 filter/search;
  无结果计数;11,105 行 KWIC 全量 set_dataframe + 每键 Filter 全表
  str.contains——性能待测(#37)。
- 方法边界注释(ⓘ MI/G²…)常驻底部一行,位置合理,但字形在部分环境 tofu。
- New Analysis Run 配置页结构良好(defaults vs params 两列、gate、summary),
  但与 RunPanel、normal view 用 `QStackedWidget` 切换无返回路径提示
  (`back_requested` 信号无人连接——Back 按钮无效,潜伏 UX bug)。
  > 验证:`RunConfigView.back_requested` 在 app.py/_wire_run_panel 中未连接。

## 5. Review

- 工作台以单候选为中心,结构正确(进度/target/candidate/context/coding/note)。
- 无页面标题与 purpose;进入页面即 0/50 但无"这页是干什么的"说明。
- `set_locked` 崩溃(B4);STALE banner 为黄色文字行,非统一 banner 组件。
- 快捷键提示常驻底部一整行文字;spec 要求 Keyboard help 弹层。
- 备注框进入编辑态无明显视觉(仅默认 :focus 边框)。
- `document_id` 显示 `doc_f08dca691060` 但无来源标题/日期上下文(Inspector
  未联动)。

## 6. Evidence

- 空态 = 纯白表格,无引导(spec #13 违反)。
- 页头 4 按钮同权重(Check newer / Replace in Claim / Export packet / +New Claim),
  违反 toolbar 层级(#6);`Replace in Claim` 在无 counterpart 时点了才报错,
  应弱化为 Inspector 内 action。
- Claim workspace 与 Inbox 共用同一张表+表头文字,无视觉分区(#23);
  PATTERN EVIDENCE / QUALITATIVE EVIDENCE 未在表中分组。
- Integrity 列每行调 `resolver.integrity()`(重算 manifest 哈希),无缓存,
  记录多时每键筛选都全量重算(性能风险)。
- Inspector 布局:先 show_kwic 再把 RUN PROVENANCE 块 `insertWidget(0,…)`,
  私闯 `_body_layout` 内部;动作行是 QLabel 假链接,无按钮语义/焦点。
- B2 崩溃、B5 重复方法;`_export_packet` 用 QFileDialog+QMessageBox(可,
  但无"打开文件夹"反馈,spec #36)。
- 快捷键 N/Enter/Delete/Ctrl+F 用 QShortcut 挂 page,与写作页 Ctrl+Shift+C
  无冲突;`Delete` 直接删除证据需确认(有)。

## 7. Writing

- 打开即自动建文档(B8);首次进入默认渲染 "–" 空标题,中央大片空白无空态。
- 三栏:Sections 树 / 中央 blocks / Rail(Claims|Evidence|Inspector)——Rail
  的 "Inspector" tab 与全局 Inspector 形成两套详情面板(#4 冲突)。
- 按钮密度高:页头 3 按钮 + 底部 4 按钮 + 每张 block 卡 3 控件(↑/↓/Remove),
  prose 是第一视觉主体的目标未达成(#24);block 卡片边框重。
- `+ Research Note`/`Insert Evidence` 等同权重排;`Insert Evidence` 弹 ID 列表
  选择器(裸 evidence_id,研究者不可读)。
- `_render_section` 每次全部重建;800ms debounce 双定时器(textChanged 连了
  timer.start 又连 `_on_prose_changed`,后者只设 `_pending_edit`——保存路径
  能工作但绕)。
- `open_button` "Open Claim" 只 navigate 到证据页,不选中对应 Claim(导航
  不带对象上下文,#26 的典型缺口)。

## 8. Runs

- 表列 `run_id/kind/status/started/finished/group_by/targets/corpus_fp/output/
  证据引用/note`——中英文列名混用;corpus_fp/output 属技术细节,应进 Inspector
  (#25);`status` 已做友好映射("✓ success")。
- **Compare 按钮永远可用**,选中 0/1 个 published run 时点击才弹提示
  (且触发 B3 NameError);应默认禁用+说明(#25)。
- 无页面 purpose;Compare 按钮全宽横条视觉突兀;Inspector 仅 frozen run 有
  manifest 详情,GUI 运行只有一行文字。
- 冻结运行(current/frozen)与 GUI 运行同表混排,kind 列区分,可接受但
  需要视觉分组。

## 9. Run Compare(对话框)

- QDialog + QTextBrowser 渲染 HTML 表格,信息完整但:_export_compare 后
  QMessageBox;无 Esc 提示;无兼容性级别的视觉分级(FULLY/PARTIALLY/NOT);
  document mapping 与 pattern delta 已实现但未展示(仅 overview+targets);
  900×640 固定尺寸在 1366×768 下接近满屏。

## 10. 跨页面共性问题汇总

1. **表格五套体验**:Documents/Sources(共享 `_table`)、Analysis 四 tab
   (`_setup_table` 重复实现)、Evidence(手写)、SupportingKwicDialog(复用
   `_table`)——无统一 BaseTableView:列宽策略、单击/双击语义、Ctrl+C、
   Enter、context menu、空态、计数各行其是;列宽默认挤压+末列拉伸是通病。
2. **Inspector 两套半**:全局 InspectorPanel + Sources 复核面板 + Writing Rail;
   全局 Inspector 还被 Evidence 页直接操作内部布局。
3. **Banner 三种**:Overview callout(QSS)、Review STALE(黄字 QLabel)、
   Writing preflight(普通 QLabel);无统一 Warning/Error/Info 层级。
4. **反馈三套**:QMessageBox(15+ 处)、Inspector badge、状态栏——无 Toast/
   统一 notification;导出完成无"打开文件夹"。
5. **硬编码颜色**:16 处 inline `setStyleSheet(f"color: {theme.X}…")` 分散
   6 个文件(theme 色板本身集中,但写法散落,改版即漏);Callout 背景
   #FBF3E6/#F9ECEC 硬编码在 QSS 之外。
6. **字体/字号**:QSS 定 PageTitle 24/SectionTitle 16/正文 13,但
   `InspectorHeading` 15、Health 标题 15、Review context 14、StatValue 20、
   brand 11——同一层级多套尺寸;`app.setFont(QFont("Segoe UI", 9))` 9pt≈12px
   与 QSS 13px 混用。
7. **间距**:12/16/24 为主,但 Review header 用 24 横距、Writing blocks 10px、
   Inspector actions 6px、sidebar margin 12——10/6/7 等随手值存在。
8. **空态**:Evidence、Writing(未选节)、Documents(无语料时)、Compare(无
   运行时)全部是空白面板;无一处有"发生了什么+下一步"。
9. **Loading**:完全没有——打开 11k KWIC 项目、Compare 读取两代归档、
   Evidence integrity 校验都是同步阻塞主线程,无任何指示。
10. **导航**:页面间只有 `navigate(key)`(切 sidebar 行);E→Evidence 后不
    选中该证据;Open Claim 不选中 Claim;无 Back/breadcrumb;Compare→Evidence
    不可达。
11. **快捷键**:Review 1/2/3/4/X/U/Enter/O、Sources A/C/U/X、Analysis E、
    Evidence N/Enter/Delete/Ctrl+F、Writing Ctrl+Shift+C——分散实现,无全局
    表;Ctrl+F 仅 Evidence;Ctrl+S 仅 Writing;无 Ctrl+K。
12. **可访问性**:动作行用 QLabel 假链接(无 Tab 焦点);表格全键盘可用但
    Enter 语义不统一;状态大量仅靠颜色(决策按钮 active 态只有边框色)。

## 11. 分辨率快查(1366×768 截图)

- 1366 下 Inspector 340 + 侧栏 240 → 中央 760px,KWIC/文档表可用但列更挤;
  无折叠手段,无法改善。
- 无超屏对话框;按钮未截字(1440/1366 均可);中文渲染正常(需显式字体回退,
  见 B4 审计注释——offscreen 需加载 msyh,真实 Windows 无此问题)。

## 12. Phase 4A 工作项导出(编号供实施引用)

1. 修 B1–B9;
2. App Shell:顶部 Project Context Bar(项目名/published run/corpus health/
   执行状态/Ctrl+K),导航收束为主链+Runs+Settings,Inspector 可折叠
   (Ctrl+I,session 记忆),Router(navigate(route, object_id, context)+
   session history+Back);
3. 共享 primitives:BaseTableView、FilterBar、EmptyState、Banner(Info/
   Warning/Error)、Toast、ErrorPanel、StatusVocabulary(单一映射源);
4. 页面重构:Overview dashboard(PIPELINE/ATTENTION/NEXT ACTION)、Analysis
   修布局+KWIC 列序+四 tab 统一 Inspector action、Review 键盘帮助弹层、
   Evidence 空态+claim workspace 分区、Writing 降噪、Runs 列精简+Compare
   门控;
5. 全局快捷键表 + docs;
6. 分辨率/DPI/perf smoke/视觉回归/集成 E2E + 421-file Gate。
