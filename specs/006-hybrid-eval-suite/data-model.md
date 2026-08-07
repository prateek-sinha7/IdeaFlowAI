# Data model

Every shape the hybrid suite reads or writes. Sourced from
`backend/evals/hybrid/common/live_scenario.py` and `common/scenario_discovery.py`.

---

## 1. Scenario YAML — the unit of coverage

One file per scenario, in `workflow/<domain>/<variant>/scenarios/`. Adding one gets live
coverage with no new Python. Files whose stem starts with `_` are skipped (the `_TEMPLATE.yaml`
convention).

```yaml
id: prototype_multi_issue_repair        # globally unique across every pipeline
name: Multi-issue repair (10 bugs)      # human label
description: >                          # what this scenario proves, and why it exists
  ...

agent_id: prototype-revision-agent      # must be a registered agent id

instruction: >                          # the user turn, verbatim as a human would type it
  ...

input:
  html: fixtures/<file>.html            # relative to the phase folder
  design_md: null                       # optional design-system markdown

output:
  filename: prototype.html              # the artifact read back and handed to the checker

logs:
  dir: .runs                            # run output, relative to evals/hybrid/

checker: prototype_multi_issue_repair   # key into the phase's CHECKERS registry

benchmark:
  expensive: false                      # true → excluded from `benchmark cheap`
  default_n: 5                          # sample count cap for expensive scenarios
```

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Must be globally unique — `discover_all_scenarios` enforces it |
| `agent_id` | yes | Resolved against the real agent registry |
| `instruction` | yes | Phrase it as a user would; it is the thing being tested |
| `input.html` | yes | The **broken** starting fixture |
| `input.design_md` | no | `null` when the pipeline takes no design system |
| `output.filename` | no | Defaults to `prototype.html` |
| `logs.dir` | no | Defaults to `.runs` |
| `checker` | yes | Must exist in the phase's `CHECKERS` dict or discovery fails |
| `benchmark.expensive` | no | Defaults `false` |
| `benchmark.default_n` | no | Defaults `10` |

## 2. `LiveScenario` — the loaded scenario

`@dataclass(frozen=True)`. Frozen on purpose: a scenario is an input, and a run must not be able
to mutate the thing it is measuring.

| Field | Type | Source |
|---|---|---|
| `id` | `str` | YAML `id` |
| `instruction` | `str` | YAML `instruction` |
| `checker` | `Callable[[str], tuple[bool, str]]` | resolved from `CHECKERS` by name |
| `html` | `str` | contents of `input.html`, already read |
| `agent_id` | `str` | YAML `agent_id` |
| `design_md` | `str \| None` | contents of `input.design_md` |
| `output_filename` | `str` | default `"prototype.html"` |
| `logs_dir` | `Path \| None` | set by `load_scenario_yaml` |
| `expensive` | `bool` | default `False` |
| `default_n` | `int` | default `10` |
| `source_path` | `Path \| None` | set by `load_scenario_yaml`; for error messages |

## 3. `LiveRunResult` — the outcome of one live run

| Field | Type | Meaning |
|---|---|---|
| `scenario_id` | `str` | which scenario ran |
| `passed` | `bool` | the checker's verdict |
| `reason` | `str` | **why** — names the specific failure |
| `errored` | `bool` | infrastructure failure, not a model attempt |
| `static_ok` | `bool` | did the delivered file survive structural checks |
| `static_issues` | `list[str]` | structural problems found |
| `tokens_in` / `tokens_out` | `int` | real cost of this run |
| `tool_calls` / `tool_results` | `list[str]` | what the agent actually did |
| `streamed_text` | `str` | the model's narration |
| `final_html` | `str` | the delivered artifact, as handed to the checker |
| `run_dir` | `str` | where the full transcript was written |

**`errored` vs `passed` is a deliberate distinction.** An expired token is not the prompt's
fault, so errored runs are excluded from a benchmark's pass-rate denominator and reported
separately. Folding them in would quietly understate a prompt that is actually fine.

## 4. Discovery

| Function | Returns |
|---|---|
| `discover_scenarios_in(phase_dir, checkers)` | `dict[str, LiveScenario]` for ONE phase folder |
| `discover_all_scenarios()` | every scenario across every pipeline; raises on a duplicate id |

`EVALS_ROOT` is `backend/evals/hybrid/`; `WORKFLOW_ROOT` is `EVALS_ROOT / "workflow"`. Both are
derived from the module's own location, so moving the suite does not break discovery — as the
two 2026-07-29 moves demonstrated.

## 5. Run output

```
backend/evals/hybrid/.runs/<run-id>/          # gitignored via the repo-wide `.runs/` rule
```

One folder per real-model run, holding the full transcript. Local-only and regenerated;
`.runs/` replaced the older `logs/` name on 2026-07-29 so every eval package shares one
convention.
