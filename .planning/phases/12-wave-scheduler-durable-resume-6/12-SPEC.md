# Phase 12: Wave Scheduler + Durable Resume [6] — Specification

**Created:** 2026-06-11
**Ambiguity score:** 0.14 (gate: ≤ 0.20)
**Requirements:** 8 locked

## Goal

A registered `wave_scheduler` strategy runs disjoint multi-file tasks in deterministic parallel waves through the existing kernel `run_fanout`, with `wave_runs` persistence, idempotent step retry, durable WS reconnect replay, and step-granular auto-resume after a server restart — prototype stays sequential and byte/event-identical; CP-SAT stays a seam.

## Background

Phase 11 landed the single kernel fan-out spawn path (`run_fanout` in `agents/execution_engine/fanout.py`) with isolation, merge, budgets, cancellation, and `subagent_runs` persistence (migration `0019`). The strategy registry holds `single_shot`, `task_loop`, and `fanout_batch` — `fanout_batch` shows the exact wave-scheduler pattern: source tasks via a declared `task_source`, build worker requests, funnel through `ctx.runner.run_fanout()` (import-pure, kernel owns all control flow).

What does NOT exist yet:

- No `wave_scheduler` strategy. `Task.depends_on` / `conflict_keys` / `targets` are declared forward fields (`agents/workflows/plan.py`) that **no parser populates** — `heading_tasks` emits id/title/body only.
- No `wave_runs` table (plan §18: id, run_id, step, wave_index, task_ids[], status). Migrations end at `0019_subagent_runs`.
- `Step.retry: RetryPolicy` (`max_attempts`, `backoff_seconds`) is declared-but-INERT — consumed nowhere; no `on` field. `_is_transient_throttle` (06-03) exists for transient classification; `ArtifactRef.content_hash` (Phase 5) exists for idempotency keys.
- WS `reconnect_pipeline` (app/api/websocket.py:560) attaches to the **in-memory** `_PIPELINE_QUEUES` only — a process restart loses the stream. The durable REST replay `GET /api/runs/{id}/events?after=<seq>` (Phase 5, API-05, idempotent by `event_id`) exists but the WS reconnect path never touches it.
- `restore_non_terminal_runs` (engine.py:2847) is run-level only: `waiting_for_user` runs re-arm their resume event; **every other** non-terminal run is deliberately marked failed ("no driver after restart", WR-05). No step-granular or mid-wave resume.
- 08-08 explicitly deferred the §22 wave/subagent tree FE panels ("no backing data until P9/11/12") — this phase creates the backing data, and the interview locked the FE tree IN scope.

## Requirements

1. **wave_scheduler strategy (WAVE-01)**: A registered `strategy:wave_scheduler` topo-sorts tasks by `depends_on` + `conflict_keys` into deterministic waves and runs each wave via the single kernel `run_fanout`; the wave-builder sits behind a swappable seam (CP-SAT later).
   - Current: No wave scheduler; `Task.depends_on`/`conflict_keys` unconsumed; `fanout_batch` is the closest analog (flat, no waves).
   - Target: `agents/capabilities/strategies/wave_scheduler.py`, `@register("strategy", "wave_scheduler", user_allowed=True)`, import-pure (kernel reached only via `ctx.runner`, the fanout_batch precedent). Deterministic wave builder: Kahn topological levels over `depends_on`, stable tie-break (task id order), tasks with overlapping `conflict_keys` never co-scheduled in one wave (overlap splits into later waves deterministically); dependency cycles or unknown `depends_on` refs rejected with a clear error **before any spawn** (zero `subagent_runs`/`wave_runs` rows). The builder is a pure, separately-testable function/seam (the CP-SAT swap point, Q32). Each wave's tasks become worker requests funneled through `ctx.runner.run_fanout(...)` (budgets, isolation, merge, cancellation all inherited). Additive `wave_*` events emitted (at minimum `wave_started`/`wave_completed` with step, wave_index, task_ids).
   - Acceptance: Unit tests prove — diamond DAG yields expected waves; same input twice yields identical partitions; overlapping `conflict_keys` tasks land in different waves; a cycle raises before any spawn (zero persisted rows). `is_registered("strategy","wave_scheduler")` passes; registry lockstep count updated.

