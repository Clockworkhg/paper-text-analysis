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


# ---------------------------------------------------------------------------
# Grouping modes: group_by plumbing, persistence, and status fallback
# ---------------------------------------------------------------------------

import json
import sys
import types

from shared.project_workflow import project_analyze, project_groups


def _fake_s4(monkeypatch, kwic_rows=2):
    from shared.research_output import write_excel_with_readme

    calls = {}

    def fake_s4(corpus_dir, out_dir, targets, log_fn=None, mi_threshold=3.0, group_by="source", sanity=True):
        calls["group_by"] = group_by
        calls["out_dir"] = out_dir
        write_excel_with_readme(
            str(Path(out_dir) / "adjectives_phrases.xlsx"),
            {
                "KWIC": pd.DataFrame({"Target": ["risk"] * kwic_rows, "Full_Context": ["risk"] * kwic_rows}),
                "Adjectives": pd.DataFrame({"Target": ["risk"], "Adjective": ["policy"], "Frequency": [1]}),
                "Phrases": pd.DataFrame(),
                "Collocates": pd.DataFrame(),
                "SemanticProsodyCandidates": pd.DataFrame(),
                "GroupComparison": pd.DataFrame({"Source_Group": ["Org"], "Group_By": [group_by]}),
            },
            title="Analysis",
            description="Analysis",
        )
        return {"adj_excel_path": str(Path(out_dir) / "adjectives_phrases.xlsx"), "group_by": group_by}

    monkeypatch.setattr("shared.project_workflow.s4_extract_adjectives", fake_s4)
    return calls


def test_project_analyze_records_group_by_and_persists_it(tmp_path: Path, monkeypatch):
    raw = tmp_path / "raw" / "Org"
    raw.mkdir(parents=True)
    (raw / "doc.txt").write_text("Risk and responsibility in policy.", encoding="utf-8")
    init_project(tmp_path / "proj", corpus_type="policy", targets="risk")
    project_import(tmp_path / "proj", input_path=tmp_path / "raw")

    calls = _fake_s4(monkeypatch)
    outputs = project_analyze(tmp_path / "proj", group_by="institution")

    assert calls["group_by"] == "institution"
    assert outputs["group_by"] == "institution"

    project = load_project(tmp_path / "proj")
    assert project["group_by"] == "institution"
    assert project["latest"]["group_by"] == "institution"
    assert project["latest"]["target_hits_total"] == 2
    assert project["history"][-1]["group_by"] == "institution"

    run_config = json.loads(
        (tmp_path / "proj" / "00_run_config" / "run_config.json").read_text(encoding="utf-8")
    )
    assert run_config["group_by"] == "institution"

    status = project_status(tmp_path / "proj")
    assert status["group_by"] == "institution"


def test_project_status_falls_back_to_kwic_rows_when_registry_hits_are_zero(tmp_path: Path):
    raw = tmp_path / "raw" / "Org"
    raw.mkdir(parents=True)
    (raw / "doc.txt").write_text("Risk and responsibility in policy.", encoding="utf-8")
    init_project(tmp_path / "proj", corpus_type="policy", targets="")
    project_import(tmp_path / "proj", input_path=tmp_path / "raw")

    docs = pd.read_csv(tmp_path / "proj" / "01_corpus" / "documents.csv")
    assert docs["target_hits_total"].sum() == 0

    from shared.research_output import write_excel_with_readme

    write_excel_with_readme(
        str(tmp_path / "proj" / "adjectives_phrases.xlsx"),
        {"KWIC": pd.DataFrame({"Target": ["risk"] * 7, "Full_Context": ["x"] * 7})},
        title="Analysis",
        description="Analysis",
    )

    status = project_status(tmp_path / "proj")
    assert status["target_hits_total"] == 7


def test_project_groups_generates_custom_template(tmp_path: Path):
    raw = tmp_path / "raw" / "Org"
    raw.mkdir(parents=True)
    (raw / "doc.txt").write_text("Risk and responsibility in policy.", encoding="utf-8")
    init_project(tmp_path / "proj", corpus_type="policy", targets="risk")
    project_import(tmp_path / "proj", input_path=tmp_path / "raw")

    result = project_groups(tmp_path / "proj")

    template = Path(result["group_template"])
    assert template.exists()
    df = pd.read_excel(template)
    assert list(df.columns) == ["source", "group", "country", "documents"]
    assert list(df["source"]) == ["Org"]

    project = load_project(tmp_path / "proj")
    assert project["history"][-1]["event"] == "groups"
    assert project["latest"]["group_overrides"] == str(template)


