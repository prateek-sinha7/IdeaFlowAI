# Phase 45: Resume Completeness Bug Fix [R0] — Research

**Researched:** 2026-07-19
**Domain:** Kernel resume-tier completeness classification (`engine.py::_first_incomplete_step`)
**Confidence:** HIGH (every anchor re-opened and re-verified this session; targeted suites run)
**Requirement:** RESUME-05

---

## Summary

The bug is real and reproduced by reading: `_first_incomplete_step` (engine.py:5909-6007) classifies a **non-wave** step complete via the disjunct `if agent_id in produced_agents or agent_id in completed_step_events: continue` (engine.py:6002). For a `task_loop` build step, `persist_task_html` (kernel_services.py:1313-1339) dual-writes an `html_file` `artifact_ref` with `producer_agent=<build agent>`, `task_id=str(task_num)` **after every task**, so `produced_agents` contains the build agent from task 1 onward — a partial build (crash at task N<M) is classified COMPLETE and the resume offset lands PAST the build step → the build is silently skipped → truncated deliverable.

**Recommended mechanism (count/identity-based, strategy-conditional per POR §5.4/I8):** Add a task-granular branch in `_first_incomplete_step` keyed on the compiled `step.strategy` (generic, already read at engine.py:5986). For `strategy == "task_loop"`, replace the produced-agent membership test with a **count check**: `complete ⟺ distinct(task_id for artifact_refs where producer_agent == agent_id) >= expected_total`, where `expected_total` is derived by re-parsing the source step's task-plan artifact with the declared parser (`step.task_source.parser` → `heading_tasks`/`json_tasks`, source content from `producer_agent == step.task_source.source_step`), exactly as `task_loop.run` does (task_loop.py:191-214). Keep a terminal-event fallback (`step_completed`/`step_reused`) as an additional "complete" condition. `single_shot` keeps the existing disjunct byte-unchanged; `wave_scheduler` keeps its existing wave_runs branch (engine.py:5988-5998) untouched.

**Why not just require `step_completed`:** VERIFIED — `step_completed`/`step_reused` are emitted ONLY when the step declares `retry` with `max_attempts>0` (engine.py:5649-5655 short-circuits to a bare `strategy.run` pass-through otherwise). The prototype build step declares **no retry** (workflow.yaml), so a genuinely-complete prototype build emits NO terminal event. Requiring `step_completed` for task-granular steps would classify every complete no-retry build INCOMPLETE → perpetual re-run across restarts = the exact over-correction the CONTEXT warns against. The count check is the only signal reliably present on the normal (no-retry) path.

**No new events. No migration. INV-3-dormant** (scripted golden runs never enter the resume path — see baseline: 10/10 goldens green).

---

## Verified Current-State Anchors (file:line, quoted)

All line numbers re-verified 2026-07-19 on `feat/ui-2`. POR §9 numbers held (no drift).

### The bug site — `_first_incomplete_step` (engine.py:5909-6007)

Construction of the two membership sets (engine.py:5934-5977):

```python
completed_step_events: set[str] = set()          # from run_events
...
    rows = await store.read_events(ectx.run_id, 0)
    for row in rows:
        ...
        if getattr(row, "type", None) in ("step_completed", "step_reused"):
            sid = payload.get("step")
            if sid:
                completed_step_events.add(sid)
...
produced_agents: set[str] = set()                # from artifact_refs
    for ref in await store.tree(ectx.run_id):
        pa = getattr(ref, "producer_agent", None)
        if pa:
            produced_agents.add(pa)
```

The classification loop (engine.py:5982-6007). Note `strategy` is **already extracted** at :5986 and the wave branch already special-cases task-granular waves:

```python
for i in range(len(ordered_agents)):
    spec = ordered_agents[i]
    agent_id = getattr(spec, "id", None)
    step = _steps_by_agent.get(agent_id)
    strategy = getattr(step, "strategy", None) if step else None

    if strategy == "wave_scheduler":
        if agent_id in running_wave_steps:
            return i
        if agent_id not in terminal_wave_indices_by_step:
            return i
        continue

    # Non-wave step: complete iff it produced its typed artifact OR a terminal
    # step event is recorded. Neither ⇒ this is the first incomplete step.
    if agent_id in produced_agents or agent_id in completed_step_events:   # ← :6002 BUG
        continue
    return i

return len(ordered_agents)
```

