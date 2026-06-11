---
phase: 13-live-verification-gap-closure
plan: 06
subsystem: execution-engine
tags: [terminal-semantics, pipeline-failed, ingress-guard, fe-contract, gap-closure, f3]
requires:
  - "13-01 (gate streaming branch in _evaluate_gates — engine.py diff base)"
  - "13-05 (deliverable-ref write guarded on `final_output and results` — the total-failure branch composes with it)"
provides:
  - "pipeline_failed terminal WS event (total collapse: every agent errored, nothing completed) + state machine 'failed'"
  - "strictly-conditional status='degraded' + agents_failed fields on pipeline_complete (partial failure)"
  - "missing_template_context WS ingress rejection for template-inject pipelines without a loadable template body"
  - "FE pipeline_failed terminal handling (both type unions + useWorkflow teardown + dashboard surface)"
affects:
  - "live verification milestone pass (ROADMAP Phase 13 success criterion 3)"
tech-stack:
  added: []
  patterns:
    - "failure tracking by observation (agent_error agent_ids recorded in the dispatch loop, events untouched)"
    - "strictly-conditional additive payload keys (OBS-01 conditional-snapshot pattern — clean runs byte-identical)"
    - "ingress guard keyed on declared capability surface (spec.injects), never workflow names (SC-001)"
key-files:
  created:
    - backend/tests/unit/test_pipeline_failure_semantics.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/app/api/websocket.py
    - frontend/src/types/index.ts
    - frontend/src/hooks/useWorkflow.ts
    - frontend/src/app/dashboard/page.tsx
decisions:
  - "Product decision (F3 missing item 3, recorded as a comment at the guard): bare prototype/ppt remain ADMISSIBLE pipeline types but REQUIRE template context — fail fast with missing_template_context instead of the silent per-agent collapse; the FE always sends od_* aliases so no user-visible flow changes except the broken ones becoming visible"
  - "Total-collapse branch placed BEFORE the completed transition and RETURNS before deliverable resolution — mirrors the BudgetExceeded failed-terminal precedent (transition → snapshot persist → one event → return)"
  - "Ingress guard condition mirrors factory._compose_injection's TemplateMissingError raise EXACTLY ('template' in spec.injects AND no od_context template_body) so ingress rejects precisely the runs the factory would halt"
  - "Degraded keys conditional on `results and _failed_agent_ids` — a cancelled run with failures but no results never gains them; clean-run pipeline_complete payload byte-identical (scenario (c) pins the key-set)"
  - "useWorkflow pipeline_failed case mirrors pipeline_cancelled teardown (no new state shape): failed agents resolve to the existing per-agent error state, in-flight agents to idle, isRunning false"
metrics:
  duration: ~16 min
  tasks: 3
  files: 6
  completed: 2026-06-12
---

# Phase 13 Plan 06: Pipeline Failure Semantics Gap Closure (F3) Summary

All-agents-failed runs now terminate as one `pipeline_failed` event in state 'failed', partial failures carry additive `status="degraded"`+`agents_failed` on `pipeline_complete`, and template-inject pipelines without a template body are rejected at WS ingress with `missing_template_context` — never again a silent `pipeline_complete` with `final_output=''`.

## What was done

### Task 1: Engine terminal semantics (commit 08114a64)

- **Failure tracking (pure observation):** the dispatch loop records `event.data.agent_id` into a local `_failed_agent_ids: set[str]` whenever an `agent_error` flows through the single `_dispatch_step_with_retry` yield site. No event is modified, reordered or suppressed.
- **Total collapse branch:** at the Step-5 terminal block, when `not results and _failed_agent_ids` (and the run is not already cancelled/failed), the engine transitions to `"failed"`, persists the budget snapshot if fan-out was active, emits ONE `pipeline_failed` event (`pipeline_type`, `pipeline_run_id`, `total_duration`, `agents_completed: 0`, `agents_total`, `agents_failed` sorted, `error: "all agents failed"`, `timestamp`), and RETURNS before deliverable resolution — composing with 13-05's `final_output and results` deliverable-ref guard (the failure path stays write-free).
- **Degraded completion:** when `results and _failed_agent_ids`, the `pipeline_complete` data dict gains the ADDITIVE `status: "degraded"` + `agents_failed` keys — strictly conditional, mirroring the OBS-01 conditional-snapshot pattern. Clean-run payload byte-identical (5 characterization suites green, zero golden re-baselines).
- **SC-001/INV-1 held:** the branch keys on counters only; kernel banned-pattern grep (`if pipeline_type ==`) still 0.
- **Tests (scenarios a/b/c):** new `tests/unit/test_pipeline_failure_semantics.py` drives the REAL `execute()` path (real compiler, planner flipped to "skip", `_run_agent` stubbed) — total collapse → exactly one `pipeline_failed`/no `pipeline_complete`/state `"failed"`/all ids listed; one-of-two fails → degraded complete with the failed id and `agents_completed: 1`; clean run → NEITHER key present.

