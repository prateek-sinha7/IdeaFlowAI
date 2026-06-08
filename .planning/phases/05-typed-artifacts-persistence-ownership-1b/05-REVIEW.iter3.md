---
phase: 05-typed-artifacts-persistence-ownership-1b
reviewed: 2026-06-08T00:00:00Z
depth: standard
iteration: 2
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
  critical: 1
  warning: 1
  info: 5
  total: 7
status: issues_found
---

# Phase 5: Code Review Report (iteration 2 — re-review after fixer)

**Reviewed:** 2026-06-08
**Depth:** standard
**Status:** issues_found

## Summary

This is iteration 2 of the auto fix↔review loop. The fixer landed 8 commits
(`fbc3e2f..f3cdd89`) for the 9 Critical+Warning findings from round 1. I read the
current code (not the commit messages) to verify each fix and to hunt for
regressions the edits introduced.

**Verified RESOLVED (7 of 9):**

- **CR-01** (multi-round clarifications all at `version=1`): RESOLVED. `_persist_qa`
  now passes `force_db_version=True`; `ScopedStore.write_ref` stamps
  `existing_count + 1` when that flag is set (authz.py:179-182), so round N → vN and
  the reconnect read (`websocket.py:555`, `order_by(version ASC)[-1]`) deterministically
  returns the newest round.
- **CR-02** (owner_id can be `None`): RESOLVED. `ClarifyEngine.run` raises
  `ValueError` on a falsy `owner_id` (clarify_engine.py:113-116) AND
  `ScopedStore.write_ref` rejects a falsy resolved owner (authz.py:162-167). The live
  call site passes `ectx.owner_id` (a required non-None dataclass field, context.py:57).
- **WR-01** (graph vs store version divergence): RESOLVED by the same `force_db_version`
  seam — the DB count is now authoritative for throwaway-graph callers.
- **WR-02** (best-effort swallow of all exceptions): RESOLVED. The three DB-write sinks
  (`_RunEventSink.persist` engine.py:124-138; the workspace/caps create degrade
  engine.py:738-744; the dual-write engine.py:929-936) and `_persist_qa` now narrow the
  catch to `SQLAlchemyError` and re-raise anything else. New contract tests added
  (test_run_events.py: `test_run_event_sink_reraises_non_db_persist_failure`).
- **WR-03** (unstable `lineage()` order on tied `created_at`): RESOLVED. Secondary sort
  keys `(version, id)` added (authz.py:267-271).
- **WR-04** (shared node / cycle crash in `_build_lineage_tree`): RESOLVED. Each node now
  attaches to at most one parent with a `_would_cycle` guard (runs.py:565-607). Trade-off
  documented: a diamond node surfaces under one parent only (its `parents[]`/`derived_from`
  fields are still present on the node), which is acceptable vs. the prior circular-ref
  500.
- **WR-05** (`restore_non_terminal_runs` re-arms every non-terminal state): RESOLVED. Only
  `waiting_for_user` runs are re-armed; all other non-terminal runs are marked `failed`
  with an explanatory `error` (engine.py:2505-2531).
- **WR-07** (0014 backfill not idempotent + shared timestamp): RESOLVED. The backfill now
  filters `WHERE workspace_id IS NULL` (0014:185-188) and evaluates `sa.func.now()`
  per-row (0014:202). `workflow_runs.user_id` is `nullable=False`, so no None owner can be
  backfilled — AUTHZ-03 holds.

All targeted unit suites pass: `test_run_events`, `test_execution_engine`,
`test_artifact_store`, `test_migration_0014`, `test_runs_api_artifacts`,
`test_runs_api_events`, `test_revision_intelligence`, `test_resumability`,
`test_artifact_graph` (54 + 7 green).

**NOT resolved / regressed — see CR-01 below.** WR-06's fix is structurally present but
does not actually persist or expose revision events on a real DB: the revision
`WorkflowRun` is created unscoped (`owner_id`/`workspace_id` = None) and the revision
`ScopedStore` carries no `workspace_id`, so (a) the `run_events` insert violates the
`workspace_id NOT NULL` constraint and is swallowed by the now-narrowed
`SQLAlchemyError` degrade, and (b) the `/events` endpoint 404s for every revision run
because `get_run` is owner+workspace scoped and the revision row has neither. The same
unscoped revision row is an AUTHZ-03 default-deny hole.

