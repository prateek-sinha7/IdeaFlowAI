# Phase 11: Engine-Owned Fan-Out + Merge [5] - Pattern Map

**Mapped:** 2026-06-10
**Files analyzed:** 18 (12 new / 6 grown)
**Analogs found:** 17 / 18 (1 partial: MergeStrategy port has no direct prior port-with-impls analog — uses ExecutionStrategy port shape)

This map is the planner's per-file "copy from here" reference. Every capability-side file MUST reach the kernel/app only through `ctx.runner` (import-linter forbids `from agents.execution_engine` / `from app.` in `agents/capabilities/**`, `agents/runtime/**`, `agents/workflows/**`). Run `/opt/homebrew/bin/lint-imports` after each plan (expect 4 kept / 0 broken).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|-------------------|------|-----------|----------------|-------|
| `agents/execution_engine/fanout.py` | service (kernel orchestrator) | event-driven / batch | `agents/execution_engine/kernel_services.py` (`run_agent`) + engine build-loop | role-match |
| `agents/execution_engine/budget.py` | service (reserve gate) | transform | `agents/execution_engine/kernel_services.py` (per-run handle obj) | role-match |
| `agents/capabilities/strategies/fanout_batch.py` | strategy (capability) | event-driven | `agents/capabilities/strategies/task_loop.py` | exact |
| `agents/capabilities/tools/providers.py` (grow) `spawn_subagents` | tool provider (capability) | request-emitter | `providers.py` `PrototypeToolProvider` (report_task_complete) | exact |
| `agents/capabilities/merge/base.py` (port) | port | transform | `agents/capabilities/base.py` `ExecutionStrategy` Protocol | role-match |
| `agents/capabilities/merge/{copy_disjoint,git_3way,json_merge,html_fragment}.py` | merge strategy (capability) | transform / file-I/O | `agents/capabilities/strategies/single_shot.py` (thin `@register` impl) | role-match |
| `agents/runtime/base.py` (grow) | port doc | — | `IsolationProvider` Protocol (in-file) | exact |
| `app/agents/runtime/local.py` (grow) | runtime impl (app) | file-I/O / subprocess | `LocalWorkspace._git` / `LocalSandboxRuntime.create_workspace` | exact |
| `app/agents/tools/runner_tools.py` (grow) concrete `spawn_subagents` | runner tool (app) | request-emitter | `report_task_complete` (store-free string tool) | exact |
| `app/models/subagent_run.py` | model (ORM) | CRUD | `app/models/exec_runs.py` `ExecRun` | exact |
| `alembic/versions/0019_subagent_runs.py` | migration | CRUD | `alembic/versions/0018_exec_runs.py` | exact |
| `agents/authz.py` (grow) `record_subagent_run`/`read_subagent_runs` | store writer (ScopedStore) | CRUD | `ScopedStore.record_exec_run` / `read_exec_runs` | exact |
| `agents/execution_engine/kernel_services.py` (grow) `record_subagent_run`, `run_fanout`, `run_worker` | handle methods | passthrough | `KernelServices.record_exec_run` / `run_agent` / `run_human_gate` | exact |
| `agents/execution_engine/context.py` (grow) budget ref | context field | — | existing `depth`/`cancel_event` fields (in-file) | exact |
| `agents/execution_engine/engine.py` (grow) fanout dispatch + tool-event derivation | sequencer | event-driven | engine dispatch loop + `report_task_complete` derivation (CLAUDE.md) | role-match |
| `agents/workflows/plan.py` (grow) `FanoutSpec`/`allowed_workers`/`Limits` live | model (dataclass) | — | existing `FanoutSpec`/`Limits`/`ToolPermissions` (in-file) | exact |
| `agents/workflows/compiler.py` (grow) materialize `FanoutSpec` + trust `Limits` | compiler | transform | `_compile_step` / `_check_trust` | exact |
| `agents/capabilities/registry.py` (grow) `_KNOWN` + lockstep | registry | — | `_KNOWN` set (in-file) | exact |
| `agents/workflows/<fanout fixture>/` + `tests/agents/test_sc001_fanout.py` | test fixture | — | `agents/workflows/sample_brownfield/workflow.yaml` + `test_sc001_nonprototype_task_loop.py` | exact |

## Pattern Assignments

### `agents/capabilities/strategies/fanout_batch.py` (strategy, event-driven)

