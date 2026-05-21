from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from shared.research_output import now_iso, write_excel_with_readme


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


def _review_instruction_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
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
    )


def create_review_templates(out_dir: Path, sample_size: int = 50) -> Dict[str, str]:
    out_dir = Path(out_dir)
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
        path = review_dir / "source_country_review.xlsx"
        write_excel_with_readme(
            str(path),
            {
                "SourceCountryReview": source_review,
                "SuggestedCountryReview": suggested_review,
                "Instructions": _review_instruction_df(),
            },
            title="Source and country review template",
            description="Human review template for source normalization and country inference.",
            fields={
                "auto_result": "Automated country/source result.",
                "human_result": "Reviewer-corrected value.",
                "is_correct": "1 correct, 0 incorrect, blank not reviewed.",
                "error_type": "Reviewer-selected error category.",
            },
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

    if not modifier_review.empty or not semantic_review.empty or not kwic.empty:
        path = review_dir / "modifier_semantic_review.xlsx"
        write_excel_with_readme(
            str(path),
            {
                "ModifierReview": modifier_review,
                "SemanticProsodyReview": semantic_review,
                "KWICSample": kwic,
                "Instructions": _review_instruction_df(),
            },
            title="Modifier and semantic-prosody review template",
            description="Human review template for modifier extraction, KWIC context checks, semantic prosody, and frame coding.",
            fields={
                "auto_result": "Automated expression or polarity candidate.",
                "human_result": "Reviewer-corrected expression or label.",
                "frame_type": "Optional frame code such as security, economy, morality, conflict, cooperation, development, legitimacy, risk.",
                "is_correct": "1 correct, 0 incorrect, blank not reviewed.",
            },
            parameters={"sample_size": sample_size},
        )
        paths["modifier_semantic_review"] = str(path)

    return paths


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

    report_path = reports_dir / "validation_report.xlsx"
    write_excel_with_readme(
        str(report_path),
        {"ValidationSummary": summary},
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
    reports_dir = out_dir / "07_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    method_summary = reports_dir / "method_summary.md"
    method_summary.write_text(
        """# Method Summary

This project uses a corpus-assisted discourse studies workflow. LexisNexis DOCX exports are split into article-level TXT files with source metadata. Source names are normalized and optionally assigned country candidates through hand rules, heuristics, and Wikidata evidence. Target terms are then analyzed through KWIC contexts, adjective and phrase candidates, collocates, and semantic-prosody candidate labels.

Automated outputs are treated as candidate evidence. Final claims should be based on KWIC/context reading and documented human review.
""",
        encoding="utf-8",
    )

    limitations = reports_dir / "method_limitations.md"
    limitations.write_text(
        """# Method Limitations

- Source normalization may merge distinct outlets or fail to merge aliases.
- Country inference is an auxiliary variable and should be manually reviewed before comparative claims.
- Modifier and collocate extraction depend on tokenization, POS tagging, parsing, and window size.
- Semantic-prosody candidate labels use a small seed list and are not final sentiment judgments.
- OCR or Lexis export formatting can affect downstream text quality.
- Automated results should be interpreted through KWIC context and, where possible, sampled validation.
""",
        encoding="utf-8",
    )

    return {"method_summary": str(method_summary), "method_limitations": str(limitations)}


def generate_validation_artifacts(out_dir: Path, sample_size: int = 50) -> Dict[str, str]:
    paths = {}
    paths.update(create_review_templates(out_dir, sample_size=sample_size))
    report = create_validation_report(out_dir)
    if report:
        paths["validation_report"] = report
    paths.update(create_method_outputs(out_dir))
    return paths
