# context-tax

**你的 agent 配置每轮都在缴税。这个工具把税单打出来。**

技能的 description、MCP 的工具定义、`CLAUDE.md` —— 这些东西在**每一次**请求里都会重新
发送一遍，不管这一轮用不用得上。装到第十个技能、第七台 MCP server 的时候，你已经有
一到两成的上下文，永远在为一个可能永远不会到来的任务待命。

`context-tax` 不是又一个 SKILL.md 格式检查器。它算的是钱和窗口：**你每轮为闲置配置付了
多少，其中哪几笔可以退。**

## 看两个真实输出

### 一、跑我自己的电脑（真实数据，不是构造的）

```
  CONTEXT TAX  ·  你的 agent 上下文税单
  ════════════════════════════════════════════════════════════════
  扫描  ~   --global --plugins

  税负率    4.2%  █···················  轻度
          可以接受，但已经有可回收的部分

  每月    12,625,500 tokens 常驻开销  ≈ $10.61  （不做缓存 $37.88）
  可退    3% 的常驻开销

── 常驻开销构成 ────────────────────────────────────────────────
  skills 描述   72 个技能        6,167 tokens  73.3%
  MCP 工具定义  1 台 server      2,250 tokens  26.7%
  常驻指令      0 份文件             0 tokens   0.0%
  触发税                      180,990 tokens  技能正文合计

── 问题 7 项 ───────────────────────────────────────────────────
  1 严重 / 5 警告 / 1 提示

   1. [严重] 触发词打架：tencent-docs ↔ tencent-saas-docs  -171 tok
      两句描述共享 88 个实质词，重合度 93%
   5. [警告] 23 个技能在多个目录各存一份：ardot-poster（2 份）等
      有 2 组的内容已经不一致了
   6. [警告] 5 个技能一触发就灌进 24,218 tokens  · 触发税
```

三条结论：

1. **73% 的常驻税在技能描述上，不是 MCP。** 这台机器只有一台 MCP server，
   却有 72 个技能的 description 每轮都要重发一遍。跟"技能装多了会变慢"的直觉
   方向一致，但比例是反的——大多数人猜错的是这一头。
2. **一个「个人版」和一个「企业版」文档技能，描述共享 88 个实质词。** 你同时
   装了它们，模型每次都得在两个几乎一样的东西之间猜。
3. **23 个技能在三个目录里各存一份，2 组内容已经不一致。** 这类重复不叠加税
   （运行时只加载一份），但会让人在两个 harness 里得到不同答案。

### 二、一个极端案例（`fixtures/messy`，仓库里可复现）

```
  税负率    9.7%  ██··················  中度
  每月    29,128,500 tokens 常驻开销  ≈ $24.47  （不做缓存 $87.39）
  可退    49% 的常驻开销  ≈ 9,604 tokens  （每月省 $12.10）

── 常驻开销构成 ────────────────────────────────────────────────
  skills 描述   7 个技能           209 tokens   1.1%
  MCP 工具定义  8 台 server     18,000 tokens  92.7%
  常驻指令      3 份文件         1,210 tokens   6.2%
  触发税                        6,360 tokens  技能正文合计

   1. [严重] 同一个意思写了两遍：CLAUDE.md ≈ AGENTS.md  -502 tok
   4. [警告] 8 个 MCP server 的工具定义常驻占用 ~18,000 tokens  -9,000 tok
   6. [警告] 1 个技能一触发就灌进 5,974 tokens  · 触发税
```

这一份是**大头在 MCP**：八台 server 的工具定义吃掉 92.7% 的税，七个技能的描述
加起来只占 1.1%。同一个工具，同一套算法，结论可以完全相反——所以别信
"某某配置类型一定最贵"这类断言，跑一遍。

### 三、一个项目级案例（两个技能，触发税 8,060 tokens）

