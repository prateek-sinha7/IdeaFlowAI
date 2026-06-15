---
phase: quick-260615-dzk
plan: 01
subsystem: ui
tags: [react, tailwind, a11y, aria, lucide, sqlalchemy, alembic, langgraph, fastapi, resumability]

# Dependency graph
requires:
  - phase: 22-capability-surfacing-and-user-empowerment-universal-runtime-
    provides: "EMP-01 _apply_selections overlay seam (engine.py:1140/:4519/:4549); EMP-03 launch selections map + _revalidate_selections_trust_user (websocket.py:1544); CapabilityPaletteSection embedded palette; migration 0022 additive-column precedent"
provides:
  - "Token-conformant AgentsPopup.tsx (max-h-[200px] expander cap, locked-row aria-label, title-cased group aria-label, enriched config-schema affordance, Sliders header icon)"
  - "WorkflowRun.selections_json additive nullable JSON column + migration 0023"
  - "Launch-time persist of selections on the run row at creation (websocket.py)"
  - "resume_run re-threads persisted selections through _execute_impl -> _apply_selections (trust=user re-compile)"
affects: [resumability, capability-surfacing, composer-ux, milestone-v1.0-live-pass]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive nullable JSON column on workflow_runs persisted at run CREATION (mirrors migration 0022) so a backend-restart resume finds launch-time state before the run can crash"
    - "Resume re-applies LESS privilege by construction: _apply_selections re-compiles trust=user at overlay time, so the persisted map can never reintroduce an engineer-only lever"
    - "Additive aria-label on a non-focusable locked row carries the lock reason to keyboard/SR users (visible pill + title preserved)"

key-files:
  created:
    - backend/alembic/versions/0023_workflow_run_selections.py
  modified:
    - frontend/src/components/workflow/AgentsPopup.tsx
    - frontend/src/components/workflow/CapabilityPaletteSection.test.tsx
    - backend/app/models/workflow.py
    - backend/app/api/websocket.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/unit/test_migrations.py

key-decisions:
  - "Persist selections at run CREATION (not finalize) so the row carries them before a crash — resume must find them"
  - "No new WS-layer re-validation on resume: the engine-side _apply_selections trust=user re-compile IS the authoritative re-validation on the resume path"
  - "No new _VOLATILE_STRIP_KEYS entry — _apply_selections mutates only the in-memory plan; the goldens take the selections=None branch unchanged (INV-3 proven)"
  - "Minor #6 (tier-locked 'Upgrade to use' variant) left as a forward-hook comment only; Minor #8 footer untouched — both intentional SKIPs per task scope"

patterns-established:
  - "WR-02 resume re-thread: read wr.selections_json in the existing db session -> selections= kwarg into resume _execute_impl -> shared overlay seam (INV-12, no fork)"

requirements-completed: [UI-REVIEW-TOP-1, UI-REVIEW-TOP-2, UI-REVIEW-TOP-3-WR-02, UI-REVIEW-MINOR-4, UI-REVIEW-MINOR-5, UI-REVIEW-MINOR-7]

# Metrics
duration: ~9min
completed: 2026-06-15
---

# Phase quick-260615-dzk: Apply Phase 22 UI-REVIEW findings (FE polish + WR-02) Summary

**Token-conformant dense-inspector polish (max-h-[200px] cap, locked-row aria-label, title-cased group labels, typed config-schema affordance, Sliders icon) plus WR-02 resolved: launch-time selections now persisted (selections_json + migration 0023) and re-applied on backend-restart resume via the shared _apply_selections trust=user overlay — all 5 INV-3 goldens byte-identical.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-15T08:18:52Z
- **Completed:** 2026-06-15T08:27:52Z
- **Tasks:** 4 (3 code + 1 verification gate)
- **Files modified:** 6 (5 modified + 1 created)

## Accomplishments
- FE polish batch applied token-conformant to the AgentModelPicker template: AdvancedExpander lever-scroll cap aligned to `max-h-[200px]`; additive `aria-label` carrying the engineer-only lock reason on locked capability rows; kind-group `aria-label` title-cased via `titleCaseKind`; config-schema affordance enriched to render field name + type + required marker (defensively narrowed from `unknown`); Capabilities header icon swapped `Boxes` -> `Sliders` (Boxes removed from imports, zero remaining uses).
- WR-02 persistence: `WorkflowRun.selections_json` additive nullable JSON column + migration `0023` (mirrors `0022`, single head, additive add_column only); launch path persists `selections_json=selections` at run creation.
- WR-02 resume re-thread: `resume_run` reads `wr.selections_json` and re-threads it through `_execute_impl` -> `_apply_selections` (trust=user re-compile); the KNOWN LIMITATION comment block replaced with a RESOLVED note.
- INV-3 proven (not assumed): all 5 characterization goldens byte-identical + semantic-event-parity; lint-imports 4 kept / 0 broken; FE 17/17 + tsc clean in src/.

## Task Commits

Each task was committed atomically (code only):

