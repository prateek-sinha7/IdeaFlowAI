# Phase 12: Wave Scheduler + Durable Resume [6] - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 13 (8 new, 5 grown)
**Analogs found:** 13 / 13 (every named surface verified in-codebase this session)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/agents/capabilities/strategies/wave_scheduler.py` (+ pure `build_waves`) | strategy / capability | event-driven (per-wave fan-out) | `strategies/fanout_batch.py` | exact (clone) |
| `backend/agents/capabilities/task_parsers/json_tasks.py` | task_parser / capability | transform (text → list[Task]) | `task_parsers/heading_tasks.py` | exact (clone) |
| `backend/alembic/versions/0020_wave_runs.py` | migration | batch / DDL | `alembic/versions/0019_subagent_runs.py` | exact (clone) |
| `backend/app/models/wave_run.py` | model (ORM) | CRUD | `app/models/subagent_run.py` | exact (clone) |
| `backend/agents/authz.py` `record/update/read_wave_runs` | store (ScopedStore) | CRUD (default-deny) | `authz.py` `record/update_subagent_run` | exact (clone) |
| `backend/agents/execution_engine/kernel_services.py` `record/update_wave_run` | service handle | CRUD (best-effort) | `kernel_services.py` `record_subagent_run` | exact (clone) |
| `backend/agents/workflows/plan.py` `RetryPolicy.on` | model (dataclass field) | config (additive) | `plan.py` `RetryPolicy` | exact (grow) |
| `backend/agents/execution_engine/engine.py` retry wrapper (D-10) | controller (dispatch loop) | request-response (retry/reuse) | `engine.py` `strategy.run(step, ectx)` site (~1402) | role-match (grow) |
| `backend/agents/execution_engine/engine.py` `resume_run` (D-06) | controller (resume entry) | event-driven (re-enter loop) | `engine.py` per-step dispatch loop + `compile_for_run` | role-match (grow) |
| `backend/agents/execution_engine/engine.py` `restore_non_terminal_runs` 3-way (D-08) | controller (startup driver) | batch (startup scan) | `engine.py` `restore_non_terminal_runs` (2847) | exact (grow) |
| `backend/app/api/websocket.py` `reconnect_pipeline` after_seq branch | route handler | streaming / replay | `websocket.py` `reconnect_pipeline` (560) + `authz.read_events` (314) | exact (grow) |
| `agents/workflows/<sample-wave>/` manifest + AGENT.md | config (fixtures) | declarative | `agents/workflows/sample_fanout/` | exact (clone) |
| `frontend/.../WaveTreePanel.tsx` + `WorkflowComposer.tsx` mount + `DashboardLayout.tsx` after_seq | component | event-driven (render) | `AgentProgressPanel.tsx` / `ValidatorIssuePanel` + `DashboardLayout.tsx:521` | role-match |

## Pattern Assignments

### `strategies/wave_scheduler.py` (strategy, event-driven) — clone `fanout_batch.py`

**Analog:** `backend/agents/capabilities/strategies/fanout_batch.py` (read in full).

**Imports + registration + purity** (lines 22-49):
```python
from __future__ import annotations
import logging
from typing import Any, AsyncIterator
from agents.capabilities.registry import CapabilityRegistry, register
# NOTHING from agents.execution_engine or app.* — kernel reached only via ctx.runner (import-linter gate)

@register("strategy", "wave_scheduler", user_allowed=True)   # D-05: matches fanout_batch trust
class WaveSchedulerStrategy:
    name = "wave_scheduler"
    def __init__(self) -> None:
        self._registry = CapabilityRegistry()
```

**Source-tasks → requests → run_fanout** (lines 50-93) — the LOAD-BEARING template. The wave loop wraps this body, calling `runner.run_fanout` ONCE per wave (D-01):
```python
async def run(self, step, ctx):
    runner = ctx.runner
    task_source = getattr(step, "task_source", None)
    source_step = getattr(task_source, "source_step", None) if task_source else None
    plan_output = runner.latest_typed_content(source_step) or "" if source_step else ""
    parser_name = task_source.parser if (task_source and task_source.parser) else "json_tasks"  # default differs
    parser = self._registry.resolve("task_parser", parser_name)
    tasks = parser.parse(plan_output)
    waves = build_waves(tasks)            # NEW pure fn — raises on cycle/unknown ref PRE-spawn (zero rows)
    for wave_index, wave in enumerate(waves):
        # D-07 mid-wave skip: if terminal wave_runs row exists → skip; else filter to incomplete workers
        requests = [{"agent": "self", "input": t.body} for t in wave]
        # record_wave_run(running) via best-effort ctx.runner handle, BEFORE spawn
        async for event in runner.run_fanout(requests, ctx, step=step):  # ONE call per wave (INV-12)
            yield event
        # update_wave_run(terminal) after merge completes/fails
