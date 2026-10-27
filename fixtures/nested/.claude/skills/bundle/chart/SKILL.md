---
name: chart
description: Use when the user wants a single chart rendered from tabular data, specifying the mark type, axis fields, and where the output should be written.
version: 1.0.0
---

# Chart

## 什么时候用

用户明确要一张图，而且数据已经是表格形态。不用于生成整份报告。

## 步骤

1. 确认 mark 类型：line、bar、area、scatter。
2. 确认 x / y 字段和聚合方式。
3. 输出到指定路径，默认 `out/chart.html`。

## 反模式

- 不要在饼图里放超过六类数据。
- 不要省略单位。
