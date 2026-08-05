# TASKS — building the `grading/` runner

Execution breakdown of [`plan.md`](plan.md). Every task names the files it owns, what it
depends on, and what "done" means. Nothing here restates the *why* — that lives in the plan.

**Status: T0-T16 complete.** 239 grading tests pass; `model_graded/` untouched at 71.
**T17 (the live calibration run) is outstanding and is the developer's to execute.**

**Standing constraints for every task:** `model_graded/` is read-only. All imports at the top
of the file. File docstring 3–4 lines, every function docstrized. Simple variable names.
SOLID / YAGNI / DRY. No task runs a live eval.

---

## The contract — read before starting any task

Parallel work is only safe if the seams are pinned first. These signatures are **fixed by
T1** and every other task implements against them without renegotiating.

**Pure modules take plain dicts, not typed objects.** `scoring.py` and `compare.py` operate
on the artifact shapes (`run.json`/`grade.json` entries as dicts), never on `JudgeVerdict` or
`DispatchResult`. This is what lets them import nothing from the package and stay testable
without constructing half the system.

**Contract clarifications** (raised during implementation, resolved here so downstream tasks
do not have to guess):

- `deliverable_file` appears both as a `dispatch.run_row` keyword and on `StageInput`. The
  explicit keyword wins when passed; otherwise `stage_input.deliverable_file` is used.
  **T12 should pass it via `StageInput` only** — `stage_input.py` already resolves it from the
  stage config, so a second source is a chance for the two to disagree.
- `DispatchResult.seed_files` records the seeds actually written, so an artifact can show what
  a row was given rather than what the config intended.
- `hooks.load_callable` returns a `Path.resolve()`d module, so a config reached through a
  symlink resolves to its real location.
- **Row-id key in artifacts.** New `run.json`/`grade.json`/`score.json` entries use **`row_id`**,
  matching `StageInput`/`DispatchResult`. `output.json` keeps **`id`**, because it is a dataset
  envelope and datasets use `id` — that is what makes promotion-to-dataset a copy. The
  committed `example-run/` predates this and uses `scenario_id`; readers keep a
  `scenario_id`/`id` fallback for historical runs rather than rewriting them. Do not
  retro-edit `example-run/` — it is documentation of a real run, not a fixture.
- **`on_upstream_failure`** is read from the stage level first, then `input:`, defaulting to
  `skip`. Not yet present in the real `workflow.yaml`.
- **Seed-file upstreams are joined too.** Stage 4 seeds `spec.md: prototype-specify` while
  `from: [prototype-plan]`, so `upstream_outputs` must carry **both**, and a row missing or
  errored in a *seed* upstream also produces a `skip_reason`. Seed agents appear in
  `upstream_chain` after the `from:` agents.
- **A `seed_files` derivation hook** takes the adapter's signature,
  `(row: dict, upstreams: dict[str, str]) -> str`. A value containing `:` is a hook reference;
  agent ids never contain a colon.
- **`deliverable_file`** is read from the stage level (`stage["deliverable_file"]`), not from
  `input:`, and reaches `dispatch` only via `StageInput`.
- **Code-track findings** are a fifth artifact kind, `<agent_token>_code_findings.json`,
  readable with `artifacts.read_stage_artifact(run_dir, agent_token, "code_findings")`.
- **Empty `dataset:`** in a run config means "use the workflow's `default_dataset`". `config.py`
  does not raise on it; **T12/T13 must honour the fallback** or reject it at the CLI layer.
- **`expect` defaults to `"pass"`** — it is present on exactly one shipped row, so every
  consumer must default it rather than `KeyError`.

**Integration findings from T12 (orchestration), as built.** Six places where a real
signature did not match the contract sketch. No module was changed to accommodate them:

- **`--replace` is a keyword on `run_workflow`, not a config option.** `config.DEFAULTS`
  rejects unknown option keys, so `options.replace` does not exist. Signature is
  `run_workflow(run_config, *, dry_run=False, replace=False)`.
- **`stage_input.build_stage_inputs` requires `config_dir`** (the workflow dir) to resolve
  `adapter:` and seed hooks, so `run_stage` takes `workflow_dir` alongside `run_dir`.
