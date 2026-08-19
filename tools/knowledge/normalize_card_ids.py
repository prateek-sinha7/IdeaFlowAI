#!/usr/bin/env python3
"""Normalize every .knowledge/cards/ ID onto {TYPE_CODE}[-{SUBTYPE}]-{rest}.

A deliberate, one-time exception to the "IDs are permanent" rule in
skills/velocity/SKILL.md, approved as a full rename rather than a
supersession chain: the prior scheme had 50+ ad-hoc requirement prefixes,
4 fix shapes and 4 bug shapes, which made book-keeping and lookup
error-prone.

Rule (generic, no per-ID special-casing):

    old_id = "{PREFIX}-{rest}"          (PREFIX = leading [A-Za-z]+ run)
    type_code = TYPE_CODE[card['type']]  (FIX/BUG/ISS/ADR)
    new_id = f"{type_code}-{rest}"            if PREFIX == type_code
             f"{type_code}-{PREFIX}-{rest}"   otherwise

`requirement`, `phase` and `doc` are retired types -- a card carrying one is
reported as an unmapped type, not renumbered. `adr` is its own code again.

ONE substitution pass, not two
-----------------------------
Everything -- each card's own `id:` line, every cross-reference, and every
link to a renamed card file -- is rewritten by a single `re.sub` over each
file's ORIGINAL text. `re.sub` scans left to right and never re-examines
what it just replaced, which is what makes this correct.

Two earlier bugs both came from violating that, and both are guarded here:

  * Double-prefixing. A first pass rewrote `id: AGENTRT-01` to
    `REQ-AGENTRT-01`; a second pass then matched `AGENTRT-01` INSIDE that
    result and produced `REQ-REQ-AGENTRT-01`. One pass cannot do this.

  * Broken links into filenames that merely CONTAIN an id.
    `BUGFIX-NESTED-REVISION.md` is a filename that happens to contain a fix
    ID; substituting inside it renamed a path to a file that was never
    renamed. The ID alternative therefore carries a `(?!\\.md)` lookahead, so
    an ID directly followed by `.md` is left alone -- while renamed CARD files
    are still updated, because full card filenames are matched by their own,
    longer alternative listed first.

Only `.knowledge/cards/*.md` are renamed.

    python3 tools/knowledge/normalize_card_ids.py --check   # report only, no writes
    python3 tools/knowledge/normalize_card_ids.py            # apply

Re-running after a successful run is a no-op (every ID already conforms), so
this doubles as a linter for cards whose prefix does not match their type.
"""
from __future__ import annotations

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CARDS_DIR = os.path.join(ROOT, ".knowledge", "cards")

# The whole schema. `requirement`, `phase` and `doc` are RETIRED -- every card
# of those types was a generated stub pointing into `.planning/`, and all 482
# were deleted rather than migrated. A card of a retired type is an error now,
# not something to renumber.
TYPE_CODE = {
    "fix": "FIX",
    "bug": "BUG",
    "issue": "ISS",
    "adr": "ADR",
}

ID_LINE_RE = re.compile(r"^id:\s*(.+?)\s*$", re.M)
TYPE_LINE_RE = re.compile(r"^type:\s*(.+?)\s*$", re.M)

# Every file that can cite a card ID. Cards are included -- their own `id:`
# line is rewritten by the same single pass as everything else.
# `.planning/` is DELIBERATELY ABSENT and must stay that way. It is a frozen
# archive: no script writes to it, ever. It was listed here once and this pass
# rewrote 1,050 lines across 31 archived files -- rewriting history to match a
# new scheme, and inventing paths (`FIX-BUGFIX-*.md`) that never existed there.
# `.knowledge/docs/` is absent because it no longer exists; it was a bulk copy
# of `.planning/` and was deleted.
REWIRE_GLOBS = [
    ".knowledge/cards/*.md",
    ".knowledge/architecture/*.md",
    ".knowledge/INDEX.md",
    ".knowledge/ARCHITECTURE.md",
    ".knowledge/CONTEXT.md",
    "skills/velocity/*.md",
]


