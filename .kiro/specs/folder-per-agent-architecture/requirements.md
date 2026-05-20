# Requirements Document

## Introduction

This feature refactors the IdeaFlowAI backend agent system from a model where 85 agent prompts are hardcoded as Python string literals spread across 6 files into a folder-per-agent architecture. Every agent will live in `agents/prompts/{id}/AGENT.md` with YAML frontmatter declaring its metadata, tools, guardrails, and context routing. Every agent will be executed as a LangChain DeepAgent (text-only agents complete in one iteration with no tool calls). Guardrails will be extracted into standalone markdown files under `agents/guardrails/`. A single `create_agent(id, context)` factory becomes the universal entry point. The Python orchestrator remains the deterministic sequencer — it reads `PIPELINE_AGENTS[pipeline_type]` to get an ordered list of IDs and calls `create_agent()` for each; the LLM never decides which agent runs next.

## Glossary

- **Agent_Spec**: The parsed representation of an `AGENT.md` file, including all YAML frontmatter fields and the prompt body.
- **AGENT.md**: A markdown file with YAML frontmatter that fully describes one agent — its identity, pipeline membership, tools, guardrails, context routing, and system prompt body.
- **AgentContext**: A dataclass passed to `create_agent()` carrying the user request, accumulated prior-agent outputs, and any attached skills or hooks.
- **DeepAgent**: The existing `app.agents.deep_agent.DeepAgent` LangGraph ReAct agent. Text-only agents (tools: []) complete in one LLM call; tool-using agents loop until done.
- **Factory**: `agents/factory.py` — the module that exposes `create_agent(agent_id, ctx)` and composes the system prompt from the spec, guardrails, and skills.
- **Guardrail**: A terse, prompt-injectable markdown rule set stored in `agents/guardrails/{name}.md` and injected verbatim into the system prompt of any agent that declares it.
- **Loader**: `agents/loader.py` — the module that reads and parses `AGENT.md` files from disk and exposes `load_agent_spec(agent_id)` and `list_agent_ids(pipeline_type)`.
- **Pipeline_Type**: A string key (e.g., `user_stories`, `app_builder`, `prototype`) that maps to an ordered list of agent IDs in the slim registry.
- **Slim_Registry**: The refactored `agents/registry.py` that contains only `PIPELINE_AGENTS`, `PIPELINE_CONTEXT_MAPS`, `SUPPORTED_PIPELINE_TYPES`, and `REVISION_BASE_MAP` — no `AgentDefinition` instances or prompt strings.
- **System_Prompt**: The fully composed string passed to DeepAgent, built by concatenating guardrail content, skill content, and the AGENT.md prompt body.

---

## Requirements

### Requirement 1: AGENT.md File Format

**User Story:** As a developer, I want each agent defined in a self-contained `AGENT.md` file with YAML frontmatter, so that I can add, modify, or review any agent by editing a single file without touching Python source.

#### Acceptance Criteria

1. THE Agent_Spec SHALL contain the following required YAML frontmatter fields: `id` (string, kebab-case), `name` (string), `role` (string), `pipeline_type` (one of: `"user_stories"`, `"ppt"`, `"prototype"`, `"app_builder"`, `"mulesoft_to_springboot"`, `"dotnet_to_azure"`, `"reverse_engineer"`, `"custom"`), `order` (integer), `max_tokens` (integer, 1–32768 inclusive).
2. THE Agent_Spec SHALL contain the following optional YAML frontmatter fields with defined defaults: `tools` (list of strings, default `[]`), `guardrails` (list of strings, default `[]`), `context_from` (list of strings, default `[]`), `icon` (string, default `"🤖"`), `estimated_duration` (float, default `3.0`).
3. WHEN `tools` is an empty list `[]`, THE Loader SHALL assign an empty tool list to the agent, causing the Factory to instantiate it with no tools and complete in one LLM call.
4. WHEN `tools` contains `"workspace"`, THE Loader SHALL assign the workspace tool set (`write_file`, `read_file`, `list_workspace_files`) to the agent.
5. WHEN `tools` contains `"prototype"`, THE Loader SHALL assign the prototype tool set (`read_template_seed`, `read_layout_reference`, `read_checklist`, `todo_write`, `emit_artifact`) to the agent.
6. WHEN `context_from` is an empty list `[]`, THE Loader SHALL record that the agent receives only the original user brief with no prior-agent output.
7. WHEN `context_from` contains the string `"$previous"`, THE Loader SHALL record that the agent receives the immediately preceding agent's output.
8. WHEN `context_from` contains explicit agent IDs (strings other than `"$previous"`), THE Loader SHALL record that the agent receives the outputs of exactly those named agents.
9. THE Agent_Spec SHALL contain a prompt body below the YAML frontmatter closing delimiter (`---`) that contains at least one non-whitespace character.
10. IF an `AGENT.md` file is missing a required field or a required field contains an empty or non-conforming value (e.g., empty string for `id` or `name`, non-integer for `order`, `max_tokens` outside 1–32768), THEN THE Loader SHALL raise a descriptive `AgentSpecError` naming the invalid field, the expected type or constraint, and the file path.
11. WITHIN a single `pipeline_type`, no two `AGENT.md` files SHALL share the same `order` value; IF a duplicate `order` is detected during loading, THEN THE Loader SHALL raise an `AgentSpecError` identifying both conflicting agent IDs and the shared `order` value.

