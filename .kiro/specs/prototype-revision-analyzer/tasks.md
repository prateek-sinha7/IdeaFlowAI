# Implementation Plan: Prototype Revision Analyzer

## Overview

Introduces a `prototype-revision-analyzer` agent that runs before tier classification on every prototype revision request. The analyzer reads the full Previous_HTML and Revision_Instruction, produces a structured tier rating and Solution_Plan, stores the solution on `ExecutionContext.analyzer_solution`, and injects it into every downstream revision agent via a new `=== REVISION ANALYSIS ===` seam at position 5 of `_compose_context_message`. All changes are app-layer-only except for the single additive field in `context.py` and the single additive seam in `engine.py` (SC-001 compliant).

---

## Tasks

- [x] 1. Foundation — data model field and agent definition files

  - [x] 1.1 Add `analyzer_solution` field to `ExecutionContext`
    - File: `backend/agents/execution_engine/context.py`
    - In the **Prototype-revision group**, add the new field after `revision_baseline_console`:
      ```python
      # analyzer_solution: the Revision_Analyzer's pre-analyzed implementation
      # blueprint. Published before the first agent step by create_revision /
      # _dispose_concierge_revision so _compose_context_message can inject the
      # === REVISION ANALYSIS === block at position 5 (after === USER GUIDANCE ===).
      # Default "" → DORMANT on every non-analyzer run → INV-3 byte-parity holds.
      # Additive field (same D-03 idiom as redo_directive / steering_notes).
      analyzer_solution: str = ""
      ```
    - Do NOT add it to `_VOLATILE_STRIP_KEYS` — it is stable, run-specific content (Requirement 7.5).
    - _Requirements: 7.4, 10.4_

  - [x] 1.2 Create `prototype-revision-analyzer` AGENT.md
    - File: `backend/agents/prompts/prototype-revision-analyzer/AGENT.md` (**CREATE**)
    - Frontmatter must include exactly: `id: prototype-revision-analyzer`, `name: Prototype Revision Analyzer`, `role: analyzer`, `pipeline_type: prototype_revision`, `order: 1`, `max_tokens: 4096`, `tools: []`, `produces: [prototype-revision-analyzer]`, `guardrails: [html-prototype, accessibility]`, `icon: 🔍`, `consumes: []`, `context_from: []`
    - System prompt body must:
      - Instruct the agent to read the Revision_Instruction and Previous_HTML from context
      - Reason step-by-step about scope, affected components, and whether new pages/routes are introduced
      - Define all three tier boundaries with at least one concrete positive example AND one negative example per tier (`small`, `large`, `feature`)
      - State the highest-tier-wins rule for mixed-scope instructions
      - Require output to be ONLY the two-H2-section Markdown block: `## Tier` (one word) + `## Solution Plan` (detailed, naming element IDs, routes, functions, CSS classes)
    - _Requirements: 1.1, 1.2, 1.4, 8.1–8.7_

  - [x] 1.3 Shift `prototype-revision-agent` order and add REVISION ANALYSIS instruction
    - File: `backend/agents/prompts/prototype-revision-agent/AGENT.md` (**EDIT**)
    - Change frontmatter: `order: 1` → `order: 2`
    - Add at the top of the system prompt body (before "You are a senior frontend engineer…"):
      ```
      > **When an `=== REVISION ANALYSIS ===` block is present in your context, follow its
      > guidance precisely. It contains a pre-analyzed implementation blueprint that takes
      > precedence over your own interpretation of the raw user instruction. Read the
      > Solution Plan, then implement it exactly as described.**
      ```
    - _Requirements: 1.1, 4.2_

  - [x] 1.4 Add REVISION ANALYSIS instruction to `prototype-revision-planner` AGENT.md
    - File: `backend/agents/prompts/prototype-revision-planner/AGENT.md` (**EDIT**)
    - Add before the `## ABSOLUTE OUTPUT CONTRACT` section:
      ```
      > **When an `=== REVISION ANALYSIS ===` block is present in your context, use the
      > Solution Plan as the primary input for your task decomposition. The Solution Plan
      > names the specific components, element IDs, functions, and routes that need to
      > change — your task list should map directly onto those named components.**
      ```
    - _Requirements: 5.1_

  - [x] 1.5 Add REVISION ANALYSIS instruction to `prototype-revision-feature-specify` AGENT.md
    - File: `backend/agents/prompts/prototype-revision-feature-specify/AGENT.md` (**EDIT**)
    - Add before "You are a product designer…":
      ```
      > **When an `=== REVISION ANALYSIS ===` block is present in your context, ground
      > your feature specification in the Solution Plan. The plan identifies the new
      > pages, routes, and capabilities the Analyzer determined are needed — reference
      > them explicitly in your spec sections.**
      ```
    - _Requirements: 6.1_

