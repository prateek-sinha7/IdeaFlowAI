# Feature Specification: Agent-Output Grading (`evals/grading/`)

**Spec ID**: 005-prompt-eval-scoring
**Created**: 2026-07-28
**Reframed**: 2026-07-29 — retargeted from the frozen `evals/model_graded/` branch onto its
replacement, `evals/grading/`. The original model-graded spec is archived under
[`superseded-model-graded/`](superseded-model-graded/).
**Status**: **Built, uncalibrated.** All modules implemented and wired into
`./evals/grading/grade.sh`; 253 offline tests pass. No live run has been made, so the baseline
is `NOT CALIBRATED`. Seven product decisions are open — see [`outstanding.md`](outstanding.md).
**Stack**: python | fastapi | (no frontend surface)

---

## 1. Problem statement

Grading answers one question: **is this agent's output good?** — as distinct from
`evals/hybrid/`, which answers *did the machinery run correctly?*

The point is not the score. The point is finding quality problems in a workflow's output and
improving the prompts that caused them. Scoring is how you tell whether an edit helped.

### Why the previous branch was replaced

`evals/model_graded/` (now frozen) produced a number that could not be acted on. Its one
committed run scored **exactly 95 on all 11 rows** — zero variance — while rejecting 7 of those
same 11 rows at the precheck stage. An eval that gives every response the same score cannot
detect a regression, and one whose gate rejects correct output makes its own pass rate
meaningless.

Two root causes, both proven by replaying the committed artifacts rather than argued:

1. **The precheck rejected correct specs.** The forbidden-string list matched bare substrings,
   and `placeholder`/`stub` are ordinary UI vocabulary in a spec describing forms. All 7
   failures were false positives; the narrowed regex list scores **11/11** on the same stored
   responses, asserted in `tests/unit/test_grading_precheck.py`.
2. **The judge graded a prompt the agent never saw.** `model_graded/judge.py` re-composed the
   system prompt with `no_tools=True`, but `no_tools = exclude_builtin_tools and not
   custom_tools` is `False` for tool-using agents. Measured live, `prototype-specify` composes
   10,956 characters and `prototype-build` 12,435 — genuinely different prompts. `dispatch.py`
   now returns the prompt it actually used, and the judge grades against that.

A third defect surfaced while building: **`build_model(provider=...)` only honours
`"mistral"`.** `"anthropic"` and `"bedrock"` are silently ignored and fall through an implicit
chain, so a rubric pinning a judge could be graded by a different model entirely.

## 2. Scope

**In scope** — the `backend/evals/grading/` package: two grading tracks, the run-config system,
the artifact layout, scoring/comparison, and the `grade.sh` CLI.

| Track | Judges | Verdict | Cost |
|---|---|---|---|
| `model/` | Prose an LLM must read — a spec, a plan, an analysis | 0–100 + rationale from a judge model | tokens |
| `code/` | The built HTML, after the build stage | pass/fail from executable checks | free |

The tracks stay separate because their failure modes differ: `model/` is flaky, costly and
needs calibration; `code/` is deterministic and should run on every commit. Mixing them makes
the cheap checks hostage to the expensive ones.

**Out of scope** — `evals/hybrid/` (machinery correctness, offline by default, code verdicts)
and `evals/model_graded/` (frozen; retiring it and migrating its 39 scenario rows is a separate
decision).

## 3. What is built

Twelve flat modules, each with one job, readable top-to-bottom in execution order:

| Module | Job |
|---|---|
| `grade_runner.py` | CLI: parse, dispatch, print, exit code. No grading logic. |
| `model_grader.py` | Orchestration only: `run_workflow → run_stage → run_row` |
| `code_grader.py` | Deterministic HTML checks over a run folder (skeleton) |
| `config.py` | Load/validate the four config kinds; registry assertion; hashes |
| `hooks.py` | Resolve `./file.py:func` relative to a config file |
| `stage_input.py` | **Pure.** Per-row prompt composition, incl. the fan-in join |
| `dispatch.py` | The only runtime-touching module: one row → agent → response |
| `precheck.py` | Wrapper / section / forbidden-regex gate + custom hook |
| `judge.py` | Judge prompt, static schema, per-dimension sub-scores |
| `scoring.py` | **Pure.** Aggregates, per-dimension stats, baseline verdict |
| `compare.py` | **Pure.** Run-to-run deltas with a noise guard |
| `artifacts.py` | **Pure I/O.** Sole owner of every run-folder path |

Four modules — `stage_input`, `scoring`, `compare`, `precheck` — are **pure**: no I/O, no model
calls, nothing imported from this package. They hold the logic whose silent failure costs a
whole run, and purity makes them testable in milliseconds. The dependency graph is asserted and
cycle-free.

## 4. Behavioural requirements

These are the invariants that make a score mean something. Each is implemented and tested.

- **R-01 — Per-dimension sub-scores, weights applied in Python.** The judge scores each
  dimension 0–100; weights are applied afterwards. A single overall number cannot tell you which
  paragraph to rewrite, and baking weights into the judge's JSON schema means a weight edit
  silently produces an all-zero run.
