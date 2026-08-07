# Tasks: Model-Graded Eval Branch (LLM-as-Judge + Report) — first example: prototype-specify

**Spec**: `specs/005-prompt-eval-scoring/spec.md`
**Plan**: `specs/005-prompt-eval-scoring/plan.md`
**Design**: `specs/005-prompt-eval-scoring/design.md`
**Revision**: regenerated after `clarifications.md` Q10 (data-driven `precheck:`/`rubric:` YAML)
and Q11 (reaffirmed `create_runner` reuse). Supersedes the prior task list's T4/T7
(`precheck.py`/`rubric.py` as required per-agent Python modules).

---

## Task T1 — Package skeleton for `model_graded/`

**Phase**: 1
**Priority**: P1
**Depends on**: none
**Traces to**: Spec §3.2 item 1, §3.5

### Description
Create `backend/tests/evals/model_graded/__init__.py` and
`backend/tests/evals/model_graded/agents/__init__.py` as empty package markers. No logic —
establishes the standalone package location confirmed in `spec.md` §3.2.

### Acceptance
- [x] `backend/tests/evals/model_graded/` and `backend/tests/evals/model_graded/agents/` exist
      and are importable Python packages.
- [x] No existing file under `common/` or `workflow/` is modified.

### Tests
- [x] N/A (no logic yet) — covered indirectly by T3's import succeeding.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/common/coding-style.md`

---

## Task T2 — `GradedScenario` / `GradedRunResult` dataclasses + `run_graded_scenario_once()`

**Phase**: 1
**Priority**: P1
**Depends on**: T1
**Traces to**: Spec Story 1 Scenario 1; `clarifications.md` Q9, Q11; `data-model.md`
§Entities; `design.md` Slice 1

### Description
Implement `model_graded/driver.py`. Define `GradedScenario` (fields per `data-model.md`: `id`,
`agent_id`, `prompt`, `min_pages`, `design_md`, `precheck_config: dict`,
`precheck_module: Callable | None`, `rubric: str`, `logs_dir`) and `GradedRunResult`
(`scenario_id`, `agent_id`, `response`, `errored`, `error_reason`, `tokens_in`, `tokens_out`,
`run_dir`) — note `GradedRunResult` no longer carries `precheck_passed`/`precheck_reason`
itself; the driver's job is dispatch and capture only (§ Component Boundaries, `design.md`
Slice 1) — pre-check runs as a separate step (T5) called by `cli.py`, not baked into the driver.

Implement `run_graded_scenario_once(scenario, *, provider=None, model=None) -> GradedRunResult`:
builds an `AgentContext` from `scenario.prompt`, calls **`create_runner(scenario.agent_id,
ctx)`** — reused as-is, per `clarifications.md` Q9/Q11 (do **not** call `build_model()`/
`model.invoke()` directly; the composed production system prompt — including
`prototype-specify`'s `injects: [template, design_system, images]` — is only produced by
`create_runner`'s `_compose_system_prompt`) — streams the response via `astream_events` (same
event handling as `common/live_scenario.py` — chunk/tool/error/usage), writes a full transcript
to `model_graded/logs/<run_id>/log.txt`, and returns the captured raw response text.

Handle the `runner_error` case per `design.md`'s Failure Modes table: mark `errored=True`.

### Acceptance
- [x] `run_graded_scenario_once()` dispatches via `create_runner` — verify by asserting the
      composed system prompt used by a mocked `create_runner` call includes injected
      content beyond the raw `AGENT.md` body (proves composition fidelity, not just that
      `create_runner` was called).
- [x] `run_id` format matches `<yymmddhhmmss>-graded-<scenario_id>-<uuid8>`.
- [x] A `runner_error` event produces `errored=True`.
- [x] `common/live_scenario.py` is untouched.
- [x] `driver.py` contains no import of `judge.py`, `report.py`, or `precheck.py` (Component
      Boundaries).

