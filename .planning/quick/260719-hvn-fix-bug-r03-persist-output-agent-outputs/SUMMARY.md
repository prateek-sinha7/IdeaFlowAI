# Quick 260719-hvn — Fix BUG-R03: the resume tier persists the terminal OUTPUT columns

**Branch:** `feat/ui-2` · **Status:** offline-verified (live crash-then-resume re-proof owned by orchestrator)

## The bug (verified facts)

A restart-auto-resumed run (branch b) and a Phase-50 user-resumed run complete with
`workflow_runs.status = completed` but EMPTY `output` / `agent_outputs` / `token_usage` /
`duration`. Status is written by the engine STATE MACHINE (step-5 transition →
`state_machine.py:117`) on BOTH the launch and resume paths, but the output-bearing columns
were written ONLY by the app-layer launch driver `_drive_launch_to_queue`'s post-stream
terminal block, which neither resume entry point replicated. Downstream: `GET /chain-context`
BREAKS, `/summary` + analytics + export-pptx DEGRADE. Deliverable render + revision are SAFE
(they read `artifact_refs`, not `output`). Live: run `15c4372f` auto-resumed with
`output`/`agent_outputs` empty.

## The fix (INV-12 — ONE mapping, no third driver)

**1. Extracted the event→WorkflowRun output-column mapping into a SHARED helper**
`_apply_terminal_output_columns(wr, events, *, model_id, duration_seconds)` in
`app/api/run_commands.py`. Replays a normalized `(event_type, data)` list — the SAME
`agent_*`/`pipeline_complete` accumulation the launch loop ran inline — into `output` /
`agent_outputs` / `token_usage` / `deliverable_mimetype` / `deliverable_filename` /
`completed_at` / `duration`, byte-for-byte identical to the old launch terminal block. Writes
NO `status`/`error` (caller-owned); does NOT commit (caller owns the session).

**Refactor choice (flagged): I refactored `_drive_launch_to_queue` to CALL the helper — the
PREFERRED "one mapping" option, not the inline+shared-fn fallback.** The launch loop now
(a) still pushes every event to the live `event_queue`, (b) collects each event into
`raw_events: list[tuple[str,dict]]`, and (c) keeps ONLY the status seen-flags inline. The
terminal block keeps the inline STATUS decision unchanged and calls the helper for the output
columns. Byte-identical is guaranteed because the helper's accumulation is the moved-out
branch bodies operating on the SAME live `update["data"]` dicts through the SAME code, and the
persistence math (json.dumps / token sums / `estimate_cost_usd` / duration) is verbatim;
duration is passed in (`round(time.monotonic() - monotonic_start, 1)`), preserving the old
`if not wr.duration` guard. Proven by launch suite 39/39 + goldens 10/10 (`SNAPSHOT_UPDATE`
unset).

**2. Wired into BOTH resume entry points:**
- **(a) USER-resume (Phase 50):** extended `_reconcile_terminal_status` — which already reads
  the durable `run_events` tail for status — to feed that SAME tail to
  `_persist_resume_output_columns(run_id, events)` (opens a session, applies the helper,
  commits). App-layer; runs on every user-resume drive regardless of engine-hook arming.
- **(b) RESTART auto-resume (Phase 46 branch b):** added a NEW injected engine hook
  `self._resume_output_persist_sink: ResumeOutputPersist | None` (mirroring the injected
  `_resume_milestone_sink` at `engine.py:839` + the live-ectx trio — the kernel cannot import
  `app.*`, so it is a `run_id -> awaitable` callback), FIRED in `_drive_resumed_stream`'s
  `finally`, DORMANT when `None` (offline / goldens → byte/event-identical resume, INV-3).
  ARMED in `app/main.py` on the SAME restore engine instance (next to `_resume_milestone_sink`
  / `register_live_ectx`) to the app callback `persist_resume_output_columns(run_id)`, which
  reads the owner-scoped durable tail via the SAME `_recover_workspace_id` +
  `ScopedStore.read_events` idiom as `_reconcile_terminal_status`, then applies the shared
  mapping.

**3. Left the state-machine `status` write untouched** (already correct on both paths). Only
the missing output-column persistence was added. No migration, no new WS event, no FE change;
`owner_id`/`workspace_id` already on the row (Q3).

Note: `_drive_user_resume` → `resume_run` → `_drive_resumed_stream`, so in the LIVE app (hook
armed) the engine hook AND `_reconcile_terminal_status` both persist for a user-resume —
idempotent (same durable tail → identical values), intentional belt-and-suspenders so
user-resume populates even when the hook is unarmed (unit tests).

## Tests (RED->GREEN, closing the coverage hole) — `tests/agents/test_restart_resume.py`

1. `test_apply_terminal_output_columns_populates_all_columns` — feeds the shared mapping a
   **user_stories-shaped** durable tail (real agent ids `domain-analyst`/`backlog-compiler` +
   `agent_complete` with tokens + `pipeline_complete` with `final_output`); asserts ALL of
   `output` / `agent_outputs` (2 agents) / `token_usage` (in 300, out 130, total 430, cache
   10) / `duration` (3.5) / `deliverable_*` / `model_id`. GREEN.
2. `test_user_resume_persists_output_columns` — END-TO-END: crash mid-wave then USER-resume to
   completion via the real `_drive_user_resume` -> `_reconcile_terminal_status`; asserts
   `output` POPULATED (durable `final_output` carrying the resumed deliverable). RED captured
   with the reconcile persist neutralized (`AssertionError: ... must persist the output column
   (empty pre-fix)`); GREEN after.
3. `test_restart_resume_fires_output_persist_hook` — branch-(b) RESTART auto-resume drives
   `resume_run` -> `_drive_resumed_stream` with a spy armed on `_resume_output_persist_sink`;
   asserts it FIRES with run_id from the `finally`. RED captured before the engine-fire line
   (`[] == ['r03b-...']`); GREEN after.

`sample_wave` is a wave-fanout fixture (emits `subagent_*`/`wave_completed`, no per-agent
`agent_complete`), so its populated resume column is `output`<-`final_output`; the per-agent
columns are asserted on a real `agent_complete` tail in test 1.

## Verification (offline)

- Goldens 10/10 (`SNAPSHOT_UPDATE` UNSET) — launch refactor behavior-preserving (INV-3).
- Launch byte-identical: `test_rest_run_launch.py` + `test_rest_revisions.py` 39/39.
- Resume + new: `test_restart_resume.py` + `test_rest_resume.py` 56/56 (53 existing + 3 new).
- `lint-imports`: 4 kept, 0 broken (no engine->app import; injected callback).

## Files

- `backend/app/api/run_commands.py` — shared `_apply_terminal_output_columns`; resume helpers
  `_resume_events_duration` / `_persist_resume_output_columns` / `persist_resume_output_columns`;
  launch driver refactored to call the mapping; `_reconcile_terminal_status` extended.
- `backend/agents/execution_engine/engine.py` — `ResumeOutputPersist` alias;
  `_resume_output_persist_sink` attribute; fire in `_drive_resumed_stream`'s `finally`.
- `backend/app/main.py` — arm `_resume_output_persist_sink = persist_resume_output_columns`.
- `backend/tests/agents/test_restart_resume.py` — three BUG-R03 tests.

## Deviations from plan

None — implemented exactly as the BUG-R03 "Fix (design only)" section specifies (shared helper
+ two wiring points + injected engine hook + app/main.py arming), with the PREFERRED
"refactor `_drive_launch_to_queue` to call the helper" option.
