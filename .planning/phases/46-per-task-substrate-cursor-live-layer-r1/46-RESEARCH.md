# Phase 46: Per-Task Substrate, Cursor & Live-Layer Re-Registration [R1] — Research

**Researched:** 2026-07-19
**Domain:** Kernel resume-tier — task-identity migration, generic per-task capture, durable→disk re-materialization + merge re-entry, per-worker/per-task skip cursor, live-layer re-registration, steering re-drain
**Confidence:** HIGH (every anchor re-opened on `feat/ui-2` this session; POR §9 anchors that drifted post-Phase-45 re-verified; targeted suites run offline)
**Requirements:** RESUME-06, RESUME-07, RESUME-08, RESUME-09, RESUME-10, RESUME-11

---

## Summary

Six requirements, five natural plans. **The substrate mostly exists** — this phase closes the wiring gaps. RESUME-06 is a mechanical 3-layer column add (`worker_index`+`task_id` on `subagent_runs`, stamped at `fanout.py:368`, task_id threaded from `wave_scheduler` requests). RESUME-07's generic capture is best done by an **extended post-task sandbox walk** at the `persist_task_html` seam, reusing the already-existing `_collect_deliverable_relpaths` walk (which already excludes `.uploads/`), writing the declared file byte-identically as `html_file` and each *other* changed file as `file_bundle` (dedup by latest durable `content_hash`) — subsumes `persist_task_html`, no dual writer. RESUME-08 adds a re-materialization step next to `_hydrate_artifacts_from_store` writing latest-version durable refs back onto the `sandbox` local (reachable at `engine.py:1350`), plus mid-wave merge re-entry reusing `wave_scheduler`/`run_fanout`. RESUME-09 threads a kernel-computed `resume_completed_task_ids` ectx field (mirroring `is_resuming`) into `task_loop` (skip completed task_nums) and `wave_scheduler` (skip completed workers by `task_id`). RESUME-10 is the highest-leverage fix: **`resume_run` calls `_execute_impl` DIRECTLY (`engine.py:6241`), bypassing the `execute()` wrapper's callback threading** — inject `milestone_sink`/`live_ectx_register`+`unregister` as engine-instance hooks at `app/main.py:141` (same site as `_resume_register_queue`), and replicate the DEF-43-03-1 seq-advance card-emission in `resume_run`'s loop (currently `itertools.count`). RESUME-11 re-derives undrained steering notes from durable `chat_message` rows whose `seq > max(agent_input.seq)`.

**Suggested plan split (5 plans, wave order by dependency×risk):**
- **Plan 46-01 — Migration + spawn-stamping (RESUME-06):** migration 0026 + ORM + 3-layer `record_subagent_run` threading + wave_scheduler task_id thread. Foundation for 09.
- **Plan 46-02 — Generic per-task capture (RESUME-07):** extend the `persist_task_html` seam to a generic walk. Independent of 01.
- **Plan 46-03 — Re-materialization + merge re-entry (RESUME-08):** depends on 02's captured rows existing.
- **Plan 46-04 — Skip cursor (RESUME-09):** depends on 01 (subagent_runs identity) + 03 (re-materialized disk).
- **Plan 46-05 — Live-layer + steering re-drain (RESUME-10 + RESUME-11):** independent of 01–04; the `resume_run` callback wiring + DEF-43-03-1 card replication + steering re-derive.

---

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **RESUME-06:** additive nullable `task_id` (String) + `worker_index` (Integer) on `subagent_runs`; head 0026 (after `0025_deep_link_nonces`); `batch_alter_table.add_column` only, NO new table, NO destructive alter, reversible single-head (SQLite upgrade→downgrade→upgrade offline). Rows written **at SPAWN** (fanout worker-spawn path stamps `worker_index`; `task_id` when the worker maps to a task).
- **RESUME-07:** every file a task wrote is durably captured per task; contract fixed — after each task, all files that task created/changed dual-write as `artifact_refs` tagged with that task's `task_id`; the declared-deliverable capture stays byte-compatible (`html_file` row keeps exact kind/location/content — INV-3). EVENT-FREE, best-effort; ZERO new WS event types. Must SUBSUME `persist_task_html` (not a second uncoordinated writer — INV-12). Prefer reusing `file_bundle`; a new `ARTIFACT_KINDS` member only if genuinely needed (additive, P13 `"deliverable"` precedent). EXCLUDE `.uploads/`; never images (ND-10).
- **RESUME-08:** resume-tier step beside `_hydrate_artifacts_from_store` (which stays graph-only) walks latest durable `artifact_refs` (by `location`, `max(version)`, filtered to completed steps/tasks) and writes them back onto the fresh `RunSandbox` BEFORE strategies re-enter. Durable mirror is the SOURCE (never git). Mid-wave merge re-entry: re-materialize the in-flight wave's fragments + re-run the merge before dispatching remaining workers/waves — reuse the existing `fanout.py` merge machinery. All reads via the run's owner-scoped `ScopedStore`.
- **RESUME-09:** the KERNEL computes the completed set (from `subagent_runs` identity + per-task `artifact_refs`) and threads it into `strategy.run`; the AGENT never decides skip (still receives completed work as injected context, unchanged). `task_loop` skips completed task numbers; `wave_scheduler` skips completed WORKERS within the in-flight wave (identity-based, NOT prefix-by-count). Terminal-completed waves stay skipped. Re-invocation via the SAME `_run_agent`/`run_fanout` paths (INV-13).
- **RESUME-10:** BOTH resume paths thread the SAME two callbacks the REST launch threads at `run_commands.py:1355` — `register_live_ectx` (+guaranteed unregister in `finally`) and `milestone_sink=persist_milestone_card`. Engine NEVER imports `app.*` (generic callables, `MilestoneSink`/`LiveEctxRegister` aliases). Inject at the app-layer auto-resume call site (`app/main.py` restore scan). Milestone-card `seq` from the engine's own counter (DEF-43-03-1; 0024 constraint) — never `append_event_next_seq`. Acceptance: `_live_ectx_for_run(run_id)` resolves on a resumed run + narrator cards emit contiguously.
- **RESUME-11:** durably-logged-but-undrained steering notes re-queued onto `ectx.steering_notes` at resume; an already-drained note must NOT be duplicated. Drained-vs-undrained is discretion (seq compare). Acceptance = the no-loss/no-duplicate test pair.

### Claude's Discretion
- Generic-capture mechanism (sandbox-delta snapshot/diff vs FilesystemBackend write-interception vs extended post-task walk) — pick the simplest correct offline AND live, INV-3-dormant.
- Completed-set threading shape (`ExecutionContext` field vs strategy kwarg — prefer the ectx-field idiom, e.g. `resume_completed_task_ids: set[str] | None`).
- Steering drained/undrained derivation (seq-comparison heuristic or equivalent).
- Plan/wave decomposition (likely 3–5 plans).

