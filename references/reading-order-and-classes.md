# 阅读顺序与区块分类

## 双栏检测

1. 取页面内 `body` / `heading` / `abstract` 区块的 `x0`。
2. 以 `0.45 × page_width` 为界分成左/右两组。
3. 两侧各 ≥4 个区块 → 判定为双栏，记录 `columns: ["left","right"]`。

## 排序键

```
(page, column, y0, x0)
```

`column` 由 `x0 < 0.45 × page_width` 决定（单栏页面全部为 0）。这保证同一栏内自上而下、栏间不交错。

## 区块分类

| 类型 | 判据 |
|-|-|
| `title` | 首页、`y0 < 0.2 × page_height`、字号 ≥14；或字号 ≥15 且文本 <120 字符 |
| `heading` | 匹配编号标题（`1.` / `1.1 `）且字号 ≥11 |
| `abstract` | 文本以 `abstract` 开头 |
| `caption` | 匹配 `Fig(ure)?. / Table / Eq. N` |
| `formula` | 含数学符号（∀∃∈∑∫√∞≈≠≤≥±×÷∂∇、希腊字母）且 <400 字符 |
| `header_footer` | `y0 < 60` 或 `y1 > page_height − 60` |
| `reference` | 匹配 `[n]` 或 `n. 大写字母` |
| `body` | 其余 |

页眉页脚跨页重复时标记 `repeated: true`。

## 表格

`page.find_tables()` → 每个表：

```json
{
  "table_index": 0,
  "page": 9,
  "bbox": [x0,y0,x1,y1],
  "rows": 8,
  "cols": 3,
  "data": [["", "train...", "PPL BLEU..."], ...]
}
```

单元格空值写为 `""`。未检测到表格时 `tables: []`。

## 低文本页

- 判据：区块数 <3 且页面文本为空。
- 处理：记入 `low_text_pages`；`--ocr` 可标记需要 OCR；未启用时在校验中提示。

## 校验

- 页面覆盖完整；
- 每 block 有 page / bbox / order 且非空；
- 页内 `order` 单调；
- 标题数为 0 时提示层级缺失；
- 低文本页未启用 OCR 时提示。
