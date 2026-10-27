---
name: sdk
description: Guide users building apps, scripts, CI pipelines, or automations on top of the Codex SDK. Covers installing, wiring streaming responses, handling cancellation, resuming sessions, runtime errors, MCP servers, and migration between SDK versions.
version: 1.0.0
---

# Codex SDK

## 安装

1. `npm i @codex/sdk` 或 `pip install codex-sdk`。
2. 从环境变量读 API key，不要写进代码。

## 流式响应

1. 用 `client.stream()` 拿增量，不要等整段返回再处理。
2. 处理取消：捕获 `AbortError`，把已经收到的部分落盘。
3. 断线重连用 session id 续接，不要从头再跑一遍。

## 常见错误

- `CursorAgentError`：多半是 runtime 版本不匹配。
- 429：指数退避，尊重 `Retry-After`。
- 工具调用返回空：检查 MCP server 是否还在跑。

## 迁移

v0 的 `run()` 改成了 `client.run()`，参数从位置参数换成了对象，其余兼容。
