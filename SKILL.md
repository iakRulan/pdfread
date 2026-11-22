---
name: pdfread
description: "Parse a scientific PDF into a citable structure: page-ordered text blocks with bbox and reading-order index, two-column de-mixing, heading/abstract/caption/formula/table/reference classification, table extraction with rows and columns, verbatim formula and special-character preservation, and explicit OCR flags for low-text pages. Trigger on: '文献阅读', 'PDF 解析', '提取全文', '表格解析', '双栏', '公式提取', 'pdf parsing', 'extract text from PDF', 'parse this paper', 'reading order'. Not for: translating, summarising, figure drawing, or explaining the science."
---

# pdfread — Citable PDF Parsing with Correct Reading Order

> **脚本路径**：本技能安装于 `/skills/weekly-skill/`，脚本绝对路径为 `/skills/weekly-skill/scripts/`（工作目录是 `/app/work`，不要用相对路径）。

Turn a PDF into a structure you can quote: every block has a page, a bbox and a reading-order index, two-column layouts are de-mixed, tables come out as rows/columns, and formulas/special characters stay verbatim. The failure mode this skill exists to prevent: a "full text" that is really a jumbled dump — columns interleaved, headers and footers mixed into the body, tables flattened, formulas mangled, and no way to point back at the source.

**Method in one line:** extract blocks → cluster by x to detect columns → order by (page, column, y) → classify each block → pull tables with `find_tables` → flag low-text pages for OCR → emit `parsed.json` + `fulltext.txt` + a verification verdict.

## When to use

- Input: a PDF (from the case) and optionally the case's questions.
- Output: under `/app/output` — `parsed.json`, `fulltext.txt`, `provenance.json`, `parse_check.json`, `result.json`.
- Works on born-digital PDFs; scanned/low-text pages are flagged rather than guessed.

## Pipeline (run in order)

### Phase 1 — Parse

```bash
python3 /skills/weekly-skill/scripts/parse_pdf.py --pdf <paper.pdf> --out /app/work [--ocr]
```

Per page:
- `page.get_text("dict")` blocks with bbox and font size;
- **column detection**: body blocks split at `0.45 × page_width`; if both sides have ≥4 blocks the page is two-column;
- **ordering**: `(page, column, y, x)` so text never interleaves across columns;
- **classification**: `title` (first-page large text), `heading` (numbered/short bold-ish), `abstract`, `caption` (`Fig./Table/Eq. N`), `formula` (math symbols), `header_footer` (top/bottom 60 pt), `reference` (`[n]` / numbered), `body`;
- **tables**: PyMuPDF `find_tables()` → `rows`, `cols`, and the full cell matrix;
- **verbatim**: no rewriting of formulas, subscripts/superscripts or Greek letters;
- **low-text pages** (few blocks and no text) are recorded in `low_text_pages` and need `--ocr`.

### Phase 2 — Verify the parse

```bash
python3 /skills/weekly-skill/scripts/verify_parse.py --case /input/case.json --work /app/work
```

Checks: every page present; every block traceable (page + bbox + order + non-empty text); reading order monotonic within each page; headings/captions/tables counted; low-text pages flagged. Writes `parse_check.json`; exits non-zero on failure.

### Phase 3 — Answer from the structure

```bash
python3 /skills/weekly-skill/scripts/report.py --case /input/case.json --work /app/work
```

For each case question, locates candidate blocks and records `block_id` + `page` + `type` + quote. **The model must read the full text and answer precisely**, replacing the naive term-match list with a grounded answer; every answer must cite at least one block id.

Copy deliverables:

```bash
mkdir -p /app/output
cp /app/work/parsed.json /app/work/fulltext.txt /app/work/provenance.json \
   /app/work/parse_check.json /app/work/result.json /app/output/
```

## Rules that must hold

1. **Reading order is fixed, not assumed.** Two-column pages are ordered column by column; a paragraph is never spliced across columns.
2. **Every block is traceable.** `page` + `bbox` + `order` on each block; an answer without a location is not an answer.
3. **Headers/footers are separated** and marked `repeated` when they recur across pages.
4. **Tables keep their cells.** Row/column structure is preserved, not flattened into prose.
5. **Formulas stay verbatim.** Special characters and sub/superscripts are not "corrected".
6. **Unreadable is flagged, not guessed.** Low-text pages go to OCR; OCR failures are reported.

## Exception handling

| Situation | Behaviour |
|-|-|
| PDF missing | error verdict, exit 1 |
| Scanned page, no text | `low_text_pages`, needs `--ocr` |
| No tables found | `tables: []` (honest, not a failure) |
| Single-column page | `columns: []`, normal ordering |
| PyMuPDF missing | clear error; no partial dump |

## Self-check

```bash
python3 /skills/weekly-skill/scripts/verify_parse.py --case /input/case.json --work /app/work
python3 -c "import json;d=json.load(open('/app/work/parsed.json'));print(d['stats']);print('low_text:', d['low_text_pages'])"
```

`valid: true` is required; a low-text page without `--ocr` is reported in `uncertainty`.


## 附录：脚本源码（自包含回退）

如果 `/skills/weekly-skill/scripts/` 下的脚本不存在（技能安装时未带上脚本），把下面每一段源码写到 `/app/work/` 下的对应文件（保持相对路径），再按上方命令运行。所有脚本均为纯文本，可直接落盘。

