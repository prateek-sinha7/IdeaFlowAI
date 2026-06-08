---
phase: 06-model-policy-1c
plan: 02
subsystem: agents
tags: [loader, agent-spec, model-policy, frontmatter, tdd]

# Dependency graph
requires:
  - phase: 06-01
    provides: ModelCatalog single source of truth (model_catalog.py) — referenced by the resolver in 06-03, not imported by the loader here
provides:
  - "AgentSpec.model: str | None field (tier-3 agent-default backing for the model resolver, MODEL-01)"
  - "Loader parse of the optional AGENT.md `model:` frontmatter field with a string-or-null type guard"
affects: [06-03, model-resolver, resolver]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Optional frontmatter field via the per-field type-guard template (mirrors the description/gate guards)"
    - "Load-time type guard only; catalog-membership validation deferred to RESOLVE time to keep the loader catalog-free"

key-files:
  created: []
  modified:
    - backend/agents/loader.py
    - backend/tests/agents/test_loader.py

key-decisions:
  - "Validation split (D-09): loader enforces only the type guard (str-or-null); catalog-membership validation is deferred to the resolver (06-03) so the loader gains no catalog import and the all-agents schema test is unaffected by catalog contents"
  - "Fully additive: model defaults to None; no existing AGENT.md declares it, so all ~80 agents load unchanged"

patterns-established:
  - "Optional model field follows the established 3-step add (dataclass field + _build_spec type-guard parse + constructor pass-through)"

requirements-completed: [MODEL-01]

# Metrics
duration: 5min
completed: 2026-06-08
---

# Phase 06 Plan 02: AgentSpec.model Field Summary

**Optional `model: str | None` frontmatter field on AgentSpec, parsed by the loader with a string-or-null type guard — the tier-3 agent-default backing for the model resolver (MODEL-01), fully additive across all ~80 existing agents.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-08T15:01:08Z
- **Completed:** 2026-06-08T15:06:07Z
- **Tasks:** 1 (TDD)
- **Files modified:** 2

## Accomplishments
- Added `AgentSpec.model: str | None = None` (D-09) — the agent-default tier the resolver reads in 06-03.
- Added the `_build_spec` parse block: `metadata.get("model")` with a string-or-null type guard raising `AgentSpecError` on a non-string value, mirroring the existing `description`/`gate` guards.
- Passed `model=model` through the `AgentSpec(...)` constructor call.
- Loader stays catalog-decoupled: no import of `model_catalog.py`; catalog-membership validation is deferred to RESOLVE time (06-03). `lint-imports` stays 3-kept / 0-broken.
- All ~80 existing AGENT.md files still parse (absent → None); the all-agents schema test stays green.

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1 (RED): failing tests for optional `model` field** - `6d9ab39` (test)
2. **Task 1 (GREEN): AgentSpec.model field + loader parse** - `1bf45f4` (feat)

No REFACTOR commit — the implementation directly reuses the established per-field guard template, so no cleanup was warranted.

**Plan metadata:** see final docs commit.

## Files Created/Modified
- `backend/agents/loader.py` - Added `AgentSpec.model: str | None = None` (after `injects`) and the `model` type-guard parse in `_build_spec`, with `model=model` passed to the constructor.
- `backend/tests/agents/test_loader.py` - Added `TestLoadAgentSpecModel` (test_model_field_parses, test_model_absent_is_none, test_model_invalid_type_raises).

## Decisions Made
- **Validation is load-time type-guard only (D-09, plan choice).** The loader enforces that a present `model` value is a string (else `AgentSpecError`), but does NOT validate it against `ModelCatalog.ids()`. Catalog-membership validation is the resolver's job at RESOLVE time (06-03). This keeps the loader free of any catalog import and means the all-agents schema test is unaffected by catalog contents.
- **Fully additive.** `model` defaults to `None`; no AGENT.md declares it today, so every existing agent loads identically.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None during the planned work. The broad `tests/agents/ tests/unit/` regression run surfaced 9 pre-existing, out-of-scope failures in `tests/unit/test_logout.py` (self-registration disabled → HTTP 403) and `tests/unit/test_pipeline_cancel.py` (async/expired-token, environmental). These were already documented in 06-01's deferred-items and reproduced unchanged here; neither suite imports the loader. Logged to `deferred-items.md` (06-02 section), not fixed (scope boundary). The targeted `tests/agents/test_loader.py` suite is 44/44 green.

## Verification
- `cd backend && python3.11 -m pytest tests/agents/test_loader.py -x -q` → **44 passed** (3 new model cases + the all-agents schema test).
- `grep -n "model: str | None" backend/agents/loader.py` → field (L108) and parse local (L374) present.
- `lint-imports` → **3 kept / 0 broken** (loader gained no forbidden/catalog import).

## Known Stubs
None. `AgentSpec.model` defaulting to `None` when absent is the intended additive default (D-09), not a stub — it is the documented tier-3 fallback the resolver consumes in 06-03, not placeholder data flowing to a UI.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `AgentSpec.model` is now available as the agent-default tier for the model resolver (06-03), which will validate it against `ModelCatalog.ids()` (the allow-list, Q2) at resolve time.
- No blockers.

## Self-Check: PASSED

- FOUND: backend/agents/loader.py
- FOUND: backend/tests/agents/test_loader.py
- FOUND: .planning/phases/06-model-policy-1c/06-02-SUMMARY.md
- FOUND commit: 6d9ab39 (test RED)
- FOUND commit: 1bf45f4 (feat GREEN)

---
*Phase: 06-model-policy-1c*
*Completed: 2026-06-08*