### Tests
- [x] Unit: mocked `create_runner`/scripted model — assert `GradedRunResult.response` captures
      the streamed text correctly.
- [x] Unit: simulated `error` event → `errored=True`.
- [x] Unit: token accumulation matches summed `usage` events.
- [x] Unit: static import-graph check (or a simple `ast`-based test) asserting `driver.py`
      imports none of `judge`, `report`, `precheck`.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/patterns.md`
- `.apex/rules/python/testing.md`
- `.apex/rules/common/testing.md`

---

## Task T3 — `model_graded/scenario_discovery.py`

**Phase**: 1
**Priority**: P1
**Depends on**: T2
**Traces to**: Spec Story 1 Scenario 2; `clarifications.md` Q10; `design.md` Component
Boundaries

### Description
Implement discovery of every `model_graded/agents/*/scenarios/*.yaml` into `GradedScenario`
instances. For each scenario YAML, parse: `id`, `agent_id`, `prompt`/`prompt_file`,
`min_pages` (optional, default 4), a **required** `precheck:` block (`wrapper: str`,
`min_sections: int`, `section_pattern: str`, `forbidden: list[str]`) stored as
`precheck_config`, an **optional** `precheck_module: <dotted.path>` resolved to a callable
(`precheck_module`), and a **required** `rubric:` text block stored verbatim as `rubric: str`.

Validate at load time (fail loud): scenario `id` must match filename stem; `agent_id` must
resolve via `agents/registry.py::get_agent_by_id`; `precheck:` block must have all four
required keys; `min_pages` (if present) must be a positive integer; `precheck_module`, if
declared, must resolve to an importable callable. Kept as a separate module from
`common/scenario_discovery.py` (not extended/imported).

### Acceptance
- [x] Discovers every YAML under `model_graded/agents/*/scenarios/`.
- [x] Scenario id globally unique across the branch (raise on collision).
- [x] `id`/filename mismatch raises.
- [x] Unknown `agent_id` raises.
- [x] Missing/malformed `precheck:` block raises (e.g. missing `wrapper` key).
- [x] Missing `rubric:` block raises.
- [x] Invalid `min_pages` raises.
- [x] Unresolvable `precheck_module` dotted path raises.
- [x] Zero changes to `common/scenario_discovery.py`.

### Tests
- [x] Unit: load a temp-dir fixture with 2 valid scenario YAMLs → both discovered.
- [x] Unit: id/filename mismatch → raises.
- [x] Unit: unknown `agent_id` → raises.
- [x] Unit: `precheck:` block missing `forbidden` key → raises.
- [x] Unit: `precheck_module: nonexistent.module:fn` → raises.
- [x] Unit: valid scenario with no `precheck_module` → `precheck_module` field is `None`.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/patterns.md`
- `.apex/rules/python/testing.md`

---

## Task T4 — `model_graded/precheck.py`: generic, config-driven pre-check

**Phase**: 1
**Priority**: P1
**Depends on**: T2
**Traces to**: Spec Story 1 Scenario 3; `clarifications.md` Q10; `design.md` Component
Boundaries ("this module has no idea `prototype-specify` exists")

### Description
Implement `run_precheck(response: str, config: dict) -> tuple[bool, str]` — **fully generic,
zero agent-specific code**. Given `config` (`wrapper`, `min_sections`, `section_pattern`,
`forbidden`):
1. Response is wrapped in `config["wrapper"]` (e.g. `<spec>...</spec>`) with no
   preamble/postamble text.
2. Count of lines matching `config["section_pattern"]` (a regex, e.g. `^### `) is ≥
   `config["min_sections"]` (or the scenario's `min_pages` override — resolved in
   `scenario_discovery.py`, passed through as `min_sections` by the time this function sees it).
3. None of `config["forbidden"]` appear (case-insensitive substring match).

Returns `(True, reason)` if all three pass, `(False, reason)` naming the first failing check
otherwise.