- **`run_row` needs the run's ids explicitly** (`dataset_run_id`, `agent_token`,
  `agent_run_id`) rather than reverse-engineering them from `run_dir.name`.
- **The composed system prompt rides on the run entry** and is popped off before
  `write_stage`, so `run.json` keeps only `system_prompt_hash` — matching the committed
  `example-run`.
- **Run-config judge overrides are overlaid onto the rubric's pinned `judge:` block** inside
  `model_grader` before the stage runs. Anything preflighting the judge must apply the same
  overlay first, or it validates a provider the run will not use.
- **`dataset.for_agent` is checked against the workflow's ROOT stage**, not the first
  *selected* stage — otherwise `agents: [prototype-plan] --from-run …` would fail spuriously
  against a dataset whose `for_agent` is the root agent.

**Noise band (T10), as built.** Threshold is **2σ** over *pooled within-repeat-group*
deviations — pooling across all runs would fold a genuine prompt effect into the noise
estimate and let the guard swallow real regressions. Conservative rather than 1σ because the
costs are asymmetric: a falsely declared improvement gets written into an `AGENT.md` and
stays, while a false "within-noise" costs one more run. A scale-aware floor (1.0 point for
0–100 metrics, 0.01 for the 0–1 pass rate) stops two identical samples promoting a 0.1-point
move to "improved". **`improved` is unreachable without a band** — no repeat data yields
`unknown-variance`, never a silent assumption that a delta is real.

**Resolved integration conflict — judge preflight (T13).** `config.load_rubric` *warns* when
`judge.provider` names a provider `build_model` cannot honour; `judge.resolve_judge_model`
*hard-fails* on the same condition. These are complementary, not contradictory — but the
hard-fail currently happens at grade time, i.e. **after** the agent dispatches have already
been paid for. **T13 must preflight the judge before the first dispatch** (resolve it, or at
minimum run the same assertion) so a misconfigured judge costs nothing. `--no-judge` skips
the preflight.

This is live today: the shipped rubric pins `provider: anthropic` and this machine's
`ANTHROPIC_API_KEY` is empty, so the calibration run would dispatch 12 agent calls and then
fail. Bedrock (`eu.anthropic.claude-haiku-4-5`) and Mistral are configured.

```python
# hooks.py
def load_callable(reference: str, *, relative_to: Path) -> Callable
    """'./file.py:func' -> the function. Raises ValueError naming the file."""

# precheck.py
def run(response: str, config: dict, *, hook: Callable | None = None) -> tuple[bool, str]
    """Generic gate AND the custom hook. Reason: 'generic: ... | custom: ...'"""

# stage_input.py
@dataclass(frozen=True)
class StageInput:
    row_id: str; prompt: str; seed_files: dict[str, str]
    deliverable_file: str | None; industry: str; tags: list[str]
    expect: str                      # "pass" | "fail"
    upstream_chain: list[dict]       # [{agent, precheck_passed, score}]
    skip_reason: str | None

def build_stage_inputs(stage: dict, *, dataset: dict,
                       upstream_outputs: dict[str, dict]) -> list[StageInput]

# dispatch.py
@dataclass
class DispatchResult:
    row_id: str; agent_id: str; response: str
    system_prompt: str               # the COMPOSED prompt actually used
    errored: bool; error_reason: str | None
    tokens_in: int; tokens_out: int
    resolved_model_id: str; log_path: str; sandbox_run_id: str

async def run_row(stage_input: StageInput, *, agent_id: str, sandbox_run_id: str,
                  log_path: Path, provider: str | None = None,
                  model: str | None = None) -> DispatchResult

# judge.py
@dataclass
class JudgeVerdict:
    sub_scores: dict[str, int]       # {dimension_id: 0-100}, keyed by id NEVER index
    evidence: dict[str, str]; rationale: str
    strengths: list[str]; weaknesses: list[str]
    resolved_model_id: str; errored: bool; error_reason: str | None
    # NOTE: no `score`/`passed` — the weighted total and threshold live in scoring.py

async def grade(response: str, *, rubric: dict, system_prompt: str,
                prompt: str, precheck_reason: str) -> JudgeVerdict

# scoring.py  — pure, dicts in, dicts out
def weighted_total(sub_scores: dict[str, int], dimensions: list[dict]) -> float
def summarize_stage(runs: list[dict], grades: list[dict], rubric: dict) -> dict
def evaluate_baseline(summary: dict, baseline: dict, hashes: dict) -> dict

# compare.py — pure
def compare_runs(runs: list[dict]) -> dict          # 2+ run_summary+score payloads
def group_by_prompt(runs: list[dict]) -> dict       # chronological, per system_prompt_hash

# artifacts.py — pure I/O, sole owner of every path
def run_folder(dataset_run_id: str, *, workflow_dir: Path) -> Path
def new_dataset_run_id(dataset_id: str) -> str      # {YYMMDD-HHMMSS}-{dataset_id}
def write_stage(run_dir: Path, agent_token: str, *, runs, grades, score, output) -> None
def write_resolved_config(run_dir: Path, config: dict) -> None
def write_system_prompt(run_dir: Path, agent_token: str, prompt: str) -> None
def guard_append_only(run_dir: Path, agent_token: str, *, replace: bool) -> None
```

