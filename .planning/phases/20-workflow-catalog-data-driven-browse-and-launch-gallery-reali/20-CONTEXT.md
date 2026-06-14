# Phase 20: Workflow Catalog — Data-Driven Browse-and-Launch - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Source:** PRD Express Path (`.planning/phases/20-workflow-catalog-data-driven-browse-and-launch-gallery-reali/20-SPEC.md`)

<domain>
## Phase Boundary

This phase delivers a **data-driven workflow catalog**: a browse-and-launch gallery that reads the live workflow list from the EXISTING `GET /api/workflows` endpoint, shows only **user-launchable** workflows (a new declared `user_launchable` manifest flag) that the user's tier entitles, and launches each through the EXISTING run flow. It is the SC-001 dividend made visible — **zero engine/kernel edits, no new tables/migrations**.

**In scope:** an additive `user_launchable` (+ `display_name`/`description`/`icon`/`launch_surface`) flag on the workflow manifest schema, surfaced through the existing `GET /api/workflows`; a new frontend catalog view that fetches that list, filters to `user_launchable` ∧ tier, and launches via the existing run/wizard paths — built by REUSING existing UI surfaces.

**Out of scope:** any run-engine/kernel change; a new launch endpoint; new tables/migrations; replacing the prototype/ppt template wizards.
</domain>

<decisions>
## Implementation Decisions

> Every item below is a LOCKED decision (PRD-derived). The authoritative, file:line-grounded detail lives in `20-SPEC.md` — downstream agents MUST read it.

### Reuse mandate (first-class — net-new UI minimized; every new file names its analog)
- The catalog IS a data-driven `CreationHub` — reuse `frontend/src/components/home/CreationHub.tsx` row JSX (`:69-123`), the `handleClick` launch fork (`:27-38`), and tier gating (`canRunPipeline`/`getUpgradeTier`/`Lock`) **verbatim**; replace only the module-const `WORKFLOWS` array (`:15-22`) with rows from the `/api/workflows` fetch.
- Add ONE `"catalog"` value to the `DashboardLayout` `MainView` state machine (`:116`) + ONE `motion.div key="catalog"` view block copied from the home block (`:1047-1059`). NO new Next route — in-dashboard view like Home/Library/History.
- Add a "Catalog" nav button to `AppHeader` copied from the Library button (`:100-110`); extend the `currentPage`/`onNavigate` unions (`:24-25`).
- Copy `AgentModelPicker.tsx` fetch/loading/error/empty shell (`:57,99-114`) for the `/api/workflows` data fetch; `.filter(user_allowed)` → `.filter(user_launchable)`.
- Reuse `entitlements.ts` (`canRunPipeline`/`getRequiredTier`/`getUpgradeTier`/`TIER_LABELS`/`TIER_PIPELINES`) for the tier filter + lock/upgrade decorator.
- Reuse `api.ts` `request<T>`+`authHeaders`+`getCapabilities` idiom for the new fetcher — name it `getWorkflowDefinitions` (NOT `getWorkflows`, which is taken by run-history at `:302`).
- Reuse `workflowChaining.ts` `CHAIN_OPTIONS` (`:35-55`) for wizard-vs-direct routing + wizard paths; reuse `WorkflowHistory.TYPE_META` (`:83-96`) + `useNotifications.WORKFLOW_LABELS` (`:19-32`) for friendly icon+label (never render the raw API `name`).
- Optional richer-page chrome (search/category): lift from `LibraryPage.tsx` (`:403-525`) / `TemplateGallery.tsx` (`:100-247`) — only if warranted; iframe-preview card NOT needed.

### Backend (additive-only — the ENTIRE BE change)
- `backend/agents/workflows/manifest.py`: add `user_launchable: bool = False`, `display_name`/`description`/`icon`/`launch_surface: str | None = None` to the `WorkflowManifest` "Optional with defaults" block (after `version: int = 1`, `:67`); add the 5 keys to `_ALLOWED_TOP_KEYS` (`:80-94`); wire through `_build_manifest` via the existing `_optional_*` helpers.
- `backend/app/api/workflows.py`: add the fields to `WorkflowSummary` (`:65-72`); populate in `list_workflows` (`:200-208`) off the manifest with `display_name or _display_name(id)` fallback; optionally mirror onto `WorkflowDetail`/`get_workflow`.
- Set `user_launchable: true` on the 5 plain-run launchables (`app_builder`, `user_stories`, `custom`, `mulesoft_to_springboot`, `dotnet_to_azure`); `prototype`/`ppt` carry `launch_surface: "wizard"`; everything else stays `false`/unset (revisions, `od_*`, `reverse_engineer`, `chat`).