### Acceptance
- [x] `run_precheck()` takes no `agent_id` parameter and makes no reference to
      `prototype-specify` or any other agent name anywhere in its implementation.
- [x] Returns `(True, ...)` on a config + response fixture that satisfies all three checks.
- [x] Returns `(False, ...)` on each of: missing wrapper, under `min_sections`, a forbidden
      string present — each with a distinguishable reason string.
- [x] Makes zero model calls (works with no network/credentials configured).

### Tests
- [x] Unit: generic fixture (not `prototype-specify`-specific) — known-good config+response →
      PASS.
- [x] Unit: 3 known-bad fixtures (one per failure mode) → each MISS with a specific reason.
- [x] Unit: a second, unrelated hypothetical config (different wrapper tag, different section
      pattern) also works correctly — proves genericity, not just that it happens to work for
      one shape.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/patterns.md`
- `.apex/rules/python/testing.md`

---

## Task T5 — Onboard `prototype-specify`: scenario YAML + custom nav-check hook

**Phase**: 1
**Priority**: P1
**Depends on**: T3, T4
**Traces to**: Spec Story 1 Scenario 2 & 3; `clarifications.md` Q2, Q4, Q10

### Description
Create `model_graded/agents/prototype_specify/scenarios/<id>.yaml` — exactly **one** scenario
(`clarifications.md` Q4): a realistic, multi-page brief, `agent_id: prototype-specify`, a
`precheck:` block (`wrapper: "<spec>"`, `min_sections: 4` or higher per the brief's implied app
type, `section_pattern` tuned to `AGENT.md`'s `### {Page Name}` heading format, `forbidden:
["Lorem ipsum", "TBD", "Coming soon", "future expansion", "placeholder", "stub"]`), a `rubric:`
text block (per T7's requirements), and `precheck_module:
model_graded.agents.prototype_specify.nav_cross_reference_check:check`.

Create `model_graded/agents/prototype_specify/nav_cross_reference_check.py` — **one function**,
`check(response: str) -> tuple[bool, str]`: parses the "Pages & Navigation" table and every
`### {Page Name}` section heading, and verifies every nav target referenced in the table has a
corresponding page section. This is the **only** agent-specific Python file for this agent
(`design.md` Component Boundaries).

### Acceptance
- [x] Exactly one scenario YAML exists under `prototype_specify/scenarios/`.
- [x] The scenario's `precheck:` block alone (via T4's generic `run_precheck`) correctly
      PASSes/MISSes wrapper-tag, section-count, and forbidden-string fixtures.
- [x] `nav_cross_reference_check.check()` returns `(True, reason)` on a fixture with all nav
      targets resolved, `(False, reason)` on a fixture with a dangling nav target.
- [x] `model_graded/agents/prototype_specify/` contains exactly one `.py` file besides
      `__init__.py` (verify via a directory listing in the test, or a lint-style check).

### Tests
- [x] Unit: 1 known-good `<spec>` fixture → both the generic precheck AND the custom hook PASS.
- [x] Unit: fixture with a dangling nav target → generic precheck PASSes, custom hook MISSes
      (proves the two checks are independent, per `design.md`'s failure-mode table requiring
      both to pass).
