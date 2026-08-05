---
inclusion: fileMatch
fileMatchPattern: "frontend/src/components/workflow/**,frontend/src/components/catalog/**,frontend/src/components/savedworkflows/**,frontend/src/app/workflow/**"
---

# Frontend — Workflow Composer & Catalog Domain

> Loaded when editing workflow, catalog, or saved-workflow components. See `invariants.md` for hard constraints.

---

## Launch Surface Map

| Entry point | Component | Route |
|-------------|-----------|-------|
| Home "Build" / "Prototype" cards | `LaunchWizard` | `/workflow/create?mode=prototype\|ppt` |
| Home "Compose custom" | `ComposerPage` | `mainView="composer"` (in-dashboard) |
| Edit saved workflow | `ComposerPage` | `mainView="composer"` via `onLaunchSaved` |
| My Workflows kebab → edit | `ComposerPage` | `mainView="composer"` |
| Inspect a catalog row | `WorkflowDialog` | modal (HomeLaunchGrid row) |

**`ConfigureScreen` + `/workflow/configure` are DELETED** (quick-260713-rcf) — prototype/ppt require template+DS context which only the wizard provides. Do NOT recreate.

---

## `LaunchWizard` Rules (Phase 37)

- Unified prototype + ppt into one mode-keyed page (`?mode=prototype|ppt`) via `MODE_CONFIG` data table.
- `launchDraft.ts` is the **single-source** launch-contract serializer — `buildLaunchDraft` / `buildDiscoveryValue`.
- Both modes' `handleContinue` output proven byte-identical to the retired pages via `launchDraft.parity.test.ts` (12 golden assertions).
- `isChaining` gates `sessionStorage.getItem("chain.source_run_id")` — ONLY read when chaining (BUG-014-A fix).
- `chain.source_run_id` consumed-once via `removeItem` after reading (matches siblings `chain.from`/`chain.brief`).
- Images threaded via `buildLaunchDraft` into the out-of-band `images` field — never concatenated into the brief (D3).

## `ComposerPage` / `AgentsPopup` Lever Rules (Phases 22/41)

- Levers sourced from live `GET /api/capabilities` payload — **never a hardcoded list** (SC-001).
- `applyLeverPatch(selections, agentId, lever, value)` is the shared reducer (single source, INV-12).
- `useAgentCapabilities` fetches + filters `user_allowed` capabilities.
- EMP-04: validator select auto-attaches the `validation` gate — compiler is the server backstop.
- COUPLED_GATE: selecting a validator must couple the gate. `RETRY_OPTIONS=[1,2,3]` (not a bool).
- `AgentModelPicker` standalone is **unmounted** (confirmed dead code). Model selection goes through `AdvancedExpander` levers.
- Canvas view keys the deliverable family on `MODE_CONFIG` data table — **never a workflow-name branch** (SC-001).

## `HomeLaunchGrid` Rules (renamed from `WorkflowCatalog`, Phase 36 D-11)

- "WorkflowCatalog" component rename = `HomeLaunchGrid` (D-11).
- **"Catalogue"** is reserved for a future shared/org marketplace — never label user's own saved workflows with it.
- Launchability = `user_launchable: true` in the manifest — **never a hardcoded name list** (SC-001).
- Two-gate filter: `user_launchable` AND `canRunPipeline(tier, type)`.
- Time estimate: `~Xm` rendered only when `type_avg_duration_sec[row.id]` has a real history entry — never fabricated.
- Agent count: always `~N agents` from `step_count` (safe-cast `agent_count` fallback).

## `SavedWorkflowsPage` Rules (Phase 21/35)

- In-page heading = **"My Workflows"** (D-11 — never "Workflow Catalogue").
- `KebabMenu` hoisted to module scope — NOT defined in render body (causes aria-expanded breakage).
- Kebab CRUD: Rename → `renameUserWorkflow`, Duplicate → `createUserWorkflow "(copy)"`, Delete → `deleteUserWorkflow` + optimistic filter.
- Delete confirmed with `deleteUserWorkflow`, remove from list only on success (not optimistic — WR-04 fix from Phase 21).

## `WorkflowDialog` Rules (Phase 37)

- Read-only compiled-workflow inspector — surfaces declared `context_providers`, deduped per-step gates+validators.
- `user_allowed=false` capabilities render with Lock + "Engineer-only" + `aria-disabled`.
- Mounted from `HomeLaunchGrid` row-level Inspect affordance.

## `AgentsPopup` 4-Tab Agent Drawer (Phase 41)

- Tabs: Overview / Skills / Hooks / Config
- Config tab has `surfaceOnly` prop — omits Edit/Save-override/Revert (ND-7/LOCK-E, durable override persistence is deferred).
- Library drawer variant: `asDrawer` prop → right slide-in (not centered modal).

---

## SC-001 in the Composer

Every render branch keys on a GENERIC discriminator:
- `ResultCard` switches on `cardKind` (clarify/gate/pipeline/deliverable/spec_revision).
- `RunChatLane` composer switches on `RunLaneState`.
- `WorkflowDialog` keys on declared `context_providers` — never `pipeline_type`.
- `HomeLaunchGrid` rows use `row.id` (generic) — never a workflow-name `if` branch.

**Before committing any composer/catalog change:** `grep -rn '"prototype"\|"od_ppt"\|"app_builder"\|"user_stories"' src/components/workflow/ src/components/catalog/` — should return 0 matches in branch logic (display labels are OK).

---

## Fan-Out Composer (Phase 51)

- "Fan out over a list" toggle in `AdvancedExpander` + `CanvasConfigRail`.
- Source picker restricted to `KNOWN_PRODUCERS = ["prototype-plan", "task-list-planner"]` earlier agents.
- Selections carry `{strategy: "fanout_batch", task_source: {parser: "heading_tasks", source_step: "producer"}}`.
- D9 compile guard: source step must be an earlier compiled step — `_validate_fanout_source_upstream` in `compiler.py`.
- NO merge picker / NO `max_parallel` / NO `on_conflict` field (INV-7 — engine decides).
- `task-list-planner` agent is in `PIPELINE_AGENTS["custom"]` (usable) but NOT yet in `/api/agents/library` display catalogue (follow-up needed).
