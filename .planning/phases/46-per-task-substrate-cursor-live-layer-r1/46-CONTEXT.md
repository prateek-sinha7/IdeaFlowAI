# Phase 46: Per-Task Substrate, Cursor & Live-Layer Re-Registration [R1] - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Source:** POR Ingest Express Path (`.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` §5.1/§5.3/§5.4/§5.8/§6-R1/§7/§8; decisions pre-LOCKED by the user)

<domain>
## Phase Boundary

Make sub-agent / fan-out / sequential-task interruptions resumable at task/worker granularity, and make resumed runs first-class LIVE runs. Six requirements (RESUME-06..11): the `subagent_runs` task-identity migration; GENERIC per-task capture (every file a task wrote — Q7); durable→disk re-materialization incl. mid-wave merge re-entry; per-worker/per-task skip via a KERNEL-computed cursor; live-ectx + milestone-sink re-registration on both resume paths; steering re-drain.

**Identity scope note (load-bearing):** in THIS phase the cursor keys on the EXISTING positional durable ids — `task_id = str(task_num)` (persist_task_html) and `worker_index` — persisted to `subagent_runs`. That is safe for pure resume (no user edits mid-flight yet). The content-addressed `task_key` (upstream-hash · content · ordinal) and mutable-list reconciliation are **Phase 48** — do NOT build them here.

OUT of scope (hard fences): uploads durability (Phase 47), task_key/reconciliation (48), gate re-arm / the KAN-88 red test (49), the REST resume endpoint (50), ND-10 images (locked non-goal — resumed runs lose `run_images` BY DESIGN, document never fix), git-as-substrate (GIT-01), cross-node (N8), mid-token resume.

</domain>

<decisions>
## Implementation Decisions

### RESUME-06 — the migration (LOCKED)
- Additive nullable `task_id` (String) + `worker_index` (Integer) columns on `subagent_runs` — the pre-authorized CR-03-followup shape. Next head after `0025_deep_link_nonces` (= `0026`). `batch_alter_table.add_column` only, NO new table, NO destructive alter, reversible single-head (upgrade→downgrade→upgrade proven offline on SQLite). Free-String status stays; existing FK untouched.
- Rows written at SPAWN — before the crash window (the `selections_json`/0023 persist-at-creation precedent): the fan-out worker record site (`fanout.py` `record_subagent_run` / worker-spawn path) stamps `worker_index` (and `task_id` when the worker maps to a task); the ORM model (`app/models/subagent_run.py`) gains the two columns.

