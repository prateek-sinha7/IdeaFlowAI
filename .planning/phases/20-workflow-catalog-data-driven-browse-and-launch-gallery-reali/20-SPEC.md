# Phase 20 — Workflow Catalog: Data-Driven Browse-and-Launch (SPEC)

> **Status:** LOCKED spec for planning. Realizes **WF-DB-01** / closes **ISS-015** (logged WONTFIX-by-design in `.planning/ISSUES-REGISTER.md` pending this phase). This is the file:line-grounded reuse contract the planner MUST bind to. Grounded by two read-only reuse-mapping passes (BE + FE) captured 2026-06-14.
>
> **Feed to planning:** `/gsd-plan-phase 20 --prd .planning/phases/20-workflow-catalog-data-driven-browse-and-launch-gallery-reali/20-SPEC.md`

---

## 1. Goal & User Value

Replace the hardcoded home tiles with a **data-driven, auto-updating catalog**: it reads the live workflow list from the EXISTING `GET /api/workflows` endpoint, shows only the **user-ready** workflows (a new declared `user_launchable` manifest flag) that the user's **tier** entitles, and launches each through the EXISTING run flow.

**User value:** a browsable "what can I build?" gallery; new workflows appear automatically when their manifest sets `user_launchable: true`; gated workflows show the existing lock/upgrade affordance instead of a broken button.

**Why it matters architecturally:** this is the **SC-001 dividend** — the kernel already runs any workflow by manifest, so a "launch any workflow" feature needs ZERO engine/kernel edits. It is wiring, not surgery.

---

## 2. Architecture — ZERO kernel/engine change (additive only)

- **No new DB tables, NO migration.** Manifests are version-controlled `workflow.yaml` data; the endpoint is DB-free (`backend/app/api/workflows.py:17-19,160-209` — module docstring states "this router issues no DB query at all"). Q3's "every new table carries `owner_id`+`workspace_id`" is not triggered: there is no new table.
- **No new launch endpoint.** The WS `run_pipeline` path is workflow-agnostic (`backend/app/api/websocket.py:539-609,1394-1408`): it reads `pipeline_type` + optional `agent_ids` from the client message, applies the generic `can_run_pipeline` tier gate, validates `agent_ids` against `allowed_custom_agent_ids`, and dispatches any `SUPPORTED_PIPELINE_TYPES` through the single `ExecutionEngine`.
- **No engine/compiler/registry change.** The new manifest fields are inert discovery metadata, never read by the compiler or kernel.

---

## 3. REUSE MANDATE (FIRST-CLASS REQUIREMENT)

> The planner MUST bind every task to an existing surface. Net-new UI is minimized, and **each new file names the existing analog it is copied from.** The FE has many internal pieces that MUST be reused rather than rebuilt.

### 3.1 Frontend reuse targets (file:line · what · reuse-as)

