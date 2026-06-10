# Phase 11: Engine-Owned Fan-Out + Merge [5] — Specification

**Created:** 2026-06-10
**Ambiguity score:** 0.12 (gate: ≤ 0.20)
**Requirements:** 13 locked

## Goal

A granted step fans out N workers (self-copies or named workers) with isolated writes, merged deterministically, under engine-enforced budgets — both declarative (`step.fanout`) and runtime (`spawn_subagents` tool) entry points funnel through one kernel `run_fanout`, and the engine alone decides isolation/caps/merge (INV-7).

## Background

Phase 4 landed the forward surface as INERT data: `Step.fanout` (`FanoutSpec`: mode/max_parallel), `Step.on_conflict="human_gate"`, `Limits` (max_tokens/max_subagents/max_depth/wall_clock_seconds), `Task.conflict_keys/depends_on/parallel`, and `ToolPermissions.spawn_subagents=False` (privileged — the CAP-03 trust ceiling keeps it off user/db manifests). Phase 9 landed the `IsolationProvider` port (`agents/runtime/base.py`) with shared_read/per-run implemented and `sub_sandbox`/`worktree` explicitly deferred to this phase; `LocalWorkspace` is the single git-subprocess owner. `workflow_runs.budget_snapshot_json` exists since 0014 as an unwritten "Phase 11 forward field". `KernelServices.run_agent` is the established handle capabilities use to run agents; cooperative `cancel_event` is checked per-agent-step; the generic WS forward (08-08) means additive events flow with zero `websocket.py` edits.

**Missing entirely:** kernel `run_fanout`, the `spawn_subagents` tool implementation, `MergeStrategy` (port + impls), `BudgetManager`, and the `subagent_runs` table (migration head = 0018). The deepagents library `task` tool is always excluded so the model can never spawn its own sub-agents — engine-owned fan-out is the sanctioned replacement.

Source contracts: plan.md §6 (FanoutSpec/IsolationProvider/MergeStrategy/BudgetManager), §12 (fan-out), §13 (merge-conflict flow), §18 (subagent_runs), §21 (cancellation), §23 (budgets/events).

## Requirements

1. **FANOUT-01 — `spawn_subagents` tool (request-emitter only)**: A runner tool `spawn_subagents(tasks=[{agent, input}], mode=…)` is bound only to steps whose effective tool permissions grant `spawn_subagents`; the tool spawns nothing itself — it emits a structured request the kernel fulfils (INV-7).
   - Current: `ToolPermissions.spawn_subagents: bool = False` flag only (plan.py); no tool exists anywhere; deepagents `task` tool excluded.
   - Target: tool bound via the 08-03 tool_provider/intersection path only when granted; tool body returns a structured fan-out request; the kernel intercepts and fulfils it.
   - Acceptance: a step without the grant has no `spawn_subagents` in its bound tools (test); a granted step's tool call produces a structured request consumed by `run_fanout`; the tool module contains no task spawning/`asyncio.gather` (grep).

2. **FANOUT-02 — one kernel `run_fanout`**: Both declarative (`step.fanout`) and runtime (tool) entry points funnel through a single kernel `run_fanout(requests, ctx)`.
   - Current: no `fanout.py`; `Step.fanout` is recorded by the compiler but consumed nowhere; the engine dispatch loop has no fan-out path.
   - Target: `agents/execution_engine/fanout.py::run_fanout` is the only spawn path; declarative steps with `fanout` declared and tool-emitted requests both reach it.
   - Acceptance: one test drives fan-out declaratively (manifest with `step.fanout`), one via the tool — both observed to execute through `run_fanout`; grep shows no second fan-out dispatch path.

3. **FANOUT-03 — worker selection**: `agent="self"` runs N copies of the step's agent; a named worker must appear in the workflow's declared `allowed_workers` and resolve in the agent registry.
   - Current: no `allowed_workers` concept in manifest/compiler/plan model.
   - Target: manifest-declared `allowed_workers` (pure data, INV-5) compiled onto the plan; `run_fanout` resolves self→step agent ×N, named→registry lookup; a worker not in `allowed_workers` (or unknown to the registry) is rejected with a structured error before any spawn.
   - Acceptance: self×N test; named-worker test; disallowed/unknown worker → structured failure, zero children spawned, no partial side effects.

