# Phase 12: Wave Scheduler + Durable Resume [6] - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning
**Mode:** SPEC-first (12-SPEC.md written the same day via /gsd-spec-phase — 8 requirements locked there, ambiguity 0.14). All four HOW gray areas (wave execution & merge cadence, restart re-entry, retry/hash mechanics, FE tree sourcing) **locked to Claude's plan-grounded recommendations** at the user's direction ("none — lock your recommendations"), consistent with the Phase 1–11 pattern.

<domain>
## Phase Boundary

A registered `wave_scheduler` strategy sources tasks (via the new `json_tasks` parser carrying `depends_on`/`conflict_keys`), topo-sorts them into **deterministic parallel waves** behind a swappable pure wave-builder seam (CP-SAT later), and drives each wave through the EXISTING kernel `run_fanout` (one spawn path — isolation, merge, budgets, cancellation all inherited). Each wave merges into the base workspace before the next wave starts, and persists an owner-scoped `wave_runs` row (additive migration 0020). Durable resume hardens around it: `Step.retry` goes live (transient-only, `(run_id, step_id, input content_hash)` keyed, artifact reuse on hash match), WS `reconnect_pipeline` gains durable `after_seq` replay from `run_events` (idempotent by `event_id`, restart-surviving), and `restore_non_terminal_runs` is extended to **step-granular in-process auto-resume** — including mid-wave via `wave_runs`/`subagent_runs` — with the WR-05 abandoned→failed path kept verbatim for stateless runs. The §22 FE wave/subagent tree panel lands (clearing the 08-08 deferral) fed by lifecycle events only, plus FE reconnect `after_seq` adoption. Prototype stays sequential and byte/event-identical.

**What this phase is NOT:** no CP-SAT or any smarter scheduler (pure-function seam only, Q32), no single-file fragment-merge parallelism (prototype sequential, Q33), no durable queue/worker substrate (N8 v1 = in-process), no per-worker retry inside `run_fanout`, no `subagent_chunk` live worker streaming (P11 D-03 stands), no REST tree endpoint (`GET /api/runs/{id}/subagents` stays deferred — events + durable replay suffice), no distributed/multi-node resume, no ECS.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**8 requirements are locked.** See `12-SPEC.md` for full requirements, boundaries, and 9 acceptance criteria.

