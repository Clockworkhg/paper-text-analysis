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

## Phase 4A:GUI Product Consolidation & UX Hardening(产品收束)

Phase 1–3C 的研究能力与数据语义冻结;Phase 4A 不新增任何分析算法、统计指标、
DOCX、AI、Evidence/Review/Compare 能力或导出格式,只做 GUI 的统一、精修与验证。
完整审计结论见 `docs/GUI_AUDIT.md`,视觉/组件规范见 `docs/GUI_DESIGN_SYSTEM.md`,
快捷键见 `docs/KEYBOARD_SHORTCUTS.md`。

### 全局 Shell

顶部 **Project Context Bar**(项目名 · published run chip · corpus health chip ·
执行状态 · Ctrl+K 搜索 · Inspector/Sidebar 折叠),左 240px 一级导航
(概览·语料·分析·复核·证据·写作 | 运行记录 | 设置),中央 Workspace,
右 340px Context Inspector(Ctrl+I 可折叠,会话记忆),底部瞬时状态栏。
全局信息只在 Context Bar 出现一次。

### 共享组件(消灭五套表格/三套横幅)

`gui_next/widgets.py`:BaseTableView(行高/列宽/单击→Inspector、双击/Enter 激活、
Ctrl+C、空态覆盖层)、FilterBar(搜索+下拉+Clear+结果计数)、EmptyState、
Banner(info/warning/error)、Toast(仅成功反馈)、PageHeader。
`gui_next/status.py` 是全部状态词的显示层(健康五态、复核四态、Evidence 完整性
三态、运行 11 态、比较三态),UI 不再发明同义词。

### 路由与全局搜索

`gui_next/router.py`:`navigate_to(route, object_id, context)` 统一跨页跳转
(对象类路由 document/kwic/evidence/claim/run/writing_section → 页面),会话
历史支持 Alt+← Back;页面实现 `focus_object` 接收定位。Ctrl+K 检索
Documents/Targets/Evidence/Claims/Writing sections/Runs(不搜 KWIC 全文)。

### 页面收束

- **Overview**:PROJECT(项目名+统计芯片)→ RESEARCH PIPELINE(九行状态,
  状态词+字形,无假百分比)→ ATTENTION(需关注清单)→ NEXT ACTION(单一
  下一步 + 主行动按钮);
- **Analysis**:修复主体挤压布局缺陷;KWIC 列序 Keyword/Left/Right 先行
  (NODE 加粗、运行元数据降灰,委托器实现);FilterBar 带结果计数;
  Add to Evidence 统一进入 Inspector actions(E 键不变);
- **Review**:键盘帮助改为 ? / F1 弹层;备注框编辑态可见;分析运行锁定
  不再引用失效控件;
- **Evidence**:Inbox 与 Claim workspace 分离(后者按 PATTERN / QUALITATIVE
  分组);统一 Inspector(OPEN RUN / supporting KWIC / Replace in Claim /
  Delete);完整性校验按 (run, manifest) 缓存;
- **Writing**:最安静页面——块控件收进右键菜单,正文第一视觉;Rail 去掉
  二级 Inspector(单点击进入全局 Inspector);无文档时空态引导,**打开项目
  不再自动写盘**(写作文档惰性创建,首个 New Section 时才生成);
- **Runs**:主表只留 Run/Date/Status/Corpus/Grouping/Targets/证据引用,
  manifest/哈希进 Inspector;Compare 仅选中两个已发布运行时可用;
  Compare 对话框带兼容性横幅。

### 审计修复(必须保持的回归)

B1 `datetime`/`store.root`(启动分析崩溃)、B2 evidence `json`/`Path` 导入、
B3 Compare `QMessageBox` 导入、B4 复核锁定 `_latest_label`、B5 证据页重复
方法/死代码、B6 分析页重复 addWidget(主体挤在左半屏)、B7 来源面板按视图
行号取对象(排序错位)、B8 打开项目即写 `09_writing`、以及 Writing Claim 卡
渲染的推导式 NameError。以上均有回归测试(`tests/test_gui_next_ux.py`)。

### 验证 Gate(Phase 4A 收尾)

