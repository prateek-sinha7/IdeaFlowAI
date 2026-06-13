---
phase: 16-terminal-state-integrity-and-reconnect-frame-contract
verified: 2026-06-13T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification: []
deferred:
  - truth: "LIVE Bedrock re-confirmation of SC1 (real ValidationException → pipeline_failed) and SC2 (real Stop → pipeline_cancelled on the wire)"
    addressed_in: "next live pass (defer-live-verification convention)"
    evidence: "CONTEXT.md deferred block + project memory 'defer-live-verification-to-milestone-end'; offline fault-injection + parity evidence is sufficient to mark the phase complete; default AWS profile / acct 473293451041 available when the live pass runs"
---

# Phase 16: Terminal-State Integrity & Reconnect Frame-Contract Verification Report

**Phase Goal:** Make abnormal run outcomes faithful end-to-end — a runner-error run ends `pipeline_failed` (not empty `pipeline_complete`); a cancelled run delivers `pipeline_cancelled` to the live wire; the Preview shows a degraded/failed affordance for a terminal empty run; durable-replay/reconnect frames match live. Engine + WebSocket + one FE affordance only, zero new tables/migrations, INV-3 parity preserved, SC-001 honored.

**Verified:** 2026-06-13
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A runner `error` on every agent ends `pipeline_failed` with `agent_error`s — never empty `pipeline_complete`; partial → `status:degraded` | ✓ VERIFIED | `engine.py:2442` `elif etype == "error":` arm sets `agent_errored`, `break`s; post-loop `if agent_errored:` (`:2585`) emits recoverable `agent_error` + `return`s, skipping result-append + `agent_complete` → failed agent stays in `_failed_agent_ids` → existing F3 maps to terminal. `test_engine_runner_error_arm.py` 2/2 (all-fail→`pipeline_failed`, partial→degraded) via REAL `execute()` + `ScriptedNonTransientError`. `test_model_fallback.py::test_non_transient_propagates` flipped (now asserts `agent_error`). Runner diff `53b939d9..HEAD` is comment-only (WR-03). |
| 2 | A real `cancel_pipeline` delivers `pipeline_cancelled` on the live wire (FE clears cards), DB row `cancelled`; cancel test deterministic | ✓ VERIFIED | `websocket.py:641` cooperative `cancel_event.set()` (not destructive); destructive `task.cancel()` kept only as defensive fallback (`:647`) + disconnect path (`:1268/:1279`). Engine pre-agent gap closed (`engine.py:1539-1563`): transition to `cancelled` + emit `pipeline_cancelled` + `return` before pipeline_complete. 3 drainer sites use `asyncio.timeout()` (`:884/:1800/:2154`). `test_pipeline_cancel.py` 5/5 — drives real `_handle_workflow_execution`, asserts exactly ONE wire ack, `wr.status=="cancelled"`, `task.cancelled() is False`. |
| 3 | Preview shows degraded/failed affordance (not neutral empty) for a terminal empty run, on BOTH live + history-reopen, keyed on server signal | ✓ VERIFIED | `PreviewPanel.tsx:302` `showFailureAffordance = !hasContent && isTerminal && terminalFailure`; live signal `pipelineState.failed/degraded` (`:292`), history `reopenedRunStatus` failed/cancelled/degraded (`:297-300`). `useWorkflow.ts:403-404` sets `failed:true`+`failedAgents` on `pipeline_failed`. WR-01 reopen fix: `page.tsx:1044-1046` content gate includes degraded, `:1067` affordance includes degraded. IN-01 fix: `parseFailedAgentIds`+threading to PreviewPanel (`:1162`). `PreviewPanel.degraded.test.tsx` 9/9. Streaming keeps neutral state (no client empty==failed guess). |
| 4 | Durable-replay revision frames carry real `section`; live-attach ack carries `live:true` | ✓ VERIFIED | `websocket.py:806-818` `_replay_section` derived from owner-scoped `_ReplayRun` row (`owner_id == user.id`) via WR-06 inverse `removesuffix('_revision')+'_output'`, applied at replay send (`:838`); non-revision keeps `None`. Live-attach ack `live: True` (`:871`); no-live-task `live: False` (`:854`). `test_ws_reconnect_replay.py` 10/10. |
| 5 | INV-3 parity: 5 goldens byte-identical; lint-imports 4/0; zero new tables/migrations; SC-001 (no workflow/model literal branching) | ✓ VERIFIED | 5 characterization goldens + banned-patterns + migration-ledger → 44 passed / 7 skipped, NO SNAPSHOT_UPDATE (byte-identical). `lint-imports` 4 kept / 0 broken. No migration/alembic/versions files added; `grep` for `Column(`/`add_column`/`create_table` in phase diff → 0. SC-001: `grep -nE 'ValidationException\|Operation not allowed'` in engine.py + websocket.py → 0; all branches key on generic event type (`error`, cancel) or `_revision` suffix transform. |

