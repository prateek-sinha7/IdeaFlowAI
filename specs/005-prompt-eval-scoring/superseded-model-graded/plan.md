# Implementation Plan: Model-Graded Eval Branch (LLM-as-Judge + Report) — first example: prototype-specify

**Spec**: `specs/005-prompt-eval-scoring/spec.md`
**Created**: 2026-07-28
**Status**: Planned
**Revision**: regenerated after `clarifications.md` Q10 (data-driven rubric/pre-check) and Q11
(reaffirmed `create_runner` reuse, with prompt-composition-fidelity as the primary reason)

## Technical Context

- **Runtime**: Python (backend eval-tooling only — no frontend/TypeScript surface, no FastAPI
  route, no React component).
- **Location**: entirely inside `backend/tests/evals/`, invoked via `./tests/evals/eval.sh`
  (the existing dev-CLI entry point). Follows that folder's existing precedent of
  non-pytest-driven, directly-executable scripts (`live_benchmark.py`, `validate_scenario.py`).
- **Model access**: `app/agents/model_factory.py::build_model()` — the same provider
  abstraction already used everywhere else in the harness (Anthropic/Bedrock local-dev default,
  Mistral opt-in per the withdrawn spec `004-groq-eval-provider`). No new SDK dependency.
- **Agent invocation**: `agents/factory.py::create_runner(agent_id, ctx)` — **reused as-is, not
  bypassed** (`clarifications.md` Q9, reaffirmed Q11). This is the load-bearing decision this
  revision of the plan is built around: `create_runner`'s `_compose_system_prompt`/
  `_compose_injection` assemble the *actual* production system prompt (injected
  template/design-system content, guardrails, skills, hooks, constitution, then the `AGENT.md`
  body) — `prototype-specify`'s own frontmatter declares `injects: [template, design_system,
  images]`, so its `AGENT.md` body alone is not what ships. A raw `build_model().invoke(...)`
  call would grade a different, incomplete prompt. `create_runner` also gives future tool-using
  agents onboarded onto this branch real tool execution, without which their "correct result"
  can't be verified at all.
- **Persistence**: flat JSON Lines file (`backend/tests/evals/reports/eval_report.jsonl`),
  git-tracked. No PostgreSQL involvement — this is dev-tooling data, not application data.
- **Deployment**: none — this ships as backend repo code only; nothing runs in production, no
  AWS/infra changes.

## Architecture Decisions

| Decision | Rationale |
|---|---|
| New standalone `backend/tests/evals/model_graded/` package, sharing no modified code with `common/live_scenario.py` or `workflow/prototype/revision/` | Explicit user direction: a new evaluation *branch*, not an extension of the existing file-editing-shaped driver. Keeps the two tracks independently runnable/understandable — spec §3.2. |
| `run_graded_scenario_once()` dispatches via `create_runner(agent_id, ctx)` — **not** a raw chat-completion call | `clarifications.md` Q9 + Q11: (1) tool-calling fidelity for future agents, (2) prompt-composition fidelity — `create_runner` is the only path that reproduces the actual injected/composed production system prompt. Bypassing it would require re-implementing that composition logic inside the grader, which is *more* new code, not less. |
| Deterministic pre-check is **generic and YAML-configured** (`precheck.py::run_precheck(response, config)`), not a required Python module per agent | `clarifications.md` Q10 — a wrapper-tag check, min-section-count check, and forbidden-substring check cover the common case for any text-completion agent as pure config. Onboarding a new agent needs zero new Python for the common case. |
| Judge rubric is **plain text/markdown per scenario**, fed into one shared prompt-builder in `judge.py` — not a per-agent `rubric.py` module | Same Q10 resolution — a new agent's grading criteria is a `rubric:` YAML block, not a new Python file. |
| An **optional** per-scenario custom precheck hook (e.g. `prototype-specify`'s `nav_cross_reference_check.py`) remains available | Q10's escape hatch — some checks (nav-target-to-page-section cross-referencing) need real parsing the generic config can't express; this is scoped narrowly (one function, one check), not a fallback to a full custom module. |
| One folder per agent under `model_graded/agents/<agent>/` (`scenarios/*.yaml` carrying `precheck:` config + `rubric:` text; an optional custom hook file) | Onboarding a second agent is a sibling folder with a scenario YAML — still true after Q10, just with less Python inside it than originally planned. |
| Judge default: same `build_model()` fallback chain as the agent under test, no forced distinct provider; override via `--judge-provider`/`--judge-model` | Keeps `--judge` frictionless on a machine with only `ANTHROPIC_API_KEY`; self-preference bias is documented and mitigable, not blocking — `clarifications.md` Q1. |
| Judge pass/fail threshold: single global constant (`DEFAULT_JUDGE_THRESHOLD = 70`), overridable per-run, not per-agent | Keeps the report's "pass" meaning consistent across agents — `clarifications.md` Q3. |
| Report: single shared `eval_report.jsonl`, agent-agnostic schema, full response inlined | The driver's deliverable is a raw response with no separate artifact file to reference — spec §3.2 item 5 (renumbered), Story 3. |
| New `./tests/evals/model_graded/model-graded.sh graded`/`./tests/evals/model_graded/model-graded.sh report` subcommands, not a flag on the existing `--live`/`benchmark` commands | Keeps the two tracks' CLI surfaces as separable as their code — spec Story 4. |
| `--samples N`, `report --worst N`, `report --by system_prompt_hash [--target T]` | The explicit iterate-on-the-prompt loop the user asked for (create dataset → grade → feedback → improve → repeat) — `clarifications.md` Q5/Q6/Q7, spec Story 6. All pure reads/loops over Phases 1–3's output — no new model-call integration. |
| Ship exactly one `prototype-specify` scenario in this spec | Mirrors the revision track's own precedent — `clarifications.md` Q4. |

## Delivery Strategy

Five phases, dependency-ordered:

**Phase 1 — Driver + scenario discovery + generic pre-check**
Stand up `model_graded/driver.py` (`GradedScenario`, `GradedRunResult`,
`run_graded_scenario_once()` — dispatches via `create_runner`, no filesystem
seeding/read-back), `model_graded/scenario_discovery.py` (loads YAML, resolves each scenario's
`precheck:` config and optional custom hook, `rubric:` text), and the **generic**
`model_graded/precheck.py::run_precheck(response, config)`. Prove it by onboarding
`prototype-specify`'s one scenario: a scenario YAML with a `precheck:` block covering wrapper
tag / min section count / forbidden strings, plus its one custom hook
(`nav_cross_reference_check.py`) for the nav-target cross-reference. Done signal: `./tests/evals/model_graded/model-graded.sh graded <id>` (no `--judge`) prints a correct PASS/MISS against the real agent, with zero
agent-specific Python beyond that one narrow hook.

**Phase 2 — Judge**
Add `model_graded/judge.py` (`JudgeVerdict`, `grade_run()`, `DEFAULT_JUDGE_THRESHOLD`) and its
**one shared** rubric-prompt-builder, parameterized by a scenario's `rubric:` text (not a
per-agent module lookup). `prototype-specify`'s scenario YAML gets its `rubric:` block. Testable
in isolation with a scripted/mocked model plus one real opt-in run.

**Phase 3 — Report**
Add `model_graded/report.py` (`append_entry()`, `summarize()`, `worst()`). Pure data plumbing,
no model calls in this phase's own logic or tests.

**Phase 4 — CLI wiring**
Add `model_graded/cli.py` and the `graded`/`report` subcommand dispatch in `./tests/evals/eval.sh`. Verify
the existing `--live`/`benchmark` commands are byte-unchanged.

**Phase 5 — Iterative loop support (Story 6)**
Add `--samples N` to `graded`; add `report.py::worst()` wiring to `report --worst N`; extend
`summarize()` with `group_by="system_prompt_hash"` and `target`, wired to
`report --by system_prompt_hash [--target T]`. Pure read/loop logic on top of Phases 1–4.

Each phase lands as its own commit/PR-sized unit; Phase 1 alone already delivers a working
(ungraded) `prototype-specify` scenario runner using only generic, agent-agnostic code plus one
34-ish-line custom hook — a strong signal the "zero-code onboarding" goal (Q10) actually holds
before investing in Phases 2–5.

## File Changes

| File | Action | Purpose |
|------|--------|---------|
| `backend/tests/evals/model_graded/__init__.py` | Create | Package marker |
| `backend/tests/evals/model_graded/driver.py` | Create | `GradedScenario`, `GradedRunResult`, `run_graded_scenario_once()` — dispatch via `create_runner` |
| `backend/tests/evals/model_graded/scenario_discovery.py` | Create | Discovers `model_graded/agents/*/scenarios/*.yaml`; resolves `precheck:` config, optional custom hook, `rubric:` text |
| `backend/tests/evals/model_graded/precheck.py` | Create | **Generic**, agent-agnostic `run_precheck(response, config)` — no agent-specific code |
| `backend/tests/evals/model_graded/judge.py` | Create | `JudgeVerdict`, `grade_run()`, `DEFAULT_JUDGE_THRESHOLD`, one shared rubric-prompt-builder |
| `backend/tests/evals/model_graded/report.py` | Create | `append_entry()`, `summarize()`, `worst()`, JSONL helpers |
| `backend/tests/evals/model_graded/cli.py` | Create | `graded`/`report` subcommand implementations, including `--samples`/`--worst`/`--by`/`--target` |
| `backend/tests/evals/model_graded/agents/__init__.py` | Create | Package marker |
| `backend/tests/evals/model_graded/agents/prototype_specify/__init__.py` | Create | Package marker |
| `backend/tests/evals/model_graded/agents/prototype_specify/scenarios/*.yaml` | Create | The one v1 scenario — brief, `precheck:` config, `rubric:` text, optional `min_pages`/`precheck_module` |
| `backend/tests/evals/model_graded/agents/prototype_specify/nav_cross_reference_check.py` | Create | The one custom precheck hook (nav-target-to-page-section cross-reference) |
| `backend/tests/evals/model_graded/logs/` | Create (dir) | Per-run transcript folders |
| `backend/tests/evals/reports/eval_report.jsonl` | Create (on first run) | Persistent append-only report store |
| `backend/tests/evals/reports/.gitkeep` | Create | Keeps the directory tracked before the first run |
| `./tests/evals/eval.sh` | Modify (additive) | Add `graded [--judge] [--samples] [--judge-provider] [--judge-model] [--judge-threshold]` and `report [--last] [--worst] [--by] [--target]` subcommand dispatch |
| `backend/tests/unit/test_model_graded_driver.py` | Create | Driver unit tests (mocked `create_runner`) |
| `backend/tests/unit/test_model_graded_precheck.py` | Create | Generic pre-check unit tests against config fixtures |
| `backend/tests/unit/test_prototype_specify_nav_check.py` | Create | Custom hook unit tests |
| `backend/tests/unit/test_model_graded_judge.py` | Create | Judge unit tests (mocked `build_model`, no network) |
| `backend/tests/unit/test_model_graded_report.py` | Create | Report JSONL round-trip, `worst()`, `summarize(group_by=..., target=...)` unit tests |

No changes to `common/live_scenario.py`, `workflow/prototype/revision/`, `live_benchmark.py`,
`agents/factory.py`, `DeepAgentRunner`, or any PostgreSQL schema — confirmed zero-diff by design.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Building a new branch rather than extending `workflow/` — more surface area than a pure grading add-on | High (known going in — deliberate tradeoff) | Medium | Phased delivery; Phase 1 alone is a complete checkpoint; borrows proven conventions (log-folder shape, YAML format, opt-in cost) without coupling code |
| Judge self-preference bias | Medium | Medium | `provider=`/`model=` override always available (`clarifications.md` Q1) |
| Judge scoring non-determinism | Medium | Low | Low temperature where supported; Story 6's `--samples`/aggregate view is the intended way to read scores |
| Structured-output parse failures from the judge | Low | Low | `JudgeVerdict.errored`/`error_reason` — never crashes the run or corrupts the report |
| Report file grows unbounded (git-tracked JSONL, full responses inlined) | Low | Low | Out of scope for v1 rotation; flagged for a future spec |
| Generic `precheck:` YAML config proves insufficiently expressive for a future agent beyond `prototype-specify` | Medium | Low | The `precheck_module` custom-hook escape hatch (Q10) exists precisely for this; expected to be used sparingly, not as the default path |
| A raw-chat-call implementation is tempting later as a "simpler" refactor | Low | Medium (would silently break prompt fidelity) | Documented explicitly in `clarifications.md` Q9/Q11 and in this plan's Technical Context — `prototype-specify`'s `injects` frontmatter is the concrete, checkable reason `create_runner` must stay |