- **`frontend/src/components/home/CreationHub.tsx`** (tiles `:15-22`, render loop `:69-123`, launch fork `handleClick` `:27-38`, tier gating via `canRunPipeline`/`getUpgradeTier`/`Lock`/"Requires X plan") — the current hardcoded launch surface. **Reuse as:** the catalog IS a data-driven CreationHub. Replace the module-const `WORKFLOWS` array (`:15-22`) with rows mapped from the `/api/workflows` fetch (filtered to `user_launchable` + tier); **keep the row JSX, gating decoration, and `handleClick` routing verbatim.** Single most-reused file.
- **`frontend/src/components/layout/DashboardLayout.tsx`** view state machine (`MainView` type `:116`, `mainView` state `:244`, `AnimatePresence` view blocks `:1046-1289`, `handleNavigate` `:970-972`, home mount `:1057`, `handleSelectFeature` `:661-664`) — each view is a `{mainView === "x" && <motion.div key="x">…}` block switched by one `useState<MainView>`. **Reuse as:** the STRUCTURAL TEMPLATE. Add ONE `"catalog"` value to the union + ONE `motion.div key="catalog"` block copied from the home block (`:1047-1059`). **NO new Next route** — it is an in-dashboard view like Home/Library/History.
- **`frontend/src/components/layout/AppHeader.tsx`** (nav `:88-111`, `currentPage`/`onNavigate` unions `:24-25`, profile dropdown `:197-219`) — the top-nav bar (Home + Library center buttons). **Reuse as:** the entry point. Add a "Catalog" nav button copied from the Library `<button>` (`:100-110`) wired to `onNavigate("catalog")`; extend both closed unions with `"catalog"`. (Placement decision for the planner: center nav vs. dropdown item.)
- **`frontend/src/components/workflow/AgentModelPicker.tsx`** (whole file) — the canonical data-driven palette consumer: mount `useEffect` with `cancelled` guard fetching an auth-gated registry endpoint (`getCapabilities(jwt)` `:57`) → `loading`/`error`/empty triad (`:99-114`) → `.filter(user_allowed)` (`:61`) → render. **Reuse as:** the COPY-FROM template for the catalog's `/api/workflows` fetch+state; mirror the effect, the triad, and `user_allowed`→`user_launchable` one-for-one.
- **`frontend/src/lib/entitlements.ts`** (`canRunPipeline` `:35`, `getRequiredTier` `:39`, `getUpgradeTier` `:46`, `TIER_LABELS` `:23`, `TIER_PIPELINES` `:4-21`, `UPGRADE_PATH` `:29`) — the FE tier→pipeline allow-list + upgrade-path helpers. **Reuse as:** the catalog's tier filter + lock/upgrade decorator, identical to CreationHub usage. (Tier data is FE-only; user tier from `getMe` → `user.tier`, passed as `userTier`.)
- **`frontend/src/lib/api.ts`** (`request<T>` `:78-93`, `authHeaders` `:95-100`, `getToken` `:22-25`, `getCapabilities` `:522-529`) — typed fetch helpers + the registry-fetch idiom. **Reuse as:** author the new manifest fetcher HERE beside `getCapabilities`, reusing `request<T>`+`authHeaders`. **NAME COLLISION:** `getWorkflows` (`:302`) is TAKEN (run-history → `/api/runs`); name the new one `getWorkflowDefinitions` / `listWorkflowManifests`.
- **`frontend/src/lib/workflowChaining.ts`** (`CHAIN_OPTIONS` `:35-55`, `requiresWizard`/`wizardPath`) — the canonical "which workflows need a wizard vs fire directly" table + exact wizard paths. **Reuse as:** the catalog's launch fork reads this instead of re-hardcoding the two `router.push` strings.
- **`frontend/src/components/history/WorkflowHistory.tsx`** `TYPE_META` (`:83-96`) + **`frontend/src/hooks/useNotifications.ts`** `WORKFLOW_LABELS` (`:19-32`) — `WorkflowType → {icon,label}` lookups already covering all user types + revisions. **Reuse as:** the catalog's friendly icon+label source. **Do NOT render the raw API `name`** — it is just `_display_name` title-cased (`Mulesoft To Springboot`).
- **`frontend/src/components/library/LibraryPage.tsx`** (responsive grid `:500`, category sidebar `:421-447`, top search `:403-415`, card `:501-525`) and **`frontend/src/components/workflow/prototype/TemplateGallery.tsx`** (search `:140-152`, category tabs `:100-138`, grid `:205-208`, footer count `:240-247`, empty state `:200-203`) — full data-driven gallery shells. **Reuse as:** IF a richer catalog PAGE with search/category facets is wanted, lift this chrome wholesale (LibraryPage is already a `mainView` block — doubly proves the pattern). The iframe-preview card is NOT needed (workflows have no preview).

### 3.2 New code (minimal — each names its analog)

1. **`getWorkflowDefinitions(token)`** in `frontend/src/lib/api.ts` — copy `getCapabilities` (`:522-529`); returns typed `WorkflowSummary[]` mirroring `backend/app/api/workflows.py:65-72`. (No FE consumer of `GET /api/workflows` exists today — confirmed.)
2. **`frontend/src/components/catalog/WorkflowCatalog.tsx`** — `CreationHub` rows+launch+gating wrapped in `AgentModelPicker`'s fetch/`loading`/`error`/empty shell. Props `onSelectFeature: (type) => void` + `userTier` (identical to CreationHub) so it drops into the same `DashboardLayout` mount. (Richer-page upgrade analog: `LibraryPage` sidebar+grid.)
3. **One `MainView` value + one nav button + one view block** — `"catalog"` added to `DashboardLayout.tsx:116` and `AppHeader.tsx:24-25` unions; a nav button copied from AppHeader's Library button; a `motion.div key="catalog"` block copied from the home block. Pure structural duplication of the existing pattern.

### 3.3 Launch wiring (reuse `CreationHub.handleClick` verbatim)

