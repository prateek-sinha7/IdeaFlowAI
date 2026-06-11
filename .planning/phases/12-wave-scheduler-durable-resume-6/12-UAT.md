---
status: complete
phase: 12-wave-scheduler-durable-resume-6
source: [12-VERIFICATION.md]
started: 2026-06-11T14:05:00Z
updated: 2026-06-11T17:45:00Z
gap_closure: >
  All 3 gaps resolved offline 2026-06-11 by plans 12-08/12-09/12-10 plus code-review
  fixes (12-REVIEW.md / 12-REVIEW-FIX.md, commits ccfc596b/8d8a7a39/41c35a69/8eb3c880).
  Live re-checks (4 items) queued in 12-VERIFICATION.md human_verification — ALL 4
  RE-VERIFIED LIVE 2026-06-11 (tests 5-8 below); fixes confirmed working end-to-end.
deferral: fulfilled 2026-06-11 — milestone-end live pass + post-gap-closure live re-pass both executed
environment: >
  Live pass executed self-driven via playwright (headless chromium) against the real
  stack: real uvicorn backend on :8000 (SQLite dev.db migrated to alembic 0020), real
  Next.js dev frontend on :3000, real /ws/chat WebSocket, stock engine / wave_scheduler /
  run_events+wave_runs persistence / FE. CAVEAT: AWS SSO expired (all profiles), so the
  LLM was the proven scripted-model harness (tests/agents/_scripted_model.py) injected
  via a /tmp runtime launcher — zero repo edits. sample_wave admitted at runtime
  (entitlements + loader sets widened in-process; fixture AGENT.md specs cache-seeded)
  since the sample workflow is not product-exposed. None of the three deferred tests
  target the model provider; engine/WS/persistence/FE surfaces all ran stock.
  Evidence: 12-UAT-EVIDENCE/ (frame analyses, run_events table, screenshots) +
  /tmp/flowin-uat-evidence/ (full frame JSONL logs).
---

## Current Test

[testing complete]

## Tests

### 1. Live wave-tree panel render with N distinct worker leaves
expected: WaveTreePanel renders wave groups (index + task ids + status badge flipping running→completed) and N DISTINCT worker leaves in wave 1 for sample_wave (CR-06 fix live)
result: issue
reported: "Backend half VERIFIED live: wave_started carries task_ids [t1,t2]/[t3,t4] + flat {wave_index, step}; subagent_spawned stamped {wave_index, step, worker} with workers 0 and 1 DISTINCT in both waves (12-06 emit contract live); wave_completed per wave; seq 1..23 contiguous, 0 dup event_ids; wave_runs rows persisted terminal. FE half FAILED: WaveTreePanel never renders — it is mounted only inside WorkflowComposer (WorkflowComposer.tsx:299), and WorkflowComposer is mounted by NO route/component in the app; dashboard/page.tsx assembles waveGroups correctly (vitest-verified routing/keying/reset all live in code) but passes the state to no component. DOM probe during+after a live wave run: 'Wave / Subagent Tree' absent (screenshot 10-runA-complete.png — run visibly executed, no wave panel)."
severity: major

### 2. Live after_seq reconnect replay — no duplicate events, no lost tail
expected: Mid-run page reload sends after_seq; tree resumes without duplicated wave/worker entries; agent_chunk text not duplicated (CR-05 live); missed tail not lost (CR-01/CR-02 live)
result: issue
reported: "Replay MECHANICS verified live. Reload half (run C): post-reload reconnect sent after_seq=0; durable tail fully replayed (seq 1..10 union across reload, no gaps); FE rebuilt state fresh, no duplicated application (per-connection wire dups 0; CR-05 dedup covers replay+drainer overlap). Client disconnect cancels the run by design (pre-existing cancel-on-disconnect policy, unchanged). Durable half (run E/E2, backend SIGKILL mid-wave-2 + restart): restore_non_terminal_runs auto-resumed; CR-01 LIVE — resumed events continued seq 18..28 past pre-kill max 17, pipeline_complete persisted at seq 28; CR-03 LIVE — in-flight wave 1 superseded + whole-wave re-run (wave_runs rows); open page reconnected with after_seq=17 and received the resumed tail through seq 22 on the wire (CR-02 replay read scoped correctly). GAPS: (a) the auto-resumed run is never registered in websocket._PIPELINE_TASKS/_PIPELINE_QUEUES, so the reconnect takes the live:false branch — replay stops at read time and the client NEVER receives the remaining tail incl. pipeline_complete; (b) the FE has no handler for pipeline_reconnected (useWorkflow ignores it), so live:false + status are dropped and the page stays 'running' forever (screenshot 51-runE2-stuck.png: '0/2 agents' + Stop, while backend status=completed); (c) pipeline_reconnected.status is null — ScopedStore.get_run scopes by workspace_id recovered from run_events (non-null) while workflow_runs.workspace_id is NULL, so the run row never matches. User recovery exists: manual reload AFTER completion replays the full durable log seq 1..28 incl. both wave-1 emissions and pipeline_complete (52-runE2-after-reload.png) — the durable log itself is intact and correct."
severity: major