```

**`build_waves` pure seam** (NEW, stdlib-only, in same module) — RESEARCH Pattern 2 is the recommended Kahn-levels + conflict-key-split shape; D-03 LOCKS: stable tie-break by task id, raise-before-spawn on cycle/unknown ref, overlapping `conflict_keys` never co-schedule. Discretion (A2): default `conflict_keys` to `targets` when empty — DOCUMENT in docstring.

---

### `task_parsers/json_tasks.py` (task_parser, transform) — clone `heading_tasks.py`

**Analog:** `backend/agents/capabilities/task_parsers/heading_tasks.py` (read in full).

**Imports + registration + purity** (lines 16-21, 89, 98-100):
```python
from __future__ import annotations
import json   # heading_tasks uses re; json_tasks uses json
from agents.capabilities.registry import register
from agents.workflows.plan import Task   # stdlib + plan.Task ONLY — never execution_engine/app

@register("task_parser", "json_tasks")   # D-05: default trust (matches heading_tasks)
class JsonTasksParser:
    name = "json_tasks"
    def parse(self, text: str) -> list[Task]:   # pure text -> list[Task], no engine state
        ...
```

`json_tasks` differs: parses a JSON array (tolerate a fenced ```json block + a `tasks:` wrapper key — discretion A4), validates `depends_on` refs naming the offender (raise on unknown), populates `targets`/`depends_on`/`conflict_keys`/`done_when`. **Do NOT edit `heading_tasks.py`** — empty git diff is a SPEC req-2 acceptance.

---

### `alembic/versions/0020_wave_runs.py` (migration, DDL) — clone `0019` verbatim (D-16)

**Analog:** `backend/alembic/versions/0019_subagent_runs.py` (read in full).

**Revision chain + table recipe** (lines 30-61):
```python
revision = "0020"
down_revision = "0019"          # single head, unbroken chain
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("wave_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("wave_index", sa.Integer(), nullable=False),
        sa.Column("task_ids", sa.JSON(), nullable=False),         # §18 line 709
        sa.Column("status", sa.String(), nullable=False),         # free String, NO sa.Enum
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),  # NAMED (alembic-check drift-free)
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_wave_runs_run", "wave_runs", ["run_id"])

def downgrade() -> None:
    op.drop_index("ix_wave_runs_run", table_name="wave_runs")
    op.drop_table("wave_runs")
```
Verify offline: in-memory SQLite upgrade head → downgrade -1 → upgrade head. Update migration-ledger in the SAME commit.

---

### `app/models/wave_run.py` (model ORM) — clone `subagent_run.py` (D-16)

**Analog:** `backend/app/models/subagent_run.py` (read in full).

**ORM shape** (lines 19-50) — UUID PK default, named FK to `workflow_runs.id`, free-String `status`, `Index` in `__table_args__`, `Base` from `app.models.database`:
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.types import JSON
from app.models.database import Base

class WaveRun(Base):
    __tablename__ = "wave_runs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    step = Column(String, nullable=False)
    wave_index = Column(Integer, nullable=False)
    task_ids = Column(JSON, nullable=False)          # §18 task_ids[]
    status = Column(String, nullable=False)          # running|completed|failed|cancelled (free String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (Index("ix_wave_runs_run", "run_id"),)
```

---

### `authz.py` ScopedStore `record/update/read_wave_runs` (store, CRUD) — clone `*_subagent_run`

**Analog:** `backend/agents/authz.py` `record_subagent_run` (939-980), `update_subagent_run` (982+), `read_events` (314-329 — the scope-filter model).

**Default-deny writer** (939-980): `self._acquire()` session, stamp `owner_id=self._owner_id` + `workspace_id=self._workspace_id` on the row, `session.add`/`commit`, `finally: if owned: session.close()`. Updater resolves the row under the owner+workspace scope (cross-owner = no-op). Reader applies `self._scope_owner_ws(query, WaveRun)` so cross-owner read = ∅. Mirror `read_events` (314-329) for the seq-ordered/scoped read pattern the mid-wave-resume reads also use.

---

### `kernel_services.py` `record/update_wave_run` (service handle, best-effort CRUD) — clone `record_subagent_run`

**Analog:** `backend/agents/execution_engine/kernel_services.py` `record_subagent_run` (410-449).

**None-degrading best-effort wrapper** (430-449) — offline-safe; audit NEVER aborts the run:
```python
store = getattr(self._ectx, "scoped_store", None)
if store is None:
    return None
