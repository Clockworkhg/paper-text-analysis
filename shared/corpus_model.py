"""Unified corpus/document/run metadata model.

This module is intentionally conservative: it builds a normalized metadata
layer around the existing pipeline outputs without moving or renaming the
legacy files that current users already rely on.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd

from shared.research_output import now_iso, write_excel_with_readme, write_json
from shared.research_templates import get_template, normalize_template_name


MODEL_VERSION = "1.0"


def stable_id(prefix: str, parts: Iterable[Any], length: int = 12) -> str:
    seed = "\n".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def parse_text_document(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta = {
        "source_raw": "Unknown",
        "date": "",
        "title": path.stem,
        "body": text,
    }
    if "----- BODY -----" not in text:
        return meta

    header, body = text.split("----- BODY -----", 1)
    meta["body"] = body.strip()
    for line in header.splitlines():
        line = line.strip()
        if line.startswith("<SOURCE>:"):
            meta["source_raw"] = line.split(":", 1)[1].strip() or "Unknown"
        elif line.startswith("<DATE>:"):
            meta["date"] = line.split(":", 1)[1].strip()
        elif line.startswith("<TITLE>:"):
            meta["title"] = line.split(":", 1)[1].strip() or path.stem
    return meta


def token_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def target_hit_counts(text: str, targets: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    text_low = (text or "").lower()
    for target in targets:
        t = target.strip()
        if not t:
            continue
        counts[t] = len(re.findall(re.escape(t.lower()), text_low))
    return counts


def split_targets(targets: str) -> List[str]:
    return [part.strip() for part in (targets or "").split(";") if part.strip()]


def build_documents_dataframe(
    corpus_dir: Path,
    corpus_id: str,
    corpus_type: str,
    targets: Optional[Iterable[str]] = None,
    run_id: str = "",
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    target_list = list(targets or [])
    if not corpus_dir.exists():
        return pd.DataFrame()

    for idx, path in enumerate(sorted(corpus_dir.rglob("*.txt")), start=1):
        rel_path = path.relative_to(corpus_dir).as_posix()
        parsed = parse_text_document(path)
        body = parsed["body"]
        hits = target_hit_counts(body, target_list)
        source_raw = parsed["source_raw"]
        source_folder = path.parent.name if path.parent != corpus_dir else ""
        document_id = stable_id("doc", [corpus_id, rel_path, parsed["title"], parsed["date"]])
        rows.append(
            {
                "document_id": document_id,
                "corpus_id": corpus_id,
                "run_id": run_id,
                "corpus_type": corpus_type,
                "document_index": idx,
                "title": parsed["title"],
                "date": parsed["date"],
                "source_raw": source_raw,
                "source_normalized": source_folder or source_raw,
                "group_label": source_folder or source_raw,
                "relative_path": rel_path,
                "absolute_path": str(path.absolute()),
                "char_count": len(body),
                "word_count_approx": token_count(body),
                "target_hits_total": sum(hits.values()),
                "target_hits_json": json.dumps(hits, ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows)


def corpus_manifest(
    *,
    corpus_id: str,
    run_id: str,
    corpus_type: str,
    input_path: str,
    output_dir: Path,
    documents: pd.DataFrame,
    targets: Iterable[str],
) -> Dict[str, Any]:
    template = get_template(corpus_type)
    return {
        "model_version": MODEL_VERSION,
        "corpus_id": corpus_id,
        "run_id": run_id,
        "corpus_type": normalize_template_name(corpus_type),
        "research_template": template,
        "created_at": now_iso(),
        "input_path": str(Path(input_path).absolute()) if input_path else "",
        "output_dir": str(output_dir.absolute()),
        "documents_count": int(len(documents)),
        "total_words_approx": int(documents["word_count_approx"].sum()) if "word_count_approx" in documents else 0,
        "total_target_hits": int(documents["target_hits_total"].sum()) if "target_hits_total" in documents else 0,
        "targets": list(targets),
        "primary_document_table": "01_corpus/documents.csv",
        "compatibility_note": (
            "Legacy outputs are still written at the output root. The normalized "
            "document registry is the stable metadata layer for new research features."
        ),
    }


def data_model_spec() -> Dict[str, Any]:
    return {
        "model_version": MODEL_VERSION,
        "entities": {
            "corpus": {
                "primary_key": "corpus_id",
                "description": "A research corpus with one or more text documents and shared metadata.",
            },
            "document": {
                "primary_key": "document_id",
                "foreign_keys": {"corpus_id": "corpus.corpus_id"},
                "description": "A normalized text unit used by KWIC, collocation, coding, and review workflows.",
            },
            "analysis_run": {
                "primary_key": "run_id",
                "foreign_keys": {"corpus_id": "corpus.corpus_id"},
                "description": "A parameterized execution of pipeline steps against a corpus.",
            },
            "review_item": {
                "primary_key": "review_id",
                "foreign_keys": {"document_id": "document.document_id"},
                "description": "A human-reviewable candidate evidence item.",
            },
        },
        "document_fields": {
            "document_id": "Stable document identifier.",
            "corpus_id": "Stable corpus identifier.",
            "run_id": "Stable analysis-run identifier.",
            "corpus_type": "Template/category such as news_lexis, academic, policy, interview, social_media.",
            "title": "Document title or filename stem.",
            "date": "Document date when available.",
            "source_raw": "Raw source metadata extracted from the input.",
            "source_normalized": "Normalized source/group label when available.",
            "group_label": "Default grouping variable for comparisons.",
            "relative_path": "Path relative to the legacy corpus directory.",
            "word_count_approx": "Approximate token count.",
            "target_hits_total": "Total hits for configured target terms.",
            "target_hits_json": "Per-target hit counts as JSON.",
        },
        "template_note": "Research templates define recommended metadata fields, coding fields, error types, method focus, and limitations by corpus_type.",
    }


def write_corpus_model(
    out_dir: Path,
    *,
    input_path: str,
    targets: str = "",
    corpus_type: str = "news_lexis",
    corpus_id: Optional[str] = None,
    run_id: Optional[str] = None,
    corpus_dir: Optional[Path] = None,
) -> Dict[str, str]:
    out_dir = Path(out_dir)
    corpus_dir = corpus_dir or (out_dir / "corpus")
    target_list = split_targets(targets)
    corpus_type = normalize_template_name(corpus_type)
    corpus_id = corpus_id or stable_id("corpus", [Path(input_path).absolute(), corpus_type])
    run_id = run_id or stable_id("run", [corpus_id, now_iso()])

    model_dir = out_dir / "01_corpus"
    model_dir.mkdir(parents=True, exist_ok=True)

    documents = build_documents_dataframe(corpus_dir, corpus_id, corpus_type, target_list, run_id=run_id)
    documents_csv = model_dir / "documents.csv"
    documents_xlsx = model_dir / "document_registry.xlsx"
    manifest_path = model_dir / "corpus_manifest.json"
    spec_path = out_dir / "00_run_config" / "data_model.json"
    template_path = out_dir / "00_run_config" / "research_template.json"

    documents.to_csv(documents_csv, index=False, encoding="utf-8-sig")
    write_excel_with_readme(
        str(documents_xlsx),
        {"Documents": documents},
        title="Normalized document registry",
        description="Stable document-level metadata generated from the pipeline corpus output.",
        fields=data_model_spec()["document_fields"],
        parameters={"corpus_id": corpus_id, "run_id": run_id, "corpus_type": corpus_type},
    )
    manifest = corpus_manifest(
        corpus_id=corpus_id,
        run_id=run_id,
        corpus_type=corpus_type,
        input_path=input_path,
        output_dir=out_dir,
        documents=documents,
        targets=target_list,
    )
    write_json(manifest_path, manifest)
    write_json(spec_path, data_model_spec())
    write_json(template_path, get_template(corpus_type))

    return {
        "corpus_id": corpus_id,
        "run_id": run_id,
        "documents_csv": str(documents_csv),
        "document_registry": str(documents_xlsx),
        "corpus_manifest": str(manifest_path),
        "data_model": str(spec_path),
        "research_template": str(template_path),
    }
