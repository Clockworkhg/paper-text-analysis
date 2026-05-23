from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from shared.research_output import now_iso, write_excel_with_readme
from shared.research_templates import get_template


# ================================================================
#  Inter-rater Reliability — Cohen's kappa & Krippendorff's alpha
# ================================================================

def _cohens_kappa(a: pd.Series, b: pd.Series) -> Dict[str, Any]:
    """Cohen's kappa for binary agreement (is_correct: 1/0).

    Returns dict with kappa, p_o, p_e, n_pairs, interpretation.
    """
    mask = a.notna() & b.notna()
    a_clean = a[mask].astype(int)
    b_clean = b[mask].astype(int)
    n = len(a_clean)

    if n == 0:
        return {"kappa": None, "p_o": None, "p_e": None,
                "n_pairs": 0, "interpretation": "无数据"}

    n_11 = int(((a_clean == 1) & (b_clean == 1)).sum())
    n_10 = int(((a_clean == 1) & (b_clean == 0)).sum())
    n_01 = int(((a_clean == 0) & (b_clean == 1)).sum())
    n_00 = int(((a_clean == 0) & (b_clean == 0)).sum())

    p_o = (n_11 + n_00) / n

    p_a1 = (n_11 + n_10) / n
    p_b1 = (n_11 + n_01) / n
    p_a0 = 1.0 - p_a1
    p_b0 = 1.0 - p_b1
    p_e = p_a1 * p_b1 + p_a0 * p_b0

    if p_e == 1.0:
        kappa = 1.0
    else:
        kappa = (p_o - p_e) / (1.0 - p_e)

    if kappa is None or (isinstance(kappa, float) and np.isnan(kappa)):
        interp = "数据不足"
    elif kappa < 0.0:
        interp = "低于随机水平"
    elif kappa < 0.20:
        interp = "轻微一致 (slight)"
    elif kappa < 0.40:
        interp = "一般一致 (fair)"
    elif kappa < 0.60:
        interp = "中等一致 (moderate)"
    elif kappa < 0.80:
        interp = "高度一致 (substantial)"
    else:
        interp = "几乎完美 (almost perfect)"

    return {
        "kappa": round(float(kappa), 4) if kappa is not None else None,
        "p_o": round(p_o, 4),
        "p_e": round(p_e, 4),
        "n_pairs": n,
        "agreement_rate": round(p_o * 100, 1),
        "table_2x2": [[n_11, n_10], [n_01, n_00]],
        "interpretation": interp,
    }


def _krippendorff_alpha_nominal(a: pd.Series, b: pd.Series) -> Dict[str, Any]:
    """Krippendorff's alpha for nominal (categorical) data with 2 coders.

    Suitable for error_type, coding fields, and any multi-category annotation.
    Returns dict with alpha, D_o, D_e, n_pairs, n_categories, interpretation.
    """
    mask = a.notna() & b.notna()
    a_clean = a[mask].astype(str).str.strip()
    b_clean = b[mask].astype(str).str.strip()

    # Drop empty strings (treated as missing)
    non_empty = (a_clean != "") & (b_clean != "")
    a_clean = a_clean[non_empty]
    b_clean = b_clean[non_empty]
    n = len(a_clean)

    if n <= 1:
        return {"alpha": None, "D_o": None, "D_e": None,
                "n_pairs": n, "n_categories": 0, "interpretation": "数据不足 (需 ≥2 对)"}

    # Build coincidence matrix
    categories = sorted(set(a_clean) | set(b_clean))
    k = len(categories)
    if k <= 1:
        return {"alpha": 1.0, "D_o": 0.0, "D_e": 0.0,
                "n_pairs": n, "n_categories": 1, "interpretation": "所有编码员完全一致"}

    o_mat = np.zeros((k, k))
    for i in range(n):
        ci = categories.index(a_clean.iloc[i])
        cj = categories.index(b_clean.iloc[i])
        o_mat[ci, cj] += 1.0

    # D_o = observed disagreement proportion
    D_o = 1.0 - np.trace(o_mat) / n

    # D_e = expected disagreement under independence
    # For 2 coders: D_e = 1 - Σ_c P_A(c) * P_B(c)
    prop_a = np.array([(a_clean == cat).sum() / n for cat in categories])
    prop_b = np.array([(b_clean == cat).sum() / n for cat in categories])
    D_e = 1.0 - np.sum(prop_a * prop_b)

    if D_e == 0.0:
        alpha = 1.0 if D_o == 0.0 else 0.0
    else:
        alpha = 1.0 - (D_o / D_e)

    if alpha is None or (isinstance(alpha, float) and np.isnan(alpha)):
        interp = "数据不足"
    elif alpha < 0.0:
        interp = "低于随机水平"
    elif alpha < 0.20:
        interp = "轻微一致 (slight)"
    elif alpha < 0.40:
        interp = "一般一致 (fair)"
    elif alpha < 0.60:
        interp = "中等一致 (moderate)"
    elif alpha < 0.80:
        interp = "高度一致 (substantial)"
    else:
        interp = "几乎完美 (almost perfect)"

    return {
        "alpha": round(float(alpha), 4) if alpha is not None else None,
        "D_o": round(float(D_o), 4),
        "D_e": round(float(D_e), 4),
        "n_pairs": n,
        "n_categories": k,
        "agreement_rate": round((1.0 - D_o) * 100, 1),
        "interpretation": interp,
    }


