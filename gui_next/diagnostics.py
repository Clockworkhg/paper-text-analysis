# -*- coding: utf-8 -*-
"""Diagnostics bundle export (Phase 4B #18).

A zip the researcher can attach to a bug report. Contents are strictly
privacy-bounded — never included: corpus text, KWIC contents, evidence
notes, writing prose, or any research content:

    diagnostics_info.txt     version / OS / runtime / build metadata
    packages.txt             package + spaCy model versions
    logs/…                   recent application + execution logs
    project_summary.json     structure summary + published-run identity
                             + manifest IDs/hashes (paths and counts only)
"""

from __future__ import annotations

import json
import os
import platform
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from gui_next.version import build_metadata, python_version, qt_version

# Log tail bound: at most the most recent 256 KB per log goes into the zip.
LOG_TAIL_BYTES = 256 * 1024


def project_summary(project_dir: Optional[Path]) -> dict:
    """Structure-level facts about the current project (no content)."""
    if project_dir is None:
        return {"project": None}
    root = Path(project_dir)
    summary: dict = {"project": {"path": str(root), "exists": root.exists()}}
    if not root.exists():
        return summary
    project_json = root / "project.json"
    try:
        data = json.loads(project_json.read_text(encoding="utf-8"))
        summary["project"].update({
            "name": data.get("name", ""),
            "project_id": data.get("project_id", ""),
            "corpus_type": data.get("corpus_type", ""),
            "targets": data.get("targets", ""),
            "created_at": data.get("created_at", ""),
        })
    except Exception as exc:
        summary["project"]["project_json_error"] = str(exc)

    corpus = root / "corpus"
    summary["corpus"] = {
        "exists": corpus.exists(),
        "document_count": sum(1 for _ in corpus.rglob("*.txt")) if corpus.exists() else 0,
    }
    for rel in ("adjectives_phrases.xlsx", "run_config.json",
                "01_corpus/documents.csv", "merged_sources.xlsx"):
        path = root / rel
        summary[rel] = {"exists": path.exists(),
                        "size": path.stat().st_size if path.exists() else 0}

    pointer = root / "runs" / "published_analysis.json"
    try:
        summary["published_run"] = json.loads(pointer.read_text(encoding="utf-8"))
    except Exception:
        summary["published_run"] = None

    manifests = []
    published = root / "runs" / "published"
    if published.exists():
        for manifest_path in sorted(published.glob("*/publication_manifest.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifests.append({
                    "run_id": manifest_path.parent.name,
                    "publication_manifest_sha256": data.get("publication_manifest_sha256", ""),
                    "corpus_fingerprint": data.get("corpus_fingerprint", ""),
                })
            except Exception:
                continue
    summary["published_generations"] = manifests
    return summary


def packages_text() -> str:
    """Installed package versions relevant to the analysis runtime."""
    lines = [f"python={python_version()}", f"qt={qt_version()}"]
    try:
        from importlib import metadata
        for name in ("pandas", "numpy", "openpyxl", "spacy", "nltk",
                     "rapidfuzz", "requests", "tldextract", "python-docx",
                     "matplotlib", "PySide6", "en-core-web-sm"):
            try:
                lines.append(f"{name}={metadata.version(name)}")
            except Exception:
                lines.append(f"{name}=(not installed)")
    except Exception as exc:
        lines.append(f"(metadata unavailable: {exc})")
    return "\n".join(lines)


def analysis_model_available() -> tuple[bool, str]:
    """spaCy en_core_web_sm presence check (#21) — never crashes the app."""
    try:
        import spacy  # noqa: F401
        try:
            spacy.load("en_core_web_sm")
            return True, "en_core_web_sm loaded"
        except Exception as exc:
            return False, f"English analysis model is unavailable: {exc}"
    except Exception as exc:
        return False, f"spaCy runtime unavailable: {exc}"


def export_diagnostics(project_dir: Optional[Path], out_path: Path) -> Path:
    """Write the diagnostics zip; returns the path written."""
    meta = build_metadata()
    info = [
        meta.get("app_name", "CADS Workbench"),
        f"version={meta.get('version', '')}",
        f"git_commit={meta.get('git_commit', '')}",
        f"build_timestamp={meta.get('build_timestamp', '')}",
        f"build_mode={meta.get('build_mode', '')}",
        f"python={python_version()}",
        f"qt={qt_version()}",
        f"os={platform.system()} {platform.release()} {platform.version()}",
        f"platform={platform.platform()}",
        f"exported_at={datetime.now().isoformat(timespec='seconds')}",
        f"frozen={getattr(__import__('sys'), 'frozen', False)}",
        f"analysis_model={analysis_model_available()[1]}",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("diagnostics_info.txt", "\n".join(info))
        bundle.writestr("packages.txt", packages_text())
        bundle.writestr("project_summary.json",
                        json.dumps(project_summary(project_dir),
                                   ensure_ascii=False, indent=2))
        from gui_next.appdata import logs_dir
        log_root = logs_dir()
        for name in ("application.log", "execution.log"):
            path = log_root / name
            if path.exists():
                with open(path, "rb") as handle:
                    handle.seek(max(0, os.path.getsize(path) - LOG_TAIL_BYTES))
                    bundle.writestr(f"logs/{name}",
                                    handle.read().decode("utf-8", errors="replace"))
    return out_path
