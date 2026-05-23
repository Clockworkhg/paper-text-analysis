"""Literature note indexing and search for the knowledge base.

Scans literature_md/ directories, extracts metadata from note headers,
generates 00_INDEX.md, and supports keyword search.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
LITERATURE_DIR = ROOT / "literature_md"

CATEGORY_LABELS: Dict[str, str] = {
    "01_core_must_read": "Core CADS/CDA Methodology (必读)",
    "02_methods_tools": "Methods & Tools — Collocation, Semantic Prosody, KWIC",
    "03_media_discourse_applications": "Media Discourse & Political Applications",
    "04_evaluation_sentiment_framing": "Evaluation, Sentiment & Framing",
    "05_text_as_data_tooling": "Text-as-Data & Computational Tooling",
    "06_low_priority": "Low Priority / Supplementary",
}


def _extract_title(path: Path) -> str:
    """Extract the H1 title from a literature note."""
    try:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("# ") and not line.startswith("## "):
                return line[2:].strip()
    except Exception:
        pass
    return path.stem


def _extract_meta(path: Path) -> Dict[str, str]:
    """Extract 文件信息 fields from a literature note."""
    meta: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
        in_meta = False
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("## 文件信息"):
                in_meta = True
                continue
            if in_meta:
                if line.startswith("## ") and not line.startswith("## 文件信息"):
                    break
                m = re.match(r"-\s*(.+?)[：:]\s*(.+)", line)
                if m:
                    meta[m.group(1).strip()] = m.group(2).strip()
    except Exception:
        pass
    return meta


def scan_literature(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Scan the literature directory and return structured metadata for all notes."""
    base_dir = Path(base_dir) if base_dir else LITERATURE_DIR
    if not base_dir.exists():
        return []

    entries: List[Dict[str, Any]] = []
    for cat_dir in sorted(base_dir.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name.startswith("."):
            continue
        cat_key = cat_dir.name
        for note_path in sorted(cat_dir.glob("*.md")):
            if note_path.name.startswith("00_INDEX"):
                continue
            title = _extract_title(note_path)
            meta = _extract_meta(note_path)
            entries.append({
                "category": cat_key,
                "category_label": CATEGORY_LABELS.get(cat_key, cat_key),
                "filename": note_path.name,
                "path": str(note_path.relative_to(base_dir)),
                "title": title,
                "original_file": meta.get("原始文件", meta.get("Original file", "")),
                "ocr_pages": meta.get("OCR 页数", meta.get("OCR pages", "")),
            })
    return entries


def build_index_md(base_dir: Optional[Path] = None) -> str:
    """Generate 00_INDEX.md content from scanned literature."""
    entries = scan_literature(base_dir)
    if not entries:
        return "# Literature Index\n\n_No literature notes found._\n"

    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        by_cat.setdefault(e["category"], []).append(e)

    lines = [
        "# Literature Knowledge Base — Index",
        "",
        f"Auto-generated. {len(entries)} notes across {len(by_cat)} categories.",
        "",
        "## Categories",
        "",
    ]

    for cat_key in sorted(by_cat.keys()):
        cat_entries = by_cat[cat_key]
        label = CATEGORY_LABELS.get(cat_key, cat_key)
        lines.append(f"### {cat_key} — {label}")
        lines.append("")
        for e in cat_entries:
            extras = []
            if e["original_file"]:
                extras.append(f"Source: {e['original_file']}")
            if e["ocr_pages"]:
                extras.append(f"{e['ocr_pages']}p")
            extra_str = f"  -- {', '.join(extras)}" if extras else ""
            lines.append(f"- [{e['title']}]({e['path']}){extra_str}")
        lines.append("")

    return "\n".join(lines)


def search_literature(query: str, base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Full-text search literature notes for a query string."""
    base_dir = Path(base_dir) if base_dir else LITERATURE_DIR
    if not base_dir.exists():
        return []

    results = []
    query_lower = query.lower()
    for cat_dir in sorted(base_dir.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name.startswith("."):
            continue
        for note_path in sorted(cat_dir.glob("*.md")):
            if note_path.name.startswith("00_INDEX"):
                continue
            try:
                text = note_path.read_text(encoding="utf-8")
                if query_lower in text.lower():
                    title = _extract_title(note_path)
                    # Find matching context snippets
                    snippets = []
                    for i, line in enumerate(text.splitlines()):
                        if query_lower in line.lower():
                            snippets.append(line.strip()[:120])
                    results.append({
                        "title": title,
                        "category": cat_dir.name,
                        "category_label": CATEGORY_LABELS.get(cat_dir.name, cat_dir.name),
                        "path": str(note_path.relative_to(base_dir)),
                        "filename": note_path.name,
                        "snippets": snippets[:5],
                    })
            except Exception:
                pass
    return results
