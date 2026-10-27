---
name: automate
description: Use this skill to create Codex Automations.
version: 1.0.0
---

# Automate

## 步骤

1. 打开 Codex 的 Automations 面板。
2. 填 cron 表达式，时区固定 UTC。
3. 指明要跑的 prompt 和工作目录。
4. 先手动触发一次看日志，再开定时。

## 反模式

- 不要设成每分钟，那是给监控用的频率。
- 不要在自动任务里申请需要人确认的权限。
- 失败重试最多三次，别无限重试把 token 烧光。

## 排查

任务没跑起来先看三点：cron 时区、工作目录是否存在、prompt 里有没有引用不存在的文件。
