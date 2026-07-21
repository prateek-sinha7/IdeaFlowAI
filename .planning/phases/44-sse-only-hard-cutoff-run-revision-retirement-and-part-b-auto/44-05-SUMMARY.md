---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 05
subsystem: ui
tags: [sse, rest, react, transport, revision, run_revision, ppt, od_ppt, strategy-a, flag-selected, lineage]

# Dependency graph
requires:
  - phase: 44-01
    provides: "flag-selected SSE down-channel + launch->attach (runConnection.attachRun) — the stream the new revision run attaches to"
  - phase: 44-04
    provides: "the api.ts owner-scoped REST run-command fetcher pattern (postGate/postCancel/postAnswers) + the runConnection.enabled flag-gate idiom"
  - phase: 29
    provides: "the byte-twin REST endpoint POST /api/runs/{id}/revisions (_mint_revision_row + _drive_revision_to_queue -> engine._handle_revision) with owner-scoped parent fence"
provides:
  - "postRevision(token, parentRunId, {target_artifact_type, instruction}) api.ts fetcher -> POST /api/runs/{id}/revisions, returning the created revision run_id"
  - "handleRevisePpt launches PPT/od_ppt revisions via REST /revisions (Strategy A) when the SSE flag is ON — server-side artifact seed + planning-context prepend + exact-kind derived_from lineage preserved (byte-twin of engine._handle_revision) — then attaches the returned run over SSE; the WS run_revision frame stays on the flag-OFF branch (deleted with the BE handler in 44-07)"
  - "Bug (a) fixed: od_ppt_revision now resolves to handleRevisePpt in activeReviseHandler (re-revising a settled od_ppt no longer resolves to undefined)"
  - "Bug (b) fixed/verified: PPT revisions supply contentSourceRunId as the explicit parent on both branches — no orphaned run (source_workflow_run_id written server-side)"