- **(a) Idea-box workflows** (`user_stories`, `app_builder`, `custom`, `migration`): `onSelectFeature(type)` → `DashboardLayout.handleSelectFeature` (`:661-664`, sets `workflowType` + `mainView="input"`) → `IdeaInputPage` (`:1164-1168`) → user types brief + Run → `IdeaInputPage.handleRun` (`:218-239`) → `onRun(message, agentIds, resolvedType, extraParams)` → `DashboardLayout.handleRunPipeline` (`:673-700`) → `onStartPipeline` (`dashboard/page.tsx:1215-1234`) → `useWorkflow.startPipeline` (`useWorkflow.ts:34-101`) → **the SINGLE `run_pipeline` WS send site** (`useWorkflow.ts:48-98`).
- **(b) Wizard workflows** (`prototype`, `ppt`): `router.push("/workflow/prototype/templates")` / `…/ppt/templates` → wizard collects template + design-system + brief, writes `sessionStorage` (`prototype.draft`/`ppt.draft` + `od_prototype.pending`/`od_ppt.pending`) + `router.push("/dashboard")` (`templates/page.tsx:188-198`) → `dashboard/page.tsx` reads the staged run on WS connect (`:749-807` proto, `:812-869` ppt) → `DashboardLayout` effects (`:579-616` / `:622-658`) fire `onStartPipeline("od_prototype"/"od_ppt", …)` → same `startPipeline`. **The catalog only does the `router.push`; the rest is untouched.**

---

## 4. Backend additive surface (the ENTIRE BE change)

### A1 — Manifest field declaration · `backend/agents/workflows/manifest.py`

Add to the `WorkflowManifest` dataclass "Optional with defaults" block (after `version: int = 1` at `:67`):
```python
user_launchable: bool = False          # ISS-015 / WF-DB-01: surfaces in the user catalog
display_name: str | None = None        # optional UI label (else _display_name fallback)
description: str | None = None         # optional UI blurb
icon: str | None = None                # optional UI icon
launch_surface: str | None = None      # optional: which surface may launch it ("wizard" etc.)
```
Add those 5 key names to `_ALLOWED_TOP_KEYS` (`:80-94`). Wire through `_build_manifest` (`:189-201`) via the existing `_optional_*` helpers (`:230-270`) — `user_launchable` needs a small bool-coerce mirroring `_optional_int`; the string fields reuse optional extraction.

### A2 — Endpoint surfacing · `backend/app/api/workflows.py`

Add the fields to `WorkflowSummary` (`:65-72`); populate in `list_workflows` (`:200-208`) off the manifest (load via `load_manifest(resolve_alias(id), _WORKFLOWS_DIR)` or carry onto `CompiledWorkflow`) with `display_name or _display_name(id)` fallback (`:114-121`). Optionally mirror onto `WorkflowDetail` (`:97-108`) + `get_workflow` (`:267-280`).

### Parity proof (WHY it cannot perturb the 5 goldens — INV-3)

- **Pure read-only discovery metadata.** The compiler (`compiler.py:174-244`) reads only `steps/context_providers/deliverable/planner/clarify/seed_files/allowed_workers/limits` — never these 5 fields → `CompiledWorkflow` byte-identical, run/event path untouched. Same posture as the shipped inert `model`/`limits` forward fields (D-06).
- **Defaults `= False`/`None` ⇒ every existing manifest unchanged.** The 5 golden manifests (`prototype`, `od_prototype`→alias, `prototype_revision`, `od_ppt`, `app_builder`) declare none of these keys → parse to defaults → identical.
- **Strict-key test does not freeze the allow-list.** `test_manifest.py:110` only parametrizes the *rejection* set (`when/if/for/expr`) and asserts each is named in the error — no "only these keys are legal" assertion. Widening `_ALLOWED_TOP_KEYS` breaks neither it nor the well-formed test (`:62-76`). `when/if/for/expr` stay rejected → INV-5 (no DSL) intact.
- **Read endpoint off the golden path.** `test_workflows_api.py:53-159` asserts specific keys + `ids == set(PIPELINE_AGENTS.keys())` only — new optional fields with defaults leave it green.

---

## 5. Workflow inventory (proposed `user_launchable`)