### Deferred Ideas (OUT OF SCOPE — hard fences)
- Content-addressed `task_key` + mutable-list reconciliation → **Phase 48** (in THIS phase the cursor keys on the EXISTING positional durable ids: `task_id = str(task_num)` for task_loop, `worker_index`/`task_id=t.id` for waves).
- Uploads durability → **Phase 47** (exclude `.uploads/`).
- Gate re-arm / the KAN-88 red test → **Phase 49** (leave `test_waiting_for_user_run_is_rearmed_not_driven` RED, untouched).
- REST resume endpoint → **Phase 50** (this phase only SHAPES the callback seam).
- ND-10 images (locked non-goal — resumed runs lose `run_images` BY DESIGN, document, never fix); git-as-substrate (GIT-01); cross-node (N8); mid-token resume.

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RESUME-06 | `subagent_runs` task identity (`task_id`+`worker_index`), stamped at spawn | Migration Recipe; anchors `subagent_run.py`, `authz.py:1072`, `kernel_services.py:434`, `fanout.py:368`, `wave_scheduler.py:245` |
| RESUME-07 | GENERIC per-task capture (every file a task wrote) | Generic-Capture Mechanism; anchors `kernel_services.py:1313`, `task_loop.py:293/358`, `sandbox.py:208` walk, `graph.py:52` kinds |
| RESUME-08 | Durable→disk re-materialization + mid-wave merge re-entry | Re-Materialization; anchors `engine.py:5865/1349`, `sandbox.py:138`, `fanout.py:617/819` merge |
| RESUME-09 | Per-worker/per-task skip via kernel cursor | Skip Cursor; anchors `task_loop.py:233`, `wave_scheduler.py:217-262`, `context.py:236` |
| RESUME-10 | Resumed run = first-class LIVE run (live-ectx + milestone-sink) | Live-Layer Wiring; anchors `resume_run engine.py:6241`, `execute() 944-1026`, `run_commands.py:1355/376`, `app/main.py:141` |
| RESUME-11 | Steering re-drain (no-loss/no-duplicate) | Steering Re-Drain Rule; anchors `engine.py:6588`, `chat_router.py:325`, `run_commands.py:429/785`, `agent_input engine.py:2997` |

---

## Verified Current-State Anchors (file:line, quoted)

All line numbers re-verified 2026-07-19 on `feat/ui-2`. **Note:** Phase 45 inserted ~58 lines into `_first_incomplete_step`, so POR §9 numbers for anything below `engine.py:6002` shifted; the anchors below are the CURRENT numbers.

### Alembic head + migration recipe
- Head = **`0025_deep_link_nonces`** (confirmed `ls alembic/versions/`). Next = **0026**.
- The additive-column recipe (`0023_workflow_run_selections.py`, verbatim):
```python
revision = "0023"; down_revision = "0022"
def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.add_column(sa.Column("selections_json", sa.JSON(), nullable=True))
def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("selections_json")
```
`0022` adds two columns the same way (drop in reverse order in `downgrade`).

### `subagent_runs` ORM (`app/models/subagent_run.py:28-50`)
Free-String `isolation`/`status`, `Integer depth`, named FK `parent_run_id → workflow_runs.id`, `Index("ix_subagent_runs_parent")`. **No `task_id`/`worker_index` today** — the gap.

### The spawn/record chain (RESUME-06 surface)
- `fanout.py:368` (inside `_run_one`, `idx`=worker_index in scope):
```python
row_id = await runner.record_subagent_run(
    parent_step=step_id, worker_agent=agent_id,
    depth=depth, isolation=isolation, status="running",
)
```
- `_select_workers` builds the worker dict and **drops extra request keys** (`fanout.py:115`):
```python
selected.append({"index": i, "agent_id": resolved, "input": req.get("input", "")})
```
- `wave_scheduler.py:244-245` — the wave's task ids ARE known and map positionally to `idx`:
```python
task_ids = [t.id for t in wave]
requests = [{"agent": "self", "input": t.body} for t in wave]
```
- Chain: `fanout.record_subagent_run` → `KernelServices.record_subagent_run` (`kernel_services.py:434`, delegates) → `ScopedStore.record_subagent_run` (`authz.py:1072`, inserts `SubagentRun(...)`). **All three signatures + the ORM ctor need the two new params.**

### Per-task capture today (RESUME-07 root)
`persist_task_html` (`kernel_services.py:1313-1339`) — single-file, `kind="html_file"` hardcoded:
```python
task_html = self.sandbox.read(filename)
if not task_html: return
await self._engine._dual_write_artifact(
    self._ectx, producer_agent=agent_id, producer_step=agent_id,
    content=task_html, kind="html_file", location=filename, task_id=str(task_num))
```
Call sites `task_loop.py:293-296` (post-task) and `:358-366` (post-fix, re-persists SAME `task_id`, guarded by `post_fix_html != pre_fix_html`). Both `if hasattr(runner, "persist_task_html")` — the SEAM.

The reusable walk already exists (`sandbox.py:208-250`, `_collect_deliverable_relpaths`): walks `root`, **already excludes `_UPLOADS_PREFIX=".uploads/"`** (`:244`) and `PLANNER.md`, sorts, returns POSIX relpaths. `serialize_sandbox_deliverable` (`:253`) reads via `read_bytes().decode("utf-8")` (CRLF-preserving, byte-oracle pinned).

### `ARTIFACT_KINDS` vocabulary + kind-keyed readers (RESUME-07 kind choice)
`graph.py:52-70` — `file_bundle` and `html_file` are already members; advisory-validated (`write_ref` logs, never raises, `*_output` carve-out). `ArtifactRef` (`graph.py:73-101`): `task_id: str|None`, `content`, `content_hash`, `location`, `version` (monotonic per `(run_id, kind)`).
- **Routing is by `producer_agent` id, NOT kind** (`engine.py:5410-5449`, `_AGENT_KIND_MAP` is a lineage-only label; `prototype-build→html_file`).
- **Only ONE kind-keyed reader:** `engine.py:870` `_surface_partial_fragments` reads `kind in ("file_bundle","fragment")` for the budget-abort partial-results payload. Siblings tagged `file_bundle` from a task_loop would appear there. Golden-dormant (goldens never hit budget abort), but a design consideration (see mechanism recommendation).

### `_dual_write_artifact` (`engine.py:5451-5507`) + `_hydrate_artifacts_from_store` (`engine.py:5865-5907`)
The SOLE artifact write path (in-memory graph + best-effort scoped-store row; `SQLAlchemyError` degrades). Hydration reads `store.tree(run_id)` and `adopt()`s each row into the graph **preserving id/hash/version — graph-only, never to disk**. The re-materialization step is the missing disk half.

