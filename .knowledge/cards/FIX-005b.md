---
id: FIX-005b
type: fix
date: 2026-06-22
status: done
area: [frontend, workflow]
files:
  - frontend/src/app/workflow/ppt/templates/page.tsx
  - frontend/src/app/workflow/prototype/templates/page.tsx
summary: >-
  Add speech-to-text and file attach to PPT and prototype wizard brief inputs — Both
  wizard pages (/workflow/ppt/templates, /workflow/prototype/templates) had a bare
  textarea with no toolbar
source: .planning/FIX-REGISTER.md#fix-005
collision_of: FIX-005
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-005b

> **Reused id.** The register uses `FIX-005` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 20/21 (wizard pages)

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

Add speech-to-text and file attach to PPT and prototype wizard brief inputs

## Root cause

Both wizard pages (/workflow/ppt/templates, /workflow/prototype/templates) had a bare textarea with no toolbar; IdeaInputPage (used by user_stories) had both buttons, making them appear only on the first workflow

## Files changed

- `frontend/src/app/workflow/ppt/templates/page.tsx`
- `frontend/src/app/workflow/prototype/templates/page.tsx`