Downstream agents MUST read `12-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):** `wave_scheduler` strategy + deterministic pure wave-builder seam + `wave_*` events · `json_tasks` TaskParser · additive `0020 wave_runs` + ORM + default-deny ScopedStore + ledger/lockstep ratchets · sample multi-file wave workflow (manifest + AGENT.md only, SC-001) · `Step.retry` consumption (transient-only + content-hash artifact reuse + `step_retry` event) · WS `reconnect_pipeline` durable replay via `after_seq` (idempotent by `event_id`) · `restore_non_terminal_runs` step-granular in-process auto-resume incl. mid-wave + WR-05 fallback · FE wave/subagent tree panel + FE reconnect `after_seq` adoption.

**Out of scope (from SPEC.md):** CP-SAT scheduling (seam only) · single-file fragment-merge (prototype sequential; manifest untouched) · ECS/EC2 (v2) · durable queue/worker substrate · retry for non-transient/content errors (fix-loop owns content) · cross-node distributed resume · FE repo-diff viewer · DB-backed user workflow authoring.

</spec_lock>

<decisions>
## Implementation Decisions

> SPEC locked the WHAT. Below are the HOW decisions — the four presented gray areas, each locked to its plan-grounded recommendation, plus the supporting decisions they imply.

### Area A — Wave execution & merge cadence (WAVE-01/02)

- **D-01: The wave loop lives INSIDE the `wave_scheduler` strategy** (control flow in strategies — INV-5; the `fanout_batch` precedent). The strategy: sources tasks via the declared `TaskSource` (parser `json_tasks`), calls the wave-builder seam, then iterates waves **sequentially**; each wave's tasks become worker requests submitted as ONE `ctx.runner.run_fanout(...)` call per wave. Kernel `run_fanout` is NOT modified as an entry point — it stays the single spawn path (INV-12), so budget reserve-before-spawn, engine-decided isolation, merge dispatch, fragment persistence, and cancellation checks all apply per wave for free.
  - *Rejected:* a new kernel-side wave loop (duplicates dispatch machinery; the strategy registry exists exactly for this) or per-task `run_fanout` calls (loses within-wave parallelism semantics and per-wave merge atomicity).
- **D-02: Per-wave merge INTO the base workspace BEFORE the next wave starts.** Wave N's fragments merge (engine-selected strategy keyed on isolation scope, the 11-03 dispatch) into the parent run's primary workspace; wave N+1's workers shared-read the merged base — this is what makes `depends_on` meaningful (dependents consume predecessors' outputs). Fragments still persist as artifacts BEFORE merge (P11 D-04), which is precisely what mid-wave resume reuses.
- **D-03: CP-SAT seam = a PURE FUNCTION, not a new capability kind.** `build_waves(tasks: list[Task]) -> list[list[Task]]` — deterministic: Kahn topological levels over `depends_on`, stable tie-break by task id, then within-level splitting so tasks with overlapping `conflict_keys` never co-schedule (overlap spills to later waves deterministically). Cycles/unknown refs raise BEFORE any spawn (zero `wave_runs`/`subagent_runs` rows). It lives as a separately-unit-testable function in the strategy module (kernel-pure, stdlib-only); a future CP-SAT builder swaps in behind the same signature. Q31/Q32's "pluggable" requirement is satisfied by `wave_scheduler` being a registered strategy — no one-impl `wave_builder` capability kind, no `_KNOWN` churn beyond the two real registrations.
- **D-04: `wave_runs` row lifecycle** — one row per executed wave, written at wave start (`running`, with step + wave_index + task_ids) and updated terminal (`completed`/`failed`/`cancelled`) after the wave's merge completes/fails; written via a best-effort `KernelServices` handle (the `record_subagent_run`/`record_exec_run` None-degrading precedent, offline-safe). `wave_started`/`wave_completed` (+ `wave_failed` on failure) events ride the generic WS forward (zero websocket.py edits, 08-08) and the single emit boundary (seq/event_id, 05-04).
- **D-05: Registrations + trust:** `@register("strategy", "wave_scheduler", user_allowed=True)` (matches `fanout_batch` — the user-composable parallel strategy family); `@register("task_parser", "json_tasks")` default trust (matches `heading_tasks`). `_KNOWN` lockstep 59 → 61.

### Area B — Restart re-entry mechanics (RESUME-04 + WAVE-03) — the riskiest area

- **D-06: A dedicated engine resume entry** (e.g. `resume_run(run_id)` — exact name planner's call) invoked by `restore_non_terminal_runs` per resumable run via `asyncio.create_task` (in-process, N8 v1). It rebuilds `ExecutionContext` the same way `execute()` does (re-compile the manifest via `compile_for_run`, rebind owner/workspace/capabilities/budget, re-acquire the checkpointer), computes the first incomplete step, and enters the SAME per-step dispatch loop from that offset — **no forked execution path** (INV-12: one dispatch loop, entered mid-plan).
- **D-07: "First incomplete step" derives from EXISTING durable surfaces — NO new step-status table** (§18 is a closed list; plan §21's "durable step-level run state" is satisfied compositionally): a step is complete iff its typed artifacts exist (`artifact_refs` by producer step) and/or its terminal step events appear in `run_events`; for wave steps, terminal `wave_runs` rows give completed waves and terminal `subagent_runs` rows + fragment artifacts give completed workers within the in-flight wave. **Mid-wave resume:** completed waves are skipped; the in-flight wave re-enters `run_fanout` with only the workers lacking terminal rows/fragments (completed fragments reused — P11 D-04 made them durable pre-merge); the wave's `wave_runs` row continues to terminal.
- **D-08: Three-way startup classification, WR-05 kept verbatim as the fallback:** (a) `waiting_for_user` → re-arm resume event (unchanged); (b) resumable in-flight runs (manifest-compiled + durable step state present) → auto-resume per D-06, emitting a resume event (additive family) before continuing to terminal; (c) anything else → WR-05 abandoned→failed with the existing message. Double-drive guard: classification happens once at startup (single-process v1); the run is stamped (status transition or resume marker event) BEFORE the driver task starts so a crash-during-resume is itself resumable; cross-process locks are explicitly out of scope (single node).
- **D-09: Checkpointer posture:** reuse the per-agent LangGraph thread where the established thread_id convention matches (`{run_id}:{agent}`/`:task`, worker ids from P11 D-01); when absent/stale, re-run the step idempotently — both branches sanctioned by §21's "resumes from its checkpoint **or** re-runs idempotently"; the Req-5 content-hash reuse makes the re-run cheap.

### Area C — Retry wrapper & hash mechanics (RESUME-02)

- **D-10: ONE retry wrapper in the engine dispatch loop around per-step strategy execution** (single home, INV-12) — NOT inside strategies, NOT per-worker inside `run_fanout` (worker failures keep their P11 flow: `subagent_runs=failed` + merge/on_conflict; per-worker retry is a deferred idea). Wrapper activates ONLY when the compiled step declares `retry.max_attempts > 0` — absent/None = byte-identical today (prototype unchanged).
- **D-11: `input content_hash` = sha256 over the step's RESOLVED input**: the consumed upstream artifacts' existing `content_hash`es + the step's resolved task/prompt input string, canonically serialized. Cheap (output hashes already content-addressed since Phase 5), deterministic, and exactly what "same input" means at the dispatch boundary. The reuse check runs BEFORE every (re-)execution — first attempts, retry re-entries, AND restart re-runs (one mechanism serves RESUME-02 and RESUME-04): a completed artifact keyed `(run_id, step_id, input_hash)` → skip execution, reuse, emit the skip/reuse event. *Researcher confirms the storage spot for input_hash* (existing `ArtifactRef` meta/lineage fields vs `run_events` payload — NO new table; additive either way).
- **D-12: `RetryPolicy.on` gains `["transient"]` default** (SPEC-locked); transient classification REUSES the 06-03 `_is_transient_throttle` family — one classifier home, no second list. `backoff_seconds` honored via a patchable sleep seam (module-level reference or settings multiplier) so scripted tests stay fast. `step_retry` emitted per attempt (additive event family, dormant without declared retry).

### Area D — FE tree data sourcing (§22; clears the 08-08 deferral)

- **D-13: Events-only data plane.** The wave/subagent tree derives ENTIRELY from `wave_*` + `subagent_*` lifecycle events — live via WS, historical via the durable replay (`after_seq` from 0 on fresh load; from last-seen seq on reconnect). NO new REST tree endpoint this phase (the 11-CONTEXT `GET /api/runs/{id}/subagents` idea stays deferred): §22 sanctions "derived from events / subagent_runs / wave_runs", Req-6 replay makes the event stream complete, and a REST snapshot endpoint remains purely additive later if replay-from-0 proves heavy.
- **D-14: Lifecycle statuses ONLY — no `subagent_chunk`.** P11 D-03's rejection stands; the panel renders wave groups (index, task ids, status) → worker leaves (agent, status). No live worker token streams.
- **D-15: Panel = additive props-driven sibling in `WorkflowComposer.tsx`** (the 08-08 D-11 reuse pattern — parent routes WS events down; `ValidatorIssuePanel`/`AgentProgressPanel` are the structural models). FE reconnect: track last-received `seq` per run, send it as `after_seq` in `reconnect_pipeline`, dedupe applied events by `event_id` at the message handler. No existing panel modified; existing-workflow UI unchanged. Visual render is human-verified (08-08 Task-3 precedent — no headless DOM harness).

### Supporting decisions

- **D-16 — 0020 migration recipe = the 0018/0019 recipe verbatim:** additive, `down_revision=0019`, §18 columns + `owner_id`/`workspace_id`, free-String status (no `sa.Enum`), named FKs, offline-reversible (in-memory SQLite upgrade→downgrade→upgrade); `WaveRun` ORM on `Base.metadata`; ScopedStore default-deny writer/updater/readers (cross-owner read = ∅); migration-ledger/lockstep ratchets updated in the same commit. The migration rides whichever plan first writes rows.
- **D-17 — Sample wave workflow is test-scoped** (sc001/sample_fanout/sample_brownfield precedent): manifest + AGENT.md at the real home `agents/workflows/<name>/`, using ONLY registered capabilities (`wave_scheduler`, `json_tasks`, existing merge impls); a planner-style step emits the JSON task list; ≥2 waves, ≥2 parallel workers in one wave, disjoint target files merged `copy_disjoint`; `grep <name> agents/execution_engine/` = 0.
- **D-18 — Plan sequencing:** follow the ROADMAP 3-plan sketch (12-01 `wave_scheduler`+`json_tasks`+`wave_runs` · 12-02 retry+mid-wave resume · 12-03 durable replay+step-granular restore) **plus the FE tree work added at SPEC time** — planner's call whether FE rides 12-03 or becomes 12-04 (update ROADMAP plan count via tools if so). Sequential execution (`use_worktrees=false`); every plan leaves the 5-snapshot characterization suite green.

### Claude's Discretion

- Exact wave-builder function home/signature details, `wave_*`/`step_retry`/resume event payload schemas (within the locked additive families), and `wave_runs` index choices within §18's columns.
- Exact resume-entry name/shape and the resume-marker mechanism (status value vs event) — D-06/D-08 fix the semantics, planner fixes the spelling.
- input_hash storage spot (ArtifactRef meta vs run_events payload) per the D-11 researcher directive.
- `json_tasks` accepted shapes beyond the SPEC minimum (e.g. tolerating `tasks:` wrapper keys), and whether `targets` doubles as default `conflict_keys` when the latter is omitted (deterministic either way; document the choice).
- FE component naming/structure within the D-15 sibling-panel pattern.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/12-wave-scheduler-durable-resume-6/12-SPEC.md` — the 8 locked requirements, boundaries, 9 acceptance criteria, interview log (json_tasks / auto-resume / FE-tree decisions). **Locked requirements — MUST read before planning.**

