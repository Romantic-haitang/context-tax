---
name: report
description: Build a weekly report from the closed issues and merged pull requests, grouped by label and owner, ending with next week's plan.
version: 1.0.0
---

# Weekly report

## 什么时候用

每周一早上要给别人一份「上周干了什么」的时候。不用于季度总结。

## 步骤

1. 拉取本周关闭的 issue 和已合并的 PR。
2. 按 label 分组：feature / bug / chore。
3. 按 owner 汇总，一个人一段，别按时间流水账。
4. chore 只留一行总计，不要把依赖升级列成十条。
5. 结尾写「下周计划」，三行以内。

## 反模式

- 不要罗列 commit 标题，那是给机器看的。
- 不要写「优化了一些体验」这种谁都能说的话。
