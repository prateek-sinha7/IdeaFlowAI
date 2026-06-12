# Phase 14: run_revision real revision loop (F2 end-to-end) - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 8 (all modifications — zero new files)
**Analogs found:** 8 / 8 (every file's analog already exists, mostly inside the same file)

All paths relative to repo root `flowin/`. Line numbers verified on branch `feature/003-workflow-engine-decoupling` (2026-06-12).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/agents/execution_engine/engine.py` (`_handle_revision`, 3656–3943) | engine handler (kernel) | streaming dispatch (async-gen forward) | `app/api/websocket.py` `_run_pipeline_to_queue` consume-loop (1500–1588) + `execute()` itself (517–533) | exact |
| `backend/agents/workflows/ppt_revision/workflow.yaml` | config (manifest) | declarative | own file — one key flips; planner-skip semantics at engine.py:1198–1205 | exact |
| `backend/agents/workflows/od_ppt_revision/workflow.yaml` | config (manifest) | declarative | same | exact |
| `backend/app/api/websocket.py` (run_revision branch, 865–978) | WS route handler | event-driven (queue + drainer) | run_pipeline path in same file: queue (1498), bg task (1500–1696), drainer (1698–1739), terminal-status persist (1593–1650) | exact |
| `backend/tests/unit/test_revision_intelligence.py` | test (rewrite) | scripted-model dispatch | `tests/agents/_scripted_model.py` `_drive` wiring (435–545); keep its own guard tests | exact |
| `backend/tests/unit/test_run_revision_fe_contract.py` | test (rewrite) | scripted-model dispatch | same harness | exact |
| `backend/tests/agents/test_manifest_parity.py` | test (update) | parametrized assert | own `test_planner_run_everywhere` (70–79) | exact |
| `backend/tests/agents/_scripted_model.py` | test fixture (additive entry) | scripted turns | own `_scripts_for` od-ppt-validator branch (322–342) | exact |

## Pattern Assignments

### `backend/agents/execution_engine/engine.py` — `_handle_revision` (kernel, streaming dispatch)

**Analog A — the dispatch target.** `execute()` signature (engine.py:517–533):
```python
async def execute(
    self,
    agents: list,
    user_message: str,
    pipeline_run_id: str,
    pipeline_type: str = "custom",
    cancel_event: asyncio.Event | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    attached_skills: list[dict] | None = None,
    attached_hooks: list[dict] | None = None,
    model_id: str | None = None,
    od_context: dict | None = None,
    gate_agent_ids: list[str] | None = None,
    parent_run_id: str | None = None,
    model_overrides: dict[str, str] | None = None,
) -> AsyncGenerator[dict, None]:
```
`execute()` is the single emit/stamp/persist chokepoint — it arms its own `_RunEventSink` + `itertools.count(1)` (555–556), mints the run workspace, calls `set_run_scope`, records run_capabilities. Therefore **everything in `_handle_revision` that duplicates this is deleted** (INV-12): `_rev_sink`/`_rev_counter`/`_stamped_send` (3724–3740), the CR-01 scope writeback + sink-arm block (3798–3823), the fake `pipeline_start` (3876–3885) and fake `pipeline_complete` (3931–3943).

**Analog B — forward-and-capture consume loop.** Copy the shape of `websocket.py:1507–1587` (`async for update in engine.execute(...)` with per-type capture). Reduced form for `_handle_revision`:
```python
# pattern source: websocket.py:1507, 1578-1587
final_output: str | None = None
terminal_failed = False
async for event in self.execute(
    agents=agents,                          # get_pipeline_agents(revision_pipeline_type)
    user_message=revision_context,
    pipeline_run_id=pipeline_run_id,
    pipeline_type=revision_pipeline_type,   # WR-06 alias, data-derived
    user_id=owner_id,
    model_id=model_id,
    od_context=None,                        # settled wrinkle
    gate_agent_ids=[],
    parent_run_id=parent_run_id,
):
    if event.get("type") == "pipeline_complete":
        final_output = event.get("data", {}).get("final_output")
    elif event.get("type") == "pipeline_failed":
        terminal_failed = True
    await websocket_send_fn(event)          # the RAW sender — events already stamped
```

**Keep unchanged** (test-pinned, security-ordered): empty-instruction guard (3683–3684), falsy-owner guard (3692–3695), `ScopedStore(owner_id)` + `await store.assert_owns(parent_run_id)` FIRST (3706, 3745), FR-014 three-link chain with `[Error:` filter (3765–3790), three-section `revision_context` composer + planning-context prefix (3840–3858), WR-06 alias transform verbatim (3870–3872):
```python
revision_pipeline_type = (
    f"{target_artifact_type.removesuffix('_output')}_revision"
)
```

**Agent resolution pattern** — same import the kernel already uses (engine.py:1155): `from agents.registry import get_pipeline_agents`; pass `get_pipeline_agents(revision_pipeline_type)` **exactly** — `_execute_impl` raises RuntimeError on plan↔registry membership mismatch (engine.py:1157–1170). Pre-dispatch guard: empty list → ValueError naming the unsupported target (Pitfall 7).

**Post-dispatch lineage write** — repoint the stub's existing block (engine.py:3898–3914), guarded `if final_output and not terminal_failed:`:
```python
_rev_graph = ArtifactGraph()
_rev_ref = _rev_graph.write_ref(
    run_id=pipeline_run_id,
    owner_id=owner_id,
    workspace_id=original.workspace_id,
    kind=target_artifact_type,            # exact kind — FR-014 chain link 1
    producer_step="revision",
    producer_agent=agents[-1].id,         # derive from resolved specs (IN-05 spirit, no literal)
    task_id=None,
    content=final_output,                 # ← was revision_context (the stub)
    location=f"artifact_refs/{target_artifact_type}",
    derived_from=original.id,
    visibility="workspace",
)
new_artifact_id = await store.write_ref(_rev_ref)
```
On write failure keep the existing `state_restoration_failed` emit (3919–3929) but do not fail the run. For producer_agent derivation, the canonical IN-05 pattern is engine.py:1822–1828 (latest typed ref with byte-identical content, fallback last agent) — `agents[-1].id` is the acceptable simplification since revision pipelines are 1–2 single_shot steps.

---

### `backend/agents/workflows/{ppt_revision,od_ppt_revision}/workflow.yaml` (config, declarative)

One-key flip; everything else byte-unchanged (clarify block is a required key — parity trap #2 test reads defaults and keeps passing):
```yaml
# current (both files):
planner: run
# becomes:
planner: skip
```
Engine semantics of the flip (engine.py:1198–1205): `skip_planner = compiled.planner == "skip" or _resuming` → `planning_context = self._default_planning_context(user_message)`, `gate_verdict = "PROCEED"`, no planner events, clarify never reached. Note `ppt_revision` has TWO steps (`ppt-revision-agent`, `ppt-revision-assembler`); `od_ppt_revision` has one (`od-ppt-revision-agent`) — relevant for the WS row's `agent_count` (currently hardcoded 1 at websocket.py:928).

---

### `backend/app/api/websocket.py` — run_revision branch (WS handler, event-driven)

**Keep:** frame validation (871–884), WorkflowRun row creation with owner stamp + WR-06 type alias (892–929), `_send_revision_event` raw sender (937–941).

**Replace:** the inline `await _rev_engine._handle_revision(...)` (946–954) and the unconditional `status = "completed"` flip (956–964).

**Analog — background task + queue + drainer** from the run_pipeline path in the same file:
```python
# websocket.py:1498, 1694-1696 — queue + bg task
event_queue = _get_or_create_queue(pipeline_run_id)   # helper at line 42
async def _run_pipeline_to_queue() -> None:
    try:
        ... dispatch, push events: await event_queue.put({"type": ..., "data": ...})
        ... persist terminal status INSIDE the task (no race)
    finally:
        await event_queue.put(None)        # sentinel
        _cleanup_pipeline(pipeline_run_id)
pipeline_bg_task = asyncio.create_task(_run_pipeline_to_queue())
_PIPELINE_TASKS[pipeline_run_id] = pipeline_bg_task
```
Drainer pattern (1703–1739): `asyncio.wait_for(event_queue.get(), timeout=10.0)` → heartbeat on timeout → `None` sentinel breaks → wrap each event as `{"type", "chunk": None, "section": _rev_target_type, "data"}` (preserving `_send_revision_event`'s section stamping).

**Terminal-status fidelity analog** (websocket.py:1610–1621) — status follows the authoritative terminal payload, not "any error happened":
```python
if degraded_failed_agents is not None:
    wr.status = "degraded"
elif pipeline_complete_seen:
    wr.status = "completed"
else:
    wr.status = "failed" if any_agent_errored else "completed"
```
For revisions the minimum contract is: `pipeline_failed` (or no `pipeline_complete`) → `"failed"`, never `"completed"` — the FE revision-of-revision lookup matches `status === "completed"` (Pitfall 4).

---

### `backend/tests/unit/test_revision_intelligence.py` and `test_run_revision_fe_contract.py` (tests, rewrite)

**Analog — `tests/agents/_scripted_model.py` `_drive` wiring (435–480):**
```python
# _scripted_model.py:441 — RunSandbox reads settings at __init__, patch at runtime
_settings.RUNS_ROOT = _RUNS_ROOT
# _scripted_model.py:471-480 — patch BOTH names (engine imported create_runner by name)
_orig_create_runner = factory_mod.create_runner
def _patched_create_runner(agent_id, ctx, **kw):
    ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
    return _orig_create_runner(agent_id, ctx, **kw)
factory_mod.create_runner = _patched_create_runner
engine_mod.create_runner = _patched_create_runner
# restore in finally (542-544)
```
Differences vs `_drive`: `planner: skip` means no planner/clarify patching needed; unique `pipeline_run_id` per test (state-machine singleton rejects reuse — StateMachineError).

**Keep as-is** (guards unchanged by this phase): empty/whitespace-instruction ValueError, falsy-owner ValueError, FR-014 ValueError byte-unchanged, `test_cross_owner_revision_denied` (PermissionError BEFORE any event).

**New assertions** (real-dispatch contract): `agent_start`/`agent_complete` for `od-ppt-revision-agent` observed; `final_output` == the scripted revised deck (unwrapped — strategy `ppt` runs `unwrap_artifact(sanitize_carousel_deck_html(last_streamed))`, ppt.py:53–55); exact-kind ref persisted with `derived_from == original.id` and `content == final_output`; `pipeline_complete.pipeline_type == "od_ppt_revision"`. Do NOT assert on instruction text appearing in output.

---

### `backend/tests/agents/test_manifest_parity.py` (test, update)

Analog is its own trap (lines 70–79). Update pattern — carve out the two run_revision-dispatched ids:
```python
# current:
def test_planner_run_everywhere(workflow_id: str) -> None:
    plan = _compile(workflow_id)
    assert plan.planner == "run", (...)
# becomes: ppt_revision / od_ppt_revision expect "skip" (Phase 14); all others "run".
# The test's own docstring anticipates the revisit. Do NOT touch
# test_prototype_planner_runs (line 62) or trap #2 (clarify defaults, 87+).
```

### `backend/tests/agents/_scripted_model.py` (fixture, additive)

Analog — the `od-ppt-validator` branch of `_scripts_for` (322–342): last agent's streamed text wrapped in a single `<artifact>` tag, plain markup that the carousel sanitizer passes through, fixed `usage` tuple. Add a dedicated `od-ppt-revision-agent` (and optionally `ppt-revision-agent`/`ppt-revision-assembler`) branch emitting an `<artifact>`-wrapped REVISED deck (distinct bytes from the parent deck) for strong unwrap/lineage assertions:
```python
if agent_id == "od-ppt-revision-agent":
    deck = ("<!doctype html><html>...<section class='deck-slide'>Revised Title</section>...</html>")
    return [_ScriptedTurn(texts=[f"Revised per instruction.\n<artifact>{deck}</artifact>"], usage=(22, 14))]
```

## Shared Patterns

### SC-001 / banned-pattern compliance
**Source:** engine.py:3870–3872 (suffix transform), 1155 (registry import), 1822–1828 (no-literal producer derivation)
**Apply to:** all engine edits. Never `if revision_pipeline_type == "od_ppt_revision"` — `tests/agents/test_banned_patterns.py` hard-fails `if pipeline_type ==` / `spec.id ==` under `agents/execution_engine/`. All strings derived: alias transform → `get_pipeline_agents(<derived>)` → `compile_for_run(<derived>)`.

### Single stamping chokepoint (PERSIST-03 / SAFE-03)
**Source:** engine.py:534–556 docstring + sink arm. Events yielded by `execute()` arrive pre-stamped (`seq`, `event_id`) and pre-persisted. Any consumer (the new `_handle_revision` forward loop, the WS drainer) must forward verbatim — never mutate `seq`/`event_id`, never persist run_events again.

### Owner-scoped access (AUTHZ / T-5-SEED)
**Source:** engine.py:3706 + 3745. `ScopedStore(owner_id)` then `assert_owns(parent_run_id)` BEFORE any cross-run read and before dispatch. Cross-run reads resolve via owner + `visibility IN ('workspace','public')` (authz.py:104–117) — the revision run getting its own fresh workspace (minted by `execute()`) is fine.

### Degrade-don't-fail persistence
**Source:** engine.py:3811–3822 (SQLAlchemyError-only degrade) and the best-effort run_events persist in `execute()`. Apply to the post-dispatch lineage write: emit `state_restoration_failed` on failure, log, do not fail the run.

## No Analog Found

None — every file modified has an exact in-repo analog (this is a wiring phase; Phase 13 + WR-06 built all seams).

## Metadata

**Analog search scope:** `backend/agents/execution_engine/`, `backend/app/api/`, `backend/agents/workflows/`, `backend/tests/{unit,agents}/`
**Files scanned:** 7 read in targeted ranges (engine.py x4 ranges, websocket.py x3 ranges, both manifests, test_manifest_parity.py, _scripted_model.py)
**Pattern extraction date:** 2026-06-12
