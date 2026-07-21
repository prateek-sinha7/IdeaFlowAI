# Tasks — Revision Pipeline Eval Suite + Fix

Small, ordered, individually landable tasks. Each maps to requirement (R-xx)
and design (D-xx) ids. Status: `[ ]` todo. Do not start a phase before the
previous phase's gate task is checked.

## Phase 0 — Harness scaffold + hello world

- [ ] **T-001** Create `backend/tests/evals/__init__.py` +
      `revision_fulfillment/__init__.py` + `fixtures/` skeleton per the
      D-02 tree. *(R-01, D-01, D-02)*
- [ ] **T-002** Register the `eval` marker in `backend/pyproject.toml`
      `markers` list. *(R-02, D-04)*
- [ ] **T-003** Write `tests/evals/conftest.py`: `RUNS_ROOT` tmpdir
      fixture, scenario-loader fixture stub, `pytestmark` convention.
      *(R-03, D-03)*
- [ ] **T-004** Write `test_hello_world.py`: import
      `ScriptedFakeChatModel`, `compile_for_run`, the `revision_validation`
      post-step class; drive one scripted model turn; assert marker
      selection. *(R-05, D-03)*
- [ ] **T-005 — PHASE GATE** Run `python3.11 -m pytest tests/evals -m eval`
      (hello world green, nothing else collected) AND
      `python3.11 -m pytest tests/ -m "not eval" --collect-only` (rest of
      suite unaffected). Record output in `STATUS.md`. *(R-01–R-05)*

## Phase 1 — Layered issue-surface tests

- [ ] **T-006** Author `fixtures/mini_prototype.html` (≤4 KB: 2–3 pages,
      routes map, topbar, one dead Save button) + minimal `fixtures/design.md`.
      *(R-06, D-02)*
- [ ] **T-007** `test_l2_compile.py` — manifest shape assertions (start
      with L2: it's mock-free, fastest signal that refs are right).
      *(R-08, D-06)*
- [ ] **T-008** `test_l1_api_entry.py` — `revision_instruction` +
      `parent_run_id` reach `execute()`; follow
      `test_run_revision_fe_contract.py` fixture style. *(R-07, D-06)*
- [ ] **T-009** `test_l3_context_seed.py` — `revision_original_html` +
      sandbox seeding via the `previous_run` provider. *(R-09, D-06)*
- [ ] **T-010** `test_l4_post_step.py` — stub-`ctx` spy on
      `RevisionValidationPostStep.run()` threaded args. *(R-10, D-06)*
- [ ] **T-011** `test_l5_selection_gap.py` — `_select_issues_to_fix`
      returns `[]` for a clean no-op edit with populated baselines;
      docstring cites FINDINGS A2. *(R-11, D-06)*
- [ ] **T-012** `test_l6_llm_boundary.py` — revision fix_message embeds the
      instruction verbatim; thread id uses the compiled agent id.
      *(R-12, D-06)*
- [ ] **T-013 — PHASE GATE** All L1–L6 green offline; note in `STATUS.md`
      which layer tests confirmed instruction propagation is INTACT
      (expected: all of L1–L4, L6 — the gap is only L5's selection
      semantics). *(R-07–R-12)*

## Phase 2 — Defect-reproducing evals

- [ ] **T-014** Write `fixtures/scenarios.yaml` with the S1/S2/S3 matrix
      from D-05. *(R-13–R-15, D-05)*
- [ ] **T-015** Build the scripted-agent script-builders (per-scenario
      tool-call scripts on `ScriptedFakeChatModel`) in `test_scenarios.py`.
      While building S2, verify the D-05 note: script it so today's
      `static_check` does NOT catch it (section+route present, nav link
      absent). *(R-13, R-14, D-05, D-03)*
- [ ] **T-016** Implement S3 (control) end-to-end and get it green —
      proves the e2e scripted drive works before the xfail pair lands.
      *(R-15)*
- [ ] **T-017** Implement S1 + S2 asserting DESIRED behavior, marked
      `xfail(strict=True, reason=...)` per D-04. Confirm they xfail (not
      xpass, not error) against current code. *(R-13, R-14, R-16, D-04)*
- [ ] **T-018 — PHASE GATE** Suite state: S3 pass, S1/S2 xfail, L1–L6
      pass, zero tokens consumed. The defect is now mechanically
      reproducible. Record in `STATUS.md`. *(R-16)*

## Phase 3 — Fix + eval-verified resolution

- [ ] **T-019** Confirm the registry contract
      (`agents/capabilities/registry.py`) and the exact `ctx.runner` handle
      surface available to post-steps; write the 5-line interface note into
      `STATUS.md` before coding (locks D-07's open choice on the retry
      handle). *(R-17, D-07)*
- [ ] **T-020** Implement
      `agents/capabilities/post_steps/instruction_fulfillment.py`: verdict
      call + lenient JSON parse + fail-open + empty-instruction skip +
      token logging. No manifest wiring yet. *(R-17, R-18, R-21, D-07)*
- [ ] **T-021** Unit tests for T-020 in the eval package: parse tolerance
      (fences/trailing text/garbage → fail-open), skip-on-empty, never-raise.
      Scripted model returns the verdict JSON. *(R-18, R-21)*
- [ ] **T-022** Implement the 1-attempt retry path (dedicated small loop
      per D-07, thread `{run}:{agent}:fulfillment:fix1`, drained
      internally). *(R-20, D-07)*
- [ ] **T-023** Wire `post_step: instruction_fulfillment` onto step 2 of
      `prototype_revision/workflow.yaml`; confirm `WorkflowResolver` +
      the L2 test (update T-007 assertions in the same commit). *(R-19)*
- [ ] **T-024** INV-3 golden handling per D-08 (default: pin the new
      post-step off in the offline golden harness, matching the
      `require_render=False` precedent); run the characterization suite.
      *(R-22, D-08)*
- [ ] **T-025** Remove S1/S2 `xfail` markers — suite must go: xpass-error
      (proving strict worked) → markers removed → green. Same commit as
      nothing else. *(R-16, R-22)*
- [ ] **T-026** Add the single live smoke test
      (`requires_api_key`, Haiku, mini fixture, `max_tokens ≤ 2048`) for
      the real fulfillment call; run it once locally, record token cost in
      `STATUS.md`. *(R-04, D-03)*
- [ ] **T-027 — PHASE GATE / DEFINITION OF DONE** Full check per R-22:
      S1/S2/S3 pass unmarked, L1–L6 pass, goldens byte-identical, existing
      revision suites (`test_phase5_revision_validation.py`,
      `test_revision_*`) green. *(R-22)*
- [ ] **T-028** (Deferred until post-ship data exists) Evaluate the
      per-agent model bump escape hatch. *(R-23)*

## Phase 4 — PARKED: thinking (do not start before T-027)

- [ ] **T-029** Un-park Defect B: write its requirements (extending
      `requirements.md` §E) from `PLAN.md` Phase 4 / FINDINGS B1–B5, then
      task it out in this file. *(R-24)*