try:
    return await store.record_wave_run(self.run_id, step=..., wave_index=..., task_ids=..., status="running")
except Exception as exc:  # noqa: BLE001 — audit must NEVER abort the run
    logger.warning("record_wave_run(...) failed: %s", exc)
    return None
```
NOTE (RESEARCH Open Q3): the restart-simulation test must bind a REAL in-memory SQLite store, not the None-degrading offline default, or it cannot prove mid-wave skip.

---

### `plan.py` `RetryPolicy.on` (model field, additive) — grow `RetryPolicy`

**Analog:** `backend/agents/workflows/plan.py` `RetryPolicy` (219-224):
```python
@dataclass
class RetryPolicy:
    max_attempts: int = 0
    backoff_seconds: float = 0.0
    on: list[str] = field(default_factory=lambda: ["transient"])   # ADD (D-12, SPEC-locked default)
```
`Task.depends_on`/`conflict_keys`/`targets` (314-316) already exist as forward fields — wave_scheduler is their ONE consumer (no parallel config surface; migration-ledger watch).

---

### `engine.py` retry wrapper + `resume_run` + `restore_non_terminal_runs` (controller) — grow engine

**Analog (dispatch site):** `engine.py` ~1401-1403 — the SINGLE per-step strategy dispatch:
```python
strategy = _registry.resolve("strategy", strategy_name)
async for event in strategy.run(step, ectx):
    yield event
