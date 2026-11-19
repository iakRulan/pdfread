# pdfread — 文献文档解析（科研阅读）Skill

把 PDF 解析成**可引用的结构**：每个 block 带页码、bbox 与阅读顺序索引，双栏不串栏，表格保持行列，公式与特殊字符逐字保留，扫描页如实标记。

## 解决什么问题

普通解析的常见失败：正文、题注、脚注、参考文献混在一起；双栏串栏、跨页错行；合并单元格与多层表头被拍平；公式上下标与希腊字母失真；读不出的部分靠猜补齐。

## 安装与依赖

- Python 3.9+
- PyMuPDF（`fitz`），用于文本块、阅读顺序与 `find_tables`
- 无需联网；OCR 需额外工具（缺失时如实标记）

```
pdfread/
├── SKILL.md
├── README.md
├── GITHUB_URL.txt
├── references/
│   ├── reading-order-and-classes.md
│   └── output-schema.md
├── examples/
│   ├── case.example.json
│   └── selftest-summary.md
└── scripts/
    ├── parse_pdf.py
    ├── verify_parse.py
    └── report.py
```

## 用法（最小示例）

```bash
python3 scripts/parse_pdf.py --pdf paper.pdf --out /app/work
python3 scripts/verify_parse.py --case /input/case.json --work /app/work
python3 scripts/report.py --case /input/case.json --work /app/work
```

输入示例：

```json
{
  "case_id": "demo",
  "pdf": "paper.pdf",
  "questions": ["What BLEU score did the model achieve?"]
}
```

> 以上为**示意示例**，不是正式案例结果。

## 输出

| 文件 | 内容 |
|-|-|
| `parsed.json` | 页面信息、blocks（page/bbox/order/type/text）、tables、stats |
| `fulltext.txt` | 按阅读顺序排列的全文（去除页眉页脚） |
| `provenance.json` | 解析覆盖与低文本页标记 |
| `parse_check.json` | 校验判决 |
| `result.json` | `case_id` / `status` / counts / answers / uncertainty |

## block 类型

`title` / `heading` / `abstract` / `caption` / `formula` / `table` / `header_footer` / `reference` / `body`

## 关键设计

- **阅读顺序**：按 (page, column, y, x) 排序，双栏逐列输出。
- **可追溯**：每 block 带 page + bbox + order。
- **表格结构**：行列与单元格归属保留。
- **符号保真**：公式、上下标、希腊字母逐字保留。
- **读不出就标记**：低文本页进 `low_text_pages`，需 OCR。

## 局限

- 不解释公式与图表的科学含义；
- 不翻译、不摘要；
- OCR 需预装工具，缺失时对应页面不可用。

## 许可与版本

- 版本：pdfread 1.0.0
- 依赖：PyMuPDF。
