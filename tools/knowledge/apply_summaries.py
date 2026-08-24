#!/usr/bin/env python3
"""Apply backfilled `compact_summary` values to cards, from staged JSON batches.

Summarising 951 cards is agent work; *writing* 951 YAML frontmatters is not.
Agents drop `{id: summary}` batches into `.knowledge/.stage/summaries/*.json`
and this script does the single, auditable write pass -- so a malformed
summary can never corrupt a card, and a re-run is a no-op.

    python3 tools/knowledge/apply_summaries.py --check   # report only, write nothing
    python3 tools/knowledge/apply_summaries.py           # apply

Only the `compact_summary:` line is touched. Every other frontmatter key, key
order, and the entire body are preserved byte-for-byte -- the file is edited
as text, never round-tripped through a YAML dumper (which would reflow
quoting, drop comments, and reorder keys across all 951 files).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CARDS = ROOT / ".knowledge" / "cards"
BATCHES = ROOT / ".knowledge" / ".stage" / "summaries"

FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)
ID_RE = re.compile(r"^id:\s*(.+?)\s*$", re.M)
SUMMARY_RE = re.compile(r"^compact_summary:.*(?:\n[ \t]+.*)*$", re.M)

# A summary that fails these is a summariser bug, not a card to silently skip.
MAX_LEN = 220
MIN_LEN = 20


def load_batches() -> tuple[dict[str, str], list[str]]:
    """Merge every staged batch. Later files win; collisions are reported."""
    merged: dict[str, str] = {}
    problems: list[str] = []
    if not BATCHES.is_dir():
        sys.exit(f"no batch directory: {BATCHES}")
    # `_manifest.json` and friends are inputs to the summarisers, not batches.
    for path in sorted(p for p in BATCHES.glob("*.json") if not p.name.startswith("_")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: invalid JSON ({exc})")
            continue
        if not isinstance(data, dict):
            problems.append(f"{path.name}: top level is not an object")
            continue
        # Batches carry {summaries, low_information, prune_candidates};
        # a bare {id: summary} map is also accepted.
        entries = data.get("summaries") if "summaries" in data else data
        if not isinstance(entries, dict):
            problems.append(f"{path.name}: 'summaries' is not an object")
            continue
        for cid, summary in entries.items():
            if cid in merged and merged[cid] != summary:
                problems.append(f"{cid}: conflicting summaries in two batches")
            merged[cid] = summary
    return merged, problems


def validate(cid: str, summary: object) -> str | None:
    """Return an error string, or None if the summary is usable."""
    if not isinstance(summary, str):
        return f"{cid}: not a string"
    s = summary.strip()
    if len(s) < MIN_LEN:
        return f"{cid}: too short ({len(s)} chars)"
    if len(s) > MAX_LEN:
        return f"{cid}: too long ({len(s)} chars)"
    if "\n" in s:
        return f"{cid}: contains a newline"
    if s.lower().startswith(("this card", "the card", "a card")):
        return f"{cid}: describes the card instead of the subject"
    return None


def yaml_scalar(s: str) -> str:
    """Single-quoted YAML scalar -- safe for colons, #, brackets, leading %."""
    return "'" + s.replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only")
    args = ap.parse_args()

    summaries, problems = load_batches()
    print(f"staged summaries : {len(summaries)}")

    by_id: dict[str, Path] = {}
    for path in CARDS.glob("*.md"):
        m = ID_RE.search(path.read_text(encoding="utf-8-sig"))
        if m:
            by_id[m.group(1).strip().strip("'\"")] = path
    print(f"cards on disk    : {len(by_id)}")

    unknown = sorted(set(summaries) - set(by_id))
    missing = sorted(set(by_id) - set(summaries))
    invalid = [e for cid, s in summaries.items() if (e := validate(cid, s))]

    written = skipped = 0
    for cid, summary in sorted(summaries.items()):
        if cid not in by_id or validate(cid, summary):
            continue
        path = by_id[cid]
        # utf-8-sig strips a leading BOM. FM_RE anchors `^---` at offset 0,
        # so a BOM-prefixed card would otherwise be permanently unwritable --
        # reported as "no parseable frontmatter" on every run, forever.
        text = path.read_text(encoding="utf-8-sig")
        m = FM_RE.match(text)
        if not m:
            problems.append(f"{cid}: no parseable frontmatter")
            continue
        fm, body = m.group(1), m.group(2)
        line = f"compact_summary: {yaml_scalar(summary.strip())}"
        if SUMMARY_RE.search(fm):
            new_fm = SUMMARY_RE.sub(lambda _: line, fm, count=1)
        else:
            # Keep it next to the other summary-ish keys rather than appended.
            new_fm = fm.rstrip("\n") + "\n" + line
        if new_fm == fm:
            skipped += 1
            continue
        if not args.check:
            path.write_text(f"---\n{new_fm}\n---\n{body}", encoding="utf-8")
        written += 1

    print(f"{'would write' if args.check else 'written'}     : {written}")
    print(f"already current  : {skipped}")
    print(f"cards still without a summary: {len(missing)}")
    for label, items in (
        ("unknown ids (no such card)", unknown),
        ("invalid summaries", invalid),
        ("problems", problems),
    ):
        if items:
            print(f"\n{label}: {len(items)}")
            for i in items[:15]:
                print(f"  {i}")
    # 0 = everything applied. 2 = some applied, some rejected. 1 = nothing
    # applied. Collapsing 1 and 2 hid the difference between "this batch is
    # broken, look at it" and "most of it landed, these few need attention" --
    # a caller that only checks non-zero treats a 95%-successful run as a
    # total failure and re-runs it.
    if not (unknown or invalid or problems):
        return 0
    return 2 if (written or skipped) else 1


if __name__ == "__main__":
    raise SystemExit(main())
