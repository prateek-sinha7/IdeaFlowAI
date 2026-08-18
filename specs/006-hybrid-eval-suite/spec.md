# Feature Specification: Revision Fulfilment & the Hybrid Eval Suite (`evals/hybrid/`)

**Spec ID**: 006-hybrid-eval-suite
**Created**: 2026-07-22 (as `.investigations/revision-pipeline-thinking-issue/`)
**Promoted to a spec**: 2026-07-29 — moved out of `.investigations/` so the suite that guards the
revision pipeline sits alongside every other spec.
**Status**: **OBSOLETE (2026-08-10).** Phases 0–2 built; Phase 3 — the actual fix — was stopped
by explicit user instruction on 2026-07-22 and never resumed. The suite that reproduced the
defect lived in `backend/evals/hybrid/`, which was deleted by
[007-minimal-eval](../007-minimal-eval/spec.md), so nothing here is runnable. The underlying
defect may or may not still exist — `THINKING_BUDGET_TOKENS` is still `0` in
`app/core/config.py` — but any revival must be re-scoped against current code rather than
resumed from this document. Read for history only.
**Stack**: python | fastapi | (no frontend surface)

---

## 1. Problem statement

When you ask the revision pipeline to fix something on a prototype, it can report "done" and
update the file **without actually fixing what you asked for**.

Nothing in the pipeline ever checks the edit against your instruction — it only checks that the
HTML is still structurally valid. A harmless-looking no-op edit passes every gate.

That is root cause **A2** in [`FINDINGS.md`](FINDINGS.md): both validation layers
(`static_check`, `render_check`) check *structural health* only. There is no instruction-
fulfilment check anywhere in the run loop, so "the page is still valid HTML" is mistaken for
"the user's request was satisfied".

A second, smaller issue — no "thinking" is visible during a run, broken in four separate places
(FINDINGS B1–B5) — is **parked** by decision on 2026-07-22, to be picked up only after the main
defect is closed.

## 2. Why this spec is eval-first

The plan deliberately inverts the usual order: **the fix may not land until an eval suite first
reproduces the defect.** A structural bug that no test can demonstrate is a bug that will come
back. That decision (2026-07-22) is what produced `backend/evals/hybrid/` — the suite is a
by-product of specifying the fix, not a separate initiative.

This is also why the suite's verdicts are **code, never a model**: "did the Save button end up
with a working handler?" is a fact you can check by reading the delivered HTML. It costs nothing,
never drifts, and is the same answer every run. Contrast [`005-prompt-eval-scoring`](../005-prompt-eval-scoring/spec.md),
which grades *quality* with a judge model and is necessarily an opinion.

## 3. What exists today

`backend/evals/hybrid/`, driven by its own CLI, `./evals/hybrid/eval.sh`:

| Piece | What it does |
|---|---|
| `workflow/<domain>/<variant>/` | Per-pipeline coverage, mirroring `agents/workflows/<pipeline_type>/`. Only `prototype/revision` is populated today. |
| `common/` | The live-scenario driver (`live_scenario.py`), cross-pipeline scenario discovery, and shared offline test helpers |
| `engine/` | Tests of mechanisms used by **multiple** pipelines — verified by grep across every manifest before anything lands here, not assumed |
| `checkers.py` | The deterministic verdict: ~10 named checks, one per known bug |
| `scenarios/*.yaml` | Declarative scenarios; a new YAML gets live coverage with no new Python |
| `validate_scenario.py` | Proves a checker correctly flags the **raw** fixture as unmet — an always-true checker can never demonstrate a fix |
| `live_benchmark.py` | Repeats a scenario N times for a pass **rate**, since one roll of a probabilistic model proves little |

**Offline by default, 0 tokens.** `--live` is a universal flag, never a command name and never
implicit. The suite is also hermetic: a session-scoped fixture swaps the DB engine for in-memory
SQLite, so evals run identically whether Postgres is up or down.

**Current live scenario:** `prototype_multi_issue_repair` — 10 independent bugs in one ~8 KB
fixture (duplicated document, dead Save button, missing Reports page, and 7 more), so a single
run answers whether one revision turn fixes a realistic punch list rather than one isolated
defect. The earlier one-bug-per-scenario set and the offline S1/S2/S3 scripted matrix were
retired in favour of it.

## 4. Status by phase

| Phase | Scope | State |
|---|---|---|
| 0 | Scaffold the suite + hello-world harness gate | **done** |
| 1 | Layered unit tests along the issue surface (API → compile → context seed → post-step → selection semantics → LLM boundary) | **done** |
| 2 | Defect evals reproducing the bug, plus a happy-path control | **done** |
| 3 | **The fix** — the `instruction_fulfillment` capability | **not started** |
| 4 | The parked "no thinking visible" work | not started |

**Do not start Phase 3 without an explicit go-ahead** — that was the standing instruction when
work stopped, and it still holds. Phase 3's shape is not specified here: the earlier fix plan
targeted the retired S1/S2 fixtures and was deleted with them, so it needs re-planning against
the current `prototype_multi_issue_repair` scenario when the time comes.

## 5. Agent-tooling frictions this suite keeps surfacing

Two verified frictions in the agent's file tools, independent of any one scenario. Both still
hold, and both make a revision turn more expensive and more likely to miss:

- **`write_file` is create-only.** It refuses to overwrite (deepagents' `FilesystemBackend`), so
  a revision agent's first instinct fails and it must fall back to `edit_file`. The prototype
  build loop works around this by convention — Task 1 uses `write_file`, everything after uses
  `edit_file`.
- **`edit_file` requires an exact match.** Removing a large duplicated region means emitting the
  entire old block verbatim, which pushes the model into long, error-prone edits. A single
  observed run spent 8.1M input tokens grinding through 18 large `edit_file` calls and still
  finished with one page duplicated — while declaring success.

The per-scenario prompt-iteration work that produced these observations targeted the retired
S1/S2/`example1` fixtures and was deleted with them; the findings above are what survived.

## 6. Documents

These are the original investigation documents, moved verbatim. Filenames are unchanged because
four source files cite them by name.

| Document | Holds |
|---|---|
| [`quickstart.md`](quickstart.md) | **How to run it**, and the recipe for adding a new pipeline's coverage |
| [`data-model.md`](data-model.md) | Scenario YAML schema, `LiveScenario`, `LiveRunResult`, discovery, run output |
| [`contracts/checker-contract.md`](contracts/checker-contract.md) | The checker signature and the six rules that keep verdicts trustworthy |
| [`research.md`](research.md) | The design calls — code vs judge, scripted vs live, one bug vs ten, where it lives |
| [`FINDINGS.md`](FINDINGS.md) | File/line-cited root causes — A = the open fix gap, B = the parked thinking issue |
| `prompt-dumps/` | The fully composed system prompts each revision agent actually receives, plus the dispatch message. Regenerate with `./evals/hybrid/eval.sh prompts` (free). |

## 6. Notes on this folder

The "living reference" the suite always needed — how to run it, and the step-by-step recipe for
adding a new pipeline's coverage — is [`quickstart.md`](quickstart.md). The scenario/checker
shapes it refers to are specified in [`data-model.md`](data-model.md) and
[`contracts/checker-contract.md`](contracts/checker-contract.md).

Historical paths inside the original investigation documents were updated for the two 2026-07-29
moves (`tests/evals/` → `evals/hybrid/`, `run-eval.sh` → `evals/hybrid/eval.sh`). Findings,
evidence tables and dated log entries were left exactly as written.
