---
name: code-review
description: Review a pull request or diff for correctness, security, and maintainability. Produces line-level comments grouped by severity, with a merge recommendation.
version: 1.2.0
---

# Code review

## 何时用
用户要求评审一个 PR、一个 diff、或者一段准备提交的改动时。

## 流程
1. 先读 PR 描述，确认这次改动想解决什么问题。描述为空就直接问。
2. 按文件顺序读 diff，不要跳读。
3. 对每个可疑点标注：`blocker` / `should-fix` / `nit`。
4. 只对 `blocker` 给出完整修复建议，其余给方向。
5. 最后给一句结论：可以合 / 改完再合 / 不建议合。

## 关注顺序
- 正确性：边界条件、错误路径、并发。
- 安全：注入、越权、密钥泄漏。
- 可维护性：命名、抽象层级、重复。
- 风格：交给格式化工具，不要在评审里争论。

## 反模式
- 不要把"我不喜欢这个写法"说成 blocker。
- 不要一次提 40 条 nit，人会麻木。
- 不要说"这里可能有性能问题"却不给依据。
