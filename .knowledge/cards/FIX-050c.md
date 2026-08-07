---
id: FIX-050c
type: fix
date: 2026-07-10
status: done
area: [frontend, agents]
files:
  - frontend/src/components/history/RunDetailPage.tsx
  - frontend/src/components/preview/PPTPreview.tsx
summary: >-
  (a) React duplicate-key errors (surfaced as the dev "N Issues" badge / SyntaxError)
  on reopened prototype / od_prototype runs from history; (b) the Deck-QA report text
  bled faintly through behind the rendered PPT slides
source: .planning/FIX-REGISTER.md#fix-050
collision_of: FIX-050
invariants: [INV-3, SC-001]
---

# FIX-050c

> **Reused id.** The register uses `FIX-050` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 39/42 (run / history UI) · commit 5bd46942

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

(a) React duplicate-key errors (surfaced as the dev "N Issues" badge / SyntaxError) on reopened prototype / od_prototype runs from history; (b) the Deck-QA report text bled faintly through behind the rendered PPT slides

## Root cause

(a) Build-loop agents all share the prototype-build id, so RunDetailPage's key={agent_id ?? idx} fallback never fired and React logged duplicate keys — fixed to an agent_id+idx composite key. (b) PPTPreview's deck <!DOCTYPE>/<html> extraction used a loose search that matched the Deck-QA agent's inline-quoted <!DOCTYPE html> in its PREPENDED markdown report (≈char 52) instead of the real deck (≈char 1130), leaking the report into the deck iframe — fixed with a line-anchored regex + a trailing-after-</html> strip. Both FE-only, found via live Bedrock UI testing.

## Files changed

- `frontend/src/components/history/RunDetailPage.tsx`
- `frontend/src/components/preview/PPTPreview.tsx`
