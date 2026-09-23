# Requirements Document

## Introduction

The three prototype revision pipeline variants (`prototype_revision`, `prototype_large_revision`, `prototype_feature_revision`) currently each define their own dedicated builder agents (`prototype-revision-agent`, `prototype-large-builder`, `prototype-feature-builder`), validator agents (`prototype-revision-validate`, `prototype-large-validate`, `prototype-feature-validate`), and planner agents (`prototype-revision-planner`, `prototype-revision-feature-plan`). These duplicate the roles already fulfilled by `prototype-build`, `prototype-validate`, `prototype-plan`, and `prototype-specify` from the main `prototype` pipeline.

This feature replaces the revision-specific duplicates with the shared main-pipeline agents, updating the three revision `workflow.yaml` manifests and the agent `AGENT.md` frontmatter to point `pipeline_type` at their respective revision pipeline identifiers, while keeping all invariants intact: no engine edits (SC-001), the 5 characterization goldens remain byte/event-identical (INV-3), PIPELINE_AGENTS continues to be discovered from disk, and all frontend tabs (context, previews, versions, steps, files, audit) continue to display correct data.

---

## Glossary

- **Main_Pipeline**: The `prototype` pipeline defined in `backend/agents/workflows/prototype/workflow.yaml`.
- **Revision_Pipelines**: The three pipelines `prototype_revision`, `prototype_large_revision`, and `prototype_feature_revision` defined in their respective `workflow.yaml` files under `backend/agents/workflows/`.
- **Shared_Agent**: An AGENT.md that declares multiple `pipeline_type` values (or whose `pipeline_type` key is updated to match a revision pipeline), allowing it to be discovered by the loader for that pipeline.
- **PIPELINE_AGENTS**: The runtime-discovered dict in `backend/agents/registry.py` that maps each pipeline type to an ordered list of agent IDs, populated by scanning `AGENT.md` frontmatter.
- **Loader**: The `backend/agents/loader.py` module that scans `AGENT.md` files and builds `AgentSpec` objects keyed on `pipeline_type`.
- **Workflow_Manifest**: A `workflow.yaml` file that declares `steps[].agent` field values referencing agent IDs.
- **Agent_ID**: The unique `id` field in an `AGENT.md` file, referenced by `workflow.yaml` step `agent:` fields.
- **Builder_Agent**: An agent executing the `task_loop` strategy that builds or modifies `prototype.html` incrementally, one task at a time.
- **Validator_Agent**: An agent executing the `single_shot` strategy that performs final quality checks and fixes on `prototype.html`.
- **Planner_Agent**: An agent executing the `single_shot` strategy that decomposes a revision or feature request into an ordered task list.
- **Specify_Agent**: An agent executing the `single_shot` strategy that writes a feature specification consumed by the planner.
- **context_from**: AGENT.md frontmatter field listing artifact IDs or `$previous` that the agent receives as context.
- **consumes**: AGENT.md frontmatter field listing the agent IDs whose outputs feed into this agent.
- **REVISION_BASE_MAP**: The dict in `backend/agents/registry.py` mapping each revision pipeline type to its base pipeline type.
- **INV-3**: The invariant that the 5 characterization golden snapshots must remain byte/event-identical after changes.
- **SC-001**: The invariant that a new custom workflow can replicate `prototype` using manifest + AGENT.md only, with zero engine edits.

---

## Requirements

### Requirement 1: Shared Validator Agent for `prototype_revision`

**User Story:** As a developer, I want the `prototype_revision` pipeline to reuse `prototype-validate` as its final validation step, so that validator logic is defined once and improvements propagate to all three revision pipelines automatically.

#### Acceptance Criteria

