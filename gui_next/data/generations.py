# -*- coding: utf-8 -*-
"""Published generation resolver (read side).

Historical evidence resolves against ``runs/published/<run_id>/`` — the
immutable artifact archive created at publication time — and NEVER against
whatever currently happens to sit in the project root. A generation that is
missing or fails integrity checks is reported as such; there is no silent
fallback to the latest run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class GenerationIntegrity:
    state: str          # VERIFIED | SOURCE_UNAVAILABLE | INTEGRITY_ERROR
    detail: str = ""


class GenerationResolver:
    def __init__(self, project_dir: str | Path):
        self.root = Path(project_dir)

    # ------------------------------------------------------------------

    def generation_dir(self, run_id: str) -> Path:
        return self.root / "runs" / "published" / run_id

    def load_manifest(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = self.generation_dir(run_id) / "publication_manifest.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def artifact_path(self, run_id: str, rel: str) -> Path:
        return self.generation_dir(run_id) / "artifacts" / rel

    def artifact_exists(self, run_id: str, rel: str) -> bool:
        return self.artifact_path(run_id, rel).exists()

    # ------------------------------------------------------------------

    def integrity(self, run_id: str, publication_manifest_hash: str = "",
                  stored_artifact_hashes: Optional[Dict[str, str]] = None) -> GenerationIntegrity:
        """Full evidence-side integrity check for one archived generation."""
        manifest = self.load_manifest(run_id)
        if manifest is None:
            return GenerationIntegrity("SOURCE_UNAVAILABLE", "已发布代际归档不存在")
        if publication_manifest_hash and \
                manifest.get("publication_manifest_sha256") != publication_manifest_hash:
            return GenerationIntegrity("INTEGRITY_ERROR", "publication manifest 哈希不匹配")

        if stored_artifact_hashes:
            for rel, expected in stored_artifact_hashes.items():
                path = self.artifact_path(run_id, rel)
                if not path.exists():
                    return GenerationIntegrity("INTEGRITY_ERROR", f"归档产物缺失: {rel}")
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual != expected:
                    return GenerationIntegrity("INTEGRITY_ERROR", f"归档产物哈希不匹配: {rel}")
        return GenerationIntegrity("VERIFIED")

    # ------------------------------------------------------------------
    # artifact readers (historical generation only)

    def read_analysis_workbook(self, run_id: str) -> Optional[pd.ExcelFile]:
        path = self.artifact_path(run_id, "adjectives_phrases.xlsx")
        if not path.exists():
            return None
        try:
            return pd.ExcelFile(path)
        except Exception:
            return None

    def read_kwic(self, run_id: str) -> pd.DataFrame:
        xls = self.read_analysis_workbook(run_id)
        if xls is None or "KWIC" not in xls.sheet_names:
            return pd.DataFrame()
        try:
            return pd.read_excel(xls, sheet_name="KWIC")
        except Exception:
            return pd.DataFrame()

    def read_registry(self, run_id: str) -> pd.DataFrame:
        path = self.artifact_path(run_id, "01_corpus/documents.csv")
        if not path.exists():
            return pd.DataFrame()
        try:
            # utf-8-sig: write_corpus_model emits a BOM that would otherwise
            # corrupt the first column name ("document_id").
            return pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame()

    def resolve_document(self, run_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Document metadata from the archived registry of this generation."""
        registry = self.read_registry(run_id)
        if registry.empty or "document_id" not in registry.columns:
            return None
        match = registry[registry["document_id"].astype(str) == str(document_id)]
        if match.empty:
            return None
        return match.iloc[0].to_dict()
