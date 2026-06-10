# Phase 11: Engine-Owned Fan-Out + Merge [5] - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning
**Mode:** SPEC-first (11-SPEC.md written the same day via /gsd-spec-phase — 13 requirements + budget defaults locked there). All four HOW gray areas (worker shape, declarative entry, event streaming, merge mechanics) **locked to Claude's plan-grounded recommendations** at the user's direction ("none — lock recommendations"), consistent with the Phase 1–8 pattern.

<domain>
## Phase Boundary

A granted step fans out N workers — self-copies or named workers from `allowed_workers` — into **isolated workspaces** (`sub_sandbox` for sandbox runs, `worktree` for `has_git` repo runs; engine-decided, INV-7), parallel (capped `asyncio.gather`) or sequential, under engine-enforced caps. Both entry points — declarative `step.fanout` and the runtime `spawn_subagents` tool (a structured-request emitter that spawns nothing itself) — funnel through ONE kernel `run_fanout(requests, ctx)`. Results return as lineage-tracked artifacts + a structured summary; a registered `MergeStrategy` (`copy_disjoint`/`git_3way`/`json`/`html_fragment`) integrates fragments deterministically; conflicts write a `merge_conflict` artifact + event and resolve per `on_conflict` (`human_gate` default | bounded `merge_agent` | `partial` | `abort`). `BudgetManager` reserves-before-spawn and enforces subagents/concurrency/depth/tokens/wall-clock at run scope (locked defaults 8/4/2/900s) and workspace scope (settings seam, default unset); `BudgetExceeded` aborts gracefully with partial results. Every child gets an owner-scoped `subagent_runs` row (additive migration 0019); `subagent_*`/`merge_*`/`budget_warning` events flow through the generic WS forward; cancellation propagates to children with isolated-workspace teardown.

**What this phase is NOT:** no wave scheduler/`wave_runs`/mid-wave resume (Phase 12), no frontend subagent-tree panel or `GET /api/runs/{id}/subagents` endpoint (Phase 12, with the wave view), no prototype parallelism via fragment-merge (MERGE-01 v2 — prototype stays sequential, Q33), no real € price table (cost enforcement dormant), no user-grantable `spawn_subagents` (CAP-03 ceiling unchanged), no durable job queue (N8), no ECS.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**13 requirements are locked** (FANOUT-01..11, OBS-01, RESUME-01). See `11-SPEC.md` for full requirements, boundaries, and 12 acceptance criteria. Ambiguity 0.12 (gate ≤ 0.20); budget-cap defaults, € dormancy, and the panel→Phase-12 deferral are decided in the SPEC's interview log.

