# Phase 20: Workflow Catalog — Data-Driven Browse-and-Launch - Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 11 (2 new FE, 4 modified FE, 2 reuse-only FE tables, 3 modified BE, N manifest YAMLs, 2 test files)
**Analogs found:** 11 / 11 (all named in 20-SPEC; verified live, drift corrected — see Metadata)

> REUSE-FIRST PHASE. Every excerpt below is the real load-bearing code to copy/adapt. Anchors are `file:line`. "Net-new styling is a defect" (UI-SPEC §0) — inherit Tailwind classes verbatim from the analog.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `frontend/src/lib/api.ts` (`getWorkflowDefinitions` + `WorkflowSummary`) | api-client | request-response (GET) | `getCapabilities` `api.ts:522-529` | exact |
| `frontend/src/components/catalog/WorkflowCatalog.tsx` (NEW) | component | request-response + render | `CreationHub.tsx` (rows/launch/gating) + `AgentModelPicker.tsx` (fetch shell) | exact (two-analog graft) |
| `frontend/src/components/layout/DashboardLayout.tsx` (MODIFY) | layout/state-machine | event-driven (view switch) | its own `home` block `:1047-1059` | exact (self-template) |
| `frontend/src/components/layout/AppHeader.tsx` (MODIFY) | nav | event-driven (onNavigate) | its own Library button `:100-110` | exact (self-template) |
| `frontend/src/lib/entitlements.ts` (REUSE) | utility | pure-fn | — (consumed, not edited) | n/a |
| `frontend/src/lib/workflowChaining.ts` + `WorkflowHistory.TYPE_META` + `useNotifications.WORKFLOW_LABELS` (REUSE) | lookup tables | pure-data | — (consumed) | n/a |
| `backend/agents/workflows/manifest.py` (MODIFY) | model/dataclass | transform (parse) | existing `version`/`model` optional fields + `_optional_int` | exact |
| `backend/app/api/workflows.py` (MODIFY) | controller | request-response (GET) | `WorkflowSummary`/`list_workflows` + `capabilities.py user_allowed` | exact |
| `backend/agents/workflows/<id>/workflow.yaml` (DATA) | config | pure-data | existing top-key block | exact |
| `backend/tests/agents/test_manifest.py` (MODIFY) | test | n/a | well-formed `:62-76` + strict-key `:110-120` | exact |
| `frontend/e2e/tests/ts-t.catalog.spec.ts` (NEW) | test | n/a | `ts-i.agent-panels.spec.ts` | exact (harness) |

---

## Pattern Assignments

### 1. `frontend/src/lib/api.ts` — `getWorkflowDefinitions` + `WorkflowSummary` (api-client, GET)

**Analog:** `getCapabilities` (`api.ts:522-529`), `request<T>` (`:78-93`), `authHeaders` (`:95-100`).

**Copy this fetcher verbatim, rename `getCapabilities`→`getWorkflowDefinitions`, path→`/api/workflows`** (`api.ts:522-529`):
```typescript
export async function getCapabilities(token: string): Promise<CapabilitiesPalette> {
  return request<CapabilitiesPalette>("/api/capabilities", {
    method: "GET",
    headers: authHeaders(token),
  });
}
```

**New type — mirror the BE `WorkflowSummary` (post-edit) `workflows.py:65-72`:**
```typescript
export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  step_count: number;
  steps: { agent_id: string; name: string; gate: string | null }[];
  user_launchable: boolean;   // NEW (BE A2)
  display_name?: string | null;
  icon?: string | null;
  launch_surface?: string | null;
}
```

**Changes vs analog:** name (`getCapabilities`→`getWorkflowDefinitions` — `getWorkflows` at `:302` is TAKEN by run-history → `/api/runs`); path; return type. Nothing else.

---

### 2. `frontend/src/components/catalog/WorkflowCatalog.tsx` — NEW (component; two-analog graft)

**Analog A — fetch+state shell:** `AgentModelPicker.tsx` mount effect (`:48-74`) + loading/error/empty triad (`:99-114`).

