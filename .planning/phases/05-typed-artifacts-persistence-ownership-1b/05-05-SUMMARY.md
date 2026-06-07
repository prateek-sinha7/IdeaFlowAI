---
phase: 05-typed-artifacts-persistence-ownership-1b
plan: 05
subsystem: api
tags: [fastapi, sqlalchemy, idor, lineage, durable-replay, ownership, deepagents]

# Dependency graph
requires:
  - phase: 05-03
    provides: ScopedStore default-deny helper (get_run / lineage / read_events / record_capabilities)
  - phase: 05-04
    provides: run_events seq sink + run_capabilities row (runtime=langchain_deepagents) populated by the engine
provides:
  - "GET /api/runs/{id}/artifacts — typed ArtifactRef lineage TREE (content excluded by default; ?include=content opt-in), owner-scoped"
  - "GET /api/runs/{id}/events?after=<seq> — run_events seq>after ascending, each with event_id (idempotent replay)"
  - "API-04 / API-05 endpoint test suites + CAPRUN-01 one-row capability test"
affects: [phase-09-diff-endpoint, phase-08-hitl, frontend-run-history]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Read endpoints route every owner check through the single default-deny ScopedStore (§19) — one enforced read path shared by engine + API"
    - "IDOR -> 404 (never 403): resolve run by owner filter, then re-resolve via ScopedStore.get_run; None -> 404"
    - "async def handler over sync ScopedStore coroutines, sharing the request Session via Depends(get_db)"
    - "In-memory lineage tree assembly (no recursive CTE) from a flat scoped ref list"

key-files:
  created:
    - backend/tests/unit/test_runs_api_artifacts.py
    - backend/tests/unit/test_runs_api_events.py
    - backend/tests/unit/test_run_capabilities.py
  modified:
    - backend/app/api/runs.py

key-decisions:
  - "Handlers are async def (not sync def): every ScopedStore method is a coroutine, so an await is required (plan D-08 discretion: choose sync def unless an await is required — it is)."
  - "Resolve the run by the owner filter first to obtain workspace_id, then construct ScopedStore(owner, workspace_id, session=db) and re-resolve via get_run (defense-in-depth single enforced read path)."
  - "after int-coercion handled by FastAPI's after: int = 0 query typing (non-int -> 422), so SQLi never reaches the parameterized ORM .filter()."
  - "Lineage tree edges restricted to ids present in THIS run's scoped set; a ref whose parent is outside the set surfaces as a root (nothing lost; cycles/dangling tolerated)."

patterns-established:
  - "Owner-scoped read endpoint: owner-filter resolve -> ScopedStore re-resolve -> 404 on None"
  - "Lineage TREE node shape: id/kind/producer_step/producer_agent/task_id/content_hash/version/visibility/retention/location/parents/derived_from/children[] (+content under ?include=content)"

requirements-completed: [API-04, API-05, CAPRUN-01, PERSIST-03, AUTHZ-02, AUTHZ-04]

# Metrics
duration: 7min
completed: 2026-06-07
---

# Phase 5 Plan 05: Owner-Scoped Artifact-Lineage + Durable-Replay Endpoints Summary

**Two owner-scoped read endpoints on /api/runs — a typed ArtifactRef lineage tree (`/artifacts`, content excluded by default) and an idempotent `seq>after` event replay (`/events`) — both routed through the single default-deny ScopedStore with cross-owner → 404, plus the CAPRUN-01 one-row `runtime=langchain_deepagents` proof.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-06-07T22:58:48Z
- **Completed:** 2026-06-07T23:05:27Z
- **Tasks:** 2
- **Files modified:** 4 (1 modified, 3 created)

