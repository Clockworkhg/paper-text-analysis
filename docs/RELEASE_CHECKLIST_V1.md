# v1.0 RC Release Checklist(CADS Workbench 1.0.0-rc1)

逐项通过后才能宣布 RC READY。任何一项失败 → 明确列出 RC BLOCKERS。

## 测试与回归

- [ ] full pytest(源码模式,offscreen)全绿
- [ ] clean-env 验证:新 virtualenv 仅声明依赖 → pytest → build → exe 可运行
- [ ] py_compile 全部源码
- [ ] source GUI E2E(fresh project:Hub→新建→导入→sanity→分析→复核→证据→写作→导出→重开恢复)
- [ ] source GUI E2E(existing project:systemic_competitor 副本,11k KWIC)
- [ ] packaged GUI E2E(exe:--version / --smoke-project / runner / 分析发布)
- [ ] new project E2E(packaged 或 source,同上 fresh 流程)
- [ ] existing project E2E(packaged smoke)
- [ ] transactional failure E2E(发布失败回滚,Phase 2B.1 套件)
- [ ] CLI regression(project init/import/sanity/analyze/review/freeze/report 全绿)

## Windows 现实场景

- [ ] 中文路径(研究项目/中欧媒体话语/)全链可用
- [ ] 空格与括号路径可用
- [ ] WPS/Excel 锁定工作簿:发布失败安全回滚 + 用户可理解提示
- [ ] read-only 项目目录:错误信息友好,不裸 PermissionError
- [ ] DPI 100% / 125% / 150% 布局无崩坏
- [ ] 1366×768 保存的窗口布局在 1920×1080 恢复不入屏外(clamp)
- [ ] 非 ASCII 内容(中文项目名/章节/Claim)JSON / Markdown 无乱码(UTF-8)

## 隐私与遥测

- [ ] diagnostics 包不含语料正文 / KWIC / Evidence 备注 / Writing 文本(自动断言)
- [ ] 无 telemetry / analytics / crash upload(代码审计)
- [ ] 日志不写入语料正文;滚动策略生效(1MB×10)
- [ ] recent projects 不含研究内容,Remove 不删除项目文件

## 产品完整性

- [ ] 正式项目 421-file byte baseline 前后一致(只读 smoke)
- [ ] legacy GUI(cads-gui-legacy)最小启动 smoke
- [ ] 版本对齐:VERSION == pyproject == gui_next.VERSION == About == --version
- [ ] 构建元数据(build_meta.json)进入 About / 日志 / 诊断,一致
- [ ] 发行包内容审计:无 tests/.git/.zcode/研究数据;含 README.txt/LICENSE/docs
- [ ] 启动性能:Launcher 即时;open 11k 项目 <10s 且 Overview 先渲染
- [ ] 关闭生命周期:运行中提示 / PUBLISHING 禁止退出 / 写作防抖落盘
- [ ] release notes + known limitations 与实际行为一致

签署:Phase 4B 收尾报告中逐项给出 ✓/✗ 与证据位置。
