---
phase: 05-typed-artifacts-persistence-ownership-1b
reviewed: 2026-06-08T00:00:00Z
depth: standard
files_reviewed: 43
files_reviewed_list:
  - backend/agents/artifact_store/store.py
  - backend/agents/artifacts/__init__.py
  - backend/agents/artifacts/graph.py
  - backend/agents/authz.py
  - backend/agents/execution_engine/clarify_engine.py
  - backend/agents/execution_engine/context.py
  - backend/agents/execution_engine/engine.py
  - backend/alembic/versions/0014_typed_artifacts_persistence.py
  - backend/alembic/versions/0015_drop_thin_artifact_store.py
  - backend/app/api/runs.py
  - backend/app/api/websocket.py
  - backend/app/models/__init__.py
  - backend/app/models/artifact_ref.py
  - backend/app/models/run_capabilities.py
  - backend/app/models/run_event.py
  - backend/app/models/workflow_definition.py
  - backend/app/models/workflow.py
  - backend/app/models/workspace.py
  - backend/tests/agents/_scripted_model.py
  - backend/tests/agents/characterization/_normalize.py
  - backend/tests/agents/live_harness.py
  - backend/tests/agents/test_artifact_graph.py
  - backend/tests/agents/test_execution_context.py
  - backend/tests/agents/test_migration_ledger.py
  - backend/tests/agents/test_parent_run_ownership.py
  - backend/tests/agents/test_phase3_compaction.py
  - backend/tests/agents/test_phase3_cutover_verify.py
  - backend/tests/agents/test_phase3_token_delta_live.py
  - backend/tests/agents/test_phase4_build_loop.py
  - backend/tests/agents/test_phase5_revision_validation.py
  - backend/tests/conftest.py
  - backend/tests/integration/test_performance.py
  - backend/tests/unit/test_agent_input_event.py
  - backend/tests/unit/test_artifact_store.py
  - backend/tests/unit/test_execution_engine.py
  - backend/tests/unit/test_migration_0014.py
  - backend/tests/unit/test_resumability.py
  - backend/tests/unit/test_revision_intelligence.py
  - backend/tests/unit/test_run_capabilities.py
  - backend/tests/unit/test_run_events.py
  - backend/tests/unit/test_runs_api_artifacts.py
  - backend/tests/unit/test_runs_api_events.py
  - specs/003-workflow-engine-decoupling/migration-ledger.md
findings:
  critical: 2
  warning: 7
  info: 5
  total: 14
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-06-08
**Depth:** standard
**Files Reviewed:** 43 (source + tests)
**Status:** issues_found

## Summary

Phase 5 lands the typed-artifact substrate (`ArtifactGraph`/`ArtifactRef`), additive
migration 0014 + the parity-gated drop 0015, the single default-deny `ScopedStore`
ownership seam, durable `run_events`, and `run_capabilities`. The kernel-purity
constraint holds (`agents/artifacts/graph.py` is stdlib-only; `ExecutionContext` only
reaches into `agents.artifacts.graph`); the `ScopedStore` correctly keeps `app.api` out
of the import graph and uses lazy `app.models` imports inside methods. The IDOR→404
precedent is preserved at the API and the cross-owner `assert_owns` lookup is sound.

The adversarial pass surfaced two correctness defects that undermine the very
ownership/versioning guarantees the phase advertises:

1. The clarifications persistence path writes a fresh in-memory `ArtifactGraph` per
   round, so every round's `clarifications` ref lands at `version=1`. The reconnect read
   orders by `version ASC` and takes `[-1]`, so with multiple rounds the row returned is
   non-deterministic (DB tie-break) — the user can be re-served an earlier round's
   questionnaire on reconnect.
2. The same path stamps `ArtifactRef.owner_id` from `ClarifyEngine._owner_id`, which is
   typed `str | None` and defaults to `None`; the dataclass contract and AUTHZ-03
   mandate a real, never-`None` owner. On the live engine path `owner_id` is non-None,
   but the helper write does not enforce it and a `None` owner row defeats the
   default-deny filter (an owner-`None` row matches no scoped read but also bypasses the
   "real principal" invariant).