### 3. Second run resets wave panel and reconnect cursor
expected: After run 1 completes, starting run 2 clears the previous wave panel and sends after_seq=0 on first reconnect (WR-03 per-run reset live)
result: pass
notes: "Cursor reset VERIFIED live (run B): run A ended at seq 23; run B's first reconnect (forced drop 80ms after pipeline_start) sent after_seq=4 — run B's own cursor, not run A's 23. WR-03 resetReplayState fires on pipeline_start (also observed live in run E2: the resume's re-emitted pipeline_start reset the FE state mid-session). 'Clears the previous wave panel' is unobservable in the DOM — same root cause as Test 1 (panel never renders); the state-reset code path is the one vitest covers and the cursor evidence exercises."

### 4. No-waves workflow panels unchanged (regression)
expected: A non-wave workflow (user_stories) runs with zero wave_*/subagent_* frames; AgentProgressPanel / preview behave as before
result: pass
notes: "Run D: user_stories completed clean — 0 wave/subagent frames, seq 1..27 contiguous, 0 dup event_ids, no errors, agent cards + preview normal (40-runD-complete.png)."

## Live Re-checks (milestone-end, post-gap-closure — 2026-06-11)

The 4 human_verification items queued in 12-VERIFICATION.md, re-run live after the
12-08/12-09/12-10 fixes landed. Same harness as the first pass (scripted-model
launcher — AWS SSO still expired; engine/WS/persistence/FE all stock), driven by
/tmp/flowin-uat-recheck.py. Evidence: 12-UAT-EVIDENCE/results-recheck.json + screenshots.

### 5. Live wave-tree panel render on the dashboard execution surface (human_verification #1)
expected: During a live sample_wave run, WaveTreePanel renders wave groups + N distinct worker leaves on the dashboard (12-08 mount live)
result: pass
notes: "Run F DOM probes: mid-wave-1 the panel rendered 'Wave 0 / t1, t2 / RUNNING' with 2 distinct sample-wave-worker leaves both RUNNING; after wave 1 the badge flipped COMPLETED; at completion both wave groups (Wave 0 t1,t2 + Wave 1 t3,t4) rendered COMPLETED with 4 worker leaves (62-runF-complete.png DOM text). Visually confirmed in-viewport (66-runH-panel-in-view.png). COSMETIC observation: at 950px viewport height the panel sits ~122px below the fold of the scrollable execution column (AgentProgressPanel's flexible space pushes it down); a normal column scroll reaches it — real mounted UI, not dead UI."

### 6. Live auto-resume reconnect delivers the full resumed tail and resolves the page (human_verification #2)
expected: Backend SIGKILL mid-wave + restart with the page open: page reconnects, live-attaches (12-09 bridge), receives the resumed tail incl. pipeline_complete, resolves out of 'running' (12-08 handler)
result: pass
notes: "Run G: killed mid-wave-2 at seq 17; FE reconnected with after_seq=17; got the LIVE-ATTACH ack ('Reconnected — resuming pipeline stream' — the 12-09 bridge registered the auto-resumed run, no live:false demotion); resumed tail seq 19..29 delivered on the wire incl. re-emitted wave 1 + pipeline_complete (seq 29); wire dups 5 (replay/drainer overlap, FE dedups by event_id per CR-05); DOM resolved — Stop button gone, 'Done in 3.0s', completion toast (63-runG-resolved.png). The 51-runE2-stuck behavior is gone. INFO: seq 18 (run_resuming audit marker) was not on this connection's wire — the reconnect raced the marker stamp and the marker is store-appended, not bridge-pushed; FE has no handler for it and the durable log is contiguous 1..29 (fresh replay delivers it). workflow_runs.workspace_id non-NULL on both runs (Gap 2c stamp live); zero marker IntegrityError warnings in either backend log (marker fix live)."

### 7. Live sample_wave run resolves its deliverable with no fallback warning (human_verification #3)
expected: No 'merged.txt not written by agent — falling back to streamed output' log line; deliverable is the serialized_sandbox bundle containing part_a..d.txt (12-10)
result: pass
notes: "0 hits for 'falling back to streamed' across both backend logs (pre- and post-restart). Run F workflow_runs.output is exactly the filename:-block bundle with all 4 parts (filename: part_a.txt 'a' … part_d.txt 'd'); run status completed."

