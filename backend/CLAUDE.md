# Backend Architecture Guide

> Principal-engineer reference for the IdeaFlowAI backend.
> Covers the deepagents-based agent runtime, the folder-per-agent configuration layer,
> extension patterns, testing, and commit conventions.

<!-- SPECKIT START -->
**Active Feature Plans**:
- [specs/001-ai-workflow-os/plan.md](../specs/001-ai-workflow-os/plan.md) (v3.0 — Universal Workflow Orchestration Engine)
- [specs/002-deepagents-migration/plan.md](../specs/002-deepagents-migration/plan.md) — **in progress**: the migration of the agent runtime onto the LangChain `deepagents` library. This guide describes the **post-migration (live) pipeline runtime** that plan landed (Phases 0–6 complete). The free-chat subsystem is mid-migration (Phase 7b) — see [The free-chat path](#the-free-chat-path).
<!-- SPECKIT END -->

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Adding an Agent](#adding-an-agent)
3. [Adding a Pipeline](#adding-a-pipeline)
4. [Adding a Guardrail](#adding-a-guardrail)
5. [Tool Sets](#tool-sets)
6. [Skills vs Guardrails vs Hooks](#skills-vs-guardrails-vs-hooks)
7. [The free-chat path](#the-free-chat-path)
8. [Testing](#testing)
9. [Commit Conventions](#commit-conventions)

---

## Architecture Overview

The backend runs every **pipeline** agent as a LangChain **`deepagents`** graph, sequenced
deterministically by the **`ExecutionEngine`**; the LLM never decides *which* agent runs next.
At run entry the engine compiles a typed, validated **`CompiledWorkflow`** from a declarative
manifest (`agents/workflows/<id>/workflow.yaml`) via `compile_for_run(pipeline_type)`, and
sources the agent **sequence**, the **deliverable** spec, the **clarify** config, and the
**planner** flag from that compiled plan. Per-step capabilities — strategy, gates, validators,
compaction, task_source, deliverable — likewise come from the manifest's `steps`. The
**registry** keeps its real, narrower role: `registry.PIPELINE_AGENTS` / `get_pipeline_agents()`
provide agent **membership/order**. Crisply: the **registry says *which* agents belong to a
pipeline** (membership/order); the **manifest (`workflow.yaml`) says *how* they run** (per-step
capabilities + deliverable + clarify + planner). Each agent is a `create_deep_agent`
graph wrapped by a thin `DeepAgentRunner` adapter that maps the LangGraph event stream onto
the WebSocket event vocabulary the frontend already consumes — so the runtime was swapped
under the hood with the UI unchanged.

### Directory Layout

```
backend/
├── agents/                             # Agent configuration + execution layer
│   ├── prompts/                        # One folder per agent (~80 total)
│   │   ├── domain-analyst/
│   │   │   └── AGENT.md                # Frontmatter metadata + system prompt body
│   │   ├── prototype-build/
│   │   │   └── AGENT.md
│   │   └── ... (one folder per agent)
│   ├── guardrails/                     # Shared, injectable rule sets (9 files)
│   │   ├── agile.md   typescript.md   react.md   accessibility.md
│   │   ├── html-prototype.md   openapi.md   java-spring.md
│   │   ├── mulesoft.md   dotnet.md
│   ├── loader.py                       # Reads + parses AGENT.md → AgentSpec
│   ├── factory.py                      # create_runner() + AgentContext + prompt/tool composition
│   ├── registry.py                     # PIPELINE_AGENTS + helpers (single source of truth)
│   ├── planner/tools.py                # PLANNING_TOOLS (deep-planner stub tools)
│   └── execution_engine/
│       ├── engine.py                   # ExecutionEngine — the deterministic sequencer
│       ├── resolver.py                 # WorkflowResolver (DAG validation)
│       └── state_machine.py
└── app/
    └── agents/
        ├── deep_agent_runner.py        # DeepAgentRunner — adapter over a deepagents graph
        ├── model_factory.py            # build_model() — provider select + botocore retries
        ├── sandbox.py                  # RunSandbox + serialize_sandbox_deliverable()
        ├── checkpointer.py             # get_checkpointer() (Postgres / InMemory dev)
        ├── render_check.py             # render_check() — headless Chromium validation
        ├── static_check.py             # static_check() — stdlib structural validation
        └── tools/
            └── runner_tools.py         # report_task_complete (store-free runner tool)
```

> Note: `app/agents/` still contains the **legacy free-chat stack** (`orchestrator.py`,
> `base.py`, `deep_agent.py`, the chat agents) and some dead pipeline-legacy modules
> (`tools/workspace.py`, `tools/prototype.py`, `summarizer.py`, `agents/prototype/*`).
> These are **not on the live pipeline path** — they are being excised / migrated in
> migration Phase 7. Do not extend them; see [The free-chat path](#the-free-chat-path).

### Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `agents/loader.py` | Read `AGENT.md` files, parse YAML frontmatter, validate all fields, cache results in `_SPEC_CACHE`; expose `AgentSpec`, `load_agent_spec()`, `list_agent_ids()`, `SUPPORTED_PIPELINE_TYPES` |
| `agents/registry.py` | Hold `PIPELINE_AGENTS` + `REVISION_BASE_MAP`; expose `get_pipeline_agents()`, `get_all_agents_flat()`, `get_agent_by_id()`, `allowed_custom_agent_ids()` — the single source of truth for agent membership/ordering |
| `agents/factory.py` | `create_runner(agent_id, ctx)` — the **live** entry point; composes the system prompt (`_compose_system_prompt`), resolves tools (`_resolve_runner_tools`), builds the per-run `RunSandbox`, and constructs a `DeepAgentRunner`. Owns `AgentContext`. |
| `agents/execution_engine/engine.py` | `ExecutionEngine` — the deterministic sequencer. `execute()` drives the pipeline; `_run_agent` runs one agent via a single `astream_events` loop; per-agent HITL gates; prototype per-task sub-agent build loop + validation |
| `app/agents/deep_agent_runner.py` | `DeepAgentRunner` — wraps a `deepagents.create_deep_agent` graph; `astream_events()` maps LangGraph events → engine events; disk filesystem backend; HITL `gate` detection |
| `app/agents/model_factory.py` | `build_model()` — Bedrock/Anthropic provider select + botocore timeouts/retries (one place) |
| `app/agents/sandbox.py` | `RunSandbox(user_id, run_id)` — per-user/per-run disk dir (traversal-proof, TTL sweep); `serialize_sandbox_deliverable()` turns written files into the `filename:`-block deliverable string |
| `app/agents/render_check.py` / `static_check.py` | Per-task prototype validation (headless render + stdlib structural checks) |
| `agents/guardrails/*.md` | Terse, prompt-injectable rule sets; injected verbatim by the factory before the prompt body |
| `agents/prompts/{id}/AGENT.md` | Single source of truth for each agent's identity, metadata, and system-prompt body |

### Data Flow (pipeline `run_pipeline`)

```
WebSocket "run_pipeline" message  (app/api/websocket.py)
      │
      ▼
ExecutionEngine.execute(agents, user_message, pipeline_run_id, pipeline_type, …,
                        gate_agent_ids=…, parent_run_id=…)
      │   compiled = compile_for_run(pipeline_type)              ← typed CompiledWorkflow
      │       └─► resolve_alias(pipeline_type)                   ← id-alias → manifest id
      │       └─► load_manifest(agents/workflows/<id>/workflow.yaml)
      │       └─► _WORKFLOW_COMPILER.compile(manifest, registry) ← validated plan
      │       (raises FileNotFoundError if no manifest for the resolved id)
      │   sequence / deliverable / clarify / planner  ← FROM compiled plan
      │   registry.get_pipeline_agents(pipeline_type)            ← agent membership
      │   ASSERT [s.agent_id for s in compiled.steps] == membership  → else RuntimeError
      │   await get_checkpointer()                               ← Postgres / InMemory
      │   RunSandbox(user_id, pipeline_run_id)                   ← per-run disk dir
      │
      └─► for each AgentSpec (in the compiled sequence):
               │
               ├─► build AgentContext (skills/hooks/od_context/run_id=pipeline_run_id)
               ├─► _should_gate(spec)?  → _run_review_gate (HITL pause/resume between agents)
               ├─► create_runner(agent_id, ctx, thread_id="<run>:<agent>", checkpointer=…)
               │         │
               │         ├─► load_agent_spec(agent_id)            ← cache hit
               │         ├─► _compose_system_prompt()             ← injects + guardrails + skills + hooks + constitution + body
               │         ├─► _resolve_runner_tools()                ← (custom_tools, exclude_builtin)
               │         └─► DeepAgentRunner(... model=build_model(ctx.model), run_sandbox=…)
               │                   └─► create_deep_agent(graph): native fs tools + report_task_complete
               │
               └─► async for event in runner.astream_events(context_message):
                         chunk      → agent_chunk
                         usage      → token accumulation
                         tool_call  → tool_call   (report_task_complete → records task)
                         tool_result→ tool_result (report_task_complete → task_progress)
                         (gate)     → HITL interrupt
                   deliverable read back from the RunSandbox disk:
                     - prototype/revision: prototype.html
                     - code-gen: serialize_sandbox_deliverable(root) → `filename:` blocks
```

The engine is the **deterministic sequencer** — it compiles the run's `CompiledWorkflow` via
`compile_for_run(pipeline_type)` and drives the **ordered sequence from the compiled plan**,
calling `create_runner()` for each step. `registry.get_pipeline_agents` supplies the agent
**membership**; the engine **asserts** the compiled step agent-ids equal that membership and
raises `RuntimeError` on drift, so the manifest and registry can never silently diverge.
Deliverables live on the **per-run disk sandbox** (shared across the run's agents, so files
one agent writes persist for the next); the engine reads them back at the end of each agent.
Token totals come from the runner's `usage` events; library auto-summarization replaces the
old cross-agent summarizer.

### Prototype build: per-task sub-agents + validation

For the `prototype` pipeline, the `build` step does **not** run the build agent once. The
engine writes `spec.md` / `design.md` / `tasks.md` into the run sandbox, then launches **one
isolated sub-agent per task** (`_run_build_task_loop`): each invocation gets its task injected
under a `=== CURRENT TASK ===` block (and may `read_file` the spec/design for detail), writes/
edits `prototype.html` via the native filesystem tools, and calls `report_task_complete`. After
each task the engine runs **Both-validation** — `static_check` (stdlib: routes↔sections, routes
map, handlers, is-active) **+** `render_check` (headless Chromium: nav switches, no console
errors) — with a bounded **N=2 internal fix-loop** (`_run_validation_fix_loop`, a non-yielding
coroutine, so no extra UI events). Prototype **revision** runs the same validation as a
smart-hybrid policy and seeds the parent run's spec/design (via `parent_run_id`).

### Runtime essentials

- **Model**: `build_model(ctx.model)` selects ChatAnthropic (local, `ANTHROPIC_API_KEY`) or
  `ChatBedrockConverse` (prod). Model is **user-selected** (Haiku default). Botocore
  read-timeout + adaptive retries are embedded here.
- **Sandbox vs checkpoint thread**: the `RunSandbox` is keyed on `ctx.run_id` and **shared**
  across the run's agents (files persist agent-to-agent). The LangGraph checkpoint `thread_id`
  is **per agent-invocation** (`f"{run_id}:{agent_id}"`, plus `:task` in the build loop) so
  agents never collide on one checkpoint thread.
- **No per-agent iteration cap**: `recursion_limit = settings.AGENT_RECURSION_LIMIT` (400) is
  the backstop; the old per-agent `max_iterations` map is gone.
- **HITL**: `gate_agent_ids` (per-run) selects which agents pause for the inter-agent Human
  review gate; default = the static set (agents whose `AGENT.md` declares `gate: Human_Gate`,
  e.g. `prototype-specify`, `prototype-plan`). Durable via the checkpointer; `_run_review_gate`
  emits the `review_gate_*` events.
- **`write_file` won't overwrite** (deepagents `FilesystemBackend`): prototype Task 1 uses
  `write_file`, all later tasks + fixes use `edit_file` — enforced by the prompt and fix-loop.

---

## Adding an Agent

### Step 1 — Create the agent folder and AGENT.md

```
backend/agents/prompts/{your-agent-id}/AGENT.md
```

Use kebab-case for the folder name. The `id` field in the frontmatter must match the folder
name exactly.

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

Open `agents/registry.py` and add the agent ID to the correct pipeline list at the correct
position:

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

`get_pipeline_agents()` discovers agents by scanning `agents/prompts/` for files whose
`pipeline_type` matches, then sorts by `order`; `PIPELINE_AGENTS` is the canonical ordered
membership list the engine drives and the `/api/agents` endpoint reads.

### Step 4 — Verify

```bash
cd backend
python3.11 -m pytest tests/agents/test_loader.py -k "schema_validation" -v
```

The schema-validation test calls `load_agent_spec` for every agent in `agents/prompts/` and
will catch any missing or invalid fields.

### AGENT.md Schema

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | string | *(required)* | Kebab-case identifier; must match the folder name exactly |
| `name` | string | *(required)* | Human-readable display name shown in the UI |
| `role` | string | *(required)* | Short role description shown in the UI progress panel |
| `pipeline_type` | string | *(required)* | Pipeline this agent belongs to; must be one of `SUPPORTED_PIPELINE_TYPES` |
| `order` | integer | *(required)* | Execution position within the pipeline (ascending, unique per pipeline) |
| `max_tokens` | integer | *(required)* | Documented per-agent output ceiling (1–32768). Retained for the UI/spec; the runtime caps every agent at `settings.MAX_OUTPUT_TOKENS`, not this value |
| `tools` | list[str] | `[]` | Tool sets to bind: `"workspace"`, `"prototype"`, `"prototype_emit_only"`, `"planning"` (see [Tool Sets](#tool-sets)) |
| `guardrails` | list[str] | `[]` | Guardrail file names (without `.md`) injected before the prompt body |
| `context_from` | list[str] | `[]` | **Legacy/vestigial.** Still parsed and stored by the loader (`AgentSpec.context_from`) for backward-compat, but **no longer drives** the engine's context injection — live inter-agent routing is by `produces`/`consumes` (see [context_from examples](#context_from-examples)) |
| `icon` | string | `"🤖"` | Emoji icon displayed in the UI pipeline progress panel |
| `estimated_duration` | float | `3.0` | Estimated run time (seconds) used for UI progress animation |
| `description` | string | *(falls back to `role`)* | Longer UI/API blurb; absence never errors (loader falls back to `role`) |
| `gate` | string\|null | `null` | `Human_Gate` puts the agent in the default review-gate set; `Validation_Gate`; or absent |
| `injects` | list[str] | `[]` | For od_prototype/od_ppt agents: any of `[template, design_system, craft]` (composed into the prompt by `_compose_injection`) |
| `produces` / `consumes` | list[str] | `[]` | **The live inter-agent routing mechanism.** An upstream agent's typed output reaches this agent IFF `set(upstream.produces) & set(this.consumes)` is non-empty; the content is read from the typed artifact graph (`ectx.artifacts`) via `_filter_consumed_outputs` / `_latest_typed_content` in `engine.py`. Also read by `WorkflowResolver` for DAG validation |

### `context_from` Examples

> **Note:** `context_from` is **legacy**. It is still parsed and stored, but the engine no
> longer routes context from it — `produces`/`consumes` (via `_filter_consumed_outputs`) is what
> actually routes inter-agent context at runtime. The examples below are retained for reference.

**Example 1 — only the user brief (no prior output)**

```yaml
context_from: []
```

The engine builds the context message from the user request alone. Use for the first agent in
a pipeline.

**Example 2 — the immediately preceding agent's output**

```yaml
context_from: ["$previous"]
```

The special token `"$previous"` always resolves to the agent that ran immediately before this
one. If this agent is first, no prior output is included.

**Example 3 — the outputs of exactly two named agents**

```yaml
context_from: ["agent-a", "agent-b"]
```

The engine includes the named agents' outputs; any whose output is not yet available is
silently omitted. Use explicit IDs for non-adjacent upstream context (common in `app_builder`).

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

Follow [Adding an Agent](#adding-an-agent). Set `pipeline_type` to your new type string and
assign sequential `order` values starting at 1.

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

### Step 4 — (Required) Create the workflow manifest

Create `agents/workflows/<your_new_pipeline>/workflow.yaml`. This manifest is **not optional**:
at run entry `compile_for_run(pipeline_type)` resolves the id and calls
`load_manifest(agents/workflows/<id>/workflow.yaml)` — **without this file it raises
`FileNotFoundError`** and the run never starts. The manifest declares the per-step `steps`
(each step's `agent_id` + its capabilities), the `deliverable`, the `clarify` config, and the
`planner` flag.

The manifest's step `agent_id`s must **match the `PIPELINE_AGENTS` membership and order** for
this pipeline, or the engine aborts at run entry with `RuntimeError` (the membership assertion
in `engine.py`). Copy an existing `agents/workflows/<id>/workflow.yaml` (e.g.
`agents/workflows/prototype/workflow.yaml`) as the template rather than hand-writing the keys.

### Step 5 — (Optional) Add a REVISION_BASE_MAP entry

If this pipeline has a corresponding revision pipeline:

```python
REVISION_BASE_MAP: dict[str, str] = {
    ...
    "your_new_pipeline_revision": "your_new_pipeline",
}
```

> Inter-agent context routing is driven by the typed `produces`/`consumes` contracts (the live
> mechanism, via `_filter_consumed_outputs`; also validated as a DAG by `WorkflowResolver`).
> `context_from` is **legacy/vestigial** — still parsed, but not used by the engine. There is no
> separate context-map table to maintain.

---

## Adding a Guardrail

A guardrail is a terse, reusable rule set injected verbatim into an agent's system prompt
before the prompt body.

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
- **Injection order**: Guardrails are injected before skills, hooks, the constitution, and the
  prompt body. Multiple guardrails are injected in list order.
- **Section heading**: Each guardrail block is preceded by `## Guardrail: {name}` in the
  composed system prompt.
- **Fallback behavior**: A missing guardrail file logs a warning and uses an empty block — the
  agent still runs with the remaining guardrails and prompt body intact.

### Available Guardrails

| Name | File | Use for |
|------|------|---------|
| `agile` | `agile.md` | User story format, acceptance criteria, story-point estimation |
| `typescript` | `typescript.md` | TypeScript strict mode, type safety, module conventions |
| `react` | `react.md` | React component patterns, hooks, accessibility in JSX |
| `accessibility` | `accessibility.md` | WCAG 2.1 AA compliance, ARIA, keyboard navigation |
| `html-prototype` | `html-prototype.md` | Single-file HTML prototypes, inline CSS/JS constraints |
| `openapi` | `openapi.md` | OpenAPI 3.x spec format, path/schema conventions |
| `java-spring` | `java-spring.md` | Spring Boot patterns, dependency injection, REST conventions |
| `mulesoft` | `mulesoft.md` | MuleSoft DataWeave, flow design, connector usage |
| `dotnet` | `dotnet.md` | .NET / C# conventions, Azure SDK patterns |

---

## Tool Sets

Agents request tools via the `tools` field in `AGENT.md`. Under the `deepagents` runtime, the
heavy lifting is done by the library's **native filesystem tools** (`write_file`, `read_file`,
`edit_file`, `ls`, `glob`, `grep`) plus `write_todos` — these write to the per-run `RunSandbox`
disk. `agents/factory.py::_resolve_runner_tools(spec, ctx)` maps each declared tool-set name onto
`(custom_tools, exclude_builtin_tools)`:

| `tools` value | What the agent gets | Notes |
|---|---|---|
| `[]` (text-only) | `([], exclude_builtin=True)` | Pure-text stream, **no** tool chips in the UI. The library's built-in tools are excluded entirely. |
| `"workspace"` | `([], exclude_builtin=False)` | Code-gen agents. Native fs tools write deliverables to the sandbox; `serialize_sandbox_deliverable()` turns them into the `filename:`-block output the frontend FilesTab/AppBuilderPreview parse. |
| `"prototype"` / `"prototype_emit_only"` | `([report_task_complete], exclude_builtin=False)` | Prototype agents write `prototype.html` via native `write_file`/`edit_file` and call `report_task_complete` (drives `task_progress`). |
| `"planning"` | `(PLANNING_TOOLS, exclude_builtin=True)` | Stub planning tools (`agents/planner/tools.py`); no disk access. Used by the deep-planner. |

The **library sub-agent dispatch tool (`task`) is always excluded** so the model cannot spawn
its own sub-agents — the engine orchestrates per-task sub-agents itself (prototype build loop).
Tool exclusion is enforced by a per-graph `_ToolFilterMiddleware` inside `DeepAgentRunner`
(built on the public `AgentMiddleware` / `ModelRequest.override` API).

`report_task_complete` (`app/agents/tools/runner_tools.py`) is **store-free**: it just returns a
confirmation string. The engine derives `task_progress` from the tool's call/result events
(reading `task_number`/`task_title` from the args) — it records nothing itself.

### Adding a custom runner tool

1. Implement a LangChain `@tool` (e.g. in `app/agents/tools/`) returning a string result.
2. Add a branch to `_resolve_runner_tools(spec, ctx)` in `agents/factory.py` that appends your
   tool for the new tool-set name (and sets `exclude_builtin` appropriately — `False` if the
   agent also needs the native fs tools, `True` for a no-disk tool-only agent). An unrecognized
   tool-set name raises `ValueError` naming the tool and the agent ID.
3. Declare it in the agent's `AGENT.md`: `tools: ["your_set"]`.

---

## Skills vs Guardrails vs Hooks

These three mechanisms all inject content into an agent's system prompt (via
`_compose_system_prompt` in `agents/factory.py`), but they come from different sources and
inject in a fixed order: **injects → guardrails → skills → hooks → constitution → prompt body**.

### Guardrails

- **What**: Terse, platform-specific rule sets stored as markdown in `agents/guardrails/`.
- **Source**: Filesystem — authored by engineers, version-controlled.
- **Scope**: Reusable across many agents.
- **Declared in**: The `guardrails` list in `AGENT.md` frontmatter.
- **When to use**: Consistent platform conventions across a group of agents.

### Skills

- **What**: User-attached capability documents provided at runtime through the UI.
- **Source**: Runtime — attached by the end user per request.
- **Scope**: Session-scoped — passed in `AgentContext.attached_skills`, applies only to the
  current run.
- **When to use**: Project-specific context (brand guidelines, coding standards) that varies
  per request.

### Hooks

- **What**: Event-driven behavioral guideline blocks attached by the user at runtime.
- **Source**: Runtime — attached by the end user.
- **Scope**: Session-scoped — passed in `AgentContext.attached_hooks`. The factory synthesizes
  an "Active Behavioral Hooks" block from each hook's name/event/description.
- **When to use**: Output-format or post-processing instructions applied to every agent in a run.

### Summary

| | Guardrails | Skills | Hooks |
|---|---|---|---|
| Source | Filesystem (version-controlled) | Runtime (user-attached) | Runtime (user-attached) |
| Scope | Reusable across agents | Per-session | Per-session |
| Declared in | `AGENT.md` frontmatter | `AgentContext.attached_skills` | `AgentContext.attached_hooks` |
| Injection order | after `injects` | after guardrails | after skills (before constitution + body) |
| Best for | Platform conventions | Project-specific context | Output-format requirements |

> A per-user **Constitution** (from Workflow_Memory) is injected last, just before the prompt
> body, by `_inject_constitution`. `injects` (template / design system / craft, for the
> od_prototype/od_ppt agents) is composed first by `_compose_injection`.

---

## The free-chat path

The conversational **`user_message`** WebSocket path is a **separate subsystem** from the
pipeline runtime above. It currently runs on the legacy `AgentOrchestrator` / `BaseAgent` stack
(`app/agents/orchestrator.py`, `app/agents/base.py`) — a multi-phase generator
(Discovery → Requirements → UserStories/PPT/Prototype/UIDesign → Preview) with its own event
vocabulary (`phase_start` / `stream` / `phase_end` / `complete`). This stack is **being migrated
onto the new runtime as a dedicated `ChatRunner` in migration Phase 7b**
([specs/002-deepagents-migration/plan.md](../specs/002-deepagents-migration/plan.md)); do not
extend it. The legacy `app/agents/deep_agent.py` (`DeepAgent`) is similarly transitional — it
powers title generation only and is being replaced by a direct `build_model().ainvoke` one-shot.

---

## Testing

Tests live under `backend/tests/`, split into:
- `tests/agents/` — the agent runtime: loader, registry, factory, guardrails, the deepagents
  runner/sandbox/static-check, and the migration's verify-gate tests.
- `tests/unit/` — engine, API, registry-consumer, resolver, workflow-memory, and other
  unit-level suites.
- `tests/integration/`, `tests/properties/`, `tests/fixtures/` — integration, Hypothesis
  property tests, and shared fixtures.

### Running the Test Suite

Use the project Python (`python3.11`, no venv — see the dev-runtime memory note):

```bash
cd backend

# Agent-runtime tests
python3.11 -m pytest tests/agents/ -v

# Specific files
python3.11 -m pytest tests/agents/test_loader.py -v
python3.11 -m pytest tests/agents/test_registry.py -v
python3.11 -m pytest tests/agents/test_create_runner.py -v
python3.11 -m pytest tests/agents/test_static_check.py -v

# Unit suites
python3.11 -m pytest tests/unit/ -v

# Property-based tests (Hypothesis)
python3.11 -m pytest tests/properties/ -v
```

### Test Categories

#### Loader / schema tests (`tests/agents/test_loader.py`)

Calls `load_agent_spec` for every agent ID in `agents/prompts/` and asserts each returns a valid
`AgentSpec` (no missing required fields, `spec.id` matches the directory, `max_tokens` in
1–32768, `order` a positive integer, etc.). Also covers error conditions (unknown ID →
`FileNotFoundError`; duplicate `order` within a pipeline → `AgentSpecError`; caching).

#### Registry tests (`tests/agents/test_registry.py`, `tests/agents/test_registry_helpers.py`)

`get_pipeline_agents` ordering (strictly ascending `order`, no duplicates) and the flat-list /
by-id / `allowed_custom_agent_ids` helpers (including the od_ pipeline handling).

#### Runner / sandbox tests (`tests/agents/test_create_runner.py`, `test_sandbox_deliverable.py`)

`create_runner` for one agent of each class behaves correctly against a scripted model + a temp
`RunSandbox`: text-only streams pure text (no tool chips); code-gen writes a file to the sandbox
disk; prototype-build writes `prototype.html` + emits a `report_task_complete` event; planning
exposes `PLANNING_TOOLS`. `serialize_sandbox_deliverable` is byte-checked against the
`filename:`-block format the UI expects.

#### Validation tests (`tests/agents/test_static_check.py`, `test_phase4_build_loop.py`, `test_phase5_*`)

`static_check` structural checks; the prototype per-task build loop (Both-validation + bounded
fix-loop); the revision smart-hybrid fix-loop selection + parent-context seeding.

#### Cutover tests (`tests/agents/test_phase3_cutover_verify.py`)

The engine→runner cutover and the runner's event-stream behavior.
`test_deep_agent_runner_hitl_live.py` is opt-in / SSO-gated (real Bedrock); scripted-model
helpers live in `tests/agents/_scripted_model.py`.

#### Guardrail tests (`tests/agents/test_guardrails.py`)

All nine guardrail files satisfy the structural constraints; a guardrail's content appears
verbatim in the composed system prompt.

#### Engine / API unit tests (`tests/unit/`)

`test_execution_engine.py`, `test_run_pipeline_validation.py`, `test_agents_api_real_registry.py`,
`test_workflow_resolver.py`, `test_resumability.py`, `test_revision_*`, etc.

### Test recipe notes (deepagents)

- **Scripted models**: stock LangChain fakes do **not** drive the deepagents loop. Use a minimal
  `BaseChatModel` whose `_stream` yields `AIMessageChunk`s with `tool_call_chunks` +
  `usage_metadata` and a no-op `bind_tools`; inject the instance as `model_id` (→ `ctx.model`).
- **`RUNS_ROOT`**: defaults to `/app/runs` (not writable locally) — monkeypatch it to a temp dir
  before `create_runner`.
- **`render_check`**: Chromium runs for real locally and degrades to a *skip* if unavailable.

> Migration Phase 7 is excising the dead pipeline-legacy and free-chat code, so some suites
> are being rewritten/removed alongside it (e.g. the old `test_factory.py` covering the deleted
> `create_agent`/`_build_tools` path). The live pipeline contract is covered by the
> `tests/agents/` runner/registry/loader/static-check suites and the `tests/unit/` engine/API
> suites above.

---

## Commit Conventions

All commits use a scoped prefix identifying the subsystem being changed, so the git log is
scannable and changelog generation is possible.

### Required Prefix Format

```
<type>(<scope>): <short description>
```

**Types**: `feat`, `fix`, `chore`, `test`, `docs`, `refactor`, `perf`

**Scopes**:

| Scope | Use for |
|-------|---------|
| `agents` | New or modified `AGENT.md` files, new agent folders |
| `engine` | Changes to `agents/execution_engine/` (the `ExecutionEngine` sequencer) |
| `runner` | Changes to `app/agents/deep_agent_runner.py` (the deepagents adapter) |
| `prompts` | Bulk prompt edits, prompt-body rewrites |
| `guardrails` | New or modified guardrail files in `agents/guardrails/` |
| `loader` | Changes to `agents/loader.py` |
| `factory` | Changes to `agents/factory.py` (`create_runner` / prompt + tool composition) |
| `registry` | Changes to `agents/registry.py` |
| `tools` | Changes to runner tools (`app/agents/tools/`) |
| `sandbox` | Changes to `app/agents/sandbox.py` / `model_factory.py` / `checkpointer.py` |
| `tests` | New or modified test files |

### Examples

```
feat(agents): add story-estimator agent to user_stories pipeline
fix(engine): make prototype task_progress count cumulative across the build loop
refactor(factory): drop the per-agent max_iterations map (recursion_limit backstop)
feat(runner): map LangGraph interrupt to a gate event via post-loop aget_state
feat(guardrails): add openapi guardrail for API-design agents
fix(loader): raise AgentSpecError when max_tokens exceeds 32768
test(agents): add create_runner isolation test for the prototype-build class
docs(agents): refresh CLAUDE.md to the deepagents runtime
```

### Rules

- Keep the subject line under 72 characters.
- Use the imperative mood ("add", "fix", "remove").
- Reference the relevant requirement/plan ID in the commit body when applicable.
- Never commit directly to `main`. Open a pull request and request review.
