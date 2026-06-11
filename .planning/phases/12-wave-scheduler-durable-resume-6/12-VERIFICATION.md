---
phase: 12-wave-scheduler-durable-resume-6
verified: 2026-06-11T17:45:00Z
status: passed
score: 15/15 must-haves verified
overrides_applied: 0
live_recheck: >
  All 4 human_verification items re-verified LIVE 2026-06-11 (milestone-end live
  re-pass, 12-UAT.md tests 5-8, evidence 12-UAT-EVIDENCE/results-recheck.json):
  (1) WaveTreePanel rendered live wave groups + 2 distinct worker leaves per wave,
  badges flipping running→completed; (2) SIGKILL mid-wave-2 + restart: page
  live-attached via the 12-09 bridge (after_seq=17 → tail 19..29 incl.
  pipeline_complete), resolved out of running; (3) zero single_file fallback
  warnings, deliverable = serialized_sandbox bundle part_a..d.txt; (4) cross-owner
  reconnect_pipeline against a live run demoted to ∅ replay + live:false + null
  status, no stream (CR-01 gate driven through the real handler).
re_verification:
  previous_status: passed (overridden human_needed — STALE, pre-gap-closure; milestone-end live UAT then found 3 gaps, 12-UAT.md status diagnosed)
  previous_score: 6/6
  gaps_closed:
    - "UAT Gap 1: WaveTreePanel was dead UI (mounted only in unrouted WorkflowComposer) — now mounted on the dashboard execution surface, fed waveGroups via a new optional waves prop (12-08)"
    - "UAT Gap 2 (FE half): pipeline_reconnected was silently dropped — handlePipelineMessage now resolves isRunning on live:false + terminal status, ending the post-resume 'running forever' hang (12-08)"
    - "UAT Gap 2a: auto-resumed runs never registered in websocket._PIPELINE_TASKS/_PIPELINE_QUEUES — injected engine→WS bridge (3 optional hooks, wired in app/main.py) registers queue+task; resumed events pushed onto the live queue; None sentinel + cleanup (12-09)"
    - "UAT Gap 2c: pipeline_reconnected.status was null — workflow_runs.workspace_id now stamped consistently with the run_events sink via the existing authz.set_run_scope seam (12-09)"
    - "UAT Gap 2 marker: _stamp_resume_marker NOT NULL IntegrityError — marker now persists under the _recover_workspace_id-recovered real workspace_id (12-09)"
    - "UAT Gap 3: sample_wave deliverable single_file name=merged.txt (never produced) → serialized_sandbox (bundles the produced merged part_*.txt base); manifest-only, zero engine edits (12-10)"
    - "Review CR-01: reconnect_pipeline live-attach owner gate (AUTHZ-03) — non-owner presenting a live run_id is demoted to the owner-scoped durable-replay path (commit ccfc596b)"
    - "Review WR-01: resume_run cleanup unconditional on the hook via _fire_resume_cleanup on every exit path incl. the three early returns (commit 8d8a7a39)"
    - "Review WR-02: live queue registered synchronously at the restore_non_terminal_runs create_task site, closing the task-before-queue race window (commit 41c35a69)"
    - "Review WR-03: Gap 2c set_run_scope call site now fails loud on non-SQLAlchemyError (PermissionError = principal drift), mirroring the revision seam (commit 8eb3c880)"
  gaps_remaining: []
  regressions: []
human_verification: []
---

# Phase 12: Wave Scheduler + Durable Resume [6] Verification Report

**Phase Goal:** Add a deterministic topological wave scheduler that runs disjoint tasks in parallel waves via fan-out, with durable mid-wave resume; prototype stays sequential and a CP-SAT seam is left.
**Verified:** 2026-06-11T17:45:00Z
**Status:** passed (all must-haves code-verified offline + all 4 deferred live re-checks verified live in the milestone-end re-pass)
**Re-verification:** Yes — after UAT gap closure (plans 12-08/12-09/12-10) + review fixes (CR-01, WR-01, WR-02, WR-03); live re-pass 2026-06-11 (12-UAT.md tests 5-8)

