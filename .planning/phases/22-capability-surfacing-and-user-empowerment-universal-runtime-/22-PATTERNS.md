# Phase 22: Capability Surfacing and User Empowerment — Universal Runtime UX Completeness - Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 17 touched (15 MODIFY, 2 NEW source: migration 0022 + WIRE-03 test) + 9 new/extended test files
**Analogs found:** 17 / 17 (brownfield — every touched file has a same-file in-place analog or a sibling precedent)

> This is a BROWNFIELD EXTENSION. Almost no file is net-new; each is a MODIFY whose "analog" is
> the surrounding in-file pattern to mirror, or a sibling precedent in the same module. Line
> numbers below are the RESEARCH.md Anchor-Verification CURRENT lines (3 drifted from CONTEXT —
> noted inline). Plan against THESE.

## File Classification

| Touched file | Role | Data Flow | Closest Analog | Match Quality |
|--------------|------|-----------|----------------|---------------|
| `backend/agents/capabilities/registry.py` | registry | transform (decorator side-effect) | in-file `_TRUST`/`user_allowed=` kwarg pattern (`:160,167-189`) | exact (extend same seam) |
| `backend/app/api/capabilities.py` | API endpoint | request-response (read) | in-file `_KNOWN` loop + `ModelCatalogEntry` projection (`:106-132`) | exact |
| `backend/agents/workflows/compiler.py` (WIRE-01/02/03) | compiler | transform | in-file `fanout`/`on_conflict`/`limits` materialization (`:249-294,487-516`) | exact (mirror inert-field-made-live) |
| `backend/agents/workflows/compiler.py` (trust at save/launch) | compiler | transform | in-file `_check_trust` (`:299-324`, DRIFTED from CONTEXT ~279-321) | exact (first caller of dormant path) |
| `backend/agents/workflows/plan.py` | model (dataclass) | n/a (target fields) | `Step.fanout`/`CompiledWorkflow.limits` already-live fields (`:366,410`) | exact (fields exist; no edit if pass-through) |
| `backend/agents/model_policy.py` | service | transform | tiers 2/4 already read `Step.model`/`_workflow_model` (`:95/101`) | consumer (no edit) |
| `backend/agents/execution_engine/engine.py` (retry) | service | event-driven | RESUME-02 wrapper gated on `step.retry` (`:1840-1842/4513`) | consumer (no edit) |
| `backend/agents/execution_engine/engine.py` (post_step seam) | service | event-driven | `_registry.resolve("post_step",...).run` (`:1888-1890`, DRIFTED from CONTEXT 1666-1668) | reference only |
| `backend/agents/factory.py` (WIRE-03 consume) | factory | transform | `_compose_system_prompt` injects seam (`:310-315`) → `_compose_injection` (`:398`) | exact (merge `step.injects` here) |
| `backend/app/models/workflow_definition.py` | model | persistence | dormant `manifest_json` column (`:39`) | exact (reuse column, zero migration) |
| `backend/app/models/workflow.py` | model | persistence | in-file Phase-5 additive forward columns (`:54-62`) | role-match (add 2 nullable cols) |
| `backend/alembic/versions/0022_*.py` (NEW) | migration | persistence | `0021_saved_user_workflows.py` (full) | exact (mirror batch_alter shape) |
| `backend/app/api/user_workflows.py` | API endpoint | CRUD (save) | P21 `_owned()` IDOR→404 + save (same file) | exact |
| `backend/app/api/websocket.py` | API endpoint | event-driven (launch) | P21 `run_pipeline` launch path (`~:1394-1406`) | exact |
| `frontend/.../AgentsPopup.tsx` (palette + expander) | React component | request-response | `AgentModelPicker.tsx` fetch/loading/error shell (`:54-89`) | role-match (reuse shell, build INSIDE AgentsPopup) |
| `frontend/.../AgentModelPicker.tsx` (DECIDE-02) | React component | request-response | in-file `user_allowed` filter (`:76`) | exact (drop the filter) |
| `frontend/.../PreviewPanel.tsx` (UXFIX-04) | React component | transform (dispatch) | in-file render-type branch block (`:557-569`) | exact (invert to generic-primary) |
| `frontend/.../DashboardLayout.tsx` (UXFIX-03) | React component | routing | `WorkflowCatalog` catalog-tab mount (`:1084-1093`) vs `home` (`:256/1070-1079`) | exact (make catalog default) |
| `frontend/src/lib/api.ts` | utility | request-response | `getCapabilities`/`CapabilitiesPalette` (`:512-525`, DRIFTED from CONTEXT 522-529) | reference (types follow BE additions) |
| `frontend/src/types/index.ts` (UXFIX-02) | utility | transform | `deriveDeliverableMimetype` heuristic (`:342`) | reference (read persisted value instead) |