Copy the effect skeleton verbatim, swap `getCapabilities`→`getWorkflowDefinitions`, `model_catalog.filter(m=>m.user_allowed)`→`.filter(w=>w.user_launchable)` (`AgentModelPicker.tsx:48-74`):
```typescript
useEffect(() => {
  let cancelled = false;
  const jwt = token ?? getToken();
  if (!jwt) { setError("Not authenticated."); setLoading(false); return; }
  setLoading(true);
  getWorkflowDefinitions(jwt)
    .then((rows) => {
      if (cancelled) return;
      setWorkflows(rows.filter((w) => w.user_launchable));   // gate 1: product flag
      setError(null);
    })
    .catch((e) => { if (!cancelled) setError(e?.message ?? "Failed to load workflows."); })
    .finally(() => { if (!cancelled) setLoading(false); });
  return () => { cancelled = true; };
}, [token]);
```
Loading/error/empty triad to copy (`AgentModelPicker.tsx:99-114`) — reuse the exact classes (`text-[11px] text-gray-400 py-2`, the red error box). Empty = no row passes `user_launchable ∧ tier`.

**Analog B — row JSX + launch + gating:** `CreationHub.tsx` render loop (`:69-123`), `handleClick` (`:27-38`), gating (`:71-72`).

Copy the row `<button>` JSX `:80-119` VERBATIM (icon-left/title/subtitle/lock/chevron, all classes). Copy `handleClick` (`CreationHub.tsx:27-38`) — but read wizard routing from `workflowChaining` instead of the two hardcoded `router.push` strings (SPEC §3.3):
```typescript
const handleClick = (type: WorkflowType) => {
  if (!canRunPipeline(userTier, type)) return;        // gate 2: tier
  const opt = CHAIN_OPTIONS.find((o) => o.type === type);
  if (opt?.requiresWizard && opt.wizardPath) { router.push(opt.wizardPath); return; }
  if (type === "prototype") { router.push("/workflow/prototype/templates"); return; }
  if (type === "ppt") { router.push("/workflow/ppt/templates"); return; }
  onSelectFeature(type);
};
```
Per-row gating decoration to copy (`CreationHub.tsx:71-72,89,104-108`):
```typescript
const allowed = canRunPipeline(userTier, workflow.type);
const upgradeTo = getUpgradeTier(userTier, workflow.type);
// ...{!allowed && <Lock .../>}... and "Requires {TIER_LABELS[upgradeTo]} plan"
```

**Friendly icon+label (NEVER raw API `name`)** — map from `TYPE_META` (`WorkflowHistory.tsx:83-96`) / `WORKFLOW_LABELS` (`useNotifications.ts:19-32`). The `WORKFLOWS` module-const array (`CreationHub.tsx:15-22`) is DELETED — rows come from the fetch, with `label = display_name ?? WORKFLOW_LABELS[id] ?? TYPE_META[id].label`.

**Props (identical to CreationHub so it drops into the same mount):**
```typescript
interface WorkflowCatalogProps { onSelectFeature: (type: WorkflowType) => void; userTier?: Tier; }
```

**Changes vs analogs:** data source (live fetch, not `WORKFLOWS` const); two-gate filter (`user_launchable` ∧ `canRunPipeline`); wizard routing via `CHAIN_OPTIONS`; friendly label via lookup tables. JSX/classes/gating UNCHANGED.

---

### 3. `frontend/src/components/layout/DashboardLayout.tsx` — MODIFY (self-template)

**Analog:** the `home` view block (`:1047-1059`), `MainView` union (`:116`), `handleSelectFeature` (`:661-664`).

Add `"catalog"` to the union (`:116`):
```typescript
type MainView = "home" | "library" | "history" | "settings" | "analytics" | "input" | "execution" | "catalog";
```
Add a `motion.div key="catalog"` block — copy the home block `:1048-1059` verbatim, swap key/condition + mount `WorkflowCatalog` (the home mount is `:1057`):
```tsx
{mainView === "catalog" && (
  <motion.div key="catalog" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="h-full">
    <WorkflowCatalog onSelectFeature={handleSelectFeature} userTier={userTier} />
  </motion.div>
)}
```
`handleSelectFeature` (`:661-664`) is REUSED AS-IS (sets `workflowType` + `mainView="input"`) — the catalog's idea-box launches flow through it exactly like CreationHub. `handleNavigate`/`onNavigate` already accepts the view name; ensure `"catalog"` is routed to `setMainView("catalog")`.

**Changes vs analog:** one union member, one view block, one mount. Pure structural duplication.

---

### 4. `frontend/src/components/layout/AppHeader.tsx` — MODIFY (self-template)

