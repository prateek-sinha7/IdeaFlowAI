---
phase: 41-configure-composer-rebuild-b7
plan: 06
subsystem: ui
tags: [react, composer, launch-seam, onStartPipeline, custom-pipeline, playwright-mocked]

# Dependency graph
requires:
  - phase: 41-04
    provides: full-page ComposerPage (Simple view + SummaryRail Run-once button) + Save-to-catalogue via createUserWorkflow/NameWorkflowModal
  - phase: 41-05
    provides: Composer Canvas view + docked Run summary Run-once button (CanvasView)
provides:
  - Composer Run-once launches the composed workflow through the EXISTING onStartPipeline → startPipeline seam (Simple SummaryRail + Canvas docked summary)
  - The composed run crosses the wire as run_pipeline with base_pipeline_type='custom' (fixed at entry, ND-AH) + the composed agent ids + SelectionsMap/gate agents as extraParams
  - Functional mocked-e2e (composer-run.spec.ts) proving Run-once fires the launch and transitions to the run/execution screen
affects: [41-07, composer, launch]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Composer Run-once reuses the EXISTING owner-scoped onStartPipeline(base_pipeline_type, brief, agentIds, attachedSkills, attachedHooks, extraParams) seam — the SAME arg convention the revision launch sites use; no new contract/endpoint, no engine edit (SC-001)"
    - "ComposerPage exposes an onRun callback that assembles the composed run; DashboardLayout maps it onto onStartPipeline (reset → start), mirroring the revision call-sites — the run lands on mainView='execution' via the UNCHANGED startPipeline path (pipelineState.isRunning flip)"
    - "base_pipeline_type is the composer's fixed-at-entry workflowType ('custom' for the compose entry) — the SAME value Save-to-catalogue persists, so Run + Save carry an identical base (ND-AH)"

key-files:
  created:
    - "frontend/e2e/tests/composer-run.spec.ts"
  modified:
    - "frontend/src/components/workflow/composer/ComposerPage.tsx"
    - "frontend/src/components/layout/DashboardLayout.tsx"

key-decisions:
  - "CORRECTION-1 applied: mirrored the intact revision launch call-sites in DashboardLayout (~:589-646) as the canonical arg convention — NOT a 41-03 configure onLaunch (the Configure surface was reverted and no longer exists)"
  - "CORRECTION-2 applied: base_pipeline_type = 'custom' for the Composer — threaded as ComposerPage.workflowType (which IS 'custom' at the compose entry, and the SAME value handleSave persists), so Run + Save stay consistent (ND-AH) and the compose entry launches as 'custom'"
  - "The Run-once button lives in CanvasView (the docked Run summary), NOT CanvasConfigRail (the per-node config rail); CanvasView was already threaded onRunOnce in 41-05, so no CanvasConfigRail edit was needed"
  - "The composer captures no dedicated run brief; the identity description (fallback: name) is passed as the run message — a bare 'custom' launch is valid (no template requirement), so no fabricated brief/cost (ND-AG)"
  - "extraParams carries the composed SelectionsMap + gate_agent_ids (the gate-bearing agents) — the SAME shared-data-model fields the existing launch already accepts (T-41-06-02 mitigation); no fabricated cost/metering field"
  - "Save-to-catalogue was ALREADY wired in 41-04 (handleSave → createUserWorkflow via NameWorkflowModal, base_pipeline_type: workflowType) — confirmed, no change needed (ND-AH)"

requirements-completed: [CMPUI-04]

# Metrics
duration: ~40min
completed: 2026-07-14
---

# Phase 41 Plan 06: Composer Run wiring Summary

**Composer "Run once" (Simple SummaryRail + Canvas docked summary) launches the composed workflow through the EXISTING onStartPipeline → startPipeline seam as a base_pipeline_type='custom' run carrying the composed agent ids + SelectionsMap/gate agents — additive FE only, no engine/backend/manifest change, no new contract, no fabricated cost (ND-AG); Save-to-catalogue confirmed reusing createUserWorkflow (ND-AH).**

## What was built

