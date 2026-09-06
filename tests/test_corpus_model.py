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


# ---------------------------------------------------------------------------
# Country join + custom grouping template (grouping modes)
# ---------------------------------------------------------------------------

from shared.corpus_model import (  # noqa: E402
    apply_country_to_registry,
    load_group_overrides,
    match_country_for_source,
    write_group_template,
)


def _write_registry(tmp_path: Path, sources):
    model_dir = tmp_path / "01_corpus"
    model_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"source_normalized": sources}).to_csv(
        model_dir / "documents.csv", index=False, encoding="utf-8-sig"
    )


def _write_country_table(tmp_path: Path, rows):
    df = pd.DataFrame(rows, columns=["Source_Merged", "Country"])
    with pd.ExcelWriter(tmp_path / "merged_sources.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="WithCountry", index=False)


def test_match_country_exact_normalized_and_fuzzy():
    mapping = {"AFP": "France", "BBC  News": "UK", "Financial Times": "UK"}

    assert match_country_for_source("AFP", mapping) == "France"
    assert match_country_for_source("bbc news", mapping) == "UK"
    assert match_country_for_source("Financial Times (London)", mapping) == "UK"
    assert match_country_for_source("Mystery Blog", mapping) == ""
    assert match_country_for_source("AFP", {}) == ""


def test_apply_country_to_registry_joins_and_writes_source_table(tmp_path: Path):
    _write_registry(tmp_path, ["AFP", "bbc news", "Mystery Blog"])
    _write_country_table(tmp_path, [("AFP", "France"), ("BBC News", "UK")])

    result = apply_country_to_registry(tmp_path)

    assert result["updated"] is True
    assert result["documents"] == 3
    assert result["matched"] == 2
    assert result["unknown"] == 1

    docs = pd.read_csv(tmp_path / "01_corpus" / "documents.csv")
    assert list(docs["country"]) == ["France", "UK", "Unknown"]

    per_source = pd.read_csv(tmp_path / "03_country" / "source_countries.csv")
    assert set(per_source.columns) == {"Source_Normalized", "Country"}


def test_apply_country_to_registry_handles_missing_inputs(tmp_path: Path):
    assert apply_country_to_registry(tmp_path) == {"updated": False, "reason": "registry_missing"}

    _write_registry(tmp_path, ["AFP"])
    assert apply_country_to_registry(tmp_path) == {"updated": False, "reason": "country_table_missing"}


def test_write_group_template_and_load_overrides(tmp_path: Path):
    _write_registry(tmp_path, ["AFP", "AFP", "BBC News"])

    result = write_group_template(tmp_path)
    template_path = Path(result["group_template"])

    assert template_path.exists()
    assert result["sources"] == 2

    # Empty group column -> no usable overrides yet.
    assert load_group_overrides(tmp_path) == {}

    # Fill the group column as a researcher would.
    df = pd.read_excel(template_path)
    df["group"] = df["group"].fillna("").astype(str)
    df.loc[df["source"] == "AFP", "group"] = "Western wire"
    df.loc[df["source"] == "BBC News", "group"] = "UK public"
    df.to_excel(template_path, index=False)

    overrides = load_group_overrides(tmp_path)
    assert overrides == {"AFP": "Western wire", "BBC News": "UK public"}
