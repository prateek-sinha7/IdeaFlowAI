# Implementation Plan: Revision Pipeline Refactor

## Overview

Promote `prototype-revision-analyzer` from a hidden pre-pipeline app-layer call
into the first declared step of all three revision pipeline manifests, wire up a
declaration-driven `produces_solution_plan` post-step hook in the engine, and
strip the parallel `run_analyzer` invocation from the app layer so the analyzer
runs exactly once — driven by the engine's normal manifest dispatch.

Implementation language: **Python**.

---

## Tasks

- [x] 1. Add `produces_solution_plan` field to the `Step` dataclass and compiler allow-list
  - [x] 1.1 Add `produces_solution_plan: bool = False` to the `Step` dataclass in `backend/agents/execution_engine/plan.py`
    - Follow the existing `require_render` field convention — a `bool` defaulting to `False` so all existing steps remain unaffected (INV-3 safe)
    - Add a brief docstring comment explaining the flag purpose and SC-001 / INV-1 compliance
    - _Requirements: 8.1, 8.3_

  - [x] 1.2 Register `"produces_solution_plan"` in `_ALLOWED_STEP_KEYS` in `backend/agents/execution_engine/compiler.py`
    - Add the key to the `frozenset` alongside existing keys such as `"compaction"` and `"post_step"`
    - _Requirements: 8.1_

  - [x] 1.3 Read and forward the flag in `WorkflowCompiler._compile_step` / `_expand_step`
    - Read `bool(raw.get("produces_solution_plan", False))` from the raw step dict
    - Pass the value through to the `Step(...)` constructor call
    - Confirm that a non-bool value (e.g. `"not_a_bool"`) is coerced via `bool()` and does not raise
    - _Requirements: 8.1_

  - [ ]* 1.4 Write unit tests for step compilation of `produces_solution_plan`
    - Assert `produces_solution_plan=True` compiles correctly from a manifest step dict
    - Assert `produces_solution_plan` defaults to `False` on a step dict that omits the key
    - Assert a non-bool value (e.g. `"not_a_bool"`) is coerced to `True` without error
    - _Requirements: 8.1_

- [x] 2. Add the post-step extraction hook to the engine
  - [x] 2.1 Insert the `produces_solution_plan` post-step hook in `backend/agents/execution_engine/engine.py`
    - After the `_run_agent` call for a `single_shot` step, check `getattr(ectx.current_step, "produces_solution_plan", False)`
    - If `True`: import `parse_analyzer_output` from `app.agents.revision_analyzer`, read `ectx.last_streamed or ""`, call `parse_analyzer_output(_raw)`, and store the result directly on `ectx.analyzer_solution` — `parse_analyzer_output` returns a `str` (not a tuple); use `ectx.analyzer_solution = parse_analyzer_output(_raw)` (replaces the previous `_tier, _solution = parse_analyzer_output(_raw)` unpack)
    - Wrap in `try/except Exception` — on failure log a WARNING and set `ectx.analyzer_solution = ""`; never re-raise
    - Do NOT reference any agent id or pipeline name — the hook must branch only on the boolean flag (SC-001 / INV-1)
    - _Requirements: 4.1, 4.3, 4.4, 7.2, 8.1, 8.2, 8.3, 9.5_

  - [ ]* 2.2 Write property test for Property 4 — injection gated on `ectx.analyzer_solution` truthiness
    - **Property 4: `_compose_context_message` injection is gated on `ectx.analyzer_solution` truthiness**
    - **Validates: Requirements 4.2, 7.3, 8.3**
    - In `tests/unit/test_compose_context.py`: use `@given(solution=st.text(min_size=1))` — for any non-empty string, the output of `_compose_context_message(ectx, ...)` SHALL contain `"=== REVISION ANALYSIS ==="`
    - Add a deterministic inverse test: `ectx.analyzer_solution = ""` → output SHALL NOT contain `"=== REVISION ANALYSIS ==="`

  - [ ]* 2.3 Write unit tests for the `produces_solution_plan` hook behaviour
    - File: `tests/unit/test_produces_solution_plan_hook.py`
    - Test that `produces_solution_plan=True` + valid `last_streamed` → `ectx.analyzer_solution` is populated
    - Test that `produces_solution_plan=False` (default) → hook does not fire, `ectx.analyzer_solution` stays `""`
    - Test that malformed output (no `## Solution Plan` section) → `ectx.analyzer_solution == ""` and no exception propagates
    - _Requirements: 4.1, 4.4, 7.2_

