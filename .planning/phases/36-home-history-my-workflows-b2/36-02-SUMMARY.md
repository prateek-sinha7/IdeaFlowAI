---
phase: 36-home-history-my-workflows-b2
plan: 02
subsystem: api
tags: [fastapi, pydantic, runs, run-summary, idor, owner-scoped, additive]

# Dependency graph
requires:
  - phase: 04-05 (runs router relocation)
    provides: "/api/runs router + WorkflowRun.user_id IDOR-404 filter idiom"
  - phase: Workstream A (revision-family read surface)
    provides: "_compute_root_ids owned-ancestor walk + get_run_family owned BFS + FamilyMemberResponse + _owner_gate_or_404"
provides:
  - "GET /api/runs/{id}/summary — additive read-only owner-scoped run aggregation (SHELL-03 backend half)"
  - "RunSummaryResponse model (existing columns + family walk; zero invented fields)"
  - "_owned_family_members helper shared by /summary and /family (extracted; no dual impl)"
  - "test_runs_api_summary.py — owner-gate 200/404/404 + malformed-JSON fallback + family-timeline"
affects: [36-04 (RunDetailPage + getRunSummary client — the SHELL-03 FE half)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive read-only aggregation endpoint over existing columns — zero tables/migrations, goldens untouched by construction (INV-3)"
    - "Summary-safe field projection: identity+KPI keys only, raw agent content never echoed (V7 leak guard)"
    - "Shared owned-family BFS helper reused by two endpoints (INV-12 no dual impl)"

key-files:
  created:
    - backend/tests/unit/test_runs_api_summary.py
  modified:
    - backend/app/api/runs.py

key-decisions:
  - "Extract _owned_family_members from get_run_family so /summary reuses the SAME owned BFS instead of duplicating the walk (INV-12); family parity 8/8 green after the refactor"
  - "Per-agent breakdown projects a fixed allow-list (_SUMMARY_SAFE_AGENT_KEYS) — raw output/input_prompt/thinking_text/tool_calls dropped so no secret-bearing bytes leak (V7)"
  - "SHELL-03 left Pending, not marked complete: this plan delivers only the backend endpoint; the RunDetailPage + getRunSummary FE half is 36-04"

patterns-established:
  - "Read-only run-detail aggregation: _owner_gate_or_404 -> tolerant json.loads(try/except -> []/{}) -> safe projection -> reuse family walk"

requirements-completed: []  # SHELL-03 is only HALF-delivered here (backend endpoint); FE page is 36-04 — intentionally NOT marked complete

# Metrics
duration: 20min
completed: 2026-07-09
---

# Phase 36 Plan 02: Owner-scoped Run-Summary Endpoint Summary

**Additive read-only `GET /api/runs/{id}/summary` that aggregates existing WorkflowRun columns + the owned revision-family walk into a single Run-detail payload — owner-gated on `user_id` (IDOR→404), inventing zero fields and adding zero tables/migrations.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-09T04:11Z (approx)
- **Completed:** 2026-07-09T04:19Z
- **Tasks:** 2
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- `get_run_summary` + `RunSummaryResponse` added to `backend/app/api/runs.py`: KPI stats (`duration` + `agent_count` + `token_usage`), failure banner (`status` + `error`), per-agent breakdown (`agent_outputs`, safe-projected), and the version/revision timeline (`root_id` + `members`).
- Owner-scoped via the shared `_owner_gate_or_404(db, workflow_id, current_user.id)` on `WorkflowRun.user_id` (NEVER the nullable `owner_id`): cross-owner + missing → 404, never 403, never a 200 with foreign data.
- DoS guard: `agent_outputs` and `token_usage` are each `json.loads`-parsed inside a try/except with `[]`/`{}` fallback (also rejects well-formed-but-wrong-shape JSON) — a malformed blob degrades to an empty aggregate, never a 500.
- Leak guard (V7): the per-agent projection surfaces only `_SUMMARY_SAFE_AGENT_KEYS` (agent_id/name/role/icon/duration/error + token counts); raw `output`/`input_prompt`/`thinking_text`/`tool_calls` are dropped and test-proven absent from the response body.
- Extracted `_owned_family_members` so `/summary` and `/family` share one owned BFS-down walk (INV-12 no dual impl); `get_run_family` was refactored to call it with byte-for-byte behavior parity (8/8 family tests still green).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add GET /{id}/summary — owner-scoped aggregation over existing columns** - `3be49bfa` (feat)
2. **Task 2: test_runs_api_summary.py — owner-gate 200/404/404 + aggregation shape** - `c7706f45` (test)

**Plan metadata:** (this SUMMARY + STATE + ROADMAP) — see final docs commit.

## Files Created/Modified
- `backend/app/api/runs.py` — added `RunSummaryResponse`, `get_run_summary` route, `_SUMMARY_SAFE_AGENT_KEYS`, and the extracted `_owned_family_members` helper; refactored `get_run_family` to reuse it.
- `backend/tests/unit/test_runs_api_summary.py` — new 8-test suite (owner 200 / cross-owner 404 / missing 404 / malformed + wrong-shape JSON fallback / raw-content-never-echoed / revision-family timeline / foreign-parent no-leak).

### RunSummaryResponse field → existing-source map (zero invented fields)

| Field | Source |
|-------|--------|
| `id` | `WorkflowRun.id` column |
| `title` | `WorkflowRun.title` column |
| `type` | `WorkflowRun.type` column |
| `status` | `WorkflowRun.status` column |
| `duration` | `WorkflowRun.duration` column |
| `agent_count` | `WorkflowRun.agent_count` column |
| `token_usage` | parsed `WorkflowRun.token_usage` column (JSON dict, `{}` fallback) |
| `error` | `WorkflowRun.error` column |
| `agents` | parsed `WorkflowRun.agent_outputs` column (JSON array, `[]` fallback), projected to `_SUMMARY_SAFE_AGENT_KEYS` |
| `root_id` | `_compute_root_ids` owned-ancestor walk |
| `members` | `_owned_family_members` owned BFS (reuses `FamilyMemberResponse`) |

## Decisions Made
- Extracted the family BFS into `_owned_family_members` rather than copy-pasting it into `/summary` — the plan explicitly forbids gratuitous duplication and INV-12 forbids dual implementations; the shared helper keeps `/family` and `/summary` in lockstep.
- Placed `RunSummaryResponse` after `FamilyMemberResponse`/`RunFamilyResponse` (not literally beside `WorkflowRunResponse`) because it reuses `FamilyMemberResponse`, which must be defined first — a Python definition-order requirement, not a scope change.
- Did NOT mark SHELL-03 complete: the requirement spans a run-detail page + endpoint; only the endpoint ships here, so marking it done would misreport. The FE half is 36-04.

## Deviations from Plan

**1. [Refactor — no dual impl] Extracted `_owned_family_members` and repointed `get_run_family`**
- **Found during:** Task 1 (building the version/revision timeline)
- **Issue:** The plan mandates reusing the family walk "do NOT duplicate the walk logic gratuitously; call/extract from the existing pattern" — inlining a second copy into `/summary` would violate INV-12/INV-3 (no dual impl).
- **Fix:** Lifted the BFS-down + ordering + `FamilyMemberResponse` construction out of `get_run_family` into a module-level `_owned_family_members(db, user_id, root_id)` helper; both endpoints now call it.
- **Files modified:** backend/app/api/runs.py
- **Verification:** `test_runs_api_family.py` 8/8 green (behavior parity after the refactor); `test_runs_api_summary.py` 8/8 green.
- **Committed in:** `3be49bfa` (Task 1 commit)

---

**Total deviations:** 1 (sanctioned extraction to satisfy the plan's explicit "do not duplicate" instruction + INV-12).
**Impact on plan:** Within `runs.py`, behavior-preserving, tightens the codebase. No scope creep; git diff remains exactly `runs.py` + the new test.

## Issues Encountered
- The GSD state handlers `state.record-metric` / `state.record-session` are inert against this repo's non-standard STATE.md format (known quirk). The Current Position + Last activity prose and the progress bar (92%) were updated instead; the metric/session tables were left as the handlers found them.

## Threat surface scan
No new security surface beyond the plan's `<threat_model>`. The endpoint adds a single read-only route behind the existing `_owner_gate_or_404`; all four mitigations (IDOR→404, DoS json fallback, leak projection, INV-3 read-only) are implemented and test-covered.

## Known Stubs
None — every response field is wired to a real WorkflowRun column or the live family walk. No placeholders, no empty-value flows.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The `GET /api/runs/{id}/summary` contract (fields + owner-scope + fallback shapes) is stable and test-pinned; 36-04 can build `RunDetailPage` + the `getRunSummary` client against it.
- SHELL-03 remains Pending until 36-04 lands the FE half.

---
*Phase: 36-home-history-my-workflows-b2*
*Completed: 2026-07-09*
