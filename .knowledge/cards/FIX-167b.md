---
id: FIX-167b
type: fix
date: 2026-08-03
status: done
area: [frontend, backend, artifacts]
files:
  - frontend/src/components/chat/ResultCard.tsx
  - backend/app/agents/chat_narrator.py
  - frontend/src/app/dashboard/page.tsx
summary: >-
  unified family chat — inline pipeline/deliverable cards, gate-approval/revision
  narrator projections, family-aware transcript seed
source: .planning/FIX-REGISTER.md#fix-167
collision_of: FIX-167
ticket: KAN-154
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-167b

> **Reused id.** The register uses `FIX-167` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 31/43 (ResultCard/chat_narrator), Phase 36 (family API)

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

unified family chat — inline pipeline/deliverable cards, gate-approval/revision narrator projections, family-aware transcript seed

## Root cause

3 gaps: ResultCard rendered pipeline/deliverable as boxes (extended inline-link path); chat_narrator had no projection for review_gate_approved or revision pipeline_start; seedRunChatTranscript fetched single-run only (now aggregates family via getRunFamily)

## Files changed

- `frontend/src/components/chat/ResultCard.tsx`
- `backend/app/agents/chat_narrator.py`
- `frontend/src/app/dashboard/page.tsx`