---

### Requirement 2: Agent Loader

**User Story:** As a developer, I want a `loader.py` module that reads and parses `AGENT.md` files from disk, so that the rest of the system can access agent specs without knowing the file layout.

#### Acceptance Criteria

1. THE Loader SHALL expose a `load_agent_spec(agent_id: str) -> AgentSpec` function that reads `agents/prompts/{agent_id}/AGENT.md` and returns a parsed `AgentSpec` dataclass.
2. THE Loader SHALL expose a `list_agent_ids(pipeline_type: str) -> list[str]` function that returns all agent IDs whose `pipeline_type` field matches the given value, ordered by their `order` field in ascending order.
3. WHEN `load_agent_spec` is called with an agent ID whose directory does not exist or whose `AGENT.md` file does not exist, THE Loader SHALL raise a `FileNotFoundError` with a message that includes the expected file path.
4. WHEN `load_agent_spec` is called with an agent ID whose `AGENT.md` file exists but cannot be read due to a permission error, THE Loader SHALL raise a `PermissionError` with a message that includes the expected file path.
5. THE Loader SHALL parse the YAML frontmatter and the markdown body, populating all `AgentSpec` fields including defaults for optional fields; IF the frontmatter contains an invalid field value, THE Loader SHALL raise an `AgentSpecError` as defined in Requirement 1, criterion 10.
6. THE Loader SHALL cache parsed `AgentSpec` instances in memory so that repeated calls for the same agent ID do not re-read the file from disk during a single process lifetime.
7. WHEN `list_agent_ids` is called with a `pipeline_type` that matches no agent's `pipeline_type` field, THE Loader SHALL return an empty list.
8. FOR ALL valid `AGENT.md` files in the `agents/prompts/` tree, `load_agent_spec` SHALL return an `AgentSpec` whose `id` field matches the directory name.

---

### Requirement 3: Guardrail Files

**User Story:** As a developer, I want platform rule sets stored as standalone markdown files in `agents/guardrails/`, so that I can update a rule set once and have it apply to every agent that references it.

#### Acceptance Criteria

1. THE System SHALL provide the following nine guardrail files: `agile.md`, `typescript.md`, `react.md`, `accessibility.md`, `html-prototype.md`, `openapi.md`, `java-spring.md`, `mulesoft.md`, `dotnet.md`.
2. WHEN a guardrail file is referenced in an `AGENT.md`'s `guardrails` list, THE Factory SHALL read the corresponding `agents/guardrails/{name}.md` file and inject its full content into the agent's system prompt before the AGENT.md prompt body, preceded by a level-2 markdown heading of the form `## Guardrail: {name}`.
3. IF an `AGENT.md` references a guardrail name that has no corresponding file in `agents/guardrails/`, THEN THE Factory SHALL emit a warning to its standard logger and proceed with an empty string for that guardrail's content, so that the agent still runs with the remaining guardrails and prompt body intact.
4. THE System SHALL ensure each guardrail file is fewer than 60 lines and contains only plain markdown prose and lists — no fenced code blocks, no YAML front matter, and no Python source.
5. WHEN an agent declares multiple guardrails, THE Factory SHALL inject all of them into the system prompt in the order they appear in the `guardrails` list, each preceded by its own `## Guardrail: {name}` section header.

---

### Requirement 4: Agent Factory

**User Story:** As a developer, I want a `factory.py` module with a single `create_agent(agent_id, ctx)` entry point, so that any workflow can instantiate any agent with one call regardless of its tool configuration.

#### Acceptance Criteria

