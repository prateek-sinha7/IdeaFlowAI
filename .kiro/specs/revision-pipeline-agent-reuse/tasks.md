# Implementation Plan: revision-pipeline-agent-reuse

## Overview

Eliminate six duplicate agent directories by extending the loader schema to support `pipeline_type: str | list[str]`, updating three `workflow.yaml` manifests to reference shared agents, updating three shared `AGENT.md` files (including removing `injects` from `prototype-validate`), running the test suite to verify correctness, and then deleting the six duplicate directories. The engine (`execution_engine/engine.py`) is **not touched** at any point (SC-001). All five characterization golden snapshots remain byte/event-identical (INV-3).

---

## Tasks

- [x] 1. Extend `AgentSpec.pipeline_type` to `str | list[str]` in `loader.py`
  - [x] 1.1 Update the `AgentSpec` dataclass `pipeline_type` field annotation from `str` to `str | list[str]` in `backend/agents/loader.py`
    - Change the field declaration: `pipeline_type: str | list[str]`
    - The docstring comment "One of SUPPORTED_PIPELINE_TYPES" should be updated to reflect the new shape
    - _Requirements: 6.1, 6.2_

  - [x] 1.2 Update `_build_spec` in `loader.py` to parse and validate `pipeline_type` as `str | list[str]`
    - Replace the `_require_nonempty_str(metadata, "pipeline_type", ...)` call with a new inline block (or extracted helper `_parse_pipeline_type`)
    - If value is a `str`: validate it is non-empty (existing logic unchanged)
    - If value is a `list`: validate it is non-empty AND every element is a non-empty `str`; raise `AgentSpecError` if any element is invalid
    - If value is any other type (int, None, bool, etc.): raise `AgentSpecError` with a descriptive message naming the file
    - Pass the parsed value through to `AgentSpec(pipeline_type=...)` unchanged
    - _Requirements: 6.1, 6.5_

  - [x] 1.3 Update `list_agent_ids` in `loader.py` to use membership matching for list values
    - Replace the single equality check `if spec.pipeline_type == pipeline_type:` with a branch:
      - If `isinstance(spec.pipeline_type, list)`: `if pipeline_type in spec.pipeline_type:`
      - Else (string): `if spec.pipeline_type == pipeline_type:`
    - The duplicate `order` detection loop that follows already operates on the `matching` list scoped to the current call — no change needed there; order uniqueness is validated per pipeline bucket
    - _Requirements: 6.1, 6.4_

  - [x] 1.4 Update `_discover_supported_pipeline_types` in `loader.py` to expand list values
    - In the `for spec in iter_agent_specs():` loop, replace the single `types.add(spec.pipeline_type)` with a branch:
      - If `isinstance(spec.pipeline_type, list)`: `for pt in spec.pipeline_type: types.add(pt)`
      - Else: `types.add(spec.pipeline_type)`
    - _Requirements: 6.1, 6.2_

  - [x]* 1.5 Write property tests for loader `pipeline_type` list parsing
    - **Property 3: Order uniqueness** — for every `pt` in `SUPPORTED_PIPELINE_TYPES`, no two agents in `list_agent_ids(pt)` share the same `order` value; add a parametric test using a tmp `prompts` dir with two agents sharing a pipeline in their list values to confirm `AgentSpecError` is raised when they share `order`
    - **Validates: Requirements 6.4, 6.5**

  - [x]* 1.6 Write unit tests for loader `pipeline_type` list parsing in `backend/tests/agents/test_loader.py`
    - Add a `TestLoadAgentSpecPipelineTypeList` class with:
      - `test_pipeline_type_list_parses`: write an AGENT.md with `pipeline_type: [prototype, prototype_revision]`; assert `spec.pipeline_type == ["prototype", "prototype_revision"]`
      - `test_pipeline_type_list_empty_raises`: write an AGENT.md with `pipeline_type: []`; assert `AgentSpecError` is raised
      - `test_pipeline_type_list_element_empty_raises`: write an AGENT.md with `pipeline_type: ["prototype", ""]`; assert `AgentSpecError` is raised naming the file
      - `test_pipeline_type_list_element_non_string_raises`: write an AGENT.md with `pipeline_type: [prototype, 42]`; assert `AgentSpecError`
      - `test_pipeline_type_null_raises`: write an AGENT.md with `pipeline_type: null`; assert `AgentSpecError`
      - `test_pipeline_type_int_raises`: write an AGENT.md with `pipeline_type: 1`; assert `AgentSpecError`
    - Add a `TestListAgentIdsWithListPipelineType` class with:
      - `test_agent_with_list_appears_in_both_buckets`: create one agent with `pipeline_type: [user_stories, ppt]`; assert it appears in both `list_agent_ids("user_stories")` and `list_agent_ids("ppt")`
      - `test_agent_with_list_absent_from_unrelated_bucket`: assert it does NOT appear in `list_agent_ids("prototype")`
      - `test_duplicate_order_within_list_pipeline_bucket_raises`: create two agents both declaring `prototype_revision` in their list and sharing `order: 2`; assert `AgentSpecError` names `prototype_revision`
      - `test_string_and_list_agents_coexist_in_bucket`: one agent has `pipeline_type: "user_stories"`, another has `pipeline_type: ["user_stories", "ppt"]`; assert both appear in `list_agent_ids("user_stories")`
    - _Requirements: 6.1, 6.4, 6.5_

