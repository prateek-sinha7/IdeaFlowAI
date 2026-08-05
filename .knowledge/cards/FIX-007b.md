---
id: FIX-007b
type: fix
date: 2026-06-23
status: done
area: [backend, frontend, workflow]
files:
  - backend/agents/capabilities/hooks/__init__.py
  - backend/agents/workflows/compiler.py
  - backend/agents/execution_engine/kernel_services.py
  - backend/app/api/runs.py
  - frontend/src/types/index.ts
  - frontend/src/lib/api.ts
  - frontend/src/hooks/useWorkflow.ts
  - frontend/src/components/preview/PreviewPanel.tsx
summary: >-
  Enable default audit hooks and add Audit tab for all workflow runs (KAN-73) — Hook
  infrastructure existed (Phase 8) but was declaration-driven — all manifests declared
  hooks:[] so no hook_runs rows were ever written and no Audit tab existed
source: .planning/FIX-REGISTER.md#fix-007
collision_of: FIX-007
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-007b

> **Reused id.** The register uses `FIX-007` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 8 (Capabilities Hardened)

> No detail section exists in the register for this entry — only the
> summary-table row below. Nothing has been invented to fill the gap.

## Description

Enable default audit hooks and add Audit tab for all workflow runs (KAN-73)

## Root cause

Hook infrastructure existed (Phase 8) but was declaration-driven — all manifests declared hooks:[] so no hook_runs rows were ever written and no Audit tab existed

## Files changed

- `backend/agents/capabilities/hooks/__init__.py`
- `backend/agents/workflows/compiler.py`
- `backend/agents/execution_engine/kernel_services.py`
- `backend/app/api/runs.py`
- `frontend/src/types/index.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/hooks/useWorkflow.ts`
- `frontend/src/components/preview/PreviewPanel.tsx`
