"""QA-KB-074 probe: find every prose site that gives a whole-log read as the cost of append_event_next_seq.

Run from the repo root (stdlib only, read-only):
    backend/.venv/bin/python -I evidence/qa-kb-074/probe_stale_prose_sites.py

Text is whitespace-normalised across line wraps (comment markers stripped), so a claim split over two
source lines still matches. Each hit prints file:line of the match START in the ORIGINAL file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".").resolve()

# (label, regex over normalised text). The first three are the three sites named by QA-KB-074 / ISS-901.
PATTERNS = [
    ("S1 read_events_of_types lists append_event_next_seq as a read_events caller",
     r"engine resume and this class's own ``append_event_next_seq`` seq allocation"),
    ("S2 _max_event_seq gives the whole-log read as why the sink cannot use append_event_next_seq",
     r"and is why the engine sink cannot allocate through :meth:`append_event_next_seq`"),
    ("S3 _stamp_resume_marker says append_event_next_seq re-reads EVERY row",
     r"NOT ``append_event_next_seq``: that allocator re-reads EVERY row"),
    # Candidates the three-site report did not count (found by widening the search):
    ("C1 test docstring: marker allocates through append_event_next_seq, which still reads the whole log",
     r"allocates its seq through ``ScopedStore.append_event_next_seq``"),
    ("C2 test docstring: that method still derives the next seq via read_events(run_id, after_seq=0)",
     r"that method still derives the next seq via ``read_events\(run_id, after_seq=0\)``"),
    ("C3 test section comment: marker routes through append_event_next_seq",
     r"After the fix \(routing through ``ScopedStore\.append_event_next_seq``\)"),
    ("C4 DOMAIN card: single allocator rejected on the whole-log cost",
     r"was rejected on that cost"),
]

GLOBS = [
    "backend/agents/**/*.py",
    "backend/app/**/*.py",
    "backend/scripts/**/*.py",
    "backend/alembic/**/*.py",
    "backend/tests/**/*.py",
    ".knowledge/architecture/*.md",
    ".knowledge/ARCHITECTURE.md",
    "docs/**/*.md",
    "specs/**/*.md",
]


def normalise(text: str) -> tuple[str, list[int]]:
    """Return (normalised text, offset->1-based original line map)."""
    out: list[str] = []
    lines: list[int] = []
    prev_space = True
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = re.sub(r"^\s*(#\s?|\*\s?|>\s?)?", "", raw)
        for ch in stripped + " ":
            if ch.isspace():
                if prev_space:
                    continue
                ch = " "
                prev_space = True
            else:
                prev_space = False
            out.append(ch)
            lines.append(lineno)
    return "".join(out), lines


def main() -> int:
    seen: set[Path] = set()
    hits = 0
    for pattern in GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path in seen or not path.is_file() or ".venv" in path.parts or "node_modules" in path.parts:
                continue
            seen.add(path)
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            norm, line_of = normalise(text)
            for label, rx in PATTERNS:
                for m in re.finditer(rx, norm):
                    hits += 1
                    print(f"{path.relative_to(ROOT)}:{line_of[m.start()]}: [{label.split()[0]}] {label[len(label.split()[0]) + 1:]}")
    print(f"-- {hits} hit(s) over {len(seen)} files scanned")
    return 0


sys.exit(main())
