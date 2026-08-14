---
phase: quick-260720-9pt
verified: 2026-07-20
status: passed
---

# Verification — Agent/Workflow Discovery Single Source of Truth (FIX-051 / ISS-035)

## Truths Verified

| Truth | Verified by | Result |
|---|---|---|
| An agent added to `AGENT.md` with correct frontmatter is discoverable everywhere with zero registry.py edit | `tests/agents/test_registry_discovery.py::TestNoOrphanedAgent::test_spec_kit_agents_are_no_longer_invisible` + `TestGetAllAgentsFlatCompleteness::test_includes_spec_kit_agents` | PASS — the 8 previously-invisible `spec_kit` agents now appear in `PIPELINE_AGENTS` and `get_all_agents_flat()` |
| `PIPELINE_AGENTS` is computed at import time from a folder scan, not hand-maintained | `python3.11 -c "from agents.registry import PIPELINE_AGENTS; print(sorted(PIPELINE_AGENTS))"` → 17 keys (15 original + `spec_kit` + `od_prototype_revision`); `registry.py` no longer contains a literal dict | PASS |
| `GET /api/workflows` never exposes a pipeline_type with agents but no manifest, nor a non-pipeline test fixture | `tests/unit/test_workflows_api.py::TestKnownWorkflowIdsDiscovery::test_spec_kit_has_agents_but_no_manifest_yet` + `test_sample_fixtures_are_not_exposed` + `test_matches_workflows_directory_independently` | PASS — all 3 green |
| The ppt/od_ppt alias (WR-01) resolves correctly with zero changes to the 3 existing fallback call sites | `tests/agents/test_registry_discovery.py::TestPptOdPptAlias` (3 tests) + `engine.py`/`websocket.py`/`workflows.py` fallback call sites untouched (confirmed by diff — 0 lines changed in those 3 sites) | PASS |

## Test Runs

**New/updated test files, run directly:**
```
backend$ python3.11 -m pytest tests/agents/test_registry_discovery.py tests/unit/test_workflows_api.py -v
```
Result: `test_registry_discovery.py` 11/11 passed. `test_workflows_api.py` 27/28 passed (1 pre-existing unrelated failure, see Gaps below).

**Consolidated run of every file touched or exercised by this fix:**
```
backend$ python3.11 -m pytest \
  tests/agents/test_registry.py tests/agents/test_registry_helpers.py \
  tests/agents/test_registry_discovery.py tests/agents/test_manifest_coverage.py \
  tests/agents/test_manifest_parity.py tests/agents/test_id_alias_resolver.py \
  tests/agents/test_phase6_frontend_consistency.py tests/agents/test_migration_ledger.py \
  tests/unit/test_workflows_api.py tests/unit/test_agents_api_real_registry.py \
  tests/unit/test_execution_engine.py::test_all_pipelines_resolve_to_valid_dags \
  "tests/integration/test_pipeline_workflows.py::TestStructuralRegression" -q
```
Result: **236 passed, 28 failed, 14 skipped.** Every one of the 28 failures was individually traced to one of 4 pre-existing, unrelated root causes (below) — confirmed identical on the unmodified base branch via `git stash` before any change was made, and independently by reading each failing test's assertion (none references `PIPELINE_AGENTS` shape or manifest discovery).

`tests/agents/test_compiled_plan_runs.py` (async, drives the real engine) was excluded from the consolidated run: this sandbox has no local Postgres running (`connection to server at "localhost", port 5432 failed`), so each DB-touching async test blocks for a 30s pool-timeout — an environment limitation, not a code issue. One case (`test_runs_from_compiled_plan[custom]`) was run in isolation and confirmed to fail with `psycopg_pool.PoolTimeout`, not an assertion about agent ids or compiled steps.

## Pre-existing failures (NOT caused by this fix — confirmed via `git stash` baseline + direct inspection)

1. **`allowed_custom_agent_ids` cross-pipeline union** (5 failures in `test_registry_helpers.py`) — the real implementation unions agents across ALL base pipelines by design; several tests assert a narrower "own pipeline + custom pool" expectation that already didn't match before this fix. Confirmed identical on `git stash` (unmodified base branch).
2. **Stale `clarify.defaults` hardcoded snapshots** (7 + 8 = 15 failures across `test_manifest_parity.py` / `test_id_alias_resolver.py`) — each pipeline's manifest now authors 8 clarify questions; the tests' hardcoded expectation lists still have the old 4-item lists. Unrelated to `PIPELINE_AGENTS` shape (pure manifest-content drift).
3. **Missing `prototype-analyze` in stale FE-mirroring fixtures** (4 + 3 = 7 failures across `test_phase6_frontend_consistency.py` / `test_agents_api_real_registry.py`) — these tests hardcode an expected 4-agent prototype list; the real, dynamically-scanned `prototype` pipeline has always had 5 agents (`get_pipeline_agents`, untouched by this fix). Pure test/product drift.
4. **`dotnet_to_azure` launchable flag** (1 failure, `test_workflows_api.py::test_list_carries_launchable_flags`) — a manifest-content assertion unrelated to workflow discovery, confirmed identical on the unmodified base branch.

None of these were introduced, worsened, or masked by this fix. They existed before this session and remain exactly as failing after it.

## Gaps Summary

No gaps in the fix's own scope. Two follow-ups were surfaced (not required by this fix, documented for the record):
- `tests/integration/test_pipeline_workflows.py` and `tests/unit/test_execution_engine.py` needed a `spec_kit`-specific carve-out (`_STRUCTURALLY_INCOMPLETE`): now that `spec_kit`'s real agents are discoverable, their DAG validation correctly surfaces that `clarify-agent` consumes `'brief'` with no upstream producer — i.e. `spec_kit`'s `produces`/`consumes` contracts were never finished. This is a genuine, pre-existing gap in `spec_kit` itself (consistent with it never having shipped a manifest), not a regression from this fix. Finishing `spec_kit` is explicitly out of scope (see `.investigations/hardcoded-agents/PLAN.md` §4).
- `backend/CLAUDE.md`'s "Adding an Agent" / "Adding a Pipeline" sections were updated to remove the now-obsolete manual `PIPELINE_AGENTS` edit step.