def frontmatter_id_and_type(text):
    m_id = ID_LINE_RE.search(text)
    m_type = TYPE_LINE_RE.search(text)
    if not m_id or not m_type:
        return None, None
    return m_id.group(1).strip("'\""), m_type.group(1).strip("'\"")


def compute_new_id(old_id, card_type):
    type_code = TYPE_CODE.get(card_type)
    if type_code is None:
        return None, f"unmapped type {card_type!r}"
    m = re.match(r"^([A-Za-z]+)-(.*)$", old_id)
    if not m:
        return None, f"id {old_id!r} has no PREFIX-rest shape"
    prefix, rest = m.group(1), m.group(2)
    if prefix.upper() == type_code:
        return f"{type_code}-{rest}", None
    return f"{type_code}-{prefix}-{rest}", None


def load_cards():
    """-> (cards, malformed, skipped).

    A file with frontmatter but no readable `id:`/`type:` is an ERROR.

    Skipping it would rename every other card around it and leave the broken
    one behind -- a partial migration, which is exactly what this script
    refuses to do everywhere else (unmapped type, id collision). A card whose
    identity cannot be read may well be referenced by the cards being
    rewritten, so proceeding risks dangling references that nothing reports.
    """
    cards, malformed, skipped = [], [], []
    for path in sorted(glob.glob(os.path.join(CARDS_DIR, "*.md"))):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            malformed.append((path, f"cannot read file: {exc}"))
            continue
        old_id, card_type = frontmatter_id_and_type(text)
        if old_id is None:
            if not text.lstrip("﻿ \t\r\n").startswith("---"):
                # No frontmatter block at all -> this was never a card. A
                # stray README or scratch note in cards/ should not block a
                # migration; only a file that LOOKS like a card but whose
                # identity cannot be read is dangerous, because other cards
                # may reference it.
                skipped.append(path)
                continue
            malformed.append((path, "has frontmatter but no readable `id:` / `type:`"))
            continue
        cards.append({"path": path, "old_id": old_id, "type": card_type})
    return cards, malformed, skipped


def plan(cards):
    """-> (id_map, file_map, errors, adr_count). Only CHANGED ids are mapped."""
    id_map, file_map, errors = {}, {}, []
    adr_count = 0
    for c in cards:
        new_id, err = compute_new_id(c["old_id"], c["type"])
        if err:
            errors.append((c["path"], err))
            continue
        c["new_id"] = new_id
        c["new_type"] = c["type"]
        if new_id == c["old_id"]:
            continue
        if id_map.get(c["old_id"], new_id) != new_id:
            errors.append((c["path"], f"duplicate old_id {c['old_id']!r} maps two ways"))
            continue
        id_map[c["old_id"]] = new_id

        base = os.path.basename(c["path"])
        suffix = f"{c['old_id']}.md"
        if not base.endswith(suffix):
            errors.append((c["path"], f"filename does not end with {suffix!r}"))
            continue
        new_base = base[: -len(suffix)] + new_id + ".md"
        c["new_base"] = new_base
        file_map[base] = new_base

    # Collision guard. Checked across the FINAL id of EVERY card -- renamed or
    # not -- because the dangerous case is a renamed card landing on an id that
    # another card already holds: `AGENTRT-01` (requirement) normalizes to
    # `REQ-AGENTRT-01`, which collides with a card already called
    # `REQ-AGENTRT-01`. Neither is a "duplicate old_id", so checking the
    # old->new mapping alone misses it entirely and both cards end up sharing
    # one id. IDs are the primary key here; two cards sharing one silently
    # breaks every depends_on/referenced_by/wikilink that points at it.
    final: dict[str, list] = {}
    for c in cards:
        if c.get("new_id"):
            final.setdefault(c["new_id"], []).append(c)
    for fid, group in sorted(final.items()):
        if len(group) > 1:
            names = ", ".join(sorted(os.path.basename(x["path"]) for x in group))
            errors.append((group[0]["path"],
                           f"id collision: {len(group)} cards would share id {fid!r} ({names})"))

    return id_map, file_map, errors, adr_count