Additional warnings concern best-effort swallowing that hides genuine persistence
failures, an ordering assumption in `list_refs`/`lineage`, and shared-node mutation in
the lineage-tree builder.

## Structural Findings (fallow)

No `<structural_findings>` block was provided with this review; none incorporated.

## Critical Issues

### CR-01: Multi-round clarifications all persist at `version=1`, making the reconnect read non-deterministic

**File:** `backend/agents/execution_engine/clarify_engine.py:420-436` (and the read at `backend/app/api/websocket.py:550-555`)

**Issue:** `_persist_qa` constructs a brand-new `ArtifactGraph()` on every call:

```python
graph = ArtifactGraph()
ref = graph.write_ref(run_id=pipeline_run_id, ..., kind="clarifications", ...)
store = ScopedStore(owner_id=self._owner_id, workspace_id=self._workspace_id)
await store.write_ref(ref)
```

`ArtifactGraph.write_ref` computes `version = 1 + count of refs of same (run_id, kind)
in THIS graph`. Because a fresh graph is created each round, the in-memory count is
always 0, so `ref.version` is always `1`. `ScopedStore.write_ref` then honors the
already-set `ref.version` (`version = getattr(ref, "version", None) or (existing_count
+ 1)` — `1` is truthy, so the DB `existing_count` branch never runs). Result: round 1,
round 2, and round 3 all write `clarifications` rows with `version=1` for the same run.

The reconnect restoration reads them back with `list_refs(run_id, kind="clarifications")`
which does `order_by(ArtifactRef.version.asc())` and takes `_clar_refs[-1]`. With all
versions equal to `1`, the tie-break is DB-/insertion-order dependent and NOT guaranteed
to be the most recent round — so a reconnecting user can be re-served an earlier round's
unanswered questions, or a stale Q&A set. This regresses the "served entirely from the
typed layer" guarantee the migration claims (05-06).

**Fix:** Persist clarifications through the same per-run graph the engine already owns
(thread `ectx.artifacts` into `ClarifyEngine`), OR let the DB assign the version by NOT
pre-setting it on the dataclass and letting `ScopedStore.write_ref` compute
`existing_count + 1`. Minimal fix in the store helper — make the DB the source of truth
for cross-call versioning when the caller cannot share a graph:

```python
# clarify_engine: do not rely on the throwaway graph's version
ref = graph.write_ref(...)          # version will be 1 (ignored)
await store.write_ref(ref, force_db_version=True)
```
and in `ScopedStore.write_ref`, when `force_db_version` is set use `existing_count + 1`
instead of `ref.version`. Alternatively, order the reconnect read by
`created_at.desc()` and take `[0]` so ties resolve to the newest row deterministically.

### CR-02: `ArtifactRef.owner_id` can be persisted as `None`, violating the never-None AUTHZ-03 invariant

**File:** `backend/agents/execution_engine/clarify_engine.py:67-73, 103-104, 421-436`

**Issue:** `ClarifyEngine._owner_id` is typed `str | None` and initialized to `None`;
`run()` assigns it from the `owner_id: str | None = None` parameter. `_persist_qa` then
passes it straight into both `graph.write_ref(owner_id=self._owner_id, ...)` and
`ScopedStore(owner_id=self._owner_id, ...)`. `ArtifactRef.owner_id` is documented as
"owner principal … never None" (`graph.py:66`) and AUTHZ-03/D-09 require a real
principal so the default-deny filter always has a real owner. Neither `write_ref`
(graph) nor `ScopedStore.write_ref` validates non-None, so a `None` owner row is
silently created. The DB column is `nullable=False` (`artifact_ref.py:34`), so on a real
DB this raises an IntegrityError that is then swallowed by the bare
`except Exception` (line 437) — meaning clarifications silently fail to persist whenever
`owner_id` is None, and the reconnect read returns nothing.

On the live engine path `ectx.owner_id` is always a real principal (`engine.py:688`), so
this is latent there; but `ClarifyEngine.run()`'s public signature invites a `None`
owner (it defaults to `None`), and any direct caller or future wiring that omits
`owner_id` gets a silent persistence failure rather than a loud error. This is a
default-deny correctness hole: the ownership boundary depends on a real owner that the
write path does not enforce.

