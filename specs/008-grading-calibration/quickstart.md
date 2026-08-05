# Quickstart: Grading Calibration

How to exercise this change end to end, and how to tell it worked.

---

## Preconditions

| | |
|---|---|
| Python | `python3.11` on PATH (no venv — project convention) |
| Working dir | `backend/` for anything importing `app.*`; `repo root` for `./backend/evals/grading/grade.sh` |
| Judge credential | `MISTRAL_API_KEY` set — **only** needed for the live step |
| Browser | Chromium via Playwright for the code track. Absent is fine: checks degrade to `available: false` and subtract nothing |
| Fixtures | Already committed at `backend/evals/grading/model/workflows/prototype/golden/calibration/` |

Verify the fixtures survived and are tracked:

```bash
cd /Users/bilala/Developer/Projects/VELOCITY-AI
git check-ignore backend/evals/grading/model/workflows/prototype/golden/calibration/fail/clinic_scheduler_broken.html \
  && echo "PROBLEM: ignored" || echo "OK: tracked"
```

---

## Setup

Nothing to install or migrate. The whole change is source edits inside
`backend/evals/grading/`.

Baseline the current behaviour before touching anything, so the delta is measurable:

```bash
cd backend
python3.11 -m pytest tests/unit/test_grading_judge.py \
                     tests/unit/test_grading_code_grader.py \
                     tests/unit/test_grading_markdown_report.py -q
```

---

## Run / Exercise the feature

### Steps 1–4 — offline, no tokens

```bash
cd backend

# after each phase
python3.11 -m pytest tests/unit/test_grading_*.py -q

# config integrity: every YAML/JSON parses, rubrics resolve, hooks import
./evals/grading/grade.sh check
```

Pricing can be exercised directly, without a model:

```bash
cd backend && python3.11 -c "
import app.core.config
from evals.grading.model import judge
F = judge.Finding
print('clean          ', judge.price_findings(98, []))
print('4 nits         ', judge.price_findings(98, [F(severity='minor', detail=str(i)) for i in range(4)]))
print('1 major        ', judge.price_findings(92, [F(severity='major', detail='thin detail page')]))
print('1 blocking     ', judge.price_findings(90, [F(severity='blocking', detail='detail page empty')]))
"
```

Expected: `98 → 98`, `98 → 94`, `92 → 84`, `90 → 45`.

And the band, also model-free:

```bash
cd backend && python3.11 -c "
from evals.grading.code import code_grader as c
for code, jud in [(100,92),(85,92),(70,92),(40,90),(0,90)]:
    print(f'code {code:>3}  judge {jud}  ->  {c.blended_score(jud, code):.1f}')
"
```

Expected: `94.4 / 89.9 / 85.0 / 55.0 / 15.0`.

### Step 5 — LIVE, the user runs this

```bash
cd /Users/bilala/Developer/Projects/VELOCITY-AI
./backend/evals/grading/grade.sh calibrate
```

Judge calls across six golden briefs × five stages plus both fail fixtures. Prints the
observed ceiling, the three invariants, and a paste-ready `baseline:` block.

> This is the only step that spends tokens, and it is **yours to run** — never launched
> automatically.

### Step 6 — after calibrate

Re-pin all five `set_from` blocks from the printed block, re-derive `min_average_score`, and
re-freeze `calibration/top/mission_control.verdict.json` under the new scale — in one commit,
so the fixture and the scale cannot drift apart.

---

## Validation Scenarios

### V-1 — The golden recovers (the headline)

Replays the frozen verdict through the new pricing; no model, no network:

```bash
cd backend && python3.11 -c "
import json, app.core.config
from evals.grading.model import judge
v = json.load(open('evals/grading/model/workflows/prototype/golden/calibration/top/mission_control.verdict.json'))
old = new = 0
for name, st in v['stages'].items():
    tot = 0
    for dim, w in st['weights'].items():
        f = [judge.Finding(severity='minor', detail=d) for d in st['findings_by_dimension'].get(dim, [])]
        tot += judge.price_findings(st['judge_reported'][dim], f)[0] * w
    tot /= 100
    old += st['capped_total']; new += tot
    print(f'{name:22} was {st[\"capped_total\"]:6.2f}  ->  now {tot:6.2f}   (judge said {st[\"reported_total\"]})')
print(f'\nrun mean  {old/5:.2f}  ->  {new/5:.2f}')
"
```

**Pass**: every stage rises, the mean moves from **85.15** to **93.57**, and no stage
exceeds its `reported_total` — pricing may only ever subtract.

*(Every finding in that fixture is cosmetic, which is the point; the replay tags them `minor`
because that is what a correctly-instructed judge would have returned.)*

### V-2 — The golden is untouched by the band

`code_score` is 100 on both HTML stages, so `code + 15 = 115` never binds.
**Pass**: build and validate `effective` values are identical before and after Phase 3.

### V-3 — Broken output fails

```bash
cd backend && python3.11 -c "
import json, app.core.config
from evals.grading.code import code_grader
p = 'evals/grading/model/workflows/prototype/golden/calibration/fail/'
html = open(p + 'clinic_scheduler_broken.html').read()
f = code_grader.check_html(html)
print('code score', code_grader.compute_code_score(f))
for i in f['issues']: print('  -', i)
print('if a judge somehow gave it 90:', code_grader.blended_score(90, code_grader.compute_code_score(f)))
"
```

**Pass**: `code score 0.0`, 7 issues listed, and the blend returns **15.0 (F)** where today
it returns 63.0 (D).

### V-4 — The fixture is intact

**Pass**: the file's SHA-256 matches `clinic_scheduler_broken.verdict.json`, and its
`code_score` is still 0.0 with the same 7 issues. A drift here means `static_check` changed
under the fixture.

### V-5 — A legacy judge reply still parses

Feed a reply with flat `weaknesses: ["x","y"]` and no `findings`.
**Pass**: the verdict parses, both entries become `major`, the score drops 16, and
`severity_fallbacks` is 1. **Fail**: any exception, or a discarded verdict.

### V-6 — No report path is left on the old arithmetic

```bash
cd backend && python3.11 -m pytest tests/unit/test_grading_markdown_report.py -q
```

**Pass**: `compute_overall`, the phase table's `effective` column and the per-row table all
reflect the band, because all three route through `blended_score`.

### V-7 — `hollow_console.html` tests the right half

**Pass**: it passes precheck, scores ≥ 90 on the code track, and ≤ 50 overall once judged.
If the code track scores it low, it has become a structural fixture and no longer tests the
judgement half — rewrite it.

### V-8 — The calibration invariants hold *(after Step 5)*

**Pass**: golden ≥ 90 each, `clinic_scheduler_broken` ≤ 20, `hollow_console` ≤ 50,
separation ≥ 25. Any failure names the brief, stage, dimension and triggering finding.

---

## Rollback / Cleanup

Every change is source-level and reversible with `git revert`. Notes:

| | |
|---|---|
| **Reverting Phases 1–3** | Restores the old caps and blend. Stored `<token>_grade.json` files stay readable — the renderer accepts both `score_caps` shapes. |
| **Reverting Phase 6 only** | Leaves baselines pinned to a hash the rubrics no longer produce, so every run reads `REFUSED`. Loud and safe, but revert Phase 4 with it. |
| **Never delete** `golden/calibration/` | It is the evidence, and it was rescued from a gitignored folder precisely because it was fragile. Re-freezing is the way to update it. |
| **Run folders** | `.runs/` is disposable by design. Nothing here depends on it after Phase 0. |
| **No cleanup needed** | No database, no service, no deployed artifact. |
