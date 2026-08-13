# 260811-mxg — measurement log

## PRE-CHANGE BASELINE

**Commit:** `edc44daa0cd46c7aeee540c6bbca489c997338f3`
**Branch:** `bugfix/spec-revision-context-loss`
**Measured:** 2026-08-11, offline (`python3.11`, no venv), from `backend/`
**Working tree at measurement time:** clean except three untracked paths that are not part of
this task (`.planning/ROUTE-MIGRATION-COST-ANALYSIS.md`,
`.planning/TEST-HARNESS-OFFLINE-DESIGN.md`, `backend/.runs-local/`).

> The remembered figure "10 failed / 6 passed, 1 broken contract" was measured on `dev` on
> 2026-07-29 and is **stale**. Everything below is measured on the pre-change commit of THIS
> branch and is the only oracle used for regression classification.

| # | Command | Verbatim summary line |
|---|---------|----------------------|
| 1 | `pytest tests/agents/test_characterization_{od_prototype,od_ppt,prototype,prototype_revision,app_builder}.py -q` | `5 failed, 5 passed, 1 warning in 36.21s` |
| 2 | `pytest tests/agents/test_restart_resume.py -q` | `7 failed, 41 passed, 1 warning in 4.65s` |
| 3 | `pytest tests/agents/test_redo_gate_safety.py tests/agents/test_steering_seam.py -q` | `3 failed, 10 passed, 1 warning in 1.08s` |
| 4 | `pytest tests/unit/test_execution_engine.py -q` | `3 failed, 11 passed, 1 warning in 0.16s` |
| 5 | `/opt/homebrew/bin/lint-imports` | `Contracts: 3 kept, 1 broken.` |

### Pre-existing reds

Everything in this list is **NOT a regression** later. Anything red after the change that is
**not** in this list **is** a regression and blocks completion. None of these are fixed by this
task — they are recorded and left alone (scope fence).

**Characterization goldens (5 of 10 red).** The 5 `*_deliverable_byte_snapshot` tests PASS; the
5 `*_event_snapshot` tests FAIL:

- `tests/agents/test_characterization_od_prototype.py::test_od_prototype_event_snapshot`
- `tests/agents/test_characterization_od_ppt.py::test_od_ppt_event_snapshot`
- `tests/agents/test_characterization_prototype.py::test_prototype_event_snapshot`
- `tests/agents/test_characterization_prototype_revision.py::test_prototype_revision_event_snapshot`
- `tests/agents/test_characterization_app_builder.py::test_app_builder_event_snapshot`

**`tests/agents/test_restart_resume.py` (7 red):**

- `test_midwave_resume_does_not_reinvoke_completed_workers`
- `test_open_gate_override_is_noop_without_review_gate`
- `test_partial_task_loop_build_reenters_step_not_skipped`
- `test_completed_task_loop_build_stays_complete_no_rerun`
- `test_resumed_run_is_wired_live_ectx_and_milestone_cards`
- `test_failed_run_resumes_skips_completed_tasks`
- `test_failed_run_with_open_gate_resumes_into_gate`

`test_offset0_gate_resume_does_not_replan_or_reclarify` is **GREEN** at baseline — it is the
TRAP-4 acceptance guard and must stay green.

**`tests/agents/test_redo_gate_safety.py` (3 red; `test_steering_seam.py` fully green):**

- `test_f2_unbounded_redos_keep_a_flat_stack`
- `test_f3_empty_output_after_redo_does_not_leak_lineage`
- `test_redo_uses_fresh_checkpoint_thread_per_attempt`

Root cause of all three (diagnosed, not fixed — out of scope): their local `_fake_gate` stubs
have a stale signature. `_run_review_gate` now passes `update_specs_eligible`, so the stub
raises `TypeError: _fake_gate() got an unexpected keyword argument 'update_specs_eligible'`.
**Consumed as a lesson for this task:** every gate stub written in Task 1 accepts `**kwargs`.

**`tests/unit/test_execution_engine.py` (3 red):**

- `test_clarify_engine_asks_once_then_limit_reached`
- `test_clarify_engine_rounds_knob_allows_multi_round`
- `test_clarify_engine_empty_submit_proceeds_after_one_round`

**`lint-imports` (1 broken contract):**

- `agents.capabilities must not import the execution kernel or the web layer` — BROKEN via
  `agents.capabilities.strategies.task_loop -> agents.execution_engine.od_context (l.562)`
  and `agents.execution_engine.od_context -> app.services.od_loader (l.26)`.