## Gap Closure Summary

The milestone-end live UAT pass (12-UAT.md, then in diagnosed state; now complete) found 2 major + 1 minor gaps after the phase had passed verification. All three were closed by plans 12-08/12-09/12-10; a delta code review (12-REVIEW.md) then found 1 Critical + 3 Warnings, all fixed (12-REVIEW-FIX.md, status: all_fixed). Every fix is verified directly in the codebase below — not from SUMMARY claims.

| Gap / Finding | Fix Plan / Commit | Fix Location (verified) | Offline Evidence |
|---|---|---|---|
| Gap 1: WaveTreePanel dead UI | 12-08 / a6dc6bc1 | `DashboardLayout.tsx:16` import, `:94` `waves?: WaveGroup[]` prop, `:1188` `<WaveTreePanel waves={waves} />` on the execution surface; `page.tsx:1083` `waves={waveGroups}` | `DashboardLayout.waveMount.test.tsx` 3 passed |
| Gap 2 FE: pipeline_reconnected dropped | 12-08 / f5ee356f | `useWorkflow.ts:383-445` — live:false+terminal resolves isRunning + clears sessionStorage run id; live:false+non-terminal and live!==false keep running | `useWorkflow.reconnect.test.ts` 6 passed |
| Gap 2a: no engine→WS bridge | 12-09 / 0da2315d | `engine.py:450-452` 3 optional hooks (default None); `:4206-4214` queue registered pre-drive; `:4247-4253` event push; `:4261-4270` sentinel + cleanup; `websocket.py:68-84` bridge funcs; `main.py:126-129` single wiring site | `test_resume_ws_bridge.py` green (in 11 passed) |
| Gap 2c: null pipeline_reconnected.status | 12-09 / a09f7b35 | `engine.py:787-801` `set_run_scope(pipeline_run_id, owner_id, ectx.workspace_id)` after workspace resolution; `websocket.py:734` scoped `get_run` now resolves | `test_resume_marker_workspace.py` green |
| Marker NOT NULL IntegrityError | 12-09 / a09f7b35 | `engine.py:3191` `_stamp_resume_marker` uses `_recover_workspace_id(owner_id, run_id)` | `test_resume_marker_workspace.py` green |
| Gap 3: merged.txt never produced | 12-10 / 8ffae37c | `sample_wave/workflow.yaml` `deliverable: strategy: serialized_sandbox`; `merged.txt` 0 hits in manifest | `test_sample_wave_workflow.py` 3 passed incl. new bundle assertion (lines 362-372) |
| CR-01: live-attach no owner check | ccfc596b | `websocket.py:605-641` — owner-filtered WorkflowRun lookup + default-deny `ScopedStore.get_run`; miss demotes `_has_live_task = False` | Code-verified; no dedicated handler test (human item 4) |
| WR-01: cleanup leak on early returns | 8d8a7a39 | `engine.py:4077-4093` `_fire_resume_cleanup`; called at `:4129`, `:4149`, `:4154` (early returns) and `:4270` (finally, un-nested from live_queue) | `test_resume_ws_bridge.py` cleanup contract green |
| WR-02: task-before-queue race | 41c35a69 | `engine.py:3073-3081` queue registered immediately before `create_task` at `:3082`; FE comment corrected `useWorkflow.ts:432-444` | dormant-bridge parity + bridge tests green |
| WR-03: PermissionError swallowed | 8eb3c880 | `engine.py:792-796` — re-raises non-`SQLAlchemyError`; warning-degrade only for the DB condition | characterization 10 passed (no offline path trips it) |