- [x] 3. Checkpoint — compiler and engine changes
  - Ensure all existing engine tests and the `test_banned_patterns.py` suite (11 tests) pass
  - `grep -rn "if pipeline_type ==" backend/agents/execution_engine/` must return 0 matches
  - `grep -rn 'spec\.id ==' backend/agents/execution_engine/` must return 0 matches
  - Ask the user if any questions arise before proceeding to YAML and app-layer changes

- [x] 4. Update the three revision workflow YAML manifests
  - [x] 4.1 Update `backend/agents/workflows/prototype_revision/workflow.yaml`
    - Prepend a new step 0 with `agent: prototype-revision-analyzer`, `strategy: single_shot`, `gates: []`, `produces_solution_plan: true`
    - Renumber all existing steps (former step 0 becomes step 1, etc.) — no other step fields may change
    - Verify `deliverable.revises_existing: true` remains intact
    - _Requirements: 2.1, 2.4, 2.5, 2.6, 5.1, 5.4, 6.1_

  - [x] 4.2 Update `backend/agents/workflows/prototype_large_revision/workflow.yaml`
    - Prepend the same `prototype-revision-analyzer` step 0 with `produces_solution_plan: true`
    - Renumber existing steps — no other step fields may change
    - Verify `deliverable.revises_existing: true` remains intact
    - _Requirements: 2.2, 2.4, 2.5, 2.6, 5.2, 5.4, 6.1_

  - [x] 4.3 Update `backend/agents/workflows/prototype_feature_revision/workflow.yaml`
    - Prepend the same `prototype-revision-analyzer` step 0 with `produces_solution_plan: true`
    - Renumber existing steps — no other step fields may change
    - Verify `deliverable.revises_existing: true` remains intact
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 5.3, 5.4, 6.1_

  - [ ]* 4.4 Write YAML smoke tests in `tests/unit/test_revision_manifest_shapes.py`
    - Parse each of the three workflow YAMLs (or their compiled `Step` objects) and assert:
      - `steps[0].agent == "prototype-revision-analyzer"` in all three
      - `steps[0].strategy == "single_shot"` in all three
      - `steps[0].gates == []` in all three
      - `steps[0].produces_solution_plan is True` in all three
      - `deliverable.revises_existing is True` in all three
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 5.4, 6.1_

- [x] 5. Refactor `run_commands.py` — remove `run_analyzer` calls from `create_revision`
  - [x] 5.1 Replace the `run_analyzer` block in `create_revision` with a `_classify_revision_tier` call
    - Remove the `from app.agents.revision_analyzer import run_analyzer` import and the `await run_analyzer(...)` call
    - Remove the pre-generated `child_run_id_pre` / `cancel_event_pre` / `event_queue_pre` allocation that existed only for `run_analyzer` events
    - Add `tier = await _classify_revision_tier(body.instruction, run_id, model_id=...)` and `effective_target = _REVISION_TIER_TARGET_MAP.get(tier, "prototype_output")`
    - Add the INFO log line per the design
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 3.1, 3.2_

  - [x] 5.2 Update the `_mint_revision_row` call in `create_revision` to pass `extra_agent_count=0`
    - Change the existing conditional `extra_agent_count` (was `1` for prototype) to `0` unconditionally
    - _Requirements: 3.4_

  - [x] 5.3 Remove the `analyzer_solution` kwarg from the `_drive_revision_to_queue` call in `create_revision`
    - Drop the `analyzer_solution=analyzer_solution` keyword argument from `asyncio.create_task(_drive_revision_to_queue(...))`
    - _Requirements: 3.5_

