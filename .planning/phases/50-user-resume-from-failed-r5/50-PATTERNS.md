# Phase 50: User Resume-From-Failed [R5] - Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 3 (1 new endpoint surface + wrapper in `run_commands.py`; 1 new test file; 1 test-file addition)
**Analogs found:** 6 / 6 concerns (every anchor re-read at file:line on `feat/ui-2`)
**Effort:** MAXIMUM — current-file excerpts, verified line numbers, drift flagged.

> Read alongside `50-RESEARCH.md` (the singleton finding, the terminal-status gap +
> thin-wrapper recommendation, the ordering pin) and `50-CONTEXT.md` (LOCKED decisions).
> This file is the concrete copy-source map; RESEARCH is the rationale.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/api/run_commands.py` → `POST /{run_id}/resume` endpoint | route/controller | request-response | `create_revision` (`run_commands.py:1617`) + `cancel_run` (`:284`) + `resolve_gate` (`:164`) | role+flow exact |
| `app/api/run_commands.py` → `_drive_user_resume` wrapper | driver (thin) | event-driven→terminal-write | `_drive_revision_to_queue._persist_terminal_status` (`:1707`) + `_drive_launch_to_queue` terminal writes (`:1465-1491`) | role-match (deliberately thinner — NOT a third ladder) |
| `tests/unit/test_rest_resume.py` (NEW) | test | request-response | `test_rest_revisions.py` + `test_rest_answers_cancel.py` | exact harness |
| `tests/agents/test_restart_resume.py` (ADD cases) | test | event-driven E2E | `_seed_workflow_run` (`:374`) + `test_waiting_for_user_rearm_arm_failure_falls_back_to_wr05_fail` (`:1029`) + `_seed_open_review_gate` (`:948`) | exact harness |

---

## Pattern Assignments

### 1. The endpoint `POST /{run_id}/resume` (route, request-response)

**Analogs:** `create_revision` (owner gate + mint + spawn), `cancel_run` (owner gate + registry lookup), `resolve_gate` (409 terminal-fence vocab), `_reject` (error shape).

**Owner gate → 404** — copy verbatim from `create_revision` (`run_commands.py:1632-1642`):
```python
db = _get_db()
try:
    wr = (db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == current_user.id)
            .first())
    if wr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run")
```
Keyed on `user_id` (NEVER nullable `owner_id`); missing == cross-owner → 404. Identical
idiom lives in `runs.py:1210` `_owner_gate_or_404` (the shared audit-read gate) — same
`.filter(id==, user_id==).first()` → 404 shape. Use the inline form (like `create_revision`),
not the `runs.py` helper (different module/`Session` dep-injection).

**Error-shape factory** — reuse `_reject` (`run_commands.py:1061-1068`) AS-IS:
```python
def _reject(code, error, *, http_status=status.HTTP_400_BAD_REQUEST, recoverable=False, **extra):
    detail = {"error": error, "code": code, "recoverable": recoverable}
    detail.update(extra)
    return HTTPException(status_code=http_status, detail=detail)
```

**Eligibility (failed-only) → 409** — new, patterned on `resolve_gate`'s terminal fence
(`:197-205`, which raises `409` + `{"error","code","recoverable"}`):
```python
if wr.status != "failed":
    raise _reject("run_not_resumable",
                  f"Run is {wr.status!r}; only failed runs are resumable",
                  http_status=status.HTTP_409_CONFLICT)
```

**Overlap guard → 409 (the M4 mutex, CR-01 vocab)** — the authoritative liveness signal is
the in-process registry, NOT the DB status. `_PIPELINE_TASKS`/`_PIPELINE_QUEUES` are already
imported into `run_commands` (`:73`), defined at `run_engine.py:39-40`:
```python
if run_id in _PIPELINE_TASKS or run_id in _PIPELINE_QUEUES:
    raise _reject("pipeline_already_running",
                  "Run is already live", http_status=status.HTTP_409_CONFLICT)
