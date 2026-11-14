#!/usr/bin/env bash
# Link everything in this repo into ~/.claude so Claude Code picks it up.
# Symlinks, not copies: edit here, commit, and `git pull` on other machines.
#
#   ./install.sh           link anything not yet linked; skip paths that already exist
#   ./install.sh --force   move existing paths aside (to <path>.bak-<time>) and link
#   ./install.sh --dry-run show what would happen
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
FORCE=0
DRY=0
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    --dry-run) DRY=1 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

run() { if [ "$DRY" = 1 ]; then echo "  would: $*"; else "$@"; fi; }

link() {
  local src="$1" dst="$2"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    echo "ok       $dst"
    return
  fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    if [ "$FORCE" = 1 ]; then
      local bak="$dst.bak-$(date +%Y%m%d%H%M%S)"
      echo "backup   $dst -> $bak"
      run mv "$dst" "$bak"
    else
      echo "skip     $dst exists (use --force to replace it)"
      return
    fi
  fi
  echo "link     $dst -> $src"
  run mkdir -p "$(dirname "$dst")"
  run ln -s "$src" "$dst"
}

# skills/<name>/      -> ~/.claude/skills/<name>
for d in "$REPO"/skills/*/; do
  [ -f "$d/SKILL.md" ] || continue
  d="${d%/}"
  link "$d" "$CLAUDE_DIR/skills/$(basename "$d")"
done

# agents/*.md, commands/*.md -> ~/.claude/agents, ~/.claude/commands
for kind in agents commands; do
  for f in "$REPO/$kind"/*.md; do
    [ -f "$f" ] || continue
    link "$f" "$CLAUDE_DIR/$kind/$(basename "$f")"
  done
done