1. THE `prototype_revision` `workflow.yaml` `steps[1].agent` field SHALL reference `prototype-validate`.
2. THE `prototype-validate` AGENT.md SHALL declare `pipeline_type: prototype` such that the Loader continues to include it in `PIPELINE_AGENTS["prototype"]`.
3. WHEN the Loader scans `agents/prompts/prototype-validate/AGENT.md` and the agent configuration is valid, THE Loader SHALL include `prototype-validate` in `PIPELINE_AGENTS["prototype_revision"]`; IF the scan succeeds but other validation errors exist in the agent configuration, THEN THE Loader SHALL raise an error and prevent system startup.
4. WHEN `prototype-validate` runs inside `prototype_revision`, THE Validator_Agent SHALL receive the output of the preceding revision agent as context via the `consumes` and `context_from` fields in its AGENT.md frontmatter, AND the engine SHALL verify that this context is delivered at runtime.
5. IF the `prototype-validate` AGENT.md `pipeline_type` field is changed in a way that removes it from the `prototype` bucket, THEN THE Loader SHALL raise an `AgentSpecError` at startup, alerting the developer.

---

### Requirement 2: Shared Builder Agent for `prototype_large_revision`

**User Story:** As a developer, I want the `prototype_large_revision` pipeline to reuse `prototype-build` as its builder step, so that the task-loop build logic is maintained in one place.

#### Acceptance Criteria

1. THE `prototype_large_revision` `workflow.yaml` `steps[1].agent` field SHALL reference `prototype-build`.
2. THE `prototype-build` AGENT.md `pipeline_type` field SHALL continue to declare `prototype` so the Loader keeps it in `PIPELINE_AGENTS["prototype"]`.
3. WHEN the Loader scans `agents/prompts/prototype-build/AGENT.md` and the agent configuration is valid, THE Loader SHALL include `prototype-build` in `PIPELINE_AGENTS["prototype_large_revision"]`; IF inclusion fails due to validation errors, THEN THE Loader SHALL treat this as a critical error that prevents the pipeline from being available for execution.
4. WHEN `prototype-build` runs inside `prototype_large_revision`, THE Builder_Agent SHALL receive the task list output from `prototype-revision-planner` as context via the `task_source.source_step` field in `workflow.yaml`.
5. THE `prototype_large_revision` `workflow.yaml` `steps[1].task_source.source_step` field SHALL reference `prototype-revision-planner`.

---

### Requirement 3: Shared Validator Agent for `prototype_large_revision`

**User Story:** As a developer, I want the `prototype_large_revision` pipeline to reuse `prototype-validate` as its final validation step, so that validator improvements apply uniformly across all revision variants.

#### Acceptance Criteria

1. THE `prototype_large_revision` `workflow.yaml` `steps[2].agent` field SHALL reference `prototype-validate`.
2. WHEN `prototype-validate` runs inside `prototype_large_revision`, THE Validator_Agent SHALL receive the builder's output as context via `consumes` and `context_from`, AND the engine SHALL verify that this context is delivered at runtime.

---

### Requirement 4: Shared Planner and Builder Agents for `prototype_feature_revision`

**User Story:** As a developer, I want the `prototype_feature_revision` pipeline to reuse `prototype-plan` as its planning step and `prototype-build` as its building step, so that planning and building logic for features is not duplicated from the main pipeline.

#### Acceptance Criteria

1. THE `prototype_feature_revision` `workflow.yaml` `steps[1].agent` field SHALL reference `prototype-plan`.
2. WHEN the Loader scans `agents/prompts/prototype-plan/AGENT.md`, THE Loader SHALL include `prototype-plan` in `PIPELINE_AGENTS["prototype_feature_revision"]`.
3. THE `prototype_feature_revision` `workflow.yaml` `steps[2].agent` field SHALL reference `prototype-build`.
4. WHEN `prototype-plan` runs inside `prototype_feature_revision`, THE Planner_Agent SHALL receive the feature specification output from `prototype-revision-feature-specify` as context.
5. THE `prototype_feature_revision` `workflow.yaml` `steps[2].task_source.source_step` field SHALL reference `prototype-plan`.
6. THE `prototype_feature_revision` `workflow.yaml` `steps[2].task_source.spec_step` field SHALL reference `prototype-revision-feature-specify`.