1366/1440/1920/2560 offscreen 截图 + 125%/150% DPI 通过;11,105 KWIC 规模
性能 smoke(load 18ms / filter 20ms / sort 5ms,远低于 500ms 冻结线);
`tests/test_gui_next_e2e.py` 全用户故事(Overview→Corpus→Analysis→E 捕获→
Review→Claim→Writing→Runs→Compare gate→Back→全局搜索);正式项目对
Phase 3C 421-file 基线 byte-for-byte identical。

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

## Phase 2A.1:Review State Integrity

人工 review state 的完整性保证:候选集/语料/分析变化后,旧决定绝不静默套用到新的研究对象上。

### State 溯源元数据(schema v2)

state 文件(`06_review/*_review_state.json`)记录:`schema_version`、project_id/name、
run_id、`corpus_fingerprint`、`input_fingerprint`(语义韵=候选集内容指纹,来源=来源表
内容指纹)+ `input_provenance`(输入文件名与其 sha256)、`created_at`/`updated_at`。
每条决定额外记录 `item_fingerprint`(语义韵=review_id+corpus+文档+target+候选内容;
来源=来源名+原始名+建议国别)。

### 加载语义

| 情形 | 行为 |
|---|---|
| item id 一致且指纹一致 | 恢复决定 |
| id 一致但内容指纹不一致 | 该决定标记 stale,不应用 |
| 候选集内容指纹整体变化 | 未匹配项全部不应用 |
| corpus 指纹变化 | 整个 state STALE |
| 旧版 state(schema<2) | STALE,需迁移,绝不按顺序 ID 恢复 |

旧决定永远保留在 state 文件中(不计入当前进度、不覆盖当前候选),界面提示需要
reconciliation/migration(自动迁移本阶段未实现)。内容一致的候选集良性重生成
不会导致失效。

### Review 状态词汇(全 GUI 统一)

`NOT_STARTED / IN_PROGRESS / COMPLETE / STALE`,用于语义韵复核、来源复核
(Overview 状态行、工作台横幅、来源面板进度条)。

### Reconciliation 与 Reliability 解耦

编码者调和只反映文件事实(FINAL/编码文件存在与否);信度只展示 IRR 表中的实际
Metric/Value/n,无值时只写"尚无数据/报告尚未生成",二者互不推断。

### 单写者保护(轻量,乐观并发)

save 前比对 state 文件当前哈希与本实例记住的哈希;不一致(另一实例已写入)则拒绝
覆盖并抛出明确错误,原文件完整;`reload()` 拉取对方更改后可继续。

### Undo

Ctrl+Z 撤销最近一次编码/备注修改(恢复 decision、note、cursor、progress 一致);
操作历史持久化于 state 文件(上限 50 条),跨会话可撤销。

### 测试

`tests/test_gui_next_state_integrity.py`:溯源元数据、同 id 不同内容不恢复、
corpus 变化 → STALE、良性重生成不失效、旧版 state 迁移、四态词汇、stale 不计入
进度、调和/信度解耦、双实例冲突拒绝且原文件完整、Ctrl+Z 一致性、全部复核操作
期间语料/分析/复核工作簿字节不变。

## Phase 2B:Analysis Execution(分析运行)

分析不重写 pipeline,而是由执行层(`gui_next/execution/`)安全调用现有 shared 工作流,
并产品化为**可审计、可取消、不覆盖旧结果**的任务生命周期。

### 执行架构

- `events.py` 生命周期状态机:`IDLE → PREPARING → RUNNING → (CANCELLING →) SUCCEEDED / FAILED / CANCELLED`,崩溃恢复补充 `INTERRUPTED`;
- `runner.py` 子进程入口(`python -m gui_next.execution.runner spec.json`):在**隔离工作副本** `runs/work_<run_id>/` 上调用 `project_analyze`(冻结 Python API),stdout 逐行输出 JSON 事件;sanity 任务直接组合 shared 只读检查函数、按传入目录执行;
- `controller.py` QProcess 驱动(QObject,UI 线程零阻塞):复制工作副本 → 启动子进程 → 流式日志 → 成功后**发布**(仅分析产物拷回项目根;`06_review/*_state.json` 永不发布)→ 记录运行日志;
- `jobs.py` 运行日志(`runs/gui_runs.json`)、写者锁、崩溃恢复、工作副本构建;
- **工作副本重定向**:副本的 project.json `project_dir` 指向副本自身,保证 `project_analyze` 全部写入落在副本内;发布时改写回真实路径。

### New Analysis Run

