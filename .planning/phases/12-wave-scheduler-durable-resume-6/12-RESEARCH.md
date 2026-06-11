# Phase 12: Wave Scheduler + Durable Resume [6] - Research

**Researched:** 2026-06-11
**Domain:** Deterministic topological wave scheduling over an existing fan-out kernel + durable in-process resume (idempotent retry, WS reconnect replay, step-granular restart resume) + an additive FE wave/subagent tree panel.
**Confidence:** HIGH

## Summary

This is a **brownfield extension phase with an unusually low ambiguity budget (0.14)**: the SPEC locked 8 requirements and the CONTEXT locked all four HOW gray areas (D-01..D-18) to plan-grounded recommendations. The research task was therefore primarily **verification** — confirming that every code surface the locked decisions depend on exists exactly as described, and resolving the two explicit researcher directives the CONTEXT delegated to this phase (the D-11 `input_hash` storage spot, and the riskiest D-06 resume-re-entry mechanics). **Every named surface was verified in the codebase this session.** [VERIFIED: codebase grep]

The work decomposes into three durable, additive layers stacked on Phase 11's `run_fanout`: (1) a registered `wave_scheduler` strategy + `json_tasks` parser + additive `0020 wave_runs` migration that topo-sorts tasks into deterministic parallel waves and drives each wave through the **unmodified** `ctx.runner.run_fanout(requests, ctx, step=step)` (one spawn path, INV-12); (2) an engine-side retry wrapper around the single per-step `strategy.run(step, ectx)` dispatch site keyed by `(run_id, step_id, input content_hash)` reusing existing artifacts on hash match; (3) a durable resume tier — WS `reconnect_pipeline` gaining an `after_seq` replay branch over `ScopedStore.read_events`, and `restore_non_terminal_runs` gaining a three-way startup classification that re-drives resumable runs in-process from the first incomplete step (mid-wave via `wave_runs`/`subagent_runs`). An additive props-driven FE tree panel renders the new `wave_*`/`subagent_*` lifecycle events.

**Primary recommendation:** Build strictly additively on the verified surfaces — clone `fanout_batch.py` for the strategy, `heading_tasks.py` for the parser, `0019_subagent_runs.py` + `ScopedStore.record_subagent_run`/`update_subagent_run`/`read_subagent_runs` for `wave_runs`, and the engine's single seq/event_id emit boundary (engine.py ~540-553) for all new events. Store the retry/restart `input_hash` in the **`run_events` payload** (NOT a new ArtifactRef field — there is no free meta slot; resolving the D-11 directive). Treat D-06 (resume re-entry) and D-11 (cross-restart hash stability) as the two highest-risk items and write the restart-simulation test first.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Topological wave partitioning (`build_waves`) | Capability (strategy module, pure fn) | — | Control flow lives in strategies (INV-5); pure stdlib seam is separately unit-testable + the CP-SAT swap point (D-03) |
| Wave loop / per-wave fan-out dispatch | Capability (`wave_scheduler` strategy) | Kernel (`run_fanout` via `ctx.runner`) | Strategy owns the loop; kernel owns spawn/isolation/merge/budget/cancel — reached only through `ctx.runner` (INV-5/INV-12) |
| `wave_runs` persistence | Kernel (`KernelServices.record_wave_run` best-effort) → ScopedStore (default-deny) | Migration `0020` / ORM | Every new table carries `owner_id`+`workspace_id`; recorder degrades to None offline (record_subagent_run precedent) |
| Idempotent step retry + content-hash reuse | Kernel (engine dispatch-loop wrapper) | `_is_transient_throttle` classifier | One retry home (INV-12); reuse check at the single per-step dispatch boundary |
| Durable WS reconnect replay | API/Backend (`app/api/websocket.py`) | ScopedStore.read_events (durable) | The in-memory queue lives in the WS layer; durable tail comes from `run_events` via the owner-scoped store |
| Step-granular restart resume | Kernel (engine `restore_non_terminal_runs` + a resume entry) | ScopedStore (`wave_runs`/`subagent_runs`/`artifact_refs` reads) | The driver and dispatch loop are engine-owned; resume rebuilds `ExecutionContext` and re-enters the SAME loop (INV-12, no forked path) |
| FE wave/subagent tree render | Frontend (props-driven sibling panel) | FE WS client (`after_seq`+dedup) | Pure render off lifecycle events; 08-08 sibling-panel reuse pattern |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Area A — Wave execution & merge cadence (WAVE-01/02):**
- **D-01:** The wave loop lives INSIDE the `wave_scheduler` strategy. It sources tasks via the declared `TaskSource` (parser `json_tasks`), calls the wave-builder seam, then iterates waves **sequentially**; each wave's tasks become worker requests submitted as ONE `ctx.runner.run_fanout(...)` call per wave. Kernel `run_fanout` is NOT modified — single spawn path (INV-12). *Rejected:* a new kernel-side wave loop, or per-task `run_fanout` calls.
- **D-02:** Per-wave merge INTO the base workspace BEFORE the next wave starts (engine-selected merge strategy keyed on isolation scope, the 11-03 dispatch). Fragments still persist as artifacts BEFORE merge (P11 D-04) — this is what mid-wave resume reuses.
- **D-03:** CP-SAT seam = a PURE FUNCTION, not a new capability kind: `build_waves(tasks: list[Task]) -> list[list[Task]]` — Kahn topological levels over `depends_on`, stable tie-break by task id, within-level splitting so overlapping `conflict_keys` never co-schedule (overlap spills to later waves deterministically). Cycles/unknown refs raise BEFORE any spawn (zero `wave_runs`/`subagent_runs` rows). Lives as a separately-unit-testable function in the strategy module (kernel-pure, stdlib-only).
- **D-04:** `wave_runs` row lifecycle — one row per executed wave, written at wave start (`running`, with step + wave_index + task_ids) and updated terminal (`completed`/`failed`/`cancelled`) after the wave's merge completes/fails; via a best-effort `KernelServices` handle (None-degrading, offline-safe). `wave_started`/`wave_completed`(+`wave_failed`) events ride the generic WS forward + single emit boundary.
- **D-05:** `@register("strategy", "wave_scheduler", user_allowed=True)`; `@register("task_parser", "json_tasks")` default trust. `_KNOWN` lockstep 59 → 61.

