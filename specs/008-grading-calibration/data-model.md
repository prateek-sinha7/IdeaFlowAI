# Data Model: Grading Calibration

There is no database. The "data model" here is the **judge's structured-output schema**, the
**JSON artifact shapes** written into run folders, and the **committed fixture files**.
Nothing persists outside the filesystem.

---

## Entities

| Entity | Kind | Where it lives |
|---|---|---|
| `Finding` | **new** Pydantic model | `model/judge.py` |
| `DimensionScore` | modified Pydantic model | `model/judge.py` |
| `JudgeOutput` | unchanged | `model/judge.py` |
| `JudgeVerdict` | modified dataclass | `model/judge.py` |
| `score_caps` entry | modified dict shape | `<token>_grade.json` |
| `TopVerdictFixture` | **new** JSON schema | `golden/calibration/top/*.verdict.json` |
| `FailFixtureVerdict` | **new** JSON schema | `golden/calibration/fail/*.verdict.json` |

---

## Fields and Constraints

### `Finding` — new

| field | type | constraint | meaning |
|---|---|---|---|
| `severity` | `Literal["blocking","major","minor"]` | required | how bad |
| `detail` | `str` | required, non-empty after strip | one self-contained sentence |

Prompt-side definitions (must appear verbatim in the rubric prose so the judge and the code
agree on the words):

- **blocking** — a reviewer would refuse to ship this. Something is missing, wrong, or
  broken enough that the artifact fails its purpose.
- **major** — a real gap a reviewer would require fixed, but the artifact still functions.
- **minor** — a nit, a preference, a "could also have". Not a defect.

### `DimensionScore` — modified

| field | type | change |
|---|---|---|
| `id` | `str` | unchanged |
| `score` | `int`, `ge=0 le=100` | unchanged |
| `evidence` | `str` | unchanged (keeps the list-joining `mode="before"` validator) |
| `strengths` | `list[str]` | unchanged |
| `weaknesses` | `list[str]` | **removed from the schema**, retained as a read-only derived property `[f.detail for f in findings]` |
| `findings` | `list[Finding]` | **new**, default `[]` |

**Legacy-shape validator** (`mode="before"`, AD-3): if the payload carries `weaknesses` as a
list of strings and no `findings`, lift it to `[{"severity": "major", "detail": w} for w in
weaknesses]`. Records `_severity_fallback = True` on the entry so the run can report how
often it fired.

### `JudgeVerdict` — modified

| field | type | change |
|---|---|---|
| `sub_scores` | `dict[str,int]` | unchanged — post-pricing values |
| `evidence`, `rationale`, `strengths`, `weaknesses` | | unchanged |
| `dimension_weaknesses` | `dict[str, list[str]]` | **retained as derived** — stored grades and the report renderer read it |
| `dimension_findings` | `dict[str, list[dict]]` | **new** — `[{severity, detail}]` per dimension, verbatim |
| `score_caps` | `dict[str, dict]` | shape extended, see below |
| `severity_fallbacks` | `int` | **new** — how many dimensions used the legacy lift |
| everything else | | unchanged |

### `score_caps` entry — modified shape

Before:
```json
{"data_realism": {"reported": 92, "capped_to": 74, "weaknesses": 2}}
```

After — the arithmetic is now fully reconstructible from the record:
```json
{"data_realism": {
   "reported": 92,
   "final": 90,
   "severe": 0,
   "minor": 2,
   "severe_penalty": 0,
   "minor_penalty": 2,
   "blocking_cap_applied": false,
   "findings": [{"severity": "minor", "detail": "…"}, …]
}}
```

Present for **every** dimension, not only reduced ones — a dimension that lost nothing is
evidence too, and its absence was previously indistinguishable from "not recorded".

---

## Relationships

```
JudgeOutput.dimensions[] ──> DimensionScore.findings[] ──> Finding
                                    │
                    price_findings(reported, findings)
                                    │
                                    ▼
              JudgeVerdict.sub_scores  +  score_caps  +  dimension_findings
                                    │
                     scoring.weighted_total(sub_scores, dimensions)
                                    │
                                    ▼
                        row["score"]  (the judge total)
                                    │
        code_grader.blended_score(judge_score, code_score)   ← CODE_BAND applies here
                                    │
                                    ▼
              markdown_report._cell_value → compute_overall → letter_grade
```

Two invariants worth stating because they are load-bearing:

1. **Weights are never baked into the schema.** `weighted_total` applies them in
   `scoring.py`, so a weight edit is recomputable over stored sub-scores without a re-run.
   This is why `top/*.verdict.json` stores the `weights` it was scored under.
2. **`blended_score` is the single chokepoint.** Every consumer
   (`markdown_report.py:126`, `:579`, `compute_overall`) routes through it, so `CODE_BAND`
   cannot leave one report path on the old arithmetic.

---

## Migrations

No schema migration — JSON artifacts are read defensively.

| Concern | Handling |
|---|---|
| Old `<token>_grade.json` with a flat `dimension_weaknesses` and no `dimension_findings` | Reports render from `dimension_weaknesses`, which is retained. Findings render as "severity unknown". |
| Old `score_caps` entries with `{reported, capped_to, weaknesses}` | The renderer accepts either shape, keyed on the presence of `final`. |
| Stored `sub_scores` were produced under the old cap table | **Not recomputed.** They are a historical record of what the old scale did. `calibrate` produces the new numbers; the frozen fixture preserves the old ones for comparison. |
| `top/*.verdict.json` written before a rubric weight change | It stores its own `weights`, so a stale comparison is detectable rather than silently wrong. Phase 6 re-freezes it. |

---

## Validation Rules

### Pricing (`judge.price_findings`)

```
severe        = count(blocking) + count(major)
minor_penalty = min(4, count(minor))
score         = reported − 8·severe − minor_penalty
if count(blocking) > 0: score = min(score, 45)
score         = clamp(score, 0, 100)
```

- Monotonic in every input: adding a finding never raises a score.
- `reported` is already `0..100` by Pydantic constraint, so only the lower clamp can bite.
- The `blocking` cap applies **after** penalties, so two blockings score below one.

### Blending (`code_grader.blended_score`)

```
if judge is None: return code
if code  is None: return judge
blended = 0.7·judge + 0.3·code
return min(blended, code + 15)
```

- The `min` makes it a strict tightening — it can only ever lower a value.
- Unchanged when only one track scored a row.
- At `code = 100` the band is 115, so it never binds on a clean row.

### Fixture integrity

| Rule | Enforced by |
|---|---|
| `clinic_scheduler_broken.html` matches its recorded SHA-256 | `calibrate` verifies before grading; a mismatch is an error, not a warning |
| `hollow_console.html` **must pass** precheck and score ≥ 90 on the code track | Asserted in `calibrate`; if it starts failing structurally it has stopped testing the judgement half |
| `top/*.verdict.json` `weights` match the live rubric weights | `calibrate` warns on divergence and names the stale fixture |
| Fixture files are tracked, not ignored | `git check-ignore` verified 2026-07-30; re-verify in CI if one is ever added |

### Calibration invariants

| Invariant | Threshold |
|---|---|
| `min(golden overall)` | ≥ 90 |
| `clinic_scheduler_broken` overall | ≤ 20 |
| `hollow_console` overall | ≤ 50 |
| `min(golden) − max(fail)` | ≥ 25 |
| severity fallback rate across the run | ≤ 20%, else warn |
