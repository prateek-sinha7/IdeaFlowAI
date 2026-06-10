# Phase 11: Engine-Owned Fan-Out + Merge [5] - Research

**Researched:** 2026-06-10
**Domain:** Brownfield engine kernel — concurrent sub-agent fan-out, workspace isolation, deterministic merge, budget enforcement, additive persistence/events, cooperative cancellation. Python · asyncio · LangGraph checkpointer · git worktrees · Alembic · Ports & Adapters.
**Confidence:** HIGH (grounded in the live codebase; every integration point inspected this session)

## Summary

Phase 11 is almost entirely **net-new kernel code plus growth of existing seams** — the forward surface (`FanoutSpec`, `Limits`, `Step.on_conflict`, `Task.conflict_keys`, `ToolPermissions.spawn_subagents`, `ExecutionContext.depth`, `workflow_runs.budget_snapshot_json`) all already exists as INERT data, and the ports that own the new behavior (`IsolationProvider`, `ExecutionStrategy`, `RuntimeEnvironment`/`Workspace`) are already defined. The work is to make those fields LIVE through one new kernel module (`fanout.py::run_fanout`), one new budget module (`budget.py::BudgetManager`), a registered `fanout_batch` strategy, a permission-bound `spawn_subagents` request-emitter tool, a `MergeStrategy` port + 4 registered impls, two new `IsolationProvider` scopes (`sub_sandbox`/`worktree`), one additive migration (`0019` `subagent_runs`), and a family of additive lifecycle events. [VERIFIED: codebase grep — all forward fields present in plan.py/context.py; run_fanout/budget/MergeStrategy/subagent_runs absent]

The architecture is locked by hard CI gates. Workers MUST run through `KernelServices.run_agent` (the same `create_runner`/deepagents path the prototype build loop uses), never a hand-rolled loop — the banned-pattern ratchet (`test_banned_patterns.py`) hard-fails on a second `create_deep_agent` outside the one allow-listed adapter, and on any `if pipeline_type ==`/`spec.id ==` branch inside `agents/execution_engine/`. The capability impls (strategy, merge, tool, isolation) MUST NOT import the kernel or `app` — `import-linter` enforces 4 forbidden contracts (`agents.capabilities ↛ {agents.execution_engine, app}`, same for `agents.workflows` and `agents.runtime`). Anything a capability needs from the kernel/app (the workspace handle, git worktree ops, the HITL gate, the audit recorder) is reached through the `ctx.runner` (`KernelServices`) handle, never an import. [VERIFIED: backend/pyproject.toml import-linter contracts; tests/agents/test_banned_patterns.py]

The riskiest research item — **mid-stream interception of the `spawn_subagents` tool call** — resolves to the post-loop tool-event derivation pattern the codebase already uses for `report_task_complete`: the tool is store-free / spawn-free and returns a structured request string; the engine derives the fan-out request from the tool call/result events in the `astream_events` loop and fulfils it via `run_fanout`. This keeps INV-13 intact (no agent-loop edit) and the tool body grep-clean of any `asyncio.gather`/spawn (FANOUT-01). The second risk — worktree merge mechanics — resolves cleanly: `LocalWorkspace` is already the single git-subprocess owner (clone/branch/diff), so worktree add/merge/remove are NEW methods on `LocalWorkspace` reached through the handle, never capability-side `subprocess` calls. [VERIFIED: app/agents/tools/providers.py + backend/CLAUDE.md report_task_complete derivation; app/agents/runtime/local.py `_git` single owner]

**Primary recommendation:** Build `run_fanout` as a kernel-private coroutine on the `ExecutionEngine` reached via a `KernelServices.run_fanout` handle method; register `fanout_batch` as a thin `ExecutionStrategy` (mirrors `task_loop`) that parses tasks from the declared `TaskSource` and submits a batch to `run_fanout`; register `spawn_subagents` as a `user_allowed=False` request-emitter tool whose request the engine derives from tool events and routes through the SAME `run_fanout`. Add `sub_sandbox`/`worktree` as new `IsolationProvider` allocate-scopes that call new `LocalWorkspace` git-worktree methods. Persist via the `0018`-recipe `0019` migration; ride all new events on the generic WS forward at the single emit boundary. Prove SC-001 with a test-scoped `fanout_batch` manifest + AGENT.md fixture (the `sc001_task_loop` precedent).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `run_fanout` dispatch (spawn workers, gather, merge, budget reserve) | Kernel (`agents/execution_engine/fanout.py`) | — | INV-7: engine alone decides isolation/caps/merge. The only spawn path; must be bypass-proof. Reached via `ctx.runner` handle by both entry points. |
| `fanout_batch` declarative strategy | Capability (`agents/capabilities/strategies/`) | Kernel (via `ctx.runner.run_fanout`) | Strategy is thin: parse declared TaskSource → worker requests → hand batch to kernel. Port-only imports (import-linter). |
| `spawn_subagents` tool (request emitter) | Capability (`agents/capabilities/tools/`) + app concrete tool (`app/agents/tools/`) | Kernel (derives + fulfils request) | Tool emits a structured request string only; spawns nothing. Engine intercepts via tool-event derivation. |
| Worker agent invocation | Kernel (`KernelServices.run_agent` → `_run_agent` → `create_runner`) | App (`DeepAgentRunner`/`create_deep_agent`) | INV-13: workers run on the one sanctioned deepagents path; per-worker `thread_id`. |
| Isolation allocation (`sub_sandbox`/`worktree`) | Runtime port (`agents/runtime/base.py::IsolationProvider`) | App impl (`app/agents/runtime/local.py::LocalWorkspace`) | Engine selects scope (has_git→worktree, else sub_sandbox). Git ops live in the single git-subprocess owner. |
| `MergeStrategy` (copy_disjoint/git_3way/json/html_fragment) | Capability (`agents/capabilities/merge/`) | App/Workspace handle (git_3way needs the workspace) | Pure-stdlib merges (copy_disjoint/json/html) are kernel-importable-clean; git_3way reaches git via the handle (08-04 heavy-dep boundary). |
| `BudgetManager` reserve/spent | Kernel (`agents/execution_engine/budget.py`) | — | Per-run object on `ExecutionContext` (INV-2: no singleton). Reserve at the single spawn point. |
| `subagent_runs` persistence | App (`app/models/` + `agents/authz.py::ScopedStore`) | Kernel (`KernelServices.record_subagent_run` handle) | Owner-scoped writes; mirrors `exec_runs` (0018) recipe exactly. |
| `merge_conflict` human_gate | Kernel (`KernelServices.run_human_gate` → `_run_review_gate`) | — | The ONE durable HITL mechanism (Phase-10 D-02); no second gate surface. |
| New lifecycle events | Kernel (single emit boundary, 05-04) | App (generic `websocket.py` forward, 08-08) | `subagent_*`/`merge_*`/`budget_warning` ride the generic forward — zero `websocket.py` edits. |

## Standard Stack

This is a brownfield phase — there are **no new external packages**. Every capability is built on the already-installed stack. The "stack" here is the in-repo seams the phase extends.

### Core (already installed — extend, do not replace)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `deepagents` | 0.6.7 | Agent runtime; workers spawn via `create_deep_agent` through `KernelServices.run_agent` | INV-13 mandate — the ONE sanctioned agent loop [VERIFIED: `python3.11 -c "import deepagents"` → 0.6.7] |
| Python stdlib `asyncio` | 3.11 | Parallel worker fan-out via capped `asyncio.gather` + `asyncio.Semaphore`; cancellation via task cancel | §26 N8: long jobs stay in-process (FastAPI task + asyncio), no queue this phase [CITED: 11-CONTEXT.md §26] |
| Python stdlib `subprocess` | 3.11 | git worktree add/merge/remove — INSIDE `LocalWorkspace` only (single git-subprocess owner) | Phase-9 D-10 discipline; capabilities never shell git [VERIFIED: app/agents/runtime/local.py `_git`] |
| Alembic | (repo-pinned) | Additive `0019` `subagent_runs` migration | `0018` recipe: additive, free-String status, offline-reversible [VERIFIED: alembic/versions/0018_exec_runs.py] |
| SQLAlchemy | (repo-pinned) | `SubagentRun` ORM + `ScopedStore` default-deny read/write | mirrors `ExecRun`/0018 [VERIFIED: agents/authz.py ScopedStore] |

