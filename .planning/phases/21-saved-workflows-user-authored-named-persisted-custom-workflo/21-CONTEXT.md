# Phase 21: Saved Workflows - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Source:** PRD Express Path (`21-SPEC.md` in this phase directory)

<domain>
## Phase Boundary

Deliver the **authoring + persistence layer** on top of the Phase 20 catalog: a user composes a custom workflow (agents + per-agent models), **names and saves** it (from BOTH the catalog and the main-page custom composer), sees it in the catalog as a **renameable/deletable** "Your workflows" entry, and **launches** it through the EXISTING run path.

**In scope:** reuse the dormant `workflows` table (`source="user"`) + additive migration `0021` (2 nullable columns) + a new owner-scoped `/api/user-workflows` CRUD router; remove the dead `engine.py` writer it supersedes; FE Save buttons, NameWorkflowModal, "Your workflows" section + per-row kebab, api.ts CRUD, and the `IdeaInputPage` agent-preload prop for launch.

**Out of scope:** any engine/kernel run-path change; a NEW persistence table; sharing/marketplace; non-`custom` base types (v1 = custom only).
</domain>

<decisions>
## Implementation Decisions

> All LOCKED (PRD-derived). The authoritative file:line detail is in `21-SPEC.md` — downstream agents MUST read it.

### Persistence (LOCKED — reuse, not new)
- REUSE `WorkflowDefinition` / `workflows` table (`backend/app/models/workflow_definition.py:13-52`) for `source="user"` rows — it is DORMANT (1 dead writer, 0 readers; future-fitted in migration 0014). A new table is REJECTED (INV-12 dual-impl).
- Additive migration `0021` (`down_revision="0020"`): add nullable `base_pipeline_type` (String) + `model_overrides` (JSON). No table, no alter of existing columns. `artifact_edges` (NOT NULL) → write `"[]"` for user rows.
- REMOVE the superseded `_persist_workflow_definition` writer (`engine.py:4026-4107` + call `:1381`) — INV-12 completion. Custom-only → dormant on the 5 non-custom goldens (prove byte-identical).

### CRUD router (new, owner-scoped) — `backend/app/api/user_workflows.py`
- Copy `runs.py` (owner-filtered CRUD, IDOR→404) + `mcp.py` create idiom. `/api/user-workflows` POST/GET/GET{id}/PATCH{id}/DELETE{id}, all `Depends(get_current_user)`, `WHERE user_id==me AND source=="user"`.
- POST validates `base_pipeline_type ∈ SUPPORTED_PIPELINE_TYPES`, `agent_ids ⊆ allowed_custom_agent_ids(base)`, `model_overrides` ∈ `ModelCatalog().ids()`; gates `can_run_pipeline(tier, base)` (enterprise for custom). Name uniqueness = API-level per-user (not a DB constraint). Stamp `user_id=owner_id=workspace_id=current_user.id`. Register in `app/main.py`.

### Run-launch (reuse, no change)
- Replay `{base_pipeline_type, agent_ids, model_overrides}` into `run_pipeline` (`websocket.py:539-613`); re-validated at `:1394-1406` / `_validate_model_overrides`. No engine run-path edit.

### Frontend (reuse-first)
- Save payload from `IdeaInputPage` (`pipelineAgents.map(id)` `:238`, `modelOverridesRef.current` `:196`, `effectiveType` `:173`).
- Save buttons: `IdeaInputPage` toolbar (`:344-398`) + `AgentsPopup` footer (`:988-996`); catalog "+ Create workflow" (`WorkflowCatalog.tsx:110-131` → `onSelectFeature("custom")`).
- `NameWorkflowModal` ⟵ `DeleteModal` (`WorkflowHistory.tsx:923-969`) + inputs ⟵ `AgentsPopup.tsx:374-393`.
- "Your workflows" section ⟵ catalog rows (`WorkflowCatalog.tsx:152-207`) + second fetch (`:57-82`); per-row kebab ⟵ `WorkflowHistory.tsx:872-918`.
- api.ts CRUD ⟵ `getWorkflowDefinitions`/`adminCreateUser`/`adminUpdateTier`/`adminDeleteUser`.
- **Load-bearing:** add `initialAgentIds`/`initialModelOverrides` to `IdeaInputPage` (it currently always derives agents from the empty custom filter `:175-177,201-203`) + a new `onLaunchSaved` prop on `WorkflowCatalog` (`onSelectFeature` only takes a `WorkflowType`).

### Claude's Discretion
- Whether Save also lives in `AgentsPopup` footer (in addition to `IdeaInputPage`).
- Whether the relaunch pre-fills the model picker UI or threads `model_overrides` straight into the run (SPEC prefers the latter).
- Exact "+ Create workflow" placement / "Your workflows" section ordering.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read before planning/implementing.**

- `.planning/phases/21-saved-workflows-user-authored-named-persisted-custom-workflo/21-SPEC.md` — the authoritative file:line reuse contract (persistence reuse decision, additive surface, launch wiring, locked decisions, invariants).
- Persistence analogs: `backend/app/models/workflow_definition.py`, `backend/alembic/versions/0017_*`, `0020_wave_runs.py`, `backend/app/api/runs.py`, `backend/app/api/mcp.py`, `backend/app/main.py`, `backend/app/core/dependencies.py`.
- Run/validation: `backend/app/api/websocket.py` (run_pipeline + re-validation), `backend/agents/registry.py` (`allowed_custom_agent_ids`), `backend/agents/capabilities/model_catalog.py`, `backend/app/core/entitlements.py`. Engine cleanup: `backend/agents/execution_engine/engine.py` (`_persist_workflow_definition`).
- FE analogs: `frontend/src/components/workflow/IdeaInputPage.tsx`, `AgentsPopup.tsx`, `AgentModelPicker.tsx`, `frontend/src/components/catalog/WorkflowCatalog.tsx`, `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/lib/api.ts`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/hooks/useWorkflow.ts`.
- `.planning/IMPLEMENTATION-REGISTER.md`; `.planning/ISSUES-REGISTER.md` (WF-DB-01 lineage).
</canonical_refs>

<specifics>
## Specific Ideas
- New BE: `0021` migration, `base_pipeline_type`+`model_overrides` columns, `app/api/user_workflows.py` router; remove `_persist_workflow_definition`.
- New FE: `NameWorkflowModal`, `getUserWorkflows`/`createUserWorkflow`/`renameUserWorkflow`/`deleteUserWorkflow` + `UserWorkflowSummary`, "Your workflows" section + kebab, Save buttons, `IdeaInputPage` preload prop + `onLaunchSaved`.
- New tests: BE CRUD/authz/validation + migration; FE mocked Playwright (compose→Save→appears→rename→launch) + a vitest for the catalog section.
</specifics>

<deferred>
## Deferred Ideas
- Saving non-`custom` base types; sharing/marketplace; org/workspace-shared workflows; versioning of saved workflows beyond the existing `version` column.
</deferred>

---

*Phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo*
*Context gathered: 2026-06-14 via PRD Express Path*