### scripts/parse_pdf.py

```python
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
```

### scripts/report.py

```python
#!/usr/bin/env python3
"""report — write result.json for a PDF parsing run.

Usage:
    python3 report.py --case /input/case.json --work /app/work
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)

    work = Path(args.work)
    data = load(work / "parsed.json")
    chk = load(work / "parse_check.json") if (work / "parse_check.json").exists() else {"valid": False, "issues": ["verify_parse not run"]}
    case = load(Path(args.case)) if Path(args.case).is_file() else {}
    questions = case.get("questions") or case.get("queries") or []

    answers = []
    blob = {b["id"]: b for b in data.get("blocks", [])}
    for q in questions:
        text = q if isinstance(q, str) else (q.get("q") or q.get("question") or "")
        terms = [t for t in text.lower().split() if len(t) > 3]
        hits = [b for b in data.get("blocks", []) if any(t in b["text"].lower() for t in terms)]
        hits.sort(key=lambda b: b.get("order", 0))
        answers.append({
            "question": text,
            "answered": bool(hits),
            "evidence": [
                {"block_id": b["id"], "page": b["page"], "type": b["type"], "quote": b["text"][:300]}
                for b in hits[:5]
            ],
            "note": None if hits else "材料中没有可定位的段落",
        })

    result = {
        "case_id": case.get("case_id") or case.get("id") or Path(args.case).stem,
        "task": "pdf-document-parsing",
        "status": "complete" if data.get("blocks") else "partial",
        "deliverables": {
            "parsed_structure": "parsed.json",
            "full_text": "fulltext.txt",
            "provenance": "provenance.json",
            "parse_check": "parse_check.json",
        },
        "counts": data.get("stats", {}),
        "low_text_pages": data.get("low_text_pages", []),
        "answers": answers,
        "validation": chk,
        "uncertainty": [
            "公式与特殊字符按结构元素识别，不解释其科学含义；",
            "扫描/低文本页面需 OCR，未启用时相应内容不可用；",
        ] + ([f"低文本页面需 OCR：{data.get('low_text_pages')}"] if data.get("low_text_pages") else []),
        "sources": [data.get("source")],
        "changes": [
            {"step": "parse", "detail": json.dumps(data.get("stats", {}), ensure_ascii=False)},
            {"step": "verify", "detail": f"valid={chk.get('valid')}"},
        ],
    }
    (work / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: status={result['status']} valid={chk.get('valid')} answers={len(answers)}")
    return result


if __name__ == "__main__":
    main()
```

### scripts/verify_parse.py

```python
#!/usr/bin/env python3
"""verify_parse — check a PDF parse for coverage, structure and traceability.

Usage:
    python3 verify_parse.py --case /input/case.json --work /app/work

Checks:
  1. every page in the source has a page_info entry;
  2. every block has page + bbox + order and non-empty text;
  3. the reading order is monotonic within each page (no column mixing);
  4. headings/captions/tables/references counts are non-zero when expected;
  5. low-text pages are flagged (need OCR) rather than silently empty.

Prints a JSON verdict; exits non-zero on hard failures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)

    work = Path(args.work)
    issues = []
    checks = {}

    p = work / "parsed.json"
    if not p.exists():
        print(json.dumps({"valid": False, "issues": ["missing parsed.json"]}, ensure_ascii=False))
        return 1
    data = load(p)

    pages = data.get("pages", 0)
    info = {pg["page"]: pg for pg in data.get("page_info", [])}
    checks["pages"] = pages
    missing_pages = [i for i in range(1, pages + 1) if i not in info]
    checks["missing_pages"] = len(missing_pages)
    if missing_pages:
        issues.append(f"缺少页面信息：{missing_pages[:5]}")

    blocks = data.get("blocks", [])
    bad_blocks = [b for b in blocks if not b.get("text") or "page" not in b or "bbox" not in b or "order" not in b]
    checks["blocks"] = len(blocks)
    checks["untraceable_blocks"] = len(bad_blocks)
    if bad_blocks:
        issues.append(f"{len(bad_blocks)} 个 block 缺 page/bbox/order 或无文本")

    # reading order monotonic within each page
    by_page = {}
    for b in blocks:
        by_page.setdefault(b["page"], []).append(b["order"])
    nonmono = [pg for pg, orders in by_page.items() if orders != sorted(orders)]
    checks["pages_with_nonmonotonic_order"] = len(nonmono)
    if nonmono:
        issues.append(f"阅读顺序在页面内非单调：{nonmono[:5]}")

    st = data.get("stats", {})
    checks["stats"] = st
    if st.get("blocks", 0) == 0:
        issues.append("没有解析到任何 block")
    if st.get("headings", 0) == 0:
        issues.append("未识别到任何标题（章节层级缺失）")

    low = data.get("low_text_pages", [])
    checks["low_text_pages"] = low
    if low and not data.get("ocr_requested"):
        issues.append(f"低文本页面 {low} 需 OCR，但未启用 --ocr")

    verdict = {"valid": not issues, "checks": checks, "issues": issues,
               "case_id": data.get("source")}
    (work / "parse_check.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
```
