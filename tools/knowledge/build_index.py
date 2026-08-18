#!/usr/bin/env python3
"""Build .knowledge/INDEX.md and .knowledge/state.yaml from .knowledge/cards/.

Deterministic and re-runnable. Reads cards, writes only INDEX.md and
state.yaml. Never touches cards, architecture/, docs/, skills/, or
tools/cardex/.
"""
import argparse
import glob
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import quote

import yaml

REPO_ROOT = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()

CARDS_DIR = f"{REPO_ROOT}/.knowledge/cards"
INDEX_PATH = f"{REPO_ROOT}/.knowledge/INDEX.md"
STATE_PATH = f"{REPO_ROOT}/.knowledge/state.yaml"
ARCH_DIR = f"{REPO_ROOT}/.knowledge/architecture"

TYPE_ORDER = ["adr", "issue", "bug", "fix"]


def write_if_changed(path, content):
    """Write only when the bytes differ. Returns True if it wrote.

    Every generator here is deterministic, so re-running with no input change
    should be a no-op ON DISK, not merely in content. Rewriting an identical
    file still updates its mtime and still shows up as a modification to git
    and to pre-commit -- which turns a hook that regenerates artifacts into one
    that reports a change on every single commit.
    """
    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except (OSError, UnicodeDecodeError):
        pass
    path.write_text(content, encoding="utf-8")
    return True


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return {}


def natural_key(card_id):
    """Numeric-aware sort key: FIX-2 < FIX-10 < FIX-50b."""
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", card_id)
    ]


