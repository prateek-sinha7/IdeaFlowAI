---
phase: 16-terminal-state-integrity-and-reconnect-frame-contract
fixed_at: 2026-06-13
review_path: .planning/phases/16-terminal-state-integrity-and-reconnect-frame-contract/16-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
deferred: 2
status: all_fixed
---

# Phase 16: Code Review Fix Report

**Fixed at:** 2026-06-13
**Source review:** `16-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (WR-01, WR-02, WR-03, IN-01, IN-03)
- Fixed: 5
- Deferred (out of scope by objective): 2 (IN-02, IN-04)

## Fixed Issues

### WR-02: Raw runner/exception text forwarded to the client unsanitized

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** `7a9a6b24`
**Applied fix:** The ISS-016 `error` arm captured the runner's raw `str(exc)` and
emitted it verbatim on the `agent_error` event (relayed to the browser and
persisted to `wr.error`). For a non-throttle Bedrock fault that string can carry
ARNs / region / model-id / internal config. Mirrored the chat path's
sanitize-before-emit contract: added a module-level `_sanitize_agent_error`
helper that returns a fixed, bounded, leak-free generic message
("The model rejected this request."); the raw provider text is now kept
server-side only (the `agent_errored` warning log records `raw=…` and
`client=…`). The engine only holds the stringified message (the runner stays
as-is per A1), so a fixed generic message is the structurally leak-proof choice —
`app.agents.llm_errors.map_exception` itself falls back to `internal_error` for
any non-exception input. Keyed on the generic event type only (SC-001).
**Verification:** parse-check OK; the 5 characterization goldens stayed
byte-identical (no SNAPSHOT_UPDATE), `test_banned_patterns` + `test_migration_ledger`
green, and `test_engine_runner_error_arm.py` (fault-injection) still passes — its
assertions check the `agent_error` `agent_id` + terminal semantics, not the
message text, so the sanitization is transparent to it. `lint-imports` 4 kept / 0
broken (the helper imports nothing new; `app.api` boundary untouched).
**Note:** requires human verification of the chosen client copy — the message is
deliberately generic; confirm it matches the desired UX tone.

### WR-03: Stale comment in the runner asserts the engine ignores `error` events

**Files modified:** `backend/app/agents/deep_agent_runner.py`
**Commit:** `a27eacec`
**Applied fix:** Comment-only. Rewrote the non-throttle swallow rationale
(`:514-516`) to state that Phase 16 (ISS-016) reversed the old assumption — the
engine's `_run_agent` consume loop now has an `error` arm that turns the yield
into a recoverable `agent_error` + `pipeline_failed`/`status:degraded` terminal,
so it no longer ignores the event. INV-3 parity for the non-throttle path holds
because the scripted golden model never raises (the arm is dormant on goldens),
not because the engine drops the event. No behavior change.
**Verification:** parse-check OK; covered by the same green golden/gate run.

### WR-01: `degraded` history-reopen renders neither deliverable nor failure affordance

**Files modified:** `frontend/src/app/dashboard/page.tsx`,
`frontend/src/components/preview/PreviewPanel.tsx`,
`frontend/src/types/index.ts`, `frontend/src/components/sidebar/Sidebar.tsx`
**Commit:** `2d2f7c8f`
**Applied fix:** The history-reopen path gated content on `status === "completed"`
and the affordance only on `failed`/`cancelled`, so a run ISS-016 newly persists
as `degraded` showed the neutral empty-state on reopen. Treated `"degraded"` as a
terminal status on BOTH gates: the content gate now renders the partial
deliverable when present (`isContentTerminal = completed || degraded`), and the
`reopenFailureSignal` in PreviewPanel now includes `degraded` so an empty
degraded reopen surfaces the affordance (CONTEXT A2: affordance on both paths).
Widened the `WorkflowStatus` union to include `"degraded"` and `"revising"` so
the `api.ts:288` cast is honest and the comparisons type-check; extended the
exhaustive `Record<WorkflowStatus, …>` status maps in `Sidebar.tsx` (degraded →
amber AlertTriangle, revising → blue Loader2). Keyed on the generic server status
field, never a workflow name (SC-001).
**Verification:** `tsc --noEmit` clean; degraded-reopen test added (below).
**Note:** the content/state gating is logic — flagged for human confirmation that
the degraded-with-partial-deliverable render is desired over the affordance.

### IN-01: `reopenedFailedAgents` prop declared/consumed but never wired

**Files modified:** `frontend/src/app/dashboard/page.tsx`,
`frontend/src/components/layout/DashboardLayout.tsx`,
`frontend/src/components/preview/PreviewPanel.tsx`
**Commit:** `2d2f7c8f`
**Applied fix:** Threaded `reopenedFailedAgents` from `page.tsx` →
`DashboardLayout` → `PreviewPanel`, parallel to `reopenedRunStatus`. Added a
`parseFailedAgentIds` helper that extracts the failed-agent ids the backend
persists into `wr.error` ("…agent(s) failed: `<id1>`, `<id2>`"); the reopen
handler sets it from `fullRun.error` and clears it on every reopen/new-run
alongside `reopenedRunStatus` (all three setter sites mirrored). The affordance
now lists the real failed agents on the history path instead of an empty list.
Server-keyed; no client guess.
**Verification:** `tsc` clean; new degraded-reopen test asserts the two real
failed-agent ids render in the affordance.

### IN-03: `cancelled` reopen labelled "failed or degraded"

**Files modified:** `frontend/src/components/preview/PreviewPanel.tsx`
**Commit:** `2d2f7c8f`
**Applied fix:** `DegradedRunAffordance` now takes a `cancelled` prop (true when
`reopenedRunStatus === "cancelled"`) and branches the copy: a cancelled run reads
"This run was cancelled" / "The run was stopped before producing a deliverable."
rather than "failed or degraded". Live cancel carries no failed/degraded flag
(useWorkflow resets agents to idle), so the cancelled signal is the reopened
server status only.
**Verification:** `tsc` clean; the `reopen+cancelled` test now asserts the
cancelled-specific copy AND the absence of the "failed or degraded" copy.

## Deferred Issues (explicitly out of scope per the fix objective)

### IN-02: Affordance lists raw agent IDs, not display names

**File:** `frontend/src/components/preview/PreviewPanel.tsx:222-226`
**Reason:** Cosmetic only and explicitly excluded by the fix objective. Resolving
kebab-case ids to human-readable `name` values requires plumbing the agent
registry / `pipelineState.agents` name map into the history-reopen path (where
only ids are persisted in `wr.error`), which is a larger UX change than the
terminal-state-integrity scope of this fix pass. The ids are still accurate and
unambiguous; deferred to a follow-up display-polish pass.

### IN-04: Per-chunk cooperative cancel still double-emits `pipeline_cancelled`

**File:** `backend/agents/execution_engine/engine.py:2357-2358,1699` +
`backend/app/api/websocket.py:1742`
**Reason:** Pre-existing (predates Phase 16) and client-invisible — the drainer
breaks on the first terminal and the duplicate frame is discarded by cleanup. The
review itself classifies it "not a Phase-16 regression and no client-visible
impact." Excluded by the fix objective as a non-regression. If revisited, the
per-chunk path should mirror the pre-agent path (yield `pipeline_cancelled` +
`return` cooperatively instead of raising) to eliminate the duplicate at the
source — left for a dedicated cancel-symmetry follow-up.

## Invariant Re-proof (INV-3 parity — mandatory after the engine.py edit)

- 5 characterization goldens (`prototype` / `od_prototype` / `prototype_revision`
  / `od_ppt` / `app_builder`): **byte-identical, no SNAPSHOT_UPDATE**.
- `test_banned_patterns` + `test_migration_ledger`: **green**.
- `test_engine_runner_error_arm.py` (fault-injection): **green** (sanitization
  transparent to the assertions).
- `lint-imports`: **4 kept / 0 broken**.
- Frontend: `tsc --noEmit` **clean**; `PreviewPanel.degraded` **9/9 pass**
  (7 original + 2 new: degraded-reopen with real failed-agent list, cancelled
  wording).

---

_Fixed: 2026-06-13_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
