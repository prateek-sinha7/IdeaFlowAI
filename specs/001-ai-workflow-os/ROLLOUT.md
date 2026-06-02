# Rollout Guide: Adding a New Pipeline Type to the Universal Engine

**Feature**: `001-ai-workflow-os` | **Phase 4 Hardening**

This guide describes the 5 steps required to add a new pipeline type to the
Universal Execution_Engine. Follow these steps in order.

---

## Step 1: Create AGENT.md files with produces/consumes contracts

For each agent in the new pipeline, create `backend/agents/prompts/{agent-id}/AGENT.md`
with the required frontmatter:

```yaml
---
id: my-new-agent
name: My New Agent
role: What this agent does
pipeline_type: my_new_pipeline   # must be in SUPPORTED_PIPELINE_TYPES
order: 1                          # unique within the pipeline
max_tokens: 4096
tools: []
produces: ["my_new_agent"]        # artifact types this agent produces
consumes: []                      # artifact types this agent requires
---

Your agent's system prompt goes here.
```

**Rules:**
- `produces` and `consumes` must form a satisfiable DAG (no cycles, all consumes satisfied upstream)
- `planning_context` and `constitution` are exempt — never add them to `consumes`
- `order` must be unique within the pipeline_type
- `pipeline_type` must be in `SUPPORTED_PIPELINE_TYPES` (add it in Step 2 if new)

---

## Step 2: Add the pipeline type to SUPPORTED_PIPELINE_TYPES and PIPELINE_AGENTS

In `backend/agents/loader.py`, add the new pipeline type to `SUPPORTED_PIPELINE_TYPES`:

```python
SUPPORTED_PIPELINE_TYPES: frozenset[str] = frozenset({
    # ... existing types ...
    "my_new_pipeline",
})
```

In `backend/agents/registry.py`, add the ordered agent list to `PIPELINE_AGENTS`:

```python
PIPELINE_AGENTS: dict[str, list[str]] = {
    # ... existing pipelines ...
    "my_new_pipeline": [
        "my-first-agent",
        "my-second-agent",
    ],
}
```

---

## Step 3: Validate the DAG with WorkflowResolver

Run the validation script to confirm the new pipeline resolves to a satisfiable DAG:

```bash
cd backend
python -c "
from agents.execution_engine.resolver import WorkflowResolver
from agents.registry import get_pipeline_agents
agents = get_pipeline_agents('my_new_pipeline')
result = WorkflowResolver().validate(agents)
print('satisfiable:', result.satisfiable)
print('errors:', result.errors)
print('order:', [a.id for a in result.dag])
"
```

If `satisfiable: False`, fix the `produces`/`consumes` contracts in the AGENT.md files.

---

## Step 4: Add to SUPPORTED_PIPELINE_TYPES in the frontend (if user-facing)

In `frontend/src/types/index.ts`, add the new type to the `WorkflowType` union:

```typescript
export type WorkflowType =
  | "user_stories"
  | "ppt"
  // ... existing types ...
  | "my_new_pipeline";
```

Add a label in `DashboardLayout.tsx` `PIPELINE_LABELS`:

```typescript
const PIPELINE_LABELS: Record<string, string> = {
  // ... existing labels ...
  my_new_pipeline: "My New Pipeline",
};
```

---

## Step 5: Add a regression test

In `backend/tests/integration/test_pipeline_workflows.py`, the structural
regression suite automatically picks up the new pipeline type from `PIPELINE_AGENTS`
and validates it. Confirm it passes:

```bash
cd backend
python -m pytest tests/integration/test_pipeline_workflows.py -k "my_new_pipeline" -v
```

For a live end-to-end test (requires LLM credentials), add a test to
`TestLiveStreamingRegression` following the existing `test_user_stories_event_sequence`
pattern.

---

## Checklist

- [ ] AGENT.md files created with valid produces/consumes contracts
- [ ] Pipeline type added to `SUPPORTED_PIPELINE_TYPES` in loader.py
- [ ] Agent list added to `PIPELINE_AGENTS` in registry.py
- [ ] `WorkflowResolver.validate()` returns `satisfiable: True`
- [ ] Frontend `WorkflowType` union updated (if user-facing)
- [ ] Structural regression test passes
- [ ] Live e2e test added (optional, requires credentials)
