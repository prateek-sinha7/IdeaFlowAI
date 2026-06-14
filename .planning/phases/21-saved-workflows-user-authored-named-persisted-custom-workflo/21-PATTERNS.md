## PATTERN MAPPING COMPLETE

# Phase 21: Saved Workflows — Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 14 (6 backend incl. 2 modify + 1 delete, 6 frontend, 2 test surfaces)
**Analogs found:** 14 / 14 (all line anchors verified against live code; alembic head confirmed = `0020`)

**Reuse posture (LOCKED, 21-SPEC §2):** This phase invents NO new pattern. The persistence spine REUSES the dormant `workflows` table (`WorkflowDefinition`); every new file below adapts an established analog. Copy the excerpt, change only what the "What changes" note says.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/app/models/workflow_definition.py` (MODIFY +2 cols) | model | — | its own existing columns (`:38-40`) | exact (self) |
| `backend/alembic/versions/0021_saved_user_workflows.py` (NEW) | migration | batch_alter additive | `0020_wave_runs.py` + `0017_repositories_repo_workspace.py:60-63` | role-match (no batch-add-column precedent → see note) |
| `backend/app/api/user_workflows.py` (NEW) | route/controller | CRUD (owner-scoped) | `runs.py` (list/get/delete + IDOR→404) + `mcp.py:220-234` (create idiom) | exact |
| `backend/app/main.py` (MODIFY) | config | — | `main.py:17,160` (runs_router) | exact |
| `backend/agents/execution_engine/engine.py` (REMOVE) | engine | delete dead writer | self `:4026-4108` + call `:1381-1386` | exact (deletion) |
| validation reuse (in `user_workflows.py` POST) | utility | validation | `websocket.py:95-155,1394-1406` + `registry.py:331-395` + `ModelCatalog().ids()` | exact |
| `backend/tests/unit/test_user_workflows.py` (NEW) | test | — | `test_runs_api.py:38-100` | exact |
| `frontend/src/lib/api.ts` (NEW fetchers + type) | utility | request-response | `getWorkflowDefinitions:557-564`, `adminCreateUser:454-466`, `adminUpdateTier:442-452`, `adminDeleteUser:468-481`, `WorkflowSummary:539-549` | exact |
| `frontend/src/components/catalog/NameWorkflowModal.tsx` (NEW) | component | — | `WorkflowHistory.tsx:923-969` (DeleteModal) + `AgentsPopup.tsx:374-393` (inputs) | exact |
| `frontend/src/components/catalog/WorkflowCatalog.tsx` (MODIFY) | component | request-response | self `:57-82,110-131,152-207` | exact (self) |
| per-row kebab (in WorkflowCatalog) | component | event-driven | `WorkflowHistory.tsx:872-918,127-128,159-175` | exact |
| `frontend/src/components/workflow/IdeaInputPage.tsx` (MODIFY load-bearing) | component | — | self `:32-43,173-203,238,344-398` | exact (self) |
| `frontend/src/components/layout/DashboardLayout.tsx` (MODIFY) | provider | event-driven | self `:662-665,674-701,1064-1075` | exact (self) |
| `frontend/e2e/tests/ts-z2.saved-workflows.spec.ts` (NEW) | test | — | `ts-z.catalog.spec.ts` | exact |

---

## Pattern Assignments

### 1. `backend/app/models/workflow_definition.py` (MODIFY — add 2 nullable columns)

**Analog:** the model's OWN existing column idiom (`:38-40`). `JSON` is already imported (`:8 from sqlalchemy.types import JSON`).

**Existing idiom to match** (`:36-40`):
```python
    owner_id = Column(String, nullable=True)                 # AUTHZ-01
    workspace_id = Column(String, nullable=True)             # AUTHZ-01
    source = Column(String, nullable=False, default="file", server_default="file")
    manifest_json = Column(JSON, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
```

**What to add** (place beside `manifest_json`, before `created_at` at `:41`):
```python
    base_pipeline_type = Column(String, nullable=True)       # Phase 21: saved-workflow base type ("custom" v1)
    model_overrides = Column(JSON, nullable=True)            # Phase 21: persisted per-agent {agent_id: model_id}
```
**What changes vs analog:** both nullable (additive, no default needed). `agents` (`:28`, `Text`) already holds the ordered agent-id list = our `agent_ids` (`json.dumps`). `artifact_edges` (`:29`, `Text`, NOT NULL) → user rows write `"[]"`. Do NOT relax any constraint.

---

### 2. `backend/alembic/versions/0021_saved_user_workflows.py` (NEW additive migration)

**Head CONFIRMED:** `0020` is the single head (`0020 <- 0019`, no `0021` exists). → `down_revision = "0020"`.

**Analog A — head pointer + `sa.JSON()` + named index + reversible downgrade** (`0020_wave_runs.py:24-54`):
```python
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table( ... sa.Column("task_ids", sa.JSON(), nullable=False) ... )
    op.create_index("ix_wave_runs_run", "wave_runs", ["run_id"])

def downgrade() -> None:
    op.drop_index("ix_wave_runs_run", table_name="wave_runs")
    op.drop_table("wave_runs")
```

**Analog B — `op.batch_alter_table(...)` shape for a portable ALTER** (`0017_repositories_repo_workspace.py:60-63,87-88`):
```python
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.create_foreign_key(_REPO_FK, "repositories", ["repo_id"], ["id"])
    # downgrade:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_constraint(_REPO_FK, type_="foreignkey")
```

**NEW file to write (the two-column add — combines both analogs; 21-SPEC:38-42):**
```python
"""0021 — additive saved user-workflows (Phase 21). Reuse the dormant `workflows`
table for source="user" rows. ADDITIVE ONLY (Q3, INV-3): no new table, no alter
of existing columns. Sequenced after 0020 (down_revision="0020"). downgrade()
drops the two columns (+ index) — fully reversible; SQLite-portable via batch."""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("workflows") as b:
        b.add_column(sa.Column("base_pipeline_type", sa.String(), nullable=True))
        b.add_column(sa.Column("model_overrides", sa.JSON(), nullable=True))
    op.create_index("ix_workflows_owner_source", "workflows", ["owner_id", "source"])

def downgrade() -> None:
    op.drop_index("ix_workflows_owner_source", table_name="workflows")
    with op.batch_alter_table("workflows") as b:
        b.drop_column("model_overrides")
        b.drop_column("base_pipeline_type")
```
**What changes vs analogs:** no `create_table` (additive `add_column` only — there is no existing batch-add-column precedent in this repo, so this is the one genuinely new shape; it is the canonical alembic batch idiom and mirrors `0017`'s `batch_alter_table` use). The optional `ix_workflows_owner_source` backs the `GET` list query (`WHERE owner_id … AND source …`). Prove `upgrade head → downgrade -1 → upgrade head` on in-memory SQLite (the `0020`/`0017` precedent).

---

### 3. `backend/app/api/user_workflows.py` (NEW owner-scoped CRUD router)

**Analog A — router shell + auth import + owner-filtered list/get/delete + IDOR→404 + 204** (`runs.py`).

Imports (`runs.py:22-36`):
```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user      # → dependencies.py:153-178
from app.models.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/user-workflows", tags=["user-workflows"])
```

Owner-filtered list (`runs.py:101-129`):
```python
@router.get("", response_model=list[...])
def list_user_workflows(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (db.query(WorkflowDefinition)
            .filter(WorkflowDefinition.user_id == current_user.id,
                    WorkflowDefinition.source == "user")
            .order_by(WorkflowDefinition.updated_at.desc()).all())
```

IDOR→404 get/delete (`runs.py:258-297` — VERBATIM ownership pattern):
```python
    row = (db.query(WorkflowDefinition)
           .filter(WorkflowDefinition.id == workflow_id,
                   WorkflowDefinition.user_id == current_user.id)
           .first())
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="...not found")
    # delete: @router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
    db.delete(row); db.commit(); return None
```

**Analog B — create-row idiom (stamp owner from current_user, add/commit/refresh)** (`mcp.py:220-234`):
```python
    sess = HandoffSession(token=token, issuer_user_id=user.id, ...)
    db.add(sess); db.commit(); db.refresh(sess)
```

**What changes vs analogs (per 21-SPEC §3.2 / §5):**
- POST body: `{name, description?, base_pipeline_type, agent_ids: list[str], model_overrides?: dict}`.
- Insert: `source="user"`, `agents=json.dumps(agent_ids)`, `artifact_edges="[]"`, and **self-id stamp** `user_id=owner_id=workspace_id=current_user.id`. Persist `base_pipeline_type` + `model_overrides` (new cols).
- Validation (see Shared Pattern §A below) runs in POST → on fail raise `HTTPException(422, …)`.
- Gate: `can_run_pipeline(current_user.tier, base_pipeline_type)` → on deny 403/422 fail-fast (no orphan rows).
- Name uniqueness: API-level — reject a `name` already among the caller's `source="user"` rows (NOT a DB constraint).
- PATCH `/{id}` = rename (+ description/overrides edit), same ownership filter as get/delete.
- Register in `main.py` (file #4).

---

### 4. `backend/app/main.py` (MODIFY — register router)

**Analog (self):** the runs_router import + include (`main.py:17,160`):
```python
from app.api.runs import router as runs_router        # :17
app.include_router(runs_router)                        # :160
```
**What to add (mirror, beside runs):**
```python
from app.api.user_workflows import router as user_workflows_router
app.include_router(user_workflows_router)
```

---

### 5. `backend/agents/execution_engine/engine.py` (REMOVE — INV-12 dead writer)

**Delete the method** `_persist_workflow_definition` (`:4026-4107`, ends just before `:4109` the "Revision intelligence" section). It is `custom`-only via the guard (`:4052-4056`):
```python
        _is_standard_pipeline = (pipeline_type in PIPELINE_AGENTS and pipeline_type != "custom")
        if _is_standard_pipeline:
            return None
```
→ it does NOT fire on the 5 non-custom goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder). The body is best-effort (swallows exceptions `:4105-4107`) and the returned id is discarded.

**Delete the ONLY call site** (`:1380-1386`):
```python
        # Persist custom workflow definition (T061, FR-013)
        await self._persist_workflow_definition(
            user_id=user_id, pipeline_type=pipeline_type,
            agents=ordered_agents, validation_result=validation,
        )
```
**What changes:** remove both blocks entirely. No replacement in the engine — the new router supersedes it. Prove the 5 characterization goldens stay byte-identical (offline parity suite) + `lint-imports` 4/0.

---

### Shared Pattern §A — POST validation predicates (reuse the run-path predicates VERBATIM)

The POST validator MUST copy the SAME predicates the launch path enforces, so a saved row can never carry something launch rejects.

**`SUPPORTED_PIPELINE_TYPES`** (`agents/loader.py:29`) — `base_pipeline_type ∈ SUPPORTED_PIPELINE_TYPES` (the run path checks this at `websocket.py:1388` / loader `:253-257`).

**`allowed_custom_agent_ids(base)`** (`registry.py:331-395`) — the run path uses it at `websocket.py:1394-1397`:
```python
    if agent_ids:
        from agents.registry import allowed_custom_agent_ids
        allowed_ids = allowed_custom_agent_ids(base_pipeline_type)
        rejected = [aid for aid in agent_ids if aid not in allowed_ids]
        if rejected: ...reject
```
→ POST: `rejected = [a for a in agent_ids if a not in allowed_custom_agent_ids(base_pipeline_type)]` → 422 if any.

**`model_overrides` allow-list** (`websocket._validate_model_overrides`, `:95-155`) — the authoritative two-check predicate:
```python
    from agents.capabilities.model_catalog import ModelCatalog
    allowed_model_ids = set(ModelCatalog().ids())   # model_catalog.py:128 def ids()
    for agent_id, model_id in model_overrides.items():
        if agent_id not in run_agent_ids: reject       # key ∈ agent_ids
        if model_id not in allowed_model_ids: reject    # value ∈ ModelCatalog().ids()
```
→ POST: import the same `_validate_model_overrides` (or replicate it) with `run_agent_ids = set(agent_ids)`; non-None return → 422.

**`can_run_pipeline`** (`entitlements.py:46-55`, `TIER_PIPELINES` `:8-31` — `custom` ∈ enterprise only):
```python
    allowed, reason = can_run_pipeline(current_user.tier, base_pipeline_type)
    if not allowed: raise HTTPException(403, reason)
```

---

### 7. `backend/tests/unit/test_user_workflows.py` (NEW — owner-scoped/IDOR API test)

**Analog:** `test_runs_api.py:21-100` — the in-memory SQLite + dependency-override harness (no Postgres). Copy verbatim:
```python
from app.api.user_workflows import router            # was app.api.runs
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db

class _FakeUser:
    def __init__(self, id): self.id = id

@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine); ...

