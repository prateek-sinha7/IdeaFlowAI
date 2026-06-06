# Phase 0B — ExecutionContext + ownership (detailed plan)

> **Goal:** lift **every per-run mutable attribute** off the `ExecutionEngine` singleton into a
> per-run `ExecutionContext` (closing the latent multi-user corruption bug, INV-2 / L14), and add the
> **explicit parent-run ownership check** on revision seeding (INV-8 / L16). **Zero behavior change** —
> the 0A snapshots must stay byte-identical and at semantic event parity.
>
> **Accept (003 §25):** snapshots green (deliverable byte-identical); the kernel singleton has **no
> per-run attributes** (only `_resolver`/`_store`/`_state_machine` remain on `self`, NFR-001);
> cross-owner parent seed is rejected by a new denial test.

Parent: [Phase 0 README](README.md) · Prev: [0A](phase-0a-safety-net.md) · Next: [0C](phase-0c-token-trim.md)

---

## B1. The problem (verified)

`get_execution_engine()` returns a **module-level singleton** (`engine.py:2638-2643`) shared across all concurrent runs. `__init__` (`engine.py:403-406`) sets only three immutable deps. But `execute()` stashes **11 per-run-mutable attributes on `self`**, mutated mid-run — so two concurrent runs corrupt each other. The three sharpest hazards:

- `self._completed_tasks.append(...)` in `_run_agent` (`engine.py:1267`) — the list grows across the whole run and drives the **monotonic** `task_progress.completed_count`; concurrent runs interleave appends → wrong counts in both.
- `self._current_task_block = ...` in `_run_build_task_loop` (`engine.py:1536`), read in `_build_context_message` (`engine.py:2480`) — concurrent runs inject the wrong task block into each other's build prompts.
- `self._revision_*` set in `execute()` (`engine.py:532, 548-550, 554, 568, 624, 639`) — a concurrent non-revision run resets these to defaults mid-flight; a concurrent revision overwrites them.

## B2. The `self._*` inventory (what moves, what stays, what's deleted)

| attr | init vs run | write site(s) | read site(s) | action |
|---|---|---|---|---|
| `_resolver` | **init** | `:404` | `:658` | **stays on kernel** (immutable dep) |
| `_store` | **init** | `:405` | `:1033,1350,1359,1932,1964,2037,2159,2167,2170,2216` | **stays on kernel** |
| `_state_machine` | **init** | `:406` | `:697,813,843,888,896,898,1128,1359,1405,1407,1434,1516,1937,1946,1971,2040` | **stays on kernel** |
| `_od_context` | run | `:474` | `:940,1180,1582,1625,2390,2504` | → `ctx.od_context` |
| `_user_id` | run | `:475` | `:942,1182,1584` | → `ctx.owner_id` |
| `_gate_agent_ids` | run | `:481` | `:1904` | → `ctx.gate_agent_ids` |
| `_parent_run_id` | run **(WRITE-ONLY DEAD)** | `:486` | **none** | **DELETE the assignment** (verified never read — every consumer uses the local `parent_run_id` param) |
| `_checkpointer` | run | `:503` | `:1213,1869` | → `ctx.checkpointer` |
| `_completed_tasks` | run (list) | `:517` | `:1267(append),1285,1286` | → `ctx.completed_tasks` (mutable) |
| `_revision_original_html` | run | `:532,554` | `:975` | → `ctx.revision_original_html` |
| `_revision_instruction` | run | `:548,568` | `:955` | → `ctx.revision_instruction` |
| `_revision_baseline_static` | run (set) | `:549,624` | `:643,953` | → `ctx.revision_baseline_static` (mutable) |
| `_revision_baseline_console` | run (set) | `:550,639` | `:644,954` | → `ctx.revision_baseline_console` (mutable) |
| `_disk_skills` | run (dict) | `:655` | `:931,1170` | → `ctx.disk_skills` (mutable) |
| `_current_task_block` | run **(strategy-local scratch)** | `:1536` | `:2480` | → `ctx.current_task_block` for 0B; **earmark for `TaskLoopStrategy` in Phase 2** (see B6) |

**11 movers + 1 deletion.** After 0B, `dir(engine)` exposes only `_resolver`, `_store`, `_state_machine` as instance state (the NFR-001 acceptance check).

