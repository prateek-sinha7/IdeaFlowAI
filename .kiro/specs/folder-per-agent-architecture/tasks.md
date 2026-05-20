# Implementation Plan: Folder-Per-Agent Architecture

## Overview

Refactor 85 agent prompts from Python string literals across 6 files into a folder-per-agent architecture. Each agent gets its own `agents/prompts/{id}/AGENT.md` with YAML frontmatter. New modules `agents/loader.py`, `agents/factory.py`, and a slim `agents/registry.py` replace the current inline definitions. `orchestrator_v2.py` is updated to use `create_agent()` from the factory. Four Python files are deleted after migration. Property-based tests using Hypothesis validate all universal correctness properties.

## Tasks

- [x] 1. Set up directory structure and core data models
  - Create `backend/agents/` directory with `__init__.py`
  - Create `backend/agents/prompts/` and `backend/agents/guardrails/` directories
  - Create `backend/tests/agents/` directory with `conftest.py`
  - Define `AgentSpec` dataclass and `AgentSpecError` exception in `agents/loader.py`
  - Define `AgentContext` dataclass in `agents/factory.py`
  - _Requirements: 1.1, 1.2, 2.1, 4.8_

- [x] 2. Implement `agents/loader.py`
  - [x] 2.1 Implement `load_agent_spec(agent_id)` with YAML frontmatter parsing, field validation, and in-memory caching
    - Use `python-frontmatter` to parse `agents/prompts/{agent_id}/AGENT.md`
    - Validate all required fields: `id`, `name`, `role`, `pipeline_type`, `order`, `max_tokens`, prompt body
    - Apply defaults for optional fields: `tools=[]`, `guardrails=[]`, `context_from=[]`, `icon="🤖"`, `estimated_duration=3.0`
    - Raise `FileNotFoundError` if directory or file missing; `PermissionError` if unreadable; `AgentSpecError` for invalid fields
    - Cache results in module-level `_SPEC_CACHE: dict[str, AgentSpec]`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 2.1, 2.3, 2.4, 2.5, 2.6, 2.8_

  - [ ]* 2.2 Write property test for AgentSpec round-trip (Property 1)
    - **Property 1: AgentSpec round-trip**
    - Generate random valid `AgentSpec` instances with Hypothesis `valid_agent_spec()` strategy; serialize to a temp `AGENT.md`; parse back with `load_agent_spec`; assert all required and optional fields match
    - **Validates: Requirements 1.1, 1.2, 2.1, 2.5, 2.8**

  - [ ]* 2.3 Write property test for invalid AGENT.md raises AgentSpecError (Property 2)
    - **Property 2: Invalid AGENT.md always raises AgentSpecError**
    - Generate `AGENT.md` content with each required field missing or set to an invalid value; assert `AgentSpecError` is raised with the field name and file path in the message
    - **Validates: Requirements 1.10, 9.8**

  - [x] 2.4 Implement `list_agent_ids(pipeline_type)` with duplicate-order detection
    - Scan `agents/prompts/` for all `AGENT.md` files matching the given `pipeline_type`
    - Sort by `order` ascending; raise `AgentSpecError` if any two agents share the same `order` within the pipeline
    - Return empty list for unknown pipeline types
    - _Requirements: 1.11, 2.2, 2.7_

  - [ ]* 2.5 Write property test for duplicate order raises AgentSpecError (Property 3)
    - **Property 3: Duplicate order within pipeline raises AgentSpecError**
    - Generate sets of agents for a pipeline where two share the same `order`; assert `AgentSpecError` is raised identifying both conflicting agent IDs and the shared `order` value
    - **Validates: Requirements 1.11**

  - [ ]* 2.6 Write property test for list_agent_ids strictly ascending order (Property 4)
    - **Property 4: list_agent_ids always returns strictly ascending order**
    - For each pipeline type, call `list_agent_ids`, resolve each ID to its `AgentSpec.order`, assert the sequence is strictly ascending with no duplicates
    - **Validates: Requirements 2.2, 5.6, 9.3**

  - [ ]* 2.7 Write unit tests for loader edge cases
    - `load_agent_spec` with non-existent agent ID → `FileNotFoundError` with path in message
    - `load_agent_spec` with unreadable file → `PermissionError` with path in message
    - `load_agent_spec` called twice for same ID → second call returns cached instance (mock file I/O)
    - `list_agent_ids` with unknown pipeline type → returns `[]`
    - _Requirements: 2.3, 2.4, 2.6, 2.7_

