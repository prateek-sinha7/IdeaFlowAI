# Phase 36: Home + History + My Workflows [B2] - Pattern Map

**Mapped:** 2026-07-09
**Files analyzed:** 8 (2 renamed, 3 modified, 1 new FE page, 1 new BE endpoint, + test/caller files)
**Analogs found:** 6 / 6 (every surface maps to an EXISTING file — no green-field invention)
**Note:** RESEARCH.md absent at map time; file list derived from 36-CONTEXT.md (authoritative surface→file map) + orchestrator's verified caller list.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `frontend/src/components/catalog/HomeLaunchGrid.tsx` (RENAME of `WorkflowCatalog.tsx`) | component (home launcher) | request-response (GET /api/workflows) | itself (pure rename) | exact / in-place |
| Fused Home view (edit `DashboardLayout.tsx` `mainView==="home"` block) | provider/router | event-driven (view switch) | `DashboardLayout.tsx:1420-1431` (home) + `:1545-1574` (input) | exact |
| `frontend/src/components/history/WorkflowHistory.tsx` (MODIFY) | component (list+detail) | CRUD (list/read/delete) | itself | exact / in-place |
| `frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx` (MODIFY) | component (grid+kebab) | CRUD | itself | exact / in-place |
| `frontend/src/components/history/RunDetailPage.tsx` (NEW) | component (detail page) | request-response (run-summary read) | `WorkflowHistory.tsx:382-880` (detail-view half) | role+flow match |
| `backend/app/api/runs.py` — new `GET /{id}/summary` (ADD) | route (read endpoint) | request-response | `runs.py:933-1018` (get_run_family) + `:386-408` (get_run) | exact (owner-gate clone) |

---

## Pattern Assignments

### 1. RENAME `WorkflowCatalog.tsx` → `HomeLaunchGrid.tsx` (D-11)

**Analog:** the file itself. This is a pure grep-all-callers rename, NOT a rewrite. Component IS the home launch grid.

**Baseline:** `grep -c "WorkflowCatalog"` across `frontend/src` = **29 hits in 7 files**. Goal after rename = **0**. Rename touches: the component export/interface/JSDoc, the import specifier `@/components/catalog/WorkflowCatalog` → `@/components/catalog/HomeLaunchGrid`, the identifier `WorkflowCatalog` → `HomeLaunchGrid`, and all comment mentions.

**Per-caller reference map (HOW each file names it — all 7):**

| File | Hits | Reference form (verbatim) | Action |
|------|------|---------------------------|--------|
| `catalog/WorkflowCatalog.tsx` | 4 | JSDoc `:4`; `interface WorkflowCatalogProps` `:44`; `export function WorkflowCatalog({` `:52`; `}: WorkflowCatalogProps)` `:55` | Rename FILE → `HomeLaunchGrid.tsx`; rename fn + `WorkflowCatalogProps`→`HomeLaunchGridProps`; update JSDoc |
| `layout/DashboardLayout.tsx` | 4 | `import { WorkflowCatalog } from "@/components/catalog/WorkflowCatalog";` `:9`; comment `:1413`; JSX `<WorkflowCatalog onSelectFeature={handleSelectFeature} onLaunchSaved={handleLaunchSaved} userTier={userTier} />` `:1429`; comment `:1567` | Repoint import path + specifier; rename JSX tag; update 2 comments |
| `layout/DashboardLayout.waveMount.test.tsx` | 3 | comment `:59`; `vi.mock("@/components/catalog/WorkflowCatalog", () => ({` `:64`; `WorkflowCatalog: () => <div data-testid="stub-workflow-catalog" />,` `:65` | Repoint `vi.mock` path + stub export key |
| `layout/DashboardLayout.catalogHome.test.tsx` | 5 | JSDoc `:4,:7`; test name `:129`; `vi.mock("@/components/catalog/WorkflowCatalog"...` `:52`; stub key `WorkflowCatalog:` `:53` | Repoint `vi.mock` path + stub export key; update test names/JSDoc |
| `catalog/WorkflowCatalog.test.tsx` | 10 | `import { WorkflowCatalog } from "./WorkflowCatalog";` `:68`; `render(<WorkflowCatalog ... />)` ×7 (`:148,:186,:234,:245,:254,:277,:305`); describe strings `:139,:224` | Rename FILE → `HomeLaunchGrid.test.tsx`; repoint import; rename component in renders + describe blocks |
| `savedworkflows/SavedWorkflowsPage.tsx` | 1 | **comment only** `:192` `{/* ── Page header — matches WorkflowCatalog style ── */}` | Update comment text |
| `lib/api.ts` | 2 | **comment only** — JSDoc `:613`, `:629` ("the data-driven WorkflowCatalog renders its rows...") | Update comment text (NO code identifier here) |

