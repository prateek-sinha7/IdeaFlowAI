---
phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo
verified: 2026-06-14T15:05:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: null
gaps: []
---

# Phase 21: Saved Workflows — User-Authored, Named, Persisted Custom Workflows — Verification Report

**Phase Goal:** Let a user compose a custom workflow (agents + per-agent models), name and save it from BOTH the catalog AND the main-page composer, see it in the catalog as their own renameable/deletable "Your workflows" entry, and launch it through the EXISTING run path. Persistence completes the half-built `workflows` table (reuse, not a new table) with the milestone's first additive table-migration; everything else is reuse.
**Verified:** 2026-06-14T15:05:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (= the 5 ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Save from BOTH composer AND catalog persists a `source="user"` `workflows` row scoped to owner/workspace/user | ✓ VERIFIED | `user_workflows.py:230-242` stamps `user_id=owner_id=workspace_id=current_user.id`, `source="user"`. Composer Save: `IdeaInputPage.tsx` → `createUserWorkflow` (grep 2). Catalog "+ Create" routes to composer (`WorkflowCatalog.tsx:236 onSelectFeature("custom")`); catalog Duplicate also calls `createUserWorkflow` (:155). e2e TS-Z2-01 asserts POST body `base_pipeline_type=="custom"` + non-empty `agent_ids`. |
| 2 | Catalog shows "Your workflows" section with Rename/Duplicate/Delete; built-in rows read-only | ✓ VERIFIED | `WorkflowCatalog.tsx` "Your workflows" (grep 2), kebab actions `renameUserWorkflow`/`createUserWorkflow`(dup)/`deleteUserWorkflow` (:141/:155/:177). Built-in rows have no kebab (vitest covers section render + kebab presence; 6/6 passed). |
| 3 | Launching a saved workflow replays `{base_pipeline_type, agent_ids, model_overrides}` through the EXISTING run_pipeline path; re-validated at launch | ✓ VERIFIED | `DashboardLayout.handleLaunchSaved:681-685` sets `savedComposition` + `workflowType=saved.base_pipeline_type`, threads to `IdeaInputPage initialAgentIds/initialModelOverrides` (:1204-1205). `IdeaInputPage` seeds `pipelineAgents` (:194) + `modelOverridesRef` (:220), guards re-derive (`if (initialAgentIds?.length) return;` :229). `onRun`/`handleRun:246` UNCHANGED. Launch-time server revalidation: launch path unchanged, re-checks live allow-list (router docstring T-21-03; engine goldens dormant). e2e TS-Z2-02 launches pre-loaded. |
| 4 | Persistence REUSES `workflows` table (0021 adds ONLY 2 nullable cols; NO new table) AND dead `_persist_workflow_definition` writer REMOVED (INV-12) | ✓ VERIFIED | `grep -c '_persist_workflow_definition' engine.py` = **0**; `grep -c 'create_table' 0021_*.py` = **0**. Migration adds `base_pipeline_type`(String,null) + `model_overrides`(JSON,null) + index via `batch_alter_table`, `down_revision="0020"`, reversible. Model cols at `workflow_definition.py:41-42`. CRUD owner-scoped: IDOR get/patch/delete → 404 (tests `test_cross_owner_*_is_404`). |
| 5 | INV-3 holds — 5 goldens byte-identical · lint-imports 4/0 · CRUD/IDOR green · migration reversible · catalog vitest · e2e | ✓ VERIFIED | All gates RUN below — every one green. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/models/workflow_definition.py` | +2 nullable cols | ✓ VERIFIED | `base_pipeline_type`/`model_overrides` at :41-42, both nullable |
| `backend/alembic/versions/0021_saved_user_workflows.py` | additive migration, no new table | ✓ VERIFIED | 2 nullable cols + `ix_workflows_owner_source`, `down_revision="0020"`, reversible; `create_table` count = 0 |
| `backend/app/api/user_workflows.py` | owner-scoped CRUD router | ✓ VERIFIED | 339 lines; POST/GET/GET{id}/PATCH{id}/DELETE{id}; save==launch validation; IDOR→404 via `_owned` |
| `backend/app/main.py` | router registered | ✓ VERIFIED | import :18, `include_router(user_workflows_router)` :162 |
| `backend/agents/execution_engine/engine.py` | dead writer removed | ✓ VERIFIED | `_persist_workflow_definition` grep = 0 (only unrelated `_persist_budget_snapshot_if_active`) |
| `backend/tests/unit/test_user_workflows.py` | CRUD/IDOR/validation tests | ✓ VERIFIED | 16 tests incl. owner-stamp, 422×4, 403 entitlement, 409 dup, IDOR×3, rename, delete→404, model+migration cols |
| `frontend/src/lib/api.ts` | 4 fetchers + type | ✓ VERIFIED | `UserWorkflowSummary` :578; `getUserWorkflows`/`createUserWorkflow`/`renameUserWorkflow`/`deleteUserWorkflow` :595/:610/:631/:648; `/api/user-workflows` grep 5 |
| `frontend/src/components/catalog/NameWorkflowModal.tsx` | name+desc modal, z-[80] | ✓ VERIFIED | exists, `z-[80]` present (over AgentsPopup) |
| `frontend/src/components/catalog/WorkflowCatalog.tsx` | section + kebab + Create + onLaunchSaved | ✓ VERIFIED | "Your workflows" + kebab + `onLaunchSaved` prop (:55,:61) + "+ Create" (:236) |
| `frontend/src/components/workflow/IdeaInputPage.tsx` | Save button + preload props + guard | ✓ VERIFIED | `createUserWorkflow` Save; `initialAgentIds`/`initialModelOverrides` props; guarded re-derive :229; ref seed :220 |
| `frontend/src/components/layout/DashboardLayout.tsx` | handleLaunchSaved + threading | ✓ VERIFIED | `savedComposition` state :667, `handleLaunchSaved` :681, seed threading :1204-1205, clear on select :671 |
| `frontend/e2e/tests/ts-z2.saved-workflows.spec.ts` | compose→Save→appears→rename→launch | ✓ VERIFIED | stateful `/api/user-workflows` mock (POST/GET/PATCH/DELETE); 2 tests, both pass |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `main.py` | `user_workflows.py` | `include_router` | ✓ WIRED (:162) |
| `user_workflows.py` | `WorkflowDefinition` | owner-scoped ORM query | ✓ WIRED (`_owned` filters id+user_id+source) |
| `user_workflows.py` | registry/model_catalog/entitlements | save==launch validation | ✓ WIRED (`allowed_custom_agent_ids`, `ModelCatalog().ids()`, `can_run_pipeline`) |
| `WorkflowCatalog.tsx` | api.ts CRUD | fetch + kebab | ✓ WIRED (getUserWorkflows :116, rename/dup/delete :141/:155/:177) |
| `IdeaInputPage.tsx` | api.ts `createUserWorkflow` | Save → modal → POST | ✓ WIRED |
| `DashboardLayout` | `WorkflowCatalog onLaunchSaved` | handleLaunchSaved | ✓ WIRED (:1093) |
| `DashboardLayout` | `IdeaInputPage initialAgentIds` | savedComposition threading | ✓ WIRED (:1204-1205) |
| `IdeaInputPage` | `startPipeline` run path | onRun (unchanged) | ✓ WIRED (handleRun :246 unchanged; payload byte-identical when no seed) |

### Behavioral Spot-Checks / Gate Execution

| Gate | Command | Result | Status |
|------|---------|--------|--------|
| SC5 — 5 goldens byte-identical | `SNAPSHOT_UPDATE= pytest test_characterization_* test_manifest_parity -q` | 42 passed in 34.68s | ✓ PASS |
| SC5 — Ports & Adapters | `/opt/homebrew/bin/lint-imports` | 4 kept, 0 broken | ✓ PASS |
| SC4/SC1/SC3 — CRUD/IDOR/422 | `pytest tests/unit/test_user_workflows.py -q` | 16 passed in 0.48s | ✓ PASS |
| SC4 — migration reversibility | alembic up head → down 0020 → up head (in-memory SQLite) | up/down/up OK — REVERSIBILITY: PASS | ✓ PASS |
| SC2 — catalog vitest | `npx vitest --run src/components/catalog` | 6 passed | ✓ PASS |
| SC1/SC2/SC3 — e2e | `npm run e2e -- e2e/tests/ts-z2.saved-workflows.spec.ts` | 2 passed in 4.4s | ✓ PASS |
| SC4 grep guard | `grep -c '_persist_workflow_definition' engine.py` | 0 | ✓ PASS |
| SC4 grep guard | `grep -c 'create_table' 0021_*.py` | 0 | ✓ PASS |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REUSE-FIRST (reuse `workflows` table, `source="user"`) | ✓ SATISFIED | No new table; +2 nullable cols only |
| INV-12 (remove superseded writer) | ✓ SATISFIED | `_persist_workflow_definition` grep = 0 |
| INV-3 (5 goldens byte-identical) | ✓ SATISFIED | 42 passed, no SNAPSHOT_UPDATE |
| SC-001 (saved workflow = pure data, no new pipeline name) | ✓ SATISFIED | launch replays through unchanged onRun; no `if saved` fork |
| Ports & Adapters (import-linter 4/0) | ✓ SATISFIED | 4 kept / 0 broken; router lives in `app.*` (legal `app→agents`) |
| Additive-migration-only (2 nullable cols) | ✓ SATISFIED | reversible up/down/up |
| Security (IDOR→404; revalidate at save AND launch) | ✓ SATISFIED | `_owned` 404; POST/PATCH revalidate; launch path unchanged revalidates |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| (none) | — | — | No TBD/FIXME/XXX debt markers in any new/modified file. "placeholder" matches are CSS classes (`placeholder-gray-400`) and input `placeholder=` attrs — not stubs. |

### Deferred Items (logged, not gaps)

Pre-existing tsc errors in `frontend/e2e/fixtures/mockApi.ts` (TS2352, lines 95-96) — confirmed PRE-EXISTING on HEAD, untouched by Phase 21, owned by the e2e-fixtures cleanup task. Not a saved-workflows concern; does not affect any Phase 21 gate (all touched files emit 0 tsc errors; e2e + vitest green).

### Human Verification Required

None. All 5 Success Criteria verified via offline gates run by the verifier (backend pytest, lint-imports, alembic reversibility, vitest, mocked Playwright). Visual polish was not in scope; the UI-SPEC mandates reuse of existing styling and the vitest + e2e assert the section/kebab/launch behaviors.

### Gaps Summary

No gaps. Every Success Criterion is backed by real code (file:line) AND a passing gate the verifier ran independently. The two grep guards (SC4) return 0 as required; the dead engine writer is gone (INV-12 complete); the migration is additive-only and reversible; the 5 characterization goldens stay byte-identical (INV-3); CRUD is owner-scoped with IDOR→404 and save==launch validation; the full compose→Save→appears→rename→launch loop passes in the mocked Playwright spec; import-linter is 4/0.

---

_Verified: 2026-06-14T15:05:00Z_
_Verifier: Claude (gsd-verifier)_
