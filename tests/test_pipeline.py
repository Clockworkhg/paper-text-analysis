# -*- coding: utf-8 -*-
"""Tests for shared/pipeline_steps.py and pipeline integration."""

from pathlib import Path
import sys
import types

import pandas as pd

from shared.exceptions import (
    InputFileNotFoundError,
    MissingPreconditionError,
    PipelineError,
)
from shared.pipeline_steps import (
    STEPS,
    check_step_done,
    normalize_group_by,
    s4_extract_adjectives,
)
from shared.cli_pipeline import parse_step_selection, runnable_steps


def test_steps_dict_contains_all_five():
    assert len(STEPS) == 5
    assert all(isinstance(k, int) and isinstance(v, str) for k, v in STEPS.items())
    assert set(STEPS.keys()) == {1, 2, 3, 4, 5}


def test_check_step_done_returns_false_for_empty_dir():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        for s in (1, 2, 3, 4, 5):
            assert check_step_done(s, td) is False


def test_check_step_done_detects_existing_output():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        Path(td, "source_counts.xlsx").touch()
        assert check_step_done(2, td) is True
        assert check_step_done(1, td) is False


def test_check_step_done_invalid_step():
    assert check_step_done(99, ".") is False


def test_parse_step_selection_supports_skip_and_only():
    assert parse_step_selection(skip="2,4") == [1, 3, 5]
    assert parse_step_selection(only="2,4,99") == [2, 4]


def test_runnable_steps_skips_target_dependent_steps_without_targets(tmp_path: Path):
    messages = []

    steps = runnable_steps([1, 4, 5], tmp_path, targets="", force=True, log=messages.append)

    assert steps == [1]
    assert any("no target terms" in message for message in messages)


def test_runnable_steps_skips_existing_outputs_unless_forced(tmp_path: Path):
    (tmp_path / "source_counts.xlsx").touch()

    assert runnable_steps([2], tmp_path, targets="China", force=False, log=lambda _: None) == []
    assert runnable_steps([2], tmp_path, targets="China", force=True, log=lambda _: None) == [2]


def test_pipeline_error_base_class():
    exc = InputFileNotFoundError("test")
    assert isinstance(exc, PipelineError)
    assert isinstance(exc, Exception)


def test_missing_precondition_is_pipeline_error():
    exc = MissingPreconditionError("no TXT files found")
    assert isinstance(exc, PipelineError)


def test_s4_injects_stable_ids_from_document_registry(tmp_path: Path, monkeypatch):
    corpus = tmp_path / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "story.txt").write_text(
        "<TITLE>: Story\n<SOURCE>: BBC\n<DATE>: 2024-01-02\n\n----- BODY -----\n\nChina is stable.",
        encoding="utf-8",
    )
    model_dir = tmp_path / "01_corpus"
    model_dir.mkdir()
    pd.DataFrame(
        {
            "relative_path": ["BBC/story.txt"],
            "document_id": ["doc_123"],
            "corpus_id": ["corpus_abc"],
            "run_id": ["run_xyz"],
        }
    ).to_csv(model_dir / "documents.csv", index=False, encoding="utf-8-sig")

    captured = {}

    def fake_process_txt(input_path, output_path, targets, cfg, log_cb=None, group_map=None):
        captured["merged"] = Path(input_path).read_text(encoding="utf-8")
        pd.DataFrame({"ok": [1]}).to_excel(output_path, index=False)

    fake_module = types.SimpleNamespace(
        process_txt=fake_process_txt,
        split_targets=lambda text: [part.strip() for part in text.split(";") if part.strip()],
    )
    monkeypatch.setitem(sys.modules, "modules.txt_modifier_extractor_gui", fake_module)

    s4_extract_adjectives(str(tmp_path / "corpus"), str(tmp_path), "China")

    assert "<DOCUMENT_ID>: doc_123" in captured["merged"]
    assert "<CORPUS_ID>: corpus_abc" in captured["merged"]
    assert "<RUN_ID>: run_xyz" in captured["merged"]


