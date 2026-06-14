---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
plan: 02
subsystem: api
tags: [capabilities, registry, fastapi, json-schema, palette, pydantic, typescript]

# Dependency graph
requires:
  - phase: 08-capability-registry
    provides: "@register/_TRUST/_KNOWN/discover seam + GET /api/capabilities palette projection (API-02)"
provides:
  - "Registry self-describes capability metadata via @register(description=, config_schema=) → _META (D-08 single source of truth)"
  - "CapabilityRegistry.describe(kind, name) accessor (lazy-discover, safe default)"
  - "GET /api/capabilities returns description + security_gated + populated config_schema per entry (additive, API-02 intact)"
  - "FE CapabilityEntry type carries description + security_gated + config_schema (the 22-05 palette data contract)"
affects: [22-05 embedded capability palette, 22-06 per-agent Advanced expander, SC-001 no-FE-hardcoded-metadata]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Capability self-description via @register kwargs → _META (mirrors the user_allowed=/_TRUST precedent)"
    - "Derived security_gated = not user_allowed (no second stored source, RESEARCH discretion A2)"

key-files:
  created: []
  modified:
    - backend/agents/capabilities/registry.py
    - backend/app/api/capabilities.py
    - backend/tests/unit/test_capabilities_api.py
    - frontend/src/lib/api.ts
    - "~45 capability impl modules (description=/config_schema= authored on @register)"

key-decisions:
  - "Metadata lives in the registry (@register → _META), projected by registry.describe — NO static map in the API layer (D-08, eroding SC-001 avoided)"
  - "security_gated is derived (not user_allowed), not a separate stored boolean (RESEARCH A2)"
  - "config_schema is JSON-Schema-lite, authored only on caps that take config; the rest legitimately stay {} (D-09)"

patterns-established:
  - "Pattern 1: A capability self-describes display metadata on its @register decorator; the API projects via a single describe() accessor"
  - "Pattern 2: Forward-compat config_schema is a per-capability JSON-Schema-lite object recorded in _META, not a hardcoded API-layer map"

requirements-completed: [SURF-02]

# Metrics
duration: ~22min
completed: 2026-06-14
---

# Phase 22 Plan 02: Capability Metadata Surfacing Summary

**`/api/capabilities` now supplies registry-sourced `description` + a derived `security_gated` flag + a populated per-capability `config_schema` (JSON-Schema-lite), additively over the API-02 contract — all self-described on each `@register` decorator (D-08), no static API-layer metadata map.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-06-14T20:07Z (approx)
- **Completed:** 2026-06-14
- **Tasks:** 2
- **Files modified:** 51 (4 core + ~47 capability impl modules carrying authored metadata)

## Accomplishments
- Extended the registry seam: `_META` sibling to `_TRUST`, `register()` gains `description=`/`config_schema=` kwargs, and a `describe(kind, name)` accessor (lazy-discover-guarded, safe `{"description": "", "config_schema": {}}` default).
- Authored a concise one-line `description` on every registered capability and a JSON-Schema-lite `config_schema` on the config-taking ones (security/validation gates; task_loop/fanout/wave strategies; code_lint/code_test/code_compile validators; single_file deliverable).
- Projected `description` + `security_gated` (derived `not user_allowed`) + populated `config_schema` through `GET /api/capabilities`, replacing the literal `{}` stub at capabilities.py:116 — additive, with the `Depends(get_current_user)` auth gate and all existing keys preserved.
- Extended the contract test (12 passed) and the FE `CapabilityEntry` type (the 22-05 palette data contract).

## Task Commits

Each task was committed atomically:

1. **Task 1: Registry `_META` + `describe()` + authored capability metadata** - `3c74cd0d` (feat)
2. **Task 2: Project description + security_gated + config_schema through the API + extend test + FE type** - `17a95345` (feat)

**Plan metadata:** _(this docs commit)_

_Note: project-level `tdd_mode: false`; Task 1's verify is an inline `describe` smoke check and the registry `describe()` is fully exercised by the Task 2 contract test, so no separate RED/GREEN registry-test split was authored._

## Files Created/Modified
- `backend/agents/capabilities/registry.py` - `_META` dict; `register()` gains `description=`/`config_schema=`; `describe()` accessor.
- `backend/app/api/capabilities.py` - `CapabilityEntry` gains `description` + `security_gated`; loop projects `registry.describe(...)` (stub removed).
- `backend/tests/unit/test_capabilities_api.py` - asserts description + security_gated + config_schema per entry, derived-flag invariant, populated-schema (security gate), auth + existing keys.
- `frontend/src/lib/api.ts` - `CapabilityEntry` interface gains `description: string` + `security_gated: boolean`.
- ~45 capability impl modules (strategies, gates, tools, validators, merge, deliverables, context_providers, task_parsers, compaction, post_steps, runtimes, prompt, repo_inventory, context_pack, skills, hooks, mcp_servers, integration_providers, runtime_env/local, repo_index/tree_sitter) - authored `description=`/`config_schema=` on `@register`.

## Decisions Made
- Metadata is registry-owned and projected via `describe` — no static `CAPABILITY_META` map in the API layer (D-08; verified `grep CAPABILITY_META|CAP_META backend/app/api/` → 0).
- `security_gated` derived from `user_allowed` rather than stored separately (RESEARCH A2; test pins `security_gated == not user_allowed` for every entry).
- `config_schema` authored only where a capability genuinely takes config; the majority legitimately keep `{}` (D-09).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `frontend npx tsc --noEmit` reports exactly 2 errors, both pre-existing `TS2352` const-assertion casts in `frontend/e2e/fixtures/mockApi.ts:95-96` (the fixtures cast to `unknown[]`, bypassing `CapabilityEntry`, so they are unaffected by this plan's type extension). Documented in this phase's `deferred-items.md`; `src/` is clean. Resolution: out of scope (SCOPE BOUNDARY).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The `/api/capabilities` payload now carries the full per-entry metadata (`description` + `security_gated` + `config_schema`) the 22-05 embedded palette and 22-06 per-agent Advanced expander render from — entirely registry-driven (SC-001: a newly `@register`'d cap appears with metadata, no FE/API edit).
- Verification gates green: `test_capabilities_api.py` 12/12; `lint-imports` 4 kept / 0 broken; banned-patterns (SC-001) 11/11; registry+cutover+parity suite 89/89.
- No new migrations; backend-additive + FE-type-only; API-02 contract preserved.

## Self-Check: PASSED

- FOUND: backend/agents/capabilities/registry.py
- FOUND: backend/app/api/capabilities.py
- FOUND: backend/tests/unit/test_capabilities_api.py
- FOUND: frontend/src/lib/api.ts
- FOUND commit: 3c74cd0d (Task 1)
- FOUND commit: 17a95345 (Task 2)

---
*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime*
*Completed: 2026-06-14*
