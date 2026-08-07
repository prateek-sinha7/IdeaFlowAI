---
id: FIX-003b
type: fix
date: 2026-06-16
status: done
area: [frontend, auth]
files:
  - frontend/src/app/workflow/ppt/templates/page.tsx
  - frontend/src/app/workflow/prototype/templates/page.tsx
summary: >-
  PPT/Prototype wizard hides brief textarea — stale chain.from in sessionStorage
source: .planning/FIX-REGISTER.md#fix-003
collision_of: FIX-003
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-003b

> **Reused id.** The register uses `FIX-003` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 21

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

PPT/Prototype wizard hides brief textarea — stale chain.from in sessionStorage

## Root cause

chain.from was never removed from sessionStorage after previous chained run; on fresh wizard open the page read it, set isChaining=true, and hid the brief textarea and showed "CHAINED PRESENTATION · STEP 1 OF 1"

## Files changed

- `frontend/src/app/workflow/ppt/templates/page.tsx`
- `frontend/src/app/workflow/prototype/templates/page.tsx`