2. **json_tasks parser**: A registered `task_parser:json_tasks` parses a JSON task list into canonical `Task` objects **including** `depends_on`/`conflict_keys`/`targets`; `heading_tasks` stays byte-untouched.
   - Current: Only `heading_tasks` exists; it populates id/title/body and nothing else; no structured-task carrier.
   - Target: `agents/capabilities/task_parsers/json_tasks.py`, `@register("task_parser", "json_tasks", ...)` — parses a JSON array (tolerating a fenced ```json block in agent output) of `{id, title, body, targets?, depends_on?, conflict_keys?, done_when?}` into `Task` objects; malformed JSON or a `depends_on` referencing an unknown task id produces a clear error naming the offender; `heading_tasks.py` has zero diff.
   - Acceptance: Parser unit tests pass (plain JSON, fenced JSON, unknown-dep error, malformed-JSON error); `git diff` on `heading_tasks.py` is empty; `is_registered("task_parser","json_tasks")` passes.

3. **wave_runs persistence (WAVE-02)**: Additive migration `0020` lands the owner/workspace-scoped `wave_runs` table + ORM + default-deny ScopedStore accessors; the scheduler writes one row per wave with status transitions.
   - Current: Migrations end at `0019_subagent_runs`; no `wave_runs` table, ORM, or store methods.
   - Target: `0020_wave_runs` (down_revision `0019`, reversible, free-String status — no `sa.Enum`, named FKs) with §18 columns (id, run_id, step, wave_index, task_ids JSON, status) **plus** `owner_id` + `workspace_id` (project constraint; `subagent_runs` precedent). `WaveRun` ORM registered on `Base.metadata`; `ScopedStore` record/update/read methods are default-deny (cross-owner read = ∅). `wave_scheduler` records each wave (pending/running → completed/failed/cancelled) via a best-effort `KernelServices` handle (the `record_subagent_run` degrade pattern — None offline).
   - Acceptance: `upgrade head → downgrade -1 → upgrade head` passes offline (in-memory SQLite, 09-02 precedent); single alembic head `0020`; cross-owner `wave_runs` read returns ∅; a wave run persists one row per executed wave with a terminal status; migration-ledger/lockstep ratchets updated in the same commit.

4. **Multi-file parallel proof, prototype sequential (WAVE-02 accept / SC-001)**: A sample multi-file workflow runs disjoint tasks in parallel waves from manifest + AGENT.md only — zero engine edits; prototype stays sequential.
   - Current: `sample_fanout` proves flat fan-out; no workflow exercises waves; prototype runs `task_loop` (sequential).
   - Target: A test-scoped sample wave workflow at the real manifest home (`agents/workflows/<name>/`, sc001/sample_fanout precedent) using ONLY registered capabilities (`wave_scheduler`, `json_tasks`, existing merge strategies): a planner-style step emits a JSON task list with dependencies; disjoint tasks (distinct target files) run in ≥2 waves with ≥2 parallel workers in some wave; fragments merge deterministically (`copy_disjoint`). The prototype manifest is NOT modified — it keeps `task_loop`.
   - Acceptance: Offline E2E test passes — ≥2 `wave_runs` rows (distinct wave_index) with terminal `completed`; within-wave workers produced `subagent_runs` rows; merged output contains every task's file; `grep <sample-name> agents/execution_engine/` = 0 (zero engine edits); the 5 characterization snapshots stay byte/event-identical.

5. **Idempotent step retry (RESUME-02)**: `Step.retry` is consumed — transient errors retry up to `max`, keyed by `(run_id, step_id, input content_hash)`, reusing the existing artifact on hash match; distinct from the validator fix-loop.
   - Current: `RetryPolicy(max_attempts, backoff_seconds)` is INERT (grep: consumed nowhere); no `on` field; transient classification exists (`_is_transient_throttle`, 06-03); content hashes exist on `ArtifactRef`.
   - Target: `RetryPolicy` gains `on: list[str]` (default `["transient"]`); a single engine-side retry wrapper at step dispatch (one home, INV-12) retries steps whose declared `retry.max_attempts > 0` on transient-classified errors with `backoff_seconds` between attempts; before any (re-)execution the step's input content-hash is computed — if a completed artifact for `(run_id, step_id, input_hash)` already exists in the typed graph, it is REUSED without re-invoking the agent; a `step_retry` event is emitted per attempt. Default (`retry` absent/None) = OFF — no behavior change for every existing manifest (prototype byte-identical). Content errors stay with the validator fix-loop (untouched).
   - Acceptance: Scripted-model tests — a transient failure retries exactly `max_attempts` times then surfaces a visible error; a non-transient error does NOT retry; a hash-match re-entry reuses the artifact (scripted model invocation count proves no second call); 5 characterization snapshots unchanged.

6. **Durable WS reconnect replay (RESUME-03)**: `reconnect_pipeline` accepts `after_seq` and replays missed events from the durable `run_events` log (idempotent by `event_id`) before attaching to the live queue — surviving a process restart.
   - Current: WS reconnect attaches to in-memory `_PIPELINE_QUEUES` only (websocket.py:560) — replay dies with the process; the REST endpoint `GET /api/runs/{id}/events?after=<seq>` already replays durably.
   - Target: The `reconnect_pipeline` message accepts optional `after_seq`; the handler first replays persisted `run_events` rows with `seq > after_seq` (owner-scoped read, dedup boundary by `event_id`), then attaches to the live queue when the pipeline is still running; when no live task exists (process restarted), replay still serves the full missed tail plus the run's current status instead of silently failing. REST endpoint unchanged.
   - Acceptance: Tests prove — reconnect with `after_seq=N` delivers exactly the `seq > N` events once each (no loss, no double-apply by `event_id`); reconnect after a simulated restart (cleared `_PIPELINE_QUEUES`/`_PIPELINE_TASKS`) still replays from the DB and reports run status; legacy reconnect without `after_seq` behaves as today.

7. **Step-granular auto-resume + mid-wave resume (RESUME-04 + WAVE-03)**: `restore_non_terminal_runs` auto-resumes resumable in-flight runs in-process at startup from the last incomplete step; wave runs resume mid-wave via `wave_runs`/`subagent_runs`; `waiting_for_user` and no-state runs keep today's behavior.
   - Current: Startup re-arms only `waiting_for_user`; every other non-terminal run → failed ("abandoned", WR-05), because no driver survives the restart.
   - Target: Startup classification becomes three-way: (a) `waiting_for_user` → re-arm resume event (unchanged); (b) resumable in-flight runs — compiled-manifest runs with persisted step state (`run_events` + `artifact_refs`, and `wave_runs`/`subagent_runs` for wave steps) — are re-driven **in-process** (N8 v1) from the first incomplete step: completed steps' artifacts are reused via the typed graph (content-hash, the Req-5 key), an in-flight wave resumes mid-wave (workers with terminal `subagent_runs` rows + fragment artifacts are NOT re-run; incomplete workers re-run; the `wave_runs` row continues), the LangGraph checkpointer thread is reused where available, otherwise the step re-runs idempotently; a resume event is emitted and the run proceeds to a terminal state; (c) runs without resume state keep the WR-05 abandoned→failed path verbatim.
   - Acceptance: Offline restart-simulation test — engine instance A executes a wave workflow and is interrupted mid-wave (driver stopped without a terminal run status); a NEW engine instance B running `restore_non_terminal_runs` resumes the run: previously-completed workers are not re-invoked (scripted call counts), remaining tasks complete, the run reaches `completed`; a `waiting_for_user` run still resumes only on user action; a stateless legacy run is still failed with the WR-05 message.

8. **FE wave/subagent tree + reconnect adoption (§22; clears the 08-08 deferral)**: An additive wave/subagent tree panel renders live `wave_*`/`subagent_*` events, and the FE reconnect sends `after_seq`.
   - Current: 08-08 deferred the tree panels (no backing data); the FE `reconnect_pipeline` message sends no sequence cursor and dedupes nothing.
   - Target: An additive, props-driven tree panel (the 08-08 D-11 sibling-panel pattern in `WorkflowComposer.tsx` — reuse, not rebuild) renders waves (index, task ids, status) and their workers (agent, status) from the run stream's `wave_*`/`subagent_*` events; the FE reconnect path sends the last-received `seq` as `after_seq` and dedupes incoming events by `event_id`. No existing panel is modified; existing workflows' UI is unchanged.
   - Acceptance: The panel renders a live wave run's tree from WS events; FE reconnect passes `after_seq` and applies replayed events exactly once; existing-workflow UI untouched; visual render human-verified (08-08 Task-3 precedent — no headless DOM harness in repo).

## Boundaries

**In scope:**
- `wave_scheduler` strategy + deterministic pure wave-builder seam (CP-SAT swap point) + `wave_*` events
- `json_tasks` TaskParser (structured tasks with depends_on/conflict_keys)
- Additive `0020 wave_runs` migration + ORM + default-deny ScopedStore accessors + ledger/lockstep ratchets
- Sample multi-file wave workflow (manifest + AGENT.md only — SC-001 proof) running disjoint tasks in parallel waves
- `Step.retry` consumption: transient-only retry + `(run_id, step_id, input content_hash)` artifact reuse + `step_retry` event
- WS `reconnect_pipeline` durable replay via `after_seq` (idempotent by `event_id`), restart-surviving
- `restore_non_terminal_runs` step-granular in-process auto-resume incl. mid-wave (wave_runs/subagent_runs) with WR-05 fallback
- FE wave/subagent tree panel (additive sibling panel) + FE reconnect `after_seq` adoption

**Out of scope:**
- CP-SAT (or any smarter) scheduling — seam only (Q32/§27 explicit deferral)
- Single-file fragment-merge parallelism — prototype stays sequential (Q33/§27); prototype manifest untouched
- ECS/EC2 runtime — v2 separate spec (§27)
- Durable queue/worker job substrate — N8 v1 is in-process resume; external queue is an infra follow-up
- Retry for non-transient/content errors — the validator fix-loop owns content refinement (RESUME-02 explicitly distinct)
- Cross-node/distributed resume — single-node restart semantics only this phase
- FE repo-diff viewer — separate 08-08 deferral; no new backing data this phase
- DB-backed user workflow authoring — REQUIREMENTS v2

## Constraints

- **Invariants**: INV-1 (kernel knows no workflow by name — scheduler keys off declared strategy/data only), INV-3 (5 characterization snapshots byte/event-identical; all new paths dormant for existing manifests), INV-5 (manifests stay data — wave config is declarative, control flow lives in the strategy), INV-12 (single homes: one retry wrapper, one spawn path; WR-05 superseded only where resume state exists), INV-13 (deepagents-only; no new agent loop)
- **Persistence**: additive `0020` only, reversible offline against in-memory SQLite (09-02 precedent); `wave_runs` carries `owner_id` + `workspace_id`; ScopedStore default-deny (cross-owner ∅)
- **Architecture**: strategy/parser import-pure (capability → kernel only via `ctx.runner`); import-linter 4 contracts stay 4 kept / 0 broken; banned-pattern + migration-ledger gates stay green
- **Concurrency/budget**: waves funnel through `run_fanout` — the engine concurrency cap (`Semaphore min(declared,4)`), `BudgetManager` reserve-before-spawn, isolation selection, merge dispatch, and cancellation boundaries all apply unchanged per wave
- **Resume substrate**: in-process re-drive at startup (N8 v1); no new external dependency for scheduling or resume (no CP-SAT lib, no queue broker)
- **Verification**: offline targeted suite + `lint-imports` (`/opt/homebrew/bin/lint-imports`); FE render human-verified; live checks deferred to the end-of-milestone pass

## Acceptance Criteria

- [ ] `is_registered("strategy","wave_scheduler")` and `is_registered("task_parser","json_tasks")` pass; `_KNOWN`/lockstep registry counts updated in the same commits
- [ ] Wave builder is deterministic (identical partitions on repeat), respects `depends_on` levels, never co-schedules overlapping `conflict_keys`, and rejects cycles/unknown refs before any spawn (zero persisted rows)
- [ ] Sample multi-file workflow (manifest + AGENT.md only) completes with ≥2 waves persisted in `wave_runs` (terminal statuses) and ≥2 parallel workers in one wave; `grep <sample> agents/execution_engine/` = 0
- [ ] `alembic upgrade head → downgrade -1 → upgrade head` green offline; single head `0020`; cross-owner `wave_runs` read = ∅
- [ ] Transient step retry fires ≤ `max_attempts` then surfaces a visible error; non-transient errors do not retry; identical `(run_id, step_id, input content_hash)` re-entry reuses the artifact with zero extra agent invocations
- [ ] WS reconnect with `after_seq` replays exactly the missed events once each (idempotent by `event_id`), including after a simulated process restart with cleared in-memory queues
- [ ] A fresh engine instance's `restore_non_terminal_runs` resumes an interrupted wave run mid-wave (completed workers not re-invoked) to `completed`; `waiting_for_user` still gates on user action; stateless runs keep the WR-05 failed path
- [ ] FE wave/subagent tree renders a live wave run and the FE reconnect adopts `after_seq` + `event_id` dedup — human-verified visual render
- [ ] 5 characterization snapshots byte/event-identical; `lint-imports` 4 kept / 0 broken; banned-pattern + migration-ledger gates green

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                            |
|--------------------|-------|------|--------|--------------------------------------------------|
| Goal Clarity       | 0.90  | 0.75 | ✓      | plan.md §21/§18/Phase-6 + 3 locked decisions     |
| Boundary Clarity   | 0.88  | 0.70 | ✓      | FE tree IN; CP-SAT/fragment-merge/queue OUT      |
| Constraint Clarity | 0.82  | 0.65 | ✓      | All gates/precedents named; json_tasks de-risks  |
| Acceptance Criteria| 0.80  | 0.70 | ✓      | 9 pass/fail criteria incl. restart simulation    |
| **Ambiguity**      | 0.14  | ≤0.20| ✓      | Gate passed after round 1                        |

## Interview Log

| Round | Perspective | Question summary                                              | Decision locked                                                                 |
|-------|-------------|---------------------------------------------------------------|---------------------------------------------------------------------------------|
| 1     | Researcher  | How do tasks acquire depends_on/conflict_keys (no parser does)? | New `json_tasks` parser (plan-sanctioned Q11 name); `heading_tasks` untouched   |
| 1     | Researcher  | Restart policy for in-flight runs (WR-05 abandons them today)? | Auto-resume in-process at startup, step-granular; WR-05 fallback for stateless runs |
| 1     | Researcher  | Reconnect scope + 08-08-deferred wave-tree FE panel?           | Backend durable WS replay (`after_seq`) **+** FE wave/subagent tree panel + FE `after_seq` adoption — both in scope |

Initial scores from roadmap/requirements/plan.md alone: 0.85/0.80/0.75/0.75 → ambiguity 0.2025 (marginally above gate). Round 1 locked the three open decisions → 0.14, gate passed; user confirmed write.

---

*Phase: 12-wave-scheduler-durable-resume-6*
*Spec created: 2026-06-11*
*Next step: /gsd-discuss-phase 12 — implementation decisions (wave-builder seam shape, resume re-entry seam, retry wrapper placement, FE panel composition)*
