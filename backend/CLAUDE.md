# Backend Architecture Guide

> Principal-engineer reference for the IdeaFlowAI backend.  
> Covers the folder-per-agent architecture, extension patterns, testing, and commit conventions.

<!-- SPECKIT START -->
**Active Feature Plan**: [specs/001-ai-workflow-os/plan.md](../specs/001-ai-workflow-os/plan.md) (v3.0 — Universal Workflow Orchestration Engine)
<!-- SPECKIT END -->

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Adding an Agent](#adding-an-agent)
3. [Adding a Pipeline](#adding-a-pipeline)
4. [Adding a Guardrail](#adding-a-guardrail)
5. [Adding a Tool Set](#adding-a-tool-set)
6. [Skills vs Guardrails vs Hooks](#skills-vs-guardrails-vs-hooks)
7. [Testing](#testing)
8. [Commit Conventions](#commit-conventions)

---

## Architecture Overview

### Directory Layout

```
backend/
├── agents/                             # Agent configuration layer
│   ├── prompts/                        # One folder per agent (85 total)
│   │   ├── domain-analyst/
│   │   │   └── AGENT.md               # Metadata + system prompt
│   │   ├── epic-architect/
│   │   │   └── AGENT.md
│   │   └── ... (one folder per agent)
│   ├── guardrails/                     # Shared, injectable rule sets
│   │   ├── agile.md
│   │   ├── typescript.md
│   │   ├── react.md
│   │   ├── accessibility.md
│   │   ├── html-prototype.md
│   │   ├── openapi.md
│   │   ├── java-spring.md
│   │   ├── mulesoft.md
│   │   └── dotnet.md
│   ├── loader.py                       # Reads + parses AGENT.md files
│   ├── factory.py                      # create_agent() entry point
│   ├── registry.py                     # Pipeline-to-ID maps only
│   └── __init__.py
├── app/
│   └── agents/
│       ├── deep_agent.py               # LangGraph ReAct executor (unchanged)
│       ├── orchestrator_v2.py          # Deterministic pipeline sequencer
│       ├── skills.py                   # Skill loading utilities
│       ├── tools/
│       │   ├── workspace.py            # write_file, read_file, list_workspace_files
│       │   └── prototype.py            # read_template_seed, read_layout_reference,
│       │                               # read_checklist, todo_write, emit_artifact
│       └── od_runner.py                # Non-prompt orchestration logic (retained)
└── CLAUDE.md                           # This file
```

### Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `agents/loader.py` | Read `AGENT.md` files from disk, parse YAML frontmatter, validate all fields, cache results in `_SPEC_CACHE`, expose `load_agent_spec()` and `list_agent_ids()` |
| `agents/factory.py` | Compose system prompts (guardrails → skills → hooks → body), build tool lists, instantiate `DeepAgent`, expose `create_agent()` and `AgentContext` |
| `agents/registry.py` | Hold `PIPELINE_AGENTS`, `PIPELINE_CONTEXT_MAPS`, `SUPPORTED_PIPELINE_TYPES`, `REVISION_BASE_MAP`; expose `get_pipeline_agents()` |
| `app/agents/orchestrator_v2.py` | Deterministic pipeline sequencer; reads registry for agent order; calls `create_agent()` per agent; streams WebSocket events |
| `agents/guardrails/*.md` | Terse, prompt-injectable rule sets; injected verbatim by the factory before the prompt body |
| `agents/prompts/{id}/AGENT.md` | Single source of truth for each agent's identity, metadata, and system prompt body |

### Data Flow

```
WebSocket request
      │
      ▼
orchestrator_v2.execute(user_message, pipeline_type)
      │
      ├─► registry.get_pipeline_agents(pipeline_type)
      │         │
      │         └─► loader.list_agent_ids(pipeline_type)   ← scans agents/prompts/
      │         └─► loader.load_agent_spec(id) × N         ← reads + caches AGENT.md
      │
      └─► for each AgentSpec (in order):
               │
               ├─► build AgentContext (driven by spec.context_from)
               ├─► factory.create_agent(agent_id, ctx)
               │         │
               │         ├─► loader.load_agent_spec(agent_id)   ← cache hit
               │         ├─► _compose_system_prompt()           ← guardrails + skills + hooks + body
               │         └─► _build_tools()                     ← workspace / prototype / []
               │
               └─► DeepAgent.astream_events(context_message)
                         │
                         └─► WebSocket events → client
```

The Python orchestrator is the **deterministic sequencer** — it reads `PIPELINE_AGENTS[pipeline_type]` to get an ordered list of IDs and calls `create_agent()` for each. The LLM never decides which agent runs next.

---

## Adding an Agent

### Step 1 — Create the agent folder and AGENT.md

```
backend/agents/prompts/{your-agent-id}/AGENT.md
```

Use kebab-case for the folder name. The `id` field in the frontmatter must match the folder name exactly.

### Step 2 — Write the AGENT.md

```markdown
---
id: your-agent-id
name: Human-Readable Agent Name
role: Short Role Description
pipeline_type: user_stories
order: 7
max_tokens: 4000
tools: []
guardrails: [agile]
context_from: ["$previous"]
icon: "🧠"
estimated_duration: 5.0
---

You are a [role]. [System prompt body here...]
```

### Step 3 — Add the agent ID to PIPELINE_AGENTS

Open `agents/registry.py` and add the agent ID to the correct pipeline list in the correct position:

```python
PIPELINE_AGENTS: dict[str, list[str]] = {
    "user_stories": [
        "domain-analyst",
        "epic-architect",
        "story-estimator",
        "nfr-specialist",
        "backlog-reviewer",
        "backlog-compiler",
        "your-agent-id",   # ← add here at the correct position
    ],
    ...
}
```

### Step 4 — Verify

```bash
cd backend
python -m pytest tests/agents/test_loader.py -k "schema_validation" -v
```

The schema validation test calls `load_agent_spec` for every agent in `agents/prompts/` and will catch any missing or invalid fields.

### AGENT.md Schema

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | string | *(required)* | Kebab-case identifier; must match the folder name exactly |
| `name` | string | *(required)* | Human-readable display name shown in the UI |
| `role` | string | *(required)* | Short role description shown in the UI progress panel |
| `pipeline_type` | string | *(required)* | Pipeline this agent belongs to; must be one of `SUPPORTED_PIPELINE_TYPES` |
| `order` | integer | *(required)* | Execution position within the pipeline (ascending, unique per pipeline) |
| `max_tokens` | integer | *(required)* | Maximum output tokens for this agent (1–32768 inclusive) |
| `tools` | list[str] | `[]` | Tool sets to bind: `"workspace"`, `"prototype"`, or both |
| `guardrails` | list[str] | `[]` | Guardrail file names (without `.md`) to inject before the prompt body |
| `context_from` | list[str] | `[]` | Prior-agent output routing (see [context_from examples](#context_from-examples) below) |
| `icon` | string | `"🤖"` | Emoji icon displayed in the UI pipeline progress panel |
| `estimated_duration` | float | `3.0` | Estimated run time in seconds used for UI progress animation |

### Complete Example AGENT.md

```markdown
---
id: story-estimator
name: Story Estimation Agent
role: Effort & Complexity Scoring
pipeline_type: user_stories
order: 3
max_tokens: 4000
tools: []
guardrails: [agile]
context_from: ["$previous"]
icon: "📊"
estimated_duration: 4.0
---

You are a Senior Agile Coach. Estimate the effort and complexity of each user story.

For every story produced by the previous agent, output:

- **Story ID**: Reference the story title
- **Story Points**: Fibonacci scale (1, 2, 3, 5, 8, 13)
- **Complexity**: Low / Medium / High
- **Rationale**: One sentence explaining the estimate

RULES:
- Use only Fibonacci story points
- Flag any story estimated at 13 points as a candidate for splitting
- Keep total response under 600 words
```

### `context_from` Examples

**Example 1 — Agent receives only the user brief (no prior output)**

```yaml
context_from: []
```

The orchestrator sets `agent_outputs = {}`. Use this for the first agent in a pipeline or any agent that should work only from the original user request.

**Example 2 — Agent receives the immediately preceding agent's output**

```yaml
context_from: ["$previous"]
```

The orchestrator sets `agent_outputs = {prev_agent_id: prev_output}`. The special token `"$previous"` always resolves to the agent that ran immediately before this one. If this agent is first in the pipeline, `agent_outputs` is `{}`.

**Example 3 — Agent receives the outputs of exactly two named agents**

```yaml
context_from: ["agent-a", "agent-b"]
```

The orchestrator sets `agent_outputs = {"agent-a": output_a, "agent-b": output_b}`. Any named agent whose output is not yet available is silently omitted. Use explicit IDs when an agent needs non-adjacent upstream context (common in the `app_builder` pipeline).

---

## Adding a Pipeline

### Step 1 — Add the pipeline type to SUPPORTED_PIPELINE_TYPES

Open `agents/loader.py` and add the new type to the frozenset:

```python
SUPPORTED_PIPELINE_TYPES: frozenset[str] = frozenset({
    "user_stories",
    "your_new_pipeline",   # ← add here
    ...
})
```

### Step 2 — Create AGENT.md files for each agent in the pipeline

Follow the steps in [Adding an Agent](#adding-an-agent). Set `pipeline_type` to your new pipeline type string and assign sequential `order` values starting at 1.

### Step 3 — Add the pipeline entry to PIPELINE_AGENTS

Open `agents/registry.py`:

```python
PIPELINE_AGENTS: dict[str, list[str]] = {
    ...
    "your_new_pipeline": [
        "first-agent-id",
        "second-agent-id",
        "third-agent-id",
    ],
}
```

### Step 4 — (Optional) Add a PIPELINE_CONTEXT_MAPS entry

If your pipeline has non-linear context routing (agents that need specific subsets of prior outputs rather than just `$previous`), add an entry to `PIPELINE_CONTEXT_MAPS`:

```python
PIPELINE_CONTEXT_MAPS: dict[str, dict[str, list[str]]] = {
    ...
    "your_new_pipeline": {
        "first-agent-id": [],
        "second-agent-id": ["first-agent-id"],
        "third-agent-id": ["first-agent-id", "second-agent-id"],
    },
}
```

If all agents use `context_from: ["$previous"]` or `context_from: []`, you do not need a `PIPELINE_CONTEXT_MAPS` entry.

### Step 5 — (Optional) Add a REVISION_BASE_MAP entry

If this pipeline has a corresponding revision pipeline:

```python
REVISION_BASE_MAP: dict[str, str] = {
    ...
    "your_new_pipeline_revision": "your_new_pipeline",
}
```

---

## Adding a Guardrail

A guardrail is a terse, reusable rule set injected verbatim into any agent's system prompt before the prompt body.

### Step 1 — Create the guardrail file

```
backend/agents/guardrails/{name}.md
```

**Structural constraints** (enforced by the test suite):
- Fewer than 60 lines
- Plain markdown prose and lists only
- No fenced code blocks (no ` ``` ` delimiters)
- No YAML frontmatter (no leading `---` block)

Example (`agents/guardrails/agile.md`):

```markdown
## Agile Guardrail

- Write user stories in "As a / I want / So that" format.
- Every story must have at least two Given/When/Then acceptance criteria.
- Prioritize stories as P0 (must-have), P1 (should-have), or P2 (nice-to-have).
- Stories must be estimable in Fibonacci story points (1, 2, 3, 5, 8, 13).
- Do not include implementation details in acceptance criteria.
```

### Step 2 — Reference the guardrail in AGENT.md

Add the guardrail name (without `.md`) to the `guardrails` list in any agent that should use it:

```yaml
guardrails: [agile, typescript]
```

### Guardrail Injection Mechanism

- **File path pattern**: `agents/guardrails/{name}.md`
- **Injection order**: Guardrails are injected before skills, hooks, and the prompt body. Multiple guardrails are injected in the order they appear in the `guardrails` list.
- **Section heading**: Each guardrail block is preceded by `## Guardrail: {name}` in the composed system prompt.
- **Fallback behavior**: If a referenced guardrail file does not exist, the factory logs a warning (`"Guardrail file not found: agents/guardrails/{name}.md — skipping"`) and uses an empty string for that block. The agent still runs with the remaining guardrails and prompt body intact.

### Available Guardrails

| Name | File | Use for |
|------|------|---------|
| `agile` | `agile.md` | User story format, acceptance criteria, story point estimation |
| `typescript` | `typescript.md` | TypeScript strict mode, type safety, module conventions |
| `react` | `react.md` | React component patterns, hooks, accessibility in JSX |
| `accessibility` | `accessibility.md` | WCAG 2.1 AA compliance, ARIA, keyboard navigation |
| `html-prototype` | `html-prototype.md` | Single-file HTML prototypes, inline CSS/JS constraints |
| `openapi` | `openapi.md` | OpenAPI 3.x spec format, path/schema conventions |
| `java-spring` | `java-spring.md` | Spring Boot patterns, dependency injection, REST conventions |
| `mulesoft` | `mulesoft.md` | MuleSoft DataWeave, flow design, connector usage |
| `dotnet` | `dotnet.md` | .NET / C# conventions, Azure SDK patterns |

---

## Adding a Tool Set

A tool set is a named group of LangChain tools that agents can request via the `tools` field in their `AGENT.md`.

### Step 1 — Implement the tool factory in `app/agents/tools/`

Create a new file (e.g., `app/agents/tools/analytics.py`) that exposes a `make_*_tools()` factory function returning a list of LangChain tool objects:

```python
# app/agents/tools/analytics.py
from langchain_core.tools import tool

@tool
def query_metrics(metric_name: str) -> str:
    """Query a named metric from the analytics store."""
    ...

@tool
def list_dashboards() -> str:
    """List all available analytics dashboards."""
    ...

def make_analytics_tools() -> list:
    return [query_metrics, list_dashboards]
```

### Step 2 — Register the tool set in `agents/factory.py`

Open `agents/factory.py` and add a branch to `_build_tools()`:

```python
def _build_tools(spec, ctx: AgentContext) -> list:
    from app.agents.tools.analytics import make_analytics_tools  # ← add import

    tools: list = []
    for tool_name in spec.tools:
        if tool_name == "workspace":
            ...
        elif tool_name == "prototype":
            ...
        elif tool_name == "analytics":                    # ← add branch
            tools.extend(make_analytics_tools())
        else:
            raise ValueError(
                f"Unrecognized tool name '{tool_name}' in agent '{spec.id}'. "
                f"Supported tool sets: 'workspace', 'prototype', 'analytics'."
            )
    return tools
```

### Step 3 — Use the tool set in an AGENT.md

```yaml
tools: ["analytics"]
```

### Existing Tool Sets

**`workspace`** — file I/O for code-generating agents

| Tool | Purpose |
|------|---------|
| `write_file` | Write content to a file in the agent workspace |
| `read_file` | Read the content of a file from the agent workspace |
| `list_workspace_files` | List all files currently in the agent workspace |

**`prototype`** — HTML prototype generation

| Tool | Purpose |
|------|---------|
| `read_template_seed` | Read the base HTML template seed for the prototype |
| `read_layout_reference` | Read the layout reference document |
| `read_checklist` | Read the prototype quality checklist |
| `todo_write` | Write a TODO item to the prototype task list |
| `emit_artifact` | Emit a completed artifact (HTML file) to the artifact store |

---

## Skills vs Guardrails vs Hooks

These three mechanisms all inject content into an agent's system prompt, but they serve different purposes and come from different sources.

### Guardrails

- **What**: Terse, platform-specific rule sets stored as markdown files in `agents/guardrails/`.
- **Source**: Filesystem — authored by engineers, version-controlled alongside the codebase.
- **Scope**: Reusable across many agents. A single guardrail file can be referenced by dozens of agents.
- **Declared in**: The `guardrails` list in `AGENT.md` frontmatter.
- **Injection position**: First — before skills, hooks, and the prompt body.
- **When to use**: When you want to enforce consistent platform conventions (e.g., "all TypeScript agents must follow strict mode") across a group of agents without duplicating the rules in every prompt.

### Skills

- **What**: User-attached capability documents provided at runtime through the UI.
- **Source**: Runtime — attached by the end user when submitting a request (e.g., "use our internal design system").
- **Scope**: Session-scoped. Skills are passed in `AgentContext.attached_skills` and apply only to the current pipeline run.
- **Declared in**: Not in `AGENT.md` — passed via `AgentContext` by the orchestrator.
- **Injection position**: Second — after guardrails, before hooks and the prompt body.
- **When to use**: When users need to inject project-specific context (brand guidelines, coding standards, domain knowledge) that varies per request.

### Hooks

- **What**: Event-driven guideline blocks attached by the user at runtime.
- **Source**: Runtime — attached by the end user (e.g., "always output a summary section at the end").
- **Scope**: Session-scoped. Hooks are passed in `AgentContext.attached_hooks` and apply only to the current pipeline run.
- **Declared in**: Not in `AGENT.md` — passed via `AgentContext` by the orchestrator.
- **Injection position**: Third — after guardrails and skills, immediately before the prompt body.
- **When to use**: When users need to add output format requirements or post-processing instructions that apply to every agent in a run.

### Summary

| | Guardrails | Skills | Hooks |
|---|---|---|---|
| Source | Filesystem (version-controlled) | Runtime (user-attached) | Runtime (user-attached) |
| Scope | Reusable across agents | Per-session | Per-session |
| Declared in | `AGENT.md` frontmatter | `AgentContext` | `AgentContext` |
| Injection order | 1st | 2nd | 3rd |
| Best for | Platform conventions | Project-specific context | Output format requirements |

---

## Testing

### Running the Test Suite

```bash
cd backend

# Run all agent tests
python -m pytest tests/agents/ -v

# Run a specific test file
python -m pytest tests/agents/test_loader.py -v
python -m pytest tests/agents/test_factory.py -v
python -m pytest tests/agents/test_registry.py -v
python -m pytest tests/agents/test_guardrails.py -v
python -m pytest tests/agents/test_orchestrator.py -v

# Run property-based tests only (Hypothesis)
python -m pytest tests/agents/ -k "property" -v

# Run with coverage
python -m pytest tests/agents/ --cov=agents --cov-report=term-missing
```

### Test Categories

#### Schema Validation Tests (`test_loader.py`)

Calls `load_agent_spec` for every agent ID discoverable in `agents/prompts/` and asserts:
- Each returns a valid `AgentSpec` with no missing required fields.
- `spec.id` matches the directory name.
- All field values satisfy their constraints (`max_tokens` in 1–32768, `order` positive integer, etc.).

Run these after adding or editing any `AGENT.md` file.

#### Loader Unit Tests (`test_loader.py`)

Tests for specific loader behaviors and error conditions:
- `load_agent_spec` with a non-existent agent ID → `FileNotFoundError` with path in message.
- `load_agent_spec` with an unreadable file → `PermissionError` with path in message.
- `load_agent_spec` called twice for the same ID → second call returns the cached instance.
- `list_agent_ids` with an unknown pipeline type → returns `[]`.
- Duplicate `order` within a pipeline → `AgentSpecError` naming both conflicting agent IDs.

#### Factory Unit Tests (`test_factory.py`)

Tests for tool resolution and prompt composition:
- `create_agent` with `tools: []` → `DeepAgent` has an empty tools list.
- `create_agent` with `tools: ["workspace"]` → workspace tools only.
- `create_agent` with `tools: ["prototype"]` → prototype tools only.
- `create_agent` with `tools: ["workspace", "prototype"]` → union of both sets.
- `create_agent` with an unknown tool name → `ValueError` with tool name and agent ID.
- `create_agent` with an unknown agent ID → `FileNotFoundError` propagated.
- Missing guardrail file → warning logged, agent still runs with empty guardrail block.

#### Factory Smoke Tests (`test_factory.py`)

For the first agent (by `order`) of each pipeline type, calls `create_agent` and asserts the returned `DeepAgent` has a non-empty `system_prompt`. Catches wiring regressions across all pipelines.

#### Registry Unit Tests (`test_registry.py`)

- `get_pipeline_agents` with an unsupported pipeline type → returns `[]`.
- `get_pipeline_agents` propagates `FileNotFoundError` from the loader.
- `get_pipeline_agents` propagates `AgentSpecError` from the loader.
- Registry contains no `AgentDefinition` instances or prompt strings.

#### Pipeline Ordering Tests (`test_registry.py`)

Calls `list_agent_ids(pipeline_type)` for every pipeline type and asserts the returned IDs are in strictly ascending `order` sequence with no duplicates.

#### Guardrail Tests (`test_guardrails.py`)

- All nine guardrail files satisfy structural constraints: fewer than 60 lines, no fenced code blocks, no YAML frontmatter.
- `create_agent` for an agent that declares at least one guardrail → the guardrail file's full content appears verbatim in the `DeepAgent`'s `system_prompt`.

#### Orchestrator Tests (`test_orchestrator.py`)

- `user_stories` pipeline executed end-to-end with a mocked LLM → all 6 agents fire in correct order, `len(WorkflowState.agent_outputs) == 6`.
- If `create_agent` raises for one agent → `agent_error` event emitted, pipeline halts.
- Context routing: `context_from: []` → `agent_outputs == {}`; `context_from: ["$previous"]` → exactly one key; explicit IDs → exactly those keys.

#### Property-Based Tests (Hypothesis)

Property tests use `@given` + `@settings(max_examples=100)` and are tagged with the property they validate:

| Property | What it tests |
|----------|--------------|
| Property 1: AgentSpec round-trip | Serialize a random valid `AgentSpec` to `AGENT.md`, parse back, assert all fields match |
| Property 2: Invalid AGENT.md raises AgentSpecError | Any `AGENT.md` with a missing/invalid required field always raises `AgentSpecError` with field name and path |
| Property 3: Duplicate order raises AgentSpecError | Two agents sharing the same `order` in a pipeline always raises `AgentSpecError` |
| Property 4: list_agent_ids strictly ascending | `list_agent_ids` always returns IDs in strictly ascending `order` with no duplicates |
| Property 5: context_from routing | `AgentContext.agent_outputs` contains exactly the keys specified by `context_from` |
| Property 6: System prompt composition order | Guardrails always precede skills, skills precede hooks, hooks precede prompt body |
| Property 7: Guardrail content verbatim | Guardrail file content always appears verbatim (unmodified) in the composed system prompt |
| Property 8: Guardrail structural constraints | All nine guardrail files satisfy line count, no code blocks, no frontmatter |
| Property 9: All AGENT.md files valid | Every discoverable `AGENT.md` produces a valid `AgentSpec` with `spec.id == directory_name` |
| Property 10: WebSocket events complete | Any pipeline run with a mocked LLM emits all required event types with required fields |

---

## Commit Conventions

All commits to this repository must use a scoped prefix that identifies the subsystem being changed. This makes the git log scannable and enables automated changelog generation.

### Required Prefix Format

```
<type>(<scope>): <short description>
```

**Types**: `feat`, `fix`, `chore`, `test`, `docs`, `refactor`, `perf`

**Scopes**:

| Scope | Use for |
|-------|---------|
| `agents` | New or modified `AGENT.md` files, new agent folders |
| `orchestrator` | Changes to `orchestrator_v2.py` |
| `prompts` | Bulk prompt edits, prompt body rewrites |
| `guardrails` | New or modified guardrail files in `agents/guardrails/` |
| `loader` | Changes to `agents/loader.py` |
| `factory` | Changes to `agents/factory.py` |
| `registry` | Changes to `agents/registry.py` |
| `tools` | Changes to `app/agents/tools/` |
| `tests` | New or modified test files |

### Examples

```
feat(agents): add story-estimator agent to user_stories pipeline
fix(orchestrator): preserve retry logic for ThrottlingException
chore(prompts): rewrite app-code-generator prompt body for clarity
feat(guardrails): add openapi guardrail for API design agents
fix(loader): raise AgentSpecError when max_tokens exceeds 32768
feat(factory): add analytics tool set registration
test(agents): add property test for AgentSpec round-trip (Property 1)
docs(agents): update CLAUDE.md with reverse_engineer pipeline steps
refactor(registry): remove legacy AgentDefinition references
```

### Rules

- Keep the subject line under 72 characters.
- Use the imperative mood ("add", "fix", "remove" — not "added", "fixes", "removed").
- Reference the relevant requirement ID in the commit body when applicable (e.g., `Implements: Requirement 8.1`).
- Never commit directly to `main`. Open a pull request and request review.
