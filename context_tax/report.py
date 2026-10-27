"""Rendering: terminal bill, Markdown, JSON."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict

from .analyze import Bill, SEVERITY_LABEL

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"
GREEN = "\x1b[32m"
CYAN = "\x1b[36m"

WIDTH = 64

CJK_PUNCT = "、。，；：！？）】》」』…"


class Painter:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def __call__(self, code: str, text: str) -> str:
        if not self.enabled or not text:
            return text
        return f"{code}{text}{RESET}"


def dwidth(text: str) -> int:
    """Display width: CJK and fullwidth chars count as 2 columns."""
    return sum(2 if ord(ch) > 0x2E7F or ch in CJK_PUNCT else 1 for ch in text)


def pad(text: str, width: int) -> str:
    deficit = width - dwidth(text)
    return text + " " * max(0, deficit)


def _bar(ratio: float, width: int = 20) -> str:
    filled = max(0, min(width, int(round(ratio * width))))
    return "█" * filled + "·" * (width - filled)


def _grade_color(grade: str) -> str:
    return {"免税": GREEN, "轻度": GREEN, "中度": YELLOW}.get(grade, RED)


def _sev_color(sev: str) -> str:
    return {"critical": RED, "warn": YELLOW, "info": CYAN}.get(sev, CYAN)


def _rule(title: str = "") -> str:
    if not title:
        return "─" * WIDTH
    head = f"── {title} "
    return head + "─" * max(0, WIDTH - dwidth(head))


_CHUNK_RE = re.compile(r"(\s+)")


def _chunks(text: str) -> list[str]:
    chunks: list[str] = []
    for part in _CHUNK_RE.split(text):
        if not part:
            continue
        if part.isspace():
            chunks.append(part)
            continue
        buf = ""
        for ch in part:
            if ord(ch) > 0x2E7F:
                if buf:
                    chunks.append(buf)
                    buf = ""
                chunks.append(ch)
            else:
                buf += ch
        if buf:
            chunks.append(buf)
    return chunks


def wrap(text: str, width: int, indent: str = "      ") -> list[str]:
    """Width-aware wrap. Breaks at spaces and CJK boundaries, never mid-word."""
    lines: list[str] = []
    current = ""
    col = 0
    for chunk in _chunks(text):
        cw = dwidth(chunk)
        if chunk.isspace():
            if current:
                current += " "
                col += 1
            continue
        if col + cw > width and current:
            if col < 8:
                # 避免行首孤字，宁可轻微溢出
                current += chunk
                col += cw
                continue
            lines.append(indent + current.rstrip())
            current = ""
            col = 0
            if chunk in CJK_PUNCT:
                # 标点不该出现在行首，粘回上一行
                if lines:
                    lines[-1] += chunk
                    continue
        current += chunk
        col += cw
    if current.strip():
        lines.append(indent + current.rstrip())
    return lines


def render_text(bill: Bill, color: bool = True, verbose: bool = False) -> str:
    p = Painter(color)
    out: list[str] = []

    out.append("")
    out.append("  " + p(BOLD, "CONTEXT TAX") + p(DIM, "  ·  你的 agent 上下文税单"))
    out.append(p(DIM, "  " + "═" * WIDTH))
    out.append(p(DIM, "  扫描  ") + bill.root)
    out.append(
        p(DIM, f"  假设  {bill.requests:,} 次请求/月 · 输入 ${bill.price_in:g}/M · "
               f"缓存命中 {bill.cache_hit:.0%}")
    )
    out.append("")

    gc = _grade_color(bill.grade)
    out.append(
        "  税负率  "
        + p(gc + BOLD, f"{bill.tax_rate * 100:5.1f}%")
        + "  "
        + p(gc, _bar(bill.tax_rate))
        + "  "
        + p(BOLD, bill.grade)
    )
    out.append(p(DIM, "          " + bill.grade_note))
    out.append("")

    out.append(
        "  每月    "
        + p(BOLD, f"{bill.monthly_tokens:,}")
        + " tokens 常驻开销  ≈ "
        + p(BOLD, f"${bill.monthly_cost:,.2f}")
        + p(DIM, f"  （不做缓存 ${bill.monthly_cost_uncached:,.2f}）")
    )
    saved_month = (
        bill.monthly_cost * (bill.recoverable / bill.always_on) if bill.always_on else 0.0
    )
    out.append(
        "  可退    "
        + p(BOLD, f"{bill.recoverable_pct:.0%}")
        + " 的常驻开销  ≈ "
        + p(BOLD, f"{bill.recoverable:,} tokens")
        + p(DIM, f"  （每月省 ${saved_month:,.2f}）")
    )
    out.append("")

    out.append(p(DIM, _rule("常驻开销构成")))
    rows = [
        ("skills 描述", bill.counts["skills"], "个技能"),
        ("MCP 工具定义", bill.counts["mcp"], "台 server"),
        ("常驻指令", bill.counts["instructions"], "份文件"),
    ]
    for name, count, unit in rows:
        tokens = bill.by_category.get(name, 0)
        share = (tokens / bill.always_on) if bill.always_on else 0.0
        out.append(
            "  "
            + p(DIM, pad(name, 14))
            + p(DIM, pad(f"{count} {unit}", 14))
            + p(BOLD, f"{tokens:>8,}")
            + " tokens  "
            + p(DIM, f"{share:5.1%}")
        )
    if bill.counts["conditional"]:
        out.append(p(DIM, f"        另有 {bill.counts['conditional']} 份条件规则按 glob 触发，不计常驻"))
    out.append(
        p(DIM, "  " + pad("触发税", 27))
        + p(BOLD, f"{bill.trigger_total:>8,}")
        + " tokens  "
        + p(DIM, "技能正文合计")
    )
    out.append("")

    if not bill.findings:
        out.append(p(GREEN, "  ✓ 没找到可回收的浪费。这个配置值得截图。"))
        out.append("")
        return "\n".join(out)

    counts = {"critical": 0, "warn": 0, "info": 0}
    for f in bill.findings:
        counts[f.severity] += 1
    out.append(p(DIM, _rule(f"问题 {len(bill.findings)} 项")))
    out.append(
        p(DIM, "  ")
        + p(RED, f"{counts['critical']} 严重")
        + p(DIM, " / ")
        + p(YELLOW, f"{counts['warn']} 警告")
        + p(DIM, " / ")
        + p(CYAN, f"{counts['info']} 提示")
    )

    for i, f in enumerate(bill.findings, 1):
        out.append("")
        head = f"  {i:>2}. "
        head += p(_sev_color(f.severity), f"[{SEVERITY_LABEL[f.severity]}]")
        head += " " + p(BOLD, f.title)
        if f.saved_tokens:
            head += p(GREEN, f"  -{f.saved_tokens:,} tok")
        if f.scope == "trigger":
            head += p(DIM, "  · 触发税")
        out.append(head)
        for line in wrap(f.detail, WIDTH - 8):
            out.append(p(DIM, line))
        for line in wrap("→ " + f.fix, WIDTH - 8):
            out.append(p(GREEN, line))
        if verbose and f.refs:
            for r in f.refs[:6]:
                out.append(p(DIM, "      · " + r))

    out.append("")
    out.append(p(DIM, "  " + "═" * WIDTH))
    out.append(p(DIM, "  估算：CJK 0.75 tok/字，ASCII 0.25 tok/字，误差约 ±8%。"))
    out.append(p(DIM, "  够用来决定删什么，不够用来报账。"))
    out.append("")
    return "\n".join(out)


def render_markdown(bill: Bill) -> str:
    lines: list[str] = ["## 上下文税单", ""]
    lines.append(f"- **税负率**：{bill.tax_rate * 100:.1f}%（{bill.grade}）")
    lines.append(f"- **常驻开销**：{bill.always_on:,} tokens / 窗口 {bill.window:,}")
    lines.append(f"- **每月**：{bill.monthly_tokens:,} tokens ≈ ${bill.monthly_cost:,.2f}")
    lines.append(f"- **可退**：{bill.recoverable_pct:.0%}（≈ {bill.recoverable:,} tokens）")
    lines.append("")
    lines.append("| 构成 | 数量 | tokens | 占比 |")
    lines.append("| --- | ---: | ---: | ---: |")
    band = [
        ("skills 描述", bill.counts["skills"], "个"),
        ("MCP 工具定义", bill.counts["mcp"], "台"),
        ("常驻指令", bill.counts["instructions"], "份"),
    ]
    for name, count, unit in band:
        tokens = bill.by_category.get(name, 0)
        share = tokens / bill.always_on if bill.always_on else 0.0
        lines.append(f"| {name} | {count} {unit} | {tokens:,} | {share:.1%} |")
    lines.append("")
    if bill.findings:
        lines.append("| 级别 | 问题 | 可省 |")
        lines.append("| --- | --- | ---: |")
        for f in bill.findings:
            title = f.title.replace("|", "\\|")
            saved = f"-{f.saved_tokens:,}" if f.saved_tokens else "—"
            lines.append(f"| {SEVERITY_LABEL[f.severity]} | {title} | {saved} |")
        lines.append("")
    return "\n".join(lines)


def render_json(bill: Bill) -> str:
    payload = asdict(bill)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(sys.stdout.isatty())
