# evals/minimal

Grades an agent workflow end to end: dispatch every stage through the real
agent runtime, check the deliverable deterministically, judge it against a
per-stage rubric, and report the result.

Nothing in the Python knows what a prototype is. A workflow is a directory.

```bash
./run-aws.sh                                # the whole thing on Bedrock: preflight,
                                            # dispatch, judge, report — one command

./eval.sh  configs/prototype_smoke.yaml     # or by hand: dispatch → prints RUN_ID
./judge.sh RUN_ID --advise                  # check + judge + report that folder

./eval.sh  configs/ppt_smoke.yaml           # a 3-stage deck workflow — same code
```

**Dispatch and judging are separate commands, deliberately.** They spend
separately and fail for different reasons: a rate limit in `build` used to
throw away the right to judge the three stages that had already succeeded.
`eval.sh` dispatches one stage per invocation into one run folder, so a stage
that fails costs only that stage — resume it with `--stage X --into RUN_ID`
and the upstream stages are reused rather than re-bought. That matters more
than it sounds: specify/plan/analyze are 4k–27k input tokens, a prototype
`build` is 168k–288k, and `validate` up to 2.5M.

---

## Layout

```
run-aws.sh              preflight + dispatch + judge + report, on Bedrock
eval.sh                 dispatch, stage by stage    — wraps `cli.py chain`
judge.sh                check + judge + report      — wraps `cli.py judge`
cli.py                  chain / judge / run / score / checks / compare / clone /
                        workflows / report / advice
run.py                  dispatch: row -> agent -> response -> artifact (the only runtime caller)
judge.py                the judge + advisor model calls (the only module that spends)
checks.py               deterministic checkers, by name (CHECKERS)
score.py                aggregation + the noise-guarded delta (pure, no I/O)
store.py                every run-folder path (the one path owner)
report.py + report.*    report.html, built from stored JSON only
workflow.py             resolves a config -> workflow -> rubrics, datasets, checkers

configs/*.yaml          a workflow + a dataset. That is all a config is.
workflows/<id>/
  workflow.yaml         stage order, each stage's agent, seed filename, checker
  rubrics/<stage>.yaml  what "good" means for that stage, per dimension
  datasets/*.json       the briefs
prompts/                judge_prompt.md, advise_prompt.md, and the versioned
                        agent prompts activate.sh switches between
.runs/                  every run's output (gitignored)
```

---

## Adding a workflow

No Python. Copy `workflows/ppt/` and edit four things:

1. **`workflow.yaml`** — the stage order, and per stage: its `agent_id`, and
   either `seed_as` (the sandbox filename its output lands under, for text
   agents) or `deliverable` (the file a tool-using agent writes, which is read
   back and graded instead of its reply). Optionally `checks:` — a name from
   `checks.CHECKERS`, or `none`.
2. **`rubrics/<stage>.yaml`** — one per stage. Dimensions with weights, the
   rubric prose, `scoring: severity_priced`, and `upstream:` naming which
   prior artifacts the judge needs as evidence.
3. **`datasets/*.json`** — `{dataset_id, rows: [{id, prompt, ...}]}`.
4. **`configs/<name>.yaml`** — `workflow: <id>` and `dataset: <file>`.

Three rules worth knowing before you write one:

- **Stage names are eval-local labels, not agent ids.** `prototype` and `ppt`
  both have a `validate` stage. Rubrics are per-workflow for exactly this
  reason — a flat `rubrics/validate.yaml` would grade one with the other's
  rubric, silently, and produce a plausible number.
- **`upstream:` is the judge's evidence, and omitting it is not neutral.**
  Upstream artifacts reach an agent as sandbox FILES it opens with tools,
  never as prompt text, so a judge sees none of them unless the rubric asks.
  Four of five prototype stages were once judged blind on their largest
  dimension this way — `validate.defect_repair_delta` graded "what did you
  fix?" against evidence that was never supplied, and priced the missing
  evidence as the artifact's failure. List only what a dimension actually
  reads: unusable context still costs the judge a read before it can score.
