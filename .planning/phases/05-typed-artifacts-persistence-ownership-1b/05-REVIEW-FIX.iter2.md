---
phase: 05-typed-artifacts-persistence-ownership-1b
fixed_at: 2026-06-08T00:00:00Z
review_path: .planning/phases/05-typed-artifacts-persistence-ownership-1b/05-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-06-08
**Source review:** .planning/phases/05-typed-artifacts-persistence-ownership-1b/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (2 Critical + 7 Warning; the 5 Info findings were out of scope and not addressed)
- Fixed: 9
- Skipped: 0

**Invariant compliance:** Every fix respected the project invariants. No `app.*` imports were
added to the kernel (`agents/artifacts/`). Migration 0014 was changed only additively (a
`WHERE workspace_id IS NULL` narrowing + a per-row `now()`), never destructively. CR-02 was
fixed by enforcing a non-None owner at the write seam (fail-loud), NOT by making any column
nullable. No dual implementations were introduced — every fix was in place.

**Shared root cause (CR-01 / CR-02 / WR-01):** `_persist_qa` built a throwaway `ArtifactGraph`
per clarification round, so `ref.version` was always `1` (non-deterministic reconnect read) and
the owner could be persisted as `None`. A single seam fix in `ScopedStore.write_ref` plus the
`ClarifyEngine` entry guard resolved all three; they are committed together (`fbc3e2f`).

## Tests

Ran the touched-area tests with `python3.11` (no venv). All green:

- `tests/unit/test_execution_engine.py`, `test_resumability.py`, `test_revision_intelligence.py`,
  `test_run_events.py`, `test_runs_api_events.py`, `test_runs_api_artifacts.py`,
  `test_artifact_store.py`, `test_migration_0014.py`
- `tests/agents/test_artifact_graph.py`, `test_parent_run_ownership.py`, `test_migration_ledger.py`,
  `test_execution_context.py`

Final targeted sweep: **84 passed, 1 skipped**. Earlier a full `tests/agents/` + engine run
(498 passed, 19 skipped) confirmed the WR-02 engine narrowing did not regress the broader suite.

Test edits required by the new invariants (committed alongside the relevant fix):
- `test_execution_engine.py` — the four ClarifyEngine tests now pass `owner_id` (now required by
  AUTHZ-03).
- `test_run_events.py` — the `_RunEventSink` degrade test was split: a SQLAlchemy
  `OperationalError` degrades (offline-harness condition), a non-DB `RuntimeError` now propagates
  (the old test asserted the masking behavior WR-02 removes).

Not run: `tests/agents/test_phase5_revision_validation.py` — it drives the LIVE agent runtime
(prototype_revision fix-loop) and hangs offline; it exercises a different code path than the
artifact/event seam touched here. `test_revision_intelligence.py` (which DOES directly exercise
`_handle_revision`, including the WR-06 stamping path against a real in-memory schema) covers the
revision changes — 9/9 passing.

## Fixed Issues

### CR-01: Multi-round clarifications all persist at `version=1` (non-deterministic reconnect read)