Downstream agents MUST read `11-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):** kernel `agents/execution_engine/fanout.py` (`run_fanout`) + `budget.py` (`BudgetManager`/`BudgetExceeded`/`BudgetSnapshot`) · `spawn_subagents` runner tool (request-emitter, permission-bound, privileged) · declarative `step.fanout` consumption + manifest `allowed_workers` (pure data, INV-5) · `sub_sandbox` + `worktree` isolation behind the existing `IsolationProvider` port (engine-decided scope) · `MergeStrategy` port + capability kind + 4 registered impls · merge-conflict flow (artifact + event + 4 `on_conflict` policies; merge_agent bounded at 2) · locked budget defaults (8/4/2/900s) + trust-conditional `Limits` + token/cost_class accounting (€ dormant) · per-workspace ceilings + `budget_snapshot_json` persistence · additive migration 0019 `subagent_runs` (owner-scoped) + `subagent_*`/`merge_*`/`budget_warning` events · cancellation propagation + isolated-workspace teardown · a test-scoped sample fan-out workflow (manifest + AGENT.md only) proving zero engine edits (SC-001).

**Out of scope (from SPEC.md):** wave scheduler/`wave_runs`/topo/mid-wave resume (Phase 12) · frontend subagent-tree panel + dedicated subagents read endpoint (Phase 12) · prototype fragment-merge wiring (MERGE-01 v2; `html_fragment` registers but nothing routes prototype through it) · real € price table/enforcement · user-grantable `spawn_subagents` · ECS/CP-SAT/PR-push (v2).

</spec_lock>

<decisions>
## Implementation Decisions

> SPEC locked the WHAT + the numeric defaults. Below are the HOW decisions — the four presented gray areas, each locked to its plan-grounded recommendation, plus the supporting decisions they imply.

### Area A — Worker execution shape (FANOUT-01/02/03; Q17 nesting)

- **D-01: One child = ONE isolated agent invocation through the existing `KernelServices.run_agent`/`create_runner` path (INV-13) — NOT a nested mini-run.** Per-worker checkpoint `thread_id` extends the build-loop convention (today `{run_id}:{agent}` + `:task` in the build loop → workers key like `{run_id}:{step}:{worker_i}`). The worker's workspace is its isolated allocation (D-04); it receives its task input (+ shared-read refs) and produces files + a structured result. Workers carry NO gates, NO per-worker validator fix-loops, NO strategies — validation/merge/conflict handling happen at the parent step after merge. Children are `subagent_runs` rows, never `workflow_runs` rows (§18).
  - *Rationale:* the prototype per-task build loop is the in-codebase precedent for engine-spawned isolated sub-agents (one agent invocation per unit, per-unit thread_id, engine owns the loop). §18 models children as `subagent_runs`, not runs. Keeps the kernel small and the child lifecycle fully engine-owned (INV-7).
  - *Rejected:* nested `engine.execute()` mini-runs per child (implies per-child `workflow_runs` rows + full event streams + gate machinery — heavier than §12/§18 describe, and the parent step already owns validation).
  - **Nesting (Q17):** the `spawn_subagents` tool may bind INSIDE a worker only when granted; a worker-initiated request funnels to the same `run_fanout` with `ctx.depth + 1` (the `ExecutionContext.depth` field reserved for this phase, context.py:168); depth > 2 (default) → `BudgetExceeded`-class rejection before spawn.
  - *Researcher directive:* confirm how `KernelServices.run_agent` threads sandbox/workspace + ModelResolver so a worker runs against its isolated workspace without perturbing the parent's binding; confirm per-worker thread_id uniqueness on the checkpointer; confirm worker token-usage events flow back to `BudgetManager` accounting + the child's `subagent_runs.tokens`.

### Area B — Declarative entry = `fanout_batch` strategy (FANOUT-01/02; INV-5)

- **D-02: Declarative fan-out is a registered `fanout_batch` `ExecutionStrategy`** — the name the plan (Q8) and `capabilities/base.py:44` already reserve. It sources tasks from the declared `TaskSource` (`source_step`/`spec_step`, the 07-11 precedent), parses them via the declared task parser (`heading_tasks`), maps each task → one worker request `{agent, input}`, and submits the batch to kernel `run_fanout`. `step.fanout` (a grown `FanoutSpec`: worker selection + mode + max_parallel) configures it; workflow-level `allowed_workers` lands on the manifest/compiled model as pure data. The compiler MATERIALIZES `FanoutSpec` (today `fanout` is allow-listed in `_STEP_KEYS` but never constructed) — additive parsing, no control flow (INV-5).
  - **Runtime entry:** a granted step's agent calls `spawn_subagents(tasks=[{agent,input}], mode=…)` mid-stream; the tool emits a structured request; the engine intercepts and fulfils it via the SAME `run_fanout`, returning the structured summary (FANOUT-06) as the tool result.
  - *Rationale:* gives declarative fan-out crisp semantics (a strategy that dispatches a parsed task list to workers) without overloading every other strategy; reuses the declared-TaskSource machinery SC-001 already proved; matches the strategy-registry architecture (adding a strategy = add a module + register, zero kernel edit).
  - *Rejected:* `step.fanout` as an orthogonal modifier any strategy honors (what `task_loop × fanout` means is undefined; parallel task scheduling with dependencies is Phase 12's `wave_scheduler`, not this phase).
  - *Researcher directive:* confirm the mid-stream tool-interception mechanics — how the engine detects the `spawn_subagents` tool call inside the deepagents `astream_events` loop and injects the fulfilled result (candidates: the HITL gate-interrupt precedent vs a tool whose coroutine awaits an engine-fulfilled future vs post-loop detection like `report_task_complete` event derivation); pick the one that keeps INV-13 (no agent-loop re-implementation) and the tool body spawn-free (FANOUT-01 grep).

### Area C — Child event streaming = lifecycle-only (FANOUT-10; INV-3)

- **D-03: The parent run stream carries lifecycle events only:** `subagent_spawned` (per child: worker id, agent, isolation scope, depth), `subagent_result` (per child: status, artifact refs, summary digest), the `merge_*` family (at minimum `merge_conflict`; planner may add `merge_started`/`merge_completed`), and `budget_warning` (≥80% of any ceiling or a failed reserve). Child agent chunks/tool events are NOT forwarded — workers run silently (the non-yielding `_run_validation_fix_loop` precedent). Worker usage still accumulates into `BudgetManager` + `subagent_runs.tokens`. All new events ride the generic `websocket.py` forward (zero edits — 08-08) and the single engine emit boundary (seq/event_id, 05-04).
  - *Rationale:* §22/Q43 name only `subagent_*`/`merge_*`/`budget_warning` — no chunk-level child events; N parallel interleaved chunk streams have no consumer until the Phase-12 panel; the FANOUT-06 structured summary + `subagent_runs` rows carry the per-worker detail. Adding tagged chunk streaming later is purely additive.
  - *Rejected:* `subagent_chunk` tagged streaming now (event-schema surface with no consumer; noisy; risks accidental parity perturbation for zero benefit this phase).
  - Existing workflows declare no fanout and grant no spawn — they emit NONE of these events; the 5 characterization snapshots stay byte/event-identical (the INV-3 gate).

### Area D — Merge mechanics (FANOUT-05/06/07/08)

- **D-04: Merge base/target = the parent run's primary workspace** (the run sandbox, or the repo working branch for `has_git` runs). Fragments = the child isolated workspaces. `MergeStrategy.merge(base, fragments)` applies non-conflicting fragment changes INTO the base; the step's deliverable/artifact flow continues from the merged base exactly as today (deliverable resolvers keep reading the run workspace). Per-worker outputs ALSO persist as lineage-tracked fragment artifacts BEFORE merge (FANOUT-06), so partial results survive `BudgetExceeded`/cancel (FANOUT-09/11).
  - **Strategy semantics:** `copy_disjoint` — copy each fragment's changed files into base; conflict = two fragments (or fragment vs base-since-spawn) touching the same relative path with differing content. `git_3way` — per-worker worktree branches merged back with the spawn-point commit as merge-base; conflict = git merge conflict. `json` — key-level merge of a target JSON document; conflict = same key, differing values. `html_fragment` — section-level composition of disjoint HTML fragments (registers to satisfy FANOUT-07; NOTHING routes prototype through it — Q33/MERGE-01 v2).
  - **Worktree mechanics:** branch-per-worker (e.g. `fanout/{step}/{worker_i}`) off the working branch at spawn; `LocalWorkspace` stays the SINGLE git-subprocess owner — worktree add/merge/remove land as `Workspace`/`IsolationProvider`-layer operations, never capability-side subprocess calls (the Phase-9 D-10 discipline: capabilities never shell git). Cleanup = `git worktree remove` + branch delete on teardown, INCLUDING the cancel path (RESUME-01).
  - **sub_sandbox mechanics:** child dir under the run root (e.g. `{run}/subagents/{step}/{worker_i}/`); reads = shared-read of parent refs, writes isolated (Q20); merged fragments copy back into the base.
  - **`merge_conflict` artifact payload:** conflicting relative paths + per-path worker provenance + truncated hunks/snippets — enough to be the `human_gate` payload (the Phase-10 D-04 principle: the payload is what the approver actually adjudicates).
  - **`on_conflict` flow (SPEC req 8):** `human_gate` (default) delegates to the ONE durable HITL mechanism (`run_human_gate` → `_run_review_gate`, Phase-10 D-02 precedent); `merge_agent` = a designated worker bounded at 2 attempts (mirrors `_MAX_FIX_ATTEMPTS`) then falls back to `human_gate`; `partial` keeps non-conflicting fragments + marks conflicted work failed + continues; `abort` fails the run.
  - *Researcher directive:* confirm what `git worktree`/merge plumbing `LocalWorkspace` needs beyond today's clone/branch/diff (new methods on the impl vs the `IsolationProvider` impl owning them — import-linter is the gate); confirm spawn-point commit capture for the 3-way merge-base; confirm shared-read seeding for `sub_sandbox` children (what of the parent workspace children may read).

### Supporting decisions

- **D-05 — BudgetManager home + accounting:** `agents/execution_engine/budget.py` (ROADMAP 11-04); the manager is a per-run object on `ExecutionContext` (INV-2 — no singleton state). `reserve()` gates countable units (subagents, concurrency slots, depth) BEFORE spawn; tokens/wall-clock are check-at-boundary + mid-flight abort (you cannot pre-reserve unknown token spend; the §6 contract `reserve(*, tokens=0, subagents=0)` covers both shapes). `spent() → BudgetSnapshot` persists to `workflow_runs.budget_snapshot_json` (the 0014 forward column goes live) on completion/abort/cancel (OBS-01). Per-workspace ceilings: a ScopedStore aggregate over the workspace's runs checked at reserve time; configured via a settings seam, default unset. Locked numbers (SPEC): subagents=8, concurrency=4, depth=2, wall=900s, merge_agent=2, warn@80% — module constants; file manifests may raise via `Limits`, user/db lower-only (08-03/10-02 trust precedent).
- **D-06 — `subagent_runs` (0019) mirrors the `exec_runs` (0018) recipe exactly:** §18 columns + `owner_id` (every new table carries owner_id + workspace_id), free-String `status` (no `sa.Enum`), ScopedStore default-deny writer/readers, offline-reversible (in-memory SQLite upgrade→downgrade→upgrade). Row written at spawn (`running`) and updated at terminal state (`complete`/`failed`/`cancelled` + tokens/cost). A best-effort `KernelServices.record_subagent_run` handle (the `record_exec_run` precedent — None-degrading offline).
- **D-07 — `spawn_subagents` tool registration:** registered via `@register` as a tool capability, `user_allowed=False` (CAP-03 keeps it off user/db manifests); bound only through the 08-03 tool_provider/intersection path when the step grants `tools.spawn_subagents`. The deepagents library `task` tool REMAINS excluded — engine fan-out is the only sanctioned spawn path (INV-13/INV-7).
- **D-08 — Sample fan-out workflow is test-scoped** (the sc001/`sample_brownfield` precedent): manifest + AGENT.md only, using only registered capabilities — e.g. a `fanout_batch` step fanning 3 self-copies, each producing a distinct file, merged `copy_disjoint`. Proves the SC-001 acceptance criterion (zero engine edits to author a fanning workflow).
- **D-09 — Plan sequencing:** follow the ROADMAP's 5-plan sketch (11-01 `run_fanout`+tool+declarative · 11-02 isolation+worker-selection+modes · 11-03 merge+conflict · 11-04 budget · 11-05 persistence+events+cancellation), executed sequentially (`workflow.use_worktrees=false` — Claude Code worktree isolation broken in this repo). The planner may re-cut boundaries (e.g. budget reserve seams are needed by 11-01's `run_fanout` — stub-and-thread or reorder is the planner's call) provided each plan leaves the characterization suite green.

### Claude's Discretion

- Exact `FanoutSpec`/`allowed_workers` field names + compiler materialization details (additive, INV-5-pure; unknown keys still rejected).
- Exact event payload schemas within the locked `subagent_*`/`merge_*`/`budget_warning` families.
- `subagent_runs` column types within §18's listed fields; index choices.
- Worktree branch naming + spawn-point capture mechanics; whether `IsolationProvider` impls register as capabilities (a registered `isolation` kind) or live as runtime-layer code bound via the §15 host seam — import-linter 4/0 is the gate either way.
- Whether `merge` strategies are kernel-side (pure-stdlib file ops) or app-side via the handle (git_3way needs the workspace handle regardless — the 08-04 heavy-dep boundary applies).
- Plan-task granularity within the 5-plan frame; where the 0019 migration rides (the plan that first writes rows — 11-05 per the sketch, or earlier if 11-01 needs the table for tests).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/11-engine-owned-fan-out-merge-5/11-SPEC.md` — the 13 locked requirements, boundaries, 12 acceptance criteria, locked budget defaults (8/4/2/900s, merge_agent=2, warn@80%), € dormancy, panel→P12. **Locked requirements — MUST read before planning.**

