#!/usr/bin/env python3
"""The thin layer: find the 2-4 cards that matter, without reading anything big.

Reads only .knowledge/.cache/*.json. Returns card *references* — the caller
decides what to open. `--show` is the one command that prints a body.

    ctx.py "reconnect banner"              search
    ctx.py --for frontend/hooks/x.ts       everything touching a file
    ctx.py --rules sse                     rules in force for an area
    ctx.py --show FIX-122                  print one card
    ctx.py --check                         freshness + orphans

Exit codes: 0 found / 1 nothing matched / 2 index missing or stale.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import (  # type: ignore[import-not-found]  # noqa: E402
    CARD_TYPES,
    cache_dir,
    knowledge_dir,
    read_json,
    repo_root,
)

TYPE_LABEL = {
    "decision": "rule ", "fix": "fix  ", "issue": "issue", "phase": "phase",
    "bug": "bug  ", "test": "test ", "req": "req  ", "doc": "doc  ", "task": "task ",
}
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "of",
    "and", "or", "for", "it", "this", "that", "with", "when", "why", "how",
}


def _load(root: Path):
    cdir = cache_dir(root)
    index = read_json(cdir / "index.json")
    if isinstance(index, dict):          # wrapped form: {generated, facets, entries}
        index = index.get("entries", [])
    links = read_json(cdir / "links.json", {})
    if index is None:
        print(
            "error: no index. Run: python3 scripts/knowledge/build_index.py",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return index, links


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in STOPWORDS}


# Migrating all of .planning/ added 292 secondary cards, and pointer cards (doc,
# task) match on title words while carrying no detail. Without a type prior they
# outrank the fix that actually explains the bug. Answer-bearing types rank first.
TYPE_WEIGHT = {
    "decision": 30, "fix": 22, "issue": 18, "bug": 16,
    "phase": 8, "test": 6, "req": 6, "doc": 0, "task": 0,
}


def score(card: dict, terms: list[str]) -> int:
    """Cheap lexical ranking. Deliberately dumb — the summaries do the work."""
    hay_id = card["id"].lower()
    hay_area = " ".join(card.get("area", [])).lower()
    hay_files = " ".join(card.get("files", [])).lower()
    hay_sum = card.get("summary", "").lower()
    sum_tokens = _tokens(hay_sum)

    total = 0
    for raw in terms:
        t = raw.lower()
        hit = 0
        if t == hay_id:
            hit += 100
        elif t in hay_id:
            hit += 40
        if t in hay_area.split():
            hit += 25
        if t in hay_files:
            hit += 15
        # Prefix match, not exact: "reconnect" must find "Reconnecting". Without
        # this the most on-point card ranks below a passing mention of it.
        if t in sum_tokens:
            hit += 12
        elif any(w.startswith(t) or t.startswith(w) for w in sum_tokens if len(w) > 3):
            hit += 10
        elif t in hay_sum:
            hit += 6
        total += hit
    # prefer cards matching more of the query, not just one term loudly
    matched = sum(
        1
        for raw in terms
        if raw.lower() in f"{hay_id} {hay_area} {hay_files} {hay_sum}"
    )
    if total == 0:
        return 0
    return total + matched * 8 + TYPE_WEIGHT.get(card["type"], 0)


def fmt(card: dict, width: int = 92) -> str:
    label = TYPE_LABEL.get(card["type"], card["type"][:5])
    area = ",".join(card.get("area", [])) or "-"
    status = card.get("status") or "-"
    summary = card.get("summary", "")
    if len(summary) > width:
        summary = summary[: width - 1].rstrip() + "…"
    return f"{card['id']:<10} {label} {status:<9} [{area}] {summary}"


def emit(cards: list[dict], header: str = "") -> int:
    if not cards:
        print("no matching cards")
        return 1
    if header:
        print(header)
    for c in cards:
        print(fmt(c))
    print(f"\n{len(cards)} card(s). Open one: ctx.py --show <ID>")
    return 0


def cmd_show(index: list[dict], root: Path, card_id: str) -> int:
    match = next((c for c in index if c["id"].lower() == card_id.lower()), None)
    if not match:
        near = [c["id"] for c in index if card_id.lower() in c["id"].lower()][:5]
        print(f"no card {card_id!r}" + (f" — did you mean: {', '.join(near)}" if near else ""))
        return 1
    # Header first (cheap, always available), then the prose fetched from source.
    for key in ("id", "type", "status", "date", "area", "files", "source", "summary"):
        val = match.get(key)
        if val:
            print(f"{key}: {', '.join(val) if isinstance(val, list) else val}")
    print()
    path = root / match["path"]
    if path.is_file():
        print(path.read_text(encoding="utf-8"))
        return 0
    recs = read_json(cache_dir(root) / "bodies.json", {}) or {}
    if match["id"] in recs:
        print(recs[match["id"]])
        return 0
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from records import resolve_body  # type: ignore[import-not-found]  # noqa: PLC0415

    print(resolve_body(match, root))
    return 0


def cmd_for(index: list[dict], links: dict, path_arg: str) -> int:
    by_file = links.get("by_file", {})
    wanted = path_arg.strip().lstrip("./")
    ids: set[str] = set()
    for f, card_ids in by_file.items():
        if f.endswith(wanted) or wanted.endswith(f) or wanted in f:
            ids.update(card_ids)
    cards = [c for c in index if c["id"] in ids]
    # rules first, then newest history
    cards.sort(key=lambda c: (c["type"] != "decision", c.get("date", ""), c["id"]), reverse=False)
    rules = [c for c in cards if c["type"] == "decision"]
    rest = sorted(
        [c for c in cards if c["type"] != "decision"],
        key=lambda c: c.get("date", ""),
        reverse=True,
    )
    return emit(rules + rest, header=f"cards touching {wanted}:")


def cmd_rules(index: list[dict], area: str | None) -> int:
    rules = [c for c in index if c["type"] == "decision" and c.get("status") != "superseded"]
    if area:
        rules = [c for c in rules if area.lower() in [a.lower() for a in c.get("area", [])]]
    rules.sort(key=lambda c: c["id"])
    return emit(rules, header=f"rules in force{f' for {area}' if area else ''}:")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="ctx.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("terms", nargs="*", help="search terms")
    p.add_argument("--for", dest="for_file", metavar="PATH", help="cards touching a file")
    p.add_argument("--rules", nargs="?", const="", metavar="AREA", help="rules in force")
    p.add_argument("--show", metavar="ID", help="print one card body")
    p.add_argument("--type", choices=CARD_TYPES, help="filter by type")
    p.add_argument("--limit", type=int, default=8, help="max results (default 8)")
    p.add_argument("--check", action="store_true", help="run the freshness check")
    p.add_argument("--root", help="repo root (default: git toplevel)")
    args = p.parse_args(argv[1:])

    root = Path(args.root).resolve() if args.root else repo_root()

    if args.check:
        import check  # type: ignore[import-not-found]  # noqa: PLC0415

        return check.main(["check.py", str(root)])

    if not knowledge_dir(root).is_dir():
        print(f"error: no .knowledge/ at {knowledge_dir(root)}", file=sys.stderr)
        return 2

    index, links = _load(root)

    if args.show:
        return cmd_show(index, root, args.show)
    if args.for_file:
        return cmd_for(index, links, args.for_file)
    if args.rules is not None:
        return cmd_rules(index, args.rules or None)
    if not args.terms:
        p.print_help()
        return 0

    # `ctx.py "reconnect banner"` arrives as ONE argv entry. Left unsplit it is
    # matched as a single literal and finds nothing — and quoting is exactly what
    # the docs tell people to do.
    terms = [w for raw in args.terms for w in raw.split() if w]

    pool = [c for c in index if not args.type or c["type"] == args.type]
    ranked = sorted(
        ((score(c, terms), c) for c in pool), key=lambda t: (-t[0], t[1]["id"])
    )
    hits = [c for s, c in ranked if s > 0][: args.limit]
    return emit(hits, header=f"matches for {' '.join(terms)!r}:")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