### Supporting (in-repo seams the phase makes live)
| Seam | Location | Purpose | When to Use |
|------|----------|---------|-------------|
| `KernelServices` handle | `agents/execution_engine/kernel_services.py` | The `ctx.runner` object capabilities reach kernel/app through; grows `run_fanout`, `record_subagent_run`, worktree/merge handle methods | Every capability→kernel/app reach (import-linter forbids direct import) |
| `IsolationProvider` port | `agents/runtime/base.py:132` | `allocate(scope)` — grows `sub_sandbox`/`worktree` scopes | Worker workspace allocation |
| `ExecutionStrategy` port | `agents/capabilities/base.py:44` (names `fanout_batch`) | Declarative fan-out entry strategy | `step.fanout` declared steps |
| Generic WS forward | `app/api/websocket.py` (08-08) | All `{type,data}` events flow with zero edits | New `subagent_*`/`merge_*`/`budget_warning` events |
| Single emit boundary | `engine.py` (05-04) | seq/event_id stamping | All new event emission |

### Alternatives Considered
| Instead of | Could Use | Tradeoff (and why rejected per CONTEXT) |
|------------|-----------|------------------------------------------|
| One child = one `run_agent` invocation (D-01) | Nested `engine.execute()` mini-run per child | Mini-runs imply per-child `workflow_runs` rows + full event streams + gate machinery — heavier than §12/§18 model; parent already owns validation. REJECTED (D-01). |
| `fanout_batch` strategy (D-02) | `step.fanout` as an orthogonal modifier any strategy honors | `task_loop × fanout` is undefined; dependency-aware parallel scheduling is Phase-12 `wave_scheduler`. REJECTED (D-02). |
| Lifecycle-only child events (D-03) | `subagent_chunk` tagged streaming now | No consumer until the Phase-12 panel; N interleaved streams add noise + parity risk. REJECTED (D-03). |
| Post-loop tool-event derivation for interception | A tool coroutine awaiting an engine-fulfilled future; or a HITL-style interrupt | Future-awaiting risks INV-13 agent-loop perturbation; the `report_task_complete` post-loop derivation pattern already exists and is parity-safe. RECOMMENDED. |

**Installation:** None. No `pip install`. (Package Legitimacy Audit below is N/A — zero external packages.)

**Version verification:** `deepagents==0.6.7` confirmed live [VERIFIED: `python3.11 -c "import deepagents; print(deepagents.__version__)"`]. All other dependencies are repo-pinned and unchanged.

## Package Legitimacy Audit

**Not applicable.** This phase installs **zero** external packages — it is brownfield kernel code on the already-installed stack (`deepagents==0.6.7`, stdlib `asyncio`/`subprocess`, repo-pinned Alembic/SQLAlchemy). No new PyPI dependency is introduced. slopcheck/registry verification is moot.

**Packages removed due to slopcheck [SLOP] verdict:** none (no packages).
**Packages flagged as suspicious [SUS]:** none (no packages).

## Architecture Patterns

### System Architecture Diagram

```
                          TWO ENTRY POINTS (both funnel to ONE run_fanout — FANOUT-02)
                          ───────────────────────────────────────────────────────────

  (A) DECLARATIVE                                  (B) RUNTIME TOOL
  step.fanout declared                             granted step's agent calls
        │                                          spawn_subagents(tasks=[{agent,input}], mode=…)
        ▼                                                 │  (tool emits a structured request STRING;
  fanout_batch strategy.run(step, ctx)                    │   spawns NOTHING — FANOUT-01 grep-clean)
   • parse declared TaskSource (heading_tasks)            ▼
   • map each task → {agent, input}              engine astream_events loop detects the tool
   • build worker requests                       call/result event, derives the request
        │                                         (the report_task_complete post-loop pattern)
        │                                                 │
        └──────────────────┬──────────────────────────────┘
                           ▼
            ctx.runner.run_fanout(requests, ctx)   ◄── the ONLY spawn path (INV-7, bypass-proof)
                           │
   ┌───────────────────────┼─────────────────────────────────────────────────────┐
   │ 1. worker selection (FANOUT-03)                                                │
   │    self → step.agent ×N  |  named → must be in allowed_workers + registry      │
   │    disallowed/unknown → structured error, ZERO spawns                          │
   ├───────────────────────────────────────────────────────────────────────────────┤
   │ 2. budget.reserve(subagents=N, concurrency, depth=ctx.depth)  (FANOUT-09)      │
   │    BEFORE any spawn; raises BudgetExceeded → graceful abort w/ partial results │
   ├───────────────────────────────────────────────────────────────────────────────┤
   │ 3. engine picks isolation scope (INV-7, NOT manifest):                         │
   │    has_git → worktree   |   else → sub_sandbox                                 │
   │    IsolationProvider.allocate(scope) → isolated Workspace per worker            │
   │    (owner_id/workspace_id stamped)                                              │
   ├───────────────────────────────────────────────────────────────────────────────┤
   │ 4. spawn workers (FANOUT-04):                                                   │
   │    parallel = asyncio.gather under Semaphore(min(declared, cap=4))             │
   │    sequential = ordered awaits                                                  │
   │    each worker = KernelServices.run_agent(thread_id={run}:{step}:{worker_i})   │
   │      → create_runner → deepagents (INV-13)                                      │
   │    cancel_event checked BEFORE wave / between sequential / before merge         │
   │    each child → subagent_runs row (running) + subagent_spawned event           │
   ├───────────────────────────────────────────────────────────────────────────────┤
   │ 5. collect results → fragment artifacts (typed, lineage) PERSIST BEFORE merge  │
   │    (FANOUT-06; partial survival on abort/cancel)                                │
   │    each child → subagent_result event + row terminal update (tokens/cost)       │
   ├───────────────────────────────────────────────────────────────────────────────┤
   │ 6. MergeStrategy.merge(base=run workspace, fragments=child workspaces)          │
   │    copy_disjoint | git_3way | json | html_fragment                             │
   │    conflict → merge_conflict ArtifactRef + merge_conflict event, then           │
   │    on_conflict: human_gate(run_human_gate) | merge_agent(≤2) | partial | abort  │
   ├───────────────────────────────────────────────────────────────────────────────┤
   │ 7. teardown isolated workspaces (incl. cancel path); budget.spent() →           │
   │    BudgetSnapshot → workflow_runs.budget_snapshot_json (OBS-01)                 │
   └───────────────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
            structured summary (per-worker status + artifact refs) → caller
            (tool result for (B); step output continues from merged base for (A))

  EVENTS: subagent_spawned / subagent_result / merge_* / budget_warning
          → single emit boundary (seq/event_id) → generic websocket.py forward (ZERO edits)
```