- [x] 2. Core logic — pure parser and async orchestrator

  - [x] 2.1 Create `backend/app/agents/revision_analyzer.py` with `parse_analyzer_output`
    - File: `backend/app/agents/revision_analyzer.py` (**CREATE**)
    - Implement `parse_analyzer_output(raw: str) -> tuple[str, str]` as a **pure function** (no I/O, no LLM calls):
      1. Split `raw` into H2-delimited sections by scanning lines matching `^## `.
      2. Find the section whose header is `Tier` (case-insensitive trim).
      3. In the tier section body, find the first non-blank line; `.strip().lower()` it.
      4. Validate: if result not in `{"small", "large", "feature"}`, log WARNING including `raw[:500]`, set `tier = "large"`.
      5. Find section whose header is `Solution Plan` (case-insensitive trim); capture full body string preserving interior whitespace.
      6. If `## Solution Plan` section is absent, log WARNING, set `solution = ""`.
      7. Return `(tier, solution)`.
    - Cover all error cases from the design's error table: absent tier section, unrecognized tier value, absent solution section, both absent.
    - The module docstring must note it is the single source for `parse_analyzer_output` and `run_analyzer`.
    - _Requirements: 2.1–2.6, 10.1_

  - [ ]* 2.2 Write property tests for `parse_analyzer_output` (Properties 1–5)
    - File: `backend/tests/unit/test_revision_analyzer.py` (**CREATE** — start with PBT section)
    - Use `hypothesis` with `@given` / `@settings(max_examples=200)`.
    - **Property 1** — tier always in valid set: `@given(st.text())` → `assert tier in {"small", "large", "feature"}`
    - **Property 2** — round-trip for well-formed output: construct `"## Tier\n{tier}\n\n## Solution Plan\n{s}"` from valid tiers + non-empty text; assert parsed tier equals `tier.lower()` and parsed solution matches `s.strip()`.
    - **Property 3** — case normalization: `@given(st.sampled_from(["SMALL", "Large", "FEATURE", ...]))` under `## Tier`; assert lowercase canonical form returned.
    - **Property 4** — invalid tier defaults to `"large"`: `@given(st.text().filter(lambda t: t.strip().lower() not in {"small", "large", "feature"}))` → assert `tier == "large"`.
    - **Property 5** — solution extraction is faithful: well-formed output with arbitrary non-empty solution body → assert solution component matches body (modulo section-end trimming).
    - Tag each test: `# Feature: prototype-revision-analyzer, Property N: <text>`
    - _Requirements: 2.1–2.5_

  - [x] 2.3 Implement `run_analyzer` async orchestrator in `revision_analyzer.py`
    - File: `backend/app/agents/revision_analyzer.py` (**EDIT** — add to existing module)
    - Signature: `async def run_analyzer(instruction: str, existing_html: str, event_queue: asyncio.Queue, parent_run_id: str, model_id: str | None = None) -> tuple[str, str]`
    - Implementation steps:
      1. Build the analyzer prompt (exact structure from design: `=== REVISION INSTRUCTION ===` + `=== CURRENT PROTOTYPE HTML ===` + output-only Markdown contract). Pass **full** `existing_html` without truncation (Requirement 8.7).
      2. `await event_queue.put({"type": "agent_start", "data": {"agent_id": "prototype-revision-analyzer", "name": "Prototype Revision Analyzer", "role": "analyzer", "icon": "🔍", "index": 1, "total": ...}})` — keys must match `_REQUIRED_DATA_KEYS["agent_start"]`.
      3. `llm = build_model(model_id, max_tokens=4096)` using same `build_model` import as `_classify_revision_tier`.
      4. `response = await llm.ainvoke([HumanMessage(content=prompt)])`.
      5. `tier, solution = parse_analyzer_output(response.content)`.
      6. `await event_queue.put({"type": "agent_complete", "data": {...}})` — include `agent_id`, `name`, `duration`, `output_length`, `input_tokens`, `output_tokens`, `total_tokens`.
      7. `await event_queue.put({"type": "revision_analyzer_complete", "data": {"tier": tier, "solution_preview": solution[:200]}})`.
      8. Return `(tier, solution)`.
    - Exception handling (exact fallback chain from design):
      ```python
      except Exception as exc:
          logger.error("run_analyzer failed (%s) — falling back to _classify_revision_tier", exc, exc_info=True)
          try:
              tier = await _classify_revision_tier(instruction, parent_run_id, model_id)
              return (tier, "")
          except Exception as exc2:
              logger.error("_classify_revision_tier fallback also failed (%s) — defaulting to large", exc2)
              return ("large", "")
      ```
    - Import `_classify_revision_tier` from `app.api.run_commands` for the fallback (lazy import inside the except block avoids circular import if needed).
    - _Requirements: 3.1, 3.4, 3.5, 3.6, 7.2_

  - [ ]* 2.4 Write unit tests for `run_analyzer` with mocked LLM
    - File: `backend/tests/unit/test_revision_analyzer.py` (**EDIT** — add unit test class)
    - Mock `build_model` and `asyncio.Queue`; test:
      - Happy path: valid tier + solution returned; all 3 events placed on queue in order (agent_start, agent_complete, revision_analyzer_complete).
      - Fallback path: LLM raises → `_classify_revision_tier` mock called; `("mocked_tier", "")` returned.
      - Double-failure path: LLM raises AND `_classify_revision_tier` raises → `("large", "")` returned.
      - `revision_analyzer_complete` payload: `data.tier` matches parsed tier, `data.solution_preview` == `solution[:200]`.
    - _Requirements: 3.1, 3.4–3.6, 7.2_