分析页 "＋ New Analysis Run" → 页内配置视图(非直接启动):targets / group_by / MI 阈值 / POS+翻译(可选)/ sanity 门禁,全部来自现有 shared/CLI 能力;流水线固定值(窗口 8 tokens、短语 ≤6)只读展示;左列显示 Current project defaults,右列 New run parameters;启动前给出完整 summary。

### Sanity 门禁

| Health | 行为 |
|---|---|
| PASS | 允许运行 |
| UNKNOWN | 禁止运行;GUI 内一键运行 sanity |
| WARNING | 显示摘要,允许运行(与 shared 行为一致) |
| BLOCKED | 禁止运行 |
| STALE | 禁止运行,必须重新 sanity |

Advanced 区提供 `--skip-sanity` 同级逃生口,固定警告"跳过卫生检查会降低研究结果可靠性,不建议用于正式研究";UNKNOWN 状态不提供该逃生口。

### 隔离、取消与恢复

- FAILED / CANCELLED:工作副本原地保留(现场不删),项目根既有成功结果**字节不变**;
- Cancel:CANCELLING(诚实显示"正在等待当前步骤安全结束……")→ 子进程 terminate → 10s 后 force kill → CANCELLED;
- 单写者:`runs/analysis_writer.lock`,第二个分析写任务被拒绝并给出提示;分析运行期间复核写入锁定(workbench/来源面板禁用编码按钮并显示 🔒 提示);
- 崩溃恢复:启动时扫描 journal 中 active 但进程已死的运行 → 标记 INTERRUPTED("Previous application session ended before this run completed."),保留日志与工作目录;
- 错误 UX:FAILED 显示阶段、异常类型、消息、日志(View log)、参数、工作目录与 Copy diagnostics;
- Runs 页区分 success / failed / cancelled / interrupted / frozen,显示 run id、起止时间、group_by、targets 数、语料指纹、产物可用性。

### Result freshness

分析成功发布后自动刷新 Analysis/Overview/Runs;Corpus Health 保持事实状态;候选集因重生成而变化时,旧 Review state 经 2A.1 指纹机制自然进入 STALE(绝不手工删除)。复核绑定调和后 FINAL 工作簿时,分析不会使其失效(调和产物不受重生成影响)。

## Phase 2B.1:Transactional Publication Integrity

分析运行的发布具备事务语义:任何 publish error / crash / stale output 都不会形成
"新旧结果混合"的伪成功状态。

### 生命周期拆分

`ANALYSIS_SUCCEEDED`(子进程 exit 0)→ `PUBLISHING`(事务进行中)→ `SUCCEEDED`
(事务 COMMITTED);失败进入 `PUBLISH_FAILED`。**子进程退出码 0 不等于正式项目
已获得新结果**;Runs 页与日志可区分 "Analysis succeeded" 与 "Publication failed"。

### Publication Manifest(allowlist 契约)

分析完成后先构建 manifest,不允许直接递归复制。manifest 记录 run_id、
corpus_fingerprint、params_hash、previous_published_run_id、generated_at、
逐文件 relative_path/sha256/size/category、files_to_remove 与 excluded 清单。

Owned-output 契约是 **allowlist**(工作簿/运行配置/登记表/国别表/复核模板/报告
逐路径列明):corpus 原文、review state、源码、runs 内其他运行内容、project.json
一律不在清单内——不是"排除几个已知文件"的黑名单。路径安全校验拒绝绝对路径、
`..`、越契约路径。

### 防陈旧:最小工作副本 + produced diff

工作副本只复制运行输入(corpus、project.json[重定向]、merged_sources、
group_overrides),**不复制上一轮分析产物**;runner 在分析前后对工作副本做文件集
diff,只有本轮真实产生的文件才可能进入 manifest——手工放入工作副本的旧文件永远
不会被发布。

### 事务提交与回滚

`PREPARE`(manifest 校验+逐文件哈希)→ `BACKUP`(旧 owned outputs 复制入
`runs/pub_<run_id>/backup`)→ 写 publication journal → `COMMITTING`(逐项
os.replace + 过期 owned output 删除,全部可回滚)→ `COMMITTED`(清理 staging/
backup,保留 manifest 与 journal)→ 运行才标记 SUCCEEDED。任一步失败 →
ROLLBACK:已替换文件从备份恢复、本轮新建文件删除——**要么完整新 generation,
要么完整旧 generation**。