```
  税负率    0.1%  ····················  免税
  每月    151,500 tokens 常驻开销  ≈ $0.13

── 常驻开销构成 ────────────────────────────────
  skills 描述   2 个技能           101 tokens  100.0%
  MCP 工具定义  0 台 server          0 tokens   0.0%
  常驻指令      0 份文件             0 tokens   0.0%
  触发税                        8,060 tokens  技能正文合计

── 问题 2 项 ───────────────────────────────────
  0 严重 / 1 警告 / 1 提示

   1. [警告] 2 个技能一触发就灌进 8,060 tokens  · 触发税
      mingli、qimen-duanjua 的正文都超过 3,000 tokens，且没有
      references/ 目录。
   2. [提示] 1 个技能的 name 和目录名对不上
      `qimen-duanjua` 在 `qimen-dunjia/` 里。
```

常驻税几乎是零，但**触发税 8,060 tokens**：两个技能都是 13KB / 20KB 的单文件，
没有 `references/`。这类配置的贵不在"每轮"，而在"那一次"——模型一旦选中它，
两万字的 SOP 一次性灌进来，而你真正的问题在同一轮里占不到几个百分点。
常驻税和触发税是两笔账，混在一起谈就会得出"我这个配置很干净"的错误结论。

顺带一个诚实说明：这个目录里有 15,393 个文件、564MB，全是聊天导出，没有
`CLAUDE.md`、没有 MCP。它"免税"是因为**没怎么配置**，不是因为配置得好。
工具给出好分数的时候，先确认它到底看见了什么。

同一套检查跑一个干净的配置（2 个技能、2 台 server、单一指令文件）：

```
  税负率    2.3%  ····················  免税
  ✓ 没找到可回收的浪费。这个配置值得截图。
```

## 跑起来

不需要安装，不需要依赖，Python 3.9+ 就行：

```bash
git clone https://github.com/Romantic-haitang/context-tax && cd context-tax
python3 -m context_tax /path/to/your/project
```

带上全局配置（`~/.claude`、`~/.agents`、`~/.codex`、`~/.cursor`、`~/.workbuddy`）：

```bash
python3 -m context_tax . --global
```

再带上宿主插件自带的技能——**这一块常常才是大头**：

```bash
python3 -m context_tax . --global --plugins
```

不带 `--plugins` 时，如果检测到插件技能存在，报告末尾会明说"另有 N 个没计入"。
免得你拿着一份漏账的税单以为自己免税。

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
| `skill-multi-copy` | 同一个技能在多个 harness 目录各存一份，且内容开始漂移 |
| `skill-unreachable` | 描述缺失 / 过短，模型永远发现不了 |
| `skill-generic` | 描述里全是"各种 / 万能 / helps with"，到处乱触发 |
| `skill-no-disclosure` | 正文超过 3,000 tokens 且没有 `references/` |
| `skill-thin` | 正文不足 60 tokens，那不是技能，是便签 |
| `skill-name-mismatch` | frontmatter 的 `name` 与目录名不一致，敲目录名调用不出来 |
| `skill-stale` | 半年没动过，多半在按旧世界的地图指路 |

`skill-overlap` 有两个必须承认的边界，写在这里以免你被自己的工具骗：

- **描述太短就不判。** 去掉虚词后不足 4 个实质词的描述，词集太小，重合度算不出
  可信结果。两个 "Use this skill to create X" 共享一个词就能凑出 100%，那是数学，
  不是证据。
- **规模悬殊就不判。** `overlap_coefficient` 除以较小的集合，所以"3 个词 vs 77 个词"
  也能算出 100%。集合规模差 3 倍以上时这个指标直接作废。

宁可不报，也不给你 55 条"自己跟自己打架"的假警报。

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
- **重复副本只算一次**。同一个技能在三个 harness 目录各存一份，运行时只会加载
  其中一份，所以不按三份收税。这类重复单独报，不算进钱里。
- **`--plugins` 是个上限**。插件缓存里的技能未必全被启用，所以这个开关算出来的
  是"最多这么多"，不是"一定这么多"。

## 作为技能使用

```bash
npx skills add Romantic-haitang/context-tax
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
