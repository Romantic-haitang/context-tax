---
name: notify
description: Send a release notification to the team channel after a deploy finishes, including the commit summary, duration, and a health check link.
version: 1.0.0
---

# Notify

## 什么时候用

部署流水线跑完、需要通知人去看结果的时候。不用于日常闲聊播报。

## 步骤

1. `git log -1 --pretty=format:'%h %s'` 取本次部署对应的 commit。
2. 从 CI 环境变量 `DEPLOY_ENV` 判断是 staging 还是 production。
3. production 走 @here，staging 只发普通消息，别半夜叫醒人。
4. 贴三样东西：commit 摘要、耗时、健康检查链接。
5. 失败时额外附上最后 20 行日志，不要整份糊上去。

## 反模式

- 不要发「部署完成」四个字就完事，没人知道部署了什么。
- 不要在消息里 @ 全组，除非 production 挂了。
- 不要把整份 CI 日志贴进频道，给链接。

## 输出模板

```
🚀 production  a1b2c3d  fix: 订单金额四舍五入
耗时 4m12s · 健康检查正常
```

> 2025-11 补：生产环境 @here 改成了 @channel（Slack 迁移后）。