All 9 plan/fix commits verified present in git: ccfc596b, 8d8a7a39, 41c35a69, 8eb3c880, a6dc6bc1, f5ee356f, 0da2315d, a09f7b35, 8ffae37c.

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — regression-checked)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `wave_scheduler` topo-sorts by `depends_on` + `conflict_keys` into waves, runs each wave via fan-out; multi-file workflow runs parallel waves; prototype stays sequential; CP-SAT seam left | VERIFIED | `wave_scheduler.py` present; `test_wave_scheduler.py` + `test_json_tasks.py` + `test_sample_wave_workflow.py` green (in the 50+11 passed); `grep sample_wave backend/agents/execution_engine/` = 0 (SC-001); characterization snapshots 10 passed (prototype sequential, byte/event-identical) |
| 2 | `wave_runs` persisted; server restart resumes mid-wave via `subagent_runs`/`wave_runs`; idempotent step retry reuses artifacts on content-hash match | VERIFIED | `0020_wave_runs.py` + `wave_run.py` ORM present; `test_wave_runs.py` (incl. cross-owner ∅) + `test_restart_resume.py` (seq continuity, whole-wave re-run, cross-step filter, stale-row flip) + `test_step_retry.py` green |
| 3 | Reconnect replays from durable `run_events` (`after=<seq>`, idempotent by `event_id`); `restore_non_terminal_runs` resumes at step granularity; `waiting_for_user` gates on user action | VERIFIED | `test_ws_reconnect_replay.py` green; NEW since prior verification: auto-resumed runs live-attach via the injected bridge so a connected client receives the resumed tail incl. `pipeline_complete` (`test_resume_ws_bridge.py`); FE resolves on `pipeline_reconnected` live:false+terminal (`useWorkflow.reconnect.test.ts`); live re-confirmation VERIFIED (live re-pass run G: live-attach + tail 19..29 incl. pipeline_complete) |

**Score:** 3/3 ROADMAP success criteria VERIFIED

### Gap-Closure Must-Have Truths (plans 12-08 / 12-09 / 12-10 — fully verified)

| # | Plan | Truth | Status | Evidence |
|---|------|-------|--------|----------|
| 1 | 12-08 | WaveTreePanel mounted on the dashboard execution surface, renders the assembled wave groups (no longer dead UI) | VERIFIED | `DashboardLayout.tsx:1188` mount inside the execution left column with its own ErrorBoundary; `page.tsx:1083` threads `waveGroups`; vitest 3 passed (non-empty waves → heading + worker leaf; empty → empty state) |
| 2 | 12-08 | pipeline_reconnected live:false + terminal status resolves the run out of running | VERIFIED | `useWorkflow.ts:403-430` — TERMINAL_STATUSES set, isRunning=false, agents finalized on completed, sessionStorage run id cleared; vitest branch tests pass |
| 3 | 12-08 | live:false + non-terminal keeps running (bounded recovery, no retry storm) | VERIFIED | `useWorkflow.ts:432-444` keep-running; WR-02 backend fix closes the race at the source; T-12-08-02 no-retry-loop decision held (comment corrected, no behavioral loop) |
| 4 | 12-08 | Non-wave workflow renders exactly as before (empty wave panel; AgentProgressPanel unchanged) | VERIFIED | `waves` prop optional, default `[]` (`DashboardLayout.tsx:94,218`); panel rendered unconditionally with its own "No waves running." empty state; vitest empty-state assertion passes; UAT Test 4 (user_stories regression) passed live pre-delta |
| 5 | 12-09 | Auto-resumed run's task + queue registered in the WS registry via an app-layer bridge; reconnect live-attaches and receives the remaining tail incl. pipeline_complete | VERIFIED | `engine.py:3073-3094` (queue+task at create_task site), `:4206-4214`/`:4247-4253` (queue pre-drive + per-event push), `websocket.py:68-84` (`_register_resume_queue`/`_register_resume_task` over the existing registries), `main.py:126-129` wiring; `test_resume_ws_bridge.py` asserts registration-before-drive, full tail on queue, None sentinel, cleanup, dormant parity |
| 6 | 12-09 | pipeline_reconnected.status non-null: workflow_runs.workspace_id stamped consistently with the run_events sink | VERIFIED | `engine.py:787-801` via existing `authz.set_run_scope` (authz.py:376 — no parallel stamper, INV-3/INV-12); `test_resume_marker_workspace.py` asserts scoped get_run resolves non-null status + cross-owner ∅ |
| 7 | 12-09 | _stamp_resume_marker recovers the real workspace_id; run_resuming marker persists without NOT NULL IntegrityError | VERIFIED | `engine.py:3191` `_recover_workspace_id` sources the marker store; no-durable-rows path never raises (best-effort, scalars captured pre-failure); test green |
| 8 | 12-09 | Kernel does not import app.api — bridge is an injected callback | VERIFIED | `grep -E "^(from app\.api|import app\.api)" engine.py` = 0; `lint-imports` 4 kept / 0 broken |
| 9 | 12-09 | Existing prototype/od_*/PPT live-attach reconnect byte/event-identical (bridge dormant when unset; legacy run_pipeline registration unchanged) | VERIFIED | Characterization 10 passed; dormant-bridge parity test in `test_resume_ws_bridge.py`; legacy registration path untouched (websocket.py run_pipeline block unmodified by the delta) |
| 10 | 12-10 | sample_wave run resolves its declared deliverable from produced files (no fallback warning) | VERIFIED | `workflow.yaml` `strategy: serialized_sandbox`; test assertion (5): `final_output` non-empty, not "(no files written)", contains `filename: part_a..d.txt` blocks — 3 passed |
| 11 | 12-10 | Fix is manifest-only — zero engine edits (SC-001) | VERIFIED | `grep -rn sample_wave backend/agents/execution_engine/` = 0; `merged.txt` 0 hits in manifest; registered-capabilities-only test asserts `serialized_sandbox` registered |
| 12 | 12-10 | SC-001 proof (>=2 waves, >=2 parallel wave-1 workers, merged part_a/b/c/d.txt, wave lifecycle events) still passes | VERIFIED | `test_sample_wave_workflow.py` 3 passed — existing assertions unchanged (line 348 asserts all 4 merged files) |

