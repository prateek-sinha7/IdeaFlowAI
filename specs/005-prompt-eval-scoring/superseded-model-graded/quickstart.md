# Quickstart: Model-Graded Eval Branch (LLM-as-Judge + Report)

## Preconditions

- `cd backend`, Python 3.11 (no venv — per this repo's dev-runtime convention).
- For the driver + pre-check only (no grading): `ANTHROPIC_API_KEY` set (or Bedrock resolvable)
  so `prototype-specify` itself can be invoked — same requirement as any existing `--live` run.
- For `--judge`: additionally, a usable judge model must resolve via `build_model()` — by
  default this is the *same* credential as above (no extra setup — `clarifications.md` Q1). To
  use a distinct judge provider, `MISTRAL_API_KEY` (spec `004` added Groq alongside it, but Groq was withdrawn on 2026-07-29).
- No database, no Docker, no frontend build required — this feature has no UI and no API
  surface (spec §3.4).

## Setup

Nothing to install beyond what the existing eval harness already requires — this spec adds no
new dependency (`build_model()` and its providers are already wired). After implementation
lands:

```bash
cd backend
python3.11 -m pytest tests/unit/test_model_graded_driver.py tests/unit/test_model_graded_judge.py \
  tests/unit/test_model_graded_report.py tests/unit/test_prototype_specify_nav_check.py -v
```

confirms the branch's own unit tests (all mocked/offline — no tokens spent) pass before running
anything live.

## Run / Exercise the feature

**1. Free sanity check (driver + pre-check only, zero judge tokens):**

```bash
./tests/evals/model_graded/model-graded.sh graded prototype_specify_<scenario-id>
```

Dispatches the scenario's brief to `prototype-specify`, captures its `<spec>...</spec>` response,
runs the deterministic pre-check, and prints PASS/MISS — no judge call, no report entry. This is
the free/offline-equivalent path for this branch, matching how a bare scenario name never spends
tokens on the existing `--live` track.

**2. Graded run (spends judge tokens, writes a report entry):**

```bash
./tests/evals/model_graded/model-graded.sh graded prototype_specify_<scenario-id> --judge
```

Same as above, plus: a judge model call scoring the response against the brief and
`prototype-specify`'s own rubric, and one new line appended to
`backend/tests/evals/reports/eval_report.jsonl`.

**3. Override the judge model** (e.g. to reduce self-preference bias by grading with a different
provider than the one that generated the response):

```bash
./tests/evals/model_graded/model-graded.sh graded prototype_specify_<scenario-id> --judge --judge-provider mistral
```

**4. View the accumulated report:**

```bash
./tests/evals/model_graded/model-graded.sh report
./tests/evals/model_graded/model-graded.sh report --last 10
```

Prints total graded runs, overall pre-check pass rate, overall judge pass rate (at the
threshold), average judge score — in aggregate and broken out per agent/scenario.

**5. The iterate-on-the-prompt loop** (Story 6 — this is the Standard Operating Procedure from
`spec.md` §1, in commands):

```bash
# Grade N samples in one shot so the pass rate is a real percentage, not one roll of the dice
./tests/evals/model_graded/model-graded.sh graded prototype_specify_<id> --judge --samples 10

# Pull up the worst-scoring runs' full rationale — read this before editing AGENT.md
./tests/evals/model_graded/model-graded.sh report --worst 5

# ... edit backend/agents/prompts/prototype-specify/AGENT.md by hand ...

# Re-run, then compare score by prompt version (system_prompt_hash changes when AGENT.md changes)
./tests/evals/model_graded/model-graded.sh graded prototype_specify_<id> --judge --samples 10
./tests/evals/model_graded/model-graded.sh report --by system_prompt_hash --target 90
```

The last command prints a per-prompt-version row (chronological) with average judge score and
whether it clears the `--target` bar — repeat steps 2–4 until it does. Nothing here is
automatic: every one of these commands is a separate, explicit invocation, and none of them
edits `AGENT.md` or re-runs on their own (spec NFR "Loop stays human-in-the-loop").

**Manual-run reminder** (per this repo's standing rule — see project memory): any command above
that spends real tokens (`--judge`, or the bare `graded` call itself, since it still invokes
`prototype-specify` for real) is something the user runs themselves. Do not script or
auto-trigger these from an agent.

## Validation Scenarios

Maps directly to `spec.md` §2's acceptance scenarios:

1. **Driver captures a text response correctly** (Story 1 AC1–2): run `graded
   prototype_specify_<id>` and confirm the printed response is wrapped in `<spec>...</spec>`
   with no other output before/after it.
2. **Pre-check catches a bad response** (Story 1 AC3): temporarily point the scenario at a
   scripted/mocked model that returns a response missing the `<spec>` wrapper or under the
   `min_pages` floor, and confirm the pre-check reports MISS with a specific reason (used by the
   `test_prototype_specify_nav_check.py` unit tests, not necessarily a live run).
3. **Judge grades independently of the pre-check** (Story 2 AC1–3): run `--judge` against a
   response that passes the pre-check; confirm the judge score/rationale is present and can be
   lower than "fully passing" even when the pre-check is PASS.
4. **Judge failure doesn't block the pre-check result** (Story 2 AC2): simulate a judge network
   error (unit test with a mocked failing `build_model()`); confirm the pre-check result is still
   returned and `judge_errored: true` is what gets recorded, not a silent omission.
5. **Report only grows** (Story 3 AC2): run `--judge` twice in a row; confirm
   `eval_report.jsonl` has two new lines and the first run's line is byte-identical to before the
   second run.
6. **Existing commands unaffected** (Story 4 AC2): run `./tests/evals/eval.sh <existing-scenario> --live`
   and `./tests/evals/eval.sh benchmark` exactly as before this spec; confirm output is unchanged.
7. **Missing judge credentials fail fast** (Story 4 AC3): unset all provider credentials, run
   `graded <id> --judge`; confirm the CLI errors before the agent-under-test call is ever made
   (no tokens spent on the run itself).
8. **Empty report summarizes cleanly** (Story 5 AC3): on a fresh checkout with no
   `eval_report.jsonl` yet, run `./tests/evals/model_graded/model-graded.sh report`; confirm it reports zero entries, not an
   error/stack trace.

## Rollback / Cleanup

- This feature is purely additive (new files + an additive `./tests/evals/eval.sh` change) — reverting is
  a plain `git revert` of the implementing commit(s); no migration to roll back, no data cleanup
  required for the existing (untouched) `common/`/`workflow/` track.
- Local cleanup after experimenting: `rm -rf backend/tests/evals/model_graded/logs/*` (per-run
  transcripts, disposable, same as the existing `tests/evals/logs/` convention) and/or
  `git checkout -- backend/tests/evals/reports/eval_report.jsonl` to discard local-only graded
  runs before committing (the file is git-tracked, so accidental local entries are easy to
  discard without affecting anyone else's copy).