@pytest.fixture
def api(db_session):
    app = FastAPI(); app.include_router(router)
    state = {"user": _FakeUser(id="owner")}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    return TestClient(app), state
```
**What changes:** seed `WorkflowDefinition` rows (`source="user"`) via a `_make_wf(db, ...)` helper (mirror `_make_run:90-100`). Assert: POST creates + validates (bad `agent_id`/`model_id`/`base_pipeline_type` → 422); GET lists only the caller's `source="user"`; flip `state["user"]` to a second user → cross-owner GET/PATCH/DELETE → 404; DELETE → 204; duplicate name → reject. Migration/schema test: load the model + assert the 2 new columns exist (mirror loader schema-validation style).

---

### 8. `frontend/src/lib/api.ts` (NEW fetchers + `UserWorkflowSummary`)

**Type analog — `WorkflowSummary` (`:539-549`):**
```ts
export interface WorkflowSummary { id: string; name: string; description: string; step_count: number; steps: {...}[]; user_launchable: boolean; display_name?: string|null; ... }
```
**New type (add `pipeline_type`/`agent_ids`/`model_overrides`):**
```ts
export interface UserWorkflowSummary {
  id: string; name: string; description?: string | null;
  base_pipeline_type: string; agent_ids: string[];
  model_overrides?: Record<string, string> | null;
  created_at?: string; updated_at?: string;
}
```

**GET analog — `getWorkflowDefinitions` (`:557-564`):**
```ts
export async function getUserWorkflows(token: string): Promise<UserWorkflowSummary[]> {
  return request<UserWorkflowSummary[]>("/api/user-workflows", { method: "GET", headers: authHeaders(token) });
}
```
**POST analog — `adminCreateUser` (`:454-466`):**
```ts
export async function createUserWorkflow(token: string, body: {name: string; description?: string; base_pipeline_type: string; agent_ids: string[]; model_overrides?: Record<string,string>}): Promise<UserWorkflowSummary> {
  return request<UserWorkflowSummary>("/api/user-workflows", { method: "POST", headers: authHeaders(token), body: JSON.stringify(body) });
}
```
**PATCH analog — `adminUpdateTier` (`:442-452`):**
```ts
export async function renameUserWorkflow(token: string, id: string, body: {name?: string; description?: string}): Promise<UserWorkflowSummary> {
  return request<UserWorkflowSummary>(`/api/user-workflows/${id}`, { method: "PATCH", headers: authHeaders(token), body: JSON.stringify(body) });
}
```
**DELETE analog — `adminDeleteUser` (`:468-481`, the manual `fetch` + `ApiError` 204 idiom):**
```ts
export async function deleteUserWorkflow(token: string, id: string): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/user-workflows/${id}`, { method: "DELETE", headers: authHeaders(token) });
  if (!response.ok) { const b = await response.json().catch(() => ({ detail: response.statusText })); throw new ApiError(response.status, b.detail ?? b); }
}
```
**What changes:** endpoints `/api/user-workflows`; `request<T>` is used for JSON-returning calls, the manual `fetch` only for the 204 DELETE (matches `adminDeleteUser`).

