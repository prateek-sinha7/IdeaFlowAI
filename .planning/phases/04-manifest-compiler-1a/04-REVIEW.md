---
phase: 04-manifest-compiler-1a
reviewed: 2026-06-07T00:00:00Z
depth: deep
files_reviewed: 47
files_reviewed_list:
  - backend/agents/capabilities/__init__.py
  - backend/agents/capabilities/base.py
  - backend/agents/capabilities/registry.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/workflows/__init__.py
  - backend/agents/workflows/app_builder/workflow.yaml
  - backend/agents/workflows/app_builder_revision/workflow.yaml
  - backend/agents/workflows/chat/workflow.yaml
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/custom/workflow.yaml
  - backend/agents/workflows/dotnet_to_azure/workflow.yaml
  - backend/agents/workflows/manifest.py
  - backend/agents/workflows/mulesoft_to_springboot/workflow.yaml
  - backend/agents/workflows/od_ppt/workflow.yaml
  - backend/agents/workflows/od_ppt_revision/workflow.yaml
  - backend/agents/workflows/plan.py
  - backend/agents/workflows/ppt/workflow.yaml
  - backend/agents/workflows/ppt_revision/workflow.yaml
  - backend/agents/workflows/prototype/workflow.yaml
  - backend/agents/workflows/prototype_revision/workflow.yaml
  - backend/agents/workflows/reverse_engineer/workflow.yaml
  - backend/agents/workflows/user_stories/workflow.yaml
  - backend/agents/workflows/user_stories_revision/workflow.yaml
  - backend/app/api/runs.py
  - backend/app/api/workflows.py
  - backend/app/main.py
  - backend/pyproject.toml
  - backend/tests/agents/test_compiled_plan_runs.py
  - backend/tests/agents/test_compiler.py
  - backend/tests/agents/test_edge_manifests.py
  - backend/tests/agents/test_id_alias_resolver.py
  - backend/tests/agents/test_manifest.py
  - backend/tests/agents/test_manifest_coverage.py
  - backend/tests/agents/test_manifest_parity.py
  - backend/tests/agents/test_pipeline_type_routing.py
  - backend/tests/agents/test_registry_capabilities.py
  - backend/tests/unit/test_runs_api.py
  - backend/tests/unit/test_workflows_api.py
  - frontend/src/components/preview/PPTPreview.tsx
  - frontend/src/components/preview/PreviewPanel.tsx
  - frontend/src/components/results/FilesTab.tsx
  - frontend/src/lib/api.ts
findings:
  critical: 1
  warning: 2
  info: 3
  total: 6
status: issues_found
---

# Phase 4: Manifest + Compiler [1A] — Code Review Report

**Reviewed:** 2026-06-07
**Depth:** deep
**Files Reviewed:** 47
**Status:** issues_found

## Summary

Phase 4 introduces the workflow declaration layer: 15 hand-authored `workflow.yaml` manifests,
a typed `WorkflowManifest` loader/validator, a thin no-DSL `WorkflowCompiler`, typed `plan.py`
contracts, a `CapabilityRegistry` name-seam, and the engine routing seam (4 concerns sourced
from the compiled plan). The `/api/workflows` namespace is reclaimed for manifest-derived
definitions; run-history CRUD moves atomically to `/api/runs` with all 10 frontend references
repointed. All 52 new Phase-4 tests pass.

The implementation is architecturally sound and correctly satisfies MAN-01 through MAN-05 and
API-01. The routing seam, IDOR ownership filters, and filename sanitization are correctly
carried over. Three concerns require attention before this can be considered fully correct:

1. A **critical gap** in INV-5/D-08 enforcement: the no-DSL strict-key rejection is applied
   only at the top level of the manifest; step-level dicts accept unknown keys silently.
2. A **warning-level data correctness bug**: the `GET /api/workflows` list endpoint returns
   misleading metadata (step_count=0, empty steps, wrong description) for the `ppt` workflow
   because `get_pipeline_agents("ppt")` returns an empty list.
3. A **warning-level protocol inconsistency**: `GateHandler` declares a `kind: str` attribute
   while all five other capability ports declare `name: str`, creating a naming mismatch with
   the registry's `(kind, name)` tuple semantics that will break Phase 7 implementations.

---

## Critical Issues

### CR-01: Step-level DSL fields silently accepted — INV-5 / D-08 not enforced below top level

