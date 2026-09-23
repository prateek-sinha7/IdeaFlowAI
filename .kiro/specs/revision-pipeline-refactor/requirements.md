# Requirements Document

## Introduction

This feature refactors the three prototype revision pipelines (`prototype_revision`, `prototype_large_revision`, `prototype_feature_revision`) to move revision tier classification out of the analyzer agent and into the existing `_classify_revision_tier` step, and to promote the `prototype-revision-analyzer` agent from a hidden pre-pipeline call into the first visible, engine-executed step in all three revision pipeline manifests. Context from the analyzer (the solution plan) must be correctly passed to all downstream agents in every pipeline, and all three pipelines must produce correct output.

## Glossary

- **Revision_Analyzer**: The existing `prototype-revision-analyzer` agent (AGENT.md at `backend/agents/prompts/prototype-revision-analyzer/AGENT.md`). Produces a structured output containing only a `## Solution Plan` section (tier classification is handled separately by `_classify_revision_tier` before the pipeline starts).
- **Tier_Classifier**: The existing `_classify_revision_tier` function in `backend/app/api/run_commands.py`. Performs a lightweight single LLM call that returns one of `small | large | feature` with no solution plan.
- **Pipeline_Router**: The app-layer logic in `run_commands.py` (the `create_revision` endpoint and `_dispose_concierge_proposal`) that selects the correct revision manifest (`prototype_revision`, `prototype_large_revision`, or `prototype_feature_revision`) based on the classified tier.
- **Small_Revision_Pipeline**: The `prototype_revision` workflow manifest and all its agent steps.
- **Large_Revision_Pipeline**: The `prototype_large_revision` workflow manifest and all its agent steps.
- **Feature_Revision_Pipeline**: The `prototype_feature_revision` workflow manifest and all its agent steps.
- **ExecutionContext**: The `ectx` dataclass (`backend/agents/execution_engine/context.py`) that carries per-run state through the engine, including the `analyzer_solution` field.
- **run_analyzer**: The existing pre-pipeline async function in `backend/app/agents/revision_analyzer.py` that currently both classifies the tier and produces the solution plan before the engine starts.
- **analyzer_solution**: The `## Solution Plan` body extracted from the Revision_Analyzer's output, stored on `ectx.analyzer_solution` and injected into downstream agent context messages as `=== REVISION ANALYSIS ===`.
- **Engine**: The `ExecutionEngine` in `backend/agents/execution_engine/engine.py` — the kernel that executes agents in topological order following the compiled manifest.
- **workflow.yaml**: The declarative manifest file for each workflow, defining the ordered list of agent steps.

---

## Requirements

### Requirement 1: Tier Classification Responsibility

**User Story:** As a developer maintaining the revision pipelines, I want tier classification (`small | large | feature`) to be the sole responsibility of `_classify_revision_tier`, so that the Revision_Analyzer agent is not responsible for routing decisions and its role is limited to producing an implementation plan.

#### Acceptance Criteria

1. WHEN a prototype revision is requested, THE Pipeline_Router SHALL call `_classify_revision_tier` to determine the tier (`small`, `large`, or `feature`) before selecting the revision manifest to launch.
2. THE Revision_Analyzer agent SHALL NOT be responsible for tier classification; tier routing decisions SHALL be made exclusively by `_classify_revision_tier` in the app-layer.
3. WHEN `_classify_revision_tier` returns `small`, THE Pipeline_Router SHALL select the `prototype_revision` manifest.
4. WHEN `_classify_revision_tier` returns `large`, THE Pipeline_Router SHALL select the `prototype_large_revision` manifest.
5. WHEN `_classify_revision_tier` returns `feature`, THE Pipeline_Router SHALL select the `prototype_feature_revision` manifest.
6. IF `_classify_revision_tier` returns an unrecognised value, THEN THE Pipeline_Router SHALL default to `large` and select the `prototype_large_revision` manifest.
7. IF `_classify_revision_tier` raises an exception, THEN THE Pipeline_Router SHALL default to `small` and select the `prototype_revision` manifest.

---

### Requirement 2: Analyzer Agent as First Step in All Three Pipelines

**User Story:** As a user watching the revision run in the UI, I want to see the Revision_Analyzer agent executing as the first visible step in every revision pipeline, so that I can see the analysis phase before the build work begins.

#### Acceptance Criteria