### Task 2: WS ingress guard (commit f54944fe)

- After agent resolution in `_handle_workflow_execution`, runs whose resolved specs declare `"template" in spec.injects` with no `od_context.template_body` are rejected: one error event (`code: "missing_template_context"`, `recoverable: False`, message naming the pipeline and the remedy) and an immediate return — the engine, checkpointer and sandbox never spin up (T-13-06-01 mitigation).
- Condition is GENERIC (declared injects only — no pipeline-name allow/deny list): bare prototype/ppt without a template are rejected; od_* runs with a loaded template pass unchanged; no-inject workflows untouched; `od_ppt_revision` without a template is rejected only if its resolved agents actually declare the inject.
- Product decision recorded as a code comment at the guard (see decisions above).
- **Tests (scenarios d/e/f):** handler-level, mirroring `test_pipeline_cancel.py`'s driving style (in-memory SQLite, recording stub engine, no-op'd title generation) — bare `prototype` → exactly one `missing_template_context` error, engine never invoked; `od_prototype` with a stubbed loaded `template_body` → guard passes, engine invoked; `user_stories` (no injects) without a template → guard does not fire. `test_run_pipeline_validation.py` (56 tests combined) green — existing ingress contract intact.

### Task 3: FE pipeline_failed handling (commit e136c16b)

- `types/index.ts`: `"pipeline_failed"` added to BOTH unions — the `StreamMessage.type` literal union (line 48) and `PipelineMessageType` (grep count exactly 2).
- `useWorkflow.ts`: new `pipeline_failed` switch case mirroring `pipeline_cancelled`'s teardown — `isRunning: false`, persisted run id cleared, agents in `agents_failed` resolved to the existing per-agent `error` state (preserving any error already set by their own `agent_error`), in-flight agents reset to idle.
- `dashboard/page.tsx`: `pipeline_failed` added to the terminal-event membership list (`pipelineTypes`) and handled adjacent to the `pipeline_complete` branch — no deliverable extraction; failure surfaced through the same chat error surface `"error"` events use (`[code:pipeline_failed]`), plus a runs-list refresh so the failed status shows.
- `npx tsc --noEmit` exits 0.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None — no placeholder values, empty-data wirings, or TODO markers introduced.

## Verification evidence

- `tests/unit/test_pipeline_failure_semantics.py` — 6/6 scenarios (a)–(f) green
- 5 characterization suites green, `tests/agents/characterization/golden/` untouched (no re-baseline)
- `tests/unit/test_run_pipeline_validation.py` green (66 passed combined in the final pass)
- `/opt/homebrew/bin/lint-imports` — Contracts: 4 kept, 0 broken
- Kernel banned-pattern gate: `grep -v '^\s*#' engine.py | grep -c "if pipeline_type =="` → 0
- `grep -c '"pipeline_failed"' engine.py` → 1; `grep -c missing_template_context websocket.py` → 1; FE greps: types=2, hook=1, page=3
- frontend `npx tsc --noEmit` → exit 0

## Success criteria

- ROADMAP Phase 13 criterion 3 TRUE: hard-failing runs terminate as a visible failure (`pipeline_failed` / `status="degraded"`) or fail fast at ingress (`missing_template_context`) — never a silent `pipeline_complete` with an empty or improvised deliverable (F3)
- Bare prototype/ppt product exposure decided and recorded: admissible, template-required, fail-fast (F3 missing item 3)

## Commits

| Task | Commit | Description |
| ---- | ------ | ----------- |
| 1 | 08114a64 | feat(13-06): pipeline_failed terminal + conditional degraded fields |
| 2 | f54944fe | feat(13-06): WS ingress guard — template-inject pipelines require template context |
| 3 | e136c16b | feat(13-06): FE pipeline_failed terminal handling |

## Self-Check: PASSED

All 6 key files exist on disk; all 3 task commits (08114a64, f54944fe, e136c16b) present in git log.