## Pattern Assignments

### `backend/agents/capabilities/registry.py` — SURF-02 metadata seam (D-08)

**Analog:** in-file `register()` decorator + `_TRUST` dict — mirror the EXACT mechanism `user_allowed=` already uses.

**Decorator seam to extend** (`:160,167-189`, VERIFIED):
```python
_TRUST: dict[tuple[str, str], bool] = {}
# ADD a sibling: _META: dict[tuple[str, str], dict] = {}

def register(
    kind: str, name: str, *, user_allowed: bool = False
    # ADD kwargs (mirror user_allowed): description: str = "", config_schema: dict | None = None
) -> Callable[[type[_T]], type[_T]]:
    def _decorate(cls: type[_T]) -> type[_T]:
        _KNOWN.add((kind, name))
        _IMPLS[(kind, name)] = cls()
        _TRUST[(kind, name)] = user_allowed
        # ADD: _META[(kind, name)] = {"description": description, "config_schema": config_schema or {}}
        return cls
    return _decorate
```
**Accessor to add** (mirror `is_user_allowed`/`_TRUST.get((kind,name), False)` at `:346`): `describe(kind, name) -> dict` reading `_META`.
**Anti-pattern:** NO static `CAPABILITY_META = {...}` map in the API layer — that is a second hardcoded source eroding SC-001 (D-08).

---

### `backend/app/api/capabilities.py` — SURF-02 projection (D-09/D-10)

**Analog:** in-file `_KNOWN` enumeration loop — the live registry projection.

**`CapabilityEntry` to extend additively** (`:56-64`, VERIFIED — preserve all existing keys):
```python
class CapabilityEntry(BaseModel):
    kind: str
    name: str
    user_allowed: bool
    config_schema: dict = {}      # ← :116 stub replaced from registry.describe(...)
    # ADD: description: str = ""
    # ADD: security_gated: bool = False   # derived: not user_allowed (RESEARCH discretion, A2)
```
**The `{}` stub to replace** (`:116`, VERIFIED — this literal is the SURF-02 gap):
```python
for kind, name in sorted(registry_mod._KNOWN):
    if kind == "model_catalog":
        continue
    capabilities.append(
        CapabilityEntry(
            kind=kind,
            name=name,
            user_allowed=registry.is_user_allowed(kind, name),
            config_schema={},     # ← replace: registry.describe(kind, name)["config_schema"]
            # description=registry.describe(kind, name)["description"],
            # security_gated=not registry.is_user_allowed(kind, name),
        )
    )
```
**Auth/contract pattern to preserve** (`:90-93`): `@router.get("", response_model=CapabilitiesPalette)` + `current_user: User = Depends(get_current_user)`. Additive only (API-02).

---

### `backend/agents/workflows/compiler.py` — WIRE-01/02/03 materialization (D-14/15/16)

**Analog:** in-file `fanout`/`on_conflict` materialization (the established "declared-but-inert field made live" pattern in THIS file).