1. THE Small_Revision_Pipeline workflow.yaml SHALL declare `prototype-revision-analyzer` as the first agent step.
2. THE Large_Revision_Pipeline workflow.yaml SHALL declare `prototype-revision-analyzer` as the first agent step.
3. THE Feature_Revision_Pipeline workflow.yaml SHALL declare `prototype-revision-analyzer` as the first agent step.
4. WHEN the Engine executes any of the three revision pipelines, THE Engine SHALL execute `prototype-revision-analyzer` as the first agent before any other step in that pipeline.
5. THE `prototype-revision-analyzer` step in all three pipeline manifests SHALL use the existing AGENT.md at `backend/agents/prompts/prototype-revision-analyzer/AGENT.md` — no new agent definition SHALL be created.
6. THE `prototype-revision-analyzer` step in each pipeline manifest SHALL be declared with `strategy: single_shot` and no human gate, so it executes automatically without waiting for user review.

---

### Requirement 3: Removal of Pre-Pipeline run_analyzer Call

**User Story:** As a developer, I want the pre-pipeline `run_analyzer` invocation removed from `run_commands.py`, so that the analyzer runs only once — inside the engine as the first manifest step — and is not duplicated outside the pipeline.

#### Acceptance Criteria

1. THE Pipeline_Router SHALL NOT call `run_analyzer` before launching the revision pipeline; tier classification SHALL be delegated solely to `_classify_revision_tier`.
2. WHEN a prototype revision is dispatched through the REST endpoint (`POST /api/runs/{id}/revisions`), THE Pipeline_Router SHALL only call `_classify_revision_tier` and SHALL NOT invoke `run_analyzer` prior to minting the revision row.
3. WHEN a prototype revision is dispatched through the Concierge path (`_dispose_concierge_proposal`), THE Pipeline_Router SHALL only call `_classify_revision_tier` and SHALL NOT invoke `run_analyzer` prior to launching the pipeline.
4. THE `extra_agent_count` offset in `_mint_revision_row` SHALL be set to `0` for prototype revisions, because the Revision_Analyzer is now a declared manifest step and is already counted in the workflow agent roster.
5. THE `_drive_revision_to_queue` function SHALL NOT receive an `analyzer_solution` kwarg from the pre-pipeline path; the `analyzer_solution` field on `ExecutionContext` SHALL be populated by the Revision_Analyzer agent step executing inside the engine.

---

### Requirement 4: Context Passing from Analyzer to Downstream Steps

**User Story:** As a developer, I want the solution plan produced by the Revision_Analyzer to be available to all downstream agents in the same pipeline, so that agents such as `prototype-revision-agent`, `prototype-revision-planner`, `prototype-revision-feature-specify`, and `prototype-build` can use the pre-analyzed implementation plan.

#### Acceptance Criteria

1. WHEN the Revision_Analyzer step completes inside the engine, THE Engine SHALL extract the `## Solution Plan` section from the agent's output and store it on `ectx.analyzer_solution`.
2. WHILE `ectx.analyzer_solution` is non-empty, THE Engine SHALL inject a `=== REVISION ANALYSIS ===` block into the context message of every subsequent agent step in the same pipeline run.
3. THE `analyzer_solution` value SHALL be available to the first downstream agent step immediately after the Revision_Analyzer step completes — no additional HTTP call or event queue flush is required.
4. IF the Revision_Analyzer step produces output that does not contain a `## Solution Plan` section, THEN THE Engine SHALL store an empty string in `ectx.analyzer_solution` and downstream agents SHALL receive no `=== REVISION ANALYSIS ===` injection.
5. THE existing `parse_analyzer_output` pure function in `backend/app/agents/revision_analyzer.py` SHALL be reused to extract the solution plan from the Revision_Analyzer's raw output; the engine hook SHALL store only the solution string on `ectx.analyzer_solution` (any tier value returned by `parse_analyzer_output` is ignored by the hook).

---

### Requirement 5: Output Correctness for All Three Pipelines

**User Story:** As a user, I want all three revision pipelines to successfully produce a revised `prototype.html` deliverable, so that my revision request is fulfilled regardless of which tier was selected.

#### Acceptance Criteria

1. WHEN the Small_Revision_Pipeline completes, THE Small_Revision_Pipeline SHALL produce a revised `prototype.html` that incorporates the revision instruction.
2. WHEN the Large_Revision_Pipeline completes, THE Large_Revision_Pipeline SHALL produce a revised `prototype.html` that incorporates the revision instruction.
3. WHEN the Feature_Revision_Pipeline completes, THE Feature_Revision_Pipeline SHALL produce a revised `prototype.html` that incorporates the revision instruction.
4. THE `revises_existing: true` deliverable configuration SHALL remain intact in all three pipeline manifests, so that the output correctly replaces the parent run's prototype artifact.
5. WHEN the Revision_Analyzer step in any pipeline produces a solution plan, THE downstream build agents in that pipeline SHALL receive the `=== REVISION ANALYSIS ===` block with that plan as part of their context.

---

### Requirement 6: No New Analyzer Agent

