---
inclusion: fileMatch
fileMatchPattern: "backend/agents/capabilities/**"
---

# Backend — Capabilities Domain

> Loaded when editing files under `backend/agents/capabilities/`. See `invariants.md` for hard constraints.

---

## Capability Registration Rules

### Self-registration pattern
```python
@register("kind", "name", user_allowed=True)  # or user_allowed=False for privileged
class MyCapability:
    name = "name"  # must match registry key
```

### Two-surface discipline (INV-12)
Every capability must be registered in **both**:
1. `_KNOWN` literal tuple in `registry.py` — compiler membership check (impl-free)
2. `discover()`'s `_builtin_modules` import tuple in `registry.py` — runtime `@register` binding

A capability in `_KNOWN` but absent from `_builtin_modules` compiles but raises `RuntimeError("known but has no bound impl")` at runtime.

### Registry counter
Current `_KNOWN` count = **69** (after Phase 22 + Phase 51 additions).
Update the drift-guard count in `test_registry_capabilities.py` in lockstep every time you add a capability.

---

## Capability Kinds & Trust

| Kind | Examples | `user_allowed` |
|------|---------|---------------|
| `strategy` | `single_shot`, `task_loop`, `fanout_batch`, `wave_scheduler` | True |
| `deliverable` | `single_file`, `serialized_sandbox`, `ppt`, `repo_diff` | True |
| `validator` | `html_static`, `html_render`, `api_prefix`, `code_compile` | True |
| `gate` | `human`, `validation` | True |
| `gate` | `security`, `approval` | **False** |
| `context_provider` | `opendesign`, `previous_run`, `conversation`, `uploaded_files` | True |
| `task_parser` | `heading_tasks`, `json_tasks` | True |
| `compaction` | `html_skeleton`, `chat_history` | True |
| `post_step` | `revision_validation`, `api_prefix_audit` | True |
| `tool` | `workspace`, `prototype` | True |
| `tool` | `spawn_subagents` | **False** (CAP-03) |
| `runtime` | `langchain_deepagents` | **False** |
| `input_provider` | `run_images` | True |
| `chat` | `concierge` | True |
| `merge` | `copy_disjoint`, `git_3way`, `json`, `html_fragment` | True |

---

## Import Boundary Rules

Capabilities **must NOT** import:
- `agents.execution_engine.*` (import-linter gate)
- `app.*` — except app-side capabilities under `app/agents/` which import the port then `@register`

Capabilities **may** import:
- `agents.workflows.plan` (the compiled plan types)
- `agents.capabilities.base` (ports)
- `agents.capabilities.registry` (for resolution)
- stdlib only for kernel-side capabilities

The `KernelServices` (`ctx.runner`) handle is the only path capabilities use to reach the kernel, sandbox, validators, and store.

---

## Validator Pattern

```python
from agents.capabilities.validators.severity import map_severity, Issue

class MyValidator:
    name = "my_validator"

    async def validate(self, target, context) -> list[Issue]:
        ...
        await target.runner.record_validation_result(...)
```

- `map_severity` is the **single source** in `validators/severity.py` — never define P0/P1/P2/P3 → CRITICAL/HIGH/MEDIUM/LOW elsewhere.
- A validator wired as a `post_step` (event-free) must **not** emit `validation_warning` events — that would appear in the event stream and break INV-3 goldens.
- A validator wired via `gates:[validation]` **can** emit — but adding it to a golden pipeline requires re-baselining.

---

## Gate Handler Contract

- `evaluate_stream(step, ctx)` is the async-generator protocol (Phase 13 addition).
- `evaluate()` is a thin collector over the stream — do NOT duplicate gate logic in both.
- `HumanGate` and `ApprovalGate` **consume** a stray `_gate_redo` (map to `GATE_WAIT_HUMAN`, never `GATE_PASS`) — the F1 fence from Phase 23.
- `_FAIL_CLOSED_GATES = {security, approval, human}` — an exception maps to `block`.
- Validation/security gates keep the fail-open degrade path.

---

## Context Provider Contract

- Self-gates on the declared inject token — never a workflow-name check (SC-001).
- Reaches disk via `ctx.runner.sandbox` — never by importing `app.agents.sandbox.RunSandbox` directly.
- Degrades to `{}` on any missing store/empty result/read error (never raises).
- `context_provider:conversation` — bounds composed history via `compaction:chat_history` before returning the block.
- `context_provider:uploaded_files` — disk wins over durable mirror; block format is `## Uploaded Files`.

---

## Compaction Contract

- `compact(transcript, *, budget, keep_recent)` — measured in characters, recent-turn fidelity always wins.
- `chat_history` compaction: recent turns stay verbatim; older tail collapses to a summary marker.
- `html_skeleton` compaction: the 0C sanctioned INV-3 exception — still the **only** place deliverable bytes may change.

---

## Model Catalog Rules (single source)

- `model_catalog.py` is the **only** place model IDs and their `Pricing` dataclass live.
- `model_pricing.py` **derives** rates from the catalog via `_resolve_pricing` — zero `claude-haiku/sonnet/opus-4` literals allowed there.
- `test_single_source_grep` enforces this: `hits == {"model_catalog.py"}`.
- All 5 entries have `vision=True`; `user_allowed=True`; `cost_class` = cheap/standard/premium.
- Adding a model = edit `model_catalog.py` only. Never add a second model list.

---

## Capability Metadata (Phase 22)

`@register` accepts `description=` and `config_schema=` kwargs. These are surfaced via `GET /api/capabilities`. A newly registered capability appears in the palette with zero FE/API edit — SC-001 at the UX layer.
