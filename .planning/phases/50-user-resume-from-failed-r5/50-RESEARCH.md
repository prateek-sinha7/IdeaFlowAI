# Phase 50: User Resume-From-Failed [R5] — Research

**Researched:** 2026-07-19
**Domain:** REST command endpoint over the shipped Phase 45–49 resume tier (FastAPI · SQLAlchemy · asyncio · LangGraph engine)
**Confidence:** HIGH (every anchor read at file:line in current `feat/ui-2`; all baselines run offline)
**Authorization:** LOCK-E/ND-4 supersede record — POR §8.1 (cite in the plan header).

---

## Summary

The endpoint `POST /api/runs/{id}/resume` is the ONLY new surface; drive is pure reuse of
`engine.resume_run`. The recommended shape is **one plan, two tasks**: (1) the endpoint +
guards + a THIN app-layer wrapper coroutine; (2) the offline E2E integration + negative
battery. The single non-trivial design finding: **`resume_run`/`_drive_resumed_stream` never
writes `WorkflowRun.status`** — terminal status is written ONLY by the app-layer drivers
(`_drive_launch_to_queue` :1471-1490, `_drive_revision_to_queue` `_persist_terminal_status`
:1707). So a bare `create_task(resume_run)` would leave a user-resumed run stuck `running`
forever on success AND on arm-failure. The fix is a **thin wrapper** `_drive_user_resume` that
`await`s `resume_run` (the sole drive path — NOT a clone of the engine-event ladder) and then
reconciles `WorkflowRun.status` from the durable terminal tail, flipping back to `failed` on
arm-failure. The engine singleton's resume hooks are ALREADY armed at startup
(`app/main.py:141-154`) and `_drive_launch_to_queue` uses the SAME `get_execution_engine()`
singleton — so the three live-layer callbacks (queue/task/live-ectx/milestone) need **zero
re-threading**: they fire automatically inside `resume_run`. Gate-at-failure composes for free
through the 49 classifier. All 10 at-risk suites are at their held baselines (restart_resume
39/0, goldens 10/10, lint 4/0).

**Primary recommendation:** Flip `failed→running`, register queue BEFORE the flip, stamp the
`run_resuming` marker, then `create_task(_drive_user_resume(run_id))` where that thin wrapper
delegates ALL drive to `resume_run` and adds ONLY terminal-status reconciliation + arm-failure
flip-back. No third engine driver; no FE edits; no migration.

---

## Verified Current-State Anchors