---

### 9. `frontend/src/components/catalog/NameWorkflowModal.tsx` (NEW)

**Shell analog — `DeleteModal` (`WorkflowHistory.tsx:923-969`):** the backdrop + scale-in + header + two-button footer. Copy verbatim, change copy + z-index:
```tsx
<motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
  className="fixed inset-0 z-[80] flex items-center justify-center bg-black/20 backdrop-blur-sm" onClick={onCancel}>
  <motion.div initial={{opacity:0,scale:0.96,y:8}} animate={{opacity:1,scale:1,y:0}} exit={{opacity:0,scale:0.96,y:8}}
    transition={{duration:0.15}} onClick={e=>e.stopPropagation()}
    className="bg-white rounded-2xl border border-gray-200 shadow-2xl p-6 max-w-[340px] w-full mx-4">
    {/* header (icon + title) — copy :940-948 */}
    {/* INPUTS here (see below) */}
    <div className="flex gap-2"> {/* footer — copy :952-965, Cancel + Save(gray-900 pill) */} </div>
  </motion.div>
</motion.div>
```
**Input analog — name `<input>` + description `<textarea>` (`AgentsPopup.tsx:374-393`):**
```tsx
<label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide block mb-1">Workflow name</label>
<input type="text" value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. Competitive research"
  className="w-full px-3 py-2 text-[12px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 placeholder-gray-400 transition-colors" />
<textarea value={description} onChange={e=>setDescription(e.target.value)} rows={3}
  className="w-full px-3 py-2 text-[11px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 placeholder-gray-400 resize-none transition-colors" />
```
**What changes:** z-index `z-50 → z-[80]` (opens over AgentsPopup, UI-SPEC §1). Props `{ initialName?, initialDescription?, onSave(name, description), onCancel }` — reused by Save AND Rename. Save button disabled when name empty.

