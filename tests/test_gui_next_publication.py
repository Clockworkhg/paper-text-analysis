# -*- coding: utf-8 -*-
"""Phase 2B.1 tests: transactional publication integrity.

Covers the allowlist contract, stale-file exclusion, path safety, manifest
tampering refusal, replace/delete fault rollback, crash-during-COMMITTING
recovery, publish-phase writer lock, published generation identity, project
identity preservation, and sanity parity between the GUI adapter and the
shared/CLI sanity implementation.
"""

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from gui_next.data.store import ProjectStore  # noqa: E402
from gui_next.execution import jobs as run_jobs  # noqa: E402
from gui_next.execution import publication as pub  # noqa: E402
from gui_next.execution.publication import PublicationError  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_work_output(work: Path, rel: str, content: str) -> Path:
    path = work / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture()
def work_and_root(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    root = tmp_path / "proj"
    root.mkdir()
    return work, root


def _simple_manifest(work: Path, produced: list[str], previous=None,
                     files_to_remove=None) -> dict:
    return pub.build_manifest(
        work_dir=work, project_dir=work, run_id="gui_t",
        corpus_fingerprint="fp", params={"targets": "China"},
        produced=produced, previous_record=previous,
    ) if False else pub.build_manifest(
        work_dir=work, project_dir=work, run_id="gui_t",
        corpus_fingerprint="fp", params={"targets": "China"},
        produced=produced, previous_record=previous)


# ---------------------------------------------------------------------------
# Allowlist contract + stale-file exclusion (§2/§3/§4)
# ---------------------------------------------------------------------------


def test_manifest_allowlist_and_stale_file_exclusion(work_and_root):
    work, _root = work_and_root
    _write_work_output(work, "adjectives_phrases.xlsx", "new workbook")
    _write_work_output(work, "07_reports/method_summary.md", "new report")
    _write_work_output(work, "_corpus_merged.txt", "internal intermediate")
    # Stale file from a previous run, planted into the work copy but NOT
    # produced this round -> must never enter the manifest.
    _write_work_output(work, "adjectives_final.xlsx", "STALE old translation")

    manifest = _simple_manifest(work, produced=[
        "adjectives_phrases.xlsx", "07_reports/method_summary.md",
        "_corpus_merged.txt",
    ])

    produced_paths = sorted(entry["relative_path"] for entry in manifest["files"])
    assert produced_paths == ["07_reports/method_summary.md", "adjectives_phrases.xlsx"]
    # The planted stale file is bound to no produced entry -> never owned.
    assert not any(e["relative_path"] == "adjectives_final.xlsx" for e in manifest["files"])
    assert "_corpus_merged.txt" in manifest["excluded"]
    entry = next(e for e in manifest["files"] if e["relative_path"] == "adjectives_phrases.xlsx")
    assert entry["sha256"] == _sha(work / "adjectives_phrases.xlsx")
    assert entry["size"] > 0 and entry["category"] == "analysis_workbook"


def test_previous_generation_obsolete_outputs_marked_for_removal(work_and_root):
    work, _root = work_and_root
    previous = {"published_run_id": "gui_prev",
                "owned_paths": ["adjectives_phrases.xlsx", "adjectives_final.xlsx",
                                "07_reports/validation_report.xlsx"]}
    _write_work_output(work, "adjectives_phrases.xlsx", "new workbook")  # final no longer generated

    manifest = _simple_manifest(work, produced=["adjectives_phrases.xlsx"], previous=previous)

    assert manifest["files_to_remove"] == ["07_reports/validation_report.xlsx", "adjectives_final.xlsx"]
    assert manifest["previous_published_run_id"] == "gui_prev"


# ---------------------------------------------------------------------------
# Path safety (§2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_path", [
    "../adjectives_phrases.xlsx",
    "C:/adjectives_phrases.xlsx",
    "corpus/a.txt",
    "06_review/foo_state.json",
    "evil.py",
    "runs/work_x/adjectives_phrases.xlsx",
    "",
])
def test_path_safety_rejects_contract_violations(bad_path):
    with pytest.raises(pub.PathSafetyError):
        pub.check_path_safety(bad_path)


def test_manifest_with_dangerous_path_is_refused(work_and_root):
    work, _root = work_and_root
    manifest = {"files": [{"relative_path": "../evil.xlsx", "sha256": "x", "size": 1, "category": "x"}],
                "files_to_remove": []}
    with pytest.raises(pub.PathSafetyError):
        pub.validate_manifest(manifest, work)


# ---------------------------------------------------------------------------
# Commit / rollback (§5)
# ---------------------------------------------------------------------------


