# context-tax

**你的 agent 配置每轮都在缴税。这个工具把税单打出来。**

技能的 description、MCP 的工具定义、`CLAUDE.md` —— 这些东西在**每一次**请求里都会重新
发送一遍，不管这一轮用不用得上。装到第十个技能、第七台 MCP server 的时候，你已经有
一到两成的上下文，永远在为一个可能永远不会到来的任务待命。

`context-tax` 不是又一个 SKILL.md 格式检查器。它算的是钱和窗口：**你每轮为闲置配置付了
多少，其中哪几笔可以退。**

## 看一个真实输出

一个"装了四个月、什么都留一点"的仓库：

```
  CONTEXT TAX  ·  你的 agent 上下文税单
  ════════════════════════════════════════════════════════════════
  税负率    9.7%  ██··················  中度
          每轮都在为不需要的东西付费

  每月    29,128,500 tokens 常驻开销  ≈ $24.47  （不做缓存 $87.39）
  可退    49% 的常驻开销  ≈ 9,604 tokens  （每月省 $12.10）

── 常驻开销构成 ────────────────────────────────────────────────
  skills 描述   7 个技能           209 tokens   1.1%
  MCP 工具定义  8 台 server     18,000 tokens  92.7%
  常驻指令      3 份文件         1,210 tokens   6.2%
  触发税                        6,360 tokens  技能正文合计

── 问题 8 项 ───────────────────────────────────────────────────
  3 严重 / 3 警告 / 2 提示

   1. [严重] 同一个意思写了两遍：CLAUDE.md ≈ AGENTS.md  -502 tok
   4. [警告] 8 个 MCP server 的工具定义常驻占用 ~18,000 tokens  -9,000 tok
   6. [警告] 1 个技能一触发就灌进 5,974 tokens  · 触发税
```

三条结论，这个输出已经把话说完：

1. **92.7% 的税是 MCP 交的**，不是技能。多数人以为技能装多了会拖慢 agent，其实最大的
   那笔账在工具定义上。
2. **`CLAUDE.md` 和 `AGENTS.md` 写了同一份东西**，一句话省 502 tokens。
3. **一个 6,000 tokens 的 API 手册塞在 SKILL.md 正文里**，一触发就是一次性全额付款。

同一套检查跑一个干净的配置（2 个技能、2 台 server、单一指令文件）：

```
  税负率    2.3%  ····················  免税
  ✓ 没找到可回收的浪费。这个配置值得截图。
```

## 跑起来

不需要安装，不需要依赖，Python 3.9+ 就行：

```bash
git clone https://github.com/OWNER/context-tax && cd context-tax
python3 -m context_tax /path/to/your/project
```

带上全局配置（`~/.claude`、`~/.agents`、`~/.codex`）：

```bash
python3 -m context_tax . --global
```

换成你的真实账单价，数字才有说服力：

```bash
python3 -m context_tax . --requests 3000 --price 15
```

想让它进 CI，超阈值就红：

```bash
python3 -m context_tax . --fail-over 0.12
```

其他开关：`--json`、`--md`、`--window`、`--cache-hit`、`--no-color`、`-v`。
算法说明：`python3 -m context_tax explain`。

## 它查什么

| 检查 | 说明 |
| --- | --- |
| `mcp-flood` | MCP server 数量与工具定义体积 |
| `instruction-duplicate` | `CLAUDE.md` / `AGENTS.md` 内容重复（多 harness 并存的重灾区） |
| `instruction-bloat` | 常驻指令过长，规则互相稀释 |
| `skill-overlap` | 两个技能的描述在抢同一个触发词 |
| `skill-unreachable` | 描述缺失 / 过短，模型永远发现不了 |
| `skill-generic` | 描述里全是"各种 / 万能 / helps with"，到处乱触发 |
| `skill-no-disclosure` | 正文超过 3,000 tokens 且没有 `references/` |
| `skill-thin` | 正文不足 60 tokens，那不是技能，是便签 |
| `skill-stale` | 半年没动过，多半在按旧世界的地图指路 |

## 为什么是"税负率"而不是"评分"

评分可以被任何一个自作聪明的权重糊弄过去。税负率只有一个定义：**你每轮为不需要的东西
付了窗口的百分之几**。这个数字你没法跟它辩论。

顺带说一句，它也不打算假装自己是质量分。一个 3% 的配置可能全是废话，
一个 12% 的配置可能每个字都在干活。这个工具只负责算清账，活儿好不好得你自己看。

## 它诚实的部分

- **只读**。不改你的文件，不给"我已经帮你改好了"这种惊喜。
- **估算，不精确**。token 按 CJK 0.75/字、ASCII 0.25/字估算，误差约 ±8%；
  MCP 按每台 15 工具 × 150 tokens 估。够用来决定删什么，不够用来报账。
- **不数你的调用量**。`--requests` 是你自己填的假设，不是观测值。
- **缓存已折算**。默认按 80% 命中率 × 0.1 倍单价计算。所以"每月省的钱"会比
  不打折的算法小很多 —— 这是对的，很多工具在这里吹牛。

## 作为技能使用

```bash
npx skills add OWNER/context-tax
```

装好之后，你可以直接说"帮我看看我的 agent 配置是不是太胖了"，
它会跑一遍、读懂报告、按"省多少"排序给你三条可执行的动作。

`SKILL.md` 里写了判读细则，`references/` 里是 MCP 估算模型和阈值表。

## 多 harness

同一份配置可以在这些地方被扫到：

| Harness | 指令文件 | 技能目录 | MCP 配置 |
| --- | --- | --- | --- |
| Claude Code | `CLAUDE.md`、`.claude/rules/` | `.claude/skills/`、`~/.claude/skills/` | `.mcp.json`、`.claude/settings.json` |
| Codex | `AGENTS.md`、`~/.codex/AGENTS.md` | `.codex/skills/` | `~/.codex/config.toml` |
| Cursor | `.cursor/rules/*.mdc`、`.cursorrules` | `.cursor/skills/` | `.cursor/mcp.json` |
| Cline / Windsurf | `.clinerules`、`.windsurfrules` | — | — |
| Copilot | `.github/copilot-instructions.md` | — | `.vscode/mcp.json` |
| Gemini CLI | `GEMINI.md` | — | — |

## License

MIT
