import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OCR_DEPS = ROOT / ".ocr_deps"
if OCR_DEPS.exists():
    sys.path.insert(0, str(OCR_DEPS))

import numpy as np
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR


SCAN_PDFS = [
    ROOT / "文献" / "语料库文献" / "Corpus, Concordance, Colloc_ (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    ROOT / "文献" / "语料库文献" / "Corups Concordance Collocat_ (z-library.sk, 1lib.sk, z-lib.sk).pdf",
    ROOT / "文献" / "语料库文献" / "Using Corpora in Discourse_ (z-library.sk, 1lib.sk, z-lib.sk).pdf",
]


def safe_stem(path: Path) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", path.stem, flags=re.UNICODE)
    return stem.strip("._")[:120] or "ocr_output"


def ocr_pdf(pdf_path: Path, out_dir: Path, scale: float) -> dict:
    pdf = pdfium.PdfDocument(str(pdf_path))
    ocr = RapidOCR()
    out_path = out_dir / f"{safe_stem(pdf_path)}.txt"

    page_count = len(pdf)
    total_blocks = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# OCR text for: {pdf_path}\n")
        f.write(f"# Pages: {page_count}\n\n")
        for i in range(page_count):
            page = pdf[i]
            bitmap = page.render(scale=scale).to_pil()
            img = np.array(bitmap)
            result, _ = ocr(img)
            lines = [item[1].strip() for item in (result or []) if len(item) >= 2 and item[1].strip()]
            total_blocks += len(lines)

            f.write(f"\n\n===== Page {i + 1} / {page_count} =====\n")
            f.write("\n".join(lines))
            f.write("\n")
            print(f"[{pdf_path.name}] page {i + 1}/{page_count}: {len(lines)} lines", flush=True)

    return {
        "source_pdf": str(pdf_path),
        "output_txt": str(out_path),
        "pages": page_count,
        "ocr_lines": total_blocks,
        "scale": scale,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR scanned literature PDFs into UTF-8 text files.")
    parser.add_argument("--out", default=str(ROOT / "文献" / "OCR文本"), help="Output directory")
    parser.add_argument("--scale", type=float, default=2.0, help="PDF render scale; 2.0 is about 144 DPI")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for pdf_path in SCAN_PDFS:
        if not pdf_path.exists():
            print(f"missing: {pdf_path}", flush=True)
            continue
        records.append(ocr_pdf(pdf_path, out_dir, args.scale))

    manifest = out_dir / "manifest.json"
    manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote manifest: {manifest}", flush=True)


if __name__ == "__main__":
    main()