def test_project_analyze_invalid_group_by_falls_back_to_source(tmp_path: Path, monkeypatch):
    raw = tmp_path / "raw" / "Org"
    raw.mkdir(parents=True)
    (raw / "doc.txt").write_text("Risk and responsibility in policy.", encoding="utf-8")
    init_project(tmp_path / "proj", corpus_type="policy", targets="risk")
    project_import(tmp_path / "proj", input_path=tmp_path / "raw")

    calls = _fake_s4(monkeypatch)
    project_analyze(tmp_path / "proj", group_by="nonsense")

    assert calls["group_by"] == "source"


# ---------------------------------------------------------------------------
# Step 0 sanity command + immutable frozen research runs
# ---------------------------------------------------------------------------

from shared.project_workflow import project_freeze, project_sanity

POLLUTED_BODY = "<SOURCE>: inner\n\n----- BODY -----\n\nPolluted text about risk."


def test_project_sanity_reports_pollution_and_writes_report(tmp_path: Path):
    raw = tmp_path / "raw" / "Org"
    raw.mkdir(parents=True)
    (raw / "doc.txt").write_text(
        f"<SOURCE>: outer\n\n----- BODY -----\n\n{POLLUTED_BODY}", encoding="utf-8"
    )
    init_project(tmp_path / "proj", corpus_type="policy", targets="risk")
    project_import(tmp_path / "proj", input_path=tmp_path / "raw")

    result = project_sanity(tmp_path / "proj")

    assert result["ok"] is False
    assert result["corpus"]["failures"]["header_tags_in_body"]["count"] == 1
    report_path = Path(result["report"])
    assert report_path.exists()


def test_project_freeze_creates_immutable_manifest(tmp_path: Path, monkeypatch):
    raw = tmp_path / "raw" / "Org"
    raw.mkdir(parents=True)
    (raw / "doc.txt").write_text("Risk and responsibility in policy.", encoding="utf-8")
    init_project(tmp_path / "proj", corpus_type="policy", targets="risk")
    project_import(tmp_path / "proj", input_path=tmp_path / "raw")
    _fake_s4(monkeypatch, kwic_rows=3)
    project_analyze(tmp_path / "proj", group_by="institution")

    import json as json_mod

    run_config = json_mod.loads(
        (tmp_path / "proj" / "00_run_config" / "run_config.json").read_text(encoding="utf-8")
    )

    result = project_freeze(tmp_path / "proj", label="final-institution")

    runs_dir = Path(result["frozen_run"])
    assert runs_dir.name == run_config["run_id"]
    assert (runs_dir / "adjectives_phrases.xlsx").exists()
    assert (runs_dir / "06_review").exists()

    manifest = json_mod.loads((runs_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["label"] == "final-institution"
    assert manifest["parameters"]["group_by"] == "institution"
    assert manifest["corpus_fingerprint"]["files"] >= 1
    assert manifest["nlp_environment"]["spacy"]
    assert manifest["git_commit"]
    file_entry = next(f for f in manifest["files"] if f["path"] == "adjectives_phrases.xlsx")
    assert len(file_entry["sha256"]) == 64

    project = load_project(tmp_path / "proj")
    assert project["frozen_runs"][-1]["run_id"] == run_config["run_id"]

    # Immutability: freezing the same run again is refused.
    import pytest
    with pytest.raises(ValueError):
        project_freeze(tmp_path / "proj")


def test_project_freeze_requires_analysis(tmp_path: Path):
    init_project(tmp_path / "proj", corpus_type="policy", targets="risk")
    import pytest
    with pytest.raises(FileNotFoundError):
        project_freeze(tmp_path / "proj")


def test_project_analyze_records_manifest_enrichment(tmp_path: Path, monkeypatch):
    raw = tmp_path / "raw" / "Org"
    raw.mkdir(parents=True)
    (raw / "doc.txt").write_text("Risk and responsibility in policy.", encoding="utf-8")
    init_project(tmp_path / "proj", corpus_type="policy", targets="risk")
    project_import(tmp_path / "proj", input_path=tmp_path / "raw")

    _fake_s4(monkeypatch)
    project_analyze(tmp_path / "proj")

    import json as json_mod
    run_config = json_mod.loads(
        (tmp_path / "proj" / "00_run_config" / "run_config.json").read_text(encoding="utf-8")
    )
    assert run_config["corpus_fingerprint"]["files"] == 1
    assert run_config["nlp_environment"]["spacy"]
    assert run_config["algorithm_version"]
    assert run_config["hand_rules_version"]