---

## Tasks

Legend — **owns**: files this task alone may create or edit. **needs**: task ids that must
land first.

### Wave 0 — unblock everything

| id | task | owns | needs |
|---|---|---|---|
| **T0** | Fix the last config bug: `workflow.yaml` stage-4 `seed_files` seeds `spec.md` and `design.md` with byte-identical content while claiming design.md is derived. Either drop `design.md` or let a `seed_files` value take the `./file.py:func` form. Needs a decision, then a one-line schema note in `model/README.md`. | `model/workflows/prototype/workflow.yaml`, `model/README.md` | — |
| **T1** | Package skeleton + freeze the contract above. `__init__.py` with the conventions docstring; the `sys.path` bootstrap in `grade_runner.py` only; empty modules with their final docstrings and signatures (no bodies). This is the file every parallel agent reads. | `__init__.py`, all 12 module stubs | — |

### Wave 1 — leaf modules, fully parallel

Every module here imports **nothing else in the package**, so these six can be built
simultaneously without coordination.

| id | task | owns | needs |
|---|---|---|---|
| **T2** | `hooks.py` — resolve `./file.py:func` relative to a config file via `importlib.util.spec_from_file_location`. Clear error naming the file and function on failure. | `hooks.py`, `tests/unit/test_grading_hooks.py` | T1 |
| **T3** | `precheck.py` — copy `run_precheck`/`_closing_tag`/`validate_precheck_config` + `cli._combined_precheck`. Change: `forbidden` is `[{pattern, reason}]` **regexes**; accepts a resolved hook. Test must assert `placeholder` inside `Search input placeholder: "..."` passes. | `precheck.py`, `tests/unit/test_grading_precheck.py` | T1 |
| **T4** | `dispatch.py` — copy `run_graded_scenario_once`, preserving every invariant in *Invariants that must survive verbatim*. Changes: returns `log_path` + `system_prompt` (not `run_dir`); one sandbox per row (`{dataset_run_id}-{row_id}`, assert ≤128 chars); `thread_id = f"{sandbox_run_id}:{agent_id}"`; pass `run_sandbox=` explicitly; empty response classified errored **before** precheck. Module-level `import agents.factory`, call through it. | `dispatch.py`, `tests/unit/test_grading_dispatch.py` | T1 |
| **T5** | `judge.py` — static `DimensionScore`/`JudgeOutput` schema (never dynamic). Score every dimension 0–100. Validate returned ids == rubric ids, keyed by id. **Hard-fail** on unhonoured/unconfigured judge provider (`build_model` only honours mistral). Grades against the passed-in composed prompt, never re-composing with `no_tools=True`. | `judge.py`, `tests/unit/test_grading_judge.py` | T1 |
| **T6** | `scoring.py` — weighted total; per-dimension aggregates; two averages + `average_clean_chain`; stddev/distinct; expect-aware pass rates + `negative_rows_correct`; clustered `recurring_weaknesses`; baseline verdict incl. `max_expected_stddev` and refusal on hash mismatch. | `scoring.py`, `tests/unit/test_grading_scoring.py` | T1 |
| **T7** | `artifacts.py` — run-folder path scheme, run-id minting, the four artifacts + `run_summary.json` + `grade_config.resolved.yaml` + `prompts/<agent>_system_prompt.md`; append-only guard, `--replace` supersede into `superseded/`, stale marking of later stages, `compute_system_prompt_hash`. | `artifacts.py`, `tests/unit/test_grading_artifacts.py` | T1 |