- [x] Unit: fixture missing the `<spec>` wrapper → generic precheck MISSes (custom hook not
      required to also catch this — division of labor).

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/patterns.md`
- `.apex/rules/python/testing.md`

---

## Task T6 — Slice 1 integration check: free sanity run

**Phase**: 1
**Priority**: P1
**Depends on**: T2, T3, T4, T5
**Traces to**: Spec Story 4 AC1 (no-`--judge` path); `design.md` Slice 1 done-signal

### Description
Verification task, no new module. Confirm `run_graded_scenario_once()` +
`scenario_discovery.py` + T4's generic `precheck.py` + T5's scenario/custom hook compose
correctly end to end via an offline (scripted-model) integration test. The real-model smoke run
is a manual, opt-in step the user runs themselves.

### Acceptance
- [x] An offline integration test exercises: discover scenario → run driver (scripted model) →
      run generic precheck → run custom hook → combined pass/fail.
- [x] Confirmed no report entry or judge call occurs anywhere in this path.

### Tests
- [x] Integration: `tests/unit/test_model_graded_slice1_integration.py` — full pipeline,
      scripted model, asserts the combined precheck result is the AND of the generic check and
      the custom hook.

### guardrailRefs
- `.apex/rules/python/testing.md`
- `.apex/rules/common/testing.md`

---

## Task T7 — `JudgeVerdict` + `grade_run()` + shared rubric-prompt-builder

**Phase**: 2
**Priority**: P1
**Depends on**: T2
**Traces to**: Spec Story 2 AC1–3; `clarifications.md` Q1, Q3, Q10; `data-model.md` §Entities

### Description
Implement `model_graded/judge.py`. Define `JudgeVerdict` (`score: int`, `passed: bool`,
`rationale: str`, `errored: bool`, `error_reason: str | None`) and `DEFAULT_JUDGE_THRESHOLD =
70`.

Implement **one shared** `build_rubric_prompt(system_prompt: str, prompt: str, response: str,
rubric: str, precheck_reason: str) -> str` — takes the scenario's `rubric:` text as a plain
string, does not look up any per-agent module (`clarifications.md` Q10). This function must
work identically regardless of which agent's scenario called it.

Implement `grade_run(scenario: GradedScenario, result: GradedRunResult, precheck_reason: str,
*, provider=None, model=None, threshold=None) -> JudgeVerdict`: builds the judge model via
`build_model(model, provider=provider)` — default resolves through the same fallback chain as
any other unadorned `build_model()` call (`clarifications.md` Q1); calls
`build_rubric_prompt(...)` with `scenario.rubric`; requests structured output; parses into
`JudgeVerdict`. On any exception — catch, return `JudgeVerdict(errored=True,
error_reason=str(e))`; never raise.

### Acceptance
- [x] `build_rubric_prompt()` takes `rubric: str` as a parameter — no per-agent import, no
      `agent_id`-keyed dispatch inside `judge.py`.
- [x] Default judge provider path is byte-identical in provider-selection terms to any other
      unadorned `build_model()` call.
- [x] `passed = score >= (threshold or DEFAULT_JUDGE_THRESHOLD)`.
- [x] Simulated network failure and malformed structured output both produce
      `JudgeVerdict(errored=True, ...)`, never an unhandled exception.
- [x] `judge.py` imports nothing from `report.py`.

### Tests
- [x] Unit: `build_rubric_prompt()` called with two *different* fabricated `rubric` strings
      produces two prompts differing only in the rubric content — proves genericity.
- [x] Unit: mocked `build_model` returning a scripted structured-output response → correct
      `JudgeVerdict` fields.
- [x] Unit: mocked `build_model` raising → `errored=True`, function does not raise.
- [x] Unit: mocked structured-output parse failure → `errored=True`.
- [x] Unit: `threshold` override changes `passed` boundary correctly.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/patterns.md`
- `.apex/rules/python/security.md`
- `.apex/rules/python/testing.md`

---

## Task T8 — `prototype-specify`'s `rubric:` YAML text

**Phase**: 2
**Priority**: P1
**Depends on**: T5, T7
**Traces to**: Spec Story 2 AC1, AC3; Background §1 "LLM-as-judge for everything else";
`clarifications.md` Q10

### Description
Write the `rubric:` text block inside `prototype-specify`'s scenario YAML (created in T5,
filled in here) — plain prose criteria, not code. Per spec §3.2 item 4: explicitly ask the
judge to assess data realism/specificity, brief-intent match per page, and sensible
template/design-system usage — and explicitly instruct the judge **not** to re-score what the
generic pre-check + custom nav-check hook already cover (wrapper tags, section count, forbidden
strings, nav cross-references), to avoid double-penalizing the same defect.

