# Phase 50: User Resume-From-Failed — Reopen & Fix [R5] - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Source:** POR Ingest Express Path (`.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` §5.6/§6-R5/§7/§8.1 — authorized by the LOCK-E/ND-4 SUPERSEDE decision record)

<domain>
## Phase Boundary

A terminal-FAILED run becomes user-resumable: `POST /api/runs/{id}/resume` (RESUME-18). Today `restore_non_terminal_runs` never touches terminal rows — a failed run's only path is a full relaunch. This phase adds the REST entry + the terminal→live transition ON TOP of the complete shared resume tier shipped in Phases 45–49 (completeness classification, per-task cursor + task keys, re-materialization incl. boundary modes, reconciliation, live-layer callbacks, gate re-entry). **The endpoint is the ONLY new surface — everything else is reuse.**

OUT of scope (hard fences): any FE affordance (the Resume button/UI is a follow-on — this phase is API + mechanics; document in deferred); resuming non-failed terminal states (`completed`/`cancelled` runs are NOT resumable this phase — reject; revision flows already cover "change a completed run"); any change to the auto-resume path's behavior beyond reuse; new drivers (resume_run IS the driver — never a third hand-copied launch-driver ladder); migrations; new WS event types; live Bedrock in executors.

</domain>

<decisions>
## Implementation Decisions

### The endpoint (LOCKED — POR §5.6)
- `POST /api/runs/{id}/resume` in `run_commands.py` (the REST command surface, beside gate/answers/cancel/revisions).
- **Ownership:** the two-layer owner check idiom (ORM `WorkflowRun.user_id` filter → ScopedStore default-deny); cross-owner AND missing → **404, never 403**.
- **Eligibility:** ONLY `status == "failed"` rows. Anything else → a clear 4xx (`409 run_not_resumable` for live/other-terminal states — exact code/shape mirrors the existing command-endpoint error vocabulary).
- **Overlap guard + idempotency (the M4 lesson):** reject with `409 pipeline_already_running` if the run is already live (registered task/queue or non-terminal status); a replayed POST during resume hits the same guard; a POST after successful completion hits the eligibility check. No unguarded re-mint path may exist.
- **Transition:** `failed → running` (existing status vocabulary — no new status; INV-12) + the EXISTING `run_resuming` marker event through the engine's own counter (`_stamp_resume_marker` discipline; 0024). The FE's `AUTO_STREAM_STATUSES` (BUG-013) then auto-attaches on its next refresh; a fresh SSE attach on the now-live run goes live (BUG-015 semantics — the queue MUST be registered before the status flips/FE can attach).

### Recovery + drive (LOCKED — pure reuse)
- Queue registered via the `run_engine.py` bridge (`_register_resume_queue` BEFORE any task/emit — the 12-09/46-05 ordering), then `create_task` driving **`resume_run`** with the SAME live-layer callbacks the restore scan threads (46-05's hooks: `register_live_ectx`/unregister-in-finally/`milestone_sink`) — the engine instance/hook wiring must match how `app/main.py` arms the restore engine (research pins the exact instance/hook plumbing; if the endpoint's engine instance differs, thread the callbacks explicitly at the call site like `run_commands.py:1373-1381` does for launch).
- Everything else is the shipped tier by construction: workspace recovered from durable rows (Pitfall 2 — never fresh-minted), `selections_json` re-applied (0023), completed steps/tasks skipped via the cursor + task keys + reconciliation (45/46/48), disk re-materialized incl. boundary modes (46/48), open gates re-entered (49 — a failed run that ALSO has an unresolved durable gate resumes into the gate, not past it).
- **No third driver:** `resume_run` (+ `_drive_resumed_stream`) is the drive path. The endpoint must NOT clone `_drive_launch_to_queue`. Terminal statuses land through the engine/resume path exactly as auto-resume does — behavior identical to the fail-safe ladder (the D2 discipline) by construction, proven by test.