### The resume tier (RESUME-08/09/10 surface)
- `restore_non_terminal_runs` (`engine.py:4815-4964`), 3-way: (a) `waiting_for_user → failed` (KAN-88, `:4868`); (b) `_is_resumable_in_flight → asyncio.create_task(self.resume_run(pipeline_run_id))` (`:4919`); (c) else `failed`. Branch (b) also calls `self._resume_register_queue(...)` synchronously BEFORE `create_task` (`:4910`) and `self._resume_register_task(...)` after (`:4927`).
- `resume_run` (`engine.py:6088-6294`) — **calls `self._execute_impl(...)` DIRECTLY at `:6241`** with `_sink = _RunEventSink()` (`:6238`, NO milestone_sink) and stamps seq via `itertools.count(start)` (`:6239`). It does NOT thread `live_ectx_register`, does NOT emit milestone cards, and has NO `live_ectx_unregister` in its `finally`. **This is Gap F.** `start = max(durable seq)+1` (`:6194-6200`).
- The `execute()` wrapper (`engine.py:944-1026`) is what threads all three callbacks + the DEF-43-03-1 card emission — but `resume_run` bypasses it.
- The re-materialization hook point: `_execute_impl` builds the `sandbox` local at `engine.py:1132` (`RunSandbox(disk_principal, pipeline_run_id)`, `.ensure()`), and hydrates at `engine.py:1349-1350` (`if _resume_from > 0: await self._hydrate_artifacts_from_store(ectx)`). `sandbox` is in scope there → re-materialization writes via `sandbox.write(location, content)`.
- `_compute_resume_offset` (`engine.py:6296-6337`) builds a temp ectx + compiled plan and calls `_first_incomplete_step` (returns int offset). The offset skip consumer is `_execute_impl:2063` (`if i < _resume_from: continue`).

### Skip-cursor sites (RESUME-09)
- `task_loop.py:233` — `for task_num in range(1, total_tasks + 1):` (NO skip today; always starts at 1).
- `wave_scheduler.py:217-262` — reads `is_resuming` (`ctx.is_resuming`, `getattr` at `:219`), computes `_completed_wave_indices` from `read_wave_runs()` step-filtered (`:222-227`), skips terminal waves wholesale (`:240`), re-runs the first-incomplete wave IN ENTIRETY (`:243`), flips stale `running` rows to `superseded` (WR-01, `:253-262`). The `:207-214` comment explicitly documents that per-worker skip is blocked on the missing `subagent_runs` identity — **exactly what RESUME-06 unblocks.**
- `ExecutionContext.is_resuming: bool = False` is a DECLARED dataclass field (`context.py:236`) — the additive-dormant-field precedent for the new cursor field.

### Live-layer wiring (RESUME-10)
- Aliases: `MilestoneSink` (`engine.py:41`), `LiveEctxRegister`/`LiveEctxUnregister` (`engine.py:51-52`) — generic callables, no app import.
- `execute()` params `milestone_sink`/`live_ectx_register`/`live_ectx_unregister` (`engine.py:903-905`); the DEF-43-03-1 seq loop (`engine.py:944-1012`): `next_seq` manual counter; per event `sink.emit_milestone_card(event)`; if a card is created, `next_seq = _card_seq+1` and the card is `yield`ed with `event_id=f"chat_reply:{event_id}"`. Unregister in `finally` (`:1018-1026`).
- Launch site `run_commands.py:1349-1382`: `engine.execute(..., live_ectx_register=register_live_ectx, live_ectx_unregister=unregister_live_ectx, milestone_sink=persist_milestone_card)`.
- `_LIVE_ECTX` registry (`run_commands.py:373-415`): `register_live_ectx(run_id, ectx)` (idempotent — docstring `:382` explicitly notes "a resumed run re-registers its rebuilt ctx"), `unregister_live_ectx` (`pop` default), `_live_ectx_for_run(run_id)`.
- App-layer injection precedent (`app/main.py:140-144`):
```python
from app.api import run_engine as _ws_bridge
engine_instance._resume_register_queue = _ws_bridge._register_resume_queue
engine_instance._resume_register_task = _ws_bridge._register_resume_task
engine_instance._resume_cleanup = _ws_bridge._cleanup_pipeline
await engine_instance.restore_non_terminal_runs()
```
Engine ctor declares the hook slots default-None (`engine.py:817-819`).

### Steering machinery (RESUME-11)
- Durable drain/consume (`engine.py:6588-6605`): reads `ectx.steering_notes`, renders `=== USER GUIDANCE ===`, then **consume-once keeping only `sticky` notes**.
- `apply_steering(ectx, note)` (`chat_router.py:325-340`) appends `{"text","sticky"}`; no-op if `ectx` is None. Steering-channel routing at `chat_router.py:315-319` (PHASE_RUNNING + plain text → `CHANNEL_STEERING`).
- Durable record: EVERY chat turn persists via `_persist_chat_message` (`run_commands.py:429-469`, called at `:785` BEFORE routing) → `store.append_event_next_seq(run_id, event_id=_chat_event_id(message_id), type="chat_message", payload_json={pipeline_run_id, message_id, text, attachments})`. **The payload carries `text` but NOT `sticky` and NOT the routed channel/action** (route is derived post-persist at `:816`).
- `agent_input` is a normal engine event (`engine.py:2997-3000`), persisted with a monotonic `seq` through the sink — so `max(seq of agent_input rows)` is durably queryable from `run_events`.
- `context.py:265-266` confirms the design intent: `steering_notes` "across `resume_run` is re-derived from the persisted `run_events` chat turns (ND-9)".

---

## Migration Recipe (RESUME-06)

**Three layers + one thread + the ORM ctor.**

1. **Migration `0026_subagent_task_identity.py`** — clone `0023` verbatim shape:
```python
revision = "0026"; down_revision = "0025"
def upgrade():
    with op.batch_alter_table("subagent_runs") as b:
        b.add_column(sa.Column("task_id", sa.String(), nullable=True))
        b.add_column(sa.Column("worker_index", sa.Integer(), nullable=True))
def downgrade():
    with op.batch_alter_table("subagent_runs") as b:
        b.drop_column("worker_index")
        b.drop_column("task_id")
```
2. **ORM** (`subagent_run.py`): add `task_id = Column(String, nullable=True)`, `worker_index = Column(Integer, nullable=True)`. Existing FK/index untouched.
3. **`ScopedStore.record_subagent_run`** (`authz.py:1072`): add `worker_index: int|None=None, task_id: str|None=None` kwargs → pass to `SubagentRun(...)` ctor.
4. **`KernelServices.record_subagent_run`** (`kernel_services.py:434`): same two kwargs → pass through to `store.record_subagent_run(...)`.
5. **`fanout.py`:** `_select_workers:115` preserves `"task_id": req.get("task_id")`; `_run_one:368` passes `worker_index=idx, task_id=worker.get("task_id")`.
6. **`wave_scheduler.py:245`:** `requests = [{"agent": "self", "input": t.body, "task_id": t.id} for t in wave]` so each row carries the plan-global task id.

**Worker→task mapping is deterministic:** `worker_index=idx` is the position in the wave's `requests`/`selected` (0-based); `task_id=t.id` is the plan-global id (`wave.task_ids[idx]`). `worker_index` alone is ambiguous across waves (each `run_fanout` call restarts `idx` at 0), so **the skip cursor must key on `task_id`** (globally unique), with `worker_index` as an audit/ordering aid.

**task_loop does NOT create `subagent_runs` rows** (verified — sequential, no fan-out; its per-task record is the `artifact_refs` written by `persist_task_html`). So RESUME-06 is a fan-out/wave-only surface; the task_loop skip cursor (RESUME-09) reads `artifact_refs.task_id`, not `subagent_runs`.

