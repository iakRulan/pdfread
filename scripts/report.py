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