**Files modified:** `backend/agents/authz.py`, `backend/agents/execution_engine/clarify_engine.py`, `backend/tests/unit/test_execution_engine.py`
**Commit:** fbc3e2f
**Applied fix:** Added `force_db_version` to `ScopedStore.write_ref`; when set, the DB
`COUNT(*)` is the authoritative cross-call per-(run, kind) version (ignoring the throwaway
graph's always-`1` value). `_persist_qa` now passes `force_db_version=True`, so rounds version
monotonically (round 1→v1, round 2→v2, …) and the websocket reconnect read (`order_by version
ASC`, take `[-1]`) deterministically returns the newest round.

### CR-02: `ArtifactRef.owner_id` can be persisted as `None` (violates never-None AUTHZ-03)

**Files modified:** `backend/agents/authz.py`, `backend/agents/execution_engine/clarify_engine.py`
**Commit:** fbc3e2f
**Applied fix:** Enforced at the single write seam — `ScopedStore.write_ref` raises `ValueError`
if the resolved owner (`ref.owner_id or self._owner_id`) is falsy (fail-loud, never persist a
dead owner-None row). `ClarifyEngine.run` additionally asserts a real `owner_id` at entry. No
column was made nullable. **Requires human verification** that no production caller relies on the
previously-silent owner-None behavior (live engine path already always passes `ectx.owner_id`,
so this is latent there).

### WR-01: `ArtifactGraph.write_ref` and `ScopedStore.write_ref` compute `version` independently

**Files modified:** `backend/agents/authz.py`, `backend/agents/execution_engine/clarify_engine.py`
**Commit:** fbc3e2f
**Applied fix:** Centralized cross-call versioning in the DB. When a caller cannot share the
per-run graph it passes `force_db_version=True` and the store stamps `existing_count + 1`; the
engine path (which shares the graph) keeps the by-construction-agreeing dataclass version. The
canonical source is now documented in the `write_ref` docstring.

### WR-02: Best-effort `except Exception` blocks swallow real persistence failures

**Files modified:** `backend/agents/execution_engine/engine.py`, `backend/agents/execution_engine/clarify_engine.py`, `backend/tests/unit/test_run_events.py`
**Commits:** 336de3d (engine), fbc3e2f (clarify portion), dac02e5 (test contract)
**Applied fix:** Narrowed every typed-substrate DB-write catch (run_events sink,
workspace/capabilities creation, `_dual_write_artifact`, clarifications persist) to
`sqlalchemy.exc.SQLAlchemyError` — the offline-harness no-schema condition (`OperationalError`
missing table / `IntegrityError` missing FK) — and surfaced it at WARNING with run context. Any
non-DB exception (including the AUTHZ-03 `ValueError`) now propagates instead of being masked as
a silent debug no-op. **Requires human verification** that no live code path legitimately threw a
non-`SQLAlchemyError` from these write seams that was previously (intentionally) swallowed; the
broad 498-test sweep found none.

### WR-03: `lineage()` ordering by `created_at` has unstable ties

**Files modified:** `backend/agents/authz.py`
**Commit:** e956dc8
**Applied fix:** `ScopedStore.lineage` now orders by `(created_at ASC, version ASC, id ASC)` so
same-timestamp refs (Python-side `datetime.now` default tying at flush) order deterministically.

### WR-04: `_build_lineage_tree` shares one node across parents; cycles crash the JSON encoder

**Files modified:** `backend/app/api/runs.py`
**Commit:** 82d0afb
**Applied fix:** Each node is now attached under exactly one non-cycle-forming parent (chosen via
an ancestry walk over the selected edges that refuses an edge whose parent is a descendant of the
child). Unattachable nodes surface as roots so nothing is lost. Verified manually that both a
mutual-parent cycle (A↦B, B↦A) and a diamond (D with parents B, C under A) now serialize to JSON
without `Circular reference detected`. **Requires human verification** — this changes diamond
lineage rendering (a multi-parent node now appears under one parent only); confirm that is
acceptable for the `GET /{id}/artifacts` consumer.

### WR-05: `restore_non_terminal_runs` re-arms resume events for un-resumable runs

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** a1492b6
**Applied fix:** Only `waiting_for_user` runs are re-registered as resumable; every other
non-terminal run (running/generating/…), whose driving coroutine the restart killed, is marked
`failed` with an explanatory `error` (single DB commit after the scan) so it is not a
phantom-live row. **Requires human verification** — this is a behavior change to startup
recovery; confirm marking interrupted in-flight runs as `failed` is the desired product behavior
(vs. leaving them for a future re-launch mechanism).

### WR-06: revision events bypass the `execute()` seq/persistence boundary

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** f3cdd89
**Applied fix:** `_handle_revision` now wraps its `websocket_send_fn` with a stamping path that
arms a `_RunEventSink` on the revision run's `ScopedStore`, stamps a monotonic `seq` + unique
`event_id` onto each event's data, and persists one `run_events` row before sending (best-effort,
mirroring `execute()`). Revision runs now have a populated event ledger for the `GET /{id}/events`
replay (API-05). Verified by `test_revision_intelligence.py` (real in-memory schema, 9/9 pass).

### WR-07: 0014 backfill is not idempotent and shares one `created_at`

**Files modified:** `backend/alembic/versions/0014_typed_artifacts_persistence.py`
**Commit:** 0e3359b
**Applied fix:** The default-workspace backfill now selects only `WHERE workspace_id IS NULL`
runs (re-run-safe against partial application — no second workspace per already-scoped run) and
evaluates `func.now()` per-row. The change is additive and non-destructive (it only narrows which
rows are touched), so the already-applied migration stays safe. Migration tests pass (8 passed, 1
skipped).

---

_Fixed: 2026-06-08_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