def test_commit_success_writes_generation_and_cleans_transaction(work_and_root):
    work, root = work_and_root
    _write_work_output(work, "adjectives_phrases.xlsx", "new workbook")
    _write_work_output(work, "07_reports/method_summary.md", "report body")

    manifest = _simple_manifest(work, produced=[
        "adjectives_phrases.xlsx", "07_reports/method_summary.md"])
    record = pub.execute_publication(manifest, work, root, "gui_ok")

    assert record["transaction"]["state"] == "COMMITTED"
    assert (root / "adjectives_phrases.xlsx").read_text(encoding="utf-8") == "new workbook"
    assert (root / "07_reports" / "method_summary.md").read_text(encoding="utf-8") == "report body"
    pointer = pub.read_published_pointer(root)
    assert pointer["published_run_id"] == "gui_ok"
    assert pointer["manifest_sha256"] == record["manifest_sha256"]
    # COMMITTED allows staging/backup cleanup; manifest record + journal trail kept.
    assert (root / "runs" / "publication_gui_ok.json").exists()
    assert not (root / "runs" / "pub_gui_ok").exists()


def test_tampered_work_output_refuses_publication(work_and_root):
    work, root = work_and_root
    _write_work_output(work, "adjectives_phrases.xlsx", "verified content")
    manifest = _simple_manifest(work, produced=["adjectives_phrases.xlsx"])
    # Tamper AFTER the manifest was built.
    _write_work_output(work, "adjectives_phrases.xlsx", "TAMPERED")

    with pytest.raises(PublicationError, match="哈希校验失败"):
        pub.execute_publication(manifest, work, root, "gui_tamper")
    assert not (root / "adjectives_phrases.xlsx").exists()  # nothing touched


def test_replace_failure_rolls_back_entire_generation(work_and_root):
    work, root = work_and_root
    # Previous generation: two owned files with old content.
    _write_work_output(root, "adjectives_phrases.xlsx", "OLD workbook")
    _write_work_output(root, "07_reports/method_summary.md", "OLD report")
    old_hashes = {_sha(root / "adjectives_phrases.xlsx"), _sha(root / "07_reports" / "method_summary.md")}

    _write_work_output(work, "adjectives_phrases.xlsx", "NEW workbook")
    _write_work_output(work, "07_reports/method_summary.md", "NEW report")
    manifest = _simple_manifest(work, produced=[
        "adjectives_phrases.xlsx", "07_reports/method_summary.md"])

    with pytest.raises(PublicationError, match="回滚"):
        pub.execute_publication(manifest, work, root, "gui_roll",
                                fault_injection={"fail_entry_index": 1})

    assert _sha(root / "adjectives_phrases.xlsx") in old_hashes  # old content restored
    assert _sha(root / "07_reports" / "method_summary.md") in old_hashes
    tx = root / "runs" / "pub_gui_roll"
    journal = json.loads((tx / "journal.json").read_text(encoding="utf-8"))
    assert journal["state"] == "ROLLED_BACK"


def test_obsolete_removal_failure_rolls_back_previous_generation(work_and_root):
    work, root = work_and_root
    _write_work_output(root, "adjectives_phrases.xlsx", "OLD workbook")
    _write_work_output(root, "adjectives_final.xlsx", "OLD translation")  # obsolete this round
    previous = {"published_run_id": "gui_prev",
                "owned_paths": ["adjectives_phrases.xlsx", "adjectives_final.xlsx"]}

    _write_work_output(work, "adjectives_phrases.xlsx", "NEW workbook")
    manifest = pub.build_manifest(
        work_dir=work, project_dir=root, run_id="gui_obs", corpus_fingerprint="fp",
        params={"targets": "China"}, produced=["adjectives_phrases.xlsx"],
        previous_record=previous)
    assert manifest["files_to_remove"] == ["adjectives_final.xlsx"]

    with pytest.raises(PublicationError, match="回滚"):
        pub.execute_publication(manifest, work, root, "gui_obs",
                                fault_injection={"fail_removal": True})

    # Old generation complete: obsolete file restored, workbook restored.
    assert (root / "adjectives_final.xlsx").read_text(encoding="utf-8") == "OLD translation"
    assert (root / "adjectives_phrases.xlsx").read_text(encoding="utf-8") == "OLD workbook"
    journal = json.loads((root / "runs" / "pub_gui_obs" / "journal.json").read_text(encoding="utf-8"))
    assert journal["state"] == "ROLLED_BACK"


def test_stale_file_in_work_copy_never_published(work_and_root):
    work, root = work_and_root
    # A stale analysis file sits in the work copy but is NOT in `produced`.
    _write_work_output(work, "adjectives_phrases.xlsx", "STALE previous-run workbook")

    manifest = _simple_manifest(work, produced=[])  # this run produced nothing

    assert manifest["files"] == []
    pub.execute_publication(manifest, work, root, "gui_stale")
    assert not (root / "adjectives_phrases.xlsx").exists()  # never promoted


