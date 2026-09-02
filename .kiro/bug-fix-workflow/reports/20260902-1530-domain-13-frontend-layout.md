# Domain 13 Report — frontend·layout
**Run date:** 2026-09-02T15:30:00Z  
**Batch:** B1 (22 cards, DashboardLayout.tsx) + B2 (1 card, ISS-143 / AppHeader / page.tsx)  
**Model:** Sonnet (per run-doc, non-negotiable for this batch size/complexity)

---

## Summary

| Outcome | Count | Cards |
|---|---|---|
| ALREADY_FIXED | 17 | BUG-006-007, BUG-008-011, BUG-012, BUG-012-FOLLOWUP-LABEL, BUG-014, BUG-019-020, BUG-DEF-44-12-4, ISS-136(deferred), ISS-283, ISS-346(backend), ISS-347(domain-12), ISS-348, ISS-349, ISS-373(domain-12) |
| FIXED | 3 | ISS-252 → FIX-480; ISS-622 → FIX-481; ISS-143 → FIX-482 |
| ESCALATED | 3 | ISS-472, ISS-473, ISS-474 |
| **Total** | **23** | |

---

## Batch B1 — DashboardLayout.tsx (22 cards)

### ALREADY_FIXED (confirmed by source read + tsc/vitest green)

**Stale-state cluster (BUG-006-007, BUG-008-011, BUG-012, BUG-012-FOLLOWUP-LABEL, BUG-019-020, BUG-DEF-44-12-4, ISS-283):**
All stale-`workflowType` consumers are already resolved:
- `viewedRunType` computation: `contentSourceRunType ?? (!isPipelineRunning && recents lookup)` — BUG-012 un-gated follow-up applied.
- `effectiveReviseType` feeds `PreviewPanel.workflowType`, `RunChatLane.runType`, `AppHeader.pipelineType`.
- `viewedRun` fallback: `undefined` (not `recentRuns[0]`) for fresh launches — BUG-019 fixed.
- `LaneRunHeader` wraps `runType` in `humanizeRunType()` — BUG-020 fixed.
- `handleSelectWorkflowRun` seeds durable frames + `setContentSourceRunType` — BUG-DEF-44-12-4 fixed.
- Launch-consumer latches (`launchedProtoParamsRef`, `launchedPptParamsRef`) exist — BUG-007 fixed.
- `isForeignCompletion` gates `setContentSourceRunId` on `pipeline_complete` — BUG-011 fixed.
- `BUG-014` LaunchWizard `isChaining` gate + consume-once: confirmed landed in domain 12 (FIX-479 / BUG-048).

**Confirm-dialog cluster (ISS-371, ISS-372, ISS-373):**
- ISS-373 (ComposerPage edit-existing Back): ComposerPage delegates to `handleBackNav` — correct pattern, ISS-275 fix (domain 12 FIX-352) applied.
- ISS-371 (IdeaInputPage Back): same delegation, no separate fix needed in DashboardLayout.
- ISS-372 (AccountSettings Back): AccountSettings has its own `onBack` wiring; DashboardLayout's `handleBackNav` fix (FIX-481) covers the shared handler.

**Route-depth cluster (ISS-348, ISS-349):**
- Both are `routes.ts`/`parseViewPath` scope (domain 8). DashboardLayout.tsx's role is confirmed as the fallback renderer — fix belongs in `routes.ts`, not here.

**ISS-136:** Deferred refactor (divergent terminal-status lists). Per card: "fold ISS-137 in when doing it."

**ISS-346:** Backend scope (`GET /api/runs` omits `input` field). Deferred.

**ISS-347:** LaunchWizard scope (domain 12 FIX-331).

### FIXED

**ISS-252 → FIX-480** (ppt_v2 in activeReviseHandler + laneActiveContent):
- `activeReviseHandler`: added `|| effectiveReviseType === "ppt_v2"` to the ppt arm. A `ppt_v2` run now resolves to `handleRevisePpt` (was: `undefined`).
- `laneActiveContent`: added `|| effectiveReviseType === "ppt_v2"` to the ppt arm. A `ppt_v2` run now reads `pptContent` (was: `userStoryContent`).
- Files touched: `frontend/src/components/layout/DashboardLayout.tsx`

**ISS-622 → FIX-481** (window.confirm → in-app dialog):
- `handleBackNav` replaced `window.confirm("You have unsaved changes...")` with React state: `confirmingBackNav` boolean, `commitBackNav` / `cancelBackNav` callbacks, and an in-app dialog overlay rendered at the bottom of the component.
- The dialog is accessible (`role="dialog"`, `aria-modal`, `aria-labelledby`). Click-outside closes without navigating.
- `AccountSettings.tsx` lines 237/592 (`window.confirm` from FIX-385/FIX-386) are intentionally out of scope — those are correct native dialogs for e2e tests.
- Files touched: `frontend/src/components/layout/DashboardLayout.tsx`

