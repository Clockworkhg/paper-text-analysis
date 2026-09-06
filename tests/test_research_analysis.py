from pathlib import Path

import pandas as pd

from shared.research_output import write_excel_with_readme
from shared.validation import create_validation_report, generate_validation_artifacts
from modules.txt_modifier_extractor_gui import (
    log_likelihood_2x2,
    parse_doc_metadata,
    polarity_candidate,
)


def test_parse_doc_metadata_with_lexis_headers():
    text = (
        "<DOCUMENT_ID>: doc_123\n<CORPUS_ID>: corpus_abc\n<RUN_ID>: run_xyz\n"
        "<TITLE>: Story\n<SOURCE>: BBC | Reuters\n<DATE>: 2024-01-02\n\n----- BODY -----\n\nChina is important."
    )
    meta = parse_doc_metadata(text)
    assert meta["Source"] == "BBC | Reuters"
    assert meta["Date"] == "2024-01-02"
    assert meta["Title"] == "Story"
    assert meta["Document_ID"] == "doc_123"
    assert meta["Corpus_ID"] == "corpus_abc"
    assert meta["Run_ID"] == "run_xyz"
    assert meta["Body"] == "China is important."


def test_polarity_candidate_seed_labels():
    assert polarity_candidate("stable")[0] == "positive_candidate"
    assert polarity_candidate("dangerous")[0] == "negative_candidate"
    assert polarity_candidate("stable but dangerous")[0] == "mixed_candidate"
    assert polarity_candidate("regional")[0] == "uncoded_candidate"


def test_log_likelihood_non_negative():
    assert log_likelihood_2x2(5, 10, 20, 100) >= 0
    assert log_likelihood_2x2(0, 0, 0, 0) == 0


def test_excel_readme_is_not_first_sheet(tmp_path: Path):
    out = tmp_path / "out.xlsx"
    write_excel_with_readme(
        str(out),
        {"Data": pd.DataFrame({"A": [1, 2]})},
        title="Test",
        description="Test workbook",
    )
    xls = pd.ExcelFile(out)
    assert xls.sheet_names == ["Data", "README"]
    assert len(pd.read_excel(out)) == 2


def test_generate_validation_artifacts_from_partial_outputs(tmp_path: Path):
    merged = tmp_path / "merged_sources.xlsx"
    write_excel_with_readme(
        str(merged),
        {
            "WithCountry": pd.DataFrame(
                {"Source_Merged": ["BBC"], "Count_Sum": [2], "Country": ["United Kingdom"]}
            ),
            "SuggestedOverrides": pd.DataFrame(
                {"Source_Merged": ["CNN"], "Suggested_Country": ["United States"], "Confidence": [0.95]}
            ),
        },
        title="Merged",
        description="Merged sources",
    )
    analysis = tmp_path / "adjectives_phrases.xlsx"
    write_excel_with_readme(
        str(analysis),
        {
            "Adjectives": pd.DataFrame({"Target": ["China"], "Adjective": ["stable"], "Frequency": [3]}),
            "Phrases": pd.DataFrame({"Target": ["China"], "Modifier_Phrase": ["very stable"], "Frequency": [2]}),
            "SemanticProsodyCandidates": pd.DataFrame(
                {
                    "Target": ["China"],
                    "Expression": ["stable"],
                    "Polarity_Candidate": ["positive_candidate"],
                    "Frequency": [3],
                }
            ),
            "KWIC": pd.DataFrame({"Target": ["China"], "Full_Context": ["China is stable"]}),
        },
        title="Analysis",
        description="Analysis outputs",
    )

    paths = generate_validation_artifacts(tmp_path, sample_size=10)
    assert Path(paths["source_country_review"]).exists()
    assert Path(paths["modifier_semantic_review"]).exists()
    assert Path(paths["validation_report"]).exists()
    assert (tmp_path / "07_reports" / "method_summary.md").exists()


def test_create_validation_report_reads_completed_review(tmp_path: Path):
    review_dir = tmp_path / "06_review"
    review_dir.mkdir()
    write_excel_with_readme(
        str(review_dir / "source_country_review.xlsx"),
        {
            "SourceCountryReview": pd.DataFrame(
                {"is_correct": [1, 0], "error_type": ["", "country_error"]}
            )
        },
        title="Review",
        description="Review",
    )
    report = create_validation_report(tmp_path)
    summary = pd.read_excel(report, sheet_name="ValidationSummary")
    row = summary[summary["Check"] == "source_country"].iloc[0]
    assert row["Reviewed"] == 2
    assert row["Correct"] == 1
    assert row["Accuracy"] == 0.5