---

### Requirement 5: Shared Validator Agent for `prototype_feature_revision`

**User Story:** As a developer, I want the `prototype_feature_revision` pipeline to reuse `prototype-validate` as its final validation step, so that feature builds benefit from the same validation logic as the main pipeline.

#### Acceptance Criteria

1. WHEN `prototype-validate` runs inside `prototype_feature_revision` as the fourth step, THE Validator_Agent SHALL be referenced by `workflow.yaml` `steps[3].agent` as `prototype-validate`, AND it SHALL receive the feature builder's output as context; IF the context transfer fails, THE Validator_Agent SHALL proceed with whatever context is available rather than failing the run.

---

### Requirement 6: AGENT.md Multi-Pipeline Discovery via Loader

**User Story:** As a developer, I want the Loader to discover shared agents for both their original pipeline and the revision pipelines, so that `PIPELINE_AGENTS` is populated correctly without hand-maintaining any list.

#### Acceptance Criteria

1. THE Loader SHALL discover an agent for a pipeline by matching the AGENT.md `pipeline_type` field to the pipeline identifier.
2. WHEN an agent AGENT.md declares `pipeline_type: prototype`, THE Loader SHALL include that agent in `PIPELINE_AGENTS["prototype"]` AND SHALL NOT automatically include it in `PIPELINE_AGENTS["prototype_revision"]` unless the revision manifest explicitly references it via `steps[].agent`; WHERE a revision manifest explicitly references a prototype agent, THE Loader SHALL include that agent in the revision pipeline's roster.
3. THE `PIPELINE_AGENTS` dict SHALL list each revision pipeline's agents in the order defined by their respective `workflow.yaml` `steps` sequence, consistent with the `order` field in each referenced AGENT.md.
4. WHERE a shared agent is referenced in multiple `workflow.yaml` manifests, THE Loader SHALL not raise duplicate-order errors because the `order` field is scoped to a single `pipeline_type` bucket.
5. IF two AGENT.md files in the same `pipeline_type` bucket declare the same `order` value, THEN THE Loader SHALL raise an `AgentSpecError` naming both conflicting agent IDs.

---

### Requirement 7: AGENT.md Context Routing Correctness

**User Story:** As a developer, I want the `consumes` and `context_from` fields in shared agent AGENT.md files to be updated to reference the correct upstream agent IDs for each revision pipeline context, so that each agent receives the right data at runtime.

#### Acceptance Criteria

1. WHEN `prototype-validate` is used as a step in `prototype_revision`, THE `consumes` field in `prototype-validate`'s AGENT.md SHALL list the revision builder agent ID that precedes it in that pipeline.
2. WHEN `prototype-validate` is used as a step in `prototype_large_revision`, THE `consumes` field in `prototype-validate`'s AGENT.md SHALL list the agent ID that precedes it in that pipeline.
3. WHEN `prototype-validate` is used as a step in `prototype_feature_revision`, THE `consumes` field in `prototype-validate`'s AGENT.md SHALL list the agent ID that precedes it in that pipeline.
4. WHEN `prototype-build` is used as a step in `prototype_large_revision` or `prototype_feature_revision`, THE `consumes` field in `prototype-build`'s AGENT.md SHALL reference the planner step that produces the task list.
5. WHEN `prototype-plan` is used as a step in `prototype_feature_revision`, THE `consumes` field in `prototype-plan`'s AGENT.md SHALL reference the specify step that precedes it.
6. THE WorkflowResolver SHALL resolve `consumes` references at compile time and SHALL raise a compile error if a referenced agent ID is not a step in the compiled workflow; the resolver SHALL NOT treat a missing agent as a success.

---

### Requirement 8: Zero Engine Edits (SC-001 Compliance)

**User Story:** As a developer, I want the reuse to be accomplished entirely through manifest and AGENT.md changes, so that the execution engine kernel remains name-free and universally applicable.

