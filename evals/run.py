#!/usr/bin/env python3
"""Deterministic evals. No model, no network, no excuses.

    python3 evals/run.py [-v]

Exit code 0 means every assertion in cases.json held.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from context_tax.analyze import analyze  # noqa: E402
from context_tax.discover import _age_days, collect  # noqa: E402

GREEN, RED, DIM, RESET = "\x1b[32m", "\x1b[31m", "\x1b[2m", "\x1b[0m"
DAY = 86400


def units() -> tuple[list[str], int]:
    """不依赖 fixture 文件的断言。

    这些数字 fixture 造不出来——mtime 在 git 里不保存，clone 下来全是 checkout
    那一刻。所以凡是关于「时间」的逻辑，都在这里用临时文件直接测。
    """
    failures: list[str] = []
    n = 0
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "SKILL.md"
        f.write_text("---\nname: x\n---\nbody\n", encoding="utf-8")

        def age(set_to: float, fm: dict | None = None) -> int:
            nonlocal n
            n += 1
            os.utime(f, (set_to, set_to))
            return _age_days(f, fm)

        # 插件缓存里真实见过的 mtime=0。照字面算会变成 20753 天。
        if age(0.0) != 0:
            failures.append(f"mtime=0 应该当作未知（返回 0），实际 {age(0.0)}")
        if age(1.0) != 0:
            failures.append("mtime=1 应该当作未知（返回 0）")

        now = time.time()
        got = age(now - 400 * DAY)
        if not (399 <= got <= 401):
            failures.append(f"400 天前的文件算出了 {got} 天")

        # frontmatter 的日期优先于 mtime：clone 之后 mtime 是今天，但作者说了实话
        got = age(now - 10 * DAY, {"updated": "2025-01-01"})
        if got < 200:
            failures.append(f"frontmatter 的 updated 没盖过 mtime（算出 {got} 天）")

        # 未来的日期不能算出负数
        if age(now + 90 * DAY) != 0:
            failures.append("未来时间应该夹到 0")

    return failures, n


def check(case: dict, verbose: bool) -> list[str]:
    exp = case["expect"]
    kwargs: dict = {}
    if case.get("as_home"):
        # 模拟 `context_tax <home> --global`：root 就是 home，同一个 skills 目录
        # 会被"项目"和"全局"各扫一遍，必须去重。
        kwargs = {"include_global": True, "home": ROOT / case["path"]}
    inv = collect(ROOT / case["path"], **kwargs)
    bill = analyze(inv)
    ids = {f.id for f in bill.findings}
    titles = [f.title for f in bill.findings]
    failures: list[str] = []

    def fail(msg: str) -> None:
        failures.append(f"{case['name']}: {msg}")

    lo, hi = exp.get("tax_rate_between", [0.0, 1.0])
    if not (lo <= bill.tax_rate <= hi):
        fail(f"税负率 {bill.tax_rate:.3f} 不在 [{lo}, {hi}] 区间")

    if "grade" in exp and bill.grade != exp["grade"]:
        fail(f"等级是 {bill.grade}，期望 {exp['grade']}")

    if "skill_count" in exp and len(inv.skills) != exp["skill_count"]:
        fail(f"去重后有 {len(inv.skills)} 个技能，期望 {exp['skill_count']}")

    if "dup_group_count" in exp and len(inv.duplicate_groups) != exp["dup_group_count"]:
        fail(f"有 {len(inv.duplicate_groups)} 组重复，期望 {exp['dup_group_count']}")

    for need in exp.get("must_have_findings", []):
        if need not in ids:
            fail(f"缺少 {need}")
    for banned in exp.get("must_not_have", []):
        if banned in ids:
            fail(f"不该出现 {banned}")
    for bad in exp.get("must_not_contain_title", []):
        if any(bad in t for t in titles):
            fail(f"标题里不该出现「{bad}」——这是自己跟自己比")

    if "min_findings" in exp and len(bill.findings) < exp["min_findings"]:
        fail(f"只有 {len(bill.findings)} 条问题，至少要有 {exp['min_findings']}")
    if "max_findings" in exp and len(bill.findings) > exp["max_findings"]:
        fail(f"有 {len(bill.findings)} 条问题，最多允许 {exp['max_findings']}")
    if "min_recoverable_pct" in exp and bill.recoverable_pct < exp["min_recoverable_pct"]:
        fail(f"可回收比例 {bill.recoverable_pct:.0%} 低于 {exp['min_recoverable_pct']:.0%}")

    if verbose:
        print(f"  {DIM}{case['name']}: 税负率 {bill.tax_rate:.1%}, "
              f"{len(bill.findings)} 条问题, 可退 {bill.recoverable_pct:.0%}{RESET}")
    return failures


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass
    verbose = "-v" in sys.argv
    spec = json.loads((ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))

    all_failures: list[str] = []
    unit_failures, unit_n = units()
    all_failures += unit_failures
    if verbose:
        print(f"  {DIM}units: {unit_n} 项时间断言{RESET}")
    for case in spec["cases"]:
        all_failures += check(case, verbose)

    print()
    if all_failures:
        for f in all_failures:
            print(f"  {RED}FAIL{RESET}  {f}")
        print(f"\n  {RED}{len(all_failures)} 项断言失败{RESET}\n")
        return 1
    print(f"  {GREEN}PASS{RESET}  {len(spec['cases'])} 个 fixture + 时间断言，全部通过\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