**Score:** 5/5 truths verified

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | LIVE Bedrock re-confirmation of SC1 (real ValidationException → pipeline_failed) + SC2 (real Stop → pipeline_cancelled on wire) | next live pass | CONTEXT.md deferred block + `defer-live-verification` project convention; offline fault-injection + parity evidence is sufficient to mark complete |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/execution_engine/engine.py` | `error` consume-arm + pre-agent cancel emit + `_sanitize_agent_error` | ✓ VERIFIED | arm `:2442`, sanitizer `:105`, pre-agent cancel `:1539-1563`; +132/-1 lines |
| `backend/app/api/websocket.py` | cooperative `cancel_event`, `_replay_section`, `live:True` ack | ✓ VERIFIED | `cancel_event.set()` `:641`, `_replay_section` `:816`, `live:True` `:871` |
| `backend/app/agents/deep_agent_runner.py` | runner unchanged except WR-03 comment | ✓ VERIFIED | git diff comment-only; `error` yield behavior preserved |
| `frontend/src/components/preview/PreviewPanel.tsx` | terminal-empty degraded affordance keyed on server signal | ✓ VERIFIED | `DegradedRunAffordance` `:198`, `showFailureAffordance` `:302` |
| `frontend/src/hooks/useWorkflow.ts` | `failed`+`failedAgents` flag on `pipeline_failed` | ✓ VERIFIED | `:403-404` |
| `frontend/src/app/dashboard/page.tsx` | reopen degraded/failed wiring + `reopenedFailedAgents` | ✓ VERIFIED | `:1044-1077`, threaded `:1161-1162` |
| `backend/tests/agents/test_engine_runner_error_arm.py` | fault-injection (all-fail/partial) | ✓ VERIFIED | 2/2 pass, real execute() |
| `backend/tests/unit/test_pipeline_cancel.py` | deterministic cancel-ack | ✓ VERIFIED | 5/5 pass |
| `backend/tests/agents/test_ws_reconnect_replay.py` | section + live:true assertions | ✓ VERIFIED | 10/10 pass |
| `frontend/src/components/preview/PreviewPanel.degraded.test.tsx` | terminal/streaming/content matrix | ✓ VERIFIED | 9/9 pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| engine `_run_agent` error arm | F3 terminal gating | `yield agent_error` → `_failed_agent_ids` | ✓ WIRED | `agent_error` emit `:2596`, return skips completion `:2604` |
| `cancel_pipeline` handler | engine cooperative cancel | `cancel_event.set()` | ✓ WIRED | event created `:1479`/`:1960`, passed to `execute(cancel_event=...)` `:1585`/`:2093`, consumed `engine.py:1539` |
| websocket replay loop | owner-scoped run row type | `removesuffix('_revision')+'_output'` | ✓ WIRED | owner filter `:801/:810`, transform `:816` |
| PreviewPanel terminal-empty | server signal | `pipelineState.failed/degraded` + `reopenedRunStatus` | ✓ WIRED | `:292,:297-302` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Fault-injection + cancel + replay | `pytest test_engine_runner_error_arm test_pipeline_cancel test_ws_reconnect_replay test_model_fallback test_run_revision_ws_dispatch` | 31 passed | ✓ PASS |
| INV-3 goldens + gates | `pytest 5×characterization + banned-patterns + migration-ledger` (no SNAPSHOT_UPDATE) | 44 passed, 7 skipped | ✓ PASS |
| import boundaries | `lint-imports` | 4 kept / 0 broken | ✓ PASS |
| FE affordance | `vitest PreviewPanel.degraded.test.tsx` | 9 passed | ✓ PASS |
| Live Bedrock SC1/SC2 | real ValidationException / Stop | deferred to next live pass | ? SKIP (deferred per convention) |

### Requirements Coverage (ISSUE IDs — cross-referenced to ISSUES-REGISTER)

| Issue | Description | Status | Evidence |
|-------|-------------|--------|----------|
| ISS-016 | runner error swallowed → empty pipeline_complete | ✓ SATISFIED | engine error arm + tests; register row = FIXED (engine, 16-01) |
| ISS-017 | FE neutral empty-state on terminal empty run | ✓ SATISFIED | PreviewPanel degraded affordance + tests (register top-table row still OPEN — doc-tracking lag, see Gaps Summary) |
| ISS-007 | pipeline_cancelled not delivered on live wire | ✓ SATISFIED | cooperative cancel + deterministic test (register row still OPEN — doc lag) |
| ISS-002 | flaky cancel test (wait_for race) | ✓ SATISFIED | asyncio.timeout() at 3 drainers + 5/5 deterministic |
| ISS-008 | replay frames carry section:None | ✓ SATISFIED | `_replay_section` owner-scoped derivation + test |
| ISS-009 | live-attach ack omits live | ✓ SATISFIED | `live:True` ack + test |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | no debt markers (TBD/FIXME/XXX/HACK/PLACEHOLDER) added in phase-modified non-test files | ℹ️ Info | clean |

### Human Verification Required

None for offline completion. LIVE Bedrock re-confirmation of SC1/SC2 is recorded as a deferred follow-up (next live pass), per the `defer-live-verification` project convention — not a blocker for phase completion.

### Gaps Summary

No goal-blocking gaps. All 5 ROADMAP Success Criteria are observably true in the codebase, proven by the targeted offline suite (31 phase tests + 44 parity/gate tests + lint-imports + 9 FE tests, all green) and direct code inspection of the locked CONTEXT decisions A1/A2/A3/B.

Note (non-blocking documentation lag): the ISSUES-REGISTER top table still shows ISS-017/ISS-007/ISS-002/ISS-008/ISS-009 as `OPEN` while the code, tests, and 16-REVIEW/16-REVIEW-FIX confirm they are resolved (only ISS-016 was flipped to FIXED). This is a register-bookkeeping lag, not a code gap — the phase contract is met. Recommend flipping those five register rows to FIXED for auditability, but it does not affect goal achievement.

All review findings (WR-01, WR-02, WR-03, IN-01, IN-03) were fixed in 16-REVIEW-FIX (5/5); IN-02/IN-04 deferred as out-of-scope cosmetic/pre-existing. Each fix was independently re-verified against the code (WR-02 sanitizer present + leak-free; WR-03 comment corrected; WR-01 degraded-reopen gates; IN-01 threaded prop; IN-03 cancelled copy).

---

_Verified: 2026-06-13_
_Verifier: Claude (gsd-verifier)_