---

### 10. `frontend/src/components/catalog/WorkflowCatalog.tsx` (MODIFY)

All four edits are SELF-analogs (copy the existing region, parameterize).

**(a) second fetch — copy the mount effect (`:57-82`)** → swap `getWorkflowDefinitions` for `getUserWorkflows`, drop the `.filter(user_launchable)` (user rows are always shown), `setUserWorkflows`. Add `const [userWorkflows, setUserWorkflows] = useState<UserWorkflowSummary[]>([])`.

**(b) "Your workflows" section — copy the row list (`:152-207`)** → a second `<section>` under the built-in `divide-y` list; `label = row.name` (user rows render their own name — the "never raw API name" rule is for MANIFEST rows only); each row clicks `onLaunchSaved(row)` instead of `handleClick(type)`; append the kebab (below) in the right affordance slot (replacing the `ArrowRight` `:194-200`).

**(c) "+ Create workflow" header affordance — copy header block (`:110-131`)** → add a subtle top-right button calling `onSelectFeature("custom")` (existing prop). Reuse a quiet text-button style from the catalog.

**(d) new prop:**
```ts
interface WorkflowCatalogProps {
  onSelectFeature: (type: WorkflowType) => void;
  onLaunchSaved: (saved: UserWorkflowSummary) => void;   // NEW — onSelectFeature only carries a WorkflowType
  userTier?: Tier;
}
```

