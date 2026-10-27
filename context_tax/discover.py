"""Discovery: find everything that gets injected into an agent's context."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__",
    ".next", "target", ".idea", ".vscode", "site-packages", "vendor",
}

# Instruction files that are injected on *every* request.
ALWAYS_ON_NAMES = {
    "CLAUDE.md": "claude-code",
    "AGENTS.md": "agents-md",
    "GEMINI.md": "gemini-cli",
    "copilot-instructions.md": "github-copilot",
    ".cursorrules": "cursor-legacy",
    ".windsurfrules": "windsurf-legacy",
    ".clinerules": "cline",
}

MCP_CONFIG_NAMES = [
    ".mcp.json",
    "mcp.json",
    ".cursor/mcp.json",
    ".vscode/mcp.json",
    ".claude/settings.json",
    "claude_desktop_config.json",
]

MAX_SKILL_DEPTH = 3

# 宿主会把插件自带的技能塞进每一次请求。这些技能不在 ~/.claude/skills 里，
# 而在插件缓存深处（.../<plugin>/<version>/skills/<name>/SKILL.md），
# 不专门去找就会漏掉，报出来的税负率会低得离谱。
PLUGIN_CACHE_ROOTS = (
    ".claude/plugins",
    ".workbuddy/plugins/cache",
    ".codex/plugins",
)


@dataclass
class Skill:
    name: str
    path: Path
    description: str
    body: str
    body_tokens: int
    desc_tokens: int
    lines: int
    has_references: bool
    frontmatter_ok: bool
    age_days: int
    scope: str = "project"


@dataclass
class InstructionFile:
    path: Path
    kind: str
    tokens: int
    lines: int
    always_on: bool
    age_days: int
    text: str = ""
    scope: str = "project"


@dataclass
class McpServer:
    name: str
    source: Path
    tokens_est: int
    conditional: bool = False


@dataclass
class Inventory:
    root: Path
    skills: list[Skill] = field(default_factory=list)
    instructions: list[InstructionFile] = field(default_factory=list)
    mcp: list[McpServer] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # 同名技能在不同 harness 目录里各存一份（只算一份税，但要报出来）
    duplicate_groups: list[list[Skill]] = field(default_factory=list)


# --- frontmatter -------------------------------------------------------------

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, bool]:
    """Minimal YAML frontmatter reader. Handles `key: value`, quotes, and `|` blocks."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text, False
    raw = m.group(1)
    body = text[m.end():]
    data: dict[str, str] = {}
    current_key: str | None = None
    block_indent: int | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if block_indent is not None and indent > block_indent:
            data[current_key] = (data.get(current_key, "") + " " + line.strip()).strip()
            continue
        block_indent = None
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value in ("|", ">", "|-", ">-"):
            data[key] = ""
            current_key = key
            block_indent = indent
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key] = value
    return data, body, True