1. **Task 1: FE polish batch (Top #1, Top #2, Minor #4/#5/#7)** - `81a12b89` (feat)
2. **Task 2: WR-02 persistence — selections_json + migration 0023 + launch-time write** - `b204a2d7` (feat)
3. **Task 3: WR-02 resume re-thread + trust re-validation + remove deferred comment** - `b4a88c74` (feat)
4. **Task 4: Full verification gate** - no commit (verification-only, no source edits)

## Files Created/Modified
- `frontend/src/components/workflow/AgentsPopup.tsx` - 5 polish fixes (expander cap, locked-row aria-label, title-cased group aria-label, typed config-schema affordance, Sliders icon) + Minor #6 forward-hook comment
- `frontend/src/components/workflow/CapabilityPaletteSection.test.tsx` - group-label assertions title-cased; +locked aria-label, non-locked-no-label, config-schema type assertions (17/17 green)
- `backend/app/models/workflow.py` - `WorkflowRun.selections_json` additive nullable JSON column
- `backend/alembic/versions/0023_workflow_run_selections.py` - additive add_column migration (revision 0023, down_revision 0022, single head)
- `backend/app/api/websocket.py` - persist `selections_json=selections` at WorkflowRun creation in `run_pipeline_impl`
- `backend/agents/execution_engine/engine.py` - `resume_run` reads `wr.selections_json` + threads `selections=` into the resume `_execute_impl` call; KNOWN LIMITATION -> RESOLVED note
- `backend/tests/unit/test_migrations.py` - +`test_migration_0023_down_revision_is_0022` (single head 0023) +`test_migration_0023_is_additive_only`

## Decisions Made
- Persist selections at run CREATION (not finalize) so the row carries them before a crash — resume must find them.
- No new WS-layer re-validation on resume: the engine-side `_apply_selections` trust=user re-compile is the authoritative re-validation on the resume path (the WS pre-check exists only because the launch path accepts a client-supplied map).
- No new `_VOLATILE_STRIP_KEYS` entry — `_apply_selections` mutates only the in-memory compiled plan; the 5 goldens take the `selections=None` branch unchanged (INV-3 proven by the Task 4 characterization suite, no SNAPSHOT_UPDATE).
- AdvancedExpander.test.tsx required no change (it has no max-h cap assertion; the only `200`-ish literal is an unrelated `context_window: 200000`).

## Deviations from Plan

None - plan executed exactly as written. The two intentional SKIPs (Minor #6 tier-locked variant -> forward-hook comment only; Minor #8 footer -> untouched) were applied as specified.

## Verification Evidence

- **INV-3 goldens:** 5 characterization goldens (prototype, od_prototype, prototype_revision, od_ppt, app_builder) byte-identical + semantic-event-parity. NO golden re-baseline / SNAPSHOT_UPDATE.
- **Backend targeted suite:** `171 passed` across the 5 goldens + manifest/routing/phase3 parity + `test_run_pipeline_validation` + `test_user_workflows` + `test_user_workflows_selections` + migration/alembic ledger (incl. the 2 new 0023 tests). Run time ~110s.
- **lint-imports:** `Contracts: 4 kept, 0 broken.`
- **FE:** `Test Files 3 passed (3) / Tests 17 passed (17)`; `npx tsc --noEmit` -> TSC CLEAN in src/ (only the 2 pre-existing `e2e/fixtures/mockApi.ts:95-96` TS2352 errors, out of scope).

## Issues Encountered

**Two PRE-EXISTING backend test failures (out of scope, logged to deferred-items.md):**

1. `tests/unit/test_migrations.py::test_migration_0016_down_revision_is_0015` — asserts `script.get_heads() == ["0016"]`, which is STALE since Phase 22's migration 0022 landed (the head has long since moved past 0016). Proven pre-existing by removing the 0023 migration + reverting the model edit (still fails). The new `test_migration_0023_down_revision_is_0022` asserts the correct current single head `["0023"]`.
2. `tests/unit/test_alembic.py::TestAlembicMigrations::test_upgrade_then_check_reports_no_drift` — pre-existing autogenerate drift on `ix_workflows_owner_source` (workflows) and `workspaces.repo_id` FK, unrelated to `workflow_runs.selections_json`. Fails identically with 0023 removed.

Both are documented in `.planning/phases/22-capability-surfacing-and-user-empowerment-universal-runtime-/deferred-items.md`. Neither was introduced by this change; per the SCOPE BOUNDARY rule they were not fixed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- WR-02 closed: a launched custom workflow that survives a backend restart now re-applies the user-composed levers instead of silently reverting to defaults.
- All 22/24 UI-REVIEW gaps that were in scope are applied (Top #1/#2/#3-WR-02, Minor #4/#5/#7); Minor #6/#8 are documented intentional SKIPs.
- Stale `test_migration_0016_down_revision_is_0015` head-equality assertion is a recommended follow-up cleanup (update to assert current head or use membership).

## Self-Check: PASSED

All 6 source files + the SUMMARY exist on disk; all 3 task commits (`81a12b89`, `b204a2d7`, `b4a88c74`) are in the git log.

---
*Phase: quick-260615-dzk*
*Completed: 2026-06-15*
