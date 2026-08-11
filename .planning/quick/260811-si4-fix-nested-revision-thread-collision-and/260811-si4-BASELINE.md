# Quick 260811-si4 — baseline, RED evidence and post-change comparison

## PRE-CHANGE BASELINE

**Measured at:** `bf51a170668d5902fd9c1e534b0642f430fde568`
(branch `bugfix/spec-revision-context-loss`, working tree CLEAN)

**Why this SHA is pre-change for CODE purposes.** The plan was written at `c0d7b46b` and
revised at `6278368c`. The commits since carry **no source change**:

- `de42a7bf` — docs/bookkeeping (registered quick-260811-mxg as FIX-217 / TEST-003, filed ISS-064..053)
- `6278368c` — chore/knowledge
- `bf51a170` — `docs(quick-260811-si4): revise the plan …` — touches `260811-si4-PLAN.md` only
  (verified: `git diff --stat 6278368c..HEAD` = 1 file, the plan)

No detached worktree was needed; every number below was measured on this working tree
with `python3.11 -m pytest` from `backend/` (no venv — `backend/.venv` does not exist).

### Measurements (verbatim summary lines)

| # | What | Command (from `backend/`) | Verbatim summary line |
|---|------|---------------------------|-----------------------|
| 1 | 5 characterization goldens (ONE invocation) | `python3.11 -m pytest tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py -q --tb=no -rfE` | `5 failed, 5 passed, 1 warning in 35.53s` |
| 2 | mxg guard (quick 260811-mxg) | `python3.11 -m pytest tests/agents/test_spec_revision_context.py -q` | `4 passed, 1 warning in 1.14s` |
| 3 | restart/resume, full file | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` | `7 failed, 48 passed, 1 warning in 4.24s` |
| 4 | restart/resume, mxg selection | `python3.11 -m pytest tests/agents/test_restart_resume.py -q -k rehydrat` | `7 passed, 48 deselected, 1 warning in 0.93s` |
| 5 | redo-gate + steering seam | `python3.11 -m pytest tests/agents/test_redo_gate_safety.py tests/agents/test_steering_seam.py -q` | `3 failed, 10 passed, 1 warning in 0.72s` |
| 6 | engine unit suite | `python3.11 -m pytest tests/unit/test_execution_engine.py -q` | `3 failed, 11 passed, 1 warning in 0.12s` |
| 7 | import contracts | `/opt/homebrew/bin/lint-imports` | `Contracts: 3 kept, 1 broken.` |

Every number matches what planning measured at `c0d7b46b`, except measurement 6
(`tests/unit/test_execution_engine.py`), for which planning quoted no figure — it is
**3 failed / 11 passed** here and all three reds are pre-existing clarify-engine failures
untouched by this task.

The single broken import contract is the known pre-existing one:

```
agents.capabilities must not import the execution kernel or the web layer BROKEN
```

### Machine-readable baseline

Tasks 2 and 3 diff against these two lines byte-for-byte, so the INV-3 dormancy claim is
asserted by a gate rather than eyeballed.

GOLDENS-BASELINE: failed=5 passed=5 ids=FAILED:tests/agents/test_characterization_app_builder.py::test_app_builder_event_snapshot FAILED:tests/agents/test_characterization_od_ppt.py::test_od_ppt_event_snapshot FAILED:tests/agents/test_characterization_od_prototype.py::test_od_prototype_event_snapshot FAILED:tests/agents/test_characterization_prototype_revision.py::test_prototype_revision_event_snapshot FAILED:tests/agents/test_characterization_prototype.py::test_prototype_event_snapshot
LINT-BASELINE: kept=3 broken=1

### Pre-existing reds

Anything in this list is **not** a regression later. Anything not in it **is**.

**Characterization goldens (5)** — event-snapshot drift, pre-dating this branch:

- `tests/agents/test_characterization_od_prototype.py::test_od_prototype_event_snapshot`
- `tests/agents/test_characterization_od_ppt.py::test_od_ppt_event_snapshot`
- `tests/agents/test_characterization_prototype.py::test_prototype_event_snapshot`
- `tests/agents/test_characterization_prototype_revision.py::test_prototype_revision_event_snapshot`
- `tests/agents/test_characterization_app_builder.py::test_app_builder_event_snapshot`

**`tests/agents/test_restart_resume.py` (7)**:

- `test_midwave_resume_does_not_reinvoke_completed_workers`
- `test_open_gate_override_is_noop_without_review_gate`
- `test_partial_task_loop_build_reenters_step_not_skipped`
- `test_completed_task_loop_build_stays_complete_no_rerun`
- `test_resumed_run_is_wired_live_ectx_and_milestone_cards`
- `test_failed_run_resumes_skips_completed_tasks`
- `test_failed_run_with_open_gate_resumes_into_gate`

**`tests/agents/test_redo_gate_safety.py` (3)** — signature rot, NOT engine defects
(`TypeError: _fake_gate() got an unexpected keyword argument 'update_specs_eligible'`,
swallowed by `_run_agent`'s broad `except Exception` into an `agent_error` event, which is why
the tests observe `gate_calls["n"] == 0`). Task 1 STEP 2 revives them by adding `**kwargs` to
the four stubs — test-only, no production diff:

- `test_f2_unbounded_redos_keep_a_flat_stack`
- `test_f3_empty_output_after_redo_does_not_leak_lineage`
- `test_redo_uses_fresh_checkpoint_thread_per_attempt`

**`tests/unit/test_execution_engine.py` (3)** — pre-existing clarify-engine reds, unrelated:

- `test_clarify_engine_asks_once_then_limit_reached`
- `test_clarify_engine_rounds_knob_allows_multi_round`
- `test_clarify_engine_empty_submit_proceeds_after_one_round`

**Import contracts (1)**: `agents.capabilities must not import the execution kernel or the web layer`.

### Post-STEP-2 note — the three revived guards

`tests/agents/test_redo_gate_safety.py` was NOT reverted. Adding `**kwargs` to the four
`_fake_gate` stubs (test-only, no production diff) took the file from **3 failed / 4 passed**
to **7 passed, 1 warning in 3.31s**, exactly as planning measured. No ISS row is needed for
constraint 7.

---

## RED evidence

Observed at `bf51a170` with the engine **unmodified** (only the two test files exist/changed):

```
cd backend && python3.11 -m pytest tests/agents/test_spec_revision_cycles.py -q --tb=line -rfE
...
tests/agents/test_spec_revision_cycles.py FFFF.                          [100%]
==================== 4 failed, 1 passed, 1 warning in 1.42s ====================
```

Verbatim failure line of each of the four defect tests — every one an **assertion**, never a
collection or fixture error (the Task 1 verify gate rejects an error as not-RED):

- `test_spec_revision_cycles.py:187: AssertionError: expected 1 first-pass dispatch + 3 per revision cycle x 2 cycles = 7; the second 'Update the Specs' ran no cycle. Got 4: ['cycles-b:story-estimator', 'cycles-b:domain-analyst:rev1', 'cycles-b:epic-architect:rev1', 'cycles-b:story-estimator:rev1']`
- `test_spec_revision_cycles.py:215: AssertionError: the second cycle never ran, so there is no depth to compare; got ['cycles-flat:story-estimator', 'cycles-flat:domain-analyst:rev1', 'cycles-flat:epic-architect:rev1', 'cycles-flat:story-estimator:rev1']`
- `test_spec_revision_cycles.py:259: AssertionError: the analyze re-run INSIDE the revision pass must NOT advertise 'Update the Specs' — that is the one route that nests; got [True, True, True]`
- `test_spec_revision_cycles.py:288: AssertionError: two revision passes minted the SAME checkpoint thread id, so one is served the other's conversation replay (the P23 class); got ['cycles-nested:story-estimator', 'cycles-nested:domain-analyst:rev1', 'cycles-nested:epic-architect:rev1', 'cycles-nested:story-estimator:rev1', 'cycles-nested:domain-analyst:rev1', 'cycles-nested:epic-architect:rev1', 'cycles-nested:story-estimator:rev1']`