**Score:** 12/12 gap-closure must-have truths VERIFIED (+ 3/3 roadmap SC = 15/15)

### Prior-Plan Truths (12-01..12-07 — quick regression check)

All 31 previously-verified plan truths regression-checked via their owning suites: `test_wave_scheduler.py`, `test_json_tasks.py`, `test_wave_runs.py`, `test_step_retry.py`, `test_restart_resume.py`, `test_ws_reconnect_replay.py` (50 passed), characterization (10 passed), `wsReplayState.test.ts` (6 passed), `tsc --noEmit` 0 errors, `lint-imports` 4/0, migration ledger + registry lockstep (107 passed, 7 skipped). No regressions.

---

## Required Artifacts (gap-closure delta — three levels + Level 4)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `frontend/src/components/layout/DashboardLayout.tsx` | WaveTreePanel mounted on execution surface, fed via new `waves` prop | VERIFIED | Import line 16; optional prop lines 93-94, 218; mount line 1188 inside execution left column; WIRED (page.tsx feeds it), data FLOWING (waveGroups state ← WS handler ← wave_*/subagent_* events) |
| `frontend/src/app/dashboard/page.tsx` | waveGroups threaded into DashboardLayout | VERIFIED | State line 70; `waves={waveGroups}` line 1083; `pipeline_reconnected` in pipelineTypes line 324 (routes into handlePipelineMessage) |
| `frontend/src/hooks/useWorkflow.ts` | pipeline_reconnected handler | VERIFIED | Case at lines 383-445, all three branches substantive; WIRED via page.tsx routing |
| `backend/agents/execution_engine/engine.py` | 3 injected bridge hooks; queue registration + live push + sentinel/cleanup; set_run_scope stamping; marker workspace recovery; _fire_resume_cleanup | VERIFIED | All confirmed at the line ranges in the Gap Closure table; WIRED into restore_non_terminal_runs + resume_run + _execute_impl |
| `backend/app/api/websocket.py` | bridge functions + CR-01 owner gate | VERIFIED | `_register_resume_queue`/`_register_resume_task` lines 68-84 over existing registries; AUTHZ-03 gate lines 605-641 before both branches |
| `backend/app/main.py` | single wiring site before restore | VERIFIED | Hooks set lines 126-128, `restore_non_terminal_runs()` awaited line 129 |
| `backend/agents/authz.py` | set_run_scope seam (reused, not modified) | VERIFIED | `async def set_run_scope` at line 376 — plan predicted modification; reuse without edit satisfies the INV-3 "no parallel stamper" intent (per 12-09-SUMMARY decision) |
| `backend/agents/workflows/sample_wave/workflow.yaml` | `deliverable: strategy: serialized_sandbox`, no merged.txt | VERIFIED | Confirmed; header comment accurately describes the produced-files flow |
| `backend/tests/agents/test_resume_ws_bridge.py` | bridge behavioral coverage | VERIFIED | Substantive (registration-before-drive, tail-on-queue, sentinel, cleanup, dormant parity, no-app.api-import check); green |
| `backend/tests/agents/test_resume_marker_workspace.py` | stamping + marker coverage | VERIFIED | Substantive (scoped get_run non-null, cross-owner ∅, marker persists at recovered workspace, no-durable-rows no-raise); green |
| `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx` | real-mount render test | VERIFIED | Renders the real DashboardLayout (heavy children stubbed); 3 passed |
| `frontend/src/hooks/useWorkflow.reconnect.test.ts` | handler branch tests | VERIFIED | 6 passed (terminal-completed, terminal-failed, non-terminal, missing status, live:true, absent live) |

