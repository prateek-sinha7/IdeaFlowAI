# Phase 21 — Saved Workflows: User-Authored, Named, Persisted Custom Workflows (SPEC)

> **Status:** LOCKED spec for planning. The authoritative, file:line-grounded reuse contract. Grounded by three read-only mapping passes (BE persistence/run, FE composer/catalog, persistence reuse-vs-new resolver) captured 2026-06-14.
>
> **Feed to planning:** `/gsd-plan-phase 21 --prd <this file> --skip-research`

---

## 1. Goal & User Value

A user composes a **custom workflow** (assembles agents + per-agent models), **names and saves** it, and it becomes a first-class, **persisted, user-owned** entry in the **catalog** ("Your workflows"), which they can **rename / duplicate / delete**. Saving is available from **BOTH** (a) the **catalog** and (b) the **main-page custom-workflow composer**. Launching a saved workflow replays its composition through the **existing** run path.

**User value:** turn the throwaway custom composer into reusable, named pipelines — "build it once, name it, run it again from the catalog."

**Scope:** persistence (reuse the existing `workflows` table) + a CRUD API + the two Save entry points + the catalog "Your workflows" section + rename/delete + launch-a-saved-workflow. **Out of scope:** any engine/kernel run-path change; a new persistence table; sharing/marketplace; saving non-`custom` base types (v1 = `custom` only).

---

## 2. Architecture — REUSE the existing `workflows` table (LOCKED decision)

