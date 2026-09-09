# 键盘快捷键(Phase 4A)

全局快捷键在 `gui_next/app.py` 统一注册(ApplicationShortcut);页面专属快捷键
属于各自页面,焦点离开页面即失效。全部快捷键以此表为准,新增能力必须先在此
登记并检查冲突。

## 全局(所有页面)

| 快捷键 | 动作 | 说明 |
|---|---|---|
| `Ctrl+K` | 全局搜索 | 搜索 Documents / Targets / Evidence / Claims / Writing sections / Runs;Enter 打开,Esc 关闭 |
| `Ctrl+S` | 保存当前可编辑上下文 | 当前页面实现 `save_context()` 时生效(写作页:立即落盘防抖中的正文编辑);无保存上下文时无操作 |
| `Ctrl+F` | 聚焦当前页面筛选框 | 页面实现 `focus_filter()` 时生效,否则打开全局搜索 |
| `Ctrl+I` | 显示/隐藏 Inspector | 折叠后中央工作区扩展;选择在会话间记忆(QSettings) |
| `Ctrl+B` | 显示/隐藏左侧导航 | |
| `Alt+←` | Back | 返回上一个导航位置(Router 历史,跨 Evidence→Run、Writing→Claim 等跳转) |
| `Esc` | 关闭临时状态 | 关闭弹层/搜索面板;在复核/来源面板中退出备注编辑框 |

## 复核 Review(语义韵编码工作台)

备注框内字母数字照常输入;以下按键在备注框外生效:

| 快捷键 | 动作 |
|---|---|
| `1` / `2` / `3` / `4` | Positive / Negative / Neutral / Mixed |
| `X` | Exclude |
| `U` | Uncertain |
| `Enter` | 保存并下一条(立即生效,无确认框) |
| `Shift+Enter` | 上一条 |
| `O` | 打开全文文档 |
| `F2` | 进入备注框(`Esc` 退出) |
| `F1` / `?` | 键盘快捷键帮助弹层 |
| `Ctrl+Z` | 撤销上一次编码/备注(跨会话可撤销) |

## 语料 Sources(国别复核面板)

| 快捷键 | 动作 |
|---|---|
| `A` | Accept |
| `C` | Change(聚焦国别输入框) |
| `U` | Uncertain |
| `X` | Exclude |
| `Enter` | Save & Next(修改过国别即记为 Change) |
| `Shift+Enter` | 上一条 |
| `F2` / `F3` | 聚焦国别框 / 备注框 |

## 分析 Analysis

| 快捷键 | 动作 |
|---|---|
| `E` | 将当前选中行加入 Evidence(Concordance / Collocates / Phrases / Groups 四表通用) |
| 双击 / `Enter` | 在 Inspector 打开选中对象的完整详情 |

## 证据 Evidence

| 快捷键 | 动作 |
|---|---|
| `N` | 新建 Claim |
| `Enter` | 在 Inspector 打开选中证据 |
| `Delete` | 删除选中证据(有引用时需确认) |
| `Ctrl+F` | 聚焦搜索框 |

## 写作 Writing

| 快捷键 | 动作 |
|---|---|
| `Ctrl+Shift+C` | 插入 Claim 引用 |
| `Ctrl+S` | 立即保存正在编辑的正文块 |
| 右键正文块 | 上移 / 下移 / Remove from Writing |

## 表格通用(所有 BaseTableView)

| 快捷键 | 动作 |
|---|---|
| `↑` `↓` | 移动选择(联动 Inspector) |
| `Enter` / 双击 | 激活行(打开详情 / 文档 / 证据) |
| `Ctrl+C` | 复制选中行(TSV,含表头) |
| 列头点击 | 排序 |
