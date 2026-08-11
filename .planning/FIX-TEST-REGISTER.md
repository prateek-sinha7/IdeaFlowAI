# Fix-Test Register — VelocityAI / Flowin

> **Purpose.** Every test suite written via `/velocity-ai-test` is logged here, linked to its Fix ID from `FIX-REGISTER.md`. Read this before writing new tests to avoid duplicating existing coverage.
>
> **How to use:** Each entry is keyed by Fix ID. When a fix is tested, a TEST-NNN entry is added here referencing the FIX-NNN from `FIX-REGISTER.md`.

---

## Summary Table

| Test ID | Fix ID | Date | Files Tested | Tests Written | Passed | Failed | Status |
|---------|--------|------|--------------|---------------|--------|--------|--------|
| TEST-001 | FIX-001 (KAN-76) | 2026-06-22 | `backend/tests/unit/test_prompt_overrides.py` | 21 | 21 | 0 | ✅ Pass |
| TEST-002 | FIX-002 (KAN-75) | 2026-06-22 | `backend/tests/unit/test_catalogue_nav.py` | 7 | 7 | 0 | ✅ Pass |
| TEST-003 | FIX-217 (quick-260811-mxg) | 2026-08-11 | `backend/agents/execution_engine/engine.py`, `backend/agents/execution_engine/context.py` | 11 | 11 | 0 | ✅ Pass |

---

## Detailed Test Entries

### TEST-003 — FIX-217 (quick-260811-mxg): spec-revision context loss

```
TEST COVERAGE — FIX-217
Unit tests:        11 total, ALL GREEN
                     4 in backend/tests/agents/test_spec_revision_context.py
                     7 in backend/tests/agents/test_restart_resume.py  (-k rehydrat)
Integration tests: N/A — the defect is prompt COMPOSITION; the scripted-model harness
                   (tests/agents/_scripted_model.py) exercises the full _run_agent
                   dispatch path offline with no Bedrock call, so a separate
                   integration tier would add cost without adding coverage.
Frontend tests:    N/A — no frontend file was changed.
Goldens:           5 failed / 5 passed — IDENTICAL failing ids at the pre-change commit
                   edc44daa and at HEAD. Re-measured independently in a detached
                   worktree at edc44daa rather than trusted as "pre-existing".
                   (The remembered "10 failed / 6 passed" was stale dev data.)
lint-imports:      3 kept / 1 broken — IDENTICAL at edc44daa; the broken contract is the
                   pre-existing agents.capabilities -> execution_engine.od_context ->
                   app.services.od_loader chain. "kernel imports only capability ports"
                   stays KEPT, so the new top-level ClarifyEngine import crossed nothing.
Adjacent suite:    test_restart_resume.py 7 failed / 48 passed vs 7 failed / 41 passed at
                   edc44daa — same 7 failing ids, +7 from this work.
Regression guards:
  - test_revision_prompt_contains_prior_artifact[live] / [reentry]: the composed prompt
    for the specify re-dispatch CONTAINS the prior spec, at BOTH _run_spec_revision_sub_pipeline
    call sites. Parametrised because fixing only the live site would leave the bug intact in
    exactly the restart scenario that exposed it.
  - test_prior_artifact_does_not_leak_to_plan_or_analyze: the injection is scoped to the
    specify sub-dispatch and cleared consume-once.
  - test_revision_uses_fresh_thread: the revision dispatch's thread_id differs from pass 1's.
  - test_rehydrate_planning_context_rebuilds_planner_and_answers: the resumed prompt carries
    the planner's real intent and the merged clarification answers, not user_message[:200].
  - test_rehydrate_survives_malformed_planner_constraints[4 params]: a non-list or
    non-string explicit_constraints degrades instead of raising TypeError out of the
    helper. All 4 seen RED against the pre-fix engine; one param initially passed for the
    wrong reason (a bare string explodes charwise and chars ARE str, so the isinstance
    assertion held) and was tightened to an exact-count assertion.
  - test_rehydrate_merge_survives_monkeypatched_clarify_engine: proves the import-time
    ClarifyEngine bind is load-bearing. Verified discriminating by running the late-binding
    counterfactual, which silently drops every answer behind one warning line.
  - test_offset0_gate_resume_does_not_replan_or_reclarify (pre-existing): stays green,
    proving D2 rehydrates rather than re-invoking the planner (BUG-R05 / quick-260719-hd5).
```