- [x] 2. Update the three revision `workflow.yaml` manifests
  - [x] 2.1 Update `backend/agents/workflows/prototype_revision/workflow.yaml`
    - Change `steps[1].agent` from `prototype-revision-validate` to `prototype-validate`
    - All other fields for that step remain identical (`tools`, `strategy`, `gates`)
    - _Requirements: 1.1_

  - [x] 2.2 Update `backend/agents/workflows/prototype_large_revision/workflow.yaml`
    - Change `steps[1].agent` from `prototype-large-builder` to `prototype-build`
    - Change `steps[1].task_source.source_step` — it already reads `prototype-revision-planner`; confirm it is unchanged
    - Change `steps[2].agent` from `prototype-large-validate` to `prototype-validate`
    - All other fields for both steps remain identical
    - _Requirements: 2.1, 2.5, 3.1_

  - [x] 2.3 Update `backend/agents/workflows/prototype_feature_revision/workflow.yaml`
    - Change `steps[1].agent` from `prototype-revision-feature-plan` to `prototype-plan`
    - Change `steps[2].agent` from `prototype-feature-builder` to `prototype-build`
    - Change `steps[2].task_source.source_step` from `prototype-revision-feature-plan` to `prototype-plan`
    - Confirm `steps[2].task_source.spec_step` is `prototype-revision-feature-specify` (no change needed)
    - Change `steps[3].agent` from `prototype-feature-validate` to `prototype-validate`
    - All other fields remain identical
    - _Requirements: 4.1, 4.3, 4.5, 4.6, 5.1_

- [x] 3. Update shared agent `AGENT.md` files
  - [x] 3.1 Update `backend/agents/prompts/prototype-validate/AGENT.md`
    - Change `pipeline_type: prototype` to the YAML list form:
      ```yaml
      pipeline_type:
        - prototype
        - prototype_revision
        - prototype_large_revision
        - prototype_feature_revision
      ```
    - Remove the `injects:` block entirely (both the key and its `- template` / `- design_system` items) — this is required for `test_run_revision_revision_agents_declare_no_template_injects` to pass (prototype_revision is in `_RUN_REVISION_DISPATCHED`)
    - Update `consumes:` to list all upstream predecessors across all participating pipelines (post-cleanup final form):
      ```yaml
      consumes:
        - prototype-build
        - prototype-revision-agent
      ```
    - _Requirements: 1.2, 1.3, 1.4, 7.1, 7.2, 7.3_

  - [x] 3.2 Update `backend/agents/prompts/prototype-build/AGENT.md`
    - Change `pipeline_type: prototype` to:
      ```yaml
      pipeline_type:
        - prototype
        - prototype_large_revision
        - prototype_feature_revision
      ```
    - Update `consumes:` to list all upstream predecessors across all participating pipelines (post-cleanup final form):
      ```yaml
      consumes:
        - prototype-plan
        - prototype-revision-planner
      ```
    - `injects: [template, design_system, craft]` is left unchanged — `prototype-build` is not used in any pipeline from `_RUN_REVISION_DISPATCHED` (only `prototype_revision` is dispatched; `prototype_large_revision` and `prototype_feature_revision` are not)
    - _Requirements: 2.2, 2.4, 7.4_

  - [x] 3.3 Update `backend/agents/prompts/prototype-plan/AGENT.md`
    - Change `pipeline_type: prototype` to:
      ```yaml
      pipeline_type:
        - prototype
        - prototype_feature_revision
      ```
    - Update `consumes:` to list all upstream predecessors across all participating pipelines (post-cleanup final form):
      ```yaml
      consumes:
        - prototype-specify
        - prototype-revision-feature-specify
      ```
    - _Requirements: 4.2, 4.4, 7.5_