- [x] 3. Engine seam — `_compose_context_message` position-5 injection

  - [x] 3.1 Add `analyzer_solution` injection block at position 5 in `_compose_context_message`
    - File: `backend/agents/execution_engine/engine.py` (**EDIT** — ONE engine edit allowed)
    - Location: immediately after the `=== USER GUIDANCE ===` block (after `ectx.steering_notes` consume-once drain, before the `if ectx.build_task_number:` block).
    - Add the following block (no pipeline-type guard, no agent-id check — generic field truthiness only, SC-001 / INV-1 compliant):
      ```python
      # ── Position 5 — Revision Analysis (additive seam, INV-1 / SC-001 compliant) ──
      # Appended IFF ectx.analyzer_solution is non-empty. Generic truthiness check on
      # a dataclass field — no pipeline_type branch, no agent_id literal (SC-001).
      # Default "" → DORMANT on every non-analyzer run → INV-3 byte-parity holds.
      _analyzer_solution = getattr(ectx, "analyzer_solution", "") or ""
      if _analyzer_solution:
          parts.append(
              f"\n=== REVISION ANALYSIS ===\n{_analyzer_solution}\n"
              "=== END REVISION ANALYSIS ==="
          )
      ```
    - Verify: `grep -rn "prototype.revision.analyzer\|prototype_revision\|prototype_large\|prototype_feature" agents/execution_engine/` must return 0 matches after this edit.
    - _Requirements: 4.1, 4.4, 10.3, 10.5_

  - [ ]* 3.2 Write property tests for `_compose_context_message` injection (Properties 9 & 10)
    - File: `backend/tests/unit/test_revision_analyzer.py` (**EDIT** — add PBT section)
    - **Property 9** — non-empty `analyzer_solution` causes injection: `@given(st.text(min_size=1))` → set `ectx.analyzer_solution = solution`; call `_compose_context_message(ectx)`; assert `"=== REVISION ANALYSIS ==="` in result.
    - **Property 10** — empty `analyzer_solution` suppresses block: `ectx.analyzer_solution = ""`; assert `"=== REVISION ANALYSIS ==="` NOT in result.
    - Use a minimal `ExecutionContext(run_id="test", owner_id="u1")` for both tests.
    - Tag: `# Feature: prototype-revision-analyzer, Property 9+10: REVISION ANALYSIS block injection`
    - _Requirements: 4.1, 4.3, 10.3, 10.4_

