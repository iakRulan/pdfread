# 输出字段字典

## `parsed.json`

| 字段 | 说明 |
|-|-|
| `source` | PDF 路径 |
| `pages` | 页数 |
| `page_info[]` | `page` / `width` / `height` / `blocks` / `columns` / `low_text` |
| `blocks[]` | `id` / `page` / `bbox` / `type` / `text` / `size` / `order`（页眉页脚另有 `repeated`） |
| `tables[]` | `table_index` / `page` / `bbox` / `rows` / `cols` / `data` |
| `stats` | `blocks` / `headings` / `captions` / `formulas` / `tables` / `references` / `header_footer` |
| `low_text_pages[]` | 需要 OCR 的页面 |
| `ocr_requested` | 是否声明启用 OCR |
| `script_version` | 版本 |

## `fulltext.txt`

按 `order` 排列的全文，排除 `header_footer`。

## `provenance.json`

`case_file` / `pages` / `blocks` / `note` / `low_text_pages`。

## `parse_check.json`

`{valid, checks, issues[], case_id}`。checks 含：`pages`、`missing_pages`、`blocks`、`untraceable_blocks`、`pages_with_nonmonotonic_order`、`stats`、`low_text_pages`。

## `result.json`

| 字段 | 说明 |
|-|-|
| `case_id` / `task` / `status` | `pdf-document-parsing` |
| `deliverables` | parsed / fulltext / provenance / parse_check |
| `counts` | 解析统计 |
| `low_text_pages` | 需 OCR 的页面 |
| `answers[]` | `question` / `answered` / `evidence[]` / `note` |
| `validation` | 校验判决 |
| `uncertainty` | 公式不解释、OCR 限制、低文本页 |