`project.json` 不在发布文件集内:身份/配置字段绝不覆盖;COMMITTED 后由执行层
做字段级合并(仅追加 analyze 历史与刷新 analysis-owned latest 指针)。

### 崩溃恢复

启动时扫描 `pub_*/journal.json` 中 state=COMMITTING 的事务,自动
ROLLBACK_TO_PREVIOUS_GENERATION;无法恢复时标记 RECOVERY_REQUIRED 并禁止新的
分析发布,直至完整性解决。journal、backup、work dir、diagnostics 一律保留。

### 已发布身份(为 Phase 3 Evidence→Run 预留)

COMMITTED 后写入 `runs/published_analysis.json`:
published_run_id / manifest_sha256 / corpus_fingerprint / params_hash /
completed_at。Overview 的"当前结果"芯片与该指针——而不是"项目根恰有哪些
xlsx"——回答"当前展示的结果来自哪次运行"。

### Sanity adapter parity

GUI sanity 与 shared/CLI 使用同一组检查函数(不允许出现第二套健康算法);
parity 测试对同一项目比对 document count / failure counts / ok 判定,完全一致。

### Development note — project_dir 写穿事故(Phase 2A.1 期间)

- **原因**:`project_analyze` / `project_sanity` 均以 project.json 内的
  `project_dir` 字段定位项目根,而非传入路径。Phase 2B 前的工作副本/离线
  sanity 未重定向该字段,导致一次自动化验证把 sanity 报告与一条 history 写入
  正式项目 `projects/systemic_competitor`。
- **影响范围**:仅新增 1 个报告文件与 1 条 history;语料、分析工作簿、
  run_config、复核工作簿经哈希核对**完全未受影响**。
- **恢复**:删除报告文件、过滤 history 条目、语义校验通过(project.json 仅
  `updated_at` 时间戳漂移,属良性)。
- **防回归**:①工作副本构建时强制重定向 project_dir(jobs.make_work_dir);
  ②sanity 任务不再经 project_sanity,直接按传入目录组合 shared 检查函数
  (runner.run_sanity_job);③controller 全路径不再透传用户目录给写操作;
  ④Phase 2B.1 起发布只允许契约内路径;⑤相关单元测试与真实项目副本 E2E
  覆盖上述每一条。

## Phase 3A:Evidence Trail Core(研究论证链)

CADS Workbench 从"可以分析和复核"升级为"可以建立可审计研究论证链"。核心链路:

```
Claim → Pattern → KWIC / Context → Document → Published Run
    → Corpus / Parameters / Publication Manifest
```

任何证据只绑定**已 COMMITTED 的已发布代际**(`runs/published/<run_id>/`),绝不依赖
"项目根当前最新文件";RUNNING/FAILED/CANCELLED/INTERRUPTED 等状态的结果可浏览诊断,
但不得作为正式证据来源。

### Evidence 数据模型(独立写边界)

`gui_next/data/evidence_store.py` 是唯一 Evidence 写入口,数据存于
`08_evidence/evidence.json`(schema v1、原子写入、乐观单写者冲突检测、溯源元数据)。
EvidenceStore 不属于分析 owned outputs——**publication 永不覆盖或删除它**。

EvidenceRecord:稳定 `evidence_id`(UUID)、evidence_type、published_run_id、
publication_manifest_hash、corpus_fingerprint、parameters_hash、document_id、target、
locator(行号仅辅助)、item_fingerprint、captured_snapshot(研究者当时看到的完整语境
快照——第二层审计保障)、researcher_note、created_at/updated_at。

支持的四种类型:KWIC(左语境/节点/右语境/来源/国别/分组)、COLLOCATE_PATTERN
(target×collocate、频次、MI、G²、窗口——MI/G² 是模式证据,不自动构成统计证明)、
PHRASE_PATTERN、GROUP_PATTERN(分组变量/组/观察值,不自动生成社会科学结论)。

幂等去重:同一 `published_run_id + evidence_type + item_fingerprint` 只有一条记录;
同一 Evidence 可被多个 Claim 引用而不复制。

### Claim 语义

ClaimRecord:title / claim_text / researcher_note / evidence_ids[] / 时间戳。Claim 是
**研究者提出的研究论断**,GUI 只组织证据,不做 Supported/Proven/True 判定,不生成
措辞。支持新建/编辑/删除/重排;同一 Evidence 服务多个 Claim;删除 Claim 不删除
Evidence;删除被引用的 Evidence 会被拒绝并提示引用数。