- [x] 4. Checkpoint — run affected test suites before deleting any directories
  - Run `pytest backend/tests/agents/test_loader.py backend/tests/agents/test_registry.py backend/tests/agents/test_manifest_coverage.py backend/tests/agents/test_manifest_parity.py backend/tests/agents/test_banned_patterns.py backend/tests/agents/test_compiled_plan_runs.py -v` and ensure all pass. At this stage the duplicate agent directories are still on disk; the manifests and shared AGENT.md files have been updated. If failures appear here, fix before proceeding to step 5.
  - Ensure `test_run_revision_revision_agents_declare_no_template_injects` passes (confirms `injects` removal from `prototype-validate` is correct)
  - Ensure `test_all_load_compile` passes for `prototype_revision`, `prototype_large_revision`, `prototype_feature_revision` (confirms the manifest→registry parity after loader change)
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Delete the six duplicate agent directories
  - [x] 5.1 Delete `backend/agents/prompts/prototype-revision-validate/` (superseded by `prototype-validate`)
    - _Requirements: 12.1_

  - [x] 5.2 Delete `backend/agents/prompts/prototype-large-builder/` (superseded by `prototype-build`)
    - _Requirements: 12.1_

  - [x] 5.3 Delete `backend/agents/prompts/prototype-large-validate/` (superseded by `prototype-validate`)
    - _Requirements: 12.1_

  - [x] 5.4 Delete `backend/agents/prompts/prototype-revision-feature-plan/` (superseded by `prototype-plan`)
    - _Requirements: 12.1_

  - [x] 5.5 Delete `backend/agents/prompts/prototype-feature-builder/` (superseded by `prototype-build`)
    - _Requirements: 12.1_

  - [x] 5.6 Delete `backend/agents/prompts/prototype-feature-validate/` (superseded by `prototype-validate`)
    - _Requirements: 12.1_

- [x] 6. Update and add test assertions
  - [x] 6.1 Add revision pipeline roster assertions to `backend/tests/agents/test_registry.py`
    - Add a `TestRevisionPipelineRosters` class with:
      - `test_prototype_revision_roster`: assert `list_agent_ids("prototype_revision") == ["prototype-revision-agent", "prototype-validate"]`
      - `test_prototype_large_revision_roster`: assert `list_agent_ids("prototype_large_revision") == ["prototype-revision-planner", "prototype-build", "prototype-validate"]`
      - `test_prototype_feature_revision_roster`: assert `list_agent_ids("prototype_feature_revision") == ["prototype-revision-feature-specify", "prototype-plan", "prototype-build", "prototype-validate"]`
      - `test_prototype_pipeline_unchanged`: assert `list_agent_ids("prototype") == ["prototype-specify", "prototype-plan", "prototype-analyze", "prototype-build", "prototype-validate"]`
    - These use the REAL filesystem; no `tmp_agent_dir` fixture needed
    - _Requirements: 9.4, 12.2_

  - [x]* 6.2 Write property tests for roster completeness and prototype regression
    - **Property 1: Roster completeness** — for each of `["prototype_revision", "prototype_large_revision", "prototype_feature_revision"]`, assert the roster equals exactly the agents referenced in the corresponding `workflow.yaml` steps in manifest order
    - **Property 2: No prototype pipeline regression** — assert `list_agent_ids("prototype")` equals the pre-change ordered list (the five prototype agents)
    - **Validates: Requirements 6.2, 6.3, 9.1, 9.4**

  - [x] 6.3 Verify `test_all_agents_have_supported_pipeline_type` in `test_loader.py` passes after deletion
    - The existing `TestSchemaValidationAllAgents::test_all_agents_have_supported_pipeline_type` checks `spec.pipeline_type in SUPPORTED_PIPELINE_TYPES`. For list-typed agents this check will fail because `["prototype", "prototype_revision"]` is not `in` a frozenset of strings.
    - Update the assertion in `test_all_agents_have_supported_pipeline_type` to handle the new list shape: if `isinstance(spec.pipeline_type, list)`, check that each element is in `SUPPORTED_PIPELINE_TYPES`; otherwise check the string directly.
    - Similarly update `test_all_agents_have_required_fields` to handle `assert spec.pipeline_type` being truthy for a non-empty list.
    - _Requirements: 6.1_