### E2E proof (LOCKED — ROADMAP SC5)
- Offline integration: seed a run failed MID-BUILD durably (the restart_resume harness idiom: partial per-task artifacts + failed status) → POST /resume → assert 200, status running, queue registered, resume drives with the completed tasks SKIPPED (cursor evidence) and the deliverable completes; family/history stays coherent (the run keeps its id/family linkage — no new run minted).
- Negative battery: cross-owner 404 · missing 404 · completed/cancelled 409 · already-live 409 · double-POST race (second gets 409) · arming/drive failure leaves an honest state (status not stuck `running` with no task — fail-safe back to failed + logged, or the task's own terminal handling covers it; pin the exact behavior).

### Guardrails (LOCKED — POR §7 + standing)
- INV-1/SC-001 (generic status/identity keying only) · INV-2 · INV-3 (goldens 10/10 `SNAPSHOT_UPDATE` unset — the endpoint is dormant on golden runs by construction; NO new WS event types; `run_resuming` is existing) · INV-12 (reuse resume_run/_stamp_resume_marker/the bridge/the 46-05 hooks; no third driver; no new status) · INV-5 · INV-13 · lint-imports 4/0 · ownership default-deny.
- The Phase 45-49 test floor stays green (restart_resume 39/0 + all suites at their held baselines: redo 4/3, declared_gate_streaming 3 env-reds, goldens 10/10); KAN-88 stays green.
- No migration. The LOCK-E/ND-4 supersede record (POR §8.1) is the authorization — cite it in the plan header.

### Execution constraints (LOCKED — standing)
- feat/ui-2 only · NO trailers · NEVER push · NEVER `git stash` · python3.11 no venv · ABSOLUTE cd backend/ (stray backend/backend exists) · targeted pytest only · NO live Bedrock in executors · sequential.

### Claude's Discretion
- The exact 409 error-body vocabulary (mirror the existing `pipeline_already_running`/command-endpoint shapes).
- Whether the failure-during-arm path flips back to `failed` synchronously or relies on the spawned task's own terminal handling — pin ONE behavior with a test.
- Plan decomposition (likely ONE plan, 2 tasks: endpoint + guards → E2E integration + battery; or two plans if the integration surface is cleaner split).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` — POR §5.6 (full mechanics incl. G6), §6-R5, §7, **§8.1 (the LOCK-E supersede — the authorization record)**. READ FULLY.
- `.planning/ROADMAP.md` — "### Phase 50" block (5 success criteria) + v3.0 header.
- `.planning/REQUIREMENTS.md` — RESUME-18.
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 14 (CR-01 `pipeline_already_running` precedent), Phase 33 (M4 replay/idempotency lesson), Phase 43/44 (live-ectx registry, run_engine bridge, SSE semantics, the launch-callback site :1373-1381), Phase 12 (Pitfall 2 workspace recovery; `_stamp_resume_marker`), quick 260615-dzk (selections), BUG-013/BUG-015 entries (AUTO_STREAM_STATUSES + live-attach semantics).
- Phase 45-49 folders — SUMMARYs/VERIFICATIONs (the shipped tier this endpoint fronts; 49's `_rearm_gate_run`/`_drive_resumed_stream` shapes).
- Code: `backend/app/api/run_commands.py` (endpoint home; the launch callback threading; `_gate_is_pending`/registries; error vocab), `backend/app/api/run_engine.py` (`_register_resume_queue`/`_register_resume_task`, `_PIPELINE_QUEUES`/`_CANCEL_EVENTS`), `backend/app/main.py` (how the restore engine instance gets its hooks — the wiring the endpoint must match), `backend/agents/execution_engine/engine.py` (resume_run + hooks + `_stamp_resume_marker` + NON_TERMINAL/status handling), `backend/app/api/runs.py` (the two-layer owner-check idiom `_owner_gate_or_404`), FE `frontend/src/providers/RunConnectionProvider.tsx` (AUTO_STREAM_STATUSES — read-only context; NO FE edits).
- Tests: `backend/tests/unit/test_rest_run_launch.py` + `test_rest_answers_cancel.py` (endpoint-test idioms), `tests/agents/test_restart_resume.py` (the seed harness + the shipped 39-test floor), goldens, lint.

</canonical_refs>

<specifics>
## Specific Ideas

- The restore scan arms hooks on ONE engine instance in `app/main.py` — the endpoint should drive resume through machinery with the SAME hooks; research whether run_commands shares that instance (module-level engine?) or constructs per-call, and pin the cleanest reuse (worst case: thread the three callables explicitly at the endpoint's create_task site, exactly like launch does at :1373-1381 — that is already the sanctioned pattern).
- A failed run whose failure happened AT a gate (failed via the old KAN-88 behavior pre-49, or arm-failure fail-safe) should, on user resume, flow through the 49 classifier: open durable gate → re-enter the gate. No special-casing — the classifier does it; add the test.
- `_stamp_resume_marker` already handles marker emission + workspace recovery on the resume path — the endpoint should not duplicate any of it.

</specifics>

<deferred>
## Deferred Ideas

- The FE "Resume" affordance (button on failed runs in history/run screen) — follow-on UI work; the API contract this phase ships is what it will call.
- Resuming `cancelled` runs (user-initiated cancel is a deliberate stop — different product semantics; revisit if asked).
- Live-Bedrock reopen-and-fix proof — the milestone-end consolidated live pass (orchestrator-owned).

</deferred>

---

*Phase: 50-user-resume-from-failed-r5*
*Context gathered: 2026-07-19 via POR Ingest Express Path (LOCK-E/ND-4 supersede §8.1 = the authorization)*
