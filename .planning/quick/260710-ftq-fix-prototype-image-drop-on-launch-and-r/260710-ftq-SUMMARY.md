---
phase: quick-260710-ftq
plan: 260710-ftq
subsystem: ui
tags: [react, nextjs, websocket, multimodal, images, dashboard]

requires:
  - phase: 30-cluster (image input)
    provides: out-of-band `images` run_pipeline carrier + DashboardLayout extraParams image-guard
provides:
  - "Prototype/ppt launch path re-populates pendingOd*Params.images so attached images reach the WS run_pipeline frame"
  - "Home 'Recent runs' chip opens the run in the execution view"
affects: [phase-34-live-pass, prototype, ppt, multimodal-input]

tech-stack:
  added: []
  patterns:
    - "Length-guarded spread preserves INV-3 dormancy (image-less launch byte-identical, no images key)"
    - "Source-lock test idiom (readFileSync grep-style assertions) for the huge page.tsx / DashboardLayout"

key-files:
  created:
    - frontend/src/app/dashboard/launchImageAndRecents.source.test.ts
  modified:
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/components/layout/DashboardLayout.tsx

key-decisions:
  - "Length-guarded images spread (not unconditional) so image-less launches stay byte-identical — INV-3"
  - "Single source-lock test covers both fixes, following revisionFamilyLinkage.source.test.ts idiom"

patterns-established:
  - "Launch-staging setters carry images alongside the existing selections/agentIds length-guarded spreads"

requirements-completed: [DEFECT-1, DEFECT-2]

duration: 3min
completed: 2026-07-10
---

# Quick 260710-ftq: Fix Prototype Image Drop on Launch + Home Recents Chip Summary

**Prototype/ppt launches now carry attached images to the WS run_pipeline frame, and the Home "Recent runs" chip opens the run in the execution view — two surgical FE-only wiring fixes.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-07-10T11:29Z
- **Completed:** 2026-07-10T11:32Z
- **Tasks:** 2
- **Files modified:** 2 source + 1 new test

## Accomplishments
- DEFECT 1: `setPendingOdProtoParams` and `setPendingOdPptParams` in `page.tsx` now include a length-guarded `images` spread, so `pendingOd*Params.images` is populated and DashboardLayout's already-correct extraParams image-guard evaluates true — the outbound `run_pipeline` frame carries the image on the prototype/ppt path (previously the model never saw it).
- DEFECT 2: the Home "Recent runs" chip `onClick` now calls `setMainView("execution")` after `onSelectWorkflowRun?.(run)`, so clicking a recents chip actually opens the run (mirrors every other run-open path).
- Added `launchImageAndRecents.source.test.ts` source-lock proving both wirings are present.

## Task Commits

Each task was committed atomically (code only, no trailer):

1. **Task 1: DEFECT 1 — carry images through prototype + ppt launch setters** - `a4a00682` (fix)
2. **Task 2: DEFECT 2 — Home recents chip opens the run in the execution view** - `ba159678` (fix)

## Files Created/Modified
- `frontend/src/app/dashboard/page.tsx` - Added length-guarded `images` spread to both prototype and ppt launch-staging setters (state types already declared `images`; `pending` object already carried `draft.images`).
- `frontend/src/components/layout/DashboardLayout.tsx` - Recents chip `onClick` now switches the shell to the execution view on open.
- `frontend/src/app/dashboard/launchImageAndRecents.source.test.ts` (new) - Source-lock: images spread present TWICE in page.tsx + recents chip calls `setMainView("execution")`.

## Decisions Made
None beyond the plan — executed exactly as written. Used the length-guarded spread (not unconditional) to preserve INV-3 image-less byte-identity, matching the sibling `selections`/`agentIds` spreads.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## Verification (offline only — per plan)
- `npx tsc --noEmit` (after mockApi.ts filter): **0** new type errors (identity vs baseline 0).
- `grep -c` images spread in page.tsx: **2** (both setters).
- `grep -c` `onSelectWorkflowRun?.(run); setMainView("execution")` in DashboardLayout.tsx: **1**.
- `npx vitest run` (useWorkflow.imagePayload + IdeaInputPage.imageInput + DashboardLayout.catalogHome + DashboardLayout.waveMount + launchImageAndRecents.source): **5 files / 13 tests green**.
- `git diff` confined to the two source files + new test; no backend/engine/manifest/golden touched.

Live Bedrock proof (prototype run with an attached image whose outbound `run_pipeline` frame carries `images` + spec-writer `agent_input.image_count`, and the recents chip opening the run) is performed by the orchestrator against the running local app after this plan — NOT run here.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Multimodal input restored on the prototype/ppt launch path; fused-Home recents chips now live.
- Ready for the orchestrator's live Bedrock verification pass.

## Self-Check: PASSED

---
*Phase: quick-260710-ftq*
*Completed: 2026-07-10*