- [x] 6. Refactor `run_commands.py` — remove `run_analyzer` from `_dispose_concierge_proposal`
  - [x] 6.1 Replace the `run_analyzer` block in `_dispose_concierge_proposal` with a `_classify_revision_tier` call
    - Remove the `run_analyzer` import and invocation from the `channel == "revision"` branch
    - Remove the `_child_run_id_pre` pre-generation pattern (was needed only for `run_analyzer` queue events)
    - Add `_tier = await _classify_revision_tier(instruction, run_id, model_id=...)` and update `target` via `_REVISION_TIER_TARGET_MAP`
    - Add the INFO log line per the design
    - _Requirements: 1.1, 3.1, 3.3_

  - [x] 6.2 Update the `_mint_revision_row` call in `_dispose_concierge_proposal` to pass `extra_agent_count=0`
    - Change the conditional `extra_agent_count` (was `1` for prototype_output) to `0` unconditionally
    - _Requirements: 3.4_

  - [x] 6.3 Remove the `analyzer_solution` kwarg from the `_drive_revision_to_queue` call in `_dispose_concierge_proposal`
    - _Requirements: 3.5_

- [x] 7. Refactor `_drive_revision_to_queue` — remove `analyzer_solution` parameter and `_ectx_register_with_solution` wrapper
  - [x] 7.1 Remove the `analyzer_solution: str = ""` parameter from `_drive_revision_to_queue`
    - Update the function signature
    - Remove the `_ectx_register_with_solution` wrapper block
    - Revert `live_ectx_register` to pass `register_live_ectx` directly (plain, no wrapper)
    - _Requirements: 3.5_

  - [ ]* 7.2 Write property tests for tier routing (Properties 1 and 2)
    - **Property 1: Tier routing is a pure function of the tier string**
    - **Validates: Requirements 1.1, 1.3, 1.4, 1.5**
    - In `tests/unit/test_tier_routing.py`: use `@given(tier=st.sampled_from(sorted({"small", "large", "feature"})))` — for any valid tier, `TIER_MAP[tier]` SHALL equal `_REVISION_TIER_TARGET_MAP[tier]`
    - **Property 2: Unknown tier falls back to `large`**
    - **Validates: Requirements 1.6, 7.4**
    - Use `@given(tier=st.text().filter(lambda s: s not in {"small", "large", "feature"}))` — for any unrecognised tier, `TIER_MAP.get(tier, TIER_MAP["large"])` SHALL equal `"prototype_large_output"`

  - [ ]* 7.3 Update `tests/integration/test_revision_analyzer_integration.py`
    - Remove: tests that patch `run_analyzer` and assert it is called from `create_revision`
    - Add: tests that patch `_classify_revision_tier` and assert:
      - `run_analyzer` is NOT called
      - `extra_agent_count=0` is passed to `_mint_revision_row`
      - `analyzer_solution` kwarg is absent from `_drive_revision_to_queue`
      - For tier `"small"`, `effective_target == "prototype_output"`
      - For tier `"large"`, `effective_target == "prototype_large_output"`
      - For tier `"feature"`, `effective_target == "prototype_feature_output"`
    - _Requirements: 1.3, 1.4, 1.5, 3.1, 3.2, 3.4, 3.5_

  - [ ]* 7.4 Update `tests/unit/test_concierge_proposal_channels.py`
    - Remove: patches of `run_analyzer` in the `revision` channel test
    - Add: patches of `_classify_revision_tier` verifying tier-to-target mapping and that `run_analyzer` is never called
    - _Requirements: 1.1, 3.1, 3.3_

