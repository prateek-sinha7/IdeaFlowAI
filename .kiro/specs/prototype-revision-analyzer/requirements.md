# Requirements Document

## Introduction

This feature introduces a **Prototype Revision Analyzer** — a new agent capability that executes before the classify-revision-tier step in the prototype revision workflow. The Analyzer reads the user's revision instruction and the previously generated HTML prototype, then produces two outputs: a **detailed solution plan** describing exactly how the revision should be implemented, and a **tier rating** (small fix / large fix / feature revision). The rating replaces the existing single-call `_classify_revision_tier` LLM heuristic with a richer, reasoned determination. The detailed solution is forwarded to every downstream revision agent type — `prototype-revision-agent` (small), `prototype-revision-planner` (large), and `prototype-revision-feature-specify` (feature) — so each agent begins with a precise, pre-analyzed implementation blueprint rather than only the raw user instruction.

All existing subsystems — revision versions, HTML previews, step tracking, file artifacts, Concierge run chat, audit log, and agent progress events — must continue to function without change.

---

## Glossary

- **Revision_Analyzer**: The new agent (`prototype-revision-analyzer`) that runs before tier classification on every prototype revision request.
- **Analyzer_Output**: The structured result produced by the Revision_Analyzer, containing a `tier` field and a `solution` field.
- **Tier**: One of three revision complexity levels — `small`, `large`, or `feature` — that determines which downstream workflow is dispatched.
- **Solution_Plan**: The detailed, structured analysis produced by the Revision_Analyzer describing what changes are needed and how to implement them.
- **Classify_Tier_Step**: The existing app-layer logic (`_classify_revision_tier` in `run_commands.py`) that selects the revision pipeline manifest based on tier.
- **Small_Revision**: The `prototype_revision` pipeline, dispatched for targeted 1–3 element changes handled by `prototype-revision-agent`.
- **Large_Revision**: The `prototype_large_revision` pipeline, dispatched for multi-component structural changes handled by `prototype-revision-planner` + `prototype-large-builder`.
- **Feature_Revision**: The `prototype_feature_revision` pipeline, dispatched for new pages/routes/capabilities handled by `prototype-revision-feature-specify` + `prototype-revision-feature-plan` + `prototype-feature-builder`.
- **Revision_Instruction**: The plain-text change request provided by the user.
- **Previous_HTML**: The full HTML content of the most recently generated prototype artifact, sourced from the parent run's output.
- **AGENT.md**: The declarative agent definition file in `backend/agents/prompts/{agent_id}/AGENT.md` that sets frontmatter (id, pipeline_type, order, tools) and the agent's system prompt.
- **Capability_Registry**: The `backend/agents/capabilities/registry.py` module that maintains the `_KNOWN` set and `discover()` import list; every new capability kind must be registered in both.
- **Execution_Engine**: The workflow-agnostic runtime kernel (`backend/agents/execution_engine/engine.py`) — must not be edited for this feature (SC-001 invariant).
- **SSE**: Server-Sent Events, the down-channel transport for streaming agent progress events to the frontend.
- **ArtifactGraph**: The graph-keyed artifact store that replaced `accumulated_outputs`; all artifact passing must go through it, never through a dict.

---

## Requirements

### Requirement 1: Revision Analyzer Agent Definition

**User Story:** As a product engineer, I want a new `prototype-revision-analyzer` agent registered in the system, so that it can be referenced in workflow manifests and discovered by the capability registry without any changes to the Execution_Engine kernel.

#### Acceptance Criteria

