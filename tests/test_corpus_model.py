import json
from pathlib import Path

import pandas as pd

from shared.corpus_model import build_documents_dataframe, write_corpus_model


def test_build_documents_dataframe_parses_lexis_headers(tmp_path: Path):
    corpus = tmp_path / "corpus"
    source_dir = corpus / "BBC"
    source_dir.mkdir(parents=True)
    (source_dir / "story.txt").write_text(
        "<SOURCE>: BBC | Reuters\n<DATE>: 2024-01-02\n\n----- BODY -----\n\nChina is stable. China grows.",
        encoding="utf-8",
    )

    df = build_documents_dataframe(corpus, "corpus_test", "news_lexis", ["China"])

    assert len(df) == 1
    row = df.iloc[0]
    assert row["document_id"].startswith("doc_")
    assert row["corpus_id"] == "corpus_test"
    assert row["corpus_type"] == "news_lexis"
    assert row["source_raw"] == "BBC | Reuters"
    assert row["source_normalized"] == "BBC"
    assert row["target_hits_total"] == 2
    assert json.loads(row["target_hits_json"]) == {"China": 2}


def test_write_corpus_model_outputs_manifest_and_registry(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.txt").write_text("Plain text about risk and policy.", encoding="utf-8")

    paths = write_corpus_model(
        tmp_path,
        input_path=str(tmp_path / "input.docx"),
        targets="risk; policy",
        corpus_type="policy",
        corpus_id="corpus_policy",
        run_id="run_policy",
    )

    assert Path(paths["documents_csv"]).exists()
    assert Path(paths["document_registry"]).exists()
    assert Path(paths["corpus_manifest"]).exists()
    assert Path(paths["data_model"]).exists()

    manifest = json.loads(Path(paths["corpus_manifest"]).read_text(encoding="utf-8"))
    assert manifest["corpus_id"] == "corpus_policy"
    assert manifest["run_id"] == "run_policy"
    assert manifest["corpus_type"] == "policy"
    assert manifest["documents_count"] == 1

    docs = pd.read_csv(paths["documents_csv"])
    assert list(docs["corpus_type"]) == ["policy"]