def _percent_agreement(a: pd.Series, b: pd.Series) -> float:
    """Simple percentage agreement between two coders."""
    mask = a.notna() & b.notna()
    if mask.sum() == 0:
        return float("nan")
    return round((a[mask] == b[mask]).sum() / mask.sum() * 100, 1)


def _read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()


def _sample(df: pd.DataFrame, n: int, sort_col: Optional[str] = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    if sort_col and sort_col in out.columns:
        out = out.sort_values(sort_col, ascending=False)
    return out.head(n).reset_index(drop=True)


def _review_instruction_df(corpus_type: str = "generic") -> pd.DataFrame:
    template = get_template(corpus_type)
    rows = [
            {
                "Field": "human_result",
                "Instruction": "Enter the reviewer-corrected label, source, country, expression, or frame.",
            },
            {
                "Field": "is_correct",
                "Instruction": "Use 1 for correct, 0 for incorrect, blank for not reviewed.",
            },
            {
                "Field": "error_type",
                "Instruction": "Optional: normalization_error, country_error, extraction_error, polarity_error, context_error, other.",
            },
            {
                "Field": "notes",
                "Instruction": "Optional evidence, KWIC comment, or reason for correction.",
            },
        ]
    for field in template.get("coding_fields", []):
        rows.append({"Field": field["name"], "Instruction": field["instruction"]})
    rows.append({"Field": "template_id", "Instruction": f"Research template: {template['template_id']} ({template['label']})."})
    return pd.DataFrame(rows)


def _infer_corpus_type(out_dir: Path) -> str:
    manifest = out_dir / "01_corpus" / "corpus_manifest.json"
    if manifest.exists():
        try:
            import json

            data = json.loads(manifest.read_text(encoding="utf-8"))
            return str(data.get("corpus_type") or "generic")
        except Exception:
            return "generic"
    return "generic"


def _add_template_columns(df: pd.DataFrame, corpus_type: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for field in get_template(corpus_type).get("coding_fields", []):
        if field["name"] not in out.columns:
            out[field["name"]] = ""
    return out


def create_review_templates(out_dir: Path, sample_size: int = 50,
                           dual_coder: bool = False) -> Dict[str, str]:
    out_dir = Path(out_dir)
    corpus_type = _infer_corpus_type(out_dir)
    template = get_template(corpus_type)
    review_dir = out_dir / "06_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    paths: Dict[str, str] = {}

    merged_path = out_dir / "merged_sources.xlsx"
    with_country = _sample(_read_sheet(merged_path, "WithCountry"), sample_size, "Count_Sum")
    suggested = _sample(_read_sheet(merged_path, "SuggestedOverrides"), sample_size, "Confidence")

    source_review = pd.DataFrame()
    if not with_country.empty:
        source_review = with_country.copy()
        source_review.insert(0, "review_id", [f"source_country_{i+1:04d}" for i in range(len(source_review))])
        source_review["auto_result"] = source_review.get("Country", "")
        source_review["human_result"] = ""
        source_review["is_correct"] = ""
        source_review["error_type"] = ""
        source_review["notes"] = ""

    suggested_review = pd.DataFrame()
    if not suggested.empty:
        suggested_review = suggested.copy()
        suggested_review.insert(0, "review_id", [f"suggestion_{i+1:04d}" for i in range(len(suggested_review))])
        suggested_review["auto_result"] = suggested_review.get("Suggested_Country", "")
        suggested_review["human_result"] = ""
        suggested_review["is_correct"] = ""
        suggested_review["error_type"] = ""
        suggested_review["notes"] = ""

    if not source_review.empty or not suggested_review.empty:
        sheets_src = {
            "SourceCountryReview": source_review,
            "SuggestedCountryReview": suggested_review,
            "Instructions": _review_instruction_df(corpus_type),
        }
        fields_src = {
            "auto_result": "Automated country/source result.",
            "human_result": "Reviewer-corrected value.",
            "is_correct": "1 correct, 0 incorrect, blank not reviewed.",
            "error_type": "Reviewer-selected error category.",
        }
        if dual_coder:
            for suffix in ("coder_a", "coder_b"):
                path = review_dir / f"source_country_review_{suffix}.xlsx"
                write_excel_with_readme(
                    str(path), sheets_src,
                    title=f"Source and country review — {suffix.replace('_', ' ').upper()}",
                    description="Human review template for source normalization and country inference.",
                    fields=fields_src,
                    parameters={"sample_size": sample_size, "coder": suffix},
                )
                paths[f"source_country_review_{suffix}"] = str(path)
        else:
            path = review_dir / "source_country_review.xlsx"
            write_excel_with_readme(
                str(path), sheets_src,
                title="Source and country review template",
                description="Human review template for source normalization and country inference.",
                fields=fields_src,
                parameters={"sample_size": sample_size},
            )
            paths["source_country_review"] = str(path)

    analysis_path = out_dir / "adjectives_phrases.xlsx"
    adjectives = _sample(_read_sheet(analysis_path, "Adjectives"), sample_size, "Frequency")
    phrases = _sample(_read_sheet(analysis_path, "Phrases"), sample_size, "Frequency")
    semantic = _sample(_read_sheet(analysis_path, "SemanticProsodyCandidates"), sample_size, "Frequency")
    kwic = _sample(_read_sheet(analysis_path, "KWIC"), sample_size)

    modifier_review_parts = []
    for kind, df, expr_col in [
        ("adjective", adjectives, "Adjective"),
        ("phrase", phrases, "Modifier_Phrase"),
    ]:
        if df.empty:
            continue
        part = df.copy()
        part.insert(0, "review_id", [f"{kind}_{i+1:04d}" for i in range(len(part))])
        part.insert(1, "kind", kind)
        part["auto_result"] = part.get(expr_col, "")
        part["human_result"] = ""
        part["is_correct"] = ""
        part["error_type"] = ""
        part["notes"] = ""
        modifier_review_parts.append(part)

    modifier_review = pd.concat(modifier_review_parts, ignore_index=True) if modifier_review_parts else pd.DataFrame()

    semantic_review = pd.DataFrame()
    if not semantic.empty:
        semantic_review = semantic.copy()
        semantic_review.insert(0, "review_id", [f"semantic_{i+1:04d}" for i in range(len(semantic_review))])
        semantic_review["auto_result"] = semantic_review.get("Polarity_Candidate", "")
        semantic_review["human_result"] = ""
        semantic_review["is_correct"] = ""
        semantic_review["error_type"] = ""
        semantic_review["frame_type"] = ""
        semantic_review["notes"] = ""
        semantic_review = _add_template_columns(semantic_review, corpus_type)

    if not modifier_review.empty or not semantic_review.empty or not kwic.empty:
        sheets_mod = {
            "ModifierReview": modifier_review,
            "SemanticProsodyReview": semantic_review,
            "KWICSample": kwic,
            "Instructions": _review_instruction_df(corpus_type),
        }
        fields_mod = {
            "auto_result": "Automated expression or polarity candidate.",
            "human_result": "Reviewer-corrected expression or label.",
            "frame_type": "Legacy optional frame code. Prefer template-specific coding columns when available.",
            "is_correct": "1 correct, 0 incorrect, blank not reviewed.",
            **{field["name"]: field["instruction"] for field in template.get("coding_fields", [])},
        }
        if dual_coder:
            for suffix in ("coder_a", "coder_b"):
                path = review_dir / f"modifier_semantic_review_{suffix}.xlsx"
                write_excel_with_readme(
                    str(path), sheets_mod,
                    title=f"Modifier and semantic-prosody review — {suffix.replace('_', ' ').upper()}",
                    description=f"Human review template for {template['label']}: {template['method_focus']}",
                    fields=fields_mod,
                    parameters={"sample_size": sample_size, "corpus_type": corpus_type,
                                "template": template["label"], "coder": suffix},
                )
                paths[f"modifier_semantic_review_{suffix}"] = str(path)
        else:
            path = review_dir / "modifier_semantic_review.xlsx"
            write_excel_with_readme(
                str(path), sheets_mod,
                title="Modifier and semantic-prosody review template",
                description=f"Human review template for {template['label']}: {template['method_focus']}",
                fields=fields_mod,
                parameters={"sample_size": sample_size, "corpus_type": corpus_type,
                            "template": template["label"]},
            )
            paths["modifier_semantic_review"] = str(path)

    return paths


# ================================================================
#  Dual-coder IRR computation
# ================================================================

def compute_dual_coder_irr(review_dir: Path) -> Dict[str, Any]:
    """Compute inter-rater reliability between two independent coders.

    Searches for coder_a / coder_b review files in review_dir,
    pairs them by matching rows on review_id, and computes:
      - Cohen's kappa for is_correct (binary)
      - Krippendorff's alpha for error_type and template coding fields
      - Percentage agreement for all judgment columns

    Returns a dict with per-sheet IRR DataFrames and a summary.
    """
    review_dir = Path(review_dir)
    if not review_dir.exists():
        return {"status": "no_review_dir", "summary": None, "sheets": {}}

    # Discover coder A / B files
    a_files = sorted(review_dir.glob("*_coder_a.xlsx"))
    b_files = sorted(review_dir.glob("*_coder_b.xlsx"))

    if not a_files or not b_files:
        return {"status": "missing_coder_files", "summary": None, "sheets": {}}

    all_results: Dict[str, pd.DataFrame] = {}
    summary_rows: List[Dict[str, Any]] = []

    for a_path in a_files:
        base_name = a_path.name.replace("_coder_a.xlsx", "")
        b_path = review_dir / f"{base_name}_coder_b.xlsx"
        if not b_path.exists():
            continue

        try:
            xl_a = pd.ExcelFile(a_path)
            xl_b = pd.ExcelFile(b_path)
        except Exception:
            continue

        common_sheets = [s for s in xl_a.sheet_names if s in xl_b.sheet_names
                         and s not in ("Instructions",)]

        for sheet in common_sheets:
            try:
                df_a = pd.read_excel(a_path, sheet_name=sheet)
                df_b = pd.read_excel(b_path, sheet_name=sheet)
            except Exception:
                continue

            if "review_id" not in df_a.columns or "review_id" not in df_b.columns:
                continue

            # Merge on review_id
            merged = df_a[["review_id"]].copy()
            for col in df_a.columns:
                if col in ("review_id",):
                    continue
                merged[f"{col}_A"] = df_a[col].values
            for col in df_b.columns:
                if col in ("review_id",):
                    continue
                merged[f"{col}_B"] = df_b[col].values

            irr_rows: List[Dict[str, Any]] = []

            # is_correct → Cohen's kappa
            if "is_correct" in df_a.columns and "is_correct" in df_b.columns:
                k_result = _cohens_kappa(
                    pd.to_numeric(df_a["is_correct"], errors="coerce"),
                    pd.to_numeric(df_b["is_correct"], errors="coerce"),
                )
                irr_rows.append({
                    "Sheet": sheet,
                    "Field": "is_correct",
                    "Metric": "Cohen's κ",
                    "Value": k_result.get("kappa"),
                    "Agreement_%": k_result.get("agreement_rate"),
                    "n_Pairs": k_result.get("n_pairs"),
                    "Interpretation": k_result.get("interpretation"),
                    "Notes": f"p_o={k_result.get('p_o')}, p_e={k_result.get('p_e')}",
                })

            # error_type → Krippendorff's alpha
            if "error_type" in df_a.columns and "error_type" in df_b.columns:
                a_result = _krippendorff_alpha_nominal(
                    df_a["error_type"].fillna(""),
                    df_b["error_type"].fillna(""),
                )
                irr_rows.append({
                    "Sheet": sheet,
                    "Field": "error_type",
                    "Metric": "Krippendorff's α",
                    "Value": a_result.get("alpha"),
                    "Agreement_%": a_result.get("agreement_rate"),
                    "n_Pairs": a_result.get("n_pairs"),
                    "Interpretation": a_result.get("interpretation"),
                    "Notes": f"{a_result.get('n_categories', 0)} categories, D_o={a_result.get('D_o')}, D_e={a_result.get('D_e')}",
                })

            # Template coding fields → Krippendorff's alpha
            for col in df_a.columns:
                if col in ("review_id", "auto_result", "human_result",
                           "is_correct", "error_type", "notes", "kind", "frame_type"):
                    continue
                if col not in df_b.columns:
                    continue
                a_result = _krippendorff_alpha_nominal(
                    df_a[col].fillna(""),
                    df_b[col].fillna(""),
                )
                if (a_result.get("n_pairs") or 0) < 2:
                    continue
                irr_rows.append({
                    "Sheet": sheet,
                    "Field": col,
                    "Metric": "Krippendorff's α",
                    "Value": a_result.get("alpha"),
                    "Agreement_%": a_result.get("agreement_rate"),
                    "n_Pairs": a_result.get("n_pairs"),
                    "Interpretation": a_result.get("interpretation"),
                    "Notes": f"{a_result.get('n_categories', 0)} categories",
                })

            if irr_rows:
                all_results[f"{base_name}/{sheet}"] = pd.DataFrame(irr_rows)
                summary_rows.extend(irr_rows)

    if not summary_rows:
        return {"status": "no_judgments_found", "summary": None, "sheets": all_results}

    summary = pd.DataFrame(summary_rows)
    return {"status": "ok", "summary": summary, "sheets": all_results}


def _accuracy_from_sheet(path: Path, sheet_name: str, label: str) -> pd.DataFrame:
    df = _read_sheet(path, sheet_name)
    if df.empty or "is_correct" not in df.columns:
        return pd.DataFrame(
            [{"Check": label, "Reviewed": 0, "Correct": 0, "Accuracy": "", "Most_Common_Error": ""}]
        )

    reviewed = df[df["is_correct"].notna() & (df["is_correct"].astype(str).str.strip() != "")]
    if reviewed.empty:
        return pd.DataFrame(
            [{"Check": label, "Reviewed": 0, "Correct": 0, "Accuracy": "", "Most_Common_Error": ""}]
        )
    correct = pd.to_numeric(reviewed["is_correct"], errors="coerce").fillna(0).astype(int).sum()
    errors = reviewed.loc[pd.to_numeric(reviewed["is_correct"], errors="coerce").fillna(0).astype(int) == 0]
    most_common_error = ""
    if "error_type" in errors.columns and not errors.empty:
        counts = errors["error_type"].dropna().astype(str)
        if not counts.empty:
            most_common_error = counts.value_counts().index[0]
    return pd.DataFrame(
        [
            {
                "Check": label,
                "Reviewed": len(reviewed),
                "Correct": int(correct),
                "Accuracy": round(correct / len(reviewed), 4),
                "Most_Common_Error": most_common_error,
            }
        ]
    )


def compute_llm_validation(out_dir: Path) -> Optional[Dict[str, Any]]:
    """Cross-reference LLM filter decisions with human review judgments.

    Reads LLM_Decisions from adjectives_phrases.xlsx and ModifierReview from
    modifier_semantic_review.xlsx, matches on (Target, kind, candidate), and
    computes precision, recall, F1 for the LLM filter.

    Returns None if either data source is missing.
    """
    out_dir = Path(out_dir)
    analysis_path = out_dir / "adjectives_phrases.xlsx"
    review_path = out_dir / "06_review" / "modifier_semantic_review.xlsx"

    if not analysis_path.exists() or not review_path.exists():
        return None

    try:
        xls = pd.ExcelFile(analysis_path)
    except Exception:
        return None

    if "LLM_Decisions" not in xls.sheet_names:
        return None

    llm_df = pd.read_excel(analysis_path, sheet_name="LLM_Decisions")
    if llm_df.empty:
        return None

    try:
        human_df = pd.read_excel(review_path, sheet_name="ModifierReview")
    except Exception:
        return None

    if human_df.empty or "is_correct" not in human_df.columns or "auto_result" not in human_df.columns:
        return None

    human_reviewed = human_df[
        human_df["is_correct"].notna() & (human_df["is_correct"].astype(str).str.strip() != "")
    ].copy()
    if human_reviewed.empty:
        return None

    human_reviewed["is_correct_int"] = (
        pd.to_numeric(human_reviewed["is_correct"], errors="coerce").fillna(0).astype(int)
    )

    matches = []
    for _, hrow in human_reviewed.iterrows():
        target = str(hrow.get("Target", "")).strip().lower()
        kind = str(hrow.get("kind", "")).strip().lower()
        expr = str(hrow.get("auto_result", "")).strip().lower()
        human_correct = int(hrow["is_correct_int"])

        llm_match = llm_df[
            (llm_df["Target"].astype(str).str.strip().str.lower() == target)
            & (llm_df["Kind"].astype(str).str.strip().str.lower() == kind)
            & (llm_df["Candidate"].astype(str).str.strip().str.lower() == expr)
        ]

        if llm_match.empty:
            continue

        llm_kept = int((llm_match["GPT_Verdict"] == "kept").any())
        matches.append({
            "Target": hrow.get("Target", ""),
            "Kind": kind,
            "Expression": expr,
            "LLM_Kept": llm_kept,
            "Human_Correct": human_correct,
        })

    if not matches:
        return None

    df = pd.DataFrame(matches)
    tp = int(((df["LLM_Kept"] == 1) & (df["Human_Correct"] == 1)).sum())
    fp = int(((df["LLM_Kept"] == 1) & (df["Human_Correct"] == 0)).sum())
    tn = int(((df["LLM_Kept"] == 0) & (df["Human_Correct"] == 0)).sum())
    fn = int(((df["LLM_Kept"] == 0) & (df["Human_Correct"] == 1)).sum())

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0
    accuracy = round((tp + tn) / len(df), 4) if len(df) > 0 else 0.0

    return {
        "n_matched": len(df),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "detail_df": df,
    }


def create_validation_report(out_dir: Path) -> Optional[str]:
    out_dir = Path(out_dir)
    review_dir = out_dir / "06_review"
    reports_dir = out_dir / "07_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    source_review = review_dir / "source_country_review.xlsx"
    modifier_review = review_dir / "modifier_semantic_review.xlsx"

    frames = [
        _accuracy_from_sheet(source_review, "SourceCountryReview", "source_country"),
        _accuracy_from_sheet(source_review, "SuggestedCountryReview", "suggested_country"),
        _accuracy_from_sheet(modifier_review, "ModifierReview", "modifier_extraction"),
        _accuracy_from_sheet(modifier_review, "SemanticProsodyReview", "semantic_prosody_candidate"),
    ]
    summary = pd.concat(frames, ignore_index=True)

    report_sheets = {"ValidationSummary": summary}

    # Check for dual-coder review files and compute IRR
    irr_result = compute_dual_coder_irr(review_dir)
    if irr_result["status"] == "ok" and irr_result["summary"] is not None:
        report_sheets["InterraterReliability"] = irr_result["summary"]

    # Cross-reference LLM filter with human review (if both exist)
    llm_val = compute_llm_validation(out_dir)
    if llm_val is not None:
        llm_summary = pd.DataFrame([{
            "Metric": "LLM Filter vs Human Review",
            "Matched_Pairs": llm_val["n_matched"],
            "True_Positive": llm_val["tp"],
            "False_Positive": llm_val["fp"],
            "True_Negative": llm_val["tn"],
            "False_Negative": llm_val["fn"],
            "Precision": llm_val["precision"],
            "Recall": llm_val["recall"],
            "F1": llm_val["f1"],
            "Accuracy": llm_val["accuracy"],
        }])
        report_sheets["LLM_Validation"] = llm_summary
        report_sheets["LLM_Validation_Detail"] = llm_val["detail_df"]

    report_path = reports_dir / "validation_report.xlsx"
    write_excel_with_readme(
        str(report_path),
        report_sheets,
        title="Validation report",
        description="Aggregates human review results. Blank accuracy means no reviewed rows have been filled yet.",
        fields={
            "Reviewed": "Number of rows with is_correct filled.",
            "Correct": "Number of reviewed rows marked correct.",
            "Accuracy": "Correct / Reviewed.",
            "Most_Common_Error": "Most common error_type among incorrect reviewed rows.",
        },
        parameters={"generated_at": now_iso()},
    )
    return str(report_path)


def create_method_outputs(out_dir: Path) -> Dict[str, str]:
    out_dir = Path(out_dir)
    corpus_type = _infer_corpus_type(out_dir)
    template = get_template(corpus_type)
    reports_dir = out_dir / "07_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    method_summary = reports_dir / "method_summary.md"
    coding_fields = "\n".join(
        f"- `{field['name']}`: {field['instruction']}"
        for field in template.get("coding_fields", [])
    ) or "- No template-specific coding fields."
    method_summary.write_text(
        f"""# Method Summary

Research template: `{template['template_id']}` - {template['label']}.

{template['description']}

Method focus: {template['method_focus']}

Target terms are analyzed through KWIC contexts, adjective and phrase candidates, collocates, and semantic-prosody candidate labels. Automated outputs are treated as candidate evidence. Final claims should be based on KWIC/context reading and documented human review.

## Template Coding Fields

{coding_fields}
""",
        encoding="utf-8",
    )

    limitations = reports_dir / "method_limitations.md"
    template_limitations = "\n".join(f"- {item}" for item in template.get("limitations", []))
    limitations.write_text(
        f"""# Method Limitations

- Source normalization may merge distinct outlets or fail to merge aliases.
- Inferred or imported metadata should be manually reviewed before comparative claims.
- Modifier and collocate extraction depend on tokenization, POS tagging, parsing, and window size.
- Semantic-prosody candidate labels use a small seed list and are not final sentiment judgments.
- OCR, export formatting, table column mapping, or transcript quality can affect downstream text quality.
- Automated results should be interpreted through KWIC context and, where possible, sampled validation.

## Template-Specific Limitations

{template_limitations}
""",
        encoding="utf-8",
    )

    return {"method_summary": str(method_summary), "method_limitations": str(limitations)}


def generate_validation_artifacts(out_dir: Path, sample_size: int = 50,
                                  dual_coder: bool = False) -> Dict[str, str]:
    paths = {}
    paths.update(create_review_templates(out_dir, sample_size=sample_size,
                                         dual_coder=dual_coder))
    report = create_validation_report(out_dir)
    if report:
        paths["validation_report"] = report
    paths.update(create_method_outputs(out_dir))
    return paths