- **ComposerPage.tsx** — added an `onRun(base_pipeline_type, brief, agentIds, extraParams)` prop and an internal `handleRunOnce` that assembles the composed run: `workflowType` → base_pipeline_type ('custom' at the compose entry, ND-AH), the identity description/name → the run brief, `pipelineAgents` → agent ids, the `SelectionsMap` + gate-bearing agent ids → `extraParams` (`selections`, `gate_agent_ids`). Both the Simple `SummaryRail` and the Canvas `CanvasView` docked Run-once now receive `onRunOnce={onRun ? handleRunOnce : undefined}` (previously inert `undefined`).
- **DashboardLayout.tsx** — the `<ComposerPage>` render now passes `onRun`, mapping it onto the EXISTING `onStartPipeline(type, brief, agentIds, attachedSkills, attachedHooks, extraParams)` seam after `onResetPipeline()` — exactly mirroring the revision launch sites. `startPipeline` flips `pipelineState.isRunning`, which auto-transitions the surface to `mainView='execution'` via the unchanged effect (DashboardLayout:404-411).
- **composer-run.spec.ts** (mocked project) — CR-01 (Simple) composes 2 agents, clicks "Run once now", and asserts the outbound `run_pipeline` frame carries `pipeline_type='custom'` + a 2-element `agent_ids` array, then that the surface transitions to the run screen (composer summary rail gone, execution chat lane visible). CR-02 (Canvas, lightly) composes 1 agent, switches to Canvas, clicks the docked "Run once", and asserts the same launch + transition.

## Verification (raw evidence)

- `npx tsc --noEmit` → **0 errors** (the root tsconfig `include: **/*.ts` also typechecks `e2e/**`; the plan's `-p e2e/tsconfig.json` command referenced a config that does not exist in this repo — e2e is covered by the root run, which is clean including the new spec).
- `npx playwright test --project=mocked composer-run` → **2 passed** (CR-01 Simple, CR-02 Canvas).
- `npx vitest run ComposerPage.test.tsx CanvasView.test.tsx DashboardLayout.waveMount.test.tsx` → **26 passed** (no regression from the wiring).
- Diff scope: `git show --pretty="" --name-only HEAD` lists only `frontend/…` paths (ComposerPage.tsx, DashboardLayout.tsx, composer-run.spec.ts) — **no agents/ backend/ manifest/ migrations/ *.py**. The additive-FE-only diff-scope gate holds on the COMMIT, not just the working tree.
- Composer Run path grep: `ComposerPage.tsx:288 onRun(…)` → `DashboardLayout.tsx:1697 onStartPipeline(type, brief, agentIds, attachedSkills, attachedHooks, extraParams)`, where `type` = `workflowType` = `'custom'` at the compose entry (proven at runtime by the e2e assertion `expect(frame.pipeline_type).toBe('custom')`).

## Deviations from Plan

- **[Correction-1 applied]** Mirrored the intact revision launch call-sites (DashboardLayout ~:589-646) as the arg convention, NOT a 41-03 configure onLaunch — the Configure surface was reverted and no longer exists. (Per the orchestrator's settled inline correction.)
- **[Correction-2 applied]** base_pipeline_type = `'custom'` for the Composer, threaded as `workflowType` (which is `'custom'` at the compose entry and the same value Save persists). (Per the orchestrator's settled inline correction.)
- **[Plan file-list mismatch — no action needed]** The plan listed `CanvasConfigRail.tsx` and `SummaryRail.tsx` under files_modified, but the Run-once button lives in `CanvasView.tsx` (docked Run summary), and both `SummaryRail`/`CanvasView` were already built (41-04/41-05) to accept `onRunOnce`. Only the parent wiring (ComposerPage + DashboardLayout) needed changing; no edit to CanvasConfigRail/SummaryRail was required.
- **[Save-to-catalogue already wired]** ND-AH's Save path (`createUserWorkflow` via `NameWorkflowModal`, `base_pipeline_type: workflowType`) was implemented in 41-04 — confirmed present, no change.
- **[e2e tsconfig]** The plan's `npx tsc --noEmit -p e2e/tsconfig.json` targets a non-existent config; the repo has a single root `tsconfig.json` whose `**/*.ts` include already typechecks the e2e spec (verified 0 errors).

## Known Stubs

None — the Run-once path is fully wired to the live seam; no placeholder/mock data. (The composer captures no dedicated run brief input, so the identity description/name is used as the run message — a bare `custom` launch is valid; this is a design choice, not a stub.)

## Self-Check: PASSED

All created/modified files exist on disk; commit 19f9fdf7 present in git log.