1. THE Revision_Analyzer SHALL have an AGENT.md file at `backend/agents/prompts/prototype-revision-analyzer/AGENT.md` with frontmatter fields: `id: prototype-revision-analyzer`, `name: Prototype Revision Analyzer`, `role: analyzer`, `pipeline_type: prototype_revision`, `order: 1` (so it precedes `prototype-revision-agent` whose order must be shifted to 2), `max_tokens: 4096`, `tools: []`, and a system prompt body.
2. THE Revision_Analyzer's AGENT.md system prompt SHALL instruct the agent to read the Revision_Instruction and Previous_HTML, reason about the nature of the change, and output a structured Markdown block containing exactly: a `## Tier` section with one value (`small`, `large`, or `feature`) and a `## Solution Plan` section with a detailed implementation description containing at least one sentence per component identified as requiring change.
3. WHEN the Capability_Registry `discover()` function is invoked, THE Revision_Analyzer SHALL be discoverable via the existing agent loader's AGENT.md scan mechanism (no new registry entry is required for the agent itself — it is a pipeline agent, not a capability kind).
4. THE Revision_Analyzer's AGENT.md SHALL declare `produces: [prototype-revision-analyzer]` so the WorkflowResolver can track its artifact contract.
5. IF the Revision_Analyzer AGENT.md file is absent, OR IF the loader raises `AgentSpecError` due to a YAML parse failure or a missing or invalid required field (id, name, role, pipeline_type, order), THEN THE System SHALL log a warning with the specific failure reason and fall back to the existing `_classify_revision_tier` heuristic, so the revision workflow degrades gracefully rather than failing. Runtime exceptions during agent execution are also a named fallback cause.

---

### Requirement 2: Analyzer Output Schema and Parsing

**User Story:** As a developer integrating the Analyzer into the revision pipeline, I want a well-defined, parseable output schema from the Revision_Analyzer, so that the Classify_Tier_Step and downstream agents can reliably consume the tier rating and the Solution_Plan.

#### Acceptance Criteria

1. THE Revision_Analyzer SHALL emit its output as a single Markdown document with two required H2 sections: `## Tier` (one line, value = `small`, `large`, or `feature`) and `## Solution Plan` (freeform Markdown, minimum 50 characters of non-whitespace content).
2. WHEN the Revision_Analyzer output is parsed, THE System SHALL extract the `tier` value by reading the first non-blank line under the `## Tier` heading, normalising it to lowercase, and then validating the normalised value — so `SMALL` becomes `small` and passes validation while a genuinely unrecognised string triggers the default.
3. IF the parsed tier value is not one of `small`, `large`, or `feature` after normalisation to lowercase, OR IF the `## Tier` section is entirely absent from the Analyzer output, THEN THE System SHALL default to `large` and log a warning including the first 500 characters of the raw output, so an unexpected LLM response never silently routes to the wrong pipeline.
4. WHEN the Revision_Analyzer output is parsed, THE System SHALL extract the `## Solution Plan` section as a string and store it as the `analyzer_solution` field in the run's execution context.
5. THE Analyzer output parser SHALL be a pure function (no I/O, no model calls) that accepts a raw string and returns `(tier: str, solution: str)`, so it can be unit-tested independently of any LLM.
6. IF the `## Solution Plan` section is absent from the Analyzer output, THEN THE System SHALL store an empty string as `analyzer_solution` and emit a warning-level log entry, so the absence of a solution plan is observable and downstream agents receive a defined (empty) value rather than encountering an undefined field.

---

### Requirement 3: Pre-Classification Execution in the Revision Flow

**User Story:** As a user submitting a revision request, I want the Revision_Analyzer to run automatically before the tier is classified, so that the tier decision is based on deep analysis of both my instruction and the current prototype rather than a simple one-shot LLM guess.

#### Acceptance Criteria

1. WHEN a prototype revision is dispatched via `POST /api/runs/{id}/revisions` with `target_artifact_type = "prototype_output"`, THE System SHALL invoke the Revision_Analyzer before calling `_classify_revision_tier`, passing both the Revision_Instruction and the Previous_HTML as inputs.
2. IF the Revision_Analyzer produces an Analyzer_Output where the `tier` field is present and its value after lowercase normalisation is one of `small`, `large`, or `feature`, THEN THE Classify_Tier_Step SHALL use that `tier` value to select the revision pipeline, replacing the existing single-call LLM heuristic.
3. IF the Revision_Analyzer produces an output but the `tier` field is absent or its normalised value is not one of the three recognised values, THEN THE System SHALL fall back to the existing `_classify_revision_tier` heuristic, so an invalid-but-non-exception analyzer response is handled identically to no response.
4. WHEN the Revision_Analyzer begins execution, THE System SHALL emit an `agent_start` SSE event for `prototype-revision-analyzer` so the frontend agent-progress UI shows the analyzer step as a running agent.
5. WHEN the Revision_Analyzer finishes, THE System SHALL emit an `agent_complete` SSE event for `prototype-revision-analyzer` before the child revision run is minted, so the agent progress sequence is accurate.
6. IF the Revision_Analyzer call raises any exception, THEN THE System SHALL log the error and fall back to the `_classify_revision_tier` heuristic.
7. IF the `_classify_revision_tier` fallback itself raises an exception, THEN THE System SHALL catch that exception, default the tier to `"small"`, and proceed with revision dispatch — so a Revision_Analyzer failure and a concurrent fallback failure never together block a revision from completing.
8. THE Revision_Analyzer invocation SHALL respect the SC-001 invariant — no workflow name, pipeline_type string, or spec id literal SHALL be added to `backend/agents/execution_engine/engine.py`.

