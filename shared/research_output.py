import json
import hashlib
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import pandas as pd

from shared.research_templates import normalize_template_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def stable_id(prefix: str, *parts: Any, length: int = 12) -> str:
    seed = "\n".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _run_command(args: Iterable[str]) -> str:
    try:
        return subprocess.check_output(
            list(args),
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        ).strip()
    except Exception:
        return ""


def git_commit() -> str:
    return _run_command(["git", "rev-parse", "--short", "HEAD"])


def git_dirty() -> bool:
    status = _run_command(["git", "status", "--short"])
    return bool(status)


def package_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return ""


def environment_snapshot() -> Dict[str, Any]:
    packages = [
        "pandas",
        "openpyxl",
        "spacy",
        "nltk",
        "rapidfuzz",
        "requests",
        "tldextract",
        "python-docx",
    ]
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "packages": {name: package_version(name) for name in packages},
    }


# Version of the analysis algorithm implemented in modules/txt_modifier_extractor.py.
# Bump when extraction/grouping/scoring semantics change so run manifests can
# distinguish results produced by different engine generations.
ALGORITHM_VERSION = "1.1"


def nlp_environment() -> Dict[str, Any]:
    """Pin the NLP model stack (spaCy + installed model) for reproducibility."""
    return {
        "spacy": package_version("spacy"),
        "en_core_web_sm": package_version("en_core_web_sm"),
        "nltk": package_version("nltk"),
    }


def ensure_research_dirs(out_dir: Path) -> Dict[str, str]:
    dirs = {
        "run_config": out_dir / "00_run_config",
        "corpus": out_dir / "01_corpus",
        "sources": out_dir / "02_sources",
        "country": out_dir / "03_country",
        "kwic": out_dir / "04_kwic",
        "modifiers": out_dir / "05_modifiers",
        "review": out_dir / "06_review",
        "reports": out_dir / "07_reports",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return {key: str(path) for key, path in dirs.items()}


def build_run_config(args: Any, steps_to_run: Iterable[int], run_steps: Iterable[int]) -> Dict[str, Any]:
    out_dir = Path(args.output)
    created_at = now_iso()
    corpus_type = normalize_template_name(getattr(args, "corpus_type", "news_lexis") or "news_lexis")
    corpus_id = stable_id("corpus", str(Path(args.input).absolute()), corpus_type)
    run_id = stable_id("run", corpus_id, created_at, getattr(args, "targets", ""))
    return {
        "created_at": created_at,
        "run_id": run_id,
        "corpus_id": corpus_id,
        "model_version": "1.0",
        "corpus_type": corpus_type,
        "project": "论文文本分析工具集",
        "research_positioning": "Corpus-Assisted Discourse Studies (CADS) with CDA, collocation, semantic prosody, and appraisal/framing analysis.",
        "input": str(Path(args.input).absolute()),
        "output": str(out_dir.absolute()),
        "targets": getattr(args, "targets", ""),
        "country_lookup_enabled": bool(getattr(args, "country", False)),
        "group_by": str(getattr(args, "group_by", "source") or "source"),
        "force": bool(getattr(args, "force", False)),
        "skip": getattr(args, "skip", ""),
        "only": getattr(args, "only", ""),
        "steps_requested": list(steps_to_run),
        "steps_to_run": list(run_steps),
        "environment": environment_snapshot(),
        "output_layout": ensure_research_dirs(out_dir),
        "method_note": (
            "Automated outputs are candidate evidence for corpus-assisted research. "
            "Final interpretations should be checked against KWIC/concordance context and, where relevant, human review."
        ),
    }


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_run_config(out_dir: Path, config: Mapping[str, Any], filename: str = "run_config.json") -> Path:
    run_config_dir = out_dir / "00_run_config"
    run_config_dir.mkdir(parents=True, exist_ok=True)
    path = run_config_dir / filename
    write_json(path, config)
    # Compatibility/convenience copy at the output root.
    write_json(out_dir / filename, config)
    return path


def readme_dataframe(
    title: str,
    description: str,
    fields: Optional[Mapping[str, str]] = None,
    parameters: Optional[Mapping[str, Any]] = None,
    method_note: Optional[str] = None,
) -> pd.DataFrame:
    rows = [
        {"Section": "Title", "Name": title, "Value": ""},
        {"Section": "Description", "Name": description, "Value": ""},
        {
            "Section": "Method",
            "Name": "Interpretation",
            "Value": method_note
            or "This file contains automated candidate evidence. Interpret results through manual context checking and documented review.",
        },
        {"Section": "Generated", "Name": "created_at", "Value": now_iso()},
        {"Section": "Environment", "Name": "git_commit", "Value": git_commit()},
    ]
    if parameters:
        for key, value in parameters.items():
            rows.append({"Section": "Parameter", "Name": str(key), "Value": json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value})
    if fields:
        for key, value in fields.items():
            rows.append({"Section": "Field", "Name": key, "Value": value})
    return pd.DataFrame(rows)


def write_excel_with_readme(
    path: str,
    sheets: Mapping[str, pd.DataFrame],
    title: str,
    description: str,
    fields: Optional[Mapping[str, str]] = None,
    parameters: Optional[Mapping[str, Any]] = None,
) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        readme_dataframe(title, description, fields, parameters).to_excel(writer, index=False, sheet_name="README")


def append_readme_sheet(
    path: str,
    title: str,
    description: str,
    fields: Optional[Mapping[str, str]] = None,
    parameters: Optional[Mapping[str, Any]] = None,
) -> None:
    from openpyxl import load_workbook

    wb = load_workbook(path)
    if "README" in wb.sheetnames:
        del wb["README"]
    ws = wb.create_sheet("README")
    df = readme_dataframe(title, description, fields, parameters)
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append(list(row))
    wb.save(path)
