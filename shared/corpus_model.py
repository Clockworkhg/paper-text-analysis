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


def _normalize_source_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def load_country_mapping(out_dir: Path) -> Dict[str, str]:
    """Read a Source_Merged -> Country mapping from merged_sources.xlsx."""
    path = Path(out_dir) / "merged_sources.xlsx"
    if not path.exists():
        return {}
    try:
        df = pd.read_excel(path, sheet_name="WithCountry")
    except Exception:
        return {}
    if df.empty or "Source_Merged" not in df.columns or "Country" not in df.columns:
        return {}
    mapping: Dict[str, str] = {}
    for _, row in df.iterrows():
        source = str(row.get("Source_Merged", "") or "").strip()
        country = str(row.get("Country", "") or "").strip()
        if source and country and country.lower() not in ("nan", "none", "unknown"):
            mapping[source] = country
    return mapping


def match_country_for_source(source: str, mapping: Dict[str, str],
                             fuzzy_threshold: int = 90) -> str:
    """Resolve one normalized source name against a country mapping.

    Tries exact match, whitespace/case-normalized match, then a rapidfuzz
    token-set match (robust to parenthetical qualifiers such as
    "Financial Times (London, England)"); returns "" when nothing is close
    enough. Matched labels still require human review downstream.
    """
    if not mapping or not source:
        return ""
    if source in mapping:
        return mapping[source]
    by_norm = {_normalize_source_key(key): value for key, value in mapping.items()}
    norm = _normalize_source_key(source)
    if norm in by_norm:
        return by_norm[norm]
    try:
        from rapidfuzz import fuzz, process
        match = process.extractOne(
            norm, list(by_norm.keys()),
            scorer=fuzz.token_set_ratio, score_cutoff=fuzzy_threshold,
        )
        if match:
            return by_norm[match[0]]
    except Exception:
        pass
    return ""


def apply_country_to_registry(out_dir: Path) -> Dict[str, Any]:
    """Join merged_sources.xlsx country labels back into 01_corpus/documents.csv.

    Also writes 03_country/source_countries.csv as the clean per-source
    country table for review and grouping. Safe to call on outputs that lack
    either file: the registry is left untouched and a reason is returned.
    """
    out_dir = Path(out_dir)
    docs_path = out_dir / "01_corpus" / "documents.csv"
    if not docs_path.exists():
        return {"updated": False, "reason": "registry_missing"}
    mapping = load_country_mapping(out_dir)
    if not mapping:
        return {"updated": False, "reason": "country_table_missing"}

    docs = pd.read_csv(docs_path)
    if "source_normalized" not in docs.columns or docs.empty:
        return {"updated": False, "reason": "source_column_missing"}

    countries: List[str] = []
    matched = 0
    for source in docs["source_normalized"].fillna("Unknown").astype(str):
        country = match_country_for_source(source, mapping)
        countries.append(country or "Unknown")
        if country:
            matched += 1
    docs["country"] = countries
    docs.to_csv(docs_path, index=False, encoding="utf-8-sig")

    country_dir = out_dir / "03_country"
    country_dir.mkdir(parents=True, exist_ok=True)
    per_source = pd.DataFrame({
        "Source_Normalized": docs["source_normalized"].astype(str),
        "Country": docs["country"].astype(str),
    }).drop_duplicates().sort_values("Source_Normalized")
    per_source.to_csv(country_dir / "source_countries.csv", index=False, encoding="utf-8-sig")

    return {
        "updated": True,
        "documents": len(docs),
        "matched": matched,
        "unknown": len(docs) - matched,
        "source_countries_csv": str(country_dir / "source_countries.csv"),
    }


def load_group_overrides(out_dir: Path) -> Dict[str, str]:
    """Read the optional 01_corpus/group_overrides.xlsx custom mapping table.

    Expected columns: ``source`` (matches registry source_normalized) and
    ``group`` (the user-defined grouping label, e.g. a stance category).
    """
    path = Path(out_dir) / "01_corpus" / "group_overrides.xlsx"
    if not path.exists():
        return {}
    try:
        df = pd.read_excel(path)
    except Exception:
        return {}
    if df.empty:
        return {}
    cols = {str(col).strip().lower(): col for col in df.columns}
    source_col = cols.get("source")
    group_col = cols.get("group")
    if not source_col or not group_col:
        return {}
    mapping: Dict[str, str] = {}
    for _, row in df.iterrows():
        source = str(row[source_col] or "").strip()
        group = str(row[group_col] or "").strip()
        if source and group and group.lower() not in ("nan", "none"):
            mapping[source] = group
    return mapping


def write_group_template(out_dir: Path) -> Dict[str, str]:
    """Write 01_corpus/group_overrides.xlsx pre-filled with registry sources.

    The ``group`` column is left blank for the researcher to fill (e.g. with
    stance/ideology categories); a known ``country`` column is pre-filled to
    serve as a starting point.
    """
    out_dir = Path(out_dir)
    docs_path = out_dir / "01_corpus" / "documents.csv"
    if not docs_path.exists():
        raise FileNotFoundError(f"Document registry not found: {docs_path}")
    docs = pd.read_csv(docs_path)
    if "source_normalized" not in docs.columns:
        raise ValueError("Document registry lacks source_normalized column")

    per_source = (
        docs.groupby(docs["source_normalized"].fillna("Unknown").astype(str))
        .size().rename("documents").reset_index().rename(columns={"source_normalized": "source"})
    )
    if "country" in docs.columns:
        country_map = (
            docs.assign(source=docs["source_normalized"].fillna("Unknown").astype(str))
            .dropna(subset=["country"])
            .groupby("source")["country"].agg(lambda s: s.mode().iat[0])
        )
        per_source["country"] = per_source["source"].map(country_map).fillna("")
    else:
        per_source["country"] = ""
    per_source["group"] = ""
    per_source = per_source.sort_values("documents", ascending=False)

    model_dir = out_dir / "01_corpus"
    model_dir.mkdir(parents=True, exist_ok=True)
    template_path = model_dir / "group_overrides.xlsx"
    write_excel_with_readme(
        str(template_path),
        {"GroupOverrides": per_source[["source", "group", "country", "documents"]]},
        title="Custom grouping overrides",
        description="Editable source-to-group mapping used by the 'custom' grouping mode. Fill the group column, keep the source column unchanged.",
        fields={
            "source": "Normalized source label from the document registry; the join key.",
            "group": "User-defined grouping label (e.g. stance category). Leave blank to fall back to institution grouping.",
            "country": "Known country label when available; informational only.",
            "documents": "Number of documents for this source.",
        },
        parameters={"sources": len(per_source)},
    )
    return {"group_template": str(template_path), "sources": len(per_source)}


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
            "country": "Source country/region joined from merged_sources.xlsx when country inference ran; requires human review.",
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