#### Acceptance Criteria

1. THE `backend/agents/execution_engine/engine.py` file SHALL NOT be modified as part of this feature.
2. WHEN the engine compiles a revision pipeline, THE WorkflowCompiler SHALL resolve steps to agent IDs from the manifest `steps[].agent` field without any pipeline-name branching; pipeline-name branching SHALL NOT be used even as a fallback when manifest data is missing or corrupted.
3. THE grep check `grep -rn "if pipeline_type ==" agents/execution_engine/` SHALL return zero matches after implementing this feature.
4. THE grep check `grep -rn "prototype_large_revision\|prototype_feature_revision\|prototype_revision" agents/execution_engine/` SHALL return zero matches after implementing this feature.
5. THE `test_banned_patterns.py` test suite SHALL pass without modification after implementing this feature.

---

### Requirement 9: Main Prototype Pipeline Behavior Unchanged

**User Story:** As a developer, I want the main `prototype` pipeline to continue running exactly as before, so that the reuse change is non-breaking for existing prototype builds.

#### Acceptance Criteria

1. THE `prototype` `workflow.yaml` SHALL NOT be modified by this feature.
2. THE five characterization golden snapshots in `tests/agents/characterization/golden/` SHALL remain byte/event-identical after this feature is implemented (INV-3).
3. WHEN `pytest tests/agents/test_characterization_*.py` is run with `SNAPSHOT_UPDATE` unset, THE test suite SHALL pass.
4. THE `PIPELINE_AGENTS["prototype"]` list SHALL contain the same ordered set of agent IDs (`prototype-specify`, `prototype-plan`, `prototype-analyze`, `prototype-build`, `prototype-validate`) as before.
5. WHEN the `prototype` pipeline runs, THE agents SHALL execute in the same order with the same tools, validators, gates, and task_source configuration as before this feature was implemented.

---

### Requirement 10: Frontend Steps Tab Correctness for Revision Pipelines

**User Story:** As a user, I want the Steps tab to show the correct agent names and roles when viewing a revision pipeline run, so that I can see which agents participated and inspect their reasoning.

#### Acceptance Criteria

1. WHEN a `prototype_revision` run is displayed in the Steps tab, THE AgentThinkingTab SHALL show the agent cards for every step defined in the `prototype_revision` `workflow.yaml`, in manifest order.
2. WHEN a `prototype_large_revision` run is displayed in the Steps tab, THE AgentThinkingTab SHALL show agent cards matching the step sequence: `prototype-revision-planner`, `prototype-build`, `prototype-validate`.
3. WHEN a `prototype_feature_revision` run is displayed in the Steps tab, THE AgentThinkingTab SHALL show agent cards matching the step sequence: `prototype-revision-feature-specify`, `prototype-plan`, `prototype-build`, `prototype-validate`.
4. THE `agents_total` field on the `pipeline_start` event SHALL equal the number of steps in the respective revision pipeline's manifest.
5. THE `agents_completed` count on the `pipeline_complete` event SHALL reflect the number of agents that actually completed during the run; IF the count mismatches `agents_total` while the pipeline is still marked successful, THE pipeline status SHALL take precedence over the agent count.

---

### Requirement 11: Frontend Versions, Previews, Files, and Audit Tabs Correctness

**User Story:** As a user, I want the Versions, Previews, Files, and Audit tabs to remain accurate for all three revision pipeline types after agent reuse, so that my revision history and deliverable access is unaffected.

#### Acceptance Criteria

1. WHEN a revision run completes, THE Versions tab SHALL list the resulting `prototype.html` deliverable under the correct revision index.
2. WHEN a revision run's deliverable is viewed in the Previews tab, THE PreviewPanel SHALL render the `prototype.html` output in an iframe regardless of which revision pipeline type produced it.
3. THE `deriveDeliverableFilename` function SHALL return `prototype.html` for `workflowType` values of `prototype_revision`, `prototype_large_revision`, and `prototype_feature_revision`.
4. THE Files tab SHALL display the workspace files produced by the revision run's shared agents using the same file-listing logic as the main prototype pipeline.
5. THE Audit tab SHALL record one audit event per agent step executed in the revision run, keyed on the shared agent's ID.
6. THE `renderType` mapping in `PreviewPanel.tsx` SHALL map `prototype_large_revision` and `prototype_feature_revision` to `prototype` in addition to the existing `prototype_revision` mapping.