- [x] 8. Deprecate `run_analyzer` in `revision_analyzer.py`
  - [x] 8.1 Mark `run_analyzer` as deprecated in `backend/app/agents/revision_analyzer.py`
    - Add a `# DEPRECATED (revision-pipeline-refactor):` comment block above the function explaining it is dead code and that `parse_analyzer_output` is now called directly by the engine
    - Do NOT delete the file or the function — `parse_analyzer_output` is still imported by the engine hook
    - _Requirements: 3.1, 4.5, 6.2_

  - [ ]* 8.2 Write property test for Property 3 — `parse_analyzer_output` round-trip
    - **Property 3: `parse_analyzer_output` round-trip preserves solution plan**
    - **Validates: Requirements 4.1, 4.5**
    - In `tests/unit/test_parse_analyzer_output.py`: use `@given(solution_body=st.text(min_size=1))` — construct `"## Tier\nsmall\n\n## Solution Plan\n" + solution_body`, call `parse_analyzer_output(doc)`, and assert the returned second element equals `solution_body` verbatim
    - Note: this test will be superseded/replaced by task 9.4 once `parse_analyzer_output` is simplified to return `str` — callers of `parse_analyzer_output` (including the engine hook task 2.1/9.2 and this test) must be updated for the simplified return type

- [x] 9. Simplify `parse_analyzer_output` and update the AGENT.md prompt
  - [x] 9.1 Simplify `parse_analyzer_output` in `backend/app/agents/revision_analyzer.py`
    - Remove tier parsing logic: delete `_VALID_TIERS`, `_DEFAULT_TIER`, `## Tier` section extraction, and all associated WARNING branches for unrecognised tiers
    - Change the function signature from `def parse_analyzer_output(raw: str) -> tuple[str, str]` to `def parse_analyzer_output(raw: str) -> str`
    - The function body should: call `_split_h2_sections(raw)`, call `_find_section(sections, "Solution Plan")`, return the body string if found, return `""` and log a WARNING if not found
    - Keep `_split_h2_sections` and `_find_section` helper functions — they are still needed
    - _Requirements: 9.3, 9.4, 9.6_

  - [x] 9.2 Update the engine hook in `backend/agents/execution_engine/engine.py` to match the simplified `parse_analyzer_output` signature
    - Change `_tier, _solution = parse_analyzer_output(_raw)` to `ectx.analyzer_solution = parse_analyzer_output(_raw)`
    - Remove the now-unused `_tier` variable and the `logger.debug` tier field
    - Update the debug log to: `logger.debug("produces_solution_plan hook: solution_len=%d (run=%s)", len(ectx.analyzer_solution), ectx.run_id)`
    - _Requirements: 9.5_

  - [x] 9.3 Update `backend/agents/prompts/prototype-revision-analyzer/AGENT.md` to remove tier classification
    - Remove Step 2 (the "Reason step-by-step" tier analysis questions: scope, affected components, new pages/routes, coordination)
    - Remove Step 3 (the "Select the tier" section and the full decision table with `small | large | feature` criteria, positive/negative examples, highest-tier-wins rule, uniform multi-element exception)
    - Remove the `## Tier` output section from the output contract at the bottom of the file
    - Remove all `## Tier` lines from the example outputs (keep the `## Solution Plan` examples, just strip the preceding `## Tier\n[value]\n\n` block)
    - Renumber Step 4 ("Write the solution plan") to Step 2
    - Update the output contract to show only `## Solution Plan` with no `## Tier` section
    - Keep Step 1 ("Read the context"), the solution plan instructions, and the solution plan examples unchanged
    - _Requirements: 9.1, 9.2_

  - [ ]* 9.4 Write property test for Property 3 (updated) — `parse_analyzer_output` round-trip with simplified signature
    - **Property 3: `parse_analyzer_output` round-trip preserves solution plan (simplified)**
    - **Validates: Requirements 4.1, 4.5, 9.3, 9.4**
    - In `tests/unit/test_parse_analyzer_output.py`: use `@given(solution_body=st.text(min_size=1))` — construct `"## Solution Plan\n" + solution_body`, call `parse_analyzer_output(doc)`, and assert the returned string equals `solution_body` verbatim
    - Replace (or update) the existing Property 3 test that used `"## Tier\nsmall\n\n## Solution Plan\n" + solution_body` and unpacked a tuple — it must now use the simplified format and return type
    - Add edge case: assert `parse_analyzer_output("")` returns `""` and does not raise
    - Add edge case: assert `parse_analyzer_output("## Solution Plan\n")` returns `""` (empty body, only the heading)

