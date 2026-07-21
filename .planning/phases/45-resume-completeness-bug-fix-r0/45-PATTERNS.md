# Phase 45: Resume Completeness Bug Fix [R0] - Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 2 (1 production edit + 1 test file extension)
**Analogs found:** 2 / 2 (both in-file — this is a surgical edit + a test-clone, so the best analogs are neighbors inside the very files under change)
**Anchor drift audit:** ALL line numbers in CONTEXT.md / RESEARCH.md re-verified this session on `feat/ui-2` — see the "Anchor Verification" table at the bottom. No material drift; two soft-drift notes recorded.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/agents/execution_engine/engine.py` (`_first_incomplete_step`, the disjunct at `:6002`) | kernel (resume-tier classifier) | transform (durable rows → resume-offset int) | the `wave_scheduler` branch immediately above it (`engine.py:5988-5998`) + `task_loop.run`'s total-tasks derivation (`task_loop.py:191-224`) | exact (same function, same read surface) |
| `backend/tests/agents/test_restart_resume.py` (new RED + companion cases) | test (unit, offline classifier) | request-response (seed durable rows → assert offset) | `test_resumed_events_seq_continues_past_durable_tail` (`:798-868`) for the seed-durable-then-call idiom + `_Step` stub (`:662-666`) | exact (same harness, same file) |

---

## Pattern Assignments

### `backend/agents/execution_engine/engine.py` — `_first_incomplete_step` (kernel classifier, transform)

**Analog A (the shape to insert alongside): the `wave_scheduler` branch — `engine.py:5988-5998`.** This is the exact precedent for a strategy-conditional branch that returns `i` (incomplete) or `continue`s (complete). The new `task_loop` branch mirrors this structure and sits directly beside it, BEFORE the `:6002` non-wave disjunct.

Copy this control-flow shape (verified `engine.py:5982-6004`):

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

    # ← INSERT the task-granular branch HERE (before :6002), same shape.

    # Non-wave step: complete iff it produced its typed artifact OR a terminal
    # step event is recorded. Neither ⇒ this is the first incomplete step.
    if agent_id in produced_agents or agent_id in completed_step_events:   # :6002 — UNCHANGED for single_shot
        continue
    return i

return len(ordered_agents)
```

**COPY THIS — the generic strategy keying.** `strategy = getattr(step, "strategy", None)` is ALREADY extracted at `:5986`. Key the new branch on `strategy == "task_loop"` (a generic capability name), NEVER on `agent_id == "prototype-build"` / `pipeline_type ==` / any workflow literal (INV-1; the banned-pattern gate is a ratchet). This is the identical idiom the `wave_scheduler` branch already uses — no name literal appears in the classifier today.

**DEVIATE HERE — the completeness predicate for the new branch.** For `single_shot` the membership test at `:6002` is byte-correct and stays verbatim. For `task_loop` it is the BUG (a partial build has the agent in `produced_agents` from task 1). The new branch must compute a count:

- **complete ⟺** `distinct({ref.task_id for ref in store.tree(run_id) if ref.producer_agent == agent_id}) >= expected_total` **OR** `agent_id in completed_step_events` (keep the event OR-condition — a retry/`step_reused` step IS complete; Pitfall 5).
- else `return i` (fail-safe INCOMPLETE — never skip on uncertainty).