**Verification:** offline SQLite `alembic upgrade head → downgrade -1 → upgrade head`. Do NOT rely on `test_migrations.py::test_migration_0016/0023_down_revision_*` — they are pre-existing STALE single-head asserts (`heads == ["0016"]` at head 0025, already RED). Add a `test_migration_0026_is_additive` following the *source-assertion* pattern (`test_migrations.py:194-212`: assert `down_revision="0025"`, `add_column` present, `drop_column`/`alter_column`/`drop_table` absent from `upgrade`).

---

## Generic-Capture Mechanism (candidates → recommendation)

**Contract (LOCKED):** after each task, capture every file that task created/changed; declared deliverable file stays byte-identical `html_file`; exclude `.uploads/` + images; EVENT-FREE; subsume `persist_task_html` (INV-12, no second writer).

| Candidate | Correct offline? | Correct live? | INV-3-dormant? | Verdict |
|-----------|------------------|---------------|----------------|---------|
| **(A) Extended post-task sandbox walk** at the persist seam | ✅ (offline harness writes to the same `RunSandbox` disk — the seam reads `self.sandbox`) | ✅ (deepagents `FilesystemBackend` lands writes on the same disk the walk reads) | ✅ (goldens: only `prototype.html` present → identical `html_file` row; siblings dedup to zero) | **RECOMMENDED** |
| (B) FilesystemBackend write-interception | needs a runner-adapter hook per write; offline scripted models don't drive the real backend uniformly | live-only | risk of touching the runner event path | Rejected — more surface, harder to keep dormant |
| (C) Sandbox-delta snapshot/diff (mtimes before/after) | needs a pre-task snapshot hook (a second call site) | mtime granularity flaky | extra state | Rejected — 2 call sites, weaker than content-hash dedup |

**Recommendation — (A):** replace `persist_task_html`'s body with a generic capture that:
1. Enumerates changed files with the **existing** `_collect_deliverable_relpaths(sandbox.root, exclude=_DELIVERABLE_EXCLUDE)` (already excludes `.uploads/` + `PLANNER.md`) — one import, no new walk logic, INV-3-proven exclusions.
2. For the **declared deliverable filename**: write byte-identically as today (`kind="html_file"`, `location=filename`, `content=sandbox.read(filename)`, `task_id=str(task_num)`) — preserves the prototype `html_file` row exactly.
3. For **every OTHER changed file**: `_dual_write_artifact(..., kind="file_bundle", location=relpath, task_id=str(task_num))` **only when** its content differs from the latest durable ref for that `location` (dedup by `content_hash` via `store.tree()` / the graph) — so unchanged siblings don't spawn runaway versions and a task that touched nothing new writes nothing.
4. Read file content the SAME way it will be re-materialized (see CRLF note below) for round-trip symmetry.

**Kind choice — reuse `file_bundle`, do NOT add a member.** `file_bundle` is already in `ARTIFACT_KINDS` and already used for fan-out fragments; routing is by `producer_agent` id so no consumer mis-routes. **One caveat:** `_surface_partial_fragments` (`engine.py:870`) reads `file_bundle` for the budget-abort partial payload — a task_loop's siblings would now appear there. This is *semantically correct* (they ARE partial results) and golden-dormant (goldens never budget-abort). If the planner wants strict isolation from that reader, an additive `"task_file"` member (P13 `"deliverable"` precedent) is the fallback — but `file_bundle` is preferred per CONTEXT and avoids a vocabulary change. **Document the `_surface_partial_fragments` interaction either way.**

**Subsumption (INV-12):** the two `hasattr(runner, "persist_task_html")` call sites (`task_loop.py:293/358`) stay — the method is *extended in place* (same name, same seam), so there is no parallel writer. The post-fix re-persist (`:358`) naturally re-captures the edited file as a new version under the same `task_id` (distinct-id counting per the Phase-45 lesson).

---

## Re-Materialization + Merge Re-Entry (RESUME-08)

### Durable → disk
Add `_rematerialize_artifacts_to_disk(ectx, sandbox)` invoked at `engine.py:1350` immediately after `_hydrate_artifacts_from_store` (which stays graph-only). It:
1. `rows = await store.tree(ectx.run_id)` (owner-scoped; same read hydrate uses).
2. Group by `location`, keep `max(version)` per location.
3. **Filter out:** `location.startswith(".uploads/")` (Phase 47); `kind == "merge_conflict"` (not a deliverable file); the typed metadata kinds that have no on-disk file (`spec`/`plan`/`task_list`/`clarifications`/`summary`/`planning_context` — these are graph-only handoffs, already restored by hydrate; re-materializing them to disk under their `location` is harmless only if their `location` is a real file path — restrict to the file-bearing kinds `html_file`/`file_bundle`/`deliverable`, or to rows whose `location` looks like a relpath). **Recommend: re-materialize only `kind in {"html_file","file_bundle","deliverable"}`** — the file-backed kinds — matching what the generic capture writes.
4. `sandbox.write(location, content)` for each (traversal-proof via `path_for`).

**CRLF/bytes (R1 refold note):** `serialize_sandbox_deliverable` reads raw bytes + explicit UTF-8 decode to preserve `\r`/`\r\n` (`sandbox.py:271-277`); `sandbox.write` → `LocalWorkspace.write_file` writes UTF-8. Capture and re-materialize must be symmetric: if the generic capture reads via `sandbox.read` (LocalWorkspace.read_file), re-materialize via `sandbox.write` — the stored `str` round-trips. **Do NOT mix** a raw-bytes capture with a `write_text`-newline-translating restore. Keep both on the `sandbox.read`/`sandbox.write` pair (symmetric) OR both on raw-bytes; note this as a byte-parity edge for the deliverable oracle.

**Scope of "completed":** re-materialize latest-version file rows for all completed steps/tasks (offset > 0), AND the in-flight wave's persisted fragments (needed by merge re-entry even at offset==0). Simplest correct rule: re-materialize ALL latest file-backed rows for the run (a not-yet-superseded fragment on disk is harmless — the re-run overwrites it deterministically into an isolated workspace). Run whenever `_is_resume` (mirror the CR-01 workspace-recovery reasoning at `engine.py:1245-1257`), not only offset>0.

### Merge re-entry
Crash window: `run_fanout` persists each completed worker's fragments via `write_fragment_artifact` (`fanout.py:447-457`) **BEFORE** `_merge_fragments` (`fanout.py:617`). If the process died between fragment-persist and merge, the wave's `wave_runs` row is still `running` (never flipped `completed` at `wave_scheduler.py:296`).

