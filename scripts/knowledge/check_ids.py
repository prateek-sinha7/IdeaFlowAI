#!/usr/bin/env python3
"""Four-source ID allocator check for FIX / ISS / TEST ids.

Why this exists
---------------
Ids get burned in commit messages, code comments and knowledge cards *before* the
register row is written, so any register is a lagging source. Taking "register max + 1"
has produced two real incidents on this repo:

  * FIX-214/215/216b were live in ``dev`` commits while FIX-REGISTER.md topped out at 213.
  * ISS-050 was already taken by FIX-185 (commit ``fd2ad8f1``) via a commit message alone.
    It was re-issued for an unrelated defect and had to be renumbered to ISS-064.
  * ISS-066 then recorded that "ISS-055 is a free gap" — it was not; ISS-055 is the tier
    entitlement bypass closed by FIX-189. Acting on that would have caused a third
    collision.

Usage
-----
    python3 scripts/knowledge/check_ids.py           # report all three prefixes
    python3 scripts/knowledge/check_ids.py ISS       # one prefix
    python3 scripts/knowledge/check_ids.py --next ISS

Exit codes: 0 = no drift, 1 = drift found (ids used outside their register).
Run from the repository root.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# prefix -> register file
REGISTERS = {
    "FIX": ".planning/FIX-REGISTER.md",
    "ISS": ".planning/ISSUES-REGISTER.md",
    "TEST": ".planning/FIX-TEST-REGISTER.md",
}

# Per-prefix id pattern. TEST is the subtle one: there are TWO unrelated TEST
# namespaces in this repo and conflating them produces 32 phantom drift rows.
#   * FIX-TEST-REGISTER.md ids are ALWAYS zero-padded to three digits (TEST-001).
#   * .knowledge/cards/ also holds QA test-CASE ids in an unpadded, sometimes
#     hierarchical form (TEST-45, TEST-2-2). Those are a different namespace and
#     must not be counted here.
# So TEST matches padded-3-digit only, and never a hierarchical suffix.
ID_PATTERNS = {
    "FIX": r"\bFIX-(\d+)\b(?!-\d)",
    "ISS": r"\bISS-(\d+)\b(?!-\d)",
    "TEST": r"\bTEST-(\d{3})\b(?!-\d)",
}

# Directories that are noise for this purpose.
SKIP_DIRS = {".git", "node_modules", ".next", "__pycache__", ".venv", "dist", "build"}

# Text-ish files worth sweeping for in-code / in-doc citations.
SWEEP_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".yaml", ".yml", ".json", ".toml"}


def _ids(text: str, prefix: str) -> set[int]:
    return {int(m) for m in re.findall(ID_PATTERNS[prefix], text)}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _register_rows(prefix: str) -> set[int]:
    """Ids that actually have a ROW (leading '| PREFIX-NNN |'), not merely a mention."""
    text = _read(REPO / REGISTERS[prefix])
    return {int(m) for m in re.findall(rf"^\|\s*{prefix}-(\d+)\s*\|", text, re.MULTILINE)}


def _register_mentions(prefix: str) -> set[int]:
    return _ids(_read(REPO / REGISTERS[prefix]), prefix)


def _cards(prefix: str) -> set[int]:
    found: set[int] = set()
    for p in (REPO / ".knowledge").rglob("*"):
        if p.is_file() and p.suffix in {".md", ".json"}:
            found |= _ids(_read(p), prefix)
    return found


def _commits(prefix: str) -> set[int]:
    try:
        out = subprocess.run(
            ["git", "log", "--all", "--pretty=%s%n%b"],
            cwd=REPO, capture_output=True, text=True, timeout=120,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return _ids(out, prefix)


def _source(prefix: str) -> set[int]:
    """Citations in code and planning docs — where ISS-054/055 were hiding."""
    found: set[int] = set()
    for root in ("backend", "frontend/src", "frontend/e2e", ".planning", ".kiro", "scripts"):
        base = REPO / root
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in SWEEP_SUFFIXES:
                continue
            if SKIP_DIRS & set(p.parts):
                continue
            found |= _ids(_read(p), prefix)
    return found


def report(prefix: str) -> bool:
    """Print the sweep for one prefix. Returns True if drift was found."""
    rows = _register_rows(prefix)
    sources = {
        "register rows": rows,
        "register mentions": _register_mentions(prefix),
        "knowledge cards": _cards(prefix),
        "commit messages": _commits(prefix),
        "code + docs": _source(prefix),
    }
    used: set[int] = set().union(*sources.values()) if sources else set()

    print(f"\n=== {prefix} ===")
    for name, ids in sources.items():
        top = max(ids) if ids else 0
        print(f"  {name:<20} count={len(ids):<5} max={prefix}-{top:03d}")

    nxt = (max(used) + 1) if used else 1
    print(f"  {'OVERALL':<20} count={len(used):<5} max={prefix}-{max(used) if used else 0:03d}")
    print(f"  --> NEXT FREE ID: {prefix}-{nxt:03d}  (max across all sources + 1; never fill gaps)")

    drift = sorted(used - rows)
    if drift:
        print(f"  !! DRIFT: {len(drift)} id(s) in use with NO row in {REGISTERS[prefix]}:")
        for i in drift:
            where = [n for n, s in sources.items() if i in s and n != "register rows"]
            print(f"       {prefix}-{i:03d}  seen in: {', '.join(where)}")
        return True

    print("  OK: every id in use has a register row.")
    return False


def main() -> int:
    args = [a for a in sys.argv[1:]]
    next_only = "--next" in args
    if next_only:
        args.remove("--next")
    prefixes = [a.upper() for a in args if a.upper() in REGISTERS] or list(REGISTERS)

    any_drift = False
    for prefix in prefixes:
        any_drift |= report(prefix)

    print(
        "\nNote: a gap inside a used range is NOT free — ISS-055 looked free and was not.\n"
        "Always take max-across-all-sources + 1."
    )
    return 1 if any_drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