1. THE Factory SHALL expose `create_agent(agent_id: str, ctx: AgentContext) -> DeepAgent` as the single public entry point for agent instantiation.
2. WHEN `create_agent` is called, THE Factory SHALL call `load_agent_spec(agent_id)` to retrieve the spec, compose the system prompt, build the tool list, and return a configured `DeepAgent` instance.
3. THE Factory SHALL compose the system prompt by concatenating in order: (a) injected guardrail content blocks (reading the `"content"` key from each guardrail dict; empty lists contribute nothing), (b) injected skill content blocks from `ctx.attached_skills` (reading the `"content"` key; empty lists contribute nothing), (c) injected hook guidelines from `ctx.attached_hooks` (reading the `"content"` key; empty lists contribute nothing), (d) the AGENT.md prompt body.
4. WHEN `spec.tools` is `[]`, THE Factory SHALL instantiate `DeepAgent` with an empty tools list, causing the agent to complete in exactly one LLM call.
5. WHEN `spec.tools` contains `"workspace"` but not `"prototype"`, THE Factory SHALL pass only the workspace tool set (`write_file`, `read_file`, `list_workspace_files`) to `DeepAgent`.
6. WHEN `spec.tools` contains `"prototype"` but not `"workspace"`, THE Factory SHALL pass only the prototype tool set (`read_template_seed`, `read_layout_reference`, `read_checklist`, `todo_write`, `emit_artifact`) to `DeepAgent`.
7. WHEN `spec.tools` contains both `"workspace"` and `"prototype"`, THE Factory SHALL pass the union of both tool sets to `DeepAgent`.
8. THE Factory SHALL expose an `AgentContext` dataclass with fields: `user_request` (str), `agent_outputs` (dict[str, str]), `attached_skills` (list[dict], default `[]`), `attached_hooks` (list[dict], default `[]`), `workspace` (AgentWorkspace, optional).
9. IF `create_agent` is called with an unknown `agent_id`, THEN THE Factory SHALL propagate the `FileNotFoundError` raised by the Loader without swallowing it.
10. IF `load_agent_spec` raises an `AgentSpecError` (malformed AGENT.md), THEN THE Factory SHALL propagate that exception without swallowing it.
11. IF `spec.tools` contains a string that is neither `"workspace"` nor `"prototype"`, THEN THE Factory SHALL raise a `ValueError` identifying the unrecognized tool name and the agent ID.

---

### Requirement 5: Slim Registry

**User Story:** As a developer, I want `registry.py` to contain only pipeline-to-agent-ID mappings, so that adding a new agent requires only creating an `AGENT.md` file and adding its ID to the relevant pipeline list.

#### Acceptance Criteria

1. THE Slim_Registry SHALL contain `PIPELINE_AGENTS: dict[str, list[str]]` mapping each pipeline type to an ordered list of agent IDs.
2. THE Slim_Registry SHALL contain `PIPELINE_CONTEXT_MAPS: dict[str, dict[str, list[str]]]` mapping pipeline types that require non-linear context routing (e.g., `app_builder`) to their per-agent dependency graphs.
3. THE Slim_Registry SHALL contain `SUPPORTED_PIPELINE_TYPES: frozenset[str]` listing all valid pipeline type strings.
4. THE Slim_Registry SHALL contain `REVISION_BASE_MAP: dict[str, str]` mapping revision pipeline types to their base pipeline types.
5. THE Slim_Registry SHALL NOT contain any `AgentDefinition` dataclass instances, Python string literals used as system prompts, or `DEEP_AGENT_CONFIG` dictionaries.
6. THE Slim_Registry SHALL expose `get_pipeline_agents(pipeline_type: str) -> list[AgentSpec]` that calls `list_agent_ids(pipeline_type)` from the Loader and returns the corresponding `AgentSpec` objects sorted by ascending `AgentSpec.order`.
7. WHEN `get_pipeline_agents` is called with an unsupported pipeline type, THE Slim_Registry SHALL return an empty list.
8. IF `get_pipeline_agents` calls `load_agent_spec` for any agent ID and that call raises a `FileNotFoundError` or `AgentSpecError`, THEN `get_pipeline_agents` SHALL propagate that exception without swallowing it.

---

### Requirement 6: Updated Orchestrator

**User Story:** As a developer, I want `orchestrator_v2.py` to use `create_agent()` from the factory instead of constructing agents inline, so that the orchestrator is decoupled from agent definitions.

#### Acceptance Criteria