### 历史代际语义(与 Review STALE 的本质区别)

发布 COMMITTED 时归档 `runs/published/<run_id>/`:publication_manifest.json +
artifacts/(分析工作簿、登记表、语料清单、run_config、研究模板、方法报告——每个
产物带 sha256)。发布 Run #015 后,来自 Run #014 的证据**仍然是
VALID HISTORICAL EVIDENCE**(界面显示 Older published run),绝不自动失效或升级。
只有三种情况标记异常:SOURCE_UNAVAILABLE(归档缺失)、INTEGRITY_ERROR(manifest
哈希或产物哈希不匹配)、以及指纹不匹配;解析永远优先读取对应历史代际,**绝不静默
回退到当前最新运行**。

### 捕获与工作台

- 分析页:`Add to Evidence`(按钮/E 键)作用于 Concordance、Collocates、Phrases、
  Groups 四个表;Inspector 同步显示 `✓ In Evidence`;需要已发布代际,否则明确拒绝。
- 证据页:左 Inbox/Claims 树,中证据表(类型/运行/自由文本过滤,Ctrl+F),右
  Inspector(完整语境 + RUN PROVENANCE 块 + [Open Run] 双向导航)。
- Claim workspace:按 STATISTICAL/PATTERN 与 QUALITATIVE/KWIC 分组展开;Pattern 类
  证据可 View supporting KWIC——打开的是**该证据绑定代际**的 KWIC,选中后
  "Add supporting KWIC"加入同一 Claim。
- 最小导出:Export Claim Evidence Packet(Markdown,严格来自 EvidenceRecord,
  审计/调试用途;正式报告导出属 Phase 3B)。
- Runs 页显示每代际的"证据引用"数;Evidence → Run 双向可达。

## Phase 3B:Evidence-aware Writing Workspace(研究写作工作台)

产品链条正式完成:Project → Corpus → Analysis → Review → Evidence → **Writing**。

### Writing 数据模型(独立写边界)

`gui_next/data/writing_store.py` 是唯一 Writing 写入口,数据存于
`09_writing/writing.json`(schema v1、原子写入、乐观单写者冲突检测、溯源元数据)。
WritingStore 不属于分析 owned outputs——publication 永不覆盖它。

结构:Writing Document → Sections(稳定 `sec_` id、层级 parent_id、排序)→ Blocks。
Block 四类:

| 类型 | 存储 | 渲染 |
|---|---|---|
| PROSE | 研究者文本 | 可编辑段落(native undo、debounce 自动保存) |
| CLAIM_REF | claim_id(引用,非复制) | Claim 卡片:标题/文本/evidence 数/Runs,自动反映 Claim 修改 |
| EVIDENCE_REF | evidence_id(引用,非复制) | Evidence 卡片:指标从 EvidenceRecord + 已发布代际实时重读 |
| RESEARCH_NOTE | 研究过程备注 | 标注 Private research note;Clean 导出排除 |

**证据数字脱钩纪律**:Writing 只存 evidence_id,不存 "MI=4.81" 等独立数值。
渲染/导出时:Writing → EvidenceStore → Historical Generation → 校验 → 显示。
半年后仍能回答:这个 4.81 来自哪个 Run、哪个 corpus、哪套参数、哪个 manifest。

### Integrity Preflight

`Validate Evidence`(整个文档或当前 Section):所有 CLAIM_REF 递归检查其引用的
EvidenceRecord,汇总 VERIFIED / SOURCE_UNAVAILABLE / INTEGRITY_ERROR /
MISSING_REFERENCE 计数,并支持定位到具体 Section/Block。

### 破损证据处理

SOURCE_UNAVAILABLE 时仍显示 captured_snapshot 并标注 ⚠;INTEGRITY_ERROR 时显示
✕ 且不得绿色渲染;不回退 latest run;不自动修改研究者 prose。

### Older Run 不是错误

引用 Run #014 而当前已 #017:仍然 ✓ Verified (Older published run)。Inspector
显示 Current analysis vs Evidence source。是否升级到新 run 由研究者决定,本阶段
无自动刷新。

### Markdown 导出(双模式)