### The specification (authoritative — `specs/003-workflow-engine-decoupling/plan.md`; nothing in it may be dropped)
- **Q12–Q20 (lines ~84–108)** — the fan-out decision records: both entry points (Q12), engine-owned tool never raw lib (Q13), self×N or named worker (Q14), parallel/sequential + caps (Q15), files+summary results (Q16), nested with depth cap (Q17), the guardrail list (Q18), fan-out ≠ code-exec (Q19).
- **§6 (lines ~324–522)** — contracts: `ExecutionContext.budget` + `depth` (lines ~338–349), `Step.fanout`/`on_conflict` (lines ~363–365), `Task.conflict_keys` (line ~390), `ToolPermissions.spawn_subagents` (line ~436), `ArtifactRef.kind` incl. `merge_conflict` (line ~458), `IsolationProvider`/`MergeStrategy`/`BudgetManager` Protocols (lines ~485–494), and the **fan-out paragraph (lines 518–522)** — the INV-7 kernel-fulfils-requests definition.
- **§12 (lines 630–638)** — fan-out & sub-agents: the two entry points funneling through `run_fanout`, worker selection, modes, isolation, merge hand-off, nesting/limits, `subagent_runs` persistence.
- **§13 (lines 640–650)** — the merge-conflict flow: `merge_conflict` artifact + event, the four `on_conflict` policies, bounded `merge_agent` retries.
- **§18 (lines 697–717)** — persistence schema: the `subagent_runs` row (line 708: id, parent_run_id, parent_step, worker_agent, depth, isolation, workspace_id, status, tokens, cost) + `workflow_runs.budget_snapshot_json` (line 704).
- **§21 (lines 740–753)** — cancellation: cooperative `cancel_event` at step/gate/**fanout** boundaries, partial-artifact preservation, `teardown()`, propagation to children.
- **§22 (lines 755–771)** — API/event contract: the new `subagent_*`/`merge_*`/`budget_warning` events; subagent tree derived from events/`subagent_runs` (the P12 panel's data).
- **§23 (lines 773–779)** — budgets/observability: per-run AND per-workspace ceilings, reserve-before-spawn, snapshot persisted.
- **§25 Phase 5 (lines 847–851)** — the phase definition + accept wording.
- **§26 N8 (line 872)** — long-job substrate stays in-process (FastAPI task) for local v1 — fan-out runs in-process via `asyncio`, no queue/worker this phase.
- **§27 (lines 879–885)** — single-file fragment-merge parallelism deferred (prototype sequential).
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — the ratchet; this phase is mostly net-new (watch item: INERT forward fields going live must not fork — one `FanoutSpec`, one `Limits` consumer).

### Project planning
- `.planning/REQUIREMENTS.md` — FANOUT-01..11 (lines ~119–129), RESUME-01 (line ~139), OBS-01 (line ~170), MERGE-01 v2 deferral (line ~192), traceability rows (Phase 11 = 13 requirements).
- `.planning/ROADMAP.md` § Phase 11 (lines ~351–371) — goal, 4 success criteria, the 5-plan sketch (D-09).
- `.planning/STATE.md` — Phase 10 closure state; N8 blocker note (in-process accepted for v1).

### Prior phase context (patterns this phase extends)
- `.planning/phases/10-safe-local-exec-gated-on-n3-4b/10-CONTEXT.md` — the ONE-durable-HITL delegation (D-02 there → merge `human_gate` here), gate_events-as-memory (D-03), payload-is-what-you-sign-off (D-04), recorder-at-enforcement-point, 0018 migration recipe.
- `.planning/phases/09-local-workspace-runtime-repo-workflows-no-exec-4a/09-CONTEXT.md` — runtime port/impl split (D-01), `LocalWorkspace` as single git-subprocess owner (D-10 discipline), `IsolationProvider` port landing with sub_sandbox/worktree explicitly deferred HERE.
- `.planning/phases/08-capabilities-hardened-registry-gates-tool-perms-runtime-3/08-CONTEXT.md` — `@register`/`discover()` + lockstep `_KNOWN` count, perms intersection (D-07), tool_provider binding seam, heavy-dep app-side boundary (D-04).

### Code to read (targets / assets)
- `backend/agents/execution_engine/engine.py` — the dispatch loop (~lines 1249–1350: per-step strategy resolve + `post_step` + cancel checks + the single emit boundary) where `run_fanout` plugs in; the §15 host seam (workspace binding) and the build-loop sub-agent precedent.
- `backend/agents/execution_engine/kernel_services.py` — `run_agent` (line ~568, the worker invocation path), `run_human_gate` (~475, the conflict `human_gate` delegate), `record_exec_run` (~358, the `record_subagent_run` model), handle factories (`make_fix_policy`/`deliverable_context` — the pattern for any merge/conflict capability needs).
- `backend/agents/execution_engine/context.py` — `depth` (line 168, reserved for this phase), `cancel_event` (line 157); where the per-run `BudgetManager` rides (D-05).
- `backend/agents/runtime/base.py` — `IsolationProvider` port (line ~132: `allocate(scope)`; sub_sandbox/worktree explicitly Phase 11), `Workspace` port (teardown, git surface).
- `backend/app/agents/runtime/local.py` — `LocalWorkspace`/`LocalSandboxRuntime` (single git-subprocess owner — worktree ops land here), `create_workspace` threading, the exec recorder-callback pattern.
- `backend/agents/workflows/plan.py` — `FanoutSpec` (line 196, grows), `Limits` (231, goes live), `Task.conflict_keys` (300), `Step.fanout`/`on_conflict` (336–337), `ToolPermissions.spawn_subagents` (73).
- `backend/agents/workflows/compiler.py` — `_STEP_KEYS` allow-list (~78–82: `fanout`/`on_conflict`/`depends_on` accepted but `FanoutSpec` never materialized — the additive parsing gap), the trust ceiling (~106) + bool perms (~401) for the `Limits` trust-conditional rule.
- `backend/agents/capabilities/base.py` — `ExecutionStrategy` port (line 44 names `fanout_batch`); the Protocol-port idiom the `MergeStrategy` port follows.
- `backend/agents/capabilities/registry.py` — `@register`/`_KNOWN` + the lockstep drift-guard (currently 53; grows with `strategy:fanout_batch`, `tool:spawn_subagents`, 4 `merge:*`, possibly `isolation` impls).
- `backend/agents/factory.py` — `_build_runner_tools`/tool_provider seam (where `spawn_subagents` binds when granted).
- `backend/alembic/versions/0018_exec_runs.py` — the 0019 recipe (additive, named FKs, free-String status, offline-reversible).
- `backend/tests/agents/test_characterization_*.py` + `test_migration_ledger.py` + `test_banned_patterns.py` + `/opt/homebrew/bin/lint-imports` — the parity/ratchet gates (5 snapshots byte/event-identical with fanout dormant; lint 4 kept/0 broken).
- `backend/tests/agents/test_sc001_nonprototype_task_loop.py` (or its current home) + `agents/workflows/sample_brownfield/` — the test-scoped-workflow precedent D-08 follows.
- `backend/CLAUDE.md` — dev runtime `python3.11` (no venv); targeted offline suite (full pytest hangs offline); commit scopes.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`KernelServices.run_agent`** — the established agent-invocation handle; workers are N calls through it with isolated workspaces + per-worker thread_ids (D-01).
- **`IsolationProvider` port + `LocalWorkspace`** (09-01/09-02) — `allocate(scope)` exists with shared_read implemented; sub_sandbox/worktree are the declared Phase-11 growth; `LocalWorkspace` already owns all git subprocess work (clone/branch/diff → + worktree/merge).
- **`run_human_gate` → `_run_review_gate`** — the ONE durable HITL surface; the merge-conflict `human_gate` rides it with a conflict payload (Phase-10 D-02/D-04 precedent).
- **ScopedStore + the 0018 migration recipe** — `subagent_runs` (0019) + default-deny writer/readers mirror `exec_runs` exactly (D-06).
- **`workflow_runs.budget_snapshot_json`** — the 0014 forward column this phase finally writes (no migration needed for it).
- **Generic WS forward (08-08) + single emit boundary (05-04)** — `subagent_*`/`merge_*`/`budget_warning` flow with zero `websocket.py` edits.
- **Declared `TaskSource` + `heading_tasks` parser (07-11)** — `fanout_batch` sources its task list the same way `task_loop` does (D-02).
- **tool_provider/perms-intersection (08-03)** — the binding path that keeps `spawn_subagents` off ungranted steps.
- **`ExecutionContext.depth` + `cancel_event`** — both fields already exist; this phase makes them live.

### Established Patterns
- **Engine alone decides isolation/caps/merge (INV-7)** — the tool emits requests; manifests declare data; all decisions in `run_fanout`.
- **Capabilities reach power via the handle, never imports** — merge strategies needing git/workspace go through the workspace handle (import-linter 4/0 kept).
- **Reserve/record at the enforcement point, bypass-proof** — budget reserve inside `run_fanout` (the only spawn path), like the exec recorder inside `exec_command`.
- **Additive events at semantic parity** — existing workflows emit no fanout events; 5 characterization snapshots stay byte/event-identical with `SNAPSHOT_UPDATE` unset.
- **Trust-conditional manifests** — file may raise `Limits`, user/db lower-only (08-03 AGENT.md-only-lowers + 10-02 ceiling precedents).
- **Test-scoped sample workflows prove SC-001** — manifest + AGENT.md only, zero engine edits (sc001/sample_brownfield precedents).
- **INERT-forward-fields-go-live without forking** — `FanoutSpec`/`Limits`/`on_conflict`/`depth` get ONE consumer each; no parallel config surface (INV-12 watch).

### Integration Points
- **Net-new:** `agents/execution_engine/fanout.py` + `budget.py`; `spawn_subagents` tool module; `fanout_batch` strategy; `MergeStrategy` port + 4 impls + `merge` capability kind; sub_sandbox/worktree `IsolationProvider` impls; migration 0019 + `SubagentRun` model + ScopedStore writer + `KernelServices.record_subagent_run`; the sample fanout manifest + AGENT.md fixtures; new events.
- **Grows:** compiler (materialize `FanoutSpec`, `allowed_workers`, trust-conditional `Limits`); `plan.py` (additive `FanoutSpec` fields); engine dispatch loop (fanout path + cancel checks at fanout boundaries); `ExecutionContext` (budget manager ref); `_KNOWN` + lockstep count; `LocalWorkspace` (worktree/merge git ops).
- **CI gates that constrain the work:** 5-pipeline characterization snapshots (fanout dormant for all existing workflows); import-linter 4 kept/0 broken (fanout.py/budget.py are kernel-side, port-only imports); banned-pattern (workers via `create_runner` — INV-13; no `task` tool re-enable); migration-ledger ratchet (0018→0019 chain).

</code_context>

<specifics>
## Specific Ideas

- **Standing project directive:** "everything from plan.md must be honored — nothing dropped." Every locked decision above takes the plan-faithful option (Q12–Q20, §12, §13, §18, §21, §23).
- **The SPEC's round-1 locked numbers are constraints, not suggestions:** subagents=8 / concurrency=4 / depth=2 / wall=900s / merge_agent=2 / warn@80%; € dormant (no invented prices); panel→P12.
- **The riskiest research item:** mid-stream tool interception for `spawn_subagents` (D-02 directive) — must keep the tool spawn-free (FANOUT-01 grep) and INV-13 intact. Second riskiest: worktree merge mechanics staying inside `LocalWorkspace` (single git-subprocess owner) without breaking the import-linter direction.
- **Parity posture:** this phase is purely additive for existing workflows — none declare `fanout`, grant `spawn_subagents`, or set `Limits`; the characterization suite must pass untouched with `SNAPSHOT_UPDATE` unset.

</specifics>

<deferred>
## Deferred Ideas

- **Wave scheduler + `wave_runs` + mid-wave resume** — Phase 12 (WAVE-01..03, RESUME-02..04); `Task.conflict_keys`/`depends_on` stay forward fields for it.
- **Frontend subagent-tree panel + `GET /api/runs/{id}/subagents`** — Phase 12, combined with the wave view (SPEC round-1 decision); this phase ships the backing data (rows + lifecycle events + ScopedStore reads).
- **`subagent_chunk` tagged child streaming** — additive later if the P12 panel wants live worker output (D-03 rejected it for now).
- **Real € price table + € ceiling enforcement** — dormant cost fields exist; enforcement when a price source lands (SPEC round-1).
- **Prototype parallelism via `html_fragment` merge** — MERGE-01 v2; the strategy registers, the wiring doesn't.
- **User-grantable `spawn_subagents`** — CAP-03 ceiling unchanged; revisit with the user-composer trust work.
- **Durable job queue/worker for long fan-outs** — N8 stays in-process (FastAPI task + asyncio) for local v1.
- **Per-workspace budget configuration UI** — the settings seam lands; a UI to set workspace ceilings is later work.

### Reviewed Todos (not folded)
None — `todo.match-phase 11` returned 0 matches.

</deferred>

---

*Phase: 11-engine-owned-fan-out-merge-5*
*Context gathered: 2026-06-10*
