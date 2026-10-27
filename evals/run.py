#!/usr/bin/env python3
"""Deterministic evals. No model, no network, no excuses.

    python3 evals/run.py [-v]

Exit code 0 means every assertion in cases.json held.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from context_tax.analyze import analyze  # noqa: E402
from context_tax.discover import collect  # noqa: E402

GREEN, RED, DIM, RESET = "\x1b[32m", "\x1b[31m", "\x1b[2m", "\x1b[0m"


def check(case: dict, verbose: bool) -> list[str]:
    exp = case["expect"]
    inv = collect(ROOT / case["path"])
    bill = analyze(inv)
    ids = {f.id for f in bill.findings}
    failures: list[str] = []

    def fail(msg: str) -> None:
        failures.append(f"{case['name']}: {msg}")

    lo, hi = exp.get("tax_rate_between", [0.0, 1.0])
    if not (lo <= bill.tax_rate <= hi):
        fail(f"税负率 {bill.tax_rate:.3f} 不在 [{lo}, {hi}] 区间")

    if "grade" in exp and bill.grade != exp["grade"]:
        fail(f"等级是 {bill.grade}，期望 {exp['grade']}")

    for need in exp.get("must_have_findings", []):
        if need not in ids:
            fail(f"缺少 {need}")
    for banned in exp.get("must_not_have", []):
        if banned in ids:
            fail(f"不该出现 {banned}")

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
    for case in spec["cases"]:
        all_failures += check(case, verbose)

    print()
    if all_failures:
        for f in all_failures:
            print(f"  {RED}FAIL{RESET}  {f}")
        print(f"\n  {RED}{len(all_failures)} 项断言失败{RESET}\n")
        return 1
    print(f"  {GREEN}PASS{RESET}  {len(spec['cases'])} 个 fixture，全部断言通过\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