1. THE Orchestrator SHALL import `create_agent` and `AgentContext` from `agents/factory.py` and SHALL NOT import `AgentDefinition` from `registry.py`.
2. WHEN executing each agent in a pipeline, THE Orchestrator SHALL populate an `AgentContext` (setting `user_request`, `agent_outputs`, `attached_skills`, `attached_hooks`, and `workspace` fields) by reading `spec.context_from` to determine which prior-agent outputs to include in `agent_outputs`, then call `create_agent(agent_id, ctx)`; the Factory is responsible for formatting those fields into the final system prompt string.
3. WHEN `spec.context_from` is `[]`, THE Orchestrator SHALL set `agent_outputs` to an empty dict in the `AgentContext`, so the agent receives only the original user request.
4. WHEN `spec.context_from` is `["$previous"]` and the current agent is not the first in the pipeline, THE Orchestrator SHALL set `agent_outputs` to a dict containing only the immediately preceding agent's ID and its output; WHEN `spec.context_from` is `["$previous"]` and the current agent is the first in the pipeline, THE Orchestrator SHALL set `agent_outputs` to an empty dict.
5. WHEN `spec.context_from` contains explicit agent IDs, THE Orchestrator SHALL set `agent_outputs` to a dict containing only those agent IDs whose outputs are already available; agent IDs with no output yet SHALL be silently omitted from the dict.
6. THE Orchestrator SHALL move skill injection, hook injection, and guardrail injection into `factory._compose_system_prompt`, removing those responsibilities from the orchestrator's `execute()` loop.
7. THE Orchestrator SHALL preserve all existing WebSocket event types with the following required fields: `pipeline_start` (`type`, `data.pipeline_type`), `agent_start` (`type`, `data.agent_id`, `data.agent_name`), `agent_chunk` (`type`, `data.agent_id`, `data.chunk`), `agent_complete` (`type`, `data.agent_id`, `data.output`), `tool_call` (`type`, `data.agent_id`, `data.tool_name`, `data.input`), `tool_result` (`type`, `data.agent_id`, `data.tool_name`, `data.output`), `pipeline_complete` (`type`, `data.final_output`), `agent_error` (`type`, `data.agent_id`, `data.error`).
8. THE Orchestrator SHALL preserve the retry logic for transient Bedrock errors (ThrottlingException, ModelTimeoutException, etc.) unchanged.

---

### Requirement 7: Agent Prompt Migration

**User Story:** As a developer, I want all agent prompts extracted from Python source files into individual `AGENT.md` files, so that no agent prompt lives in Python source code.

#### Acceptance Criteria

1. THE System SHALL provide an `AGENT.md` file for every agent currently defined in `registry.py`, `app_builder_sdlc.py`, `migration_pipelines.py`, `ppt_pipeline.py`, `custom_agents.py`, and `od_runner.py`.
2. WHEN all `AGENT.md` files are present, THE Loader's `list_agent_ids(pipeline_type)` SHALL return the same ordered agent IDs for every pipeline type (`user_stories`, `ppt`, `ppt_revision`, `prototype`, `prototype_revision`, `app_builder`, `app_builder_revision`, `mulesoft_to_springboot`, `dotnet_to_azure`, `reverse_engineer`, `custom`) that the pre-migration `get_pipeline_agents(pipeline_type)` returned.
3. THE System SHALL migrate agents in the following batches: (1) `user_stories` pipeline (6 agents from `registry.py`), (2) `ppt` + `ppt_revision` pipelines (agents from `registry.py` and `ppt_pipeline.py`), (3) `prototype` + `prototype_revision` pipelines (agents from `registry.py`), (4) `app_builder` + `app_builder_revision` pipelines (agents from `registry.py` and `app_builder_sdlc.py`), (5) `mulesoft_to_springboot` pipeline (agents from `migration_pipelines.py`), (6) `dotnet_to_azure` pipeline (agents from `migration_pipelines.py`), (7) `custom` pipeline (agents from `custom_agents.py`), (8) remaining revision agents (from `registry.py`), (9) shared SDLC agents (from `od_runner.py`).
4. AFTER migration, THE System SHALL delete `app_builder_sdlc.py`, `ppt_pipeline.py`, `custom_agents.py`, and `migration_pipelines.py` from `app/agents/`; `od_runner.py` SHALL be retained with its non-prompt logic intact.
5. FOR ALL migrated agents, the `AGENT.md` prompt body SHALL be semantically equivalent to the original Python string literal, verified by a diff test that confirms no instruction sentences, role descriptions, output format rules, or constraint clauses were dropped or altered.

---

### Requirement 8: CLAUDE.md Principal-Engineer Guide

