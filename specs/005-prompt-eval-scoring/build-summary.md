# SUMMARY — what was built

A record of what this folder is and how it got here. For *running* it see
[the operator runbook](../../backend/evals/grading/docs/README.md); for *why* each design decision went the way it did see
[`plan.md`](plan.md); for the task breakdown see [`tasks.md`](tasks.md).

**Status:** built and wired into `./evals/grading/grade.sh`. **239 offline tests**, no live run
yet, so the baseline is uncalibrated. `evals/model_graded/` was never modified and still
passes its own 71 tests.

---

## What problem this solves

The previous grading branch (`model_graded/`, now frozen) produced a number that could not be
acted on. Its one committed run scored **exactly 95 on all 11 rows** — zero variance — while
rejecting 7 of those same 11 rows at the precheck stage. An eval that gives every response the
same score cannot detect a regression, and one whose gate rejects correct output makes its own
pass rate meaningless.

This folder replaces that with a loop: run a workflow's agents, score them in a way that says
*which part* of the output is weak, and tell you whether editing a prompt actually helped.

## The two real bugs in the old branch, and their evidence

Both were found by replaying the committed artifacts, so both are proven rather than argued.

**1. The precheck rejected correct specs.** The forbidden-string list matched bare substrings,
and `placeholder` / `stub` are ordinary UI vocabulary in a spec that describes forms:

```
Search input placeholder: "Search waitlist..."
`.form-input` "Room" placeholder "e.g., Conf Room 3"
click student row -> `#/students/{id}` (stub page)
```

Every one of the 7 failures was a false positive. Re-running the narrowed regex list against
the same 11 stored responses: **11/11 pass**, up from 4/11. `tests/unit/test_grading_precheck.py`
asserts this against the real artifacts.

**2. The judge graded a prompt the agent never saw.** `model_graded/judge.py` re-composed the
system prompt with `no_tools=True`. But `no_tools = exclude_builtin_tools and not custom_tools`,
so for tool-using agents it is **False**. Measured live: `prototype-specify` composes 10,956
characters, `prototype-build` 12,435 — genuinely different prompts. `dispatch.py` now returns
the prompt it actually used and the judge grades against that.

A third defect was found while building: **`build_model(provider=...)` only honours `"mistral"`.** `"anthropic"` and `"bedrock"` are silently ignored and fall through an
implicit chain, so a rubric that pins a judge may be graded by a different model entirely.

---

## Architecture

Twelve flat modules, each with one job, read top-to-bottom in execution order.

| Module | Lines | Job |
|---|---|---|
| `grade_runner.py` | 733 | CLI: parse, dispatch, print, exit code. No grading logic. |
| `model_grader.py` | 754 | Orchestration only: `run_workflow → run_stage → run_row` |
| `code_grader.py` | 139 | Deterministic HTML checks over a run folder (skeleton) |
| `config.py` | 385 | Load/validate the four config kinds; registry assertion; hashes |
| `hooks.py` | 75 | Resolve `./file.py:func` relative to a config file |
| `stage_input.py` | 285 | **Pure.** Per-row prompt composition, incl. the fan-in join |
| `dispatch.py` | 198 | The only runtime-touching module: one row → agent → response |
| `precheck.py` | 110 | Wrapper / section / forbidden-regex gate + custom hook |
| `judge.py` | 237 | Judge prompt, static schema, per-dimension sub-scores |
| `scoring.py` | 461 | **Pure.** Aggregates, per-dimension stats, baseline verdict |
| `compare.py` | 378 | **Pure.** Run-to-run deltas with a noise guard |
| `artifacts.py` | 194 | **Pure I/O.** Sole owner of every run-folder path |

Dependency direction, asserted and cycle-free:

```
grade_runner → model_grader, code_grader, compare, config
model_grader → config, stage_input, dispatch, precheck, judge, scoring, artifacts
config, stage_input → hooks
dispatch, scoring, compare, judge, precheck, artifacts, hooks → (leaves)
```

Four modules — `stage_input`, `scoring`, `compare`, `precheck` — are **pure**: no I/O, no model
calls, nothing imported from this package. That is deliberate. They hold the logic whose silent
failure costs a whole run, and purity makes them testable in milliseconds. `scoring` and
`compare` take plain dicts rather than typed objects, which is what keeps them leaves.

## What each design decision buys you

**One dataset-keyed run folder, shared by every stage.** All stages write into the same
`artifacts/` directory indexed by a stable row id. That is what makes the `prototype-analyze`
fan-in a lookup — it needs the spec *and* the tasks for the same row — and what lets a summary
show a row degrading across stages.

**Row ids never carry an agent suffix.** `billing_console` at every stage; the agent goes in the
filename. Suffixing (`billing_console_plan`) makes cross-stage joins impossible, which is the
one thing a chained eval exists to do.

**Per-dimension sub-scores, weights applied in Python.** The judge scores each dimension 0–100;
weights are applied afterwards. A single overall number can't tell you which paragraph to
rewrite, and baking weights into the judge's JSON schema would mean a weight edit silently
produces an all-zero run.

**Append-only run folders.** Overwriting a stage destroys captured response text
irrecoverably, so it hard-errors unless `--replace`, which supersedes rather than deletes.

**Judge preflight before the first dispatch.** A misconfigured judge used to fail *after* every
agent call had been paid for. It now costs nothing.

**A noise guard on comparisons.** `compare` refuses to call a delta an improvement when it sits
inside observed run-to-run variance, and reports `unknown-variance` rather than assuming when
there is no repeat data. The old branch failed by returning a constant; reading noise as
progress is the mirror-image failure, and it is more seductive because it looks like the loop
is working.

**Run configs + a resolved snapshot.** Every run writes its fully merged settings to
`grade_config.resolved.yaml` **before** the first dispatch, so a crashed run is still
reproducible and a before/after comparison can hold everything but the prompt constant.

## Tests

239 offline tests. No model calls, no network.

| | | | |
|---|---|---|---|
| config 34 | precheck 28 | runner 29 | artifacts 24 |
| stage_input 22 | scoring 19 | compare 18 | hooks 16 |
| model_grader 15 | judge 14 | dispatch 12 | code_grader 8 |

The ones that matter most replay **real committed artifacts** rather than synthetic fixtures:
the precheck 11/11 replay, and a scoring test that reproduces the constant-95 run and asserts
the baseline fails naming `distinct_score_count 1 < 3`.

## Config shipped

`prototype-specify` is fully onboarded: a 12-row dataset (11 real briefs + 1 negative test), a
rubric with three weighted dimensions and calibration anchors, a nav-cross-reference validate
hook, and three run configs (smoke / calibration / full chain). All five prototype stages are
declared in `workflow.yaml` — including the analyze fan-in and the build stage's adapter and
seeding — so onboarding stages 2–5 is config work with no structural decisions left.

---

## What is NOT done

- **No live run has been made**, so `baseline.set_from` is `NOT CALIBRATED` and the judge is
  unverified against real output. This is deliberate: an uncalibrated baseline is worse than
  none, because it looks authoritative.
- **Stages 2–5 are declared but not onboarded** — no rubric, hook or dataset yet.
- **`code_grader` is a dispatchable skeleton.** It reuses `static_check`/`render_check` and
  handles today's reality (no build stage exists) without crashing, but the populated
  `code/workflows/` layout is unbuilt.
- **`od_context` is never populated**, so `injects: [template, design_system]` is inert — no
  agent here is graded with a real design system attached. Recorded under `known_gaps` in
  `workflow.yaml`.
- **Verification step 5 is unverified**: confirming that every run folder's resolved config
  re-runs to an identical plan needs a real run folder.
- **`model_graded/` still exists in parallel.** Retiring it, and migrating its 39 scenario
  rows, is a separate decision.

## Before the first live run

Three credential facts checked on this machine:

1. `ANTHROPIC_API_KEY` is **empty**, and the rubric pins `claude-sonnet-5`.
2. The **Bedrock bearer token is expired**.
3. Mistral works, and is now the pinned provider for every shipped config.

So no good judge path is currently available. Preflight will say so in about a second, naming
what is configured, rather than spending anything. Fix that first, then:

```bash
./evals/grading/grade.sh smoke   # 2 rows, no judge
./evals/grading/grade.sh full    # 12 rows, judged
```

The single most important signal in that first run is **`distinct_score_count > 1`**. Its
absence is what made the previous run worthless, and `baseline.min_distinct_scores` now fails
the run instead of letting it hide in an average.