```
(`pipeline_already_running` is the CR-01 code; the launch/revision paths register into these
same dicts at `:1297`/`:1667`.)

**Queue + cancel-event seed** — mirror launch (`:1248-1249`, `:1276`) and `_register_resume_task`
(`run_engine.py:117-118`):
```python
event_queue = _get_or_create_queue(run_id)          # idempotent (run_engine.py:64)
_CANCEL_EVENTS[run_id] = asyncio.Event()
```

**Flip status + commit** — plain ORM write on the SAME `wr` (no new status; INV-12):
```python
wr.status = "running"
db.commit()
```

**Stamp marker** — reuse the engine method, do NOT reimplement (`engine.py:5524`):
```python
await get_execution_engine()._stamp_resume_marker(wr)   # additive run_resuming event
```

**Spawn + register task + return** — mirror launch (`:1277-1299`):
```python
task = asyncio.create_task(_drive_user_resume(run_id, user=current_user))
_PIPELINE_TASKS[run_id] = task
return {"run_id": run_id}
```

**COPY:** the owner-gate block, `_reject`, the queue/cancel/task registry idioms, the
`{"run_id": ...}` return shape.
**DEVIATE:** no mint (resume reuses the existing row — never construct `WorkflowRun`, unlike
launch `:1256` / `_mint_revision_row` `:1601`); spawn `_drive_user_resume`, NOT
`_drive_launch_to_queue`.

---

### 2. Singleton + armed hooks (reuse — zero re-threading)

**Analog:** `_drive_launch_to_queue:1327` and `app/main.py:134` BOTH call the same module
singleton `get_execution_engine()`.

**Hook-arming block (`app/main.py:141-154`)** — arms six resume hooks on that singleton at
startup, BEFORE `restore_non_terminal_runs()`:
```python
engine_instance._resume_register_queue = _ws_bridge._register_resume_queue
engine_instance._resume_register_task  = _ws_bridge._register_resume_task
engine_instance._resume_cleanup        = _ws_bridge._cleanup_pipeline
engine_instance._resume_live_ectx_register   = register_live_ectx
engine_instance._resume_live_ectx_unregister = unregister_live_ectx
engine_instance._resume_milestone_sink       = persist_milestone_card
await engine_instance.restore_non_terminal_runs()
```

**`resume_run` reads hooks off `self.*` (never kwargs):** it takes ONLY `run_id`
(`engine.py:7233 async def resume_run(self, run_id)`), reads `self._resume_register_queue`
etc. internally. Contrast `engine.execute(...)` which the launch driver feeds
`live_ectx_register=` / `live_ectx_unregister=` / `milestone_sink=` explicitly
(`run_commands.py:1375-1383`).

**COPY:** nothing — the endpoint drives `engine.resume_run(run_id)` on the same armed
singleton, so the live-layer trio + queue/task/cleanup bridge fire automatically.
**DEVIATE (DO NOT):** do NOT thread `live_ectx_register=`/`milestone_sink=` at the resume
call site — `resume_run` accepts no such kwargs; adding them is dead code (RESEARCH §Hook
Plumbing). This is the launch-vs-resume divergence to flag.

---

### 3. The thin `_drive_user_resume` wrapper (driver — deliberately thinner)

**Analogs:** `_persist_terminal_status` (`:1707`) — the exact status-write idiom; the launch
driver terminal-status mapping (`:1465-1491`) — the event→status decision table; the
arm-failure flip-back — `_drive_launch_to_queue`'s `except Exception` (`:1546-1562`) and the
`test_restart_resume.py:1029` WR-05 fail-safe philosophy.

**The status-write idiom to borrow (`_drive_revision_to_queue._persist_terminal_status:1707`):**
```python
def _persist_terminal_status(new_status: str) -> None:
    sdb = _get_db()
    try:
        swr = sdb.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
        if swr:
            swr.status = new_status
            swr.completed_at = datetime.now(timezone.utc)
            sdb.commit()
    finally:
        sdb.close()
```

**The event→status mapping to mirror (`_drive_launch_to_queue:1470-1491`):**
```python
if pipeline_cancelled_seen:            wr.status = "cancelled"
elif degraded_failed_agents is not None: wr.status = "degraded"
elif pipeline_complete_seen and not pipeline_error_seen and not pipeline_failed_seen:
                                       wr.status = "completed"
else:                                  wr.status = "failed"   # fail-safe on any error/no-clean-terminal
```

**Wrapper shape (from RESEARCH §Arm-Failure, PINNED):**
```python
async def _drive_user_resume(run_id: str, *, user: User) -> None:
    engine = get_execution_engine()
    try:
        await engine.resume_run(run_id)        # SOLE drive path — armed-singleton hooks fire
        _reconcile_terminal_status(run_id)      # read durable tail → completed/degraded/failed/cancelled
    except Exception as exc:
        logger.error("user-resume drive failed run=%s: %s", run_id, exc, exc_info=True)
        _flip_back_to_failed(run_id, str(exc))  # honest state — never stuck "running"