## B3. New file — `backend/agents/execution_engine/context.py`

The **Phase-0B-minimal** `ExecutionContext`: the smallest dataclass that captures all per-run-mutable state with zero behavior change. It is **not** the full §6 future context (no `CompiledWorkflow`/`Workspace`/`ArtifactGraph`/`BudgetManager` — those land in Phases 1-2/5). Reconciliation with plan §6 is noted inline.

```python
# backend/agents/execution_engine/context.py  (new; plan §28/§32 target path)
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field


@dataclass
class ExecutionContext:
    """Per-run mutable state for one ExecutionEngine.execute() invocation.

    Replaces the self._* run-state stashing on the singleton kernel (L14, INV-2).
    Phase-0B-minimal: the smallest subset that removes singleton mutation with no
    behavior change. The full kernel context (plan §6 — plan, workspace, artifacts,
    budget, models, model_overrides, depth) is added in later phases.
    """
    # ── identity / ownership (set once) ──
    run_id: str                                  # was the pipeline_run_id param
    owner_id: str                                # was self._user_id (value: user_id or "anon"); INV-8
    pipeline_type: str = "custom"

    # ── simple per-run values (set once in execute) ──
    od_context: dict | None = None               # was self._od_context
    gate_agent_ids: list[str] | None = None      # was self._gate_agent_ids (None = static gate set)
    model_id: str | None = None                  # session-level model passthrough
    cancel_event: asyncio.Event | None = None    # was the cancel_event param
    parent_run_id: str | None = None             # ownership-checked before seeding (INV-8/L16)
    checkpointer: object | None = None           # was self._checkpointer (shared singleton handle)

    # ── revision scratch (simple values) ──
    revision_original_html: str = ""             # was self._revision_original_html
    revision_instruction: str | None = None      # was self._revision_instruction

    # ── MUTABLE COLLECTIONS that accumulate during the run ──
    # (field(default_factory=...) so each ctx gets its OWN — never a shared default;
    #  these are exactly the attrs whose cross-run sharing corrupts concurrent runs)
    completed_tasks: list[dict] = field(default_factory=list)         # was self._completed_tasks — APPENDED in _run_agent
    revision_baseline_static: set[str] = field(default_factory=set)   # was self._revision_baseline_static
    revision_baseline_console: set[str] = field(default_factory=set)  # was self._revision_baseline_console
    disk_skills: dict[str, str] = field(default_factory=dict)         # was self._disk_skills — {agent_id: skill_md}

    # ── strategy-local scratch (Phase-0B home; moves to TaskLoopStrategy in Phase 2, see B6) ──
    current_task_block: str = ""                 # was self._current_task_block — set per build task
```