**The `task_loop` step falls into the non-wave branch and is mis-classified.** The fix inserts a task-granular branch alongside the `wave_scheduler` branch (or refines the non-wave disjunct) BEFORE :6002.

### Return contract + consumers

- `_first_incomplete_step` returns `int` = the resume offset (index of first incomplete step; `len(ordered_agents)` if all complete). Doc: engine.py:5928-5931.
- Caller chain: `resume_run` (engine.py:6031) → `_compute_resume_offset` (engine.py:6239-6285) → `_first_incomplete_step` (called at engine.py:6279) → offset passed as `_resume_from=offset` into `_execute_impl` (engine.py:6198).
- The single consumer of the offset is the skip in the dispatch loop (engine.py:2061-2063):
  ```python
  if i < _resume_from:
      continue
  ```
  So a too-large offset = the build step's `i` is `< _resume_from` = build skipped. **This is the data-loss path.**

### The compiled plan IS available at classification time (Question 2 — answered)

`_compute_resume_offset` already calls `compile_for_run(pipeline_type)` (engine.py:6274) and passes `compiled` into `_first_incomplete_step` (engine.py:6279). `_steps_by_agent = {s.agent_id: s for s in (compiled.steps or [])}` (engine.py:5965) already maps agent_id → compiled `Step`, and `step.strategy` / `step.task_source` are already reachable. **No new plumbing needed** — the fix is INV-1/INV-2-safe with zero signature changes. `Step.strategy: str = "single_shot"` and `Step.task_source: TaskSource | None` (plan.py:358/361); `TaskSource.parser` / `.source_step` (plan.py:162-174).

### The per-task dual-write (root cause) — kernel_services.py:1313-1339

```python
async def persist_task_html(self, task_num, agent_id="prototype-build", *, filename):
    task_html = self.sandbox.read(filename)
    if not task_html:
        return
    await self._engine._dual_write_artifact(
        self._ectx, producer_agent=agent_id, producer_step=agent_id,
        content=task_html, kind="html_file", location=filename,
        task_id=str(task_num),
    )
```
Called after every task AND after a fix-loop edit (task_loop.py:293-296 and :358-366). Each call writes a NEW `artifact_ref` version tagged `task_id=str(task_num)`. `store.tree()` rows carry `.task_id` and `.content` (proven by `_hydrate_artifacts_from_store` reading `row.task_id`/`row.content`, engine.py:5895-5896). `tree()` aliases `lineage()` (authz.py:277-279).

### The total-tasks derivation (task_loop.run) — task_loop.py:191-214

```python
task_source_decl = getattr(step, "task_source", None)
source_step = getattr(task_source_decl, "source_step", None) or _DEFAULT_SOURCE_STEP  # "prototype-plan"
plan_output = runner.latest_typed_content(source_step) or ""
...
parser_name = "heading_tasks"
if task_source_decl is not None and getattr(task_source_decl, "parser", None):
    parser_name = task_source_decl.parser
parser = self._registry.resolve("task_parser", parser_name)
tasks = parser.parse(plan_output)
total_tasks = len(tasks)
if total_tasks == 0:
    ... run once with an empty task block  # persists task_id="1"
```
`heading_tasks.parse` is pure `text -> list[Task]` (heading_tasks.py:105-122), registered `("task_parser","heading_tasks")`. The engine already resolves capabilities via `_CAPABILITY_REGISTRY` (engine.py:466) / `CapabilityRegistry().resolve(...)` — resolving `"task_parser"` is the same import-safe pattern used for `strategy`/`deliverable`/`post_step`.

### `step_completed` emission is retry-gated — engine.py:5634-5717 (Question 3a)

```python
retry = getattr(step, "retry", None)
if not (retry and getattr(retry, "max_attempts", 0) > 0):
    # Dormant: byte/event-identical legacy dispatch.
    async for event in strategy.run(step, ectx):
        yield event
    return
...
# only in the retry-enabled branch:
yield {"type": "step_completed", "data": {"step": step_id, "input_hash": ..., "output_ref_id": ...}}
```
**Prototype build declares no `retry`** (agents/workflows/prototype/workflow.yaml: build step is `strategy: task_loop` + `task_source`, no `retry:` key). ⇒ no `step_completed` on the golden path. There is also **no other always-emitted per-step terminal event** in `_execute_impl` (the post-strategy code at engine.py:2208-2259 emits only optional gate/hook events, none persisted as a step terminal marker).