### Launch wiring (reuse existing paths)
- Idea-box workflows → `onSelectFeature(type)` → `handleSelectFeature` → `IdeaInputPage` → `handleRun` → `handleRunPipeline` → `useWorkflow.startPipeline` (the single `run_pipeline` send site, `useWorkflow.ts:34-101`).
- Wizard workflows (`prototype`/`ppt`) → `router.push("/workflow/{type}/templates")` → existing staged-run machinery (no bare run).

### Two-gate filtering (MUST honor)
- A row is shown iff `user_launchable` (product workflow) AND `can_run_pipeline(user.tier, type)` (this user). Gated-but-launchable workflows render the existing lock/upgrade affordance; fixtures (`sample_*`), `*_revision`, and `od_*` NEVER appear.

### Claude's Discretion
- Exact placement of the "Catalog" nav entry (center nav vs profile dropdown).
- Whether to ship the simple list (data-driven CreationHub) or the richer search/category page (LibraryPage chrome) — default to the simplest reuse that meets the criteria; do not over-build.
- `WorkflowSummary` field population mechanism (load manifest alongside `compile_for_run`, or carry fields onto `CompiledWorkflow`) — pick the lower-risk additive path.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase spec (authoritative, file:line-grounded)
- `.planning/phases/20-workflow-catalog-data-driven-browse-and-launch-gallery-reali/20-SPEC.md` — the locked reuse contract: every reuse target, the additive backend surface + parity proof, workflow inventory, gotchas, invariants, exit criteria.

### Issue/register provenance
- `.planning/ISSUES-REGISTER.md` — ISS-015 / WF-DB-01 (the WONTFIX-by-design entry this phase realizes; the guardrail "manifest-driven picker reads `GET /api/workflows` + a `user_launchable` flag, never a hardcoded dropdown").
- `.planning/IMPLEMENTATION-REGISTER.md` — pointer-first per-phase index (read before touching code to avoid duplication / contradicting locked decisions).

### Reuse anchors (frontend)
- `frontend/src/components/home/CreationHub.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/layout/AppHeader.tsx`, `frontend/src/components/workflow/AgentModelPicker.tsx`, `frontend/src/lib/entitlements.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/workflowChaining.ts`, `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/hooks/useNotifications.ts`.

### Reuse anchors (backend)
- `backend/agents/workflows/manifest.py`, `backend/app/api/workflows.py`, `backend/app/api/capabilities.py` (the sibling pattern), `backend/app/core/entitlements.py`, `backend/agents/registry.py`.

### Invariant tests (must stay green / be extended)
- Characterization goldens (5: prototype/od_prototype/prototype_revision/od_ppt/app_builder); `backend/tests/agents/test_manifest.py`; `backend/tests/.../test_workflows_api.py`; import-linter (`lint-imports`, 4 contracts).
</canonical_refs>

<specifics>
## Specific Ideas

- New FE files: `frontend/src/lib/api.ts` → `getWorkflowDefinitions(token)` (copy `getCapabilities`); `frontend/src/components/catalog/WorkflowCatalog.tsx` (CreationHub rows + AgentModelPicker shell; props `onSelectFeature`+`userTier`).
- New test surface: a mocked Playwright e2e spec under `frontend/e2e/tests/` (filters fixtures/revisions out, renders entitled rows, launches via existing flow); manifest-schema unit test for the 5 new optional fields + strict-key still rejecting `when/if/for/expr`.
- Workflow inventory table (which workflows get `user_launchable`) is in `20-SPEC.md` §5.
</specifics>

<deferred>
## Deferred Ideas

- Richer catalog facets (multi-category sidebar, search) beyond the simple data-driven list — only if the simple reuse proves insufficient.
- Surfacing per-workflow detail pages off `GET /api/workflows/{id}`.
- Any backend run-engine work — explicitly out of scope (the kernel already runs any workflow).
</deferred>

---

*Phase: 20-workflow-catalog-data-driven-browse-and-launch-gallery-reali*
*Context gathered: 2026-06-14 via PRD Express Path*