### 8. Cross-owner live-attach demotion — CR-01 (human_verification #4)
expected: A second authenticated user presenting a live run_id gets ∅ replay + live:false, never the live stream
result: pass
notes: "While run F was live mid-wave-1 (registered in _PIPELINE_TASKS), uat12b@example.com opened a raw WS (bearer subprotocol) and sent reconnect_pipeline {pipeline_run_id: <run F>, after_seq: 0}. Received exactly ONE frame: pipeline_reconnected {status: null, replayed_through_seq: 0, live: false, 'Replayed durable run_events tail (no live task)'} — ∅ replayed rows, null status (default-deny scoping), and zero run-F stream frames over the following 9s while the run was actively emitting waves (crossowner-frames.jsonl). The real reconnect_pipeline handler drove the websocket.py:605-641 gate."

## How it was run

1. Backend via /tmp/flowin-uat-launcher.py (runtime patches only; uvicorn :8000, dev.db @ alembic 0020)
2. Frontend `npm run dev` (:3000); dedicated `uat12@example.com` user (enterprise), removed after
3. /tmp/flowin-uat-driver.py — playwright scenarios A (clean wave run), B (2nd-run drop → cursor reset), C (mid-run reload), E/E2 (mid-run backend SIGKILL + restart), D (user_stories regression); WS frames intercepted + logged both directions
4. Live re-pass (tests 5-8): /tmp/flowin-uat-recheck.py — runs F (clean, DOM probes), G (SIGKILL mid-wave-2 + restart), H (panel geometry), cross-owner raw-WS probe as uat12b@example.com; users uat12/uat12b re-seeded for the pass, removed after

## Summary

total: 8
passed: 6
issues: 2 (both resolved by 12-08/12-09/12-10 + review fixes; re-verified live in tests 5-8)
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "WaveTreePanel renders wave groups and N distinct worker leaves during a live wave run"
  status: resolved
  resolution: "12-08 (a6dc6bc1): WaveTreePanel mounted in DashboardLayout beside AgentProgressPanel (own ErrorBoundary), waveGroups threaded from dashboard/page.tsx via new optional waves prop; 3 mount vitests green. ValidatorIssuePanel (phase-8 scope) recorded as known-unwired — explicitly out of this gap's scope. Live render re-check queued (12-VERIFICATION.md human_verification #1)."
  reason: "User-observable: wave run executes but no wave tree UI exists anywhere in the app"
  severity: major
  test: 1
  root_cause: "WaveTreePanel is mounted only in WorkflowComposer (frontend/src/components/workflow/WorkflowComposer.tsx:299), and WorkflowComposer is mounted by no route or parent component (only the unrouted composer imports it; /workflow uses WorkflowView, dashboard uses DashboardLayout+AgentProgressPanel). dashboard/page.tsx assembles waveGroups (state, routing, CR-06 worker keying, WR-03 reset — all correct) but never passes it to any component. 12-04 followed the ValidatorIssuePanel 'sibling panel' precedent — ValidatorIssuePanel (phase 8, API-03) is dead UI for the same reason (pre-existing latent gap, surfaced by this pass)."
  artifacts:
    - path: "frontend/src/components/workflow/WorkflowComposer.tsx"
      issue: "only mount site of WaveTreePanel (line 299) + ValidatorIssuePanel (line 294); component unreachable — no route/parent renders WorkflowComposer"
    - path: "frontend/src/app/dashboard/page.tsx"
      issue: "waveGroups state (line 70) assembled at line 245 but passed to no component"
    - path: "frontend/src/components/layout/DashboardLayout.tsx"
      issue: "the live execution surface (mounts AgentProgressPanel) — has no waves prop and no WaveTreePanel mount"
  missing:
    - "Mount WaveTreePanel on the live execution surface (DashboardLayout, beside AgentProgressPanel) and thread waveGroups from dashboard/page.tsx down to it"
    - "Decide ValidatorIssuePanel's fate the same way (same dead-mount gap, phase-8 scope) — mount it live or record as known-unwired"
  debug_session: "diagnosed live during this UAT pass (root cause file:line verified)"

