# -*- coding: utf-8 -*-
"""Run Compare + Evidence Refresh (Phase 3C).

All comparison reads go through GenerationResolver against archived
published generations — never the live project root, never another run.
Only COMMITTED runs can participate.

Compatibility levels:
- FULLY_COMPARABLE: corpus fingerprint, document count, target set,
  group_by, MI threshold, algorithm/rules versions all identical.
- PARTIALLY_COMPARABLE: some parameters differ but core analysis
  dimensions still overlap (shared targets, same algorithm generation).
- NOT_COMPARABLE: corpus fingerprint changed AND algorithm generation
  changed, or no shared targets — deltas would be meaningless.

Descriptive only: this module reports increased/decreased/appeared/
disappeared. It never interprets why.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from gui_next.data.generations import GenerationResolver


class NotComparableError(ValueError):
    pass


FULLY_COMPARABLE = "FULLY_COMPARABLE"
PARTIALLY_COMPARABLE = "PARTIALLY_COMPARABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"

_PARAM_KEYS = ("group_by", "mi_threshold", "pos_translate")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_run_config(project_dir: Path, run_id: str) -> Dict[str, Any]:
    resolver = GenerationResolver(project_dir)
    path = resolver.artifact_path(run_id, "run_config.json")
    data = _read_json(path) or {}
    full = resolver.artifact_path(run_id, "00_run_config/run_config.json")
    if full.exists():
        extra = _read_json(full) or {}
        data.setdefault("algorithm_version", extra.get("algorithm_version", ""))
        data.setdefault("hand_rules_version", extra.get("hand_rules_version", ""))
    return data


def _read_kwic(project_dir: Path, run_id: str) -> pd.DataFrame:
    path = GenerationResolver(project_dir).artifact_path(run_id, "adjectives_phrases.xlsx")
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name="KWIC")
    except Exception:
        return pd.DataFrame()


def _read_sheet(project_dir: Path, run_id: str, sheet: str) -> pd.DataFrame:
    path = GenerationResolver(project_dir).artifact_path(run_id, "adjectives_phrases.xlsx")
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet)
    except Exception:
        return pd.DataFrame()


def _read_registry(project_dir: Path, run_id: str) -> pd.DataFrame:
    path = GenerationResolver(project_dir).artifact_path(run_id, "01_corpus/documents.csv")
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Compatibility gate
# ---------------------------------------------------------------------------


def compute_compatibility(config_a: Dict[str, Any], config_b: Dict[str, Any],
                          corpus_fp_a: str, corpus_fp_b: str,
                          doc_count_a: int, doc_count_b: int,
                          targets_a: List[str], targets_b: List[str],
                          algorithm_a: str = "", algorithm_b: str = "",
                          rules_a: str = "", rules_b: str = "") -> Dict[str, Any]:
    differences: List[Dict[str, str]] = []
    same_corpus = (corpus_fp_a == corpus_fp_b)
    if not same_corpus:
        differences.append({"field": "corpus_fingerprint",
                            "a": corpus_fp_a[:12], "b": corpus_fp_b[:12]})
    if doc_count_a != doc_count_b:
        differences.append({"field": "documents",
                            "a": str(doc_count_a), "b": str(doc_count_b)})
    same_targets = set(targets_a) == set(targets_b)
    if not same_targets:
        differences.append({"field": "targets",
                            "a": f"{len(targets_a)} targets", "b": f"{len(targets_b)} targets"})
    for key in _PARAM_KEYS:
        va, vb = str(config_a.get(key, "")), str(config_b.get(key, ""))
        if va != vb:
            differences.append({"field": key, "a": va, "b": vb})
    if algorithm_a != algorithm_b:
        differences.append({"field": "algorithm_version", "a": algorithm_a, "b": algorithm_b})
    if rules_a != rules_b:
        differences.append({"field": "hand_rules_version", "a": rules_a, "b": rules_b})

    core_broken = (not same_corpus and algorithm_a != algorithm_b) or \
                  (bool(targets_a) and bool(targets_b) and not (set(targets_a) & set(targets_b)))

    if core_broken:
        level = NOT_COMPARABLE
    elif not differences:
        level = FULLY_COMPARABLE
    else:
        level = PARTIALLY_COMPARABLE
    return {"level": level, "differences": differences,
            "same_corpus": same_corpus, "same_targets": same_targets}


# ---------------------------------------------------------------------------
# Overview comparison
# ---------------------------------------------------------------------------


def compare_overview(project_dir: Path, run_a: str, run_b: str) -> Dict[str, Any]:
    config_a = _read_run_config(project_dir, run_a)
    config_b = _read_run_config(project_dir, run_b)
    reg_a = _read_registry(project_dir, run_a)
    reg_b = _read_registry(project_dir, run_b)
    kwic_a = _read_kwic(project_dir, run_a)
    kwic_b = _read_kwic(project_dir, run_b)
    col_a = _read_sheet(project_dir, run_a, "Collocates")
    col_b = _read_sheet(project_dir, run_b, "Collocates")
    phr_a = _read_sheet(project_dir, run_a, "Phrases")
    phr_b = _read_sheet(project_dir, run_b, "Phrases")

    resolver = GenerationResolver(project_dir)
    manifest_a = resolver.load_manifest(run_a) or {}
    manifest_b = resolver.load_manifest(run_b) or {}

    targets_a = [t.strip() for t in (config_a.get("targets") or "").split(";") if t.strip()]
    targets_b = [t.strip() for t in (config_b.get("targets") or "").split(";") if t.strip()]
    corpus_a = manifest_a.get("corpus_fingerprint", "")
    corpus_b = manifest_b.get("corpus_fingerprint", "")

    compat = compute_compatibility(
        config_a, config_b, corpus_a, corpus_b,
        len(reg_a), len(reg_b), targets_a, targets_b,
        config_a.get("algorithm_version", ""), config_b.get("algorithm_version", ""),
        config_a.get("hand_rules_version", ""), config_b.get("hand_rules_version", ""),
    )

    return {
        "run_a": run_a, "run_b": run_b,
        "compatibility": compat,
        "documents_a": len(reg_a), "documents_b": len(reg_b),
        "targets_a": targets_a, "targets_b": targets_b,
        "kwic_count_a": len(kwic_a), "kwic_count_b": len(kwic_b),
        "collocate_count_a": len(col_a), "collocate_count_b": len(col_b),
        "phrase_count_a": len(phr_a), "phrase_count_b": len(phr_b),
        "group_by_a": config_a.get("group_by", ""), "group_by_b": config_b.get("group_by", ""),
        "mi_a": config_a.get("mi_threshold", ""), "mi_b": config_b.get("mi_threshold", ""),
        "algorithm_a": config_a.get("algorithm_version", ""),
        "algorithm_b": config_b.get("algorithm_version", ""),
        "published_a": manifest_a.get("completed_at", ""),
        "published_b": manifest_b.get("completed_at", ""),
    }


# ---------------------------------------------------------------------------
# Target comparison
# ---------------------------------------------------------------------------


def compare_targets(project_dir: Path, run_a: str, run_b: str,
                    targets_a: List[str], targets_b: List[str]) -> List[Dict[str, Any]]:
    kwic_a = _read_kwic(project_dir, run_a)
    kwic_b = _read_kwic(project_dir, run_b)

    def target_stats(kwic: pd.DataFrame, target: str) -> Tuple[int, int]:
        if kwic.empty or "Target" not in kwic.columns:
            return 0, 0
        hits = kwic[kwic["Target"].astype(str) == target]
        docs = hits["Document_ID"].nunique() if "Document_ID" in hits.columns and not hits.empty else 0
        return len(hits), docs

    all_targets = sorted(set(targets_a) | set(targets_b))
    results = []
    for target in all_targets:
        hits_a, docs_a = target_stats(kwic_a, target)
        hits_b, docs_b = target_stats(kwic_b, target)
        if target not in targets_a:
            status = "added"
        elif target not in targets_b:
            status = "removed"
        elif hits_a == hits_b:
            status = "unchanged"
        else:
            status = "changed"
        delta = hits_b - hits_a
        delta_pct = f"{delta / hits_a * 100:+.1f}%" if hits_a > 0 else ""
        results.append({
            "target": target, "status": status,
            "hits_a": hits_a, "hits_b": hits_b, "delta": delta, "delta_pct": delta_pct,
            "docs_a": docs_a, "docs_b": docs_b,
        })
    return results


# ---------------------------------------------------------------------------
# Pattern comparison
# ---------------------------------------------------------------------------


def compare_patterns(project_dir: Path, run_a: str, run_b: str,
                     sheet: str, key_fields: List[str],
                     metric_fields: List[str],
                     comparable: bool = True) -> List[Dict[str, Any]]:
    df_a = _read_sheet(project_dir, run_a, sheet)
    df_b = _read_sheet(project_dir, run_b, sheet)

    def index_by_key(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        if df.empty:
            return result
        for _, row in df.iterrows():
            key_parts = tuple(str(row.get(f, "")) for f in key_fields)
            key = hashlib.sha1("|".join(key_parts).encode("utf-8", errors="ignore")).hexdigest()[:16]
            if key not in result:
                result[key] = row.to_dict()
        return result

    index_a = index_by_key(df_a)
    index_b = index_by_key(df_b)
    all_keys = sorted(set(index_a) | set(index_b))

    results = []
    for key in all_keys:
        row_a = index_a.get(key)
        row_b = index_b.get(key)
        if row_a is not None and row_b is None:
            status = "only_a"
        elif row_b is not None and row_a is None:
            status = "only_b"
        else:
            status = "present_both"
        entry: Dict[str, Any] = {"status": status, "key": key}
        for field in key_fields:
            entry[field] = str(row_a.get(field, "") if row_a else
                               row_b.get(field, "") if row_b else "")
        for field in metric_fields:
            va = row_a.get(field) if row_a else None
            vb = row_b.get(field) if row_b else None
            entry[f"{field}_a"] = va
            entry[f"{field}_b"] = vb
            if comparable and va is not None and vb is not None:
                try:
                    entry[f"{field}_delta"] = float(vb) - float(va)
                except (ValueError, TypeError):
                    entry[f"{field}_delta"] = None
            else:
                entry[f"{field}_delta"] = None
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Document identity mapping
# ---------------------------------------------------------------------------


def _meta_key(row: Dict[str, Any]) -> str:
    return "|".join(str(row.get(k, "")).strip().lower()
                    for k in ("title", "source_normalized", "date"))


def _content_key(row: Dict[str, Any]) -> str:
    raw = f"{row.get('title', '')}|{row.get('source_raw', '')}|{row.get('date', '')}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def build_document_mapping(project_dir: Path, run_a: str, run_b: str) -> List[Dict[str, Any]]:
    reg_a = _read_registry(project_dir, run_a)
    reg_b = _read_registry(project_dir, run_b)

    by_id_b: Dict[str, Dict[str, Any]] = {}
    meta_b: Dict[str, List[Dict[str, Any]]] = {}
    content_b: Dict[str, List[Dict[str, Any]]] = {}
    if not reg_b.empty:
        for _, row in reg_b.iterrows():
            d = row.to_dict()
            doc_id = str(d.get("document_id", ""))
            by_id_b[doc_id] = d
            meta_b.setdefault(_meta_key(d), []).append(d)
            content_b.setdefault(_content_key(d), []).append(d)

    used_b: set = set()
    results: List[Dict[str, Any]] = []
    if not reg_a.empty:
        for _, row_a in reg_a.iterrows():
            d = row_a.to_dict()
            doc_id = str(d.get("document_id", ""))
            title = str(d.get("title", ""))
            if doc_id in by_id_b and doc_id not in used_b:
                used_b.add(doc_id)
                results.append({"doc_id_a": doc_id, "doc_id_b": doc_id,
                                "level": "EXACT_ID", "title": title})
            else:
                ck = _content_key(d)
                cands = [c for c in content_b.get(ck, []) if str(c.get("document_id")) not in used_b]
                if len(cands) == 1:
                    match_b = str(cands[0]["document_id"])
                    used_b.add(match_b)
                    results.append({"doc_id_a": doc_id, "doc_id_b": match_b,
                                    "level": "CONTENT_MATCH", "title": title})
                else:
                    mk = _meta_key(d)
                    cands = [c for c in meta_b.get(mk, []) if str(c.get("document_id")) not in used_b]
                    if len(cands) == 1:
                        match_b = str(cands[0]["document_id"])
                        used_b.add(match_b)
                        results.append({"doc_id_a": doc_id, "doc_id_b": match_b,
                                        "level": "METADATA_MATCH", "title": title})
                    elif len(cands) > 1:
                        results.append({"doc_id_a": doc_id, "level": "AMBIGUOUS", "title": title})
                    else:
                        results.append({"doc_id_a": doc_id, "level": "UNMATCHED_A", "title": title})

    if not reg_b.empty:
        for _, row_b in reg_b.iterrows():
            doc_id_b = str(row_b.get("document_id", ""))
            if doc_id_b not in used_b and not any(r.get("doc_id_b") == doc_id_b for r in results):
                results.append({"doc_id_b": doc_id_b, "level": "UNMATCHED_B",
                                "title": str(row_b.get("title", ""))})
    return results


# ---------------------------------------------------------------------------
# Comparison record persistence
# ---------------------------------------------------------------------------


def comparison_dir(project_dir: Path, run_a: str, run_b: str) -> Path:
    return Path(project_dir) / "runs" / "comparisons" / f"{run_a}__{run_b}"


def save_comparison_record(project_dir: Path, record: Dict[str, Any]) -> Path:
    d = comparison_dir(project_dir, record["run_a"], record["run_b"])
    d.mkdir(parents=True, exist_ok=True)
    path = d / "comparison.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_comparison_record(project_dir: Path, run_a: str, run_b: str) -> Optional[Dict[str, Any]]:
    path = comparison_dir(project_dir, run_a, run_b) / "comparison.json"
    return _read_json(path)


def save_document_mapping(project_dir: Path, run_a: str, run_b: str,
                          mapping: List[Dict[str, Any]]) -> Path:
    d = comparison_dir(project_dir, run_a, run_b)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "document_mapping.json"
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_document_mapping(project_dir: Path, run_a: str, run_b: str) -> List[Dict[str, Any]]:
    path = comparison_dir(project_dir, run_a, run_b) / "document_mapping.json"
    return _read_json(path) or []


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_comparison_markdown(project_dir: Path, run_a: str, run_b: str,
                               out_path: Optional[Path] = None) -> Path:
    overview = compare_overview(project_dir, run_a, run_b)
    compat = overview["compatibility"]
    targets = compare_targets(project_dir, run_a, run_b,
                              overview["targets_a"], overview["targets_b"])
    resolver = GenerationResolver(project_dir)
    manifest_a = resolver.load_manifest(run_a) or {}
    manifest_b = resolver.load_manifest(run_b) or {}

    lines = ["# Run Comparison", "",
             f"## Run A: `{run_a}`", "",
             f"- Corpus fingerprint: `{manifest_a.get('corpus_fingerprint', '')}`",
             f"- Manifest hash: `{manifest_a.get('publication_manifest_sha256', '')}`",
             f"- Published: {manifest_a.get('completed_at', '')}", "",
             f"## Run B: `{run_b}`", "",
             f"- Corpus fingerprint: `{manifest_b.get('corpus_fingerprint', '')}`",
             f"- Manifest hash: `{manifest_b.get('publication_manifest_sha256', '')}`",
             f"- Published: {manifest_b.get('completed_at', '')}", "",
             f"## Compatibility: {compat['level']}", ""]
    for diff in compat["differences"]:
        lines.append(f"- {diff['field']}: {diff['a']} → {diff['b']}")
    if not compat["differences"]:
        lines.append("- No differences detected.")
    lines.append("")

    lines += ["## Documents", "", "| | Run A | Run B |", "|---|---|---|",
              f"| Documents | {overview['documents_a']} | {overview['documents_b']} |",
              f"| KWIC rows | {overview['kwic_count_a']} | {overview['kwic_count_b']} |",
              f"| Collocates | {overview['collocate_count_a']} | {overview['collocate_count_b']} |",
              f"| Phrases | {overview['phrase_count_a']} | {overview['phrase_count_b']} |", ""]

    lines += ["## Target Comparison", "",
              "| Target | Status | Hits A | Hits B | Δ |", "|---|---|---|---|---|"]
    for t in targets:
        lines.append(f"| {t['target']} | {t['status']} | {t['hits_a']} | {t['hits_b']} | {t['delta']} |")
    lines.append("")

    doc_mapping = build_document_mapping(project_dir, run_a, run_b)
    levels: Dict[str, int] = {}
    for d in doc_mapping:
        levels[d["level"]] = levels.get(d["level"], 0) + 1
    lines += ["## Document Mapping", ""]
    for level, count in sorted(levels.items()):
        lines.append(f"- {level}: {count}")
    lines.append("")

    lines += ["ⓘ Run differences describe changes in corpus/output under the recorded "
              "analysis configurations. They do not by themselves establish "
              "substantive discourse change.", ""]

    out = Path(out_path) if out_path else \
        comparison_dir(project_dir, run_a, run_b) / "comparison.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Evidence Refresh (§10-14)
# ---------------------------------------------------------------------------


def find_evidence_counterpart(project_dir: Path, run_b: str,
                              record: Dict[str, Any]) -> Dict[str, Any]:
    kind = record.get("evidence_type", "")
    snap = record.get("captured_snapshot", {}) or {}
    target = record.get("target", "")

    sheet_map = {"collocate_pattern": "Collocates", "phrase_pattern": "Phrases",
                 "group_pattern": "GroupComparison"}
    if kind in sheet_map:
        df = _read_sheet(project_dir, run_b, sheet_map[kind])
        if df.empty:
            return {"state": "NO_MATCH"}
        mask = pd.Series(True, index=df.index)
        if "Target" in df.columns:
            mask &= df["Target"].astype(str) == target
        col_field = {"collocate_pattern": "Collocate",
                     "phrase_pattern": "Modifier_Phrase"}.get(kind)
        if col_field and col_field in df.columns:
            needle = str(snap.get(col_field, "") or snap.get("Expression", "")).strip()
            if needle:
                mask &= df[col_field].astype(str).str.strip() == needle
        matches = df[mask]
        if matches.empty:
            return {"state": "NO_MATCH"}
        return {"state": "CANDIDATE_MATCH", "counterpart": matches.iloc[0].to_dict(),
                "run_b": run_b}

    if kind == "kwic":
        kwic = _read_kwic(project_dir, run_b)
        if kwic.empty:
            return {"state": "NO_MATCH"}
        mask = pd.Series(True, index=kwic.index)
        doc_id = record.get("document_id", "")
        if doc_id and "Document_ID" in kwic.columns:
            mask &= kwic["Document_ID"].astype(str) == doc_id
        if target and "Target" in kwic.columns:
            mask &= kwic["Target"].astype(str) == target
        node = str(snap.get("Keyword", "")).strip()
        if node and "Keyword" in kwic.columns:
            mask &= kwic["Keyword"].astype(str).str.strip() == node
        matches = kwic[mask]
        if matches.empty:
            return {"state": "NO_MATCH"}
        return {"state": "CANDIDATE_MATCH", "counterpart": matches.iloc[0].to_dict(),
                "run_b": run_b}

    return {"state": "NOT_SEARCHED"}


def export_evidence_refresh_audit(project_dir: Path, decisions: List[Dict[str, Any]],
                                  out_path: Optional[Path] = None) -> Path:
    out = Path(out_path) if out_path else \
        Path(project_dir) / "runs" / "evidence_refresh_audit.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Evidence Refresh Audit", "",
             f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}", "",
             "| Claim | Old Evidence | Old Run | New Candidate | New Run | Decision | Timestamp |",
             "|---|---|---|---|---|---|---|"]
    for d in decisions:
        lines.append(f"| {d.get('claim_id', '')} | {d.get('old_evidence_id', '')} | "
                     f"{d.get('old_run', '')} | {d.get('new_evidence_id', '')} | "
                     f"{d.get('new_run', '')} | {d.get('decision', '')} | {d.get('at', '')} |")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


