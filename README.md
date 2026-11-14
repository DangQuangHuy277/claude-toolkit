# claude-toolkit

My personal Claude Code setup: skills, agents and slash commands that I want on every machine.

## Set up a machine

```bash
git clone https://github.com/DangQuangHuy277/claude-toolkit.git ~/Code/Personal/claude-toolkit
~/Code/Personal/claude-toolkit/install.sh
```

`install.sh` symlinks each item into `~/.claude/` (or `$CLAUDE_CONFIG_DIR`). Paths that already exist are skipped. `--force` moves them aside first, and `--dry-run` shows what would happen. Because the items are symlinks, editing a skill in place edits the repo. Commit and push the change, then `git pull` on the other machines. Run `install.sh` again after you add a new item.

## Layout

| Folder | Becomes | Contents |
|---|---|---|
| `skills/<name>/` | `~/.claude/skills/<name>` | A folder with a `SKILL.md`, plus any `scripts/`, `references/` and `assets/` |
| `agents/*.md` | `~/.claude/agents/` | Subagent definitions |
| `commands/*.md` | `~/.claude/commands/` | Slash commands |

## Skills

| Skill | What it does | Needs |
|---|---|---|
| [architecture-diagram](skills/architecture-diagram/SKILL.md) | Interactive architecture diagram that you and Claude refine over rounds. Claude writes a `.arch.json` model and serves a local drag-and-drop editor where you add, connect and annotate components and ask questions pinned to them. Claude reads back what changed. Rule checks, round diffs, Mermaid export. | Python 3 (standard library only) |
