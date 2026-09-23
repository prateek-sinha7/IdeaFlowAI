---
id: BUG-012-GROUNDED-CONTEXT
type: bug
kind: event
title: BUG-012 — grounded fix spec
status: resolved
applies_to:
  phases: []
  modules:
  - DashboardLayout
  - User
  - WorkflowHistory
  - app
  - contentSourceRunScope.source.test
  - core
  globs:
  - page.tsx
  - DashboardLayout.tsx
  - PreviewPanel.tsx
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - ts-t.history.spec.ts
  - contentSourceRunScope.source.test.ts
  requirements: []
locked_constraints: []
verification:
  type: manual
  status: required
  test_files: []
compact_summary: 'Reopened od_ppt/od_prototype runs render blank because PreviewPanel''s detectedType short-circuits on stale workflowType before consulting typed content; fix threads a durable contentSourceRunType.'
last_updated: '2026-08-14'
author: 'Bilal Arshad <bilala@hexaware.com>'
author_source: applies-to-glob
---

# BUG-012 — grounded fix spec (reopened typed deck renders blank; DURABLE viewed-run-type binding)

> Frontend-only. The 4th and last stale-`workflowType` consumer (siblings: BUG-006 label = FIXED, BUG-008 generic gate = FIXED). Root cause verified to file:line by a deep-investigation agent + orchestrator source spot-checks. User chose the **durable** fix (thread the viewed run's real type end-to-end; no recents-window caveat). Executable spec for a `gsd-quick`.

## The bug (VERIFIED)
Reopening a completed **od_ppt** (and **od_prototype**) run renders the run-screen Preview **BLANK** despite the deck being correctly loaded. Live-verified: od_ppt run `cbd46671-…` has 20,183 chars of valid deck HTML (`mime text/html`) yet reopens blank, with the render-mode chrome mislabeled **"RENDERS AS User Stories"** on an od_ppt run.

## Root cause (VERIFIED — dispatch keyed on a stale `workflowType`, NOT a data gap)
1. The deck **is** seeded on reopen: `page.tsx:1310-1311` runs `setPptContent(fullRun.output)` for od_ppt (`:1312-1313` `setPrototypeContent` for od_prototype). `pptContent` is passed to `<PreviewPanel pptContent=… >` (`DashboardLayout.tsx:1821`). Not a data gap.
2. `PreviewPanel.tsx:536` `detectedType = workflowType || (userStoryContent?…:pptContent?"ppt":…)` — the `workflowType` prop is truthy-**stale** (`DashboardLayout.tsx:1825` passes `workflowType={workflowType}`, DashboardLayout state default `"user_stories"` at `:250-256`; the only rebinder `:330-368` is `if (pipelineState?.isRunning)`-gated at `:331` and never fires on a terminal reopen). So `detectedType` short-circuits to `"user_stories"` and **never consults the seeded `pptContent`**.
3. `renderType="user_stories"` (`:538-545`) → `renderDeliverable()` calls `FIRST_PARTY_RENDERERS["user_stories"]?.()` (`:893`), which returns `null` (no `userStoryContent`); the generic step is skipped (od_ppt seeds a TYPED slot, not `genericDeliverable`); **`return null` (`:903`) → blank.** The `"ppt"` renderer holding the deck is never dispatched.

**Why the earlier "user_stories reopens perfectly" screenshot was luck:** the stale default equals `"user_stories"`, so a reopened user_stories run coincidentally matches. Launch an od_ppt run first (binds `workflowType="ppt"`), then reopen a user_stories run → *it* would blank. The defect is general: **any reopened run whose type ≠ the stale `workflowType` blanks.** (BUG-008 does NOT cover this — it decoupled only `hasGenericDeliverable`, the GENERIC channel; od_ppt/od_prototype seed TYPED slots. app_builder routes through the generic-else `page.tsx:1314` → rescued by BUG-008, so it is NOT blank.)

## The DURABLE fix (chosen) — thread the viewed run's REAL type end-to-end
The recents-based `viewedRunType` (`DashboardLayout.tsx:1265-1268`) is `undefined` for runs outside the recents window (the caveat of the targeted BUG-006-style one-liner). The durable source is `fullRun.type`, captured at reopen. Thread it:

### 1. `frontend/src/app/dashboard/page.tsx`
- **Declare** (after `:165` `const [contentSourceRunId, …] = useState<string|null>(null);`):
  ```
  const [contentSourceRunType, setContentSourceRunType] = useState<WorkflowType | null>(null);
  ```
  (`WorkflowType` is already imported/used in this file for the reducer; if a cast is needed use `fullRun.type as WorkflowType`.)
- **Set on reopen** — immediately after `setContentSourceRunId(fullRun.id);` (`:1244`):
  ```
  setContentSourceRunType((fullRun.type as WorkflowType) ?? null);
  ```
- **Clear on a fresh (non-revision) launch** — immediately after `setContentSourceRunId(null);` (`:1484`, inside the fresh-run reset block that clears pptContent/prototypeContent/genericDeliverable):
  ```
  setContentSourceRunType(null);
  ```
- **Pass to DashboardLayout** — beside `contentSourceRunId={contentSourceRunId}` (`:1507`):
  ```
  contentSourceRunType={contentSourceRunType}
  ```

### 2. `frontend/src/components/layout/DashboardLayout.tsx`
- **Add the prop** to the component's props type (near `:75 contentSourceRunId?: string | null;`) and destructure it (near `:210`): `contentSourceRunType?: WorkflowType | null;`.
- **Fold it into `viewedRunType`** (`:1265-1268`) — prefer the durable threaded type, fall back to the recents lookup (identical value for in-recents runs; defined for out-of-recents runs where recents returns undefined):
  ```
  const viewedRunType =
    !isPipelineRunning && contentSourceRunId != null
      ? (contentSourceRunType ?? recentRuns?.find((r) => r.id === contentSourceRunId)?.type)
      : undefined;
  ```
  This leaves `effectiveReviseType = viewedRunType ?? workflowType` (`:1269`) unchanged in form but now durable.
- **Feed the viewed type to the PreviewPanel render dispatch** — at `:1825` change `workflowType={workflowType}` to:
  ```
  workflowType={effectiveReviseType}
  ```
  During live/launch, `viewedRunType` is `undefined` (gated on `!isPipelineRunning`) → `effectiveReviseType === workflowType` → **byte-identical, no regression**. On a terminal reopen → the viewed run's real type → `detectedType`/`renderType` correct → the right first-party renderer fires. **PreviewPanel.tsx itself is NOT edited** — the dispatch is already correct once fed the right type. (Mirrors the shipped BUG-006 fix, which already feeds `effectiveReviseType` to the type LABEL at `:1745`.)

**Intended consequence (not scope creep):** because `viewedRunType` now sources durably, the revise-handler selection (`:1270`) and the type label (`:1745`, BUG-006) also become correct for out-of-recents reopened runs — the same `viewedRunType`, sourced better. Confirm no at-risk test regresses (in-recents runs are unchanged — `contentSourceRunType` equals the recents type there).

## Scope fences (STRICT)
- **Frontend only.** Files: `page.tsx`, `DashboardLayout.tsx`, + tests. Do NOT edit `PreviewPanel.tsx` (the dispatch is correct once fed the right type), the `FIRST_PARTY_RENDERERS` table, `GenericDeliverablePreview`, or the P18 sandbox contract. Do NOT touch the j1u/lb6/n2d fixes or the SSE/reducer path (BUG-012 is a reopen-time binding, NOT a live-frame-scoping bug — orthogonal to the deferred systemic per-run-subscriber fix).
- Preserve the primary launch→watch flow **byte-identically** (viewedRunType undefined during live → workflowType).

## Constraints
- Branch **feat/ui-2**. NO commit trailer. NEVER push. FE cwd-sensitive (run from `frontend/`; kill :3000 before mocked Playwright).
- SC-001: DashboardLayout/PreviewPanel are guarded — the fix keys on `run.type` / an existing type variable, adds **no workflow-name string literal**. page.tsx is exempt.
- Keep at-risk green: `ts-u.revisions`, `revisionFamilyLinkage.source`, `ts-t.history` (incl. TS-T-04b), `WorkflowHistory.genericReopen`, `DashboardLayout.laneTitle`/`launchLatch`, and the n2d tests (`PreviewPanel.genericDeliverable`, `contentSourceRunScope.source`). The "132/0" baseline is stale; the 8 pre-Phase-42 vitest reds in untouched files are NOT regressions.

## Verification (executor)
- `npx tsc --noEmit` clean.
- **BUG-012 fail-before / pass-after (the core proof):** a mocked-Playwright reopen (extend `ts-t.history.spec.ts`, e.g. TS-T-04c) — History-tap a `type:"od_ppt"` completed run whose `output` is deck HTML → assert the deck renders on the shared run screen (the `ppt`/deck renderer output is present) and NOT the blank/"Output will appear here" state; **fail-before** (blank) must be observed against the unmodified tree, **pass-after** GREEN. Mirror for an `od_prototype` reopen if cheap. PLUS a source-lock (mirror `contentSourceRunScope.source.test.ts`) asserting `setContentSourceRunType(` is set on reopen + cleared on the fresh-launch reset + `workflowType={effectiveReviseType}` at the PreviewPanel site.
- **No-regression:** reopened user_stories still renders (now via the real type, not coincidence); a launched run renders its live deliverable (launch→watch byte-identical); reopened app_builder unchanged (generic path); the at-risk suites above green.
- Executor does NOT run live Bedrock — the orchestrator does the live proof (reopen a real od_ppt run → deck renders; reopen an od_prototype run → prototype renders).
