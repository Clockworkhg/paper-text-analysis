from pathlib import Path

import pandas as pd

from shared.corpus_importers import import_file_corpus, import_table_corpus


def test_import_file_corpus_writes_workbench_layout(tmp_path: Path):
    source = tmp_path / "input" / "PolicyOrg"
    source.mkdir(parents=True)
    (source / "brief.txt").write_text("Climate policy creates transition risk.", encoding="utf-8")

    out = tmp_path / "out"
    paths = import_file_corpus(
        tmp_path / "input",
        out,
        corpus_type="policy",
        targets="risk",
    )

    assert Path(paths["documents_csv"]).exists()
    assert Path(paths["source_counts"]).exists()
    imported_txt = out / "corpus" / "PolicyOrg" / "brief.txt"
    assert imported_txt.exists()
    text = imported_txt.read_text(encoding="utf-8")
    assert "<TITLE>: brief" in text
    assert "<SOURCE>: PolicyOrg" in text
    assert "----- BODY -----" in text

    docs = pd.read_csv(paths["documents_csv"])
    assert docs.loc[0, "corpus_type"] == "policy"
    assert docs.loc[0, "target_hits_total"] == 1


def test_import_table_corpus_uses_column_mapping(tmp_path: Path):
    table = tmp_path / "rows.csv"
    pd.DataFrame(
        {
            "body": ["AI governance is contested.", "AI policy is evolving."],
            "headline": ["one", "two"],
            "org": ["Lab", "Agency"],
            "year": [2024, 2025],
        }
    ).to_csv(table, index=False, encoding="utf-8-sig")

    out = tmp_path / "out"
    paths = import_table_corpus(
        table,
        out,
        text_col="body",
        title_col="headline",
        source_col="org",
        date_col="year",
        corpus_type="academic",
        targets="AI",
    )

    docs = pd.read_csv(paths["documents_csv"])
    assert len(docs) == 2
    assert set(docs["source_normalized"]) == {"Lab", "Agency"}
    assert docs["target_hits_total"].sum() == 2
    assert (out / "corpus" / "Lab" / "one.txt").exists()
