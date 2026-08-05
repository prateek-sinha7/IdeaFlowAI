---
id: FIX-039b
type: fix
date: 2026-07-06
status: done
area: [backend, workflow]
files:
  - backend/app/api/websocket.py
summary: >-
  Workflow history incorrect titles — 3 root causes in websocket.py: wizard-chain
  reuses source title, run_revision never calls title gen, legacy revision placeholder
  shows raw HTML marker
source: .planning/FIX-REGISTER.md#fix-039
collision_of: FIX-039
ticket: KAN-92
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-039b

> **Reused id.** The register uses `FIX-039` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 14/16/22

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

Workflow history incorrect titles — 3 root causes in websocket.py: wizard-chain reuses source title, run_revision never calls title gen, legacy revision placeholder shows raw HTML marker

## Root cause

(1) _generate_workflow_title wizard-chain path wrote source pipeline's Title verbatim with no pipeline_type suffix; (2) _handle_revision_execution set title=f"Revision: {instruction[:50]}" and never scheduled _generate_workflow_title; (3) _handle_workflow_execution WorkflowRun placeholder fell through to or content for revision messages starting with === EXISTING … ===, showing raw HTML marker for 2-5s

## Files changed

- `backend/app/api/websocket.py`
