---
phase: 05-typed-artifacts-persistence-ownership-1b
fixed_at: 2026-06-08T00:00:00Z
review_path: .planning/phases/05-typed-artifacts-persistence-ownership-1b/05-REVIEW.md
iteration: 2
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report (iteration 2)

**Fixed at:** 2026-06-08
**Source review:** .planning/phases/05-typed-artifacts-persistence-ownership-1b/05-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 2 (1 Critical CR-01 + 1 Warning WR-01; the 5 Info findings were out of scope and not addressed)
- Fixed: 2
- Skipped: 0

This is iteration 2 of the auto fix↔review loop. The iteration-2 re-review confirmed 7 of
the 9 round-1 fixes as RESOLVED and surfaced one new BLOCKER (CR-01) plus one new Warning
(WR-01), both rooted in the round-1 WR-06 fix. Both are now fixed.

**Invariant compliance:** Every fix respected the project invariants:
- **Kernel purity:** no `app.api` imports added to `agents/`. `agents/authz.py` already
  imports `app.models.*` inside methods (the sanctioned pattern); the new
  `set_run_scope` follows it. `agents/artifacts/` untouched (still stdlib-only).
- **Additive-only migrations (Q3):** no migration files touched.
- **Backward-compat / parity:** the change is confined to the revision path
  (`_handle_revision`) and a new opt-in `ScopedStore` method. The non-revision event
  stream and the `execute()` seq boundary are untouched. All characterization suites
  (`test_characterization_prototype*`, `test_characterization_prototype_revision`) and
  `test_phase5_revision_validation` pass — byte-identity + semantic-event-parity holds.
- **Default-deny scoping (AUTHZ-01/03):** the fix enforces non-None `(owner_id,
  workspace_id)` at the write seam and FAILS LOUD on a falsy principal
  (`set_run_scope` raises `ValueError`). No column was made nullable.
- **No dual implementations (INV-3/INV-12):** fixed in place.
- **deepagents (INV-13):** untouched.

## Fixed Issues (iteration 2)

### CR-01: WR-06 fix defeated on a real DB — revision `run_events` cannot persist and `/events` 404s for every revision run

**Files modified:** `backend/agents/execution_engine/engine.py`, `backend/agents/authz.py`,
`backend/app/api/websocket.py`, `backend/tests/unit/test_revision_intelligence.py`
**Commit:** `2d72081`
**Status:** fixed (regression-tested on a real DB)

**Root cause:** the round-1 WR-06 fix armed a `_RunEventSink` for the revision path, but
(1) the revision `ScopedStore` had `workspace_id=None`, so `append_event` stamped
`run_events.workspace_id=None` into a NOT NULL column → `IntegrityError` → swallowed by the
WR-02 narrow-catch (no revision ledger row ever landed on Postgres/sqlite); and (2) the
revision `workflow_runs` row was created owner/workspace-None, so the owner+workspace-scoped
`get_run` used by `/events` returned `None` → 404 for every revision run (also an AUTHZ-03
default-deny hole on the run row).

**Applied fix:**
- **engine.py `_handle_revision`:** the parent artifact's workspace
  (`original.workspace_id`, NOT NULL on `artifact_refs`) is the authoritative workspace for
  the whole revision run. After the cross-run read resolves `original`, that workspace is
  threaded onto the `ScopedStore` (`store._workspace_id`) so `append_event` satisfies
  `run_events.workspace_id` NOT NULL, and the sink is **armed only then** (the first emit,
  `pipeline_start`, is below the read, so deferring the arm is safe and changes no event
  ordering). The store also stamps `(owner_id, workspace_id)` back onto the revision
  `workflow_runs` row via `set_run_scope`, wrapped in a WR-02-style narrow-catch degrade.
- **authz.py:** new `ScopedStore.set_run_scope(run_id, owner_id, workspace_id)` — the single
  enforced write seam for stamping the scope back; it raises `ValueError` on a falsy owner or
  workspace (AUTHZ-01/03 fail-loud), and no-ops when the row is absent (offline-harness
  parity, same as `append_event`).
- **websocket.py:** the revision `WorkflowRun` is created with `owner_id=user.id` (never
  owner-None at creation) and `parent_run_id` linked when the parent row exists; the engine
  completes the scope by writing back the workspace once it is known.
- **Regression test:** `test_revision_run_events_persist_and_resolve_on_real_db` creates the
  revision `workflow_runs` row exactly as the WS layer does (owner set, workspace UNSET),
  drives `_handle_revision` against an in-memory sqlite DB with the full schema, then asserts
  (1) the run row's workspace was stamped back, (2) an owner+workspace-scoped store (mirroring
  the `/events` endpoint's `ScopedStore(owner, workflow_run.workspace_id)`) resolves the run,
  and (3) the `pipeline_start`/`pipeline_complete` `run_events` rows persisted with the real
  workspace/owner and replay in monotonic `seq` order. This directly exercises the failure
  mode the offline harness missed.

