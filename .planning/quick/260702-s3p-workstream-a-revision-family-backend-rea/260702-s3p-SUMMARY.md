---
phase: quick-260702-s3p
plan: 01
subsystem: backend-api
tags: [revision-family, idor, read-surface, app-layer]
requires:
  - WorkflowRun.parent_run_id (self-FK, migration 0013) — the sole lineage column
  - agents.authz.ScopedStore.lineage — the owner+workspace-scoped ArtifactRef read
provides:
  - GET /api/runs/{id}/family — owner-scoped revision family (root + owned descendants)
  - WorkflowRunResponse.parent_run_id + root_run_id on list AND get
  - GET /api/runs/{id}/artifacts?kind=X — exact-kind pre-tree filter
  - _resolve_owned_parent_run_id — ownership-checked parent linkage at both WS ingress sites
affects:
  - Workstream B (FE revision families) consumes root_run_id + /family next
  - Workstream C (FE run-inputs) consumes ?kind=clarifications&include=content next
tech-stack:
  added: []
  patterns:
    - memoized in-Python owned-ancestor walk with batched parent fetches (CTE-free, SQLite+Postgres portable)
    - _run_response injects a server-computed required field over Pydantic from_attributes
key-files:
  created:
    - backend/tests/unit/test_ws_parent_link_ownership.py
    - backend/tests/unit/test_runs_api_family.py
  modified:
    - backend/app/api/websocket.py
    - backend/app/api/runs.py
    - backend/tests/unit/test_runs_api_artifacts.py
decisions:
  - D-06 — parent linkage + every family/root walk step keys on WorkflowRun.user_id, never the nullable backfilled owner_id
  - D-07 — root_run_id is server-computed (last owned ancestor), not an ORM column
  - D-2 — revision_index is chronological (created_at ASC), id tiebreak for SQLite determinism
  - D-8 — kind filter is exact in-Python equality applied before tree-building (no SQL, no LIKE)
metrics:
  duration: ~18 min
  completed: 2026-07-02
---

# Quick 260702-s3p: Workstream A — Revision-Family Backend Read Surface Summary

Ownership-hardened both WS parent-link ingress sites and exposed the revision-family read surface (`parent_run_id` + server-computed `root_run_id`, a new owner-scoped `/family` endpoint, and a `?kind=` artifacts filter) — app-layer only, zero engine edits, zero migrations.

## What Was Built

**Task 1 — IDOR fix at both ingress sites (`websocket.py`).** New module helper `_resolve_owned_parent_run_id(db, candidate_id, user_id)` links `parent_run_id` only when the candidate row exists AND `WorkflowRun.user_id == user_id` (D-06). Site 1 (`_handle_workflow_execution`) routes `source_workflow_run_id` through it with `user.id` — the primary `run_pipeline` IDOR path. Site 2 (`_handle_revision_execution`) conditions only the persisted ROW column; the engine still receives `parent_run_id` verbatim, so revision dispatch behavior is unchanged (engine `assert_owns` stays the content gate). A falsy candidate issues no query.

**Task 2 — family read surface (`runs.py`).** `WorkflowRunResponse` gains `parent_run_id` (verbatim column) and `root_run_id` (required, server-computed). `_compute_root_ids` is a memoized in-Python owned-ancestor walk with batched parent fetches (chosen over a recursive CTE for SQLite+Postgres portability): a NULL-parent page issues zero extra queries; a foreign/missing parent terminates the walk (root = last owned ancestor); a per-walk visited set guards cycles. `_run_response` injects the computed `root_run_id` over `from_attributes` by iterating `model_fields` (auto-tracks future field additions). New `GET /{workflow_id}/family` is owner-scoped at every step (entry resolve, root walk, BFS-over-owned-children), returns `{root_id, members[]}` ordered `(created_at ASC, id ASC)` with 1-based `revision_index`; the root member's out-of-family parent pointer is nulled so no foreign id leaks; cross-owner/missing → 404 (never 403).

**Task 3 — kind filter (`runs.py`).** `GET /{workflow_id}/artifacts` gains `kind: Optional[str]`; refs are filtered by exact in-Python equality BEFORE `_build_lineage_tree` (value never reaches SQL). A filtered-out parent drops its edge so a surviving child surfaces as a root; composes with `include=content`; unknown kind → empty list (not 422); no param → byte-identical prior behavior.

## Deviations from Plan

None — plan executed exactly as written. One in-development iteration inside Task 2 (not a plan deviation): the initial `_root_of` walk stepped INTO the foreign node before terminating, resolving a foreign-parent chain's root to the foreign id. Fixed before commit by terminating when the parent id itself resolves to the foreign/missing sentinel (root = last OWNED ancestor). The foreign-parent-termination test caught it in the RED-before-GREEN cycle.

## Hard Gate Battery (POR §4 Gates)

| Gate | Result |
|------|--------|
| Touched unit suites (artifacts, family, runs_api, ws_parent_link_ownership, run_revision_ws_dispatch, runs_api_events) | **52 passed** |
| Task 1 suite (ws_parent_link_ownership + run_revision_ws_dispatch) | 18 passed |
| Task 2 suite (runs_api_family + runs_api) | 19 passed |
| Characterization goldens (5, `SNAPSHOT_UPDATE` unset) | **9 passed, 1 failed** — the failure is exactly the KNOWN pre-existing baseline `test_characterization_od_ppt::test_od_ppt_event_snapshot` (local skills example.html event drift); every OTHER golden byte/event-identical (INV-3 held) |
| `/opt/homebrew/bin/lint-imports` | **4 kept / 0 broken** |
| Scope fence (`git status --porcelain` + full-plan `git diff`) | Clean — only `backend/app/api/` + `backend/tests/unit/`; zero `backend/agents/`, zero migrations, zero frontend, zero new WS event types, zero `source_run_id` references |

## Commits

- `45552896` — fix(api): ownership-harden both parent-link ingress sites (IDOR, POR §3)
- `d9d1399c` — feat(api): parent_run_id + root_run_id fields and GET /api/runs/{id}/family
- `798aa4b2` — feat(api): kind filter on GET /api/runs/{id}/artifacts (D-8)

## Notes for Workstream B / C

- FE consumes `root_run_id` (plain field, group history rows by it) and `/family` (version timeline) — Workstream B.
- FE reopen of clarifications uses `GET /api/runs/{id}/artifacts?kind=clarifications&include=content` — Workstream C.
- `parent_run_id` is exposed verbatim on list/get (POR §4.2 contract); in the `/family` response only, an out-of-family (foreign/missing) parent pointer is nulled to prevent metadata leakage.

## Self-Check: PASSED

- FOUND: backend/app/api/websocket.py (`_resolve_owned_parent_run_id`)
- FOUND: backend/app/api/runs.py (`get_run_family`, `_compute_root_ids`, `root_run_id`)
- FOUND: backend/tests/unit/test_ws_parent_link_ownership.py
- FOUND: backend/tests/unit/test_runs_api_family.py
- FOUND: backend/tests/unit/test_runs_api_artifacts.py (`TestKindFilter`)
- FOUND commit: 45552896, d9d1399c, 798aa4b2
