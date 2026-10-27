"""CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .analyze import analyze
from .discover import collect
from .report import render_json, render_markdown, render_text, supports_color

EXPLAIN = """\
context-tax 是怎么算的

三类开销，只有第一类每轮都收税：

1. 常驻开销（每轮全量注入）
   - 每个技能的 name + description
   - 每台 MCP server 暴露的全部工具定义
   - CLAUDE.md / AGENTS.md / copilot-instructions.md 这类无条件的指令文件
   - 带 alwaysApply: true 的规则文件

2. 触发税（只在技能被选中时付一次）
   - SKILL.md 正文。正文再大也不占常驻，但一触发就是全额，
     而且会挤占真正相关信息的注意力预算。

3. 条件规则（按 glob 命中才注入）
   - .cursor/rules 里声明了 globs 但没有 alwaysApply 的文件

估算方式
  tokens : CJK 0.75/字、全角标点 0.6/字、ASCII 0.25/字，误差约 ±8%
  MCP    : 每台 server 15 个工具 × 150 tokens（--mcp-tool-tokens 可调）
  账单   : 常驻 tokens × 每月请求数 × 输入单价 × 缓存折算系数
           缓存折算 = 命中率 × 0.1 + (1 - 命中率)

为什么用「税负率」而不是「总分」
  总分可以被任何一个自作聪明的权重糊弄过去。税负率只有一个定义：
  你每轮为不需要的东西付了窗口的百分之几。这个数字你没法跟它辩论。

边界
  本工具只读，不修改任何文件。所有建议都需要你自己确认后执行。
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="context-tax",
        description="算清你的 agent 配置每轮偷偷吃掉多少上下文。只读，不改文件。",
    )
    p.add_argument("path", nargs="?", default=".", help="项目根目录（默认当前目录）")
    p.add_argument("-g", "--global", dest="include_global", action="store_true",
                   help="同时扫描 ~/.claude、~/.agents 等全局配置")
    p.add_argument("--window", type=int, default=200_000, help="上下文窗口 tokens（默认 200000）")
    p.add_argument("--requests", type=int, default=1500, help="每月请求数（默认 1500）")
    p.add_argument("--price", type=float, default=3.0, help="每百万输入 tokens 价格（默认 3.0 美元）")
    p.add_argument("--cache-hit", type=float, default=0.80, help="prompt cache 命中率（默认 0.8）")
    p.add_argument("--mcp-tool-tokens", type=int, default=150, help="单个 MCP 工具定义估算 tokens")
    p.add_argument("--mcp-tools-per-server", type=int, default=15, help="每台 MCP server 工具数")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.add_argument("--md", "--markdown", dest="markdown", action="store_true", help="输出 Markdown")
    p.add_argument("--no-color", action="store_true", help="关闭颜色")
    p.add_argument("-v", "--verbose", action="store_true", help="显示问题涉及的文件路径")
    p.add_argument("--fail-over", type=float, default=None, metavar="RATE",
                   help="税负率超过该值(0-1)时以退出码 1 结束，用于 CI 门禁")
    p.add_argument("--version", action="version", version=f"context-tax {__version__}")
    return p


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] in ("explain", "how", "method"):
        print(EXPLAIN)
        return 0

    if argv and argv[0] == "scan":
        argv = argv[1:]

    args = build_parser().parse_args(argv)
    root = Path(args.path).expanduser()
    if not root.exists():
        print(f"路径不存在：{root}", file=sys.stderr)
        return 2

    inv = collect(
        root,
        include_global=args.include_global,
        tool_tokens=args.mcp_tool_tokens,
        tools_per_server=args.mcp_tools_per_server,
    )
    bill = analyze(
        inv,
        window=args.window,
        requests=args.requests,
        price_in=args.price,
        cache_hit=args.cache_hit,
    )

    if args.json:
        print(render_json(bill))
    elif args.markdown:
        print(render_markdown(bill))
    else:
        color = supports_color() and not args.no_color
        print(render_text(bill, color=color, verbose=args.verbose))

    if args.fail_over is not None and bill.tax_rate > args.fail_over:
        print(f"税负率 {bill.tax_rate:.1%} 超过阈值 {args.fail_over:.1%}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
