---
phase: 06-model-policy-1c
plan: 01
subsystem: api
tags: [model-catalog, capability-registry, settings, inv-12, kernel-purity, model-policy]

# Dependency graph
requires:
  - phase: 04-capability-registry
    provides: "CapabilityRegistry._KNOWN name-only membership pattern (D-07) + import-linter contract for agents.capabilities"
provides:
  - "ModelCatalog kernel-pure data capability — the single authoritative model-id + metadata list (MODEL-04)"
  - "('model_catalog','default') discoverable via CapabilityRegistry.is_registered"
  - "AVAILABLE_MODELS + _VALID_MODEL_IDS as derived projections over the catalog (INV-12 single source)"
affects: [06-02-loader, 06-03-resolver, 06-04-override-validator, model-policy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Kernel-pure data capability (frozen dataclass records + read-only accessor), no Protocol/base.py port"
    - "INV-12 single-source projection: web-layer constants derived from a kernel catalog, not hand-maintained"
    - "Name-only capability membership in registry._KNOWN (no instance/@register/trust until Phase 8)"

key-files:
  created:
    - backend/agents/capabilities/model_catalog.py
    - backend/tests/agents/test_model_catalog.py
  modified:
    - backend/agents/capabilities/registry.py
    - backend/app/api/settings.py

key-decisions:
  - "ModelCatalog is pure data (frozen ModelEntry dataclass + accessor), no behavior Protocol in base.py (RESEARCH #3)"
  - "Store BOTH tier (legacy/display) and cost_class (canonical), asserted consistent fast↔cheap/balanced↔standard/powerful↔premium (D-04)"
  - "settings.py projection emits exactly {id,name,description,tier} (label→name) so /api/settings shape stays byte-identical"
  - "ModelCatalog import moved to settings.py top-of-file to satisfy ruff E402 (was mid-file)"

patterns-established:
  - "Single-source projection (INV-12): a grep test proves model-id literals live in exactly one file"
  - "Kernel purity: agents.capabilities module imports no app.* (import-linter 3-kept/0-broken)"

requirements-completed: [MODEL-04]

# Metrics
duration: 18min
completed: 2026-06-08
---

# Phase 6 Plan 01: ModelCatalog Single-Source Data Capability Summary

**Kernel-pure `ModelCatalog` enumerating the 5 selectable Claude models with full policy metadata, registered name-only in the capability registry, with `app/api/settings.py::AVAILABLE_MODELS` refactored into a derived projection so exactly one hand-maintained model-id list remains (INV-12).**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-08T (plan start)
- **Completed:** 2026-06-08
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `ModelCatalog` data capability with 5 `ModelEntry` records (id/label/description/tier/cost_class/provider/context_window/user_allowed); all `user_allowed=True` including both Opus tiers (no gate, N11).
- `('model_catalog','default')` added to `registry._KNOWN` as pure membership (docstring count 14 → 15); `is_registered` unchanged.
- `AVAILABLE_MODELS` + `_VALID_MODEL_IDS` now derive from `ModelCatalog().list()/ids()`; the literal model list was removed — INV-12 single-source grep proves model-id literals live only in `model_catalog.py`.
- `/api/settings` response shape unchanged: projection emits exactly `{id,name,description,tier}`.
- Kernel purity held: catalog imports no `app.*`; `lint-imports` stays 3-kept / 0-broken.

## Task Commits

1. **Task 1: Create ModelCatalog data capability + tests** — `95f76f6` (feat) — TDD GREEN: module + 6 behavior tests created together (field set, ids/get/is_allowed, cost_class, tier↔cost_class consistency, user_allowed-all-true, kernel purity).
2. **Task 2: Register catalog name + refactor AVAILABLE_MODELS to projection** — `089f04c` (refactor) — registry membership + settings projection + 3 INV-12 tests (projection equality, registry membership, single-source grep). Includes the ruff E402 import-position fix.

**Plan metadata:** committed separately with SUMMARY/STATE/ROADMAP.

## Files Created/Modified
- `backend/agents/capabilities/model_catalog.py` (created) — kernel-pure `ModelEntry` (frozen dataclass) + `ModelCatalog` (list/get/is_allowed/ids); 5 seeded entries.
- `backend/tests/agents/test_model_catalog.py` (created) — 9 tests total (6 catalog + 3 projection/registry/single-source).
- `backend/agents/capabilities/registry.py` (modified) — `_KNOWN += ("model_catalog","default")`; docstring count 14 → 15.
- `backend/app/api/settings.py` (modified) — `AVAILABLE_MODELS`/`_VALID_MODEL_IDS` projections; `ModelCatalog` imported at top; literal list removed.

## Decisions Made
- Catalog modeled as pure data (no `base.py` Protocol) per RESEARCH #3 — it is data, not a behavior port.
- Kept both `tier` and `cost_class` (D-04 store-both) and asserted the mapping consistency in a test.
- `context_window` numerics are [ASSUMED] metadata (200000 default, 1000000 for Sonnet 4.6); they do not affect resolution.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Moved ModelCatalog import to top of settings.py (ruff E402)**
- **Found during:** Task 2 (settings.py projection refactor)
- **Issue:** The plan's `<action>` placed `from agents.capabilities.model_catalog import ModelCatalog` mid-file next to `AVAILABLE_MODELS`; ruff flagged E402 (module-level import not at top of file), which would fail the lint gate.
- **Fix:** Moved the import into the existing top-of-file import block (alongside `from app.api.api_key_auth import mint_api_key`); updated the explanatory comment to note the import is at top.
- **Files modified:** backend/app/api/settings.py
- **Verification:** `ruff check app/api/settings.py` → All checks passed; tests still 9/9 green; `lint-imports` 3-kept/0-broken.
- **Committed in:** 089f04c (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — lint gate)
**Impact on plan:** Cosmetic import placement only; the app→kernel import (the load-bearing change) is intact and import-linter-allowed. No scope creep.

## Issues Encountered
- Full `tests/agents/ tests/unit/` regression showed 9 pre-existing failures (`test_logout.py` x6, `test_pipeline_cancel.py`, + same families). Root causes are environmental/config: HTTP 403 "Self-registration is disabled" (auth config) and AWS `ExpiredTokenException` (expired local SSO token). None touch `model_catalog.py`/`registry.py`/`settings.py`. Logged to `06-model-policy-1c/deferred-items.md`; not fixed (out of scope). 949 passed / 19 skipped otherwise.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The single authoritative model source is in place: 06-02 (loader), 06-03 (resolver), and 06-04 (override-validator) can all import `ModelCatalog` from the kernel side.
- Allow-list validation (websocket/AGENT.md `model` ingress) should key off `ModelCatalog.ids()` / `is_allowed` per the PATTERNS allow-list guidance.
- No blockers.

## Self-Check: PASSED

---
*Phase: 06-model-policy-1c*
*Completed: 2026-06-08*
