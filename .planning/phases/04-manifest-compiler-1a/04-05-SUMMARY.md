---
phase: 04-manifest-compiler-1a
plan: 05
subsystem: api
tags: [fastapi, pydantic, manifests, workflow-compiler, idor, run-history]

# Dependency graph
requires:
  - phase: 04-manifest-compiler-1a (04-02)
    provides: plan.py dataclasses (CompiledWorkflow, Step, DeliverableSpec, ClarifySpec) + manifest.py loader
  - phase: 04-manifest-compiler-1a (04-03)
    provides: WorkflowCompiler.compile + the 15 authored manifests
  - phase: 04-manifest-compiler-1a (04-04)
    provides: compile_for_run(pipeline_type) run-entry seam + resolve_alias
provides:
  - "GET /api/workflows — manifest-derived workflow definitions (list + {id} detail, 404 on unknown)"
  - "GET/DELETE/POST /api/runs — relocated run-history CRUD (list, get, chain-context, delete, export-pptx)"
  - "Established /api/runs as the run-history sub-resource home for Phase 5 (artifacts/events)"
affects: [phase-5-artifacts-events, dynamic-workflow-composer, frontend-run-history]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Definitions router derives all metadata from compile_for_run + get_pipeline_agents (no DB query)"
    - "Path param resolved against an in-memory closed allow-list (PIPELINE_AGENTS keys) — never a filesystem read on an unvalidated id"
    - "Pure-relocation of routes with ownership filter + filename sanitization carried over verbatim"

key-files:
  created:
    - backend/app/api/runs.py
    - backend/tests/unit/test_runs_api.py
    - backend/tests/unit/test_workflows_api.py
  modified:
    - backend/app/api/workflows.py
    - backend/app/main.py
    - frontend/src/lib/api.ts
    - frontend/src/components/results/FilesTab.tsx
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/preview/PPTPreview.tsx

key-decisions:
  - "Workflow display name derived from the manifest id (title-cased); description is a generated step-summary — manifests stay pure data (INV-5), no presentation strings added"
  - "GET /api/workflows lists all 15 PIPELINE_AGENTS keys (od_prototype is an alias, not a key, so excluded from the list); {id} accepts any known key incl. aliases via compile_for_run"
  - "Clean break with no 308/redirect aliases — RESEARCH D-02 confirmed JWT-only, no external API-key consumer"

patterns-established:
  - "Manifest-definitions controller: read-only projection of CompiledWorkflow over the registry, zero DB coupling"
  - "Closed-allow-list path-param resolution for traversal-proof {id} lookups"

requirements-completed: [API-01]

# Metrics
duration: 10min
completed: 2026-06-07
---

# Phase 04 Plan 05: Reclaim /api/workflows + relocate run-history to /api/runs Summary

**`/api/workflows` now serves manifest-derived workflow definitions (list + full compiled step configs, 404 on unknown id) while all run-history CRUD moved verbatim to `/api/runs` with the IDOR ownership filter and export-pptx filename sanitization preserved, and the 10 frontend refs repointed atomically.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-07T16:49:58Z
- **Completed:** 2026-06-07T17:00:21Z
- **Tasks:** 3
- **Files modified:** 9 (3 created, 6 modified)

## Accomplishments
- `GET /api/workflows` lists every authored workflow (all 15 `PIPELINE_AGENTS` ids) with manifest-derived metadata (id, name, description, step summary); `GET /api/workflows/{id}` returns the full compiled step configs (strategy, gates, validators, task_source, deliverable, clarify, context_providers) with 404 on an unknown id — the `prototype` payload matches its manifest exactly.
- All five run-history routes relocated to a new `/api/runs` router (`GET /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/chain-context`, `DELETE /api/runs/{id}`, `POST /api/runs/export-pptx`) with the per-user `user_id == current_user.id` ownership filter preserved on every query and the export-pptx `re.sub` filename sanitization carried over verbatim.
- 10 frontend refs repointed from `/api/workflows*` to `/api/runs*` atomically (clean break, no aliases); both routers mounted in `main.py`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Relocate run-history CRUD to /api/runs, mount in main.py (D-02)** - `496eb43` (feat)
2. **Task 2: Rewrite /api/workflows as the manifest-definitions router (API-01/D-01)** - `e263339` (feat)
3. **Task 3: Repoint the 10 frontend refs to /api/runs (D-02 atomic cutover)** - `53aba9a` (feat)