**Human-verification flag:** the underlying issue was a real-DB persistence/scoping defect
(constraint + scope), not a subtle algorithmic logic bug; the new real-DB regression test
asserts the exact persist + 404-resolution behavior end to end, so no additional human
verification is required beyond the standard phase verifier. Noted for completeness: the
same owner_id/workspace_id are NOT written back onto the **main** pipeline `workflow_runs`
row either — that is a pre-existing, out-of-scope condition the review did not flag for the
revision-focused fix; left untouched.

### WR-01: stale `_RunEventSink.persist` docstring claimed a silent `debug` swallow

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** `ce1aa8a`
**Status:** fixed

**Applied fix:** updated the `_RunEventSink` class docstring to match the WR-02 contract: the
DB-write case (`SQLAlchemyError`) degrades to a `warning`; any other exception is treated as
a real bug and PROPAGATES (re-raised), not swallowed. The `seq`/`event_id` are still stamped
regardless so 0A parity holds. The parallel comments at engine.py:738-744 and 929-936 were
verified accurate (the review confirmed only the class docstring was stale).

## Tests

Ran with `python3.11` (no venv), tests under `backend/tests/`. All green:

- `tests/unit/test_revision_intelligence.py` — **10 passed** (includes the new
  `test_revision_run_events_persist_and_resolve_on_real_db` CR-01 regression test).
- `tests/unit/test_run_events.py` — 7 passed.
- `tests/unit/test_runs_api_events.py` — 7 passed.
- `tests/unit/test_runs_api_artifacts.py` — 5 passed.
- `tests/unit/test_artifact_store.py` — 8 passed.
- `tests/unit/test_execution_engine.py` — 9 passed.
- `tests/unit/test_resumability.py` — 7 passed.
- `tests/agents/test_characterization_prototype_revision.py` — 2 passed.
- `tests/agents/test_characterization_prototype.py` — 2 passed.
- `tests/agents/test_phase5_revision_validation.py` — 8 passed.
- `tests/agents/test_parent_run_ownership.py` — 13 passed.

Total across the touched-area suites: **78 passed**, 0 failed. The characterization +
revision-validation suites passing confirms the revision-path scoping change did not perturb
the deterministic non-revision event stream (parity / byte-identity invariant).

**Bug-reproduction confirmation:** a standalone check confirmed the pre-fix failure mode —
`ScopedStore(owner_id=..)` (workspace None) calling `append_event` against the real schema
raises `IntegrityError` (the NOT NULL violation the narrow-catch was masking). The fix
threads the real workspace so the insert succeeds.

## Carried-forward record — iteration 1 (informational)

Iteration 1 landed 8 commits (`fbc3e2f..f3cdd89`) for the 9 round-1 Critical+Warning findings
(CR-01, CR-02, WR-01..WR-07). The iteration-2 re-review independently VERIFIED 7 of those 9
as RESOLVED against the current code (round-1 CR-01, CR-02, WR-01, WR-02, WR-03, WR-04, WR-05,
WR-07). WR-06's round-1 fix was structurally present but defeated on a real DB — that is the
iteration-2 CR-01 fixed above.

Note on ID reuse: round-1 and round-2 reuse the IDs CR-01/WR-01 for DIFFERENT findings. The
IDs in this report's "Fixed Issues (iteration 2)" section refer to the **iteration-2** review
findings in `05-REVIEW.md`. The round-1 mapping (for traceability) was:

- round-1 CR-01 (multi-round clarifications all at version=1) — fbc3e2f
- round-1 CR-02 (owner_id can be None) — fbc3e2f
- round-1 WR-01 (graph vs store version divergence) — fbc3e2f
- round-1 WR-02 (best-effort swallow) — 336de3d / fbc3e2f / dac02e5
- round-1 WR-03 (unstable lineage order) — e956dc8
- round-1 WR-04 (lineage tree cycle crash) — 82d0afb
- round-1 WR-05 (restore re-arms all non-terminal) — a1492b6
- round-1 WR-06 (revision events bypass seq/persist) — f3cdd89 (superseded by iteration-2 CR-01)
- round-1 WR-07 (0014 backfill not idempotent) — 0e3359b

## Out of scope (not addressed — Info tier)

The 5 Info findings (IN-01..IN-05) remain open by design — `fix_scope` is critical_warning.
They are non-blocking and documented in `05-REVIEW.md`.

---

_Fixed: 2026-06-08_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