**Durable evidence merged-vs-unmerged:** `wave_runs.status` — `completed` ⇒ merge ran (wave skipped wholesale); `running`/absent ⇒ the in-flight wave, merge NOT done. In live `shared_read`/`copy_disjoint` mode the merge only needs the fragment files back on disk. Today `wave_scheduler` (`:253-262`) flips a stale `running` row to `superseded` then **re-runs the whole wave** (re-spawns every worker). Phase 46 improves this: for the in-flight wave, (1) re-materialize its fragments (§ above), (2) **skip the completed workers** (RESUME-09), (3) re-run only the incomplete workers + the merge. The minimal re-entry reuses `runner.run_fanout(requests, ctx, step=step)` with the completed-worker requests filtered out — the merge inside `run_fanout` (`_merge_fragments`) then runs over whatever completed (re-materialized + newly-run) fragments. **No second merge implementation** — the existing `run_fanout`→`_merge_fragments` path IS the re-entry, driven by a shorter `requests` list. Fragments that were re-materialized to disk are picked up by `_fragment_files(worker_ws)` in shared/copy mode.

*(Offline harness reality, register 11-05: fan-out runs `shared_read` with no base workspace; per-worker isolated-write redirection is live-only. Test merge re-entry by seeding durable fragment rows + `wave_runs` rows directly and driving the classifier/strategy — the Phase-45 seed-durable-then-classify idiom.)*

---

## Skip Cursor (RESUME-09)