def _age_days(path: Path) -> int:
    try:
        return max(0, int((time.time() - path.stat().st_mtime) // 86400))
    except OSError:
        return 0


# --- discovery ---------------------------------------------------------------

def _iter_skill_dirs(skills_root: Path) -> list[Path]:
    found: list[Path] = []
    base_depth = len(skills_root.parts)
    for dirpath, dirnames, _ in os.walk(skills_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        depth = len(Path(dirpath).parts) - base_depth
        if depth > MAX_SKILL_DEPTH:
            dirnames[:] = []
            continue
        if (Path(dirpath) / "SKILL.md").is_file():
            found.append(Path(dirpath))
            # 这里**不能**截断遍历。把一整个技能仓库 clone 进 skills/ 是很常见的用法，
            # 仓库里往往还套着子技能（skills/mingli/qimen-dunjia/SKILL.md）。
            # 早期版本在这里 dirnames[:] = []，导致 20KB 的子技能一行都没被算进税单。
    return sorted(found)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _load_one(d: Path, scope: str) -> Skill:
    from .tokens import estimate_tokens

    p = d / "SKILL.md"
    text = _read(p)
    fm, body, ok = parse_frontmatter(text)
    name = (fm.get("name") or d.name).strip()
    desc = (fm.get("description") or "").strip()
    if not desc:
        # some authors put the summary in body H1 instead of frontmatter
        first_para = " ".join(
            ln.strip() for ln in body.splitlines() if ln.strip() and not ln.startswith("#")
        )
        desc = first_para[:400]
    return Skill(
        name=name,
        path=p,
        description=desc,
        body=body,
        body_tokens=estimate_tokens(body),
        desc_tokens=estimate_tokens(desc),
        lines=body.count("\n") + 1,
        has_references=(d / "references").is_dir() or (d / "assets").is_dir(),
        frontmatter_ok=ok and "name" in fm and "description" in fm,
        age_days=_age_days(p),
        scope=scope,
    )


def load_skills(skills_root: Path, scope: str, notes: list[str]) -> list[Skill]:
    skills = [_load_one(d, scope) for d in _iter_skill_dirs(skills_root)]
    if skills_root.exists() and not skills:
        notes.append(f"{skills_root} 存在但没有找到 SKILL.md")
    return skills


def _iter_plugin_skill_roots(base: Path, max_depth: int = 8) -> list[Path]:
    """插件缓存里所有 `skills` 目录（版本号那层很深，所以要放宽深度）。"""
    roots: list[Path] = []
    base_depth = len(base.parts)
    for dirpath, dirnames, _ in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        cur = Path(dirpath)
        if cur.name == "skills" and cur != base:
            roots.append(cur)
            dirnames[:] = []
            continue
        if len(cur.parts) - base_depth >= max_depth:
            dirnames[:] = []
    return roots


def plugin_skill_roots(home: Path) -> list[Path]:
    out: list[Path] = []
    for rel in PLUGIN_CACHE_ROOTS:
        base = home / rel
        if base.is_dir():
            out.extend(_iter_plugin_skill_roots(base))
    return out


def load_plugin_skills(home: Path, notes: list[str]) -> list[Skill]:
    skills: list[Skill] = []
    for sr in plugin_skill_roots(home):
        skills.extend(load_skills(sr, "plugin", notes))
    return skills


def _dedupe_skills(skills: list[Skill]) -> tuple[list[Skill], list[list[Skill]]]:
    """合并重复技能。

    两种重复都会把账算错：
      1. 同一份 SKILL.md 被扫两遍（root 就是 home 时，.agents/skills 既算项目又算全局）
      2. 同名技能在多个 harness 目录各存一份（运行时只会加载其中一个）

    重复计入不但会把税负算高，还会让「描述重叠」检测器拿一个技能和它自己比，
    报出 `sdk ↔ sdk` 这种自己跟自己打架的结论。所以按路径先去重，再按名字
    只留一份计费，其余收进 duplicate_groups 单独报告。
    """
    by_path: dict[Path, Skill] = {}
    for s in skills:
        key = s.path.resolve()
        prev = by_path.get(key)
        # 同一路径优先保留 project 那份，它更接近实际加载位置
        if prev is None or (prev.scope == "global" and s.scope == "project"):
            by_path[key] = s

    by_name: dict[str, list[Skill]] = {}
    for s in by_path.values():
        by_name.setdefault(s.name, []).append(s)

    unique: list[Skill] = []
    groups: list[list[Skill]] = []
    for group in by_name.values():
        group.sort(key=lambda s: (s.scope != "project", str(s.path)))
        unique.append(group[0])
        if len(group) > 1:
            groups.append(group)
    unique.sort(key=lambda s: s.name)
    groups.sort(key=lambda g: g[0].name)
    return unique, groups


_CURSOR_MDC_ALWAYS_RE = re.compile(r"^\s*alwaysApply\s*:\s*true", re.MULTILINE | re.IGNORECASE)
_CURSOR_MDC_GLOBS_RE = re.compile(r"^\s*globs\s*:", re.MULTILINE | re.IGNORECASE)


def load_instructions(root: Path, notes: list[str]) -> list[InstructionFile]:
    from .tokens import estimate_tokens

    candidates: list[tuple[Path, str, str]] = []  # (path, kind, scope)

    for name, kind in ALWAYS_ON_NAMES.items():
        for cand in (root / name, root / ".claude" / name, root / ".github" / name):
            if cand.is_file():
                candidates.append((cand, kind, "project"))

    for sub in (".cursor/rules", ".claude/rules", ".agents/rules"):
        d = root / sub
        if d.is_dir():
            for f in sorted(d.rglob("*.md*")):
                if f.suffix in (".md", ".mdc"):
                    candidates.append((f, "cursor-rules" if "cursor" in sub else "claude-rules", "project"))

    seen: set[Path] = set()
    out: list[InstructionFile] = []
    for path, kind, scope in candidates:
        rp = path.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        text = _read(path)
        always_on = True
        if kind in ("cursor-rules", "claude-rules"):
            if _CURSOR_MDC_GLOBS_RE.search(text) and not _CURSOR_MDC_ALWAYS_RE.search(text):
                always_on = False
        out.append(
            InstructionFile(
                path=path,
                kind=kind,
                tokens=estimate_tokens(text),
                lines=text.count("\n") + 1,
                always_on=always_on,
                age_days=_age_days(path),
                text=text,
                scope=scope,
            )
        )
    return out


def _mcp_names_from_json(path: Path) -> list[str]:
    text = _read(path)
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    names: list[str] = []
    for key in ("mcpServers", "servers", "mcp_servers"):
        block = data.get(key)
        if isinstance(block, dict):
            names.extend(block.keys())
    return names


def _mcp_names_from_toml(path: Path) -> list[str]:
    if tomllib is None:
        return []
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return []
    block = data.get("mcp_servers") or data.get("mcpServers") or {}
    return list(block.keys()) if isinstance(block, dict) else []


def load_mcp(root: Path, tool_tokens: int, tools_per_server: int, notes: list[str]) -> list[McpServer]:
    servers: dict[str, McpServer] = {}
    for rel in MCP_CONFIG_NAMES:
        p = root / rel
        if not p.is_file():
            continue
        names = _mcp_names_from_json(p)
        if rel == ".claude/settings.json" and not names:
            continue
        for n in names:
            servers.setdefault(n, McpServer(n, p, tool_tokens * tools_per_server))
    for rel in ("config.toml", ".codex/config.toml"):
        p = root / rel
        if p.is_file():
            for n in _mcp_names_from_toml(p):
                servers.setdefault(n, McpServer(n, p, tool_tokens * tools_per_server))
    return list(servers.values())


def collect(root: Path, include_global: bool = False, home: Path | None = None,
            tool_tokens: int = 150, tools_per_server: int = 15,
            include_plugins: bool = False) -> Inventory:
    root = root.resolve()
    inv = Inventory(root=root)

    # 单个技能仓库的常见形态：SKILL.md 就在仓库根目录
    if (root / "SKILL.md").is_file():
        inv.skills.append(_load_one(root, "project"))

    project_skill_roots = [
        root / "skills",
        root / ".claude" / "skills",
        root / ".agents" / "skills",
        root / ".codex" / "skills",
        root / ".cursor" / "skills",
    ]
    for sr in project_skill_roots:
        if sr.is_dir():
            inv.skills.extend(load_skills(sr, "project", inv.notes))

    inv.instructions.extend(load_instructions(root, inv.notes))
    inv.mcp.extend(load_mcp(root, tool_tokens, tools_per_server, inv.notes))

    if include_global:
        home = home or Path.home()
        for sr in (
            home / ".claude" / "skills",
            home / ".agents" / "skills",
            home / ".codex" / "skills",
            home / ".cursor" / "skills",
            home / ".workbuddy" / "skills",
        ):
            if sr.is_dir():
                inv.skills.extend(load_skills(sr, "global", inv.notes))
        for name, kind in ALWAYS_ON_NAMES.items():
            for cand in (home / ".claude" / name, home / ".codex" / name):
                if cand.is_file() and cand.resolve() not in {i.path.resolve() for i in inv.instructions}:
                    from .tokens import estimate_tokens

                    text = _read(cand)
                    inv.instructions.append(
                        InstructionFile(
                            path=cand,
                            kind=kind + " (global)",
                            tokens=estimate_tokens(text),
                            lines=text.count("\n") + 1,
                            always_on=True,
                            age_days=_age_days(cand),
                            text=text,
                            scope="global",
                        )
                    )
        for cfg in (home / ".claude.json", home / ".cursor" / "mcp.json"):
            if cfg.is_file():
                for n in _mcp_names_from_json(cfg):
                    if not any(s.name == n for s in inv.mcp):
                        inv.mcp.append(McpServer(n, cfg, tool_tokens * tools_per_server))

        if include_plugins:
            inv.skills.extend(load_plugin_skills(home, inv.notes))
        else:
            # 不纳入也要说一声，否则会给人"免税"的错觉
            available = len({
                d.name for sr in plugin_skill_roots(home) for d in _iter_skill_dirs(sr)
            })
            if available:
                inv.notes.append(
                    f"宿主插件里另有 {available} 个技能没有计入（加 --plugins 纳入）——"
                    "它们同样每轮都在占上下文。"
                )

    inv.skills, inv.duplicate_groups = _dedupe_skills(inv.skills)
    return inv