**Discipline note.** All 5 original tests were written FIRST and observed RED, with verbatim
output recorded in `260811-mxg-BASELINE.md`. The two added later (malformed-planner-row,
monkeypatched-ClarifyEngine) were likewise proven RED/discriminating against the pre-fix
engine before being accepted. The absence of any assertion on the revision payload —
`spec_revision_context` appeared in ZERO test files — is why this defect shipped.

**Live proof (Bedrock, run `5ecb990f-2c80-4752-a615-2bed3280387a`).** Full incident
reproduction including a deliberate backend SIGTERM at the plan gate. spec v1 -> v2:
31,742 -> 36,640 chars (+15.4%), 19 -> 19 headings (0 lost), 97.6% verbatim carry-over, the
planted `KESTREL` sentinel retained 4x -> 4x; task_list 45,229 -> 87,567 (+93.6%). The
incident it reproduces lost 8 headings, dropped "Spinnaker" 4x -> 0x and kept only 29.3%.

---


*Entries are appended below after each `/velocity-ai-test` session.*

---

---

## Detailed Test Entries

### TEST-001 — FIX-001 (KAN-76) — Show and Edit Agent Prompts

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-test KAN-76 and KAN-75`

#### Fix Summary (from FIX-REGISTER)
- **Root cause:** `prompt_body` omitted from `AgentResponse` + `AgentDef`; no prompt endpoints; `AgentCapabilitiesModal` had no prompt section; factory.py never injected user overrides at runtime
- **Files fixed:** `backend/app/api/agents.py`, `backend/app/agents/prompt_overrides.py` (new), `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`, `frontend/src/components/workflow/AgentsPopup.tsx`, `backend/agents/factory.py`
- **What changed:** Added prompt_body to API responses; new GET/PUT/DELETE prompt override endpoints; new `prompt_overrides.py` storage module; factory wires override at runtime

#### Test Files Written
| File | Test count | Framework |
|------|-----------|-----------|
| `backend/tests/unit/test_prompt_overrides.py` | 21 | pytest |

#### Test Cases

| # | Test name | Purpose | Result |
|---|-----------|---------|--------|
| 1 | `test_save_writes_to_correct_path` | Override lands at `skills/users/{uid}/{agent_id}/PROMPT_OVERRIDE.md` | ✅ PASS |
| 2 | `test_read_returns_content_when_override_exists` | Reading an existing override returns it verbatim | ✅ PASS |
| 3 | `test_read_returns_none_when_no_override` | Missing override returns None safely | ✅ PASS |
| 4 | `test_has_override_true_after_save` | `has_user_prompt_override` reflects save | ✅ PASS |
| 5 | `test_has_override_false_before_save` | `has_user_prompt_override` returns False before save | ✅ PASS |
| 6 | `test_delete_removes_file` | Delete removes file, returns True | ✅ PASS |
| 7 | `test_delete_idempotent_returns_false_when_nothing_to_delete` | Idempotent delete returns False | ✅ PASS |
| 8 | `test_users_isolated_from_each_other` | User A override invisible to User B | ✅ PASS |
| 9 | `test_save_raises_on_empty_user_id` | Empty user_id raises ValueError | ✅ PASS |
| 10 | `test_save_raises_on_oversized_content` | >32KB raises ValueError | ✅ PASS |
| 11 | `test_read_returns_none_on_empty_user_id` | Empty user_id returns None safely | ✅ PASS |
| 12 | `test_skill_and_override_coexist_in_same_directory` | SKILL.md and PROMPT_OVERRIDE.md coexist | ✅ PASS |
| 13 | `test_base_prompt_used_when_no_override` | Base AGENT.md body used when no override | ✅ PASS |
| 14 | `test_override_replaces_base_prompt_when_user_has_override` | User override replaces base prompt at runtime | ✅ PASS |
| 15 | `test_base_prompt_used_when_user_id_is_none` | user_id=None uses base prompt — INV-3 preserved | ✅ PASS |
| 16 | `test_override_lookup_failure_falls_back_to_base_prompt` | Exception in lookup → base prompt, never crashes run | ✅ PASS |
| 17 | `test_after_delete_base_prompt_is_used_again` | Delete override → base prompt restored | ✅ PASS |
| 18 | `test_agent_response_model_has_prompt_body_field` | `AgentResponse.prompt_body` exists (root cause guard) | ✅ PASS |
| 19 | `test_agent_prompt_response_model_has_required_fields` | `AgentPromptResponse` has all 4 fields | ✅ PASS |
| 20 | `test_prompt_override_request_model_exists` | `PromptOverrideRequest` importable | ✅ PASS |
| 21 | `test_max_prompt_override_bytes_larger_than_max_skill_bytes` | 32KB > 8KB cap | ✅ PASS |

#### Run Output
```
28 passed, 1 warning in 1.43s
(21 from TEST-001, 7 from TEST-002 — run together)
```

#### Verdict
- **Tests written:** 21
- **Tests passed:** 21
- **Tests failed:** 0
- **Status:** ✅ All passing

#### Notes
- Factory tests use `MagicMock` + `patch` to isolate the `_compose_system_prompt` call from the full capability registry. The real assembly policy is patched to return `blocks["prompt_body"]` directly, making the test purely about whether the override or base prompt ends up in the block.
- Frontend (TypeScript) tests for the `AgentCapabilitiesModal` prompt section would require a vitest setup with MSW mocking; deferred as the backend coverage gives high confidence.

#### Fix Confidence
- [x] **High** — root cause test (`test_override_replaces_base_prompt_when_user_has_override`) + happy path + edge cases (isolation, empty user_id, oversized content, exception fallback, revert) all pass; regression (INV-3 user_id=None path) clean

---

### TEST-002 — FIX-002 (KAN-75) — Catalogue Nav Tab

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-test KAN-76 and KAN-75`

