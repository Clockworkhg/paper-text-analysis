# app/utils.py
import re

def safe_filename(title: str, max_len: int = 120) -> str:
    title = (title or "").strip()
    title = re.sub(r'[\\/:*?"<>|]', "_", title)   # Windows 非法字符
    title = re.sub(r"\s+", " ", title)
    return title[:max_len] if title else "untitled"

def safe_foldername(name: str, max_len: int = 60) -> str:
    if not name:
        return "Unknown_Source"

    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"[\'`$]", "", name)
    name = re.sub(r"[^\w\u4e00-\u9fa5\- ]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len]