**Analog B (how to derive `expected_total` — copy the strategy's own derivation so classifier and strategy agree by construction): `task_loop.run`, `task_loop.py:191-224` (verified).** The classifier must re-parse the SAME source_step artifact with the SAME parser the strategy uses:

```python
# task_loop.py:191-224 — the exact derivation to mirror in the classifier
task_source_decl = getattr(step, "task_source", None)
source_step = (
    getattr(task_source_decl, "source_step", None) or _DEFAULT_SOURCE_STEP  # "prototype-plan", task_loop.py:89
)
plan_output = runner.latest_typed_content(source_step) or ""
parser_name = "heading_tasks"
if task_source_decl is not None and getattr(task_source_decl, "parser", None):
    parser_name = task_source_decl.parser
parser = self._registry.resolve("task_parser", parser_name)
tasks = parser.parse(plan_output)
total_tasks = len(tasks)
if total_tasks == 0:
    total_tasks = 1        # 0 tasks → run once, persists task_id="1" (task_loop.py:215-222)
```

**DEVIATE HERE — the classifier reads the DURABLE store, not the in-memory runner.** `task_loop.run` gets `plan_output` from `runner.latest_typed_content(source_step)` (the hydrated in-memory graph). In `_first_incomplete_step` the in-memory graph is EMPTY on a fresh-process resume — read the source_step content the same way the classifier already reads `produced_agents`: iterate `await store.tree(ectx.run_id)` (verified `engine.py:5972`) and take the `.content` of the row whose `.producer_agent == source_step`. So:
- `expected_total = max(len(parser.parse(plan_content)), 1)` where `plan_content` is the `store.tree()` row content for `producer_agent == source_step`.
- Resolve the parser via the registry the same import-safe way the engine already resolves capabilities — `_CAPABILITY_REGISTRY` / `CapabilityRegistry().resolve("task_parser", parser_name)` (engine.py:466 precedent; the same pattern used for `strategy`/`deliverable`).

**COPY THIS — the fail-safe convention (already the function's contract).** Every read in this function is wrapped `try/except → pass` and degrades to "treat as incomplete" (see `:5949`, `:5962`, `:5976`). Match it: if `source_step` content is missing, parser resolve fails, or `store` is None → `expected_total` is underivable → **INCOMPLETE (return i)**, never skip. The outer `_compute_resume_offset` also wraps the whole call `try/except → return 0` (verified `engine.py:6280-6285`), a second fail-safe layer. Do NOT invert the fail-safe to "skip on uncertainty" (Pitfall 4) — that reintroduces data loss.

**COPY THIS — count DISTINCT task_ids, not rows/versions (Pitfall 7).** The fix-loop re-persists the same `task_id` (see root cause below), so use a `set` of `ref.task_id` values. `store.tree()` rows carry `.task_id` (proven by `_hydrate_artifacts_from_store` reading `row.task_id`, verified `engine.py:5895`).

**Root cause the count must defeat — `persist_task_html`, `kernel_services.py:1313-1339` (verified verbatim):**

```python
async def persist_task_html(self, task_num: int, agent_id: str = "prototype-build", *, filename: str) -> None:
    task_html = self.sandbox.read(filename)
    if not task_html:
        return
    await self._engine._dual_write_artifact(
        self._ectx, producer_agent=agent_id, producer_step=agent_id,
        content=task_html, kind="html_file", location=filename,
        task_id=str(task_num),                              # ← per-task tag; present from task 1
    )
```

Called after every task (task_loop.py per-task + fix-loop sites), so `produced_agents` contains the build agent from task 1 — the `:6002` membership test cannot separate partial from complete. The distinct-`task_id` count can.

**DO NOT TOUCH (CONTEXT + RESEARCH guardrails, Pitfall 8):** the `wave_scheduler` branch (`:5988-5998`), `_hydrate_artifacts_from_store` (`:5865-5907`), `restore_non_terminal_runs`, `resume_run` re-entry, terminal emission, the `single_shot` `:6002` disjunct, the `for i in range(len(...))` (NOT `enumerate(ordered_agents)`) index loop — the single-dispatch-loop grep gate (INV-12) counts on the classifier NOT being an `enumerate(ordered_agents)` loop (comment at `:5979-5981`). No new events (INV-3).

---

### `backend/tests/agents/test_restart_resume.py` — new RED + companion (test, unit)

**Analog: `test_resumed_events_seq_continues_past_durable_tail` (`:798-868`, verified) — the seed-durable-rows-then-invoke idiom.** This is the closest existing case that seeds durable rows against a bound `ScopedStore` and then exercises the resume path over the same in-memory session. Clone its setup skeleton.

**Harness primitives to reuse verbatim:**

`_make_session()` (`:362-371`, verified) — in-memory SQLite + `Base.metadata.create_all`, returns `(session, db)`:
```python
session, db = _make_session()
```

`_seed_workflow_run(...)` (`:374-384`, verified) — inserts the `workflow_runs` row the classifier/`resume_run` read. Note the default `type_="sample_wave"`; the new cases can keep any type (the unit classifier path does not gate on it):
```python
_seed_workflow_run(session, run_id, owner=owner, status="generating")
```

Bound `ScopedStore` seeding pattern (`:813-832`, verified — the block to mirror):
```python
from agents.authz import ScopedStore
session, db_engine = _make_session()
run_id = f"pb-{uuid.uuid4().hex[:8]}"
owner = "pb-user"
workspace_id = "ws-pb"
_seed_workflow_run(session, run_id, owner=owner, status="generating")
pre_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
# ... seed rows on pre_store ...
session.commit()
```

**DEVIATE HERE — seed `artifact_refs` (not `run_events`).** The seq test seeds events via `pre_store.append_event(...)`. The new cases instead seed durable `artifact_refs` via `pre_store.write_ref(ref)` (verified signature `authz.py:134`; it maps a `agents/artifacts/graph.ArtifactRef` dataclass → the `artifact_refs` ORM row, stamping `producer_agent`/`task_id`). Construct graph refs:
- **Plan artifact:** `write_ref(ArtifactRef(run_id=run_id, owner_id=owner, kind="task_list", producer_agent="prototype-plan", producer_step="prototype-plan", content="## Task 1: ...\n## Task 2: ...\n## Task 3: ...", ...))` so `heading_tasks.parse` yields `total=3`. (Confirm the graph `ArtifactRef` required fields — `content_hash`, `version` — by reading `agents/artifacts/graph.py`; `write_ref` fills `version` from the DB count when the dataclass omits it, `authz.py:185`.)
- **Partial build (RED):** ONE ref only — `producer_agent="prototype-build"`, `kind="html_file"`, `task_id="1"` (mirrors `persist_task_html`). No task 2/3 rows = the crash point.
- **Complete build (companion):** THREE refs, `task_id` in `"1"`,`"2"`,`"3"`.

**DEVIATE HERE — extend the `_Step` stub (`:662-666`, verified) to carry `strategy` + a populated `task_source`.** Today it is:
```python
class _Step:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.task_source = None
```
The new cases need `strategy` and a `task_source` with `.parser`/`.source_step`. Prefer the REAL dataclasses over widening the stub: build the compiled step from `agents.workflows.plan.Step(agent_id="prototype-build", strategy="task_loop", task_source=TaskSource(parser="heading_tasks", source_step="prototype-plan"))` (verified fields: `Step.strategy` plan.py:358, `Step.task_source`; `TaskSource.parser` plan.py:181, `TaskSource.source_step` plan.py:183). A `compiled` object exposing `.steps = [ ...single_shot plan step..., that build step, ...single_shot validate step... ]` gives `_steps_by_agent` the strategy keys.

**Invocation (offline, direct classifier call) — mirror the `_compute_resume_offset` temp-context shape (`engine.py:6264-6270`, verified):**
```python
tmp = ExecutionContext(run_id=run_id, owner_id=owner, disk_principal="anon")
tmp.workspace_id = workspace_id
tmp.scoped_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
idx = await engine._first_incomplete_step(tmp, ordered_agents, compiled)
```
`ordered_agents` = specs with `.id` (the classifier reads `getattr(spec, "id", None)` at `:5984` — NOTE: specs use `.id`, compiled steps use `.agent_id`; keep them consistent). Reuse `_load_fixture_specs()` (`:156`) or minimal `.id`-bearing stubs.

**Assertions (the RED→GREEN contract):**
- **RED (partial):** on HEAD `idx > build_index` (offset lands past `prototype-build` → build silently skipped); after fix `idx == build_index`.
- **Companion (complete):** `idx > build_index` both before and after (a finished build stays complete — guards over-correction / infinite re-run).

**LEAVE ALONE:** `test_waiting_for_user_run_is_rearmed_not_driven` (`:877`) stays RED — it is Phase 49's KAN-88 anchor, NOT a regression. Verify-by-delta against the pre-phase baseline (6 pass + 1 known red → after: 8 pass + 1 known red).

---

## Shared Patterns

### Generic strategy keying (INV-1 / SC-001)
**Source:** `engine.py:5986` + the `wave_scheduler` branch `:5988`.
**Apply to:** the engine edit. Read `getattr(step, "strategy", None)` and branch on capability names (`"task_loop"`, `"wave_scheduler"`). Never a workflow/agent-id literal. The `_DEFAULT_SOURCE_STEP="prototype-plan"` fallback is a soft literal owned by the STRATEGY (task_loop.py:89) — the prototype manifest DECLARES `source_step`, so `step.task_source.source_step` is populated and the literal is never hit; if the classifier needs a fallback, read the declared value first and only then fall back (mirror task_loop.py:192-194), aware it's a soft literal the banned-pattern gate tolerates in a generic-read context.

### Fail-safe-to-incomplete
**Source:** `engine.py:5949/5962/5976` (per-read `except → pass`) + `:6280-6285` (`_compute_resume_offset` outer `except → return 0`).
**Apply to:** the engine edit. Any uncertainty (no store, no source content, parser resolve failure, exception) → INCOMPLETE / re-drive. Correct-but-wasteful is explicitly acceptable (CONTEXT); silent-skip is the bug.

### Seed-durable-then-invoke (offline SQLite)
**Source:** `test_restart_resume.py:362-384` (`_make_session`/`_seed_workflow_run`) + `:813-832` (bound `ScopedStore` seeding).
**Apply to:** both new test cases.

---

## Verification-Gate Idioms (recent-phase convention)

| Gate | Command | Expected |
|------|---------|----------|
| Per-task quick | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` (from `backend/`, ~2s) | new RED green + 6 prior pass + 1 known red = **8 passed, 1 failed** |
| Characterization / INV-3 dormancy | `python3.11 -m pytest tests/agents/test_characterization_*.py -q` (`SNAPSHOT_UPDATE` unset) | **10 passed** (goldens never enter resume → fix dormant) |
| Banned-pattern / INV-1 / INV-12 | `python3.11 -m pytest tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py -q` | green |
| Import purity | `/opt/homebrew/bin/lint-imports` | `Contracts: 4 kept, 0 broken` |

Full-for-phase merge gate: run all four together (~40s). Offline only — python3.11, no venv, no Bedrock/Chromium/Postgres (full suite hangs offline). The `test_waiting_for_user_run_is_rearmed_not_driven` red is a KNOWN pre-existing baseline red — verify-by-delta, do not "fix" it.

---

## No Analog Found

None. Both changes have exact in-file analogs (a sibling strategy branch; a sibling seed-and-invoke test). RESEARCH.md's recommended mechanism is directly grounded in existing code; the planner does not need to fall back to abstract research patterns.

---

## Anchor Verification (every CONTEXT/RESEARCH line re-checked on disk this session)

| Anchor (as cited) | Current on disk | Status |
|-------------------|-----------------|--------|
| `_first_incomplete_step` `engine.py:5909-6007`, bug at `:6002` | `def` at 5909; loop 5982-6007; disjunct at **6002** | ✅ exact |
| `strategy` extracted at `:5986` | `strategy = getattr(step, "strategy", None)` at 5986 | ✅ exact |
| `wave_scheduler` branch `:5988-5998` | 5988-5998 | ✅ exact |
| `produced_agents` build via `store.tree()` `:5969-5977` | 5969-5977 | ✅ exact |
| `completed_step_events` build `:5934-5948` | 5935-5948 | ✅ exact (CONTEXT said 5934; set init is 5935) |
| `_compute_resume_offset` `:6239-6285`, calls `_first_incomplete_step` at `:6279` | 6239-6285; temp ctx 6264-6270; call at 6279 | ✅ exact |
| `resume_run` `:6031` | `async def resume_run` at 6031 | ✅ exact |
| `_hydrate_artifacts_from_store` `:5865-5907` | 5865-5907; reads `row.task_id` at 5895 | ✅ exact |
| `_dispatch_step_with_retry` `:5634` (retry gate) | `async def` at 5634 | ✅ exact |
| `persist_task_html` `kernel_services.py:1313-1339` | 1313-1339 verbatim | ✅ exact |
| task_loop total derivation `task_loop.py:191-214` | task_source_decl 191, parse 210, total_tasks 214 | ✅ exact |
| task_loop 0-task fallback `:215-222` | 215-222 | ✅ exact |
| `_DEFAULT_SOURCE_STEP="prototype-plan"` task_loop.py:89 | line 89 | ✅ exact |
| `Step.strategy` plan.py:358 / `Step` class 346 | class 346, `strategy: str = "single_shot"` 358 | ✅ exact |
| `TaskSource` plan.py:162; `.parser`/`.source_step` "162-174" | class 162; `parser` **181**, `source_step` **183** | ⚠ soft drift — fields at 181/183 (CONTEXT/RESEARCH said "162-174"); same class, no impact |
| test `_make_session` / `_seed_workflow_run` | 362-371 / 374-384 | ✅ exact |
| test `_Step` stub `:662-666` | 662-666 (has `agent_id` + `task_source`; **no `strategy`** — must extend) | ✅ exact |
| seed-durable analog `test_resumed_events_seq...` `:813-832` | 798-868; seed block 813-832 | ✅ exact |
| pre-existing red `test_waiting_for_user...` | `def` at 877; asserts at ~898 | ✅ exact |
| `store.write_ref` seam `authz.py:134` | 134 (maps graph `ArtifactRef` → ORM row) | ✅ exact |

**Soft-drift note:** RESEARCH/CONTEXT cite `TaskSource.parser/.source_step` as "plan.py:162-174"; the actual field lines are 181 (`parser`) and 183 (`source_step`) — inside the class that opens at 162. Cosmetic only; access is by attribute name, not line. No other drift found; POR §9 line numbers held.

---

## Metadata

**Analog search scope:** `backend/agents/execution_engine/{engine.py,kernel_services.py}`, `backend/agents/capabilities/strategies/task_loop.py`, `backend/agents/capabilities/task_parsers/heading_tasks.py`, `backend/agents/workflows/plan.py`, `backend/agents/authz.py`, `backend/tests/agents/test_restart_resume.py`.
**Files scanned:** 7 (all read/grepped this session).
**Pattern extraction date:** 2026-07-19