The resolver proved the existing `WorkflowDefinition` / `workflows` table (`backend/app/models/workflow_definition.py:13-52`) is **DORMANT**: exactly one best-effort writer (`engine.py:4086`, swallows errors, id discarded) and **zero readers** anywhere in `backend/`. It was future-fitted in migration `0014` with `source` (default `"file"`), `owner_id`, `workspace_id`, `manifest_json`, `version`. Per **INV-12 (no dual implementations — finish the half-built abstraction, don't add a parallel one)**, we **REUSE** this table for `source="user"` rows. A new `user_workflows` table is REJECTED (it would be the textbook dual-implementation violation).

- **No new table.** Additive migration `0021` adds only **2 nullable columns**.
- **The run path is untouched.** Launch = replay `{base_pipeline_type, agent_ids, model_overrides}` into the existing `run_pipeline` WS handler (`websocket.py:539-613`), re-validated at launch (`:1394-1406`). Zero engine change *to the run path*.
- **The one engine edit is a DELETION (INV-12):** remove the dead `_persist_workflow_definition` writer (`engine.py:4026-4107` + its call at `:1381`) that the new owner-scoped router supersedes. It is `custom`-only (`:4052-4056`), best-effort, unread, and **does not fire on any of the 5 (non-custom) characterization goldens** → INV-3 byte-parity holds (must be proven).

---

## 3. Backend reuse + additive surface

### 3.1 Persistence (reuse the table; the spine)
- **Model** `backend/app/models/workflow_definition.py:13-52` (`WorkflowDefinition`, table `workflows`) — already has `id`, `user_id` (FK users, NOT NULL, indexed), `name`, `agents` (Text JSON ordered agent-id list = our `agent_ids`), `owner_id`/`workspace_id` (nullable, AUTHZ-01, added 0014), `source` (default `"file"`), `manifest_json`, `version`, `created_at`/`updated_at`. **Reuse as:** the saved-workflow home. ADD two nullable columns:
  - `base_pipeline_type: str | None` (no existing column carries it),
  - `model_overrides: sa.JSON | None` (today only persisted per-run on `run_capabilities.py:31`, not on the definition).
- **Register** nothing new in `models/__init__.py` (the model already imports). The 2 columns are added to the existing class.
- **Migration** `backend/alembic/versions/0021_saved_user_workflows.py` — head is `0020_wave_runs.py` → `down_revision="0020"`. Additive-only:
  ```python
  with op.batch_alter_table("workflows") as b:
      b.add_column(sa.Column("base_pipeline_type", sa.String(), nullable=True))
      b.add_column(sa.Column("model_overrides", sa.JSON(), nullable=True))
  ```
  (Optional additive index `ix_workflows_owner_source` on `(owner_id, source)` to back the list query.) **Copy-from:** `0017_repositories_repo_workspace.py:42-89` (header/shape) + `0020_wave_runs.py:34-78` (head pointer, `sa.JSON()`, named index, reversible `downgrade`).
- **`artifact_edges` is NOT NULL** on the table — user rows write `"[]"` (do NOT relax the constraint).

### 3.2 CRUD router (new, owner-scoped) — `backend/app/api/user_workflows.py`
**Copy-from:** `backend/app/api/runs.py:36,101-129,248-297` (router shell + owner-filtered list/get/delete, IDOR→404) + `backend/app/api/mcp.py:221-234` (create-row idiom). `router = APIRouter(prefix="/api/user-workflows", tags=["user-workflows"])`, every handler `Depends(get_current_user)` (`backend/app/core/dependencies.py:153-178`).
- `POST ""` — validate `base_pipeline_type ∈ SUPPORTED_PIPELINE_TYPES` + `agent_ids ⊆ allowed_custom_agent_ids(base_pipeline_type)` (`agents/registry.py:331-395`) + `model_overrides` values ∈ `ModelCatalog().ids()` / keys ∈ `agent_ids`; on fail → 422. Insert a row: `source="user"`, `agents=json.dumps(agent_ids)`, `artifact_edges="[]"`, stamp `user_id=owner_id=workspace_id=current_user.id` (self-id convention, `app/api/workspace.py:6,29`). Also gate by `can_run_pipeline(current_user.tier, base_pipeline_type)` (fail-fast — no orphan rows a user can't run).
- `GET ""` — `WHERE user_id==current_user.id AND source=="user"`, `order_by(updated_at.desc())`.
- `GET "/{id}"` / `PATCH "/{id}"` (rename + edit description/overrides) / `DELETE "/{id}"` — each `id==:id AND user_id==current_user.id`; miss/cross-owner → **404** (`runs.py:263-267`); delete → 204.
- **Name uniqueness:** API-level validation (reject a duplicate `name` among the caller's `source="user"` rows) — NOT a DB unique constraint (the shared table also holds `source="file"` rows; a cross-source constraint is wrong + migration-risky). 
- **Register** in `backend/app/main.py` beside `runs_router` (`main.py:15` import, `:158/160` `include_router`).

### 3.3 Remove the superseded dead writer (INV-12)
Delete `_persist_workflow_definition` (`engine.py:4026-4107`) and its call site (`:1381`). It is the half-built, unscoped, unread dual author the new router replaces. Prove the 5 goldens stay byte-identical (it is custom-only → dormant on prototype/od_prototype/prototype_revision/od_ppt/app_builder anyway).

### 3.4 Run-launch (reuse, no change)
`websocket.py:539-613` `run_pipeline` reads `{pipeline_type, agent_ids, model_overrides}` and dispatches; `:1394-1406` re-validates `agent_ids` against the LIVE `allowed_custom_agent_ids`; `:1465-1475`/`_validate_model_overrides` (`:95-155`) re-validates `model_overrides`. **Launching a saved workflow = replay the stored triple into this exact path** → a stale saved agent/model is rejected at launch (security), never smuggled.

### 3.5 Entitlements (reuse)
`backend/app/core/entitlements.py:8-31` `TIER_PIPELINES` — `custom` ∈ enterprise only. `can_run_pipeline` (`:46-55`) gates launch at `websocket.py:581` AND (new) save. **No entitlements change.** (v1 saved workflows are `custom`-based → enterprise.)

### 3.6 Catalog endpoint stays DB-free
`backend/app/api/workflows.py` (Phase 20, `GET /api/workflows`) issues **no DB query** — it must stay manifest-only. Saved workflows are served by the SEPARATE `/api/user-workflows` endpoint; the FE merges client-side.

---

## 4. Frontend reuse + additive surface

### 4.1 Composer state = the Save payload (reuse)
`IdeaInputPage.tsx` — `pipelineAgents` (`:175-177`, the assembled `AgentDef[]`) → `agent_ids = pipelineAgents.map(a=>a.id)` (`:238`); `modelOverridesRef.current` (`:196-199`, a **ref**) → `model_overrides`; `effectiveType` (`:173`) → `base_pipeline_type`. These are the exact three values `onRun` already sends.

### 4.2 Save entry points (new buttons, reuse styles)
- **#1 main-page composer:** a **"Save workflow"** button in the `IdeaInputPage` toolbar (`:344-398`) and/or the `AgentsPopup` footer (`:988-996`) → opens `NameWorkflowModal` → `createUserWorkflow({name, description?, pipeline_type: effectiveType, agent_ids, model_overrides: modelOverridesRef.current})`.
- **#2 catalog:** a **"+ Create workflow"** affordance in the `WorkflowCatalog` header (`:110-131`) → `onSelectFeature("custom")` (existing prop, `DashboardLayout.tsx:1073`) → routes into the composer where Save #1 lives. (Catalog needs no own composer.)

### 4.3 NameWorkflowModal (new, copy DeleteModal)
**Copy-from** `WorkflowHistory.tsx:923-969` (`DeleteModal` shell — `fixed inset-0 z-50`, backdrop, header, two-button footer) + name `<input>`/`<textarea>` styling from `AgentsPopup.tsx:374-393` (`AgentCapabilitiesModal`). Used by both Save entry points + Rename. There is **no shared `<Modal>` primitive** — hand-rolled per existing convention; keep z-index ≥ `z-[80]` if it can open over `AgentsPopup`.

### 4.4 "Your workflows" catalog section (extend WorkflowCatalog)
- Second fetch: copy the mount effect `WorkflowCatalog.tsx:57-82` → `getUserWorkflows(jwt)` → `setUserWorkflows`.
- Second list: a "Your workflows" `<section>` with rows copied from `:152-207` (label = `row.name`), each row carrying a **kebab menu**.
- Kebab menu: **copy** `WorkflowHistory.tsx:872-899` (the `MoreHorizontal` toggle + `AnimatePresence` dropdown) + `:916-918` (click-outside dismiss) + `:127-128` (state). Items: **Rename** (→ `NameWorkflowModal` prefilled → `renameUserWorkflow`), **Duplicate** (→ `createUserWorkflow` with copied payload + "(copy)" name), **Delete** (→ `DeleteModal` → `deleteUserWorkflow`, optimistic remove per `:159-175`).

### 4.5 api.ts CRUD (new, copy admin* fetchers)
In `frontend/src/lib/api.ts`: `getUserWorkflows` (copy `getWorkflowDefinitions` `:557-564`), `createUserWorkflow` (copy `adminCreateUser` `:454-466`), `renameUserWorkflow` PATCH (copy `adminUpdateTier` `:442-452`), `deleteUserWorkflow` DELETE (copy `adminDeleteUser` `:468-481` / `deleteWorkflow` `:354-370`). New `UserWorkflowSummary` type (copy `WorkflowSummary` `:539-549` + `agent_ids`/`model_overrides`/`pipeline_type`).

### 4.6 Launch a saved workflow — the ONE load-bearing FE change
`IdeaInputPage` has **no agent-preload**: `pipelineAgents` is always re-derived from `LIBRARY_AGENTS.filter(type)` (`:175-177` + effect `:201-203`), which is **empty for `custom`**. To launch a saved workflow you MUST add:
- `initialAgentIds?: string[]` (+ `initialModelOverrides?`) prop on `IdeaInputPage` — seed `pipelineAgents` from the saved ids (resolve via `LIBRARY_AGENTS`/agent registry) instead of the empty custom filter, and **guard the re-derive effect** so it doesn't clobber the seed; seed `modelOverridesRef`.
- A NEW `onLaunchSaved(saved)` prop on `WorkflowCatalog` → `DashboardLayout` (`onSelectFeature` only takes a `WorkflowType`, so it can't carry a saved composition) → sets the saved composition + `workflowType=saved.base_pipeline_type` + `mainView="input"`. The user types the brief, then Run flows UNCHANGED through `handleRunPipeline` (`DashboardLayout.tsx:674`) → `useWorkflow.startPipeline` (`useWorkflow.ts:34-96`, which already sets `payload.agent_ids` `:54-55` + merges `model_overrides` `:94-95`).
- `AgentModelPicker` has no initial-overrides prop (`:127` defaults "Default") — either add one, or thread `model_overrides` straight into the run extraParams (preferred; the picker UI is optional on relaunch).

---

## 5. Locked decisions (resolving the open questions)
1. **base_pipeline_type = `custom` for v1** (the Save buttons live in the custom composer). The table/validation supports other base types; exposing them is deferred.
2. **`model_overrides` ARE persisted** with the saved workflow (the user explicitly chose per-agent models); re-validated at launch.
3. **Name uniqueness = per-user, API-level** (reject duplicate among the caller's `source="user"` rows). No DB unique constraint (shared table).
4. **`workspace_id = owner_id = user_id = current_user.id`** at save (self-id convention; satisfies the owner_id+workspace_id rule).
5. **Save is gated by `can_run_pipeline(tier, base_pipeline_type)`** (enterprise for custom) — fail-fast at save AND enforced at launch.
6. **Built-in (manifest) catalog rows stay read-only** — only `source="user"` rows get the kebab menu.

---

## 6. Critical gotchas the plan MUST honor
1. `IdeaInputPage` has no agent-preload → the `initialAgentIds` prop + guarded re-derive effect is mandatory for launch (§4.6).
2. `custom` seeds zero agents (the saved workflow's value lives entirely in its persisted `agent_ids`).
3. `model_overrides` live in a **ref** (read `.current` on save); the picker has no value prop (thread overrides into the run instead).
4. No shared Modal/Menu primitive — copy `DeleteModal` + the `WorkflowHistory` kebab.
5. `onSelectFeature` only takes a `WorkflowType` → add a distinct `onLaunchSaved` prop.
6. The dead `engine.py:4086` writer MUST be removed (INV-12), not left as a second author.
7. `artifact_edges` NOT NULL → write `"[]"` for user rows.
8. `GET /api/workflows` stays DB-free → user workflows on the separate endpoint, merged in the FE.

---

## 7. Invariants
- **INV-3** — the 5 characterization goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder) MUST stay byte-identical. The new columns/router/FE never touch the run/event path; the ONLY engine edit removes a `custom`-only dead write that doesn't fire on the (non-custom) goldens. The plan MUST run the characterization suite to prove it.
- **INV-12 (no dual implementations)** — reuse the `workflows` table AND delete the superseded `_persist_workflow_definition` writer. Adding the CRUD without deleting the dead writer = phase not done.
- **SC-001** — a saved workflow is pure data (`{base_pipeline_type, agent_ids, model_overrides}`); the kernel knows no workflow by name; no new pipeline name, no `if saved_workflow:` fork.
- **Ports & Adapters** — the new model column edits, router, and FE live in `app.*`/frontend; `app → agents.registry/loader/model_catalog` is the already-legal direction. `lint-imports` stays 4 kept / 0 broken.
- **Additive-migration-only** — `0021` adds 2 nullable columns (+ optional index); no alter of existing columns/constraints; `owner_id`+`workspace_id` already present (stamped on create).
- **Security** — owner-scoped CRUD (IDOR→404); `agent_ids` + `model_overrides` validated at save AND re-validated at launch; no new capability grants (`exec`/`network`/`secrets`/`spawn_subagents` stay OFF).

---

## 8. Exit criteria
- Offline parity+gate suite green (5 goldens byte-identical, with the engine-writer removed) + `lint-imports` 4/0.
- Migration `0021` applies cleanly (additive; `alembic upgrade` head → 0021; downgrade reverts) — no new table.
- `POST/GET/PATCH/DELETE /api/user-workflows` work owner-scoped (cross-owner → 404); save validates `agent_ids`/`base_pipeline_type`/`model_overrides`; the dead `_persist_workflow_definition` writer is gone.
- FE: Save from BOTH the composer and the catalog persists a `source="user"` row; it appears in the catalog "Your workflows" section; rename/duplicate/delete work; launching a saved workflow pre-loads its agents/models and runs through the existing path.
- Tests: backend CRUD + authz (IDOR) + validation tests; a manifest/model-schema-style unit test for the 2 new columns; a **mocked Playwright spec** (compose → Save → appears in "Your workflows" → rename → launch).

**Out of scope:** engine/kernel run-path change; a new table; sharing; non-`custom` base types.

**Canonical refs:** the 3 reuse maps captured this session (BE persistence/run, FE composer/catalog, reuse-vs-new resolver); `.planning/ISSUES-REGISTER.md` (WF-DB-01 / ISS-015 lineage — this is the authoring layer atop the Phase 20 catalog); `.planning/IMPLEMENTATION-REGISTER.md`.
