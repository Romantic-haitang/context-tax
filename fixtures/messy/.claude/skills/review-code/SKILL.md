---
name: review-code
description: Review code changes or a diff for correctness, security, and maintainability. Produces line-level comments grouped by severity.
version: 0.4.0
---

# Review code

读 diff，找问题，分级，输出。

## 检查项
- 边界条件
- 错误路径
- 安全：注入、越权、密钥
- 可维护性

输出格式：每条一个 severity + 文件行号 + 一句话说明。