- [x] 3. Checkpoint — Ensure loader tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement `agents/factory.py`
  - [x] 4.1 Implement `_compose_system_prompt(spec, ctx)` with guardrail injection, skill injection, hook injection, and prompt body concatenation
    - Read each `agents/guardrails/{name}.md` file; prepend `## Guardrail: {name}\n\n`; log warning and use empty string if file missing
    - Append skill content blocks from `ctx.attached_skills` (read `"content"` key)
    - Append hook guideline blocks from `ctx.attached_hooks` (read `"content"` key)
    - Append `spec.prompt_body`; join all blocks with `\n\n`
    - _Requirements: 3.2, 3.3, 3.5, 4.3_

  - [ ]* 4.2 Write property test for system prompt composition order (Property 6)
    - **Property 6: System prompt composition preserves order**
    - Generate agents with random combinations of guardrails, skills, hooks, and body; assert the composed prompt contains guardrail blocks before skill blocks, skill blocks before hook blocks, and hook blocks before `prompt_body`; assert each guardrail block is preceded by `## Guardrail: {name}` heading
    - **Validates: Requirements 3.2, 3.5, 4.3**

  - [ ]* 4.3 Write property test for guardrail content verbatim in system prompt (Property 7)
    - **Property 7: Guardrail content appears verbatim in system prompt**
    - For each agent that declares guardrails, assert the full text content of each referenced `agents/guardrails/{name}.md` file appears verbatim (without modification) in the composed `system_prompt`
    - **Validates: Requirements 3.2, 9.4**

  - [x] 4.4 Implement `_build_tools(spec, ctx)` with tool set resolution
    - Map `"workspace"` → `write_file`, `read_file`, `list_workspace_files`
    - Map `"prototype"` → `read_template_seed`, `read_layout_reference`, `read_checklist`, `todo_write`, `emit_artifact`
    - Support union of both sets when both are declared
    - Raise `ValueError` for any unrecognized tool name, including agent ID in message
    - _Requirements: 1.3, 1.4, 1.5, 4.4, 4.5, 4.6, 4.7, 4.11_

  - [x] 4.5 Implement `create_agent(agent_id, ctx)` public entry point
    - Call `load_agent_spec(agent_id)`, compose system prompt, build tools, instantiate and return `DeepAgent`
    - Propagate `FileNotFoundError` and `AgentSpecError` from loader without swallowing
    - _Requirements: 4.1, 4.2, 4.9, 4.10_

  - [ ]* 4.6 Write unit tests for factory edge cases
    - `create_agent` with `tools: []` → `DeepAgent` has empty tools list
    - `create_agent` with `tools: ["workspace"]` → workspace tools only
    - `create_agent` with `tools: ["prototype"]` → prototype tools only
    - `create_agent` with `tools: ["workspace", "prototype"]` → union of both sets
    - `create_agent` with unknown tool name → `ValueError` with tool name and agent ID
    - `create_agent` with unknown agent ID → `FileNotFoundError` propagated
    - Missing guardrail file → warning logged, agent still runs with empty guardrail block
    - _Requirements: 4.4, 4.5, 4.6, 4.7, 4.9, 4.10, 4.11, 3.3_