- truth: "A client connected during an auto-resumed run receives the full resumed tail including pipeline_complete"
  status: resolved
  resolution: "12-09 (0da2315d): engine→WS live-task bridge — 3 optional injected hooks wired once in app/main.py; resume_run registers the live queue before the drive loop, pushes every resumed event, terminates with None sentinel + cleanup (gap a). (a09f7b35): workflow_runs.workspace_id stamped via authz.set_run_scope so scoped get_run resolves and pipeline_reconnected.status is non-null (gap c); _stamp_resume_marker recovers the real workspace_id (NOT NULL fixed). 12-08 (f5ee356f): FE pipeline_reconnected handler — live:false + terminal resolves isRunning, non-terminal keeps running without a retry loop (gap b). Hardened by review fixes: ccfc596b (owner-gated live attach, AUTHZ-03), 8d8a7a39 (cleanup on every resume_run exit path), 41c35a69 (queue registered synchronously at create_task site — closes the task-before-queue race), 8eb3c880 (fail-loud on principal drift). 8 backend + 6 FE tests green. Live restart re-check queued (human_verification #2)."
  reason: "User-observable: after a backend restart mid-run, the open page reconnects, gets a partial tail, then hangs 'running' forever even though the run completed"
  severity: major
  test: 2
  root_cause: "Three-part gap: (1) restore_non_terminal_runs/resume_run never registers the resumed task+queue in websocket._PIPELINE_TASKS/_PIPELINE_QUEUES (engine has no registration hook), so reconnect_pipeline takes the live:false branch — the replay read returns rows persisted so far and nothing afterwards is ever delivered; (2) the FE has no pipeline_reconnected handler (useWorkflow.handleMessage lacks the case; page.tsx routes it into the pipeline handler list where it is dropped), so live:false + status are ignored and isRunning never resolves; (3) pipeline_reconnected.status is null because ScopedStore.get_run is scoped to the workspace_id recovered from run_events (non-null) while workflow_runs.workspace_id is NULL on rows created by the WS run path — the run row never matches the scoped read (workspace stamping inconsistency between the run-row INSERT and the engine event sink)."
  artifacts:
    - path: "backend/app/api/websocket.py"
      issue: "reconnect_pipeline live:false branch (≈lines 560-680): replay-then-status; _PIPELINE_TASKS never holds auto-resumed runs; status report reads a row the workspace scoping can never match"
    - path: "backend/agents/execution_engine/engine.py"
      issue: "restore_non_terminal_runs/resume_run: no live-queue/task registration visible to the WS layer; _stamp_resume_marker inserts run_events with workspace_id=None → NOT NULL IntegrityError, run_resuming marker lost (warning logged every in-process auto-resume)"
    - path: "frontend/src/hooks/useWorkflow.ts"
      issue: "no pipeline_reconnected case — live:false/status dropped; no re-poll or completion resolution after a no-live-task reconnect"
  missing:
    - "Register auto-resumed runs in the WS live-task/queue registry (or an equivalent engine→WS bridge) so reconnects can live-attach"
    - "FE: handle pipeline_reconnected — on live:false with terminal status resolve the run state; on non-terminal schedule re-poll/re-replay until terminal"
    - "Make workflow_runs.workspace_id stamping consistent with the run_events sink (or scope get_run by owner only) so the status report resolves"
    - "Fix _stamp_resume_marker to recover/stamp the run's real workspace_id (NOT NULL constraint)"
  debug_session: "diagnosed live during this UAT pass (run E/E2 evidence: 12-UAT-EVIDENCE/runE-durable-resume.txt, results-runE2.json, screenshots 51/52)"

- truth: "sample_wave deliverable resolves merged.txt"
  status: resolved
  resolution: "12-10 (8ffae37c): manifest deliverable switched from single_file/merged.txt (never produced) to the registered serialized_sandbox strategy, bundling the copy_disjoint-merged part_*.txt base; zero engine edits (SC-001 grep clean); test asserts final_output is the resolved bundle, not the streamed fallback. Live no-fallback-warning re-check queued (human_verification #3)."
  reason: "single_file: merged.txt not written by agent — falling back to streamed output (every run, incl. clean run A)"
  severity: minor
  test: 1
  root_cause: "Sample-manifest quirk, not an engine bug: sample_wave declares deliverable single_file name=merged.txt but no agent writes that file — workers write part_*.txt which copy_disjoint merges into the base; the single_file resolver then can't find merged.txt and falls back gracefully to streamed output. The offline e2e asserts the merged base files, not the named deliverable."
  artifacts:
    - path: "backend/agents/workflows/sample_wave/workflow.yaml"
      issue: "deliverable.name merged.txt never produced by any step"
  missing:
    - "Either have the merge/deliverable step materialize merged.txt from the merged base, or change the sample manifest's deliverable to match what the workflow produces"
  debug_session: "diagnosed live during this UAT pass"