---

### 11. Per-row kebab (in WorkflowCatalog "Your workflows" rows)

**Analog — `WorkflowHistory.tsx:872-918` (MoreHorizontal toggle + AnimatePresence dropdown + dismiss layer) + state `:127-128` + delete handler `:159-175`.**

State (`:127-128`):
```tsx
const [openMenuId, setOpenMenuId] = useState<string | null>(null);
const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
```
Toggle + dropdown (`:872-899`) — copy verbatim, add Rename/Duplicate items beside Delete:
```tsx
<div className="relative">
  <button onClick={e=>{e.stopPropagation(); setOpenMenuId(openMenuId===row.id?null:row.id);}}
    className="flex items-center justify-center h-7 w-7 rounded-lg text-gray-300 hover:text-gray-600 hover:bg-gray-100 transition-colors opacity-0 group-hover:opacity-100">
    <MoreHorizontal className="h-4 w-4" />
  </button>
  <AnimatePresence>{openMenuId===row.id && (
    <motion.div initial={{opacity:0,scale:0.95,y:-4}} animate={{opacity:1,scale:1,y:0}} exit={{opacity:0,scale:0.95,y:-4}}
      transition={{duration:0.1}} className="absolute right-0 top-8 z-20 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[120px]"
      onClick={e=>e.stopPropagation()}>
      {/* Rename → NameWorkflowModal prefilled → renameUserWorkflow */}
      {/* Duplicate → createUserWorkflow(copied payload + "(copy)") */}
      {/* Delete  → setDeleteConfirmId(row.id) → DeleteModal */}
    </motion.div>
  )}</AnimatePresence>
</div>
```
Dismiss layer (`:916-918`):
```tsx
{openMenuId && (<div className="fixed inset-0 z-10" onClick={()=>setOpenMenuId(null)} />)}
```
Optimistic delete (`:159-175` pattern):
```tsx
await deleteUserWorkflow(token, deleteConfirmId);
setUserWorkflows(prev => prev.filter(w => w.id !== deleteConfirmId));
```
**What changes:** items are Rename/Duplicate/Delete (history had Delete only); Delete confirm reuses `DeleteModal` (`:923-969`). Built-in manifest rows get NO kebab (UI-SPEC §4).

