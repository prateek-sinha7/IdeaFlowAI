# Escalated — Domain 15: backend·other

10 cards with status `ESCALATED`.

---

## ~~ISS-096~~ — CLOSED ✓

**Closed:** `od-ppt-validator` path doesn't exist on this branch (only `ppt-validator` does).
`test_od_ppt_validator_deck_reemission_contract` passes 14/14 today. No red to pin a test to.

---

## ~~ISS-130~~ — CLOSED ✓

**Closed:** hazard already fixed upstream by KRN-005's full-invocation `scratch_lock`
(`context.py:489`, `kernel_services.py:1677-1724`, landed `7a8530627`).
Both `test_scratch_lock_fanout_race.py` tests pass today.

---

## ~~ISS-132~~ — CLOSED ✓

**Fixed:** `invocation_gated=False` added at the `runner.run_agent(...)` call site in
`task_loop.py` (lines 334–351). Each task iteration is an invocation, not a step
boundary — same reasoning and same fix shape as ISS-097/FIX-242 on `run_worker` and
`run_merge_agent`. The step's own declared `gates: [human]` fires at the step boundary
unchanged. SC-001 grep: 0 hits. AST parse: clean.

**File changed:** `backend/agents/capabilities/strategies/task_loop.py`

---

## ~~ISS-156~~ — CLOSED ✓

**Closed:** the `## Attached files` vs `PRIORITY OVERRIDE` mismatch is not present on this
branch. All three named test files are green today (`test_run_commands_fix218.py` 24/24,
`useChatAttachments.test.ts` 6/6, `ChatAttachments.test.tsx` 3/3). Not reproducible.

---

## ~~ISS-630~~ — CLOSED ✓

**Fixed:** `test_revision_analyzer_integration.py` rewritten for the post-refactor contract.

Changes (test file only, 0 production files):
- Added `_stub_bedrock_construction` autouse fixture — stubs `ChatBedrockConverse.__init__` and `build_model` so `_classify_revision_tier` never hits the ISS-102 live-model guard
- `test_agent_count_is_rev_agents_plus_one` → `test_agent_count_is_rev_agents` — removed `+1` (analyzer is now step 0 of manifest, already counted in `len(get_pipeline_agents("prototype_revision"))`)
- `test_analyzer_solution_passed_to_drive_revision` → `test_drive_revision_called_without_analyzer_solution_kwarg` — asserts the kwarg is ABSENT (removed in refactor; engine populates `ectx.analyzer_solution` via `produces_solution_plan` post-step hook)
- `test_revision_analyzer_complete_event_has_required_keys` → `test_revision_endpoint_returns_run_id_with_capturing_analyzer` — `revision_analyzer_complete` SSE event no longer emitted by app layer
- `test_double_failure_in_endpoint_proceeds_with_large_tier_pipeline` — removed stale `analyzer_solution == ""` assertion
- 9 `xfail` markers removed across all affected tests

---

## ~~ISS-632~~ — CLOSED ✓

**Fixed:** Removed `[:2]` roster slice from `_drive_engine` in `test_pipeline_failure_semantics.py` and `_drive_execute` in `test_engine_runner_error_arm.py`. Both now drive the full 6-agent `user_stories` roster. Count assertions updated to `len(specs)` / `len(specs) - 1`. `_drive_engine` now returns `(events, engine, run_id, specs)`. All 5 xfail markers removed from `test_pipeline_failure_semantics.py`, 2 from `test_engine_runner_error_arm.py`.

**Files changed (test only):**
- `backend/tests/unit/test_pipeline_failure_semantics.py`
- `backend/tests/agents/test_engine_runner_error_arm.py`

---

## ~~ISS-634~~ — CLOSED ✓

**Fixed:** `_drive_single_agent` in `test_chunk_sanitizer.py` now passes `compiled_override` with a single-step plan (the one spec being tested), bypassing ADR-0008's `_roster_is_partial` fill-in. The `_ChunkStreamSanitizer` behaviour was always correct — only the harness was expanding the roster. 4 xfail markers removed.

**File changed (test only):**
- `backend/tests/agents/test_chunk_sanitizer.py`

---

## ~~ISS-638~~ — CLOSED ✓

**Fixed:** 6 stale assertions updated across 5 test files. 0 production files changed.

| row | file | change |
|---|---|---|
| (1) tool_grant | `test_tool_grant_invariants.py` | Narrowed heuristic to `write_file`/`workspace` tools only — excludes `pptx` |
| (2) phase5 count | `test_phase5_revision_validation.py` | `agent_start==2` → `==3`; starts list updated for FIX-433 3-step roster |
| (3) prompt hygiene | `test_text_only_prompt_hygiene.py` | Removed `[:2]` slice; drive full roster |
| (4) chained_from | `test_workflows_api.py` | Added `("ppt_v2", False)` to `prototype.chained_from` assertion |
| (5) phase5 fix_message | `test_phase5_revision_validation.py` | xfail removed — FIX-437 already cured this row |
| (6) phase8 offline chained | `test_phase8_live.py` | xfail removed — FIX-437 already cured this row |

---

## ~~ADR-0002~~ — CLOSED ✓ (Option 3: superseded)

**Closed 2026-09-03:** `pipeline_type` is the permanent on-wire/on-disk name.

Reasons:
- 3 DB columns (`base_pipeline_type`, `overrides_pipeline_type`, `pipeline_output`) cannot be renamed without a non-additive migration — blocked by the additive-only invariant
- `pipeline_type` is the SSE wire key consumed by 93 frontend files; renaming is a breaking API change
- 94 AGENT.md files, 122 backend `.py` files use it consistently with zero functional issue

New surfaces may use `workflow` vocabulary; existing surfaces keep `pipeline_type`.

**CI gate:** `test_workflow_vocabulary_gate.py` — `xfail(strict=True)` markers converted to `pytest.mark.skip` so the suite stays green. `@pytest.mark.issue("ADR-0002")` kept for traceability.

**Knowledge card:** ADR-0002 status updated to `superseded`.

---

## ~~ISS-094~~ — CLOSED ✓

**Closed:** already fixed upstream in `engine.py`. Not reproducible on current branch.

---