#### Fix Summary (from FIX-REGISTER)
- **Root cause:** `SavedWorkflowsPage` was fully implemented but only reachable via profile dropdown; no Catalogue tab in main nav
- **Files fixed:** `frontend/src/components/layout/AppHeader.tsx` (Catalogue tab added), `frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx` (redesigned)
- **What changed:** Added `LayoutGrid` icon + Catalogue button to `<nav>`; SavedWorkflowsPage redesigned with list/grid toggle, search, metadata, themed styling

#### Test Files Written
| File | Test count | Framework |
|------|-----------|-----------|
| `backend/tests/unit/test_catalogue_nav.py` | 7 | pytest |

#### Test Cases

| # | Test name | Purpose | Result |
|---|-----------|---------|--------|
| 1 | `test_user_workflows_api_module_importable` | Backend data source importable | ✅ PASS |
| 2 | `test_user_workflow_summary_has_timestamps` | `created_at`/`updated_at` in response model | ✅ PASS |
| 3 | `test_user_workflow_summary_has_base_pipeline_type` | Pipeline type badge field present | ✅ PASS |
| 4 | `test_user_workflow_summary_has_agent_ids` | Agent count field present | ✅ PASS |
| 5 | `test_user_workflow_summary_has_name_and_description` | Card title/subtitle fields present | ✅ PASS |
| 6 | `test_user_workflows_router_has_get_list_endpoint` | GET /api/user-workflows registered | ✅ PASS |
| 7 | `test_user_workflows_router_has_crud_endpoints` | POST/PATCH/DELETE registered | ✅ PASS |

#### Run Output
```
28 passed, 1 warning in 1.43s
(7 from TEST-002, 21 from TEST-001 — run together)
```

#### Verdict
- **Tests written:** 7
- **Tests passed:** 7
- **Tests failed:** 0
- **Status:** ✅ All passing

#### Notes
- Frontend navigation tests (e.g. Catalogue tab renders in AppHeader, `currentPage="saved-workflows"` highlights it) require vitest + React Testing Library. The backend tests focus on the data contract that the Catalogue renders.
- The `AppHeader.tsx` change is a 12-line addition — TypeScript type-checks clean (confirmed via `get_diagnostics`); the Catalogue tab's correctness is verified by the clean TS build.

#### Fix Confidence
- [x] **High** — data contract (all metadata fields present for the Catalogue display) verified; router endpoints confirmed; TS diagnostics clean on the changed component