### Acceptance
- [x] `rubric:` text explicitly lists what to focus on (realism/intent-match/DS-usage) and what
      not to re-check (structure, already covered).
- [x] `build_rubric_prompt()` (T7) called with this scenario's `rubric` text produces a prompt
      containing the rubric content verbatim.

### Tests
- [x] Unit: `build_rubric_prompt(..., rubric=<this scenario's rubric text>, ...)` — plain
      string-containment assertion, no model call needed.

### guardrailRefs
- `.apex/rules/python/testing.md`

---

## Task T9 — Slice 2 integration check: real judge smoke run (manual, opt-in)

**Phase**: 2
**Priority**: P2
**Depends on**: T7, T8
**Traces to**: `design.md` Slice 2 done-signal

### Description
Not automated in CI — per this repo's standing rule, any real-model run is manual, triggered by
the user themselves. Documented checklist step in `quickstart.md`: run `grade_run()` once for
real against Slice 1's scenario output and confirm score/rationale are sane.

### Acceptance
- [ ] Documented in `quickstart.md` — no code changes required by this task itself.

### Tests
- [ ] N/A — manual verification only.

### guardrailRefs
- (none)

---

## Task T10 — `report.py`: `append_entry()`

**Phase**: 3
**Priority**: P1
**Depends on**: T2, T7
**Traces to**: Spec Story 3 AC1–3; `data-model.md` §Report entry schema

