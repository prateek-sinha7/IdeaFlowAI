---
phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo
reviewed: 2026-06-14T00:00:00Z
depth: deep
files_reviewed: 12
files_reviewed_list:
  - backend/app/models/workflow_definition.py
  - backend/alembic/versions/0021_saved_user_workflows.py
  - backend/app/api/user_workflows.py
  - backend/app/main.py
  - backend/agents/execution_engine/engine.py
  - backend/tests/unit/test_user_workflows.py
  - frontend/src/lib/api.ts
  - frontend/src/components/catalog/NameWorkflowModal.tsx
  - frontend/src/components/catalog/WorkflowCatalog.tsx
  - frontend/src/components/catalog/WorkflowCatalog.test.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/workflow/IdeaInputPage.tsx
  - frontend/e2e/tests/ts-z2.saved-workflows.spec.ts
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-06-14
**Depth:** deep
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 21 (Saved Workflows) was reviewed adversarially against its LOCKED spec (the reuse contract, INV-3/INV-12/SC-001, additive-migration, owner-scoped security). The core contract holds up well:

- **Migration 0021 is genuinely additive** — 2 nullable columns + 1 index via `batch_alter_table`, `down_revision="0020"`, no `create_table`, no alter of existing columns, single head (`heads: ['0021']`), reversible (proven by `test_migration_adds_then_drops_columns`).
- **Engine-writer removal (INV-12) is clean** — `_persist_workflow_definition` and its call site are fully gone; `grep -rn "_persist_workflow_definition"` across the backend returns zero hits; no dangling references; import-linter stays 4/0.
- **CRUD security is sound** — every handler is `Depends(get_current_user)`; `_owned()` filters `id AND user_id AND source=="user"` (cross-owner/missing → 404, verified by `test_cross_owner_{get,patch,delete}_is_404`); POST validates `base_pipeline_type ∈ SUPPORTED_PIPELINE_TYPES`, `agent_ids ⊆ allowed_custom_agent_ids` (the EXACT launch predicate), `model_overrides` via the two-check allow-list, entitlement gate, and per-user name uniqueness (409). No unscoped query, no IDOR vector found.
- **SC-001 holds** — the saved workflow is pure data; no new pipeline name, no `if saved_workflow:` fork; launch replays the triple through the unchanged run path.
- **Tests are non-vacuous** — the success-path POST tests use REAL custom agent ids (`market-research-agent`, `report-generator` confirmed ∈ `PIPELINE_AGENTS["custom"]`) and a real ModelCatalog id, so 201 is genuinely exercised; IDOR/validation/launch are all asserted. All 16 backend tests pass.

No Critical findings. Four Warnings concern launch-replay override clobbering, a validation gap (empty `agent_ids`), a semantic column overload, and an optimistic-delete-on-error UI inconsistency.

## Warnings

### WR-01: Launch-replay model_overrides are silently clobbered if the user touches the model picker

**File:** `frontend/src/components/workflow/AgentModelPicker.tsx:46,76-88` (interacts with `frontend/src/components/workflow/IdeaInputPage.tsx:196-199`)
**Issue:** On launching a saved workflow, `IdeaInputPage` seeds `modelOverridesRef.current = initialModelOverrides`, and those overrides correctly flow into the run (good). But `AgentModelPicker` initializes its own `overrides` state to `{}` and never receives the seeded values (it has no initial-overrides prop — exactly the gap SPEC §4.6 flagged). `setAgentModel` builds the emitted map from that empty internal state and calls `onChange(next)` → `handleModelOverridesChange` overwrites `modelOverridesRef.current` **wholesale**. So if a user launches a saved workflow with overrides for agents A+B and then changes agent C's model in the Advanced popup, the ref is replaced with `{C: ...}` only — agents A and B's persisted overrides are silently dropped from the run. This is a correctness regression on the launch-replay path (the saved composition is not faithfully replayed once the picker is touched).
**Fix:** Either (a) add an `initialOverrides?: Record<string,string>` prop to `AgentModelPicker`, seed `useState(initialOverrides ?? {})`, and thread `initialModelOverrides` through `AgentsPopup` → picker so the picker's internal state starts reconciled with the seed; or (b) make `handleModelOverridesChange` merge rather than replace when launching a saved workflow. Option (a) is preferred (it also fixes the UI showing "Default" for seeded agents).

### WR-02: POST accepts an empty `agent_ids` list — persists an unrunnable orphan row

**File:** `backend/app/api/user_workflows.py:200-207`
**Issue:** The subset check `rejected = [aid for aid in body.agent_ids if aid not in allowed_ids]` is trivially satisfied for an empty list (`rejected == []`), and `SaveUserWorkflowRequest.agent_ids: list[str]` has no `min_length`. A direct API caller can POST `agent_ids: []` and persist a `source="user"` row that the launch path can never run (the FE disables Save/Run at zero agents, but the API is the security boundary). This contradicts the spec's own "fail-fast — no orphan rows a user can't run" rationale (§3.2).
**Fix:** Add a non-empty guard, e.g. `agent_ids: list[str] = Field(min_length=1)` on the request model, or explicitly `if not body.agent_ids: raise HTTPException(422, "agent_ids must be non-empty")` before the subset check.

