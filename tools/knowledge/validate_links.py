#!/usr/bin/env python3
"""Validate .knowledge/: markdown links, card cross-references, and card filenames.

Despite the name this is the pipeline's validation stage, not a link checker
alone -- it fails the build on a dead link, a reference to a card that does
not exist, or a filename whose timestamp or id is wrong.

Read-only. Reusable after any regeneration of INDEX.md / architecture cards.
"""
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    ).stdout.strip()
)
KNOWLEDGE_DIR = REPO_ROOT / ".knowledge"

# Matches [text](target) — not images (no leading `!`).
LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")

# Fenced blocks and inline code spans hold *illustrative* markdown -- e.g. the
# retrieval protocol shows `- [ID](cards/<file>.md)` as the index line format.
# Those are examples, not links, and must not be resolved.
FENCE_RE = re.compile(r"^\s*(```|~~~)", re.M)
CODESPAN_RE = re.compile(r"`[^`\n]*`")


def strip_code(text: str) -> str:
    """Blank out fenced blocks and inline code, preserving offsets and lines."""
    out, in_fence = [], False
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else CODESPAN_RE.sub(lambda m: " " * len(m.group(0)), line))
    return "\n".join(out)


def is_external(target: str) -> bool:
    return bool(urlsplit(target).scheme)


FM_ID = re.compile(r"^id:\s*(.+?)\s*$", re.M)

# The cross-reference graph lives in the card BODY now, under a `<!-- RELATED -->`
# marker, as `[[<card-file-stem>|<CARD-ID>]]`. Two things can be wrong and both
# matter: the ID may name no card, or the link TARGET may name no file. The
# markdown-link walk below sees neither, since a wikilink is not a markdown
# link -- which is precisely how 106 dead frontmatter refs once went unnoticed.
RELATED_START = "<!-- RELATED -->"
RELATED_END = "<!-- /RELATED -->"
# Anchored: a card discussing the marker in prose must not be mistaken for one
# declaring a graph.
START_LINE = re.compile(r"^" + re.escape(RELATED_START) + r"[ \t]*$", re.M)
END_LINE = re.compile(r"^" + re.escape(RELATED_END) + r"[ \t]*$", re.M)
CARD_REF = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
SECTION = re.compile(r"^\*\*(?:Depends on|Referenced by):\*\*\s*(.+)$", re.M)
BARE_ID = re.compile(r"\b([A-Z]{2,6}-[A-Za-z0-9][A-Za-z0-9.-]*)")


def card_ids() -> set:
    ids = set()
    for p in (KNOWLEDGE_DIR / "cards").glob("*.md"):
        m = FM_ID.search(p.read_text(encoding="utf-8", errors="replace"))
        if m:
            ids.add(m.group(1).strip().strip("'\""))
    return ids