---

### 12. `frontend/src/components/workflow/IdeaInputPage.tsx` (MODIFY — load-bearing launch preload + Save button)

**Props analog (self, `:32-43`)** — add two seeds:
```ts
interface IdeaInputPageProps {
  workflowType: WorkflowType;
  onBack: () => void;
  onRun: (message: string, agentIds: string[], resolvedType: WorkflowType, extraParams?: Record<string, unknown>) => void;
  initialAgentIds?: string[];                          // NEW — saved-workflow agent seed
  initialModelOverrides?: Record<string, string>;     // NEW — saved-workflow model seed
}
```

**Seed `pipelineAgents` instead of the empty custom filter** — `effectiveType` (`:173`), current state init (`:175-177`) + re-derive effect (`:201-203`) ALWAYS derive from `LIBRARY_AGENTS.filter(type)`, which is EMPTY for `custom`. Guard them:
```ts
// :175-177 init — seed from initialAgentIds when present
const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(() =>
  initialAgentIds?.length
    ? initialAgentIds.map(id => LIBRARY_AGENTS.find(a => a.id === id)).filter(Boolean) as AgentDef[]
    : LIBRARY_AGENTS.filter(a => a.pipeline_type === effectiveType).sort((a,b)=>a.order-b.order)
);
// :201-203 re-derive effect — GUARD so the seed is not clobbered
useEffect(() => {
  if (initialAgentIds?.length) return;   // saved-workflow launch: keep the seed
  setPipelineAgents(LIBRARY_AGENTS.filter(a => a.pipeline_type === effectiveType).sort((a,b)=>a.order-b.order));
}, [effectiveType]);
```
**Seed `modelOverridesRef` (`:196-199`):**
```ts
const modelOverridesRef = useRef<Record<string, string>>(initialModelOverrides ?? {});
```
**`onRun` (`:238`) is UNCHANGED** — it already sends `pipelineAgents.map(a=>a.id)`, `effectiveType`, and merges `model_overrides` from the ref (`:229-238`). The seed flows through untouched (preserves the existing custom flow when `initialAgentIds` is absent).