```
`_reconcile_terminal_status` reads the run's durable `run_events` tail (owner-scoped
ScopedStore) for the terminal `pipeline_complete`/`pipeline_failed`/`pipeline_cancelled` and
maps via the `:1470-1491` table. `_flip_back_to_failed` is the `_persist_terminal_status`
idiom above with `new_status="failed"` + `wr.error = exc`.

**COPY:** the `_get_db()`/query/`.status=`/`completed_at`/`commit`/`finally close()` idiom;
the four-way event→status decision.
**DEVIATE (HARD — Pitfall 7 / INV-12):** the wrapper MUST NOT contain `async for ... engine.execute(`
and MUST NOT clone `_drive_launch_to_queue`'s ~260-line event ladder (the whole
`agent_start`/`tool_call`/`agent_complete` accumulation at `:1387-1463`). It delegates 100%
of drive to `resume_run` and adds ONLY the two status writes the resume tier structurally
lacks. Do NOT add a status writer to `_drive_resumed_stream` (would perturb auto-resume — OUT
of scope).

---

### 4. Ordering pin — queue-register → status flip → marker → create_task

**Analog (the canonical sequence to mirror):** restore branch-b (`engine.py:5344-5394`):
`_is_resumable_in_flight` → `_stamp_resume_marker(wr)` FIRST → `_resume_register_queue`
(`:5367`) BEFORE `create_task(self.resume_run(...))` (`:5376`) → `_register_resume_task`
(`:5384`). The comment at `:5353-5366` (WR-02) is the exact rationale: register the live
queue at the SAME synchronous site as the driver task, BEFORE `create_task`, because
`resume_run` registers the queue again only after several awaited DB round-trips — a client
reconnecting in that window saw a task with NO queue.

**The BUG-015 attach condition proving queue-before-flip (`run_stream.py:281`):**
```python
live_queue = _get_or_create_queue(workflow_id) if workflow_id in _PIPELINE_QUEUES else None
```
If the status flip commits before `_get_or_create_queue`, the FE's SSE attach (triggered by
`running ∈ AUTO_STREAM_STATUSES`) hits `workflow_id not in _PIPELINE_QUEUES` → `live_queue=None`
→ `live=False` → "runs forever" from the FE's view. So register queue (step 4) BEFORE commit
(step 5).

**Endpoint sequence (RESEARCH ordering pin):** owner-404 → eligibility-409 → overlap-409
(registry mutex) → register queue + cancel-event → flip `running` + commit → stamp marker →
`create_task(_drive_user_resume)` + register task → return 200.

**COPY:** the branch-b register-queue-before-create_task ordering (endpoint version is
synchronous, not via the `_resume_register_*` hooks — the endpoint calls
`_get_or_create_queue`/`_PIPELINE_TASKS[...]=` directly since it runs in-process on the API
event loop).
**DEVIATE:** the endpoint flips status to `running` explicitly (branch-b never writes status —
its runs are already non-terminal). Marker placement: after commit (audit event,
order-independent) — matches branch-b intent, differs in that branch-b stamps before commit
because it has no status flip.

---

### 5. Double-POST mutex (in-process registry, asyncio no-preemption)

**Analog:** the registry-check idiom used by existing guards; `_PIPELINE_TASKS`/`_PIPELINE_QUEUES`
membership checks. `cancel_run:300` reads `_CANCEL_EVENTS.get(run_id)`; `run_stream.py:281`
reads `workflow_id in _PIPELINE_QUEUES`.

**Argument (RESEARCH Pitfall 2):** asyncio has NO preemption without `await`. Perform the
overlap check (step 3) and the registration (`_get_or_create_queue` + `_PIPELINE_TASKS[...]=`)
with **NO `await` between them**. The `db.commit()` await sits AFTER the sync registration, so
it cannot reopen the window. The second concurrent POST, resuming after the first registered,
sees the entry → 409. Durable `run_resuming` marker makes a LATER replay idempotent; the
in-process registry makes a CONCURRENT double-POST atomic (P33 M4 lesson).

**COPY:** the `run_id in _PIPELINE_TASKS or run_id in _PIPELINE_QUEUES` membership test +
immediate synchronous registration.
**DEVIATE:** none.

---

### 6. Test idioms

**Analog A — endpoint battery (`test_rest_revisions.py` + `test_rest_answers_cancel.py`):**
- Harness: in-memory SQLite `StaticPool` on `Base.metadata`, `monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())` (`test_rest_answers_cancel.py:44-56`). NOTE the 44-03 relocation: `_get_db` + `_CANCEL_EVENTS` live on `app.api.run_engine`, patch there. `test_rest_revisions.py` patches BOTH `ws_module._get_db` AND `run_commands._get_db` + stubs `engine_mod.get_execution_engine`.
- Register tables explicitly before `create_all` (`test_rest_revisions.py:44-49`: `import app.models.artifact_ref/run_event/workflow/workspace`).
- `_FakeUser(id)` + `TestClient(app)` with `app.dependency_overrides[get_current_user]`.
- Clear module-global registries per test (`ws_module._CANCEL_EVENTS.clear()`).
- 404/409 battery: cross-owner + missing → 404 (assert no seam touched); the driver-seam scenarios (happy/failed/degraded/cancelled) asserted at the driver, NOT via TestClient task-timing (`test_rest_revisions.py:24-26` explicitly avoids the task-timing race).

New `test_rest_resume.py`: model on `test_rest_revisions.py` structure. Cases (RESEARCH
Validation map): `test_resume_cross_owner_404`, `test_resume_missing_404`,
`test_resume_completed_409`, `test_resume_cancelled_409`, `test_resume_already_running_409`,
`test_resume_double_post_second_409`, `test_resume_registers_queue_before_status_flip`,
`test_resume_flips_running_and_stamps_marker`, `test_resume_arm_failure_flips_back_to_failed`.

**Analog B — E2E failed→resume seed (`test_restart_resume.py`):**
- `_seed_workflow_run(session, run_id, *, owner, status, type_, input_, workspace_id)`
  (`:374`) — seed the `workflow_runs` row; for a failed-mid-build E2E pass `status="failed"`
  + seed durable partial per-task artifacts/events under the SAME `workspace_id` (the branch-a
  tests do this so both the classifier read and `_is_resumable_in_flight` resolve).
- `_seed_open_review_gate(session, run_id, owner, workspace_id, gate_key)` (`:948`) — the
  gate-at-failure seed; pair with a `status="failed"` row + a durable `review_gate_ready`
  event and NO resolution → assert resume re-emits `review_gate_ready` (parks at gate, does
  not run the gated model or complete past it). This composes through the 49 classifier
  (`_first_incomplete_step:6957` → `gate_reentry` sentinel `:2187` → consumer `:3038`) with
  ZERO endpoint special-casing.
- Arm-failure honest-state shape: `test_waiting_for_user_rearm_arm_failure_falls_back_to_wr05_fail`
  (`:1029`) — scripted store-arm `RuntimeError`, spy that `resume_run` is NOT driven, assert
  `row.status == "failed"`. The Phase-50 analog: force `resume_run` to raise, assert the
  wrapper's `_flip_back_to_failed` leaves `status="failed"` (never stuck `running`).

New E2E cases appended to `test_restart_resume.py`: `test_failed_run_resumes_skips_completed_tasks`
(cursor evidence + deliverable completes + same run id, no new row) and
`test_failed_run_with_open_gate_resumes_into_gate`.

**COPY:** the SQLite/StaticPool/`_get_db`-patch harness; `_seed_workflow_run`/`_seed_open_review_gate`;
the driver-seam assertion style (avoid TestClient task-timing).
**DEVIATE:** the resume endpoint has NO mint to assert — instead assert "no new WorkflowRun row"
(Pitfall 5) and "same id/parent_run_id" (family coherence).

---

## Shared Patterns

### Ownership default-deny (404 never 403)
**Source:** `create_revision:1632-1642` (inline), `runs.py:1210` `_owner_gate_or_404` (helper form).
**Apply to:** the resume endpoint's Layer-1 gate. `.filter(id==run_id, user_id==current_user.id).first()`
→ None → 404. Keyed on `user_id`, never `owner_id` (D-06). ScopedStore default-deny inside
`resume_run` is Layer 2 (automatic).

### 409 error vocabulary
**Source:** `_reject:1061` + `resolve_gate:197-205` (terminal fence) — `{"error","code","recoverable"}`.
**Apply to:** eligibility (`run_not_resumable`) + overlap (`pipeline_already_running`, CR-01).

### Terminal-status persistence idiom
**Source:** `_persist_terminal_status:1707` + `_drive_launch_to_queue:1470-1491`.
**Apply to:** `_drive_user_resume`'s reconcile + flip-back ONLY (not a full ladder).

### In-process registries
**Source:** `run_engine.py:39-47` (`_PIPELINE_QUEUES`/`_PIPELINE_TASKS`/`_CANCEL_EVENTS`),
`_get_or_create_queue:64`, `_cleanup_pipeline:70`. Already imported into `run_commands:73`.
**Apply to:** overlap mutex + queue/cancel/task registration. Cleanup fires inside
`_drive_resumed_stream`'s finally via the injected `_resume_cleanup` hook — the endpoint adds
no cleanup.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `_reconcile_terminal_status` (durable-tail → status map) | utility | transform | No existing fn reads the run_events terminal tail to derive status; the LOGIC (event→status table) is cloned from `:1470-1491`, but reading it from the durable tail (vs. from a live stream loop) is new. Small, endpoint-local. Model the ScopedStore read on `_stamp_resume_marker:5555` (`store.read_events(run_id, after_seq=0)`). |

Everything else is a clone of an existing idiom.

---

## Anchor Verification

All anchors re-read at file:line on `feat/ui-2` this session (2026-07-19):

| Anchor | File:line | Verified fact |
|---|---|---|
| `_reject` factory | `run_commands.py:1061-1068` | `{"error","code","recoverable"}` + `**extra`; default 400 |
| `resolve_gate` 409 fence | `run_commands.py:197-205` | 409 `pipeline_not_running` shape |
| `cancel_run` owner gate + registry | `run_commands.py:284-305` | `_review_gate_owned_by`→404; `_CANCEL_EVENTS.get` |
| launch mint + spawn + task-register | `run_commands.py:1247-1299` | `_CANCEL_EVENTS[..]=Event()`, `_get_or_create_queue`, `create_task`, `_PIPELINE_TASKS[..]=` |
| launch hook threading | `run_commands.py:1375-1383` | `live_ectx_register=`/`unregister=`/`milestone_sink=` kwargs to `engine.execute` |
| launch terminal-status map | `run_commands.py:1470-1491` | cancelled/degraded/completed/else-failed |
| launch arm-failure except | `run_commands.py:1546-1562` | `except Exception` → `wr.status="failed"` + error + commit |
| `create_revision` owner gate | `run_commands.py:1632-1642` | `.filter(id==, user_id==).first()` → 404 |
| `_persist_terminal_status` | `run_commands.py:1707-1716` | `_get_db`/query/`.status=`/`completed_at`/commit/finally close |
| singleton (launch) | `run_commands.py:1327` | `engine = get_execution_engine()` |
| registries | `run_engine.py:39-47` | `_PIPELINE_QUEUES`/`_PIPELINE_TASKS`/`_CANCEL_EVENTS` |
| `_get_or_create_queue` / `_cleanup_pipeline` | `run_engine.py:64-73` | idempotent queue; registry pop cleanup |
| resume bridge hooks | `run_engine.py:91-118` | `_register_resume_queue`/`_register_resume_task` (+cancel event seed) |
| `_owner_gate_or_404` | `runs.py:1210-1227` | shared `user_id`-keyed → 404 |
| main.py hook-arming | `main.py:133-155` | 6 hooks armed on singleton, then `restore_non_terminal_runs()` |
| restore branch-b ordering | `engine.py:5344-5394` | marker → register_queue → create_task(resume_run) → register_task |
| `_stamp_resume_marker` | `engine.py:5524-5569` | additive `run_resuming` at max(seq)+1; NO status write |
| `resume_run` signature/body | `engine.py:7233-7290` | `(self, run_id)`; READS row only; no status write |
| BUG-015 attach | `run_stream.py:281` | `if workflow_id in _PIPELINE_QUEUES else None` |
| `_seed_workflow_run` | `test_restart_resume.py:374-394` | seed helper (owner/status/type_/workspace_id) |
| arm-failure fail-safe test | `test_restart_resume.py:1029-1065` | scripted raise → `row.status=="failed"` |
| `_seed_open_review_gate` | `test_restart_resume.py:948` | gate-seed helper |
| endpoint-test harness | `test_rest_answers_cancel.py:44-56`, `test_rest_revisions.py:44-49` | SQLite StaticPool + `_get_db` patch on `run_engine`; explicit table imports |

## Metadata

**Analog search scope:** `backend/app/api/{run_commands,run_engine,run_stream,runs}.py`,
`backend/agents/execution_engine/engine.py`, `backend/app/main.py`,
`backend/tests/unit/test_rest_{revisions,answers_cancel}.py`,
`backend/tests/agents/test_restart_resume.py`.
**Pattern extraction date:** 2026-07-19