### prototype manifest (agents/workflows/prototype/workflow.yaml)

Build step (verified): `- agent: prototype-build` / `strategy: task_loop` / `task_source: {parser: heading_tasks, source_step: prototype-plan}`. Preceding steps `single_shot`; trailing `prototype-validate` `single_shot`. No `retry` anywhere.

---

## Completeness-Signal Analysis

Acceptance bar (LOCKED): partial build → INCOMPLETE; genuinely completed build → COMPLETE (no infinite re-run); `single_shot` byte-unchanged; `step_reused` untouched; no new events preferred; dormant on goldens.

### (a) `step_completed` / `step_reused` events — REJECTED as the primary signal
- **Where emitted:** only in `_dispatch_step_with_retry` retry-enabled branch (engine.py:5666, :5710). Durable via the normal run_events sink (persisted like any yielded event).
- **In the 5 goldens?** No — goldens don't touch resume, and prototype has no retry so no `step_completed` fires there either. Keying on it does NOT perturb goldens (dormant).
- **Fatal flaw for task_loop:** absent on the normal no-retry build path ⇒ a COMPLETE prototype build has no terminal event ⇒ requiring it = perpetual re-run. **Keep it only as an additional OR-condition** (covers retry-configured or reused steps), never as the sole task-granular signal.

### (b) Per-task `artifact_refs` count vs parsed total — RECOMMENDED
- **Durable:** `artifact_refs` is the immutable system of record (artifact_ref.py:24,40; survives restart + 48h TTL). `task_id`-tagged rows present from task 1 (kernel_services.py:1338).
- **Shape:** `distinct({str(task_num)}) for rows where producer_agent == agent_id`. Total from `heading_tasks`/`json_tasks` parse of the `source_step` artifact content (already in `store.tree()` rows).
- **Distinguishes partial vs complete:** partial ⇒ `distinct < total`; complete ⇒ `distinct >= total`. This is the ONLY signal that cleanly separates the two on the no-retry path.
- **Brittleness:** counting is robust (distinct task_ids). The total re-parse reuses the exact same parser + source_step the strategy uses, so classifier and strategy agree by construction. Residual brittleness: if the `source_step` plan artifact is missing/underivable, total is unknown → **fail-safe to INCOMPLETE (re-run)**, never skip (correct-but-wasteful is explicitly acceptable). INV-1-safe: keyed on `step.strategy`/`step.task_source` (generic capability names), no workflow-name literal.