- [x] 5. Checkpoint — Ensure factory tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement slim `agents/registry.py`
  - [x] 6.1 Write slim `agents/registry.py` with pipeline-to-ID maps and `get_pipeline_agents()`
    - Define `SUPPORTED_PIPELINE_TYPES`, `PIPELINE_AGENTS`, `PIPELINE_CONTEXT_MAPS`, `REVISION_BASE_MAP`
    - Implement `get_pipeline_agents(pipeline_type)` calling `list_agent_ids` and `load_agent_spec`, sorted by `AgentSpec.order`
    - Return empty list for unsupported pipeline types; propagate `FileNotFoundError` and `AgentSpecError`
    - Remove all `AgentDefinition` instances, prompt strings, and `DEEP_AGENT_CONFIG` dicts
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [ ]* 6.2 Write unit tests for slim registry
    - `get_pipeline_agents` with unsupported pipeline type → returns `[]`
    - `get_pipeline_agents` propagates `FileNotFoundError` from loader
    - `get_pipeline_agents` propagates `AgentSpecError` from loader
    - Registry contains no `AgentDefinition` instances or prompt strings (static analysis assertion)
    - _Requirements: 5.5, 5.7, 5.8_

- [x] 7. Create nine guardrail files in `agents/guardrails/`
  - [x] 7.1 Create `agents/guardrails/agile.md`, `typescript.md`, `react.md`, `accessibility.md`, `html-prototype.md`
    - Each file: plain markdown prose and lists only; fewer than 60 lines; no fenced code blocks; no YAML frontmatter
    - Extract content from existing agent prompts where applicable
    - _Requirements: 3.1, 3.4_

  - [x] 7.2 Create `agents/guardrails/openapi.md`, `java-spring.md`, `mulesoft.md`, `dotnet.md`
    - Each file: plain markdown prose and lists only; fewer than 60 lines; no fenced code blocks; no YAML frontmatter
    - Extract content from existing agent prompts where applicable
    - _Requirements: 3.1, 3.4_

  - [ ]* 7.3 Write property test for guardrail file structural constraints (Property 8)
    - **Property 8: All guardrail files satisfy structural constraints**
    - For all nine guardrail files, assert line count < 60, no fenced code blocks (no ` ``` ` delimiters), and no YAML frontmatter (no leading `---` block)
    - **Validates: Requirements 3.4**

- [x] 8. Migrate Batch 1 — `user_stories` pipeline (6 agents from `registry.py`)
  - [x] 8.1 Create `AGENT.md` files for all 6 `user_stories` agents: `domain-analyst`, `epic-architect`, `story-estimator`, `nfr-specialist`, `backlog-reviewer`, `backlog-compiler`
    - Extract prompt body verbatim from `registry.py` `USER_STORY_AGENTS` list
    - Set YAML frontmatter: `id`, `name`, `role`, `pipeline_type: user_stories`, `order`, `max_tokens`, `icon`, `estimated_duration`
    - Set `tools: []`, `guardrails: [agile]` for all; set `context_from` per agent routing
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [ ]* 8.2 Write diff test for `user_stories` batch prompt equivalence
    - For each of the 6 migrated agents, assert the `AGENT.md` prompt body is semantically equivalent to the original Python string literal (no instruction sentences, role descriptions, output format rules, or constraint clauses dropped or altered)
    - _Requirements: 7.5_

- [x] 9. Migrate Batch 2 — `ppt` + `ppt_revision` pipelines (from `registry.py` and `ppt_pipeline.py`)
  - [x] 9.1 Create `AGENT.md` files for `ppt` agents: `ppt-content-strategist`, `ppt-slide-architect`, `ppt-code-generator`, `ppt-assembler`
    - Extract prompt body from `CONTENT_STRATEGIST_PROMPT`, `SLIDE_ARCHITECT_PROMPT`, `PPTXGENJS_CODE_GENERATOR_PROMPT`, `PRESENTATION_ASSEMBLER_PROMPT` in `ppt_pipeline.py`
    - Set `pipeline_type: ppt`, correct `order`, `max_tokens`, `skills` → `context_from` mapping
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [x] 9.2 Create `AGENT.md` files for `ppt_revision` agents: `ppt-revision-agent`, `ppt-revision-assembler`
    - Extract prompt body from `PPT_REVISION_AGENT_PROMPT` and reuse `PRESENTATION_ASSEMBLER_PROMPT`
    - Set `pipeline_type: ppt_revision`, correct `order`, `max_tokens`, `context_from`
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [ ]* 9.3 Write diff tests for `ppt` and `ppt_revision` batch prompt equivalence
    - _Requirements: 7.5_

- [x] 10. Migrate Batch 3 — `prototype` + `prototype_revision` pipelines (from `registry.py`)
  - [x] 10.1 Create `AGENT.md` files for `prototype` agents: `requirements-analyst`, `html-prototype-builder`, and any polisher/finalizer agents
    - Extract prompt bodies from `PROTOTYPE_AGENTS` list in `registry.py`
    - Set `pipeline_type: prototype`, `tools: ["prototype"]` for tool-using agents, `guardrails: [html-prototype]`
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [x] 10.2 Create `AGENT.md` for `prototype-revision-agent`
    - Extract prompt body from `PROTOTYPE_REVISION_AGENT` in `registry.py`
    - Set `pipeline_type: prototype_revision`, `order: 1`, `max_tokens: 32000`
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [ ]* 10.3 Write diff tests for `prototype` and `prototype_revision` batch prompt equivalence
    - _Requirements: 7.5_

- [x] 11. Migrate Batch 4 — `app_builder` + `app_builder_revision` pipelines (from `registry.py` and `app_builder_sdlc.py`)
  - [x] 11.1 Create `AGENT.md` files for all 15 `app_builder` agents (e.g., `material-analyzer`, `app-user-stories`, `app-system-design`, `app-security-architecture`, `app-ux-design`, `app-api-design`, `app-database-design`, `app-code-generator`, `app-feature-implementation`, `app-infra-generator`, `app-code-compliance`, `app-test-implementation`, `app-test-compliance`, `app-devops`, `app-sdlc-governance`)
    - Extract prompt bodies from `app_builder_sdlc.py` constants and `registry.py` `APP_BUILDER_AGENTS` list
    - Set `pipeline_type: app_builder`, correct `order`, `max_tokens`, `tools` (workspace for code-generating agents)
    - Encode `APP_BUILDER_CONTEXT_MAP` routing into each agent's `context_from` field
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [x] 11.2 Create `AGENT.md` for `app-builder-revision-agent`
    - Extract prompt body from `APP_BUILDER_REVISION_AGENT` in `registry.py`
    - Set `pipeline_type: app_builder_revision`, `order: 1`, `max_tokens: 32000`
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [ ]* 11.3 Write diff tests for `app_builder` and `app_builder_revision` batch prompt equivalence
    - _Requirements: 7.5_

- [x] 12. Migrate Batches 5 & 6 — `mulesoft_to_springboot` and `dotnet_to_azure` pipelines (from `migration_pipelines.py`)
  - [x] 12.1 Create `AGENT.md` files for all `mulesoft_to_springboot` agents
    - Extract prompt bodies from `migration_pipelines.py` constants (e.g., `SDLC_SECURITY_ARCHITECTURE_PROMPT`, `SDLC_CODE_COMPLIANCE_PROMPT`, `SDLC_TEST_COMPLIANCE_PROMPT`, `SDLC_GOVERNANCE_PROMPT`, `MIGRATION_TEST_IMPLEMENTATION_PROMPT`)
    - Set `pipeline_type: mulesoft_to_springboot`, `guardrails: [mulesoft, java-spring]` where applicable
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [x] 12.2 Create `AGENT.md` files for all `dotnet_to_azure` agents
    - Extract prompt bodies from `migration_pipelines.py`
    - Set `pipeline_type: dotnet_to_azure`, `guardrails: [dotnet]` where applicable
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [ ]* 12.3 Write diff tests for `mulesoft_to_springboot` and `dotnet_to_azure` batch prompt equivalence
    - _Requirements: 7.5_

- [x] 13. Migrate Batch 7 — `custom` pipeline (from `custom_agents.py`)
  - [x] 13.1 Create `AGENT.md` files for all `custom` pipeline agents
    - Extract prompt bodies from `custom_agents.py`
    - Set `pipeline_type: custom`, correct `order`, `max_tokens`, `tools`, `guardrails`
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [ ]* 13.2 Write diff tests for `custom` batch prompt equivalence
    - _Requirements: 7.5_

- [x] 14. Migrate Batch 8 — remaining revision agents (from `registry.py`)
  - [x] 14.1 Create `AGENT.md` for `user-story-revision-agent`
    - Extract prompt body from `USER_STORY_REVISION_AGENT` in `registry.py`
    - Set `pipeline_type: user_stories_revision`, `order: 1`, `max_tokens: 32000`
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [ ]* 14.2 Write diff test for remaining revision agents prompt equivalence
    - _Requirements: 7.5_

- [x] 15. Migrate Batch 9 — shared SDLC agents (from `od_runner.py`)
  - [x] 15.1 Create `AGENT.md` files for any agents whose prompts are defined in `od_runner.py`
    - Extract only prompt string literals; retain all non-prompt logic in `od_runner.py`
    - Set correct `pipeline_type`, `order`, `max_tokens`, `tools`, `guardrails`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 15.2 Write diff tests for `od_runner.py` batch prompt equivalence
    - _Requirements: 7.5_

- [x] 16. Checkpoint — Ensure all 85 AGENT.md files are present and valid
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Update `orchestrator_v2.py` to use factory
  - [x] 17.1 Replace `AgentDefinition`-based agent construction with `create_agent()` from `agents/factory.py`
    - Import `create_agent` and `AgentContext` from `agents/factory.py`; remove import of `AgentDefinition` from `registry.py`
    - Replace `_build_agent_context()` and `_build_tools_for_agent()` with `AgentContext` construction driven by `spec.context_from`
    - Implement context routing: `[]` → empty dict; `["$previous"]` → single prior agent; explicit IDs → filtered dict
    - Move skill injection, hook injection, and guardrail injection out of `execute()` loop (now handled by `factory._compose_system_prompt`)
    - Preserve all existing WebSocket event types with required fields unchanged
    - Preserve retry logic for transient Bedrock errors unchanged
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [ ]* 17.2 Write property test for context_from routing produces correct agent_outputs keys (Property 5)
    - **Property 5: context_from routing produces exactly the right agent_outputs keys**
    - Generate pipeline states with varying `context_from` configurations; assert `AgentContext.agent_outputs` contains exactly the keys specified by `spec.context_from` in each case
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 9.5**

  - [ ]* 17.3 Write property test for WebSocket events completeness (Property 10)
    - **Property 10: WebSocket events are complete and well-formed for any pipeline run**
    - Run each pipeline type with a mocked LLM returning a non-empty string; assert the event sequence includes at least one `pipeline_start` (with `data.pipeline_type`), one `agent_start` per agent (with `data.agent_id` and `data.agent_name`), one `agent_complete` per agent (with `data.agent_id` and `data.output`), and one `pipeline_complete` (with `data.final_output`)
    - **Validates: Requirements 6.7, 9.6**

  - [ ]* 17.4 Write unit tests for orchestrator context routing
    - `context_from: []` → `agent_outputs == {}`
    - `context_from: ["$previous"]` on first agent → `agent_outputs == {}`
    - `context_from: ["$previous"]` on non-first agent → `agent_outputs` has exactly one key
    - Orchestrator retry on `ThrottlingException` → retries up to 2 times
    - _Requirements: 6.3, 6.4, 6.5, 6.8_

- [x] 18. Checkpoint — Ensure orchestrator tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 19. Schema validation and smoke tests
  - [x] 19.1 Write schema validation test in `tests/agents/test_loader.py`
    - Call `load_agent_spec` for all agent IDs discoverable in `agents/prompts/`; assert each returns a valid `AgentSpec` with no missing required fields and `spec.id == directory_name`
    - _Requirements: 9.1, 9.8_

  - [ ]* 19.2 Write property test for all AGENT.md files produce valid AgentSpec (Property 9)
    - **Property 9: All AGENT.md files produce valid AgentSpec with matching id**
    - Scan `agents/prompts/`, call `load_agent_spec` for each, assert no missing required fields and `AgentSpec.id == directory_name`
    - **Validates: Requirements 2.8, 9.1**

  - [x] 19.3 Write factory smoke test in `tests/agents/test_factory.py`
    - For the first agent (by `order`) of each pipeline type, call `create_agent` and assert the returned `DeepAgent` has a non-empty `system_prompt`
    - _Requirements: 9.2_

  - [x] 19.4 Write pipeline ordering test in `tests/agents/test_registry.py`
    - Call `list_agent_ids(pipeline_type)` for every pipeline type; assert returned IDs are in strictly ascending `order` sequence with no duplicates
    - _Requirements: 9.3_

  - [x] 19.5 Write guardrail injection test in `tests/agents/test_guardrails.py`
    - Call `create_agent` for an agent that declares at least one guardrail; assert the guardrail file's full content appears verbatim in the `DeepAgent`'s `system_prompt`
    - _Requirements: 9.4_

  - [x] 19.6 Write end-to-end `user_stories` pipeline integration test in `tests/agents/test_orchestrator.py`
    - Execute `user_stories` pipeline with mocked LLM (returns non-empty string for every invocation); assert all 6 agents fire in correct order and `len(WorkflowState.agent_outputs) == 6` after completion
    - Assert that if `create_agent` raises for one agent, an `agent_error` event is emitted and the pipeline halts
    - _Requirements: 9.6, 9.7_

- [x] 20. Delete migrated Python source files
  - [x] 20.1 Delete `app/agents/app_builder_sdlc.py`, `app/agents/ppt_pipeline.py`, `app/agents/custom_agents.py`, `app/agents/migration_pipelines.py`
    - Remove all import statements referencing these files from `registry.py` and any other modules
    - Verify no remaining references to deleted modules exist in the codebase
    - _Requirements: 7.4_

- [x] 21. Create `backend/CLAUDE.md` architecture guide
  - [x] 21.1 Write `backend/CLAUDE.md` with all eight required sections
    - (a) Architecture Overview — directory layout and module responsibilities
    - (b) Adding an Agent — steps to create `AGENT.md` and add ID to `PIPELINE_AGENTS`
    - (c) Adding a Pipeline — steps to add `PIPELINE_AGENTS` entry and optional `PIPELINE_CONTEXT_MAPS` entry
    - (d) Adding a Guardrail — steps to create a guardrail file and reference it in `AGENT.md`
    - (e) Adding a Tool Set — steps to implement a tool factory in `tools/` and register it in `factory.py`
    - (f) Skills vs Guardrails vs Hooks — definitions and when to use each
    - (g) Testing — how to run the test suite and what each test category covers
    - (h) Commit Conventions — required prefix format (`feat(agents):`, `fix(orchestrator):`, `chore(prompts):`)
    - Include `AGENT.md` schema table (field name, type, default, purpose) and a complete example `AGENT.md`
    - Document `context_from` with three annotated examples
    - Document guardrail injection mechanism and all nine available guardrail names
    - Document both tool sets with exact tool names
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 22. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at each major phase boundary
- Property tests (Properties 1–10) use Hypothesis with `@settings(max_examples=100)` and the tag format `# Feature: folder-per-agent-architecture, Property N: {property_text}`
- Unit tests and property tests are complementary — both are required for full coverage
- Migration batches (Tasks 8–15) must be completed before the orchestrator update (Task 17) to ensure all `AGENT.md` files exist when `create_agent()` is called
- `od_runner.py` is retained with its non-prompt logic intact; only prompt string literals are extracted
- The `AgentDefinition` dataclass in `registry.py` is deleted as part of Task 6.1; all call sites in `orchestrator_v2.py` are updated in Task 17.1

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "7.1", "7.2"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "4.1"] },
    { "id": 3, "tasks": ["2.5", "2.6", "2.7", "4.2", "4.3", "4.4", "7.3"] },
    { "id": 4, "tasks": ["4.5", "4.6", "6.1"] },
    { "id": 5, "tasks": ["6.2", "8.1", "9.1", "9.2", "10.1", "10.2", "11.1", "11.2", "12.1", "12.2", "13.1", "14.1", "15.1"] },
    { "id": 6, "tasks": ["8.2", "9.3", "10.3", "11.3", "12.3", "13.2", "14.2", "15.2", "17.1"] },
    { "id": 7, "tasks": ["17.2", "17.3", "17.4", "19.1", "19.2", "19.3", "19.4", "19.5"] },
    { "id": 8, "tasks": ["19.6", "20.1"] },
    { "id": 9, "tasks": ["21.1"] }
  ]
}
```