**Analog:** `agents/capabilities/strategies/task_loop.py` (the direct precedent — same TaskSource-sourcing shape).

**Class + registry + handle access** (task_loop.py:135-176):
- `@register("strategy", "fanout_batch", user_allowed=True)` (mirror task_loop's registration; `fanout_batch` is already reserved in `capabilities/base.py:44` and is a valid manifest reference).
- `__init__` holds a module-singleton `CapabilityRegistry()` (capabilities are stateless).
- `async def run(self, step, ctx)` — `runner = ctx.runner`; `run_id = getattr(runner, "run_id", "")`; read `cancel_event = getattr(runner, "cancel_event", None)`.

**Source the task list exactly like task_loop** (task_loop.py:166-190):
```python
task_source_decl = getattr(step, "task_source", None)
source_step = getattr(task_source_decl, "source_step", None) or _DEFAULT_SOURCE_STEP
plan_output = runner.latest_typed_content(source_step) or ""
parser_name = "heading_tasks"
if task_source_decl is not None and getattr(task_source_decl, "parser", None):
    parser_name = task_source_decl.parser
parser = self._registry.resolve("task_parser", parser_name)
tasks = parser.parse(plan_output)
```

**Map tasks → worker requests and submit the batch to the kernel** (NEW handle method on KernelServices — do NOT import `fanout.py`):
```python
requests = [{"agent": "self", "input": t.body} for t in tasks]   # "self" = step.agent_id ×N (D-01)
async for event in runner.run_fanout(requests, ctx, step=step):  # the ONLY spawn path (FANOUT-02)
    yield event                                                   # re-yield lifecycle-only events (D-03)
```

**Import-purity note (task_loop.py:34-37):** NOTHING from `agents.execution_engine` or `app.*`; the agent loop / merge / run_fanout are reached ONLY through `ctx.runner`.

---

### `agents/capabilities/tools/providers.py` (grow) — `spawn_subagents` (tool provider, request-emitter)

**Analog:** `PrototypeToolProvider` (providers.py:71-83) — a thin `@register("tool", …)` class returning the custom-tool KEY.

**Registration** — note `user_allowed=False` (CAP-03; never user/db grantable):
```python
@register("tool", "spawn_subagents", user_allowed=False)
class SpawnSubagentsToolProvider:
    name = "spawn_subagents"
    def provide(self, spec, ctx) -> tuple[list[str], bool]:
        return (["spawn_subagents"], False)   # KEY only — factory resolves the concrete tool
```
The provider stays string-keyed (`TOOL_REPORT_TASK_COMPLETE` precedent, providers.py:12-14) so the capability layer imports NO app-side concrete tool. Concrete `@tool` lives app-side (see runner_tools.py below).

---

### `app/agents/tools/runner_tools.py` (grow) — concrete `spawn_subagents` (runner tool, request-emitter)

**Analog:** `report_task_complete` (the store-free string tool — backend/CLAUDE.md "Tool Sets"). This is the load-bearing FANOUT-01 pattern: **the tool body spawns NOTHING.**

**Pattern (D-02 / Research Pattern 3):** the `@tool` returns a structured-request string only; the engine derives the request from the tool call/result events and fulfils it via `run_fanout` — identical to how the engine derives `task_progress` from `report_task_complete`.
```python
# Tool body: return json.dumps({"fanout_request": tasks, "mode": mode}) — NO asyncio, NO run_fanout import.
```
**Guardrail (Pitfall 1):** the tool module must contain no `asyncio.gather` / spawn / kernel import — plan a banned-pattern-style grep assertion. The deepagents `task` tool stays excluded (factory `_ToolFilterMiddleware`).

---

### `agents/execution_engine/kernel_services.py` (grow) — `run_fanout` / `run_worker` / `record_subagent_run` (handle methods)

**Analogs (all in-file):**
- `run_agent` (kernel_services.py:568-637) — the worker-invocation primitive. `run_worker` wraps it per worker: set the worker's isolated workspace + per-worker `thread_id = f"{run_id}:{step}:{worker_i}"` (extends the build-loop `f"{run_id}:{spec.id}:{task_num}"` convention; add a depth segment for nested fan-out per A4), then re-yield `_run_agent` events. Workers carry NO gates, NO per-worker fix-loop (D-01).
- `run_human_gate` (kernel_services.py:475-516) — the ONE durable HITL delegate. The merge `human_gate` conflict policy routes through THIS (no sibling `run_merge_gate`). Pass the `merge_conflict` payload as the `payload` dict (rides the generic `review_gate_ready.data.output` field, exactly like the 10-03 approval snapshot).
- `record_exec_run` (kernel_services.py:358-399) — clone EXACTLY for `record_subagent_run`: `store = getattr(self._ectx, "scoped_store", None)`; `if store is None: return None`; wrap the delegate in `try/except Exception` → `logger.warning(...); return None` (audit must NEVER abort the run — INV-3 parity).

`record_subagent_run` signature to clone:
```python
async def record_subagent_run(self, *, parent_step, worker_agent, depth, isolation,
                              status, tokens=None, cost=None) -> str | None:
    store = getattr(self._ectx, "scoped_store", None)
    if store is None:
        return None
    try:
        return await store.record_subagent_run(self.run_id, parent_step=parent_step, ...)
    except Exception as exc:
        logger.warning("record_subagent_run failed: %s", exc); return None
```

---

### `app/models/subagent_run.py` + `alembic/versions/0019_subagent_runs.py` (model + migration, CRUD)

**Analogs:** `app/models/exec_runs.py::ExecRun` (ORM) and `alembic/versions/0018_exec_runs.py` (migration). Clone the 0018 recipe exactly.

**Migration header** (0018_exec_runs.py:24-29): `revision = "0019"; down_revision = "0018"; branch_labels = None; depends_on = None`. Module docstring states ADDITIVE ONLY (Q3, INV-3), free-String status (NO `sa.Enum`), offline-reversible (upgrade head → downgrade -1 → upgrade head against in-memory SQLite).

**Table** (mirror 0018's column shape; columns from §18 line 708):
```python
op.create_table("subagent_runs",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("parent_run_id", sa.String(), nullable=False),
    sa.Column("owner_id", sa.String(), nullable=False),        # AUTHZ-01 — every new table
    sa.Column("workspace_id", sa.String(), nullable=False),    # AUTHZ-01
    sa.Column("parent_step", sa.String(), nullable=False),
    sa.Column("worker_agent", sa.String(), nullable=False),
    sa.Column("depth", sa.Integer(), nullable=False),
    sa.Column("isolation", sa.String(), nullable=False),       # shared_read|sub_sandbox|worktree (free String)
    sa.Column("status", sa.String(), nullable=False),          # running|complete|failed|cancelled (free String — NO sa.Enum)
    sa.Column("tokens", sa.Integer(), nullable=True),
    sa.Column("cost", sa.JSON(), nullable=True),               # cost_class-weighted; € dormant
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(["parent_run_id"], ["workflow_runs.id"]),
    sa.PrimaryKeyConstraint("id"),
)
op.create_index("ix_subagent_runs_parent", "subagent_runs", ["parent_run_id"])
```
`downgrade()` drops the index then the table (0018 mirror). Add the `subagent_runs` row to `specs/003-workflow-engine-decoupling/migration-ledger.md` so `test_migration_ledger.py` tracks the 0018→0019 chain (single head).

---

### `agents/authz.py` (grow) — `ScopedStore.record_subagent_run` / `read_subagent_runs` (store writer, CRUD)

**Analog:** `ScopedStore.record_exec_run` (authz.py:843-888) + `read_exec_runs` (authz.py:888-905). Clone exactly:
- `record_subagent_run`: `from app.models.subagent_run import SubagentRun` (local import, like exec); `session, owned = self._acquire()`; build the row stamping `owner_id=self._owner_id, workspace_id=self._workspace_id` (default-deny scoping); `session.add(row); session.commit(); return row.id`; `finally: if owned: session.close()`. Row written at spawn (`running`), updated at terminal state (D-06).
- `read_subagent_runs`: `query = session.query(SubagentRun).filter(...)` then `query = self._scope_owner_ws(query, SubagentRun)` so a cross-owner read returns ∅ (the FANOUT-10 / T-08-02 mitigation).

---

### `agents/capabilities/merge/base.py` + 4 impls (port + merge strategies, transform)

**Analog:** `agents/capabilities/base.py::ExecutionStrategy` (the `@runtime_checkable` Protocol idiom) for the port shape; `agents/capabilities/strategies/single_shot.py` for the thin `@register` impl shape.

**Port (`merge/base.py`):**
```python
@runtime_checkable
class MergeStrategy(Protocol):
    name: str
    def merge(self, base: Any, fragments: Any) -> Any:   # -> MergeResult (conflicts + applied)
        ...
```
**Impls** — each a thin `@register("merge", <name>)` class (`user_allowed=True` per A2 — engine picks them; user never names them):
- `copy_disjoint.py` — pure-stdlib file ops; conflict = two fragments (or fragment vs base-since-spawn) touching the same relative path with differing content → emit `merge_conflict`, NEVER overwrite (Pitfall 6). Sort fragment iteration order for byte-stable determinism.
- `git_3way.py` — reaches git ONLY via `ctx.runner` worktree/merge handle methods (NO capability-side `subprocess`; Pitfall 2 / Phase-9 D-10).
- `json_merge.py` — pure-stdlib key-level merge; conflict = same key, differing values.
- `html_fragment.py` — registers to satisfy FANOUT-07; NOTHING routes prototype through it (Q33 / MERGE-01 v2).

---

### `app/agents/runtime/local.py` (grow) — worktree/sub_sandbox alloc (runtime impl, file-I/O / subprocess)

**Analog:** `LocalWorkspace._git` (local.py:187 — the single git-subprocess owner) + `LocalSandboxRuntime.create_workspace`/`teardown` (local.py:387/434) + `@register("runtime_env", "local")` (local.py:374).

**Worktree ops are NEW methods on `LocalWorkspace`** (the `_git` owner) reached via the handle — capabilities NEVER shell git (Phase-9 D-10):
- `git worktree add` off the working branch at spawn (branch `fanout/{step}/{worker_i}`), capture the spawn-point commit for the 3-way merge-base, `git worktree remove` + branch delete on teardown.
- `sub_sandbox` alloc = a child dir `{run}/subagents/{step}/{worker_i}/` with shared-read of parent refs (Q20).
- Engine selects scope (INV-7, NOT manifest): `scope = "worktree" if base_workspace_has_git else "sub_sandbox"` then `isolation_provider.allocate(scope)`.

**Teardown (Pitfall 5 / RESUME-01):** wrap the fan-out body so `teardown()` runs in a `finally`/cancel handler for EVERY allocated isolated workspace — `git worktree remove` + branch delete, not just rmtree. Acceptance asserts zero isolated dirs remain after cancel.

---

### `agents/workflows/compiler.py` (grow) — materialize `FanoutSpec` + trust-conditional `Limits` (compiler, transform)

**Analog:** `_compile_step` (compiler.py:219) + `_check_trust` (compiler.py:190-217). `fanout`/`on_conflict` are already in `_ALLOWED_STEP_KEYS` (compiler.py:78-79) but `FanoutSpec` is never constructed — close that additive gap (INV-5: pure data, no control flow; unknown keys still rejected via `set(raw) - _ALLOWED_STEP_KEYS`, compiler.py:231).

**Trust pattern for `Limits`** (compiler.py:208-211): file/builtin manifests may RAISE limits; an untrusted (`user`/`db`) manifest is checked against `is_user_allowed` and may only lower (08-03/10-02 ceiling precedent):
```python
if trusted:
    return
if not registry.is_user_allowed(kind, name):
    raise CompilerError(...)   # names the bad (kind, name)
```

---

### `agents/capabilities/registry.py` (grow) — `_KNOWN` + lockstep (registry)

**Analog:** `_KNOWN` set (registry.py:77-134). Add the new pairs AND update the lockstep drift-guard count TOGETHER (Pitfall 7 — two places):
```python
("strategy", "fanout_batch"),
("tool", "spawn_subagents"),     # user_allowed=False
("merge", "copy_disjoint"), ("merge", "git_3way"), ("merge", "json"), ("merge", "html_fragment"),
# + any isolation:* pairs if isolation impls register as capabilities (Claude's Discretion)
```

---

### `agents/workflows/<fanout fixture>/` + `tests/agents/test_sc001_fanout.py` (test fixture, SC-001 proof)

**Analogs:** `agents/workflows/sample_brownfield/workflow.yaml` (single-file manifest) + `tests/agents/test_sc001_nonprototype_task_loop.py` + `tests/agents/test_sample_brownfield_workflow.py`. Test-scoped manifest + AGENT.md only, using only registered capabilities (D-08): a `fanout_batch` step fanning 3 self-copies, each producing a distinct file, merged `copy_disjoint` — proves zero engine edits author a fanning workflow (SC-001).

## Shared Patterns

### Capability → kernel/app ONLY via `ctx.runner`
**Source:** `agents/capabilities/strategies/task_loop.py:34-37` (the import-purity docstring).
**Apply to:** `fanout_batch`, all 4 merge impls, the `spawn_subagents` provider, the runtime impls.
No `from agents.execution_engine` / `from app.` in `agents/capabilities/**`, `agents/runtime/**`, `agents/workflows/**`. Gate: `/opt/homebrew/bin/lint-imports` (4 kept / 0 broken).

### One durable HITL surface (no second gate)
**Source:** `KernelServices.run_human_gate` (kernel_services.py:475-516) — delegates to the unchanged `_run_review_gate`; structured payload rides the generic `review_gate_ready.data.output`.
**Apply to:** the merge-conflict `human_gate` policy. NO `run_merge_gate`.

### Best-effort owner-scoped audit (None-degrading)
**Source:** `KernelServices.record_exec_run` (kernel_services.py:358-399) + `ScopedStore.record_exec_run` (authz.py:843-888).
**Apply to:** `record_subagent_run` (handle + store). `store is None → None`; persist failure → `logger.warning(...); return None` — audit must never abort the run (INV-3 parity).

### Additive events ride the generic WS forward (zero edits)
**Source:** single emit boundary (engine.py, 05-04) + generic `app/api/websocket.py` forward (08-08).
**Apply to:** `subagent_spawned` / `subagent_result` / `merge_*` / `budget_warning`. Existing workflows declare no fanout → emit NONE of these → the 5 characterization snapshots stay byte/event-identical with `SNAPSHOT_UPDATE` unset (the INV-3 gate).

### Per-worker checkpoint thread_id
**Source:** build-loop convention (backend/CLAUDE.md "Runtime essentials": `f"{run_id}:{agent_id}"` + `:task`).
**Apply to:** every `run_fanout` worker spawn → `f"{run_id}:{step}:{worker_i}"` (add a depth/parent segment for nested fan-out, A4).

### Reserve at the single enforcement point (bypass-proof)
**Source:** the exec recorder wired INSIDE `exec_command` (the enforcement-point discipline, 10-02).
**Apply to:** `budget.reserve(subagents=N, concurrency=…, depth=ctx.depth)` is the FIRST thing `run_fanout` does, before any `allocate`/`run_agent` (Pitfall 4 / FANOUT-09). `BudgetManager` is a per-run object on `ExecutionContext` (INV-2 — never `self._budget` on the engine).

### No analog — `BudgetManager` reserve/spent semantics
**Note:** `budget.py` is genuinely net-new kernel logic (no prior reserve-gate analog). Its *shape* (per-run handle object, module-constant defaults 8/4/2/900s + merge_agent=2 + warn@80%) mirrors how `KernelServices` is a per-run object; the planner should use RESEARCH.md §6 contract `reserve(*, tokens=0, subagents=0)` for the dual reserve-before-spawn (countable) vs check-at-boundary (tokens/wall-clock) shapes (D-05).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `agents/execution_engine/budget.py` (`BudgetManager`) | service | transform | No prior reserve-gate exists; net-new. Object-lifecycle shape mirrors the per-run `KernelServices` handle; numeric defaults locked in SPEC. |

(`agents/capabilities/merge/base.py` is marked partial, not no-analog: the `ExecutionStrategy` Protocol at `capabilities/base.py:44` is the port idiom to copy.)

## Metadata

**Analog search scope:** `backend/agents/{execution_engine,capabilities,workflows,runtime,authz}`, `backend/app/agents/{runtime,tools}`, `backend/app/models`, `backend/alembic/versions`, `backend/tests/agents`.
**Files scanned:** ~22 (read: task_loop.py, capabilities/base.py, registry.py, kernel_services.py, runtime/base.py, plan.py, compiler.py, tools/providers.py, app/agents/runtime/local.py, authz.py, alembic 0018, sample_brownfield manifest; grep-scoped the rest).
**Pattern extraction date:** 2026-06-10
