---
id: FIX-040b
type: fix
date: 2026-07-06
status: done
area: [frontend, sse]
files:
  - frontend/src/components/layout/DashboardLayout.tsx
summary: >-
  Notification Panel shows raw context block text for chained/revision runs —
  addRunningNotification called with raw enrichedInput before marker stripping
source: .planning/FIX-REGISTER.md#fix-040
collision_of: FIX-040
ticket: KAN-93
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-040b

> **Reused id.** The register uses `FIX-040` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 22 (notifications) · Phase 25 (parseRunInput)

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

Notification Panel shows raw context block text for chained/revision runs — addRunningNotification called with raw enrichedInput before marker stripping

## Root cause

5 addRunningNotification call sites in DashboardLayout.tsx passed enrichedInput.slice(0,60) or message.slice(0,60) without stripping injected === CONTEXT FROM PREVIOUS === / === EXISTING PROTOTYPE HTML === markers. Fix: use already-computed chainBrief/historyBrief (stripped) in chain handlers; apply parseRunInput() in handleRunPipeline, handleQuestionnaireSubmit, handleQuestionnaireSkip

## Files changed

- `frontend/src/components/layout/DashboardLayout.tsx`