### The specification (authoritative — `specs/003-workflow-engine-decoupling/plan.md`; nothing in it may be dropped)
- **Q31/Q32/Q33 (lines ~155–165)** — wave scheduler as a registered strategy; deterministic topo builder with CP-SAT seam; prototype stays sequential.
- **§6 Task contract (lines ~383–395)** — `Task.depends_on`/`parallel`/`conflict_keys` (wave scheduling + merge) + `TaskParser` Protocol (adapters: heading_tasks | json_tasks | bracket_p).
- **§18 (lines ~700–717)** — `wave_runs` row (line 709: id, run_id, step, wave_index, task_ids[], status); `run_events` (line 711: seq, event_id — the replay log).
- **§21 (lines ~740–753)** — THE resume contract: idempotent retry keyed `(run_id, step_id, input content_hash)` with artifact reuse; reconnect = replay `after=<last_seq>` idempotent by `event_id`; restart = `restore_non_terminal_runs` at step granularity; mid-wave via `subagent_runs`/`wave_runs`.
- **§22 (lines ~755–771)** — `wave_*` run-stream events; the replay endpoint contract; "subagent tree + wave view derived from events / subagent_runs / wave_runs" (D-13's sanction).
- **§25 Phase 6 (lines ~853–856)** — phase definition + accept wording.
- **§26 N8 (line ~872)** — in-process substrate for local v1 (D-06's sanction).
- **§27 (lines ~879–885)** — CP-SAT + fragment-merge deferrals.
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — the ratchet; INERT-fields-go-live watch: ONE consumer each for `Task.depends_on`/`conflict_keys`/`Step.retry` (no parallel config surface).

### Project planning
- `.planning/REQUIREMENTS.md` — WAVE-01..03 (lines ~133–135), RESUME-02..04 (lines ~140–142), traceability (Phase 12 = 6 requirement IDs).
- `.planning/ROADMAP.md` § Phase 12 (lines ~385–402) — goal, 3 success criteria, the 3-plan sketch (D-18 may grow it).
- `.planning/STATE.md` — Phase 11 closure state (fan-out decision log 11-01…11-05); N8 note.

### Prior phase context (patterns this phase extends)
- `.planning/phases/11-engine-owned-fan-out-merge-5/11-CONTEXT.md` — worker shape (D-01), lifecycle-only events (D-03), merge-into-base + fragments-persist-before-merge (D-04), budget home (D-05), 0019 recipe (D-06), test-scoped samples (D-08). Phase 12 composes ALL of these.
- `.planning/phases/10-safe-local-exec-gated-on-n3-4b/10-CONTEXT.md` — recorder-at-enforcement-point; ONE-durable-HITL (`waiting_for_user` gates ride it).

### Code to read (targets / assets — all verified this session)
- `backend/agents/capabilities/strategies/fanout_batch.py` — THE structural template for `wave_scheduler` (declared TaskSource → registry-resolved parser → requests → `ctx.runner.run_fanout`; import-pure).
- `backend/agents/execution_engine/fanout.py` — `run_fanout` (line 241: requests + ctx + step), `_select_isolation_scope` (226), `_merge_fragments` (819), `FanoutError` (70) — the per-wave engine machinery D-01 reuses unmodified.
- `backend/agents/execution_engine/kernel_services.py` — `run_fanout` handle (797), `record_subagent_run` (410, the D-04 recorder model), `run_worker` (813), `agent_exists` (775).
- `backend/agents/execution_engine/engine.py` — `restore_non_terminal_runs` (2847: the WR-05 logic D-08 extends), the per-step dispatch loop (the D-06 re-entry + D-10 wrapper site), the single emit boundary.
- `backend/agents/execution_engine/context.py` — `ExecutionContext` fields incl. `checkpointer` (127), `cancel_event`, budget ref — what `resume_run` must rebuild.
- `backend/agents/workflows/plan.py` — `Task` forward fields (298–320: depends_on/parallel/conflict_keys), `Step.retry` (declared-INERT), `RetryPolicy` (221–227: gains `on`), `TaskSource` (162).
- `backend/agents/capabilities/task_parsers/heading_tasks.py` — registration shape (89) + the id/title/body-only `parse` (100–118) `json_tasks` sits beside (byte-untouched).
- `backend/app/api/websocket.py` — `reconnect_pipeline` (556–600: the in-memory attach D-15/Req-6 extends), `_PIPELINE_QUEUES`/`_PIPELINE_TASKS`.
- `backend/app/api/runs.py` — the durable replay endpoint (667–705: `seq > after`, `event_id`) — the semantics the WS path adopts.
- `backend/alembic/versions/0019_subagent_runs.py` — the 0020 recipe (D-16).
- `backend/agents/capabilities/registry.py` + `backend/tests/agents/test_registry_capabilities.py` — `_KNOWN` lockstep currently 59 (line 146) → 61.
- `frontend/` `WorkflowComposer.tsx` + sibling panels (`ValidatorIssuePanel`/`AgentProgressPanel`) — the D-15 structural models; the FE WS client reconnect path for `after_seq` adoption.
- `backend/tests/agents/test_characterization_*.py`, `test_migration_ledger.py`, `test_banned_patterns.py`, `/opt/homebrew/bin/lint-imports` — the parity/ratchet gates (5 snapshots byte/event-identical with waves/retry/resume dormant; lint 4 kept/0 broken).
- `agents/workflows/sample_fanout/` + the sc001 test — the D-17 sample precedent.
- `backend/CLAUDE.md` — `python3.11` (no venv); targeted offline suite (full pytest hangs offline).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`run_fanout` + `KernelServices.run_fanout`** — the complete per-wave engine: worker selection, concurrency cap (Semaphore ≤4), budget reserve, isolation, fragment persistence, merge dispatch, cancellation, teardown. The strategy calls it once per wave; nothing in it changes.
- **P11 fragment artifacts (persist-before-merge)** — already durable; mid-wave resume = "skip workers whose fragments + terminal `subagent_runs` rows exist".
- **`GET /api/runs/{id}/events?after=` (Phase 5)** — the replay semantics (seq cursor + event_id idempotency) the WS reconnect path adopts wholesale.
- **`restore_non_terminal_runs` + WR-05** — the startup scan and the abandoned→failed fallback both survive; resume classification slots in between.
- **ScopedStore + 0018/0019 recipe** — `wave_runs` is the third copy of a proven mold.
- **`_is_transient_throttle` (06-03)** — the single transient classifier `RetryPolicy.on=["transient"]` binds to.
- **`ArtifactRef.content_hash` (Phase 5)** — output hashes already content-addressed; D-11's input_hash composes them.
- **Generic WS forward (08-08) + single emit boundary (05-04)** — `wave_*`/`step_retry`/resume events flow with zero websocket.py forwarding edits.
- **Scripted-model test harness + characterization suite** — restart simulation = engine instance A interrupted, instance B resumes against the same DB (offline).

### Established Patterns
- **Strategy owns control flow, kernel owns power (INV-5/INV-7)** — the wave loop is strategy-side; spawn/merge/budget stay kernel-side behind `ctx.runner`.
- **INERT-forward-fields-go-live without forking (INV-12)** — `Task.depends_on`/`conflict_keys`, `Step.retry` each get ONE consumer; no parallel config surface.
- **Best-effort recorder handles** — `record_wave_run` clones `record_subagent_run` degrade semantics (None offline).
- **Additive events at semantic parity** — existing workflows declare no waves/retry and never restart-resume in tests; 5 snapshots stay byte/event-identical with `SNAPSHOT_UPDATE` unset.
- **Test-scoped sample workflows prove SC-001** — manifest + AGENT.md only, zero engine edits.
- **Capabilities reach the kernel only via `ctx.runner`** — `wave_scheduler`/`json_tasks` import nothing from `agents.execution_engine`/`app` (import-linter 4/0).

### Integration Points
- **Net-new:** `strategies/wave_scheduler.py` (+ the pure `build_waves` seam) · `task_parsers/json_tasks.py` · migration `0020_wave_runs` + `WaveRun` ORM + ScopedStore methods + `KernelServices.record_wave_run` · sample wave workflow fixtures · FE wave/subagent tree panel · `wave_*`/`step_retry`/resume events.
- **Grows:** `RetryPolicy` (`on` field) + compiler materialization if needed (additive key) · engine dispatch loop (retry wrapper + resume re-entry offset) · `restore_non_terminal_runs` (three-way classification) · `websocket.py` `reconnect_pipeline` (after_seq replay branch) · FE WS client (after_seq + event_id dedup) · `_KNOWN` lockstep 59→61.
- **CI gates that constrain the work:** 5-pipeline characterization snapshots (waves/retry/resume dormant for existing workflows) · import-linter 4 kept/0 broken · banned-pattern (INV-13 — workers via existing `create_runner` path only) · migration-ledger ratchet (0019→0020 chain).

</code_context>

<specifics>
## Specific Ideas

- **Standing project directive:** "everything from plan.md must be honored — nothing dropped." Every locked decision takes the plan-faithful option (§21 verbatim for retry/reconnect/restart; §18's closed table list → D-07's no-new-step-status-table).
- **The riskiest research item:** D-06 resume re-entry — rebuilding `ExecutionContext` from durable state and entering the dispatch loop mid-plan without a forked path; second riskiest: D-11's input-hash serialization being stable across restarts (it must be — restart re-runs depend on hash equality for reuse).
- **Parity posture:** purely additive for existing workflows — none declare waves/retry, the WS legacy reconnect (no `after_seq`) behaves as today, and restore's WR-05 fallback is byte-kept; the characterization suite must pass untouched with `SNAPSHOT_UPDATE` unset.
- **User scope choice at SPEC time:** FE wave tree IN this phase (the one expansion over the recommendation) — backend `wave_*` events and durable replay are therefore hard dependencies of the FE plan, sequencing matters (D-18).

</specifics>

<deferred>
## Deferred Ideas

- **CP-SAT (or any smarter) wave builder** — swaps in behind the D-03 pure-function seam (§27).
- **`GET /api/runs/{id}/subagents` / waves REST tree endpoint** — additive later if replay-from-0 proves heavy for the panel (D-13).
- **`subagent_chunk` live worker streaming** — P11 D-03 rejection stands; revisit if the tree panel wants live worker output.
- **Per-worker retry inside `run_fanout`** — workers keep the P11 failed→merge/on_conflict flow; step-level retry only this phase (D-10).
- **Durable queue/worker substrate for long jobs** — N8 stays in-process for local v1; infra follow-up.
- **Cross-node/distributed resume locks** — single-node startup-only classification this phase (D-08).
- **Prototype parallelism via fragment-merge** — MERGE-01 v2 (Q33).
- **Real € price table + enforcement** — still dormant (P11 carry-over).
- **FE repo-diff viewer** — the remaining 08-08 deferral; separate backing-data story.
- **CR-03-followup: per-task skip on mid-wave resume** — additive migration adding task_id/worker_index to subagent_runs, enabling a correct per-task skip of completed workers on mid-wave resume (replaces the whole-wave re-run this phase ships). Whole-wave re-run is correct but wastes cost re-running already-completed file-writer workers; per-task skip removes that waste once task identity is durable.

### Reviewed Todos (not folded)
None — `todo.match-phase 12` returned 0 matches.

</deferred>

---

*Phase: 12-wave-scheduler-durable-resume-6*
*Context gathered: 2026-06-11*