def build_regex(id_map, file_map):
    """One alternation: card FILENAMES first (longer/more specific), then IDs.

    The `(?!\\.md)` on the ID branch keeps un-renamed doc filenames intact.
    """
    if not id_map and not file_map:
        return None
    parts = []
    if file_map:
        parts.append("|".join(re.escape(f) for f in sorted(file_map, key=len, reverse=True)))
    if id_map:
        ids = "|".join(re.escape(i) for i in sorted(id_map, key=len, reverse=True))
        parts.append(rf"(?:{ids})\b(?!\.md)")
    return re.compile(rf"(?<![\w.-])(?:{'|'.join(parts)})")


def collect_targets():
    targets = set()
    for pattern in REWIRE_GLOBS:
        for path in glob.glob(os.path.join(ROOT, pattern), recursive=True):
            if os.path.isfile(path):
                targets.add(path)
    return sorted(targets)


def main():
    check = "--check" in sys.argv

    cards, malformed, skipped = load_cards()
    id_map, file_map, errors, adr_count = plan(cards)
    errors = malformed + errors   # an unreadable card aborts, same as any other error

    print(f"Cards loaded:      {len(cards)}")
    if malformed:
        print(f"Unreadable cards:  {len(malformed)}")
    if skipped:
        print(f"Not cards (no frontmatter, ignored): {len(skipped)}")
        for s in skipped[:5]:
            print(f"  - {os.path.relpath(s, ROOT)}")
    print(f"IDs to rename:     {len(id_map)}")
    print(f"Files to rename:   {len(file_map)}")
    print(f"adr -> doc merges: {adr_count}")
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for path, err in errors:
            print(f"  {os.path.relpath(path, ROOT)}: {err}")
        print("Aborting -- refusing to run a partial migration.")
        return 1
    if not id_map:
        print("\nAll card IDs already conform. Nothing to do.")
        return 0

    by_type = {}
    for c in cards:
        if c.get("new_id") and c["new_id"] != c["old_id"]:
            by_type.setdefault(c["type"], []).append((c["old_id"], c["new_id"]))
    for t, pairs in sorted(by_type.items()):
        print(f"\n-- {t} ({len(pairs)}) --")
        for old, new in pairs[:6]:
            print(f"  {old}  ->  {new}")
        if len(pairs) > 6:
            print(f"  ... and {len(pairs) - 6} more")

    regex = build_regex(id_map, file_map)
    assert regex is not None
    combined = {**file_map, **id_map}

    touched, hits = 0, 0
    for path in collect_targets():
        with open(path, encoding="utf-8") as fh:
            original = fh.read()
        updated, n = regex.subn(lambda m: combined[m.group(0)], original)
        if not n:
            continue
        touched += 1
        hits += n
        if not check:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(updated)

    print(f"\nCross-reference rewrite: {touched} files, {hits} replacements")

    if check:
        print("--check: nothing written.")
        return 0

    # adr -> doc, then rename the card files themselves.
    retyped = renamed = 0
    for c in cards:
        if c.get("new_type") and c["new_type"] != c["type"]:
            with open(c["path"], encoding="utf-8") as fh:
                text = fh.read()
            new_text = TYPE_LINE_RE.sub(f"type: {c['new_type']}", text, count=1)
            if new_text != text:
                with open(c["path"], "w", encoding="utf-8") as fh:
                    fh.write(new_text)
                retyped += 1
        if c.get("new_base"):
            os.rename(c["path"], os.path.join(os.path.dirname(c["path"]), c["new_base"]))
            renamed += 1

    print(f"Cards retyped (adr -> doc): {retyped}")
    print(f"Card files renamed:         {renamed}")
    print("\nNow run: python3 tools/knowledge/rebuild_knowledge.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