def first_prose_sentence(body):
    """First non-empty prose sentence from the card body (skip headings/blockquotes/etc)."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", ">", "|", "```", "<!--", "-", "*")):
            continue
        # Take up to the first sentence-ending period, else the whole line.
        match = re.search(r"[.!?](\s|$)", stripped)
        sentence = stripped[: match.end()].strip() if match else stripped
        return sentence
    return ""


def one_line(text):
    return " ".join(text.split())


def truncate(text, limit=140):
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def load_card(path):
    """-> (frontmatter, body), or (None, None) if this file is not a card.

    A `.md` in cards/ with no `---` frontmatter block was never a card -- a
    stray README or scratch note. Indexing must skip it, not die: `parts[1]`
    on an undelimited file raises IndexError and takes the whole rebuild
    pipeline down with it. Same rule as tools/knowledge/normalize_card_ids.py, so the
    two agree on what counts as a card.
    """
    text = open(path, encoding="utf-8", errors="replace").read()
    parts = text.split("---", 2)
    if len(parts) < 2:
        return None, None
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, None
    if not isinstance(frontmatter, dict):
        return None, None
    body = parts[2] if len(parts) > 2 else ""
    return frontmatter, body


def describe(frontmatter, body):
    """Return (description, source) where source is one of
    compact_summary/title/body."""
    summary = frontmatter.get("compact_summary")
    if summary and str(summary).strip():
        return one_line(str(summary).strip()), "compact_summary"
    title = frontmatter.get("title")
    if title and str(title).strip():
        return one_line(str(title).strip()), "title"
    sentence = first_prose_sentence(body)
    if sentence:
        return one_line(sentence), "body"
    return "", "none"


RELATED_START = "<!-- RELATED -->"
RELATED_END = "<!-- /RELATED -->"
START_LINE = re.compile(r"^" + re.escape(RELATED_START) + r"[ \t]*$", re.M)
END_LINE = re.compile(r"^" + re.escape(RELATED_END) + r"[ \t]*$", re.M)
REF_LABEL = {"depends_on": "Depends on", "referenced_by": "Referenced by"}
LABEL_REF = {v: k for k, v in REF_LABEL.items()}

# `[FIX-034](20260704-1815-FIX-034.md)` -- an ORDINARY markdown link: card ID
# as the text, exact sibling filename as the target. Not a `[[wikilink]]`,
# which stock VS Code does not resolve and therefore cannot click. Same form
# INDEX.md uses, which is the form confirmed to work.
CARD_REF = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
WIKILINK = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")
SECTION = re.compile(r"^\*\*(Depends on|Referenced by):\*\*\s*(.+)$", re.M)
# A bare `FIX-034` / `BUG-012-sse` / `ADR-0001` written by hand.
BARE_ID = re.compile(r"\b([A-Z]{2,6}-[A-Za-z0-9][A-Za-z0-9.-]*)")


def split_related(body):
    """-> (block_text_or_None, body_without_block).

    Delimited at BOTH ends because the block sits at the top of the body now,
    ahead of the prose. A start marker alone was enough only while it was last
    in the file; anchoring on one marker and taking the remainder would eat
    the entire card.
    """
    # Anchored to a line of its own. A card may legitimately DISCUSS the
    # marker in prose -- an issue card about this very block quoted it inside
    # backticks, and an unanchored split matched that mention and treated half
    # the card's narrative as the graph.
    m_start = START_LINE.search(body)
    if not m_start:
        return None, body.strip("\n")
    before, rest = body[: m_start.start()], body[m_start.end():]
    m_end = END_LINE.search(rest)
    if m_end:
        block, after = rest[: m_end.start()], rest[m_end.end():]
    else:
        # A block written before the end marker existed ran to end-of-file.
        block, after = rest, ""
    return block, (before.rstrip("\n") + "\n\n" + after.lstrip("\n")).strip("\n")


def read_related(block):
    """-> {'depends_on': [id, ...], 'referenced_by': [...]} from the block.

    This block is the SOURCE of the cross-reference graph. It used to live in
    frontmatter, which is YAML -- so no editor rendered it and no link in it
    was ever clickable. In the body it is the thing you navigate, not a
    description of one.
    """
    out = {"depends_on": [], "referenced_by": []}
    if not block:
        return out
    for label, payload in SECTION.findall(block):
        ids = [m.group(1) for m in CARD_REF.finditer(payload)]
        # Tolerate the older wikilink form so a card written before the switch
        # keeps its graph on the next rebuild instead of losing it.
        ids += [m.group(2) for m in WIKILINK.finditer(payload)]
        # And accept a BARE id. Hand-writing the link form would mean knowing
        # the target's filename, which carries a datetime -- the very lookup
        # this block exists to spare you. So `**Depends on:** FIX-034` is a
        # legitimate way to author a card, and the rebuild renders the link.
        stripped = CARD_REF.sub(" ", payload)
        stripped = WIKILINK.sub(" ", stripped)
        ids += [tok for tok in BARE_ID.findall(stripped)]
        seen, unique = set(), []
        for i in ids:
            if i not in seen:
                seen.add(i)
                unique.append(i)
        out[LABEL_REF[label]] = unique
    return out


def write_related_blocks(cards):
    """Render each card's `## Related` block directly beneath the frontmatter.

    The ID set is never invented or dropped -- it is read back from the block
    itself. Only the LINK TARGETS are refreshed, because they embed filenames
    that carry a datetime: rename a card and every link to it would otherwise
    be silently wrong. An id resolving to no card is kept so validate_links
    reports it rather than being quietly deleted here.
    """
    by_id = {c["id"]: c["filename"] for c in cards}
    written = 0
    for card in cards:
        with open(card["path"], encoding="utf-8") as fh:
            text = fh.read()
        head, fm, body = text.split("---", 2)
        block, prose = split_related(body)
        # Both branches below re-wrap `prose` in fixed padding, so it must
        # carry none of its own -- otherwise every run adds a newline and the
        # file grows by a byte forever while never converging.
        prose = prose.strip("\n")
        refs = read_related(block)

        sections = []
        for key in ("depends_on", "referenced_by"):
            ids = refs[key]
            if not ids:
                continue
            ids.sort(key=natural_key)
            # An id that resolves to no card is KEPT, as bare text rather than
            # a link. Dropping it would erase the only evidence that the
            # reference was ever made: the block would silently shrink and
            # validate_links would report a clean tree. A bad reference must
            # survive long enough to be reported.
            rendered = [f"[{r}]({by_id[r]})" if r in by_id else r for r in ids]
            sections.append(f"**{REF_LABEL[key]}:** {', '.join(rendered)}")

        if sections:
            rendered = "\n\n".join(
                [RELATED_START, "## Related", "\n\n".join(sections), RELATED_END]
            )
            new_body = f"\n\n{rendered}\n\n{prose}\n"
        else:
            new_body = f"\n\n{prose}\n"

        new = head + "---" + fm + "---" + new_body
        if new != text:
            with open(card["path"], "w", encoding="utf-8") as fh:
                fh.write(new)
            written += 1
    print(f"Related blocks: {written} card(s) updated")


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--set-sync-point",
        action="store_true",
        help="move last_sync_commit/last_sync_date to HEAD. Only `sync` should "
             "pass this: the watermark records what sync last reconciled "
             "against, and advancing it on an ordinary index build silently "
             "discards the commit range sync had yet to review.",
    )
    return ap.parse_args()


def main():
    args = parse_args()
    files = sorted(glob.glob(f"{CARDS_DIR}/*.md"))
    cards = []
    by_type = {}
    by_kind = {}
    source_counts = {"compact_summary": 0, "title": 0, "body": 0, "none": 0}
    no_description = []

    skipped_not_cards = []
    retired_type = []

    for path in files:
        frontmatter, body = load_card(path)
        if frontmatter is None:
            skipped_not_cards.append(os.path.basename(path))
            continue
        card_id = frontmatter.get("id")
        card_type = frontmatter.get("type")
        card_kind = frontmatter.get("kind")
        desc, source = describe(frontmatter, body)
        desc = truncate(desc)
        source_counts[source] += 1
        if source == "none":
            no_description.append(card_id)
        if card_type not in TYPE_ORDER:
            retired_type.append((os.path.basename(path), card_type))
        by_type[card_type] = by_type.get(card_type, 0) + 1
        if card_kind:
            by_kind[card_kind] = by_kind.get(card_kind, 0) + 1
        cards.append({
            "id": card_id,
            "type": card_type,
            "description": desc,
            "filename": os.path.basename(path),
            "path": path,
            "frontmatter": frontmatter,
        })

    write_related_blocks(cards)

    # --- INDEX.md ---
    lines = []
    lines.append("# Card Index")
    lines.append("")
    lines.append(f"{len(cards)} cards. Generated by tools/knowledge/build_index.py — do not edit by hand.")
    lines.append("Card files live in `.knowledge/cards/` as `{YYYYMMDD}-{HHMM}-{ID}.md`.")
    lines.append("Resolve a bare card ID by globbing `.knowledge/cards/*-<ID>.md`.")
    lines.append("")

    present_types = sorted(
        set(c["type"] for c in cards),
        key=lambda t: TYPE_ORDER.index(t) if t in TYPE_ORDER else len(TYPE_ORDER),
    )
    for card_type in present_types:
        group = [c for c in cards if c["type"] == card_type]
        group.sort(key=lambda c: natural_key(c["id"]))
        lines.append(f"## {card_type} ({len(group)})")
        lines.append("")
        for c in group:
            link_target = "cards/" + quote(c["filename"])
            lines.append(f"- [{c['id']}]({link_target}) — {c['description']}")
        lines.append("")

    wrote_index = write_if_changed(pathlib.Path(INDEX_PATH), "\n".join(lines).rstrip() + "\n")
    print(f"INDEX.md: {'updated' if wrote_index else 'unchanged'}")

    # --- state.yaml ---
    # `git rev-parse HEAD` FAILS in a repo that has been `git init`ed but has
    # no commits yet (exit 128), and outside a checkout entirely. Both are
    # ordinary states -- a fresh clone before the first commit, a sandbox, an
    # export -- not errors. With `check=True` this raised CalledProcessError
    # mid-function, AFTER INDEX.md had been written and BEFORE state.yaml was,
    # leaving the tree half-built and the next stage failing on the missing
    # file it was supposed to produce.
    #
    # An empty commit is the honest value: "there is no commit to record".
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    )
    commit = proc.stdout.strip() if proc.returncode == 0 else ""
    if not commit:
        print("  note: no git HEAD (no commits yet, or not a checkout) -- "
              "recording an empty commit in state.yaml")
    arch_count = len(glob.glob(f"{ARCH_DIR}/MOD-*.md"))

    prev = load_state()
    # `last_sync_commit` means "the commit `sync` last reconciled against", and
    # only `sync` may move it. Setting it to HEAD on every index build erased
    # the very window sync exists to mine: a `prime` or `book-keeping` run
    # between syncs advanced the watermark past commits nobody had reviewed,
    # and sync then reported "0 commits" forever. Preserve it; seed it only
    # when the field has never existed.
    # `index_generated_at` is gone: nothing read it, git already records when
    # the commit happened, and a wall-clock stamp made state.yaml differ on
    # every run even when the corpus was identical.
    state = {
        "schema_version": 1,
        "last_sync_commit": prev.get("last_sync_commit") or commit,
        "last_sync_date": prev.get("last_sync_date")
        or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "cards_count": len(cards),
        "cards_by_type": dict(sorted(by_type.items())),
        "cards_by_kind": dict(sorted(by_kind.items())),
        "architecture_count": arch_count,
    }
    if args.set_sync_point:
        state["last_sync_commit"] = commit
        state["last_sync_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    wrote_state = write_if_changed(
        pathlib.Path(STATE_PATH),
        yaml.safe_dump(state, sort_keys=False, default_flow_style=False),
    )
    print(f"state.yaml: {'updated' if wrote_state else 'unchanged'}")

    # --- report ---
    total_lines = len(open(INDEX_PATH, encoding="utf-8").readlines())
    print(f"INDEX.md total lines: {total_lines}")
    print(f"cards indexed: {len(cards)}")
    if retired_type:
        print(f"WARNING: {len(retired_type)} card(s) carry a RETIRED type "
              f"(schema is {'|'.join(TYPE_ORDER)}):")
        for name, ty in retired_type:
            print(f"  {name}: type: {ty}")
    if skipped_not_cards:
        print(f"not cards (no parseable frontmatter, skipped): {len(skipped_not_cards)}")
        for name in skipped_not_cards[:5]:
            print(f"  - {name}")
    print(f"by_type: {dict(sorted(by_type.items()))} sum={sum(by_type.values())}")
    print(f"description source counts: {source_counts}")
    print(f"cards with no usable description: {no_description}")
    with open(STATE_PATH, encoding="utf-8") as f:
        parsed = yaml.safe_load(f)
    print(f"state.yaml parses OK: {parsed is not None}")


if __name__ == "__main__":
    sys.exit(main())
