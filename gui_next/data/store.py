# -*- coding: utf-8 -*-
"""Read-only data access for the gui-next workbench.

Loads existing project outputs (project.json, document registry, analysis
workbook, review files, frozen runs) without touching them. The analysis
kernel and file formats are frozen; this layer only reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

EMPTY_DF = pd.DataFrame()

CODING_COLUMN_HINTS = ("semantic", "final", "research_move", "stance", "coding", "judgement", "judgment")
AUTO_VALUES = {"", "nan", "none", "needs_kwic_review", "uncoded_candidate"}

# State glyphs/roles used by pages to color pipeline status rows.
OK = "✓"
WARN = "⚠"
PENDING = "○"
OK_ROLE = "ok"
WARN_ROLE = "warn"
MUTED_ROLE = "muted"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_df_excel(path: Path, sheet: str) -> pd.DataFrame:
    try:
        return pd.read_excel(path, sheet_name=sheet)
    except Exception:
        return EMPTY_DF


class ProjectStore:
    """Snapshot of a project directory for the GUI. Call refresh() to reload."""

    def __init__(self, project_dir: str | Path):
        self.root = Path(project_dir).resolve()
        self.refresh()

    # ------------------------------------------------------------------
    # basics

    def refresh(self) -> None:
        self.project: Dict[str, Any] = _read_json(self.root / "project.json")
        self.run_config: Dict[str, Any] = _read_json(self.root / "run_config.json")
        self.sanity_report: Dict[str, Any] = _read_json(self.root / "07_reports" / "corpus_sanity_report.json")
        self.manifest: Dict[str, Any] = _read_json(self.root / "01_corpus" / "corpus_manifest.json")
        self._docs: Optional[pd.DataFrame] = None
        self._kwic: Optional[pd.DataFrame] = None
        self._collocates: Optional[pd.DataFrame] = None
        self._adjectives: Optional[pd.DataFrame] = None
        self._group: Optional[pd.DataFrame] = None
        self._semantic: Optional[pd.DataFrame] = None
        self._sources: Optional[pd.DataFrame] = None

    @property
    def is_project(self) -> bool:
        return bool(self.project)

    @property
    def name(self) -> str:
        return self.project.get("name", self.root.name)

    @property
    def targets(self) -> List[str]:
        raw = self.project.get("targets", "") or self.run_config.get("targets", "")
        return [t.strip() for t in raw.split(";") if t.strip()]

    @property
    def group_by(self) -> str:
        return self.project.get("group_by", self.run_config.get("group_by", "source"))

    @property
    def run_id(self) -> str:
        return self.run_config.get("run_id", "")

    @property
    def documents_df(self) -> pd.DataFrame:
        if self._docs is None:
            path = self.root / "01_corpus" / "documents.csv"
            try:
                self._docs = pd.read_csv(path)
            except Exception:
                self._docs = EMPTY_DF
        return self._docs

    def _sheet(self, name: str) -> pd.DataFrame:
        path = self.root / "adjectives_phrases.xlsx"
        if not path.exists():
            return EMPTY_DF
        try:
            return pd.read_excel(path, sheet_name=name)
        except Exception:
            return EMPTY_DF

    @property
    def kwic_df(self) -> pd.DataFrame:
        if self._kwic is None:
            self._kwic = self._sheet("KWIC")
        return self._kwic

    @property
    def collocates_df(self) -> pd.DataFrame:
        if self._collocates is None:
            self._collocates = self._sheet("Collocates")
        return self._collocates

    @property
    def adjectives_df(self) -> pd.DataFrame:
        if self._adjectives is None:
            self._adjectives = self._sheet("Adjectives")
        return self._adjectives

    @property
    def group_df(self) -> pd.DataFrame:
        if self._group is None:
            self._group = self._sheet("GroupComparison")
        return self._group

    @property
    def semantic_df(self) -> pd.DataFrame:
        if self._semantic is None:
            self._semantic = self._sheet("SemanticProsodyCandidates")
        return self._semantic

    @property
    def sources_df(self) -> pd.DataFrame:
        if self._sources is None:
            self._sources = _read_df_excel(self.root / "merged_sources.xlsx", "WithCountry")
        return self._sources

    # ------------------------------------------------------------------
    # review files (read-only summary)

    def review_files(self) -> List[Dict[str, Any]]:
        """List modifier-review workbooks, best final candidates first."""
        review_dir = self.root / "06_review"
        if not review_dir.exists():
            return []
        files = sorted(review_dir.glob("modifier_semantic_review*.xlsx"))
        priority = {"modifier_semantic_review_FINAL.xlsx": 0}
        loaded = []
        for path in files:
            sheet, total, coded = self._review_progress(path)
            loaded.append({
                "path": path,
                "name": path.name,
                "priority": priority.get(path.name, (0 if "FINAL" in path.name else 1 if "coder" in path.name else 2)),
                "sheet": sheet,
                "rows": total,
                "coded": coded,
                "percent": round(100 * coded / total) if total else 0,
            })
        return sorted(loaded, key=lambda item: item["priority"])

    def _review_progress(self, path: Path) -> tuple[str, int, int]:
        """Best-effort coding progress: rows with any coding-hint column filled."""
        try:
            xls = pd.ExcelFile(path)
        except Exception:
            return "", 0, 0
        sheet_name, total, coded = "", 0, 0
        for sheet in xls.sheet_names:
            df = _read_df_excel(path, sheet)
            if df.empty:
                continue
            coding_cols = [
                col for col in df.columns
                if any(hint in str(col).lower() for hint in CODING_COLUMN_HINTS)
            ]
            if not coding_cols:
                continue
            sheet_name, total = sheet, len(df)
            filled = df[coding_cols].astype(str)
            is_set = filled.apply(
                lambda col: ~col.str.strip().str.lower().isin(AUTO_VALUES)
            )
            coded = int(is_set.any(axis=1).sum())
            break
        return sheet_name, total, coded

    # ------------------------------------------------------------------
    # runs

    def frozen_runs(self) -> List[Dict[str, Any]]:
        return list(self.project.get("frozen_runs", []))

    def runs_index(self) -> List[Dict[str, Any]]:
        """Frozen runs plus the current (unfrozen) run, newest first."""
        rows = [
            {
                "run_id": item.get("run_id", ""),
                "label": item.get("label", ""),
                "at": item.get("at", ""),
                "frozen": True,
                "files": item.get("files", 0),
                "dir": item.get("dir", ""),
            }
            for item in self.frozen_runs()
        ]
        if self.run_id:
            frozen_ids = {row["run_id"] for row in rows}
            if self.run_id not in frozen_ids:
                rows.insert(0, {
                    "run_id": self.run_id,
                    "label": "current",
                    "at": self.run_config.get("created_at", ""),
                    "frozen": False,
                    "files": 0,
                    "dir": "",
                })
        return rows

    def run_manifest(self, run_id: str) -> Dict[str, Any]:
        return _read_json(self.root / "runs" / run_id / "manifest.json")

    # ------------------------------------------------------------------
    # inter-rater reliability (honest statistic display)

    def reliability_summary(self, limit: int = 6) -> List[Dict[str, Any]]:
        """Judgment-field reliability rows with actual statistic values.

        Rows look like {metric, field, value, pairs, interpretation}; a NaN
        value stays "" so the UI never upgrades 'no data' into a pass.
        """
        path = self.root / "07_reports" / "validation_report.xlsx"
        if not path.exists():
            return []
        try:
            if "InterraterReliability" not in pd.ExcelFile(path).sheet_names:
                return []
            df = pd.read_excel(path, sheet_name="InterraterReliability")
        except Exception:
            return []
        if df.empty:
            return []
        judgment_fields = {"is_correct", "error_type", "human_result", "frame_type",
                           "polarity", "appraisal_type", "frame_code", "target_relation"}
        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            field_name = str(row.get("Field", ""))
            if field_name and field_name not in judgment_fields:
                continue
            value = row.get("Value")
            value_str = "" if value is None or pd.isna(value) else f"{float(value):.3f}"
            rows.append({
                "sheet": str(row.get("Sheet", "")),
                "field": field_name,
                "metric": str(row.get("Metric", "")),
                "value": value_str,
                "pairs": row.get("n_Pairs", ""),
                "interpretation": str(row.get("Interpretation", "")),
            })
            if len(rows) >= limit:
                break
        return rows

    # ------------------------------------------------------------------
    # overview status

    def _corpus_txt_count(self) -> int:
        corpus = self.root / "corpus"
        return sum(1 for _ in corpus.rglob("*.txt")) if corpus.exists() else 0

    def has_analysis(self) -> bool:
        return (self.root / "adjectives_phrases.xlsx").exists()

    def analysis_blocked_reason(self) -> str:
        failures = self.sanity_report.get("failures", {}) if self.sanity_report else {}
        marker = failures.get("marker_lines_in_body", {}).get("count", 0)
        tags = failures.get("header_tags_in_body", {}).get("count", 0)
        if marker or tags:
            total = self.sanity_report.get("documents", "?")
            return (
                f"语料卫生检查未通过:{marker} 篇文档正文含分隔线标记,{tags} 篇含头部标签"
                f"(共 {total} 篇)。请用原始 DOCX/干净正文重新导入。"
            )
        return ""

    def pipeline_status(
        self,
        health: Optional[tuple] = None,
        source_progress: Optional[Dict[str, int]] = None,
        country_pending: int = 0,
        country_total: int = 0,
        semantic_progress: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, str]]:
        """Rows for the Overview pipeline table.

        Review rows are split (Phase 2A): source normalization review,
        country review, semantic review, coder reconciliation, and
        reliability each report their own state instead of one percentage.
        ``health`` is a (HealthState, detail) tuple from gui_next.data.health.
        """
        corpus_txt = self._corpus_txt_count()

        if health is not None:
            state, detail = health
            role = {"PASS": OK_ROLE, "WARNING": WARN_ROLE, "BLOCKED": "error",
                    "STALE": WARN_ROLE, "UNKNOWN": MUTED_ROLE}.get(state.value, MUTED_ROLE)
            sanitation = (state.value, detail, role)
        else:
            sanitation = ("UNKNOWN", "未评估", MUTED_ROLE)

        if source_progress and source_progress.get("total"):
            decided, total = source_progress["decided"], source_progress["total"]
            status = source_progress.get("status", "")
            if status == "STALE":
                src_state = "STALE"
                src_detail = (f"旧复核结果 {source_progress.get('stale_count', 0)} 条已保留未计入"
                              "(需要 reconciliation/migration);当前已复核 "
                              f"{decided}/{total}")
            else:
                src_state = f"{decided}/{total}"
                src_detail = "全部来源已复核" if decided >= total else f"待复核 {total - decided} 个来源"
        else:
            src_state, src_detail = "–", "无来源清单或未开始"

        if country_total:
            if country_pending:
                country_state, country_detail = WARN, f"待复核 {country_pending} 条国别建议"
            else:
                country_state, country_detail = OK, "国别建议均已处理"
        else:
            country_state, country_detail = "–", "无国别建议(国别推断未运行)"

        if semantic_progress and semantic_progress.get("total"):
            coded, total = semantic_progress["coded"], semantic_progress["total"]
            status = semantic_progress.get("status", "")
            if status == "STALE":
                sem_state = "STALE"
                sem_detail = (f"旧人工编码 {semantic_progress.get('stale_count', 0)} 条已保留未计入"
                              "(需要 reconciliation/migration);当前已编码 "
                              f"{coded}/{total}")
            else:
                sem_state = f"{coded}/{total}"
                sem_detail = "全部候选已编码" if coded >= total else f"待编码 {total - coded} 条候选"
        else:
            sem_state, sem_detail = "–", "无候选清单或未开始"

        # Coder reconciliation: a *file fact* (FINAL/coder workbooks), never
        # inferred from reliability data.
        review_files = self.review_files()
        coder_files = [item for item in review_files if "coder" in item["name"]]
        final_file = next((item for item in review_files if "FINAL" in item["name"]), None)
        if final_file:
            recon_state = OK
            recon_detail = f"FINAL 已生成({len(coder_files)} 份编码文件)" if coder_files else "FINAL 已生成"
        elif coder_files:
            recon_state, recon_detail = WARN, f"{len(coder_files)} 份编码文件待调和"
        else:
            recon_state, recon_detail = "–", "无双编码文件"

        # Reliability: only actual IRR facts (metric/value/n). No value means
        # "尚无数据" — never auto-interpreted as reconciled or passed.
        reliability_rows = self.reliability_summary()
        judgment = next((row for row in reliability_rows
                         if row["field"] in ("is_correct", "error_type") and row["value"]), None)
        if judgment:
            irr_state = f"{judgment['metric']} {judgment['value']}"
            irr_detail = (f"{judgment['field']} · n={judgment['pairs']} · "
                          f"{judgment['interpretation']}(统计值,非方法学通过)")
        elif reliability_rows:
            irr_state, irr_detail = "–", "判定字段信度:尚无数据"
        else:
            irr_state, irr_detail = "–", "信度报告尚未生成"

        frozen = self.frozen_runs()
        final_run = (OK, frozen[-1].get("label") or frozen[-1].get("run_id", ""), OK_ROLE) if frozen else (PENDING, "未固化", MUTED_ROLE)

        return [
            {"stage": "语料导入", "state": corpus_txt, "detail": f"{corpus_txt} 篇文档" if corpus_txt else "未导入"},
            {"stage": "语料卫生", "state": sanitation[0], "detail": sanitation[1]},
            {"stage": "来源规范化复核", "state": src_state, "detail": src_detail},
            {"stage": "国别复核", "state": country_state, "detail": country_detail},
            {"stage": "分析", "state": OK if self.has_analysis() else PENDING, "detail": f"运行 {self.run_id[:13]}" if self.has_analysis() else "尚未运行"},
            {"stage": "语义韵复核", "state": sem_state, "detail": sem_detail},
            {"stage": "编码者调和", "state": recon_state, "detail": recon_detail},
            {"stage": "编码者信度", "state": irr_state, "detail": irr_detail},
            {"stage": "最终运行固化", "state": final_run[0], "detail": final_run[1]},
        ]

    def stat_chips(self) -> List[Dict[str, str]]:
        return [
            {"label": "文档", "value": str(len(self.documents_df))},
            {"label": "KWIC 命中", "value": f"{len(self.kwic_df):,}"},
            {"label": "搭配候选", "value": f"{len(self.collocates_df):,}"},
            {"label": "目标词", "value": str(len(self.targets))},
            {"label": "分组", "value": self.group_by},
            {"label": "运行", "value": f"#{self.run_id[-6:]}" if self.run_id else "–"},
        ]

