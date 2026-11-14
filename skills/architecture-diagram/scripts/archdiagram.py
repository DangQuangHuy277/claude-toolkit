#!/usr/bin/env python3
"""Architecture diagram helper: local editor server plus text views for Claude.

Standard library only. Subcommands:
  serve   <model.arch.json> [--port N]   run the canvas editor on 127.0.0.1
  summary <model.arch.json>              compact text view: components, deps, open questions, rule problems
  diff    <model.arch.json> [--base R]   what changed since a round (default: the last round Claude took)
  round   <model.arch.json> --by claude|user   snapshot the current model as the next round
  check   <model.arch.json>              rule violations only (exit 1 if any)
  mermaid <model.arch.json>              Mermaid flowchart for docs
  new     <model.arch.json> --title T    write an empty model
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
EDITOR = HERE.parent / "assets" / "editor.html"

DEFAULT_KINDS = {
    "binary": {"label": "Binary", "color": "blue"},
    "module": {"label": "Module", "color": "violet"},
    "lib": {"label": "Shared lib", "color": "teal"},
    "adapter": {"label": "Adapter", "color": "orange"},
    "store": {"label": "Data store", "color": "cyan"},
    "external": {"label": "External", "color": "grape"},
    "note": {"label": "Note", "color": "yellow"},
}


# ---------- model io ----------

def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def dump(model: dict) -> bytes:
    return (json.dumps(model, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def version_of(raw: bytes) -> str:
    return hashlib.sha1(raw).hexdigest()[:16]


def load(path: Path) -> dict:
    return normalize(json.loads(path.read_text(encoding="utf-8")))


def normalize(m: dict) -> dict:
    m.setdefault("version", 1)
    m.setdefault("title", "Architecture")
    m.setdefault("kinds", DEFAULT_KINDS)
    m.setdefault("groups", [])
    m.setdefault("nodes", [])
    m.setdefault("edges", [])
    m.setdefault("rules", [])
    for n in m["nodes"]:
        n.setdefault("kind", "module")
        n.setdefault("name", n.get("id", "?"))
    for i, e in enumerate(m["edges"]):
        e.setdefault("id", f"{e.get('from')}->{e.get('to')}")
        e.setdefault("kind", "depends on")
    return m


def write_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    os.replace(tmp, path)


def rounds_dir(path: Path) -> Path:
    stem = path.name[: -len(".arch.json")] if path.name.endswith(".arch.json") else path.stem
    return path.parent / f"{stem}.rounds"


def list_rounds(path: Path) -> list[dict]:
    out = []
    d = rounds_dir(path)
    if not d.is_dir():
        return out
    for f in sorted(d.glob("round-*.json"), key=lambda p: int(p.stem.split("-")[1])):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = data.get("_round", {})
        out.append({"n": int(f.stem.split("-")[1]), "by": meta.get("by", "?"), "at": meta.get("at", ""), "file": str(f)})
    return out


def take_round(path: Path, by: str) -> int:
    model = load(path)
    rs = list_rounds(path)
    n = (rs[-1]["n"] + 1) if rs else 1
    snap = dict(model)
    snap["_round"] = {"n": n, "by": by, "at": now()}
    write_atomic(rounds_dir(path) / f"round-{n}.json", dump(snap))
    return n


def load_round(path: Path, n: int) -> dict:
    return normalize(json.loads((rounds_dir(path) / f"round-{n}.json").read_text(encoding="utf-8")))


# ---------- rules / diff / questions ----------

def matches(sel: str, node: dict) -> bool:
    if sel == "*":
        return True
    key, _, val = sel.partition(":")
    return {"id": node.get("id"), "kind": node.get("kind"), "group": node.get("group")}.get(key) == val


def violations(m: dict) -> list[str]:
    nodes = {n["id"]: n for n in m["nodes"]}
    out = []
    for e in m["edges"]:
        a, b = nodes.get(e.get("from")), nodes.get(e.get("to"))
        if a is None or b is None:
            out.append(f"edge {e.get('id')} points at a missing component")
            continue
        for r in m["rules"]:
            if r.get("edgeKind") and r["edgeKind"] != e.get("kind"):
                continue
            if not matches(r.get("from", "*"), a):
                continue
            if "only" in r:
                bad = not any(matches(s, b) for s in r["only"])
            else:
                bad = matches(r.get("to", "*"), b)
            if bad:
                out.append(f"{a['name']} -> {b['name']}: {r.get('text', r.get('id', 'rule'))}")
    return out


DETAIL_FIELDS = ("name", "kind", "group", "summary", "job", "data", "status")


def diff(old: dict, new: dict) -> list[str]:
    out = []
    on, nn = {n["id"]: n for n in old["nodes"]}, {n["id"]: n for n in new["nodes"]}
    for i, n in nn.items():
        if i not in on:
            out.append(f"+ component {n['name']} ({n.get('kind')})")
        else:
            for f in DETAIL_FIELDS:
                if on[i].get(f) != n.get(f):
                    out.append(f"~ {n['name']}.{f}: {on[i].get(f)!r} -> {n.get(f)!r}")
            ot, nt = on[i].get("thread", []), n.get("thread", [])
            for msg in nt[len(ot):]:
                out.append(f"? {n['name']} [{msg.get('by')}]: {msg.get('text')}")
    for i, n in on.items():
        if i not in nn:
            out.append(f"- component {n['name']}")
    name = lambda m, i: next((n["name"] for n in m["nodes"] if n["id"] == i), i)  # noqa: E731
    oe = {(e["from"], e["to"]): e for e in old["edges"]}
    ne = {(e["from"], e["to"]): e for e in new["edges"]}
    for k, e in ne.items():
        if k not in oe:
            out.append(f"+ {name(new, k[0])} -[{e.get('kind')}]-> {name(new, k[1])}")
        else:
            for f in ("kind", "why"):
                if oe[k].get(f) != e.get(f):
                    out.append(f"~ {name(new, k[0])} -> {name(new, k[1])}.{f}: {oe[k].get(f)!r} -> {e.get(f)!r}")
            ot, nt = oe[k].get("thread", []), e.get("thread", [])
            for msg in nt[len(ot):]:
                out.append(f"? {name(new, k[0])} -> {name(new, k[1])} [{msg.get('by')}]: {msg.get('text')}")
    for k, e in oe.items():
        if k not in ne:
            out.append(f"- {name(old, k[0])} -[{e.get('kind')}]-> {name(old, k[1])}")
    return out


def open_questions(m: dict) -> list[str]:
    names = {n["id"]: n["name"] for n in m["nodes"]}
    out = []
    for n in m["nodes"]:
        t = n.get("thread") or []
        if t and t[-1].get("by") == "user":
            out.append(f"[{n['id']}] {n['name']}: {t[-1].get('text')}")
    for e in m["edges"]:
        t = e.get("thread") or []
        if t and t[-1].get("by") == "user":
            out.append(f"[edge {e['id']}] {names.get(e['from'])} -> {names.get(e['to'])}: {t[-1].get('text')}")
    return out


# ---------- text commands ----------

def cmd_summary(path: Path) -> int:
    m = load(path)
    kinds = m["kinds"]
    print(f"# {m['title']}  ({len(m['nodes'])} components, {len(m['edges'])} edges)")
    rs = list_rounds(path)
    if rs:
        print(f"rounds: {', '.join(f'{r['n']}({r['by']})' for r in rs)}")
    groups = {g["id"]: g.get("label", g["id"]) for g in m["groups"]}
    by_group: dict[str, list[dict]] = {}
    for n in m["nodes"]:
        by_group.setdefault(n.get("group") or "", []).append(n)
    deps: dict[str, list[str]] = {}
    names = {n["id"]: n["name"] for n in m["nodes"]}
    for e in m["edges"]:
        lab = names.get(e["to"], e["to"]) + ("" if e["kind"] == "depends on" else f" ({e['kind']})")
        deps.setdefault(e["from"], []).append(lab)
    for g, ns in by_group.items():
        print(f"\n## {groups.get(g, g) or 'Ungrouped'}")
        for n in ns:
            k = kinds.get(n["kind"], {}).get("label", n["kind"])
            line = f"- {n['name']} [{k}] id={n['id']}"
            if n.get("status"):
                line += f" status={n['status']}"
            print(line)
            for f in ("summary", "job", "data"):
                if n.get(f):
                    print(f"    {f}: {n[f]}")
            if deps.get(n["id"]):
                print(f"    -> {', '.join(deps[n['id']])}")
    qs = open_questions(m)
    if qs:
        print("\n## Open questions (last message is from the user)")
        for q in qs:
            print(f"- {q}")
    vs = violations(m)
    if vs:
        print("\n## Rule violations")
        for v in vs:
            print(f"- {v}")
    return 0


def cmd_diff(path: Path, base: int | None) -> int:
    rs = list_rounds(path)
    if base is None:
        mine = [r for r in rs if r["by"] == "claude"]
        if not mine:
            print("no round taken by claude yet; pass --base N" if rs else "no rounds yet")
            return 0
        base = mine[-1]["n"]
    changes = diff(load_round(path, base), load(path))
    print(f"changes since round {base}:" if changes else f"no changes since round {base}")
    for c in changes:
        print(c)
    return 0


def cmd_mermaid(path: Path) -> int:
    m = load(path)
    safe = lambda s: "".join(ch if ch.isalnum() else "_" for ch in s)  # noqa: E731
    print("flowchart TB")
    grouped: dict[str, list[dict]] = {}
    for n in m["nodes"]:
        if n["kind"] != "note":
            grouped.setdefault(n.get("group") or "", []).append(n)
    labels = {g["id"]: g.get("label", g["id"]) for g in m["groups"]}
    for g, ns in grouped.items():
        if g:
            print(f'  subgraph {safe(g)}["{labels.get(g, g)}"]')
        for n in ns:
            print(f'    {safe(n["id"])}["{n["name"]}"]')
        if g:
            print("  end")
    for e in m["edges"]:
        arrow = "-->" if e["kind"] == "depends on" else f"-. {e['kind']} .->"
        print(f"  {safe(e['from'])} {arrow} {safe(e['to'])}")
    return 0


# ---------- server ----------

def make_handler(path: Path):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj).encode())

        def _current(self):
            raw = path.read_bytes()
            return json.loads(raw), version_of(raw)

        def do_GET(self):  # noqa: N802
            p = self.path.split("?")[0]
            if p in ("/", "/index.html"):
                return self._send(200, EDITOR.read_bytes(), "text/html; charset=utf-8")
            if p == "/api/model":
                m, v = self._current()
                return self._json(200, {"model": normalize(m), "version": v, "file": str(path)})
            if p == "/api/version":
                return self._json(200, {"version": version_of(path.read_bytes())})
            if p == "/api/rounds":
                return self._json(200, list_rounds(path))
            if p.startswith("/api/rounds/"):
                try:
                    return self._json(200, load_round(path, int(p.rsplit("/", 1)[1])))
                except (ValueError, OSError):
                    return self._json(404, {"error": "no such round"})
            return self._json(404, {"error": "not found"})

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_PUT(self):  # noqa: N802
            if self.path != "/api/model" or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._json(400, {"error": "bad request"})
            body = self._body()
            cur, v = self._current()
            if body.get("base") != v:
                return self._json(409, {"model": normalize(cur), "version": v})
            raw = dump(normalize(body["model"]))
            write_atomic(path, raw)
            return self._json(200, {"version": version_of(raw)})

        def do_POST(self):  # noqa: N802
            if self.path != "/api/round" or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._json(400, {"error": "bad request"})
            n = take_round(path, "user")
            return self._json(200, {"n": n})

    return H


def cmd_serve(path: Path, port: int) -> int:
    if not path.exists():
        print(f"{path} does not exist; create it first (new subcommand)", file=sys.stderr)
        return 2
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(path))
    print(json.dumps({"url": f"http://localhost:{srv.server_port}/", "file": str(path), "pid": os.getpid()}), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("serve", "summary", "diff", "round", "check", "mermaid", "new"):
        p = sp.add_parser(name)
        p.add_argument("file", type=Path)
        if name == "serve":
            p.add_argument("--port", type=int, default=0)
        if name == "diff":
            p.add_argument("--base", type=int)
        if name == "round":
            p.add_argument("--by", choices=["claude", "user"], default="claude")
        if name == "new":
            p.add_argument("--title", default="Architecture")
    a = ap.parse_args()
    path = a.file.resolve()
    if a.cmd == "new":
        if path.exists():
            print(f"{path} already exists", file=sys.stderr)
            return 2
        write_atomic(path, dump(normalize({"title": a.title})))
        print(path)
        return 0
    if a.cmd == "serve":
        return cmd_serve(path, a.port)
    if a.cmd == "summary":
        return cmd_summary(path)
    if a.cmd == "diff":
        return cmd_diff(path, a.base)
    if a.cmd == "round":
        print(f"round {take_round(path, a.by)} saved")
        return 0
    if a.cmd == "check":
        vs = violations(load(path))
        for v in vs:
            print(v)
        print("no rule violations" if not vs else f"{len(vs)} violation(s)")
        return 1 if vs else 0
    if a.cmd == "mermaid":
        return cmd_mermaid(path)
    return 2


if __name__ == "__main__":
    sys.exit(main())
