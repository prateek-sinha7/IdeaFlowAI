# Phase 49: Gate Resume Across Restart [R4] — Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 6 new/modified surfaces (engine.py · store.py · a shared pendency module · chat_router.py/run_stream.py/run_commands.py re-export · clarify path · test_restart_resume.py)
**Analogs found:** 6 / 6 (every re-arm/re-entry seam has an in-repo shipped precedent to clone — this phase composes, it does not invent)
**Effort:** MAXIMUM — every excerpt below is quoted from current `feat/ui-2` HEAD with verified line numbers; anchor-verification table at the foot.

> All excerpts read live this session. `engine.py` = 7489 lines; targeted non-overlapping reads only. No source edited.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `agents/execution_engine/engine.py` — branch (a) re-arm | kernel / startup-scan | event-driven (durable-classify) | branch (b) auto-resume, engine.py:5009–5059 | exact (sibling branch, same method) |
| `agents/execution_engine/engine.py` — gate-mode re-entry in `_run_agent` | kernel / re-entry | request-response (HITL) | `pending_revision_output` short-circuit, engine.py:2978–3042 | exact (skip-model + re-gate precedent) |
| `agents/execution_engine/engine.py` — open-gate override in `_first_incomplete_step` | kernel / classifier | transform (offset derivation) | the produced-disjunct `continue`, engine.py:6548–6552 | exact (the override slot IS this line) |
| `agents/execution_engine/engine.py` — redo-attempt continuation | kernel / audit-derive | transform (durable count) | `_gate_redo` audit write, engine.py:3901–3916 + read_gate_events, kernel_services.py:1118 | role-match (read side is D-03 approval memory) |
| shared open-gate module (NEW, home = Claude's discretion) | pure kernel-importable module | transform (pure over events) | `derive_open_gate`, chat_router.py:192 (logic) · `agents/capabilities/task_identity.py` (module SHAPE) | exact (logic) + exact (shared-home precedent) |
| `agents/artifact_store/store.py` — public `_resume_events` accessor (IN-02) | store / HITL | request-response | existing `get_review_event`/`get_resume_event`, store.py:53/111 | exact (same registry, add public read) |
| clarify twin re-arm driver | kernel / re-entry (pre-dispatch) | event-driven (replay) | clarify wait, clarify_engine.py:261–277 + branch(b) driver spawn | role-match (asymmetric — see Clarify below) |
| `tests/agents/test_restart_resume.py` — KAN-88 flip + new cases | test | — | KAN-88 anchor :877 + `_ResumeHarness` :188 + `_build_partial_build_fixture` :952 | exact (extend the file) |

---

## Pattern Assignments

### 1. Branch (a) re-arm — analog: the shipped branch (b) driver-spawn

**Analog:** `restore_non_terminal_runs`, engine.py:4937. Branch (a) TODAY (the KAN-88 fail to reverse) and branch (b) (the re-arm's driver template with 46-05 queue/task hooks) live in the SAME method.

**Branch (a) as shipped — the fail path to flip (engine.py:4990–5008):**
```python
if wr.status == "waiting_for_user":
    # KAN-88: after a backend restart the ClarifyEngine coroutine that was
    # `await event.wait()` is gone — re-arming the asyncio.Event does not help
    # because no coroutine will ever await it to resume the pipeline. The correct
    # behaviour is to mark these runs as failed ...
    prior_status = wr.status
    wr.status = "failed"
    wr.error = (
        "Run abandoned: backend restarted while waiting for user clarification "
        "(WR-05-clarify). The clarify gate cannot be resumed after a backend "
        "restart — please start a new run."
    )
    abandoned += 1
```

**Branch (b) — the re-arm DRIVER TEMPLATE to clone (engine.py:5009–5059, post-46-05 shape):**
```python
elif await self._is_resumable_in_flight(wr):
    await self._stamp_resume_marker(wr)          # additive run_resuming event, NOT a status flip
    import asyncio as _asyncio
    # ── WR-02: register the run's LIVE queue at the SAME synchronous site as the
    # driver task, BEFORE create_task (idempotent _get_or_create_queue). ──
    if self._resume_register_queue is not None:
        try:
            self._resume_register_queue(pipeline_run_id)
        except Exception as _q_exc:  # noqa: BLE001
            logger.warning("resume queue registration failed for %s: %s", pipeline_run_id, _q_exc)
    _resume_task = _asyncio.create_task(self.resume_run(pipeline_run_id))
    if self._resume_register_task is not None:
        try:
            self._resume_register_task(pipeline_run_id, _resume_task)
        except Exception as _reg_exc:  # noqa: BLE001
            logger.warning("resume task registration failed for %s: %s", pipeline_run_id, _reg_exc)
    resumed += 1
```

**The gate (engine.py:5088–5120) — `_is_resumable_in_flight`:** compiles `wr.type` then requires ≥1 `read_events` OR `tree()` OR `read_wave_runs` row. Returns `False` offline/no-DB.

**COPY:** the queue-before-task ordering, the best-effort `try/except` on both hooks, `create_task` of a driver, the counter bump. Keep `_stamp_resume_marker` (additive event, never a status change — Pitfall 2).

**DEVIATE (load-bearing):**
- The driver **must NOT be `resume_run`** — the KAN-88 test spies `engine.resume_run` and asserts `n == 0`. Spawn a NEW coroutine (`_rearm_gate_run` or a `resume_run(..., gate_only=True)` variant the test does not spy).
- **Arm-then-classify, fail-safe** (CONTEXT §Specifics): `await self._store.get_review_event(gate_key)` (or `get_resume_event(run)` for clarify) BEFORE leaving `waiting_for_user`; on any exception fall back to the shipped fail path.
- **A1 reconciliation (the anchor contract, HIGH risk):** the KAN-88 test seeds ONLY the `workflow_runs` row (no durable events) → `_is_resumable_in_flight` returns `False`. To keep `status == "waiting_for_user"` with zero test edits, branch (a) must **leave a compilable `waiting_for_user` row untouched (armed, not failed)** and reserve `failed` for the genuinely stateless/uncompilable case. Resolve against the test at plan time — the test is the contract.
- Do NOT `wr.status = "failed"` and do NOT emit `pipeline_start`/`run_resuming` (both are in `_QUESTIONNAIRE_RESOLUTIONS`, chat_router.py:75 — they'd close a clarify gate; Pitfall 2).

---

### 2. Skip-the-model gate re-entry — analog: `pending_revision_output` (THE precedent to clone, quoted in full)

**Analog:** engine.py:2978–3042, the top of `_run_agent`'s `while True:` loop (loop opens :2969; locals reset :2965–2968). This is the WORKING precedent for re-opening a gate with persisted output and ZERO model call. Clone it as a sibling sentinel (`ectx.gate_reentry`).

**The full short-circuit to mirror (engine.py:2978–3042):**
```python
pending_revision_output = getattr(ectx, "spec_revision_pending_output", None)
if pending_revision_output is not None:
    ectx.spec_revision_pending_output = None  # consume-once
    output = pending_revision_output
    if results and results[-1].get("agent_id") == spec.id:
        results[-1] = {**results[-1], "output": output}
    # Re-open the gate directly — skip the model call entirely.
    if self._should_gate(spec, ectx):
        _ek = self._artifact_kind_for(spec)
        async for gate_event in self._run_review_gate(
            pipeline_run_id=pipeline_run_id,
            agent_id=spec.id,
            agent_name=spec.name,
            output=output,
            redoable=True,
            update_specs_eligible=_ek in self._UPDATE_SPECS_ELIGIBLE_KINDS,
            artifact_kind=_ek,
            cancel_event=cancel_event,
        ):
            if gate_event.get("type") == "_gate_rejected":
                current = self._state_machine.get_state(pipeline_run_id)
                if current not in ("cancelled", "failed"):
                    self._state_machine.transition(pipeline_run_id, "cancelled")
                yield {"type": "pipeline_cancelled", "data": {
                    "pipeline_run_id": pipeline_run_id,
                    "reason": f"User rejected output from {spec.name}",
                }}
                return
            elif gate_event.get("type") == "_gate_edited":
                edited = gate_event.get("edited_content", output)
                if edited:
                    _ek = self._artifact_kind_for(spec)
                    _prior_ref = self._latest_typed_ref_id(ectx, spec.id, _ek)  # RESUME-15 lineage
                    await self._dual_write_artifact(
                        ectx, producer_agent=spec.id, producer_step=spec.id,
                        content=edited, kind=_ek,
                        location=f"artifact_refs/{spec.id}", derived_from=_prior_ref,
                    )
                if results and results[-1].get("agent_id") == spec.id:
                    results[-1] = {**results[-1], "output": edited}
            elif gate_event.get("type") == "_gate_redo":
                redo_directive = gate_event.get("instructions") or ""
                redo_attempt += 1
                break
            elif gate_event.get("type") == "_gate_update_specs":
                ectx.spec_revision_pending_output = gate_event.get("analysis_report") or ""
                spec_revision_attempt += 1
                break
            else:
                yield gate_event
        else:
            return
        continue
    return
```

**COPY exactly:** the `getattr(ectx, <sentinel>, None)` guard, the consume-once clear, the `results[-1]` update, the `if self._should_gate(...)` → `_run_review_gate(...)` call with the SAME kwargs, the full five-branch consumer, `else: return`, and the trailing `continue`. This IS the five-action consumer — approve/reject/edit/redo/update_specs all fall out for free.

**DEVIATE:**
- New sentinel: `ectx.gate_reentry = {"agent_id": k, "output": <max-version>, "artifact_kind": kind, "gate_key": key}`, set in the `_is_resume` block (~engine.py:2084–2149) AFTER `_hydrate_artifacts_from_store`; seed `output` via `_latest_typed_content(ectx, agent_id)` (engine.py:5631, `max(version)`). Also seed `ectx.last_streamed = output` (WR-02 — the gate must review real output).
- Guard the sentinel on `spec.id` match so it fires ONLY at the gated step k (consume-once, dormant on goldens — Pitfall 3).
- Seed `redo_attempt`/`spec_revision_attempt` from durable evidence here (§4) BEFORE the consumer, or a post-restart redo collides on `:redo{N}`.

---

### 3. Open-gate classifier override — analog: the produced-disjunct it must beat

**Analog:** `_first_incomplete_step`, engine.py:6400. The events are ALREADY read at :6431 (`rows = await store.read_events(ectx.run_id, 0)`) — reuse them, no extra round-trip.

**The exact line to override (engine.py:6548–6552):**
```python
# Non-wave step: complete iff it produced its typed artifact OR a terminal
# step event is recorded. Neither ⇒ this is the first incomplete step.
if agent_id in produced_agents or agent_id in completed_step_events:
    continue
return i
```
`produced_agents` is built from durable `artifact_refs` (`tree_rows`, :6468–6471). A produced-but-ungated `single_shot` step hits `continue` here → the offset lands PAST the unresolved gate (the silent-skip bug). **CONFIRMED at HEAD.**

**COPY / INSERT (before the :6548 non-wave check, or in `_compute_resume_offset` before return):**
```python
open_kind, open_gate_key = derive_open_gate(rows)   # rows already read at :6431
if open_kind == "review" and open_gate_key:
    _target = open_gate_key.split(":", 1)[1]         # gate_key = f"{run}:{agent_id}" (engine.py:4802)
    for j in range(len(ordered_agents)):
        if getattr(ordered_agents[j], "id", None) == _target:
            return j                                  # re-enter step j in GATE MODE
```

**DEVIATE:** generic keying only — parse `agent_id` out of `gate_key`, match `ordered_agents[j].id`. Zero name literals (INV-1). No-op when `derive_open_gate` returns `(None, None)` — proven dormant against every existing branch-(b) test that seeds no `review_gate_ready` (RESEARCH §KAN-88). Wave/task_loop branches above are untouched.

---

### 4. Redo continuation — analog: the `_gate_redo` audit write + the D-03 read

**Analog (write side):** the inline `_gate_redo` consumer, engine.py:3881–3917.

**The audit write to count (engine.py:3901–3916):**
```python
# T7 (B8): best-effort, content-free redo audit row in the INLINE consumer
# (NOT _run_review_gate, which has no ectx). Dormant on goldens. Never breaks the run.
_runner = getattr(ectx, "runner", None)
if _runner is not None and hasattr(_runner, "record_gate_event"):
    try:
        await _runner.record_gate_event(
            spec.id, "human", "redo",
            {"has_instructions": bool(redo_directive)},
        )
    except Exception:  # noqa: BLE001 — audit never aborts a run
        logger.debug("redo audit row failed for agent %s (ignored)", spec.id, exc_info=True)
redo_attempt += 1  # next re-run gets a FRESH checkpoint thread (:redo{N})
```

**The thread-id collision class to avoid (engine.py:3185–3198):**
```python
thread_id = f"{pipeline_run_id}:{spec.id}:{task_num}" if task_num else f"{pipeline_run_id}:{spec.id}"
...
if redo_attempt:
    thread_id = f"{thread_id}:redo{redo_attempt}"   # collision == the P23 checkpointer-replay bug
```

**The read side (kernel_services.py:1118, `read_gate_events`):** default-deny, owner-scoped, best-effort `[]` on no-store. Rows carry `step, gate, outcome` (gate_events.py:35–37 — `step`, `gate="human"`, `outcome="redo"`).

**COPY:** count via `ctx.runner.read_gate_events(run_id)` filtered on `r.step == spec.id and r.gate == "human" and r.outcome == "redo"`.

**DEVIATE / decision (A2):** seed **fail-safe HIGH** — `redo_attempt = max(gate_events_redo_count, artifact_version_count − 1)` so the next `:redo{N}` is strictly greater than any pre-restart id (over-estimate is safe; under-estimate collides). `spec_revision_attempt` has NO symmetric audit row today (`_gate_update_specs`, engine.py:3918–3988, writes none) — either add a 1-line `record_gate_event(spec.id,"human","update_specs",…)` (golden-dormant) or count spec-kind versions. Flag for planner (A2).

---

### 5. Shared open-gate derivation — analog: `derive_open_gate` (logic) + `task_identity.py` (module shape)

**Analog A — the canonical logic (chat_router.py:192, the superset — handles clarify AND review):**
```python
def derive_open_gate(events: list) -> tuple[str | None, str | None]:
    ...
    ordered = sorted(events, key=_seq)
    open_questionnaire = False
    open_review_key: str | None = None
    for r in ordered:
        t = _type(r)
        if t == _QUESTIONNAIRE_READY:  open_questionnaire = True
        elif t == _REVIEW_GATE_READY:  open_review_key = _payload(r).get("gate_key")
        if t in _QUESTIONNAIRE_RESOLUTIONS:  open_questionnaire = False
        if t in _REVIEW_RESOLUTIONS:         open_review_key = None
    if open_review_key is not None:  return "review", open_review_key
    if open_questionnaire:           return "questionnaire", None
    return None, None
```
Reads rows via getattr/get (ORM OR dict) — lifts cleanly to a pure module. Resolution frozensets: `_QUESTIONNAIRE_RESOLUTIONS` (chat_router.py:72), `_REVIEW_RESOLUTIONS` (chat_router.py:84). **VERIFIED byte-identical** to `run_stream._GATE_RESOLUTION_TYPES` (run_stream.py:68). The three near-duplicates to unify: `derive_open_gate` (superset) · `_dangling_review_gate` (run_stream.py:119, review-only ROW) · `_gate_is_pending` (run_commands.py:134, in-memory peek — IN-02).

**Analog B — the kernel-pure shared-home SHAPE (Phase 48, `agents/capabilities/task_identity.py:1–34`):** "THE single home" pure module, stdlib-only, explicit scope guard "MUST NOT import `app.*`, `agents.execution_engine`, or `agents.workflows` control flow … the kernel/strategies import THIS module, never the reverse." Copy this docstring discipline + import-guard comment for the new module.

**COPY:** the `derive_open_gate` body verbatim into the new pure module + the two resolution frozensets. Have `chat_router.derive_open_gate`, `run_stream._dangling_review_gate`, and the kernel all import IT.

**DEVIATE / home decision (A3, Pitfall 7 — import direction):** kernel must NOT import `app.*` (main.py:138); app MAY import kernel/capabilities. Two candidate homes:
- `agents/capabilities/task_identity.py`'s tier — a NEW `agents/capabilities/gate_pendency.py` (pure, kernel- AND app-importable, matches the 48 precedent exactly). **Recommended** — import-clean in both directions.
- `agents/execution_engine/gate_pendency.py` — kernel-side; verify app→execution_engine import does not break `lint-imports` (4/0).
Pick the one that keeps `lint-imports` at 4 kept / 0 broken.

---

### 6. Store public accessor (IN-02) — analog: existing HITL half

**Analog:** `ArtifactStore`, store.py:40–154. The private peek to encapsulate is at `run_commands.py:145`:
```python
event = store._resume_events.get(f"review:{gate_key}")
return event is not None and not event.is_set()
```
The store's own key convention (store.py:113): `key = f"review:{gate_key}"`.

**COPY / ADD a public method on `ArtifactStore` (mirror `get_review_event` at store.py:111):**
```python
def review_event_pending(self, gate_key: str) -> bool:
    event = self._resume_events.get(f"review:{gate_key}")
    return event is not None and not event.is_set()
```
Then `run_commands._gate_is_pending` (and callers at :209 etc.) call the accessor — the `store._resume_events` literal disappears from the app layer. Branch (a) arms via the existing `get_review_event(gate_key)` (store.py:111) / `get_resume_event(run)` (store.py:53); answers/gate ingress is byte-unchanged (`set_review_response` :118, `set_questionnaire_responses` :62).

---

### 7. Clarify twin — analog: the clarify wait + branch(b) driver (ASYMMETRIC)

**Analog:** `clarify_engine.py:261–277` (the wait):
```python
event = await self._store.get_resume_event(pipeline_run_id)
event.clear()
await websocket_send_fn({"type": "questionnaire_ready", "data": {
    "pipeline_run_id": pipeline_run_id, "questions": questions,
    "round": round_num, "timestamp": _now_iso()}})
await event.wait()
responses = await self._store.get_questionnaire_responses(pipeline_run_id)
```
Durable resolver: `questionnaire_complete` emitted after answers merge (clarify_engine.py:295). Answers ride unchanged `POST /answers` → `set_questionnaire_responses` (store.py:62) sets the SAME `_resume_events[run]` event.

**The asymmetry (LOAD-BEARING, engine.py:1695/1708):**
```python
_resuming = _resume_from > 0
...
skip_planner = compiled.planner == "skip" or _resuming
```
A resumed run (`_resume_from > 0`) SKIPS planner AND clarify. A clarify-parked run has NO produced steps → `_first_incomplete_step` = 0 → `_resuming = False` → a naive `resume_run` would RE-RUN the planner + LLM-regenerate questions. **So clarify CANNOT route through the review offset override.**

**COPY:** the branch(b) driver-spawn (queue-before-task, best-effort hooks) — but as a DISTINCT clarify driver.
**DEVIATE:** replay the durable `questionnaire_ready` payload's `questions`+`round` (NO `_generate_questions` LLM call), re-enter `get_resume_event(run)` → `clear` → re-emit `questionnaire_ready` (existing type, engine-counter seq) → `await event.wait()`; on answers proceed into the NORMAL dispatch from planning (offset 0, replay mode). Seam decision (A5): thin replay wrapper vs re-entering `ClarifyEngine.run` with reconstructed merged context — bias to reuse `ClarifyEngine.run` (INV-12), decide in 49-03. Status stays `waiting_for_user` throughout (KAN-88 assertion).

---

## Shared Patterns

### Driver lifecycle / 46-05 hooks
**Source:** engine.py:5032–5058 (spawn) + main.py:141–155 (wiring) + `resume_run` finally (engine.py:6985–7013, WR-01 leak precedent).
**Apply to:** BOTH re-arm drivers (review + clarify). Register queue BEFORE emit; thread `_resume_register_queue/_register_resume_task/_cleanup`, `_resume_live_ectx_register/_unregister`, `_resume_milestone_sink`; replicate the `finally` (queue None sentinel → cleanup → live-ectx unregister) or a parked run leaks registry entries. `cancel_event=None` on the parked wait (plain `await event.wait()`, engine.py:4869 — matches the deferred T8/F7).

### Goldens dormancy (INV-3)
**Source:** `_VOLATILE_STRIP_KEYS` (redoable/update_specs_eligible/artifact_kind already stripped, engine.py:4790/4800); `_run_review_gate` re-emit is an EXISTING type via the existing emit boundary with engine-counter seq (0024/DEF-43-03-1).
**Apply to:** every new emit/sentinel. New machinery must be `getattr`-guarded so the 5 characterization runs (never park at a gate) are byte/event-identical. Goldens 10/10 is the proof.

### Name-free keying (INV-1 / SC-001)
**Source:** `_artifact_kind_for(spec)` structural derivation (engine.py:2990); `gate_key = f"{run}:{agent_id}"` (engine.py:4802).
**Apply to:** the classifier override (parse gate_key), the pendency derivation (generic event types). Banned-pattern gate forbids `pipeline_type ==` in `agents/execution_engine/` — stays 11/0.

---

## Test Idioms

**Analog file:** `tests/agents/test_restart_resume.py`. Extend it (do NOT create a new file) — reuse `_ResumeHarness` (:188, shared in-memory session across simulated restart; patches compile/registry/factory/ScopedStore + SessionLocal), `_seed_workflow_run`, and `_build_partial_build_fixture` (:952, `pre_store.write_ref` seeds).

**KAN-88 anchor IN FULL (test_restart_resume.py:877–899) — the A1 contract:**
```python
async def test_waiting_for_user_run_is_rearmed_not_driven():
    session, db_engine = _make_session()
    run_id = f"wf-{uuid.uuid4().hex[:8]}"
    _seed_workflow_run(session, run_id, owner="wf-user", status="waiting_for_user")
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        resume_called = {"n": 0}
        async def _spy_resume(rid):
            resume_called["n"] += 1
        engine.resume_run = _spy_resume            # spy — the re-arm driver must NOT be resume_run
        await engine.restore_non_terminal_runs()
    assert resume_called["n"] == 0, "waiting_for_user must NOT be auto-resumed (branch a)"
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert row.status == "waiting_for_user", "waiting_for_user status must be unchanged"
```
Seeds ONLY the `workflow_runs` row (no durable events). Asserts (1) `resume_run` not called; (2) status stays `waiting_for_user`. Two design constraints fall out: the driver ≠ `resume_run`; a compilable `waiting_for_user` row is left armed-not-failed even with no durable rows (A1). **Flips RED→GREEN with zero test edits.**

**Adjacent idioms:**
- `test_stateless_run_keeps_wr05_failed_path` (:908) — `status="generating"`, no durable rows → branch (c) fail. Asserts `failed` + `"WR-05"` in error. UNTOUCHED — keep green (proves branch-(a) change is scoped to `waiting_for_user`).
- **New cases (Wave 0 gaps):** five-actions + redo-numbering (49-02) seed a durable `review_gate_ready` + ref via `_build_partial_build_fixture`/`write_ref`; assert gate re-opens, each action works, next thread == `:redo{N+prior}`. Clarify twin (49-03) seeds `questionnaire_ready` via `pre_store.append_event`; assert re-emit + `waiting_for_user` + POST /answers proceeds.

**Baseline floor (offline, python3.11, `cd backend/`):** restart_resume 1F/24P → must reach **25/0** (KAN-88 flips, no new red); `redo_gate_safety` **held 3F/4P** (pre-existing `_fake_gate()` missing `update_specs_eligible` kwarg, KAN-101 drift — do NOT fix, held by delta); `declared_gate_streaming` **3F** (env-red: `sqlite3.IntegrityError FOREIGN KEY` on `run_events` persist, Postgres-gated — record baseline, confirm unchanged, A4); goldens 10/10; banned_patterns 11/0; lint-imports 4/0; sse_stream 17/0 (incl. D-14g `TestGateRearm`); mechanical_router 28/0.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | Every surface has a shipped in-repo precedent. This phase composes existing seams (branch b, `pending_revision_output`, `derive_open_gate`, `task_identity` module shape, the clarify wait); it introduces NO net-new pattern. |

---

## Anchor Verification (research claim vs read HEAD)

| Symbol | Research line | Read HEAD | Status |
|--------|--------------|-----------|--------|
| `restore_non_terminal_runs` | 4937 | 4937 | ✓ |
| branch (a) fail path | 4990–5008 | 4990–5008 | ✓ |
| branch (b) driver spawn | 5009–5059 | 5009–5059 | ✓ |
| `_is_resumable_in_flight` | 5088 | 5088 | ✓ |
| `pending_revision_output` short-circuit | 2978–3042 | 2978–3042 | ✓ |
| `_run_agent` while-loop + locals | 2969 / 2965–2968 | 2969 / 2965–2968 | ✓ |
| `_first_incomplete_step` | 6400 | 6400 | ✓ |
| produced-disjunct `continue` | 6550 | 6548–6552 | ✓ |
| events read reused | 6431 | 6431 | ✓ |
| `_gate_redo` audit write | 3905–3910 | 3901–3916 (`record_gate_event` :3907) | ✓ (±2, same block) |
| `_gate_update_specs` (no audit) | 3918–3988 | 3918–3988 | ✓ |
| redo thread-id suffix | 3185–3198 | 3185–3198 | ✓ |
| `_run_review_gate` | 4764 | 4764 | ✓ |
| gate_key format | 4802 | 4802 | ✓ |
| plain `event.wait()` (cancel None) | 4866–4869 | 4866–4869 | ✓ |
| transition → waiting_for_user | 4819 | 4819 | ✓ |
| `derive_open_gate` | 192 | 192 | ✓ |
| `_QUESTIONNAIRE_RESOLUTIONS` / `_REVIEW_RESOLUTIONS` | 72 / 84 | 72 / 84 | ✓ |
| `_dangling_review_gate` / `_GATE_RESOLUTION_TYPES` | 119 / 68 | 119 / 68 | ✓ |
| D-14g re-emit | 188–191 | 188–191 | ✓ |
| `_gate_is_pending` private peek | 134 | 134 (peek :145) | ✓ |
| store HITL half | 42/53/111/118 | 42/53/111/118 | ✓ |
| clarify wait / `questionnaire_complete` | 261–277 / 295 | 261–277 / 295 | ✓ |
| planner/clarify skip | 1695 / 1708 | 1695 / 1708 | ✓ |
| gate_events cols | 26+ | step/gate/outcome :35–37 | ✓ |
| `read_gate_events` | 1118 | 1118 | ✓ |
| KAN-88 anchor test | 877–899 | 877–899 | ✓ |
| `_ResumeHarness` | 188 | 188 | ✓ |
| task_identity.py precedent | (48) | `agents/capabilities/task_identity.py:1–34` | ✓ (note: lives in `capabilities/`, NOT `execution_engine/` — informs the shared-home choice, §5 A3) |

**Flag drift:** none. Every research anchor confirmed within ±2 lines at HEAD. The one nuance: `task_identity.py` lives under `agents/capabilities/` (the import-clean pure tier), which is the better home candidate for the shared pendency module than `agents/execution_engine/` — see §5 A3.

## Metadata

**Analog search scope:** `backend/agents/execution_engine/` (engine.py, clarify_engine.py, kernel_services.py) · `backend/agents/artifact_store/store.py` · `backend/agents/capabilities/task_identity.py` · `backend/app/api/` (chat_router.py, run_stream.py, run_commands.py) · `backend/app/models/gate_events.py` · `backend/tests/agents/test_restart_resume.py`
**Files scanned:** 10 (all read at file:line, current `feat/ui-2` HEAD)
**Pattern extraction date:** 2026-07-19
