import re
import os
from pathlib import Path
from typing import Optional

import pandas as pd
import tldextract

RE_MULTI_SPACE = re.compile(r"\s+")
RE_QUOTES = re.compile(r'^[\'"]|[\'"]$')
RE_DATE_LIKE = re.compile(
    r"(\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*\b\d{4}\b)|(\b\d{1,2}:\d{2}\b)|(\bAM\b|\bPM\b|\bGMT\b)",
    re.IGNORECASE,
)
TLDEXTRACT_CACHE_DIR = Path(
    os.environ.get("TLDEXTRACT_CACHE", Path(__file__).resolve().parents[1] / ".cache" / "tldextract")
)
TLD_EXTRACTOR = tldextract.TLDExtract(
    cache_dir=str(TLDEXTRACT_CACHE_DIR),
    suffix_list_urls=(),
)


def normalize_word(w: str) -> str:
    if w is None:
        return ""
    w = str(w).strip()
    w = RE_MULTI_SPACE.sub(" ", w)
    return w


def normalize_basic(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).strip()
    s = RE_MULTI_SPACE.sub(" ", s)
    s = RE_QUOTES.sub("", s).strip()
    return s


def strip_variants(name: str) -> str:
    s = name
    s = re.sub(r"\s*-\s*(online|international edition|english version)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^TVEyes\s*-\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^TVeyes\s*-\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bTranscript\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bFeatured Segments\b", "", s, flags=re.IGNORECASE)

    if RE_DATE_LIKE.search(s):
        s = re.split(r"\s+\d{1,2}:\d{2}\s*(AM|PM)?", s, flags=re.IGNORECASE)[0].strip()
        s = re.split(r"\s+\b(?:Dienstag|Donnerstag)\b", s, flags=re.IGNORECASE)[0].strip()

    return normalize_basic(s)


def domain_canonical(name: str) -> Optional[str]:
    s = name.strip()
    if re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", s):
        ext = TLD_EXTRACTOR(s)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}".lower()
    s2 = s.lower()
    if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", s2):
        ext = TLD_EXTRACTOR(s2)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}".lower()
    return None
