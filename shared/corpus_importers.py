"""Import non-Lexis corpora into the workbench corpus layout."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from shared.corpus_model import stable_id, write_corpus_model
from shared.io_utils import read_table
from shared.research_output import now_iso, write_excel_with_readme, write_json


TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
DOCX_EXTENSIONS = {".docx"}


def safe_segment(value: Any, fallback: str = "Unknown") -> str:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() == "nan":
        text = fallback
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80] or fallback


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="gbk", errors="ignore")


def _extract_metadata_header(body: str, tag: str) -> str:
    """Extract a LexisNexis-style metadata tag from the top of a file body.

    Looks for ``<TAG>: value`` lines before ``----- BODY -----``.
    Returns the value or empty string.
    """
    header = body.split("----- BODY -----")[0] if "----- BODY -----" in body else ""
    if not header:
        # Try first 20 lines for files without BODY separator
        lines = body.splitlines()[:20]
    else:
        lines = header.splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith(f"<{tag}>:"):
            value = line.split(":", 1)[1].strip()
            return value if value else ""
    return ""


def read_docx_file(path: Path) -> str:
    from docx import Document

    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def write_workbench_txt(
    *,
    out_path: Path,
    title: str,
    source: str,
    date: str,
    body: str,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        f"<TITLE>: {title}",
        f"<SOURCE>: {source}",
    ]
    if date:
        header.append(f"<DATE>: {date}")
    text = "\n".join(header) + "\n\n----- BODY -----\n\n" + (body or "")
    out_path.write_text(text, encoding="utf-8")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    i = 2
    while True:
        candidate = parent / f"{stem}_{i:03d}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def write_source_counts(out_dir: Path, rows: List[Dict[str, Any]]) -> str:
    counts: Dict[str, int] = {}
    for row in rows:
        source = row.get("source") or "Unknown"
        counts[source] = counts.get(source, 0) + 1
    df = pd.DataFrame(
        [{"Source": source, "Count": count} for source, count in counts.items()]
    ).sort_values("Count", ascending=False)
    path = out_dir / "source_counts.xlsx"
    write_excel_with_readme(
        str(path),
        {"Sources": df},
        title="Source counts from imported corpus",
        description="Counts document frequency by source/group after generic corpus import.",
        fields={
            "Source": "Source or grouping label assigned during import.",
            "Count": "Number of imported documents associated with the source.",
        },
        parameters={"generated_at": now_iso()},
    )
    return str(path)


def write_import_report(
    out_dir: Path,
    *,
    input_path: Path,
    corpus_type: str,
    rows: List[Dict[str, Any]],
    skipped: List[Dict[str, Any]],
) -> str:
    report = {
        "generated_at": now_iso(),
        "input_path": str(input_path.absolute()),
        "output_dir": str(out_dir.absolute()),
        "corpus_type": corpus_type,
        "imported_count": len(rows),
        "skipped_count": len(skipped),
        "skipped": skipped[:100],
        "by_source_count": {},
    }
    for row in rows:
        source = row.get("source") or "Unknown"
        report["by_source_count"][source] = report["by_source_count"].get(source, 0) + 1
    report_dir = out_dir / "corpus"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "import_report.json"
    write_json(path, report)
    return str(path)


def finalize_import(
    out_dir: Path,
    *,
    input_path: Path,
    corpus_type: str,
    targets: str,
    rows: List[Dict[str, Any]],
    skipped: List[Dict[str, Any]],
) -> Dict[str, str]:
    source_counts = write_source_counts(out_dir, rows)
    report = write_import_report(
        out_dir,
        input_path=input_path,
        corpus_type=corpus_type,
        rows=rows,
        skipped=skipped,
    )
    corpus_id = stable_id("corpus", [input_path.absolute(), corpus_type])
    run_id = stable_id("run", [corpus_id, "import", now_iso()])
    model = write_corpus_model(
        out_dir,
        input_path=str(input_path),
        targets=targets,
        corpus_type=corpus_type,
        corpus_id=corpus_id,
        run_id=run_id,
    )
    manifest = {
        "source_counts": source_counts,
        "import_report": report,
        **model,
    }
    write_json(out_dir / "00_run_config" / "import_manifest.json", manifest)
    return manifest


def import_file_corpus(
    input_dir: Path,
    out_dir: Path,
    *,
    corpus_type: str,
    targets: str = "",
    default_source: str = "",
) -> Dict[str, str]:
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    corpus_dir = out_dir / "corpus"
    raw_dir = out_dir / "01_corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    files = [
        p for p in sorted(input_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in (TEXT_EXTENSIONS | DOCX_EXTENSIONS)
    ]
    for idx, path in enumerate(files, start=1):
        try:
            if path.suffix.lower() in TEXT_EXTENSIONS:
                body = read_text_file(path)
            else:
                body = read_docx_file(path)
            title = path.stem
            # Try to parse source from LexisNexis/TXT metadata headers first
            source = _extract_metadata_header(body, "SOURCE") or default_source or path.parent.name or "Imported"
            # Parse date too if available
            date = _extract_metadata_header(body, "DATE") or ""
            source_dir = corpus_dir / safe_segment(source)
            out_path = unique_path(source_dir / f"{safe_segment(title, f'doc_{idx:04d}')}.txt")
            write_workbench_txt(out_path=out_path, title=title, source=source, date=date, body=body)
            # Copy original file into project for portability
            raw_source_dir = raw_dir / safe_segment(source)
            raw_source_dir.mkdir(parents=True, exist_ok=True)
            raw_dest = unique_path(raw_source_dir / path.name)
            shutil.copy2(path, raw_dest)
            rows.append({"source": source, "title": title, "path": str(out_path), "date": date})
        except Exception as exc:
            skipped.append({"path": str(path), "error": str(exc)})

    return finalize_import(
        out_dir,
        input_path=input_dir,
        corpus_type=corpus_type,
        targets=targets,
        rows=rows,
        skipped=skipped,
    )


def first_existing_column(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    lower = {str(col).lower().strip(): col for col in df.columns}
    for candidate in candidates:
        found = lower.get(candidate.lower().strip())
        if found is not None:
            return found
    return None


def import_table_corpus(
    input_file: Path,
    out_dir: Path,
    *,
    text_col: str,
    corpus_type: str,
    targets: str = "",
    title_col: str = "",
    source_col: str = "",
    date_col: str = "",
    group_col: str = "",
) -> Dict[str, str]:
    input_file = Path(input_file)
    out_dir = Path(out_dir)
    if not input_file.exists():
        raise FileNotFoundError(f"Input table does not exist: {input_file}")

    df = read_table(str(input_file))
    if text_col not in df.columns:
        raise ValueError(f"Text column not found: {text_col}")

    title_col = title_col or first_existing_column(df, ["title", "headline", "name"]) or ""
    source_col = source_col or first_existing_column(df, ["source", "author", "institution", "platform"]) or ""
    date_col = date_col or first_existing_column(df, ["date", "published_at", "time", "year"]) or ""
    group_col = group_col or source_col

    corpus_dir = out_dir / "corpus"
    raw_dir = out_dir / "01_corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    # Copy original table file into project for portability
    raw_dest = unique_path(raw_dir / input_file.name)
    shutil.copy2(input_file, raw_dest)
    rows: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        body = row.get(text_col, "")
        if pd.isna(body) or not str(body).strip():
            skipped.append({"row": int(idx), "error": "empty text"})
            continue
        title = row.get(title_col, "") if title_col else f"row_{idx + 1:04d}"
        source = row.get(group_col, "") if group_col else row.get(source_col, "") if source_col else "Imported"
        date = row.get(date_col, "") if date_col else ""
        title_s = safe_segment(title, f"row_{idx + 1:04d}")
        source_s = safe_segment(source, "Imported")
        source_dir = corpus_dir / source_s
        out_path = unique_path(source_dir / f"{title_s}.txt")
        write_workbench_txt(
            out_path=out_path,
            title=str(title_s),
            source=str(source_s),
            date="" if pd.isna(date) else str(date),
            body=str(body),
        )
        rows.append({"source": source_s, "title": title_s, "path": str(out_path)})

    return finalize_import(
        out_dir,
        input_path=input_file,
        corpus_type=corpus_type,
        targets=targets,
        rows=rows,
        skipped=skipped,
    )
