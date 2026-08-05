#!/usr/bin/env python3
"""Freshness and integrity checks for the knowledge store.

Three drifts are possible, and all three are *reported loudly* rather than
silently tolerated — a confident stale map is worse than no map:

  1. cards vs registers  — someone appended to a register the old way
  2. index vs cards      — a card was added or hand-edited, index not rebuilt
  3. cards vs code       — a card names a file that has since moved or gone

    python3 scripts/knowledge/check.py [repo_root]

Exit: 0 clean · 1 warnings · 2 errors.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import (  # type: ignore[import-not-found]  # noqa: E402
    CardError,
    cache_dir,
    frontmatter_hash,
    knowledge_dir,
    load_all,
    read_json,
    repo_root,
    surface_dir,
)

OK, WARN, ERR = "ok", "warn", "err"
MARK = {OK: "  ok  ", WARN: " warn ", ERR: " ERR  "}


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, level: str, check: str, detail: str = "") -> None:
        self.rows.append((level, check, detail))

    @property
    def worst(self) -> str:
        if any(r[0] == ERR for r in self.rows):
            return ERR
        if any(r[0] == WARN for r in self.rows):
            return WARN
        return OK

    def render(self) -> str:
        out = []
        for level, check, detail in self.rows:
            out.append(f"[{MARK[level]}] {check}")
            for line in (detail or "").splitlines():
                if line.strip():
                    out.append(f"          {line}")
        return "\n".join(out)


def _git_show(root: Path, ref: str, path: str) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return r.stdout if r.returncode == 0 else None


def check_cards(root: Path, rep: Report):
    try:
        cards = load_all(root)
    except CardError as e:
        rep.add(ERR, "cards parse", str(e))
        return None

    ids = [c.id for c in cards]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        rep.add(ERR, "unique ids", f"duplicates: {', '.join(dupes)}")
    else:
        rep.add(OK, f"cards parse ({len(cards)} cards, unique ids)")
    return cards


def check_index_fresh(root: Path, cards: list, rep: Report):
    stamp = read_json(cache_dir(root) / "stamp.json", {})
    if not stamp:
        rep.add(ERR, "index built", "no .cache/stamp.json — run build_index.py")
        return
    want = frontmatter_hash(cards)
    if stamp.get("frontmatter_sha1") != want:
        rep.add(
            WARN,
            "index vs cards",
            f"stale — cards changed since the last build ({stamp.get('built_at', '?')}).\n"
            "run: python3 scripts/knowledge/build_index.py",
        )
    elif stamp.get("card_count") != len(cards):
        rep.add(WARN, "index vs cards", "card count drifted — rebuild")
    else:
        rep.add(OK, f"index vs cards (fresh, built {stamp.get('built_at', '?')})")


def check_architecture_fresh(root: Path, rep: Report):
    """ARCHITECTURE.md's Stage section vs .planning/STATE.md.

    A drift the frontmatter hash cannot see. ARCHITECTURE.md derives its stage from
    STATE.md, which is not a card, so STATE.md can advance a whole milestone while
    `index vs cards` still reports fresh. A stale "current state" file is the worst
    thing in this store — it is the one file read for the present.
    """
    arch = surface_dir(root) / "ARCHITECTURE.md"
    state = root / ".planning" / "STATE.md"
    if not arch.is_file():
        rep.add(WARN, "architecture", "no surface/ARCHITECTURE.md — run build_index.py")
        return
    if not state.is_file():
        rep.add(OK, "architecture (no STATE.md to drift from)")
        return

    text = arch.read_text(encoding="utf-8")
    m = re.search(r"(?m)^\|\s*\*\*Last updated\*\*\s*\|\s*([\d-]+)", text)
    built_from = m.group(1) if m else None

    head = state.read_text(encoding="utf-8", errors="replace")[:2000]
    sm = re.search(r'(?m)^last_updated:\s*"?([\d-]+)', head)
    actual = sm.group(1) if sm else None

    if built_from and actual and built_from != actual:
        rep.add(
            WARN,
            "architecture vs STATE.md",
            f"stale — ARCHITECTURE.md reports {built_from}, STATE.md says {actual}.\n"
            "run: python3 scripts/knowledge/build_index.py",
        )
    elif not built_from or not actual:
        rep.add(WARN, "architecture vs STATE.md", "could not compare last_updated dates")
    else:
        rep.add(OK, f"architecture vs STATE.md (fresh, {actual})")


def check_files_exist(root: Path, cards: list, rep: Report):
    missing: dict[str, list[str]] = {}
    total = 0
    for c in cards:
        for f in c.files:
            total += 1
            if not (root / f).exists():
                missing.setdefault(f, []).append(c.id)
    if missing:
        detail = "\n".join(
            f"{f}  ← {', '.join(sorted(ids))}" for f, ids in sorted(missing.items())
        )
        rep.add(
            WARN,
            f"cards vs code ({len(missing)}/{total} paths missing)",
            detail + "\n(file renamed or deleted — the card's claim can no longer be verified)",
        )
    else:
        rep.add(OK, f"cards vs code ({total} referenced paths all exist)")


def check_links(cards: list, rep: Report):
    known = {c.id for c in cards}
    prefixes = {i.split("-")[0] for i in known}
    dangling: dict[str, list[str]] = {}
    external = 0
    for c in cards:
        for target in c.links():
            if target in known:
                continue
            if target.split("-")[0] in prefixes:
                dangling.setdefault(target, []).append(c.id)
            else:
                external += 1
    if dangling:
        detail = "\n".join(
            f"{t}  ← referenced by {', '.join(sorted(src))}" for t, src in sorted(dangling.items())
        )
        rep.add(WARN, f"links ({len(dangling)} point at cards that do not exist)", detail)
    else:
        rep.add(OK, f"links resolve ({external} external refs ignored)")


def check_sources(root: Path, cards: list, rep: Report):
    """Have the source registers grown since we extracted from them?"""
    cfg = read_json(knowledge_dir(root) / "sources.json", {})
    registers = cfg.get("registers") or {}
    if not registers:
        rep.add(WARN, "cards vs registers", "no .knowledge/sources.json — cannot detect drift")
        return

    ref = cfg.get("content_ref", "HEAD")
    card_ids = {c.id for c in cards}
    stale = []

    for path, meta in sorted(registers.items()):
        content = _git_show(root, ref, path)
        if content is None:
            stale.append(f"{path}: not readable at {ref}")
            continue

        pattern = meta.get("id_pattern")
        if not pattern:
            continue
        found = set(re.findall(pattern, content))
        unextracted = sorted(found - card_ids, key=lambda s: (len(s), s))
        if unextracted:
            shown = ", ".join(unextracted[:6])
            more = f" (+{len(unextracted) - 6} more)" if len(unextracted) > 6 else ""
            stale.append(f"{path}: {len(unextracted)} entries not yet extracted — {shown}{more}")

    if stale:
        rep.add(
            WARN,
            "cards vs registers",
            "\n".join(stale) + "\nrun the knowledge-extract skill on the delta",
        )
    else:
        rep.add(OK, f"cards vs registers (all entries extracted, ref {ref})")


# Deliberately not migrated, with the reason. Anything else uncovered is a gap.
EXCLUDED = {
    # Not carried as a card, but not ignored either: build_architecture.py lifts its
    # frontmatter and Current Position into surface/ARCHITECTURE.md on every build,
    # which is why check_architecture_fresh exists. A card would freeze a file that
    # changes every session; regenerating keeps it current by construction.
    ".planning/STATE.md": "current state — lifted into surface/ARCHITECTURE.md, not carded",
    ".planning/config.json": "tooling config, not project knowledge",
}


def check_coverage(root: Path, cards: list, rep: Report):
    """Every file under .planning/ is either carried by a card or excluded on purpose."""
    covered = set()
    for c in cards:
        for key in ("source", "shard"):
            v = c.fm.get(key)
            if v:
                covered.add(str(v).split("#")[0].strip())
    folders = {s.rstrip("/") for s in covered if not Path(s).suffix}
    planning = root / ".planning"
    if not planning.is_dir():
        rep.add(WARN, "coverage", "no .planning/ directory")
        return

    missing = []
    for p in planning.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        rel = p.relative_to(root).as_posix()
        if rel in covered or rel in EXCLUDED:
            continue
        if any(rel.startswith(d + "/") for d in folders):
            continue
        missing.append(rel)

    total = sum(1 for p in planning.rglob("*") if p.is_file() and not p.name.startswith("."))
    if missing:
        shown = "\n".join(missing[:10])
        more = f"\n(+{len(missing) - 10} more)" if len(missing) > 10 else ""
        rep.add(WARN, f"coverage ({total - len(missing)}/{total} .planning files carried)",
                shown + more + "\nrun: python3 scripts/knowledge/migrate.py all")
    else:
        rep.add(OK, f"coverage ({total}/{total} .planning files carried, "
                    f"{len(EXCLUDED)} excluded by design)")


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else repo_root()
    if not knowledge_dir(root).is_dir():
        print(f"error: no .knowledge/ at {knowledge_dir(root)}", file=sys.stderr)
        return 2

    rep = Report()
    cards = check_cards(root, rep)
    if cards is None:
        print(rep.render())
        return 2

    check_index_fresh(root, cards, rep)
    check_architecture_fresh(root, rep)
    check_files_exist(root, cards, rep)
    check_links(cards, rep)
    check_sources(root, cards, rep)
    check_coverage(root, cards, rep)

    print(rep.render())
    verdict = rep.worst
    print(
        "\n"
        + {
            OK: "clean.",
            WARN: "usable, but see warnings above.",
            ERR: "BROKEN — fix errors before relying on the index.",
        }[verdict]
    )
    return {OK: 0, WARN: 1, ERR: 2}[verdict]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
