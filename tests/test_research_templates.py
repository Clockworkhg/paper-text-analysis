import json
from pathlib import Path

import pandas as pd

from shared.corpus_model import write_corpus_model
from shared.research_templates import get_template, list_templates, normalize_template_name
from shared.research_output import write_excel_with_readme
from shared.validation import generate_validation_artifacts


def test_template_aliases_and_listing():
    assert normalize_template_name("news") == "news_lexis"
    assert normalize_template_name("paper") == "academic"
    assert normalize_template_name("unknown-kind") == "generic"
    ids = {item["template_id"] for item in list_templates()}
    assert {"news_lexis", "policy", "academic", "interview", "social_media", "translation"} <= ids


def test_corpus_model_writes_research_template(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.txt").write_text("Policy risk and responsibility.", encoding="utf-8")

    paths = write_corpus_model(
        tmp_path,
        input_path=str(tmp_path / "input"),
        targets="risk",
        corpus_type="policy",
        corpus_id="corpus_policy",
        run_id="run_policy",
    )

    template = json.loads(Path(paths["research_template"]).read_text(encoding="utf-8"))
    manifest = json.loads(Path(paths["corpus_manifest"]).read_text(encoding="utf-8"))
    assert template["template_id"] == "policy"
    assert manifest["research_template"]["template_id"] == "policy"


def test_validation_review_uses_template_columns(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.txt").write_text("Policy risk and responsibility.", encoding="utf-8")
    write_corpus_model(
        tmp_path,
        input_path=str(tmp_path / "input"),
        targets="risk",
        corpus_type="academic",
        corpus_id="corpus_academic",
        run_id="run_academic",
    )
    write_excel_with_readme(
        str(tmp_path / "adjectives_phrases.xlsx"),
        {
            "Adjectives": pd.DataFrame({"Target": ["AI"], "Adjective": ["novel"], "Frequency": [1]}),
            "Phrases": pd.DataFrame({"Target": ["AI"], "Modifier_Phrase": ["novel method"], "Frequency": [1]}),
            "SemanticProsodyCandidates": pd.DataFrame(
                {"Target": ["AI"], "Expression": ["novel"], "Polarity_Candidate": ["positive_candidate"], "Frequency": [1]}
            ),
            "KWIC": pd.DataFrame({"Target": ["AI"], "Full_Context": ["AI uses a novel method."]}),
        },
        title="Analysis",
        description="Analysis",
    )

    paths = generate_validation_artifacts(tmp_path, sample_size=10)
    review = pd.read_excel(paths["modifier_semantic_review"], sheet_name="SemanticProsodyReview")
    assert "research_move" in review.columns
    assert "stance_marker" in review.columns

    instructions = pd.read_excel(paths["modifier_semantic_review"], sheet_name="Instructions")
    assert "research_move" in set(instructions["Field"])
