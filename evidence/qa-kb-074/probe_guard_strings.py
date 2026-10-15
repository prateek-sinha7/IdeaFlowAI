"""QA-KB-074 probe: do the guard strings proposed in ISS-901 match the CURRENT source after whitespace normalisation?

Run from the repo root (stdlib only, read-only):
    backend/.venv/bin/python -I evidence/qa-kb-074/probe_guard_strings.py

ABSENT strings must be found today (so a guard fails before the fix); PRESENT strings must be found today (so a guard
that is satisfied by deleting the text is impossible). Prints PASS/FAIL per string.
"""

from __future__ import annotations

import sys
from pathlib import Path

AUTHZ = Path("backend/agents/authz.py")
ENGINE = Path("backend/agents/execution_engine/engine.py")

CHECKS = [
    # (file, kind, string)
    (AUTHZ, "ABSENT-after-fix", "this class's own ``append_event_next_seq`` seq allocation"),
    (AUTHZ, "ABSENT-after-fix", "and is why the engine sink cannot allocate through :meth:`append_event_next_seq`"),
    (ENGINE, "ABSENT-after-fix", "that allocator re-reads EVERY row"),
    (AUTHZ, "PRESENT-always", "that would add two index probes per event"),
    (ENGINE, "PRESENT-always", "mints a fresh ``event_id`` per call"),
]


def main() -> int:
    bad = 0
    norm = {p: " ".join(p.read_text(encoding="utf-8").split()) for p in (AUTHZ, ENGINE)}
    for path, kind, needle in CHECKS:
        count = norm[path].count(needle)
        ok = count == 1
        bad += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {kind:16s} occurrences={count}  {path.name}: {needle}")
    print("-- every string occurs exactly once today" if not bad else f"-- {bad} string(s) do not occur exactly once")
    return 1 if bad else 0


sys.exit(main())
