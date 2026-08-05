# Quickstart — running the suite, and adding a pipeline to it

The living reference for `backend/evals/hybrid/`. Two halves: **running what exists**, and
**adding coverage for a new pipeline**. Everything here is offline and free unless a line is
marked `[LIVE]`.

---

## Running it

```bash
cd backend

./evals/hybrid/eval.sh                    # the whole suite, offline          (free)
./evals/hybrid/eval.sh layers             # engine + revision layer tests     (free)
./evals/hybrid/eval.sh hello              # harness gate only                 (free)
./evals/hybrid/eval.sh check              # every scenario's checker is honest(free)
./evals/hybrid/eval.sh scenarios          # list discovered scenarios         (free)
./evals/hybrid/eval.sh phases             # list phase folders                (free)
./evals/hybrid/eval.sh prompts            # dump composed prompts to disk     (free)

./evals/hybrid/eval.sh <scenario-id>          # validate one scenario         (free)
./evals/hybrid/eval.sh <scenario-id> --live   # ONE real-model run            [LIVE]
./evals/hybrid/eval.sh benchmark <id> 10      # N runs → a pass RATE          [LIVE]
```

`--live` is a universal flag, never a command name and never implicit. A bare scenario id runs
`validate_scenario.py`, which spends nothing.

**Reading the result.** Green on the default command means nothing regressed. It does **not**
mean the revision defect is fixed — the defect is structural and still open (see
[`spec.md`](spec.md) §4). A live run answers a different question: did the real model, right
now, satisfy this one instruction.

---

## Adding a new pipeline's eval coverage

The suite is organised as `workflow/<domain>/<variant>/`, mirroring
`agents/workflows/<pipeline_type>/` — `<domain>` is the pipeline_type with any trailing
`_revision` stripped, `<variant>` is `build` or `revision`.

### 1. Create the phase folder

```
backend/evals/hybrid/workflow/<domain>/<variant>/
├── __init__.py
├── conftest.py            # only if the phase needs its own fixtures
├── checkers.py            # the pass/fail logic + a CHECKERS registry
├── test_live.py           # copy verbatim; only the checkers import line changes
├── scenarios/
│   └── <scenario-id>.yaml
└── fixtures/
    └── <fixture>.html
```

### 2. Write the checker

Pass/fail logic has to be code — it inspects a real artifact. Everything *else* about a scenario
is data. One function per defect, plus an aggregate if a scenario covers several:

```python
def save_button_wired(final_html: str) -> tuple[bool, str]:
    """Is the Save button actually wired — inline onclick or a JS listener?"""
    ...
    return False, "Save button has no working handler"   # (ok, reason)

CHECKERS = {"<scenario-id>": <aggregate_or_single_checker>}
```

**Contract:** `Callable[[str], tuple[bool, str]]` — takes the delivered file's text, returns
`(passed, reason)`. `reason` must name the specific thing that failed; it is what a human reads
first. Return `(True, "")` on success. See
[`contracts/checker-contract.md`](contracts/checker-contract.md).

### 3. Declare the scenario as YAML

No Python needed per scenario — `test_live.py` discovers every YAML in the folder. Fields are
specified in [`data-model.md`](data-model.md); copy `scenarios/_TEMPLATE.yaml`.

### 4. Prove the checker can fail

```bash
./evals/hybrid/eval.sh <scenario-id>
```

This runs the checker against the **raw, unfixed fixture** and insists it reports failure. A
checker that already passes on broken input can never demonstrate a fix — this catches that for
free, before any live run pays for it. `eval.sh check` does it for every scenario at once.

### 5. Only then, spend a token

```bash
./evals/hybrid/eval.sh <scenario-id> --live
```

---

## Rules that keep this suite trustworthy

- **Offline by default, always.** A new test must run with the scripted stand-in model unless it
  is explicitly marked `requires_api_key`. Live tests are excluded from every default mode.
- **Scenario ids are globally unique** across every pipeline (enforced by
  `discover_all_scenarios`), so one id always means one scenario no matter how many pipelines
  accumulate.
- **`engine/` is for mechanisms used by more than one pipeline**, and membership is *verified*,
  not assumed — `grep -rl <thing> agents/workflows/*/workflow.yaml` before anything lands there.
  Anything specific to one pipeline belongs in its `workflow/<domain>/<variant>/` folder.
- **The suite is hermetic.** A session-scoped fixture swaps the DB engine for in-memory SQLite,
  so results are identical whether Postgres is up or down.
- **Never assert on a model's prose.** Assert on the artifact it produced. Prose assertions are
  how a suite becomes flaky; that is `005-prompt-eval-scoring`'s job, with a judge and a
  baseline.
