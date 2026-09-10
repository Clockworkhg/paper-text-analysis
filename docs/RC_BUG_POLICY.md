# RC Bug Policy(v1.0.0-rc1 起生效)

自 tag `v1.0.0-rc1` 起,项目进入 **Bugfix-only** 生命周期。本政策冻结于
RC 发布时,在 v1.0.0 正式版(Stable)之前持续有效。

## 1. 接受的修复(按优先级)

### P0 — 数据完整性(最高优先,立即修)
- 数据损坏:corpus / analysis 工作簿 / published generation / evidence /
  writing 存储丢失或被错误覆盖;
- transaction recovery failure(发布事务无法回滚到安全点)。

### P1 — 崩溃与阻塞
- 任何未处理 crash;
- 无法启动(打包 exe / 源码模式);
- 无法完成核心研究链(导入 → sanity → 分析 → 复核 → 证据 → 写作 → 导出);
- packaged analysis blocker(打包子进程无法运行分析);
- 严重的文件权限 / 路径兼容问题(只读目录、超长路径等核心场景)。

### P2 — 明显阻碍
- 明显的 UX blocker(按钮失效、布局崩坏导致无法操作);
- 文案错误导致研究语义被误解(如把候选模式表述为结论);
- 非核心兼容问题(特定显示缩放、特定路径形态)。

## 2. RC 周期明确禁止

以下一律**不实现**,记录到 `POST_V1_ROADMAP.md`:

- DOCX / PDF 导出;
- AI 能力;
- 新分析算法 / 新统计指标;
- 新 Evidence 类型 / 新 Review 类型;
- 新 Run Compare 功能;
- 新 dashboard / 新 GUI 页面;
- 功能性重构;
- 删除 legacy GUI;
- 修改 `shared/` 研究算法。

## 3. 修复纪律

每个 bug 一个独立 commit,包含:

1. 最小复现(测试优先);
2. regression test(合并进相应 tests/ 文件);
3. 最小修复;
4. 不夹带任何 feature。

修复后必须重跑:full pytest + 受影响的 packaged E2E;涉及发布/存储的修复
必须重跑 421-file 正式项目基线。

## 4. Release 分支策略

- 开发分支(`gui-next`)保留,继续进入下一阶段前不动;
- RC bug 修复在 `release/v1.0` 分支进行(从 tag `v1.0.0-rc1` 切出),
  每个 bug 独立 commit,不混 feature;
- Stable 发布时从 release 分支打 `v1.0.0` tag。

## 5. Stable Promotion Gate(v1.0.0-rc1 → v1.0.0)

满足以下全部条件方可升级为 v1.0.0,**不需要新增任何功能**:

- RC 实际使用期间无 P0;
- 所有发现的 P1 已修复并有 regression test;
- full pytest 全绿(dev + clean-venv);
- clean build 全绿;
- packaged fresh-project E2E 与 existing-project E2E 全绿;
- formal project 421-file byte baseline 全绿;
- `docs/RELEASE_CHECKLIST_V1.md` 全项通过;
- `docs/RELEASE_NOTES_v1.0-rc1.md` 的 known limitations 复核并更新。
