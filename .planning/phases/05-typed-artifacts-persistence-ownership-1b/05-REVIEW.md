---
phase: 05-typed-artifacts-persistence-ownership-1b
reviewed: 2026-06-08T13:10:00Z
depth: standard
iteration: 3
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
  critical: 0
  warning: 0
  info: 3
  total: 3
status: clean
---

# Phase 5: Code Review Report (iteration 3 — FINAL re-review)

**Reviewed:** 2026-06-08
**Depth:** standard
**Status:** clean

## Summary

This is iteration 3, the final pass of the auto fix↔review loop. The iteration-2 review
raised one BLOCKER (CR-01: the round-1 WR-06 fix was defeated on a real DB — revision
`run_events` could not persist and `/events` 404'd for every revision run) plus one Warning
(WR-01: a stale `_RunEventSink.persist` docstring). The fixer landed those (commits up to
`2d72081`). I read the current code — not the fix report — to verify the fix holds and to
hunt for any regression the latest edits introduced.

**Verdict: the iteration-2 BLOCKER fix HOLDS. Zero Critical, zero Warning findings remain.**
Three Info-tier observations are recorded below but are out of `fix_scope` (critical_warning)
and do not gate the loop.

### 1. CR-01 (revision run scoping + run_events persistence + /events resolution) — VERIFIED FIXED

Traced the full revision path end to end:

- **`engine.py::_handle_revision` (2671, 2729-2746):** the store is built
  `ScopedStore(owner_id=owner_id)` and the parent artifact's workspace
  (`original.workspace_id`) is threaded onto it (`store._workspace_id = _rev_ws_id`) AFTER
  the cross-run read resolves `original` and BEFORE the first emit. The sink is armed only
  inside the `if owner_id and _rev_ws_id:` guard (2730, 2746), so it can never be armed with
  a workspace-less store. `original.workspace_id` is read from `artifact_refs`, whose
  `workspace_id` column is `NOT NULL` (`artifact_ref.py:35`,
  `0014_typed_artifacts_persistence.py:47`), so the read value is provably non-None — the
  guard's "else" (sink never armed) is unreachable for any parent artifact that came from
  the DB.

- **`authz.py::set_run_scope` (351-394):** stamps `(owner_id, workspace_id)` onto the
  revision `workflow_runs` row and FAILS LOUD with `ValueError` on a falsy owner or
  workspace (369-374, AUTHZ-01/03 — never widens nullability), and no-ops when the row is
  absent (offline-harness parity, same shape as `append_event`). The lookup is
  unscoped-by-owner, but the write only ever stamps the caller-supplied real principal, and
  the run_id is a freshly-generated uuid for this same user's revision run, so there is no
  cross-owner write surface.

- **`websocket.py` revision-run creation (608-639):** the revision `WorkflowRun` is created
  with `owner_id=user.id` (never owner-None at creation, 623) and `user_id=user.id` (637);
  the workspace is stamped back by the engine. The `/events` endpoint
  (`runs.py:674-696`) first resolves the row by `(id, user_id)`, reads its `workspace_id`,
  then builds `ScopedStore(owner_id=current_user.id, workspace_id=workflow_run.workspace_id)`
  and calls `get_run` — exactly what the new regression test mirrors.

- **`run_events.workspace_id` / `owner_id` (run_event.py:30-31; 0014:105-106):** both
  `NOT NULL`. `append_event` stamps `self._owner_id` / `self._workspace_id`
  (authz.py:300-305); with the armed store carrying the real workspace, the insert satisfies
  both constraints — no IntegrityError, no swallow.

- **The new regression test
  `test_revision_run_events_persist_and_resolve_on_real_db`
  (test_revision_intelligence.py:368-459)** genuinely exercises a real sqlite DB: the
  `db_factory` fixture builds an in-memory SQLite engine via `Base.metadata.create_all`
  (test:50-55) — the SAME ORM metadata the 0014 migration encodes, so all four typed tables
  with their NOT NULL columns exist — and monkeypatches `app.models.database.SessionLocal`
  onto it (test:59) so every engine-path `ScopedStore` (no injected session) hits this DB.
  It creates the revision run with `workspace_id=None` exactly as the WS layer transiently
  does (test:404-414), drives `_handle_revision`, then asserts (a) the run row's workspace
  was stamped back to `WS` (440), (b) an owner+workspace-scoped store mirroring the `/events`
  endpoint resolves the run (445-447, the 404-prevention check), and (c) the
  `pipeline_start`/`pipeline_complete` `run_events` rows actually persisted with the real
  `(owner_id, workspace_id)` and replay in monotonic `seq` order (450-459). I ran the suite:
  **10 passed** (this test included). The pre-fix failure mode (NOT NULL violation on
  `workspace_id=None`, swallowed by the WR-02 narrow-catch) is the exact behavior this test
  now precludes.

### 2. WR-01 docstring fix — VERIFIED accurate

The `_RunEventSink` class docstring (engine.py:99-107) now states the WR-02 narrowed
contract precisely: the DB-write case (`SQLAlchemyError`) degrades to a `warning`; **any
OTHER exception PROPAGATES (re-raised) — it is NOT swallowed**; `seq`/`event_id` are stamped
regardless so 0A parity holds. This matches the actual code at engine.py:127-141:
`except Exception` → `if not isinstance(exc, SQLAlchemyError): raise` → else
`logger.warning(...)`. The two parallel sites (the workspace/caps degrade at 741-753 and the
revision scope-writeback degrade at 2734-2745) follow the identical narrow-catch + re-raise
shape. No stale `debug`-swallow wording remains anywhere in the sink path.

### 3. Regression hunt on the latest edits — NONE FOUND

- **Non-revision event ordering / payloads:** UNCHANGED. The public `execute()` wrapper
  (537-606) and its single seq/event_id boundary are untouched by the iteration-3 edits; the
  revision changes are confined to `_handle_revision` and the new `set_run_scope` method.
  The revision path uses its OWN `_stamped_send` counter (2690-2705) and is deliberately NOT
  routed through `execute()`, so there is no double-stamping and no shared-counter
  interference. On the revision path the deferred sink-arm sits strictly before the first
  emit (`pipeline_start` at 2783, below the read at 2713), so event ORDER is unchanged
  (`pipeline_start` → `pipeline_complete`); only the persistence side-effect was added.
- **Scoping seam correctness:** `set_run_scope` and `assert_owns` both perform the
  intentional unscoped-by-owner lookup with a documented, bounded write/compare; neither
  widens the default-deny read filter. `assert_owns` still PROPAGATES `PermissionError`
  (engine.py:872-873) so a cross-owner parent is never silently seeded (L16 intact).
- **Kernel purity (INV):** verified `agents/artifacts/*.py` imports stdlib only — no
  `app.models` / `app.api` / `fastapi` / `sqlalchemy` (grep clean). `agents/authz.py`
  imports `app.models.*` inside methods (the sanctioned pattern) and never `app.api.*`.
- **Additive-only migrations:** 0014 only adds; the typed-table `workspace_id`/`owner_id`
  columns are `NOT NULL` (AUTHZ-01) and the backfill is idempotent (WR-07,
  `WHERE workspace_id IS NULL`). No migration files were touched in iteration 3.

Targeted suites re-run green during this review: `test_revision_intelligence` (10 passed,
incl. the new real-DB regression). The iteration-2 fix record documents the broader
touched-area set (`test_run_events`, `test_runs_api_events`, `test_runs_api_artifacts`,
`test_artifact_store`, `test_execution_engine`, `test_resumability`,
`test_phase5_revision_validation`, `test_parent_run_ownership`,
`test_characterization_prototype{,_revision}`) at 78 passed, consistent with the unchanged
non-revision contract.

## Structural Findings (fallow)

No `<structural_findings>` block was provided with this review; none incorporated.

## Info

_The following are non-blocking observations (Info tier). They are OUT of the
critical_warning fix scope and do not affect loop termination._

### IN-01: `_handle_revision` skips run-events persistence (silently) when `owner_id` is falsy

**File:** `backend/agents/execution_engine/engine.py:2730`
**Issue:** The sink-arm and scope-writeback are gated on `if owner_id and _rev_ws_id:`. The
live WS call site always passes `owner_id=user.id` (websocket.py:664), so this never fires
in production — but if a future/forward caller passes `owner_id=None`, the revision still
streams events while persisting no `run_events` ledger and writing no run scope, with no
log line. The subsequent `store.write_ref(_rev_ref)` would then raise `ValueError`
(AUTHZ-03) and surface the problem, so it is not a silent data-loss path today, just an
implicit precondition.
**Fix:** Consider asserting `owner_id` truthy at method entry (mirroring `ClarifyEngine.run`'s
falsy-owner `ValueError`) so the contract is explicit rather than encoded in a downstream
`write_ref` failure.

### IN-02: `set_run_scope` lookup is unscoped-by-owner by design but lacks a same-owner sanity assertion

**File:** `backend/agents/authz.py:377-391`
**Issue:** `set_run_scope` reads the target `workflow_runs` row by id alone and overwrites its
`(owner_id, workspace_id)` with the caller-supplied values. This is safe in the current
single call site (a freshly-created revision run owned by the same caller, after
`assert_owns` on the parent), but the method itself does not verify the row's existing
`owner_id` is None-or-equal before clobbering it — so a future caller could re-scope a row to
a different owner. The docstring documents the intent; the guard is by-convention.
**Fix:** Optionally add a defensive check: only stamp when the existing `owner_id` is None or
already equals the supplied owner; otherwise raise (turning a misuse into a loud failure
rather than a cross-owner overwrite).

### IN-03: revision `pipeline_complete` reports `total_duration: 0.0` and `agents_completed: 1` as constants

**File:** `backend/agents/execution_engine/engine.py:2843-2845`
**Issue:** The revision path emits a placeholder `total_duration=0.0` and hardcoded
`agents_completed=1`/`agents_total=1`. This is consistent with the Phase-3 "store the
instruction + context as the revision artifact" stub (the method comment at 2795-2797 notes
a full DeepAgent revision loop is not yet wired), so it is intentional, not a defect — but
the constant duration will read as "instant" in any UI/telemetry that consumes it.
**Fix:** When the real revision agent loop lands, replace the constants with measured values;
no action needed for this phase.

---

_Reviewed: 2026-06-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