- **Declare `checks: none` rather than leaving it off.** The fallback rule
  (an `.html` deliverable gets `html_prototype`) exists for runs stored before
  checkers were declarable. `html_prototype` lints a hash-routed multi-page
  app and fails any valid `.html` that is not one.

---

## Commands

The two scripts cover the normal path. Underneath them:

```bash
cd backend                                    # every command needs this cwd

python3.11 -m evals.minimal.cli chain  <config> [--stage S --into RUN_ID]
python3.11 -m evals.minimal.cli judge  <run_id> [--stage S] [--advise] [--concurrency N]
python3.11 -m evals.minimal.cli run    <config> [--stage S --into RUN_ID]  # one invocation, all stages
python3.11 -m evals.minimal.cli checks <run_id> [--stage S]     # free
python3.11 -m evals.minimal.cli score  <run_id> [--stage S] [--advise]
python3.11 -m evals.minimal.cli workflows [<id>]                # free: validate the wiring
python3.11 -m evals.minimal.cli report                          # rebuild report.html
python3.11 -m evals.minimal.cli advice [--summary]              # pool advice, warn on stale
python3.11 -m evals.minimal.cli compare <run_a> <run_b>         # noise-guarded delta
python3.11 -m evals.minimal.cli clone  <run_id> --label awsjudge
```

**Judging refuses to run blind.** Before it spends, every stage's declared
`upstream:` evidence is verified present, non-empty, and byte-matching the
stage that produced it. It prints what it found, and stops the whole run if
it does not add up:

```
validate  upstream OK — municipal_permits: spec.md (32,598 chars, from specify),
                        prototype.html (77,067 chars, from build)
validate  note — presentation.html is byte-identical to this stage's own output
                 — it changed nothing
UPSTREAM FAILED  validate: upstream 'prototype.html' does not match the stored
                 output of 'build' — the judge would be reading something other
                 than what that stage produced
```

**A second opinion on the same artifacts** — dispatch is the expensive half
(a 5-stage chain on Bedrock ran 2.9M input tokens), so re-judging must never
mean re-generating:

```bash
NEW=$(python3.11 -m evals.minimal.cli clone <run_id> --label awsjudge)
./judge.sh "$NEW" --judge-provider bedrock --advise
```

The two runs then differ in the judge and in nothing else. Run one at a time:
parallel terminals share one Mistral account, and that is what produces 429s —
the dispatch provider is irrelevant, since the judge is Mistral-hosted either
way unless overridden.

---

## Reading a result

```
build   judge 91.1 (n=2)   checks 40.7 (n=3)   completed 2/5   GATE: FAILED [render] — …
```

Four unsynthesised facts, never a blend. A failing check does **not** zero the
judge score: read the two columns together. `judge 82.0  checks 0.0` is the
honest statement that the content is reasonable and the page does not run.

Two things the numbers do not cover, both observed:

- **The judge is lenient about what it finds.** It reliably reports real
  defects and just as reliably declines to deduct for them, so
  `scoring: severity_priced` takes the arithmetic out of its hands: it tags
  each finding `blocking`/`major`/`minor` and Python prices them
  (`judge.SEVERITY_COST`). Judging what is wrong is a language task;
  converting that into a number is not.
- **Passing checks is not a working page.** `render_check` loads the document
  and walks its nav links, but nothing in this stack checks the viewport — a
  prototype that renders its content one full screen below the fold passes
  every automated signal here and is blank when you open it. Open the
  artifact.

---

## Prompt experiments

`prompts/agents/<agent-id>.vN.md` holds the versioned prompt bodies;
`prompts/activate.sh` switches which one the eval user dispatches with, via
production's own per-user override store — no code here changes:

```bash
cd prompts
./activate.sh prototype-build v2     # one agent
./activate.sh prototype v2           # every agent in the workflow
./activate.sh status                 # what is currently active
./activate.sh prototype reset        # back to canonical AGENT.md
```

Promotion into `backend/agents/prompts/<id>/AGENT.md` is always manual.
