---
name: bundle
description: Use when the user asks for the team's report toolkit as a whole, e.g. building several of its charts at once or checking which of its sub-skills applies to a request.
version: 1.0.0
---

# Report toolkit

## 什么时候用

一次要出好几张图、或者不确定该用哪个子技能的时候。只出一张图就直接用子技能。

## 步骤

1. 先判断需要哪几类图：趋势、构成、分布。
2. 分别调用对应的子技能，不要在一个 prompt 里让模型自己拼。
3. 拼装时统一配色和字号，别每张图各写一套。

## 反模式

- 不要为了凑数把同一份数据画两遍。
- 不要在子技能里再引用回本技能，绕成环。