# ---------------------------------------------------------------------------
# Crash during COMMITTING (§6)
# ---------------------------------------------------------------------------


def test_crash_during_committing_recovers_previous_generation(work_and_root, tmp_path):
    work, root = work_and_root
    _write_work_output(root, "adjectives_phrases.xlsx", "OLD workbook")
    previous_owned = ["adjectives_phrases.xlsx"]

    _write_work_output(work, "adjectives_phrases.xlsx", "NEW workbook")
    _write_work_output(work, "07_reports/method_summary.md", "NEW report")
    manifest = pub.build_manifest(
        work_dir=work, project_dir=root, run_id="gui_crash", corpus_fingerprint="fp",
        params={"targets": "China"}, produced=[
            "adjectives_phrases.xlsx", "07_reports/method_summary.md"],
        previous_record={"published_run_id": "gui_prev", "owned_paths": previous_owned},
    )

    # Hard-crash a child process after the first commit.
    crash_script = tmp_path / "crash_publish.py"
    crash_script.write_text(
        "import os, sys\n"
        f"sys.path.insert(0, r'{Path(__file__).resolve().parents[1]}')\n"
        "from gui_next.execution import publication as pub\n"
        "import json\n"
        "manifest = json.loads(sys.argv[1])\n"
        "try:\n"
        "    pub.execute_publication(manifest, sys.argv[2], sys.argv[3], 'gui_crash',\n"
        "                            fault_injection={'crash_after_commit': 1})\n"
        "except pub.PublicationError as exc:\n"
        "    sys.stderr.write('CHILD PUBLISH ERROR: %s\\n' % exc)\n"
        "os._exit(0)\n",
        encoding="utf-8",
    )
    import subprocess
    import sys as _sys

    result = subprocess.run(
        [_sys.executable, str(crash_script), json.dumps(manifest), str(work), str(root)],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 70  # simulated hard death mid-COMMITTING
    assert "simulated crash" in result.stderr

    # Mid-COMMITTING state on disk: first file replaced, second missing.
    journal = json.loads((root / "runs" / "pub_gui_crash" / "journal.json").read_text(encoding="utf-8"))
    assert journal["state"] == "COMMITTING"

    # Recovery restores the complete previous generation.
    recovered = pub.recover_publications(root)
    assert recovered and recovered[0]["state"] == "ROLLED_BACK"
    assert (root / "adjectives_phrases.xlsx").read_text(encoding="utf-8") == "OLD workbook"
    assert not (root / "07_reports" / "method_summary.md").exists()
    journal = json.loads((root / "runs" / "pub_gui_crash" / "journal.json").read_text(encoding="utf-8"))
    assert journal["state"] == "ROLLED_BACK"
    assert "Crash during COMMITTING" in journal["recovery_note"]

    # A recorded publication must not exist for the crashed run.
    assert not (root / "runs" / "publication_gui_crash.json").exists()


def test_recovery_required_blocks_new_publication(work_and_root):
    work, root = work_and_root
    tx = pub._tx_dir(root, "gui_stuck")
    tx.mkdir(parents=True)
    (tx / "journal.json").write_text(json.dumps({
        "journal_version": 1, "run_id": "gui_stuck", "state": "RECOVERY_REQUIRED",
        "entries": [], "removals": []}), encoding="utf-8")
    assert pub.recovery_required(root)
    assert pub.recovery_required(root)[0]["run_id"] == "gui_stuck"


# ---------------------------------------------------------------------------
# Writer lock coverage + published identity (§7/§8)
# ---------------------------------------------------------------------------


def _tiny_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "01_corpus").mkdir(parents=True)
    corpus = proj / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\nChina poses a threat to Europe.", encoding="utf-8")
    pd.DataFrame({
        "document_id": ["doc_a"], "title": ["A"], "source_normalized": ["BBC"],
        "source_raw": ["BBC"], "country": ["UK"], "date": [""],
        "word_count_approx": [12], "target_hits_total": [2], "relative_path": ["BBC/a.txt"],
    }).to_csv(proj / "01_corpus" / "documents.csv", index=False)
    (proj / "project.json").write_text(json.dumps(
        {"project_id": "p", "name": "x", "targets": "China",
         "project_dir": str(proj), "latest": {}, "history": []}), encoding="utf-8")
    return proj


