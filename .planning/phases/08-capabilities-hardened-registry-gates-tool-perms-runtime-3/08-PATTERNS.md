# Phase 8: Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3] - Pattern Map

**Mapped:** 2026-06-09
**Files analyzed:** 40 (net-new + grows + shrinks-deleted)
**Analogs found:** 38 / 40 (only OTel hook impl + frontend panels lack a strict in-repo analog)

> This is a brownfield Ports & Adapters refactor. Almost every net-new surface has a live analog already cited at `file:line` in `08-RESEARCH.md` (`## Sources`). The dominant idiom is **inert-field activation** (RESEARCH Pattern 1) + **move-don't-copy deletion** (INV-12): bind impls into seams that already exist, then delete the inline original. All line anchors below were verified against the live tree this session unless tagged `[from RESEARCH]`.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| **NET-NEW — ports (`agents/capabilities/base.py`, grows)** |
| `PromptAssemblyPolicy` port | port (Protocol) | transform | `base.py:104` `GateHandler` / `:53` `Validator` | exact (idiom) |
| `AgentRuntimeAdapter` port | port (Protocol) | request-response | `base.py:42` `ExecutionStrategy` | exact (idiom) |
| `HookHandler` port | port (Protocol) | event-driven | `base.py:86` `PostStep` / `:104` `GateHandler` | exact (idiom) |
| `ToolProvider` / `SkillProvider` / `HookProvider` ports | port (Protocol) | transform | `base.py:75` `ContextProvider` (returns blocks) | exact (idiom) |
| **NET-NEW — self-registering capabilities** |
| `agents/capabilities/gates/{human,validation,approval,security}.py` | capability (gate) | event-driven | `capabilities/post_steps/revision_validation.py` + `registry.py` `install()`:80 | exact (role+reg) |
| `agents/capabilities/tools/*.py` (`tool_provider`) | capability (provider) | transform | `factory.py:384` `_build_runner_tools` switch (the inline impl being lifted) | exact (lift) |
| `agents/capabilities/skills/*.py` (`skill_provider`) | capability (provider) | transform | `factory.py:220-245` inline skills (lift) [from RESEARCH] | exact (lift) |
| `agents/capabilities/hooks/secret_scan.py` | capability (hook) | event-driven | `base.py:86` `PostStep` idiom + `KernelServices` handle | role-match |
| `agents/capabilities/hooks/otel_tracing.py` | capability (hook) | event-driven / streaming | (no OTel analog in tree) | **no analog** |
| `agents/capabilities/runtimes/langchain_deepagents.py` (`AgentRuntimeAdapter`) | capability (runtime) | request-response | `app/agents/deep_agent_runner.py:240` `create_deep_agent` (wraps, never replaces) | exact (wrap) |
| `agents/capabilities/prompt/*.py` (`PromptAssemblyPolicy`) | capability / config | transform | `factory.py:174-255` `_compose_system_prompt` block order (lift) | exact (lift) |
| `agents/capabilities/validators/*.py` (pure-stdlib: `task_done_when`, `spec_plan_coverage?`) | capability (validator) | transform | `capabilities/post_steps/revision_validation.py` (capability shape) | role-match |
| **NET-NEW — app-side heavy-dep validators** |
| `app/agents/validators/html_static.py` | capability (validator) | file-I/O | `app/agents/static_check.py` (wrapped) + `base.py:53` `Validator` | exact |
| `app/agents/validators/html_render.py` | capability (validator) | file-I/O | `app/agents/render_check.py` (wrapped) + `base.py:53` `Validator` | exact |
| `app/agents/validators/design_quality.py` (Tier#6, warnings-first) | capability (validator) | transform | `static_check.py` (stdlib-style checks) | role-match |
| **NET-NEW — persistence** |
| `app/models/validation_results.py` | model | CRUD | `app/models/run_capabilities.py` | exact |
| `app/models/gate_events.py` | model | CRUD | `app/models/run_capabilities.py` | exact |
| `app/models/hook_runs.py` | model | CRUD | `app/models/run_capabilities.py` | exact |
| `alembic/versions/0016_*.py` | migration | CRUD | `alembic/versions/0015_drop_thin_artifact_store.py` (head; down_revision="0015") | role-match |
| ScopedStore writers for the 3 tables | service | CRUD | `agents/authz.py:58` `ScopedStore` | exact |
| **NET-NEW — API** |
| `app/api/capabilities.py` (`GET /api/capabilities`) | route (controller) | request-response | `app/api/workflows.py:160-209` (`list_workflows`) | exact |
| registration in `app/main.py` | config | — | `main.py:148` workflows_router | exact |
| **NET-NEW — frontend** |
| capability palette panel | component | request-response | `frontend/src/components/library/AgentLibrary.tsx` | role-match (not deep-read) |
| per-agent model picker | component | request-response | `frontend/src/components/workflow/*` | role-match |
| validator/issue panel | component | request-response | `frontend/src/components/results/*` + `ReviewGatesSection.tsx` | role-match |
| **GROWS** |
| `agents/capabilities/registry.py` (`@register`/`discover()` + `user_allowed`) | registry | event-driven | self (`install()`:80 → evolves) | exact (evolution) |
| `agents/workflows/compiler.py` (trust check) | service | transform | `compiler.py:110-211` INV-4 ref-validation [from RESEARCH] | exact (same seam) |
| `agents/workflows/plan.py` (grant fields) | model | — | `plan.py:45-61` `ToolPermissions`, `:100-105` `FixPolicy`, `:214-241` `Step` (ALL inert) [from RESEARCH] | exact (inert activation) |
| `agents/execution_engine/engine.py` (gate seam + hook firing) | controller (kernel) | event-driven | `engine.py:1011-1041` dispatch loop; `:2043` `_run_review_gate` [from RESEARCH] | exact |
| `agents/capabilities/strategies/task_loop.py` (validation re-point) | capability (strategy) | event-driven | self (`:292` unconditional `run_validation_fix_loop`) [from RESEARCH] | exact (refactor) |
| `agents/factory.py` (F1–F4 → policy/providers) | factory | transform | self (`:174-255`, `:220-245`, `:282-306`, `:384-446`) | exact (lift) |
| `app/agents/deep_agent_runner.py` (F5 → adapter) | runner | request-response | self (`:240` `create_deep_agent`) | exact (wrap) |
| `app/api/websocket.py` (additive events) | route | streaming | `websocket.py:595` generic `{"type": event["type"]}` forward [from RESEARCH] | exact (no edit needed for new types) |
| **SHRINKS → DELETED** |
| F1 `blocks.append`, F2 `_build_runner_tools`, F3 `_inject_skills/_inject_hooks`, F4 constitution no-op, F5 hardcoded `create_deep_agent`, `registry.install()` | — | — | migration-ledger F1–F5 rows; `test_migration_ledger.py`, `test_banned_patterns.py` | exact (ratchet) |

---

## Pattern Assignments

### `agents/capabilities/{gates,hooks,runtimes,tools,skills,prompt}/*` ports (capabilities/base.py, GROWS)

**Analog:** `backend/agents/capabilities/base.py` (verified this session)

**The one-method-`Protocol` idiom every new port copies** (`base.py:104-112`):
```python
@runtime_checkable
class GateHandler(Protocol):
    """A step gate — human | validation | approval | security (§9)."""
    name: str  # capability name, e.g. "human" | "validation" | "approval" | "security"
    async def evaluate(self, step: Any, ctx: Any) -> Any:
        """Evaluate the gate, returning a gate outcome (pass | block | wait_human)."""
        ...
```

**Provider ports copy the `ContextProvider` mapping-return shape** (`base.py:75-83`):
```python
@runtime_checkable
class ContextProvider(Protocol):
    name: str
    async def load(self, ctx: Any) -> dict[str, str]:
        """Return a mapping of block-name -> content."""
        ...
```

**Idiom the planner must replicate:**
- `@runtime_checkable class X(Protocol)`, a `name: str` attribute, ONE method, `...` body.
- Type runtime objects (`Step`, `ctx`, `target`) as `Any` — base.py imports ONLY stdlib `typing` (import-linter keeps kernel→ports one-way; NO import of `engine`/`app`).
- New kinds: `PromptAssemblyPolicy` (transform → composed prompt str), `AgentRuntimeAdapter` (wraps a runner), `HookHandler` (`async def handle(event, ctx) -> outcome`), `ToolProvider`/`SkillProvider`/`HookProvider` (return tool/skill/hook sets).

---

### `agents/capabilities/registry.py` — `@register`/`discover()` + `user_allowed` (GROWS; deletes `install()`)

**Analog:** self — `registry.py` (verified this session). This IS the seam D-01 evolves; the docstring (`:13-16`) already names Phase 8 as owner.

**The `_KNOWN` membership surface that MUST stay impl-free** (`registry.py:46-63`):
```python
_KNOWN: set[tuple[str, str]] = {
    ("strategy", "single_shot"), ("strategy", "task_loop"),
    ("validator", "html_static"), ("validator", "html_render"),
    ("gate", "human"), ("gate", "validation"),
    ("compaction", "html_skeleton"),
    ("post_step", "revision_validation"),
    ("model_catalog", "default"),
    # ... 16 pairs total
}
```

**The lazy explicit-binding `install()` that `discover()` REPLACES** (`registry.py:80-138`):
```python
def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    # Local (NOT module-level) imports so importing registry for the membership
    # path never drags in impl modules — keeps compiler import impl-free.
    from agents.capabilities.strategies.task_loop import TaskLoopStrategy
    ...
    _IMPLS[("strategy", "task_loop")] = TaskLoopStrategy()
    ...
    _INSTALLED = True
```

**The lazy-on-first-resolve binding to preserve** (`registry.py:173-184`):
```python
def resolve(self, kind: str, name: str) -> object:
    if (kind, name) not in _KNOWN:          # validated FIRST — no dynamic resolution
        raise KeyError(f"unknown capability reference: ({kind!r}, {name!r})")
    if not _INSTALLED:
        install()                            # ← discover() takes this slot
    return _IMPLS[(kind, name)]
```

**Idiom the planner must replicate:**
- `@register(kind, name)` binds `(kind,name)→impl` at module import; `discover()` explicitly imports the known capability subpackages (NO `pkgutil.walk_packages`, NO entry-points) — including `app/agents/validators/` (the only app-side capability package).
- `discover()` is invoked at engine import / first `execute()`, **NEVER at compiler import** (`test_registry_capabilities.py` asserts zero impls bound at compiler import).
- `_KNOWN` stays the pure-membership INV-4 surface (`is_registered`); regenerate it from the registered set OR keep it a declared allow-list the decorator validates against (Claude's discretion, D-01).
- `install()`/`_register_builtins` is **DELETED**, not kept beside `discover()` (INV-12).
- Add `user_allowed: bool` to the registration (D-02); fold the `test_strategies.py` autouse `_IMPLS` save/restore reset fixture here (D-12).
- **Lockstep test edit:** `test_registry_capabilities.py` `_EXPECTED_NAMES` + `test_registered_count_is_exactly_sixteen` bump as new kinds/names land (expected, NOT a snapshot re-baseline).

---

### `app/agents/validators/html_static.py` · `html_render.py` (NET-NEW; D-04 backbone)

**Analog:** `app/agents/static_check.py` / `render_check.py` (wrapped) + `base.py:53` `Validator` port + `agents/execution_engine/kernel_services.py` handle.

**The import-direction proof (app → capabilities is LEGAL)** [from RESEARCH `app/api/websocket.py:94`, import-linter forbids only the reverse `agents.capabilities → app`].

**Idiom the planner must replicate** [from RESEARCH Code Example, D-04]:
```python
# app/agents/validators/html_static.py — lives APP-side (heavy dep), self-registers:
from agents.capabilities.base import Validator       # port import — import-linter LEGAL
from agents.capabilities.registry import register     # the new @register (D-01)

@register("validator", "html_static")
class HtmlStaticValidator:                              # satisfies Validator Protocol (base.py:53)
    name = "html_static"
    async def validate(self, target) -> list:          # target = DeliverableContext
        result = target.runner.static_check(target.path)   # via KernelServices handle — NOT a kernel import
        return _to_issues(result)                      # P0–P3 → CRITICAL/HIGH/MEDIUM/LOW
```
- Kernel/`task_loop` `resolve("validator","html_static")` + call `.validate` — **never** import `app.*`.
- `design_quality` (Tier#6) is **warnings-first**: emits only P2/P3, never blocks.
- Each run/attempt writes a `validation_results` row (D-10).

---

### `app/models/validation_results.py` · `gate_events.py` · `hook_runs.py` (NET-NEW) + `alembic/0016`

**Analog:** `backend/app/models/run_capabilities.py` (verified this session) — the exact §18 additive-table + `owner_id`/`workspace_id` precedent; its `skills`/`hooks` JSON cols are already reserved "Phase 8".

**The model shape to mirror** (`run_capabilities.py:21-39`):
```python
class RunCapabilities(Base):
    __tablename__ = "run_capabilities"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    runtime = Column(String, nullable=False)
    skills = Column(JSON, nullable=True)             # Phase 8
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

**Idiom the planner must replicate:**
- Every new table: `id` UUID PK + `run_id` FK + **`owner_id` + `workspace_id` (both `nullable=False`)** + payload cols (validator name/severity/attempt/issues JSON; gate name/outcome; hook name/event/outcome).
- Alembic `0016`: `down_revision = "0015"` (head is `0015_drop_thin_artifact_store.py`); additive only (no destructive alter); indexes per §18 (`validation_results` (run_id, step); `gate_events` (run_id); `hook_runs` (run_id)).
- Writes go through `agents/authz.py:58` `ScopedStore` (default-deny); `owner_id`/`workspace_id` sourced from `ExecutionContext` at write time.

---

### `app/api/capabilities.py` — `GET /api/capabilities` (NET-NEW)

**Analog:** `backend/app/api/workflows.py:160-209` `list_workflows` (verified this session).

**The auth + router idiom to copy** (`workflows.py:160-163`):
```python
@router.get("", response_model=list[WorkflowSummary])
def list_workflows(
    current_user: User = Depends(get_current_user),
):
    ...
```

**Idiom the planner must replicate:**
- `router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])`; `@router.get("")` with `current_user: User = Depends(get_current_user)` (JWT, same posture as every endpoint).
- Return the registry palette: `(kind, name, user_allowed, config schema)` incl. runtimes/skills/hooks/model catalog.
- Register in `app/main.py` alongside `workflows_router` (`main.py:148`).
- WS events: new `validator_result`/`validation_warning`/`gate_*` flow through the generic `websocket.py:595` `{"type": event["type"], ...}` forward — **no `websocket.py` edit for new event TYPES** (additive only).

---

### `agents/factory.py` F2 → `tool_provider` registry (GROWS → F2 DELETED)

**Analog:** self — `factory.py:384-446` `_build_runner_tools` (verified this session). The inline switch IS the impl being lifted.

**The closed switch to replace** (`factory.py:418-444`):
```python
if not spec.tools:
    return ([], True)                      # pure-text agent
for tool_name in spec.tools:
    if tool_name == "workspace":
        exclude = False
    elif tool_name in ("prototype", "prototype_emit_only"):
        if report_task_complete not in custom:
            custom.append(report_task_complete)
        exclude = False
    elif tool_name == "planning":
        custom.extend(PLANNING_TOOLS)
    else:
        raise ValueError(f"Unrecognized tool name '{tool_name}' ...")
return (custom, exclude)
```

**Idiom the planner must replicate:**
- A `tool_provider` registry resolves the same `(custom_tools, exclude_builtin)` per declared set, now grant-driven: effective = `intersection(owner_allow_list, workflow_ceiling, step_grant)`; AGENT.md may only LOWER.
- **Parity bar (RESEARCH Pitfall 5):** existing manifests with no explicit grant + default `ToolPermissions` (read_files ON, rest OFF, `plan.py:53-61`) MUST bind the SAME sets the switch produced — `test_create_runner.py` is the gate.
- `_build_runner_tools` grep → 0 (F2 exit gate); deletion only after parity proven.

---

### F1/F3/F4 → `PromptAssemblyPolicy` + skill/hook providers + constitution fix (factory.py, GROWS → deleted)

**Analog:** self — `factory.py:174-255` (`_compose_system_prompt` block order), `:220-245` (inline skills/hooks), `:258-306` (constitution no-op, running-loop branch `:282-292` = R12) [anchors from RESEARCH/CONTEXT].

**Idiom the planner must replicate:**
- Default `PromptAssemblyPolicy` order MUST be `injects→guardrails→skills→hooks→constitution→prompt_body` (confirmed by `backend/CLAUDE.md` "Skills vs Guardrails vs Hooks" + RESEARCH Pitfall 2); blocks joined with `"\n\n"` — **byte-identical** composed prompt for existing agents (the 5 characterization snapshots gate it; NEVER re-baseline).
- `skill_provider` (ui·disk·template·repo) gains a provider interface + versioning; the legacy prompt-only hook survives as `kind: behavioral` (the `## Active Behavioral Hooks` block still renders).
- F4/R12 fix: **pre-warm the constitution at run entry** (RESEARCH A3 — lower-risk than await-in-running-loop). Existing snapshots carry NO Constitution (RESEARCH A4) → byte-identical; the constitution-injected-in-prod test is a **NEW** test.
- Grep gates → 0: `blocks\.append` (F1), `_inject_skills|_inject_hooks` (F3).

---

### F5 → `AgentRuntimeAdapter` (deep_agent_runner.py + runtimes/, GROWS → deleted)

**Analog:** `app/agents/deep_agent_runner.py:240` `create_deep_agent` [from RESEARCH].

**Idiom the planner must replicate:**
- `AgentRuntimeAdapter` (`langchain_deepagents`) **wraps, never replaces** `create_deep_agent` (INV-13).
- **Keep the `create_deep_agent` CALL inside `deep_agent_runner.py`** so the banned-pattern allow-list `_ALLOWED_CREATE_DEEP_AGENT = {"app/agents/deep_agent_runner.py"}` stays stable (RESEARCH Open Q2); the runtime capability *selects/wraps* `DeepAgentRunner` via the handle, never calling `create_deep_agent` itself nor importing `app` from the kernel.
- F5 CHECK gate: `create_deep_agent` only in the allow-listed module; `test_banned_patterns.py` + import-linter green.

---

### `agents/execution_engine/engine.py` — gate seam + hook firing (GROWS)

**Analog:** self — dispatch loop `engine.py:1011-1041`; human gate `_run_review_gate:2043` + `review_gate_*` events [from RESEARCH].

**Idiom the planner must replicate** [from RESEARCH Code Example]:
```python
for i, spec in enumerate(ordered_agents):
    step = _steps_by_agent.get(spec.id)
    # [NEW D-03] pre-step gates (security/approval) block BEFORE the strategy runs
    strategy = _registry.resolve("strategy", strategy_name)
    async for event in strategy.run(step, ectx):
        yield event
    # [NEW D-03] post-step gates (validation) evaluate HERE
# register "human" → existing _run_review_gate (unchanged → review_gate_* parity)
```
- `human` gate registers behind the `GateHandler` registry → routes to existing `_run_review_gate` (GATE-03 byte/event parity, no re-baseline).
- Hooks bind at existing lifecycle points (`before_write`≈runner tool-call/write; `post_task`≈task_loop per-task; `before_step`≈dispatch loop `:1011`) WITHOUT leaking events: `otel_tracing` emits OTel spans/`hook_runs` rows (NOT WS events); `secret_scan` blocking is additive (RESEARCH Pitfall 6).

---

### `agents/capabilities/strategies/task_loop.py` — validation re-point (GROWS, D-06)

**Analog:** self — `task_loop.py:292` unconditional `runner.run_validation_fix_loop` [from RESEARCH].

**Idiom the planner must replicate:**
- The generic `FixPolicy` fix-loop REPLACES the internals of `KernelServices.run_validation_fix_loop` (behavior-identical, now config-driven: deliverable name + `max_attempts` + fix-prompt template + registered validators) — it stays where `task_loop` invokes it (NOT moved into the gate; RESEARCH Pitfall 4 / anti-pattern).
- `task_loop`'s inline validation now drives registered `html_static`/`html_render` + the generic loop — byte/event-identical to Phase 7 (the 5 snapshots gate it).
- The `validation` gate is **additive** — the declarative entry for non-build steps (`gates:[validation]`). `revision_validation` post_step becomes a `validation` gate ONLY if `test_characterization_prototype_revision.py` proves parity; else stays a post_step (decide with snapshot evidence).

---

## Shared Patterns

### Capability port (one-method Protocol)
**Source:** `backend/agents/capabilities/base.py:42-112`
**Apply to:** every net-new port (`PromptAssemblyPolicy`, `AgentRuntimeAdapter`, `HookHandler`, `ToolProvider`/`SkillProvider`/`HookProvider`)
```python
@runtime_checkable
class GateHandler(Protocol):
    name: str
    async def evaluate(self, step: Any, ctx: Any) -> Any: ...
```
Stdlib-`typing`-only; runtime objects typed `Any`; no kernel/app import.

### Self-registration + lazy discovery
**Source:** `backend/agents/capabilities/registry.py:80-184`
**Apply to:** every net-new capability module (gates, tools, skills, hooks, runtimes, validators)
- `@register(kind, name)` binds at import; `discover()` (replacing `install()`) imports known subpackages incl. `app/agents/validators/`; never runs at compiler import; `_KNOWN` stays impl-free membership.

### App-side capability via the handle (no kernel→app edge)
**Source:** `app/api/websocket.py:94` (import-direction proof) + `agents/execution_engine/kernel_services.py` (handle) + `base.py:53` port
**Apply to:** all heavy-dep validators (`html_static`/`html_render`/`design_quality`)
- Capability lives app-side, imports the PORT + heavy dep, self-registers; kernel reaches it via `resolve` + `ctx.runner` (`KernelServices`) only.

### Additive owner/workspace-scoped table
**Source:** `app/models/run_capabilities.py:21-39` + `agents/authz.py:58` `ScopedStore` + `alembic/versions/0015_*.py` (head)
**Apply to:** `validation_results`, `gate_events`, `hook_runs`
- UUID PK + `run_id` FK + `owner_id`/`workspace_id` (`nullable=False`); Alembic `down_revision="0015"`; writes via `ScopedStore`, scope from `ExecutionContext`.

### Authenticated FastAPI GET endpoint
**Source:** `app/api/workflows.py:160-163` + `main.py:148`
**Apply to:** `GET /api/capabilities`
- `APIRouter(prefix=..., tags=...)`; `current_user: User = Depends(get_current_user)`; register in `main.py`.

### Move-don't-copy deletion (INV-12 ratchet)
**Source:** `specs/003-workflow-engine-decoupling/migration-ledger.md` F1–F5 rows + `tests/agents/test_migration_ledger.py` + `test_banned_patterns.py`
**Apply to:** F1–F5 + `registry.install()`
- Wrap → rewire → prove parity against the 5 characterization snapshots → DELETE inline original → flip ledger row ☑. Deletion is the exit gate; never delete before the routed path proves byte/event-identical.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `agents/capabilities/hooks/otel_tracing.py` | capability (hook) | event-driven / streaming | No OpenTelemetry dependency or tracer exists in the tree (RESEARCH: grep found ZERO `opentelemetry` refs). New external dep `opentelemetry-sdk`/`-api` (`[ASSUMED]` — gate install behind `checkpoint:human-verify`); logging-only span analog is the fallback (A1). Hook *shape* still copies the `HookHandler` port idiom. |
| frontend panels (palette / model picker / validator panel) | component | request-response | `frontend/src/components/{workflow,library,results}/` confirmed by directory listing only — NOT deep-read this session (RESEARCH Secondary/MEDIUM confidence). Planner should `Read` `AgentLibrary.tsx` / `ReviewGatesSection.tsx` + a results surface before composing; reuse/extend, do not rebuild (D-11). |

---

## Metadata

**Analog search scope:** `backend/agents/capabilities/`, `backend/agents/workflows/`, `backend/agents/execution_engine/`, `backend/agents/factory.py`, `backend/app/agents/`, `backend/app/models/`, `backend/app/api/`, `backend/alembic/versions/`, `frontend/src/components/`
**Files scanned (read this session):** `capabilities/base.py`, `capabilities/registry.py`, `app/models/run_capabilities.py`, `app/api/workflows.py`, `factory.py` (F2 site), `backend/CLAUDE.md`. All other anchors carried verbatim from `08-RESEARCH.md` `## Sources` (HIGH confidence, every claim cited at `file:line`).
**Pattern extraction date:** 2026-06-09
