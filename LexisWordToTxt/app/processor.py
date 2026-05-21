# app/processor.py
from pathlib import Path
from docx import Document
from datetime import datetime
import json

from .utils import safe_filename, safe_foldername
from .rules import extract_metadata, extract_body, get_canonical_source

def preflight_check(full_text: str):
    """
    对 Lexis DOCX 文本做格式预检，返回 dict：
    - ok: 是否满足最低运行条件
    - level: "error" | "warn" | "ok"
    - messages: 需要展示给用户的信息列表
    - stats: 统计信息（供日志/弹窗使用）
    """
    t = full_text.replace("\r\n", "\n").replace("\r", "\n")

    eod_count = t.count("End of Document")
    body_count = t.count("\nBody\n") + t.count("\nBody\r\n") + t.count("\nBody")  # 宽松统计
    # 最稳妥还是 split 后再判断
    blocks = [b.strip() for b in t.split("End of Document") if b.strip()]
    block_count = len(blocks)

    # 逐块检查是否包含 Body 行（严格：行等于 Body）
    def has_body_line(block: str) -> bool:
        for line in block.split("\n"):
            if line.strip() == "Body":
                return True
        return False

    blocks_with_body = sum(1 for b in blocks if has_body_line(b))
    blocks_without_body = block_count - blocks_with_body

    messages = []
    level = "ok"
    ok = True

    # 硬性错误：完全没有 End of Document，无法拆分
    if eod_count == 0 and block_count <= 1:
        ok = False
        level = "error"
        messages.append("未检测到 'End of Document' 分隔标记：无法拆分为多篇新闻。")
        messages.append("请确认：Lexis 导出时包含全文，并且导出的 Word 文档保留了 'End of Document'。")

    # 硬性错误：连 Body 都不存在（提取正文会全空）
    if ok and blocks_with_body == 0:
        # 这里不直接判死刑：有些导出可能把正文段落结构改了，但通常跑不出内容
        level = "error"
        ok = False
        messages.append("未检测到任何 'Body' 标记：提取正文将失败（输出正文可能为空）。")
        messages.append("请确认：Lexis 导出内容包含 'Body' 段落标记。")

    # 警告：End of Document 太少
    if ok and eod_count == 0 and block_count == 1:
        level = "warn"
        messages.append("仅检测到 1 个文档块且缺少 'End of Document'：可能只导出了一篇或格式不标准。")

    # 警告：部分文章缺少 Body
    if ok and blocks_without_body > 0:
        ratio = blocks_without_body / max(block_count, 1)
        # 缺失比例高就提示更强烈
        if ratio >= 0.3:
            level = "warn"
            messages.append(f"有 {blocks_without_body}/{block_count} 篇未检测到 'Body'：可能导出字段不完整或格式异常。")
        else:
            messages.append(f"提示：有 {blocks_without_body}/{block_count} 篇未检测到 'Body'（可能正常，也可能是格式差异）。")

    stats = {
        "eod_count": eod_count,
        "block_count": block_count,
        "blocks_with_body": blocks_with_body,
        "blocks_without_body": blocks_without_body,
        "body_count_rough": body_count,
    }

    return {"ok": ok, "level": level, "messages": messages, "stats": stats}

def process_docx(docx_path: Path,
                 out_dir: Path,
                 write_metadata: bool,
                 filename_max_len: int,
                 group_by_source: bool,
                 canonical_map: dict,
                 noise_keywords: list[str],
                 normalize_source: bool,
                 log_fn):

    """
    核心处理函数：从 docx 提取文章，拆分 End of Document，输出 txt。
    log_fn: callable(str) 用于把日志写到 GUI
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = Document(docx_path)
    full_text = "\n".join(p.text for p in doc.paragraphs)

    raw_articles = full_text.split("End of Document")
    articles = [a.strip() for a in raw_articles if a.strip()]

    if not articles:
        raise RuntimeError("未识别到任何新闻文档，请检查文件格式（是否包含 'End of Document' 标记）。")

    log_fn(f"✅ 共识别到 {len(articles)} 篇新闻，开始提取…")

    used_names = set()
    empty_body_count = 0
    by_source = {}          # 机构 -> 篇数
    unknown_examples = []   # 记录少量未知来源样例（方便补映射）

    for idx, article in enumerate(articles, start=1):
        title, sources, date_line = extract_metadata(article)
        body_text = extract_body(article)

        if not body_text:
            empty_body_count += 1

        fname = safe_filename(title, max_len=filename_max_len)
        filename = f"{fname}.txt"
        if filename in used_names:
            filename = f"{fname}_{idx:03d}.txt"
        used_names.add(filename)

        meta_lines = []
        if write_metadata:
            if sources:
                meta_lines.append("<SOURCE>: " + " | ".join(sources))
            if date_line:
                meta_lines.append("<DATE>: " + date_line)

        out_text = ""
        if meta_lines:
            out_text += "\n".join(meta_lines) + "\n\n----- BODY -----\n\n"
        out_text += body_text

        # 选择用于分类的来源（优先取第一行；没有就 Unknown）
        canonical_source = get_canonical_source(
            sources,
            canonical_map=canonical_map,
            noise_keywords=noise_keywords,
            enable_normalize=normalize_source
        )
        safe_source = safe_foldername(canonical_source)
        by_source[canonical_source] = by_source.get(canonical_source, 0) + 1

        # 收集少量 Unknown_Source 的样例（最多留 20 个，避免 report 太大）
        if canonical_source == "Unknown_Source" and len(unknown_examples) < 20:
            unknown_examples.append({
                "title": title,
                "raw_sources": sources[:8]  # 只取前几个，避免太长
            })

        if group_by_source:
            source_dir = out_dir / safe_source
            source_dir.mkdir(parents=True, exist_ok=True)
            target_path = source_dir / filename
        else:
            target_path = out_dir / filename

        target_path.write_text(out_text, encoding="utf-8")

        if idx % 10 == 0 or idx == len(articles):
            log_fn(f"进度：{idx}/{len(articles)}")

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_docx": str(docx_path),
        "output_dir": str(out_dir),
        "options": {
            "write_metadata": bool(write_metadata),
            "group_by_source": bool(group_by_source),
            "normalize_source": bool(normalize_source),
            "filename_max_len": int(filename_max_len),
        },
        "stats": {
            "total_articles": len(articles),
            "empty_body_count": empty_body_count,
            "sources_total": len(by_source),
            "unknown_source_count": by_source.get("Unknown_Source", 0),
        },
        "by_source_count": dict(sorted(by_source.items(), key=lambda x: (-x[1], x[0]))),
        "unknown_examples": unknown_examples,
        "rules": {
            "canonical_map_size": len(canonical_map or {}),
            "noise_keywords_size": len(noise_keywords or []),
        }
    }

    return len(articles), empty_body_count, report

def write_report_json(out_dir: Path, report: dict) -> Path:
    """
    写入带时间戳的处理报告：
    report-YYYY-MM-DD-HHMMSS.json
    """
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    filename = f"report-{ts}.json"

    report_path = out_dir / filename
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report_path