**SC-001 guard (routes/page-keys stay GENERIC):** the rename must NOT touch data keys. `DashboardLayout.tsx:173` `type MainView = "home" | ... | "catalog" | "saved-workflows"` — the `"catalog"`/`"home"` page-key STRINGS are generic run-view keys, NOT the component name; leave them. The launch wiring `onSelectFeature={handleSelectFeature}` / `onLaunchSaved={handleLaunchSaved}` (`:1429`) is generic and unchanged.

---

### 2. Fused Home (merge `input` + `home` views into one landing)

**Analog:** `DashboardLayout.tsx` — the two view blocks to fuse:
- **home block** `:1420-1431` — `mainView === "home"` renders `<WorkflowCatalog .../>` (→ `HomeLaunchGrid`) inside a keyed `motion.div key="home"`.
- **input block** `:1545-1574` — `mainView === "input"` renders `<IdeaInputPage workflowType onBack onRun ... workflowId={workflowType} />`.

**Routing pattern to copy** (`DashboardLayout.tsx:807-811` — the seam between them):
```typescript
const handleSelectFeature = useCallback((type: WorkflowType) => {
  setSavedComposition(null);
  setWorkflowType(type);
  setMainView("input");        // ← the home→input hop the fusion collapses/re-frames
}, []);
```
`MainView` union `:173` is the generic page-key registry — any fused/added landing key goes here. `AnimatePresence mode="wait"` at `:1412` wraps every keyed view block; a fused Home follows the same `motion.div key=... initial/animate/exit` idiom (`:1421-1427`).

**Deliverable grid + recents strip:** the launcher grid IS `HomeLaunchGrid` (rows from live `GET /api/workflows`, `WorkflowCatalog.tsx:64-89`). Recents source = the `recentRuns?: WorkflowRun[]` prop already threaded into DashboardLayout (`:68`, `:283`); reuse it, do not add a fetch.

---

### 3. History — `WorkflowHistory.tsx` (MODIFY in place)

**Analog:** itself. All target behaviors already have scaffolding — ADD grouping/sort, do NOT rebuild.

**List fetch + sort source fields** (`:165-173`):
```typescript
getWorkflows(token, { limit: 100 }).then((data) => setRuns(data))
```
`WorkflowRun` fields for Today/Earlier/Older grouping + token/duration sort ALREADY EXIST on each row: `createdAt` (grouping + `formatDate` `:111-123`), `duration` (`formatDuration` `:125-129`), `tokenUsage.total_tokens` (rendered `:485-505`). Group by `createdAt` bucket; sort key off `duration` / `tokenUsage.total_tokens`. No new field, no new fetch.

**KAN-96 click branch — PRESERVE verbatim** (`:175-198`, `handleSelectRun`):
```typescript
if (activeRunId && run.id === activeRunId && onViewRunningPipeline) {
  onViewRunningPipeline();   // running run → live execution view
  return;
}
setSelectedRun(run); ...      // terminal run → detail
```
Wired from `DashboardLayout.tsx:1458-1460`: `activeRunId={pipelineState?.pipelineRunId ?? null}` + `onViewRunningPipeline={() => setMainView("execution")}`.

**KAN-92 titles — do NOT regress:** the list/detail render `run.title` / `selectedRun.title` (`:285`, `:477`), NOT a `Revision:` placeholder. `TYPE_META` `:96-109` supplies the type LABEL only; the async-generated title stays the display string.

**Real delete — already wired** (`:263-276` `handleDeleteConfirm`): `await deleteWorkflow(token, deleteConfirmId)` then `setRuns(prev => prev.filter(...))`. Backed by `DELETE /api/runs/{id}` (`runs.py:411-465`). `DeleteModal` `:1032-1081`. Kebab open state `openMenuId` `:151`.