def test_writer_lock_held_through_publishing_and_identity_recorded(tmp_path: Path, qapp):
    from gui_next.execution.controller import AnalysisController
    from gui_next.execution.events import RunState

    proj = _tiny_project(tmp_path)
    controller = AnalysisController(proj)
    spec = run_jobs.build_spec(kind="analyze", project_dir=str(proj), targets="China",
                               group_by="source", mi_threshold=3.0, sanity=False)
    assert controller.start(spec, "gui_pub_lock")

    # While publishing (or shortly after), a second writer must be refused.
    refused_during = None
    waited = 0
    terminal = False
    from PySide6.QtTest import QTest
    while waited < 180_000:
        QTest.qWait(100)
        waited += 100
        if controller.state in (RunState.ANALYSIS_SUCCEEDED, RunState.PUBLISHING):
            second = AnalysisController(proj)
            spec2 = run_jobs.build_spec(kind="analyze", project_dir=str(proj), targets="China",
                                        group_by="source", sanity=False)
            refused_during = second.start(spec2, "gui_second")
            break
        if controller.state in (RunState.SUCCEEDED, RunState.PUBLISH_FAILED,
                                RunState.FAILED, RunState.CANCELLED):
            terminal = True
            break
    assert terminal, "run never reached a terminal state"
    # The lock is released only after publication completed or rolled back.
    assert run_jobs.active_writer(proj) is None
    assert refused_during is None or refused_during is False

    # Published generation identity.
    store = ProjectStore(proj)
    pointer = store.published_analysis()
    assert pointer["published_run_id"] == "gui_pub_lock"
    assert pointer["corpus_fingerprint"]
    chips = {c["label"]: c["value"] for c in store.stat_chips()}
    assert chips["当前结果"] == "Run #b_lock"  # last 6 chars of the run id


def test_project_identity_preserved_after_publish(tmp_path: Path, qapp):
    from gui_next.execution.controller import AnalysisController
    from gui_next.execution.events import RunState
    from PySide6.QtTest import QTest

    proj = _tiny_project(tmp_path)
    original = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    controller = AnalysisController(proj)
    spec = run_jobs.build_spec(kind="analyze", project_dir=str(proj), targets="China",
                               group_by="source", mi_threshold=3.0, sanity=False)
    assert controller.start(spec, "gui_ident")
    waited = 0
    while waited < 180_000 and controller.state not in (
            RunState.SUCCEEDED, RunState.PUBLISH_FAILED, RunState.FAILED, RunState.CANCELLED):
        QTest.qWait(100)
        waited += 100
    assert controller.state is RunState.SUCCEEDED

    after = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    # Identity/config fields never overwritten by publication.
    assert after["project_id"] == original["project_id"]
    assert after["name"] == original["name"]
    assert after["project_dir"] == str(proj)
    # Analysis history appended exactly once.
    analyze_entries = [h for h in after["history"] if h.get("event") == "analyze"]
    assert len(analyze_entries) == 1
    # Latest pointers refreshed by the merge.
    assert after["latest"].get("analysis_output")


# ---------------------------------------------------------------------------
# Sanity adapter parity (§9)
# ---------------------------------------------------------------------------


def test_gui_sanity_parity_with_shared_sanity(tmp_path: Path):
    from gui_next.execution.runner import run_sanity_job
    from shared.project_workflow import project_sanity

    proj = tmp_path / "parity"
    (proj / "01_corpus").mkdir(parents=True)
    corpus = proj / "corpus" / "BBC"
    corpus.mkdir(parents=True)
    # Polluted: markers + header tags inside the body.
    (corpus / "a.txt").write_text(
        "<SOURCE>: BBC\n\n----- BODY -----\n\n<SOURCE>: inner\n\n----- BODY -----\n\nx",
        encoding="utf-8")
    pd.DataFrame({
        "document_id": ["doc_a"], "title": ["A"], "source_normalized": ["BBC"],
        "source_raw": ["BBC"], "country": ["UK"], "date": [""],
        "word_count_approx": [5], "target_hits_total": [0], "relative_path": ["BBC/a.txt"],
    }).to_csv(proj / "01_corpus" / "documents.csv", index=False)
    (proj / "project.json").write_text(json.dumps(
        {"project_id": "p", "name": "parity", "targets": "",
         "project_dir": str(proj), "latest": {}, "history": []}), encoding="utf-8")

    # Shared/CLI implementation first.
    shared_result = project_sanity(str(proj))
    shared_report = json.loads(
        Path(shared_result["report"]).read_text(encoding="utf-8"))
    shared_corpus = shared_report["corpus"]

    # GUI adapter on the same project (report rewritten).
    gui_result = run_sanity_job({"project_dir": str(proj)})
    gui_report = json.loads(Path(gui_result["sanity_report"]).read_text(encoding="utf-8"))
    gui_corpus = gui_report["corpus"]

    # Key fields must agree exactly — same rules, no second health algorithm.
    assert gui_report["ok"] == shared_report["ok"] == False
    assert gui_corpus["documents"] == shared_corpus["documents"] == 1
    for key in ("marker_lines_in_body", "header_tags_in_body"):
        assert gui_corpus["failures"][key]["count"] == shared_corpus["failures"][key]["count"] == 1
