#!/usr/bin/env bash
# 把 context-tax 装成本地技能。优先符号链接（改代码即时生效），失败则拷贝。
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="context-tax"
TARGETS=("$HOME/.claude/skills" "$HOME/.agents/skills")

echo "源目录: $SRC"
installed=0

for base in "${TARGETS[@]}"; do
  mkdir -p "$base"
  dest="$base/$NAME"
  rm -rf "$dest"
  if ln -s "$SRC" "$dest" 2>/dev/null; then
    echo "  链接 -> $dest"
  else
    cp -R "$SRC" "$dest"
    echo "  拷贝 -> $dest"
  fi
  installed=$((installed + 1))
done

if [ "$installed" -eq 0 ]; then
  echo "没有找到可安装的目标目录，手动把仓库复制到你的 skills 目录即可。" >&2
  exit 1
fi

cat <<'TIP'

装好了。重启你的 agent，然后试试：

  帮我看看我的 agent 配置是不是太胖了

其他 harness：
  Codex    把本仓库路径加进 ~/.codex/ 下任意被扫描的位置，或直接 `python3 -m context_tax .`
  Cursor   把 SKILL.md 的正文贴进 .cursor/rules/context-tax.mdc，alwaysApply: false
  任意 CLI  python3 -m context_tax /你的项目 --global
TIP