> The endpoint today lists ALL `PIPELINE_AGENTS` keys raw (`registry.py:31-159`) with no flag/tier — the catalog CANNOT render the raw list; it filters on the new flag. `od_prototype` is an alias (not a key, won't appear); `sample_*` are not in `PIPELINE_AGENTS` (already invisible/unrunnable).

| Workflow id | `user_launchable` | Wizard-gated | Notes |
|---|:---:|:---:|---|
| `app_builder` | **true** | no | pro/enterprise; plain-run. Prime candidate. |
| `user_stories` | **true** | no | basic+; plain-run. |
| `custom` | **true** | no | enterprise; **seeds zero agents** → lands on idea page needing AgentsPopup assembly first. |
| `mulesoft_to_springboot` | **true** | no | enterprise (`migration`); plain-run. |
| `dotnet_to_azure` | **true** | no | enterprise (`migration`); plain-run. |
| `prototype` | wizard tile (`launch_surface:"wizard"`) | **yes (template)** | bare type is template-gated-unreachable; launch via Prototype wizard → `od_prototype`. |
| `ppt` / `od_ppt` | wizard tile (`launch_surface:"wizard"`) | **yes (template)** | launch via PPT wizard (template + design-system); never bare run. |
| `reverse_engineer` | **false** | — | empty-steps stub (D-05); not launchable yet. |
| `chat` | **false** | — | internal (`ChatRunner`), not engine-driven. |
| `*_revision` ×5 | **false** | — | revision pipelines — launched only via the revise-artifact path. |
| `od_ppt_revision` | **false** | — | internal dispatch. |
| `sample_wave`/`sample_fanout`/`sample_brownfield` | **n/a** | — | not in `PIPELINE_AGENTS` → already never listed. |

**Net launchable set:** `app_builder`, `user_stories`, `custom`, `mulesoft_to_springboot`, `dotnet_to_azure` (+ `prototype`/`ppt` as wizard tiles). FE additionally filters by `can_run_pipeline(user.tier, …)`.

---

## 6. Critical gotchas the plan MUST honor

1. The endpoint returns ALL raw `PIPELINE_AGENTS` keys today with no flag/tier — the catalog filters on the new `user_launchable` flag, never renders raw.
2. **TWO gates ANDed:** `user_launchable` (is it a product workflow) AND `can_run_pipeline(tier, type)` (may THIS user) — `backend/app/core/entitlements.py:8-30,46-56`; tiers are **basic/pro/enterprise** (no `admin` in that map).
3. `prototype`/`ppt` CANNOT be one-click launched (template + design-system required, `templates/page.tsx` `canContinue` gate) — route to the wizard or re-introduce the broken buttons ISS-015 was WONTFIX'd over.
4. `custom` seeds zero agents → idea page needs AgentsPopup assembly first (not an immediate run).
5. `migration` is a meta-type → one tile; sub-type (`mulesoft_to_springboot`/`dotnet_to_azure`) resolves inside `IdeaInputPage` (`MIGRATION_OPTIONS` `:19-30`).
6. `od_*` are internal dispatch types — never surface as user rows.
7. In-dashboard view, NOT a Next route — do not create `app/catalog/page.tsx`.

---

## 7. Invariants (all proven safe by the BE/FE reuse maps)

- **INV-3 byte/event parity** — the 5 characterization goldens (prototype / od_prototype / prototype_revision / od_ppt / app_builder) MUST stay byte-identical; the new fields are dormant on goldens (defaults, never read by compiler/kernel). The plan MUST run the characterization suite to prove it.
- **SC-001** — launchability keyed on the DECLARED `user_launchable` flag, enumerated generically over `PIPELINE_AGENTS`; NOT a hardcoded name dropdown. The kernel still knows no workflow by name. A brand-new manifest setting `user_launchable: true` joins the catalog with zero code edit.
- **Ports & Adapters** — import-linter stays **4 kept / 0 broken**. Edited files: `agents/workflows/manifest.py` (pure-data, gains no import); `app/api/workflows.py` (already imports `compile_for_run`/`registry`, none forbidden for `app`). No source→forbidden edge created.
- **INV-5** — `_ALLOWED_TOP_KEYS` widened only with non-control-flow presentation/visibility keys; `when/if/for/expr` stay rejected (no DSL).
- **Additive-only** — no new tables, no migration.

---

## 8. Exit criteria

- Offline parity+gate suite green (5 goldens byte-identical) + `lint-imports` 4/0.
- The catalog renders ONLY `user_launchable` ∧ tier-entitled workflows from a live `GET /api/workflows` fetch (no hardcoded name list); fixtures/`*_revision`/`od_*` filtered out.
- Idea-box launches reach the existing single `run_pipeline` send site; `prototype`/`ppt` route to the existing template wizard (no bare run); gated workflows show the existing lock/upgrade affordance.
- A **mocked Playwright e2e spec** under `frontend/e2e/tests/` asserts the catalog filters fixtures/revisions out, renders entitled rows, and launches via the existing flow.
- A manifest-schema unit test covers the 5 new optional fields + strict-key still rejecting control-flow tokens.

**Out of scope:** any run-engine/kernel change; a new launch endpoint; new tables/migrations; replacing the prototype/ppt wizards.

**Canonical refs:** ISS-015 / WF-DB-01 in `.planning/ISSUES-REGISTER.md`; `.planning/IMPLEMENTATION-REGISTER.md`; the BE/FE reuse maps captured 2026-06-14 (this session).