# ---------------------------------------------------------------------------
# Grouping modes in the analysis engine (requires spaCy)
# ---------------------------------------------------------------------------

import pytest

from config import TxtAnalysisConfig
from modules.txt_modifier_extractor import process_txt, resolve_group_label


def _spacy_available() -> bool:
    try:
        import spacy
        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False


requires_spacy = pytest.mark.skipif(not _spacy_available(), reason="spaCy/en_core_web_sm unavailable")


def _synthetic_corpus(tmp_path):
    docs = []
    for source, source_norm, doc_id in (
        ("BBC News", "BBC", "doc_a"),
        ("Voice of News", "VOA", "doc_b"),
    ):
        docs.append(
            f"<DOCUMENT_ID>: {doc_id}\n<SOURCE>: {source}\n<SOURCE_NORM>: {source_norm}\n"
            f"<TITLE>: Story\n\n----- BODY -----\n\n"
            f"China faces serious pressure. Observers warn the situation is difficult."
        )
    corpus = tmp_path / "merged.txt"
    corpus.write_text("\n\n==========\n\n".join(docs), encoding="utf-8")
    return corpus


def _run_process_txt(tmp_path, group_by, group_map=None):
    corpus = _synthetic_corpus(tmp_path)
    output = tmp_path / "out.xlsx"
    cfg = TxtAnalysisConfig(
        split_mode="regex",
        split_regex="====LINE====",
        window_tokens=8,
        phrase_max_tokens=6,
        group_by=group_by,
    )
    process_txt(str(corpus), str(output), ["China"], cfg, group_map=group_map)
    return pd.ExcelFile(output)


def test_resolve_group_label_modes():
    meta = {"Source": "BBC News", "Source_Norm": "BBC", "Document_ID": "doc_a"}
    assert resolve_group_label(meta, "source") == "BBC News"
    assert resolve_group_label(meta, "institution") == "BBC"
    assert resolve_group_label(meta, "country", {"doc_a": "UK"}) == "UK"
    assert resolve_group_label(meta, "country", {"BBC": "UK"}) == "UK"
    # No mapping entry -> fall back to institution-level label, not Unknown.
    assert resolve_group_label(meta, "country", {}) == "BBC"
    assert resolve_group_label(meta, "custom", {"doc_a": "Anglosphere"}) == "Anglosphere"
    assert resolve_group_label({"Source": "X", "Source_Norm": "", "Document_ID": ""}, "institution") == "X"


@requires_spacy
def test_process_txt_source_mode_keeps_raw_header_groups(tmp_path):
    xls = _run_process_txt(tmp_path, "source")
    group = xls.parse("GroupComparison")
    assert set(group["Group_By"]) == {"source"}
    assert set(group["Source_Group"]) == {"BBC News", "Voice of News"}


@requires_spacy
def test_process_txt_institution_mode_groups_by_normalized_source(tmp_path):
    xls = _run_process_txt(tmp_path, "institution")
    group = xls.parse("GroupComparison")
    assert set(group["Group_By"]) == {"institution"}
    assert set(group["Source_Group"]) == {"BBC", "VOA"}

    kwic = xls.parse("KWIC")
    assert "Source_Normalized" in kwic.columns
    assert "Group" in kwic.columns
    assert set(kwic["Source_Normalized"]) == {"BBC", "VOA"}
    assert set(kwic["Group"]) == {"BBC", "VOA"}


@requires_spacy
def test_process_txt_country_mode_uses_group_map(tmp_path):
    group_map = {"doc_a": "United Kingdom", "doc_b": "United States"}
    xls = _run_process_txt(tmp_path, "country", group_map=group_map)
    group = xls.parse("GroupComparison")
    assert set(group["Group_By"]) == {"country"}
    assert set(group["Source_Group"]) == {"United Kingdom", "United States"}

    kwic = xls.parse("KWIC")
    assert set(kwic["Group"]) == {"United Kingdom", "United States"}


@requires_spacy
def test_process_txt_meta_records_group_by(tmp_path):
    xls = _run_process_txt(tmp_path, "institution", group_map={"BBC": "BBC"})
    meta = xls.parse("Meta")
    assert meta.iloc[0]["Group_By"] == "institution"
    assert meta.iloc[0]["Group_Map_Size"] == 1
