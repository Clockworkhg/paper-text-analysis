# -*- coding: utf-8 -*-
"""Analysis runner subprocess: ``python -m gui_next.execution.runner spec.json``.

Executes one job spec against the frozen shared/ Python API inside an
isolated work copy, emitting JSON-line lifecycle events on stdout:

    {"event": "stage", "stage": "RUNNING", "message": ...}
    {"event": "log", "line": ...}          (also captures library prints)
    {"event": "error", "type": ..., "message": ..., "traceback_tail": ...}
    {"event": "result", "outputs": {...}}

The runner never writes outside the work copy it was given; publishing to
the real project is the parent controller's job (only on success).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gui_next.execution import jobs
from gui_next.execution.events import encode, error_event, log_event, result_event, stage_event  # noqa: E402


def emit(event: dict) -> None:
    sys.stdout.write(encode(event) + "\n")
    sys.stdout.flush()


def run_sanity_job(spec: dict) -> dict:
    """Sanity check against the *given* directory (never project.json's
    stored path — a work copy or relocation must not redirect the check).
    Composed from the same shared check functions the CLI uses; writes only
    the sanity report file. Kept as a module function for parity tests.
    """
    from shared.corpus_sanity import check_corpus_sanity, check_registry_sanity
    from shared.research_output import write_json

    project_dir = Path(spec["project_dir"])
    emit(stage_event("RUNNING", "sanity check"))
    corpus_report = check_corpus_sanity(project_dir / "corpus")
    registry_report = check_registry_sanity(project_dir)
    result = {
        "ok": bool(corpus_report["ok"] and registry_report["ok"]),
        "corpus": corpus_report,
        "registry": registry_report,
    }
    report_path = project_dir / "07_reports" / "corpus_sanity_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_path, result)
    return {"sanity_report": str(report_path), "ok": result["ok"]}


def run_job(spec: dict) -> dict:
    kind = spec.get("kind", "analyze")
    if kind == "sanity":
        return run_sanity_job(spec)

    if kind == "analyze":
        if spec.get("test_sleep_before_analyze"):
            emit(log_event(f"[test hook] sleeping {spec['test_sleep_before_analyze']}s before analysis"))
            time.sleep(float(spec["test_sleep_before_analyze"]))
        if spec.get("inject_failure"):
            raise RuntimeError("Injected failure (execution-layer test hook)")

        from shared.project_workflow import project_analyze

        work_dir = Path(spec["project_dir"])
        before = jobs.snapshot_files(work_dir)
        emit(stage_event("RUNNING", "corpus model + modifier analysis"))
        outputs = project_analyze(
            spec["project_dir"],
            targets=spec.get("targets") or None,
            group_by=spec.get("group_by", "source"),
            mi_threshold=float(spec.get("mi_threshold", 3.0)),
            pos_translate=bool(spec.get("pos_translate", False)),
            sanity=bool(spec.get("sanity", True)),
            force=True,
        )
        produced = sorted(jobs.snapshot_files(work_dir) - before)
        outputs = dict(outputs)
        outputs["produced"] = produced
        return {"analysis_output": outputs.get("analysis_output", ""), "produced": produced}

    raise ValueError(f"Unknown job kind: {kind}")


def main(argv: list[str]) -> int:
    spec_path = Path(argv[0])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    emit(stage_event("PREPARING", spec.get("kind", "analyze")))
    try:
        outputs = run_job(spec)
        emit(result_event(outputs))
        return 0
    except BaseException as exc:  # noqa: BLE001 - reported to the parent, then exit
        emit(error_event(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
