---
id: FIX-041b
type: fix
date: 2026-07-08
status: done
area: [frontend, evals]
files:
  - frontend/src/components/workflow/prototype/TemplateCard.tsx
  - frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx
summary: >-
  OD/PPT gallery card shows a broken/blank image when a thumbnail 404s — no fallback
  to the live iframe unless has_thumbnail is already false
source: .planning/FIX-REGISTER.md#fix-041
collision_of: FIX-041
invariants: [INV-3]
relates: [FIX-039]
---

# FIX-041b

> **Reused id.** The register uses `FIX-041` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 4 (OD catalog UI) · builds on FIX-039/040

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

OD/PPT gallery card shows a broken/blank image when a thumbnail 404s — no fallback to the live iframe unless has_thumbnail is already false

## Root cause

The thumbnail <img> in TemplateCard and CompactPPTCard had an onLoad but NO onError handler; the thumbnail-vs-iframe choice keyed solely off the backend has_thumbnail flag. When that flag is stale (thumbnail generated at build time, not committed — FIX-040) or the file 404s at request time, the <img> fails silently and the card sticks on the pulse placeholder / broken image instead of degrading to the FIX-039 live iframe. Fix (FE-only): add a thumbnailError state; on <img> onError, set it (and force-mount the iframe), which nulls thumbnailUrl so the existing iframe fallback path renders.

## Files changed

- `frontend/src/components/workflow/prototype/TemplateCard.tsx`
- `frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx`