**User Story:** As a developer, I want the same `prototype-revision-analyzer` agent reused across all three revision pipelines, so that there is a single AGENT.md definition and no duplicated or shadow agents are created.

#### Acceptance Criteria

1. THE three revision pipeline manifests (`prototype_revision`, `prototype_large_revision`, `prototype_feature_revision`) SHALL all reference the single `prototype-revision-analyzer` agent id in their first step.
2. NO new AGENT.md file, agent prompt directory, or agent id SHALL be created for the purposes of this refactor; the existing `prototype-revision-analyzer` definition SHALL be reused unchanged.
3. THE `prototype-revision-analyzer` AGENT.md `pipeline_type` field MAY remain set to its current value (`prototype_revision_analyzer`) or be updated to reference all three revision pipelines — it SHALL NOT conflict with existing invariants or tests. The AGENT.md prompt content MAY also be updated to reflect the agent's new role as a pure solution-plan producer (see Requirement 9).

---

### Requirement 9: Analyzer Agent Output Simplification

**User Story:** As a developer, I want the `prototype-revision-analyzer` agent to produce only a `## Solution Plan` section — with no tier classification in its output — so that the agent's role is clearly limited to implementation planning and its output contract is simpler to parse and maintain.

#### Acceptance Criteria

1. THE `prototype-revision-analyzer` AGENT.md SHALL be updated to remove tier classification instructions (Steps 2–3 and the tier decision table from the current prompt), so that the agent's output contract contains only a `## Solution Plan` section and no `## Tier` section.
2. THE `prototype-revision-analyzer` AGENT.md output contract example and instructions SHALL describe a single-section Markdown output with only `## Solution Plan`.
3. THE `parse_analyzer_output` function in `backend/app/agents/revision_analyzer.py` SHALL be simplified to extract only the solution plan body — tier parsing logic (`## Tier` section extraction, `_VALID_TIERS`, `_DEFAULT_TIER`, and the associated WARNING branches) SHALL be removed.
4. THE simplified `parse_analyzer_output` SHALL return only the solution string (not a `(tier, solution)` tuple); callers SHALL be updated accordingly.
5. THE engine hook (the `produces_solution_plan` post-step logic) SHALL store only the solution string directly on `ectx.analyzer_solution` — no tier value is extracted or stored by this hook.
6. IF the `## Solution Plan` section is absent from the Revision_Analyzer's output, THEN THE simplified `parse_analyzer_output` SHALL return an empty string and log a WARNING, consistent with the existing behaviour for the missing-solution-plan case.

---

### Requirement 7: Fallback and Resilience

**User Story:** As a developer, I want the revised revision pipelines to degrade gracefully when classification or analysis fails, so that a revision run never silently hangs or crashes without producing a result.

#### Acceptance Criteria

1. IF `_classify_revision_tier` fails (raises an exception), THEN THE Pipeline_Router SHALL default to tier `small`, select the `prototype_revision` pipeline, and proceed without the solution plan.
2. IF the Revision_Analyzer step fails inside the engine, THEN THE Engine SHALL apply its standard agent-error handling — emitting an `agent_error` event, setting `ectx.analyzer_solution` to `""`, and continuing the pipeline run with no analysis injection.
3. WHEN `ectx.analyzer_solution` is empty (due to fallback or missing section), THE downstream agents SHALL not receive the `=== REVISION ANALYSIS ===` block, and pipeline execution SHALL continue normally.
4. THE `_classify_revision_tier` fallback chain SHALL remain: unrecognised tier → `large`; exception → `small`.

---

### Requirement 8: SC-001 and Engine Invariant Compliance

**User Story:** As a developer, I want the refactored pipelines to comply with the SC-001 and INV-1 invariants, so that no workflow-name or agent-id literal appears in the engine kernel and the kernel remains workflow-agnostic.

#### Acceptance Criteria

1. THE Engine kernel SHALL NOT contain any literal check on workflow names (`prototype_revision`, `prototype_large_revision`, `prototype_feature_revision`) to determine whether to execute the analyzer step — the analyzer step SHALL be declared in each manifest and executed by generic manifest-driven dispatch.
2. THE tier routing logic (`_classify_revision_tier` and the `_REVISION_TIER_TARGET_MAP`) SHALL remain in the app-layer (`run_commands.py`), NOT in the engine kernel.
3. THE injection of `=== REVISION ANALYSIS ===` into agent context messages SHALL be gated solely on `ectx.analyzer_solution` being non-empty — no agent-id or pipeline-type check.
4. WHEN `grep -rn "if pipeline_type ==" agents/execution_engine/` is executed against the codebase, THE result SHALL return 0 matches (SC-001 kernel name-free check must remain green).
