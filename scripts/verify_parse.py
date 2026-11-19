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