**Analog:** the Library `<button>` (`:100-110`), the two closed unions (`:24-25`).

Copy the Library button verbatim, swap `library`→`catalog`, icon, label (`AppHeader.tsx:100-110`):
```tsx
<button
  onClick={() => onNavigate("catalog")}
  className={`flex items-center gap-1 sm:gap-1.5 rounded-md px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium transition-all ${
    currentPage === "catalog" ? "bg-white text-gray-900" : "text-gray-400 hover:text-white border border-transparent"
  }`}
>
  <LayoutGrid className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
  <span className="hidden sm:inline">Catalog</span>
</button>
```
Extend BOTH unions (`AppHeader.tsx:24-25`) with `"catalog"`:
```typescript
currentPage: "home" | "library" | "workflow" | "execution" | "history" | "analytics" | "catalog";
onNavigate: (page: "home" | "library" | "history" | "settings" | "analytics" | "catalog") => void;
```
Import a new icon from lucide-react (the existing block is `:5-16`; `LayoutGrid` is a fitting catalog glyph).

**Changes vs analog:** one button, `+"catalog"` on two unions, one icon import. Style indistinguishable from Home/Library (UI-SPEC §5).

---

### 5. `frontend/src/lib/entitlements.ts` — REUSE (no edit)

Signatures the catalog calls (do not change):
```typescript
export function canRunPipeline(tier: Tier, pipelineType: string): boolean   // :35  — gate 2
export function getUpgradeTier(currentTier: Tier, pipelineType: string): Tier | null  // :46 — lock decorator
export const TIER_LABELS: Record<Tier, string>  // :23 — "Requires {Basic|Pro|Enterprise} plan"
```
Tier source: `getMe` → `user.tier`, passed down as `userTier`. Tiers are **basic/pro/enterprise** only (no `admin`).

---

### 6. Reuse lookup tables (no edit) — routing + labels

`workflowChaining.ts` `CHAIN_OPTIONS` (`:35-55`) — `{type,label,requiresWizard,wizardPath}`; `ppt`/`prototype` carry `requiresWizard:true` + `wizardPath`. The catalog's launch fork reads this (see §2 `handleClick`).
`WorkflowHistory.tsx TYPE_META` (`:83-96`) and `useNotifications.ts WORKFLOW_LABELS` (`:19-32`) — `id → {icon,label}` / `id → label`, already covering all launchable ids (`user_stories`/`app_builder`/`custom`/`mulesoft_to_springboot`/`dotnet_to_azure`/`prototype`/`ppt`). Use for friendly display — NEVER render the raw API `name`.

---

### 7. `backend/agents/workflows/manifest.py` — MODIFY (additive dataclass + parser)

**Analog:** the existing optional `version: int = 1` (`:67`) + forward `model`/`limits` (`:70-71`); `_optional_int` bool-reject idiom (`:259-270`); `_ALLOWED_TOP_KEYS` literal (`:80-94`); `_build_manifest` extraction+construction (`:180-201`).

Add to the "Optional with defaults" block after `version: int = 1` (`:67`) — SPEC §4 A1:
```python
user_launchable: bool = False
display_name: str | None = None
description: str | None = None
icon: str | None = None
launch_surface: str | None = None
```
Add the 5 names to `_ALLOWED_TOP_KEYS` (`:80-94`) — copy the existing literal entries (e.g. `"version",`).

Add a bool-coerce helper modeled on `_optional_int` (`:259-270`) — `bool` is NOT an int subclass trap here; accept only real bools:
```python
def _optional_bool(data: dict, key: str, file_str: str, default: bool) -> bool:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ManifestValidationError(
            f"{file_str}: field '{key}' must be a boolean, got "
            f"{type(value).__name__!r} ({value!r})"
        )
    return value
```
For the 4 string fields, add an `_optional_str` (mirror `_optional_int` returning `str | None`, default `None`). Then wire in `_build_manifest` extraction (`:180-187`) and pass into the constructor (`:189-201`) alongside `version=...`.

**Changes vs analog:** 5 new fields, 5 new allow-list entries, 2 new `_optional_*` helpers, 5 new extraction lines + 5 constructor kwargs. INERT — never read by compiler/kernel (parity proof SPEC §4).

---

### 8. `backend/app/api/workflows.py` — MODIFY (controller surfacing)