affects: [44-06 (remove the flag), 44-07 (delete the BE run_revision WS handler + _handle_revision WS driver), 44-09 (re-point the mocked e2e harness to REST /revisions)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Flag-selected revision up-channel: REST postRevision (SSE flag ON) | legacy WS run_revision frame (OFF) — exactly one transport per branch, mirroring 44-04's command rewires; the flag + WS branch are removed together in 44-06/44-07"
    - "REST revision launch attaches the returned run_id via runConnection.attachRun(run_id) so a NEW child run streams over SSE immediately (no refreshLiveRuns poll wait) — reuses the W1/44-01 launch->attach seam"

key-files:
  created: []
  modified:
    - "frontend/src/lib/api.ts - postRevision fetcher (RevisionCommand body: target_artifact_type + instruction; parent linkage via the path run id) returning {run_id}"
    - "frontend/src/components/layout/DashboardLayout.tsx - handleRevisePpt flag-gated onto postRevision(contentSourceRunId) + attachRun; od_ppt_revision added to the activeReviseHandler ppt branch; runConnection added to the useCallback deps"

key-decisions:
  - "Kept handleRevisePpt FLAG-SELECTED (REST /revisions when runConnection.enabled, WS run_revision when OFF) rather than the plan's unconditional REST + grep-0 — the NEXT_PUBLIC_SSE_TRANSPORT flag is not removed until 44-06 and the mocked ts-u.revisions specs assert the WS run_revision frame until 44-09; unconditional REST would delete the frame those flag-OFF specs assert. Same orchestrator-guardrail override 44-01/44-04 applied."
  - "Attached the returned revision run_id via runConnection.attachRun(run_id) (not fire-and-forget) — a revision creates a NEW child run that the provider is not yet attached to, so the .then(attachRun) makes it stream over SSE like the W1 launch->attach path."
  - "Passed contentSourceRunId (the on-screen run, page.tsx-tracked) as the explicit parent on both branches — the REST endpoint writes source_workflow_run_id/derived_from server-side from the path run id, so no orphan (bug (b))."

patterns-established:
  - "Pattern: flag-selected revision up-channel — REST postRevision + attachRun (flag ON) | legacy WS run_revision frame (flag OFF); parent linkage is contentSourceRunId on both."

requirements-completed: [W3, "D1", "CTX-04", "WR-03"]

# Metrics
duration: 20min
completed: 2026-07-15
---

# Phase 44 Plan 05: run_revision Retirement (Strategy A) — PPT Revisions over REST /revisions Summary

**handleRevisePpt launches PPT/od_ppt revisions via the byte-twin REST POST /api/runs/{id}/revisions (server-side artifact seed + planning-context + exact-kind derived_from lineage) and attaches the returned run over SSE when the flag is ON, keeping the WS run_revision frame on the flag-OFF branch — plus the two verified pre-existing bugs closed (od_ppt_revision resolves; PPT revisions carry the parent, no orphan).**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-15T22:05:00Z
- **Completed:** 2026-07-15T22:25:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `postRevision` REST fetcher added to `api.ts` — mirrors the backend `RevisionCommand` body (`target_artifact_type` + `instruction`) verbatim, parent linkage via the path run id, returns the created `{run_id}`. It targets the Phase-29 byte-twin of `engine._handle_revision`, so full parity (server seed + planning-context + `derived_from` lineage) is preserved with zero FE re-implementation.
- `handleRevisePpt` rewired flag-selected: SSE ON → `postRevision(getToken(), contentSourceRunId, {target_artifact_type, instruction})` then `runConnection.attachRun(run_id)` so the new child run streams over SSE (W1); OFF → the existing WS `run_revision` frame, kept byte-identical until the BE handler deletion (44-07).
- Bug (a) fixed: `od_ppt_revision` added to the `activeReviseHandler` ppt branch — re-revising a settled od_ppt now resolves to `handleRevisePpt` (was `undefined`).
- Bug (b) fixed/verified: `contentSourceRunId` is supplied as the explicit parent on both branches; the REST endpoint writes `source_workflow_run_id`/`derived_from` server-side from the path run id — no orphaned run.
- `engine._handle_revision` and the BE WS `run_revision` handler are UNTOUCHED (44-07 owns the BE deletion; the REST `/revisions` endpoint keeps using `_handle_revision`).

## Task Commits

Each task was committed atomically (no trailer):

1. **Task 1: add the postRevision REST fetcher in api.ts** - `8bfb1956` (feat)
2. **Task 2: rewire handleRevisePpt to REST /revisions (Strategy A, flag-gated) + fix the 2 bugs** - `950e1f71` (feat)

**Plan metadata:** committed with this SUMMARY.

## Files Created/Modified
- `frontend/src/lib/api.ts` - `postRevision(token, parentRunId, {target_artifact_type, instruction})` → `POST /api/runs/{id}/revisions`, reusing the existing `request`/`authHeaders` machinery (cross-owner/missing parent → `ApiError(404)`), returns `{run_id}`.
- `frontend/src/components/layout/DashboardLayout.tsx` - imports `postRevision`; `handleRevisePpt` Phase-3 branch flag-gated on `runConnection.enabled` (REST `postRevision` + `.then(attachRun)` | WS `run_revision` frame), `contentSourceRunId` passed as the explicit parent on both; `runConnection` added to the `handleRevisePpt` deps; `od_ppt_revision` added to the `activeReviseHandler` ppt branch. The legacy pre-Phase-3 text-injection fallback (`onStartPipeline`) is preserved unchanged for the no-run-id case.

## Decisions Made
- handleRevisePpt kept FLAG-SELECTED, not unconditional REST (see Deviations — the load-bearing intermediate-state rule for this wave).
- The returned revision `run_id` is attached via `runConnection.attachRun` (a NEW child run must be attached to stream over SSE), rather than fire-and-forget.
- `contentSourceRunId` is the explicit parent on both branches (no orphan; server writes lineage).

## Deviations from Plan

### Auto-fixed Issues

**1. [Orchestrator guardrail override] Kept handleRevisePpt FLAG-GATED instead of unconditional REST (grep-0)**
- **Found during:** Task 2 (handleRevisePpt rewire)
- **Issue:** The plan's Task-2 acceptance criterion requires `grep -c 'type: "run_revision"' DashboardLayout.tsx` == 0 (unconditional REST, no WS frame remaining). But `NEXT_PUBLIC_SSE_TRANSPORT` is not removed until 44-06 and the mocked `ts-u.revisions` specs assert the WS `run_revision` frame until the harness is re-pointed in 44-09. Deleting the WS frame this wave would break the flag-OFF intermediate state (the same rule 44-01 and 44-04 applied).
- **Fix:** `if (runConnection.enabled) { postRevision + attachRun } else if (websocketSend) { WS run_revision frame }`. The REST branch is the new Strategy-A behavior; the WS branch is retained byte-identical. Consequently `grep -c 'type: "run_revision"'` returns **1** (only inside the flag-OFF `else` branch) — the plan's grep-0 criterion is intentionally NOT met this wave; 44-06/44-07 remove the flag + the WS branch + the BE handler together.
- **Files modified:** frontend/src/components/layout/DashboardLayout.tsx
- **Verification:** `npx tsc --noEmit` clean; the flag-OFF WS path is byte-identical to baseline (proven — see Issues Encountered: the 3 `ts-u.revisions` reds are identical before/after).
- **Committed in:** 950e1f71 (Task 2)

**2. [Rule 3 - Blocking] Added `runConnection` to the handleRevisePpt useCallback deps**
- **Found during:** Task 2
- **Issue:** The rewired branch reads `runConnection.enabled`/`runConnection.attachRun`; the existing deps array omitted `runConnection` (stale-closure hazard, matches how 44-04 added it to the cancel handlers).
- **Fix:** Added `runConnection` to the `handleRevisePpt` dependency array.
- **Files modified:** frontend/src/components/layout/DashboardLayout.tsx
- **Verification:** `npx tsc --noEmit` clean.
- **Committed in:** 950e1f71 (Task 2)

---

**Total deviations:** 2 (1 orchestrator-guardrail override, 1 blocking).
**Impact on plan:** The SSE-active behavior the plan specifies (PPT revision → REST `/revisions` byte-twin with full parity, no orphan, od_ppt_revision resolves) is fully delivered; the only difference is it is flag-SELECTED rather than force-on this wave (44-06/44-07 remove the flag + WS branch). The deps fix is mechanical. No scope creep, no backend touched.

## Issues Encountered
**3 pre-existing mocked `ts-u.revisions` reds (out of scope — logged to `deferred-items.md` as DEF-44-05-1).** Running the flag-OFF mocked suite as the gate surfaced 3 failures: `TS-U-01`, `TS-U-02`, `TS-U-07`. These were verified PRE-EXISTING: the same 3 fail identically on the pre-44-05 baseline (`1b06e122`) with the two 44-05 files reverted, and `TS-U-07` (user-story revision) is not even touched by 44-05. Root cause is harness/timing drift from the Phase 39/40 redesign that absorbed the per-preview Revise bar into the settled run-lane composer — the composer renders (snapshot shows the "Ask for a change or a follow-up…" placeholder) but `mockWs.waitForClientFrame` times out on the expected frame. W5/44-09 re-points the mocked harness to REST `/revisions` and reconciles these specs. Not fixed here per the deviation scope-boundary rule (pre-existing suite reds unrelated to the task).

## Known Stubs
None — `postRevision` calls the live owner-scoped Phase-29 REST endpoint; the created run streams over the 44-01 SSE down-channel after `attachRun`.

## Threat Surface
No new surface. `POST /api/runs/{id}/revisions` is owner-gated on the PARENT server-side (T-44-05-01 IDOR → 404 via `_mint_revision_row` requiring a real `owner_id` + the owned-parent resolve; covered by `tests/unit/test_rest_revisions.py`); the FE passes the user's own `contentSourceRunId`. T-44-05-02 (orphan) is mitigated by supplying the parent explicitly so `source_workflow_run_id`/`derived_from` are written (engine :5302-5331). No npm installs (T-44-05-SC).

## User Setup Required
None - no external service configuration required. To exercise the REST revision path locally set `NEXT_PUBLIC_SSE_TRANSPORT=1`; unset (default) keeps the WS `run_revision` path.

## Next Phase Readiness
- W3b lands: PPT/od_ppt revisions ride REST `/revisions` (Strategy A, full parity) when the flag is ON, streaming over the 44-01 SSE down-channel; the 2 pre-existing bugs are closed. The FE stops emitting the WS `run_revision` frame on the SSE branch.
- 44-06 removes `NEXT_PUBLIC_SSE_TRANSPORT` (collapse the flag-OFF `else` WS branch here). 44-07 deletes the BE WS `run_revision` handler + `_handle_revision`'s WS driver (KEEP `engine._handle_revision` — REST uses it). 44-09 re-points the mocked `ts-u.revisions` harness to REST `/revisions` (closes DEF-44-05-1).

## Self-Check: PASSED
- Both modified files present on disk (`frontend/src/lib/api.ts`, `frontend/src/components/layout/DashboardLayout.tsx`).
- Both task commits present in git history (`8bfb1956`, `950e1f71`).
- `npx tsc --noEmit` clean; `postRevision` targets `/revisions` and returns `{run_id}`; `od_ppt_revision` in the activeReviseHandler ppt branch; `handleRevisePpt` calls `postRevision(contentSourceRunId)`; `engine._handle_revision` untouched (FE-only plan).

---
*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto*
*Completed: 2026-07-15*
