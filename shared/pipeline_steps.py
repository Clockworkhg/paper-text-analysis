# -*- coding: utf-8 -*-
"""
Shared pipeline step functions used by both CLI (pipeline.py) and GUI (integrated_app.py).
Each step accepts an optional log_fn callback for progress reporting.
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from shared.exceptions import (
    AnalysisError,
    InputFileNotFoundError,
    MissingPreconditionError,
)
from shared.research_output import write_excel_with_readme

logger = logging.getLogger(__name__)

STEPS: Dict[int, str] = {
    1: "Lexis DOCX \u2192 TXT + \u7edf\u8ba1\u62a5\u544a",
    2: "\u7edf\u8ba1JSON \u2192 \u673a\u6784\u7edf\u8ba1\u8868 Excel",
    3: "\u673a\u6784\u5408\u5e76 + \u56fd\u522b\u8bc6\u522b",
    4: "TX\u8bed\u6599 \u2192 \u4fee\u9970\u5f62\u5bb9\u8bcd/\u77ed\u8bed\u7edf\u8ba1",
    5: "\u5f62\u5bb9\u8bcd\u8868 \u2192 \u8bcd\u6027 + \u4e2d\u6587\u7ffb\u8bd1",
}


def _log(log_fn: Optional[Callable[[str], None]], msg: str, level: str = "info") -> None:
    if log_fn:
        log_fn(msg)
    log_method = getattr(logger, level, logger.info)
    log_method(msg)


def s1_docx_to_txt(
    docx_path: str,
    out_dir: str,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    from docx import Document
    from LexisWordToTxt.app.processor import process_docx, write_report_json, preflight_check
    from LexisWordToTxt.app.constants import DEFAULT_SOURCE_CANONICAL_MAP, DEFAULT_NOISE_KEYWORDS

    docx = Path(docx_path)
    if not docx.exists():
        raise InputFileNotFoundError(f"\u8f93\u5165\u6587\u4ef6\u4e0d\u5b58\u5728: {docx_path}")

    out = Path(out_dir) / "corpus"
    out.mkdir(parents=True, exist_ok=True)

    doc = Document(docx)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    check = preflight_check(full_text)
    if not check["ok"]:
        _log(log_fn, f"  \u26a0 \u9884\u68c0\u8b66\u544a: {'; '.join(check['messages'])}", "warning")

    count, empty, report = process_docx(
        docx_path=docx,
        out_dir=out,
        write_metadata=True,
        filename_max_len=80,
        group_by_source=True,
        canonical_map=DEFAULT_SOURCE_CANONICAL_MAP,
        noise_keywords=DEFAULT_NOISE_KEYWORDS,
        normalize_source=True,
        log_fn=log_fn if log_fn else lambda msg: None,
    )

    report_path = write_report_json(out, report)
    _log(log_fn, f"  \u6587\u7ae0\u6570: {count}, \u7a7a\u6b63\u6587: {empty}")
    _log(log_fn, f"  corpus: {out}")
    _log(log_fn, f"  report: {report_path}")
    return {"count": count, "empty": empty, "report_path": str(report_path), "corpus_dir": str(out)}


def s2_json_to_excel(
    report_path: str,
    out_dir: str,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    excel_path = out / "source_counts.xlsx"

    if not Path(report_path).exists():
        raise InputFileNotFoundError(f"\u62a5\u544aJSON\u4e0d\u5b58\u5728: {report_path}")

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "by_source_count" not in data or not isinstance(data["by_source_count"], dict):
        raise ValueError("JSON \u7f3a\u5c11 by_source_count \u5b57\u6bb5")

    sources: Dict[str, int] = data["by_source_count"]
    df = pd.DataFrame(
        [{"Source": k, "Count": v} for k, v in sources.items()]
    ).sort_values("Count", ascending=False)

    write_excel_with_readme(
        str(excel_path),
        {"Sources": df},
        title="Source counts from LexisNexis report",
        description="Counts article frequency by original source name before source normalization and country inference.",
        fields={
            "Source": "Original source name reported in the LexisNexis export.",
            "Count": "Number of articles associated with the source.",
        },
        parameters={"report_path": report_path, "out_dir": str(out)},
    )
    _log(log_fn, f"  \u673a\u6784\u6570: {len(df)}")
    _log(log_fn, f"  output: {excel_path}")
    return {"excel_path": str(excel_path), "source_count": len(df)}


def s3_merge_and_country(
    source_excel_path: str,
    out_dir: str,
    enable_country: bool = True,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    from config import MergeConfig
    from modules.hebing import run_hebing

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    merged_path = out / "merged_sources.xlsx"

    if not Path(source_excel_path).exists():
        raise InputFileNotFoundError(f"\u6e90\u8868\u4e0d\u5b58\u5728: {source_excel_path}")

    cfg = MergeConfig(
        fuzzy_threshold=92,
        enable_country_lookup=enable_country,
        request_delay_ms=150,
        max_lookup=800,
        auto_accept_threshold=0.85,
        pie_topn=12,
    )

    run_hebing(
        in_path=source_excel_path,
        out_path=str(merged_path),
        overrides_path="",
        cfg=cfg,
        verbose=True,
    )

    from shared.corpus_model import apply_country_to_registry
    try:
        country_state = apply_country_to_registry(out)
        if country_state.get("updated"):
            _log(
                log_fn,
                f"  国别已回写登记表: {country_state['matched']}/{country_state['documents']} 篇匹配"
                f"（未匹配 {country_state['unknown']} 篇 → Unknown）",
            )
    except Exception as exc:
        _log(log_fn, f"  ⚠ 国别回写登记表失败: {exc}", "warning")

    _log(log_fn, f"  output: {merged_path}")
    return {"merged_path": str(merged_path)}


GROUPING_MODES = ("source", "institution", "country", "custom")


def normalize_group_by(value: str) -> str:
    mode = (value or "source").strip().lower()
    return mode if mode in GROUPING_MODES else "source"


def _build_group_map(
    out: Path,
    registry: Dict[str, Dict[str, Any]],
    group_by: str,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, str]:
    """Build a document/source -> group-label map for country/custom modes."""
    from shared.corpus_model import load_group_overrides

    group_map: Dict[str, str] = {}
    if group_by == "custom":
        overrides = load_group_overrides(out)
        if not overrides:
            _log(
                log_fn,
                "  ⚠ 未找到 01_corpus/group_overrides.xlsx（或缺少 source/group 列），"
                "自定义分组回退为按媒体机构分组。",
                "warning",
            )
            return group_map
        group_map.update(overrides)

    keyed: Dict[str, str] = {}
    has_country_column = False
    for meta in registry.values():
        source = str(meta.get("source_normalized", "") or "").strip()
        document_id = str(meta.get("document_id", "") or "").strip()
        label = ""
        if group_by == "country":
            label = str(meta.get("country", "") or "").strip()
            has_country_column = has_country_column or bool(str(meta.get("country", "")) not in ("", "nan", "None"))
        elif group_by == "custom" and source:
            label = overrides.get(source, "")
        if not label:
            continue
        if source:
            keyed.setdefault(source, label)
        if document_id:
            keyed.setdefault(document_id, label)
    if group_by == "country" and not has_country_column:
        _log(
            log_fn,
            "  ⚠ 登记表缺少 country 列（先运行步骤 3 机构合并+国别），国别分组回退为按媒体机构分组。",
            "warning",
        )
    group_map.update(keyed)
    return group_map


def s4_extract_adjectives(
    corpus_dir: str,
    out_dir: str,
    targets: str,
    log_fn: Optional[Callable[[str], None]] = None,
    mi_threshold: float = 3.0,
    group_by: str = "source",
) -> Dict[str, Any]:
    from config import TxtAnalysisConfig
    from modules.txt_modifier_extractor_gui import process_txt, split_targets

    corpus = Path(corpus_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    group_by = normalize_group_by(group_by)

    all_txt_files = list(corpus.rglob("*.txt"))
    if not all_txt_files:
        raise MissingPreconditionError(f"\u8bed\u6599\u76ee\u5f55 {corpus_dir} \u4e0b\u672a\u627e\u5230 TXT \u6587\u4ef6")
    all_txt_files = sorted(all_txt_files)

    registry: Dict[str, Dict[str, Any]] = {}
    registry_path = out / "01_corpus" / "documents.csv"
    if registry_path.exists():
        try:
            reg_df = pd.read_csv(registry_path)
            for _, row in reg_df.iterrows():
                rel = str(row.get("relative_path", "")).replace("\\", "/")
                if rel:
                    registry[rel] = row.to_dict()
        except Exception:
            registry = {}

    group_map: Dict[str, str] = {}
    if group_by in ("country", "custom"):
        group_map = _build_group_map(out, registry, group_by, log_fn=log_fn)

    merged_txt = out / "_corpus_merged.txt"
    skipped = 0
    with open(merged_txt, "w", encoding="utf-8") as f:
        for tf in all_txt_files:
            try:
                content = tf.read_text(encoding="utf-8", errors="ignore")
                rel = tf.relative_to(corpus).as_posix()
                meta = registry.get(rel, {})
                if meta:
                    def _meta_value(key: str) -> str:
                        value = meta.get(key, "")
                        return "" if pd.isna(value) else str(value)

                    header_lines = [
                        f"<DOCUMENT_ID>: {_meta_value('document_id')}",
                        f"<SOURCE_NORM>: {_meta_value('source_normalized')}",
                        f"<CORPUS_ID>: {_meta_value('corpus_id')}",
                        f"<RUN_ID>: {_meta_value('run_id')}",
                    ]
                    content = "\n".join(header_lines) + "\n" + content
                f.write(content)
                f.write("\n\n==========\n\n")
            except Exception:
                skipped += 1
                _log(log_fn, f"  \u26a0 \u8df3\u8fc7 {tf.name}", "warning")

    if skipped:
        _log(log_fn, f"  \u8df3\u8fc7 {skipped} \u4e2a\u65e0\u6cd5\u8bfb\u53d6\u7684\u6587\u4ef6", "warning")

    _log(log_fn, f"  \u5408\u5e76 {len(all_txt_files) - skipped} \u4e2aTXT \u2192 {merged_txt}")

    target_list = split_targets(targets)
    _log(log_fn, f"  \u68c0\u7d22\u76ee\u6807: {target_list}")
    _log(log_fn, f"  \u5206\u7ec4\u65b9\u5f0f: {group_by}")

    adj_excel = out / "adjectives_phrases.xlsx"
    cfg = TxtAnalysisConfig(
        split_mode="regex",
        split_regex="====LINE====",
        window_tokens=8,
        phrase_max_tokens=6,
        nlp_batch_size=64,
        max_doc_chars=200000,
        use_online_judge=False,
        mi_threshold=mi_threshold,
        group_by=group_by,
    )

    process_txt(
        input_path=str(merged_txt),
        output_path=str(adj_excel),
        targets=target_list,
        cfg=cfg,
        log_cb=log_fn if log_fn else lambda msg: None,
        group_map=group_map or None,
    )

    _log(log_fn, f"  output: {adj_excel}")
    return {"adj_excel_path": str(adj_excel), "group_by": group_by}


def s5_pos_and_translate(
    adj_excel_path: str,
    out_dir: str,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    from modules.jiacixing import ensure_nltk_data, guess_pos, Translator

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    final_excel = out / "adjectives_final.xlsx"

    if not Path(adj_excel_path).exists():
        raise InputFileNotFoundError(f"\u5f62\u5bb9\u8bcd\u8868\u4e0d\u5b58\u5728: {adj_excel_path}")

    nltk_ready = ensure_nltk_data()
    if not nltk_ready:
        _log(log_fn, "  \u26a0 NLTK data unavailable; POS labels will fall back to UNKNOWN.", "warning")

    df_adj = pd.read_excel(adj_excel_path, sheet_name="Adjectives")
    translator = Translator(concurrency=5)

    words: List[str] = df_adj["Adjective"].tolist()
    _log(log_fn, f"  \u8bcd\u6027\u6807\u6ce8 {len(words)} \u8bcd...")
    pos_list = [guess_pos(None if pd.isna(w) else str(w)) for w in words]

    _log(log_fn, f"  \u4e2d\u6587\u7ffb\u8bd1 {len(words)} \u8bcd\uff08\u5e76\u53d1\uff09...")
    zh_list = translator.translate_batch(
        ["" if pd.isna(w) else str(w) for w in words]
    )

    df_adj["POS"] = pos_list
    df_adj["\u4e2d\u6587\u610f\u601d"] = zh_list

    write_excel_with_readme(
        str(final_excel),
        {"AdjectivesFinal": df_adj},
        title="POS and translation enrichment for adjective candidates",
        description="Adds automatic POS labels and Chinese translation helpers to adjective candidates.",
        fields={
            "Adjective": "Candidate adjective extracted near a target term.",
            "POS": "Automatically guessed part of speech.",
            "\u4e2d\u6587\u610f\u601d": "Automatic translation/helper meaning; review before interpretation.",
        },
        parameters={"input": adj_excel_path, "translator_concurrency": 5},
    )
    _log(log_fn, f"  output: {final_excel}")
    return {"final_excel_path": str(final_excel)}


def check_step_done(step_num: int, out_dir: str) -> bool:
    out = Path(out_dir)
    checks: Dict[int, Any] = {
        1: lambda: (out / "corpus").exists() and any((out / "corpus").rglob("*.txt")),
        2: lambda: (out / "source_counts.xlsx").exists(),
        3: lambda: (out / "merged_sources.xlsx").exists(),
        4: lambda: (out / "adjectives_phrases.xlsx").exists(),
        5: lambda: (out / "adjectives_final.xlsx").exists(),
    }
    fn = checks.get(step_num)
    return fn() if fn else False