**File:** `backend/agents/workflows/compiler.py:100-146`
**Issue:** The manifest loader enforces strict-key rejection only at the YAML top level
(`_ALLOWED_TOP_KEYS` in `manifest.py:76-89`). The compiler's `_compile_step` reads specific
keys from a raw step dict using `.get()` but performs **no allow-list check on the step dict's
own keys**. A step containing a DSL or control-flow field — e.g.
`{"agent": "x", "strategy": "single_shot", "when": "condition"}` — is parsed and compiled
without error. The `when:` key is silently ignored.

This directly violates D-08 ("Manifests are pure data. The loader/schema rejects unknown/extra
keys — so a conditional/loop/expression field simply has nowhere to live") and INV-5 ("any DSL
construct / control flow inside manifests — permanently out"). The test `test_rejects_dsl` only
covers a top-level `when:` key (caught by the loader) and an expression smuggled into a
capability name (caught by registry lookup) — it does not cover a step-level unknown key, which
would currently pass both guards.

The same gap applies to `task_source` dicts and the `clarify` / `deliverable` nested dicts,
which are also processed by `.get()` without key allow-listing.

**Fix:** Add a step-level key allow-list in `_compile_step`, analogous to `_ALLOWED_TOP_KEYS`:

```python
_ALLOWED_STEP_KEYS: frozenset[str] = frozenset({
    "agent", "strategy", "gates", "validators", "compaction", "task_source",
    # forward surface (inert in Phase 4 — declared now, consumed Phase 6/7)
    "tools", "model", "fix", "fanout", "on_conflict", "retry", "injects",
})

def _compile_step(self, raw: dict, registry: CapabilityRegistry) -> Step:
    extra = set(raw) - _ALLOWED_STEP_KEYS
    if extra:
        raise CompilerError(
            f"unknown step key(s) {sorted(extra)} in step {raw.get('agent', '?')!r} "
            f"— manifests are pure data; a DSL/control-flow field has nowhere to live (INV-5)"
        )
    # ... rest of existing logic unchanged
```

Add a corresponding test:
```python
def test_rejects_step_level_dsl_key() -> None:
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(
            _manifest(steps=[{"agent": "a", "strategy": "single_shot", "when": "cond"}]),
            CapabilityRegistry(),
        )
    assert "when" in str(exc.value)
```

---

## Warnings

### WR-01: `GET /api/workflows` list returns step_count=0 and empty steps for `ppt` workflow

**File:** `backend/app/api/workflows.py:148-162`
**Issue:** `list_workflows` calls `get_pipeline_agents(workflow_id)` to build the step summary
for each entry. For `workflow_id="ppt"`, `get_pipeline_agents("ppt")` returns `[]` because the
ppt agents declare `pipeline_type: od_ppt` in their AGENT.md files (they are shared with the
`od_ppt` pipeline). The result is that the `/api/workflows` list response for `ppt` shows:

```json
{
  "id": "ppt",
  "step_count": 0,
  "steps": [],
  "description": "Workflow defined; agents TBD."
}
```

This is factually wrong — `ppt` has 3 well-defined steps. The detail endpoint
(`GET /api/workflows/ppt`) is less affected (it calls `compile_for_run("ppt")` and returns
all 3 compiled steps), though step names fall back to agent IDs and `order=0` for all three
because `spec_by_id` is also empty.

The same pattern is known throughout the engine (the `ppt`/`get_pipeline_agents` discrepancy
pre-dates Phase 4 and is handled in the WebSocket layer with an explicit fallback). The list
endpoint does not apply the same fallback.

**Fix:** In `list_workflows`, apply the same fallback used in the engine and WebSocket layer
when `step_specs` is empty:

```python
from agents.registry import PIPELINE_AGENTS, get_pipeline_agents
# ...
for workflow_id in PIPELINE_AGENTS:
    step_specs = get_pipeline_agents(workflow_id)
    if not step_specs and workflow_id in PIPELINE_AGENTS:
        # Fallback: load AgentSpecs directly from PIPELINE_AGENTS membership
        # (handles 'ppt' whose agents declare pipeline_type: od_ppt)
        from agents.loader import load_agent_spec
        step_specs = [load_agent_spec(aid) for aid in PIPELINE_AGENTS[workflow_id]]
    # ... rest unchanged
```

Apply the same fallback in `get_workflow` for `spec_by_id` population so the detail endpoint
also returns real names/roles/orders for `ppt` steps.

---

### WR-02: `GateHandler` protocol declares `kind: str` while all other ports declare `name: str` — naming mismatch with registry semantics

**File:** `backend/agents/capabilities/base.py:87-95`
**Issue:** All five other capability Protocol ports (`TaskParser`, `ExecutionStrategy`,
`Validator`, `DeliverableResolver`, `ContextProvider`) declare a `name: str` attribute. The
`GateHandler` protocol declares `kind: str` instead:

```python
@runtime_checkable
class GateHandler(Protocol):
    kind: str         # ← inconsistent with every other port's 'name: str'
    async def evaluate(self, step: Any, ctx: Any) -> Any: ...
```

The `CapabilityRegistry` registers gates as `("gate", "human")` and `("gate", "validation")`,
where the second element is the capability **name**. When Phase 7 implements concrete gate
classes, they must satisfy the `GateHandler` Protocol (requiring a `kind` attribute) while
also being registered by name. This creates a semantic conflict: a gate implementation would
need both `self.name = "human"` (for registry registration, Phase 8) and `self.kind = ???`
(to satisfy the Protocol). The attribute these impls declare to identify themselves differs
from what every other capability uses.

**Fix:** Rename the attribute on `GateHandler` to `name: str` for consistency with all other
ports, so Phase 7 gate implementations have a uniform `name` attribute across all capability
kinds:

```python
@runtime_checkable
class GateHandler(Protocol):
    name: str   # capability name, e.g. "human" | "validation" | "approval" | "security"

    async def evaluate(self, step: Any, ctx: Any) -> Any:
        """Evaluate the gate, returning a gate outcome (pass | block | wait_human)."""
        ...
```

Update the pyproject.toml vulture `ignore_names` list to add `"name"` if needed (though
`name` is already a common attribute and is unlikely to be flagged). Update
`test_registry_capabilities.py` comment accordingly.

---

## Info

### IN-01: No import-linter contracts for the new `agents.workflows` and `agents.capabilities` packages

**File:** `backend/pyproject.toml:134-146`
**Issue:** The SPEC (§32 / SAFE-05) specifies a Ports & Adapters architecture where
`agents.workflows` and `agents.capabilities` must not import the kernel
(`agents.execution_engine`). The current import-linter config only enforces the existing
`engine → app.api` boundary. No contracts are added for the new packages, meaning:
- `agents.capabilities.registry` importing `agents.execution_engine` would not be caught.
- `agents.workflows.compiler` importing `agents.execution_engine` would not be caught.

Both currently respect the intended direction, but the boundary is unenforced — a future
accidental inward import would go undetected by CI.

**Fix:** Add two import-linter contracts:

```toml
[[tool.importlinter.contracts]]
name = "agents.workflows must not import the execution kernel"
type = "forbidden"
source_modules = ["agents.workflows"]
forbidden_modules = ["agents.execution_engine"]

[[tool.importlinter.contracts]]
name = "agents.capabilities must not import the execution kernel"
type = "forbidden"
source_modules = ["agents.capabilities"]
forbidden_modules = ["agents.execution_engine"]
```

---

### IN-02: `import re as _re` and `import json as _json` repeated inside a single handler function

**File:** `backend/app/api/runs.py:145,181,239,329`
**Issue:** Inside `export_pptx`, `import re as _re` appears twice (lines 181 and 239). In
`_extract_chain_context`, `import re as _re` and `import json as _json` are also deferred.
These modules are always needed when the functions execute; deferring them inside the function
body adds unnecessary repeated import overhead and obscures the module's actual dependencies.

**Fix:** Move `re` and `json` to module-level imports alongside the existing top-level imports:

```python
import json
import re
# ... rest of imports
```

Remove all `import re as _re` and `import json as _json` occurrences inside function bodies;
replace usages with `re.` and `json.` directly.

---

### IN-03: `test_manifest_coverage.py::test_all_load_compile` does not assert `step_count` or step names for `ppt` in the list endpoint

**File:** `backend/tests/unit/test_workflows_api.py:50-71`
**Issue:** The `test_list_entries_carry_metadata` test asserts step metadata only for the
`prototype` workflow. The `ppt` pipeline's broken list metadata (WR-01: step_count=0, empty
steps) is not covered by any test, so the regression introduced in the list endpoint is
currently invisible to the test suite. The `test_get_each_known_id_compiles` test does not
check the list endpoint's step_count.

**Fix:** Add a parametrized assertion that every workflow id in the list response has a
`step_count` matching the length of its compiled plan (not `get_pipeline_agents`):

```python
def test_list_step_counts_match_compiled_plan(self, client):
    from agents.execution_engine.engine import compile_for_run
    resp = client.get("/api/workflows")
    assert resp.status_code == 200, resp.text
    for entry in resp.json():
        compiled = compile_for_run(entry["id"])
        assert entry["step_count"] == len(compiled.steps), (
            f"{entry['id']}: list step_count {entry['step_count']} != "
            f"compiled plan {len(compiled.steps)}"
        )
```

---

_Reviewed: 2026-06-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