## Key Link Verification (gap-closure delta)

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `page.tsx` | `DashboardLayout.tsx` | `waves={waveGroups}` prop | WIRED | line 1083 |
| `DashboardLayout.tsx` | `WaveTreePanel.tsx` | mount on execution surface | WIRED | line 1188, unconditional, own ErrorBoundary |
| `page.tsx handleWebSocketMessage` | `useWorkflow.handlePipelineMessage` | `pipeline_reconnected` in pipelineTypes | WIRED | page.tsx:324 routes it; case exists at useWorkflow.ts:383 |
| `engine.py resume_run / restore_non_terminal_runs` | `websocket._PIPELINE_QUEUES/_PIPELINE_TASKS` | injected callbacks (no app.api import) | WIRED | hooks set in main.py:126-128; registration at engine.py:3073-3094 + 4206-4214; lint-imports 4/0 |
| `websocket.py reconnect_pipeline` | `ScopedStore.get_run` | owner+workspace-scoped status read | WIRED | line 734; resolves non-null after the 12-09 stamp; CR-01 gate also rides get_run (line 640) |
| `engine.py _stamp_resume_marker` | `_recover_workspace_id` | real workspace recovery before append_event | WIRED | line 3191 |
| `engine.py _execute_impl` | `authz.set_run_scope` | consistent workspace stamping (fail-loud non-DB) | WIRED | lines 787-801 |
| `workflow.yaml deliverable` | merged copy_disjoint base | `strategy: serialized_sandbox` (registered) | WIRED | manifest + registered-capability assertion in test |

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `WaveTreePanel` (via DashboardLayout) | `waves` prop | `page.tsx waveGroups` state ← WS `wave_*`/`subagent_*` events (assembler vitest-covered) | Yes — prop threaded end-to-end, no hardcoded empty at the call site (`waves={waveGroups}`) | FLOWING (live-verified) |
| `useWorkflow pipeline_reconnected` | `msg.live` / `msg.status` | backend `websocket.py:736-744` payload (status from scoped `get_run`, non-null post-12-09) | Yes | FLOWING |
| resume live queue | resumed events | `resume_run` drive loop pushes each persisted event (`engine.py:4247-4253`) + None sentinel | Yes — same dict shape as the run_pipeline queue contract | FLOWING (live-verified) |
| `workflow_runs.workspace_id` | stamped scope | `set_run_scope` after workspace resolution | Yes — real DB write via existing seam | FLOWING |
| sample_wave deliverable | `final_output` | serialized_sandbox bundle of the copy_disjoint-merged base | Yes — test asserts part_a..d.txt filename: blocks present, "(no files written)" absent | FLOWING |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Gap-closure backend suites | `pytest test_resume_ws_bridge.py test_resume_marker_workspace.py test_sample_wave_workflow.py -q` | 11 passed | PASS |
| Regression: waves/resume/replay/retry | `pytest test_restart_resume.py test_ws_reconnect_replay.py test_wave_scheduler.py test_json_tasks.py test_wave_runs.py test_step_retry.py -q` | 50 passed | PASS |
| Characterization parity (5 workflows) | `pytest test_characterization_*.py -q` | 10 passed | PASS |
| Import contracts | `/opt/homebrew/bin/lint-imports` | 4 kept, 0 broken | PASS |
| Migration ledger + registry lockstep | `pytest test_migration_ledger.py test_registry_capabilities.py -q` | 107 passed, 7 skipped | PASS |
| FE gap-closure + regression vitest | `npx vitest run DashboardLayout.waveMount.test.tsx useWorkflow.reconnect.test.ts wsReplayState.test.ts` | 15 passed (3 files) | PASS |
| FE TypeScript | `npx tsc --noEmit` | 0 errors (exit 0) | PASS |
| SC-001 invariant | `grep -rn sample_wave backend/agents/execution_engine/` | 0 hits | PASS |
| Commits exist | `git log` for all 9 claimed hashes | all present | PASS |