- [x] 4. Integration — `create_revision` endpoint and Concierge path

  - [x] 4.1 Replace `_classify_revision_tier` with `run_analyzer` in `create_revision`
    - File: `backend/app/api/run_commands.py` (**EDIT**)
    - Locate the `create_revision` function; find the block `if body.target_artifact_type == "prototype_output":` that calls `_classify_revision_tier`.
    - Replace the `_classify_revision_tier` call with:
      ```python
      from app.agents.revision_analyzer import run_analyzer
      tier, analyzer_solution = await run_analyzer(
          instruction=body.instruction,
          existing_html=existing_html,
          event_queue=event_queue,
          parent_run_id=run_id,
          model_id=getattr(current_user, "preferred_model", None),
      )
      effective_target = _REVISION_TIER_TARGET_MAP.get(tier, "prototype_output")
      ```
    - Update `_mint_revision_row` call to pass `agent_count=len(_rev_agents) + 1` (the `+1` accounts for the pre-mint Analyzer step — Requirement 9.6). This applies **only** when the `prototype_output` analyzer path is active; refactor `_mint_revision_row` call or add a local variable as needed.
    - After `_mint_revision_row`, add atomic context-storage block:
      ```python
      try:
          ectx = _get_or_create_ectx(child_run_id)
          ectx.analyzer_solution = analyzer_solution
      except Exception as exc:
          logger.error("Failed to store analyzer_solution for run=%s: %s", child_run_id, exc)
          _abort_revision_run(child_run_id, exc)
          raise HTTPException(status_code=500, detail="Revision analyzer context storage failed")
      ```
    - The `revision_analyzer_complete` event was already emitted onto `event_queue` by `run_analyzer`; it rides the standard `ScopedStore.append_event` stamping path (seq/event_id) — no additional emit call needed here.
    - _Requirements: 3.1–3.8, 7.1, 7.2, 7.6, 9.6_

  - [x] 4.2 Update Concierge path (`CHANNEL_REVISION` in `post_message`) to use `run_analyzer`
    - File: `backend/app/api/run_commands.py` (**EDIT**)
    - Locate the `CHANNEL_REVISION` dispatch block inside `post_message` (around line 1427) where `_classify_revision_tier` is called with `target == "prototype_output"`.
    - Replace the `_classify_revision_tier` call with `run_analyzer` using the same interface:
      ```python
      from app.agents.revision_analyzer import run_analyzer
      _tier, _analyzer_solution = await run_analyzer(
          instruction=instruction,
          existing_html=existing_html,
          event_queue=event_queue,
          parent_run_id=run_id,
          model_id=getattr(current_user, "preferred_model", None),
      )
      target = _REVISION_TIER_TARGET_MAP.get(_tier, "prototype_output")
      ```
    - After `_mint_revision_row` in this path, add the same atomic context-storage block as in task 4.1.
    - Source `existing_html` from the parent run's `output` column — identical to the existing Concierge-path HTML extraction already in this block.
    - _Requirements: 3.1, 9.4_