**Fix:** Make `owner_id` required (drop the `None` default) or assert it early:

```python
async def run(self, ..., owner_id: str, workspace_id: str | None = None, ...):
    if not owner_id:
        raise ValueError("ClarifyEngine.run requires a real owner_id (AUTHZ-03)")
```

And/or enforce in the single seam — `ScopedStore.write_ref` should reject a falsy
resolved owner:

```python
resolved_owner = getattr(ref, "owner_id", None) or self._owner_id
if not resolved_owner:
    raise ValueError("artifact_refs.owner_id must be a real principal (AUTHZ-03)")
```

## Warnings

### WR-01: `ArtifactGraph.write_ref` and `ScopedStore.write_ref` compute `version` independently and can diverge

**File:** `backend/agents/artifacts/graph.py:122-124` and `backend/agents/authz.py:149-157`

**Issue:** The graph computes `version` from its in-memory per-(run, kind) count; the
store recomputes it from a DB `COUNT(*)` but then prefers the dataclass value
(`getattr(ref, "version", None) or (existing_count + 1)`). When the same `ArtifactGraph`
is shared per run (the engine path) the two agree by construction. But any caller that
constructs a throwaway graph (CR-01 clarify path; `_handle_revision` at
`engine.py:2697`) gets a graph version of `1` that overrides the DB count, so DB
versions are NOT monotonic per (run, kind) for those rows. The `version` column is
documented "monotonic per (run, kind)" (`artifact_ref.py:43`) — this invariant is
violated for clarify/revision writes. (For `_handle_revision` the row lands in a fresh
revision run so `1` is coincidentally correct; for clarify it is not — see CR-01.)

**Fix:** Centralize versioning in ONE place. Either always share the per-run graph, or
have `ScopedStore.write_ref` ignore the dataclass `version` and always use
`existing_count + 1` (the DB is the durable source of truth). Document which is
canonical.

### WR-02: Best-effort `except Exception` blocks swallow real persistence failures with only debug/warning logs

**File:** `backend/agents/execution_engine/engine.py:124-129, 729-734, 861-866 (debug), 2861-2866`; `backend/agents/execution_engine/clarify_engine.py:437-438`

**Issue:** Every typed-substrate write (`_dual_write_artifact`, the run_events sink,
workspace/capabilities creation, clarifications persist) wraps the DB call in a broad
`except Exception` that degrades to a `logger.debug`/`logger.warning` and continues. The
stated rationale is the offline characterization harness has no `workflow_runs` FK row.
The problem: this masks genuine production failures (FK violations from a real bug,
connection exhaustion, schema drift) as silent no-ops. A run that fails to persist ALL
its artifacts/events would look completely healthy in logs at default levels (several
are `logger.debug`). There is no metric, no error event, and no way to distinguish "no
FK row in tests" from "the artifact_refs table is broken in prod."

**Fix:** Narrow the catch to the specific expected exception (e.g. SQLAlchemy
`IntegrityError` for the missing-FK harness case) and re-raise / surface anything else,
or at minimum log at `warning`+ with a stable error code and emit a counter so silent
total-persistence-loss is observable. Do not catch bare `Exception` on the DB write
path.

### WR-03: `lineage()` orders by `created_at` but `created_at` has second-or-finer ties from a Python-side default

**File:** `backend/agents/authz.py:224-238`; `backend/app/models/artifact_ref.py:54-56`

**Issue:** `ScopedStore.lineage` returns refs `order_by(ArtifactRef.created_at.asc())`,
and `_build_lineage_tree` (`runs.py:520`) relies on this ordering to assemble the tree.
`created_at` is set by a Python-side `default=lambda: datetime.now(timezone.utc)` at
flush time. Multiple artifacts written in the same task loop iteration (e.g. the
per-task HTML write + a `produces` fold write happen back-to-back) can receive
timestamps that tie at the stored precision, making the order between same-timestamp
refs non-deterministic. The tree builder tolerates dangling parents but assumes a
parent appears before its child is processed only insofar as it pre-builds all nodes
first (it does), so the tree itself is robust — but any consumer that depends on
`lineage()` insertion order (and the docstring implies it) gets unstable results.

