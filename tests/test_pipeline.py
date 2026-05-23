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

    def fake_process_txt(input_path, output_path, targets, cfg, log_cb=None):
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
