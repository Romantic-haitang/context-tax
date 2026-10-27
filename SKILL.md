---
name: context-tax
description: Audit an agent setup for context that gets paid for every turn but never earns its keep — skill descriptions, MCP tool definitions, and instruction files. Use when the user asks why their agent feels slow, expensive, or forgetful; wants to trim CLAUDE.md / AGENTS.md / rules files; is installing many skills or MCP servers; or asks for a context, token, or cost audit. Not for debugging one specific failing prompt, not for model selection, and not for optimizing application code.
version: 0.1.0
license: MIT
---

# Context tax

你的配置每轮都在缴税。这个技能负责把税单算出来，然后告诉你哪几笔是可以退的。

## 先跑，再说话

不要凭印象评价一份配置。先执行：

```bash
python3 <skill_dir>/scripts/run.py <项目根目录> --no-color
```

需要包含全局配置（`~/.claude`、`~/.agents`、`~/.codex`、`~/.cursor`、`~/.workbuddy`）时加 `--global`。
宿主插件自带的技能（往往是大头）要加 `--plugins` 才会算进去；不加时报告末尾会提示有多少个没计入。

如果用户问的是"为什么这么贵"，加 `--requests 3000 --price <实际单价>` 再跑一次，用他的真实数字说话。

## 三层结论，按顺序说

1. **常驻税**：每轮全额注入的部分。看税负率落在哪一档，以及构成里谁占大头。
   - 大头可能是 MCP 工具定义，也可能是技能描述——两种都见过，别预设结论，看输出。
2. **触发税**：技能正文。只在被选中时付一次，但一次就够呛。
3. **正确性问题**：描述打架、描述缺失、技能太薄、多份副本漂移。这些问题省不了多少 token，
   但它们让 agent 选错工具——比贵更糟。

## 铁律

- **只读**。这个技能不修改任何用户文件，也不建议"我帮你改好了"。改由用户决定。
- **不编数字**。所有数字来自脚本输出。脚本标了 `~` 的，你要说"估算"。
- **不给没有落点的建议**。"建议优化配置"是废话，"把 7 台 server 砍到 4 台，省 9,000 tokens"
  才是建议。
- **先给最大的那笔账**。用户不关心第 6 个 nit，关心那个占 92% 的东西。

## 输出格式

```
税负率 9.7%（中度）· 每月约 2,900 万 tokens 常驻
最大的一笔：8 台 MCP server 的工具定义，占 92.7%

1. 砍到 4 台核心 server        -9,000 tok/轮
2. CLAUDE.md 与 AGENTS.md 重复  -502 tok/轮
3. 三个 review 技能互相打架     选错技能的代价比 token 更贵
...
```

三到五条，按"省多少"排序。每条必须有：动作、对象、数字。

## 判读细则

阈值、等级含义、以及"看到 X 该说什么"，见 `references/interpretation.md`。
MCP 那部分的估算模型和争议点，见 `references/mcp-tokens.md`。

## 反模式

- 把"技能正文很大"说成常驻开销。它不在常驻里，别混。
- 建议删掉所有技能。技能本身不贵，烂技能才贵。
- 拿税负率当质量分。一个 3% 的配置可能全是废话，一个 12% 的配置可能每个字都在干活。
- 忽略 prompt cache。开了缓存之后常驻部分的实际单价是 0.1x，你的"月省 $50"会变成 $5。
  脚本已经按 `--cache-hit` 折算过了，别自己再乘一遍。