### Recommended Module Structure
```
backend/agents/execution_engine/
├── fanout.py              # NEW — run_fanout(requests, ctx): worker-select, reserve, isolate,
│                          #        spawn (gather/seq), collect fragments, merge, teardown
├── budget.py              # NEW — BudgetManager / BudgetExceeded / BudgetSnapshot;
│                          #        module-constant defaults (8/4/2/900s, merge_agent=2, warn@80%)
├── kernel_services.py     # GROW — run_fanout handle, record_subagent_run, worktree/merge handle methods
├── context.py             # GROW — budget manager ref field (make depth live)
└── engine.py              # GROW — fanout dispatch path + tool-event derivation + cancel checks at fanout boundaries

backend/agents/capabilities/
├── strategies/fanout_batch.py   # NEW — @register("strategy","fanout_batch"); parse TaskSource → requests → run_fanout
├── tools/providers.py           # GROW — @register("tool","spawn_subagents", user_allowed=False) request emitter
└── merge/                       # NEW package
    ├── __init__.py
    ├── base.py                  # MergeStrategy port (name + merge(base, fragments) -> MergeResult)
    ├── copy_disjoint.py         # @register("merge","copy_disjoint")  (pure stdlib file ops)
    ├── git_3way.py              # @register("merge","git_3way")       (via workspace handle)
    ├── json_merge.py            # @register("merge","json")           (pure stdlib key-merge)
    └── html_fragment.py         # @register("merge","html_fragment")  (registers; nothing routes prototype)

backend/agents/runtime/base.py   # GROW — IsolationProvider doc: sub_sandbox/worktree scopes now live
backend/app/agents/runtime/local.py  # GROW — LocalWorkspace worktree add/merge/remove + sub_sandbox child-dir alloc
backend/app/agents/tools/runner_tools.py  # GROW — concrete spawn_subagents @tool (request-emitter, returns string)
backend/app/models/subagent_run.py        # NEW — SubagentRun ORM
backend/alembic/versions/0019_subagent_runs.py  # NEW — additive, 0018 recipe
backend/agents/authz.py          # GROW — ScopedStore.record_subagent_run + read
backend/agents/workflows/plan.py # GROW — FanoutSpec fields (worker selection); allowed_workers on CompiledWorkflow
backend/agents/workflows/compiler.py  # GROW — materialize FanoutSpec, allowed_workers, trust-conditional Limits
backend/agents/workflows/<fixture>/   # NEW test-scoped fanout manifest + AGENT.md (SC-001 proof)
```

### Pattern 1: Capability reaches kernel/app ONLY through `ctx.runner` (the handle)
**What:** Strategies, merge impls, and tools never import `agents.execution_engine` or `app`. They call methods on the `KernelServices` handle attached at `ctx.runner`.
**When to use:** Always — import-linter forbids the direct import (4 contracts). `git_3way` needing git, `fanout_batch` needing `run_fanout`, the merge_conflict needing `run_human_gate` all go through the handle.
**Example:**
```python
# Source: agents/capabilities/strategies/task_loop.py:141-188 (the precedent fanout_batch mirrors)
async def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
    runner = ctx.runner                       # the KernelServices handle (typed Any here)
    parser = self._registry.resolve("task_parser", parser_name)
    tasks = parser.parse(runner.latest_typed_content(source_step) or "")
    requests = [{"agent": "self", "input": t.body} for t in tasks]
    async for event in runner.run_fanout(requests, ctx, step=step):   # NEW handle method
        yield event
```

### Pattern 2: Per-worker `thread_id` extends the build-loop convention
**What:** Each worker invocation gets a unique LangGraph checkpoint thread_id so workers never collide.
**When to use:** Every `run_fanout` worker spawn.
**Example:**
```python
# Source: backend/CLAUDE.md + kernel_services.py:48 — the build-loop precedent
#   engine path:        f"{run_id}:{spec.id}"
#   build-loop per-task: f"{run_id}:{spec.id}:{task_num}"
#   fanout per-worker:   f"{run_id}:{step}:{worker_i}"   ← recommended extension
```

### Pattern 3: Tool-event derivation for `spawn_subagents` (the interception mechanism)
**What:** The tool body returns a structured-request string and spawns nothing; the engine derives the request from the tool call/result events in the existing `astream_events` loop — exactly how `task_progress` is derived from `report_task_complete`.
**When to use:** Runtime entry point (B). Keeps INV-13 (no agent-loop edit) and FANOUT-01 (tool body grep-clean).
**Example:**
```python
# Source: backend/CLAUDE.md "report_task_complete is store-free: it just returns a
#         confirmation string. The engine derives task_progress from the tool's
#         call/result events" — the identical pattern for spawn_subagents.
# Tool body (app/agents/tools/runner_tools.py): returns json.dumps({"fanout_request": tasks, "mode": mode})
# Engine: on tool_result event for spawn_subagents → parse → ctx.runner.run_fanout(...) → return summary as the tool result
```

### Pattern 4: Additive migration mirrors the `0018` recipe exactly
**What:** `0019` `subagent_runs` — additive only, named FK to `workflow_runs.id`, free-String status (NO `sa.Enum`), `owner_id`+`workspace_id` NOT NULL, JSON columns for structured fields, offline-reversible (in-memory SQLite upgrade→downgrade→upgrade).
**Example:**
```python
# Source: alembic/versions/0018_exec_runs.py (the exact recipe to clone)
revision = "0019"; down_revision = "0018"
op.create_table("subagent_runs",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("parent_run_id", sa.String(), nullable=False),
    sa.Column("owner_id", sa.String(), nullable=False),        # AUTHZ-01
    sa.Column("workspace_id", sa.String(), nullable=False),    # AUTHZ-01
    sa.Column("parent_step", sa.String(), nullable=False),
    sa.Column("worker_agent", sa.String(), nullable=False),
    sa.Column("depth", sa.Integer(), nullable=False),
    sa.Column("isolation", sa.String(), nullable=False),       # shared_read|sub_sandbox|worktree
    sa.Column("status", sa.String(), nullable=False),          # running|complete|failed|cancelled (free String)
    sa.Column("tokens", sa.Integer(), nullable=True),
    sa.Column("cost", sa.JSON(), nullable=True),               # cost_class-weighted; € dormant
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(["parent_run_id"], ["workflow_runs.id"]),
    sa.PrimaryKeyConstraint("id"),
)
```

### Anti-Patterns to Avoid
- **Capability-side `subprocess`/git:** never call git from `git_3way` or any merge impl. Worktree add/merge/remove are NEW `LocalWorkspace` methods reached via the handle. (Phase-9 D-10; import-linter is the gate.)
- **A second HITL surface:** the merge `human_gate` MUST delegate to `run_human_gate` → `_run_review_gate`. No sibling `run_merge_gate`. (Phase-10 D-02.)
- **A second spawn path:** the tool body must spawn nothing; `run_fanout` is the ONLY spawn site. (FANOUT-01 grep; FANOUT-02.)
- **Re-enabling the deepagents `task` tool:** stays excluded — engine fan-out is the only sanctioned spawn. (INV-13; banned-pattern gate.)
- **Workflow-name/agent-id branch in fanout/budget/merge:** zero `if pipeline_type ==`/`spec.id ==` inside `agents/execution_engine/`. (INV-1; kernel-scoped hard-fail.)
- **Singleton budget state:** `BudgetManager` is a per-run object on `ExecutionContext`, never `self._budget` on the engine. (INV-2.)
- **`sa.Enum` for status:** free-String, matching `0018`/`0017`. (Migration-ledger discipline.)
- **Forking the forward fields:** ONE consumer each for `FanoutSpec`/`Limits`/`on_conflict`/`depth`. (INV-12 watch — migration-ledger.)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Running a worker agent | A custom agent loop / direct `create_deep_agent` | `KernelServices.run_agent` (→ `_run_agent` → `create_runner`) | INV-13; banned-pattern ratchet hard-fails a second `create_deep_agent` |
| Per-worker checkpoint isolation | A bespoke thread/key scheme | `f"{run_id}:{step}:{worker_i}"` extending the build-loop convention | Proven collision-free pattern [backend/CLAUDE.md] |
| Isolated worker workspace | A new disk-dir helper | `IsolationProvider.allocate(sub_sandbox\|worktree)` → `LocalWorkspace` | Traversal-proof `RunSandbox` + single git owner already exist |
| git worktree/merge plumbing | Capability-side `subprocess.run(["git",...])` | NEW `LocalWorkspace` methods (the `_git` owner) reached via handle | Phase-9 D-10; import-linter contract |
| HITL pause/resume for merge conflict | A new gate mechanism | `run_human_gate` → `_run_review_gate` | One durable HITL (Phase-10 D-02); review payload rides generic `review_gate_ready.data.output` |
| Owner-scoped child persistence | Raw SQLAlchemy writes | `ScopedStore.record_subagent_run` (default-deny) + `0018` migration recipe | AUTHZ-01 default-deny; reversible-offline proven |
| Streaming new events to the frontend | `websocket.py` edits | The generic WS forward + single emit boundary | 08-08/05-04: additive events flow with zero edits |
| Audit best-effort degradation | New try/except scaffolding | The `record_exec_run` None-degrading pattern | Audit must never abort the run (INV-3 parity) |
| Compiler control flow for fanout | A DSL / branching in the compiler | Materialize `FanoutSpec`/`allowed_workers` as pure data; control flow in the strategy/engine | INV-5: compiler stays thin |