def _make_s4_project(tmp_path: Path, registry_extra: dict):
    corpus = tmp_path / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "story.txt").write_text(
        "<TITLE>: Story\n<SOURCE>: BBC\n\n----- BODY -----\n\nChina is stable.",
        encoding="utf-8",
    )
    model_dir = tmp_path / "01_corpus"
    model_dir.mkdir()
    row = {
        "relative_path": ["BBC/story.txt"],
        "document_id": ["doc_123"],
        "source_normalized": ["BBC"],
    }
    row.update(registry_extra)
    pd.DataFrame(row).to_csv(model_dir / "documents.csv", index=False, encoding="utf-8-sig")


def test_s4_injects_source_norm_and_records_institution_mode(tmp_path: Path, monkeypatch):
    _make_s4_project(tmp_path, {})
    captured = {}

    def fake_process_txt(input_path, output_path, targets, cfg, log_cb=None, group_map=None):
        captured["merged"] = Path(input_path).read_text(encoding="utf-8")
        captured["group_by"] = cfg.group_by
        captured["group_map"] = group_map
        pd.DataFrame({"ok": [1]}).to_excel(output_path, index=False)

    monkeypatch.setitem(sys.modules, "modules.txt_modifier_extractor_gui", types.SimpleNamespace(
        process_txt=fake_process_txt,
        split_targets=lambda text: [part.strip() for part in text.split(";") if part.strip()],
    ))

    result = s4_extract_adjectives(str(tmp_path / "corpus"), str(tmp_path), "China", group_by="institution")

    assert "<SOURCE_NORM>: BBC" in captured["merged"]
    assert captured["group_by"] == "institution"
    assert captured["group_map"] is None
    assert result["group_by"] == "institution"


def test_s4_country_mode_builds_group_map_from_registry(tmp_path: Path, monkeypatch):
    _make_s4_project(tmp_path, {"country": ["United Kingdom"]})
    captured = {}

    def fake_process_txt(input_path, output_path, targets, cfg, log_cb=None, group_map=None):
        captured["group_by"] = cfg.group_by
        captured["group_map"] = group_map
        pd.DataFrame({"ok": [1]}).to_excel(output_path, index=False)

    monkeypatch.setitem(sys.modules, "modules.txt_modifier_extractor_gui", types.SimpleNamespace(
        process_txt=fake_process_txt,
        split_targets=lambda text: [part.strip() for part in text.split(";") if part.strip()],
    ))

    s4_extract_adjectives(str(tmp_path / "corpus"), str(tmp_path), "China", group_by="country")

    assert captured["group_map"] == {"BBC": "United Kingdom", "doc_123": "United Kingdom"}


def test_s4_custom_mode_without_overrides_falls_back_to_institution(tmp_path: Path, monkeypatch):
    _make_s4_project(tmp_path, {})
    captured = {}

    def fake_process_txt(input_path, output_path, targets, cfg, log_cb=None, group_map=None):
        captured["group_by"] = cfg.group_by
        captured["group_map"] = group_map
        pd.DataFrame({"ok": [1]}).to_excel(output_path, index=False)

    monkeypatch.setitem(sys.modules, "modules.txt_modifier_extractor_gui", types.SimpleNamespace(
        process_txt=fake_process_txt,
        split_targets=lambda text: [part.strip() for part in text.split(";") if part.strip()],
    ))

    s4_extract_adjectives(str(tmp_path / "corpus"), str(tmp_path), "China", group_by="custom")

    assert captured["group_by"] == "custom"
    assert captured["group_map"] is None


def test_normalize_group_by_rejects_unknown_modes():
    assert normalize_group_by("institution") == "institution"
    assert normalize_group_by("COUNTRY") == "country"
    assert normalize_group_by("") == "source"
    assert normalize_group_by("nonsense") == "source"


def test_cli_group_by_defaults_and_choices():
    from research_tool import build_parser

    parser = build_parser()
    args = parser.parse_args(["analyze", "-o", "out", "-t", "China"])
    assert args.group_by == "source"

    args = parser.parse_args(["project", "analyze", "-p", "proj", "--group-by", "country"])
    assert args.group_by == "country"

    args = parser.parse_args(["run", "-i", "in.docx", "-o", "out", "--group-by", "institution"])
    assert args.group_by == "institution"