4. **FANOUT-04 — modes + `max_concurrency`**: Parallel mode = capped `asyncio.gather`; sequential mode runs workers in order; the engine enforces `max_concurrency` regardless of what the manifest asks.
   - Current: `FanoutSpec.mode`/`max_parallel` fields exist, unconsumed.
   - Target: parallel execution bounded by a semaphore at `min(declared, engine default 4)` (trust-conditional: file manifests may raise, user/db manifests only lower); sequential mode strictly ordered.
   - Acceptance: instrumented test observes concurrent worker count ≤ cap in parallel mode; sequential test observes strict start/finish ordering; a user-trust manifest declaring concurrency above the ceiling is clamped/rejected.

5. **FANOUT-05 — isolation (engine-decided)**: `IsolationProvider.allocate(scope)` supports `shared_read` | `sub_sandbox` | `worktree`; worker writes are isolated by default; the engine (not the manifest) picks the scope (INV-7).
   - Current: port exists (09-01); `shared_read`/per-run implemented; `sub_sandbox`/`worktree` absent.
   - Target: `sub_sandbox` (isolated child dir under the run workspace) and `worktree` (git worktree off the run's repo workspace) implemented behind the existing port; engine selects `worktree` when the base workspace `has_git=True`, else `sub_sandbox`; read-only inputs surface via `shared_read`.
   - Acceptance: two parallel workers writing the same filename land in distinct isolated workspaces (no cross-contamination before merge); engine-scope-selection test (has_git→worktree, sandbox→sub_sandbox); allocated workspaces carry owner_id/workspace_id.

6. **FANOUT-06 — results = artifacts + structured summary**: Each worker returns files/artifacts (typed, lineage-tracked) and a structured summary to the caller.
   - Current: nothing.
   - Target: worker outputs land in the `ArtifactGraph` as typed `ArtifactRef`s with lineage (producer step/agent, parent run linkage); the caller (tool result or step output) receives a structured summary of per-worker status + artifact references.
   - Acceptance: after a fan-out, artifacts are queryable via the typed graph with correct producer/lineage fields; the tool-entry caller receives a structured summary naming every worker's status and artifacts.

7. **FANOUT-07 — `MergeStrategy` registry**: A `MergeStrategy` port (name + `merge(base, fragments) → MergeResult`) registered as a capability kind, with `copy_disjoint`, `git_3way`, `json`, and `html_fragment` implementations.
   - Current: §6 contract only; no port in `capabilities/base.py`, no impls, no `merge` capability kind.
   - Target: port + 4 registered strategies (`@register("merge", name)`); disjoint-fragment merges are deterministic; overlap is reported as conflict, never silently overwritten. `html_fragment` registers to satisfy this requirement, but **no workflow routes prototype through parallel fragment-merge** — prototype stays sequential (Q33; MERGE-01 is v2).
   - Acceptance: ≥1 test per strategy; `copy_disjoint` over disjoint file sets produces a byte-stable deterministic result; overlapping writes produce a reported conflict; prototype manifest unchanged (no fanout declared).

8. **FANOUT-08 — merge-conflict flow**: On conflict, write a `merge_conflict` artifact + emit a `merge_conflict` event, then resolve per the step's `on_conflict` policy: `human_gate` (default) | `merge_agent` (bounded) | `partial` | `abort`.
   - Current: `Step.on_conflict` recorded, consumed nowhere; `merge_conflict` is an allowed ArtifactRef kind with no producer; durable HITL exists (`run_human_gate` → `_run_review_gate`, the D-02 single mechanism).
   - Target: conflict → owner-scoped `merge_conflict` `ArtifactRef` (conflicting hunks/files) + `merge_conflict` event; `human_gate` pauses via the existing durable HITL and resumes on user resolution; `merge_agent` spawns the designated merge worker bounded at **2 attempts** (mirrors `_MAX_FIX_ATTEMPTS`) then falls back to `human_gate`; `partial` keeps non-conflicting fragments, marks conflicted work failed, continues; `abort` fails the run.
   - Acceptance: 4 policy tests (one per `on_conflict` value); conflict artifact persisted + readable owner-scoped; `merge_agent` attempt count observed ≤ 2 with no oscillation; `human_gate` pause/resume round-trips.

9. **FANOUT-09 — `BudgetManager` reserve-before-spawn**: `BudgetManager` reserves before every spawn and enforces total subagents, concurrency, tokens, cost, wall-clock, and recursion/fan-out depth (`ctx.depth`); `BudgetExceeded` aborts gracefully with partial results.
   - Current: `Limits` dataclass INERT; `ctx.depth` field exists; no `BudgetManager`, no enforcement.
   - Target: `agents/execution_engine/budget.py::BudgetManager` with `reserve(...)` (raises `BudgetExceeded`) + `spent() → BudgetSnapshot`. **Locked defaults when `Limits` is undeclared: max_subagents=8/run, max_concurrency=4, max_depth=2, wall_clock=900s, tokens=uncapped-unless-declared** (module constants, N3 precedent). Trust-conditional: file manifests may raise via `Limits`; user/db manifests may only lower. **Cost: token + cost_class-weighted accounting; the € field exists in snapshots/rows but € enforcement stays dormant until a real price table lands (no invented prices).** On `BudgetExceeded`: completed workers' artifacts preserved + surfaced, pending workers never spawn, a visible event reports the abort.
   - Acceptance: with cap N, worker N+1 never spawns and the rejection has no side effects (reserve-before-spawn test); nested fan-out beyond depth 2 rejected; wall-clock breach aborts; partial results surfaced on abort; defaults asserted as module constants; user-trust manifest raising a cap is rejected/clamped at compile.

10. **FANOUT-10 — `subagent_runs` persistence + events**: Every child gets a `subagent_runs` row; `subagent_spawned`/`subagent_result`/`merge_*` (and `budget_warning`) events are emitted.
    - Current: no `subagent_runs` table (head = 0018); durable `run_events` log + generic WS forward exist.
    - Target: additive migration **0019** `subagent_runs` (id, parent_run_id, parent_step, worker_agent, depth, isolation, workspace_id, status, tokens, cost, **+ owner_id** — every new table carries owner_id + workspace_id), reads default-deny via `ScopedStore`; one row per child updated through its lifecycle; `subagent_*`/`merge_*` events emitted at the engine's single emit boundary; `budget_warning` emitted when ≥80% of any ceiling is consumed or a reserve fails.
    - Acceptance: 0019 reversible offline (upgrade→downgrade→upgrade, in-memory SQLite precedent); one row per child with depth/isolation/status/tokens populated; cross-owner `subagent_runs` read = ∅; events appear in the run stream with zero `websocket.py` edits.

11. **FANOUT-11 — cancellation propagates to children**: Cancelling a run mid-fan-out cancels all in-flight children and prevents pending spawns.
    - Current: `cancel_event` checked per-agent-step at the top-level loop only; no children exist.
    - Target: cancellation propagates to in-flight worker tasks; pending workers never spawn; each child's `subagent_runs` row marked `cancelled`; isolated workspaces torn down; partial artifacts preserved; `pipeline_cancelled` emitted.
    - Acceptance: cancel mid-parallel-fan-out test — in-flight workers stop, pending never start, rows read `cancelled`, `teardown()` called for every allocated isolated workspace, completed fragments' artifacts retained.

12. **OBS-01 — per-run AND per-workspace ceilings + persisted snapshot**: `BudgetManager` enforces ceilings at both run and workspace scope; the budget snapshot is persisted on the run.
    - Current: `workflow_runs.budget_snapshot_json` exists (0014), never written; no workspace-scope accounting.
    - Target: per-run ceilings from `Limits`/defaults (req 9); per-workspace ceilings checked at reserve time against aggregate spend across the workspace's runs — **default unset (uncapped) with a settings-level config seam** (no UI yet); `BudgetSnapshot` (tokens, cost, subagents, depth, wall_clock spent) written to `workflow_runs.budget_snapshot_json` on completion/abort/cancel.
    - Acceptance: with a workspace ceiling configured low, a second run in the same workspace fails its reserve with `BudgetExceeded`; snapshot JSON persisted with spent figures on completion AND on abort; workspace accounting keyed owner+workspace (cross-owner unaffected).

13. **RESUME-01 — cooperative cancel at fan-out boundaries + teardown**: `cancel_event` is checked at step/gate/**fanout** boundaries (and per-chunk, already live); on cancel the run is marked `cancelled`, partial artifacts preserved, isolated workspaces torn down, `pipeline_cancelled` emitted.
    - Current: per-agent-step + per-chunk checks exist; `pipeline_cancelled` emitted; no fanout-boundary checks, no isolated-workspace teardown (none exist).
    - Target: checks added before a fan-out wave, between sequential workers, and before merge; cancel anywhere in the fan-out path leaves no leaked isolated workspaces and preserves completed fragments as artifacts.
    - Acceptance: cancel between sequential workers stops the next spawn; cancel before merge skips merge and marks the run cancelled; no isolated workspace dirs remain after cancel (teardown asserted).

## Boundaries

**In scope:**
- Kernel `agents/execution_engine/fanout.py` (`run_fanout`) + `budget.py` (`BudgetManager`/`BudgetExceeded`/`BudgetSnapshot`)
- `spawn_subagents` runner tool (structured-request emitter, permission-bound, stays privileged/engineer-only)
- Declarative `step.fanout` consumption + manifest `allowed_workers` (pure data, INV-5)
- `sub_sandbox` + `worktree` isolation behind the existing `IsolationProvider` port; engine-decided scope
- `MergeStrategy` port + capability kind + `copy_disjoint`/`git_3way`/`json`/`html_fragment` registered impls
- Merge-conflict flow: `merge_conflict` artifact + event + all 4 `on_conflict` policies (human_gate default, merge_agent bounded at 2)
- Locked budget defaults (8 subagents / 4 concurrency / depth 2 / 900s wall) + trust-conditional `Limits` + token/cost_class accounting (€ dormant)
- Per-workspace ceilings (settings seam, default unset) + `budget_snapshot_json` persistence
- Additive migration 0019 `subagent_runs` (owner-scoped) + `subagent_*`/`merge_*`/`budget_warning` events
- Cancellation propagation + isolated-workspace teardown
- A test-scoped sample fan-out workflow (manifest + AGENT.md only, sc001 precedent) proving a fanning workflow needs zero engine edits (SC-001)

**Out of scope:**
- Wave scheduler, `wave_runs`, topo-sort, mid-wave resume — Phase 12 (RESUME-02/03/04, WAVE-01..03)
- Frontend subagent-tree panel — **deferred to Phase 12** (round-1 decision): one combined subagent+wave tree panel lands when `wave_runs` also exists; Phase 11 is backend-complete (events + rows + owner-scoped reads)
- Dedicated `GET /api/runs/{id}/subagents` endpoint — rides with the Phase 12 panel; `ScopedStore` reads land now
- Prototype parallelism / single-file fragment-merge wiring — v2 (MERGE-01); prototype stays sequential (Q33); `html_fragment` registers but nothing routes prototype through it
- Real € price table / € ceiling enforcement — dormant until a price source exists (round-1 decision; no invented prices)
- User-grantable `spawn_subagents` — stays privileged (CAP-03 ceiling unchanged)
- ECS/containers, CP-SAT, PR/commit push — v2 per REQUIREMENTS.md

## Constraints

- **INV-7**: the engine alone decides isolation/caps/merge — the tool only emits requests; isolation scope is never manifest-controlled
- **INV-13**: workers run via the registered `langchain_deepagents` runtime path (`KernelServices.run_agent`/`create_runner`); no hand-rolled agent loop; banned-pattern gate stays green
- **INV-1**: zero workflow-name/id branches in fanout/budget/merge code (kernel banned-pattern hard-fail)
- **INV-3**: the 5 characterization snapshots stay byte/event-identical — fan-out is dormant for every existing workflow (none grant `spawn_subagents` or declare `fanout`)
- **INV-5**: compiler stays thin — `fanout`/`limits`/`on_conflict`/`allowed_workers` are recorded data; all control flow lives in the engine/capabilities
- **Persistence**: additive 0019 only; `subagent_runs` carries owner_id + workspace_id; reads default-deny via `ScopedStore`
- **Trust**: `spawn_subagents` privileged (compiler CAP-03 rejects user/db manifests referencing it); `Limits` trust-conditional (file may raise, user/db lower-only — 08-03/10-02 precedent)
- **Locked defaults** (module constants): max_subagents=8, max_concurrency=4, max_depth=2, wall_clock=900s, merge_agent attempts=2, budget_warning threshold=80%
- **Architecture**: import-linter 4 contracts kept (capabilities never import kernel/app — handles via `KernelServices` factories); lint-imports 4 kept / 0 broken
- **Verification**: offline targeted suite (~35s parity/gate set + new fan-out suites); no live-Bedrock dependency (deferred to end-of-milestone live pass)

## Acceptance Criteria

- [ ] A granted step fans out N self-copies in parallel with observed concurrency ≤ 4 (default cap); sequential mode preserves strict order
- [ ] A step without `tools.spawn_subagents` never has the tool bound; both declarative and tool entry points funnel through the single kernel `run_fanout` (grep: no second spawn path)
- [ ] A named worker resolves via `allowed_workers` + registry; a disallowed worker is rejected with zero spawns
- [ ] Parallel workers write into isolated workspaces (`sub_sandbox`; `worktree` when `has_git=True` — engine-selected) and `copy_disjoint` merges disjoint fragments deterministically; all 4 merge strategies registered with passing tests
- [ ] A merge conflict writes an owner-scoped `merge_conflict` artifact + emits a `merge_conflict` event; all 4 `on_conflict` policies behave per spec (human_gate pauses/resumes durably; merge_agent bounded at 2 attempts; partial continues; abort fails the run)
- [ ] Reserve-before-spawn holds: exceeding subagents/depth/wall-clock raises `BudgetExceeded`, aborts gracefully, and surfaces partial results; defaults asserted as module constants (8/4/2/900s)
- [ ] A configured per-workspace ceiling fails the second run's reserve; `BudgetSnapshot` persisted to `workflow_runs.budget_snapshot_json` on completion and on abort
- [ ] Migration 0019 is reversible offline; every child has one owner-scoped `subagent_runs` row; cross-owner read = ∅
- [ ] `subagent_spawned`/`subagent_result`/`merge_*`/`budget_warning` events appear in the run stream with zero `websocket.py` edits
- [ ] Cancel mid-fan-out: in-flight children cancelled, pending never spawn, rows marked `cancelled`, isolated workspaces torn down, partial artifacts preserved, `pipeline_cancelled` emitted
- [ ] 5 characterization snapshots byte/event-identical; lint-imports 4 kept/0 broken; banned-pattern + migration-ledger gates green
- [ ] A test-scoped sample fan-out workflow (manifest + AGENT.md only) runs end-to-end with zero engine edits (SC-001 held)

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                          |
|--------------------|-------|------|--------|------------------------------------------------|
| Goal Clarity       | 0.90  | 0.75 | ✓      | INV-7 + 4 roadmap success criteria             |
| Boundary Clarity   | 0.90  | 0.70 | ✓      | Panel→P12, MERGE-01 v2, € dormant — explicit   |
| Constraint Clarity | 0.85  | 0.65 | ✓      | Cap numbers + trust semantics locked round 1   |
| Acceptance Criteria| 0.85  | 0.70 | ✓      | 12 pass/fail criteria                          |
| **Ambiguity**      | 0.12  | ≤0.20| ✓      |                                                |

## Interview Log

| Round | Perspective              | Question summary                                  | Decision locked                                                                 |
|-------|--------------------------|---------------------------------------------------|---------------------------------------------------------------------------------|
| 0     | Researcher (scout)       | What exists today?                                | INERT forward fields + IsolationProvider port + budget_snapshot_json column; run_fanout/tool/merge/budget/subagent_runs all missing |
| 1     | Researcher               | Default budget caps (plan gives no numbers)?      | Conservative locked module constants: subagents=8, concurrency=4, depth=2, wall=900s; trust-conditional (file raises, user lowers) |
| 1     | Researcher               | € ceilings with no price table?                   | Token + cost_class accounting now; € field present but enforcement dormant until a real price table (no invented prices) |
| 1     | Boundary Keeper          | Frontend subagent-tree panel: P11 or P12?         | Defer to Phase 12 — one combined subagent+wave panel; P11 ships events/rows/reads |
| 1     | Boundary Keeper (self-resolved) | html_fragment vs MERGE-01 v2 deferral?      | FANOUT-07 text mandates all 4 strategies registered; MERGE-01 defers only the prototype-parallelism wiring — prototype stays sequential |

---

*Phase: 11-engine-owned-fan-out-merge-5*
*Spec created: 2026-06-10*
*Next step: /gsd-discuss-phase 11 — implementation decisions (fanout.py shape, worktree mechanics, merge_agent prompt, budget accounting wiring)*