**Key insight:** Nearly every "hard" piece of this phase already has a single, blessed home in the codebase. The phase's job is to *route through* those homes, not rebuild them. The two genuinely new mechanisms — `run_fanout` (the spawn/merge orchestrator) and `BudgetManager` (the reserve gate) — are kernel-private, and even they reach agents/workspaces/HITL/persistence through existing handles.

## Runtime State Inventory

> This is a brownfield phase but **net-additive**, not a rename/refactor of existing strings. The relevant "runtime state" question is: *what existing runtime state does fan-out interact with, and what new state must be cleaned up?*

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | NEW only: `subagent_runs` rows (one per child, owner-scoped). No existing datastore stores a fanout key today. `workflow_runs.budget_snapshot_json` (0014 column) goes from unwritten → written. | `0019` migration (new table) + write `budget_snapshot_json` on completion/abort/cancel. No data migration of existing rows (column already exists, default NULL). |
| Live service config | None — fan-out runs in-process (FastAPI task + asyncio, §26 N8). No external service (n8n/Datadog/etc.) holds fanout config. | None. |
| OS-registered state | **Isolated worker workspaces** — `sub_sandbox` child dirs (`{run}/subagents/{step}/{worker_i}/`) and `worktree` git worktrees + branches (`fanout/{step}/{worker_i}`). These are NEW on-disk/git state created per fan-out. | `teardown()` on every allocated isolated workspace, INCLUDING the cancel path (RESUME-01): `git worktree remove` + branch delete; rmtree the sub_sandbox dir. Acceptance asserts "no isolated workspace dirs remain after cancel." |
| Secrets/env vars | None — no new secret/env name. Worker workspaces inherit the run's default deny policy (exec OFF). | None. |
| Build artifacts | None — no package rename, no egg-info, no compiled artifact affected. | None. |

**Nothing found in categories Live-service-config / Secrets / Build-artifacts:** confirmed — fan-out is in-process and additive; the only durable side effects are the new `subagent_runs` rows and the per-worker isolated workspaces (both explicitly torn down).

## Common Pitfalls

### Pitfall 1: The `spawn_subagents` tool accidentally spawns (FANOUT-01 violation)
**What goes wrong:** The tool body imports `run_fanout` or calls `asyncio.gather` to "just do the spawn," collapsing the request-emitter contract.
**Why it happens:** It feels natural to make the tool do the work it names.
**How to avoid:** Tool body returns a structured string ONLY (`json.dumps({"fanout_request": ...})`). The engine derives + fulfils. Acceptance has an explicit grep: the tool module contains no task-spawning / `asyncio.gather`. Plan a banned-pattern-style assertion.
**Warning signs:** `import` of the kernel from the tool module; `asyncio` in the tool body.

### Pitfall 2: Capability imports the kernel/app and breaks import-linter
**What goes wrong:** `git_3way` imports `LocalWorkspace`, or `fanout_batch` imports `fanout.py`. `lint-imports` flips a contract to broken (4 kept → 3 kept / 1 broken).
**Why it happens:** The capability needs git or `run_fanout`.
**How to avoid:** Reach everything through `ctx.runner`. Run `/opt/homebrew/bin/lint-imports` after each plan; expect 4 kept / 0 broken.
**Warning signs:** Any `from agents.execution_engine` or `from app.` in a `agents/capabilities/**` or `agents/runtime/**` or `agents/workflows/**` module.

### Pitfall 3: A characterization snapshot drifts (INV-3 break)
**What goes wrong:** A new event, a changed thread_id shape, or a reordered emit perturbs one of the 5 byte/event-identical snapshots.
**Why it happens:** Touching the dispatch loop or emit boundary.
**How to avoid:** Fan-out is DORMANT for every existing workflow — none declare `fanout`, grant `spawn_subagents`, or set `Limits`. New code paths must be strictly conditional (gated like the exec-workspace provisioning at engine.py:1200-1226). Run the 5 characterization tests with `SNAPSHOT_UPDATE` unset; they must pass untouched.
**Warning signs:** A snapshot test fails; a new event appears in an existing workflow's stream.