**User Story:** As a developer, I want a `backend/CLAUDE.md` file that documents the new architecture, so that any engineer (or AI assistant) can understand how to add agents, pipelines, guardrails, and tools without reading the source code.

#### Acceptance Criteria

1. THE System SHALL create `backend/CLAUDE.md` containing the following eight named sections: (a) "Architecture Overview" — directory layout and module responsibilities, (b) "Adding an Agent" — steps to create `AGENT.md` and add ID to `PIPELINE_AGENTS`, (c) "Adding a Pipeline" — steps to add a `PIPELINE_AGENTS` entry and optional `PIPELINE_CONTEXT_MAPS` entry, (d) "Adding a Guardrail" — steps to create a guardrail file and reference it in `AGENT.md`, (e) "Adding a Tool Set" — steps to implement a tool factory in `tools/` and register it in `factory.py`, (f) "Skills vs Guardrails vs Hooks" — definitions and when to use each, (g) "Testing" — how to run the test suite and what each test category covers, (h) "Commit Conventions" — required prefix format (`feat(agents):`, `fix(orchestrator):`, `chore(prompts):`).
2. THE CLAUDE.md SHALL document the `AGENT.md` schema with a field-by-field table listing each field's name, type, default value, and purpose, followed by a complete example `AGENT.md` that includes all 6 required fields (`id`, `name`, `role`, `pipeline_type`, `order`, `max_tokens`) and all 5 optional fields (`tools`, `guardrails`, `context_from`, `icon`, `estimated_duration`).
3. THE CLAUDE.md SHALL document the `context_from` field with three annotated examples: (a) `context_from: []` — agent receives only the user brief, (b) `context_from: ["$previous"]` — agent receives the immediately prior agent's output, (c) `context_from: ["agent-a", "agent-b"]` — agent receives the outputs of exactly those two named agents.
4. THE CLAUDE.md SHALL document the guardrail injection mechanism by describing: the file path pattern (`agents/guardrails/{name}.md`), the injection order (guardrails precede the prompt body), the fallback behavior when a file is missing (warning logged, empty string used), and the names of all nine available guardrails: `agile`, `typescript`, `react`, `accessibility`, `html-prototype`, `openapi`, `java-spring`, `mulesoft`, `dotnet`.
5. THE CLAUDE.md SHALL document the two tool sets with their exact tool names: `workspace` provides `write_file`, `read_file`, `list_workspace_files`; `prototype` provides `read_template_seed`, `read_layout_reference`, `read_checklist`, `todo_write`, `emit_artifact`.

---

### Requirement 9: Schema Validation and Smoke Tests

**User Story:** As a developer, I want automated tests that verify the new architecture is wired correctly, so that regressions are caught before deployment.

#### Acceptance Criteria

1. THE System SHALL provide a schema validation test that calls `load_agent_spec` for all agent IDs discoverable in `agents/prompts/` and asserts that each returns a valid `AgentSpec` with no missing required fields.
2. THE System SHALL provide a factory smoke test that calls `create_agent` for the first agent by `order` from each pipeline type and asserts that the returned `DeepAgent` has a non-empty `system_prompt`.
3. THE System SHALL provide a pipeline ordering test that calls `list_agent_ids(pipeline_type)` for every pipeline type and asserts the returned IDs are in strictly ascending `order` sequence with no duplicates.
4. THE System SHALL provide a guardrail injection test that calls `create_agent` for an agent that declares at least one guardrail and asserts that the guardrail file's full content appears verbatim in the `DeepAgent`'s `system_prompt`.
5. THE System SHALL provide a context routing test that inspects the `AgentContext` fields passed to `create_agent` and verifies: (a) an agent with `context_from: []` has `agent_outputs == {}`, (b) an agent with `context_from: ["$previous"]` has `agent_outputs` containing exactly one key (the prior agent's ID), (c) an agent with explicit IDs in `context_from` has `agent_outputs` containing exactly those IDs as keys.
6. WHEN the `user_stories` pipeline is executed end-to-end in a test with a mocked LLM (where the mock returns a non-empty string for every invocation), THE System SHALL fire all 6 agents in the correct order and accumulate their outputs in `WorkflowState.agent_outputs` such that `len(WorkflowState.agent_outputs) == 6` after completion.
7. IF the factory raises an error for any agent ID during the `user_stories` pipeline test, THEN THE pipeline SHALL halt and yield an `agent_error` event rather than continuing with incomplete context.
8. IF a required YAML field is absent from an `AGENT.md`, THEN THE schema validation test SHALL fail with an `AgentSpecError` message identifying the file path and the missing field name.