**Sibling test files that LOCK behavior** (find + do not break):
```
frontend/src/components/history/WorkflowHistory*.test.tsx  (+ RevisionFamilyView tests)
```
Grouping helpers live in the sibling `./RevisionFamilyView` (`groupRunsByFamily`, `baseWorkflowType`, `VersionTimeline`, `FamilyGroupCard`), imported `:38` — extend there, not inline.

---

### 4. My Workflows — `SavedWorkflowsPage.tsx` (MODIFY: label rename + real kebab)

**Analog:** itself. Kebab actions are ALREADY real (not static text) — verify + relabel.

**Label rename (D-11 — "Catalogue" is RESERVED, drop it here)** `:200-206`:
```tsx
<h1 ...>Workflow Catalogue</h1>       // ← rename to "My Workflows"
<p ...>Your saved custom workflows — launch, manage and reuse them.</p>
```
Also the delete-copy `:372` "removed from your catalogue" and comment `:192`.

**Real kebab actions — already implemented** (`KebabMenu` `:151-186`): Rename → `setRenameRow(row)` (`handleRenameSave` `:118-126`, `renameUserWorkflow`), Duplicate → `handleDuplicate` `:128-139` (`createUserWorkflow`), Delete → `setDeleteConfirmId` (`handleDeleteConfirm` `:141-148`, `deleteUserWorkflow`). Each does an optimistic `setUserWorkflows`. This is the working pattern; the phase task is to confirm parity, not rebuild.

---

### 5. Run detail/reopen page (NEW-BUILD `RunDetailPage.tsx`)

**Closest FE analog:** the detail-view HALF of `WorkflowHistory.tsx:382-880` (the `if (selectedRun) { ... }` branch). Copy its anatomy:
- Left sidebar: back button `:460-465`, run header (icon/label/status badge) `:466-482`, **KPI token strip** `:485-505` (`fmt()` M/K formatter, total/input/output from `tokenUsage`), **per-agent breakdown** `:508-566` (`detailAgentOutputs` dedup memo `:303-336` → `<details>` cards with duration + `total_tokens`), suggested-next-steps footer `:568-669`.
- Main panel: `VersionTimeline` (**version/revision timeline**) `:676-681`, tab bar `:683-733`, tabbed content `:736-870`.
- **Failure banner:** `DegradedRunAffordance` (imported `:22` from `preview/PreviewPanel`), gated on persisted status `:436-439` (`reopenTerminalFailure = status ∈ {failed,cancelled,degraded}`), failed-agent ids via `parseFailedAgentIds(selectedRun.error)` `:444` + `buildAgentNameById` `:450-452`.

**Detail data fetch pattern** (`:189-197`): `getWorkflow(token, run.id)` → `setSelectedRun(full)`. Family via `getRunFamily(token, selectedRun.rootRunId)` `:203-220`. **Reuse Phase-32 `components/ui/` primitives + Phase-35 shell chrome** for the page frame (D-15 reskin-look/keep-behavior) — do NOT fork the palette.

**Closest BACKEND analog for the run-summary read:** `runs.py` `get_run` `:386-408` + `get_run_family` `:933-1018`.

---

### 6. run-summary endpoint — `GET /api/runs/{id}/summary` (ADD to `runs.py`)

**Analog to clone (owner-gate + shape):** `get_run_family` `:933-1018` and the shared gate `_owner_gate_or_404` `:1068-1085`.

**Owner-scope pattern — clone verbatim** (`runs.py:1075-1085`, docstring `:14-17`):
```python
workflow_run = (
    db.query(WorkflowRun)
    .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == user_id)  # NOT owner_id
    .first()
)
if not workflow_run:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
```
IDOR → 404 (never 403, never a cross-owner 200). Key on `WorkflowRun.user_id == current_user.id`, NEVER the nullable `owner_id` (CONTEXT INVARIANT + model `:20` vs `:58`).

**Response schema idiom to copy:** `WorkflowRunResponse` `:88-120` (`model_config = {"from_attributes": True}`) / `RunFamilyResponse` `:926-931`. Additive `BaseModel` — no engine/golden touch (INV-3).

**Every run-summary datum → its EXISTING column/route (DO NOT INVENT FIELDS):**