- [x] 7. Verify characterization goldens and run full test suite
  - [x] 7.1 Run the full characterization test suite and confirm INV-3 holds
    - Run `pytest backend/tests/agents/test_characterization_*.py -v` with `SNAPSHOT_UPDATE` unset
    - The `prototype_revision` golden (`prototype_revision.events.json`, `prototype_revision.html`, `prototype_revision.wsframes.json`) must not diverge. If removing `injects` from `prototype-validate` changes what context is prepended to the prompt in the scripted-model harness and the golden diverges, regenerate it once with `SNAPSHOT_UPDATE=1`, then re-run without the env var to confirm the new golden is stable. Commit the new golden.
    - The `prototype`, `ppt`, and `app_builder` goldens must remain byte-identical (their pipelines are untouched)
    - _Requirements: 9.2, 9.3_

  - [x]* 7.2 Write a property test for SC-001 compliance
    - **Property 4: SC-001 compliance** — run `grep -rn "if pipeline_type ==" agents/execution_engine/` and `grep -rn "prototype_large_revision\|prototype_feature_revision\|prototype_revision" agents/execution_engine/` from within a test; assert both return zero matches. The test should live in `backend/tests/agents/test_banned_patterns.py` or a new test class alongside the existing `test_banned_patterns.py` checks.
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

  - [x] 7.3 Run the full test suite and confirm no regressions
    - Run `pytest backend/tests/agents/ -v --tb=short` and confirm:
      - `test_banned_patterns.py` — all 11 tests pass (zero engine edits)
      - `test_registry_capabilities.py` — drift-guard count unchanged (no new capabilities)
      - `test_manifest_coverage.py::test_exactly_18_keys` — still 18 (no new workflow.yaml added or removed)
      - `test_manifest_parity.py` — all traps pass including `test_run_revision_revision_agents_declare_no_template_injects`
      - `test_compiled_plan_runs.py::_every_step_agent_loads` — all steps reference valid on-disk agents (deleted directories must NOT be referenced)
    - _Requirements: 8.5, 9.2, 13.1, 13.3_

- [x] 8. Verify frontend correctness for revision pipeline types
  - [x] 8.1 Verify `renderType` mapping in `frontend/src/components/preview/PreviewPanel.tsx` covers `prototype_large_revision` and `prototype_feature_revision`
    - Confirm lines already map both to `"prototype"` (confirmed present in the existing file at lines 577–578)
    - If absent or incorrect, add:
      ```ts
      : detectedType === "prototype_large_revision" ? "prototype"
      : detectedType === "prototype_feature_revision" ? "prototype"
      ```
    - _Requirements: 11.6_

  - [x] 8.2 Verify `deriveDeliverableFilename` in `frontend/src/components/results/FilesTab.tsx` covers `prototype_large_revision` and `prototype_feature_revision`
    - The current prototype branch only checks `workflowType === "prototype" || workflowType === "prototype_revision"` — `prototype_large_revision` and `prototype_feature_revision` fall through to the generic `fallback || "deliverable"` return
    - Extend the prototype branch condition to include both revision variants:
      ```ts
      if (
        workflowType === "prototype" || workflowType === "prototype_revision"
        || workflowType === "prototype_large_revision" || workflowType === "prototype_feature_revision"
      ) {
      ```
    - Apply the same fix to `deriveDeliverableFiles` (the `(workflowType === "prototype" || workflowType === "prototype_revision") && prototypeContent` branch) so the Files tab row appears for all three revision variants
    - _Requirements: 11.3, 11.4_

- [x] 9. Final checkpoint — full suite green
  - Run `pytest backend/tests/agents/ -v` and confirm all tests pass. Run `git status --porcelain backend/tests/agents/characterization/golden/` and confirm no unexpected changes (or that only `prototype_revision.*` goldens changed, if they required regeneration). Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for an MVP. All non-starred tasks must be completed for the feature to be correct and CI-green.
- Task ordering is critical: the loader schema change (task 1) must land before the AGENT.md updates (task 3), which must land before the deletions (task 5). The checkpoint at task 4 verifies correctness with duplicate directories still present — only after that checkpoint are the deletions safe.
- `engine.py` must not be opened or modified at any point. The grep checks in task 7.2 / requirements 8.3–8.4 verify this.
- If the `prototype_revision` characterization golden diverges after removing `injects` from `prototype-validate`, regenerate once (`SNAPSHOT_UPDATE=1`) and commit. All other goldens must stay byte-identical.
- `test_manifest_coverage.py::test_exactly_18_keys` will remain at 18 because no `workflow.yaml` is added or removed — only the contents of three existing ones change.
- The `_RUN_REVISION_DISPATCHED` set in `test_manifest_parity.py` already includes `prototype_revision`. Removing `injects` from `prototype-validate` (task 3.1) is what makes `test_run_revision_revision_agents_declare_no_template_injects` pass for that pipeline.
- Each task references specific file paths; an agent executing tasks 1–3 can work entirely from this document without opening the design doc.

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["1.5", "1.6", "2.1", "2.2", "2.3"] },
    { "id": 3, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6"] },
    { "id": 5, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 6, "tasks": ["7.1", "7.2", "7.3", "8.1", "8.2"] }
  ]
}
```