- [x] 5. Event vocabulary — characterization test guard

  - [x] 5.1 Add `revision_analyzer_complete` to `_DOCUMENTED_EVENT_TYPES`
    - File: `backend/tests/agents/test_phase3_cutover_verify.py` (**EDIT**)
    - Locate `_DOCUMENTED_EVENT_TYPES = frozenset(...)`.
    - Add to the set:
      ```python
      # ── Revision Analyzer events (prototype-revision-analyzer feature) ───────
      # revision_analyzer_complete — emitted by run_analyzer after the analyzer
      # agent returns, with payload {tier, solution_preview}. Added to the
      # vocabulary so the INV-3 golden suite recognises it without re-baselining
      # the 5 existing characterization goldens (which never trigger the analyzer).
      "revision_analyzer_complete",
      ```
    - Verify: the 5 golden characterization snapshot files under `tests/agents/characterization/golden/` must remain byte-identical (`git status --porcelain tests/agents/characterization/golden/` → empty output) after all changes.
    - _Requirements: 7.3, 9.3, 9.7_

- [x] 6. Unit + PBT tests (complete test file)

  - [x] 6.1 Complete `test_revision_analyzer.py` with concrete unit tests
    - File: `backend/tests/unit/test_revision_analyzer.py` (**EDIT** — add/consolidate concrete examples)
    - Concrete `parse_analyzer_output` examples:
      - Well-formed: both sections present with valid tier → returns exact `(tier, solution)`.
      - `## Tier` section absent → `("large", <solution or "">)` + WARNING logged.
      - Tier value `"unknown_tier"` → `("large", ...)` + WARNING with `raw[:500]`.
      - `## Solution Plan` absent → `(tier, "")` + WARNING logged.
      - Both sections absent → `("large", "")` + WARNING logged.
      - Empty raw string → `("large", "")`.
      - Tier value `"SMALL"` → `"small"` (case normalization).
    - AGENT.md smoke test:
      - Load `backend/agents/prompts/prototype-revision-analyzer/AGENT.md` and parse the YAML frontmatter block.
      - Assert `id == "prototype-revision-analyzer"`, `order == 1`, `pipeline_type == "prototype_revision"`, `max_tokens == 4096`, `tools == []`.
    - `prototype-revision-agent` order smoke test:
      - Load its AGENT.md; assert `order == 2`.
    - _Requirements: 1.1–1.5, 2.1–2.6_

  - [ ]* 6.2 Write remaining property tests (Properties 6 & 8)
    - File: `backend/tests/unit/test_revision_analyzer.py` (**EDIT**)
    - **Property 6** — tier drives pipeline selection: `@given(st.sampled_from(["small", "large", "feature"]))` → mock `run_analyzer` to return `(tier, "")` → assert `_REVISION_TIER_TARGET_MAP[tier]` matches `effective_target` computed in the endpoint code path (test via direct dict lookup).
    - **Property 8** — `revision_analyzer_complete` payload matches analyzer output: `@given(st.sampled_from(["small","large","feature"]), st.text(min_size=0, max_size=500))` → call `parse_analyzer_output` on constructed raw → assert event payload `data.tier == tier` and `data.solution_preview == solution[:200]`.
    - Tag: `# Feature: prototype-revision-analyzer, Property 6/8: <text>`
    - _Requirements: 2.4, 3.2, 7.2_