def related_refs(path: Path):
    """Yield (target_filename, card_id) for every link in the Related block.

    The link TARGETS are also caught by the ordinary markdown-link walk below,
    which is the point -- they are real links, so they get real validation for
    free. This pass adds the check that walk cannot make: that the link TEXT
    names a card that actually exists.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    m_start = START_LINE.search(text)
    if not m_start:
        return
    rest = text[m_start.end():]
    m_end = END_LINE.search(rest)
    block = rest[: m_end.start()] if m_end else rest
    for m in CARD_REF.finditer(block):
        yield m.group(2), m.group(1)
    # A reference left as bare text is one build_index could not resolve to a
    # card file. It is deliberately preserved rather than dropped, so it must
    # be reported here -- otherwise a bad reference vanishes from the block
    # AND from this report, and the tree looks clean.
    for line in SECTION.findall(block):
        stripped = CARD_REF.sub(" ", line)
        for m in BARE_ID.finditer(stripped):
            yield None, m.group(1)


CARD_NAME = re.compile(r"^(\d{8})(?:-(\d{4}))?-(.+)\.md$")


def check_card_filenames(cards_dir: Path):
    """-> list of (path, what, detail) for malformed or dishonest filenames.

    A card's filename is the ONLY record of when it was authored, and
    `book-keeping.md` asks the author to supply a real time ("you are
    authoring now, so you HAVE a real time"). Nothing verified that, so a
    plausible-looking invention was accepted silently -- a card stamped 2000
    and committed at 1841 reads as fact forever after.

    Three things are checked, all cheap and all objective:
      * the `{YYYYMMDD}[-{HHMM}]-{ID}.md` shape parses at all
      * HHMM is a real clock time, and the stamp is not in the FUTURE
      * the ID in the filename matches the `id:` in the frontmatter

    Date-only names are legal: they exist for migrated cards whose authoring
    time was genuinely unrecoverable. A fabricated time is not the same thing
    as an absent one.
    """
    import datetime

    now = datetime.datetime.now()
    problems = []
    for path in sorted(cards_dir.glob("*.md")):
        m = CARD_NAME.match(path.name)
        if not m:
            problems.append((path, "filename shape",
                             "expected {YYYYMMDD}[-{HHMM}]-{ID}.md"))
            continue
        day_s, hhmm, file_id = m.groups()
        try:
            stamp = datetime.datetime.strptime(day_s, "%Y%m%d")
        except ValueError:
            problems.append((path, "date", f"{day_s!r} is not a real date"))
            continue
        if hhmm is not None:
            hour, minute = int(hhmm[:2]), int(hhmm[2:])
            if hour > 23 or minute > 59:
                problems.append((path, "time", f"{hhmm!r} is not a clock time"))
                continue
            stamp = stamp.replace(hour=hour, minute=minute)
        if stamp > now:
            problems.append((path, "future timestamp",
                             f"{stamp:%Y-%m-%d %H:%M} is later than now "
                             f"({now:%Y-%m-%d %H:%M}) -- use the real authoring time"))
            continue
        m_id = FM_ID.search(path.read_text(encoding="utf-8", errors="replace"))
        real_id = m_id.group(1).strip().strip("'\"") if m_id else None
        if real_id and real_id != file_id:
            problems.append((path, "id mismatch",
                             f"filename says {file_id!r}, frontmatter says {real_id!r}"))
    return problems


def main() -> int:
    total = 0
    broken = []

    known = card_ids()
    cards_dir = KNOWLEDGE_DIR / "cards"

    name_problems = check_card_filenames(cards_dir)
    for path, what, detail in name_problems:
        broken.append((str(path.relative_to(REPO_ROOT)), what, detail))
    print(f"Card filenames checked: {len(list(cards_dir.glob('*.md')))}"
          + (f" -- {len(name_problems)} PROBLEM(S)" if name_problems else ""))
    ref_total = 0
    for card in sorted(cards_dir.glob("*.md")):
        for target, ref in related_refs(card):
            ref_total += 1
            rel = str(card.relative_to(REPO_ROOT))
            if ref not in known:
                broken.append((rel, "unknown card id", ref))
            elif target is None:
                continue
            elif not (cards_dir / target).exists():
                broken.append((rel, f"wikilink target for {ref}", target))
    print(f"Card cross-refs checked: {ref_total}")

    for md_path in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        text = strip_code(md_path.read_text(encoding="utf-8"))
        for match in LINK_RE.finditer(text):
            link_text, target = match.group(1), match.group(2).strip()
            if is_external(target) or target.startswith("#"):
                continue
            total += 1
            # Strip any in-file anchor.
            path_part = target.split("#", 1)[0]
            resolved = (md_path.parent / unquote(path_part)).resolve()
            # A link may legitimately target a directory -- three pointer
            # cards reference evidence folders, not single documents.
            if not resolved.exists():
                broken.append((str(md_path.relative_to(REPO_ROOT)), link_text, target))

    print(f"Total local links checked: {total}")
    print(f"Resolved: {total - len(broken)}")
    print(f"Broken: {len(broken)}")
    for src, text, target in broken:
        print(f"  {src}: [{text}]({target})")

    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
