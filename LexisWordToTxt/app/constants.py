# app/constants.py
from pathlib import Path
import re

SETTINGS_FILE = Path("settings.json")
RECENT_RUNS_MAX = 20

USER_CANONICAL_MAP_FILE = Path("source_map.json")
USER_NOISE_KEYWORDS_FILE = Path("source_noise.json")

# 下面两坨大字典/列表：
DEFAULT_SOURCE_CANONICAL_MAP = {
    # Reuters
    "Reuters": "Reuters",
    "Reuters UK": "Reuters",
    "Reuters News": "Reuters",

    # Associated Press
    "Associated Press": "Associated Press",
    "Associated Press News": "Associated Press",
    "AP": "Associated Press",
    "AP News": "Associated Press",
    "Associated Press International": "Associated Press",

    # AFP
    "Agence France-Presse": "AFP",
    "Agence France Presse": "AFP",
    "AFP": "AFP",

    # Bloomberg
    "Bloomberg": "Bloomberg",
    "Bloomberg News": "Bloomberg",

    # BBC
    "BBC": "BBC",
    "BBC News": "BBC",
    "BBC World Service": "BBC",

    # Deutsche Welle
    "Deutsche Welle": "Deutsche Welle",
    "Deutsche Welle World": "Deutsche Welle",
    "DW": "Deutsche Welle",

    # Financial Times / WSJ / Economist
    "Financial Times": "Financial Times",
    "FT": "Financial Times",
    "The Wall Street Journal": "The Wall Street Journal",
    "Wall Street Journal": "The Wall Street Journal",
    "WSJ": "The Wall Street Journal",
    "The Economist": "The Economist",
    "Economist": "The Economist",

    # US major
    "The New York Times": "The New York Times",
    "New York Times": "The New York Times",
    "NYT": "The New York Times",
    "The Washington Post": "The Washington Post",
    "Washington Post": "The Washington Post",
    "Los Angeles Times": "Los Angeles Times",

    # UK / EU
    "The Guardian": "The Guardian",
    "Guardian": "The Guardian",
    "Politico": "POLITICO",
    "POLITICO": "POLITICO",

    # Cable / Networks
    "CNN": "CNN",
    "CNN International": "CNN",
    "NBC News": "NBC News",
    "CBS News": "CBS News",
    "FOX News": "FOX News",
    "Fox News": "FOX News",

    # Others commonly seen
    "Al Jazeera": "Al Jazeera",
    "Al Jazeera English": "Al Jazeera",
    "Nikkei": "Nikkei",
    "Nikkei Asia": "Nikkei",
    "South China Morning Post": "South China Morning Post",
    "SCMP": "South China Morning Post",
}

DEFAULT_NOISE_KEYWORDS = [
    # Lexis 检索/缩窄提示
    "Narrowed by",
    "Search Terms",
    "Search Type",
    "Results",
    "Documents",
    "Job Number",
    "Date and Time",

    # Lexis/平台字段（有些会出现在“来源”行里）
    "Delivered by",
    "Link to the original story",
    "Load-Date",
    "Language:",
    "Document-Type:",
    "Publication-Type:",
    "Section:",
    "Byline:",
    "Dateline:",
    "Length:",
    "Copyright",

    # 聚合/分发平台（常见出现在 SOURCE 列表里）
    "LexisNexis",
    "Newstex",
    "Newstex Blogs",
    "Blogs",
    "ProQuest",
    "Factiva",
]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DATE_LINE_RE = re.compile(rf"^{MONTHS}\s+\d{{1,2}},\s+\d{{4}}\b", re.IGNORECASE)
APP_TITLE = "Lexis DOCX → TXT 批量转换工具 v1.0"

USAGE_TEXT = """使用说明：

1）在 LexisNexis 导出新闻时，请导出为 Word（.docx），并确保文档里包含分隔标记 “End of Document（不需要特意检查，一般都会包含 | 提示：如果导出的 DOCX 不含 “End of Document”，程序无法正确拆分文章。）”
2）打开本软件：
   - 点击【选择 DOCX 文件】选择 Lexis 导出的 .docx
   - 点击【选择输出文件夹】选择你要保存 txt 的位置
3）点击【开始处理】
4）输出结果：
   - 每篇新闻会生成一个 .txt 文件
   - 默认用“标题”命名（自动处理 Windows 非法字符），若重名会自动加序号

可选项：
- 写入 SOURCE/DATE：会在 txt 文件头部写入 <SOURCE> 与 <DATE>（便于后续分组/追溯）
- 文件名最大长度：防止标题过长导致 Windows 路径报错
"""

