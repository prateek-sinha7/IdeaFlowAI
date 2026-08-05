# Superseded — the original model-graded spec

**Archived 2026-07-29. Do not build from these documents.**

These are spec 005 as originally written on 2026-07-28, specifying
`backend/tests/evals/model_graded/` (now `backend/evals/model_graded/`). They are kept verbatim
because they record real design reasoning — the LLM-as-judge shape, the rubric/precheck split,
the dataset-chaining idea — that carried over into the replacement.

## Why they are archived

The branch they specify was built, run once, and frozen. That run scored **exactly 95 on all 11
rows** while rejecting 7 of the same rows at precheck: a score with zero variance cannot detect
a regression, and a gate that rejects correct output makes its own pass rate meaningless. The
two root causes are documented with evidence in [`../spec.md`](../spec.md) §1.

These documents also carried their own unheeded warning in the original status line:

> plan.md/design.md/tasks.md/data-model.md now stale — see clarifications.md Q12-Q15;
> re-run /apex:plan and /apex:design

That replan never happened, and the code it would have replanned is now frozen.

## What replaced them

`backend/evals/grading/` — see [`../spec.md`](../spec.md), [`../plan.md`](../plan.md),
[`../tasks.md`](../tasks.md), [`../build-summary.md`](../build-summary.md).

## Reading them safely

- **Paths are stale.** They say `backend/tests/evals/model_graded/`; the package now lives at
  `backend/evals/model_graded/`, and its CLI is `./evals/model_graded/model-graded.sh`.
- **`run-eval.sh` no longer exists.** It was deleted on 2026-07-29; each eval package owns its
  own script.
- **The scores quoted here are not trustworthy** — that is why the branch was frozen. Do not
  calibrate anything against them.

| File | Was |
|---|---|
| `spec.md` | The model-graded feature specification |
| `plan.md` / `design.md` / `tasks.md` | Implementation planning (marked stale by their own author) |
| `data-model.md` | Artifact shapes: `run.json`, `grade.json`, `score.json` |
| `research.md` / `clarifications.md` | Prior art and resolved Q&A (Q1–Q15) |
| `quickstart.md` | Operator guide for the frozen CLI |
| `build-summary.md` | What that branch shipped |
| `contracts/` | API + integration contracts |
