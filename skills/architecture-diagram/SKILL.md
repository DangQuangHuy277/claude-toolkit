---
name: architecture-diagram
description: Interactive, editable architecture diagram that Claude and the user refine together over several rounds until it is the architecture to implement. Claude writes a component model (.arch.json) and opens a local drag-and-drop canvas editor; the user adds, moves, connects and annotates components and asks questions pinned to them; Claude reads back exactly what changed, answers, and proposes the next revision. Use this whenever the user wants to design, sketch, review, discuss or iterate on an architecture, system design, component or module layout, service boundaries or dependency structure, or wants a diagram they can edit themselves, even if they only say "let's draw the architecture", "diagram this", "check the diagram" or "I changed the diagram".
---

# Architecture diagram

The diagram is a shared working document, not an illustration. The goal is to
converge, round by round, on an architecture the user is ready to implement. The
file is the source of truth; the editor and Claude both read and write it.

## Pieces

- `scripts/archdiagram.py` (Python 3, standard library only). Run it with the
  path to the model file. Subcommands: `new`, `serve`, `summary`, `diff`,
  `round`, `check`, `mermaid`.
- `assets/editor.html`: the canvas editor that `serve` hosts on `127.0.0.1`.
  It autosaves to the file, and it reloads within a couple of seconds when the
  file changes on disk, so Claude's edits appear without a refresh.
- `references/model.md`: the file format, rules syntax, and how threads work.
  Read it before writing or editing a model.

`SKILL=~/.claude/skills/architecture-diagram` below.

## Where the file lives

In a repository, put it in the docs next to the design it belongs to, for
example `docs/architecture/<topic>.arch.json`, and follow the project's own
docs layout when it has one. Commit the `.arch.json` and its `<topic>.rounds/`
folder with the design: the rounds are the history of the discussion. Outside a
repository, use the current folder. Ask only if the location is truly unclear.

## Workflow

### 1. First draft

1. Understand what is being designed. In an existing codebase, read the real
   structure first (modules, crates, packages, services, the spec that governs
   them) so the draft reflects reality, and note the spec's constraints as
   `rules` so violations show up in red while the user edits.
2. Write the model with the Write tool (`references/model.md`). Leave out `x`/`y`
   and the editor lays nodes out by dependency depth. Use `group`s for layers
   or boundaries, `summary` for the one line shown on the card, `job` for the
   longer responsibility, `status: "proposed"` for things you are suggesting
   rather than describing. Where you are unsure, ask your question in that
   node's `thread` instead of guessing silently.
3. `python3 $SKILL/scripts/archdiagram.py round <file> --by claude` to save
   round 1.
4. Start the editor in the background (Bash with `run_in_background: true`):
   `python3 $SKILL/scripts/archdiagram.py serve <file>`. It prints one JSON line
   with the `url`. Read the background output to get it, then open that URL in
   the browser pane if one is available (in the Claude desktop app:
   `preview_start` with `url`), and also give the user the URL.
5. Tell the user, briefly, how to work: double-click empty space to add,
   click a node's `+` to add a component it depends on, drag the `+` onto
   another node to connect, double-click a node or arrow to open details and
   the **Ask** tab, **Send to Claude** when done, then say "check the
   diagram" in the chat.

### 2. Each round after that

When the user says they changed the diagram, sent it, or asks you to check it:

1. `python3 $SKILL/scripts/archdiagram.py diff <file>`: what changed since your
   last round, including new questions (lines starting with `?`).
2. `python3 $SKILL/scripts/archdiagram.py summary <file>` when you need the
   whole picture: components grouped, dependencies, open questions, rule
   violations. Prefer these two over reading the raw JSON, which is mostly
   coordinates.
3. Respond in two places:
   - **In the file:** answer each open question by appending
     `{"by": "claude", "text": "...", "at": "<ISO time>"}` to that node's or
     edge's `thread`, and make the changes you propose. Edit with the Edit tool
     and keep `x`/`y` of nodes the user placed. They arranged them on purpose.
   - **In the chat:** a short account of what you saw and what you changed, and
     anything that needs a decision. Disagree openly when a change breaks a rule
     or a stated goal; explain the consequence and let the user decide.
4. `round <file> --by claude` so the user's **Review** mode shows exactly what
   you changed.

The editor's **Review** mode compares the current file to a chosen round and
colors added, changed and removed components and arrows. It also lists rule
violations, so the user rarely needs you to explain what moved.

### 3. Finishing

When the user is happy, mark agreed components `"status": "agreed"` and drop or
mark rejected ones, take a final round, and offer what helps next:
`mermaid <file>` to embed a diagram in the spec, a written summary of
responsibilities and dependencies, or an implementation plan.

## Things to get right

- **Edits from both sides.** The editor saves through a version check, so if
  you edit the file while the user is mid-edit, their next save is refused and
  the editor reloads your version. Keep your edits quick, batched, and in
  between the user's rounds rather than during them.
- **Stable ids.** Node `id`s are what diffs, edges and rules key on. Rename with
  `name`, never by changing `id`.
- **Coordinates.** When you add nodes, either leave out `x`/`y` (placed
  automatically next to their depth level) or place them near related nodes.
  Don't relayout the user's diagram unless they ask.
- **Questions are the discussion.** A question in a thread whose last message is
  from the user is open. `summary` lists them. Answer all of them every round,
  even if only to say it needs the user's decision.
- **The server.** One `serve` per file. If the user reports the page is not
  reachable, check whether the background process is still running and
  restart it. The page keeps working offline but cannot save.