## Files Created/Modified
- `backend/app/api/runs.py` - NEW `APIRouter(prefix="/api/runs")` housing the relocated run-history CRUD (JWT-only, ownership-filtered, verbatim export sanitization)
- `backend/app/api/workflows.py` - REWRITTEN as the manifest-definitions router (list + {id}, derived from compiled manifests; no DB query)
- `backend/app/main.py` - mount `runs_router` alongside `workflows_router`
- `backend/tests/unit/test_runs_api.py` - relocated-shapes + IDOR (cross-user 404) + export-pptx sanitization (11 tests)
- `backend/tests/unit/test_workflows_api.py` - list-all-15 + prototype-matches-manifest + 404 + per-id compile + traversal 404 (7 tests)
- `frontend/src/lib/api.ts` - list/get/chain-context/delete repointed to `/api/runs` (4 refs)
- `frontend/src/components/results/FilesTab.tsx`, `.../preview/PreviewPanel.tsx`, `.../preview/PPTPreview.tsx` - PPT-list + export-pptx repointed to `/api/runs` (6 refs)

## Decisions Made
- **Name/description derivation:** the manifest carries no presentation strings (INV-5), so the workflow `name` is the title-cased id and `description` is a generated step summary. This keeps the data layer pure while giving the composer usable metadata.
- **List = the 15 `PIPELINE_AGENTS` keys:** `od_prototype` is an id-alias (resolved by `compile_for_run`), not a registry key, so it is reachable via `GET /api/workflows/{id}` but not listed (no duplicate `prototype` entry).
- **No legacy aliases:** clean break per RESEARCH D-02 (JWT-only surface, no external API-key consumer).

## Deviations from Plan

None - plan executed exactly as written.

(One test-assertion correction during Task 1: the export-pptx sanitization test initially asserted the literal word "Set-Cookie" was absent from the Content-Disposition header. The sanitizer correctly strips the header-injection vector — CR/LF and `:` — but leaves the inert word "Set-Cookie" as filename text. The assertion was tightened to check for the actual injection characters (CR/LF, `:`, `"`) rather than the harmless word. This was a fix to the new test only, not to the security code, which carries over verbatim.)

## Issues Encountered
None.

## Threat Model Compliance
- **T-04-12 (IDOR / ASVS V4):** ownership filter preserved on all 6 run-reading query paths in `runs.py` (`grep -c "user_id == current_user.id"` = 6); cross-user GET/DELETE/chain-context return 404, asserted by `test_runs_api.py`.
- **T-04-13 (path traversal / ASVS V5):** `{id}` resolved against the in-memory `_KNOWN_WORKFLOW_IDS` (PIPELINE_AGENTS keys); unknown/traversal id -> 404; no `open(` and no filesystem read on an unvalidated id, asserted by `test_workflows_api.py`.
- **T-04-14 (HTTP response splitting):** export-pptx filename `re.sub(r"[^A-Za-z0-9._-]", "_", title)[:40]` carried over verbatim; asserted by `test_export_pptx_filename_is_sanitized`.
- **T-04-15 (auth weakening):** both routers keep `Depends(get_current_user)`; API-key surface untouched.

## Verification
- `pytest tests/unit/test_workflows_api.py tests/unit/test_runs_api.py` — 18 passed.
- `pytest tests/unit/ --ignore=test_logout.py --ignore=test_pipeline_cancel.py` — 417 passed (the 8 logout/cancel failures are pre-existing, logged in deferred-items.md).
- `pytest tests/agents/` — 467 passed, 19 skipped (no regression).
- `lint-imports` — 1 contract kept, 0 broken.
- Frontend repoint grep — 0 `/api/workflows` refs remain in the 4 files; 10 `/api/runs` refs present.
- App boots: `/api/workflows`, `/api/workflows/{workflow_id}` (definitions) + `/api/runs`, `/api/runs/export-pptx`, `/api/runs/{workflow_id}`, `/api/runs/{workflow_id}/chain-context` (run-history) all registered.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `/api/runs` is established as the run-history sub-resource home; Phase 5 can land `/api/runs/{id}/artifacts|events` there directly.
- The dynamic composer can now read available workflows from `GET /api/workflows` instead of a hardcoded type list (API-01 satisfied).

## Self-Check: PASSED

- Created files verified on disk: `runs.py`, `test_runs_api.py`, `test_workflows_api.py`, `04-05-SUMMARY.md`.
- Task commits verified in git log: `496eb43`, `e263339`, `53aba9a`.

---
*Phase: 04-manifest-compiler-1a*
*Completed: 2026-06-07*
