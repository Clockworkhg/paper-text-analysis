"""Project-level workflow orchestration for the corpus workbench."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from shared.corpus_importers import import_file_corpus, import_table_corpus
from shared.corpus_model import stable_id, write_corpus_model
from shared.pipeline_steps import s4_extract_adjectives, s5_pos_and_translate
from shared.research_output import build_run_config, now_iso, write_json, write_run_config
from shared.research_templates import get_template, normalize_template_name
from shared.validation import generate_validation_artifacts


PROJECT_FILE = "project.json"


def _safe_console_print(message: str) -> None:
    """Print progress text even when the Windows console uses a narrow encoding."""
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe)


def project_path(path: str | Path) -> Path:
    return Path(path).resolve()


def project_file(project_dir: str | Path) -> Path:
    return project_path(project_dir) / PROJECT_FILE


def load_project(project_dir: str | Path) -> Dict[str, Any]:
    path = project_file(project_dir)
    if not path.exists():
        raise FileNotFoundError(f"Project not initialized: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_project(project_dir: str | Path, data: Dict[str, Any]) -> Path:
    path = project_file(project_dir)
    data["updated_at"] = now_iso()
    write_json(path, data)
    return path


def init_project(
    project_dir: str | Path,
    *,
    corpus_type: str = "generic",
    name: str = "",
    targets: str = "",
) -> Dict[str, Any]:
    root = project_path(project_dir)
    root.mkdir(parents=True, exist_ok=True)
    corpus_type = normalize_template_name(corpus_type)
    template = get_template(corpus_type)
    data = {
        "project_id": stable_id("project", [str(root), corpus_type]),
        "name": name or root.name,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "project_dir": str(root),
        "corpus_type": corpus_type,
        "targets": targets,
        "template": {
            "template_id": template["template_id"],
            "label": template["label"],
            "description": template["description"],
        },
        "history": [],
        "latest": {},
    }
    save_project(root, data)
    return data


def ensure_project(project_dir: str | Path, corpus_type: str = "generic", targets: str = "") -> Dict[str, Any]:
    path = project_file(project_dir)
    if path.exists():
        return load_project(project_dir)
    return init_project(project_dir, corpus_type=corpus_type, targets=targets)


def update_latest_from_paths(project: Dict[str, Any], paths: Dict[str, str]) -> None:
    for key in ("corpus_id", "run_id", "documents_csv", "corpus_manifest", "research_template"):
        if key in paths:
            project["latest"][key] = paths[key]


def _kwic_hit_total(root: Path) -> int:
    """Count KWIC rows in the analysis workbook; 0 when it is absent/unreadable.

    The document registry is rebuilt on import and can legitimately report
    zero target hits after the targets change, so the analysis workbook is
    the authoritative source for hit totals once an analysis exists.
    """
    path = root / "adjectives_phrases.xlsx"
    if not path.exists():
        return 0
    try:
        df = pd.read_excel(path, sheet_name="KWIC", usecols=["Target"])
        return int(len(df))
    except Exception:
        return 0


def project_import(
    project_dir: str | Path,
    *,
    input_path: str | Path,
    corpus_type: Optional[str] = None,
    targets: Optional[str] = None,
    default_source: str = "",
    text_col: str = "text",
    title_col: str = "",
    source_col: str = "",
    date_col: str = "",
    group_col: str = "",
) -> Dict[str, str]:
    project = ensure_project(project_dir, corpus_type=corpus_type or "generic", targets=targets or "")
    root = Path(project["project_dir"])
    corpus_type = normalize_template_name(corpus_type or project.get("corpus_type", "generic"))
    targets = project.get("targets", "") if targets is None else targets
    input_path = Path(input_path)

    if input_path.is_dir():
        paths = import_file_corpus(
            input_path,
            root,
            corpus_type=corpus_type,
            targets=targets,
            default_source=default_source,
        )
    else:
        paths = import_table_corpus(
            input_path,
            root,
            text_col=text_col,
            corpus_type=corpus_type,
            targets=targets,
            title_col=title_col,
            source_col=source_col,
            date_col=date_col,
            group_col=group_col,
        )

    project["corpus_type"] = corpus_type
    project["targets"] = targets
    project["template"] = {
        "template_id": get_template(corpus_type)["template_id"],
        "label": get_template(corpus_type)["label"],
        "description": get_template(corpus_type)["description"],
    }
    update_latest_from_paths(project, paths)
    project["latest"]["input_path"] = str(input_path.resolve())
    project["history"].append({"event": "import", "at": now_iso(), "input": str(input_path.resolve()), "paths": paths})
    save_project(root, project)
    return paths


def project_analyze(
    project_dir: str | Path,
    *,
    targets: Optional[str] = None,
    corpus_type: Optional[str] = None,
    corpus_dir: str | Path = "",
    pos_translate: bool = False,
    force: bool = False,
    mi_threshold: float = 3.0,
    group_by: str = "source",
) -> Dict[str, str]:
    from shared.pipeline_steps import normalize_group_by

    project = load_project(project_dir)
    root = Path(project["project_dir"])
    corpus_type = normalize_template_name(corpus_type or project.get("corpus_type", "generic"))
    targets = project.get("targets", "") if targets is None else targets
    corpus = Path(corpus_dir) if corpus_dir else root / "corpus"
    if not corpus.exists():
        raise FileNotFoundError(f"Corpus directory does not exist: {corpus}")
    group_by = normalize_group_by(group_by)

    run_args = Namespace(
        input=str(corpus),
        output=str(root),
        targets=targets,
        corpus_type=corpus_type,
        country=False,
        force=force,
        skip="",
        only="4,5" if pos_translate else "4",
        group_by=group_by,
    )
    steps = [4, 5] if pos_translate else [4]
    run_config = build_run_config(run_args, steps, steps)
    write_run_config(root, run_config)

    model = write_corpus_model(
        root,
        input_path=str(corpus),
        targets=targets,
        corpus_type=corpus_type,
        corpus_id=run_config.get("corpus_id"),
        run_id=run_config.get("run_id"),
        corpus_dir=corpus,
    )

    # The rebuild above regenerates the registry from the TXT corpus and
    # drops any previously joined country column; re-apply it so the
    # country grouping mode sees up-to-date labels.
    from shared.corpus_model import apply_country_to_registry
    country_state = apply_country_to_registry(root)
    if country_state.get("updated"):
        _safe_console_print(
            f"国别已回写登记表: {country_state['matched']}/{country_state['documents']} 篇匹配"
            f"（未匹配 {country_state['unknown']} 篇 → Unknown）"
        )

    state: Dict[str, Any] = {"corpus_model": model}

    def _log(msg: str) -> None:
        _safe_console_print(msg)

    state["s4"] = s4_extract_adjectives(
        str(corpus), str(root), targets, log_fn=_log,
        mi_threshold=mi_threshold, group_by=group_by,
    )
    outputs = {"analysis_output": state["s4"]["adj_excel_path"], "group_by": group_by, **model}
    if pos_translate:
        state["s5"] = s5_pos_and_translate(state["s4"]["adj_excel_path"], str(root), log_fn=_log)
        outputs["pos_translation_output"] = state["s5"]["final_excel_path"]
    state["validation"] = generate_validation_artifacts(root)
    outputs.update(state["validation"])

    run_config["status"] = "completed"
    run_config["state"] = state
    write_run_config(root, run_config)

    project["targets"] = targets
    project["corpus_type"] = corpus_type
    project["group_by"] = group_by
    update_latest_from_paths(project, model)
    project["latest"]["analysis_output"] = outputs["analysis_output"]
    project["latest"]["group_by"] = group_by
    project["latest"]["target_hits_total"] = _kwic_hit_total(root)
    project["latest"]["validation_report"] = outputs.get("validation_report", "")
    project["history"].append({
        "event": "analyze", "at": now_iso(), "targets": targets,
        "group_by": group_by, "outputs": outputs,
    })
    save_project(root, project)
    return outputs


def project_review(project_dir: str | Path, *, sample_size: int = 50,
                   dual_coder: bool = False) -> Dict[str, str]:
    project = load_project(project_dir)
    root = Path(project["project_dir"])
    paths = generate_validation_artifacts(root, sample_size=sample_size,
                                          dual_coder=dual_coder)
    project["latest"]["validation_report"] = paths.get("validation_report", "")
    project["history"].append({"event": "review", "at": now_iso(),
                               "sample_size": sample_size, "dual_coder": dual_coder,
                               "paths": paths})
    save_project(root, project)
    return paths


def project_groups(project_dir: str | Path) -> Dict[str, Any]:
    """Generate the editable custom grouping template (01_corpus/group_overrides.xlsx)."""
    from shared.corpus_model import write_group_template

    project = load_project(project_dir)
    root = Path(project["project_dir"])
    result = write_group_template(root)
    project["latest"]["group_overrides"] = result.get("group_template", "")
    project["history"].append({"event": "groups", "at": now_iso(),
                               "sources": result.get("sources", 0),
                               "paths": result})
    save_project(root, project)
    return result


def project_run(
    project_dir: str | Path,
    *,
    input_path: str | Path,
    corpus_type: Optional[str] = None,
    targets: Optional[str] = None,
    default_source: str = "",
    text_col: str = "text",
    title_col: str = "",
    source_col: str = "",
    date_col: str = "",
    group_col: str = "",
    pos_translate: bool = False,
    mi_threshold: float = 3.0,
    group_by: str = "source",
) -> Dict[str, Dict[str, str]]:
    imported = project_import(
        project_dir,
        input_path=input_path,
        corpus_type=corpus_type,
        targets=targets,
        default_source=default_source,
        text_col=text_col,
        title_col=title_col,
        source_col=source_col,
        date_col=date_col,
        group_col=group_col,
    )
    analyzed = project_analyze(
        project_dir,
        targets=targets,
        corpus_type=corpus_type,
        pos_translate=pos_translate,
        mi_threshold=mi_threshold,
        group_by=group_by,
    )
    return {"import": imported, "analyze": analyzed}


def project_status(project_dir: str | Path) -> Dict[str, Any]:
    project = load_project(project_dir)
    root = Path(project["project_dir"])
    docs_path = root / "01_corpus" / "documents.csv"
    analysis_path = root / "adjectives_phrases.xlsx"
    review_dir = root / "06_review"
    validation_path = root / "07_reports" / "validation_report.xlsx"
    manifest_path = root / "01_corpus" / "corpus_manifest.json"

    documents = 0
    target_hits = 0
    if docs_path.exists():
        try:
            docs = pd.read_csv(docs_path)
            documents = len(docs)
            if "target_hits_total" in docs.columns:
                target_hits = int(pd.to_numeric(docs["target_hits_total"], errors="coerce").fillna(0).sum())
        except Exception:
            documents = 0
    if analysis_path.exists() and target_hits <= 0:
        # The registry can be rebuilt (e.g. by a later import) with different
        # targets; the analysis workbook remains the hit-count authority.
        target_hits = _kwic_hit_total(root)

    next_step = "import"
    if documents and not analysis_path.exists():
        next_step = "analyze"
    elif analysis_path.exists() and not validation_path.exists():
        next_step = "review"
    elif validation_path.exists():
        next_step = "inspect_results"

    return {
        "project_id": project.get("project_id", ""),
        "name": project.get("name", ""),
        "project_dir": str(root),
        "corpus_type": project.get("corpus_type", "generic"),
        "targets": project.get("targets", ""),
        "group_by": project.get("group_by", "source"),
        "documents": documents,
        "target_hits_total": target_hits,
        "has_corpus_manifest": manifest_path.exists(),
        "has_analysis": analysis_path.exists(),
        "has_review_dir": review_dir.exists(),
        "has_validation_report": validation_path.exists(),
        "next_step": next_step,
        "latest": project.get("latest", {}),
    }


def _read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No data available._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(str(row.get(col, "")).replace("\n", " ") for col in columns) + " |")
    return "\n".join([header, sep, *body])


def _top_sources(root: Path, limit: int = 10) -> list[dict[str, Any]]:
    docs_path = root / "01_corpus" / "documents.csv"
    if not docs_path.exists():
        return []
    try:
        docs = pd.read_csv(docs_path)
    except Exception:
        return []
    if docs.empty or "source_normalized" not in docs.columns:
        return []
    counts = docs["source_normalized"].fillna("Unknown").astype(str).value_counts().head(limit)
    return [{"Source": source, "Documents": int(count)} for source, count in counts.items()]


def _validation_summary(root: Path) -> list[dict[str, Any]]:
    path = root / "07_reports" / "validation_report.xlsx"
    if not path.exists():
        return []
    try:
        df = pd.read_excel(path, sheet_name="ValidationSummary")
    except Exception:
        return []
    cols = [col for col in ["Check", "Reviewed", "Correct", "Accuracy", "Most_Common_Error"] if col in df.columns]
    return df[cols].fillna("").to_dict(orient="records") if cols else []


def _analysis_summary(root: Path) -> list[dict[str, Any]]:
    path = root / "adjectives_phrases.xlsx"
    if not path.exists():
        return []
    rows = []
    try:
        xls = pd.ExcelFile(path)
        for sheet in ["KWIC", "Adjectives", "Phrases", "Collocates", "SemanticProsodyCandidates", "GroupComparison"]:
            if sheet in xls.sheet_names:
                df = pd.read_excel(path, sheet_name=sheet)
                rows.append({"Sheet": sheet, "Rows": len(df)})
    except Exception:
        return []
    return rows


def project_report(project_dir: str | Path, *, filename: str = "research_report.md") -> Dict[str, str]:
    project = load_project(project_dir)
    root = Path(project["project_dir"])
    status = project_status(root)
    manifest = _read_json_if_exists(root / "01_corpus" / "corpus_manifest.json")
    template = manifest.get("research_template") or get_template(project.get("corpus_type", "generic"))
    report_path = root / "07_reports" / filename
    report_path.parent.mkdir(parents=True, exist_ok=True)

    latest = project.get("latest", {})
    history_rows = [
        {"Event": item.get("event", ""), "At": item.get("at", ""), "Detail": item.get("input") or item.get("targets") or item.get("sample_size", "")}
        for item in project.get("history", [])[-10:]
    ]

    lines = [
        f"# Research Project Report: {project.get('name', root.name)}",
        "",
        f"Generated at: {now_iso()}",
        "",
        "## Project",
        "",
        f"- Project ID: `{project.get('project_id', '')}`",
        f"- Project directory: `{root}`",
        f"- Corpus type: `{project.get('corpus_type', 'generic')}`",
        f"- Template: {template.get('label', '')}",
        f"- Targets: {project.get('targets', '') or '_Not set_'}",
        f"- Suggested next step: `{status['next_step']}`",
        "",
        "## Corpus",
        "",
        f"- Documents: {status['documents']}",
        f"- Target hits: {status['target_hits_total']}",
        f"- Approximate words: {manifest.get('total_words_approx', '')}",
        f"- Corpus ID: `{manifest.get('corpus_id', latest.get('corpus_id', ''))}`",
        f"- Latest run ID: `{manifest.get('run_id', latest.get('run_id', ''))}`",
        "",
        "### Top Sources / Groups",
        "",
        _markdown_table(_top_sources(root), ["Source", "Documents"]),
        "",
        "## Analysis Outputs",
        "",
        _markdown_table(_analysis_summary(root), ["Sheet", "Rows"]),
        "",
        "## Validation",
        "",
        _markdown_table(_validation_summary(root), ["Check", "Reviewed", "Correct", "Accuracy", "Most_Common_Error"]),
        "",
        "## Key Files",
        "",
        f"- Project state: `{root / PROJECT_FILE}`",
        f"- Document registry: `{root / '01_corpus' / 'document_registry.xlsx'}`",
        f"- Analysis workbook: `{root / 'adjectives_phrases.xlsx'}`",
        f"- Review folder: `{root / '06_review'}`",
        f"- Validation report: `{root / '07_reports' / 'validation_report.xlsx'}`",
        f"- Method summary: `{root / '07_reports' / 'method_summary.md'}`",
        f"- Method limitations: `{root / '07_reports' / 'method_limitations.md'}`",
        "",
        "## Research Template",
        "",
        template.get("description", ""),
        "",
        f"Method focus: {template.get('method_focus', '')}",
        "",
        "### Coding Fields",
        "",
        _markdown_table(template.get("coding_fields", []), ["name", "instruction"]),
        "",
        "### Limitations",
        "",
        "\n".join(f"- {item}" for item in template.get("limitations", [])) or "_No template limitations listed._",
        "",
        "## Recent History",
        "",
        _markdown_table(history_rows, ["Event", "At", "Detail"]),
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")

    project["latest"]["research_report"] = str(report_path)
    project["history"].append({"event": "report", "at": now_iso(), "path": str(report_path)})
    save_project(root, project)
    return {"research_report": str(report_path)}