### WR-03: User-supplied free-text description is overloaded onto the `constitution_ref` column

**File:** `backend/app/api/user_workflows.py:143,238,306`
**Issue:** The `description` (up to 2000 chars of arbitrary user text) is stored in and projected from `WorkflowDefinition.constitution_ref`, a column whose documented semantic is "key in `workflow_memory` for per-workflow constitution" (`workflow_definition.py:19,30`). It is functionally safe TODAY (zero DB readers of `constitution_ref` exist — the only runtime reader, `factory.py:374`, reads `ctx.planning_context.constitution_ref`, not the row), but it is a latent footgun: any future feature that loads `constitution_ref` across all `workflows` rows would interpret a user's prose description as a constitution lookup key. This is a maintainability/correctness-risk defect — the spec added two new columns specifically to avoid overloading existing ones, then overloaded a third for description.
**Fix:** Add a dedicated nullable `description` column to the additive migration (it is still additive), or, if a 4th column is undesirable, document the overload explicitly at the column definition and guard any future cross-source `constitution_ref` reader to skip `source="user"` rows. The dedicated column is the clean option and consistent with the phase's own additive-migration approach.

### WR-04: Delete optimistically removes the row from the UI even when the server delete fails

**File:** `frontend/src/components/catalog/WorkflowCatalog.tsx:170-182`
**Issue:** In `handleDeleteConfirm`, `setUserWorkflows(prev => prev.filter(...))` at line 181 runs **unconditionally after** the try/catch — so a failed `deleteUserWorkflow` (network error / 404) sets `savedError` AND still removes the row from the visible list. The user sees an error toast and the row vanishing simultaneously; on the next catalog mount the row reappears (it was never deleted), which is confusing and can mask a real failure. The Duplicate/Rename handlers correctly only mutate state inside the success path; Delete is inconsistent with them.
**Fix:** Move the optimistic removal inside the `try` (after the `await` succeeds), or remove first and re-insert on `catch`:
```ts
try {
  await deleteUserWorkflow(jwt, id);
  setUserWorkflows((prev) => prev.filter((w) => w.id !== id));
} catch (e) {
  setSavedError((e as Error)?.message ?? "Delete failed.");
}
```

## Info

### IN-01: `description` length cap differs between create and the column

**File:** `backend/app/api/user_workflows.py:61,75`
**Issue:** `description` is `Field(max_length=2000)` on the Pydantic models, but the underlying `constitution_ref` is an unbounded `Column(String)`. Harmless today, but if WR-03 is addressed by repurposing rather than a new column, the 2000-char intent is enforced only at the API layer, not the schema.
**Fix:** If a dedicated column is added (WR-03), give it an explicit length or document that the 2000 cap is API-enforced.

### IN-02: `_validate_model_overrides` has an unreachable `isinstance` branch given the Pydantic type

**File:** `backend/app/api/user_workflows.py:107-111`
**Issue:** `model_overrides` is typed `dict[str, str] | None` on both request models, so by the time `_validate_model_overrides` runs from the POST/PATCH handlers the `not isinstance(model_overrides, dict)` guard is dead for those callers (Pydantic already coerced/rejected). The guard is reasonable defensive depth (the helper could be called with raw input elsewhere), but it is currently dead on every real call path.
**Fix:** Keep as defensive code, or add a brief comment noting it guards non-Pydantic callers; no change required.

### IN-03: WorkflowCatalog kebab test relies on a "click every button until menu opens" loop

**File:** `frontend/src/components/catalog/WorkflowCatalog.test.tsx:266-269,282-285`
**Issue:** The kebab tests iterate all buttons clicking each until "Rename"/"Delete" appears. This passes deterministically today (only the saved-row kebab toggles the menu), but it is brittle: a future layout change that makes another button reveal matching text, or that reorders buttons, could make the loop click the wrong control first. The assertion is non-vacuous but loosely targeted.
**Fix:** Target the kebab directly (e.g. the `MoreHorizontal` icon button within the saved row's container, or add a `data-testid`/`aria-label="Workflow actions"` to the toggle) instead of brute-forcing every button.

### IN-04: Saved-list fetch is fire-and-forget with no loading state

**File:** `frontend/src/components/catalog/WorkflowCatalog.tsx:112-129`
**Issue:** The second `useEffect` (saved workflows) has no `setLoading`/`finally` equivalent to the built-in fetch — a slow `getUserWorkflows` simply pops the "Your workflows" section in late with no skeleton/spinner. This is an intentional non-fatal design (a failed saved-list fetch must not block the built-in catalog, per the comment), so it is acceptable, but worth noting for UX parity with the primary list.
**Fix:** Optional — add a lightweight loading indicator for the saved section, or accept the current pop-in behavior as designed.

---

_Reviewed: 2026-06-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
