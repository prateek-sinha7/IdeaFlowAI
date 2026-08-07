# Execution Design: Model-Graded Eval Branch (LLM-as-Judge + Report) — first example: prototype-specify

**Spec**: `specs/005-prompt-eval-scoring/spec.md`
**Plan**: `specs/005-prompt-eval-scoring/plan.md`
**Created**: 2026-07-28
**Status**: Designed
**Revision**: regenerated after `clarifications.md` Q10 (data-driven `precheck:`/`rubric:` YAML,
no per-agent Python modules) and Q11 (reaffirmed `create_runner` reuse — prompt-composition
fidelity is the primary reason, tool-calling fidelity the second)

## Build Slices

Mirrors `plan.md`'s 5-phase delivery strategy, restated as independently shippable slices. Each
slice is a complete, testable unit — later slices consume earlier slices' output types, never
their internals.

### Slice 1 — Foundation: generic driver + generic pre-check + `prototype-specify` onboarding

Stand up `model_graded/driver.py` (`GradedScenario`, `GradedRunResult`,
`run_graded_scenario_once()` — dispatches via `create_runner(agent_id, ctx)`, **reused as-is**,
not a raw chat call, per `clarifications.md` Q9/Q11), `model_graded/scenario_discovery.py`, and
the **generic**, agent-agnostic `model_graded/precheck.py::run_precheck(response, config)`. Then
prove all three by onboarding `prototype-specify`'s one scenario:
`model_graded/agents/prototype_specify/scenarios/*.yaml` carrying a `precheck:` config block
(wrapper tag, min section count, forbidden strings) and one narrow custom hook,
`nav_cross_reference_check.py` — a single function, not a full module, for the one check
(nav-target-to-page-section cross-reference) the generic config can't express. No judge, no
report yet — this slice's own "done" signal is `./tests/evals/model_graded/model-graded.sh graded <scenario-id>` (no
`--judge`) printing a correct PASS/MISS against the real agent, using **zero agent-specific
Python beyond that one ~30-line hook**. This is the concrete proof that the "zero-code
onboarding" goal (Q10) actually holds, not just a claim.

### Slice 2 — Judge

Add `model_graded/judge.py` (`JudgeVerdict`, `grade_run()`, `DEFAULT_JUDGE_THRESHOLD = 70`) and
**one shared** rubric-prompt-builder function, parameterized by a scenario's `rubric:` YAML text
block — not a per-agent `rubric.py` module lookup. `prototype-specify`'s scenario YAML gets its
`rubric:` block, written to explicitly ask the judge to assess what the generic pre-check + the
nav-check hook cannot: data realism/specificity, brief-intent match per page, template/DS usage.
Consumes Slice 1's `GradedScenario`/`GradedRunResult` — never touches `create_runner` directly.
Done signal: a scripted/mocked judge call returns a well-formed `JudgeVerdict`, plus one real
opt-in `grade_run()` call against Slice 1's scenario producing a sane score.

### Slice 3 — Report

Add `model_graded/report.py` (`append_entry()`, `summarize()`, `worst()`) and
`backend/tests/evals/reports/`. Pure data-in/data-out — no model calls in this slice's own logic
or tests. Unchanged from the prior design revision (Q10/Q11 don't touch this layer at all).

### Slice 4 — CLI wiring + iterate-loop surface

Add `model_graded/cli.py` and `./tests/evals/model_graded/model-graded.sh graded`/`./tests/evals/model_graded/model-graded.sh report` dispatch, composing
Slices 1–3 end to end, including Story 6's iterate-loop flags (`--samples`, `--worst`,
`--by system_prompt_hash`, `--target`). Done signal: the full Standard Operating Procedure
(`spec.md` §1) runs end to end via real commands, and the existing `--live`/`benchmark` commands
are verified byte-unchanged.

### Slice 5 — Verification and hardening

Full unit-test sweep across all five modules (mocked, no network), one real opt-in smoke run of
the complete loop, and a read-through of `quickstart.md`'s 8 validation scenarios against the
actual implementation.

## Component Boundaries

```
model_graded/
├── driver.py             ── owns: agent invocation via create_runner, response capture, run logging
├── scenario_discovery.py ── owns: YAML → GradedScenario loading, resolves precheck config + rubric text + optional custom hook
├── precheck.py            ── owns: GENERIC config-driven structural check (wrapper/min-sections/forbidden) — no agent-specific code
├── judge.py               ── owns: judge model call, ONE shared rubric-prompt-builder, structured-output parsing, JudgeVerdict
├── report.py              ── owns: JSONL persistence, summarize(), worst() — no model calls
├── cli.py                 ── owns: argument parsing, orchestrating driver→(precheck)→judge→report calls
└── agents/
    └── prototype_specify/
        ├── scenarios/*.yaml            ── data only: prompt, precheck: config, rubric: text
        └── nav_cross_reference_check.py ── ONE narrow custom hook — the only agent-specific code that exists
```

**Hard boundaries** (a violation here is a design bug, not a style nit):
- `driver.py` never imports `judge.py`/`report.py`/`precheck.py` — it has no idea grading or
  checking exists, only that it dispatches via `create_runner` and captures a response.
- `precheck.py` never imports anything agent-specific — it is a pure `(response, config) ->
  (bool, str)` function, generic over every possible scenario.
