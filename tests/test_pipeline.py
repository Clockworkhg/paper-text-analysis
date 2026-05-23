# -*- coding: utf-8 -*-
"""Tests for shared/pipeline_steps.py and pipeline integration."""

from pathlib import Path

from shared.exceptions import (
    InputFileNotFoundError,
    MissingPreconditionError,
    PipelineError,
)
from shared.pipeline_steps import (
    STEPS,
    check_step_done,
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
