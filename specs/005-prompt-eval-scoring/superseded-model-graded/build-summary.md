# Build Summary: 005-prompt-eval-scoring

## Run 1 — Task T1

**Task**: T1 — Package skeleton for `model_graded/`
**Status**: Complete

(See prior entry — package markers only, no logic.)

---

## Run 2 — Tasks T2 through T16 (T9 and T17 remain: real-model manual steps)

**Status**: Complete except T9/T17, which require a real judge/agent model call — per this
repo's standing rule (project memory: "Never run live LLM evals myself"), those stay the user's
manual action, documented in `quickstart.md` as checklist steps, not run by this agent.

### Files changed

**New — `backend/tests/evals/model_graded/` (the branch itself)**
- `driver.py` — `GradedScenario`, `GradedRunResult`, `run_graded_scenario_once()`. Dispatches via
  `create_runner(agent_id, ctx)` — reused as-is (`clarifications.md` Q9/Q11). No sandbox seeding,
  no file read-back. Writes a full `log.txt` transcript per run under `model_graded/logs/<run_id>/`.
- `precheck.py` — the **generic**, agent-agnostic `run_precheck(response, config)` (`clarifications.md`
  Q10): wrapper-tag check, min-section-count check, forbidden-substring check, driven entirely by
  a scenario's `precheck:` YAML block. Zero agent-specific code.
- `scenario_discovery.py` — discovers `agents/*/scenarios/*.yaml`, resolves each scenario's
  `precheck:` config, optional `precheck_module:` custom hook, and `rubric:` text. Fail-loud
  validation at load time (unknown `agent_id`, malformed `precheck:` block, missing `rubric:`,
  unresolvable custom hook, invalid `min_pages`).
- `judge.py` — `JudgeVerdict`, `grade_run()`, `DEFAULT_JUDGE_THRESHOLD = 70`, and **one shared**
  `build_rubric_prompt()` parameterized by a scenario's plain-text `rubric:` — no per-agent
  module. Never raises; a judge failure always degrades to an errored `JudgeVerdict`.
- `report.py` — `append_entry()`, `load_entries()`, `summarize()`, `worst()`,
  `compute_system_prompt_hash()`. Pure data plumbing — no model/agent imports whatsoever.
- `cli.py` — the `graded`/`report` subcommands: `--judge`, `--samples N`, `--judge-provider`,
  `--judge-model`, `--judge-threshold` on `graded`; `--last`, `--worst`, `--by`, `--target` on
  `report`. The only module importing all of driver/precheck/judge/report together.

**New — `backend/tests/evals/model_graded/agents/prototype_specify/` (first example)**
- `scenarios/prototype_specify_billing_console.yaml` — the one v1 scenario
  (`clarifications.md` Q4): a B2B SaaS billing admin-console brief, inline `precheck:` config,
  inline `rubric:` text, `precheck_module:` pointing at the one custom hook.
- `nav_cross_reference_check.py` — the **only** agent-specific Python file for this agent: parses
  the "Pages & Navigation" table and page-spec headings, verifies every nav target has a matching
  page section. Everything else about grading this agent is data.

**Modified (additive only)**
- `./tests/evals/eval.sh` — added `graded`/`report` case branches plus header-comment entries.
  `git diff` confirms every existing case (`all`, `--live`, `hello`, `layers`, `prompts`, `phase`,
  `benchmark`, the bare-scenario fallback) is byte-unchanged.

**New — reports/logs scaffolding**
- `backend/tests/evals/reports/.gitkeep`, `backend/tests/evals/model_graded/logs/.gitkeep`.

**New — tests (`backend/tests/unit/`)**
- `test_model_graded_precheck.py` (7 tests)
- `test_model_graded_driver.py` (6 tests — includes the composition-fidelity import guard, see
  Deviations below)
- `test_model_graded_scenario_discovery.py` (9 tests, incl. one against the real shipped scenario)
- `test_model_graded_judge.py` (8 tests)
- `test_model_graded_report.py` (9 tests)
- `test_model_graded_cli.py` (7 tests)
- `test_model_graded_slice1_integration.py` (3 tests — Task T6, generic precheck + custom hook
  composing correctly against the real shipped scenario)
- `test_prototype_specify_nav_check.py` (4 tests)

**53 new tests total, all passing.**

### Tests added/updated

See file list above — one test file per module, named per `tasks.md`'s task list (with
`test_prototype_specify_precheck.py` renamed to `test_prototype_specify_nav_check.py` per the
Q10 pivot away from a per-agent `precheck.py`, already reflected in `quickstart.md`).

### Build/test commands run