| run-summary datum | Existing source | Ref |
|-------------------|-----------------|-----|
| owner gate key | `WorkflowRun.user_id` | model `:20`; gate `runs.py:1077` |
| title | `WorkflowRun.title` | model `:21` |
| status (incl. `degraded`) | `WorkflowRun.status` | model `:22-29` |
| failure banner text | `WorkflowRun.error` | model `:35` |
| per-agent breakdown | `WorkflowRun.agent_outputs` (JSON array) | model `:32`; parsed pattern `runs.py:500-506` / FE `WorkflowHistory.tsx:303-336` |
| agent count | `WorkflowRun.agent_count` | model `:33` |
| duration KPI | `WorkflowRun.duration` | model `:34` |
| token KPIs (total/input/output) | `WorkflowRun.token_usage` (JSON) | model `:36` |
| created / completed timestamps | `WorkflowRun.created_at`, `completed_at` | model `:38-41` |
| version/revision timeline (family) | `parent_run_id` → `get_run_family` walk | model `:46`; `runs.py:933-1018` |
| deliverable shape | `deliverable_mimetype`, `deliverable_filename` | model `:72-73` |

Aggregation-only over ONE owned row (+ optional family walk). **No new table, additive migrations only (Q3 — none needed).** Register the route with `@router.get("/{workflow_id}/summary", response_model=...)` following `:933`. Verify with `/opt/homebrew/bin/lint-imports` (4/0) + targeted pytest (offline; never full pytest — it hangs).

---

## Shared Patterns

### Owner-scoped read gate (all run-summary + detail reads)
**Source:** `runs.py:1068-1085` (`_owner_gate_or_404`) — reuse the helper directly, don't re-implement.
**Apply to:** the new `GET /{id}/summary`.
```python
_owner_gate_or_404(db, workflow_id, current_user.id)   # → WorkflowRun or 404
```

### Cancellable mount-fetch (all FE list/detail loads)
**Source:** `WorkflowCatalog.tsx:64-89` / `SavedWorkflowsPage.tsx:98-108` — `let cancelled=false` guard + `getToken()` early-out + `.then/.catch/.finally(setLoading)` + cleanup `return () => { cancelled = true }`.
**Apply to:** `RunDetailPage.tsx` summary fetch; any new Home recents fetch.

### Optimistic list mutation after write
**Source:** `WorkflowHistory.tsx:270` + `SavedWorkflowsPage.tsx:146` — `await mutate(...)` then `setState(prev => prev.filter/map(...))`.
**Apply to:** History delete, My Workflows kebab actions.

### Token/duration formatters (KPI display)
**Source:** `WorkflowHistory.tsx:125-129` (`formatDuration`), `:492` (`fmt` M/K), `:111-123` (`formatDate`); `SavedWorkflowsPage.tsx:41-64` (`formatRelativeDate`/UTC-normalize).
**Apply to:** RunDetailPage KPI strip + History group headers.

### Kebab dropdown + AnimatePresence menu
**Source:** `SavedWorkflowsPage.tsx:151-186` (canonical `KebabMenu`) and `WorkflowHistory.tsx:151` `openMenuId` state + outside-click catcher `:1024-1027`.
**Apply to:** History row kebab, My Workflows.

### Delete-confirm modal (a11y)
**Source:** `WorkflowHistory.tsx:1032-1081` (`DeleteModal`) / `SavedWorkflowsPage.tsx:353-387`.
**Apply to:** any new delete affordance; add keyboard/aria per CONTEXT a11y invariant.

---

## No Analog Found

None. Every Phase-36 surface maps to an existing file or an in-file clone. The only NEW artifacts (`RunDetailPage.tsx`, `GET /{id}/summary`) have strong in-repo analogs listed above — no RESEARCH.md fallback required.

---

## Metadata

**Analog search scope:** `frontend/src/components/{catalog,history,savedworkflows,layout}`, `frontend/src/lib/api.ts`, `backend/app/api/runs.py`, `backend/app/models/workflow.py`.
**Rename caller scope verified:** `grep -rn "WorkflowCatalog" frontend/src` = 29 hits / 7 files (2 files are comment-only: `SavedWorkflowsPage.tsx`, `api.ts`).
**Pattern extraction date:** 2026-07-09
