from pathlib import Path

import pandas as pd

from shared.research_output import write_excel_with_readme
from shared.validation import create_validation_report, generate_validation_artifacts
from txt_modifier_extractor_gui import (
    log_likelihood_2x2,
    parse_doc_metadata,
    polarity_candidate,
)


def test_parse_doc_metadata_with_lexis_headers():
    text = "<SOURCE>: BBC | Reuters\n<DATE>: 2024-01-02\n\n----- BODY -----\n\nChina is important."
    meta = parse_doc_metadata(text)
    assert meta["Source"] == "BBC | Reuters"
    assert meta["Date"] == "2024-01-02"
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