- **R-02 — Row ids never carry an agent suffix.** `billing_console` at every stage; the agent
  goes in the filename. Suffixing makes cross-stage joins impossible, which is the one thing a
  chained eval exists to do.
- **R-03 — One dataset-keyed run folder, shared by every stage.** This is what makes the
  `prototype-analyze` fan-in a lookup, and what lets a summary show a row degrading across
  stages.
- **R-04 — Append-only run folders.** Re-running a stage that already has artifacts is a hard
  error unless `--replace`, which supersedes rather than deletes. Overwriting destroys captured
  response text irrecoverably.
- **R-05 — Judge preflight before the first dispatch.** A misconfigured judge costs zero instead
  of failing after every agent call has been paid for.
- **R-06 — A noise guard on comparisons.** `compare` refuses to call a delta an improvement when
  it sits inside observed run-to-run variance, and reports `unknown-variance` rather than
  assuming when there is no repeat data. Reading noise as progress is the mirror image of the
  old branch's constant score, and more seductive because it looks like the loop is working.
- **R-07 — A resolved config snapshot before the first dispatch.** Every run writes its fully
  merged settings to `grade_config.resolved.yaml`, so a crashed run is still reproducible and a
  before/after comparison can hold everything but the prompt constant.
- **R-08 — The judge grades the prompt the agent actually received**, returned by `dispatch.py`,
  never re-composed.
- **R-09 — Blast radius printed before spending.** Stages, rows, dispatch estimate and the models
  that will actually be used; `--dry-run` stops right there having dispatched nothing.
- **R-10 — `distinct_score_count` is a run-level gate.** `baseline.min_distinct_scores` fails the
  run rather than letting a dead judge hide inside an average.

**Exit codes** — `0` ok · `2` usage/config · `3` baseline FAIL · `4` judge preflight ·
`5` no credentials · `6` run did not complete.

## 5. Current state

**Tests** — 253 offline, no model calls, no network. The ones that matter most replay **real
committed artifacts** rather than synthetic fixtures: the precheck 11/11 replay, and a scoring
test that reproduces the constant-95 run and asserts the baseline fails naming
`distinct_score_count 1 < 3`.

**Config shipped** — `prototype-specify` is fully onboarded: a 12-row dataset (11 real briefs +
1 negative test), a rubric with three weighted dimensions and calibration anchors, a
nav-cross-reference validate hook, and four run configs (`smoke` / `small` / `full` /
`partial`). All five prototype stages are declared in `workflow.yaml` — including the analyze
fan-in and the build stage's adapter and seeding — so onboarding stages 2–5 is config work with
no structural decisions left.

### Not done

- **No live run has been made**, so `baseline.set_from` is `NOT CALIBRATED` and the judge is
  unverified against real output. Deliberate: an uncalibrated baseline is worse than none,
  because it looks authoritative.
- **Stages 2–5 are declared but not onboarded** — no rubric, hook or dataset yet.
- **`code_grader` is a dispatchable skeleton.** It reuses `static_check`/`render_check` and
  handles today's reality (no build stage exists) without crashing, but the populated
  `code/workflows/` layout is unbuilt.
- **`od_context` is never populated**, so `injects: [template, design_system]` is inert — no
  agent here is graded with a real design system attached. Recorded under `known_gaps` in
  `workflow.yaml`.
- **Resolved-config re-run is unverified** — confirming a run folder's resolved config re-runs
  to an identical plan needs a real run folder.

## 6. Open decisions

Seven product judgements are deliberately undecided in [`outstanding.md`](outstanding.md),
because deciding them silently would change what a score means. They gate the live calibration
run (`tasks.md` T17), which is the developer's to execute:

1. The negative-test row cannot fail a structural precheck
2. Which judge should the baseline be calibrated on?
3. Should agents be graded with the real design system attached?
4. When is a score a measurement? (`repeats`)
5. Onboarding order for stages 2–5
6. The judge has two usable scores

## 7. Document map

| Document | Holds |
|---|---|
| `spec.md` (this file) | What the system is, why, and its behavioural contract |
| [`plan.md`](plan.md) | The design and the reasoning behind each decision |
| [`tasks.md`](tasks.md) | Execution breakdown + the contract every module implements |
| [`build-summary.md`](build-summary.md) | What was built, with the evidence for each claim |
| [`outstanding.md`](outstanding.md) | Product decisions awaiting an answer |
| [`research/`](research/) | Free-tier provider survey → model comparison → the pick (why Mistral) |
| `backend/evals/grading/docs/README.md` | **Operator runbook** — how to run it. Stays with the code. |
| [`superseded-model-graded/`](superseded-model-graded/) | The original model-graded spec, archived |

## 8. History

This spec was created on 2026-07-28 as *"Model-Graded Eval Branch (LLM-as-Judge + Report)"*,
specifying `backend/tests/evals/model_graded/`. That branch was built, produced the
unactionable constant-95 run described in §1, and was frozen. Its replacement, `evals/grading/`,
was built without a spec of its own, leaving the only eval spec in the repo pointing at dead
code. This reframe retargets the spec onto the live system; the original documents are archived
verbatim under `superseded-model-graded/` rather than deleted.