### Wave 2 — one in-package dependency each, parallel with one another

| id | task | owns | needs |
|---|---|---|---|
| **T8** | `config.py` — load/validate the four config kinds into frozen dataclasses; merge defaults < config < CLI with every override recorded; **registry assertion** (stage list == `get_pipeline_agents`, each `from:` == `AGENT.md consumes`); `for_agent` guard; three hashes (config/rubric/dataset), rubric hash excluding `baseline`; warn on a provider `build_model` cannot honour. | `config.py`, `tests/unit/test_grading_config.py` | T1, T2 |
| **T9** | `stage_input.py` — the five input shapes; fan-in **inner join on row id** with `skip_reason` rather than silent drops; `len(from) > 1` requires `template`; placeholders validated at load; `adapter` applied after composition; `seed_files` resolved per row; `expect: fail` and errored/failed-upstream skip policy (`on_upstream_failure`). | `stage_input.py`, `tests/unit/test_grading_stage_input.py` | T1, T2 |
| **T10** | `compare.py` — per-row and per-dimension deltas; precheck/threshold flips; `group_by_prompt` chronologically by `system_prompt_hash` with a met/not-met flag; **noise guard** that refuses to call a within-variance delta an improvement. | `compare.py`, `tests/unit/test_grading_compare.py` | T1, T6 |
| **T11** | `code_grader.py` — skeleton, dispatchable: read `prototype.html` from a run folder by `dataset_run_id`, call `static_check`/`render_check`, write findings keyed by row id. **Must not import `judge.py`.** | `code_grader.py`, `tests/unit/test_grading_code_grader.py` | T1, T7 |

### Wave 3 — orchestration

| id | task | owns | needs |
|---|---|---|---|
| **T12** | `model_grader.py` — `run_workflow → run_stage → run_row` only. Stage order from `workflow.yaml`, stop at first non-implemented stage; chaining via `output.json`; all-errored stage aborts the rest; row-level concurrency (bounded, per-row exceptions isolated, zero concurrent writers); `run_summary.json` written `status: running` before each stage and again after. | `model_grader.py`, `tests/unit/test_grading_model_grader.py` | T3–T9, T11 |

### Wave 4 — entry point and wiring

| id | task | owns | needs |
|---|---|---|---|
| **T13** | `grade_runner.py` — argparse for the full CLI surface; `--config` load/merge; credential gates; `--dry-run` printing the resolved plan + dispatch estimate; `report`/`compare` subcommands; human summary; exit non-zero on baseline FAIL. | `grade_runner.py`, `tests/unit/test_grading_runner.py` | T10, T12 |
| **T14** | `./evals/hybrid/eval.sh` — add the `grading)` arm **before** the `*)` catch-all; `exec "$PY" -m evals.grading.grade_runner "$@"`; usage block in the header in the existing aligned style; token-spend warning to stderr (always live, no `--live` flag). Leave `graded)`/`dataset)`/`report)` bound to `model_graded`. | `./evals/hybrid/eval.sh` | T13 |

### Wave 5 — verification and close-out

| id | task | owns | needs |
|---|---|---|---|
| **T15** | Full offline verification: all `test_grading_*` pass; **all 71 `test_model_graded_*` still pass**; config integrity checks (parses, registry match, weights sum 100, patterns compile); `--dry-run` on all three configs; `code_grader` replay against `example-run/`; `compare` on two committed runs. | — (runs checks) | T14 |
| **T16** | Docs close-out: update `PLAN.md` status, `README.md`, `model/README.md`, `configs/README.md` to describe a runner that exists. Record what shipped vs. deferred. | all `*.md` in `grading/` | T15 |
| **T17** | **Developer-run, live.** `./evals/grading/grade.sh smoke` (2 rows, no judge), then `grade.sh full`. Then calibrate: set `baseline.set_from` + hashes from that run. | `prototype_specify_rubric.yaml` | T15 |