---

### Requirement 4: Solution Plan Injection into Small Revision Agent

**User Story:** As a user requesting a small fix, I want the `prototype-revision-agent` to receive the Revision_Analyzer's detailed Solution_Plan, so that it performs the exact, well-reasoned change rather than re-interpreting my brief instruction from scratch.

#### Acceptance Criteria

1. WHEN the `prototype_revision` pipeline is dispatched and an `analyzer_solution` is available in the run context, THE System SHALL insert the Solution_Plan into the context block injected into `prototype-revision-agent`'s prompt at position 5 (after `=== USER GUIDANCE ===`), using the section header `=== REVISION ANALYSIS ===`.
2. THE `prototype-revision-agent` AGENT.md system prompt SHALL include an explicit instruction stating: "When an `=== REVISION ANALYSIS ===` block is present in your context, follow its guidance precisely; it takes precedence over your own interpretation of the raw user instruction."
3. IF no `analyzer_solution` is available (e.g., the analyzer was skipped due to an error), THEN THE System SHALL omit the `=== REVISION ANALYSIS ===` block entirely from `prototype-revision-agent`'s context input, so the agent operates without a revision analysis block rather than receiving an empty placeholder.
4. THE Solution_Plan injection SHALL use the `ExecutionContext`'s existing `_compose_context_message` extension point — a new `ectx.analyzer_solution` field appended at position 5 — so no new context-composition path is introduced outside the kernel.
5. IF the injection mechanism raises an exception, THEN THE System SHALL proceed with `prototype-revision-agent` execution without the `=== REVISION ANALYSIS ===` block, so a context-composition failure does not abort the pipeline.

---

### Requirement 5: Solution Plan Injection into Large Revision Planner

**User Story:** As a user requesting a large structural revision, I want the `prototype-revision-planner` to receive the Revision_Analyzer's detailed Solution_Plan, so that it produces a better-decomposed task list that targets the exact components identified by the analyzer.

#### Acceptance Criteria

1. WHEN the `prototype_large_revision` pipeline is dispatched AND an `analyzer_solution` is available in the run context, THE System SHALL inject the Solution_Plan into `prototype-revision-planner`'s context input by prepending a `=== REVISION ANALYSIS ===` delimited block before the agent's primary input.
2. IF an `analyzer_solution` was successfully injected into `prototype-revision-planner`'s context, THEN the planner's output task list SHALL reference at least one component identifier named in the Solution_Plan, making the influence of the analysis observable.
3. IF no `analyzer_solution` is available, THEN THE `prototype-revision-planner` SHALL receive its context input without a `=== REVISION ANALYSIS ===` block and proceed as if the block was never present.
4. WHEN `prototype-revision-planner` produces its task list, THE System SHALL make that task list available to `prototype-large-builder` before invoking `prototype-large-builder`, so the builder executes tasks shaped by the analysis.
5. IF the Solution_Plan injection fails after tasks have already been generated by `prototype-revision-planner`, THEN THE System SHALL allow the task_loop builder to proceed with the already-generated tasks rather than failing the pipeline.

---

### Requirement 6: Solution Plan Injection into Feature Revision Specify Agent

**User Story:** As a user requesting a feature addition, I want the `prototype-revision-feature-specify` agent to receive the Revision_Analyzer's detailed Solution_Plan, so that the feature specification it writes is grounded in the analyzer's understanding of the existing prototype and the intended new capability.

#### Acceptance Criteria