**Threading shape (discretion → recommend ectx field).** Add a declared dormant field to `ExecutionContext` (mirroring `is_resuming: bool = False` at `context.py:236`):
```python
resume_completed_task_ids: dict[str, set[str]] | None = None  # {step_id: {task_id,...}}, None on a normal run
```
Compute it kernel-side in the resume tier (in `_execute_impl` after hydrate, or in `_compute_resume_offset`'s companion) and stamp it on `ectx` BEFORE the dispatch loop. Strategies read `getattr(ctx, "resume_completed_task_ids", None)` (dormant/None on normal runs → byte-identical).

**Completed-set computation (kernel-side):**
- **task_loop step:** `{ r.task_id for r in store.tree(run_id) if r.producer_agent == step_agent and r.task_id is not None }` — the DISTINCT `task_id` set (fix-loop re-persists the same id, so a `set` de-dups — the Phase-45 caveat). This is the same durable read the Phase-45 completeness fix already does.
- **wave step:** from `subagent_runs` (post-RESUME-06) — `{ r.task_id for r in read_subagent_runs(run_id) if r.parent_step == step_id and r.status == "complete" and r.task_id }`. Key on `task_id` (plan-global), NOT `worker_index` (wave-local, ambiguous).

**Consumption:**
- `task_loop.py:233` loop: `if resume_completed and str(task_num) in resume_completed.get(step_id, set()): continue` (skip the agent invocation; the file is already on disk from re-materialization, so the NEXT task's skeleton read is coherent — existing context machinery unchanged).
- `wave_scheduler.py`: in the first-incomplete wave's dispatch (`:243-245`), filter `requests`/`task_ids` to the workers whose `t.id` is NOT in the completed set (identity-based, NOT the deleted-for-cause prefix-by-count skip 12-06 CR-03). Terminal-completed waves stay skipped via the existing `_completed_wave_indices` (`:240`, untouched).

**INV-13:** re-invocation of remaining work stays on `runner.run_agent`/`runner.run_fanout` → `DeepAgentRunner` — no new agent loop. **Agents receive prior completed work via the existing context machinery** (`latest_typed_content` reads the hydrated graph / the re-materialized disk) — unchanged.

---

## Live-Layer Wiring (RESUME-10)

**Root problem (verified):** `resume_run` calls `_execute_impl` DIRECTLY (`engine.py:6241`) and hand-rolls the seq/persist loop with `_RunEventSink()` (no milestone_sink) + `itertools.count` (`engine.py:6238-6239`) — it never threads `live_ectx_register`, never emits milestone cards, and has no `live_ectx_unregister` in `finally`. So a resumed run is dead to steering/images/Concierge/narrator.

**Minimal wiring (three engine-instance hooks, injected app-side — no engine→app import):**
1. Add three default-None slots in the engine ctor (beside `_resume_register_queue` at `engine.py:817-819`): `self._resume_milestone_sink`, `self._resume_live_ectx_register`, `self._resume_live_ectx_unregister`.
2. Set them at `app/main.py:141` (same block as the queue/task hooks) from the app-layer callables the launch path uses: `register_live_ectx` / `unregister_live_ectx` / `persist_milestone_card` (all in `run_commands.py`, no kernel import).
3. In `resume_run`:
   - `sink = _RunEventSink(milestone_sink=self._resume_milestone_sink)` (instead of `_RunEventSink()` at `:6238`).
   - Pass `live_ectx_register=self._resume_live_ectx_register` into the `_execute_impl(...)` call (`:6241`) — `_execute_impl:1184` already registers the ectx when the callback is present.
   - Add `finally`: `if self._resume_live_ectx_unregister: self._resume_live_ectx_unregister(run_id)` (guaranteed unregister, mirroring `execute():1018`). Fold into the existing `finally` at `:6280` (which already does `_fire_resume_cleanup`).
4. **Milestone-card seq (DEF-43-03-1) — replicate in `resume_run`'s loop.** Currently `itertools.count(start)` (`:6239`) can't be advanced past a card seq. Restructure to the manual `next_seq = start` counter and replicate `execute():982-1012`: stamp `seq = next_seq; next_seq += 1`; after `sink.persist(...)`, call `card_result = await sink.emit_milestone_card(event)`; if a card is created, `if _card_seq >= next_seq: next_seq = _card_seq + 1` and `yield` the `chat_reply` with `event_id=f"chat_reply:{event_id}"`, ALSO pushing it onto `live_queue` (the resume path already pushes events to `live_queue` at `:6271-6277`). This keeps resumed-run cards contiguous on the 0024 `(run_id, seq)` constraint — never `append_event_next_seq`.

**Idempotent register:** `register_live_ectx` overwrites (docstring `run_commands.py:382`), so a resumed run re-registering its rebuilt ectx is safe. Keyed on `run_id` only (SC-001).

**Phase-50 seam:** the same three engine hooks (or a param-threaded variant of `resume_run`) are what the future `POST /resume` endpoint reuses — build the hook now, consume in 50. No endpoint here.

---

## Steering Re-Drain Rule (RESUME-11)

**Durable source:** `chat_message` `run_events` rows (`run_commands.py:429-469`), each with a `seq` and `payload_json.text`. `agent_input` events (`engine.py:2997`) are persisted with `seq`.

**Drained-vs-undrained heuristic (seq compare — the POR rule, verified viable):**
- `last_input_seq = max(seq for run_events rows where type == "agent_input")` (0 if none).
- A steering `chat_message` row is **undrained** iff its `seq > last_input_seq` (no dispatch consumed guidance after it arrived) AND it carries non-empty `text`.
- On resume, re-queue each undrained note's `text` onto `ectx.steering_notes` (as `{"text": ..., "sticky": False}`) BEFORE the first re-dispatch. This is **no-loss** (undrained notes survive) and **no-duplicate** (drained ones have `seq < last_input_seq` → skipped; the engine's own consume-once at `engine.py:6603` then drops them after one render).

**Classification gap (flag for the planner — honest):** the `chat_message` payload does NOT carry the routed channel or `sticky` (route is derived post-persist at `run_commands.py:816`). So a durable `chat_message` row cannot be *definitively* distinguished as "steering" vs a clarify-answer / gate-action turn from the row alone. **Why this is acceptable for Phase 46's scope:** branch-(b) auto-resume only fires for in-flight (generating/running) runs, NOT `waiting_for_user` (branch (a) → failed, Phase 49). During a running phase, plain-text turns route to steering anyway (`chat_router.py:315`), and gate actions/answers don't occur mid-dispatch. So "text present + `seq > last_input_seq`" ≈ undrained steering note for the in-flight-resume case. Document this bound; the content-addressed classification is Phase 48/49 territory.

**Sticky edge (defer to Phase 47):** a *drained* sticky note (uploaded-context) re-renders every dispatch by design (`engine.py:6603`); its row `seq < last_input_seq` so the heuristic won't re-queue it → sticky uploaded context is lost on resume. But sticky notes = uploaded-document context, whose durability is **Phase 47** (Q6). For Phase 46, target UNDRAINED one-shot notes only; note the sticky-on-resume loss as a Phase-47-covered gap. The `sticky` flag is not in the durable row, so re-queued notes are one-shot (`sticky=False`) — correct for undrained notes (they drain on the next dispatch).

**Where to invoke:** a `_redrain_steering_notes(ectx)` helper called in the resume tier (in `_execute_impl` when `_is_resume`, after ectx construction, before the dispatch loop) — reads `store.read_events(run_id, 0)`, computes the rule, appends to `ectx.steering_notes`. Dormant on normal runs (no resume).

---

## Edge Cases

1. **Fix-loop re-persist under the same `task_id`** (`task_loop.py:358-366`): capture and cursor must count DISTINCT `task_id`, not rows/versions (a `set`). The generic capture writes a new version of the edited file under the same `task_id` — correct (latest version wins at re-materialization).
2. **`_surface_partial_fragments` reader** (`engine.py:870`): task_loop siblings tagged `file_bundle` will surface in the budget-abort payload. Semantically correct + golden-dormant; document. (Fallback: additive `"task_file"` kind if strict isolation is wanted.)
3. **CRLF byte-parity:** capture-read and re-materialize-write must be symmetric (both `sandbox.read`/`sandbox.write`, or both raw-bytes). The deliverable byte-oracle (`test_sandbox_deliverable.py`) reads raw bytes — keep the generic-capture content faithful.
4. **`.uploads/` exclusion:** both the generic walk (already excludes via `_collect_deliverable_relpaths`) and re-materialization (filter `location.startswith(".uploads/")`) must exclude it — Phase 47's surface. Images never captured (ND-10).
5. **worker_index ambiguity across waves:** `worker_index` restarts at 0 per `run_fanout` call; the skip cursor MUST key on `task_id` (plan-global), not `worker_index`.
6. **Merge re-entry at offset==0:** the in-flight wave step IS the first incomplete step (offset points at it); its completed workers' fragments must still be re-materialized + skipped. Re-materialization runs on `_is_resume`, not only offset>0.
7. **DEF-43-03-1 seq collision:** if `resume_run` keeps `itertools.count`, a milestone card drawn from the store's next seq would collide with the counter's next value → the engine's best-effort persist DROPS the event → durable-log gap on reconnect. Must switch to the advanceable manual counter.
8. **`input_hash` stability (Pitfall 1):** completed-step reuse (`engine.py` input_hash = sorted upstream content_hashes, no timestamp/uuid) must stay stable — the new re-materialization writes files but does NOT change content_hashes (it restores the exact stored `content`), so reuse keys are unperturbed.
9. **Workspace recovery (Pitfall 2):** re-materialization + the cursor read the ORIGINAL workspace_id (`_recover_workspace_id`, `engine.py:1253-1259` / `:6314`), never a fresh `create_workspace` — else owner+workspace-scoped reads resolve to ∅.
10. **0024 seq uniqueness:** every resume-emitted event (incl. cards) draws seq from the engine counter seeded at `max(durable seq)+1` (`resume_run:6194`); never `append_event_next_seq` (out-of-band chat allocator only).
11. **asyncio lifecycle (WR-01 registry-leak precedent, 12-REVIEW):** the live-ectx unregister must run in `resume_run`'s `finally` (normal completion, exception, or GeneratorExit) beside the existing `_fire_resume_cleanup(run_id)` — no leaked `_LIVE_ECTX[run_id]` after a resumed run ends.
12. **Golden dormancy per new seam:** goldens never call `resume_run`/`_first_incomplete_step`/the capture-of-siblings (a golden prototype run writes only `prototype.html` → the generic capture produces the identical single `html_file` row, siblings=∅). The 5 characterization suites (10 tests) must stay 10/10 with `SNAPSHOT_UPDATE` unset — the INV-3 proof for EACH new seam (migration, capture, re-materialization, cursor, live-layer, steering).
13. **Offline harness shared_read reality (register 11-05):** per-worker isolated-write redirection is live-only; seed durable rows directly and drive classifier/strategies offline (Phase-45 idiom) for merge-re-entry + skip tests.

---

## At-Risk Tests & Pre-Phase Baseline (real pytest output, 2026-07-19, `feat/ui-2`, python3.11, backend/ cwd, offline)

| Suite | Result | Notes |
|-------|--------|-------|
| `test_restart_resume.py` | **8 passed, 1 failed** | The 1 fail = `test_waiting_for_user_run_is_rearmed_not_driven` (KAN-88 / Phase-49 anchor — LEAVE RED) |
| `test_wave_scheduler.py` | **10 passed** | wave build/dispatch/mid-wave |
| `test_subagent_runs.py` | **13 passed** | migration-touched — must stay green after the column add |
| `test_fanout.py` | **21 passed** | spawn/merge/isolation |
| `test_fanout_cancel.py` | **6 passed** | cancel/teardown |
| `test_sc001_fanout.py` | **4 passed** | banned-pattern / agnostic |
| `test_migrations.py` | **27 passed, 2 failed, 7 skipped** | **Both failures PRE-EXISTING + stale:** `test_migration_0016_down_revision_is_0015` and `test_migration_0023_down_revision_is_0022` assert `heads == ["0016"]`/`["0023"]` at head 0025. NOT Phase-46-caused; will remain RED |
| `test_migration_ledger.py` | green (part of Phase-45's `34 passed, 7 skipped` battery) | banned-pattern deletion ledger, not alembic head |
| `test_sse_stream.py` | (in `28 passed, 1 failed` bundle) | green portion |
| `test_attach_replay_matrix.py` | **1 failed** (`TestMidStreamResume::test_last_event_id_header_resumes_over_http`, `assert '3' in ['2']`) | **PRE-EXISTING** SSE Last-Event-Id resume flake — verify-by-delta; not Phase-46-caused |
| `test_characterization_*.py` (5 files) | **10 passed** (per Phase-45, `SNAPSHOT_UPDATE` unset) | INV-3 gate — must stay 10/10 |

**Combined at-risk sweep** (restart_resume + wave + subagent + 3 fanout): **61 passed, 1 failed** (KAN-88 anchor only). Verbatim KAN-88 red:
```
tests/agents/test_restart_resume.py:898: assert row.status == "waiting_for_user"
E   AssertionError: assert 'failed' == 'waiting_for_user'
```

**Pre-phase baseline to defend (verify-by-delta):**
- `test_restart_resume.py`: 8 pass / 1 fail (KAN-88) — the fail count must NOT increase.
- `test_migrations.py`: 2 stale-head fails are PRE-EXISTING — Phase 46 must not add a THIRD (the new `0026` source-assertion test must PASS; the stale 0016/0023 asserts stay their pre-existing red).
- `test_attach_replay_matrix.py`: the 1 SSE fail is pre-existing.
- 5 characterization goldens: 10/10 (INV-3).

---

## Pitfalls

1. **INV-12 single dispatch path.** Re-enter the SAME `_execute_impl`/`run_fanout`; extend `persist_task_html` in place (don't add a second capture writer); reuse `run_fanout`→`_merge_fragments` for merge re-entry (no second merge impl); the `enumerate(ordered_agents)` pin stays at 1. Do NOT add a third launch driver.
2. **INV-1 / banned-pattern gate.** Key ONLY on generic identity (`strategy`, `task_id`, `worker_index`, `producer_agent`, event types). Zero `pipeline_type ==` / `spec.id ==` / `"prototype-build"` literals in the kernel. The `_AGENT_KIND_MAP` `prototype-build→html_file` is a pre-existing lineage label, not a new branch — don't add cousins.
3. **INV-2 no per-run engine state.** Cursor/steering-redrain/re-materialization state on `ExecutionContext` or durable rows — never `self._*`. Add `resume_completed_task_ids` as a declared dormant ectx field (mirror `is_resuming`).
4. **INV-3 golden dormancy per seam.** Each of the 5 new seams (migration/capture/re-materialization/cursor/live-layer/steering) must be dormant on scripted golden runs; prove with 10/10 characterization + `SNAPSHOT_UPDATE` unset. ZERO new WS event types (the capture is EVENT-FREE; cards ride the existing `chat_reply`).
5. **0024 seq + DEF-43-03-1.** Resume-emitted events + milestone cards draw seq from the engine counter (`max(durable)+1`, advanceable manual counter), never `append_event_next_seq`. Switching `resume_run` off `itertools.count` is mandatory for cards.
6. **Pitfall 1 (input_hash stability):** re-materialization restores exact stored `content` → content_hashes unchanged → step-reuse keys stable.
7. **Pitfall 2 (workspace recovery):** always `_recover_workspace_id`, never fresh-mint on resume.
8. **Distinct task_id counting** (fix-loop re-persist) — `set`, not row count.
9. **Migration verification** — do NOT trust the stale `test_migrations.py` head asserts; prove reversibility via `alembic upgrade→downgrade→upgrade` on SQLite + a source-assertion test.
10. **asyncio lifecycle (WR-01):** unregister live-ectx in `resume_run`'s `finally` — no `_LIVE_ECTX` leak.
11. **Offline harness shared_read (11-05):** isolated writes are live-only; seed durable rows for tests.
12. **CRLF symmetry:** capture-read ↔ re-materialize-write must be the same codec pair (deliverable byte-oracle).
13. **lint-imports 4/0:** engine reaches app only via injected callables (`milestone_sink`/`live_ectx_register`/`_resume_*`); no `from app...` in the kernel.

---

## Validation Architecture

Framework: **pytest** + `pytest-asyncio`, `python3.11 -m pytest` from `backend/`, offline, no venv. Full suite hangs offline — targeted only. `/opt/homebrew/bin/lint-imports` from `backend/`.

### Requirement → test map (exact commands + expected outcomes)

| Req | Behavior | Command | Expected |
|-----|----------|---------|----------|
| RESUME-06 | 0026 additive + reversible | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` (SQLite); `pytest tests/unit/test_migrations.py -k "0026 or additive" -x` | reversible; new source-assertion test GREEN |
| RESUME-06 | subagent rows carry `task_id`/`worker_index` at spawn | `pytest tests/agents/test_subagent_runs.py tests/agents/test_fanout.py -q` | 13+21 pass; new assertion on stamped identity |
| RESUME-07 | multi-file task captured; prototype byte-neutral | `pytest tests/agents/test_characterization_prototype.py -q` (byte-neutral) + a NEW multi-file task_loop capture test | goldens 10/10; sibling `file_bundle` rows present in the multi-file fixture |
| RESUME-08 | latest durable files re-materialized to disk; merge re-entry | NEW `test_restart_resume.py` cases (seed durable rows → assert `sandbox.read(location)` restored; seed mid-wave fragments+`running` wave_run → assert merge re-runs) | RED→GREEN |
| RESUME-09 | completed task/worker skipped, not re-invoked | NEW `test_restart_resume.py` cases (partial task_loop: completed task_num not re-dispatched; wave: completed worker `task_id` filtered from requests) | RED→GREEN |
| RESUME-10 | resumed run resolves `_live_ectx_for_run` + emits cards | NEW test: drive `resume_run` with injected sink+register stubs → assert ectx registered + a `chat_reply` card yielded with engine-counter seq | RED→GREEN |
| RESUME-11 | undrained steering re-queued; drained not duplicated | NEW no-loss/no-duplicate pair (seed `chat_message` rows around `agent_input` seq → assert `ectx.steering_notes` after re-drain) | both GREEN |
| INV-3 | 5 goldens byte/event-identical (all seams dormant) | `pytest tests/agents/test_characterization_*.py -q` (`SNAPSHOT_UPDATE` unset) | `10 passed` |
| INV-1/12 | no name literal; single dispatch loop | `pytest tests/agents/test_banned_patterns.py tests/agents/test_sc001_fanout.py -q`; `grep -c 'enumerate(ordered_agents)' engine.py` | green; `1` |
| Import purity | kernel imports only ports | `/opt/homebrew/bin/lint-imports` | `Contracts: 4 kept, 0 broken` |
| Regression | KAN-88 stays red; no new fails | `pytest tests/agents/test_restart_resume.py tests/agents/test_wave_scheduler.py -q` | `8 passed, 1 failed` unchanged |

### Sampling / gates
- **Per task commit (quick):** the plan's targeted new test(s) + `test_restart_resume.py` (~2s) — RED→GREEN + KAN-88 unchanged.
- **Per wave merge:** `pytest tests/agents/test_restart_resume.py tests/agents/test_wave_scheduler.py tests/agents/test_subagent_runs.py tests/agents/test_fanout.py tests/agents/test_characterization_*.py tests/agents/test_banned_patterns.py -q` + `lint-imports` (~50s).
- **Phase gate (before `/gsd-verify-work`):** goldens 10/10 · banned-pattern green · lint-imports 4/0 · new RED→GREEN per criterion · KAN-88 still red · the 2 pre-existing `test_migrations` stale-head fails unchanged (not increased) · `test_attach_replay_matrix` pre-existing fail unchanged.

### Wave 0 gaps
- New tests: multi-file task_loop capture; re-materialization; merge re-entry; task/worker skip; live-ectx-resolves-on-resume + card-seq; steering no-loss/no-duplicate pair; `test_migration_0026_is_additive`. Reuse the `test_restart_resume.py` seed-durable-then-classify idiom + the Phase-45 fixtures.
- No framework install needed (pytest+asyncio present).

---

## Sources

### Primary (HIGH — code re-opened this session on `feat/ui-2`)
- `backend/agents/execution_engine/engine.py` — aliases `:41/:51`, `execute()` `:884-1026` (DEF-43-03-1 loop), `_execute_impl` sandbox `:1132` + hydrate/rematerialize hook `:1349`, offset skip `:2063`, `agent_input` `:2997`, `_surface_partial_fragments` `:870`, `_AGENT_KIND_MAP` `:5422`, `_dual_write_artifact` `:5451`, `_hydrate_artifacts_from_store` `:5865`, `_first_incomplete_step` `:5909-6064` (Phase-45 branch `:6005`, disjunct `:6059`), `restore_non_terminal_runs` `:4815-4964`, `_stamp_resume_marker` `:5000`, `resume_run` `:6088-6294`, `_compute_resume_offset` `:6296`, steering drain `:6588-6605`, engine ctor hooks `:817`.
- `backend/agents/execution_engine/fanout.py` — `run_fanout` `:241`, `_select_workers` `:78-116`, `_run_one` record `:368` + fragment persist `:445-457`, merge dispatch `:617`, `_merge_fragments` `:819`.
- `backend/agents/capabilities/strategies/wave_scheduler.py` — mid-wave skip `:217-262`, dispatch `:235-300`.
- `backend/agents/capabilities/strategies/task_loop.py` — loop `:233`, persist sites `:293-296/:358-366`.
- `backend/agents/execution_engine/kernel_services.py` — `record_subagent_run` `:434`, `write_fragment_artifact` `:705-761`, `persist_task_html` `:1313-1339`.
- `backend/agents/authz.py` — `record_subagent_run` `:1072`, `update`/`read` `:1115/:1148`, `record_wave_run`/`read_wave_runs` `:1180/:1238`, `tree` `:277`.
- `backend/agents/artifacts/graph.py` — `ARTIFACT_KINDS` `:52`, `ArtifactRef` `:73`, `write_ref` `:118`, `adopt` `:182`.
- `backend/app/agents/sandbox.py` — `RunSandbox` `:60`, `write`/`read` `:138/:144`, `_UPLOADS_PREFIX` `:41`, `_collect_deliverable_relpaths` `:208`, `serialize_sandbox_deliverable` `:253`.
- `backend/app/api/run_commands.py` — `_LIVE_ECTX`/register `:373-415`, `_persist_chat_message` `:429`, turn persist `:785`, steering dispatch `:852-873`, launch callbacks `:1349-1382`.
- `backend/app/api/chat_router.py` — `apply_steering` `:325`, steering route `:315`.
- `backend/app/main.py` — resume-bridge injection + restore scan `:140-144`.
- `backend/agents/execution_engine/context.py` — `is_resuming` `:236`, `steering_notes` `:271`, `pending_turn_images` `:288`.
- `backend/app/models/subagent_run.py` `:28-50`; `backend/alembic/versions/0019/0022/0023`.
- Live test runs (this session): the at-risk sweep (61 pass / 1 KAN-88 fail), `test_migrations` (27p/2 stale-fail), SSE (`attach_replay` 1 pre-existing fail).

### POR / register (HIGH — read fully)
- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` §2/§3/§4/§5.1-5.4/§5.8/§6-R1/§7/§9.
- `.planning/phases/46-.../46-CONTEXT.md` (locked decisions); `.planning/phases/45-.../45-RESEARCH.md` + `45-01-SUMMARY.md` (fresh anchors + shipped completeness fix).
- `.planning/REQUIREMENTS.md` RESUME-06..11; `.planning/ROADMAP.md` "### Phase 46" (8 SC).

## Metadata
**Confidence:** Anchors HIGH (every file re-opened, POR §9 post-Phase-45 drift re-verified). Mechanism recommendations HIGH (extended-walk reuses proven exclusion code; live-layer wiring proven by reading `resume_run` bypass). Steering classification MEDIUM (durable row lacks channel/sticky — bounded by in-flight-resume scope, documented). Baseline HIGH (run this session).
**Research date:** 2026-07-19 · **Valid until:** ~2026-08-18 (re-verify line numbers if `engine.py` churns).

## RESEARCH COMPLETE

1. **RESUME-06** is a mechanical 3-layer column add (`subagent_run.py` ORM → `authz.py:1072` → `kernel_services.py:434`) + stamp `worker_index=idx`/`task_id=worker.get("task_id")` at `fanout.py:368`, with `wave_scheduler.py:245` threading `task_id=t.id` and `_select_workers:115` preserving it. Migration 0026 clones the `0023` batch-add recipe.
2. **RESUME-07** — recommend the **extended post-task walk** at the `persist_task_html` seam, reusing `_collect_deliverable_relpaths` (already excludes `.uploads/`); declared file stays `html_file`, siblings `file_bundle` (dedup by content_hash). Only reader of `file_bundle` is `_surface_partial_fragments` (`engine.py:870`) — golden-dormant, documented.
3. **RESUME-08** — re-materialize latest file-backed rows onto the `sandbox` local at `engine.py:1350`; merge re-entry reuses `run_fanout`→`_merge_fragments` with completed workers filtered; `wave_runs.status` is the merged/unmerged discriminator.
4. **RESUME-09** — add a declared dormant `resume_completed_task_ids` ectx field (mirror `is_resuming`); task_loop skips by `artifact_refs.task_id`, waves skip by `subagent_runs.task_id`. Agents still get context via `latest_typed_content` (unchanged).
5. **RESUME-10** — the load-bearing find: `resume_run` calls `_execute_impl` DIRECTLY (`engine.py:6241`), bypassing `execute()`'s callbacks. Inject three engine hooks at `app/main.py:141`, pass into `resume_run`, replicate the DEF-43-03-1 seq-advance card loop (switch off `itertools.count`), unregister in `finally`.
6. **RESUME-11** — re-derive undrained steering from `chat_message` rows with `seq > max(agent_input.seq)`; no-loss/no-duplicate; classification bound to in-flight-resume scope (durable row lacks channel/sticky — documented, sticky-on-resume deferred to Phase 47).
7. **Baseline (offline, this session):** at-risk sweep 61 pass / 1 fail (KAN-88 anchor, leave red); `test_migrations` has 2 PRE-EXISTING stale-head fails; `test_attach_replay_matrix` 1 pre-existing fail; goldens 10/10. Suggested split: 5 plans (migration+stamp · capture · re-materialize+merge · cursor · live-layer+steering).
8. **Guardrails:** every seam INV-3-dormant on goldens, INV-1 name-free, INV-2 ectx/durable-only, INV-12 single dispatch/merge/capture path, 0024 seq from the engine counter, lint-imports 4/0, KAN-88 stays red.
