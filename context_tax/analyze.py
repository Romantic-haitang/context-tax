"""The analysis layer: turn an inventory into findings and a bill."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
import re

from .discover import Inventory, InstructionFile, Skill
from .tokens import jaccard, overlap_coefficient, word_set

CACHE_READ_MULTIPLIER = 0.1
INSTRUCTION_TARGET_TOKENS = 2000
MCP_SERVER_BUDGET = 4
SKILL_BODY_TRIGGER_BUDGET = 3000
THIN_SKILL_TOKENS = 60
STALE_DAYS = 180

# 描述重叠检测的门槛。低于这些规模的词集不能拿来算重合度——
# 否则两个各自只有三个词的描述共享一个 "codex" 就能算出 75%。
MIN_DESC_WORDS = 4
MIN_SHARED_WORDS = 4
DESC_JACCARD_CANDIDATE = 0.45
DESC_COOP_CANDIDATE = 0.70
BODY_COOP_CANDIDATE = 0.60
BODY_MIN_WORDS = 40
COOP_MAX_SIZE_RATIO = 3.0

SEVERITY_ORDER = {"critical": 0, "warn": 1, "info": 2}
SEVERITY_LABEL = {"critical": "严重", "warn": "警告", "info": "提示"}


@dataclass
class Finding:
    id: str
    severity: str
    title: str
    detail: str
    fix: str
    saved_tokens: int = 0
    scope: str = "always"  # always = 常驻税, trigger = 触发税
    refs: list[str] = field(default_factory=list)


@dataclass
class Bill:
    root: str
    window: int
    always_on: int
    trigger_total: int
    by_category: dict[str, int]
    tax_rate: float
    grade: str
    grade_note: str
    recoverable: int
    recoverable_pct: float
    requests: int
    price_in: float
    cache_hit: float
    monthly_tokens: int
    monthly_cost: float
    monthly_cost_uncached: float
    counts: dict[str, int]
    findings: list[Finding]
    notes: list[str]


def _grade(rate: float) -> tuple[str, str]:
    if rate < 0.04:
        return "免税", "配置很干净，常驻开销几乎可以忽略"
    if rate < 0.08:
        return "轻度", "可以接受，但已经有可回收的部分"
    if rate < 0.15:
        return "中度", "每轮都在为不需要的东西付费"
    if rate < 0.25:
        return "重度", "四分之一以上的上下文被闲置配置占着"
    return "危险", "上下文被你自己塞满了，模型能用来思考的空间所剩无几"


def _fmt_list(names: list[str], limit: int = 4) -> str:
    if len(names) <= limit:
        return "、".join(names)
    return "、".join(names[:limit]) + f" 等 {len(names)} 个"


# --- detectors ---------------------------------------------------------------

def _detect_skill_overlap(skills: list[Skill]) -> list[Finding]:
    out: list[Finding] = []
    sigs = {s.path: (word_set(s.description), word_set(s.body[:1500])) for s in skills}
    seen: set[tuple[str, str]] = set()
    for a, b in combinations(skills, 2):
        # 同一份技能不跟自己比。dedupe 之后理论上不会出现，但这里再挡一道，
        # 免得哪天调用方忘了去重就报出 `sdk ↔ sdk` 这种没法解释的结论。
        if a.name == b.name or a.path.resolve() == b.path.resolve():
            continue
        da, db = sigs[a.path][0], sigs[b.path][0]
        ba, bb = sigs[a.path][1], sigs[b.path][1]
        # 词集太小的时候重合度没有意义：去掉虚词后只剩两三个词，
        # 共享一个 "codex" 就能算出很高的比例。宁可不报。
        if min(len(da), len(db)) < MIN_DESC_WORDS:
            continue
        shared = len(da & db)
        if shared < MIN_SHARED_WORDS:
            continue
        desc_j = jaccard(da, db)
        # overlap_coefficient 除以较小的那个集合，所以"3 个词 vs 77 个词"
        # 也能算出 100%。集合规模悬殊时这个指标没有意义，直接作废。
        size_ratio = max(len(da), len(db)) / min(len(da), len(db))
        desc_coop = overlap_coefficient(da, db) if size_ratio <= COOP_MAX_SIZE_RATIO else 0.0
        # 正文对正文（同量级），比"短描述 vs 长正文"可靠得多。
        body_o = 0.0
        if min(len(ba), len(bb)) >= BODY_MIN_WORDS:
            body_ratio = max(len(ba), len(bb)) / min(len(ba), len(bb))
            if body_ratio <= COOP_MAX_SIZE_RATIO:
                body_o = overlap_coefficient(ba, bb)
            if body_o < BODY_COOP_CANDIDATE:
                body_o = 0.0
        if desc_j < DESC_JACCARD_CANDIDATE and desc_coop < DESC_COOP_CANDIDATE and not body_o:
            continue
        key = tuple(sorted([str(a.path), str(b.path)]))
        if key in seen:
            continue
        seen.add(key)
        saved = min(a.desc_tokens, b.desc_tokens)
        worst = max(desc_j, desc_coop, body_o)
        # 只省十几个 token 的重叠，谈不上"严重"。金额决定档位，不是比例。
        severity = "critical" if (desc_j >= 0.70 and shared >= 6) else "warn"
        out.append(
            Finding(
                id="skill-overlap",
                severity=severity,
                title=f"触发词打架：{a.name} ↔ {b.name}",
                detail=(
                    f"两句描述共享 {shared} 个实质词，重合度 {worst:.0%}——"
                    f"模型看到同一个请求时会在两者之间随机挑一个，"
                    f"你以为是双保险，实际是互相拆台。"
                ),
                fix=f"合并成一个技能，或给两者的 description 加互斥边界（用于…；不用于…）。"
                    f"省下的 {saved} tokens 是次要的——真正的收益是不再选错技能。",
                saved_tokens=saved,
                refs=[str(a.path), str(b.path)],
            )
        )
    return out


_GENERIC_MARKERS = (
    "各种", "一切", "任何", "all kinds", "any task", "various", "assist with",
    "helps with", "helps you", "a tool for", "一个工具", "综合", "万能",
)


def _detect_skill_reachable(skills: list[Skill]) -> list[Finding]:
    out: list[Finding] = []
    unreachable: list[str] = []
    generic: list[str] = []
    for s in skills:
        if not s.description.strip() or len(s.description.strip()) < 20:
            unreachable.append(s.name)
        elif any(m in s.description.lower() for m in _GENERIC_MARKERS):
            generic.append(s.name)
    if unreachable:
        out.append(
            Finding(
                id="skill-unreachable",
                severity="warn",
                title=f"{len(unreachable)} 个技能装上去等于没装",
                detail=(
                    f"{_fmt_list(unreachable)} 的 description 缺失或不足 20 字。"
                    "模型靠 description 决定要不要加载一个技能——描述为空，它这辈子都不会触发。"
                ),
                fix="补一句「做什么 + 什么时候用 + 不用于什么」的描述，这是技能唯一的简历。",
                refs=unreachable,
            )
        )
    if generic:
        out.append(
            Finding(
                id="skill-generic",
                severity="warn",
                title=f"{len(generic)} 个技能写了等于没写的描述",
                detail=(
                    f"{_fmt_list(generic)} 的描述里有「各种 / 万能 / helps with」这类词，"
                    "边界形同虚设，结果是到处乱触发，挤掉真正该加载的技能。"
                ),
                fix="把描述改成可判定的条件句：什么时候用、什么时候不用。",
                refs=generic,
            )
        )
    return out


def _detect_skill_quality(skills: list[Skill]) -> list[Finding]:
    out: list[Finding] = []
    bloated = [s for s in skills if s.body_tokens > SKILL_BODY_TRIGGER_BUDGET and not s.has_references]
    if bloated:
        saved = sum(s.body_tokens - SKILL_BODY_TRIGGER_BUDGET for s in bloated)
        verb = "的正文都超过" if len(bloated) > 1 else "的正文超过"
        out.append(
            Finding(
                id="skill-no-disclosure",
                severity="warn",
                scope="trigger",
                title=f"{len(bloated)} 个技能一触发就灌进 "
                      f"{sum(s.body_tokens for s in bloated):,} tokens",
                detail=(
                    f"{_fmt_list([s.name for s in bloated])} {verb} 3,000 tokens，"
                    "且没有 references/ 目录。平时不占常驻税，但一旦触发就是一次性全额付款，"
                    "还会把真正相关的信息挤出注意力窗口。"
                ),
                fix="正文只留判定流程和最短成功路径，细则、示例、长清单丢进 references/，按需读取。",
                saved_tokens=0,
                refs=[str(s.path) for s in bloated],
            )
        )
    thin = [s for s in skills if s.body_tokens < THIN_SKILL_TOKENS]
    if thin:
        out.append(
            Finding(
                id="skill-thin",
                severity="info",
                title=f"{len(thin)} 个「技能」其实只是张便签",
                detail=f"先看这几个：{_fmt_list([s.name for s in thin])}。"
                       f"正文都不到 {THIN_SKILL_TOKENS} tokens，装上去只是增加了发现成本，"
                       "还占着 description 的触发名额。",
                fix="要么写成一个真的技能，要么删掉。半成品技能比没有技能更费神。",
                refs=[str(s.path) for s in thin],
            )
        )
    return out


def _detect_instructions(instructions: list[InstructionFile]) -> list[Finding]:
    out: list[Finding] = []
    always = [i for i in instructions if i.always_on]

    heavy = [i for i in always if i.tokens > 4000]
    if heavy:
        saved = sum(i.tokens - INSTRUCTION_TARGET_TOKENS for i in heavy)
        out.append(
            Finding(
                id="instruction-bloat",
                severity="critical" if any(i.tokens > 8000 for i in heavy) else "warn",
                title=f"{len(heavy)} 份常驻指令文件塞进了 "
                      f"{sum(i.tokens for i in heavy):,} tokens",
                detail=(
                    "常驻指令每轮都全额付费，而且越长越不被遵守——"
                    "规则超过一定密度后，模型会开始挑着执行，你加的每一条都在稀释前一条。"
                ),
                fix=f"把每份压到 {INSTRUCTION_TARGET_TOKENS:,} tokens 以内（只留不可推导的约定），"
                    f"其余移到 docs/ 或 references/ 按需读取。可省 ~{saved:,} tokens。",
                saved_tokens=saved,
                refs=[str(i.path) for i in heavy],
            )
        )

    for a, b in combinations(always, 2):
        wa, wb = word_set(a.text[:8000]), word_set(b.text[:8000])
        if jaccard(wa, wb) >= 0.55:
            smaller, bigger = (a, b) if a.tokens <= b.tokens else (b, a)
            out.append(
                Finding(
                    id="instruction-duplicate",
                    severity="critical",
                    title=f"同一个意思写了两遍：{a.path.name} ≈ {b.path.name}",
                    detail=(
                        f"两份文件词重合度 {jaccard(wa, wb):.0%}，其中较小的一份 "
                        f"{smaller.tokens:,} tokens 完全是重复付费。"
                        "多 harness 并存时最典型的浪费。"
                    ),
                    fix=f"保留一份作源，另一份改用软链接或一行 include（'{bigger.path.name} 见源文件'）。"
                        f"可省 ~{smaller.tokens:,} tokens。",
                    saved_tokens=smaller.tokens,
                    refs=[str(a.path), str(b.path)],
                )
            )
    return out


def _detect_mcp(inv: Inventory, window: int) -> list[Finding]:
    out: list[Finding] = []
    n = len(inv.mcp)
    total = sum(s.tokens_est for s in inv.mcp)
    if n > MCP_SERVER_BUDGET:
        surplus = sorted(inv.mcp, key=lambda s: s.tokens_est)[: n - MCP_SERVER_BUDGET]
        saved = sum(s.tokens_est for s in surplus)
        out.append(
            Finding(
                id="mcp-flood",
                severity="critical" if total > window * 0.12 else "warn",
                title=f"{n} 个 MCP server 的工具定义常驻占用 ~{total:,} tokens",
                detail=(
                    f"工具定义是每轮全量注入的，{n} 台 server 意味着模型每轮都要先读完 "
                    f"{total:,} tokens 的说明书，其中大部分和当前任务无关。"
                ),
                fix=f"只保留核心的 {MCP_SERVER_BUDGET} 台，其余按需临时启用。"
                    f"可省 ~{saved:,} tokens。",
                saved_tokens=saved,
                refs=[s.name for s in surplus],
            )
        )
    elif n and total > window * 0.10:
        out.append(
            Finding(
                id="mcp-flood",
                severity="warn",
                title=f"MCP 工具定义占了上下文的 {total / window:.1%}",
                detail="即便只有几台 server，工具 schema 也可能很胖，尤其是带大枚举参数的那种。",
                fix="检查是否有 server 暴露了几十个工具，把它们拆开或换成按需执行的 CLI。",
                saved_tokens=0,
                refs=[s.name for s in inv.mcp],
            )
        )
    return out


def _detect_stale(skills: list[Skill]) -> list[Finding]:
    stale = [s for s in skills if s.age_days > STALE_DAYS]
    if not stale:
        return []
    oldest = max(stale, key=lambda s: s.age_days)
    return [
        Finding(
            id="skill-stale",
            severity="info",
            title=f"{len(stale)} 个技能已经 {STALE_DAYS}+ 天没动过",
            detail=(
                f"最老的是 {oldest.name}（{oldest.age_days} 天）。"
                "模型换代了、工具改名了、你的工作流也变了，这些技能多半在按旧世界的地图指路。"
            ),
            fix="逐个过一遍：还能用就更新，不能用就删。技能不是收藏品。",
            refs=[str(s.path) for s in stale],
        )
    ]


# --- main --------------------------------------------------------------------

def _detect_duplicate_copies(inv: Inventory) -> list[Finding]:
    """同名技能在多个 harness 目录各存一份。

    这类副本不会叠加常驻税（运行时只会加载其中一个），所以 saved_tokens 记 0。
    真正的成本是维护漂移：你改了 .agents 里那份，.codex 里那份还停在三个月前，
    两个 harness 从此开始给你不同的答案。
    """
    groups = inv.duplicate_groups
    if not groups:
        return []

    harnesses = sorted({s.scope for g in groups for s in g})
    examples = [f"{g[0].name}（{len(g)} 份）" for g in groups]
    drift = [g for g in groups if len({s.desc_tokens for s in g}) > 1 or
             len({s.body_tokens for s in g}) > 1]
    return [
        Finding(
            id="skill-multi-copy",
            severity="warn" if drift else "info",
            title=f"{len(groups)} 个技能在多个目录各存一份：{_fmt_list(examples)}",
            detail=(
                f"同名的 SKILL.md 出现在 {len(harnesses)} 处目录里。因为运行时只会加载其中一份，"
                "它不叠加常驻税——所以这笔账不算在钱上。"
                + (
                    f"但有 {len(drift)} 组的内容已经不一致了，说明你改了其中一份、忘了另一份。"
                    if drift else "目前各副本内容一致，但下次你只改一处的时候就不一致了。"
                )
            ),
            fix="用一个目录做唯一事实来源，其余用软链接或安装脚本同步。别手工维护两份。",
            saved_tokens=0,
            refs=[str(s.path) for g in groups for s in g][:8],
        )
    ]


def _norm_skill_name(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", raw.strip().lower()).strip("-")


def _detect_skill_naming(skills: list[Skill]) -> list[Finding]:
    """frontmatter 的 name 和目录名对不上。

    大多数宿主按 name 解析调用（`/name`），按目录名安装和展示。两者不一致时，
    用户在界面上看到的是目录名，敲出来的是 name，于是"这个技能怎么调不出来"
    就变成了一道玄学题——实际原因只是作者手滑。
    """
    pairs: list[tuple[Skill, str]] = []
    for s in skills:
        dirname = s.path.parent.name
        if not dirname or dirname.startswith("."):
            continue
        if _norm_skill_name(s.name) and _norm_skill_name(s.name) != _norm_skill_name(dirname):
            pairs.append((s, dirname))
    if not pairs:
        return []
    shown = "；".join(f"`{s.name}` 在 `{d}/` 里" for s, d in pairs[:3])
    more = f"，另有 {len(pairs) - 3} 个" if len(pairs) > 3 else ""
    return [
        Finding(
            id="skill-name-mismatch",
            severity="info",
            title=f"{len(pairs)} 个技能的 name 和目录名对不上",
            detail=(
                f"{shown}{more}。宿主多半按 name 解析调用、按目录名展示安装，"
                "两边不一致时用户看到的名字敲不出来，只会以为是宿主抽风。"
            ),
            fix="把 frontmatter 的 name 改成和目录名一致（推荐），或者反过来重命名目录。别让它们各自为政。",
            saved_tokens=0,
            refs=[str(s.path) for s, _ in pairs],
        )
    ]
def analyze(
    inv: Inventory,
    window: int = 200_000,
    requests: int = 1500,
    price_in: float = 3.0,
    cache_hit: float = 0.80,
) -> Bill:
    skills_total_desc = sum(s.desc_tokens for s in inv.skills)
    mcp_total = sum(s.tokens_est for s in inv.mcp)
    always_instr = sum(i.tokens for i in inv.instructions if i.always_on)
    cond_instr = sum(i.tokens for i in inv.instructions if not i.always_on)

    by_category = {
        "skills 描述": skills_total_desc,
        "MCP 工具定义": mcp_total,
        "常驻指令": always_instr,
        "条件规则": 0,  # 条件规则不计入常驻税
    }
    always_on = skills_total_desc + mcp_total + always_instr
    trigger_total = sum(s.body_tokens for s in inv.skills)

    findings: list[Finding] = []
    findings += _detect_duplicate_copies(inv)
    findings += _detect_skill_overlap(inv.skills)
    findings += _detect_skill_reachable(inv.skills)
    findings += _detect_skill_quality(inv.skills)
    findings += _detect_skill_naming(inv.skills)
    findings += _detect_instructions(inv.instructions)
    findings += _detect_mcp(inv, window)
    findings += _detect_stale(inv.skills)
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], -f.saved_tokens))

    recoverable = min(always_on, sum(f.saved_tokens for f in findings if f.scope == "always"))
    rate = always_on / window if window else 0.0
    grade, note = _grade(rate)

    effective_mult = cache_hit * CACHE_READ_MULTIPLIER + (1 - cache_hit)
    monthly_tokens = always_on * requests
    monthly_cost = monthly_tokens / 1_000_000 * price_in * effective_mult
    monthly_cost_uncached = monthly_tokens / 1_000_000 * price_in

    counts = {
        "skills": len(inv.skills),
        "instructions": len([i for i in inv.instructions if i.always_on]),
        "conditional": len([i for i in inv.instructions if not i.always_on]),
        "mcp": len(inv.mcp),
    }

    return Bill(
        root=str(inv.root),
        window=window,
        always_on=always_on,
        trigger_total=trigger_total,
        by_category=by_category,
        tax_rate=rate,
        grade=grade,
        grade_note=note,
        recoverable=recoverable,
        recoverable_pct=(recoverable / always_on) if always_on else 0.0,
        requests=requests,
        price_in=price_in,
        cache_hit=cache_hit,
        monthly_tokens=monthly_tokens,
        monthly_cost=monthly_cost,
        monthly_cost_uncached=monthly_cost_uncached,
        counts=counts,
        findings=findings,
        notes=inv.notes,
    )