- `judge.py` never imports `report.py`, and its rubric-prompt-builder never branches on
  `agent_id` — it takes `rubric: str` as a plain argument, from whichever scenario called it.
- `report.py` never imports `driver.py`/`judge.py`/`precheck.py`/`build_model`/`create_runner` —
  pure data plumbing, testable with zero model/agent mocking.
- Only `cli.py` imports all of `driver.py`/`precheck.py`/`judge.py`/`report.py` — the only place
  that knows the full pipeline shape.
- Nothing in `model_graded/` imports from `common/live_scenario.py` or
  `workflow/prototype/revision/`, and nothing in those modules imports from `model_graded/`.
- `model_graded/agents/prototype_specify/` contains **exactly one** Python file
  (`nav_cross_reference_check.py`) — everything else about this agent's grading behavior lives
  in its scenario YAML. Any second agent that ends up needing more than one custom hook file is
  a signal the generic `precheck.py` config needs to grow a new built-in check, not that custom
  Python modules should become the default pattern again.

## State Transitions / Flows

**Single graded run** (Story 1 + 2 + 3):

```
GradedScenario (loaded from YAML: prompt, precheck config, rubric text, optional custom hook)
   │
   ▼ run_graded_scenario_once()  ── dispatches via create_runner(agent_id, ctx)
GradedRunResult { response, errored, tokens }
   │
   ├─ if errored=True ──► skip precheck, skip judge, skip report append (this run doesn't count)
   │
   ▼ run_precheck(response, scenario.precheck_config)   [+ scenario.precheck_module(response) if declared]
precheck_passed, precheck_reason
   │
   ▼ (if --judge) grade_run()  ── rubric-prompt-builder(system_prompt, prompt, response, scenario.rubric)
JudgeVerdict { score, passed, rationale, errored }
   │
   ▼ append_entry()
eval_report.jsonl  (+1 line, never mutates existing lines)
```

**Multi-sample loop** (Story 6, `--samples N`) and **prompt-improvement iteration** (the
Standard Operating Procedure) — unchanged from the prior design revision; see `spec.md` §1 and
the previous `design.md` for the full diagrams. Neither is affected by Q10/Q11 — they operate on
`GradedRunResult`/`JudgeVerdict`/report entries, one layer above where those decisions apply.

## Failure Modes

| Failure | Where caught | Behavior |
|---|---|---|
| Agent-under-test call fails (auth, network, timeout) | `driver.py::run_graded_scenario_once` | `GradedRunResult.errored=True`; pre-check is NOT run against a partial/garbage response; no judge call attempted; no report entry written |
| Judge model call fails (network) | `judge.py::grade_run` | `JudgeVerdict(errored=True, error_reason=...)` returned, never raised; pre-check result still reported/persisted |
| Judge returns malformed/unparseable structured output | `judge.py::grade_run` | Same as above — `errored=True` |
| `precheck.py::run_precheck` given a malformed `config` dict (missing a required key) | `scenario_discovery.py`, at load time, not at check time | Raises at load time — a scenario with a broken `precheck:` block must never silently pass/skip its check |
| Custom `precheck_module` hook itself raises | `scenario_discovery.py`/`driver.py` boundary | Treated as a check failure (`False`, the exception message as the reason), not an uncaught crash — the generic check's result and the custom hook's result are both required to pass |
| `report.append_entry()` given a dict missing a required field | `report.py::append_entry` | Raises immediately — never reaches the JSONL file |
| `--judge` requested with no usable judge credential | `cli.py`, before any model call | Fails fast, before the agent-under-test call is attempted |
| Scenario YAML references an unknown `agent_id` | `scenario_discovery.py` at load time | Raises at discovery time |
| Empty report store queried via `report`/`report --worst`/`report --by` | `report.py::summarize`/`worst` | Returns a clean "zero entries" result, never an exception |

## Observability Hooks

- **Per-run transcript**: every `run_graded_scenario_once()` call writes a full `log.txt` under
  `model_graded/logs/<run_id>/`, mirroring `common/live_scenario.py`'s existing convention.
- **Report entries are the durable observability signal** — `eval_report.jsonl` is git-tracked,
  so `git log -p` on it is a free history of every graded run and every prompt-version score
  change, without a dashboard.
- **CLI progress output**: `graded --samples N` prints a per-sample line (precheck + judge
  verdict) as it runs, plus a running tally.
- No metrics/tracing/APM integration — local dev tooling, not a running service.

## Rollback Notes

- Entirely additive: reverting is a plain revert of the implementing commit(s) — no migration,
  no data cleanup for the untouched `common/`/`workflow/` track.
- A bad `eval_report.jsonl` entry is a normal git operation on a text file, not a database
  incident.
- No feature flag needed — every action requires an explicit human-run CLI command.
- Rolling back Q10 specifically (if the generic `precheck:`/`rubric:` config ever proves
  insufficient across more than a couple of agents) is scoped narrowly: it would mean adding
  more built-in check types to `precheck.py`'s generic config, or in the worst case reopening a
  per-agent-module pattern for a *specific* agent via its `precheck_module` hook — never a
  rewrite of `driver.py`, `judge.py`, or `report.py`, which don't encode this decision at all.
