---
id: FIX-216b
type: fix
date: 2026-08-11
status: done
area: [backend]
files:
  - backend/app/api/run_commands.py
summary: >-
  od_prototype/od_ppt revision maps to wrong pipeline type —
  od_prototype_revision has no registered agents and is excluded from hexaware
  tier, causing pipeline_not_entitled on Concierge-proposed revisions
invariants: [INV-1, INV-3, INV-12, SC-001]
relates: [FIX-189, FIX-212]
---

## Description

When the Concierge proposed a revision for an `od_prototype` or `od_ppt` run,
the `_dispose_concierge_proposal` revision disposal path derived:
`revision_pipeline_type = od_prototype_revision`

This pipeline type has no registered agents AND is excluded from the hexaware
tier's entitlements, causing `pipeline_not_entitled` → HTTP 403.

## Root Cause

`_dispose_concierge_proposal` revision channel used `wr_type` verbatim as the
fallback `target`, producing `od_prototype_output` → `od_prototype_revision`.

The equivalent fix for the direct REST revision endpoint existed in
`create_revision` (FIX-216a, a sibling fix) but was not applied to the
Concierge disposal path.

## Fix

Added `_OD_BASE_MAP = {"od_prototype": "prototype", "od_ppt": "ppt"}` lookup
in `_dispose_concierge_proposal` revision channel (mirrors the existing map
in `create_revision`):
- `od_prototype` → `base_type=prototype` → `target=prototype_output` → `prototype_revision` (has agents, entitled)
- `od_ppt` → `base_type=ppt` → `target=ppt_output` → `ppt_revision` (has agents, entitled)

## Invariants

- INV-1/3/12/SC-001 ✅ — generic suffix/prefix strip, no workflow-name literal