### (c) `wave_runs` rows — ALREADY HANDLED, leave untouched
- `wave_scheduler` steps already have a dedicated branch (engine.py:5988-5998) reading terminal/running `wave_runs` (authz.py:1238 `read_wave_runs`). Correct today and covered by 4 green tests (midwave ×2, cross-step, stale-row). **Phase 45 must not alter it.** `fanout_batch` is a distinct strategy (strategies/fanout_batch.py exists) but is not exercised by the prototype path; treat it as task-granular too if it emits per-worker refs, else leave to the non-wave branch (out of R0's live-data-loss scope).

### (d) Final `kind="deliverable"` ref (engine.py:2415-2453) — usable only as a LAST-step witness, not adopted
- Persisted only on successful whole-run completion. It witnesses the LAST step, not per-step completeness, and doesn't help the build (a non-terminal step). Not needed given (b). Do not introduce a dependency on it.

### Recommendation

For `strategy == "task_loop"` (and any future per-task strategy), a step is **complete** iff:

1. `distinct(task_id for artifact_refs where producer_agent == agent_id) >= expected_total`, where `expected_total = max(len(parser.parse(plan_content)), 1)` and `plan_content` is the `store.tree()` content for `producer_agent == source_step` (declared `step.task_source.source_step`, fallback `"prototype-plan"`; parser from `step.task_source.parser`, fallback `"heading_tasks"`); **OR**
2. a durable `step_completed`/`step_reused` event exists for the step (covers retry/reused steps).

Otherwise **incomplete** (fail-safe). `single_shot` keeps the existing `produced_agents ∪ completed_step_events` disjunct verbatim.

*(`expected_total = max(..., 1)` mirrors the strategy's "0 tasks → run once, persists task_id='1'" fallback at task_loop.py:215-222, so a genuinely-complete 0-task build still classifies complete.)*

---

## Edge Cases

1. **Completed build followed by a later incomplete step (e.g. `prototype-validate` crashed).** The classifier loop `continue`s past a complete build (count check returns complete) and returns the LATER step's index. Correct — requires the count check to reliably return complete for a finished build (it does: all N task_ids present). Verified this is the loop's existing `continue`/`return i` shape (engine.py:5982-6004).

2. **Run interrupted BEFORE any task persisted.** `produced_agents` lacks the build agent, `distinct task_ids == 0 < total` → incomplete → return build index. If the upstream plan step never completed either, the classifier returns the earlier (plan) index first and never reaches build. Both correct.

3. **Legacy/old run where the chosen signal is absent (no plan artifact / underivable total).** Fail-safe direction MUST be re-run, never skip. Implementation: if total cannot be derived (no source_step content, parser resolve fails), treat as INCOMPLETE. Worst case = a completed build with the plan artifact gone re-runs on each restart (rare; acceptable per "correct-but-wasteful"). Document this as the single residual over-correction risk. Note: `_compute_resume_offset` already wraps everything in a `try/except → return 0` (engine.py:6280-6285), so a classifier exception degrades to "re-drive from 0" (also fail-safe, never skip).

4. **`_hydrate_artifacts_from_store` interplay.** `_hydrate_artifacts_from_store` (engine.py:5865-5907) adopts ALL durable refs into the in-memory graph regardless of the offset — it runs in `_execute_impl` at `_resume_from > 0` (engine.py:1340-1349). A step now classified incomplete still gets its earlier per-task refs hydrated into `ectx.artifacts`, which is harmless (the re-entered build re-derives content from disk/typed graph via `latest_typed_content`). **Do NOT touch `_hydrate_artifacts_from_store`** (CONTEXT guardrail) — it re-seeds the graph only; it does not gate the offset. The count check reads the durable store directly (not the hydrated graph), so hydration order is irrelevant to classification.

5. **Fix-loop re-persist.** A fix-loop edit re-persists the SAME `task_id` (task_loop.py:363-366), so `distinct` is unaffected (still one id per task). Counting distinct ids (not rows/versions) is essential — do not count row versions.

---

## At-Risk Tests & Current Baseline

Run 2026-07-19, `feat/ui-2`, `python3.11 -m pytest`, backend/ cwd, offline (no venv, no network, no Bedrock).

### `backend/tests/agents/test_restart_resume.py` — **6 passed, 1 failed** (the 1 fail is the sanctioned pre-existing red)

| Test | Status | Pins |
|------|--------|------|
| `test_midwave_resume_does_not_reinvoke_completed_workers` | PASS | wave resume skip (leave untouched) |
| `test_midwave_resume_reruns_whole_inflight_wave_no_parallel_dropout` | PASS | CR-03 mid-wave |
| `test_cross_step_does_not_skip_second_steps_waves` | PASS | CR-04 per-step wave scoping |
| `test_stale_running_wave_row_is_flipped_terminal_on_resume` | PASS | WR-01 wave row flip |
| `test_resumed_events_seq_continues_past_durable_tail` | PASS | CR-01 seq continuity |
| `test_waiting_for_user_run_is_rearmed_not_driven` | **FAIL (pre-existing)** | KAN-88 / Phase 49 anchor — **LEAVE ALONE** |
| `test_stateless_run_keeps_wr05_failed_path` | PASS | branch (c) |

Verbatim failure (the anchor red — must stay red after Phase 45; verify-by-delta):
```
tests/agents/test_restart_resume.py:898: in test_waiting_for_user_run_is_rearmed_not_driven
    assert row.status == "waiting_for_user", "waiting_for_user status must be unchanged"
E   AssertionError: assert 'failed' == 'waiting_for_user'
==================== 1 failed, 6 passed, 1 warning in 1.42s ====================
```

**None of the 7 tests directly unit-test `_first_incomplete_step` on a `task_loop` step** — the resume suite exercises only `wave_scheduler` and stateless/gate branches. This is why the bug is uncaught: there is NO existing test covering a sequential `task_loop` partial-build resume. The RED case fills exactly that gap.

### `backend/tests/agents/test_characterization_*.py` (5 files) — **10 passed** (INV-3 gate green)

```
tests/agents/test_characterization_app_builder.py ..
tests/agents/test_characterization_od_ppt.py ..
tests/agents/test_characterization_od_prototype.py ..
tests/agents/test_characterization_prototype_revision.py ..
tests/agents/test_characterization_prototype.py ..
==================== 10 passed, 1 warning in 35.86s ====================
```
`SNAPSHOT_UPDATE` unset. Goldens never enter the resume path, so the fix is dormant here — this must stay 10/10 after the change (the INV-3 proof).

---

## RED-Case Construction

Two viable levels; **recommend both** (unit RED as the primary RED→GREEN, plus a companion no-regression case).

### Primary RED — direct classifier unit test (simplest, deterministic)

Synthesize a partial-build durable state and assert the offset. Reuses the file's existing SQLite `ScopedStore` idioms (`_make_session`, `ScopedStore(..., session=...)`, `_seed_workflow_run`) — the same harness `test_resumed_events_seq_continues_past_durable_tail` uses (test_restart_resume.py:813-832 is the closest analog for seeding durable rows via a bound `ScopedStore`).

Construction:
1. `session, db = _make_session()`; `_seed_workflow_run(session, run_id, owner=..., status="generating")`.
2. Seed the plan artifact: one `artifact_ref` via the store's dual-write/adopt path (or directly `ArtifactRef` ORM insert) with `producer_agent="prototype-plan"`, `kind="task_list"` (or the plan kind), `content` = a `## Task 1:` … `## Task 3:` markdown (3 tasks) — so `heading_tasks.parse` yields `total=3`.
3. Seed **only task 1** of the build: one `artifact_ref` with `producer_agent="prototype-build"`, `kind="html_file"`, `task_id="1"` (mirrors `persist_task_html`). No task 2/3 rows (the crash point).
4. Build a compiled plan whose `prototype-build` step is `strategy="task_loop"`, `task_source=TaskSource(parser="heading_tasks", source_step="prototype-plan")` (or compile the real prototype manifest via the harness's `_patched_compile`).
5. Build `ordered_agents` (the 5 prototype specs, or the `_load_fixture_specs` idiom) and a `tmp` `ExecutionContext` with `scoped_store` bound to the session (the `_compute_resume_offset` shape at engine.py:6264-6270).
6. **Assert (current HEAD, RED):** `await engine._first_incomplete_step(tmp, ordered_agents, compiled)` returns an index PAST `prototype-build` (i.e. `> build_index`, e.g. the validate index or `len`), because `produced_agents` contains `"prototype-build"` → :6002 `continue`s. **Assert (post-fix, GREEN):** returns exactly `build_index` (the build step is re-entered).

A `_Step`-style stub already exists in the file (test_restart_resume.py:662-666) with `agent_id` + `task_source`; extend it (or use the real compiled Step) so `strategy` and `task_source.parser/source_step` are populated.

### Companion no-regression (guards over-correction)

Same setup but seed **all 3** build task_ids (`"1"`,`"2"`,`"3"`). Assert the classifier returns an index PAST `prototype-build` (complete → skipped) — proving a fully-completed build is NOT re-entered (no infinite re-run). This is the acceptance-bar's second half.

### Full-run RED (optional, higher fidelity)

If a full drive is wanted, extend the `_ResumeHarness` with a `task_loop` fixture (analogous to `sample_wave`) whose build crashes after task 1 (a scripted model that raises on task 2). Then `resume_run` over the shared DB and assert the build agent's model IS re-invoked on instance B (partial build re-entered) and the final deliverable contains all tasks. The wave harness at test_restart_resume.py:188-359 is the template (patches compile/registry/factory/ScopedStore/SessionLocal onto one in-memory session). Heavier; the unit RED is sufficient for RED→GREEN and cheaper to run in the Nyquist loop.

---

## Pitfalls

1. **INV-12 (single dispatch loop).** The fix lives entirely inside `_first_incomplete_step` (a completeness SCAN, explicitly `for i in range(len(...))`, NOT `enumerate(ordered_agents)` — see the comment at engine.py:5979-5981 preserving the single-dispatch-loop grep gate). Do NOT add a second dispatch loop or a parallel resume path. The banned-pattern/`enumerate(ordered_agents)` pin must stay at 1.

2. **INV-1 / banned-pattern gate.** Key ONLY on `step.strategy` / `step.task_source.parser` / `step.task_source.source_step` (generic capability names). NEVER `if pipeline_type ==`, `spec.id ==`, `"prototype-build"`, `agent_id == "..."`, or any workflow/agent-name literal. `test_banned_patterns.py` + `test_migration_ledger.py` are ratchets. The `_DEFAULT_SOURCE_STEP="prototype-plan"` fallback lives in the STRATEGY (task_loop.py:89) — if the classifier needs a fallback, read the compiled declaration first and only fall back generically; do not hard-code a prototype id in the kernel classifier (mirror the strategy's fallback pattern but be aware it's a soft literal — the prototype manifest DECLARES `source_step`, so `step.task_source.source_step` is populated and the literal fallback is never hit for prototype).

3. **INV-2 (no per-run engine state).** All new state is local to `_first_incomplete_step` (the temp `ExecutionContext`, local sets). Nothing on `self._*`. Reads come from durable rows via `ectx.scoped_store`. Already the function's contract.

4. **Over-correction / perpetual re-entry.** The single genuine risk. A completed build must classify complete or every restart re-runs it. The count check + the `expected_total = max(len(tasks), 1)` guard + the `step_completed` OR-fallback cover the normal + retry + 0-task cases. The residual (plan artifact gone on an old completed run) fail-safes to re-run — acceptable, documented (Edge Case 3). Do NOT invert the fail-safe to "skip on uncertainty" — that reintroduces data loss.

5. **`step_reused` semantics unchanged.** The `step_reused` path (engine.py:5662-5673) and its `completed_step_events` membership must keep working for completed steps. Keep the `completed_step_events` OR-condition intact for task-granular steps (a task_loop step that was reused via input_hash IS complete). Do not remove `completed_step_events` from the task-granular condition — add the count check as an additional path, not a replacement of the event path.

6. **Golden dormancy proof.** The 5 characterization suites (10 tests) are the INV-3 proof: they must stay 10/10 with `SNAPSHOT_UPDATE` unset AFTER the change. Because goldens never call `resume_run`/`_first_incomplete_step`, the fix is structurally dormant on them — re-running the goldens green is the dormancy proof (no new events, no re-baseline).

7. **Count distinct task_ids, not rows/versions.** Fix-loop re-persists the same `task_id` (task_loop.py:363-366) and each task may write multiple versions. Use a `set` of `task_id` values, or the guard will over- or under-count.

8. **Do not touch adjacent machinery** (CONTEXT guardrail): `restore_non_terminal_runs` branches, `resume_run` re-entry, `_hydrate_artifacts_from_store`, terminal emission. The change is confined to the classification predicate.

---

## Validation Architecture

Framework: **pytest** (+ `pytest-asyncio`), config `backend/pytest.ini` (implied by existing markers). Run with `python3.11 -m pytest` from `backend/`, offline, no venv. Full suite hangs offline — use targeted suites only.

### Phase Requirements → Test Map

| Req | Behavior | Test type | Automated command | Exists? |
|-----|----------|-----------|-------------------|---------|
| RESUME-05 | Partial `task_loop` build resumes by re-entering the build step (not skipped) | unit | `python3.11 -m pytest tests/agents/test_restart_resume.py -k "partial_build or task_loop" -x` | ❌ Wave 0 (new RED→GREEN) |
| RESUME-05 | Fully-completed build still classifies complete (no infinite re-run) | unit | `python3.11 -m pytest tests/agents/test_restart_resume.py -k "completed_build" -x` | ❌ Wave 0 (companion) |
| INV-3 | 5 goldens byte/event-identical (fix dormant) | characterization | `python3.11 -m pytest tests/agents/test_characterization_*.py -q` | ✅ (10 passed) |
| INV-1 | No workflow-name/agent-id literal added to kernel | banned-pattern | `python3.11 -m pytest tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q` | ✅ |
| INV-12 | Single dispatch loop; no forked resume path | banned-pattern | included above | ✅ |
| Regression | Existing wave/stateless resume unchanged; pre-existing red stays red | unit | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` | ✅ (6 pass, 1 known red) |
| Import purity | kernel imports only ports (4/0) | import-linter | `/opt/homebrew/bin/lint-imports` | ✅ |

### Sampling / gates

- **Per task commit (quick):** `python3.11 -m pytest tests/agents/test_restart_resume.py -q` (~2s) — must show the new RED green + the 6 prior pass + the 1 known pre-existing red (unchanged).
- **Per wave merge (full-for-phase):** `python3.11 -m pytest tests/agents/test_restart_resume.py tests/agents/test_characterization_*.py tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q` (~40s) + `/opt/homebrew/bin/lint-imports`.
- **Phase gate (before `/gsd-verify-work`):** the full-for-phase set green (10 goldens + banned-pattern + lint-imports 4/0), the new RED→GREEN passing, and `test_waiting_for_user_run_is_rearmed_not_driven` STILL failing (verify-by-delta against the pre-phase baseline — its red is Phase 49's, not a regression).

### Expected outputs

- New RED test: FAILS on current HEAD (offset lands past `prototype-build`), PASSES after the fix (offset == build index).
- Companion: PASSES both before and after (guards the fix doesn't over-correct) — but on HEAD it "passes" only coincidentally (complete build already classified complete); its real value is post-fix regression coverage.
- Goldens: `10 passed`. Banned-pattern/ledger: green. `lint-imports`: `Contracts: 4 kept, 0 broken`.
- `test_restart_resume.py` after fix: `2 failed`? NO — expected `7 passed if new tests added minus the 1 known red`. Precisely: prior 6 pass + 1 pre-existing red + 2 new (both green post-fix) = **8 passed, 1 failed** (the failed one is only the KAN-88 anchor).

---

## Sources

### Primary (HIGH — code re-opened this session on `feat/ui-2`)
- `backend/agents/execution_engine/engine.py:5865-6285` — `_first_incomplete_step`, `resume_run`, `_compute_resume_offset`, `_dispatch_step_with_retry`, `_hydrate_artifacts_from_store`.
- `backend/agents/execution_engine/engine.py:2061-2063` — the `_resume_from` skip (offset consumer).
- `backend/agents/execution_engine/kernel_services.py:1313-1339` — `persist_task_html` (root cause).
- `backend/agents/capabilities/strategies/task_loop.py:163-368` — total-tasks derivation + per-task persist call sites.
- `backend/agents/capabilities/task_parsers/heading_tasks.py` — parser (pure, registered).
- `backend/agents/workflows/plan.py:162-379` — `Step` / `TaskSource` dataclasses.
- `backend/agents/workflows/prototype/workflow.yaml` — build step strategy/task_source, no retry.
- `backend/agents/authz.py:277-321,1238` — `ScopedStore.tree/read_events/read_wave_runs`.
- `backend/tests/agents/test_restart_resume.py` — harness idioms + baseline (run this session).

### Live test runs (this session)
- `pytest tests/agents/test_restart_resume.py` → 6 passed, 1 failed (KAN-88 anchor).
- `pytest tests/agents/test_characterization_*.py` → 10 passed.

### POR / register (HIGH — read fully)
- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` §2/§4-B/§5.4/§6-R0/§7/§9.
- `.planning/phases/45-resume-completeness-bug-fix-r0/45-CONTEXT.md` (locked decisions).
- `.planning/REQUIREMENTS.md` RESUME-05.

## Metadata

**Confidence breakdown:**
- Bug mechanics / anchors: HIGH — every line quoted from re-opened files; POR §9 line numbers held.
- Recommended mechanism: HIGH — the only signal reliably present on the no-retry golden path; step_completed rejection proven by reading the retry gate.
- Test baseline: HIGH — actually run this session.
- Residual over-correction risk (plan-artifact-gone legacy run): MEDIUM — fail-safe direction (re-run) is correct but wasteful; documented.

**Research date:** 2026-07-19
**Valid until:** ~2026-08-18 (stable brownfield engine; re-verify line numbers if engine.py churns).