**Fix:** Add a stable secondary sort key, e.g. `order_by(created_at.asc(),
version.asc(), id.asc())`, or order by the monotonic `seq`-equivalent. For artifact_refs
specifically there is no monotonic per-run counter; consider adding one or sort by
`(version, id)` within a kind.

### WR-04: `_build_lineage_tree` shares the same node dict across multiple parents, corrupting the tree on diamond lineage

**File:** `backend/app/api/runs.py:551-573`

**Issue:** `nodes = {r.id: _node(r) for r in refs}` builds ONE dict per ref. When a ref
has multiple in-set parents (`_parent_ids` can return both `derived_from` AND entries
from `parents[]`), the loop appends the SAME `nodes[r.id]` object as a child under every
parent:

```python
for pid in pids:
    nodes[pid]["children"].append(nodes[r.id])
```

This means a single node object is referenced from multiple `children` lists. JSON
serialization will duplicate it (acceptable), but if any later code mutates a node
in-place it mutates it under every parent, and a cycle (A parent of B, B parent of A,
both in-set) produces an infinite structure that `json` serialization (FastAPI response
encoding) will fail on with `ValueError: Circular reference detected`. The docstring
claims "Cycles … are tolerated" but the implementation does not break cycles — it only
tolerates dangling (out-of-set) parents.

**Fix:** Track visited nodes when attaching children and skip an edge that would
re-introduce an already-attached ancestor, or detect cycles explicitly:

```python
attached: set[str] = set()
for r in refs:
    for pid in _parent_ids(r):
        if r.id in attached:   # already placed — don't double-attach
            break
        nodes[pid]["children"].append(nodes[r.id])
        attached.add(r.id)
```
and add a cycle guard so a mutual-parent pair cannot create a self-referential tree
before it reaches the JSON encoder.

### WR-05: `restore_non_terminal_runs` re-arms resume events but never restores artifact/clarification state

**File:** `backend/agents/execution_engine/engine.py:2450-2505`

**Issue:** The docstring says it restores runs "so they can be resumed by user action,"
and re-registers `asyncio.Event`s for `waiting_for_user` runs. But it re-arms a resume
event for EVERY non-terminal run (not just `waiting_for_user` — the `NON_TERMINAL` set
includes `running`/`generating`/etc.), and it transitions the state machine to whatever
status the DB row holds. A run in `generating` that was interrupted by a restart now has
a state-machine entry of `generating` and a dangling resume event, but no coroutine is
actually driving it — the engine never re-launches the pipeline body. So these runs are
"restored" into a permanently-stuck state that looks live to the state machine. The
30-second SC-007 claim is met trivially (it only touches in-memory dicts), but the
restoration is incomplete: only `waiting_for_user` runs are genuinely resumable.

**Fix:** Only re-register resume events for `waiting_for_user` runs; for other
non-terminal states either mark them `failed` (the process that owned them is gone) or
explicitly document that they are abandoned. Don't transition the state machine into a
live-looking state with no driver.

### WR-06: `_handle_revision` is invoked outside the `execute()` seq/persistence boundary, so revision events are never durably logged

**File:** `backend/app/api/websocket.py:637-645`; `backend/agents/execution_engine/engine.py:2590-2741`

**Issue:** The PERSIST-03 design routes ALL engine events through the single `execute()`
wrapper that stamps `seq`/`event_id` and persists `run_events`. But the `run_revision`
handler calls `_rev_engine._handle_revision(...)` directly, emitting `pipeline_start` /
`pipeline_complete` / `state_restoration_failed` through `_send_revision_event` with no
`seq`, no `event_id`, and no `run_events` row. So a revision run produces a
`WorkflowRun` and an `artifact_refs` row but an empty `run_events` log — the
`GET /{id}/events` replay endpoint returns nothing for revision runs, breaking the
idempotent-replay contract (API-05) for that run class. This is a consistency gap, not
just a missing-feature: the same run id has artifacts but no event ledger.