## Probe Execution

No `scripts/*/tests/probe-*.sh` probes exist in this repo and no PLAN/SUMMARY for this phase declares probe-based verification — SKIPPED (no probes declared or discovered).

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| WAVE-01 | 12-01 | wave_scheduler topo-sort by depends_on + conflict_keys, fan-out per wave, CP-SAT seam | SATISFIED | wave_scheduler suites green; sample_wave SC-001 proof; regression-checked this pass |
| WAVE-02 | 12-01, 12-10 | wave_runs persistence; multi-file workflow in parallel waves; prototype sequential | SATISFIED | wave_runs suites green; sample_wave deliverable now resolves from produced files (Gap 3 closed); characterization unchanged |
| WAVE-03 | 12-01/03/06, 12-08, 12-09 | Resume mid-wave via subagent_runs/wave_runs after restart | SATISFIED | Mid-wave resume suites green; wave tree live render VERIFIED in the live re-pass (12-UAT.md test 5) |
| RESUME-02 | 12-02 | Idempotent per-step retry keyed (run_id, step_id, input_hash); artifact reuse on hash match | SATISFIED | test_step_retry.py green (regression) |
| RESUME-03 | 12-03/04/05/07, 12-08, 12-09 | Reconnect = durable replay via after=<seq>, idempotent by event_id | SATISFIED | Replay suites green; auto-resumed-run delivery VERIFIED live (12-UAT.md test 6) |
| RESUME-04 | 12-03/06, 12-08, 12-09 | restore_non_terminal_runs at step granularity; waiting_for_user gates | SATISFIED | Three-way classifier suites green; live restart resume + page resolution VERIFIED live (12-UAT.md test 6) |

All 6 phase requirement IDs are claimed by plans, marked `[x]` in REQUIREMENTS.md (lines 133-142), and mapped to Phase 12 in the traceability table (lines 250-252). No orphaned requirements.

## Anti-Patterns Found

No TBD/FIXME/XXX debt markers in any of the 12 gap-delta files. No stub patterns (empty returns, hardcoded-empty props, console.log-only handlers) introduced. Carried quality debt (tracked, non-blocking — out of `fix_scope: critical_warning`):

| File | Finding | Severity | Impact |
|------|---------|----------|--------|
| `useWorkflow.ts:392-393` / `websocket.py:750-754` | IN-01 (review, unfixed): comment/tests document `live: true` but the live-attach payload omits the `live` key; behavior correct (`live !== false` treats both identically) | INFO | Fictional documented contract; future-reader risk |
| `engine.py` (~3156 area) | IN-02 (review, unfixed): marker owner derived from `wr.owner_id or wr.user_id` vs `user_id` elsewhere — latent principal divergence | INFO | Marker silently lost only if owner_id ever diverges from user_id |
| `app/main.py:117-131` | IN-03 (review, unfixed): bridge wiring shares the restore scan's try block — a wiring failure would also skip restoration | INFO | Low likelihood; failure coupling only |
| `websocket.py:605-641` | CR-01 gate has no dedicated handler-driving cross-owner regression test (12-REVIEW-FIX note) | WARNING | Authorization logic verified by reading, not by an automated handler test — listed as human item 4 / follow-up test |
| `engine.py` WR-09..WR-14 | Prior-review warnings carried (second-restart re-entry, offset-0 resume, resume-failure loop, dropped task ref, pipeline_start mid-replay reset, retry-on-wave-step) | WARNING | Tracked quality debt from the prior verification; none breaks a ROADMAP SC for the primary scenario |

