---
id: FIX-004b
type: fix
date: 2026-06-22
status: done
area: [frontend, workflow]
files:
  - frontend/src/components/catalog/WorkflowCatalog.tsx
summary: >-
  Replace loading text with skeleton rows on home page WorkflowCatalog — Tiny "Loading
  workflows…" text shown while API fetches made home page look broken/blank; no
  skeleton showed page structure
source: .planning/FIX-REGISTER.md#fix-004
collision_of: FIX-004
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-004b

> **Reused id.** The register uses `FIX-004` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 20 (Workflow Catalog)

<!-- verbatim from the register -->

### FIX-004 — Home Page Skeleton Loading State

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-78`

#### Root Cause
`WorkflowCatalog` starts with `loading=true` and fetches from `GET /api/workflows` on every mount. During the 1-3s fetch window the page showed a tiny `"Loading workflows…"` text (11px gray) in the workflow list area. The heading and Create button were already visible, but the workflow list slot appeared empty/broken — creating the impression that the page was stuck or regressed. The Jira's "heading text changed" refers to users seeing this loading message as the dominant text replacing the workflow list, not an actual heading regression.

#### Phase Context
- **Phase(s) involved:** Phase 20 — Workflow Catalog (data-driven WorkflowCatalog, 20-02)
- **Relevant register section:** `_register-parts/20-workflow-catalog-data-driven-browse-and-launch-gallery-reali.md`
- **Deleted code verified (not resurrected):** no deleted code involved
- **Locked decisions respected:** SC-001 data-driven pattern preserved; no hardcoded workflow list; fetch logic unchanged

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/catalog/WorkflowCatalog.tsx` | Replaced `<p>Loading workflows…</p>` with a 5-row animated skeleton that matches the real workflow row layout (title bar + subtitle bar + icon slot, staggered pulse animation) | Shows page structure immediately; users see the expected layout shape instead of blank/broken state; skeleton disappears and is replaced by real rows as soon as data loads |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected
- **INV-3** (golden parity): not affected — no backend or deliverable changes
- **INV-12** (no duplication): not applicable
- **SC-001** (zero engine edits): not affected — frontend loading UX only

#### Verification
- TypeScript: 0 diagnostics on `WorkflowCatalog.tsx`
- Skeleton rows use same `divide-y`, `py-5`, `px-3 -mx-3` classes as real rows — layout is consistent
- 5 skeleton rows match the expected 5-6 real workflow rows
- Staggered `animationDelay` provides a natural cascading shimmer

#### Notes
- The actual h1 heading "What would you like to build today?" is correct and unchanged since 20-02; no heading regression exists.
- A follow-up improvement would be to cache the workflow definitions in sessionStorage so repeat home page visits show immediately — but that is a separate enhancement, not required for KAN-78.

| FIX-007 | 2026-06-23 | Enable default audit hooks and add Audit tab for all workflow runs (KAN-73) | Hook infrastructure existed (Phase 8) but was declaration-driven — all manifests declared hooks:[] so no hook_runs rows were ever written and no Audit tab existed | `backend/agents/capabilities/hooks/audit_logger.py` (new), `backend/agents/capabilities/hooks/__init__.py`, `backend/agents/workflows/compiler.py`, `backend/agents/execution_engine/kernel_services.py`, `backend/app/api/runs.py`, `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`, `frontend/src/hooks/useWorkflow.ts`, `frontend/src/components/results/AuditTab.tsx` (new), `frontend/src/components/preview/PreviewPanel.tsx` | Phase 8 (Capabilities Hardened) | INV-1/3/12/SC-001 ✅ | Done |

---
