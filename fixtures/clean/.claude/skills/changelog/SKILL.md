---
name: changelog
description: Generate or update CHANGELOG.md from git history since the last tag. Use when the user asks for a changelog, release notes, or a version bump summary. Not for writing commit messages.
version: 1.0.0
---

# Changelog

1. `git describe --tags --abbrev=0` 拿到上一个 tag。
2. `git log <tag>..HEAD --pretty=format:'%s'` 取提交。
3. 按 feat / fix / perf / docs 分组，删掉 chore 和 merge。
4. 只写用户能感知的变化，不写重构细节。

输出格式和禁用句式见 references/style.md。
