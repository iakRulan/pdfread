# 自测记录（示例，非平台正式案例）

- 日期：2026-11-19
- 输入：arXiv:1706.03762（Attention Is All You Need）PDF，15 页
- 命令：

```bash
python3 scripts/parse_pdf.py --pdf paper.pdf --out .
python3 scripts/verify_parse.py --case case.json --work .
python3 scripts/report.py --case case.json --work .
```

## 结果摘要

| 指标 | 值 |
|-|-|
| 页数 | 15 |
| blocks | 485 |
| 标题 / 题注 / 公式 | 7 / 10 / 7 |
| 表格 | 5（含行列矩阵） |
| 参考文献 | 40 |
| 页眉页脚 | 15（跨页重复已标记） |
| 校验 | `valid: true`，0 issues |
| 低文本页 | 无 |

## 观察到的真实问题与修复（示例价值）

1. **双栏串栏**：初版直接按 y 排序会把左右栏拼成一句。修复：先按 `x0` 分栏，再按 (page, column, y, x) 排序。
2. **页眉页脚混入正文**：修复：按页面上下 60pt 判定并单独分类，全文输出时排除。
3. **公式被"清理"**：修复：不重写文本，公式符号保留原样，并按数学符号分类。

> 本文件为**技能自测示例**，不冒充平台正式案例结果。
