# BUILDING — 重建 CADS Workbench v1.0 RC

本文件记录重建 v1.0-rc1 发行包所需的完整环境与步骤。目标是**依赖集合明确、
过程可重复**(不追求可执行文件 bit-for-bit 一致)。

## 1. 环境要求

| 项 | 值 |
|---|---|
| OS | Windows 10/11 x64 |
| Python | 3.13(3.10+ 应可用,以 lock 快照为准) |
| PyInstaller | 6.19.0 |
| spaCy | 3.8.x + en_core_web_sm(与 lock 一致) |

## 2. 依赖快照

重建时以 `requirements-lock.txt`(若存在)或以下命令生成快照为准:

```
pip freeze > requirements-lock.txt
```

核心 runtime 依赖(pyproject.toml):pandas、numpy、openpyxl、spacy、nltk、
rapidfuzz、requests、tldextract、matplotlib、python-docx;GUI:PySide6≥6.6;
构建:pyinstaller≥6.0。

spaCy 模型:打包前确认 `python -c "import en_core_web_sm"` 可用
(开发安装:`python -m spacy download en_core_web_sm`)。

## 3. 干净环境构建(验证性,推荐)

```powershell
python -m venv .zcode\tmp\rc_venv
.zcode\tmp\rc_venv\Scripts\python -m pip install --upgrade pip
.zcode\tmp\rc_venv\Scripts\python -m pip install -e ".[gui,build,dev]"
.zcode\tmp\rc_venv\Scripts\python -m pytest tests -q        # 全量测试
.zcode\tmp\rc_venv\Scripts\python build_exe.py --workbench  # onedir 构建
```

## 4. 构建产物

```
dist/CADS-Workbench-1.0.0-rc1/
    CADS Workbench.exe      产品入口(windowed,onedir)
    _internal/              运行时与依赖
    build_meta.json         version/commit/timestamp/mode(单一元数据源)
    docs/                   QUICKSTART、KEYBOARD_SHORTCUTS、METHODOLOGY、
                            DATA_DICTIONARY、RELEASE_NOTES
    README.txt / LICENSE
```

构建机制(`CADS-Workbench.spec`):

- entry 为 `gui_next/__main__.py`;windowed、onedir;
- hiddenimports:`gui_next.execution.runner`(子进程经
  `CADS Workbench.exe --gui-next-runner spec.json` 复用同一 exe,见
  `controller._runner_command`)、spacy、en_core_web_sm、matplotlib agg、
  tldextract 等;
- 排除 torch/tensorflow/Qt 绑定竞争版本/测试框架等;
- 不打入:tests、.git、开发截图、真实研究数据、.zcode。

## 5. 打包后验证(packaged E2E)

```powershell
# 版本元数据
"CADS Workbench.exe" --version

# 只读页面 smoke(退出码 0)
"CADS Workbench.exe" --smoke-project <项目副本>

# 分析子进程(与 GUI 同一 runner 路径)
"CADS Workbench.exe" --gui-next-runner <spec.json>
```

packaged 模式完整 E2E(Hub → 新建 → sanity → 分析发布 → 证据 → 写作 →
compare → 诊断)在源码模式自动化之上,以 exe 重复 runner/分析路径验证;
两者共享同一套冻结代码,不复制分析逻辑。

## 6. 已知构建注意点(打包 E2E 实证)

- **spaCy 模型**:必须以 data 形式打包 `en_core_web_sm` 包目录 **及其
  dist-info**(`spacy.util.is_package` 经 importlib.metadata 解析,缺
  dist-info 时 `spacy.load(name)` 报 E050)。spec 已自动处理;构建机需
  可 `import en_core_web_sm`。
- **tkinter**:分析链 `shared/pipeline_steps → modules/txt_modifier_
  extractor_gui` 顶层 `import tkinter`,因此发行包**必须包含 tkinter**
  (spec 已从 excludes 移除;不要再加回)。
- **matplotlib 后端**:runner 子进程强制 `MPLBACKEND=Agg`,并对 stdio
  强制 UTF-8(backslashreplace)——语料中的私用区字符在 GBK 管道下曾使
  子进程崩溃。
- `CADS_RUNNER_EXE` 环境变量可在开发模式把子进程指向打包 exe,用于
  跨模式验证。
- 验证命令:`"CADS Workbench.exe" --version` / `--smoke-project <副本>` /
  `--e2e-analysis <副本>`(sanity+分析+事务发布全链,硬 Gate)/
  `--gui-next-runner <spec>`。

## 7. 已知构建注意点(历史)

- windowed exe 无控制台;stdout 仅在重定向时可用(--version/--runner);
- 首次冷启动因 onedir 解压缓存稍慢;warm launch 见 RELEASE_CHECKLIST;
- 如更换 PyInstaller 大版本,必须重跑 clean-venv 全量验证。