## Structural Findings (fallow)

No `<structural_findings>` block was provided with this review; none incorporated.

## Critical Issues

### CR-01: WR-06 fix is defeated on a real DB — revision `run_events` cannot persist and `/events` 404s for every revision run (AUTHZ-03 hole on the revision run row)

**File:** `backend/app/api/websocket.py:608-624`; `backend/agents/execution_engine/engine.py:2664, 2674-2676, 2689`; `backend/agents/authz.py:284-312`; `backend/app/models/run_event.py:31`; `backend/app/api/runs.py:687-696`

**Issue:** The round-1 WR-06 fix wraps the revision emit path with a `_RunEventSink`
(`engine.py:2674-2692`) so revision events get `seq`/`event_id` stamped and an
`append_event` call. But two unscoped-principal facts make the fix a no-op on Postgres
and re-open the very gap WR-06 was meant to close:

1. **The revision `ScopedStore` has no `workspace_id`.** `_handle_revision` builds
   `store = ScopedStore(owner_id=owner_id)` (engine.py:2664) — `workspace_id` defaults to
   `None`. `append_event` stamps `workspace_id=self._workspace_id` = `None`
   (authz.py:304), but `run_events.workspace_id` is `nullable=False`
   (run_event.py:31 / 0014:106, AUTHZ-01). On a real DB this raises `IntegrityError`,
   which — after the WR-02 narrowing — is caught as `SQLAlchemyError` and degraded to a
   warning (engine.py:131-138). So **no `run_events` row is ever written for a revision
   run.** (The revision `artifact_refs` write succeeds because it uses
   `original.workspace_id` at engine.py:2771 — exactly the asymmetry WR-06 described:
   artifacts persist, the event ledger does not.)

2. **The revision `WorkflowRun` is created unscoped.** websocket.py:608-620 inserts the
   revision run with only `user_id` set — `owner_id` and `workspace_id` are left `None`
   (both nullable on `workflow_runs`, 0014:139-141). The `/events` endpoint resolves the
   run via `store.get_run(workflow_id)` (runs.py:692), which applies `_scope_owner_ws`
   (`owner_id == current_user.id AND workspace_id == workflow_run.workspace_id`,
   authz.py:124-127). Since the revision row's `owner_id` is `None` (≠ `current_user.id`),
   `get_run` returns `None` → **404 for every revision run's `/events`**, regardless of
   whether any row landed. This also means the revision run row itself violates the
   never-None AUTHZ-03 / AUTHZ-01 invariant ("every new table/row carries a real
   owner_id + workspace_id").

Net effect: the idempotent-replay contract (API-05) is still broken for the revision run
class — same as round 1 — but now the failure is masked by the best-effort
`SQLAlchemyError` degrade instead of being structurally absent. The offline test harness
has no DB schema, so `test_revision_intelligence` passes trivially and does not catch
this; it is a real-DB-only defect.

**Fix:** Scope the revision run and thread its workspace into the sink. Minimal:

```python
# websocket.py — create the revision run owner+workspace scoped (AUTHZ-01/03).
# Reuse the PARENT run's workspace so the lineage stays in one workspace, or
# create a fresh workspace via ScopedStore.create_workspace.
_parent = db.query(WorkflowRun).filter(WorkflowRun.id == _rev_parent_run_id).first()
_rev_ws_id = _parent.workspace_id if _parent else None
_rev_wr = WorkflowRun(
    id=_rev_pipeline_run_id,
    user_id=user.id,
    owner_id=user.id,            # AUTHZ-03 — never None
    workspace_id=_rev_ws_id,     # AUTHZ-01 — real workspace
    ...
)
```
```python
# engine.py _handle_revision — give the store a real workspace so append_event
# can satisfy run_events.workspace_id NOT NULL.
store = ScopedStore(owner_id=owner_id, workspace_id=original.workspace_id)
# (resolve original.workspace_id BEFORE arming the sink, or pass the parent ws in)
```
Then `get_run` will resolve the revision run and `read_events` will return its ledger.
Add a real-DB (sqlite-with-0014-schema) test that creates a revision run, drives
`_handle_revision`, and asserts `GET /{rev_id}/events` returns the stamped
`pipeline_start`/`pipeline_complete` rows — the offline harness alone cannot cover this.

## Warnings

### WR-01: `_RunEventSink.persist` docstring still claims a silent `debug` swallow after the WR-02 narrowing

**File:** `backend/agents/execution_engine/engine.py:99-103`

**Issue:** The class docstring still reads "swallowed with a debug log so the live event
stream … are NEVER perturbed" and "stripped from the 0A multiset." The implementation
changed under WR-02: it now re-raises any non-`SQLAlchemyError` and logs the DB case at
`warning`, not `debug`. The stale docstring will mislead the next maintainer into
believing a non-DB failure is still swallowed (the opposite of the new contract) — a
maintainability hazard around a security-relevant persistence path.

**Fix:** Update the docstring to match: "DB failures (`SQLAlchemyError`, e.g. the offline
harness has no schema) degrade to a `warning`; any other exception propagates as a real
bug." Same one-line drift check on the parallel comments at engine.py:738-744 and
929-936 (those comments are accurate; the class docstring at 99-103 is the stale one).

