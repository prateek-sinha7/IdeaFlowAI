# API Contract: Grading Calibration

## HTTP / REST / RPC / UI

**None.**

`evals/grading/` is a developer CLI tool. It exposes no HTTP route, no RPC method, no
WebSocket event, and no UI surface. Nothing in `app/api/` is touched, and no frontend
consumes any of it. It is invoked by a human at a terminal and writes files.

The contracts that *do* exist are three: a **CLI surface**, a **model-output schema**, and
an **internal Python surface** other modules in the package call. They are specified below
because breaking any of them breaks a caller.

---

## 1. CLI contract — `grade.sh calibrate`

### New subcommand

```
./backend/evals/grading/grade.sh calibrate [--workflow prototype]
```

| property | value |
|---|---|
| Cost | **LIVE** — judge calls across 6 golden briefs × 5 stages + 2 fail fixtures |
| Warning banner | Required, matching the `rejudge` / `advise` pattern in `grade.sh` |
| Who runs it | **The user, always.** Never invoked automatically. |
| Reads | `golden/*/` and `golden/calibration/fail/*` — committed files, never `.runs/` |
| Writes | A calibration report; does not mutate rubrics or baselines |

### Exit codes

| code | meaning |
|---|---|
| `0` | every invariant held |
| `1` | an invariant failed — output names the brief, stage, dimension and triggering finding |
| `2` | usage error (unknown workflow, missing fixture, SHA-256 mismatch) |

### stdout contract

Must include, in order: a per-brief × per-stage score table; the four invariant checks with
observed values; the severity-fallback rate; and a paste-ready `baseline:` block for Phase 6.

### Unchanged subcommands

`run`, `plan`/`dry-run`, `smoke`/`small`/`full`/`partial`/`all`, `report`, `compare`,
`history`, `rejudge`, `advise`, `code`, `runs`, `configs`, `check`, `test` — all keep their
current arguments, output shape and exit codes. `calibrate` is additive.

---

## 2. Model-output contract — what the judge must return

The judge is called via `with_structured_output(JudgeOutput, include_raw=True)`. The schema
is the contract; the prompt must describe it in the same words.

### Request additions (`build_judge_prompt`)

Adds a severity definition block, verbatim-aligned with `data-model.md`:

- **blocking** — a reviewer would refuse to ship this
- **major** — a real gap a reviewer would require fixed; the artifact still functions
- **minor** — a nit or preference; not a defect

**Removed** from the prompt: the cap announcement (*"a dimension where you report one
weakness is capped at 84, two at 74…"*) and *"Scores above 90 should be rare"* — both
contradicted the 95 anchor and, together with the cap table, made 84 the effective ceiling.

### Response — per dimension

```json
{
  "id": "data_realism",
  "score": 92,
  "evidence": "…",
  "strengths": ["…"],
  "findings": [
    {"severity": "minor", "detail": "Node labels use 11.5px where body text is 14px."}
  ]
}
```

### Compatibility guarantee

A reply carrying the legacy `weaknesses: ["…"]` and no `findings` **must still be accepted**.
Each string becomes `{severity: "major", detail: …}` and the dimension is counted in
`severity_fallbacks`. Rejecting it would discard a verdict already paid for — the failure
mode `_lift_narrative` and `_join_evidence` already exist to prevent.

### Breaking-change policy

`dimension_weaknesses` stays in `JudgeVerdict` and in `<token>_grade.json` as a derived
view, so every stored run folder and both report renderers keep working without migration.

---

## 3. Internal Python contract

Signatures other modules depend on. Changing any of these is a breaking change within the
package.

| symbol | before | after | notes |
|---|---|---|---|
| `code_grader.blended_score(judge, code)` | `0.7·j + 0.3·c` | `min(0.7·j + 0.3·c, c + 15)` | **Signature unchanged.** Three call sites (`markdown_report.py:126`, `:579`, `compute_overall`) pick the band up for free — deliberate, so no path can be left on the old arithmetic. |
| `code_grader.grade_run_folder(..., render, interactions)` | default `False` | default **`True`** | Behaviour change for callers that omit the flags. The live path (`model_grader.py:198-199`) already passes `True`; the old default silently inflated `code_score`. |
| `judge.consistency_cap(n)` | `int` | **removed** | Replaced by `price_findings`. `test_grading_judge.py:502-508` asserts it directly and must be rewritten. |
| `judge.price_findings(reported, findings)` | — | `(score: int, breakdown: dict)` | **New.** Pure, no model, no I/O. |
| `judge._capped_sub_scores(dimensions)` | `(sub_scores, score_caps)` | same tuple, richer `score_caps` | Contract preserved; entries now present for every dimension, not only reduced ones. |
| `judge.CONSISTENCY_CAPS`, `CONSISTENCY_CAP_FLOOR` | module constants | **removed** | Replaced by `BLOCKING_CAP`, `SEVERE_PENALTY`, `MINOR_PENALTY`, `MINOR_FLOOR`. |
| `scoring.weighted_total(sub_scores, dimensions)` | | **unchanged** | Weights stay out of the judge schema so a weight edit is recomputable over stored sub-scores. |

---

## 4. File-format contract

| path | contract |
|---|---|
| `golden/calibration/top/*.verdict.json` | Must carry `weights`, `judge_reported`, `after_caps`, `score_caps`, `findings_by_dimension`, `reported_total`, `capped_total`, `code_score`, `precheck_passed`, plus a `headline` block. Re-frozen whenever the golden artifacts or rubric weights change. |
| `golden/calibration/fail/*.verdict.json` | Must carry `sha256`, `code_score`, `static_issues`, `precheck_passed`, `expected_band`. `calibrate` verifies the hash before grading; a mismatch is an error. |
| `<token>_grade.json` | Gains `dimension_findings` and `severity_fallbacks`; retains `dimension_weaknesses`. Readers must accept both `score_caps` shapes, keyed on the presence of `final`. |
