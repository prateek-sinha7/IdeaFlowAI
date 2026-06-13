---
phase: 18-custom-workflow-ux-completeness
plan: 04
subsystem: ui
tags: [react, frontend, model-overrides, capability-palette, dead-code-removal, ISS-014, MODEL-03]

# Dependency graph
requires:
  - phase: 18-03
    provides: useWorkflow run_pipeline payload surface (extraParams/context merge) touched alongside Phase 16
  - phase: 08-api-capabilities
    provides: /api/capabilities palette + model_catalog (API-02) — retained as the relocated picker's data source
provides:
  - "WorkflowComposer.tsx + CapabilityPalette.tsx deleted (orphan-ness fault-injection-proven; no broken imports)"
  - "Per-agent AgentModelPicker relocated into the live AgentsPopup Agents tab"
  - "model_overrides threaded from the relocated picker into the run_pipeline payload (MODEL-03 FE half, end-to-end)"
  - "INV-3/INV-12 dual-impl smell (unrouted composer) resolved"
affects: [composer-routing, IMPLEMENTATION-REGISTER Phase-8/Phase-12 reconciliation, MODEL-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Run-level params (gate_agent_ids, model_overrides) threaded via IdeaInputPage extraParams → DashboardLayout → useWorkflow Object.assign(payload, context) single ingress"
    - "Ref-held selection (modelOverridesRef) so a popup reporting state doesn't re-render the page (mirrors gateSelectionRef)"
    - "Orphan-ness fault injection (rename-to-.bak + tsc/vitest) before deleting suspected dead UI"

key-files:
  created:
    - frontend/src/components/workflow/IdeaInputPage.modelOverrides.test.tsx
    - .planning/phases/18-custom-workflow-ux-completeness/deferred-items.md
  modified:
    - frontend/src/components/workflow/AgentsPopup.tsx
    - frontend/src/components/workflow/IdeaInputPage.tsx
    - frontend/src/hooks/useWorkflow.ts
    - frontend/src/lib/api.ts
    - frontend/src/components/layout/DashboardLayout.waveMount.test.tsx
  deleted:
    - frontend/src/components/workflow/WorkflowComposer.tsx
    - frontend/src/components/workflow/CapabilityPalette.tsx

key-decisions:
  - "RELOCATED (not deleted) AgentModelPicker — rendered it inside the AgentsPopup Agents tab and threaded its selection to model_overrides, delivering MODEL-03 end-to-end. Smallest-diff path: reuse the existing component (keeps its /api/capabilities fetch + user_allowed filter intact) rather than inlining its logic."
  - "model_overrides path uses the EXISTING generic Object.assign(payload, context) merge in useWorkflow — no new plumbing. Made it explicit via a comment (single send site, no double-send) for traceability."
  - "model_overrides is included in extraParams ONLY when ≥1 non-default model is picked; empty selection omits the key → byte-identical run_pipeline payload (INV-3 preserved for all existing runs)."
  - "AgentModelPicker.tsx RETAINED (now consumed by AgentsPopup) — the delete-fallback was NOT taken; MODEL-03 FE half is delivered, not carried to v2."
  - "/api/capabilities + test_capabilities_api.py KEPT untouched (API-02 contract + the model-catalog data source)."

patterns-established:
  - "Fault-inject orphan-ness before deleting: rename → tsc+vitest → delete only if zero NEW broken imports"

requirements-completed: [ISS-014]

# Metrics
duration: 8 min
completed: 2026-06-13
---

# Phase 18 Plan 04: Delete orphaned composer + relocate the model picker (ISS-014) Summary

**Deleted the unrouted WorkflowComposer + its dead CapabilityPalette, and relocated the per-agent AgentModelPicker into the live AgentsPopup Agents tab — wiring its selection into the run_pipeline payload as `model_overrides` to deliver MODEL-03 end-to-end, with the `/api/capabilities` (API-02) contract retained.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-13T15:42:00Z (approx)
- **Completed:** 2026-06-13T15:50:44Z
- **Tasks:** 2
- **Files modified:** 5 modified, 2 created, 2 deleted

## Accomplishments
- Relocated `AgentModelPicker` into the live `AgentsPopup` "Agents" tab (populated from the live `/api/capabilities` model catalog, `user_allowed` only) — no longer orphaned.
- Threaded the per-agent model selection up through `IdeaInputPage` `extraParams` into the `run_pipeline` payload as `model_overrides` (MODEL-03 FE half complete; backend `_validate_model_overrides` already validates + persists it).
- Empty selection omits `model_overrides` → byte-identical payload (INV-3 preserved for existing runs).
- Fault-injection-confirmed orphan-ness, then DELETED `WorkflowComposer.tsx` + `CapabilityPalette.tsx` (the INV-3/INV-12 dual-impl smell).
- Retained `/api/capabilities` + `test_capabilities_api.py` (API-02) — 8 passed, untouched.

## Task Commits

1. **Task 1: Relocate AgentModelPicker + wire model_overrides** - `de30059b` (feat)
2. **Task 2: Fault-inject orphan-ness, delete WorkflowComposer + CapabilityPalette** - `61394d95` (refactor)

## Fault-Injection Result (orphan-ness proof)

Before deleting, renamed `WorkflowComposer.tsx` + `CapabilityPalette.tsx` to `.bak`, then ran `npx tsc --noEmit` and the full `npx vitest run`:
- **tsc:** clean (exit 0, ZERO broken imports) both with the files renamed away AND after real deletion.
- **vitest:** identical result with the files renamed vs. restored — the ONLY failures (7) are pre-existing in `workflowChaining.test.ts` (6) + `AgentProgressPanel.test.tsx` (1), present even with the composer fully restored, and the failing sources were last touched in old commits (4889e3a8, a219fade) — never by phase 18.
- A broken import would have named the live consumer; none appeared → no live consumer existed. The only references to the deleted symbols were two prose comments (`lib/api.ts:516`, `DashboardLayout.waveMount.test.tsx:4`), now tidied to reflect the deletion.

## model_overrides wiring path (relocation branch — the path taken)

`AgentsPopup` model picker `onChange(modelOverrides)` → new `onModelOverridesChange` prop → `IdeaInputPage` `modelOverridesRef` → included in `onRun(..., extraParams)` as `{ model_overrides }` when non-empty → `DashboardLayout.handleRunPipeline` → `onStartPipeline` → `useWorkflow.startPipeline` where `Object.assign(payload, context)` merges it into the `run_pipeline` payload. Proven by `IdeaInputPage.modelOverrides.test.tsx` (selected override reaches `model_overrides`; empty selection omits it).

## Files Created/Modified
- `frontend/src/components/workflow/AgentsPopup.tsx` - Imports + renders `AgentModelPicker` in the Agents tab; new `onModelOverridesChange` prop.
- `frontend/src/components/workflow/IdeaInputPage.tsx` - `modelOverridesRef` + `handleModelOverridesChange`; includes `model_overrides` in `extraParams` only when non-empty; passes the handler to `AgentsPopup`.
- `frontend/src/hooks/useWorkflow.ts` - Explicit comment documenting the `model_overrides` ingress via the existing `Object.assign(payload, context)` merge (single send site; no double-send).
- `frontend/src/lib/api.ts` - Tidied the `getCapabilities` doc comment (relocated picker; composer/palette deleted).
- `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx` - Tidied the "unrouted WorkflowComposer" prose comment.
- `frontend/src/components/workflow/IdeaInputPage.modelOverrides.test.tsx` (created) - MODEL-03 wiring assertion.
- `frontend/src/components/workflow/WorkflowComposer.tsx` (deleted), `CapabilityPalette.tsx` (deleted).
- `.planning/phases/18-custom-workflow-ux-completeness/deferred-items.md` (created) - logs the 7 pre-existing FE test failures (out of scope).

## Decisions Made
See `key-decisions` frontmatter. Headline: RELOCATE (not delete) the picker — MODEL-03 delivered end-to-end; AgentModelPicker.tsx retained because it is now consumed by AgentsPopup.

## Deviations from Plan

None - plan executed exactly as written. (The plan's PREFERRED branch — relocate the picker — was taken; the delete-fallback was not needed.)

## Issues Encountered

**Pre-existing FE test failures (out of scope, NOT fixed):** 7 failures in `workflowChaining.test.ts` + `AgentProgressPanel.test.tsx`, unrelated to this plan (identical with the deleted files restored; sources untouched by phase 18). Logged to `deferred-items.md` per the executor scope boundary. The deletion is import-clean — zero NEW failures introduced, tsc green.

## Verification

- `cd frontend && npx tsc --noEmit` → clean (exit 0), before and after deletion.
- Fault injection (rename → tsc + vitest) → zero broken imports; only pre-existing failures.
- `grep -rn "WorkflowComposer\|CapabilityPalette" frontend/src` → only 2 documentation comments (no imports; files gone).
- `npx vitest run` waveMount + `IdeaInputPage.modelOverrides` suites → green (6 passed).
- `cd backend && python3.11 -m pytest tests/unit/test_capabilities_api.py -q` → 8 passed (API-02 retained, untouched).
- Diff is frontend-only (2 deletions + AgentsPopup/IdeaInputPage/useWorkflow/api.ts/waveMount-test edits + 1 new FE test); backend `/api/capabilities` untouched.

## Threat Surface

No new trust boundary. `model_overrides` ingress crosses into the untrusted run payload but is type-guarded + allow-listed by the UNCHANGED backend `_validate_model_overrides` (websocket.py:95-132). The deleted files were FE-only, unrouted, fault-injection-proven orphaned — no route/permission scope removed. Plan threat register (T-18-08/09/10/SC) fully satisfied; no new flags.

## Next Phase Readiness
- Phase 18 plan-04 complete (the last code plan of the phase; 18-05 docs reconciliation already exists). The IMPLEMENTATION-REGISTER Phase-8 §846 / Phase-12 §1198 "separate composer-routing concern" is resolved here and reconciled in 18-05.
- Carry-forward: the 7 pre-existing FE test failures (`deferred-items.md`) want a dedicated FE-health / workflow-chaining fix in a future plan or the post-phase UI pass. Live Playwright visual confirmation (composer gone, picker in the Agents tab, model_overrides on a real run) is the dedicated post-phase UI pass.

## Self-Check: PASSED

- Created files exist on disk: `IdeaInputPage.modelOverrides.test.tsx`, `deferred-items.md`, `18-04-SUMMARY.md` — all FOUND.
- Deleted files gone: `WorkflowComposer.tsx`, `CapabilityPalette.tsx` — both DELETED.
- Task commits exist: `de30059b`, `61394d95` — both FOUND.

---
*Phase: 18-custom-workflow-ux-completeness*
*Completed: 2026-06-13*