## Info

(Carried over from round 1 — the fixer scoped its commits to Critical+Warning only, so
the five INFO items remain open. None are blocking.)

### IN-01: `ScopedStore.assert_owns` treats an absent parent as "allowed"

**File:** `backend/agents/authz.py:459-463`

**Issue:** When the parent run row is absent, `assert_owns` returns `None` (allow). This
is intentional (TTL-swept/same-owner degrade, now well-documented in the method
docstring) but the method name implies a stronger guarantee than it provides. No leak
(the subsequent seed read finds no files), but a future caller could misread the name.

**Fix:** Optional — the docstring now covers it (authz.py:459-463); consider renaming to
`assert_not_cross_owner` for self-documentation.

### IN-02: `ALWAYS_CLARIFY = True` is a hardcoded behavioral flag with no config override

**File:** `backend/agents/execution_engine/engine.py:148`

**Issue:** Forcing CLARIFY_REQUIRED on every run is a product decision baked into a module
constant; the comment says "Set to False to let the planner decide" but it is not wired to
settings. Toggling requires a code edit + deploy.

**Fix:** Source from `settings.ALWAYS_CLARIFY`.

### IN-03: Bare `except Exception: pass` in `export_pptx`/`_extract_chain_context` hides JSON-decode failures

**File:** `backend/app/api/runs.py:177-178` (and the parallel `_extract_chain_context` blob load)

**Issue:** `json.loads(wr.agent_outputs)` failures are swallowed silently. A corrupted
`agent_outputs` blob yields an empty result with no log, making field diagnosis hard. (Not
a security issue — the data is already owner-scoped.)

**Fix:** `except (ValueError, TypeError) as e: logger.warning(...)` at minimum.

### IN-04: `clarify_engine` keyword-match question routing has overlapping keys with silent first-match-wins

**File:** `backend/agents/execution_engine/clarify_engine.py:362-373`

**Issue:** The `QUESTION_LIBRARY` substring/word-overlap matching iterates a dict and takes
the first match; with keys like `topic`/`subject`, `tone`/`style`, `persona`/`user` mapping
to identical questions, the selected question depends on Python dict insertion order. It
works but is fragile and untested for collisions.

**Fix:** Make the mapping explicit (ordered list of `(priority, matcher, question)`) or
document that ties resolve by insertion order.

### IN-05: `_now()` re-imports `datetime` inside the function; `_log_event` re-imports `json` per call

**File:** `backend/agents/execution_engine/engine.py:151-153, 70`

**Issue:** `_now()` does `from datetime import datetime, timezone` per call and
`_log_event` does `import json as _json` per call. Minor; module-level imports are clearer.
(The `clarify_engine` half of this finding is now resolved — datetime is imported at
module top, clarify_engine.py:22.)

**Fix:** Hoist to module-level imports (the module already imports `json` at top).

---

_Reviewed: 2026-06-08 (iteration 2)_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