Map plan §6 → 0B field: §6 `owner_id` ⇐ `_user_id` (value kept `user_id or "anon"`); §6 `planning_context`/`accumulated_outputs` stay **local params** in `execute()` for 0B (they're already threaded as params, not on `self` — leave them; the plan removes `accumulated_outputs` in 1B); §6 `cancel_event`/`parent_run_id`/`checkpointer`/`completed_tasks` map directly. The engine-specific run fields (`od_context`, `disk_skills`, `gate_agent_ids`, `revision_*`, `current_task_block`) are legitimate per-run state today; Phase 2 re-homes them to ContextProviders/validators/strategies.

## B4. `execute()` refactor (keep the public signature identical)

Both callers use keyword args and construct no context object — `app/api/websocket.py:1110-1122` (full kwargs) and `agents/execution_engine/ndjson_adapter.py:62-68` (5 kwargs). So **keep `execute()`'s signature byte-for-byte** and build `ctx` internally:

```python
# inside execute(), replacing the self._x = param stashes at engine.py:474-655
ctx = ExecutionContext(
    run_id=pipeline_run_id,
    owner_id=user_id or "anon",          # synthetic-owner seam (plan §19); 0B keeps today's "anon"
    pipeline_type=pipeline_type,
    od_context=od_context,
    gate_agent_ids=gate_agent_ids,
    model_id=model_id,
    cancel_event=cancel_event,
    parent_run_id=parent_run_id,
    # checkpointer set just below after `await get_checkpointer()`
)
ctx.checkpointer = await get_checkpointer()
ctx.disk_skills = self._load_disk_skills(agents, owner_id_or_user_id)   # was self._disk_skills
# revision block writes ctx.revision_* instead of self._revision_*
```

Then:
- **Delete** the dead `self._parent_run_id = parent_run_id` (`engine.py:486`).
- Replace every `self._x =` run-state write (`:474,475,481,503,517,532,548-550,554,568,624,639,655`) with `ctx.x =`.
- Replace `self._completed_tasks` init (`:517`) — now `ctx.completed_tasks` (default_factory).

> **Note — `user_id or "anon"`:** appears at `:472` (the run's own sandbox), `:585` (parent sandbox), and via `ctx`. For 0B keep the exact `or "anon"` semantics (no behavior change). `ctx.owner_id` is where the plan's `anon:<session_id>` formalization later attaches. The cross-owner denial test (B5) must use **two distinct real ids**, not anon-vs-anon (today both `None`/`"anon"` collapse to the same principal).

## B5. The parent-run ownership check (L16 / INV-8)

### What's there today (the leak)

The revision seeding block (`engine.py:583-610`) does `RunSandbox(user_id or "anon", parent_run_id)` and copies `spec.md`/`design.md`/`tasks.md` from the parent sandbox into this run's. The **only** thing tying parent to owner is reusing the same `user_id` string as the disk path segment — **implicit, not enforced**. The WS layer validates `source_workflow_run_id` *exists* (`websocket.py:1042-1048`) but **does not filter by `user_id`** — a client can pass another user's run id.

### The check

`WorkflowRun` (`app/models/workflow.py:12-54`) has `id` (PK == run_id) and `user_id` (FK, **NOT NULL**). So ownership is a single scoped lookup: `WorkflowRun(id=parent_run_id).user_id == ctx.owner_id`. Per plan §19 + INV-8 the check belongs in a **store/authz helper**, not inline.

New `backend/agents/authz.py` (the §28/§32 target; Phase-0B-minimal):

```python
# backend/agents/authz.py  (new)
from __future__ import annotations
import logging
logger = logging.getLogger("agents.authz")

def assert_run_owned(parent_run_id: str, owner_id: str) -> bool:
    """Return True iff `parent_run_id` is owned by `owner_id` (INV-8, default-deny).

    Single scoped query against workflow_runs.user_id. A missing row or an
    owner mismatch returns False (deny). Never raises — the caller degrades
    gracefully (a denied/absent parent simply isn't seeded), preserving today's
    "missing parent only logs a warning" behavior. Phase 1B routes all
    artifact/run reads through this layer; 0B uses it for parent seeding only.
    """
    if not parent_run_id or not owner_id:
        return False
    try:
        from app.models.database import SessionLocal
        from app.models.workflow import WorkflowRun
        db = SessionLocal()
        try:
            row = db.query(WorkflowRun.user_id).filter(WorkflowRun.id == parent_run_id).first()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 — never break a revision on a lookup error
        logger.warning("assert_run_owned(%s) lookup failed (%s) — denying", parent_run_id, exc)
        return False
    if row is None:
        logger.warning("assert_run_owned: parent run %s not found — denying", parent_run_id)
        return False
    if row[0] != owner_id:
        logger.warning("assert_run_owned: parent run %s owned by %r, not %r — denying cross-owner seed",
                       parent_run_id, row[0], owner_id)
        return False
    return True
```

Wire it at the **top** of the seeding block (`engine.py:583`), before `RunSandbox(...)`:

```python
if parent_run_id and assert_run_owned(parent_run_id, ctx.owner_id):
    parent_sb = RunSandbox(ctx.owner_id, parent_run_id)   # was user_id or "anon"
    ...                                                     # unchanged copy loop
elif parent_run_id:
    logger.warning("prototype_revision: parent run %s not owned by %s — skipping seed (proceeding on HTML+instruction)",
                   parent_run_id, ctx.owner_id)
```

The existing graceful-degrade path (revision continues on HTML + instruction, `engine.py:646-650`) absorbs the denial — no exception, no broken revision.

> **L16 ledger note:** the §31 pattern is `RunSandbox(user_id or "anon", parent_run_id)` — after 0B that exact string is gone (replaced by `RunSandbox(ctx.owner_id, parent_run_id)` behind the `assert_run_owned` guard), so when 0B lands, flip L16 `☐→☑` with the SHA and the guard enforces 0-matches.

### The cross-owner denial test

`backend/tests/characterization/test_char_authz_parent_seed.py` (or under `tests/agents/`):

- **Positive control (today's behavior preserved):** create `WorkflowRun(id=parent, user_id="alice")`, seed `RunSandbox("alice", parent)` with `spec.md`; run `execute(..., user_id="alice", parent_run_id=parent)`; assert the revision sandbox **contains** the seeded `spec.md`/`design.md`/`tasks.md`.
- **Denial:** same parent owned by `"alice"`; run `execute(..., user_id="bob", parent_run_id=parent)`; assert (1) bob's sandbox contains **none** of alice's files, (2) the run still completes (graceful degrade — no exception), (3) a warning is logged.

## B6. Threading `ctx` through the helpers

Pass `ctx` to the 7 methods that read/write run state; convert `getattr(self, "_x", default)` → `ctx.x` and the mutations → `ctx.<collection>`:

| method (file:line) | reads from ctx | mutates ctx | change |
|---|---|---|---|
| `execute` (`:408`) | — | builds + writes all run fields | constructs ctx; deletes self._* writes; passes ctx down |
| `_run_agent` (`:1108`) | `disk_skills`, `od_context`, `owner_id`, `checkpointer` | **`completed_tasks.append`** (`:1267`) | add `ctx` param; `:1170,1180,1182,1213,1267,1285,1286` |
| `_run_build_task_loop` (`:1450`) | `od_context`, `owner_id`, `checkpointer` | **`current_task_block`** (`:1536`) | add `ctx`; `:1536,1582,1584`; pass ctx into `_run_agent` + the `AgentContext` it builds (`:1577`) |
| `_build_context_message` (`:2315`) | `od_context` (`:2390,2504`), `current_task_block` (`:2480`) | — | add `ctx` param |
| `_should_gate` (`:1890`) | `gate_agent_ids` (`:1904`) | — | add `ctx` param |
| `_run_validation_fix_loop` (`:1706`) | `checkpointer` (`:1869`) | — | already takes most state as kwargs; add `ctx` (or pass `checkpointer=ctx.checkpointer`) |
| `_write_build_reference_files` (`:1605`) | `od_context` (`:1625`) | — | add `ctx` param |

Methods reading **only** `_store`/`_state_machine`/`_resolver` need **no** `ctx`: `_run_planner`, `_invoke_planner`, `_default_planning_context`, `_emit_planner_events`, `_run_review_gate`, `_persist_workflow_definition`, `restore_non_terminal_runs`, `_handle_revision`, `_build_context_sources`, `_filter_consumed_outputs`, `_load_disk_skills`, `_count_plan_tasks`, `_extract_task_block`, `_load_template_example`, `_extract_existing_prototype_html`, `_slim_revision_message`, `_extract_html_skeleton` (dead).

> `_load_disk_skills(agents, user_id)` already takes `user_id` as a param — keep it; just store the result on `ctx.disk_skills` in `execute()` instead of `self._disk_skills`.

## B7. `current_task_block` — 0B home, Phase 2 destination

Plan §6 says strategy-local scratch (the task block) should live in the strategy, not the context. But **strategies don't exist until Phase 2.** For 0B the minimal, behavior-preserving move is `ctx.current_task_block` (above) — strictly better than mutating the singleton, and the field carries a comment marking it for relocation into `TaskLoopStrategy` when L11 moves (Phase 2). The alternative (threading it as an explicit param through `_run_build_task_loop → _run_agent → _build_context_message`) is more signature churn for a value that's already conceptually run state. **Decision: `ctx` for 0B; delete from ctx in Phase 2 when the strategy owns it** (track on the §31 ledger as part of L11/L14).

## B8. D1 `_handle_revision` — do NOT delete in 0B (correction to §31)

003 §31 lists D1 (`_handle_revision`, `engine.py:2138-2251`) as dead → delete in 0B. **The investigation found it is called by the WS `run_revision` handler (`websocket.py:~625`)** — a separate path from `execute()`. So it may be **live, not dead**.

**0B task:** confirm whether `run_revision` is a reachable, used route (grep the frontend/API for the `run_revision` message type; check if any client sends it).
- If **live** → `_handle_revision` is not dead; **leave it**, and correct §31 (move D1 out of 0B; it's superseded only when the revision path migrates in Phase 2). Keep D1 `status:"pending"` in the ledger.
- If **dead** (the route is itself unused) → delete `_handle_revision` **and** the dead `run_revision` handler together, flip D1 `☐→☑` with the SHA.

Until confirmed, **0B does not touch `_handle_revision`.** (This is exactly the kind of stale-assumption the 0A net guards against — resolve it with evidence, not the plan's prior.)

## B9. Ordered task checklist (0B)

1. Land 0A first (snapshots are the oracle).
2. Resolve **B8** (`_handle_revision` live or dead) — record the finding; correct §31 if needed.
3. Create `backend/agents/execution_engine/context.py` (B3).
4. Create `backend/agents/authz.py` with `assert_run_owned` (B5).
5. Refactor `execute()`: build `ctx`, delete the dead `self._parent_run_id`, replace all `self._x =` run writes with `ctx.x =`, store disk-skills + checkpointer on ctx (B4).
6. Thread `ctx` through the 7 helpers (B6); convert reads + the 3 mutation sites.
7. Wire `assert_run_owned` into the seeding block; switch `RunSandbox(user_id or "anon", …)` → `RunSandbox(ctx.owner_id, …)` (B5).
8. Add the cross-owner denial + positive-control tests (B5).
9. **Run the 0A characterization snapshots** → must be **byte-identical** (no `--snapshot-update`). Any diff = a behavior change = fix or revert.
10. Add the NFR-001 assertion test: after a run, `vars(engine)` keys ⊆ `{_resolver,_store,_state_machine}` (no per-run attrs leaked onto `self`).
11. Flip ledger **L14** and **L16** `☐→☑` with the deleting/landing commit SHA in `migration-ledger.json`, in the **same commit** → `test_migration_ledger.py` now enforces 0-matches for both. (D1 only if B8 found it dead.)
12. Full suite green: `cd backend && python3.11 -m pytest tests/characterization tests/agents tests/unit tests/test_migration_ledger.py -v`.

## B10. Definition of Done (0B)

- [ ] `ExecutionContext` holds all per-run state; `execute()` signature unchanged; both callers untouched.
- [ ] No per-run attribute remains on the kernel singleton — the NFR-001 assertion test passes (`self` exposes only `_resolver`/`_store`/`_state_machine`).
- [ ] The 3 mutation hazards (`completed_tasks.append`, `current_task_block`, `revision_*`) now mutate `ctx`, not `self`.
- [ ] Dead `self._parent_run_id` assignment deleted.
- [ ] `assert_run_owned` wired; cross-owner parent seed **rejected** (denial test green); positive control still seeds (today's behavior preserved).
- [ ] **0A characterization snapshots byte-identical** (deliverable + normalized events) — zero behavior change proven.
- [ ] Ledger L14 + L16 flipped to `☑` with SHA; guard enforces 0-matches. D1 resolved per B8.
- [ ] All existing test suites (`tests/agents`, `tests/unit`) still green.

## B11. 0B-specific risks

- **A subtle parity break** (threading `ctx` changes an event field/order) → caught immediately by re-running the 0A snapshots (gate, not guesswork).
- **A read site missed** (an overlooked `getattr(self, "_x")`) → grep the L14 broadened pattern (A0A ledger) returns >0 → 0B's own ledger flip would fail; also ruff/runtime AttributeError. The §B2 table is the exhaustive checklist.
- **`assert_run_owned` over-denies** (e.g. DB unavailable in a context where it was implicitly allowed) → it denies + logs + degrades gracefully, never raises; positive-control test ensures the same-owner path still seeds.
- **anon-vs-anon** (two unauthenticated runs share `"anon"`) → unchanged from today (0B preserves behavior); the denial test uses distinct real ids; the `anon:<session_id>` fix is deferred to plan §19 (later phase).