## RED evidence

All five new tests written and OBSERVED RED on `edc44daa` before any implementation.
Every failure is an assertion or an `AttributeError` raised INSIDE the test body — pytest
reported `4 failed` / `2 failed` with **zero errors**, so no failure is a collection or
fixture problem masquerading as a RED.

`pytest tests/agents/test_spec_revision_context.py -q` → `4 failed, 1 warning in 1.38s`
(0 passed, 0 errors):

```
tests/agents/test_spec_revision_context.py:149: in test_revision_injects_prior_artifact_into_specify_dispatch
    assert PRIOR in msg, (
E   AssertionError: D1: the specify re-dispatch must carry the PRIOR artifact it is told to preserve; prompt was:
E     === SPEC KIT ANALYSIS REPORT (REVISION CONTEXT) ===
E     ... Preserve unchanged sections.
E     REPORT-SENTINEL
E     === END SPEC KIT ANALYSIS REPORT ===
```

(the same verbatim failure for BOTH parameters — `[live]`, the post-stream consumer at
engine.py:4296, and `[reentry]`, the RESUME-17 gate re-entry at engine.py:3270; the
report reaches the writer and the document it must preserve does not — D1 exactly)

```
tests/agents/test_spec_revision_context.py:177: in test_revision_prior_artifact_does_not_leak_to_plan_or_analyze
    assert not ectx.spec_revision_prior_artifact, (
E   AttributeError: 'ExecutionContext' object has no attribute 'spec_revision_prior_artifact'
```

```
tests/agents/test_spec_revision_context.py:197: in test_revision_dispatch_uses_a_fresh_checkpoint_thread
    assert all(t.endswith(":rev1") for t in sub_threads), (
E   AssertionError: every revision dispatch must thread a fresh :rev1 checkpoint; got ['rev-live:domain-analyst', 'rev-live:epic-architect', 'rev-live:story-estimator']
```

`pytest tests/agents/test_restart_resume.py -q -k rehydrat` → `2 failed, 48 deselected,
1 warning in 1.45s` (0 passed, 0 errors):

```
tests/agents/test_restart_resume.py:3789: in test_rehydrate_planning_context_rebuilds_planner_and_answers
    rebuilt = engine._rehydrate_planning_context(ectx, user_message)
E   AttributeError: 'ExecutionEngine' object has no attribute '_rehydrate_planning_context'
```

```
tests/agents/test_restart_resume.py:3895: in test_resume_dispatch_carries_rehydrated_planning_context
    assert _REHYDRATE_ANSWER in first, (
E   AssertionError: D2: a resumed dispatch must carry the user's clarification answers; got:
E     === ORIGINAL USER REQUEST ===
E     Run the wave workflow.
E     === END REQUEST ===
E     ## Planning Context (Deep Planner Analysis)
E     **Inferred Intent**: Run the wave workflow.
E     ## End Planning Context
```

That last block IS the D2 defect reproduced offline: the resumed dispatch's whole planning
block is the stub, with `inferred_intent == user_message[:200]` and every list empty, while
the durable `planning_context` + `clarifications` rows sit unread in the graph.

### Fixture notes carried out of the RED pass

- Test 5 fails on its ASSERTION, not on setup — the resume drive really dispatched and
  really composed a prompt.
- The `[reentry]` parameter genuinely reaches the specify re-dispatch, so both consumer
  sites are proven live rather than assumed (TRAP 2).
- Every new gate stub takes `**kwargs`. The three baseline reds in
  `test_redo_gate_safety.py` are stale stubs pinning a pre-`update_specs_eligible`
  signature; copying that shape would have produced a pytest ERROR instead of a RED.

## POST-CHANGE RESULTS

Measured after Task 2 (`7badc86a`) and Task 3, on the same machine, same commands.

| # | Command | Pre-change | Post-change | Verdict |
|---|---------|-----------|-------------|---------|
| 1 | the 5 characterization goldens | `5 failed, 5 passed` | `5 failed, 5 passed` | identical — same 5 ids, no new red |
| 2 | `tests/agents/test_restart_resume.py` | `7 failed, 41 passed` | `7 failed, 43 passed` | same 7 ids; +2 newly-green (the new D2 pair) |
| 3 | `test_redo_gate_safety.py` + `test_steering_seam.py` | `3 failed, 10 passed` | `3 failed, 10 passed` | identical — same 3 ids |
| 4 | `tests/unit/test_execution_engine.py` | `3 failed, 11 passed` | `3 failed, 11 passed` | identical — same 3 ids |
| 5 | `lint-imports` | `Contracts: 3 kept, 1 broken.` | `Contracts: 3 kept, 1 broken.` | identical — same contract, same import chain |
| 6 | `tests/agents/test_spec_revision_context.py` (new) | `4 failed` | `4 passed` | newly-green |

