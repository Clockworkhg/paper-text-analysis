# 论文文本分析工具集

这是一个面向新闻/论文语料处理的 Python 工具集，包含 LexisNexis DOCX 拆分、来源机构统计、机构合并与国别识别、目标词修饰语提取、词性标注/翻译、KWIC 分析等功能。

## 主要入口

- `integrated_app.py`：集成式 Tkinter 图形界面，适合日常操作。
- `pipeline.py`：命令行全流程串联脚本，适合批处理。
- `LexisWordToTxt/main.py`：Lexis DOCX 转 TXT 子工具入口。
- `shared/`：归一化、读写表格、手工规则、Wikidata 查询等共享模块。
- `tests/`：基础规则与归一化测试。

## 环境准备

建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果要使用修饰语提取功能，还需要安装 spaCy 英文模型：

```powershell
python -m spacy download en_core_web_sm
```

## 运行方式

启动集成 GUI：

```powershell
python integrated_app.py
```

运行全流程命令行：

```powershell
python pipeline.py -i corpus.docx -o output -t "China; India"
```

常用参数：

- `--skip 3,4`：跳过指定步骤。
- `--only 1,2`：只运行指定步骤。
- `--force`：已有输出时强制重跑。
- `--no-country`：关闭联网国别推断。

## 测试

```powershell
python -m pytest
```

项目已配置 `pytest.ini`，会自动把项目根目录加入导入路径，并关闭 pytest 缓存写入，避免 Windows 权限环境下的 `.pytest_cache` 问题。

## 目录说明

```text
.
├── integrated_app.py              # 集成 GUI
├── pipeline.py                    # 全流程命令行
├── config.py                      # 流程配置 dataclass
├── shared/                        # 共享工具模块
├── LexisWordToTxt/                # DOCX 转 TXT 子模块
├── tests/                         # 单元测试
├── requirements.txt               # Python 依赖
├── pytest.ini                     # pytest 配置
└── .gitignore                     # 忽略生成文件和本地配置
```

## 注意事项

- `tldextract` 的缓存默认写入项目内 `.cache/tldextract`，也可以用环境变量 `TLDEXTRACT_CACHE` 指定位置。
- 生成结果建议输出到 `output/` 或 `outputs/`，这些目录默认不会纳入 git。
- `.idea/`、`__pycache__/`、`.pytest_cache/` 等本地文件已被忽略。