**The precedent to mirror** (`:487-503`, VERIFIED — comments literally describe the WIRE pattern):
```python
# The ``fanout`` key was already in _ALLOWED_STEP_KEYS but never constructed
# (declared-but-inert). Materialize it now so ``Step.fanout`` is populated...
fanout = self._compile_fanout(raw.get("fanout"), where)
on_conflict = raw.get("on_conflict", "human_gate") or "human_gate"
if on_conflict not in _ALLOWED_ON_CONFLICT:
    raise CompilerError(...)
```
**The `Step(...)` constructor to extend** (`:505-517`, VERIFIED — currently drops model/retry/injects):
```python
return Step(
    agent_id=agent_id, strategy=strategy, gates=gates, hooks=hooks,
    task_source=task_source, validators=validators, compaction=compaction,
    post_step=post_step, tools=effective_tools, fanout=fanout, on_conflict=on_conflict,
    # WIRE-01/02/03 ADD: model=<coerce raw.get("model")→ModelPolicy>,
    #                    retry=<coerce raw.get("retry")→RetryPolicy>,
    #                    injects=list(raw.get("injects") or []),
)
```
**The `CompiledWorkflow(...)` constructor to extend** (`:231-244`, VERIFIED — currently no `model=`):
```python
return CompiledWorkflow(
    id=manifest.id, steps=steps, context_providers=..., seed_files=...,
    allowed_workers=..., deliverable=deliverable, planner=manifest.planner,
    clarify=clarify, limits=limits,
    # WIRE-01 ADD: model=<coerce manifest top-level model:→ModelPolicy>
)
```
**Anti-pattern:** Do NOT loosen `_ALLOWED_STEP_KEYS` (`:65-86`) into silent-accept — INV-5 strict-key rejection stays. WIRE-03 D-17 test asserts every key is consumed OR raises.

---

### `backend/agents/workflows/compiler.py` — trust re-validation (EMP-02/03, D-12)

**Analog:** the DORMANT `_check_trust` — this phase is its FIRST `trust="user"` caller.

**The check to invoke** (`:299-324`, VERIFIED — DRIFTED from CONTEXT ~279-321):
```python
@staticmethod
def _check_trust(registry, kind, name, trusted, where) -> None:
    if trusted:
        return
    if not registry.is_user_allowed(kind, name):
        raise CompilerError(
            f"capability ({kind!r}, {name!r}) is not user-allowed in {where} "
            f"— a user/db manifest may not reference it (CAP-03)"
        )
```
**Limits ceiling backstop also active under untrusted** (`_compile_limits` `:279-289`): a user manifest raising a Limits cap above `_LIMITS_DEFAULT_CEILING` → `CompilerError`. Invoke `compile(..., trust="user")` at BOTH save (user_workflows.py) AND launch (websocket.py) — see Pitfall 3 below.

---

### `backend/agents/workflows/plan.py` — WIRE target fields (no edit if pass-through)

**Analog:** the fields ALREADY exist (`:362,368,369,408`, VERIFIED):
```python
model: ModelPolicy | None = None          # :362 — Step
retry: RetryPolicy | None = None          # :368 — Step
injects: list[str] = field(default_factory=list)   # :369 — Step (defaults [] → WIRE-03 no-op for goldens)
# CompiledWorkflow:
model: ModelPolicy = field(default_factory=ModelPolicy)   # :408
```
No dataclass edit needed for WIRE — the compiler just stops dropping the kwargs.

---

### `backend/agents/factory.py` — WIRE-03 consume side (D-16, generic merge)

**Analog:** the existing AGENT.md injects seam in `_compose_system_prompt` (`:310-315`, VERIFIED):
```python
# 0. Injection content (od_prototype / od_ppt agents)
injects = getattr(spec, "injects", []) or []
if injects:
    injection_block = _compose_injection(spec, ctx, injects)
    if injection_block:
        blocks["injects"] = injection_block
```
**Merge pattern (provably INV-3-safe, RESEARCH WIRE-03 Decision):** combine `spec.injects` (AGENT.md) with the compiled `step.injects`, order-stable, no workflow-name branch:
```python
effective = list(spec.injects) + [i for i in step_injects if i not in spec.injects]
```
When `step.injects == []` (every golden step today) → returns exactly `spec.injects` → byte-identical. Extend `tests/unit/test_factory_injects.py` for the merge. **SC-001:** the merge keys on generic `step.injects`, never a workflow/agent name.

---

### `backend/app/models/workflow_definition.py` — EMP-03 persistence (D-11, ZERO migration)