**Save button — toolbar analog (`:344-398`, Run pill `:387-398`):** add a "Save workflow" button beside Run, reusing the gray-900 pill style. On click → open `NameWorkflowModal` → `createUserWorkflow({ name, description, base_pipeline_type: effectiveType, agent_ids: pipelineAgents.map(a=>a.id), model_overrides: modelOverridesRef.current })`. (Optional second Save in `AgentsPopup` footer `:988-996` — Claude's Discretion.)

---

### 13. `frontend/src/components/layout/DashboardLayout.tsx` (MODIFY — wire onLaunchSaved)

**Analogs (self):** `handleSelectFeature` (`:662-665`), `handleRunPipeline` (`:674-701`), catalog mount (`:1064-1075`).

`handleSelectFeature` (`:662-665`) sets type + view but can't carry a saved composition:
```tsx
const handleSelectFeature = useCallback((type: WorkflowType) => {
  setWorkflowType(type); setMainView("input");
}, []);
```
**Add `handleLaunchSaved` (mirror, carrying the saved triple into state for IdeaInputPage seeds):**
```tsx
const handleLaunchSaved = useCallback((saved: UserWorkflowSummary) => {
  setSavedComposition({ agentIds: saved.agent_ids, modelOverrides: saved.model_overrides ?? {} }); // new state
  setWorkflowType(saved.base_pipeline_type as WorkflowType);
  setMainView("input");
}, []);
```
**Catalog mount (`:1073`)** — pass the new prop:
```tsx
<WorkflowCatalog onSelectFeature={handleSelectFeature} onLaunchSaved={handleLaunchSaved} userTier={userTier} />
```
**IdeaInputPage mount** — thread the seeds: `initialAgentIds={savedComposition?.agentIds}` `initialModelOverrides={savedComposition?.modelOverrides}` (clear `savedComposition` on a normal `handleSelectFeature` so a non-saved launch starts clean). Run flows UNCHANGED through `handleRunPipeline` (`:674-701`) → `useWorkflow.startPipeline` (already sets `agent_ids` + merges `model_overrides`).

---

### 14. `frontend/e2e/tests/ts-z2.saved-workflows.spec.ts` (NEW mocked Playwright spec)

**Analog — `ts-z.catalog.spec.ts`** (the catalog mocked spec).

Harness import + per-spec mock-route + the reverse-registration precedence rule (`:14,68-78`):
```ts
import { test, expect } from "../fixtures/test";

async function mockUserWorkflows(page) {
  // registered AFTER dashboard.goto() → wins over the fixtures' catch-all (reverse order)
  await page.route("**/api/user-workflows*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SAVED_PAYLOAD) }));
}
async function openCatalog(page) { await page.getByRole("button", { name: /^Catalog$/ }).click(); }
```
Assertion idiom (`:97-101`):
```ts
const rows = page.getByRole("button").filter({ has: page.getByRole("heading", { level: 2 }) });
await expect(page.getByText("My saved workflow")).toBeVisible();
```
**What changes:** mock `/api/user-workflows` (GET list + POST create + PATCH rename + DELETE), `tier: "enterprise"` (custom needs enterprise). Cover the flow: compose → Save (NameWorkflowModal) → appears in "Your workflows" → rename → launch reaches `IdeaInputPage`. A vitest may additionally cover the WorkflowCatalog section render.

---

## Shared Patterns

### Authentication (every backend handler)
**Source:** `app/core/dependencies.py:153-178` (`get_current_user`), used by `runs.py:103` etc.
**Apply to:** every `user_workflows.py` handler — `current_user: User = Depends(get_current_user)`.

### IDOR → 404 ownership filter
**Source:** `runs.py:258-267,283-292` (`.filter(id==:id, user_id==current_user.id)` → `if not row: 404`).
**Apply to:** GET/PATCH/DELETE in `user_workflows.py` (+ `source=="user"` on list). Cross-owner → 404, never 403/leak.

### Validation predicates (save == launch)
**Source:** `websocket.py:95-155,1394-1406` + `registry.py:331-395` + `entitlements.py:46-55` + `ModelCatalog().ids()` (`model_catalog.py:128`).
**Apply to:** `user_workflows.py` POST. See Shared Pattern §A.

### Self-id stamp
**Source:** 21-SPEC §5.4 (`workspace_id = owner_id = user_id = current_user.id`); create idiom `mcp.py:232-234`.
**Apply to:** `user_workflows.py` POST insert + `artifact_edges="[]"`, `source="user"`.

### Hand-rolled modal / kebab (no shared primitive)
**Source:** `WorkflowHistory.tsx:923-969` (DeleteModal) + `:872-918` (kebab).
**Apply to:** `NameWorkflowModal`, the per-row kebab + delete confirm. UI-SPEC §1: NO new visual language; z-index ≥ `z-[80]` for the modal.

### Playwright mock precedence
**Source:** `ts-z.catalog.spec.ts:5-13,68-78` — register `page.route` AFTER `dashboard.goto()` so reverse-order matching beats the fixtures' catch-all.
**Apply to:** the new saved-workflows spec.

---

## No Analog Found

| File / sub-pattern | Role | Reason |
|---|---|---|
| `0021` batch `add_column` two-column shape | migration | No existing migration ADDS a column via `batch_alter_table` (all prior ones `create_table` or `create_foreign_key`). The shape is the canonical alembic batch idiom (mirrors `0017`'s `batch_alter_table` usage) — written fresh in §2 above; not a true "no pattern", just no exact precedent. |

Everything else has an exact or self-analog.

---

## Metadata

**Analog search scope:** `backend/{app/api,app/models,app/core,agents,alembic/versions,tests/unit}`, `frontend/src/{lib,components/{catalog,history,workflow,layout}}`, `frontend/e2e/tests`.
**Drift check:** alembic head verified = `0020` (single head, `0020<-0019`); all `file:line` anchors in 21-SPEC confirmed against live code — NO drift found. `JSON` already imported in the model (`:8`).
**Pattern extraction date:** 2026-06-14