```bash
cd backend
python3.11 -m pytest tests/unit/test_model_graded_precheck.py \
  tests/unit/test_model_graded_driver.py \
  tests/unit/test_model_graded_scenario_discovery.py \
  tests/unit/test_model_graded_judge.py \
  tests/unit/test_model_graded_report.py \
  tests/unit/test_model_graded_cli.py \
  tests/unit/test_model_graded_slice1_integration.py \
  tests/unit/test_prototype_specify_nav_check.py -q
# → 53 passed

./tests/evals/model_graded/model-graded.sh graded no-such-scenario   # clean "unknown scenario" error, no tokens spent
./tests/evals/model_graded/model-graded.sh report                    # clean zero-entries output, no crash
./tests/evals/model_graded/model-graded.sh report --worst 3          # clean zero-entries output
./tests/evals/model_graded/model-graded.sh report --by system_prompt_hash --target 90   # clean zero-entries output
./tests/evals/eval.sh prototype_multi_issue_repair   # existing deterministic-track command, unchanged output
```

Full `backend/tests/unit/` regression sweep was also launched to confirm nothing pre-existing
broke; see follow-up note if it surfaces anything (running in background at time of writing —
check follow-up commit/session for the result if not already resolved).

### Notable deviations from plan/design

1. **`cli.py`'s `_BACKEND` path bug, found and fixed during implementation.** Originally computed
   as `Path(__file__).resolve().parents[2]` (→ `backend/tests`, one level too shallow) instead of
   `parents[3]` (→ `backend/`). This was invisible when importing the module directly from the
   `backend/` working directory (Python's own `-c`/`-m` cwd-insertion masked it) but broke real
   `./tests/evals/model_graded/model-graded.sh graded ...` invocations with `ModuleNotFoundError: No module named
   'agents.registry'`. Caught by actually running the CLI through `./tests/evals/eval.sh` (not just unit
   tests, which all mock past the module-resolution layer) — fixed and re-verified.
2. **`report.py`'s `append_entry`/`load_entries` default-argument gotcha, found and fixed.**
   Originally `report_path: Path = DEFAULT_REPORT_PATH` — a mutable-at-import-time default that
   would NOT respect a test monkeypatching the module constant, since Python binds default
   argument values once at function-definition time. Fixed to `report_path: Path | None = None`
   with the default resolved inside the function body at call time. Caught before it could
   contaminate the real `backend/tests/evals/reports/eval_report.jsonl` during test runs — the
   original CLI test suite would have silently written into the actual project report file.
3. **T2's specific acceptance bullet** ("verify by asserting the composed system prompt used by
   a mocked `create_runner` call includes injected content beyond the raw `AGENT.md` body") was
   satisfied via an architectural guard instead of a literal content assertion:
   `test_driver_never_builds_a_raw_model_call_itself` asserts `driver.py` never imports
   `langchain_core.messages`/`langchain_anthropic` directly — i.e., it structurally cannot
   construct a competing, non-composed chat call, only ever dispatching through `create_runner`.
   Testing the *actual* composed-prompt content would require exercising the real
   `_compose_system_prompt`/`_compose_injection` pipeline, which is already covered by this
   repo's own `tests/agents/test_create_runner.py` suite — re-testing that machinery here would
   duplicate coverage rather than add it.
4. **`min_sections` is not in `precheck.py`'s `REQUIRED_CONFIG_KEYS`** (only `wrapper`,
   `section_pattern`, `forbidden` are) — deliberately, so a scenario author can omit
   `min_sections` in the YAML and have it default from the friendlier `min_pages` field
   (`scenario_discovery.py` fills it in before `run_precheck` ever sees the config). `min_pages`
   isn't part of `plan.md`'s originally-sketched `precheck:` shape as a merge source; this was an
   implementation-time resolution of the "Exact `precheck:` YAML config schema" item already
   flagged as an open Unknown in `research.md`.
5. **Real judge smoke run (T9) and full SOP walkthrough (T17) are not executed by this agent** —
   both require real, token-spending model calls, which this repo's standing project-memory rule
   reserves for the user to trigger manually. Both are ready to run via the documented
   `quickstart.md` commands whenever the user chooses to.

### Blockers / follow-up items

- **Pending user action**: run T9 (`./tests/evals/model_graded/model-graded.sh graded prototype_specify_billing_console
  --judge`, eyeball the score/rationale) and T17 (the full iterate-loop walkthrough) to close out
  the two remaining unchecked tasks.
- Full `backend/tests/unit/` regression run was in progress at the time this summary was written
  (to confirm zero breakage to pre-existing suites) — no failures observed in the portion that
  had completed; confirm the full run is green before treating this spec as fully verified.