| Concern | Anchor (file:line) | Fact | Prov |
|---|---|---|---|
| Engine singleton + hook arming | `app/main.py:133-155` | startup calls `get_execution_engine()` then sets `_resume_register_queue/_resume_register_task/_resume_cleanup/_resume_live_ectx_register/_resume_live_ectx_unregister/_resume_milestone_sink`, then `restore_non_terminal_runs()` | VERIFIED |
| Launch driver uses SAME singleton | `run_commands.py:1327` | `engine = get_execution_engine()` — the identical module singleton main.py armed | VERIFIED |
| resume_run body | `engine.py:7233-7419` | reads WorkflowRun row (type/input/user_id/session_id/parent_run_id/selections_json), computes offset, seeds seq, registers live queue via injected hook (:7359), drives `_drive_resumed_stream` with `_is_resume=True, _resume_from=offset` | VERIFIED |
| resume_run writes NO status | `engine.py:7233-7419` grep | only READS `WorkflowRun` (:7259); never assigns `.status` | VERIFIED |
| Shared resume driver | `engine.py:7421-7554` | `_drive_resumed_stream`: persists events via `_RunEventSink`, pushes to live_queue, emits milestone cards, `finally` fires `_fire_resume_cleanup` + `_resume_live_ectx_unregister` — **no `WorkflowRun.status` write** | VERIFIED |
| `_RunEventSink` | `engine.py:322-416` | persists run_events + milestone cards only; NO status write | VERIFIED |
| Terminal-status writers (all) | grep app+agents | ONLY `run_commands.py:1471/1475/1484/1490/1541/1557`, `_drive_revision`'s `_persist_terminal_status` :1707, and restore branch-c fail `engine.py:5251/5333/5401`; `fanout.py:428` is wave-local | VERIFIED |
| Restore branch-b ordering | `engine.py:5344-5394` | `_is_resumable_in_flight` → `_stamp_resume_marker(wr)` FIRST → register queue → `create_task(resume_run)` → register task | VERIFIED |
| `_stamp_resume_marker` | `engine.py:5524-5569` | additive `run_resuming` event at `max(seq)+1` via recovered workspace_id; best-effort; NO status write (additive event, not a status) | VERIFIED |
| `_is_resumable_in_flight` | `engine.py:5490-5522` | True iff `compile_for_run` succeeds AND ≥1 durable run_events/artifact_refs/wave_runs row (owner-scoped) | VERIFIED |
| Overlap registries | `run_engine.py:39-47` | `_PIPELINE_QUEUES`, `_PIPELINE_TASKS`, `_CANCEL_EVENTS` — module-level dicts, single event-loop thread | VERIFIED |
| Live-attach (BUG-015) | `run_stream.py:281` | `live_queue = _get_or_create_queue(id) if id in _PIPELINE_QUEUES else None` — queue MUST exist before attach or `live=False` | VERIFIED |
| FE auto-attach | `RunConnectionProvider.tsx:65-71` | `AUTO_STREAM_STATUSES = {running, planning, analyzing, generating, revising}` — `running` present ⇒ FE auto-attaches; parked runs excluded (BUG-013) | VERIFIED |
| Owner idiom (404) | `run_commands.py:324-348` (`_review_gate_owned_by`), `1634-1642` (revision parent), `run_engine.py:436-472` (`_resolve_owned_parent_run_id`) | ORM `WorkflowRun.user_id == user_id` filter; missing == cross-owner → 404, never 403; keyed on `user_id` never nullable `owner_id` | VERIFIED |
| 409 error vocab | `run_commands.py:1061-1068` (`_reject`), `198-215`, `649` | `HTTPException(status_code=409, detail={"error","code","recoverable",...})`; CR-01 precedent `pipeline_already_running` (register :1454) | VERIFIED |
| Gate-reentry classifier | `engine.py:6944-6962` | `_first_incomplete_step` open-gate override: `derive_open_gate(durable_rows)` → returns gated step index | VERIFIED |
| Gate-reentry sentinel set | `engine.py:2187-2199` | `_execute_impl` sets `ectx.gate_reentry={agent_id,artifact_kind,gate_key}` when `_resume_from` == gated step | VERIFIED |
| Gate-reentry consumer | `engine.py:3038-3059` | consume-once; reconstructs output from `_latest_typed_content` max-version; re-opens gate model-skip; all five actions identical | VERIFIED |
| Workspace recovery (Pitfall 2) | `engine.py:6477` (`_recover_workspace_id`), used :7342/:7716/:5552 | recovers ORIGINAL workspace_id from durable rows — never fresh-minted | VERIFIED |
| selections re-apply (0023) | `engine.py:7288`, `7414`, `7464-7468` | `wr.selections_json` re-threaded through `_apply_selections` trust=user re-compile | VERIFIED |
| M4 idempotency lesson | register :3168 | "no idempotency short-circuit on a replayed message_id can re-mint a revision child run" — the re-mint hazard | CITED |

---

## Hook/Instance Plumbing (recommendation)

**Finding:** `run_commands._drive_launch_to_queue:1327` and `app/main.py:134` both call
`get_execution_engine()` — the **same module singleton**. `app/main.py:141-154` arms that
singleton's six resume hooks at startup, BEFORE `restore_non_terminal_runs()`. Those hooks
persist for the process lifetime. `resume_run` consumes them internally
(`self._resume_register_queue` :7359, `self._resume_milestone_sink`/`_resume_live_ectx_register`
via `_drive_resumed_stream` :7453/:7473, unregister :7547).