Every failure reason matches what planning predicted:

| Test | Predicted pre-fix reason | Observed |
|------|--------------------------|----------|
| 1 (B second cycle) | only 4 dispatches, no `:rev2` | 4 dispatches, all `:rev1` — the second click ran nothing |
| 2 (B flat stack) | cycle 2 never happened, dispatch-count assertion fires first | exactly that |
| 3 (A affordance) | `update_specs_eligible` True at firing `[1]` | `[True, True, True]` |
| 4 (A nested) | 7 thread ids but only 4 unique | 7 ids / 4 unique — two passes both minted `:rev1` |

Gate results at this point:

```
RED-OK (4 assertion failures, 0 passed, 0 errors)
BOUNDARY-GREEN-PRE-FIX
STUBS-REVIVED-OK
```

`test_single_cycle_shape_is_unchanged` (the dormancy guard) PASSES on the unmodified engine.

---

## POST-CHANGE RESULTS

**Measured at:** `9be1b458` (Task 2's engine commit), same working tree, same commands.

| # | What | Baseline | Now | Delta |
|---|------|----------|-----|-------|
| 1 | 5 characterization goldens | `5 failed, 5 passed, 1 warning in 35.53s` | `5 failed, 5 passed, 1 warning in 38.42s` | unchanged — same counts, same failing ids |
| 2 | mxg guard `test_spec_revision_context.py` | `4 passed, 1 warning in 1.14s` | `4 passed, 1 warning in 1.17s` | unchanged |
| 3 | `test_restart_resume.py`, full | `7 failed, 48 passed, 1 warning in 4.24s` | `7 failed, 48 passed, 1 warning in 4.57s` | unchanged |
| 4 | `test_restart_resume.py -k rehydrat` | `7 passed, 48 deselected, 1 warning in 0.93s` | `7 passed, 48 deselected, 1 warning in 0.93s` | unchanged |
| 5 | `test_redo_gate_safety.py` + `test_steering_seam.py` | `3 failed, 10 passed, 1 warning in 0.72s` | `13 passed, 1 warning in 3.54s` | **+3 newly green** (the revived guards) |
| 6 | `tests/unit/test_execution_engine.py` | `3 failed, 11 passed, 1 warning in 0.12s` | `3 failed, 11 passed, 1 warning in 0.12s` | unchanged |
| 7 | **NEW** `test_spec_revision_cycles.py` | *(4 failed, 1 passed — the RED gate)* | `5 passed, 1 warning in 1.48s` | **+4 newly green** |
| 8 | import contracts | `Contracts: 3 kept, 1 broken.` | `Contracts: 3 kept, 1 broken.` | unchanged |

### Machine-readable post-change

Rendered with the IDENTICAL command as Task 1's `GOLDENS-BASELINE` / `LINT-BASELINE`, and
string-diffed against them by the Task 2 and Task 3 verify gates:

GOLDENS-POST: failed=5 passed=5 ids=FAILED:tests/agents/test_characterization_app_builder.py::test_app_builder_event_snapshot FAILED:tests/agents/test_characterization_od_ppt.py::test_od_ppt_event_snapshot FAILED:tests/agents/test_characterization_od_prototype.py::test_od_prototype_event_snapshot FAILED:tests/agents/test_characterization_prototype_revision.py::test_prototype_revision_event_snapshot FAILED:tests/agents/test_characterization_prototype.py::test_prototype_event_snapshot
LINT-POST: kept=3 broken=1

Both gates reported `GOLDEN-DORMANCY-OK` / `LINT-DORMANCY-OK` — byte-identical to the Task 1
baseline, counts AND failing ids, so INV-3 dormancy is asserted rather than eyeballed.

### Classification — every test non-passing now, or that changed state

- baseline-red: tests/agents/test_characterization_od_prototype.py::test_od_prototype_event_snapshot — pre-existing event-snapshot drift; identical failing id before and after
- baseline-red: tests/agents/test_characterization_od_ppt.py::test_od_ppt_event_snapshot — pre-existing event-snapshot drift; identical failing id before and after
- baseline-red: tests/agents/test_characterization_prototype.py::test_prototype_event_snapshot — pre-existing event-snapshot drift; identical failing id before and after
- baseline-red: tests/agents/test_characterization_prototype_revision.py::test_prototype_revision_event_snapshot — pre-existing event-snapshot drift; identical failing id before and after
- baseline-red: tests/agents/test_characterization_app_builder.py::test_app_builder_event_snapshot — pre-existing event-snapshot drift; identical failing id before and after
- baseline-red: tests/agents/test_restart_resume.py::test_midwave_resume_does_not_reinvoke_completed_workers — pre-existing; unrelated to the update_specs path
- baseline-red: tests/agents/test_restart_resume.py::test_open_gate_override_is_noop_without_review_gate — pre-existing; unrelated to the update_specs path
- baseline-red: tests/agents/test_restart_resume.py::test_partial_task_loop_build_reenters_step_not_skipped — pre-existing; unrelated to the update_specs path
- baseline-red: tests/agents/test_restart_resume.py::test_completed_task_loop_build_stays_complete_no_rerun — pre-existing; unrelated to the update_specs path
- baseline-red: tests/agents/test_restart_resume.py::test_resumed_run_is_wired_live_ectx_and_milestone_cards — pre-existing; unrelated to the update_specs path
- baseline-red: tests/agents/test_restart_resume.py::test_failed_run_resumes_skips_completed_tasks — pre-existing; unrelated to the update_specs path
- baseline-red: tests/agents/test_restart_resume.py::test_failed_run_with_open_gate_resumes_into_gate — pre-existing; unrelated to the update_specs path
- baseline-red: tests/unit/test_execution_engine.py::test_clarify_engine_asks_once_then_limit_reached — pre-existing clarify-engine red; untouched by this task
- baseline-red: tests/unit/test_execution_engine.py::test_clarify_engine_rounds_knob_allows_multi_round — pre-existing clarify-engine red; untouched by this task
- baseline-red: tests/unit/test_execution_engine.py::test_clarify_engine_empty_submit_proceeds_after_one_round — pre-existing clarify-engine red; untouched by this task
- baseline-red: lint-imports `agents.capabilities must not import the execution kernel or the web layer` — the one pre-existing broken import contract, unchanged
- newly-green: tests/agents/test_spec_revision_cycles.py::test_reopened_gate_second_update_specs_runs_a_second_cycle — Defect B fixed; 4 dispatches became 7, cycle 2 on `:rev2`
- newly-green: tests/agents/test_spec_revision_cycles.py::test_reopened_gate_cycle_keeps_a_flat_stack — cycle 2's gates now exist AND sit at cycle 1's stack depth (flat sibling)
- newly-green: tests/agents/test_spec_revision_cycles.py::test_update_specs_not_offered_while_a_revision_is_in_flight — eligibility went `[True, True, True]` to `[True, False, True]`
- newly-green: tests/agents/test_spec_revision_cycles.py::test_nested_revision_keeps_distinct_threads_and_restores_the_outer_pass — 4 unique ids of 7 became 7 of 7; outer pass left at index 1 with its report intact
- newly-green: tests/agents/test_redo_gate_safety.py::test_f2_unbounded_redos_keep_a_flat_stack — revived by the `**kwargs` stub fix (Task 1 STEP 2), dead since KAN-101
- newly-green: tests/agents/test_redo_gate_safety.py::test_f3_empty_output_after_redo_does_not_leak_lineage — revived by the `**kwargs` stub fix
- newly-green: tests/agents/test_redo_gate_safety.py::test_redo_uses_fresh_checkpoint_thread_per_attempt — revived by the `**kwargs` stub fix

**Zero regressions.** No test green in the baseline is red now.

---

## Deferred: live Bedrock acceptance (end-of-milestone)

Not required for completion (the deferred-live-verification rule); the offline evidence above
is sufficient. The oracle is behavioural and needs no new tooling.

1. **Reach the first analyze gate.** Launch `od_prototype` (needs `template_id` +
   `design_system_id`), let it run to the analyze gate, click **Update the Specs**, then
   approve the specify and plan re-runs.
2. **The in-flight fence (Defect A).** At the analyze re-run's gate INSIDE the pass, confirm
   the **Update the Specs** button is ABSENT while Redo / Approve / Reject remain.
   `InlineGateActions.tsx:130` drives that button purely from the server flag, so its absence
   IS the `update_specs_eligible=False` assertion.
3. **The second cycle (Defect B).** Approve; at the RE-OPENED analyze gate confirm the button
   IS present. Click it and confirm a real second cycle runs: the FE "Spec Revision Cycle"
   banner advances (it keys on a done agent re-starting, `dashboard/page.tsx:352-357`) and
   three agents re-dispatch.
4. **Distinct threads.** From the backend log, confirm cycle 2's `thread_id`s carry `:rev2`
   and never `:rev1`.
5. **Content carry-over.** Pull the spec versions via
   `GET /api/runs/{id}/artifacts?kind=spec&include=content` — **not** through the UI, because
   `agent_start` wipes `output: ""` (FIX-039, `useWorkflow.ts`) and erases the prior version
   from the screen the moment the revision starts. Assert `len(v3) >= len(v2)` and
   `headings(v3) ⊇ headings(v2)` — the same property shape the mxg live pass used
   (run `5ecb990f`: 0 headings lost, 97.6% verbatim carry-over).

Local run recipe: SSO profile `hex-ai-fe`, leave `ANTHROPIC_API_KEY` empty, backend on `:8010`,
QA login `qa-enterprise@flowinqa.com`.
