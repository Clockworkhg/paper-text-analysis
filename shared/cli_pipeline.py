# -*- coding: utf-8 -*-
"""Shared runner for command-line pipeline entry points."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from shared.corpus_model import write_corpus_model
from shared.pipeline_steps import (
    STEPS,
    check_step_done,
    s1_docx_to_txt,
    s2_json_to_excel,
    s3_merge_and_country,
    s4_extract_adjectives,
    s5_pos_and_translate,
)
from shared.research_output import build_run_config, write_run_config
from shared.validation import generate_validation_artifacts


def parse_step_selection(skip: str = "", only: str = "") -> List[int]:
    """Return the requested pipeline step numbers in execution order."""

    skip_set = _parse_step_list(skip)
    only_set = _parse_step_list(only)
    if only_set:
        return sorted(only_set & set(STEPS.keys()))
    return sorted(step for step in STEPS if step not in skip_set)


def runnable_steps(
    requested_steps: Iterable[int],
    out_dir: Path,
    *,
    targets: str,
    force: bool,
    log: Callable[[str], None] = print,
) -> List[int]:
    """Apply target and existing-output filters to requested steps."""

    steps = list(requested_steps)
    if not targets:
        log("Warning: no target terms were provided; steps 4/5 will be skipped.")
        steps = [step for step in steps if step not in (4, 5)]

    run_steps: List[int] = []
    for step in steps:
        if not force and check_step_done(step, str(out_dir)):
            log(f"[Step {step}] {STEPS[step]} already has output; skipping. Use --force to rerun.")
            continue
        run_steps.append(step)
    return run_steps


def run_cli_pipeline(args: Any, *, log: Callable[[str], None] = print) -> int:
    """Run the legacy 1-5 pipeline from a parsed argparse namespace."""

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = getattr(args, "targets", "") or ""
    force = bool(getattr(args, "force", False))
    country = _country_enabled(args)
    setattr(args, "country", country)
    corpus_type = getattr(args, "corpus_type", "news_lexis")
    requested_steps = parse_step_selection(getattr(args, "skip", ""), getattr(args, "only", ""))
    run_steps = runnable_steps(requested_steps, out_dir, targets=targets, force=force, log=log)

    run_config = build_run_config(args, requested_steps, run_steps)
    run_config_path = write_run_config(out_dir, run_config)

    if not run_steps:
        if (out_dir / "corpus").exists():
            run_config["corpus_model"] = write_corpus_model(
                out_dir,
                input_path=args.input,
                targets=targets,
                corpus_type=corpus_type,
                corpus_id=run_config.get("corpus_id"),
                run_id=run_config.get("run_id"),
            )
        run_config["status"] = "skipped"
        run_config["reason"] = "all requested outputs already exist"
        write_run_config(out_dir, run_config)
        log("All requested steps are already complete.")
        return 0

    _print_run_header(args, out_dir, run_steps, country, run_config_path, log)

    state: Dict[str, Any] = {}
    try:
        _run_selected_steps(args, out_dir, run_steps, country, corpus_type, run_config, state, log)
    except KeyboardInterrupt:
        log("\nInterrupted by user.")
        _write_failed_config(out_dir, run_config, state)
        return 1
    except Exception as exc:
        log(f"\nError: {exc}")
        traceback.print_exc()
        _write_failed_config(out_dir, run_config, state)
        return 1

    state["validation"] = generate_validation_artifacts(out_dir)
    run_config["status"] = "completed"
    run_config["state"] = state
    write_run_config(out_dir, run_config)

    log("=" * 60)
    log(f"Pipeline completed. Output directory: {out_dir.absolute()}")
    log(f"Review/validation artifacts: {out_dir / '06_review'} ; {out_dir / '07_reports'}")
    log("=" * 60)
    return 0


def _parse_step_list(value: str) -> set[int]:
    return {int(part.strip()) for part in value.split(",") if part.strip()}


def _country_enabled(args: Any) -> bool:
    if hasattr(args, "country"):
        return bool(args.country)
    return not bool(getattr(args, "no_country", False))


def _print_run_header(
    args: Any,
    out_dir: Path,
    run_steps: List[int],
    country: bool,
    run_config_path: Path,
    log: Callable[[str], None],
) -> None:
    log("=" * 60)
    log("Full pipeline run")
    log(f"Input: {args.input}")
    log(f"Output: {out_dir.absolute()}")
    log(f"Steps: {run_steps}")
    log(f"Targets: {getattr(args, 'targets', '') or '(modifier analysis skipped)'}")
    log(f"Country inference: {'enabled' if country else 'disabled'}")
    log(f"Run config: {run_config_path}")
    log("=" * 60)
    log("")


def _run_selected_steps(
    args: Any,
    out_dir: Path,
    run_steps: List[int],
    country: bool,
    corpus_type: str,
    run_config: Dict[str, Any],
    state: Dict[str, Any],
    log: Callable[[str], None],
) -> None:
    targets = getattr(args, "targets", "") or ""

    if 1 in run_steps:
        log(f"[Step 1] {STEPS[1]}")
        state["s1"] = s1_docx_to_txt(args.input, str(out_dir), log_fn=log)
        state["corpus_model"] = write_corpus_model(
            out_dir,
            input_path=args.input,
            targets=targets,
            corpus_type=corpus_type,
            corpus_id=run_config.get("corpus_id"),
            run_id=run_config.get("run_id"),
            corpus_dir=Path(state["s1"]["corpus_dir"]),
        )
        log("")

    if 2 in run_steps:
        log(f"[Step 2] {STEPS[2]}")
        report_path = _find_report_path(out_dir, state)
        state["s2"] = s2_json_to_excel(report_path, str(out_dir), log_fn=log)
        log("")

    if 3 in run_steps:
        log(f"[Step 3] {STEPS[3]}")
        source_excel = state.get("s2", {}).get("excel_path") or str(out_dir / "source_counts.xlsx")
        state["s3"] = s3_merge_and_country(source_excel, str(out_dir), enable_country=country, log_fn=log)
        log("")

    if 4 in run_steps:
        log(f"[Step 4] {STEPS[4]}")
        corpus_dir = state.get("s1", {}).get("corpus_dir") or str(out_dir / "corpus")
        state["s4"] = s4_extract_adjectives(
            corpus_dir, str(out_dir), targets, log_fn=log,
            group_by=getattr(args, "group_by", "source"),
            sanity=not getattr(args, "skip_sanity", False),
        )
        log("")

    if 5 in run_steps:
        adj_path = Path(state.get("s4", {}).get("adj_excel_path") or out_dir / "adjectives_phrases.xlsx")
        if adj_path.exists():
            log(f"[Step 5] {STEPS[5]}")
            state["s5"] = s5_pos_and_translate(str(adj_path), str(out_dir), log_fn=log)
            log("")
        else:
            log("[Step 5] Skipped because adjectives_phrases.xlsx is missing; run step 4 first.")


def _find_report_path(out_dir: Path, state: Dict[str, Any]) -> str:
    report_path: Optional[str] = state.get("s1", {}).get("report_path")
    if report_path:
        return report_path
    report_files = sorted((out_dir / "corpus").glob("report-*.json"))
    if report_files:
        return str(report_files[-1])
    raise FileNotFoundError("Step 2 requires a step-1 report JSON. Run step 1 first.")


def _write_failed_config(out_dir: Path, run_config: Dict[str, Any], state: Dict[str, Any]) -> None:
    run_config["status"] = "failed"
    run_config["state"] = state
    write_run_config(out_dir, run_config)
