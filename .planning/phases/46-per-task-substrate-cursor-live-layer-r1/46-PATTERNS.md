# Phase 46: Per-Task Substrate, Cursor & Live-Layer Re-Registration [R1] — Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** ~14 kernel/app files across 8 surfaces (5 suggested plans)
**Analogs found:** 8 / 8 surfaces (every surface has a copy-from analog already in-tree)
**Effort:** MAXIMUM — every excerpt below re-opened on `feat/ui-2` this session; line numbers verified against the current file on disk. Drift from CONTEXT/RESEARCH citations is called out in the **Anchor Verification** table at the bottom.

> This is a brownfield wiring phase: the substrate mostly exists. For nearly every new
> line the closest analog is *in the same file* (an existing dormant-seam / additive-column /
> resume-tier pattern). The planner should copy the in-file precedent, not invent a shape.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/alembic/versions/0026_subagent_task_identity.py` (NEW) | migration | batch DDL | `alembic/versions/0023_workflow_run_selections.py` | exact |
| `backend/app/models/subagent_run.py` (MOD) | model | ORM column-add | `subagent_run.py` existing `tokens`/`cost` nullable cols (`:42-43`) | exact (in-file) |
| `backend/agents/authz.py` `ScopedStore.record_subagent_run` (MOD) | store/adapter | insert | same method's existing `tokens`/`cost` kwargs (`:1081-1082/:1105-1106`) | exact (in-file) |
| `backend/agents/execution_engine/kernel_services.py` `record_subagent_run` (MOD) | service | delegate pass-through | same method (`:434-463`) | exact (in-file) |
| `backend/agents/execution_engine/fanout.py` `_select_workers`/`_run_one` (MOD) | service | fan-out spawn | worker-dict build `:115` / record site `:368` | exact (in-file) |
| `backend/agents/capabilities/strategies/wave_scheduler.py` (MOD) | strategy | pub-sub dispatch | requests build `:244-245` / `is_resuming` skip block `:217-262` | exact (in-file) |
| `backend/agents/execution_engine/kernel_services.py` `persist_task_html` → generic capture (MOD-in-place) | service | file-I/O + dual-write | `persist_task_html` (`:1313-1339`) + `sandbox._collect_deliverable_relpaths` (`:208-250`) | exact |
| `backend/agents/execution_engine/engine.py` `_rematerialize_artifacts_to_disk` (NEW method) | service | durable→disk transform | `_hydrate_artifacts_from_store` (`:5865-5907`) — the graph-only twin | role+flow (mirror) |
| `backend/agents/execution_engine/context.py` `resume_completed_task_ids` (NEW field) | model | dormant scratch | `is_resuming: bool = False` (`:236`) + `steering_notes` (`:271`) | exact (in-file) |
| `backend/agents/capabilities/strategies/task_loop.py` loop skip (MOD) | strategy | request-response | the `range(1, total_tasks+1)` loop (`:233`) | exact (in-file) |
| `backend/agents/execution_engine/engine.py` `resume_run` live-wire (MOD) | service | callback threading | `execute()` wrapper (`:944-1026`) — the seq/card/register/unregister reference impl | exact (in-file mirror) |
| `backend/app/main.py` resume-hook injection (MOD) | config/wiring | app→engine injection | `_resume_register_queue`/`_task`/`_cleanup` block (`:140-144`) | exact (in-file) |
| `backend/agents/execution_engine/engine.py` `_redrain_steering_notes` (NEW) + steering drain (existing) | service | event-derive | drain seam `:6588-6605` + `chat_router.apply_steering` (`:325-340`) | role+flow |
| `backend/tests/agents/test_restart_resume.py` (+ new cases) | test | seed-durable-then-invoke | `_build_partial_build_fixture` (`:952-1047`) + `test_resumed_events_seq_continues_past_durable_tail` (`:798-874`) | exact |
| `backend/tests/unit/test_migrations.py` `test_migration_0026_is_additive` (NEW) | test | source-assertion | `test_migration_0023_is_additive_only` (`:193-212`) | exact |
| `backend/tests/agents/test_subagent_runs.py` reversibility (NEW) | test | alembic round-trip | `test_0019_reversible_offline` (`:77-110`) + `test_0019_migration_uses_free_string_status` (`:113-119`) | exact |

---

## Pattern Assignments

### Plan 46-01 — Migration 0026 + spawn stamping (RESUME-06)

#### `0026_subagent_task_identity.py` (migration) — analog `0023_workflow_run_selections.py`

**Copy this** batch-add recipe verbatim, swap table + columns (`0023` lines 34-45 on disk):
```python
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("subagent_runs") as b:
        b.add_column(sa.Column("task_id", sa.String(), nullable=True))
        b.add_column(sa.Column("worker_index", sa.Integer(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("subagent_runs") as b:
        b.drop_column("worker_index")
        b.drop_column("task_id")
```
**Deviate:** `down_revision="0025"` (NOT `"0022"`), two columns (drop in reverse order). Keep the `0023`-style module docstring naming the additive/INV-3 rationale (the `0023` docstring is the template — the `0022` precedent it cites already drops two cols in reverse).

#### `subagent_run.py` (ORM) — analog: the existing nullable cols in the SAME class

Existing precedent (`subagent_run.py:42-43`, verified):
```python
    tokens = Column(Integer, nullable=True)          # accumulated child tokens
    cost = Column(JSON, nullable=True)               # cost_class-weighted (€ dormant)
```
**Copy this** shape — add beside them (INV-3: nullable, no FK/index change; `String`/`Integer` already imported at `:22`):
```python
    task_id = Column(String, nullable=True)          # RESUME-06: plan-global task id (skip-cursor key)
    worker_index = Column(Integer, nullable=True)    # RESUME-06: wave-local worker position (audit)
```

#### `ScopedStore.record_subagent_run` (`authz.py:1072-1113`) — in-file analog: its own `tokens`/`cost` kwargs

Signature already carries the two-optional-kwarg pattern (`:1081-1082`):
```python
        tokens: int | None = None,
        cost: Any = None,
    ) -> str:
```
and the ctor already threads them (`:1105-1106`):
```python
                tokens=tokens,
                cost=cost,
```
**Copy this**: add `worker_index: int | None = None, task_id: str | None = None` to the signature and `worker_index=worker_index, task_id=task_id,` to the `SubagentRun(...)` ctor (`:1095-1107`).

#### `KernelServices.record_subagent_run` (`kernel_services.py:434-463`) — in-file pass-through

Same-name delegate; signature `:442-443` and the `store.record_subagent_run(...)` call `:458-463`. **Copy this**: add the two kwargs to the signature and forward them in the delegate call. Best-effort None-degrade already present (`:454-456`) — untouched.

#### `fanout.py` — two edit points, both verified

`_select_workers` builds the worker dict and **drops** every request key except three (`:115`):
```python
        selected.append({"index": i, "agent_id": resolved, "input": req.get("input", "")})
```
**Deviate:** add `"task_id": req.get("task_id")` so the plan-global id survives to the record site.

`_run_one` records at `:368-374` (`idx` = worker index in scope, `agent_id` resolved):
```python
        row_id = await runner.record_subagent_run(
            parent_step=step_id,
            worker_agent=agent_id,
            depth=depth,
            isolation=isolation,
            status="running",
        )
```
**Deviate:** add `worker_index=idx, task_id=worker.get("task_id"),`. (`idx` restarts at 0 per `run_fanout` call → `worker_index` is wave-local; the cursor keys on `task_id`.)

#### `wave_scheduler.py:244-245` — request build

Current (verified — no task_id today):
```python
            task_ids = [t.id for t in wave]
            requests = [{"agent": "self", "input": t.body} for t in wave]
```
**Deviate:** `requests = [{"agent": "self", "input": t.body, "task_id": t.id} for t in wave]` so each spawned row carries the plan-global id. (`task_ids` list stays for the `wave_runs` row.)

---

### Plan 46-02 — Generic per-task capture (RESUME-07)

#### `persist_task_html` → generic walk (`kernel_services.py:1313-1339`) — extend IN PLACE (INV-12)

Current body (verified `:1328-1339`) — this is what must stay byte-identical for the declared file:
```python
        task_html = self.sandbox.read(filename)
        if not task_html:
            return
        await self._engine._dual_write_artifact(
            self._ectx,
            producer_agent=agent_id,
            producer_step=agent_id,
            content=task_html,
            kind="html_file",
            location=filename,
            task_id=str(task_num),
        )
```
**Copy this** as branch 1 (declared deliverable → `kind="html_file"`, unchanged). **Add** a sibling walk after it, reusing the existing exclusion-proven walk from `sandbox.py`:

`_collect_deliverable_relpaths(root, exclude)` (`sandbox.py:208-250`, verified) already:
- walks `root`, emits regular files only (`:237-238`),
- **excludes `.uploads/`** via `if relpath.startswith(_UPLOADS_PREFIX): continue` (`:244-245`) — the ND-10/Phase-47 fence, free,
- excludes `exclude_set`/basename (`:246-247`), sorts (`:249`).

**Copy this** for the sibling enumeration; for each relpath ≠ `filename`, `_dual_write_artifact(..., kind="file_bundle", location=relpath, task_id=str(task_num))` **only when** content differs from the latest durable ref for that location (dedup by `content_hash` — read the graph/`store.tree`). Read via `self.sandbox.read(relpath)` (same codec as branch 1) for CRLF round-trip symmetry with re-materialization.

**Seam is untouched** — the two `if hasattr(runner, "persist_task_html")` call sites stay exactly as-is (`task_loop.py:293-296` post-task, `:358-366` post-fix). The post-fix site (`:363` `post_fix_html != pre_fix_html`) naturally re-captures the edited file as a new version under the same `task_id` — distinct-`task_id` counting (`set`) per the Phase-45 lesson.

**Kind vocabulary** (`graph.py:52-70`, verified): `file_bundle` and `html_file` already members — **reuse `file_bundle`, add nothing**. If strict isolation from the one `file_bundle` reader is wanted, the additive `"task_file"` member follows the `"deliverable"` precedent (`:66`) — but CONTEXT prefers `file_bundle`.

**Document the one reader:** `_surface_partial_fragments` (`engine.py:862-881`) reads `kind in ("file_bundle","fragment")` (`:870`) for the budget-abort partial payload. task_loop siblings would surface there — semantically correct + golden-dormant (goldens never budget-abort). Flag in the plan.

---

### Plan 46-03 — Re-materialization + merge re-entry (RESUME-08)

#### `_rematerialize_artifacts_to_disk` (NEW) — mirror `_hydrate_artifacts_from_store` (`engine.py:5865-5907`)

The hydrate twin is the exact read/loop pattern to copy — it is the **graph-only** half; the new method is the **disk** half. Verified body (`:5877-5907`):
```python
        store = getattr(ectx, "scoped_store", None)
        if store is None:
            return
        try:
            rows = await store.tree(ectx.run_id)
        except Exception:  # noqa: BLE001 — offline / schema-less → empty graph
            return
        for row in rows or []:
            try:
                ectx.artifacts.adopt(_GraphRef(... id/kind/.../version ...))
            except Exception:  # noqa: BLE001
                continue
```
**Copy this** owner-scoped read + best-effort degrade shape. **Deviate:** instead of `ectx.artifacts.adopt(...)`, group rows by `location` keeping `max(version)`, filter to `kind in {"html_file","file_bundle","deliverable"}` AND drop `location.startswith(".uploads/")`, then `sandbox.write(location, content)` for each. `sandbox.write` (`sandbox.py:138-142`) → `LocalWorkspace.write_file`, traversal-proof via `path_for` (`:130-136`). Read/write codec must pair with the capture (`sandbox.read`/`sandbox.write`; the CRLF note — `serialize_sandbox_deliverable` docstring `:270-277`).

#### Hook point — verified injection seam

`engine.py:1349-1350` (verified), immediately after the `sandbox` local exists (`:1132 RunSandbox(disk_principal, pipeline_run_id)`):
```python
        if _resume_from > 0:
            await self._hydrate_artifacts_from_store(ectx)
```
**Copy this** call-site shape; add `await self._rematerialize_artifacts_to_disk(ectx, sandbox)` here (gate on `_is_resume`, not only `_resume_from > 0`, per Edge-Case 6: the in-flight wave at offset==0 needs its fragments back on disk). `sandbox` is in scope at `:1350`.

#### Merge re-entry — reuse `run_fanout`→`_merge_fragments`, no second impl

Fragments already persist BEFORE merge (verified `fanout.py:445-457`, `write_fragment_artifact` with `worker_index=idx`). The merged-vs-unmerged discriminator is `wave_runs.status`: the wave row is flipped `completed` only at `wave_scheduler.py:296` (`await runner.update_wave_run(row_id, status="completed")`) — a `running`/absent row ⇒ merge never ran. Today the mid-wave path re-runs the whole wave (`:243-262`); Phase 46 filters completed workers out of `requests` (see 46-04) so the same `run_fanout` merge runs over re-materialized + newly-run fragments. **No new merge code.**

---

### Plan 46-04 — Skip cursor (RESUME-09)

#### `context.py` new field — analog `is_resuming` (`context.py:236`)

Verified precedent (a declared dormant dataclass field with a long INV-3 rationale comment):
```python
    is_resuming: bool = False
```
and `steering_notes: list = field(default_factory=list)` (`:271`). **Copy this** idiom:
```python
    resume_completed_task_ids: dict[str, set[str]] | None = None  # {step_id: {task_id,...}}; None on a normal run → dormant
```
Compute kernel-side in the resume tier, stamp on `ectx` before the dispatch loop; strategies read `getattr(ctx, "resume_completed_task_ids", None)` → `None` on a normal run = byte-identical.

#### `task_loop.py:233` loop — verified

```python
        for task_num in range(1, total_tasks + 1):
            if cancel_event is not None and cancel_event.is_set():
```
**Deviate:** immediately inside the loop add `if <completed set for this step>: continue` skipping the `runner.run_agent(...)` invocation (`:280-288`). Completed set = the DISTINCT `task_id` set from `store.tree(run_id)` where `producer_agent == step_agent` (same durable read the Phase-45 completeness fix uses; `set` de-dups the fix-loop re-persist).

#### `wave_scheduler.py` — verified skip precedent at `:217-262`

The `is_resuming` block (`:219-227`) + the `:207-214` comment explicitly document that per-worker skip is blocked ONLY on the missing `subagent_runs` identity that RESUME-06 now adds. **Copy this** `_resuming`-gated read pattern; in the first-incomplete wave's dispatch (`:244-245`) filter `requests`/`task_ids` to workers whose `t.id ∉ completed_worker_task_ids` (from `read_subagent_runs`, keyed on `task_id`, `status=="complete"`). Terminal waves stay skipped via the untouched `_completed_wave_indices` (`:240`).

---

### Plan 46-05 — Live layer (RESUME-10) + steering re-drain (RESUME-11)

#### `resume_run` live-wire — the reference impl is `execute()` in the SAME file

**The gap (verified `engine.py:6238-6241`):**
```python
        sink = _RunEventSink()                 # :6238 — NO milestone_sink
        counter = itertools.count(start)       # :6239 — can't advance past a card seq
        try:
            async for event in self._execute_impl(
                agents=agents,
                ...
                _sink=sink,
                _resume_from=offset,
                _is_resume=True,
            ):                                 # :6241 — no live_ectx_register threaded
```
and the `finally` (`:6280+`) fires `_resume_cleanup` but has NO live-ectx unregister.

**The reference impl to mirror is `execute()` (`engine.py:944-1026`), verified:**
- `sink = _RunEventSink(milestone_sink=milestone_sink)` (`:944`),
- manual `next_seq` allocator with the DEF-43-03-1 advance (`:952`, `:982-983`, `:999-1012`):
```python
                seq = next_seq
                next_seq += 1
                ...
                card_result = await sink.emit_milestone_card(event)
                if card_result is not None:
                    _created, _card_seq, _card = card_result
                    if _card_seq >= next_seq:
                        next_seq = _card_seq + 1
                    if _created:
                        yield {"type": "chat_reply", "data": {**_card, "seq": _card_seq, "event_id": f"chat_reply:{event_id}"}}
```
- `_execute_impl(..., live_ectx_register=live_ectx_register)` threaded (`:973`),
- `finally: if live_ectx_unregister is not None: live_ectx_unregister(pipeline_run_id)` (`:1013-1026`).

**Copy this into `resume_run`:** switch `_RunEventSink()` → `_RunEventSink(milestone_sink=self._resume_milestone_sink)`; replace `itertools.count(start)` with the manual `next_seq = start` counter + the card-advance block (keep the existing `live_queue.put_nowait` push at `:6271-6277`, ALSO push the card); thread `live_ectx_register=self._resume_live_ectx_register` into the `_execute_impl` call; add the unregister into the existing `finally` at `:6280`.

The register-in-`_execute_impl` consumer already exists (`engine.py:1184-1189`, verified):
```python
        if live_ectx_register is not None:
            try:
                live_ectx_register(pipeline_run_id, ectx)
```

#### Engine ctor hooks — analog `:817-819`

Verified default-None slots:
```python
        self._resume_register_queue: Callable[[str], asyncio.Queue] | None = None
        self._resume_register_task: Callable[[str, asyncio.Task], None] | None = None
        self._resume_cleanup: Callable[[str], None] | None = None
```
**Copy this**: add `self._resume_milestone_sink = None`, `self._resume_live_ectx_register = None`, `self._resume_live_ectx_unregister = None`.

#### `app/main.py:140-144` — analog injection block (verified)

```python
        from app.api import run_engine as _ws_bridge
        engine_instance._resume_register_queue = _ws_bridge._register_resume_queue
        engine_instance._resume_register_task = _ws_bridge._register_resume_task
        engine_instance._resume_cleanup = _ws_bridge._cleanup_pipeline
        await engine_instance.restore_non_terminal_runs()
```
**Copy this**: add three assignments from `run_commands` callables (verified present): `register_live_ectx` / `unregister_live_ectx` (`run_commands.py:376-394`) / `persist_milestone_card`. These are the SAME callables the launch path threads at `run_commands.py:1373-1374/:1381` (verified). Engine never imports `app.*` — generic callables only (`MilestoneSink`/`LiveEctxRegister` aliases, `engine.py:41/:51-52`, verified).

The auto-resume `create_task(self.resume_run(...))` site is `engine.py:4919-4921` (verified) — the hooks are consumed inside `resume_run`, so this site needs no edit.

**Shared registry** `register_live_ectx` is idempotent-by-overwrite (`run_commands.py:382` docstring: *"a resumed run re-registers its rebuilt ctx"*) — resume-safe.

#### Steering re-drain (RESUME-11) — analog: the drain seam + `apply_steering`

The consume site is verified (`engine.py:6588-6605`) — one-shot drop, keep sticky:
```python
        steering_notes = getattr(ectx, "steering_notes", None) or []
        if steering_notes:
            guidance = "\n\n".join(n["text"] for n in steering_notes if isinstance(n, dict) and n.get("text"))
            ...
            ectx.steering_notes = [n for n in steering_notes if isinstance(n, dict) and n.get("sticky")]
```
The append shape is `apply_steering` (`chat_router.py:325-340`, verified):
```python
    queue.append({"text": note.get("text", ""), "sticky": bool(note.get("sticky"))})
```
**Copy this** append shape in a NEW `_redrain_steering_notes(ectx)` called in the resume tier (in `_execute_impl` when `_is_resume`, before the dispatch loop). Derive undrained notes from durable rows:
- durable source `chat_message` rows via `_persist_chat_message` (`run_commands.py:429-469`, verified) — `payload_json` carries `text` + `attachments` but **NOT `sticky` and NOT the routed channel** (route derived post-persist),
- `agent_input` is a seq'd engine event; `last_input_seq = max(seq of agent_input rows)`,
- a `chat_message` row is undrained iff `seq > last_input_seq` and `text` non-empty → append `{"text": ..., "sticky": False}`.

**Flag (honest):** the durable row lacks channel/sticky, so this is bounded to the in-flight-resume case (branch-(b) only fires for running runs, plain text routes to steering — `chat_router.py:315-319`). Sticky-on-resume loss is Phase-47 territory. Document, don't over-engineer.

---

### Plan-wide test idioms (all plans) — analogs in `tests/`

#### Seed-durable-then-invoke — `_build_partial_build_fixture` (`test_restart_resume.py:952-1047`, verified)

The canonical Phase-45 pattern: `_seed_workflow_run` → `ScopedStore(...session=session)` → `pre_store.write_ref(ArtifactRef(... task_id=str(tid), kind="html_file", location="prototype.html" ...))` per task → build a `SimpleNamespace`/real-`Step` compiled plan → build an `ExecutionContext` with `.scoped_store` → drive `engine._first_incomplete_step(tmp, ordered_agents, compiled)`. **Copy this** for capture / re-materialization / skip / merge-re-entry tests (seed durable rows + `wave_runs`; offline `shared_read` reality — register 11-05 — means seed, don't run real isolated writes).

#### resume_run live-wire test — `test_resumed_events_seq_continues_past_durable_tail` (`:798-874`, verified)

Seeds a non-terminal `workflow_runs` row, a durable event tail, then `await engine_b.resume_run(run_id)` and asserts every resumed event's `seq` continues past the tail. **Copy this** to assert (a) the injected `register`/`sink` stubs fire (ectx registered, a `chat_reply` card yielded with engine-counter seq) and (b) unregister runs in `finally`.

#### Migration source-assertion — `test_migration_0023_is_additive_only` (`test_migrations.py:193-212`, verified)

```python
    src = mig.read_text()
    assert 'revision = "0023"' in src
    assert 'down_revision = "0022"' in src
    upgrade_body = src.split("def upgrade")[1].split("def downgrade")[0]
    assert "add_column" in upgrade_body
    assert "drop_column" not in upgrade_body
    assert "alter_column" not in upgrade_body
    assert "drop_table" not in upgrade_body
```
**Copy this** as `test_migration_0026_is_additive` (assert `revision "0026"`, `down_revision "0025"`, both new columns in `upgrade_body`, no destructive ops). **Do NOT** touch the two stale head-asserts (`test_migration_0016/0023_down_revision_*`, `:162/:180`) — they are PRE-EXISTING RED at head 0025.

#### Reversibility round-trip — `test_0019_reversible_offline` (`test_subagent_runs.py:77-110`, verified)

Pins explicit revisions (NOT `head`/`-1`): `command.upgrade(cfg, "0019")` → inspect columns → `command.downgrade(cfg, "0018")` → assert dropped → `command.upgrade(cfg, "0019")`. **Copy this** for 0026 (upgrade 0026 → assert `task_id`/`worker_index` present on `subagent_runs` → downgrade 0025 → assert absent → upgrade 0026). Plus `test_0019_migration_uses_free_string_status` (`:113-119`) for the source-string checks.

---

## Shared Patterns

### Additive-nullable-column trilogy (RESUME-06 spans 3 files)
**Source:** `subagent_run.py:42-43` (ORM) · `authz.py:1081-1082/:1105-1106` (store kwargs+ctor) · `kernel_services.py:442-443/:458-463` (delegate). **Apply to:** every new column — the two-optional-kwarg + ctor-forward pattern is already proven in-file by `tokens`/`cost`.

### Dormant additive ectx field (INV-2/INV-3)
**Source:** `context.py:236` (`is_resuming`), `:271` (`steering_notes`). **Apply to:** `resume_completed_task_ids` — declared field, defaults to the dormant value, strategies read via `getattr(..., None)` → normal runs byte-identical.

### Best-effort owner-scoped durable read (degrade to empty/None)
**Source:** `_hydrate_artifacts_from_store` (`engine.py:5877-5883`): `store = getattr(ectx,"scoped_store",None); if store is None: return; try: rows = await store.tree(...) except Exception: return`. **Apply to:** `_rematerialize_artifacts_to_disk`, the skip-cursor completed-set read, and `_redrain_steering_notes` — never widen scope, never raise into the run.

### App→engine callback injection (no `from app...` in the kernel)
**Source:** `app/main.py:140-144` sets `engine_instance._resume_*`; the kernel declares default-None slots (`engine.py:817-819`) and generic callable aliases (`engine.py:41/:51-52`). **Apply to:** the three new live-layer hooks. `lint-imports` must stay `4 kept, 0 broken`.

### DEF-43-03-1 seq-advance card emission
**Source:** `execute()` (`engine.py:944-1012`) — manual `next_seq`, `sink.emit_milestone_card`, advance `if _card_seq >= next_seq: next_seq = _card_seq + 1`, yield `chat_reply` with `event_id=f"chat_reply:{event_id}"`. **Apply to:** `resume_run` (replaces `itertools.count`). Never `append_event_next_seq` for engine-emitted events (0024 constraint).

### `.uploads/` + image exclusion (Phase-47/ND-10 fence)
**Source:** `sandbox._collect_deliverable_relpaths:244-245` (walk excludes `_UPLOADS_PREFIX`). **Apply to:** the generic capture (free — reuse the walk) AND `_rematerialize_artifacts_to_disk` (filter `location.startswith(".uploads/")`).

---

## No Analog Found

None. Every surface has an in-tree analog — this is a wiring/extension phase. The only genuinely NEW method bodies (`_rematerialize_artifacts_to_disk`, `_redrain_steering_notes`) each mirror an existing method's read/degrade skeleton (`_hydrate_artifacts_from_store` and the `apply_steering`/drain pair respectively).

---

## Anchor Verification (CONTEXT/RESEARCH cited line vs actual on disk, `feat/ui-2`, 2026-07-19)

| Anchor (as cited) | Cited | Actual on disk | Status |
|---|---|---|---|
| Alembic head | `0025_deep_link_nonces` | `0025_deep_link_nonces.py` is last in `ls` | ✅ exact |
| `0023` add-column recipe | `0023:34-45` | `revision="0023"` `:37`, upgrade body `:41-43`, downgrade `:46-48` | ✅ (recipe verbatim; line offsets +3 from docstring) |
| `subagent_run.py` no task_id/worker_index | `:28-50` | class `:28-50`, nullable `tokens`/`cost` `:42-43`; NO task_id/worker_index | ✅ exact |
| `fanout.py` record site | `:368` | `record_subagent_run(...)` opens at `:368` | ✅ exact |
| `_select_workers` drops keys | `:115` | `selected.append({"index","agent_id","input"})` at `:115` | ✅ exact |
| `wave_scheduler` requests build | `:244-245` | `task_ids`/`requests` at `:244-245`, no task_id | ✅ exact |
| `wave_scheduler` mid-wave skip | `:217-262` | `_completed_wave_indices` `:217-227`, stale-flip `:253-262` | ✅ exact |
| `kernel_services.record_subagent_run` | `:434` | method opens `:434` | ✅ exact |
| `authz.record_subagent_run` | `:1072` | method opens `:1072`, ctor `:1095-1107` | ✅ exact |
| `persist_task_html` | `:1313-1339` | def `:1313`, dual-write body `:1328-1339` | ✅ exact |
| task_loop persist call sites | `:290-296` / `:358-366` | post-task `:293-296`, post-fix `:358-366` | ✅ exact |
| `_collect_deliverable_relpaths` walk | `:208` | def `:208`, `.uploads/` exclude `:244-245` | ✅ exact |
| `ARTIFACT_KINDS` / `file_bundle`,`html_file` | `graph.py:52` | frozenset `:52-70`; both members present (`:57-58`) | ✅ exact |
| `_surface_partial_fragments` reader | `engine.py:870` | `if kind in ("file_bundle","fragment")` at `:870` (method `:862`) | ✅ exact |
| `_dual_write_artifact` | `engine.py:5451` | def `:5451` | ✅ exact |
| `_hydrate_artifacts_from_store` | `engine.py:5865-5907` | def `:5865`, loop `:5884-5907` | ✅ exact |
| re-materialization hook point | `engine.py:1349-1350` | `if _resume_from > 0: await self._hydrate...` `:1349-1350`; `sandbox` local `:1132` | ✅ exact |
| offset skip consumer | `:2063` | `if i < _resume_from:` at `:2063` | ✅ exact |
| `execute()` params + card loop | `:903-905` / `944-1026` (`982-1012`) | params `:903-905`; sink `:944`; card block `:999-1012` | ✅ exact |
| `resume_run` | `:6088-6294` | def `:6088`; `_RunEventSink()` `:6238`; `itertools.count(start)` `:6239`; `_execute_impl` call `:6241`; finally `:6280` | ✅ exact (Gap F confirmed) |
| live_ectx register consumer | `_execute_impl:1184` | `if live_ectx_register is not None:` `:1184-1189` | ✅ exact |
| engine ctor hook slots | `:817-819` | `_resume_register_queue/_task/_cleanup` `:817-819` | ✅ exact |
| aliases `MilestoneSink`/`LiveEctxRegister` | `:41` / `:51` | `MilestoneSink` `:41`, `LiveEctxRegister` `:51`, `LiveEctxUnregister` `:52` | ✅ exact |
| `restore_non_terminal_runs` branch (b) | `:4815-4964` (`:4919`) | def `:4815`; `create_task(self.resume_run(...))` `:4919-4921` | ✅ exact |
| `app/main.py` injection block | `:140-144` (`:141`) | bridge import `:140`, assignments `:141-143`, restore `:144` | ✅ exact |
| `run_commands` launch callbacks | `:1355` | `engine.execute(...)` spans `:1349-1382`; **callbacks at `:1373-1374/:1381`, NOT `:1355`** (`:1355` is `user_id=user.id`) | ⚠ loose anchor — the "1355" cite means the launch call block; the actual `live_ectx_register`/`unregister`/`milestone_sink` kwargs are `:1373/:1374/:1381` |
| `_LIVE_ECTX` registry + register | `:373-415` | `_LIVE_ECTX` `:373`, `register_live_ectx` `:376-384` (idempotent docstring `:382`), `_live_ectx_for_run` `:397-415` | ✅ exact |
| `_persist_chat_message` (no sticky/channel) | `:429` | def `:429`, `payload_json` `text`+`attachments` only `:463-468` | ✅ exact (confirms the RESUME-11 classification gap) |
| steering drain / consume-once | `engine.py:6588-6605` | drain `:6588`, one-shot drop/keep-sticky `:6603-6605` | ✅ exact |
| `apply_steering` | `chat_router.py:325` | def `:325`, append `:340`; steering route `:315-319` | ✅ exact |
| `context.py` `is_resuming` / `steering_notes` | `:236` / `:271` | `is_resuming: bool = False` `:236`, `steering_notes` `:271` | ✅ exact |
| Phase-45 seed fixture | `_build_partial_build_fixture` | `:952-1047`, `write_ref(... task_id=str(tid))` `:996-1013` | ✅ exact |
| resume_run seq test | `test_resumed_events_seq_continues_past_durable_tail` | `:798-874` | ✅ exact |
| migration source-assertion | `test_migrations.py:194-212` | `test_migration_0023_is_additive_only` `:193-212` | ✅ exact |
| stale head asserts (leave RED) | `0016`/`0023` down_revision tests | `:162`, `:180` | ✅ exact — DO NOT touch |
| reversibility idiom | `test_subagent_runs test_0019_reversible_offline` | `:77-110`; free-string source test `:113-119` | ✅ exact |

**Only drift:** the `run_commands.py:1355` cite is a loose block anchor — the three callbacks are threaded at `:1373-1374` (`live_ectx_register`/`unregister`) and `:1381` (`milestone_sink`) inside the `engine.execute(...)` call spanning `:1349-1382`. No semantic drift; the planner should reference `:1373-1381` for the exact kwargs. All other anchors are exact (Phase-45's +58-line `engine.py` shift is already reflected in the RESEARCH numbers, which matched disk).

## Metadata

**Analog search scope:** `backend/agents/execution_engine/` (engine, fanout, kernel_services, context), `backend/agents/capabilities/strategies/` (task_loop, wave_scheduler), `backend/agents/authz.py`, `backend/agents/artifacts/graph.py`, `backend/app/agents/sandbox.py`, `backend/app/api/` (run_commands, chat_router), `backend/app/main.py`, `backend/app/models/subagent_run.py`, `backend/alembic/versions/`, `backend/tests/` (test_restart_resume, test_subagent_runs, test_migrations).
**Files scanned:** ~18 (all cited anchors re-opened).
**Pattern extraction date:** 2026-07-19
