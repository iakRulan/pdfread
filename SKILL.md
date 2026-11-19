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