---

## Parallelisation

```
T0 ─┐
T1 ─┴─► T2 T3 T4 T5 T6 T7  ─► T8 T9 T10 T11 ─► T12 ─► T13 ─► T14 ─► T15 ─► T16 ─► T17
        └── 6 in parallel ──┘  └─ 4 parallel ─┘                                  (human)
```

| Wave | Tasks | Parallel? | Why |
|---|---|---|---|
| 0 | T0, T1 | 2 agents | T1 freezes the contract — nothing else can safely start |
| 1 | T2–T7 | **6 agents** | every module imports nothing in-package; disjoint files |
| 2 | T8–T11 | **4 agents** | one leaf dependency each, no overlap between them |
| 3 | T12 | 1 | integrates everything; splitting it would create merge conflicts |
| 4 | T13, T14 | 1 (sequential) | T14 is 15 lines and depends on T13's module path |
| 5 | T15, T16 | 1 | verification must see the whole system |
| — | T17 | human | live tokens — never agent-initiated |

**Why the waves are shaped this way.** The dependency direction in the plan was chosen partly
for readability and partly so this graph would be wide: six leaf modules with zero in-package
imports is what makes a 6-way parallel wave possible at all. The pure-modules-take-dicts rule
in the contract is the other half — without it `scoring.py` would import `judge.py` and Wave 1
would collapse to a chain.

**Realistic saving.** 18 tasks; the measured critical path is **8** —
T1 → Wave 1 → Wave 2 → T12 → T13 → T14 → T15 → T16. So roughly **2.2×**, not 18×, because
everything from T12 onward is inherently sequential. Widening Wave 1 further would not help;
the tail is the constraint.

Verified mechanically: no dependency cycles, every dependency references a real task, and
**no two tasks own the same file** — which is what makes the parallel waves safe to run in
one repo.

### Agent dispatch

Each Wave-1/2 agent gets: the contract block above, its row from the task table, the code
style rules, and a hard boundary — **only edit the files in your `owns` column**. Files are
disjoint by construction, so parallel agents in one repo cannot conflict.

Each agent's definition of done, uniformly:

1. Module implements the contract signature exactly — no renegotiating a shape.
2. Tests pass offline, no model calls, no network.
3. `python3.11 -c "import evals.grading.<module>"` succeeds (no cycles).
4. No inline imports; docstrings present; `model_graded/` untouched.

**Integration risk to watch.** The contract is frozen at T1 but not *proven* until T12 wires
it together. If a Wave-1 agent finds the contract genuinely wrong, it must stop and report
rather than quietly widen a signature — a silently changed shape is exactly what turns a
6-way parallel wave into a debugging session.

---

## Traceability

Every `PLAN.md` section maps to at least one task:

| Plan section | Tasks |
|---|---|
| Task 0 — config bug | T0 |
| Files (12 modules) | T1–T13 |
| Code style | all (standing constraint) |
| Stage input composition | T9 |
| Full-workflow vs single-stage | T12, T13 |
| Run folder is append-only | T7 |
| Degraded / failed / negative rows | T4 (empty→errored), T6 (expect-aware), T9 (skip policy), T12 (abort) |
| Judge sub-scores | T5, T6 |
| Judge misconfiguration hard-fails | T5, T8 |
| Hashes | T7, T8 |
| Run config `--config` | T8, T7 (resolved snapshot), T13 |
| Closing the loop | T6 (aggregates, clustering), T10 (compare, noise), T4+T7 (composed prompt), T11 (code track) |
| Registry assertion | T8 |
| Concurrency: rows not stages | T12 |
| Copied dispatch path changes (6) | T4 |
| Invariants verbatim | T4 |
| CLI surface | T13, T14 |
| Tests (10 modules) | owned by each module's task |
| Verification (7 steps) | T15 (1–5), T17 (6–7) |
| Out of scope | not tasked, by design |