### Pitfall 4: Budget reserved AFTER spawn (FANOUT-09 violation)
**What goes wrong:** Workers spawn, then the budget is checked — N+1 already ran before `BudgetExceeded`.
**Why it happens:** Reserve feels like a post-condition.
**How to avoid:** `budget.reserve(subagents=N, concurrency=…, depth=ctx.depth)` is the FIRST thing `run_fanout` does, before any `allocate`/`run_agent`. Countable units (subagents/concurrency/depth) reserve-before-spawn; tokens/wall-clock are check-at-boundary + mid-flight abort (you can't pre-reserve unknown token spend — the §6 contract `reserve(*, tokens=0, subagents=0)` covers both shapes, D-05). Acceptance: "worker N+1 never spawns and the rejection has no side effects."
**Warning signs:** A spawned-then-aborted worker leaves a `subagent_runs` row for work that should never have started.

### Pitfall 5: Worktree state leaks on cancel (RESUME-01 violation)
**What goes wrong:** Cancel mid-fan-out leaves `git worktree` dirs + `fanout/*` branches behind.
**Why it happens:** Teardown is wired for the happy path only.
**How to avoid:** Wrap the fan-out body so `teardown()` runs in a `finally` / cancel handler for EVERY allocated isolated workspace. `LocalWorkspace.teardown` must remove the worktree (`git worktree remove`) + delete the branch, not just rmtree. Acceptance asserts zero isolated dirs remain after cancel.
**Warning signs:** `git worktree list` shows orphaned worktrees after a cancelled test run.

### Pitfall 6: Merge silently overwrites instead of reporting a conflict (FANOUT-07 violation)
**What goes wrong:** Two fragments touch the same path; `copy_disjoint` last-writer-wins instead of flagging.
**Why it happens:** Copying is simpler than diffing.
**How to avoid:** `copy_disjoint` conflict = two fragments (or fragment vs base-since-spawn) touching the same relative path with differing content → emit `merge_conflict`, never overwrite. Acceptance: "overlapping writes produce a reported conflict." Determinism: disjoint sets produce a byte-stable result (sort fragment iteration order).
**Warning signs:** A merge test with overlapping writes passes without a `merge_conflict` event.

### Pitfall 7: `_KNOWN` lockstep count drifts
**What goes wrong:** New `@register` entries (`strategy:fanout_batch`, `tool:spawn_subagents`, 4× `merge:*`, possibly `isolation:*`) added to `_KNOWN` but the lockstep drift-guard count not updated.
**Why it happens:** Two places to update.
**How to avoid:** Update `_KNOWN` AND the registry lockstep count together (currently 53 entries). Confirm `user_allowed`: `spawn_subagents` is `user_allowed=False` (CAP-03); merge strategies likely `user_allowed=True` (they're palette-safe — engine picks them); `runtime_env`-style isolation impls `user_allowed=False`.
**Warning signs:** A registry drift-guard test fails with a count mismatch.

### Pitfall 8: `merge_agent` oscillation past 2 attempts
**What goes wrong:** The `merge_agent` policy retries unboundedly.
**Why it happens:** No counter.
**How to avoid:** Bound at 2 attempts (mirrors `_MAX_FIX_ATTEMPTS`), then fall back to `human_gate`. Acceptance: "merge_agent attempt count observed ≤ 2 with no oscillation."

## Code Examples

### Worker invocation through the handle (one child = one isolated agent — D-01)
```python
# Source: agents/execution_engine/kernel_services.py:568-637 (run_agent) — the worker path.
# run_fanout calls a handle method that, per worker, sets the worker's isolated workspace +
# per-worker thread_id, then re-yields _run_agent events. Workers carry NO gates, NO per-worker
# fix-loop (validation/merge happen at the parent step after merge).
async for ev in ctx.runner.run_worker(            # NEW handle method (wraps run_agent)
    step, ctx, worker_index=i, workspace=isolated_ws,
    thread_id=f"{run_id}:{step_id}:{i}", agent_id=worker_agent, input=task_input,
):
    ...  # lifecycle-only: do NOT forward chunk events (D-03)
```

### Best-effort owner-scoped child persistence (the `record_exec_run` model — D-06)
```python
# Source: agents/execution_engine/kernel_services.py:358-399 (record_exec_run) — clone for subagent.
async def record_subagent_run(self, *, parent_step, worker_agent, depth, isolation,
                              status, tokens=None, cost=None) -> str | None:
    store = getattr(self._ectx, "scoped_store", None)
    if store is None:
        return None                                  # offline harness → None-degrade
    try:
        return await store.record_subagent_run(self.run_id, parent_step=parent_step, ...)
    except Exception as exc:                          # audit must NEVER abort the run
        logger.warning("record_subagent_run failed: %s", exc); return None
```

### Engine selects isolation scope (INV-7 — engine, not manifest)
```python
# Source: derived from app/agents/runtime/local.py create_workspace(has_git=...) + 11-CONTEXT D-04.
scope = "worktree" if base_workspace_has_git else "sub_sandbox"   # engine decides, NOT step.fanout
isolated_ws = isolation_provider.allocate(scope)                  # via the handle
```

### Cancel checks at fan-out boundaries (RESUME-01)
```python
# Source: engine.py dispatch loop cancel idiom (engine.py:1261, 2230, 2343).
if cancel_event and cancel_event.is_set():        # before the wave
    raise asyncio.CancelledError
# ... between sequential workers, and before merge — same check; finally: teardown all isolated ws.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Step.fanout`/`Limits`/`on_conflict`/`depth` declared but INERT | Made LIVE: compiler materializes, engine consumes | Phase 11 (this) | The forward surface from Phase 4 finally has consumers — ONE each (INV-12) |
| `IsolationProvider` port with only `shared_read`/per-run | Adds `sub_sandbox`/`worktree` scopes | Phase 11 | Worker writes isolated; engine-selected scope |
| `workflow_runs.budget_snapshot_json` column unwritten (since 0014) | Written on completion/abort/cancel | Phase 11 | Budget observability goes live (OBS-01) |
| Prototype build loop = the only engine-owned sub-agent loop | Generic `run_fanout` (workflow-agnostic) | Phase 11 | Any workflow can fan out; prototype stays sequential (Q33) |
| Migration head `0018` (`exec_runs`) | `0019` (`subagent_runs`) | Phase 11 | Additive chain extends; reversible offline |

**Deprecated/outdated:**
- The deepagents library `task` (sub-agent dispatch) tool: stays EXCLUDED. Engine fan-out is the sanctioned replacement (INV-13). Do not re-enable.
- `html_fragment` merge wiring into prototype: deferred to MERGE-01 v2. The strategy registers; nothing routes prototype through it (prototype stays sequential).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `report_task_complete` post-loop tool-event derivation pattern is the right interception mechanism for `spawn_subagents` (vs an awaited future or HITL-interrupt). | Pattern 3 / Area B directive | If the engine's `astream_events` loop can't cleanly derive + fulfil mid-stream and return a tool result, a different mechanism (awaited future) is needed — but that risks INV-13. Planner should confirm against the live `_run_agent` loop before committing. |
| A2 | `merge` strategies register `user_allowed=True` and isolation impls `user_allowed=False`. | Pitfall 7 | If a merge strategy should NOT be user-palette-exposed, the trust flag flips. Low risk (engine picks merge; user never names it). Claude's Discretion per CONTEXT. |
| A3 | `git_3way` reaching git via a NEW `LocalWorkspace` worktree-merge handle method (vs the `IsolationProvider` impl owning merge) is the cleaner split. | Module structure | Either satisfies import-linter (CONTEXT marks this Claude's Discretion). Planner decides the exact method home. |
| A4 | Per-worker `thread_id = {run_id}:{step}:{worker_i}` is collision-free on the checkpointer. | Pattern 2 | If a worker also nests (depth+1 spawns its own workers), the key needs the depth/parent segment too. Directive in D-01 to confirm uniqueness — planner should add the depth segment for nested fan-out. |
| A5 | `BudgetSnapshot` cost is stored as JSON (cost_class-weighted; € dormant) in `subagent_runs.cost` and the run snapshot. | Migration pattern | If a scalar numeric cost column is preferred, the schema differs. Column types are Claude's Discretion per CONTEXT. |
| A6 | The sample fan-out fixture lives test-scoped (`tests/agents/fixtures/` + a `agents/workflows/<fixture>/`) like `sc001_task_loop`, NOT shipped as a production workflow. | SC-001 proof | If it must ship as a real workflow it'd add to `PIPELINE_AGENTS`/registry. D-08 locks it test-scoped — low risk. |

## Open Questions

1. **Where does the `0019` migration ride in the 5-plan sequence?**
   - What we know: ROADMAP sketch puts persistence in 11-05; but 11-01's `run_fanout` tests may need the table to write rows.
   - What's unclear: whether 11-01 should land `0019` early.
   - Recommendation: planner's call (D-09 explicitly permits re-cutting). If 11-01 tests assert a `subagent_runs` row, land `0019` + the ORM + ScopedStore writer in 11-01; otherwise 11-05. Either way the migration is additive and reversible.

2. **Budget reserve seams needed by 11-01's `run_fanout`.**
   - What we know: `run_fanout` must `reserve()` before spawn, but `BudgetManager` is the ROADMAP's 11-04.
   - What's unclear: stub-and-thread vs reorder.
   - Recommendation: stub `BudgetManager.reserve` as a no-op-returning seam in 11-01 (so `run_fanout` has the call site), make it enforce in 11-04. Each plan must leave the characterization suite green (D-09).

3. **`merge_agent` worker designation.**
   - What we know: `merge_agent` policy spawns "a designated merge worker bounded at 2."
   - What's unclear: how the merge worker agent is named/selected (a reserved agent id? a manifest field?).
   - Recommendation: planner decides — likely a named worker from `allowed_workers` or a convention agent id. Bound at 2 then fall back to `human_gate` is locked.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `deepagents` | Worker agent invocation (INV-13) | ✓ | 0.6.7 | — |
| `python3.11` | Dev runtime (no venv) | ✓ | 3.11 | — |
| `git` | `worktree` isolation + `git_3way` merge | ✓ | (system) | `sub_sandbox` covers non-git runs; git_3way only used when has_git |
| `git worktree` | Worker isolation for repo runs | ✓ | (system git) | — |
| `lint-imports` | import-linter 4-contract gate | ✓ | `/opt/homebrew/bin/lint-imports` | — |
| Alembic + in-memory SQLite | `0019` offline-reversible test | ✓ | repo-pinned | — |
| Postgres / Bedrock / Chromium | Full pytest suite | ✗ (offline) | — | Targeted offline parity/gate suite (~35s) — full pytest hangs offline (MEMORY: offline-test-suite-targeted) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Full backend pytest (Postgres/Bedrock/Chromium-gated) hangs offline — verify with the targeted parity/gate suite + `lint-imports` (per memory). Live Bedrock checks deferred to end-of-milestone live pass.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 (`python3.11 -m pytest`, no venv) |
| Config file | `backend/pyproject.toml` (pytest + import-linter contracts) |
| Quick run command | `cd backend && python3.11 -m pytest tests/agents/test_fanout.py -x` (new) |
| Full suite command | Targeted offline set: `cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py tests/agents/test_compiler_trust.py tests/agents/test_sc001_*.py` + `/opt/homebrew/bin/lint-imports` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FANOUT-01 | `spawn_subagents` bound only when granted; tool body spawn-free | unit + grep | `pytest tests/agents/test_fanout_tool.py -x` | ❌ Wave 0 |
| FANOUT-02 | both entry points funnel through one `run_fanout` | unit | `pytest tests/agents/test_fanout.py -k funnel -x` | ❌ Wave 0 |
| FANOUT-03 | self×N; named worker via allowed_workers; disallowed rejected zero-spawn | unit | `pytest tests/agents/test_fanout.py -k worker_select -x` | ❌ Wave 0 |
| FANOUT-04 | parallel ≤ cap (semaphore); sequential ordered; user-trust clamp | unit (instrumented) | `pytest tests/agents/test_fanout.py -k modes -x` | ❌ Wave 0 |
| FANOUT-05 | sub_sandbox/worktree isolation; engine-scope-select; owner/workspace stamped | unit | `pytest tests/agents/test_isolation.py -x` | ❌ Wave 0 |
| FANOUT-06 | fragment artifacts typed/lineage; structured summary | unit | `pytest tests/agents/test_fanout.py -k summary -x` | ❌ Wave 0 |
| FANOUT-07 | 4 merge strategies registered; copy_disjoint deterministic; overlap→conflict | unit | `pytest tests/agents/test_merge.py -x` | ❌ Wave 0 |
| FANOUT-08 | 4 on_conflict policies; merge_conflict artifact+event; merge_agent≤2; human_gate round-trip | unit | `pytest tests/agents/test_merge_conflict.py -x` | ❌ Wave 0 |
| FANOUT-09 | reserve-before-spawn; depth>2 reject; wall-clock abort; defaults asserted | unit | `pytest tests/agents/test_budget.py -x` | ❌ Wave 0 |
| FANOUT-10 | one subagent_runs row/child; events emitted; cross-owner read=∅ | unit + migration | `pytest tests/agents/test_subagent_runs.py -x` | ❌ Wave 0 |
| FANOUT-11 | cancel mid-fanout: in-flight stop, pending never spawn, rows cancelled, teardown | unit | `pytest tests/agents/test_fanout_cancel.py -x` | ❌ Wave 0 |
| OBS-01 | per-run + per-workspace ceilings; snapshot persisted on complete+abort | unit | `pytest tests/agents/test_budget.py -k workspace_ceiling -x` | ❌ Wave 0 |
| RESUME-01 | cancel at fanout boundaries; no leaked workspaces; partial preserved | unit | `pytest tests/agents/test_fanout_cancel.py -k teardown -x` | ❌ Wave 0 |
| SC-001 | test-scoped fanout workflow runs zero-engine-edit | integration | `pytest tests/agents/test_sc001_fanout.py -x` | ❌ Wave 0 |
| Parity (INV-3) | 5 characterization snapshots byte/event-identical | snapshot | `pytest tests/agents/test_characterization_*.py` | ✅ exists |
| INV-13/INV-1 | banned-pattern: no 2nd create_deep_agent; no kernel name-branch; spawn-free tool | ratchet | `pytest tests/agents/test_banned_patterns.py` | ✅ exists |
| Ledger | 0018→0019 single head; reversible | ratchet | `pytest tests/agents/test_migration_ledger.py` | ✅ exists |
| Import direction | capability/runtime/workflow ↛ kernel/app | lint | `/opt/homebrew/bin/lint-imports` | ✅ config exists |

### Sampling Rate
- **Per task commit:** the new focused suite for the task's requirement (`pytest tests/agents/test_<area>.py -x`) + `lint-imports` if a capability/kernel module changed.
- **Per wave merge:** the targeted offline set (characterization + banned-patterns + migration-ledger + compiler-trust + sc001) + `lint-imports` (4 kept / 0 broken).
- **Phase gate:** full targeted offline suite green before `/gsd-verify-work`; live Bedrock deferred to end-of-milestone.

### Wave 0 Gaps
- [ ] `tests/agents/test_fanout.py` — covers FANOUT-02/03/04/06
- [ ] `tests/agents/test_fanout_tool.py` — covers FANOUT-01 (incl. spawn-free grep assertion)
- [ ] `tests/agents/test_isolation.py` — covers FANOUT-05 (sub_sandbox/worktree, scope select, teardown)
- [ ] `tests/agents/test_merge.py` — covers FANOUT-07 (4 strategies, determinism, conflict detection)
- [ ] `tests/agents/test_merge_conflict.py` — covers FANOUT-08 (4 policies, artifact+event, human_gate round-trip)
- [ ] `tests/agents/test_budget.py` — covers FANOUT-09 + OBS-01 (reserve, defaults, depth, wall-clock, workspace ceiling, snapshot)
- [ ] `tests/agents/test_subagent_runs.py` + `0019` reversibility test — covers FANOUT-10
- [ ] `tests/agents/test_fanout_cancel.py` — covers FANOUT-11 + RESUME-01 (teardown asserted)
- [ ] `tests/agents/test_sc001_fanout.py` + `tests/agents/fixtures/sc001_fanout/` + `agents/workflows/<fanout fixture>/` — covers SC-001
- [ ] Add `subagent_runs` row(s) to the `0019` ledger entry (migration-ledger.md) so `test_migration_ledger.py` tracks it
- [ ] Scripted-model scaffolding for parallel workers (extend `tests/agents/_scripted_model.py`; `RUNS_ROOT` monkeypatch to temp dir)

## Security Domain

> `security_enforcement: true`, ASVS level 1, block on high.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Ports & Adapters; INV-7 engine-owned decisions; least-privilege defaults (spawn_subagents OFF) |
| V2 Authentication | no | No new auth surface; runs inherit the run's principal |
| V3 Session Management | no | No sessions; per-run `ExecutionContext` |
| V4 Access Control | **yes** | `ScopedStore` default-deny on `subagent_runs` (owner_id+workspace_id NOT NULL); cross-owner read = ∅; `spawn_subagents` `user_allowed=False` (CAP-03 — never user/db-grantable); per-workspace budget keyed owner+workspace |
| V5 Input Validation | **yes** | Worker selection rejects unknown/disallowed agents BEFORE spawn (structured error, zero side effects); compiler rejects unknown step keys + not-user-allowed references (INV-5/CAP-03); `allowed_workers` is an allow-list |
| V6 Cryptography | no | No crypto introduced |
| V7 Error Handling/Logging | yes | Best-effort audit (None-degrade) must never abort the run; `merge_conflict` artifact carries truncated hunks (no raw secret leak); `budget_warning`/`merge_*` events at the single emit boundary |
| V12 Files/Resources | **yes** | Isolated worker workspaces are traversal-proof (`RunSandbox.path_for`); git clone protocol-restricted (`GIT_ALLOW_PROTOCOL`); teardown removes worktrees/branches/dirs (no leak); workers inherit exec=OFF policy |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Resource exhaustion via unbounded fan-out (fork bomb) | Denial of Service | `BudgetManager` reserve-before-spawn: subagents=8/concurrency=4/depth=2/wall=900s caps; per-workspace ceiling; depth>2 → BudgetExceeded |
| Privilege escalation via user-granted spawn | Elevation of Privilege | `spawn_subagents` `user_allowed=False`; compiler CAP-03 rejects user/db manifests referencing it; the deepagents `task` tool stays excluded |
| Cross-owner data read via subagent rows | Information Disclosure | `ScopedStore` default-deny; `subagent_runs` owner_id+workspace_id NOT NULL; cross-owner read = ∅ (acceptance-asserted) |
| Worker write cross-contamination before merge | Tampering | Writes isolated per worker (sub_sandbox/worktree); merge detects same-path conflicts, never silently overwrites |
| Secret leakage in merge_conflict payload | Information Disclosure | Truncated hunks/snippets only (Phase-10 D-04 payload discipline); the worker policy is exec/network/secrets OFF |
| git transport code-exec at worktree/clone | Tampering/EoP | `GIT_ALLOW_PROTOCOL=file:https:ssh` (no ext::/fd::); option-injection guard (`source.startswith("-")`); git ops only inside `LocalWorkspace` |
| Orphaned worktrees/branches after cancel | Resource leak (DoS) | `teardown()` in cancel path: `git worktree remove` + branch delete + rmtree; acceptance asserts zero residue |
| Bypassing the budget by spawning outside run_fanout | EoP / DoS | `run_fanout` is the ONLY spawn path (FANOUT-02 grep); reserve at the enforcement point (bypass-proof, like the exec recorder) |

## Project Constraints (from CLAUDE.md)

- **INV-13 (runtime mandate):** every agent runs on `deepagents==0.6.7` via `from deepagents import create_deep_agent`; adapter id `langchain_deepagents`. Workers spawn through `KernelServices.run_agent`/`create_runner` ONLY. No hand-rolled loop, no second `create_deep_agent`. Enforced by `test_banned_patterns.py`.
- **Architecture (Ports & Adapters):** kernel depends only on capability ports; impls self-register into `CapabilityRegistry` via `@register`. Adding a capability = add module + register, zero kernel edit. Enforced by import-linter (4 contracts in `backend/pyproject.toml`).
- **Compiler thin, no DSL (INV-5):** manifests are pure data; `fanout`/`allowed_workers`/`on_conflict`/`limits` are recorded, control flow lives in strategy/engine.
- **Persistence additive only (Q3):** `0019` additive migration; `subagent_runs` carries `owner_id` + `workspace_id`; reads default-deny via `ScopedStore`.
- **Security defaults OFF:** `exec`/`network`/`secrets`/`spawn_subagents` default OFF; `spawn_subagents` stays privileged (CAP-03, never user-grantable this phase).
- **No dual implementations (INV-3/INV-12):** making a forward field live must not create a parallel config surface — ONE consumer each for `FanoutSpec`/`Limits`/`on_conflict`/`depth`. A phase that adds an abstraction without deleting what it supersedes is not done.
- **Backward-compat (INV-3):** existing prototype/od_/PPT/code-gen behavior stays byte-identical + event-parity — the 5 characterization snapshots pass untouched (fan-out dormant for all existing workflows).
- **Dev/test reality:** `python3.11` (no venv); full pytest hangs offline — verify with the targeted parity/gate suite (~35s) + `/opt/homebrew/bin/lint-imports`; live Bedrock deferred to end-of-milestone.
- **GSD workflow enforcement:** edits go through a GSD command; commit scopes per `backend/CLAUDE.md` (`engine`/`factory`/`registry`/`tools`/`sandbox`/`tests`).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **SPEC-first:** 13 requirements (FANOUT-01..11, OBS-01, RESUME-01) + budget defaults locked in `11-SPEC.md`. All four HOW gray areas locked to Claude's plan-grounded recommendations.
- **D-01 — Worker shape:** one child = ONE isolated `KernelServices.run_agent` invocation (NOT a nested mini-run). Per-worker thread_id `{run_id}:{step}:{worker_i}`. Workers carry NO gates / NO per-worker fix-loop. Children are `subagent_runs` rows, never `workflow_runs`. Nesting (Q17): the tool may bind inside a worker only when granted; funnels to the same `run_fanout` with `ctx.depth+1`; depth>2 → rejected before spawn.
- **D-02 — Declarative entry = `fanout_batch` ExecutionStrategy:** sources tasks from declared `TaskSource`, parses via declared task parser, maps each task → one worker request, submits to `run_fanout`. `step.fanout` (grown `FanoutSpec`) configures it; `allowed_workers` lands on the compiled model as pure data. Compiler MATERIALIZES `FanoutSpec` (additive, INV-5). Runtime entry: granted step's agent calls `spawn_subagents`; tool emits a structured request; engine fulfils via the SAME `run_fanout`.
- **D-03 — Child events lifecycle-only:** parent stream carries `subagent_spawned`/`subagent_result`/`merge_*`/`budget_warning` ONLY. Child chunks NOT forwarded (workers run silent). All new events ride the generic `websocket.py` forward (zero edits) + the single emit boundary.
- **D-04 — Merge base = parent run's primary workspace; fragments = child workspaces.** `copy_disjoint`/`git_3way`/`json`/`html_fragment` semantics as specified. Worktree: branch-per-worker `fanout/{step}/{worker_i}` off the working branch; `LocalWorkspace` stays the SINGLE git-subprocess owner; cleanup incl. cancel path. sub_sandbox: child dir `{run}/subagents/{step}/{worker_i}/`, shared-read parent refs, writes isolated. `merge_conflict` payload = conflicting paths + worker provenance + truncated hunks. on_conflict: human_gate (default, via `run_human_gate`→`_run_review_gate`) | merge_agent (bounded 2 then human_gate) | partial | abort.
- **D-05 — BudgetManager in `budget.py`; per-run object on `ExecutionContext` (no singleton).** `reserve()` gates countable units before spawn; tokens/wall-clock check-at-boundary + mid-flight abort. `spent()→BudgetSnapshot` → `workflow_runs.budget_snapshot_json`. Per-workspace ceilings via settings seam (default unset). Locked numbers: subagents=8, concurrency=4, depth=2, wall=900s, merge_agent=2, warn@80% — module constants; file manifests may raise via `Limits`, user/db lower-only.
- **D-06 — `subagent_runs` (0019) mirrors `exec_runs` (0018) exactly:** §18 columns + owner_id, free-String status, ScopedStore default-deny, offline-reversible. Row at spawn (running) → terminal update. Best-effort `record_subagent_run` (None-degrading).
- **D-07 — `spawn_subagents` tool:** `@register` tool capability, `user_allowed=False` (CAP-03); bound only via tool_provider/intersection when the step grants `tools.spawn_subagents`. The deepagents `task` tool REMAINS excluded.
- **D-08 — Sample fan-out workflow is test-scoped** (sc001/sample_brownfield precedent): manifest + AGENT.md only, registered capabilities only (e.g. `fanout_batch` fanning 3 self-copies → distinct files, merged copy_disjoint). Proves SC-001.
- **D-09 — Plan sequencing:** follow the ROADMAP 5-plan sketch (11-01..11-05) sequentially (`use_worktrees=false`). Planner may re-cut boundaries provided each plan leaves the characterization suite green.
- **Locked numbers are constraints:** subagents=8 / concurrency=4 / depth=2 / wall=900s / merge_agent=2 / warn@80%; € dormant (no invented prices); panel→Phase-12.
- **Standing directive:** everything from `plan.md` honored — nothing dropped (Q12–Q20, §6, §12, §13, §18, §21, §23).

### Claude's Discretion
- Exact `FanoutSpec`/`allowed_workers` field names + compiler materialization details (additive, INV-5-pure; unknown keys still rejected).
- Exact event payload schemas within the locked `subagent_*`/`merge_*`/`budget_warning` families.
- `subagent_runs` column types within §18's listed fields; index choices.
- Worktree branch naming + spawn-point capture mechanics; whether `IsolationProvider` impls register as capabilities (a registered `isolation` kind) or live as runtime-layer code bound via the §15 host seam — import-linter 4/0 is the gate either way.
- Whether `merge` strategies are kernel-side (pure-stdlib file ops) or app-side via the handle (git_3way needs the workspace handle regardless — the 08-04 heavy-dep boundary applies).
- Plan-task granularity within the 5-plan frame; where the 0019 migration rides (the plan that first writes rows — 11-05 per the sketch, or earlier if 11-01 needs the table for tests).

### Deferred Ideas (OUT OF SCOPE)
- Wave scheduler + `wave_runs` + mid-wave resume — Phase 12 (`Task.conflict_keys`/`depends_on` stay forward fields).
- Frontend subagent-tree panel + `GET /api/runs/{id}/subagents` — Phase 12 (this phase ships backing data: rows + lifecycle events + ScopedStore reads).
- `subagent_chunk` tagged child streaming — additive later.
- Real € price table + € ceiling enforcement — dormant; cost fields exist, enforcement deferred.
- Prototype parallelism via `html_fragment` merge — MERGE-01 v2 (strategy registers, wiring doesn't; prototype stays sequential).
- User-grantable `spawn_subagents` — CAP-03 ceiling unchanged.
- Durable job queue/worker for long fan-outs — N8 stays in-process (FastAPI task + asyncio).
- Per-workspace budget configuration UI — settings seam lands; UI is later work.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FANOUT-01 | `spawn_subagents` request-emitter tool, permission-bound, spawns nothing | Pattern 3 (tool-event derivation); D-07 (`user_allowed=False`, tool_provider binding); Pitfall 1 (spawn-free grep). Concrete tool in `app/agents/tools/runner_tools.py`, capability in `tools/providers.py`. |
| FANOUT-02 | one kernel `run_fanout`; both entry points funnel through it | Architecture diagram (both paths → `run_fanout`); D-02; `KernelServices.run_fanout` handle method. Grep-asserted single spawn path. |
| FANOUT-03 | worker selection (self×N / named via `allowed_workers` + registry) | `run_fanout` step 1; compiler materializes `allowed_workers`; registry `resolve`/`is_registered`. Disallowed → structured error pre-spawn. |
| FANOUT-04 | modes + `max_concurrency` (semaphore-capped gather / sequential) | Architecture diagram step 4; `asyncio.Semaphore(min(declared, 4))`; trust-conditional clamp via compiler `Limits` rule (compiler.py:323-356 precedent). |
| FANOUT-05 | engine-decided isolation (shared_read/sub_sandbox/worktree) | `IsolationProvider.allocate` grows scopes (runtime/base.py:132); `LocalWorkspace` worktree methods; engine selects scope (has_git→worktree). owner/workspace stamped (create_workspace pattern). |
| FANOUT-06 | results = typed/lineage artifacts + structured summary | Fragment artifacts persisted BEFORE merge (D-04); `ArtifactGraph`/`ArtifactRef` + `ScopedStore.write_ref`; summary returned to caller. |
| FANOUT-07 | `MergeStrategy` port + 4 registered impls | New `merge/` package; port mirrors `capabilities/base.py` idiom; `@register("merge", name)`; copy_disjoint deterministic, overlap→conflict (Pitfall 6). |
| FANOUT-08 | merge-conflict flow + 4 on_conflict policies | D-04; `merge_conflict` ArtifactRef (kind already allowed) + event; human_gate via `run_human_gate`→`_run_review_gate`; merge_agent ≤2 (Pitfall 8). |
| FANOUT-09 | `BudgetManager` reserve-before-spawn | `budget.py` (D-05); reserve first in `run_fanout` (Pitfall 4); module-constant defaults; depth via `ctx.depth`; graceful abort with partial. |
| FANOUT-10 | `subagent_runs` persistence + events | `0019` migration (0018 recipe, Pattern 4); `SubagentRun` ORM; `ScopedStore.record_subagent_run`; events via generic forward (D-03). |
| FANOUT-11 | cancellation propagates to children | Cancel checks at fanout boundaries (RESUME-01 code example); in-flight `asyncio` task cancel; pending never spawn; rows→cancelled; teardown (Pitfall 5). |
| OBS-01 | per-run + per-workspace ceilings + persisted snapshot | D-05; per-workspace ScopedStore aggregate at reserve; `BudgetSnapshot`→`budget_snapshot_json` (0014 column live) on complete/abort/cancel. |
| RESUME-01 | cooperative cancel at fanout boundaries + teardown | `cancel_event` checks before wave / between sequential / before merge; `finally` teardown of every isolated workspace (incl. worktree remove + branch delete). Zero-residue acceptance. |
</phase_requirements>

## Sources

### Primary (HIGH confidence — verified in this session)
- `backend/agents/runtime/base.py` — `IsolationProvider`/`Workspace`/`RuntimeEnvironment` ports (sub_sandbox/worktree explicitly Phase-11 growth points)
- `backend/app/agents/runtime/local.py` — `LocalWorkspace` (single git-subprocess owner `_git`; clone/branch/diff; teardown; create_workspace `has_git`/`exec`/`recorder`)
- `backend/agents/execution_engine/context.py` — `ExecutionContext` (`depth:168`, `cancel_event:157`, `runner`/`scoped_store`/`workspace_id` fields)
- `backend/agents/execution_engine/kernel_services.py` — `run_agent:568`, `record_exec_run:358`, `run_human_gate:475`, `make_fix_policy:432`, `deliverable_context:446` (the handle pattern to extend)
- `backend/agents/execution_engine/engine.py` — dispatch loop (strategy resolve:1316, post_step:1345, cancel checks:1261, exec-workspace gated provisioning:1200-1226, emit/append_event:124)
- `backend/agents/capabilities/base.py` — port idiom (`ExecutionStrategy:44` names `fanout_batch`; `MergeStrategy` follows the one-method-Protocol idiom)
- `backend/agents/capabilities/strategies/task_loop.py` — the strategy precedent `fanout_batch` mirrors (handle-only reach, registry resolve, no kernel/app import)
- `backend/agents/capabilities/tools/providers.py` — `@register("tool", ...)` ToolProvider pattern (`spawn_subagents` follows, `user_allowed=False`)
- `backend/agents/capabilities/registry.py` — `_KNOWN` set (53 entries) + `@register`/`user_allowed`/`is_user_allowed`/lockstep
- `backend/agents/workflows/plan.py` — `FanoutSpec:196`, `Limits:231`, `Task.conflict_keys:300`, `Step.fanout:336`/`on_conflict:337`, `ToolPermissions.spawn_subagents:73`, intersect/lower helpers
- `backend/agents/workflows/compiler.py` — `_ALLOWED_STEP_KEYS:63` (fanout/on_conflict/depends_on accepted, FanoutSpec never materialized), trust ceiling + privileged-grant rules:218-356
- `backend/agents/authz.py` — `ScopedStore` (default-deny, `record_exec_run`, `create_workspace`, `write_ref`, `append_event`)
- `backend/alembic/versions/0018_exec_runs.py` — the exact `0019` recipe (additive, named FK, free-String status, reversible)
- `backend/pyproject.toml` — the 4 import-linter forbidden contracts (capability/workflow/runtime ↛ kernel/app)
- `backend/tests/agents/test_banned_patterns.py` — INV-13/INV-1 ratchet (no 2nd create_deep_agent; kernel name-branch hard-fail)
- `backend/tests/agents/test_migration_ledger.py` + `specs/003-workflow-engine-decoupling/migration-ledger.md` — additive-chain ratchet + format
- `backend/tests/agents/test_sc001_nonprototype_task_loop.py` + `tests/agents/fixtures/sc001_task_loop/` — the SC-001 test-scoped-fixture precedent (D-08)
- `backend/CLAUDE.md` — per-worker thread_id convention; `report_task_complete` store-free tool-event derivation; `task` tool excluded
- `.planning/phases/11-engine-owned-fan-out-merge-5/11-SPEC.md` + `11-CONTEXT.md` — the 13 locked requirements + 9 implementation decisions
- `python3.11 -c "import deepagents"` → 0.6.7 (INV-13 runtime confirmed)

### Secondary (MEDIUM confidence)
- `specs/003-workflow-engine-decoupling/plan.md` §6/§12/§13/§18/§21/§23 (referenced via CONTEXT canonical-refs; not re-read line-by-line this session — CONTEXT's distillation treated as authoritative)

### Tertiary (LOW confidence)
- None — all claims grounded in inspected code or locked CONTEXT/SPEC decisions.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new packages; `deepagents==0.6.7` verified live; all seams inspected.
- Architecture: HIGH — every integration point (dispatch loop, handle, ports, registry, compiler, migration recipe, import contracts) read this session. The one MEDIUM item (tool-interception mechanism, A1) is flagged in the Assumptions Log with a planner directive.
- Pitfalls: HIGH — derived from the live CI gates (banned-patterns, import-linter, characterization, migration-ledger) and the locked CONTEXT decisions.

**Research date:** 2026-06-10
**Valid until:** 2026-07-10 (stable brownfield; codebase on an active feature branch — re-verify the dispatch loop line numbers if `engine.py` churns before planning)
