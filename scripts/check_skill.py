#!/usr/bin/env python3
"""Check SKILL.md against the Agent Skills conventions we tell everyone else to follow.

Dogfooding: if our own SKILL.md can't pass, the tool has no business advising anyone.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DESC_MIN, DESC_MAX = 40, 1024
BODY_MAX_LINES = 500


def main() -> int:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    problems: list[str] = []

    if not text.startswith("---"):
        print("SKILL.md 没有 frontmatter")
        return 1
    block = text.split("---", 2)[1]
    body = text.split("---", 2)[2]
    fm: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()

    name = fm.get("name", "")
    desc = fm.get("description", "")

    if not NAME_RE.match(name):
        problems.append(f"name '{name}' 不是 kebab-case")
    if not desc:
        problems.append("description 缺失")
    elif not DESC_MIN <= len(desc) <= DESC_MAX:
        problems.append(f"description 长度 {len(desc)}，应在 {DESC_MIN}-{DESC_MAX} 之间")
    else:
        lowered = desc.lower()
        if "not for" not in lowered and "不用于" not in lowered:
            problems.append("description 缺少负向边界（'not for …'），会过度触发")

    body_lines = len(body.strip().splitlines())
    if body_lines > BODY_MAX_LINES:
        problems.append(f"正文 {body_lines} 行，超过 {BODY_MAX_LINES} 行应移到 references/")

    refs = re.findall(r"`(references/[^`]+)`", body)
    for r in refs:
        if not (ROOT / r).is_file():
            problems.append(f"正文引用了不存在的文件：{r}")

    if problems:
        for p in problems:
            print(f"FAIL  {p}")
        return 1
    print(f"PASS  SKILL.md（description {len(desc)} 字，正文 {body_lines} 行，"
          f"{len(refs)} 处 references 引用均存在）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