**Analog:** `WorkflowSummary` (`:65-72`), `list_workflows` population (`:200-208`), `_display_name` fallback (`:114-121`); sibling per-item trust flag `capabilities.py user_allowed` (`:61,115`).

Add to `WorkflowSummary` (`:65-72`):
```python
user_launchable: bool = False
display_name: str | None = None
icon: str | None = None
launch_surface: str | None = None
```
Populate in `list_workflows` (`:200-208`). Load the manifest alongside the existing `compile_for_run(workflow_id)` (lower-risk additive path, per CONTEXT Discretion) and mirror the `capabilities.py` per-row flag idiom (`is_user_allowed(kind,name)` → here `manifest.user_launchable`):
```python
manifest = load_manifest(resolve_alias(workflow_id), _WORKFLOWS_DIR)  # additive read
out.append(
    WorkflowSummary(
        id=workflow_id,
        name=_display_name(workflow_id),
        description=manifest.description or _describe(workflow_id, step_specs),
        step_count=len(compiled.steps),
        steps=steps,
        user_launchable=manifest.user_launchable,
        display_name=manifest.display_name or _display_name(workflow_id),  # :114-121 fallback
        icon=manifest.icon,
        launch_surface=manifest.launch_surface,
    )
)
```
Capabilities sibling pattern (per-item trust flag, `capabilities.py:111-117`):
```python
CapabilityEntry(kind=kind, name=name, user_allowed=registry.is_user_allowed(kind, name), config_schema={})
```

**Changes vs analog:** 4 new response fields, 1 manifest read, 4 populated kwargs. Endpoint stays DB-free + off the golden path (`test_workflows_api` green — SPEC §4).

---

### 9. `backend/agents/workflows/<id>/workflow.yaml` — DATA (add keys)

**Analog:** any existing manifest top-key block (all share `id`/`version`/`planner`/`clarify`/`deliverable`/`context_providers`/`seed_files`/`steps`).

Exact dirs confirmed present under `backend/agents/workflows/`: `app_builder/`, `user_stories/`, `custom/`, `mulesoft_to_springboot/`, `dotnet_to_azure/` (the 5 plain-run launchables) + `prototype/`, `ppt/` (wizard tiles). `od_prototype` is an ALIAS dir (resolves to `prototype`); `*_revision`/`od_*`/`reverse_engineer`/`chat`/`sample_*` get NOTHING.

Add to each launchable (e.g. `app_builder/workflow.yaml`, top key block):
```yaml
user_launchable: true
```
For `prototype/workflow.yaml` and `ppt/workflow.yaml` ADDITIONALLY:
```yaml
user_launchable: true
launch_surface: "wizard"
```
Optionally `display_name`/`description`/`icon` per workflow. All others: leave the keys ABSENT (default `False`/`None` → parity-safe).

**Changes vs analog:** 1–4 new top keys per launchable manifest; zero changes to step/deliverable/clarify (goldens stay byte-identical).

---

### 10. `backend/tests/agents/test_manifest.py` — MODIFY/ADD

**Analog:** well-formed test (`:62-76`) + strict-key rejection test (`:110-120`); `_WELL_FORMED` const (`:31-46`).

