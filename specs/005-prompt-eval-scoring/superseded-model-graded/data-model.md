# Data Model: Model-Graded Eval Branch (LLM-as-Judge + Report)

No PostgreSQL schema changes (spec §3.3). This feature's "data model" is entirely in-process
Python dataclasses plus one flat file format (JSON Lines). Documented here for completeness per
the planning template.

## Entities

### `GradedScenario` (in-memory, loaded from YAML)

The unit of "what to run" — one per `model_graded/agents/<agent>/scenarios/*.yaml` file.

| Field | Type | Constraints |
|---|---|---|
| `id` | `str` | Required; must match the YAML filename stem (mirrors the existing `LiveScenario` convention — a scenario answers to one name) |
| `agent_id` | `str` | Required; must resolve via `agents/registry.py::get_agent_by_id` — dispatch stays on `create_runner` (`clarifications.md` Q9, reused as-is, not bypassed) |
| `prompt` | `str` | Required; the brief/message dispatched to the agent. Loaded inline (`prompt:`) or from a sibling file (`prompt_file:`) — implementation choice, following the existing `instruction`/`instruction_file` dual-mode pattern |
| `min_pages` | `int` | Optional; defaults to 4 (`clarifications.md` Q2) |
| `design_md` | `str \| None` | Optional; injected template/design-system fixture content, only if the scenario supplies one |
| `precheck_config` | `dict` | Required; the scenario's `precheck:` YAML block — `wrapper: str`, `min_sections: int`, `section_pattern: str`, `forbidden: list[str]` — consumed by the **generic**, shared `precheck.py::run_precheck(response, config)` (`clarifications.md` Q10; no per-agent Python) |
| `precheck_module` | `Callable[[str], tuple[bool, str]] \| None` | Optional; a **narrow custom hook** for checks the generic config can't express (e.g. `prototype-specify`'s nav-target cross-reference), run in addition to, not instead of, `precheck_config`'s generic check |
| `rubric` | `str` | Required; plain text/markdown judge-grading criteria, fed as-is into the **one shared** rubric-prompt-builder in `judge.py` (`clarifications.md` Q10; no per-agent rubric module) |
| `logs_dir` | `Path` | Set by the loader; defaults to `model_graded/logs/` |

### `GradedRunResult` (in-memory, produced by the driver)

| Field | Type | Notes |
|---|---|---|
| `scenario_id` | `str` | |
| `agent_id` | `str` | |
| `response` | `str` | Raw captured text — the deliverable itself, no filesystem read-back |
| `precheck_passed` | `bool` | |
| `precheck_reason` | `str` | |
| `errored` | `bool` | Infra failure (auth, network) — distinct from a real-but-unsatisfactory response, mirroring `LiveRunResult.errored`'s existing distinction |
| `error_reason` | `str \| None` | |
| `tokens_in` / `tokens_out` | `int` | |
| `run_dir` | `str` | Path to `model_graded/logs/<run_id>/` |

### `JudgeVerdict` (in-memory, produced by `judge.grade_run()`)

| Field | Type | Constraints |
|---|---|---|
| `score` | `int` | 0–100 |
| `passed` | `bool` | `score >= DEFAULT_JUDGE_THRESHOLD` (70, overridable per-run — `clarifications.md` Q3) |
| `rationale` | `str` | Required, non-empty on success |
| `errored` | `bool` | True if the judge call itself failed (network/parse error) |
| `error_reason` | `str \| None` | Populated iff `errored` |

### Report entry (persisted — one JSON object per line in `eval_report.jsonl`)

The durable record; not a Python class, but a fixed dict shape written/read by
`model_graded/report.py`. This is the only entity that actually persists across process runs.

| Field | Type | Constraints |
|---|---|---|
| `timestamp` | `str` (ISO 8601, UTC) | Required |
| `run_id` | `str` | Required; unique per entry (matches `run_dir`'s folder name) |
| `scenario_id` | `str` | Required |
| `agent_id` | `str` | Required — the field Story 5's per-agent breakdown groups on |
| `provider` | `str \| null` | Judge provider override used, or `null` for default |
| `model` | `str \| null` | Judge model override used, or `null` for default |
| `system_prompt_path` | `str` | Path to the agent's `AGENT.md` |
| `system_prompt_hash` | `str` | `sha256:<hex>` of the `AGENT.md` content at run time |
| `prompt` | `str` | The brief/message sent |
| `response` | `str` | The full raw response (inlined — no separate artifact file exists for this branch's deliverable) |
| `run_dir` | `str` | Path to the full transcript/log folder |
| `precheck_passed` | `bool` | |
| `precheck_reason` | `str` | |
| `judge_score` | `int \| null` | `null` only if `--judge` was never passed for this run (a driver-only, ungraded entry is never written — see Validation Rules) |
| `judge_passed` | `bool \| null` | |
| `judge_rationale` | `str \| null` | |
| `judge_errored` | `bool` | |
| `tokens_in` / `tokens_out` | `int` | |

## Fields and Constraints

- `run_id` format: `<yymmddhhmmss>-graded-<scenario_id>-<uuid8>`, matching the existing
  `<yymmddhhmmss>-live-<scenario_id>-<uuid8>` convention from `common/live_scenario.py` (sortable
  by name, collision-proof via the UUID suffix).
- `system_prompt_hash` is always computed fresh from the on-disk `AGENT.md` at run time — never
  cached across runs — so a report reader can always detect prompt drift between entries. This
  is also the grouping key for Story 6's per-prompt-version trend view
  (`report --by system_prompt_hash [--target T]`) — no separate "prompt version" entity exists;
  the hash *is* the version identity.
- Every report entry corresponds to exactly one `run_graded_scenario_once()` call that was
  followed by a `grade_run()` call — i.e. entries are only ever written for `--judge` runs
  (Story 4 Acceptance Scenario 1: a bare `graded <scenario-id>` with no `--judge` produces no
  report entry at all, matching the existing track's "a bare scenario name never spends tokens /
  never gets recorded" behavior).

## Relationships

```
GradedScenario (1) ──run_graded_scenario_once()──> (1) GradedRunResult
GradedScenario + GradedRunResult ──grade_run()──> (1) JudgeVerdict
GradedRunResult + JudgeVerdict ──append_entry()──> (1) report entry (appended to eval_report.jsonl)
```

No entity has a foreign key into PostgreSQL or any other persisted application entity — this
data model is entirely self-contained within `backend/tests/evals/`.

## Migrations

None. No database involved (spec §3.3).

## Validation Rules

- `GradedScenario.id` must equal its source YAML filename stem (fail loudly at load time
  otherwise — same rule as the existing `LiveScenario` loader).
- `min_pages` must be a positive integer when present in YAML.
- A `JudgeVerdict` with `errored=True` must have a non-`None` `error_reason`, and must not have a
  populated `score`/`passed` (both stay at their type's zero-ish/`None` default) — an errored
  judge call must never be mistaken for a real low score.
- `report.append_entry()` must reject (raise, not silently drop) an entry missing any required
  field from the schema above — a malformed line must never reach the JSONL file (spec NFR
  "Report integrity").
- `report.append_entry()` must open the file in append mode and write exactly one line
  terminated by `\n` — never rewrite/truncate the existing file (enforces "the report only
  grows," spec Story 3 Acceptance Scenario 2).