- [x] 7. Integration tests

  - [x] 7.1 Create `test_revision_analyzer_integration.py`
    - File: `backend/tests/integration/test_revision_analyzer_integration.py` (**CREATE**)
    - Test `create_revision` endpoint with mocked `run_analyzer`:
      - Assert `agent_start` event for `prototype-revision-analyzer` is emitted before any pipeline agent event.
      - Assert `agent_complete` event for `prototype-revision-analyzer` is emitted before first pipeline `agent_start`.
      - Assert `revision_analyzer_complete` event appears with `data.tier` and `data.solution_preview` keys.
      - Assert `ectx.analyzer_solution` is set before the first pipeline agent step executes.
      - Assert `agent_count == len(_rev_agents) + 1` on the minted `WorkflowRun` row.
    - Test Concierge path (mock `run_analyzer` and `_mint_revision_row`):
      - Assert `run_analyzer` is called with `instruction` from the chat message and `existing_html` from the parent run's `output` column.
    - Test fallback: mock `run_analyzer` to raise → assert `_classify_revision_tier` mock is called instead (run does not abort).
    - Test double-failure: mock both `run_analyzer` and `_classify_revision_tier` to raise → assert run proceeds with tier `"large"` and empty solution.
    - Test `ectx.analyzer_solution` storage failure: mock `_get_or_create_ectx` to raise → assert endpoint returns HTTP 500.
    - _Requirements: 3.1–3.7, 4.1, 5.1, 6.1, 7.1, 7.6, 9.4_

- [x] 8. CI / validation — SC-001 grep checks

  - [x] 8.1 Verify SC-001 kernel name-free checklist passes
    - After all edits are committed to the working tree, run the following grep commands and assert each returns **0 matches**:
      1. `grep -rn "prototype.revision.analyzer\|RevisionAnalyzer" backend/agents/execution_engine/`
      2. `grep -rn "if pipeline_type ==" backend/agents/execution_engine/`
      3. `grep -rn "spec\.id ==" backend/agents/execution_engine/`
      4. `grep -rn "prototype_revision\|prototype_large\|prototype_feature" backend/agents/execution_engine/`
    - If any command returns matches, identify the source file and line, then refactor until all four commands are clean.
    - _Requirements: 10.1, 10.2, 10.5, 9.7_

  - [x] 8.2 Verify banned-pattern CI ratchets pass
    - Run `pytest backend/tests/agents/test_banned_patterns.py` — all 11 pattern tests must pass.
    - Run `pytest backend/tests/agents/test_sse_cutover_banned_patterns.py` — all 5 pattern tests must pass.
    - Run `pytest backend/tests/agents/test_phase3_cutover_verify.py` — `TestNewEngineEventVocabulary` must pass with `revision_analyzer_complete` in vocabulary.
    - Run `pytest backend/tests/agents/test_characterization_*.py` — all 5 golden snapshot tests must be byte-identical (SNAPSHOT_UPDATE must be unset).
    - Ensure `git status --porcelain backend/tests/agents/characterization/golden/` returns empty output.
    - _Requirements: 9.3, 9.7, 10.2_

  - [x] 8.3 Final checkpoint — ensure all tests pass
    - Run `pytest backend/tests/unit/test_revision_analyzer.py -v` — all unit + PBT tests pass.
    - Run `pytest backend/tests/integration/test_revision_analyzer_integration.py -v` — all integration tests pass.
    - Run `pytest backend/tests/agents/test_characterization_prototype_revision.py` — golden snapshot byte-identical.
    - Ask the user if any questions arise before marking complete.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP implementation.
- Each task references specific requirements for traceability.
- The ONE engine edit (task 3.1) is the only change inside `agents/execution_engine/` — strictly additive and SC-001 / INV-1 compliant (generic field truthiness, no pipeline-type guard).
- `parse_analyzer_output` is a pure function — property-based tests are particularly effective here because any raw string must produce a valid tier.
- The `run_analyzer` fallback chain must be implemented exactly: LLM failure → `_classify_revision_tier` → default `("large", "")`.
- All `event_queue.put` calls in `run_analyzer` must use keys matching `_REQUIRED_DATA_KEYS` in `test_phase3_cutover_verify.py` to pass the vocabulary guard.
- Property tests use `hypothesis` library (already a dev dependency).

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4", "3.1"] },
    { "id": 4, "tasks": ["3.2", "4.1", "4.2", "5.1"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["8.1", "8.2"] },
    { "id": 8, "tasks": ["8.3"] }
  ]
}
```
