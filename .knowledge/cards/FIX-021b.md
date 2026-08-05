---
id: FIX-021b
type: fix
date: 2026-06-30
status: done
area: [frontend, auth]
files:
  - frontend/src/components/workflow/TokenUsageSummary.tsx
summary: >-
  Token count dialog in left panel too large — reduce to single compact line
source: .planning/FIX-REGISTER.md#fix-021
collision_of: FIX-021
ticket: KAN-83
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-021b

> **Reused id.** The register uses `FIX-021` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 22 (UI)

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

Token count dialog in left panel too large — reduce to single compact line

## Root cause

TokenUsageSummary rendered a multi-section bordered card (header + input/output breakdown + ratio bar + cost row = ~80px). KAN-83 requires a single line showing only the token count. Replaced the 4-row rounded-xl border bg-gray-50 px-4 py-3 card layout with a single flex items-center gap-1.5 flex-wrap line: ⚡ TOKEN USAGE · 128.7K total · 128.6K input · 11.8K output · ~$0.041

## Files changed

- `frontend/src/components/workflow/TokenUsageSummary.tsx`