**Analog:** the DORMANT nullable `manifest_json` column (`:39`, VERIFIED):
```python
manifest_json = Column(JSON, nullable=True)   # reuse for compact per-step selections map
# row already owner-scoped: owner_id (:36), workspace_id (:37); P21 added
# base_pipeline_type/model_overrides/description (:41-43)
```
Store the compact `{agent_id: {validators, gates, model, retry, ...}}` selections map here. No new migration (INV-12 reuse-first; existing user rows legitimately stay `NULL` = "no selections", parity).

---

### `backend/app/models/workflow.py` + `0022_*.py` — UXFIX-02 (D-19)

**Analog (model):** in-file Phase-5 additive forward columns (`:54-62`) — add two nullable columns beside them:
```python
# ADD: deliverable_mimetype = Column(String, nullable=True)
# ADD: deliverable_filename = Column(String, nullable=True)
# run already carries owner_id (:58) + workspace_id (:59) scope
```
**Analog (migration):** `0021_saved_user_workflows.py` (full) — mirror the additive batch_alter shape:
```python
revision = "0022"
down_revision = "0021"

def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.add_column(sa.Column("deliverable_mimetype", sa.String(), nullable=True))
        b.add_column(sa.Column("deliverable_filename", sa.String(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("deliverable_filename")
        b.drop_column("deliverable_mimetype")
```
ADDITIVE ONLY (no alter/drop of existing cols); single-head chain. Both keys already in `_VOLATILE_STRIP_KEYS` → goldens stay byte-identical (INV-3). Emit already live at `engine.py:2117-2128`.

---

### `frontend/.../AgentsPopup.tsx` — palette + Advanced expander (SURF-01/03, EMP-01/04, D-01/05)

**Analog:** `AgentModelPicker.tsx` fetch/loading/error/empty shell — REUSE this shape; build the palette INSIDE `AgentsPopup` (NOT a standalone component — see Pitfall 1).

**The fetch shell to mirror** (`AgentModelPicker.tsx:54-89`, VERIFIED):
```typescript
const [models, setModels] = useState<CapabilityModelEntry[]>([]);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
useEffect(() => {
  let cancelled = false;
  const jwt = token ?? getToken();
  if (!jwt) { setError("Not authenticated."); setLoading(false); return; }
  setLoading(true);
  getCapabilities(jwt)
    .then((palette) => { if (cancelled) return; setModels(...); setError(null); })
    .catch((e) => { if (cancelled) return; setError(e?.message ?? "..."); })
    .finally(() => { if (!cancelled) setLoading(false); });
  return () => { cancelled = true; };
}, [token]);
```
For the palette consume `palette.capabilities` (not `model_catalog`). Render grouped-by-kind from the payload; `user_allowed=false` → locked row (D-04). **SC-001:** no hardcoded capability-name array in the source (grep target = 0). Per-agent Advanced expander = validator + gate + non-default model + retry (treat agent ≈ step, D-05); coupled-gate auto-attach inline (EMP-04, D-07).

---

### `frontend/.../AgentModelPicker.tsx` — DECIDE-02 (D-23)

**The filter to DROP** (`:76`, VERIFIED):
```typescript
setModels(palette.model_catalog.filter((m) => m.user_allowed));   // ← drop the .filter; offer all tiers
```

---

### `frontend/.../PreviewPanel.tsx` — UXFIX-04 generic-primary (D-21)

**The branch block to invert** (`:557-569`, VERIFIED — generic is fallback-last today):
```tsx
{renderType === "user_stories" && userStoryContent && <UserStoryPreview .../>}
{renderType === "app_builder" && userStoryContent && <AppBuilderIDEPreview .../>}
{renderType === "ppt" && (pptContent || pptxCode) && <PPTPreview .../>}
{renderType === "prototype" && prototypeContent && <PrototypePreview .../>}
{hasGenericDeliverable && genericDeliverable && (   // ← make this the PRIMARY dispatch
  <GenericDeliverablePreview .../>
)}
```
Restructure into a mimetype-dispatch table where the 4 first-party types are registered entries the generic dispatcher routes to. No visual regression; per-type tests stay green. NOTE: `custom` already removed from the MarkdownPreview branch (CR-01 fix — keep that).

---

### `frontend/.../DashboardLayout.tsx` — UXFIX-03 catalog-as-home (D-20)