**Recommendation — REUSE THE ARMED SINGLETON; DO NOT re-thread callbacks.** Unlike the launch
path (which threads `live_ectx_register=`/`milestone_sink=` explicitly at
`run_commands.py:1375-1383` because `engine.execute()` takes them as kwargs), `resume_run`
takes NO callback kwargs — it reads them off `self.*`. Since the endpoint drives through
`engine.resume_run(run_id)` on the SAME armed singleton, the live-layer trio
(register_live_ectx / unregister / milestone_sink) and the queue/task/cleanup bridge fire
automatically. **No explicit threading is needed and NONE should be added** (adding it would be
dead code — resume_run ignores kwargs it doesn't accept). This satisfies RESUME-10 by
construction: the resumed-from-failed run is a first-class live run exactly as auto-resume is.

Evidence the trio is live on the resume path today: `_drive_resumed_stream:7453` arms the sink
with `self._resume_milestone_sink`; :7473 threads `self._resume_live_ectx_register` into
`_execute_impl`; :7547 unregisters in `finally`. All None-safe (offline/goldens dormant, INV-3).

**Guaranteed unregister:** already handled by `_drive_resumed_stream`'s `finally`
(`_fire_resume_cleanup` :7540 + `_resume_live_ectx_unregister` :7547) — the endpoint adds
nothing here.

---

## Endpoint Anatomy

Clone these idioms verbatim:

**Owner gate → 404 (from `create_revision:1634-1642`):**
```python
db = _get_db()
try:
    wr = (db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == current_user.id)
            .first())
    if wr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run")
```
Missing and cross-owner are indistinguishable (no existence oracle). Keyed on `user_id`
(NEVER the nullable `owner_id` — D-06). This is the two-layer idiom's first layer; the
ScopedStore default-deny (used inside resume_run's reads) is the second.

**Eligibility (failed-only) → 409:** after the owner gate, `if wr.status != "failed": raise
_reject("run_not_resumable", f"Run is {wr.status!r}, only failed runs are resumable",
http_status=status.HTTP_409_CONFLICT)`. `_reject:1061` yields the exact
`{"error","code","recoverable"}` shape the command surface uses.

**Overlap guard → 409 (the M4 atomic guard):** the authoritative liveness signal is the
in-process registry, NOT the DB status. Check `run_id in _PIPELINE_TASKS or run_id in
_PIPELINE_QUEUES` → `raise _reject("pipeline_already_running", ...,
http_status=409)` (CR-01 vocab, register :1454). `_PIPELINE_TASKS`/`_PIPELINE_QUEUES` live in
`run_engine.py:39-40`, already imported into run_commands (:76). A `task.done()` refinement is
optional but the registry entry alone is the mutex (see Pitfalls).

**Queue-before-flip (BUG-015):** `event_queue = _get_or_create_queue(run_id)` (idempotent,
`run_engine.py:64`) MUST execute BEFORE the DB commit that flips status to `running`, so that
when the FE observes `running` (via `AUTO_STREAM_STATUSES` refresh) and opens the SSE stream,
`run_stream.py:281`'s `run_id in _PIPELINE_QUEUES` check is already true → `live=True`.

**Cancel-event seed (parity with launch :1248-1249):** `_CANCEL_EVENTS[run_id] =
asyncio.Event()` so the resumed run is Stop-able (resume_run's per-chunk cancel checks read it,
same as `_register_resume_task:117-118`).

---

## Ordering Pin (the exact sequence)

Inside the endpoint (all on the single event loop, minimize awaits between the registry mutex
and registration):

1. **Owner gate** — `db.query(WorkflowRun).filter(id==run_id, user_id==current_user.id)`; None → 404. *(await: DB read)*
2. **Eligibility** — `wr.status != "failed"` → 409 `run_not_resumable`. *(same session, no extra await)*
3. **Overlap guard (mutex)** — `run_id in _PIPELINE_TASKS or run_id in _PIPELINE_QUEUES` → 409 `pipeline_already_running`. **No await between this check and step 4–7.**
4. **Register queue** — `_get_or_create_queue(run_id)` (idempotent) + `_CANCEL_EVENTS[run_id]=asyncio.Event()`. *(sync — this is the BUG-015 pre-attach registration)*
5. **Flip status** — `wr.status = "running"`; `db.commit()`. *(await: DB commit — now the run is discoverable as live: queue present + status running)*
6. **Stamp marker** — `await engine._stamp_resume_marker(wr)` (double-drive guard; additive `run_resuming` event, NOT a status; :5524). *(Optional but recommended — mirrors branch-b :5350.)*
7. **Spawn + register task** — `task = asyncio.create_task(_drive_user_resume(run_id, user=current_user))`; `_PIPELINE_TASKS[run_id] = task`. *(sync — closes the mutex window opened at step 3)*
8. **Return 200** — `{"run_id": run_id}` (mirror launch/revision return shape).

Rationale for queue(4)-before-flip(5): the FE must never see `running` without a live queue
(BUG-015). Rationale for marker(6) after flip: the marker is an audit event, order-independent
of status; placing it after commit keeps the DB write atomic. `create_task`(7) after the flip
so the FE's `AUTO_STREAM` attach (triggered by `running`) finds both the queue AND, shortly
after, the live task — `_has_live_task` true.

Note: `resume_run` tolerates entering on an already-`running` row — it only READS the row for
identity (:7259-7288) and never asserts/writes status. So flipping to `running` in step 5
before `create_task` in step 7 is safe; there is NO status write inside resume_run/_execute_impl
that conflicts (verified grep — the only engine status writes are restore branch-c fails).

---

## Arm-Failure Behavior

**Today, if `resume_run` dies immediately:** `_drive_resumed_stream`'s `except Exception`
(:7524) logs "failed mid-drive", then `finally` (:7526-7554) fires `_fire_resume_cleanup`
(drops queue/task registry entries — WR-01) + `_resume_live_ectx_unregister`. It does **NOT**
flip `WorkflowRun.status`. If `resume_run` raises BEFORE reaching `_drive_resumed_stream` (e.g.
empty agent list :7304, unresolvable pipeline :7299), it calls `_fire_resume_cleanup` and
returns — again no status write. **Net: after the endpoint has flipped `failed→running`, any
arm/drive failure leaves the run stuck `running` with no task = a phantom-live row.** This is
the same latent gap auto-resume has, but for a user-initiated resume it is a visible defect
(the CONTEXT negative battery explicitly requires "arming/drive failure leaves an honest
state").

**Recommendation (PINNED — sync flip-back to failed, via the thin wrapper):** the endpoint
spawns a thin app-layer coroutine `_drive_user_resume` that owns terminal-status reconciliation:

```python
async def _drive_user_resume(run_id: str, *, user: User) -> None:
    engine = get_execution_engine()
    try:
        await engine.resume_run(run_id)          # SOLE drive path — armed-singleton hooks fire
        # reconcile terminal status from the durable tail (last pipeline_* event)
        _reconcile_terminal_status(run_id)        # → completed / degraded / failed / cancelled
    except Exception as exc:
        logger.error("user-resume drive failed run=%s: %s", run_id, exc, exc_info=True)
        _flip_back_to_failed(run_id, str(exc))    # honest state, never stuck "running"
```

This is **NOT a third engine driver** — it re-implements none of `_drive_launch_to_queue`'s
~260-line `engine.execute` event ladder. It delegates 100% of the drive to `resume_run` and
adds ONLY the two status writes the resume tier structurally lacks. `_reconcile_terminal_status`
reads the run's durable `run_events` tail (owner-scoped ScopedStore) for the terminal
`pipeline_complete`/`pipeline_failed`/`pipeline_cancelled` and maps to `completed`/`degraded`/
`failed`/`cancelled` — the same mapping `_drive_launch_to_queue:1470-1491` applies from the live
stream. Both writes are best-effort (offline harness has no DB → degrade, INV-3).

**Why the wrapper, not a shared-tier change:** adding a status writer to `_drive_resumed_stream`
would change AUTO-RESUME behavior (currently leaves status non-terminal) — explicitly OUT of
scope per CONTEXT ("any change to the auto-resume path's behavior beyond reuse"). So the
reconciler MUST live in the endpoint-specific wrapper.

> **CONTEXT tension to flag for the planner/discuss:** the CONTEXT states "Terminal statuses
> land through the engine/resume path exactly as auto-resume does." The verified code reality is
> that auto-resume does NOT reconcile `WorkflowRun.status` at all. A literal "exactly as
> auto-resume does" would ship a run stuck `running`. The thin wrapper is the minimal
> reconciliation that satisfies the E2E proof ("deliverable completes; family/history coherent")
> and the negative battery ("arm-failure leaves an honest state") WITHOUT cloning the engine
> driver or perturbing auto-resume. This is the single decision the plan must lock.

---

## Gate-at-Failure Composition

A failed run that ALSO carries a durable open review gate resumes INTO the gate, not past it —
**zero endpoint special-casing.** Verified trace:

1. Endpoint → `create_task(_drive_user_resume)` → `resume_run` → `_compute_resume_offset:7698`
   → `_first_incomplete_step:6865`.
2. `_first_incomplete_step:6957-6962` open-gate override: `derive_open_gate(durable_rows)`
   returns `("review", gate_key)`; the loop returns the gated step index `_j` (parsed from
   `gate_key = f"{run}:{agent_id}"`) as the offset — the gated agent produced its output but is
   PARKED, so its step is the resume point, not "complete".
3. `resume_run` drives `_drive_resumed_stream(_resume_from=offset, _is_resume=True)` →
   `_execute_impl:2187-2199` sets `ectx.gate_reentry = {agent_id, artifact_kind, gate_key}`.
4. Dispatch loop `:3038-3059` consumes the sentinel (consume-once, guarded on `spec.id`):
   reconstructs output from `_latest_typed_content` max-version (F5), re-seeds `ectx.last_streamed`,
   seeds redo/spec-revision attempt counters fail-safe-high, re-opens the gate **model-skip** —
   all five actions (approve/reject/edit/redo/update_specs) identical post-resume.

**Test design (add to the battery):** seed a run `status="failed"` durably with (a) partial
per-task artifacts AND (b) a durable `review_gate_ready` event for a gated agent with NO
`review_gate_response`/resolution. POST /resume → assert 200, status flips `running`, and the
resumed stream re-emits `review_gate_ready` for that gate (the run parks at the gate) rather
than running the gated agent's model or completing past it. Reuse the restart_resume gate-seed
idioms (test_restart_resume seeds compilable rows + durable events).

---

## Family Coherence

- **Same run id, no new row.** `resume_run:7259` reads the EXISTING `WorkflowRun` by id and
  mints nothing (verified: no `WorkflowRun(...)` constructor anywhere in the resume path — the
  only minters are launch :1256 and `_mint_revision_row` :1601). The endpoint likewise never
  mints. RESUME-18's "NEVER re-mint a run row" holds by construction.
- **Family linkage intact.** `parent_run_id` is READ from the row (:7269) and never rewritten;
  the `/family` + `root_run_id` walk (runs.py) is unaffected.
- **Runs list.** `GET /api/runs` reads `r.status` directly (runs.py:985/1147) — after the flip
  it shows `running` (then the wrapper reconciles to `completed`/`failed` at terminal). The FE
  `AUTO_STREAM_STATUSES` includes `running` (RunConnectionProvider.tsx:65-71) → the reopened run
  auto-attaches its SSE stream on the next `refreshLiveRuns`. **Read-only confirm — NO FE edits.**
- The focused-run sticky (:60-63) keeps a viewed run streamed even while parked, so the
  resume→gate→build transition streams live without FE changes.

---

## At-Risk Tests & Baseline (real output, 2026-07-19, python3.11, offline)

| Suite | Command target | Baseline | Status |
|---|---|---|---|
| restart_resume | `tests/agents/test_restart_resume.py` | **39 passed / 0** | GREEN (floor) |
| rest_run_launch | `tests/unit/test_rest_run_launch.py` | **25 passed / 0** | GREEN |
| rest_answers_cancel | `tests/unit/test_rest_answers_cancel.py` | **9 passed / 0** | GREEN |
| rest_revisions | `tests/unit/test_rest_revisions.py` | **14 passed / 0** | GREEN |
| approve_review_ownership | `tests/unit/test_approve_review_ownership.py` | **6 passed / 0** | GREEN |
| sse_stream | `tests/unit/test_sse_stream.py` | **17 passed / 0** | GREEN |
| mechanical_router | `tests/unit/test_mechanical_router.py` | **28 passed / 0** | GREEN |
| goldens (characterization ×5) | `tests/agents/test_characterization_*.py` | **10 passed / 0** | GREEN (INV-3 floor) |
| redo_gate_safety | `tests/agents/test_redo_gate_safety.py` | **4 passed / 3 failed** | HELD (3 env-reds, pre-existing) |
| declared_gate_streaming | `tests/agents/test_declared_gate_streaming.py` | **0 passed / 3 failed** | HELD (3 env-reds — Chromium/Bedrock-gated) |
| lint-imports | `/opt/homebrew/bin/lint-imports` | **4 kept / 0 broken** | GREEN |

The two HELD suites (redo 4/3, declared_gate_streaming 0/3) are environment-gated reds that
match the CONTEXT-stated floor — do NOT attempt to green them in this phase. Everything else
must stay at these tallies. New tests land in `tests/unit/test_rest_resume.py` (new file,
mirroring `test_rest_revisions.py` structure) + additions to `tests/agents/test_restart_resume.py`
for the failed→resume E2E.

---

## Pitfalls

1. **Terminal-status gap (the headline).** `resume_run` writes NO `WorkflowRun.status`. A bare
   `create_task(resume_run)` leaves a resumed-from-failed run stuck `running` on success and on
   failure. → the thin `_drive_user_resume` wrapper reconciles terminal status + flips back to
   `failed` on arm-failure. Verified by grep: the only resume-path status writers are none.

2. **Double-POST race atomicity.** Two concurrent POSTs both `await` the DB eligibility read and
   could both see `status=="failed"`. The atomic mutex is NOT the DB status — it is the
   in-process `_PIPELINE_TASKS`/`_PIPELINE_QUEUES` registry check. asyncio has no preemption
   without `await`: perform the overlap check (step 3) and the registration (steps 4/7) with **no
   `await` between the check and `_get_or_create_queue`/`_PIPELINE_TASKS[...]=`**. The second
   coroutine, resuming after the first registered, sees the entry → 409. (The DB commit's await
   sits AFTER the sync registration, so it cannot reopen the window.) This is the P33 M4 lesson
   applied: the durable `run_resuming` marker makes a LATER replay idempotent; the in-process
   registry makes a CONCURRENT double-POST atomic.

3. **Queue-after-flip (BUG-015 regression).** If the status flip commits before
   `_get_or_create_queue`, the FE's attach hits `run_id not in _PIPELINE_QUEUES` →
   `live=False` → the stream settles disconnected and the run "runs forever" from the FE's view.
   Register queue in step 4, commit in step 5.

4. **Fresh-minted workspace (Pitfall 2).** Do NOT construct a workspace or ScopedStore in the
   endpoint. resume_run recovers the ORIGINAL `workspace_id` from durable rows
   (`_recover_workspace_id` :7342/:7716) — a fresh id makes owner+workspace-scoped reads resolve
   to ∅ (binding drift). The endpoint only reads the row for the owner gate; all recovery is
   inside resume_run.

5. **Re-minting a run row.** Never. resume_run keeps the same id/family; the endpoint must not
   create a WorkflowRun. Assert "no new row" in the E2E.

6. **INV-3 dormancy.** The endpoint is absent from every golden path by construction (goldens
   are scripted offline runs with no DB, never hit `/resume`). No new WS/SSE event types
   (`run_resuming` is existing). `_stamp_resume_marker` uses the additive event, not a new
   status. The 10 goldens + 39 restart_resume must stay byte/event-identical.

7. **No third driver.** `_drive_user_resume` delegates ALL drive to `resume_run`; it must not
   loop over `engine.execute` events or clone `_drive_launch_to_queue`/`_drive_revision_to_queue`.
   Its only logic is post-completion status reconciliation + arm-failure flip-back. Enforce via
   review: the wrapper body has no `async for ... engine.execute(`.

8. **Owner keyed on `user_id`, 404 never 403.** Use `WorkflowRun.user_id == current_user.id`
   (not `owner_id`). Missing and cross-owner both → 404 (no existence oracle). Cloned from
   `create_revision:1634-1642`.

---

## Validation Architecture

**Framework:** pytest 8.3.4 + pytest-asyncio 0.24 (STRICT), python3.11 no venv, ABSOLUTE `cd backend/`.

**Req → Test map (RESUME-18):**

| Behavior | Test | Command |
|---|---|---|
| owner 404 (cross-owner + missing) | `test_resume_cross_owner_404`, `test_resume_missing_404` | `python3.11 -m pytest tests/unit/test_rest_resume.py -x` |
| eligibility 409 (completed/cancelled/running) | `test_resume_completed_409`, `test_resume_cancelled_409` | ″ |
| overlap 409 (already live) | `test_resume_already_running_409` | ″ |
| double-POST race (2nd → 409) | `test_resume_double_post_second_409` | ″ |
| queue-before-flip (live attach) | `test_resume_registers_queue_before_status_flip` | ″ |
| status flip failed→running + marker | `test_resume_flips_running_and_stamps_marker` | ″ |
| E2E: failed mid-build → resume → tasks skipped, deliverable completes, same id | `test_failed_run_resumes_skips_completed_tasks` | `python3.11 -m pytest tests/agents/test_restart_resume.py -x` |
| gate-at-failure re-entry | `test_failed_run_with_open_gate_resumes_into_gate` | ″ |
| arm-failure → honest state (back to failed, not stuck running) | `test_resume_arm_failure_flips_back_to_failed` | `python3.11 -m pytest tests/unit/test_rest_resume.py -x` |

**Sampling:** per-task commit → the touched suite (`test_rest_resume.py` ~<1s or
`test_restart_resume.py` ~2s); per-wave/phase gate → the full at-risk battery above +
`lint-imports` (all must return to the recorded baseline tallies).

**Wave 0 gaps:** `tests/unit/test_rest_resume.py` (new file — endpoint battery; model on
`test_rest_revisions.py`); new failed→resume + gate-at-failure cases appended to
`test_restart_resume.py` (reuse its durable-seed harness). No framework install needed.

---

## RESEARCH COMPLETE

1. **Reuse the armed singleton** — `run_commands` and `app/main.py` share `get_execution_engine()`; resume_run reads the six hooks off `self.*`, so the live-layer trio fires automatically. Do NOT re-thread callbacks (resume_run takes none).
2. **The one real gap:** `resume_run`/`_drive_resumed_stream` never write `WorkflowRun.status` (only app drivers do, :1471/:1707). A bare `create_task(resume_run)` strands a resumed run at `running`. Fix = thin `_drive_user_resume` wrapper (delegates drive to resume_run; adds only terminal reconcile + arm-failure flip-back). NOT a third engine driver.
3. **Ordering pinned:** owner-404 → eligibility-409 → overlap-409(registry mutex, no await) → register queue → flip running + commit → stamp marker → create_task(wrapper) + register task → 200. Queue-before-flip = BUG-015; registry-check-then-register-with-no-await = double-POST atomicity.
4. **Gate-at-failure composes free** through the 49 classifier (`_first_incomplete_step:6957` → `gate_reentry` sentinel :2195 → consumer :3038) — zero endpoint special-casing; add the seed test.
5. **Family coherent:** same run id, no new row, parent link untouched, `running∈AUTO_STREAM_STATUSES` ⇒ FE auto-attaches — no FE edits.
6. **Baselines all at floor:** restart_resume 39/0, rest suites 25/9/14/6, sse 17, router 28, goldens 10/0, lint 4/0; held reds redo 4/3 + declared_gate_streaming 0/3 (env). Recommend ONE plan / TWO tasks (endpoint+wrapper+guards → E2E+battery). Cite POR §8.1 LOCK-E supersede in the plan header.
