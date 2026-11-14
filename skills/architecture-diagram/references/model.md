# Model file format (`*.arch.json`)

Pretty-printed JSON (2-space indent). The editor rewrites the whole file on every
save in that format, so git diffs stay readable.

```json
{
  "version": 1,
  "title": "learning-hub crates",
  "kinds": {
    "binary":   {"label": "Binary",     "color": "blue"},
    "module":   {"label": "Module",     "color": "violet"},
    "lib":      {"label": "Shared lib", "color": "teal"},
    "adapter":  {"label": "Adapter",    "color": "orange"},
    "store":    {"label": "Data store", "color": "cyan"},
    "external": {"label": "External",   "color": "grape"},
    "note":     {"label": "Note",       "color": "yellow"}
  },
  "groups": [
    {"id": "clients", "label": "Clients"},
    {"id": "modules", "label": "Modules"}
  ],
  "nodes": [
    {
      "id": "hub-service",
      "name": "hub-service",
      "kind": "binary",
      "group": "core",
      "summary": "Wires modules, owns the DB",
      "job": "Holds the one SQLite connection. Coordinates cross-module work using IDs.",
      "data": "events, module_versions, meta",
      "status": "agreed",
      "x": 200, "y": 260,
      "thread": [
        {"by": "user",   "text": "Should hub-runner stay in this process?", "at": "2026-11-14T10:02:00Z"},
        {"by": "claude", "text": "Yes for now: runs are rare ...",          "at": "2026-11-14T10:05:00Z"}
      ]
    }
  ],
  "edges": [
    {"id": "hub-web->hub-client", "from": "hub-web", "to": "hub-client", "kind": "depends on",
     "why": "typed requests over the socket", "thread": []}
  ],
  "rules": [
    {"id": "clients-only-client", "from": "group:clients", "only": ["id:hub-client", "id:hub-contract"],
     "text": "Clients talk to the service only through hub-client (spec §4)."},
    {"id": "no-module-to-module", "from": "group:modules", "to": "group:modules",
     "text": "No module depends on another module."}
  ]
}
```

## Fields

**Node.** Only `id`, `name` and `kind` are needed.
- `id`: stable key (lowercase, hyphens). Never change it to rename; change `name`.
- `kind`: a key of `kinds`. Add kinds freely (`queue`, `ui`, `job`...). The
  `color` is a Mantine color name (blue, cyan, teal, green, lime, yellow,
  orange, red, pink, grape, violet, indigo, gray) or a `#hex`.
- `group`: the id of a `groups` entry. The editor draws a labeled box around
  the members.
- `summary`: one short line shown on the card. `job`: responsibilities,
  including what it must never do. `data`: what data or tables it owns.
- `status`: `proposed`, `agreed` or `rejected`, or absent. Shown on the card.
  Rejected nodes are faded.
- `x`, `y`: top-left position in canvas pixels. Cards are 160 px wide; the
  default spacing is 200 px across and 130 px down. Leave both out to have the
  editor place the node, then it saves the position back.
- `thread`: the conversation about this node, oldest first.

**Edge.** `from` depends on / calls / sends to `to`, and the arrow points at
`to`. `kind` defaults to `depends on` (solid); any other kind draws dashed with
its label. The editor offers `calls`, `sends events to`, `reads data from` and
`writes data to`, and keeps any custom kind you write. `why` says what crosses
the boundary. `id` is `from->to`.

**Rules.** Each rule checks every edge whose source matches `from`:
- With `to`: the edge breaks the rule if its target matches `to` (a forbid
  rule).
- With `only`: the edge breaks the rule if its target matches none of the
  selectors (an allow-list).
- Optional `edgeKind` limits a rule to one edge kind.
- Selectors: `*`, `id:<id>`, `kind:<kind>`, `group:<group>`.

Rule-breaking edges draw red, and the top bar shows the count. `check` exits 1
when any rule is broken, so it can run in CI.

## Threads and open questions

A thread is open when its last message has `"by": "user"`. `summary` lists open
threads. `diff` prints new messages since the base round as `? <target> [by]:
text`. To answer, append a `claude` message; don't edit or delete the user's
messages.

## Rounds

`round` copies the model to `<topic>.rounds/round-N.json` with
`"_round": {"n", "by", "at"}`. Rounds are taken at hand-offs: Claude after each
revision (`--by claude`), the user with **Send to Claude** (`by: user`). Two
defaults follow from that:
- `diff`, run by Claude, compares against the last round Claude took, so it
  shows everything the user did since.
- The editor's Review mode compares against the last round the user sent, so it
  shows everything Claude did since. Any round can be picked in the dropdown.