## Human Verification — RESOLVED (milestone-end live re-pass, 2026-06-11)

All 4 deferred items were re-verified live against the real stack (uvicorn :8000 +
Next.js :3000 + real /ws/chat; scripted-model harness, AWS SSO expired — none of the
items target the model provider). Full detail: 12-UAT.md tests 5-8; evidence:
12-UAT-EVIDENCE/results-recheck.json + screenshots 60/62/63/66 + crossowner-frames.jsonl.

### 1. Live wave-tree panel render — VERIFIED LIVE

Run F/H: WaveTreePanel rendered live on the dashboard execution column — mid-wave-1
"Wave 0 / t1, t2 / RUNNING" with 2 distinct sample-wave-worker leaves; badge flipped
COMPLETED on wave_completed; final state shows both wave groups with 4 worker leaves
(66-runH-panel-in-view.png). Cosmetic note: at 950px viewport height the panel sits
~122px below the fold of the scrollable execution column; normal scroll reaches it.

### 2. Live auto-resume reconnect — VERIFIED LIVE

Run G: SIGKILL mid-wave-2 (seq 17) + restart; page reconnected with after_seq=17,
LIVE-ATTACHED via the 12-09 bridge ("Reconnected — resuming pipeline stream"), received
seq 19..29 incl. pipeline_complete, and resolved out of "running" (Stop gone, "Done in
3.0s", 63-runG-resolved.png). INFO: seq 18 = run_resuming audit marker raced the attach
and was not on this connection's wire (store-appended, not bridge-pushed; FE has no
handler; durable log contiguous 1..29 — fresh replay delivers it).

### 3. Live deliverable resolution — VERIFIED LIVE

Zero "falling back to streamed" hits across both backend logs; run F
workflow_runs.output is the serialized_sandbox filename:-block bundle with all four
part_a..d.txt files; runs completed with non-NULL workspace_id (Gap 2c stamp live)
and zero marker IntegrityError warnings (marker fix live).

### 4. Cross-owner live-attach demotion (CR-01) — VERIFIED LIVE

While run F was live and registered, uat12b sent reconnect_pipeline with run F's id
over a raw authenticated WS: exactly one reply — pipeline_reconnected {status: null,
replayed_through_seq: 0, live: false} — ∅ replayed rows and zero run-F stream frames
over the following 9s (crossowner-frames.jsonl). The real handler drove the
websocket.py:605-641 gate. (A dedicated handler-driving regression test remains a
nice-to-have follow-up; the live check covers the gap flagged by 12-REVIEW-FIX.)

## Gaps Summary

No blocking gaps and no open items. All 3 UAT gaps (dead wave panel, auto-resume
reconnect delivery/status/marker, sample deliverable) are closed, verified in the
codebase with passing offline tests, AND re-verified live end-to-end; all 4 in-scope
review findings (CR-01, WR-01, WR-02, WR-03) are fixed, code-verified, and CR-01 is
live-verified through the real handler. No regressions across the 193 targeted backend
tests, 10 characterization snapshots, 15 FE vitest tests, tsc, and the 4 import
contracts.

---

_Verified: 2026-06-11T17:45:00Z_
_Verifier: Claude (gsd-verifier) + milestone-end live re-pass (self-driven UAT)_
_Re-verification: Yes — after UAT gap closure (12-08/12-09/12-10) + review fixes; live re-pass 2026-06-11_