---

### Requirement 12: Deprecation and Cleanup of Duplicate Agent Files

**User Story:** As a developer, I want the now-redundant revision-specific agent AGENT.md files removed from disk, so that there is a single source of truth for each agent's behavior and no divergence can occur silently.

#### Acceptance Criteria

1. WHEN this feature is fully implemented and validated, THE following duplicate AGENT.md directories SHALL be removed: `agents/prompts/prototype-revision-validate/`, `agents/prompts/prototype-large-builder/`, `agents/prompts/prototype-large-validate/`, `agents/prompts/prototype-feature-builder/`, `agents/prompts/prototype-feature-validate/`, `agents/prompts/prototype-revision-feature-plan/`.
2. AFTER removal, THE `PIPELINE_AGENTS` for each revision pipeline SHALL still be populated correctly from the shared main-pipeline agent AGENT.md files referenced in each `workflow.yaml`.
3. THE `prototype-revision-agent` AGENT.md SHALL be retained because it handles the simple single-agent `prototype_revision` scenario with revision-specific prompt instructions not present in `prototype-build`.
4. THE `prototype-revision-planner` AGENT.md SHALL be retained because it handles revision-specific task decomposition for `prototype_large_revision`.
5. THE `prototype-revision-feature-specify` AGENT.md SHALL be retained because it handles feature specification for `prototype_feature_revision`.
6. IF any retained AGENT.md file references a deleted agent ID in its `consumes` field, THEN THE WorkflowCompiler SHALL raise a compile error naming the broken reference before any run executes.

---

### Requirement 13: Registry Drift-Guard Test Consistency

**User Story:** As a developer, I want the capability registry drift-guard test count to remain consistent, so that adding or removing agents does not silently break CI.

#### Acceptance Criteria

1. THE `test_registry_capabilities.py` drift-guard count SHALL be updated in lockstep with any changes to `_KNOWN` in `registry.py` caused by this feature.
2. IF this feature requires no new capability kinds or names, THEN THE `_KNOWN` set in `backend/agents/capabilities/registry.py` SHALL remain unchanged.
3. WHEN `pytest tests/` is run after implementing this feature, THE `test_registry_capabilities` test SHALL pass without modification to the expected count.

---

### Requirement 14: Revision Context Injection to Shared Agents

**User Story:** As a developer, I want shared agents running in a revision pipeline to receive the revision-specific context blocks injected by the engine (such as `=== REVISION ANALYSIS ===`), so that their behaviour adapts correctly to the revision scenario without requiring separate AGENT.md prompt bodies.

#### Acceptance Criteria

1. WHEN `prototype-build` executes in `prototype_large_revision` or `prototype_feature_revision`, THE engine SHALL inject the same `=== CURRENT TASK ===` block as it does for a main pipeline `prototype-build` invocation.
2. WHEN `prototype-validate` executes in any revision pipeline, THE engine SHALL inject the `=== CURRENT PROTOTYPE ===` compaction block when `compaction: html_skeleton` is configured for a preceding step in the same run.
3. THE `=== ADDITIONAL INSTRUCTIONS (REVISE) ===` block SHALL be injected into shared agents when `ectx.redo_directive` is set, following the existing `_compose_context_message` injection order (SC-001 — generic, not keyed on pipeline name).
4. IF the revision pipeline manifest declares `context_providers: [previous_run]`, THEN THE engine SHALL inject the previous run's `prototype.html` only into agents that normally use prototype context (such as `prototype-build`), NOT into agents that do not use prototype.html as input context.