New-field test — copy the `test_loads_well_formed_manifest` shape (`:62-76`), feeding a manifest that declares the 5 keys, asserting they parse:
```python
def test_loads_optional_catalog_fields(tmp_path: Path):
    doc = _WELL_FORMED + (
        "user_launchable: true\n"
        "display_name: Demo Workflow\n"
        "description: A demo\n"
        "icon: rocket\n"
        "launch_surface: wizard\n"
    )
    base = _write_manifest(tmp_path, "demo", doc)
    m = load_manifest("demo", base)
    assert m.user_launchable is True
    assert m.display_name == "Demo Workflow"
    assert m.launch_surface == "wizard"
```
Add a default test (absent keys → `False`/`None`) and a bool-type-reject test (mirror `_optional_int`'s reject). The strict-key rejection test (`:110-120`) is PRESERVED UNCHANGED — `when/if/for/expr` must still raise (proves INV-5 holds after widening the allow-list).

**Changes vs analog:** +2/3 new tests; existing strict-key + well-formed tests untouched.

---

### 11. `frontend/e2e/tests/ts-t.catalog.spec.ts` — NEW (mocked Playwright)

**Analog:** `ts-i.agent-panels.spec.ts` (header `:1-12`), the mock-API harness (`mockApi.ts:130-180`).

Header + harness import (copy `ts-i.agent-panels.spec.ts:5-6`):
```typescript
import { test, expect } from "../fixtures/test";   // mocks auto-installed
```
Mock the new endpoint — the REST stub routes `**/api/**` via `MockApi.handle` (`mockApi.ts:180`); add a `**/api/workflows` row to the controller's `handle()` chain (sibling of the `/api/capabilities` line `:141`), or per-spec override via `page.route`. Fixture gotcha: mock-API is `page.route("**/api/**")` (in-browser), and selectors are TEXT-based (almost NO `data-testid`) — assert on the friendly label, e.g.:
```typescript
test("TS-T catalog filters + launches", async ({ dashboard, page }) => {
  await dashboard.goto();
  // navigate to Catalog nav button, then:
  await expect(page.getByText("App Builder")).toBeVisible();           // entitled launchable shown
  await expect(page.getByText("User Stories (Revised)")).toHaveCount(0); // *_revision filtered out
  await page.getByText("Generate product requirements").click();        // launch → idea page (existing flow)
});
```
The `/api/workflows` mock must return rows with `user_launchable` set so the spec proves the filter (entitled rows render; `*_revision`/`od_*`/fixtures absent).

**Changes vs analog:** new `/api/workflows` mock route; text-based assertions on friendly labels; no WS needed for the filter/render test (the launch handoff is the existing flow ts-i already covers).

---

## Shared Patterns

### Two-gate filtering (applies to WorkflowCatalog + workflows.py)
`user_launchable` (manifest flag, BE) AND `canRunPipeline(tier, type)` (FE entitlements `:35`). Gated-but-launchable rows render the lock/upgrade affordance (`CreationHub.tsx:104-117`), never hidden. Fixtures (`sample_*` — not in `PIPELINE_AGENTS`), `*_revision`, `od_*` NEVER pass gate 1.

### Auth-gated GET fetch (applies to api.ts + WorkflowCatalog)
`request<T>` + `authHeaders(token)` (`api.ts:78-100`); mount `useEffect` with `cancelled` guard + loading/error/empty triad (`AgentModelPicker.tsx:48-74,99-114`). The canonical data-driven-palette-consumer pattern.

### Additive-only manifest field (applies to manifest.py + workflows.py + YAMLs)
New fields default `False`/`None`, never read by compiler/kernel → 5 goldens byte-identical (INV-3); allow-list widened only with presentation/visibility keys → `when/if/for/expr` stay rejected (INV-5). No new table/migration.

### Friendly label, never raw `name` (applies to WorkflowCatalog + e2e spec)
`display_name ?? WORKFLOW_LABELS[id] ?? TYPE_META[id].label` — the raw API `name` is just `_display_name` title-cased (`workflows.py:114-121`) and must not reach the user (UI-SPEC §4).

---

## No Analog Found

None. Every file has a verified existing analog (this is the SC-001 reuse dividend).

---

## Metadata

**Analog search scope:** `frontend/src/{lib,components,hooks}`, `frontend/e2e/{tests,fixtures}`, `backend/{agents/workflows,app/api,tests/agents}`.
**Drift corrected vs the prompt's line cites:**
- `AppHeader` imports lucide icons at `:5-16` (the prompt's `:100-110` is the Library button itself — correct; icon import lives in the top block).
- `DashboardLayout` `MainView` already includes `"input"` and `"execution"` (prompt cited only `:116` — confirmed, full union is at `:116`).
- `WorkflowSummary` BE currently has NO `display_name`/`icon` fields (`:65-72` is `id/name/description/step_count/steps` only) — the prompt's "add fields" is correct; there is no pre-existing `display_name` field to mirror, only the `_display_name()` HELPER (`:114-121`).
- e2e: confirmed only `ts-i.agent-panels` and `ts-q.terminal-states` exist among the candidates; `ts-i` is the stronger harness exemplar (mockApi + dashboard page object). Suggested new file name `ts-t.catalog.spec.ts` (next free letter).
- Manifest dirs verified to physically exist for all 5 launchables + `prototype`/`ppt`; `od_prototype` is alias-resolved (no own row).
**Pattern extraction date:** 2026-06-14