### Per-test classification

Every non-passing test after the change, classified. **No `new-red`.**

**baseline-red (14 — unchanged, untouched, out of scope):**

- `test_od_prototype_event_snapshot`, `test_od_ppt_event_snapshot`,
  `test_prototype_event_snapshot`, `test_prototype_revision_event_snapshot`,
  `test_app_builder_event_snapshot`
- `test_midwave_resume_does_not_reinvoke_completed_workers`,
  `test_open_gate_override_is_noop_without_review_gate`,
  `test_partial_task_loop_build_reenters_step_not_skipped`,
  `test_completed_task_loop_build_stays_complete_no_rerun`,
  `test_resumed_run_is_wired_live_ectx_and_milestone_cards`,
  `test_failed_run_resumes_skips_completed_tasks`,
  `test_failed_run_with_open_gate_resumes_into_gate`
- `test_f2_unbounded_redos_keep_a_flat_stack`,
  `test_f3_empty_output_after_redo_does_not_leak_lineage`,
  `test_redo_uses_fresh_checkpoint_thread_per_attempt`
- `test_clarify_engine_asks_once_then_limit_reached`,
  `test_clarify_engine_rounds_knob_allows_multi_round`,
  `test_clarify_engine_empty_submit_proceeds_after_one_round`
- `lint-imports`: `agents.capabilities must not import the execution kernel or the web layer`

**new-red: NONE.**

**newly-green (6 — the five new tests, one of them parametrized):**

- `test_revision_injects_prior_artifact_into_specify_dispatch[live]` (engine.py:4296 site)
- `test_revision_injects_prior_artifact_into_specify_dispatch[reentry]` (engine.py:3270 site)
- `test_revision_prior_artifact_does_not_leak_to_plan_or_analyze`
- `test_revision_dispatch_uses_a_fresh_checkpoint_thread`
- `test_rehydrate_planning_context_rebuilds_planner_and_answers`
- `test_resume_dispatch_carries_rehydrated_planning_context`

`test_offset0_gate_resume_does_not_replan_or_reclarify` (TRAP 4 / BUG-R05) is **GREEN**,
and green for the right reason: with `--log-cli-level=INFO` it emits no
`resume rehydrate:` line at all, so the rehydrator took its no-durable-row early return
and never reached the merge — its pass is not a swallowed exception.

### Adversarial check on the import-time `ClarifyEngine` binding

The binding's whole purpose is to survive `monkeypatch.setattr(_clar_mod, "ClarifyEngine",
_FakeClarify)`, and no test exercises that conjunction (the TRAP-4 test patches the fake
but returns early). Verified directly instead: with `clarify_engine.ClarifyEngine`
replaced by a `_FakeClarify` that has no `_merge_answers`, the rehydrator still merged
`['Target? → SPINNAKER']`. A function-level import would have resolved the fake, raised
`AttributeError`, been caught by the narrow guard, and silently dropped every answer —
the exact degradation this fix removes.

## Deferred: live Bedrock acceptance (end-of-milestone)

Offline evidence (scripted-model tests + goldens + `lint-imports`) closes this task; the
live pass is deferred. Recipe, from section 5 of `BUGFIX-SPEC-REVISION-CONTEXT.md`:

- The model is stochastic, so assert **properties** against the DB, not exact text.
- Pull `spec` v1 and v2 from `artifact_refs` via
  `GET /api/runs/{id}/artifacts?kind=spec&include=content` — **not** through the UI: the
  FE keeps one slot per agent id and `agent_start` wipes `output: ""` (FIX-039,
  `useWorkflow.ts`), erasing v1 from the screen the moment the revision starts.
- The four assertions. All four FAIL on the reported run, so they are a real before/after
  oracle rather than a tautology:

  ```
  headings(v2) ⊇ headings(v1)              # reported run: 19 vs 27      → FAIL
  "Spinnaker" in v2                         # reported run: 0 hits        → FAIL
  "Workflow Completion Checklist" in v2     # reported run: absent        → FAIL
  len(v2) >= len(v1)                        # reported run: 39,115 < 43,670 → FAIL
  ```

- **Run it three times** — one pass on a stochastic model proves nothing.
