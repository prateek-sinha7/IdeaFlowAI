#!/usr/bin/env python3
"""Fold the individual card files into one records.jsonl — and back again.

    python3 scripts/knowledge/compact.py            # cards/*.md -> records.jsonl
    python3 scripts/knowledge/compact.py --prune    # ...and delete the card files
    python3 scripts/knowledge/compact.py --materialize   # write bodies back out
    python3 scripts/knowledge/compact.py --restore  # records.jsonl -> cards/*.md

Nothing is deleted unless `--prune` is passed, and `--restore` reverses it, so this
is a reversible change rather than a one-way door.

`--materialize` exists for one specific decision: if the `.planning/` registers are
ever deleted, the bodies go with them, because records.jsonl stores anchors rather
than prose. Run it first and the prose is written into the store.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import TYPE_DIR, knowledge_dir, load_cards_from_files, repo_root  # type: ignore[import-not-found]  # noqa: E402
from records import load_records, records_path, resolve_body, save_records  # type: ignore[import-not-found]  # noqa: E402

SKIP_FM = {"summary_field"}


def card_to_record(c) -> dict:
    rec: dict = {}
    for k, v in c.fm.items():
        if k in SKIP_FM or v in (None, "", []):
            continue
        rec[k] = v
    rec.setdefault("id", c.id)
    rec.setdefault("type", c.type)
    return rec


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="compact.py")
    ap.add_argument("--prune", action="store_true", help="delete card files after folding")
    ap.add_argument("--restore", action="store_true", help="rebuild card files from records")
    ap.add_argument("--materialize", action="store_true",
                    help="store bodies inline (needed only if .planning/ will be deleted)")
    ap.add_argument("--root")
    args = ap.parse_args(argv[1:])

    root = Path(args.root).resolve() if args.root else repo_root()
    kdir = knowledge_dir(root)

    if args.restore:
        recs = load_records(kdir)
        if not recs:
            print("error: no records.jsonl to restore from", file=sys.stderr)
            return 2
        for rec in recs:
            d = kdir / TYPE_DIR[rec["type"]]
            d.mkdir(parents=True, exist_ok=True)
            fm = ["---"]
            for k, v in rec.items():
                if k == "body":
                    continue
                if isinstance(v, list):
                    fm.append(f"{k}: [{', '.join(str(x) for x in v)}]")
                else:
                    fm.append(f"{k}: {v}")
            fm.append("---")
            body = rec.get("body") or resolve_body(rec, root)
            (d / f"{rec['id']}.md").write_text("\n".join(fm) + "\n\n" + body + "\n", encoding="utf-8")
        print(f"restored {len(recs)} card files from records.jsonl")
        return 0

    if args.materialize:
        recs = load_records(kdir)
        if not recs:
            print("error: no records.jsonl", file=sys.stderr)
            return 2
        n = 0
        for rec in recs:
            if "body" not in rec:
                rec["body"] = resolve_body(rec, root)
                n += 1
        save_records(kdir, recs)
        size = records_path(kdir).stat().st_size / 1024
        print(f"materialized {n} bodies inline · records.jsonl now {size:.0f} KB")
        print("the store no longer depends on .planning/ for prose")
        return 0

    cards = load_cards_from_files(root)
    if not cards:
        print("error: no card files found to fold", file=sys.stderr)
        return 2
    before = sum(c.path.stat().st_size for c in cards)
    save_records(kdir, [card_to_record(c) for c in cards])
    after = records_path(kdir).stat().st_size

    print(f"folded {len(cards)} card files -> records.jsonl")
    print(f"  {before / 1024:>7.0f} KB in {len(cards)} files")
    print(f"  {after / 1024:>7.0f} KB in 1 file  ({100 * (1 - after / before):.0f}% smaller)")
    print("  bodies now resolve from .planning/ on demand (compact.py --materialize to inline)")

    if args.prune:
        removed = 0
        for c in cards:
            c.path.unlink()
            removed += 1
        for d in TYPE_DIR.values():
            p = kdir / d
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        print(f"  pruned {removed} card files (compact.py --restore to bring them back)")

    print("next: python3 scripts/knowledge/build_index.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