1. WHEN the `prototype_feature_revision` pipeline is dispatched AND an `analyzer_solution` is available in the run context, THE System SHALL inject the Solution_Plan into `prototype-revision-feature-specify`'s context input by prepending a `=== REVISION ANALYSIS ===` delimited block before the agent's primary input.
2. IF an `analyzer_solution` was successfully injected into `prototype-revision-feature-specify`'s context, THEN the agent's output specification SHALL reference the Solution_Plan's analysis (e.g., include component names, page names, or capability descriptions from the plan) so the influence of the analysis is observable.
3. IF no `analyzer_solution` is available, THEN THE `prototype-revision-feature-specify` agent SHALL receive its context input without a `=== REVISION ANALYSIS ===` block and proceed as if the block was never present.
4. THE `analyzer_solution` field SHALL be stored on the `ExecutionContext` from the moment the child revision run is minted until the pipeline completes or is terminated, so it is available to all agents in the feature revision pipeline — specify, plan, and builder.
5. IF the Solution_Plan injection into `prototype-revision-feature-specify` raises an exception, THEN THE System SHALL produce a log entry including the failure reason and allow the agent to proceed without the `=== REVISION ANALYSIS ===` block, so the feature revision pipeline is not blocked by an injection failure.

---

### Requirement 7: Analyzer Output Persisted in Run Context

**User Story:** As a developer debugging a revision, I want the Analyzer_Output to be durably accessible on the child run's execution context and in the event stream, so that I can trace what tier was selected and what solution plan was produced.

#### Acceptance Criteria

1. WHEN the Revision_Analyzer produces an Analyzer_Output, THE System SHALL store the `analyzer_solution` string on the child run's `ExecutionContext` before the first agent step executes.
2. WHEN the Revision_Analyzer produces an Analyzer_Output, THE System SHALL emit a `revision_analyzer_complete` SSE event within 2 seconds of the Analyzer completing — even if no SSE client is connected — with payload `{"tier": "<tier>", "solution_preview": "<first 200 chars of solution>"}` so the event is durably persisted to the run_events tail for later replay by the frontend and audit log.
3. THE `revision_analyzer_complete` event type SHALL be added to `_DOCUMENTED_EVENT_TYPES` in the characterization test normalizer, so the INV-3 golden suite remains byte-identical for existing runs that do not exercise the new code path.
4. WHEN a revision run is replayed from its durable event tail (SSE replay), THE `revision_analyzer_complete` event SHALL appear in the replayed sequence before any `agent_start` events for the revision pipeline's first agent step, so audit and step history are complete and ordered.
5. THE `analyzer_solution` field SHALL NOT be added to `_VOLATILE_STRIP_KEYS` — it is stable, run-specific content that should be preserved in characterization snapshots.
6. WHEN the Revision_Analyzer produces an Analyzer_Output, THE System SHALL attempt to both store `analyzer_solution` on `ExecutionContext` (AC1) and emit `revision_analyzer_complete` (AC2) as a best-effort atomic pair; IF either operation fails, THE System SHALL log the failure reason and abort the revision run with an error status — it SHALL NOT proceed with one operation completed and the other missing, so the context and event stream remain consistent.

---

### Requirement 8: Tier Rating Quality and Accuracy

**User Story:** As a user submitting revision requests, I want the Revision_Analyzer's tier rating to be accurate and consistent, so that my revisions are routed to the correct pipeline and I am not subjected to unnecessarily heavy multi-step workflows for simple fixes.

#### Acceptance Criteria

1. WHEN the Revision_Analyzer evaluates a Revision_Instruction that targets exactly one discrete UI element or content token and the change is scoped to a single file or component, THE Revision_Analyzer SHALL rate the request as `small`.
2. WHEN the Revision_Analyzer evaluates a Revision_Instruction requesting changes across multiple pages, layout reworks, or fixes that require coordinated HTML/CSS/JavaScript changes that are not uniform across pages, THE Revision_Analyzer SHALL rate the request as `large`.
3. IF the Revision_Analyzer evaluates a Revision_Instruction that is multi-page but where the change is simple and uniform across pages (e.g., the same typo fixed identically on several pages), THEN THE Revision_Analyzer MAY rate the request as `small` instead of `large`.
4. WHEN the Revision_Analyzer evaluates a Revision_Instruction requesting a new page, new route, or new capability absent from the current prototype, THE Revision_Analyzer SHALL rate the request as `feature`.
5. THE Revision_Analyzer system prompt SHALL explicitly define the three tier boundaries with at least one concrete positive example and one concrete negative example per tier, so the LLM has deterministic decision criteria.
6. IF the Revision_Analyzer evaluates a Revision_Instruction that spans multiple tiers (e.g., fix a button label AND add a new page), THEN THE Revision_Analyzer SHALL rate the request using the highest applicable tier (in order: `feature` > `large` > `small`), so a mixed-scope instruction is never under-routed.
7. WHEN the Previous_HTML is longer than 8000 characters, THE Revision_Analyzer SHALL receive the full prototype content without truncation, so the Solution_Plan quality depends on understanding the complete prototype structure.

