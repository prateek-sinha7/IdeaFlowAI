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

Every run writes **`.runs/<workflow>/<dataset_run_id>/reports/`** — a layered document set:

| | |
|---|---|
| `reports/report.md` | the top level: one score per phase (judge, code, combined), the clustered strengths and weaknesses across the run, and the rejudge command |
| `reports/<agent>_report.md` | one phase in full: spread statistics, per-dimension aggregates, every row's sub-scores, the judge's rationale and quoted evidence |
| `reports/code_report.md` | the deterministic code track's per-row findings, when it ran |
| `reports/prompt_advice_<agent>.md` | the proposed prompt delta for that phase — where the output drifted from the prompt's intent, what to add/remove/reword, and the strengths an edit must not lose |

`grade.sh report` regenerates the whole set for free. Dispatch transcripts live in
`logs/<row_id>/<agent>.log` — one brief's transcripts across every stage, together.

## The report — every run on one surface

The markdown above is one run at a time, seven files deep. The report is all of them at once, as
**one file**:

```bash
./evals/grading/grade.sh dashboard          # rebuild .runs/report.html
./evals/grading/grade.sh dashboard --open   # …and launch it
./evals/grading/grade.sh dashboard --export <run-id>   # one shareable file
```

**Free** — it renders artifacts already on disk, calls no model and dispatches nothing. It is
also rebuilt automatically at the end of every run, rejudge and code pass, so it is never stale.

| | |
|---|---|
| `.runs/evals_data.json` | every run's artifacts consolidated into one dataset |
| `.runs/report.html` | the one report over the whole tree — click a run to drill into its phases, rows, judge reasoning and sandboxed previews, all in place |

Nothing is written into a run folder: the markdown set above stays the per-run record, and the
report is the single surface across all of them. `--export <run-id>` optionally writes one run as
a standalone file for sharing.

The five views answer what a single run's report cannot:

- **quality trend** — are we improving, and since when? Golden references are drawn as ceiling
  lines rather than trend points.
- **prompt versions** — runs grouped by `system_prompt_hash`, with `compare`'s noise band
  deciding whether a delta is real, and **the actual text diff between two versions** beside it.
- **dimension heatmap** — which rubric dimension is chronically weak across every run.
- **stage × row matrix** — is a phase weak everywhere, or is one brief breaking the chain? The
  four failures that all score 0 (dispatch error, failed precheck, broken chain, judge failure)
  are drawn apart, because an average erases the difference.
- **cost & code health** — agent vs judge tokens, and the browser findings, trended.

Everything is opened by double-click: no server, no network, no build step. Details and the
rules the package keeps: [`site/README.md`](site/README.md).

**One command does the whole loop.** A live run runs every step in order and leaves all of it in
the run folder:

```
dispatch the agents → judge → code checks → prompt advice → reports/
```

The deterministic **code checks run automatically** after any run whose HTML stages completed
(static + headless-browser: nav clicked, buttons/filters exercised — free), so the reports carry
judge, code and combined scores. **Prompt advice then runs automatically** over every judged
stage, reading the judge's weaknesses *and* the browser findings as ground truth, and writes one
proposal per phase. Disable either with `--no-code` / `--no-advise`, or
`options: {code_grading: false, advise: false}`.

Advice is LIVE — one model call per judged stage, on the judge model — and the plan's cost line
counts it before anything is spent. It is a **proposal, never a grade**: nothing it writes feeds
back into a score.

The same three tracks can also be run by hand against any finished run:

```bash
./evals/grading/grade.sh rejudge <run-id>   # re-score stored outputs — same run minus the
                                            # generation; judge tokens are the only spend
./evals/grading/grade.sh code <run-id>      # re-run the code checks by hand (free) — e.g. on
                                            # an old folder, or after editing the checks
./evals/grading/grade.sh advise <run-id>    # ingest the evidence and propose a prompt delta
                                            # per agent (one model call per stage)
```

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
