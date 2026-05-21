# app/rules.py
from docx import Document
from pathlib import Path
import re

import json

from .constants import DATE_LINE_RE
# 如果函数里用了 DEFAULT_SOURCE_CANONICAL_MAP / DEFAULT_NOISE_KEYWORDS
from .constants import DEFAULT_SOURCE_CANONICAL_MAP, DEFAULT_NOISE_KEYWORDS

def extract_metadata(article_text: str):
    """
    提取：标题、媒体来源（可能多行）、日期行（如 December 3, 2025 ...）
    规则：只在 Body 之前的“头部区域”内解析，避免误伤正文。
    """
    lines = article_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    while lines and not lines[0].strip():
        lines.pop(0)

    title = lines[0].strip() if lines else ""
    header_lines = []

    for line in lines[1:]:
        if line.strip() == "Body":
            break
        header_lines.append(line.strip())

    header_lines = [x for x in header_lines if x]

    date_line = ""
    for x in header_lines:
        if DATE_LINE_RE.match(x):
            date_line = x
            break

    stop_prefixes = (
        "Copyright", "Delivered by", "Length:", "Byline:", "Dateline:", "Section:",
        "Document-Type:", "Publication-Type:", "Language:", "Load-Date:", "Journal Code:"
    )

    sources = []
    for x in header_lines:
        if x == date_line:
            break
        if any(x.startswith(p) for p in stop_prefixes):
            break
        if x.startswith(("Date and Time:", "Job Number:", "Documents", "Search Terms:", "Search Type:", "Client/Matter:")):
            continue
        if x.lower().startswith("link to the original story"):
            continue
        if "Delivered by" in x and "(" in x:
            continue
        sources.append(x)

    return title, sources, date_line

def extract_body(article_text: str) -> str:
    """
    只提取 Lexis 正文（Body），遇到 Notes / Classification 即停止。
    """
    lines = article_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    in_body = False
    body_lines = []

    for line in lines:
        if line.strip() == "Body":
            in_body = True
            continue
        if in_body and line.strip() in {"Notes", "Classification"}:
            break
        if in_body:
            body_lines.append(line)

    return "\n".join(body_lines).strip()

def pick_primary_source(sources: list[str], noise_keywords: list[str]) -> str:
    """
    从 Lexis 的 SOURCE 列表中，智能选取“真实报道机构”
    - 从后往前扫描
    - 跳过明显是检索噪音 / 标题 / 平台信息的项
    """
    if not sources:
        return "Unknown_Source"

    noise_keywords = noise_keywords or []

    for item in reversed(sources):
        text = (item or "").strip()
        if not text:
            continue

        # 太长的一般是标题/说明
        if len(text) > 80:
            continue

        # 跳过噪音关键词
        if any(k.lower() in text.lower() for k in noise_keywords):
            continue

        return text

    return (sources[-1] or "").strip() or "Unknown_Source"


def normalize_source_name(name: str) -> str:
    """
    对机构名做基础规范化：
    - 去掉括号里的地区说明
    - 去掉常见的版本/区域后缀
    - 压缩空白
    """
    if not name:
        return ""

    text = name.strip()

    # 去掉括号内容，如 (UK), (World), (APAC)
    text = re.sub(r"\s*\(.*?\)\s*", " ", text)

    # 常见“非核心机构名”的后缀（可逐步补充）
    suffixes = [
        " International",
        " World",
        " Global",
        " Europe",
        " Asia",
        " Asia Pacific",
        " APAC",
        " Americas",
        " Africa",
        " Middle East",
    ]

    for suf in suffixes:
        if text.lower().endswith(suf.lower()):
            text = text[: -len(suf)].strip()

    # 压缩空白
    text = re.sub(r"\s+", " ", text)

    return text

def get_canonical_source(
    sources: list[str],
    canonical_map: dict,
    noise_keywords: list[str],
    enable_normalize: bool = True
) -> str:
    """
    从 Lexis sources 中选取并规范化真实报道机构名（支持用户自定义规则）
    """
    raw = pick_primary_source(sources, noise_keywords=noise_keywords)
    if not raw:
        return "Unknown_Source"

    key = normalize_source_name(raw) if enable_normalize else raw.strip()
    return (canonical_map or {}).get(key, key) or "Unknown_Source"

def load_user_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        import sys
        print(f"[rules] failed to load user JSON '{path}': {e}", file=sys.stderr)
        return default