---

### Requirement 9: Preservation of Existing Revision Subsystems

**User Story:** As a user of the prototype workflow, I want all existing features — revision versions, HTML previews, step tracking, files, Concierge chat, audit log, and agent progress — to continue working exactly as before, so that the Analyzer insertion does not introduce regressions.

#### Acceptance Criteria

1. THE System SHALL preserve the `revision_versions` list returned by `GET /api/runs/{id}/family` unchanged — a revision run with an Analyzer step SHALL still appear as a single revision entry with the same `revision_index` and `parent_run_id` as it would without the Analyzer.
2. THE System SHALL preserve the HTML preview behavior — `GET /api/runs/{id}/artifacts` SHALL return HTTP 200 with an artifact entry for `prototype.html` for any revision run regardless of whether the Analyzer ran.
3. WHEN a revision run that used the Analyzer is replayed on the SSE stream, THE `stream_attached` event SHALL appear first in the replayed sequence, followed by all step events in monotonically ascending `seq` order with no seq gaps relative to an Analyzer-free replay of the same pipeline steps.
4. WHEN a revision is dispatched via `CHANNEL_REVISION` from the Concierge, THE System SHALL invoke the Revision_Analyzer using the plain instruction text and the parent run's output column as inputs, matching the existing Concierge-path input sourcing.
5. WHEN `ScopedStore.append_event` writes `run_events` rows for Revision_Analyzer execution, each row SHALL have a `run_id` matching the revision run's id, a `seq` value that is unique and monotonically increasing from 0 within that run, and a non-null unique `event_id`.
6. WHEN a revision run that includes the Analyzer is minted, THE `agent_count` column on the child revision `WorkflowRun` row SHALL equal the pre-Analyzer pipeline agent count plus 1, so the frontend progress bar formula produces the correct percentage.
7. WHEN the banned-pattern CI ratchet runs (`test_sse_cutover_banned_patterns.py` and `test_banned_patterns.py`), THE System SHALL pass all 11 + 5 pattern tests unchanged — no banned symbol (workflow name in engine, WS tokens) shall be introduced.

---

### Requirement 10: No Engine Edits (SC-001 Compliance)

**User Story:** As a platform architect, I want the Prototype Revision Analyzer to be implemented entirely outside the Execution_Engine kernel, so that the SC-001 invariant — a new custom workflow can be created with zero engine edits — is maintained.

#### Acceptance Criteria

1. THE Revision_Analyzer SHALL be defined, imported, and called exclusively in the app-layer (`app/api/run_commands.py` or a new `app/agents/` module) — `grep -rn "prototype.revision.analyzer\|RevisionAnalyzer" agents/execution_engine/` SHALL return 0 matches.
2. WHEN the SC-001 kernel name-free checklist is executed (`grep -rn "if pipeline_type ==" agents/execution_engine/` and `grep -rn 'spec\.id ==' agents/execution_engine/`), BOTH commands SHALL return 0 matches.
3. IF `ectx.analyzer_solution` is non-empty, THEN THE `_compose_context_message` function SHALL include the `=== REVISION ANALYSIS ===` block at position 5 in the composed context, with no pipeline-name guard or conditional branch keyed to a workflow name anywhere in the kernel code path.
4. THE new `ectx.analyzer_solution` field on `ExecutionContext` SHALL be typed `str` with a default value of `""`, so all existing golden characterization runs that do not set it remain byte-identical (INV-3 safe).
5. WHEN `grep -rn "prototype_revision\|prototype_large\|prototype_feature" agents/execution_engine/` is run, THE command SHALL return 0 matches.