### Description
Unchanged from the prior design revision (Q10/Q11 don't affect `report.py`). Implement
`append_entry(entry: dict) -> None` — validates all required fields present, raises on any
missing field, appends exactly one `\n`-terminated JSON line to
`backend/tests/evals/reports/eval_report.jsonl`, creates file/dir if absent, never
rewrites/truncates. `system_prompt_hash` computed fresh every call.

### Acceptance
- [x] Missing required field → raises before any write.
- [x] Valid entry → exactly one new line appended; prior lines byte-identical afterward.
- [x] File/directory auto-created on first call.
- [x] `report.py` imports nothing from `driver.py`, `judge.py`, `precheck.py`, `build_model`,
      or `create_runner`.

### Tests
- [x] Unit: missing-field dict → raises, file unchanged.
- [x] Unit: two sequential valid calls → 2 lines, first unchanged after the second.
- [x] Unit: `system_prompt_hash` differs when the on-disk `AGENT.md` fixture content differs.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/security.md`
- `.apex/rules/python/testing.md`
- `.apex/rules/common/testing.md`

---

## Task T11 — `report.py`: `summarize()` and `worst()`

**Phase**: 3
**Priority**: P1
**Depends on**: T10
**Traces to**: Spec Story 5 AC1–3; Story 6 AC2–3; `clarifications.md` Q6, Q7

### Description
Unchanged from the prior design revision. `summarize(entries, *,
group_by="agent_id"|"scenario_id"|"system_prompt_hash", last_n=None, target=None) -> dict` and
`worst(entries, n) -> list[dict]`, both pure functions over already-loaded entries.

### Acceptance
- [x] Empty `entries` → clean "zero entries" result, no exception.
- [x] `worst(entries, n)` returns exactly `n` entries (or fewer), ascending by `judge_score`,
      ungraded entries excluded.
- [x] `summarize(group_by="system_prompt_hash")` groups correctly, chronological order.
- [x] `target` given → each row includes a met/not-met indicator.
- [x] `last_n` filters before all other computation.

### Tests
- [x] Unit: empty list → zero-entries result.
- [x] Unit: `worst()` ordering + exclusion of ungraded entries.
- [x] Unit: `summarize(group_by="system_prompt_hash", target=90)` against a 2-hash fixture.
- [x] Unit: `last_n` filtering changes the result vs. unfiltered.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/patterns.md`
- `.apex/rules/python/testing.md`

---

## Task T12 — `model_graded/cli.py`: `graded` subcommand (single run + `--judge`)

**Phase**: 4
**Priority**: P1
**Depends on**: T2, T3, T4, T7, T10
**Traces to**: Spec Story 4 AC1, AC3; `design.md` Component Boundaries

### Description
Implement `graded <scenario-id> [--judge] [--judge-provider P] [--judge-model M]
[--judge-threshold T]`. Resolve the scenario via `scenario_discovery.py`, call
`run_graded_scenario_once()`, then `run_precheck(response, scenario.precheck_config)` and, if
`scenario.precheck_module` is set, also call it — combined pass/fail is the AND of both. If
`--judge`: verify a usable judge credential resolves **before** the driver call; then
`grade_run()` + `report.append_entry()`. Without `--judge`: print driver + combined precheck
result only, no report entry.

### Acceptance
- [x] Bare `graded <id>`: agent call + generic precheck + custom hook (if any), prints
      PASS/MISS, zero report entries.
- [x] `graded <id> --judge`: agent call + precheck + judge call + exactly one report entry.
- [x] `--judge` with no usable credential: errors before the agent-under-test call.
- [x] `--judge-provider`/`--judge-model`/`--judge-threshold` pass through to `grade_run()`.

### Tests
- [x] CLI-integration: bare `graded` path, mocked driver — no report write.
- [x] CLI-integration: `--judge` path, mocked driver+judge — exactly one `append_entry()` call.
- [x] Unit: missing judge credential → driver invocation count = 0.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/security.md`
- `.apex/rules/python/testing.md`
- `.apex/rules/common/security.md`

---

## Task T13 — `model_graded/cli.py`: `report` subcommand

**Phase**: 4
**Priority**: P2
**Depends on**: T11, T12
**Traces to**: Spec Story 5 AC1–3

### Description
Unchanged from the prior design revision. `report [--last N]` — loads `eval_report.jsonl`,
calls `summarize()`, prints the aggregate result.

### Acceptance
- [x] `report` with no flags summarizes the full file.
- [x] `report --last N` summarizes only the most recent N entries.
- [x] Nonexistent/empty file → "zero entries," no crash.

### Tests
- [x] CLI-integration: fixture JSONL → correct printed summary.
- [x] CLI-integration: missing file → clean zero-entries output.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/testing.md`

---

## Task T14 — Wire `graded`/`report` into `./tests/evals/eval.sh`

**Phase**: 4
**Priority**: P1
**Depends on**: T12, T13
**Traces to**: Spec Story 4 AC2

### Description
Unchanged from the prior design revision. Additive-only dispatch for `graded`/`report` in
`./tests/evals/eval.sh`.

### Acceptance
- [x] Both commands work end to end.
- [x] `git diff ./tests/evals/eval.sh` shows only additive lines.
- [x] Existing `--live`/`benchmark` commands produce byte-identical output to before this spec.

### Tests
- [x] Regression: existing commands' output/exit-code parity with pre-change behavior.

### guardrailRefs
- `.apex/rules/common/git-workflow.md`
- `.apex/rules/python/testing.md`

---

## Task T15 — `--samples N` on `graded`

**Phase**: 5
**Priority**: P1
**Depends on**: T12
**Traces to**: Spec Story 6 AC1

### Description
Unchanged from the prior design revision. Extend `graded` with `--samples N` (default 1) —
loops the driver→precheck(→judge→report) pipeline N times, independent report entries, progress
output as it runs.

### Acceptance
- [x] `--samples N` (with `--judge`) → exactly N report entries.
- [x] `--samples N` (without `--judge`) → N precheck runs, zero report entries.
- [x] Default behaves identically to `--samples 1`.
- [x] Per-sample and final-summary output printed as the loop progresses.

### Tests
- [x] Unit/CLI-integration: `--samples 5 --judge` → exactly 5 `append_entry()` calls, 5
      distinct `run_id`s.
- [x] Unit: `--samples` omitted vs. `--samples 1` → identical call pattern.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/testing.md`

---

## Task T16 — `report --worst N` / `report --by system_prompt_hash [--target T]`

**Phase**: 5
**Priority**: P1
**Depends on**: T11, T13
**Traces to**: Spec Story 6 AC2, AC3; `clarifications.md` Q6, Q7

### Description
Unchanged from the prior design revision. `--worst N` calls `worst()` and prints full entries;
`--by system_prompt_hash [--target T]` calls `summarize(group_by="system_prompt_hash",
target=T)` and prints the chronological breakdown with met/not-met labels.

### Acceptance
- [x] `--worst N` prints exactly `worst()`'s return, no synthesis.
- [x] `--by system_prompt_hash` prints one row per hash, chronological.
- [x] `--target T` adds a clear met/not-met indicator.
- [x] None of these flags trigger a model call, re-run, or write to `AGENT.md`/the report file.

### Tests
- [x] CLI-integration: `--worst 3` on a fixture → 3 lowest, correctly ordered.
- [x] CLI-integration: `--by system_prompt_hash --target 90` on a 2-hash fixture → correct
      averages and labels.
- [x] Unit: zero calls to `build_model`/`create_runner`/`append_entry` in this command's path.

### guardrailRefs
- `.apex/rules/python/coding-style.md`
- `.apex/rules/python/testing.md`
- `.apex/rules/common/testing.md`

---

## Task T17 — Full Standard Operating Procedure walkthrough (manual, opt-in verification)

**Phase**: 5
**Priority**: P2
**Depends on**: T14, T15, T16
**Traces to**: Spec §1 "Standard Operating Procedure"; `quickstart.md` §Validation Scenarios

### Description
Unchanged from the prior design revision. Manual checklist: run `graded --judge --samples N`,
read `report --worst N`, edit `AGENT.md`, re-run, confirm `report --by system_prompt_hash
--target T` shows the expected before/after.

### Acceptance
- [ ] All 8 validation scenarios in `quickstart.md` confirmed manually against the real
      implementation.

### Tests
- [ ] N/A — manual verification only.

### guardrailRefs
- (none)

---

## Coverage Check (Step 3b)

| Plan/Data-Model item | Implementation task | Verification task |
|---|---|---|
| `GradedScenario`/`GradedRunResult`/driver (via `create_runner`) | T2 | T2 (unit), T6 (integration) |
| `scenario_discovery.py` (incl. `precheck:`/`rubric:`/`precheck_module` parsing) | T3 | T3 (unit) |
| `precheck.py` — generic, config-driven | T4 | T4 (unit) |
| `prototype_specify` onboarding (scenario YAML + one custom hook) | T5 | T5 (unit), T6 (integration) |
| `JudgeVerdict`/`grade_run()`/shared rubric-prompt-builder | T7 | T7 (unit), T9 (manual) |
| `prototype_specify`'s `rubric:` YAML text | T8 | T8 (unit) |
| `report.py::append_entry()` | T10 | T10 (unit) |
| `report.py::summarize()`/`worst()` | T11 | T11 (unit) |
| `cli.py graded` (incl. combined precheck + custom hook dispatch) | T12 | T12 (unit) |
| `cli.py report` | T13 | T13 (unit) |
| `./tests/evals/eval.sh` wiring + backward-compat | T14 | T14 (regression) |
| `--samples` (Story 6) | T15 | T15 (unit) |
| `report --worst`/`--by`/`--target` (Story 6) | T16 | T16 (unit) |
| Full loop / SOP | — | T17 (manual, all 8 quickstart scenarios) |
| `create_runner` reuse (Q9/Q11) — composition fidelity | T2 | T2's mocked-composition-content assertion |
| Zero-code onboarding (Q10) | T4, T5, T7, T8 | T5's "exactly one `.py` file" directory-listing assertion |

No contract in `contracts/api-contract.md` or `contracts/integration-contracts.md` is
uncovered. The two model-call integrations documented there map to T2 (agent-under-test, via
`create_runner`) and T7 (judge).
