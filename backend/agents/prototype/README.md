# agents/prototype — Prototype Pipeline Module

Everything related to the prototype pipeline lives here. This makes it easy
to understand, modify, and eventually replace the pipeline with the Spec Kit
Approach 2+3 implementation.

## Module Structure

```
agents/prototype/
├── __init__.py          — module docstring + public API
├── README.md            — this file
├── pipeline.py          — pipeline constants, agent IDs, behaviour flags
├── context.py           — load_prototype_context(): template + DS + craft loader
├── artifact_store.py    — PrototypeArtifactStore: shared HTML store across agents
└── tools.py             — LangChain tools: read_template_seed, emit_artifact, etc.
```

## Current Pipeline Flow (Approach 1 — single-shot)

```
User brief + template + design system
        ↓
SmartPlanner → CLARIFY_REQUIRED → ClarifyEngine (MCQ questions)
        ↓ (user answers)
Agent 1: requirements-analyst    → <spec> JSON (pages, routes, interactions)
Agent 2: html-prototype-builder  → full HTML SPA (emit_artifact → ArtifactStore)
Agent 3: prototype-polisher      → patched HTML (5-dim critique + fixes)
Agent 4: prototype-finalizer     → validated HTML (P0 structural checks)
        ↓
pipeline_complete → final_output = ArtifactStore.html
```

## Planned: Approach 2+3 (Spec Kit style)

When implemented, `pipeline.py` will contain `PrototypePipeline` — a
Spec Kit-style orchestrator that replaces the current 4-agent flow:

```
Phase 1: prototype-specify  → spec.md  (pages, components, interactions)
         [Human review gate — user edits spec.md before proceeding]
Phase 2: prototype-plan     → tasks.md (atomic build tasks)
Phase 3: prototype-builder  → HTML (one task at a time, workspace tools)
Phase 4: prototype-validate → final HTML (P0 checks)
```

`SKIP_PLANNER_FOR_PROTOTYPE` in `pipeline.py` toggles the front-end
SmartPlanner + ClarifyEngine. Currently `False`: the planner + clarifier run
before the agents, so the user answers a clarifying questionnaire first, then the
spec-kit agents (specify → plan → build → validate) run. Set it `True` to skip
them and let prototype-specify handle planning/clarification itself.

## Key Files Outside This Module

| File | What it does |
|------|-------------|
| `agents/prompts/requirements-analyst/AGENT.md` | Agent 1 prompt |
| `agents/prompts/html-prototype-builder/AGENT.md` | Agent 2 prompt |
| `agents/prompts/prototype-polisher/AGENT.md` | Agent 3 prompt |
| `agents/prompts/prototype-finalizer/AGENT.md` | Agent 4 prompt |
| `agents/prompts/prototype-revision-agent/AGENT.md` | Revision agent prompt |
| `agents/guardrails/html-prototype.md` | Shared guardrail for all prototype agents |
| `agents/execution_engine/engine.py` | Calls `PrototypeArtifactStore`, reads HTML after each agent |
| `agents/factory.py` | Creates `make_prototype_tools()` with shared store |
| `agents/execution_engine/od_context.py` | Re-exports `load_prototype_context` |
| `app/agents/tools/prototype.py` | Backward-compat shim → imports from this module |
| `frontend/src/components/preview/PrototypePreview.tsx` | Renders the HTML in an iframe |
| `frontend/src/app/workflow/prototype/templates/page.tsx` | Wizard: template + DS picker |
