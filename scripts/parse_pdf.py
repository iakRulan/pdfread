#!/usr/bin/env python3
"""parse_pdf — structure a scientific PDF into citable, correctly ordered blocks.

Usage:
    python3 parse_pdf.py --pdf PATH --out DIR [--ocr]

What it does:
  * extracts text blocks with page + bbox, and assigns a reading-order index;
  * detects two-column layouts by x-clustering and orders within each column;
  * classifies blocks: title / heading / abstract / caption / table / formula /
    header / footer / reference / body;
  * extracts tables (PyMuPDF find_tables) with row/column structure;
  * keeps formulas and special characters verbatim (no rewriting);
  * writes parsed.json + fulltext.txt + provenance.json.

Every block carries `page`, `block_id`, `bbox` and `column`, so any downstream
answer can point back to a location. Low-text pages are flagged for OCR instead
of being guessed.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

try:
    import fitz
except Exception:  # pragma: no cover
    fitz = None

VERSION = "1.0.0"

HEADING_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?[A-Z][A-Za-z0-9 ,\-:()&/]{2,80}$")
NUM_HEAD_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(\S.*)$")
CAPTION_RE = re.compile(r"^\s*(Fig(?:ure)?\.?|Table|Tab\.|Equation|Eq\.?)\s*(\d+)", re.IGNORECASE)
MATH_RE = re.compile(r"[∀∃∈∉∑∏∫√∞≈≠≤≥±×÷∂∇α-ωΑ-Ω]")
REF_RE = re.compile(r"^\s*(\[\d+\]|\d+\.\s+[A-Z])")


def classify(text, span_size, page_h, y0, y1, is_first_page):
    t = text.strip()
    if not t:
        return "empty"
    if CAPTION_RE.match(t):
        return "caption"
    if MATH_RE.search(t) and len(t) < 400:
        return "formula"
    if is_first_page and y0 < page_h * 0.2 and span_size >= 14:
        return "title"
    if y0 < 60 or y1 > page_h - 60:
        return "header_footer"
    if NUM_HEAD_RE.match(t) and span_size >= 11:
        return "heading"
    if t.lower().startswith("abstract"):
        return "abstract"
    if REF_RE.match(t):
        return "reference"
    if span_size >= 15 and len(t) < 120:
        return "title"
    return "body"


def detect_columns(blocks, page_width):
    """Two-column detection by x0 clustering of body blocks."""
    body = [b for b in blocks if b["type"] in {"body", "heading", "abstract"}]
    if len(body) < 8:
        return {}
    left = [b for b in body if b["bbox"][0] < page_width * 0.45]
    right = [b for b in body if b["bbox"][0] >= page_width * 0.45]
    if len(left) >= 4 and len(right) >= 4:
        return {"left": 0, "right": 1}
    return {}


def order_blocks(blocks, columns):
    """Sort by page, then column (if two-column), then y, then x."""
    col_of = {}
    for b in blocks:
        x0 = b["bbox"][0]
        if "left" in columns and x0 < b["_page_width"] * 0.45:
            col_of[b["id"]] = 0
        elif "right" in columns:
            col_of[b["id"]] = 1
        else:
            col_of[b["id"]] = 0
    return sorted(blocks, key=lambda b: (b["page"], col_of[b["id"]], b["bbox"][1], b["bbox"][0]))


def extract_tables(page, page_no, out_id):
    tables = []
    try:
        found = page.find_tables()
    except Exception:
        found = None
    if not found:
        return tables
    for ti, tab in enumerate(found.tables):
        try:
            data = tab.extract()
        except Exception:
            data = None
        if not data:
            continue
        tables.append({
            "table_index": ti,
            "page": page_no,
            "bbox": [round(v, 1) for v in tab.bbox],
            "rows": len(data),
            "cols": max((len(r) for r in data), default=0),
            "data": [[("" if c is None else str(c)) for c in row] for row in data],
        })
    return tables


def parse(pdf_path: Path, ocr=False):
    if fitz is None:
        raise RuntimeError("PyMuPDF is required")
    doc = fitz.open(str(pdf_path))
    pages_out = []
    blocks = []
    tables = []
    bid = 0
    low_text_pages = []

    for pno in range(doc.page_count):
        page = doc[pno]
        page_w, page_h = page.rect.width, page.rect.height
        raw = page.get_text("dict")
        page_blocks = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            text_parts = []
            sizes = []
            for line in block.get("lines", []):
                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                if line_text.strip():
                    text_parts.append(line_text)
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        sizes.append(span.get("size", 0))
            text = " ".join(text_parts).strip()
            if not text:
                continue
            x0, y0, x1, y1 = block["bbox"]
            size = round(sum(sizes) / len(sizes), 1) if sizes else 0
            btype = classify(text, size, page_h, y0, y1, pno == 0)
            b = {
                "id": bid,
                "page": pno + 1,
                "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                "type": btype,
                "text": text,
                "size": size,
                "_page_width": page_w,
            }
            page_blocks.append(b)
            blocks.append(b)
            bid += 1

        if len(page_blocks) < 3 and page.get_text("text").strip() == "":
            low_text_pages.append(pno + 1)

        columns = detect_columns(page_blocks, page_w)
        pages_out.append({
            "page": pno + 1,
            "width": round(page_w, 1),
            "height": round(page_h, 1),
            "blocks": len(page_blocks),
            "columns": list(columns.keys()),
            "low_text": (pno + 1) in low_text_pages,
        })
        tables.extend(extract_tables(page, pno + 1, bid))

    ordered = order_blocks(blocks, {"left": 0, "right": 1} if any(p["columns"] for p in pages_out) else {})
    for i, b in enumerate(ordered):
        b.pop("_page_width", None)
        b["order"] = i

    # de-duplicate repeated headers/footers across pages
    hf = [b for b in ordered if b["type"] == "header_footer"]
    repeated = Counter(b["text"] for b in hf)
    for b in hf:
        b["repeated"] = repeated[b["text"]] > 1

    fulltext = "\n\n".join(b["text"] for b in ordered if b["type"] not in {"header_footer"})
    return {
        "source": str(pdf_path),
        "pages": doc.page_count,
        "page_info": pages_out,
        "blocks": ordered,
        "tables": tables,
        "stats": {
            "blocks": len(ordered),
            "headings": sum(1 for b in ordered if b["type"] == "heading"),
            "captions": sum(1 for b in ordered if b["type"] == "caption"),
            "formulas": sum(1 for b in ordered if b["type"] == "formula"),
            "tables": len(tables),
            "references": sum(1 for b in ordered if b["type"] == "reference"),
            "header_footer": len(hf),
        },
        "low_text_pages": low_text_pages,
        "ocr_requested": ocr,
        "script_version": VERSION,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ocr", action="store_true")
    args = ap.parse_args(argv)

    pdf = Path(args.pdf)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not pdf.exists():
        print(json.dumps({"status": "error", "issues": [f"PDF not found: {pdf}"]}, ensure_ascii=False))
        return 1

    data = parse(pdf, ocr=args.ocr)
    (out / "parsed.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    full = "\n\n".join(b["text"] for b in data["blocks"] if b["type"] != "header_footer")
    (out / "fulltext.txt").write_text(full, encoding="utf-8")

    provenance = {
        "case_file": str(pdf),
        "pages": data["pages"],
        "blocks": data["stats"]["blocks"],
        "note": "每个 block 带 page + bbox + order，可回指原文位置。",
        "low_text_pages": data["low_text_pages"],
    }
    (out / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"parse_pdf: {data['pages']} pages, {data['stats']['blocks']} blocks, "
          f"{data['stats']['tables']} tables, {data['stats']['captions']} captions -> {out / 'parsed.json'}")
    return data


if __name__ == "__main__":
    main()
