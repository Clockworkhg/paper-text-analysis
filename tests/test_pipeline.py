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


def test_pipeline_error_base_class():
    exc = InputFileNotFoundError("test")
    assert isinstance(exc, PipelineError)
    assert isinstance(exc, Exception)


def test_missing_precondition_is_pipeline_error():
    exc = MissingPreconditionError("no TXT files found")
    assert isinstance(exc, PipelineError)
