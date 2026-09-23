# TRIAGE — cards with no recorded fix site (NOT scheduled)

21 cards have no `applies_to.globs`, so they cannot be collision-checked and must
not be batched. Each needs an analyzer pass to assign a fix site FIRST; then it
joins the domain that owns that file. Run this lane by saying **"triage the
unplaced cards"** — Kiro dispatches analyzers (Sonnet) to locate each, then moves
it into the right domain run-doc.

## frontend · unplaced (18)
BUG-009-sse, BUG-010-sse, BUG-035, BUG-074, BUG-104, BUG-106,
BUG-CWF-001-custom-workflow, BUG-CWF-002-custom-workflow, ISS-018, ISS-071,
ISS-107, ISS-122, ISS-129, ISS-135, ISS-159, ISS-160, ISS-179, ISS-186

## backend · unplaced (3)
BUG-036, BUG-037, ISS-020

## Special case — ISS-190 (no landed FIX card)
Its root (`.knowledge/cards/…ISS-190.md`) is marked resolved but carries NO FIX
card, so its tier-A′ siblings ISS-195 / ISS-197 have no diff to replicate. Treat
these three as triage, not A′: an analyzer must establish the actual fix (or
confirm the root was mis-closed) before the siblings can be fixed. This is also a
data-quality signal — a root was closed without linking a FIX card.

## Several BUG-CWF / BUG-0xx cards
Some `frontend·unplaced` entries (BUG-035/074/104/106, BUG-CWF-*) read as
symptom-only reports from a bulk import; the analyzer should check whether they are
duplicates of already-carded ISS defects before assigning a fix site.