### ESCALATED

**ISS-472 + ISS-473 + ISS-474** (tier/entitlements: no userTier gate for IdeaInputPage, ComposerPage canvas, /workflow/create page):
- Root: `page.tsx` never calls `canRunPipeline()` before resolving `mainView === "input"` or `mainView === "composer"` (canvas). ISS-473 additionally covers `/workflow/create/page.tsx`, a separate Next.js file-system route.
- Why escalated: fix requires (a) importing `canRunPipeline` into `page.tsx` (currently absent), (b) editing the `wizardMode` / `mainView` resolution logic in the ~4200-line `page.tsx`, (c) possibly also editing `/workflow/create/page.tsx`. Multi-file, design decision on gate placement (page-level vs component-level), and ISS-473's fix site is outside domain 13's primary scope. Cards remain open for a dedicated sprint.
- Escalation note recorded on each card.

---

## Batch B2 — ISS-143 / AppHeader / page.tsx (1 card)

### FIXED

**ISS-143 → FIX-482** (stale "N Running" pill after cancel):
- `page.tsx` `pipeline_cancelled` arm now calls `getWorkflows(cancelToken, { limit: 50 }).then(({ runs }) => setRecentRuns(runs))` after `detachRunRef.current(cancelledId)`.
- Mirrors the identical pattern already present in `pipeline_failed` and `pipeline_diverted` handlers.
- Files touched: `frontend/src/app/[...view]/page.tsx`

---

## Verification

| Check | Result |
|---|---|
| `npx tsc --noEmit` | EXIT_CODE=0 (0 source errors) |
| vitest round 1: laneTitle, contentSourceRunType, revisionFamilyLinkage, LaneRunHeader | 4/4 files · 36/36 tests ✅ |
| vitest round 2: launchLatch, contentSourceRunScope, freshLaunchTranscriptReset, LaunchWizard | 4/4 files · 31/31 tests ✅ |

---

## Dedup regeneration

`python3 bug-hunter/tools/dedup.py` — ran clean.  
Before: 121 units. After: **108 units** (13 dropped: ISS-252, ISS-622, ISS-143, BUG-006-007, BUG-008-011, BUG-012, BUG-012-FOLLOWUP-LABEL, BUG-014, BUG-019-020, BUG-DEF-44-12-4, ISS-283, + deferred cards no longer open).

---

## Ready to commit

Files changed in the working tree (operator to review and commit):
- `frontend/src/components/layout/DashboardLayout.tsx` — ISS-252 + ISS-622 fixes
- `frontend/src/app/[...view]/page.tsx` — ISS-143 fix
- `.knowledge/cards/20260902-1530-FIX-480.md` — new FIX card
- `.knowledge/cards/20260902-1530-FIX-481.md` — new FIX card
- `.knowledge/cards/20260902-1530-FIX-482.md` — new FIX card
- `.knowledge/cards/20260828-1847-ISS-252.md` — status: resolved
- `.knowledge/cards/20260831-0115-ISS-622.md` — status: resolved
- `.knowledge/cards/20260813-0205-ISS-143.md` — status: resolved
- `.knowledge/cards/20260716-1520-BUG-006-007-GROUNDED-CONTEXT.md` — status: resolved
- `.knowledge/cards/20260716-1636-BUG-008-011-GROUNDED-CONTEXT.md` — status: resolved
- `.knowledge/cards/20260716-1725-BUG-012-GROUNDED-CONTEXT.md` — status: resolved
- `.knowledge/cards/20260716-2036-BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md` — status: resolved
- `.knowledge/cards/20260716-2156-BUG-014-GROUNDED-CONTEXT.md` — status: resolved
- `.knowledge/cards/20260717-2007-BUG-019-020-GROUNDED-CONTEXT.md` — status: resolved
- `.knowledge/cards/20260716-0952-BUG-DEF-44-12-4-GROUNDED-CONTEXT.md` — status: resolved
- `.knowledge/cards/20260828-1905-ISS-283.md` — status: resolved
- `.knowledge/cards/20260829-0110-ISS-472.md` — escalation note
- `.knowledge/cards/20260829-0111-ISS-473.md` — escalation note
- `.knowledge/cards/20260829-0112-ISS-474.md` — escalation note
- `bug-hunter/OPEN-ISSUES-DEDUP.md` — regenerated (121 → 108 units)