**Analog:** the catalog-tab mount (`:1084-1093`, VERIFIED) — make it the default landing; the `home`/`CreationHub.WORKFLOWS` hardcoded array (`:256/1070-1079`) no longer drives the default landing.

---

## Shared Patterns

### Capability self-description (single source of truth)
**Source:** `registry.py` `@register` + `_TRUST`/`_META` (`:167-189`).
**Apply to:** SURF-02 (capabilities.py). NEVER add a parallel metadata map in the API layer (D-08).

### Trust re-validation at the boundary
**Source:** `compiler.py::_check_trust` (`:299-324`) invoked via `compile(..., trust="user")`.
**Apply to:** EVERY user-manifest entry point — `user_workflows.py` SAVE and `websocket.py` LAUNCH (D-12). UI lock affordance is advisory; the compiler is the authoritative backstop.

### Inert-field-made-live materialization
**Source:** `compiler.py` `fanout`/`on_conflict`/`limits` (`:249-294,487-516`).
**Apply to:** WIRE-01/02/03 — pass-through into the two constructors; never loosen `_ALLOWED_STEP_KEYS` (INV-5).

### Additive owner-scoped persistence
**Source:** migration `0021_saved_user_workflows.py` (batch_alter, nullable, single-head).
**Apply to:** UXFIX-02 migration 0022. EMP-03 reuses an existing column (`manifest_json`) — zero migration.

### Reuse-first FE fetch shell
**Source:** `AgentModelPicker.tsx:54-89` fetch/loading/error/cancel pattern.
**Apply to:** the embedded palette in AgentsPopup. Do NOT recreate the P18-deleted `CapabilityPalette.tsx`.

### INV-3 goldens / SC-001 name-free
**Apply to:** all backend changes. Run the 5 characterization goldens after every change; kernel name-free grep = 0; `deliverable_mimetype`/`deliverable_filename` stay in `_VOLATILE_STRIP_KEYS`.

## No Analog Found

None. Every touched file has an in-file or sibling precedent. The only net-new artifacts are
the migration `0022` (analog = 0021), the embedded palette UI + Advanced expander (analog =
AgentModelPicker shell, built inside AgentsPopup), the `_META` registry extension (analog =
`_TRUST`), and the WIRE-03 parametrized `_ALLOWED_STEP_KEYS` test (new file
`tests/agents/test_allowed_step_keys.py`, analog = `tests/agents/test_compiler.py`).

## Key Pitfalls (from RESEARCH — carry into plans)

1. **Do NOT resurrect a standalone `CapabilityPalette.tsx`** — P18 deleted it as an INV-12 dual-impl. Palette lives INSIDE `AgentsPopup` (D-01). Highest-priority landmine.
2. **WIRE-03 INV-3:** merge `step.injects` with `spec.injects` order-stably; `step.injects==[]` for all goldens → provable no-op. Run goldens to confirm.
3. **Trust re-validation at LAUNCH, not just SAVE** — compile `manifest_json` with `trust="user"` at BOTH `user_workflows.py` and `websocket.py run_pipeline` (defends a tampered row).
4. **DECIDE-01 scopes only 3 confirm labels** (REPO-02 N6/N10, REPO-04 N5/N7, FANOUT-05 N2) — do NOT touch WAVE-03 N8 (line 135).
5. **Offline full pytest hangs** — use the targeted ~35s suite + `lint-imports` (`/opt/homebrew/bin/lint-imports`).

## Metadata

**Analog search scope:** `backend/agents/{capabilities,workflows,execution_engine}/`, `backend/app/{api,models}/`, `backend/alembic/versions/`, `frontend/src/components/{workflow,preview,layout}/`, `frontend/src/lib/`, `frontend/src/types/`.
**Files read this session:** registry.py, capabilities.py, compiler.py (3 ranges), factory.py, plan.py, workflow.py, workflow_definition.py, 0021 migration, AgentModelPicker.tsx, PreviewPanel.tsx.
**Anchor source:** RESEARCH.md Anchor Verification Report (all 24 refs verified live 2026-06-14; 3 drifts reflected above).
**Pattern extraction date:** 2026-06-14
