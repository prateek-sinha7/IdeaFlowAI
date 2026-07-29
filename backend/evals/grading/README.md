# `evals/grading/`

Grading answers **is this agent's output good?** — and, more to the point, *which prompt do I
change, and did my change help?*

```bash
# free preview — composes every prompt, dispatches nothing
./evals/grading/grade.sh plan smoke

# read a finished run — free
./evals/grading/grade.sh report <dataset_run_id> --worst 3
```

The `model` track is **always live**; there is no `--live` flag. It prints its blast radius and
preflights the judge before spending anything.

Every run writes **`.runs/<workflow>/<dataset_run_id>/REPORT.md`** — the whole run as one
readable document: stage overview, token spend split agent-vs-judge, per-dimension aggregates,
a row table with every sub-score, the clustered weaknesses, and the judge's rationale and
quoted evidence per row. `grade.sh report` reprints and regenerates it for free.

## Docs

**Running it** lives here, next to the code:

| | |
|---|---|
| [`docs/README.md`](docs/README.md) | **Start here** — running it, commands, the improvement loop, troubleshooting |

**Why it looks like this** lives in the spec — `specs/005-prompt-eval-scoring/` (moved there
2026-07-29, so the planning record sits with every other spec rather than inside the package):

| | |
|---|---|
| [`spec.md`](../../../specs/005-prompt-eval-scoring/spec.md) | What this system is and its behavioural contract |
| [`plan.md`](../../../specs/005-prompt-eval-scoring/plan.md) | The design and the reasoning behind each decision |
| [`tasks.md`](../../../specs/005-prompt-eval-scoring/tasks.md) | Execution breakdown and the contract every module implements |
| [`build-summary.md`](../../../specs/005-prompt-eval-scoring/build-summary.md) | What was built, with the evidence for each claim |
| [`outstanding.md`](../../../specs/005-prompt-eval-scoring/outstanding.md) | **Product decisions awaiting an answer** — questions I did not decide for you |

Per-folder READMEs stay next to what they document: [`configs/`](configs/README.md),
[`model/`](model/README.md), [`code/`](code/README.md), and each workflow's own folder.