**Fix:** Route revision emits through the same stamping path (extract the stamping into a
shared helper both `execute()` and `_handle_revision` use), or document that
`*_revision` runs are intentionally excluded from `run_events` and have the events
endpoint say so.

### WR-07: 0014 backfill assigns the same `created_at = func.now()` to every backfilled workspace and is not idempotent

**File:** `backend/alembic/versions/0014_typed_artifacts_persistence.py:176-203`

**Issue:** The data backfill loops over existing runs and inserts one workspace per run.
Two robustness gaps: (1) `now = sa.func.now()` is evaluated once and reused for every
insert, so all backfilled workspaces share an identical `created_at` (cosmetic but
hides ordering). (2) The migration is not re-run-safe: if `upgrade()` partially applied
(e.g. failed mid-loop and was retried), runs that already got `owner_id`/`workspace_id`
set would get a SECOND workspace row, since the loop reads ALL runs unconditionally with
no `WHERE workspace_id IS NULL` guard. Additive migrations should be defensive against
partial application.

**Fix:** Filter the backfill to unscoped runs only:

```python
existing = bind.execute(
    sa.select(workflow_runs.c.id, workflow_runs.c.user_id)
    .where(workflow_runs.c.workspace_id.is_(None))
).fetchall()
```

## Info

### IN-01: `ScopedStore.assert_owns` treats an absent parent as "allowed" — document the trust boundary

**File:** `backend/agents/authz.py:423-435`

**Issue:** When the parent run row is absent, `assert_owns` returns `None` (allow). This
is intentional (TTL-swept/same-owner degrade) and propagated correctly, but it means a
caller can pass any non-existent `parent_run_id` and pass the ownership check. Since the
subsequent seed read finds no files, there's no leak, but the method name implies a
stronger guarantee than it provides. A one-line note at the call site contract would
prevent future misuse.

**Fix:** Rename to `assert_not_cross_owner` or add an explicit comment that absence ==
allow by design.

### IN-02: `ALWAYS_CLARIFY = True` is a hardcoded behavioral flag with no config override

**File:** `backend/agents/execution_engine/engine.py:139`

**Issue:** Forcing CLARIFY_REQUIRED on every run is a product decision baked into a
module constant; the comment says "Set to False to let the planner decide" but it is not
wired to settings. Toggling requires a code edit + deploy.

**Fix:** Source from `settings.ALWAYS_CLARIFY` so it can be changed per environment.

### IN-03: Bare `except Exception: pass` in `export_pptx` and `_extract_chain_context` hides JSON-decode failures

**File:** `backend/app/api/runs.py:177-178, 337-338`

**Issue:** `json.loads(wr.agent_outputs)` failures are swallowed silently. A corrupted
`agent_outputs` blob results in an empty result with no log, making field diagnosis
hard. (Not a security issue — the data is already owner-scoped.)

**Fix:** `except (ValueError, TypeError) as e: logger.warning(...)` at minimum.

### IN-04: `clarify_engine` keyword-match question routing has overlapping keys with silent first-match-wins

**File:** `backend/agents/execution_engine/clarify_engine.py:346-359`

**Issue:** The `QUESTION_LIBRARY` substring/word-overlap matching iterates a dict and
takes the first match; with keys like `topic`/`subject`, `tone`/`style`,
`persona`/`user` mapping to identical questions, and `data`/`security`/`integration`
sharing words, the selected question for an ambiguity item depends on Python dict
insertion order. It "works" but is fragile and untested for collisions. Maintainability
risk, not a correctness bug today.

**Fix:** Make the mapping explicit (ordered list of (priority, matcher, question)) or
document that ties resolve by insertion order.

### IN-05: `_now()`/timestamp helpers re-import `datetime`/`json` inside functions

**File:** `backend/agents/execution_engine/engine.py:70, 142-144`; `clarify_engine.py:60-61`

**Issue:** `_log_event` does `import json as _json` per call and `_now()` imports
`datetime` per call. Minor; module-level imports are clearer and avoid repeated import
machinery. Purely stylistic.

**Fix:** Hoist these to module-level imports (the module already imports `json` at top).

---

_Reviewed: 2026-06-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
