# -*- coding: utf-8 -*-
"""Tests for Step-0 corpus sanity checks and corpus fingerprinting."""

from pathlib import Path

from shared.corpus_sanity import (
    check_corpus_sanity,
    corpus_fingerprint,
)


def _write_corpus(tmp_path: Path, files: dict[str, str]):
    for rel, text in files.items():
        target = tmp_path / "corpus" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


CLEAN_LEXIS = (
    "<TITLE>: Story\n<SOURCE>: BBC\n\n----- BODY -----\n\n"
    "China faces serious pressure from abroad. The situation remains difficult."
)
CLEAN_PLAIN = "A plain policy document about risk and responsibility in modern governance."
POLLUTED = (
    "<TITLE>: outer\n<SOURCE>: outer\n\n----- BODY -----\n\n"
    "<TITLE>: inner\n<SOURCE>: inner\n\n----- BODY -----\n\n"
    "Real body text about China."
)


def test_clean_lexis_corpus_passes(tmp_path: Path):
    _write_corpus(tmp_path, {"BBC/a.txt": CLEAN_LEXIS})

    report = check_corpus_sanity(tmp_path / "corpus")

    assert report["ok"] is True
    assert report["documents"] == 1
    assert report["failures"]["marker_lines_in_body"]["count"] == 0


def test_plain_text_corpus_without_headers_passes(tmp_path: Path):
    _write_corpus(tmp_path, {"docs/policy.txt": CLEAN_PLAIN})

    report = check_corpus_sanity(tmp_path / "corpus")

    assert report["ok"] is True


def test_double_wrapped_corpus_fails(tmp_path: Path):
    _write_corpus(tmp_path, {"BBC/a.txt": POLLUTED, "VOA/b.txt": POLLUTED})

    report = check_corpus_sanity(tmp_path / "corpus")

    assert report["ok"] is False
    assert report["failures"]["marker_lines_in_body"]["count"] == 2
    assert report["failures"]["header_tags_in_body"]["count"] == 2
    assert report["failures"]["header_tags_in_body"]["examples"]


def test_warnings_for_short_duplicate_and_encoding_issues(tmp_path: Path):
    body = "Short body about China."
    _write_corpus(tmp_path, {
        "BBC/a.txt": f"<SOURCE>: BBC\n\n----- BODY -----\n\n{body}",
        "BBC/b.txt": f"<SOURCE>: BBC\n\n----- BODY -----\n\n{body}",
        "BBC/c.txt": "<SOURCE>: BBC\n\n----- BODY -----\n\n\ufffd\ufffd broken",
    })

    report = check_corpus_sanity(tmp_path / "corpus")

    assert report["ok"] is True  # warnings only
    warnings = report["warnings"]
    assert warnings["short_body"]["count"] == 3
    assert warnings["duplicate_bodies"]["groups"] == 1
    assert warnings["replacement_chars"]["total"] == 2


def test_corpus_fingerprint_is_stable_and_sensitive(tmp_path: Path):
    _write_corpus(tmp_path, {"BBC/a.txt": CLEAN_LEXIS})

    first = corpus_fingerprint(tmp_path / "corpus")
    second = corpus_fingerprint(tmp_path / "corpus")
    assert first["sha256"] == second["sha256"]
    assert first["files"] == 1

    _write_corpus(tmp_path, {"BBC/b.txt": CLEAN_PLAIN})
    changed = corpus_fingerprint(tmp_path / "corpus")
    assert changed["sha256"] != first["sha256"]
    assert changed["files"] == 2