- [x] 9. Checkpoint — app-layer and deprecation changes
  - Ensure `ruff check` passes on `run_commands.py` and `revision_analyzer.py`
  - Ensure `pyright` passes on modified files
  - Ensure `lint-imports` boundaries remain green
  - Ask the user if any questions arise before proceeding to golden regeneration

- [x] 10. Regenerate the three revision pipeline characterization goldens
  - [x] 10.1 Regenerate `prototype_revision` characterization golden with `SNAPSHOT_UPDATE=1`
    - Run `SNAPSHOT_UPDATE=1 pytest tests/agents/test_characterization_prototype_revision.py` (or equivalent)
    - Verify the new golden includes `agent_start` / `agent_complete` events for `prototype-revision-analyzer` as step 0
    - Verify `=== REVISION ANALYSIS ===` appears in the context of the second step (first downstream agent)
    - _Requirements: 2.1, 2.4, 4.2, 5.1_

  - [x] 10.2 Regenerate `prototype_large_revision` characterization golden with `SNAPSHOT_UPDATE=1`
    - Same verification: `prototype-revision-analyzer` events at step 0, `=== REVISION ANALYSIS ===` in step-1 context
    - _Requirements: 2.2, 2.4, 4.2, 5.2_

  - [x] 10.3 Regenerate `prototype_feature_revision` characterization golden with `SNAPSHOT_UPDATE=1`
    - Same verification: `prototype-revision-analyzer` events at step 0, `=== REVISION ANALYSIS ===` in step-1 context
    - _Requirements: 2.3, 2.4, 4.2, 5.3_

  - [ ]* 10.4 Run the full INV-3 golden suite to confirm the 5 non-revision golden files are byte/event-identical
    - Run `pytest tests/agents/test_characterization_*.py` with `SNAPSHOT_UPDATE` unset
    - `git status --porcelain tests/agents/characterization/golden/` must show only the three revision files changed — no other golden diffs
    - _Requirements: 8.1_ (INV-3 compliance)

- [x] 11. Final checkpoint — full suite and invariant verification
  - Run `pytest` for all modified and new test files; all must pass
  - Run `pytest tests/agents/test_characterization_*.py` (SNAPSHOT_UPDATE unset) — 5 non-revision goldens must be byte/event-identical
  - Run `python -m pytest tests/ -k "banned_patterns"` — all 11 SC-001 / INV-1 banned-pattern tests must pass
  - Confirm `grep -rn "if pipeline_type ==" backend/agents/execution_engine/` returns 0 matches
  - Confirm `grep -rn 'spec\.id ==' backend/agents/execution_engine/` returns 0 matches
  - Ask the user if any questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- The implementation order is intentional: data model and compiler changes (task 1) come first so the engine hook (task 2) can reference the new `Step` field; YAML changes (task 4) come after both so the compiler can validate the new key; app-layer changes (tasks 5–7) are independent of each other and can run in parallel; golden regeneration (task 10) must come last
- All property tests use `hypothesis` (`@given` / `@settings`) per the design's Testing Strategy section
- SC-001 / INV-1 compliance is a hard constraint on every task that touches `engine.py`: the engine must never branch on an agent id or pipeline name
- INV-3 compliance is a hard constraint on tasks 1 and 2: `produces_solution_plan` defaults to `False`, leaving all existing (non-revision) steps byte/event-identical
- `parse_analyzer_output` in `revision_analyzer.py` is a pure function already in production — reuse it; do not duplicate its logic
- The `_ectx_register_with_solution` wrapper removal (task 7.1) is a pure dead-code deletion with no functional change to `ExecutionContext`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "4.1", "4.2", "4.3"] },
    { "id": 4, "tasks": ["4.4", "5.1", "6.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "6.2", "6.3"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3", "7.4", "8.1"] },
    { "id": 8, "tasks": ["8.2"] },
    { "id": 9, "tasks": ["9.1", "9.3"] },
    { "id": 10, "tasks": ["9.2", "9.4"] },
    { "id": 11, "tasks": ["10.1", "10.2", "10.3"] },
    { "id": 12, "tasks": ["10.4"] }
  ]
}
```
