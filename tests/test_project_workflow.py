from pathlib import Path

import pandas as pd

from shared.project_workflow import (
    init_project,
    load_project,
    project_import,
    project_review,
    project_report,
    project_status,
)


def test_project_init_writes_project_json(tmp_path: Path):
    project = init_project(tmp_path / "proj", corpus_type="policy", targets="risk; responsibility")

    assert project["project_id"].startswith("project_")
    assert project["corpus_type"] == "policy"
    assert project["targets"] == "risk; responsibility"
    loaded = load_project(tmp_path / "proj")
    assert loaded["template"]["template_id"] == "policy"


def test_project_import_updates_status(tmp_path: Path):
    raw = tmp_path / "raw" / "Org"
    raw.mkdir(parents=True)
    (raw / "doc.txt").write_text("Risk and responsibility in policy.", encoding="utf-8")

    init_project(tmp_path / "proj", corpus_type="policy", targets="risk")
    paths = project_import(tmp_path / "proj", input_path=tmp_path / "raw")

    assert Path(paths["documents_csv"]).exists()
    project = load_project(tmp_path / "proj")
    assert project["latest"]["documents_csv"] == paths["documents_csv"]

    status = project_status(tmp_path / "proj")
    assert status["documents"] == 1
    assert status["target_hits_total"] == 1
    assert status["next_step"] == "analyze"


def test_project_review_generates_templates_after_import(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "doc.txt").write_text("Academic contribution and method.", encoding="utf-8")

    init_project(tmp_path / "proj", corpus_type="academic", targets="method")
    project_import(tmp_path / "proj", input_path=raw)

    analysis = tmp_path / "proj" / "adjectives_phrases.xlsx"
    from shared.research_output import write_excel_with_readme

    write_excel_with_readme(
        str(analysis),
        {
            "Adjectives": pd.DataFrame({"Target": ["method"], "Adjective": ["novel"], "Frequency": [1]}),
            "Phrases": pd.DataFrame({"Target": ["method"], "Modifier_Phrase": ["novel method"], "Frequency": [1]}),
            "SemanticProsodyCandidates": pd.DataFrame(
                {"Target": ["method"], "Expression": ["novel"], "Polarity_Candidate": ["positive_candidate"], "Frequency": [1]}
            ),
            "KWIC": pd.DataFrame({"Target": ["method"], "Full_Context": ["novel method"]}),
        },
        title="Analysis",
        description="Analysis",
    )

    paths = project_review(tmp_path / "proj", sample_size=10)
    assert Path(paths["modifier_semantic_review"]).exists()
    review = pd.read_excel(paths["modifier_semantic_review"], sheet_name="SemanticProsodyReview")
    assert "research_move" in review.columns


def test_project_report_summarizes_project(tmp_path: Path):
    raw = tmp_path / "raw" / "Org"
    raw.mkdir(parents=True)
    (raw / "doc.txt").write_text("Risk and responsibility in policy.", encoding="utf-8")

    init_project(tmp_path / "proj", corpus_type="policy", targets="risk")
    project_import(tmp_path / "proj", input_path=tmp_path / "raw")

    from shared.research_output import write_excel_with_readme

    write_excel_with_readme(
        str(tmp_path / "proj" / "adjectives_phrases.xlsx"),
        {
            "KWIC": pd.DataFrame({"Target": ["risk"], "Full_Context": ["risk in policy"]}),
            "Adjectives": pd.DataFrame({"Target": ["risk"], "Adjective": ["policy"], "Frequency": [1]}),
            "Phrases": pd.DataFrame(),
            "Collocates": pd.DataFrame(),
            "SemanticProsodyCandidates": pd.DataFrame(),
            "GroupComparison": pd.DataFrame(),
        },
        title="Analysis",
        description="Analysis",
    )
    project_review(tmp_path / "proj", sample_size=10)
    result = project_report(tmp_path / "proj")

    report = Path(result["research_report"])
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Research Project Report" in text
    assert "Policy text analysis" in text
    assert "Documents: 1" in text
    assert "KWIC" in text