### RESUME-07 — generic per-task capture (LOCKED, Q7)
- Every file a task wrote is durably captured per task — superseding `persist_task_html`'s single-declared-file scope (kernel_services.py:1313-1339). Mechanism discretion (below), but the contract is fixed: after each task, all files that task created/changed in the run sandbox are dual-written as `artifact_refs` rows tagged with that task's `task_id`; the declared-deliverable capture stays byte-compatible (the prototype path's existing `html_file` row must keep its exact kind/location/content behavior — INV-3).
- Capture is EVENT-FREE and best-effort (extra DB rows are golden-safe; the golden harness asserts deliverable bytes + event multiset, never DB row counts). Zero new WS event types.
- If a new `ARTIFACT_KINDS` member is genuinely needed for sibling files, it is an ADDITIVE vocabulary member (the P13 `"deliverable"` precedent); prefer reusing `file_bundle` if it fits.
- No sanctioned dual implementation: the generic capture must SUBSUME (extend or replace-in-place) `persist_task_html`'s write path, not sit beside it as a second uncoordinated writer (INV-12). The `hasattr(runner, "persist_task_html")` call sites in `task_loop.py:290-296/:358-366` are the seam.

### RESUME-08 — durable→disk re-materialization + merge re-entry (LOCKED)
- A resume-tier step (beside `_hydrate_artifacts_from_store`, engine.py:5865-5907 — which stays graph-only) walks the latest durable `artifact_refs` for the run (by `location`, `max(version)`, filtered to completed steps/tasks) and writes them back onto the fresh `RunSandbox` BEFORE strategies re-enter. Disk-as-live-truth is preserved; the durable mirror is the SOURCE (never git — worktree commits are ephemeral, POR §3.2).
- Mid-wave merge re-entry: when a wave's fragments persisted but the per-wave merge never ran (crash window between `write_fragment_artifact` and merge), resume re-materializes that wave's fragments to disk and re-runs the merge for the in-flight wave before dispatching remaining workers/waves. Reuse the existing merge machinery (`fanout.py` merge path) — no second merge implementation.
- All durable reads via the run's own owner-scoped `ScopedStore` (default-deny; `user_id` keying) — zero scope widening.

### RESUME-09 — per-worker / per-task skip (LOCKED)
- The KERNEL computes the completed set (from `subagent_runs` task_id/worker_index rows + per-task `artifact_refs`) and threads it into `strategy.run` — the AGENT never decides the skip set (agents still receive completed work as injected context via the existing context machinery, unchanged).
- `task_loop`: loop skips completed task numbers (the Phase-45 completeness fix decides step re-entry; this decides intra-step skip).
- `wave_scheduler`: skip completed WORKERS within the in-flight wave (identity-based — NOT the deleted-for-cause prefix-by-count skip, 12-06 CR-03; that rationale is now satisfied because identity is durable). Terminal-completed waves stay skipped as today (`_completed_wave_indices`, step-filtered).
- INV-13: re-invocation of remaining work goes through the SAME `_run_agent`/`run_fanout` paths (no new agent loop).

### RESUME-10 — live-layer re-registration (LOCKED, closes the Phase-43 dormancy)
- BOTH resume paths — auto (`restore_non_terminal_runs` branch (b) → `resume_run`) and the future Phase-50 endpoint (build the seam now, consume it in 50) — thread the SAME two injected callbacks the REST launch threads at `run_commands.py:1355`: `register_live_ectx` (+ guaranteed unregister in `finally`) and `milestone_sink=persist_milestone_card`.
- Wiring rule: the engine NEVER imports `app.*` — callbacks arrive as generic callables (the Phase-43 `MilestoneSink`/`LiveEctxRegister` aliases, engine.py:41/51). The auto-resume call site is app-layer (the startup restore scan / the `run_engine.py` bridge wiring in `app/main.py`) — inject there.
- Milestone cards on resumed runs draw `seq` from the engine's own counter (DEF-43-03-1; the 0024 uniqueness constraint) — never `append_event_next_seq`.
- Acceptance: on a resumed run, `_live_ectx_for_run(run_id)` resolves (steering/per-turn images/Concierge deliverable), and narrator milestone cards emit with a contiguous durable log.

### RESUME-11 — steering re-drain (LOCKED contract, mechanism discretion)
- Steering notes durably logged as chat rows but NOT yet drained into a dispatch at crash time are re-queued onto `ectx.steering_notes` at resume. An already-drained note must NOT be duplicated into a later prompt. Determining drained-vs-undrained is discretion (e.g. compare the steering row's `seq` against the last `agent_input` event's seq — kernel-computable from durable `run_events`); the acceptance bar is the no-loss/no-duplicate pair of tests.

### Guardrails (LOCKED — POR §7)
- INV-1/SC-001: every new branch keys on generic identity (`strategy`, `task_id`, `worker_index`, event types) — zero workflow-name/agent-id literals in the kernel; banned-pattern gate green.
- INV-2: cursor/transient state on `ExecutionContext` or durable rows, never the singleton.
- INV-3: the 5 characterization goldens byte/event-identical every plan (`SNAPSHOT_UPDATE` unset); all new machinery DORMANT on scripted golden runs; ZERO new WS event types preferred (if unavoidable: additive + `_VOLATILE_STRIP_KEYS` + `_DOCUMENTED_EVENT_TYPES`, the P28 pattern).
- INV-12: single `_execute_impl`/`run_fanout` dispatch path (the `enumerate(ordered_agents)` pin stays 1); reuse `resume_run`/`_stamp_resume_marker`/the merge machinery; no parallel capture writer.
- INV-5: no manifest DSL; control flow in strategies + resume tier. INV-13: deepagents only.
- Ports & adapters: capabilities reach the kernel via `ctx.runner` handles; engine reaches app only via injected callables; `lint-imports` 4/0.
- The Phase-45 fix and its two tests must stay green; the KAN-88 red stays red and untouched.

### Execution constraints (LOCKED — standing)
- Branch `feat/ui-2` ONLY. NO commit trailers. NEVER push. NEVER `git stash`.
- python3.11, no venv; targeted pytest ONLY (full suite hangs offline); `/opt/homebrew/bin/lint-imports` from `backend/`.
- NO live Bedrock in executors (orchestrator owns live proofs; milestone-end live pass covers the ladder).
- Migration proven reversible on offline SQLite (`alembic upgrade head` → `downgrade -1` → `upgrade head`).

### Claude's Discretion
- Generic-capture mechanism: sandbox-delta detection (snapshot file list/mtimes before task → diff after) vs FilesystemBackend write-interception vs extending the post-task persist hook to walk changed files — pick the simplest that is correct for the offline harness AND live, and INV-3-dormant.
- The completed-set threading shape into `strategy.run` (a field on `ExecutionContext` — e.g. `resume_completed_task_ids: set[str] | None` — vs a strategy kwarg; prefer the ectx-field idiom used by other resume state).
- Steering drained/undrained derivation (seq-comparison heuristic or equivalent), per the no-loss/no-duplicate acceptance pair.
- Plan/wave decomposition (likely 3-5 plans: migration+spawn-stamping · generic capture · re-materialization+merge-re-entry · skip cursor · live-layer+steering) and wave ordering.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Plan of record + tracking
- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` — POR §2 (substrate + resume tier), §3 (isolation/merge/uploads), §5.1/5.3/5.4/5.8, §6-R1, §7, §9 (anchor index). READ FULLY.
- `.planning/ROADMAP.md` — "### Phase 46" block (8 success criteria) + the v3.0 milestone header guardrails.
- `.planning/REQUIREMENTS.md` — RESUME-06..11.
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 11 (fan-out: run_fanout/isolation/merge/budget; CR-02 isolated-write wiring), Phase 12 (wave scheduler + resume tier: D-01..D-18, CR-03/CR-04 mid-wave semantics, Pitfalls 1-2), Phase 43 (live-ectx registry + milestone_sink + DEF-43-03-1), Phase 44 (run_engine.py relocation; SSE-only), Phase 30 (per-turn images/steering seams), quick 260615-dzk (selections re-apply on resume).
- `.planning/phases/45-resume-completeness-bug-fix-r0/` — the Phase-45 fix + tests this phase builds on (45-RESEARCH.md's anchor tables are fresh).

### Code under change / at risk (verify anchors — they drift)
- `backend/app/models/subagent_run.py` + `backend/alembic/versions/` (head 0025) — the migration surface.
- `backend/agents/execution_engine/fanout.py` — worker spawn/record sites, merge path, `_completed_wave_indices` consumers.
- `backend/agents/execution_engine/kernel_services.py` — `persist_task_html` (:1313-1339), `write_fragment_artifact` (:705-761), handles.
- `backend/agents/capabilities/strategies/task_loop.py` — loop start :233, persist call sites :290-296/:358-366.
- `backend/agents/capabilities/strategies/wave_scheduler.py` — wave skip logic.
- `backend/agents/execution_engine/engine.py` — resume tier (:4815-6237 region), `_first_incomplete_step` (now with the 45 fix), `_hydrate_artifacts_from_store`, `MilestoneSink`/`LiveEctxRegister` aliases (:41/:51), `execute()` params (:903-904), `_compose_context_message` steering drain.
- `backend/agents/execution_engine/context.py` — `steering_notes`, `pending_turn_images`/`turn_images_once`, resume fields.
- `backend/app/api/run_commands.py` — `_LIVE_ECTX` (:373-415), the callback injection site (:1355), `_load_pending_proposal`.
- `backend/app/api/run_engine.py` — `_register_resume_queue`/`_register_resume_task` (:91/:100), queues/cancel registries.
- `backend/app/main.py` — the startup restore-scan / bridge wiring (where auto-resume callbacks get injected).
- `backend/agents/authz.py` — ScopedStore (write_ref/tree/read_events), `append_event_next_seq` (do NOT use for engine-emitted events).
- `backend/agents/artifacts/graph.py` — ArtifactRef fields + ARTIFACT_KINDS vocabulary.
- `backend/app/agents/sandbox.py` — RunSandbox read/write/root, `_UPLOADS_PREFIX` (exclude from capture).
- Tests: `backend/tests/agents/test_restart_resume.py` (+ the 2 Phase-45 tests), `test_wave_scheduler.py`, `test_fanout*.py`, `test_subagent_runs.py`, `test_migrations.py`/migration-ledger, the 5 `test_characterization_*.py`, `test_sse_stream.py`/`test_attach_replay_matrix.py` (must stay green).

</canonical_refs>

<specifics>
## Specific Ideas

- The capture must EXCLUDE the `.uploads/` prefix (Phase 47's surface) and never capture images (ND-10).
- The fix-loop re-persists an edited task file under the SAME task_id (task_loop.py:358-366) — capture and cursor must treat that as a new VERSION of the same task's artifacts (distinct-id counting, the Phase-45 lesson).
- Fragments already persist BEFORE merge (`write_fragment_artifact` with task_id=worker_index) — the merge re-entry consumes those existing rows; only the merge invocation is new resume logic.
- `restore_non_terminal_runs` branch (b) currently creates `asyncio.create_task(resume_run)` — the live-ectx register/unregister must wrap THAT task's lifecycle (register before first dispatch, unregister in finally), mirroring the launch wrapper at run_commands.py:1355.
- Offline harness reality (register 11-05): fan-out runs `shared_read` offline with no base workspace — per-worker isolated-write redirection is live-only; design tests accordingly (seed durable rows directly, drive the classifier/strategies offline — the Phase-45 test idiom).

</specifics>

<deferred>
## Deferred Ideas

- Content-addressed `task_key` + reconciliation → Phase 48.
- Uploads durable mirror → Phase 47.
- Gate re-arm → Phase 49. REST resume endpoint → Phase 50 (this phase only SHAPES the callback seam it will reuse).
- Live-Bedrock proof of the full crash→resume ladder → milestone-end live pass (orchestrator-owned).

</deferred>

---

*Phase: 46-per-task-substrate-cursor-live-layer-r1*
*Context gathered: 2026-07-19 via POR Ingest Express Path (decisions pre-locked in POR §8)*
