# 015 — Data Model

Derived from spec.md §4 (Key Entities) and §5 (Screen inventory). No database or API schema
changes — every entity below is a frontend-only routing concept: what a URL identifies and how
it's parsed. Backend entities (`Run`, `WorkflowRun`, `user_workflows`, library rows) are consumed
as-is; nothing here adds a field to any of them.

## Screen

The unit this feature gives a URL to — a distinct view a user can navigate to and stand on.

| Field | Type | Notes |
|---|---|---|
| `mainView` | `string` (enum-like) | The existing state discriminator already used inside `DashboardLayout` today (e.g. `"runs-history"`, `"run-detail"`, `"library"`) — Phase 1 does not invent new names, it makes the EXISTING ones addressable by URL. |
| `path` | `string` | The route pattern that resolves to this `mainView` — see the Route → Screen table below. |
| `ids` | `{ runId?, workflowId?, agentSlug?, ... }` | Optional identifiers a screen needs beyond its `mainView`, extracted from dynamic path segments. |
| `tab` | `string \| undefined` | For screens with sub-tabs (run detail's steps/files/audit/etc.), the active tab, also part of the path. |

## Route → Screen mapping (the single source of truth, both directions)

This table IS the contract Phase 1's catch-all parser and `pathFor` builder both read from — one
table, not two independently maintained functions. (Full list — see spec.md §5 for the grouped
summary and `contracts/route-map.md` for the authoritative, versioned version of this table.)

**Correction (verified against `DashboardLayout.tsx` during implementation kickoff):** `screen`
below is the business-level concept spec.md's Key Entities use — it is NOT a 1:1 alias for
`DashboardLayout`'s actual `MainView` union (`:267`), which is coarser. Several distinct screens
collapse onto the SAME `MainView` value, differentiated by extra fetched/carried state, not by a
different enum case:

- **`execution`** covers the live-streaming view AND the reopened/completed run-detail view
  (Preview/Steps/Files/Audit tabs) AND the fullscreen artifact preview — decided by
  `reopenedRunStatus`/`pipelineState` (state owned by `dashboard/page.tsx`), not a separate
  `MainView`. Opening `/runs/{id}` cold (no in-memory `pipelineState`) means the catch-all must
  **fetch the run by id first** (mirrors `getRunSummary`, confirmed available in `lib/api.ts`)
  and populate that state before `DashboardLayout` will render the right thing — this is the
  real weight behind FR-003's "load from the id/path" requirement, not just a `mainView` set.
- **`composer`** covers both a blank composer (`/workflows/new`) and editing a saved workflow
  (`/workflows/{id}/edit`) — decided by whether `savedComposition` is populated (fetched by id),
  not a separate `MainView`.
- **`history`** is the run list only; opening a specific run from it calls `onSelectWorkflowRun`
  then `setMainView("execution")` — there is no distinct "run-detail" `MainView` to route to.

**Resolved (T4 — traced `handleSelectFeature`/`handleLaunchSaved`/`SavedWorkflowsPage` directly,
not from inference):** the three rows that were TBD/uncertain are settled below.

- `/create/{mode}` and `/workflows/{id}/run` both bifurcate by workflow type rather than landing
  on one `MainView`: `mode`/`base_pipeline_type` `ppt`/`prototype` never touch `DashboardLayout`
  at all — `HomeLaunchGrid.handleClick` (`HomeLaunchGrid.tsx:190-195`, via `selectWorkflowWizardPath`
  in `globalSlice.ts:224-230`) and `handleLaunchSaved`'s ppt/prototype branches
  (`DashboardLayout.tsx:1239-1290`) both `router.push` straight to the separate
  `/workflow/create?mode=…` page (`app/workflow/create/page.tsx` → `LaunchWizard`). Every other
  type resolves to `"input"` (or `"composer"` for `custom`) via `handleSelectFeature`
  (`DashboardLayout.tsx:1187-1191`) / the tail of `handleLaunchSaved`
  (`DashboardLayout.tsx:1316-1322`).
- `/workflows/{id}` (read view) has **no existing `MainView`** to point at — confirmed by reading
  `SavedWorkflowsPage`'s props (`SavedWorkflowsPage.tsx:77-83`): it exposes only `onLaunchSaved`
  and `onCreateNew` (wired at `DashboardLayout.tsx:2446`), no per-row "open"/read-only callback,
  and the card itself has no `onClick`. This screen does not exist yet — Phase 1 must not invent
  a `MainView` for it, it has to be built new.

| Path pattern | `screen` (spec.md concept) | underlying `MainView` | ids | fetch-by-id required? |
|---|---|---|---|---|
| `/dashboard` | home | `"home"` | — | no |
| `/create` | create catalog | `"catalog"` | — | no |
| `/create/{mode}` | create config | `mode ∈ {ppt, prototype}`: **no MainView** — `<LaunchWizard>` rendered directly (`page.tsx:3339-3343` `wizardMode` early-return, not `router.push` to avoid infinite redirect via `next.config.ts` T17). `mode ∈ {app, user-stories}` (anything not wizard-routed and not `custom`): `"input"` via `handleSelectFeature` (`DashboardLayout.tsx:1187-1191`) | `mode` | no |
| `/workflows/new` | blank composer | `"composer"` | — | no |
| `/runs` | run history | `"history"` | — | no |
| `/runs/{id}` | run detail → Preview | `"execution"` (reopened) | `runId` | **yes** — `getRunSummary` |
| `/runs/{id}/steps` | run detail → Steps | `"execution"` (reopened) | `runId` | **yes** |
| `/runs/{id}/steps/{agentId}` | one agent's detail | `"execution"` (reopened) | `runId`, `agentId` | **yes** |
| `/runs/{id}/files` | run detail → Files | `"execution"` (reopened) | `runId` | **yes** |
| `/runs/{id}/audit` | run detail → Audit | `"execution"` (reopened) | `runId` | **yes** |
| `/runs/{id}/stream` | live execution | `"execution"` (live) | `runId` | only if not already the active pipeline run |
| `/runs/{id}/versions/{v}` | specific artifact version | `"execution"` (reopened) | `runId`, `version` | **yes** |
| `/runs/{id}/preview/full` | fullscreen artifact | `"execution"` (reopened) — **no fullscreen flag exists**; renders identically to `/runs/{id}`. Legacy alias, see `contracts/route-map.md`'s note on this row | `runId` | **yes** |
| `/workflows` | saved workflows list | `"saved-workflows"` | — | no |
| `/workflows/{id}` | saved workflow read view | **no existing MainView** — `SavedWorkflowsPage` (`SavedWorkflowsPage.tsx:77-83`, mounted at `DashboardLayout.tsx:2437-2446`) exposes only `onLaunchSaved`/`onCreateNew`, no open/read-only affordance; this screen has to be built new, not routed onto an existing one | `workflowId` | **yes** |
| `/workflows/{id}/edit` | composer editing it | `"composer"` (`savedComposition` populated) | `workflowId` | **yes** — fetch the saved workflow |
| `/workflows/{id}/run` | launch panel pre-filled | After fetching saved workflow to determine `base_pipeline_type` (`page.tsx:3220-3235`): `base_pipeline_type ∈ {ppt, prototype}` → **no MainView**, `<LaunchWizard>` rendered directly via `wizardMode` early-return (`page.tsx:3339-3343`, not `router.push` which loops via T17); `custom` → `"composer"`; everything else → `"input"`, with `savedComposition` pre-populated as the pre-fill | `workflowId` | **yes** |
| `/library` (`?tab=&category=`) | library | `"library"` | — | no |
| `/library/{type}/{slug}` | `library-{type}-detail` | `slug` | — |
| `/settings/{tab}` | `settings` | — | `tab` |
| `/analytics` | `analytics` | — | — |
| `/admin` | `admin` | — | — |

## Run (consumed, not owned)

| Field | Relevance to routing |
|---|---|
| `id` | Addresses `/runs/{id}` and all its sub-views. |
| `status` | Determines whether `/runs/{id}/stream` shows a live connection or redirects/renders the terminal state in place (spec.md edge case: completed/failed/cancelled/diverted). |

## Saved workflow (consumed, not owned)

| Field | Relevance to routing |
|---|---|
| `id` | Addresses `/workflows/{id}`, `/workflows/{id}/edit`, `/workflows/{id}/run`. |

## Library item (consumed, not owned)

| Field | Relevance to routing |
|---|---|
| `type` | One of `agents`/`skills`/`hooks` — the path segment. |
| `slug` | Addresses `/library/{type}/{slug}`. |

## Session / auth state (consumed, not owned)

| Concept | Relevance to routing |
|---|---|
| Authenticated vs. not | Drives FR-002 (root redirect) and FR-009 (deep-link access control). |
| Expired session (401 from any API call) | Drives FR-015's redirect to `/login?expired=1`, centralized in `lib/api.ts` (plan.md Phase 6). |