- **Draft**:完整溯源 + Private research notes(可选);有完整性问题时也记录警告。
- **Clean**:精简证据表示 + [EVD-NNNN] 引用编号 + Evidence Appendix(ID/类型/
  target/Document ID/Source/Published Run/manifest hash/corpus fingerprint/
  integrity;Pattern 含指标,KWIC 含短语境);有完整性问题时**必须**在文件顶部
  写入 "WARNING: Evidence integrity issues are present.",不得静默生成看似正常的正式稿。
- 导出前自动运行 Integrity Preflight。

### 其他

- Claim/Evidence 可在多章节引用(Section→ID 关系,不在 Claim 上存 section);
  同一条 KWIC 属于 Claim A、Claim B,并出现在 Findings 和 Discussion,均引用
  同一 EvidenceRecord。
- 双向导航:Writing Claim block → Open Claim → Evidence → Open Run → Runs 页
  (显示证据引用数)。
- 编辑体验:QPlainTextEdit(native undo/copy/paste)、Ctrl+S、800ms debounce
  自动保存、冲突时提示 "Writing document changed in another session" + Reload。
- 删除 Section 有确认;删除 Block 仅解除写作引用;Claim/Evidence 本体的删除仍由
  Evidence 页规则控制。
- 无 AI 自动写作;无 DOCX;无 Run Compare。

## Phase 3C:Published Run Compare & Evidence Refresh

### Run Compare

Runs 页 "Compare Published Runs" 按钮:仅允许比较 COMMITTED 的已发布代际;
比较通过 Historical Generation Resolver 读取归档产物,不从项目根读取。

兼容性三级门禁:
- FULLY_COMPARABLE:corpus fingerprint、document count、target set、group_by、
  MI threshold、algorithm/rules version 全部一致
- PARTIALLY_COMPARABLE:部分参数不同但核心维度仍有交集
- NOT_COMPARABLE:corpus + algorithm 同时变化或目标词零交集

比较输出:Documents/KWIC/Collocates/Phrases 计数、Targets(added/removed/changed/
unchanged + delta%)、Document Mapping(EXACT_ID / CONTENT_MATCH / METADATA_MATCH /
AMBIGUOUS / UNMATCHED)、Compatible Pattern Delta(ΔMI/ΔG²)。所有变化仅为描述性
(增/减/出现/消失),不自动解释话语含义。

可导出 Comparison Markdown(Run A/B 溯源 + 兼容性 + 目标差异 + 文档映射摘要)。

### Evidence Refresh

Evidence 页 "Check against newer run":在较新已发布代际中寻找对应证据,发现
CANDIDATE_MATCH 后可选择 Add as additional evidence(自动链接 lineage
UPDATED_COUNTERPART),或 Replace in Claim(修改 Claim 引用关系,旧证据保留)。

Evidence lineage(`evidence_links`)记录 source/target/relationship/
comparison_run_pair;第一阶段仅支持 UPDATED_COUNTERPART 和 RELATED。
Evidence Refresh Audit Markdown 可导出(方法审计,非论文正文)。

**永不自动升级**:发布新 Run 后,旧 Evidence 仍为 Verified Historical Evidence,
Claim/Writing 不自动变化,选择权完全在研究者。

## 阶段规划

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | Overview / Corpus / Analysis(KWIC)/ Review 只读 + Inspector + Runs | ✅ |
| Phase 2A | **Human Review Workbench**:Source/Country 复核(证据面板 + Accept/Change/Uncertain/Exclude)、语义韵键盘编码工作台、Overview 状态拆分、语料健康状态机、写边界 `review_store.py` | ✅ |
| Phase 2B | 分析运行接入(执行层/生命周期/隔离/取消/崩溃恢复) | ✅ |
| Phase 2B.1 | 事务化发布(manifest 契约/备份回滚/崩溃恢复/发布身份/sanity parity) | ✅ |
| Phase 3A | Evidence Trail Core(证据捕获/Claim 工作台/历史代际解析/完整性校验) | ✅ |
| Phase 3B | Evidence-aware Writing Workspace(结构化写作/证据卡片/Markdown 导出/Appendix) | ✅ |
| Phase 3C | Published Run Compare & Evidence Refresh(兼容性门禁/目标差异/文档映射/证据刷新) | ✅ |
| Phase 4A | GUI Product Consolidation & UX Hardening(App Shell/共享组件/Router/空态/审计修复/性能与安全 Gate) | ✅ |
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