**Area B — Restart re-entry (RESUME-04 + WAVE-03) — riskiest:**
- **D-06:** A dedicated engine resume entry (e.g. `resume_run(run_id)` — exact name planner's call) invoked by `restore_non_terminal_runs` per resumable run via `asyncio.create_task` (in-process, N8 v1). Rebuilds `ExecutionContext` as `execute()` does (re-compile via `compile_for_run`, rebind owner/workspace/capabilities/budget, re-acquire checkpointer), computes the first incomplete step, enters the SAME per-step dispatch loop from that offset — NO forked execution path (INV-12).
- **D-07:** "First incomplete step" derives from EXISTING durable surfaces — NO new step-status table. A step is complete iff its typed artifacts exist (`artifact_refs` by producer step) and/or its terminal step events appear in `run_events`; for wave steps, terminal `wave_runs` rows give completed waves and terminal `subagent_runs` rows + fragment artifacts give completed workers within the in-flight wave. Mid-wave resume: completed waves skipped; in-flight wave re-enters `run_fanout` with only workers lacking terminal rows/fragments.
- **D-08:** Three-way startup classification, WR-05 kept verbatim as fallback: (a) `waiting_for_user` → re-arm resume event (unchanged); (b) resumable in-flight runs → auto-resume per D-06, emitting a resume event; (c) anything else → WR-05 abandoned→failed. Double-drive guard: classification once at startup (single-process v1); run stamped BEFORE the driver task starts. Cross-process locks OUT of scope.
- **D-09:** Checkpointer posture: reuse the per-agent LangGraph thread where the `{run_id}:{agent}`/`:task` convention matches; when absent/stale, re-run the step idempotently (the Req-5 content-hash reuse makes re-run cheap).

**Area C — Retry wrapper & hash mechanics (RESUME-02):**
- **D-10:** ONE retry wrapper in the engine dispatch loop around per-step strategy execution (single home, INV-12) — NOT inside strategies, NOT per-worker inside `run_fanout`. Activates ONLY when the compiled step declares `retry.max_attempts > 0` — absent/None = byte-identical today.
- **D-11:** `input content_hash` = sha256 over the step's RESOLVED input: the consumed upstream artifacts' existing `content_hash`es + the step's resolved task/prompt input string, canonically serialized. The reuse check runs BEFORE every (re-)execution — first attempts, retry re-entries, AND restart re-runs. A completed artifact keyed `(run_id, step_id, input_hash)` → skip execution, reuse, emit the skip/reuse event. *Researcher confirms the storage spot for input_hash* (RESOLVED below — see Open Questions / D-11 resolution).
- **D-12:** `RetryPolicy.on` gains `["transient"]` default; transient classification REUSES the 06-03 `_is_transient_throttle` family. `backoff_seconds` honored via a patchable sleep seam. `step_retry` emitted per attempt.

**Area D — FE tree data sourcing (§22; clears 08-08 deferral):**
- **D-13:** Events-only data plane. The tree derives ENTIRELY from `wave_*` + `subagent_*` lifecycle events — live via WS, historical via durable replay (`after_seq` from 0 on fresh load; from last-seen seq on reconnect). NO new REST tree endpoint this phase.
- **D-14:** Lifecycle statuses ONLY — no `subagent_chunk`. Panel renders wave groups (index, task ids, status) → worker leaves (agent, status). No live worker token streams.
- **D-15:** Panel = additive props-driven sibling in `WorkflowComposer.tsx` (08-08 D-11 reuse pattern; `ValidatorIssuePanel`/`AgentProgressPanel` structural models). FE reconnect: track last-received `seq` per run, send as `after_seq` in `reconnect_pipeline`, dedupe by `event_id`. No existing panel modified. Visual render human-verified.

**Supporting:**
- **D-16:** `0020` migration recipe = the `0018`/`0019` recipe verbatim: additive, `down_revision=0019`, §18 columns + `owner_id`/`workspace_id`, free-String status (no `sa.Enum`), named FKs, offline-reversible; `WaveRun` ORM on `Base.metadata`; ScopedStore default-deny writer/updater/readers; migration-ledger/lockstep ratchets updated in the same commit.
- **D-17:** Sample wave workflow is test-scoped (sc001/sample_fanout precedent): manifest + AGENT.md at `agents/workflows/<name>/`, ONLY registered capabilities; ≥2 waves, ≥2 parallel workers in one wave, disjoint target files merged `copy_disjoint`; `grep <name> agents/execution_engine/` = 0.
- **D-18:** Plan sequencing: ROADMAP 3-plan sketch (12-01 / 12-02 / 12-03) **plus FE tree work** — planner's call whether FE rides 12-03 or becomes 12-04 (update ROADMAP plan count via tools if so). Sequential execution; every plan leaves the 5-snapshot characterization suite green.

### Claude's Discretion
- Exact wave-builder function home/signature; `wave_*`/`step_retry`/resume event payload schemas (within locked additive families); `wave_runs` index choices within §18's columns.
- Exact resume-entry name/shape and the resume-marker mechanism (status value vs event) — D-06/D-08 fix semantics, planner fixes spelling.
- `input_hash` storage spot (ArtifactRef meta vs run_events payload) per the D-11 researcher directive — **RESOLVED: run_events payload (see below).**
- `json_tasks` accepted shapes beyond SPEC minimum (e.g. `tasks:` wrapper keys), and whether `targets` doubles as default `conflict_keys` when the latter is omitted (deterministic either way; document the choice).
- FE component naming/structure within the D-15 sibling-panel pattern.

### Deferred Ideas (OUT OF SCOPE)
- CP-SAT (or any smarter) wave builder — swaps in behind the D-03 pure-function seam.
- `GET /api/runs/{id}/subagents` / waves REST tree endpoint — additive later if replay-from-0 proves heavy.
- `subagent_chunk` live worker streaming — P11 D-03 rejection stands.
- Per-worker retry inside `run_fanout` — workers keep the P11 failed→merge/on_conflict flow; step-level retry only.
- Durable queue/worker substrate for long jobs — N8 stays in-process for local v1.
- Cross-node/distributed resume locks — single-node startup-only classification.
- Prototype parallelism via fragment-merge — MERGE-01 v2 (Q33); prototype manifest untouched.
- Real € price table + enforcement — still dormant.
- FE repo-diff viewer — separate 08-08 deferral.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WAVE-01 | `wave_scheduler` strategy topo-sorts by `depends_on`+`conflict_keys` into waves, runs each wave via fan-out; deterministic builder, CP-SAT seam | `fanout_batch.py` verified as exact structural template (declared TaskSource → registry parser → `ctx.runner.run_fanout(requests, ctx, step=step)`). `Task.depends_on`/`conflict_keys` exist as forward fields (`plan.py`). `build_waves` is a pure stdlib Kahn-levels function — no new dependency. |
| WAVE-02 | `wave_runs` persistence; multi-file workflow runs disjoint tasks in parallel waves; prototype sequential | `0019_subagent_runs.py` + `ScopedStore.record_subagent_run`/`update_subagent_run`/`read_subagent_runs` + `KernelServices.record_subagent_run` verified as the exact `wave_runs` recipe. `sample_fanout` precedent verified for D-17 sample. |
| WAVE-03 | Resume mid-wave via `subagent_runs`/`wave_runs` after restart | `run_fanout` already persists fragments before merge (P11 D-04) + writes terminal `subagent_runs` rows; mid-wave resume = re-enter `run_fanout` with only workers lacking terminal rows/fragments. `wave_runs` terminal rows give completed waves. |
| RESUME-02 | Idempotent per-step retry `retry:{max,on}` for transient errors, keyed `(run_id,step_id,input content_hash)`, reuses artifact on hash match | `RetryPolicy(max_attempts,backoff_seconds)` verified INERT in `plan.py`; gains `on` field. `_is_transient_throttle` verified at `model_policy.py:214`. `ArtifactRef.content_hash` = `sha256(content.utf-8)` verified at `graph.py:121`. Single dispatch site `strategy.run(step, ectx)` at engine.py ~1401. |
| RESUME-03 | Reconnect = durable replay from `run_events` via `after=<last_seq>`, idempotent by `event_id` | `ScopedStore.read_events(run_id, after_seq)` verified (`authz.py:314`); REST endpoint `GET /{workflow_id}/events?after=` verified (`runs.py`). WS `reconnect_pipeline` verified at `websocket.py:560` (in-memory only — gains the durable branch). |
| RESUME-04 | Restart = `restore_non_terminal_runs` extended to step granularity; `waiting_for_user` gates on user action; in-flight steps resume from checkpoint or re-run idempotently | `restore_non_terminal_runs` verified at `engine.py:2847` (WR-05 abandoned→failed path intact). `compile_for_run` (engine.py:199) verified for `ExecutionContext` rebuild. Per-step dispatch loop verified at engine.py ~1346-1438 — re-enterable at an offset. |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (`collections`, `hashlib`, `json`, `asyncio`) | 3.11 | Kahn topo-sort wave builder, content-hash, canonical serialization, in-process resume driver | INV-5/§26 N8 mandate: NO new external dependency for scheduling or resume — wave builder is stdlib-pure, resume is in-process `asyncio.create_task` |
| `deepagents` | 0.6.7 | Worker agent runtime (inherited via `run_fanout` → `create_runner`) | INV-13 mandate — verified installed (`python3.11 -c "import deepagents; print(deepagents.__version__)"` → `0.6.7`). NO new agent loop; workers spawn via the existing path only. |
| SQLAlchemy + Alembic | (existing) | `0020 wave_runs` additive migration + `WaveRun` ORM on `Base.metadata` | Additive-only (Q3); mirrors `0019` verbatim (D-16) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| React + `motion/react` | (existing FE) | Additive props-driven wave/subagent tree panel | D-15 — sibling of `AgentProgressPanel`/`ValidatorIssuePanel`; no new FE dependency |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib Kahn topo-sort | `graphlib.TopologicalSorter` (stdlib 3.9+) | `graphlib` gives topo order but NOT levels or stable tie-break or conflict-key within-level splitting; a hand-rolled Kahn-levels pass is simpler to make deterministic + separately testable + the CP-SAT swap point. Recommend hand-rolled (D-03). |
| in-process `asyncio.create_task` resume | external queue/worker (Celery/RQ/SQS) | OUT of scope (N8 v1 = in-process; durable queue is a deferred infra follow-up). Do NOT add. |
| CP-SAT (`ortools`) wave builder | the pure `build_waves` seam | Explicitly deferred (Q32/§27) — seam only this phase. Do NOT add `ortools`. |

**Installation:** **None.** This phase adds ZERO external packages — the runtime mandate (INV-13) plus the N8 in-process constraint plus the CP-SAT-seam-only constraint together forbid any new dependency. The only "install" is the additive `0020` Alembic migration (a code artifact, not a package).

**Version verification:** `deepagents==0.6.7` confirmed installed and importable. [VERIFIED: `python3.11 -c "import deepagents; print(deepagents.__version__)"` → `0.6.7`]

## Package Legitimacy Audit

> **Not applicable — this phase installs zero external packages.**

| Package | Registry | Disposition |
|---------|----------|-------------|
| (none) | — | No new packages. `deepagents==0.6.7` already installed + pinned (INV-13); no additions. |

**Packages removed due to slopcheck [SLOP] verdict:** none (none proposed).
**Packages flagged as suspicious [SUS]:** none.

*slopcheck was not run because no package install occurs in this phase. If the planner discovers a package need, gate it behind a `checkpoint:human-verify` task and run the legitimacy gate then.*

## Architecture Patterns

### System Architecture Diagram

```
                          ┌─────────────────────────────────────────────┐
  manifest + AGENT.md  →  │  compile_for_run(pipeline_type)              │
  (json_tasks source)     │     → CompiledWorkflow (steps, task_source)  │
                          └───────────────────┬─────────────────────────┘
                                              │
                          ┌───────────────────▼─────────────────────────┐
   engine.execute()  /    │  per-step dispatch loop (engine.py ~1346)    │
   resume_run(run_id) ───▶│  for spec in ordered_agents[OFFSET:]:        │   ◀── D-06 resume re-enters
                          │    ┌──────────────────────────────────────┐  │       at first-incomplete OFFSET
                          │    │ D-10 RETRY WRAPPER (if retry.max>0)   │  │
                          │    │  compute input_hash → reuse-check ───┼──┼──▶ run_events payload
                          │    │  strategy.run(step, ectx) ───────────┼──┼──┐ (input_hash stored here)
                          │    │  on transient err → backoff → retry  │  │  │
                          │    └──────────────────────────────────────┘  │  │
                          └─────────────────────────────────────────────┘  │
                                              │ (strategy = wave_scheduler) │
                          ┌───────────────────▼─────────────────────────┐  │
                          │  wave_scheduler.run(step, ctx)               │  │
                          │   tasks = json_tasks.parse(source content)   │  │
                          │   waves = build_waves(tasks)   ◀── PURE FN,  │  │
                          │     (Kahn levels + conflict_keys split;      │  │
                          │      cycle/unknown-ref → raise pre-spawn)    │  │
                          │   for wave in waves:  (sequential)           │  │
                          │     skip if wave_runs row terminal ◀─ mid-   │  │  resume
                          │     requests = [worker req per task]         │  │
                          │     record_wave_run(running) ────────────────┼──┼──▶ wave_runs (0020)
                          │     async for ev in ctx.runner.run_fanout(   │  │
                          │         requests, ctx, step=step): yield ev  │  │
                          │     (run_fanout: isolate→spawn→persist frag  │  │
                          │      →merge into base→subagent_runs rows)    │  │
                          │     update_wave_run(terminal)                │  │
                          └───────────────────┬─────────────────────────┘  │
                                              │ all events                  │
                          ┌───────────────────▼─────────────────────────┐  │
                          │ single emit boundary (engine.py ~540-553)    │  │
                          │  seq=next(counter); event_id=uuid;           │◀─┘
                          │  sink.persist(seq,event_id,type,data) ───────┼──▶ run_events (durable)
                          │  → generic WS forward (zero websocket edits)  │
                          └───────────────────┬─────────────────────────┘
                                              │
            ┌─────────────────────────────────┴──────────────────────────┐
            ▼                                                              ▼
  ┌──────────────────────┐                              ┌──────────────────────────────┐
  │ WS live queue        │                              │ reconnect_pipeline (after_seq) │ ◀── RESUME-03
  │ (_PIPELINE_QUEUES)   │                              │  replay read_events(seq>N)     │
  └──────────┬───────────┘                              │  then attach live OR (restart) │
             │                                          │  serve tail + status            │
             ▼                                          └──────────────┬─────────────────┘
  ┌────────────────────────────────────────────────────────────────────▼──────────────┐
  │ FE: WorkflowComposer → wave/subagent tree panel (D-15 sibling)                      │
  │   render wave_* / subagent_* events; dedup by event_id; reconnect sends after_seq   │
  └─────────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/agents/capabilities/
├── strategies/wave_scheduler.py     # NEW: @register strategy + pure build_waves() seam
└── task_parsers/json_tasks.py       # NEW: @register parser (depends_on/conflict_keys/targets)

backend/agents/execution_engine/
├── engine.py                        # GROW: retry wrapper (D-10), resume_run entry (D-06),
│                                    #       restore_non_terminal_runs 3-way classify (D-08)
└── kernel_services.py               # GROW: record_wave_run / update_wave_run handles

backend/agents/authz.py              # GROW: ScopedStore record/update/read_wave_runs (default-deny)
backend/agents/workflows/plan.py     # GROW: RetryPolicy.on field (additive)
backend/alembic/versions/0020_wave_runs.py   # NEW: additive migration (0019 recipe)
backend/app/models/wave_run.py       # NEW: WaveRun ORM on Base.metadata
backend/app/api/websocket.py         # GROW: reconnect_pipeline after_seq replay branch

agents/workflows/<sample-wave-name>/ # NEW: manifest + AGENT.md (test-scoped, SC-001)

frontend/src/components/workflow/
├── WorkflowComposer.tsx             # GROW: mount additive tree panel (line ~264 placeholder)
└── WaveTreePanel.tsx (or similar)   # NEW: props-driven sibling panel
frontend/src/components/layout/DashboardLayout.tsx  # GROW: reconnect sends after_seq (line ~521)
```

### Pattern 1: Strategy sources tasks → builds requests → funnels through run_fanout
**What:** The declarative entry — a strategy parses a task list and submits ONE `run_fanout` call per wave; the kernel owns all spawn machinery.
**When to use:** The `wave_scheduler` strategy body. Clone `fanout_batch.py` structure.
**Example:**
```python
# Source: backend/agents/capabilities/strategies/fanout_batch.py  [VERIFIED: codebase]
async def run(self, step, ctx):
    runner = ctx.runner
    task_source = getattr(step, "task_source", None)
    source_step = getattr(task_source, "source_step", None) if task_source else None
    plan_output = runner.latest_typed_content(source_step) or "" if source_step else ""
    parser_name = (task_source.parser if task_source and task_source.parser else "json_tasks")
    parser = self._registry.resolve("task_parser", parser_name)
    tasks = parser.parse(plan_output)

    waves = build_waves(tasks)                 # PURE fn — raises on cycle/unknown ref PRE-spawn
    for wave_index, wave in enumerate(waves):
        # ... skip-if-terminal wave_runs row check (mid-wave resume, D-07) ...
        requests = [{"agent": "self", "input": t.body} for t in wave]
        # record_wave_run(running) via best-effort ctx.runner handle
        async for event in runner.run_fanout(requests, ctx, step=step):  # ONE call per wave
            yield event
        # update_wave_run(terminal) after merge
```
**Import purity:** the strategy imports ONLY `agents.capabilities.registry` (+ the pure `build_waves`); NEVER `agents.execution_engine` or `app.*`. The kernel is reached only via `ctx.runner` (import-linter gate). [VERIFIED: codebase — `fanout_batch.py` module docstring + import block]

### Pattern 2: Deterministic Kahn-levels wave builder (the CP-SAT seam)
**What:** A pure function: topological levels over `depends_on`, stable tie-break by task id, then within-level conflict_keys splitting.
**When to use:** `build_waves(tasks) -> list[list[Task]]` in the strategy module.
**Example (recommended shape — [ASSUMED] design, not lifted from an existing file):**
```python
def build_waves(tasks: list[Task]) -> list[list[Task]]:
    by_id = {t.id: t for t in tasks}
    # 1. Validate refs BEFORE any work (raise pre-spawn → zero rows).
    for t in tasks:
        for dep in t.depends_on:
            if dep not in by_id:
                raise WaveBuildError(f"task '{t.id}' depends_on unknown task '{dep}'")
    # 2. Kahn levels (deterministic: sort the ready set by task id each round).
    indeg = {t.id: len(t.depends_on) for t in tasks}
    remaining = set(by_id)
    levels: list[list[Task]] = []
    while remaining:
        ready = sorted([tid for tid in remaining if indeg[tid] == 0])
        if not ready:
            raise WaveBuildError("dependency cycle detected")   # remaining but none ready
        level = [by_id[tid] for tid in ready]
        # 3. Within-level conflict_keys split: tasks sharing a conflict_key
        #    cannot co-schedule → keep the first, spill the rest to a later wave.
        scheduled, deferred, used_keys = [], [], set()
        for t in level:
            keys = set(t.conflict_keys) or set(t.targets)   # documented default (discretion)
            if keys & used_keys:
                deferred.append(t)
            else:
                used_keys |= keys
                scheduled.append(t)
        levels.append(scheduled)
        for t in scheduled:
            remaining.discard(t.id)
            for u in tasks:
                if t.id in u.depends_on:
                    indeg[u.id] -= 1
        # deferred tasks stay in `remaining` with indeg 0 → picked next round deterministically
    return levels
```
*Note:* this is a recommended design, not a verbatim lift — the planner owns the exact spelling. The determinism requirements (stable sort, raise-before-spawn) are LOCKED (D-03).

### Pattern 3: `wave_runs` persistence = the `subagent_runs` recipe verbatim
**What:** Best-effort `KernelServices` recorder → default-deny `ScopedStore` writer/updater/reader → additive migration + ORM.
**When to use:** `wave_runs` persistence (WAVE-02).
**Example:**
```python
# Source: backend/agents/authz.py:939 + kernel_services.py:410  [VERIFIED: codebase]
# ScopedStore.record_wave_run clones record_subagent_run EXACTLY:
#   row carries owner_id + workspace_id (default-deny scope); free-String status; returns row.id
# KernelServices.record_wave_run clones the None-degrading wrapper:
#   store = getattr(self._ectx, "scoped_store", None); if store is None: return None
#   try: return await store.record_wave_run(...) except Exception: log + return None
```

### Pattern 4: All new events ride the single emit boundary — zero websocket edits
**What:** `wave_started`/`wave_completed`/`wave_failed`, `step_retry`, and the resume event are plain dicts yielded from the engine; the boundary stamps `seq`/`event_id` and persists to `run_events`.
**Example:**
```python
# Source: backend/agents/execution_engine/engine.py ~540-553  [VERIFIED: codebase]
seq = next(counter)
event_id = str(uuid.uuid4())
data["seq"] = seq
data["event_id"] = event_id
await sink.persist(seq, event_id, event.get("type", ""), data)
# → generic WS forward delivers it; the FE renders by event["type"] (08-08).
```

### Anti-Patterns to Avoid
- **A new kernel-side wave loop or per-task `run_fanout` calls** — duplicates dispatch machinery / loses within-wave parallelism + per-wave merge atomicity (D-01 rejected both). One `run_fanout` per wave.
- **A new `wave_builder` capability KIND** — one-impl registry churn for no benefit; the pluggability requirement is satisfied by `wave_scheduler` being a registered strategy + the pure-fn seam (D-03).
- **A new step-status table** — §18 is a closed list; step-completeness is derived compositionally from `artifact_refs` + `run_events` + `wave_runs`/`subagent_runs` (D-07).
- **A forked resume execution path** — resume rebuilds `ExecutionContext` and re-enters the SAME dispatch loop at an offset (D-06, INV-12). Do NOT write a second loop.
- **Retry inside the strategy or per-worker inside `run_fanout`** — one wrapper at the engine dispatch site only (D-10).
- **`subagent_chunk` / live worker token streaming** — lifecycle statuses only (D-14).
- **Editing `heading_tasks.py`** — `json_tasks` is a NEW sibling; `heading_tasks` must have an empty git diff (SPEC req 2 acceptance).
- **`sa.Enum` columns or a non-`0019` down_revision** — free-String status, `down_revision="0019"`, single head (D-16).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Worker spawn / isolation / merge / budget / cancel | A wave-specific spawn path | `ctx.runner.run_fanout(requests, ctx, step=step)` | The single spawn path already does selection, Semaphore≤4 concurrency, budget reserve-before-spawn, engine-decided isolation, fragment-persist-before-merge, merge dispatch, cancellation + teardown (INV-12). [VERIFIED: `fanout.py:241`] |
| Owner-scoped persistence + cross-owner deny | A new store class | `ScopedStore.record/update/read_*` (clone `*_subagent_run`) | Default-deny scoping (`_scope_owner_ws`) is proven; cross-owner read = ∅. [VERIFIED: `authz.py:939-1030`] |
| Best-effort offline-safe recording | Inline try/except at call sites | `KernelServices.record_wave_run` (clone `record_subagent_run`) | None-degrades offline so audit never aborts the run. [VERIFIED: `kernel_services.py:410`] |
| Durable event replay | A new replay query | `ScopedStore.read_events(run_id, after_seq)` | Already owner-scoped, ordered by seq asc, idempotent by event_id — the REST endpoint already uses it. [VERIFIED: `authz.py:314`, `runs.py`] |
| Transient error classification | A second transient list | `_is_transient_throttle(exc)` | One classifier home (06-03); layered botocore/status/substring detection. [VERIFIED: `model_policy.py:214`] |
| Content hashing | A new hash scheme | `hashlib.sha256(content.encode("utf-8")).hexdigest()` (existing ArtifactRef convention) | Output hashes already content-addressed; input_hash COMPOSES them. [VERIFIED: `graph.py:121`] |
| seq/event_id assignment + WS forward | A second emit path | The single emit boundary (engine.py ~540) | Contiguous per-run seq + uuid event_id; generic forward = zero websocket.py edits. [VERIFIED: `engine.py:540-553`] |
| Migration recipe | A bespoke migration | `0019_subagent_runs.py` recipe verbatim | Additive, reversible offline, named FK, no enum, single head. [VERIFIED: `0019_subagent_runs.py`] |
| FE tree panel scaffolding | A new panel architecture | `AgentProgressPanel`/`ValidatorIssuePanel` props-driven sibling pattern | 08-08 D-11 reuse; parent routes WS events down. [VERIFIED: `AgentProgressPanel.tsx`, `WorkflowComposer.tsx:264` placeholder] |

**Key insight:** Phase 11 already built the hard part (the spawn/merge/budget/isolation kernel). Phase 12 is overwhelmingly *composition of verified surfaces* — the genuinely new logic is (a) the pure `build_waves` topo function and (b) the resume re-entry offset computation. Everything else clones an existing, tested recipe.

## Runtime State Inventory

> This is a brownfield phase that ADDS durable state but does not rename/migrate existing state. Included for completeness because resume semantics touch stored data.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | NEW `wave_runs` table (additive `0020`). NO existing data renamed/re-keyed. Existing `subagent_runs`/`run_events`/`artifact_refs` are READ by resume logic, not mutated structurally. | Code: add table + ORM + store methods. No data migration of existing rows. |
| Live service config | None — no external service config embeds a renamed string. The sample wave workflow is test-scoped at `agents/workflows/<name>/` (in git). | None. |
| OS-registered state | None — resume is in-process `asyncio.create_task` at FastAPI startup; no Task Scheduler / systemd / pm2 registration. | None. |
| Secrets/env vars | None — no new secret or env var name. `backoff_seconds` uses a patchable sleep seam (module reference or settings multiplier), not a new secret. | None — verified: no new SOPS/env key in the locked decisions. |
| Build artifacts | The `0020` migration must reach a single Alembic head; the registry `_KNOWN` lockstep ratchets 59→61. Stale state would be a wrong head count or a lockstep mismatch. | Run `alembic upgrade head` reversibility check; update `_KNOWN` + the lockstep test assertion (`test_registry_capabilities.py:146`) in the SAME commit. |

**Cross-restart durability note (the riskiest runtime-state item):** RESUME-04 depends on durable surfaces surviving a process restart. The `run_events` log, `artifact_refs`, `subagent_runs`, and the new `wave_runs` rows are all DB-persisted (Postgres in prod, in-memory SQLite in the offline harness). The restart-simulation test exercises "engine instance A interrupted, instance B resumes against the SAME DB" — confirm the offline harness commits these rows before the simulated kill (best-effort recorders degrade to None offline, so the restart test must use a real session, not a None store, or it cannot prove mid-wave skip).

## Common Pitfalls

### Pitfall 1: Cross-restart input_hash instability (the second-riskiest item, per CONTEXT)
**What goes wrong:** The restart re-run reuse check fails because the recomputed `input_hash` differs from the pre-restart one — so the engine re-invokes a completed step, wasting tokens and breaking the "completed workers not re-invoked" acceptance criterion.
**Why it happens:** Non-deterministic serialization — dict key ordering, set ordering (`conflict_keys`/`targets` are lists but may be assembled from sets), float/whitespace drift, or including volatile fields (timestamps, uuids) in the canonical input string.
**How to avoid:** Canonical serialization with `json.dumps(..., sort_keys=True, separators=(",",":"))` over a FIXED tuple of inputs: the sorted list of consumed upstream `content_hash`es + the resolved task/prompt string. Hash ONLY content-addressed inputs that are themselves stable across restarts (the upstream `content_hash`es already are — `graph.py:121`). NEVER include the run timestamp, a fresh uuid, or unsorted collections.
**Warning signs:** The restart-simulation test shows a non-zero re-invocation count for a previously-completed step; the same step produces a NEW `artifact_refs` version on resume.

### Pitfall 2: Resume re-entry binding drift (the riskiest item, per CONTEXT)
**What goes wrong:** `resume_run` rebuilds `ExecutionContext` differently than `execute()` did — wrong owner/workspace, missing budget object, stale checkpointer thread_id — so the resumed run diverges from the original or crashes.
**Why it happens:** `execute()` builds the context inline; duplicating that build risks omitting a field (`scoped_store`, `budget`, `cancel_event`, `depth`, `checkpointer`). The build loop's thread_id convention (`{run_id}:{agent}`/`:task`) must be reproduced exactly for checkpointer reuse (D-09).
**How to avoid:** Extract the `ExecutionContext` construction `execute()` does into a shared builder (or call `compile_for_run` + the same rebind sequence) so resume and fresh-execute share ONE construction path — do NOT copy-paste-drift. Re-enter the EXISTING `for i, spec in enumerate(ordered_agents)` loop at the computed offset (engine.py ~1346); do not write a parallel loop. The checkpointer branch is sanctioned to degrade: reuse the thread where the convention matches, else re-run idempotently (the hash reuse makes it cheap).
**Warning signs:** Resumed run has a different owner_id on new artifacts; budget reserve raises because `ctx.budget` is None; two dispatch loops diverge in behavior under the characterization suite.

### Pitfall 3: Double-drive on restart
**What goes wrong:** A run is classified resumable AND its original driver somehow also resumes (or two restarts overlap), producing duplicate fan-out spawns.
**Why it happens:** No marker is written before the driver task starts, so a crash-during-resume re-classifies the same run on the next restart with no record that a driver was already launched.
**How to avoid:** Stamp the run (a status transition or a resume-marker event) BEFORE `asyncio.create_task(resume_run(...))` (D-08). Classification happens ONCE at startup (single-process v1). Cross-process locks are explicitly out of scope — do not over-engineer, but DO write the marker so a crash-during-resume is itself resumable.
**Warning signs:** Duplicate `wave_runs`/`subagent_runs` rows for the same wave/worker after a restart; `_KNOWN`/lockstep unaffected but the restart test shows >expected spawn counts.

### Pitfall 4: Parity perturbation — existing workflows must stay byte/event-identical
**What goes wrong:** A `wave_*`/`step_retry`/resume event, a `wave_runs` write, or a retry-wrapper branch fires for an EXISTING workflow (prototype/od_*/ppt/code-gen), breaking one of the 5 characterization snapshots.
**Why it happens:** The new paths aren't strictly gated on declared opt-in. Existing manifests declare no waves, no `retry`, and never restart-resume in tests — so every new path must be dormant for them.
**How to avoid:** Gate the retry wrapper on `step.retry and step.retry.max_attempts > 0` (absent/None = today). Gate resume on the three-way classification (existing tests never hit branch b). Gate `wave_runs` writes inside the `wave_scheduler` strategy only. Run the 5 snapshots with `SNAPSHOT_UPDATE` UNSET after every plan.
**Warning signs:** A characterization snapshot diff; a new event type appearing in a prototype run's event multiset.

### Pitfall 5: Mid-wave resume re-runs completed workers
**What goes wrong:** On resume, an in-flight wave re-enters `run_fanout` with ALL its task requests instead of only the incomplete ones — re-invoking workers that already have terminal `subagent_runs` rows + persisted fragments.
**Why it happens:** The resume logic skips completed WAVES (terminal `wave_runs`) but doesn't filter WORKERS within the in-flight wave.
**How to avoid:** For the in-flight wave (non-terminal `wave_runs` row), read its `subagent_runs` rows + fragment artifacts; build the `run_fanout` request list from ONLY the tasks whose workers lack a terminal row/fragment (D-07). Completed fragments are reused (P11 D-04 made them durable pre-merge).
**Warning signs:** The restart-simulation test's scripted-model invocation count exceeds the number of incomplete workers.

### Pitfall 6: `targets`-as-default-`conflict_keys` ambiguity
**What goes wrong:** Two tasks writing the same file land in the same wave (because `conflict_keys` was omitted and `targets` wasn't used as the fallback), producing a merge conflict that the sample workflow's `copy_disjoint` can't resolve cleanly.
**Why it happens:** The discretion choice (whether `targets` doubles as default `conflict_keys`) wasn't made + documented.
**How to avoid:** DECIDE and DOCUMENT (this is explicit discretion). Recommendation: default `conflict_keys` to `targets` when `conflict_keys` is empty — disjoint target files are exactly what "no conflict" means for `copy_disjoint`, and it makes the sample workflow's intent (distinct files → parallel) work without redundant declaration. Document the choice in the strategy/parser docstring.
**Warning signs:** Sample workflow merge produces a `merge_conflict` artifact when files were supposed to be disjoint.

## Code Examples

### json_tasks parser shape (clone heading_tasks structure)
```python
# Source: backend/agents/capabilities/task_parsers/heading_tasks.py  [VERIFIED: codebase]
# json_tasks differs: parses a JSON array (tolerating a fenced ```json block),
# builds Task with depends_on/conflict_keys/targets/done_when populated.
@register("task_parser", "json_tasks")          # default trust (matches heading_tasks)
class JsonTasksParser:
    name = "json_tasks"
    def parse(self, text: str) -> list[Task]:
        raw = _strip_fence(text)                # tolerate ```json ... ``` (discretion)
        data = json.loads(raw)                  # malformed → clear error
        items = data.get("tasks", data) if isinstance(data, dict) else data  # tolerate wrapper key (discretion)
        by_id = {it["id"] for it in items}
        for it in items:                        # validate refs (name the offender)
            for dep in it.get("depends_on", []):
                if dep not in by_id:
                    raise ValueError(f"task '{it['id']}' depends_on unknown task id '{dep}'")
        return [Task(id=str(it["id"]), title=it.get("title",""), body=it.get("body",""),
                     targets=it.get("targets",[]), depends_on=it.get("depends_on",[]),
                     conflict_keys=it.get("conflict_keys",[]), done_when=it.get("done_when",[]))
                for it in items]
```
*Imports stdlib + `agents.workflows.plan.Task` ONLY (the heading_tasks import discipline).* [VERIFIED: import block of `heading_tasks.py`]

### 0020 migration (clone 0019 verbatim)
```python
# Source: backend/alembic/versions/0019_subagent_runs.py  [VERIFIED: codebase]
revision = "0020"
down_revision = "0019"          # single head, unbroken chain
def upgrade():
    op.create_table("wave_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("wave_index", sa.Integer(), nullable=False),
        sa.Column("task_ids", sa.JSON(), nullable=False),         # §18: task_ids[]
        sa.Column("status", sa.String(), nullable=False),         # free String, NO sa.Enum
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),  # NAMED
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_wave_runs_run", "wave_runs", ["run_id"])
def downgrade():
    op.drop_index("ix_wave_runs_run", table_name="wave_runs")
    op.drop_table("wave_runs")
```

### WS reconnect after_seq replay branch (add to reconnect_pipeline)
```python
# Source: backend/app/api/websocket.py:560 + runs.py replay  [VERIFIED: codebase]
# In the reconnect_pipeline handler, BEFORE attaching to the live queue:
after_seq = message_data.get("after_seq", 0)
if after_seq or not (running_task and not running_task.done()):
    from agents.authz import ScopedStore as _ScopedStore
    _scoped = _ScopedStore(owner_id=user.id)            # owner-scoped (no cross-session leak)
    for r in await _scoped.read_events(_reconnect_run_id, after_seq=after_seq):
        await websocket.send_json({"type": r.type, "chunk": None, "section": None,
                                   "data": r.payload_json})   # dedup by event_id is FE-side
# then attach to the live queue if still running; if restarted (no live task),
# the replayed tail + current run status is the complete reconnect response.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `restore_non_terminal_runs` run-level only (`waiting_for_user` resumes, all else → failed WR-05) | Three-way classification with in-process step-granular auto-resume (this phase) | Phase 12 | Resumable runs survive a restart; WR-05 kept verbatim as the fallback for stateless runs |
| WS reconnect = in-memory queue only (`_PIPELINE_QUEUES`) | `reconnect_pipeline` durable `after_seq` replay over `run_events` | Phase 12 | Reconnect survives a process restart |
| `Task.depends_on`/`conflict_keys` declared but unconsumed; `Step.retry` INERT | Consumed by `wave_scheduler` + the retry wrapper (one consumer each, no fork) | Phase 12 | Forward fields go live without a parallel config surface (migration-ledger watch) |

**Deprecated/outdated:** None for this phase. `deepagents==0.6.7` is current and pinned (do NOT change). No library version churn — zero new packages.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The recommended `build_waves` Kahn-levels + conflict-split implementation shape is correct for the locked determinism requirements | Architecture Pattern 2 | Low — the design is a recommendation; the LOCKED requirements (stable tie-break, raise-pre-spawn, conflict-keys never co-schedule) constrain it. Planner owns exact spelling. Unit tests (diamond DAG, repeat-identical, conflict-split, cycle-raises) verify. |
| A2 | `targets` should default `conflict_keys` when the latter is omitted | Pitfall 6 | Low — this is explicit discretion; either choice is deterministic. Recommended for `copy_disjoint` correctness; must be DOCUMENTED. |
| A3 | The recommended `after_seq` replay branch placement (before live-attach, owner-scoped) matches the existing reconnect control flow | Code Examples | Low — verified the existing reconnect structure (`websocket.py:540-620`) and the `read_events` signature; exact insertion point is the planner's call. |
| A4 | `json_tasks` tolerating a `tasks:` wrapper key and a fenced ```json block is acceptable | Code Examples | Low — explicit discretion ("accepted shapes beyond SPEC minimum"); SPEC req 2 only mandates plain + fenced JSON + unknown-dep/malformed errors. |

**Note:** The two CONTEXT-flagged risks (D-06 resume re-entry, D-11 cross-restart hash stability) are LOCKED decisions, not assumptions — they are addressed as Pitfalls 1 & 2, not Assumptions.

## Open Questions

1. **D-11 input_hash storage spot (the explicit researcher directive — RESOLVED)**
   - What we know: `ArtifactRef` (`graph.py:53-82`) has NO free generic-metadata field. Its fields are identity/provenance (`id`, `kind`, `owner_id`, `workspace_id`, `run_id`, `producer_step`, `producer_agent`, `task_id`), content (`content`, `content_hash`, `location`, `version`), and lineage (`parents`, `derived_from`, `visibility`, `retention`). `content_hash` is the OUTPUT hash (sha256 of content) — it is NOT a place to put the INPUT hash. `derived_from`/`parents` are lineage pointers (ref ids), not a hash slot.
   - **Resolution: store `input_hash` in the `run_events` payload**, not in `ArtifactRef`. The reuse mechanism is: on (re-)execution, compute `input_hash`, then look up whether a completed-step event for `(run_id, step_id, input_hash)` already exists in `run_events` (durable, owner-scoped via `read_events`) AND the corresponding output artifact exists in `artifact_refs` (by `producer_step`). Emit a `step_completed`/`step_reused` event carrying `{run_id, step_id, input_hash, output_ref_id}` through the single emit boundary. This is additive (no schema change — `run_events.payload_json` is free-form JSON), survives restart (durable), and serves BOTH RESUME-02 (retry re-entry) and RESUME-04 (restart re-run) with one mechanism. NO new table, NO ArtifactRef field, NO migration beyond `0020`.
   - Recommendation: planner defines the `step_reused`/`step_completed` event payload schema (within the additive family) carrying `input_hash` + the produced `output_ref_id`; the reuse-check reads `run_events` for that `(step_id, input_hash)` pair.

2. **Resume-marker mechanism: status value vs event (discretion)**
   - What we know: D-08 requires the run be stamped BEFORE the driver task starts (double-drive guard). The two options are a `workflow_runs.status` transition (e.g. a `resuming` status) or a resume-marker `run_events` row.
   - What's unclear: A new status value risks the characterization suite (the NON_TERMINAL list at `engine.py:2868` would need to include it) and the state machine's allowed transitions; an event-marker is purely additive.
   - Recommendation: prefer the **event-marker** (additive, no state-machine/NON_TERMINAL surface change, restart-survivable). The planner fixes the spelling (D-08 fixes the semantics).

3. **Does the offline restart-simulation harness commit durable rows?**
   - What we know: best-effort recorders degrade to None offline (no `scoped_store`); the restart test needs REAL persisted `wave_runs`/`subagent_runs`/`run_events` to prove mid-wave skip.
   - What's unclear: whether the existing scripted-model harness binds a real (in-memory SQLite) `ScopedStore` to the context.
   - Recommendation: the restart-simulation test MUST bind a real in-memory SQLite session (the `0019`/`0020` reversibility tests already use one) so instance A's rows persist for instance B. If the harness defaults to a None store, the test author wires a session explicitly. Flag for the planner: this is the gating fixture for the RESUME-04 acceptance criterion.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3.11` | All backend code (no venv) | ✓ | 3.11 | — |
| `deepagents` | Worker runtime (INV-13, via run_fanout) | ✓ | 0.6.7 | — (mandate — no fallback permitted) |
| `lint-imports` | Import-purity gate (4 contracts) | ✓ | (at `/opt/homebrew/bin/lint-imports`) | — |
| Alembic + in-memory SQLite | `0020` reversibility test offline | ✓ | (existing) | — |
| PostgreSQL (live) | Prod persistence of `wave_runs`/`run_events` | ✗ (offline harness) | — | In-memory SQLite for offline tests; live Postgres check DEFERRED to end-of-milestone live pass (per user memory) |
| Bedrock / live model | Real worker invocation | ✗ (offline harness) | — | Scripted-model test harness (offline); live check deferred to milestone end |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** live Postgres + live Bedrock — both verified-offline via the scripted/in-memory harness; live verification deferred to the end-of-milestone pass (consistent with the project's `defer-live-verification-to-milestone-end` convention). The full backend pytest hangs offline (Chromium/Bedrock/Postgres-gated) — use the **targeted parity/gate suite** + `lint-imports` (~35s) per the project's `offline-test-suite-targeted` convention.

## Validation Architecture

> `workflow.nyquist_validation: true` — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (backend) + the scripted-model characterization harness; vitest/jest absent for FE (visual render human-verified per 08-08) |
| Config file | `backend/` pytest config (existing); the FE has NO headless DOM harness (08-08 precedent — D-15) |
| Quick run command | `cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py tests/agents/test_registry_capabilities.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -x` |
| Full suite command | targeted offline suite above + `/opt/homebrew/bin/lint-imports` (full pytest hangs offline — do NOT run it) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WAVE-01 | build_waves: diamond DAG → expected waves; repeat-identical; conflict-keys split; cycle/unknown-ref raises pre-spawn | unit | `python3.11 -m pytest tests/agents/test_wave_scheduler.py -x` | ❌ Wave 0 |
| WAVE-01 | `is_registered("strategy","wave_scheduler")`; `_KNOWN` count 61 | unit | `python3.11 -m pytest tests/agents/test_registry_capabilities.py -x` | ✅ (update assertion 59→61) |
| (parser) | json_tasks: plain JSON, fenced JSON, unknown-dep error, malformed error; `is_registered("task_parser","json_tasks")`; `heading_tasks.py` zero diff | unit | `python3.11 -m pytest tests/agents/test_json_tasks.py -x` | ❌ Wave 0 |
| WAVE-02 | `0020` reversible offline (upgrade→downgrade→upgrade); single head; cross-owner read = ∅; one row per wave terminal | unit/integration | `python3.11 -m pytest tests/agents/test_wave_runs.py -x` | ❌ Wave 0 |
| WAVE-02/SC-001 | sample multi-file workflow: ≥2 `wave_runs` (distinct wave_index, terminal); ≥2 parallel workers in one wave; merged output has every file; `grep <sample> agents/execution_engine/`=0 | integration (offline E2E) | `python3.11 -m pytest tests/agents/test_sample_wave_workflow.py -x` | ❌ Wave 0 |
| RESUME-02 | transient retries ≤max then visible error; non-transient no retry; hash-match reuse → zero extra invocations | unit (scripted-model) | `python3.11 -m pytest tests/agents/test_step_retry.py -x` | ❌ Wave 0 |
| RESUME-03 | reconnect after_seq=N delivers seq>N once each; restart (cleared queues) replays from DB + reports status; legacy (no after_seq) unchanged | integration | `python3.11 -m pytest tests/agents/test_ws_reconnect_replay.py -x` | ❌ Wave 0 |
| RESUME-04/WAVE-03 | instance A interrupted mid-wave → instance B resumes; completed workers not re-invoked (call counts); reaches completed; waiting_for_user still gates; stateless → WR-05 failed | integration (restart-sim) | `python3.11 -m pytest tests/agents/test_restart_resume.py -x` | ❌ Wave 0 |
| (parity) | 5 characterization snapshots byte/event-identical (SNAPSHOT_UPDATE unset) | regression | `python3.11 -m pytest tests/agents/test_characterization_*.py -x` | ✅ (must stay green) |
| (gates) | import-linter 4 kept/0 broken; banned-pattern (INV-13); migration-ledger 0019→0020 chain | gate | `/opt/homebrew/bin/lint-imports` + `python3.11 -m pytest tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -x` | ✅ |

### Sampling Rate
- **Per task commit:** the quick run command (characterization + registry + ledger + banned-pattern) — proves no parity/gate regression.
- **Per wave merge:** the full targeted offline suite + `lint-imports`.
- **Phase gate:** full targeted suite green + `lint-imports` 4/0 before `/gsd-verify-work`; FE render human-verified; live Postgres/Bedrock deferred to end-of-milestone.

### Wave 0 Gaps
- [ ] `tests/agents/test_wave_scheduler.py` — covers WAVE-01 build_waves determinism + registration
- [ ] `tests/agents/test_json_tasks.py` — covers the parser + heading_tasks-zero-diff
- [ ] `tests/agents/test_wave_runs.py` — covers WAVE-02 migration reversibility + cross-owner deny + row lifecycle
- [ ] `tests/agents/test_sample_wave_workflow.py` — covers SC-001 multi-file parallel proof
- [ ] `tests/agents/test_step_retry.py` — covers RESUME-02 retry + hash reuse (scripted-model)
- [ ] `tests/agents/test_ws_reconnect_replay.py` — covers RESUME-03 after_seq replay incl. restart
- [ ] `tests/agents/test_restart_resume.py` — covers RESUME-04 mid-wave resume (needs a REAL in-memory SQLite session bound — see Open Question 3)
- [ ] Update `test_registry_capabilities.py` `_KNOWN` assertion 59→61 (same commit as the registrations)

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1` — section included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No new auth surface; resume runs in-process under the run's existing principal |
| V3 Session Management | yes | WS reconnect replay is owner-scoped: `ScopedStore(owner_id=user.id).read_events(...)` — a reconnecting user can only replay THEIR run's events (the existing T-5-IDOR mitigation pattern at `websocket.py`); a cross-owner reconnect resolves to ∅ |
| V4 Access Control | yes | `wave_runs` carries `owner_id`+`workspace_id`; ScopedStore default-deny (cross-owner read = ∅, the FANOUT-10/T-11-01-03 precedent). The `0020` migration must enforce both columns NOT NULL. |
| V5 Input Validation | yes | `json_tasks` parses untrusted agent-emitted JSON: malformed JSON → clear error (no crash); unknown `depends_on` ref → named error BEFORE spawn; `after_seq` is int-coerced by FastAPI/the message handler (non-int rejected, never reaches raw SQL — the `runs.py` `after:int` precedent). `wave_index`/`task_ids` are internally generated, not user-supplied. |
| V6 Cryptography | no | `content_hash`/`input_hash` are sha256 for DEDUP/idempotency, NOT a security control (explicit note at `graph.py:22`). Do not treat hash equality as an auth check. |

### Known Threat Patterns for the wave-scheduler / resume stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-owner replay of another user's run events on WS reconnect | Information Disclosure | Owner-scoped `read_events` (default-deny ScopedStore); a non-owned run → ∅ replay (existing T-5-IDOR pattern) |
| Cross-owner read/write of `wave_runs` | Information Disclosure / Tampering | `owner_id`+`workspace_id` NOT NULL + `_scope_owner_ws` filter on every read/update (clone `subagent_runs` exactly); cross-owner update is a no-op |
| Fan-out fork-bomb via crafted wave/task list | Denial of Service | `run_fanout` already enforces budget reserve-before-spawn + Semaphore≤4 + per-workspace aggregate ceiling (P11) — waves inherit this per wave unchanged; `build_waves` raises on cycles BEFORE any spawn (zero rows) |
| Resume double-drive spawning duplicate workers | Tampering / DoS | Single-process startup classification (once) + stamp-before-driver marker (D-08); cross-process locks out of scope (single node) |
| Untrusted JSON task list path-traversal via `targets` | Tampering | `targets`/`conflict_keys` are merge/scheduling keys, NOT raw filesystem paths the engine opens; isolation is engine-decided (`_select_isolation_scope`, never the manifest); the sample workflow uses `copy_disjoint` into the run-scoped base workspace |
| Banned-pattern bypass — hand-rolling a worker spawn outside `run_fanout` | Tampering (INV-13 violation) | Banned-pattern CI gate (R15) + import-linter (capability → kernel only via `ctx.runner`); workers spawn ONLY through the existing `create_runner`/`run_fanout` path |

## Sources

### Primary (HIGH confidence)
- Codebase (verified this session via Read/grep) — all surfaces below confirmed to exist as the CONTEXT/SPEC describe:
  - `backend/agents/capabilities/strategies/fanout_batch.py` — structural template (TaskSource → registry parser → `ctx.runner.run_fanout(requests, ctx, step=step)`; import-pure)
  - `backend/agents/capabilities/task_parsers/heading_tasks.py` — parser template + import discipline
  - `backend/agents/execution_engine/fanout.py:241` — `run_fanout(requests, ctx, *, step)` signature; `_select_isolation_scope:226`
  - `backend/agents/execution_engine/engine.py` — dispatch loop (~1346-1438, `strategy.run(step, ectx)` site); single emit boundary (~540-553); `restore_non_terminal_runs:2847` (WR-05); `compile_for_run:199`
  - `backend/agents/workflows/plan.py` — `Task.depends_on/conflict_keys/targets`, `RetryPolicy(max_attempts,backoff_seconds)` INERT, `Step.retry`, `TaskSource`, `FanoutSpec`
  - `backend/agents/authz.py` — `ScopedStore.record_subagent_run:939`/`update_subagent_run:982`/`read_subagent_runs`/`read_events:314`/`get_run:335`
  - `backend/agents/execution_engine/kernel_services.py:410` — `record_subagent_run` None-degrading recorder
  - `backend/agents/artifacts/graph.py:53-135` — `ArtifactRef` field set + `content_hash = sha256(content.utf-8)` (`:121`); hash-is-not-security note (`:22`)
  - `backend/agents/model_policy.py:214` — `_is_transient_throttle`
  - `backend/alembic/versions/0019_subagent_runs.py` — the `0020` recipe (additive, down_revision, named FK, no enum, reversible)
  - `backend/app/api/websocket.py:540-620` — `reconnect_pipeline` (in-memory only)
  - `backend/app/api/runs.py` — `GET /{workflow_id}/events?after=` durable replay (the semantics the WS adopts)
  - `backend/agents/capabilities/registry.py` + `backend/tests/agents/test_registry_capabilities.py:146` — `_KNOWN` count 59 (→61)
  - `frontend/src/components/workflow/{AgentProgressPanel,WorkflowComposer}.tsx`, `frontend/src/components/layout/DashboardLayout.tsx:521` — FE sibling-panel model + reconnect send site
- `.planning/phases/12-wave-scheduler-durable-resume-6/12-SPEC.md` — 8 locked requirements, boundaries, 9 acceptance criteria
- `.planning/phases/12-wave-scheduler-durable-resume-6/12-CONTEXT.md` — D-01..D-18 locked decisions + canonical refs
- `.planning/phases/11-engine-owned-fan-out-merge-5/11-CONTEXT.md` — the fan-out patterns this phase composes
- `python3.11 -c "import deepagents; print(deepagents.__version__)"` → `0.6.7` (INV-13 mandate verified)

### Secondary (MEDIUM confidence)
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — the `0018→0019` recipe + INERT-fields-go-live watch (read for the `0020` ratchet pattern + the one-consumer-each rule)

### Tertiary (LOW confidence)
- None — this phase required no external research; every claim is codebase-verified or a documented design recommendation flagged in the Assumptions Log.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new packages (constraint-forced); `deepagents==0.6.7` verified installed; all reused surfaces verified in-codebase.
- Architecture: HIGH — every locked decision (D-01..D-18) maps to a verified existing surface; the only NEW logic (`build_waves` pure fn, resume offset) is well-bounded with locked determinism requirements.
- Pitfalls: HIGH — derived from the CONTEXT's own flagged risks (D-06 re-entry, D-11 hash stability) + the INV-3 parity gate + the verified default-deny/best-effort/single-emit recipes.

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (stable — brownfield, no fast-moving external dependency; `deepagents` pin is fixed by INV-13).