```
- **D-10 retry wrapper** wraps THIS site only. Gate strictly on `step.retry and step.retry.max_attempts > 0` (absent/None = byte-identical today — Pitfall 4). Before every (re-)execution compute `input_hash` (D-11: `json.dumps(sort_keys=True, separators=(",",":"))` over sorted upstream `content_hash`es + resolved input string — Pitfall 1) and reuse-check via `run_events` payload (RESEARCH Open Q1 RESOLVED: store `input_hash` in `run_events` payload, NOT ArtifactRef). Transient classify via `_is_transient_throttle` (`model_policy.py:214`); patchable sleep seam for `backoff_seconds`; emit `step_retry` per attempt.
- **D-06 `resume_run(run_id)`** re-enters the SAME `for i, spec in enumerate(ordered_agents)` loop (engine.py ~1346) at the first-incomplete OFFSET — NO forked path (Pitfall 2). Rebuild `ExecutionContext` via `compile_for_run` (199) + the same rebind sequence `execute()` uses; extract a shared builder to avoid copy-paste drift.

**Analog (startup driver):** `engine.py` `restore_non_terminal_runs` (2847-2910+):
- `NON_TERMINAL` list (2866-2869); WR-05 abandoned→failed loop (2880-2906+) kept VERBATIM as fallback (branch c).
- D-08 three-way: (a) `waiting_for_user` → re-arm resume event (unchanged, 2893-2901); (b) resumable in-flight → stamp BEFORE `asyncio.create_task(resume_run(...))` (Pitfall 3 double-drive guard), emit resume marker (RESEARCH Open Q2: prefer event-marker over a new status value — avoids touching NON_TERMINAL/state-machine); (c) else WR-05.

**Emit boundary** (engine.py ~540-553): all `wave_*`/`step_retry`/resume events are plain dicts yielded from the engine; the boundary stamps `seq`/`event_id` + persists to `run_events` → generic WS forward (zero websocket.py forwarding edits, 08-08).

---

### `websocket.py` `reconnect_pipeline` after_seq branch (route, streaming/replay) — grow handler

**Analog:** `backend/app/api/websocket.py` `reconnect_pipeline` (560-605, in-memory queue attach only) + `authz.read_events` (314-329).

Add a durable replay branch BEFORE the live-queue attach (RESEARCH Code Example, placement A3 = planner's call):
```python
after_seq = message_data.get("after_seq", 0)
# replay durable tail via owner-scoped ScopedStore.read_events(run_id, after_seq) ordered seq asc;
# send each as {"type": r.type, "data": r.payload_json}; FE dedups by event_id.
# then attach to the live queue if still running (existing 566-604 path);
# if restarted (no live task) the replayed tail + run status is the complete response.
```
Existing `_PIPELINE_TASKS`/`_PIPELINE_QUEUES` lookups (563-564) unchanged. Legacy reconnect (no `after_seq`) behaves as today (parity).

---

### Sample wave workflow (config fixtures) — clone `sample_fanout/` (D-17)

**Analog:** `agents/workflows/sample_fanout/`. Manifest + AGENT.md at `agents/workflows/<name>/`, ONLY registered capabilities (`wave_scheduler`, `json_tasks`, existing merge impls); a planner-style step emits the JSON task list; ≥2 waves, ≥2 parallel workers in one wave, disjoint targets merged `copy_disjoint`. Acceptance: `grep <name> agents/execution_engine/` = 0 (SC-001, zero engine edits).

---

### FE `WaveTreePanel.tsx` + mount + reconnect (component) — clone `AgentProgressPanel`/`ValidatorIssuePanel` (D-15)

**Analogs:**
- `frontend/src/components/workflow/AgentProgressPanel.tsx` (1-45) — props-driven panel: `"use client"`, `motion/react`, typed `...Props` interface, inner card components. Structural model for wave-group → worker-leaf rendering (lifecycle statuses ONLY, no `subagent_chunk` — D-14).
- `frontend/src/components/workflow/WorkflowComposer.tsx` — sibling-panel mount precedent: imports `ValidatorIssuePanel` (line 8), renders `<ValidatorIssuePanel issues={...} />` (line 285). Mount the new `<WaveTreePanel ... />` the same additive way; modify NO existing panel.
- `frontend/src/components/layout/DashboardLayout.tsx` (494, 521) — the `reconnect_pipeline` send site. GROW: track last-received `seq` per run, send it as `after_seq` in the existing message (521), dedupe applied events by `event_id` at the message handler.

Visual render is human-verified (08-08 Task-3 precedent — no headless DOM harness).

## Shared Patterns

### Capability import purity (import-linter, 4 kept / 0 broken)
**Source:** `fanout_batch.py:15-20` docstring + `heading_tasks.py:10-13` import block
**Apply to:** `wave_scheduler.py`, `json_tasks.py` — import ONLY `agents.capabilities.registry` (+ `agents.workflows.plan.Task` for the parser, + the local pure `build_waves`); NEVER `agents.execution_engine`/`app.*`. Kernel reached only via `ctx.runner`.

### Default-deny owner/workspace scoping (AUTHZ-01)
**Source:** `authz.py` `record_subagent_run` (939-980) + `_scope_owner_ws` (used at 325)
**Apply to:** every `wave_runs` write/read — stamp `owner_id`+`workspace_id`, filter reads through `_scope_owner_ws` so cross-owner = ∅.

### Best-effort offline-safe recording
**Source:** `kernel_services.py` `record_subagent_run` (430-449)
**Apply to:** `record/update_wave_run` — `getattr(self._ectx,"scoped_store",None)` None-guard + `try/except` that logs and returns None; audit never aborts the run.

### Single emit boundary → durable + WS forward (zero websocket edits)
**Source:** `engine.py` ~540-553
**Apply to:** all new `wave_*`/`step_retry`/resume/`step_reused` events — yield plain dicts; boundary stamps `seq`/`event_id`, persists to `run_events`.

### Additive parity (5-snapshot characterization stays green)
**Source:** the gate suite (`test_characterization_*`, `test_migration_ledger`, `test_banned_patterns`, `lint-imports`)
**Apply to:** every plan — existing workflows declare no waves/no retry/never restart-resume; gate every new path on declared opt-in (retry on `max_attempts>0`, resume on classification branch b, `wave_runs` writes inside the strategy only). Run snapshots with `SNAPSHOT_UPDATE` unset after each plan.

### Registry `_KNOWN` lockstep ratchet 59 → 61
**Source:** `registry.py` `_KNOWN` set (78-138; `("strategy","fanout_batch")`=81, `("task_parser","heading_tasks")`=101 are the exact insertion neighbors)
**Apply to:** add `("strategy","wave_scheduler")` + `("task_parser","json_tasks")`; update the lockstep assertion in `tests/agents/test_registry_capabilities.py` in the SAME commit.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | Every named surface was verified in-codebase; the only genuinely new logic without a clone is the pure `build_waves` Kahn-levels function (RESEARCH Pattern 2 supplies the recommended shape; D-03 locks determinism) and the `resume_run` offset computation (re-uses the existing dispatch loop + `compile_for_run`). |

## Metadata

**Analog search scope:** `backend/agents/capabilities/{strategies,task_parsers}`, `backend/agents/execution_engine`, `backend/agents/authz.py`, `backend/agents/workflows/plan.py`, `backend/alembic/versions`, `backend/app/models`, `backend/app/api/websocket.py`, `backend/agents/capabilities/registry.py`, `frontend/src/components/{workflow,layout,results}`
**Files scanned:** 13 analogs read; FE panel/reconnect sites located via grep
**Pattern extraction date:** 2026-06-11