## Accomplishments
- `GET /api/runs/{id}/artifacts`: assembles the run's `ArtifactRef` rows into a nested lineage TREE by walking `parents`/`derived_from` in memory; inline `content` excluded by default, opt-in via `?include=content` (D-10, T-5-CONTENT mitigation).
- `GET /api/runs/{id}/events?after=<seq>`: returns only `run_events` rows with `seq > after`, ascending, each carrying a unique `event_id` (API-05 idempotent replay); `after` int-coerced by FastAPI (ASVS V5).
- Both endpoints route every read through the single default-deny `ScopedStore` (§19) and surface cross-owner / missing runs as 404 (IDOR → 404, never 403) — mirroring the `runs.py` precedent.
- CAPRUN-01: a focused test driving `ScopedStore.record_capabilities` proves exactly one `run_capabilities` row per run with `runtime == "langchain_deepagents"` and the deferred forward columns present + nullable.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add GET /{id}/artifacts (lineage tree) + GET /{id}/events?after=<seq> with IDOR→404** - `f6168f8` (feat)
2. **Task 2: Wave 0 API + CAPRUN-01 tests** - `5d341e6` (test)

**Plan metadata:** (final docs commit — see below)

## Files Created/Modified
- `backend/app/api/runs.py` - Added `_build_lineage_tree` helper + two `async def` handlers (`get_run_artifacts`, `get_run_events`); both construct `ScopedStore` from the run's workspace and re-resolve via `get_run` for the 404 guard.
- `backend/tests/unit/test_runs_api_artifacts.py` - API-04: ≥2-node walkable tree (root A, child B `derived_from` A), content default-excluded / `?include=content`, empty-run tree, cross-owner 404, missing 404.
- `backend/tests/unit/test_runs_api_events.py` - API-05: `?after=k` → only `seq>k` ascending with `event_id`, full replay, idempotent re-replay, non-int `after` → 422, cross-owner 404, missing 404.
- `backend/tests/unit/test_run_capabilities.py` - CAPRUN-01: exactly one row, `runtime=langchain_deepagents`, deferred cols present/nullable, owner/workspace stamped.

## Decisions Made
- **`async def` over sync `def`:** the plan permitted either, defaulting to sync unless an `await` is required. Every `ScopedStore` method is a coroutine, so `await` IS required → handlers are `async def`. FastAPI mixes sync/async handlers freely.
- **Two-step owner resolution:** resolve the run by `WorkflowRun.user_id == current_user.id` first (to obtain `workspace_id` for the scoped store), then re-resolve through `ScopedStore.get_run` so the ownership boundary still lives in the single enforced read path (defense-in-depth, §19).
- **Tree edges scoped to the run's set:** a ref whose `derived_from`/`parents` point outside the scoped result becomes a root rather than being dropped — no artifact is lost and cycles/dangling ids are tolerated.

## Deviations from Plan

None - plan executed exactly as written. (The `async def` choice is an explicit plan-sanctioned discretion under D-08, not a deviation.)

## Issues Encountered
None.

## Threat Flags

None — no new security surface beyond the plan's `<threat_model>`. The two endpoints are exactly the `mitigate`-disposed surfaces (T-5-IDOR, T-5-SQLI, T-5-REPLAY, T-5-CONTENT); each mitigation is implemented and test-covered.

## Verification Evidence
- `cd backend && python3.11 -m pytest tests/unit/test_runs_api_artifacts.py tests/unit/test_runs_api_events.py tests/unit/test_run_capabilities.py -x` → 14 passed.
- `cd backend && python3.11 -m pytest tests/unit/ -q` → 462 passed, 8 failed (the 8 are the documented pre-existing environmental failures only: `test_logout.py` self-registration disabled, `test_pipeline_cancel.py` expired AWS Bedrock token — out of scope).
- `cd backend && python3.11 -m pytest tests/agents/ -q` → 480 passed, 19 skipped (characterization unaffected).
- `cd backend && lint-imports` → Contracts: 3 kept, 0 broken (exit 0).
- `python3.11 -c "from app.api.runs import router"` → imports clean, both `/artifacts` + `/events` routes registered.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The phase's API read surface is complete. Phase 9 owns the deferred `/diff` endpoint (intentionally NOT added here).
- The lineage-tree response shape and the `seq/event_id` event shape are now the contract the frontend run-history view and any replay consumer can build against.
- Migration 0015 (drop the thin `workflow_artifacts` table) remains sequenced LAST (plan 05-06) after read-cutover + parity green.

---
*Phase: 05-typed-artifacts-persistence-ownership-1b*
*Completed: 2026-06-07*

## Self-Check: PASSED
- All 4 source/test files present on disk.
- Both task commits (`f6168f8`, `5d341e6`) present in git history.
