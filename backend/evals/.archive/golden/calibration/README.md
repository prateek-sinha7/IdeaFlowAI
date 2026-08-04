# `calibration/` — the two ends of the scale, frozen

`.runs/` is **gitignored and disposable** (`evals/grading/.gitignore:7`). Everything in this
folder was extracted out of it on **2026-07-30** so that clearing run folders cannot destroy
the evidence the grading scale is calibrated against.

Nothing here is run output. These are committed fixtures.

```
calibration/
├── top/
│   └── mission_control.verdict.json      ← what the grader DID to a verified-perfect artifact
└── fail/
    ├── clinic_scheduler_broken.html      ← real broken agent output
    └── clinic_scheduler_broken.verdict.json
```

## `top/` — the known-good end

The artifacts themselves live at `../mission_control/` and are already committed. What was
**not** durable is the graded verdict: `mission_control.verdict.json` freezes, per stage,
what the judge actually reported, what the caps did to it, and every finding that triggered
a cap.

It is the primary evidence for spec `008-grading-calibration`:

| stage | judge reported | after caps | code | dimensions capped |
|---|---|---|---|---|
| prototype-specify | 94.40 | **84.40** | — | 2 / 3 |
| prototype-plan | 91.60 | **84.40** | — | 2 / 3 |
| prototype-analyze | 97.45 | **88.00** | — | 2 / 3 |
| prototype-build | 94.55 | **80.00** | 100 | **3 / 3** |
| prototype-validate | 94.55 | **88.95** | 100 | 2 / 3 |
| **mean** | **94.51** | **85.15** | | **11 / 15** |

Recorded overall: **B / 87.0**.

Every stage was capped. Eleven of fifteen dimensions were capped. Not one cap was triggered
by a defect — the findings are things like *"node labels use 11.5px where body text is
14px"* and *"the metric could be contextualised with industry benchmarks"*. The judge's own
rationale called the build *"exceptional … near-flawless"* and scored it 92/95/98; the cap
table rewrote that to 74/84/84 purely because three sentences had been written down.

That 9.36-point gap between what the judge said and what the harness recorded is the defect
008 exists to fix.

## `fail/` — the known-bad end

`clinic_scheduler_broken.html` is **real agent output** from run `260730-012401-small`, not
a file broken on purpose. It matters that it is real: a synthetic fixture only proves the
harness catches defects that were chosen in advance to be catchable.

- `code_score` **0.0** — 7 structural issues (five dead `#/patient/:id` nav links, a routes
  map missing `patient-detail`, an extra `patientDetail` entry matching no section)
- `precheck_passed` **false** — so with `skip_on_precheck_failure: true` it never reached the
  judge at all, which is why no judge score was ever recorded for it

A second fixture, `hollow_console.html`, is specified but **not yet written**: a page that
passes every structural check and is empty inside — the defect class no automated check can
see. See spec 008 §3.2.

## Re-freezing after a new golden run

```bash
cd backend/evals/grading
python3.11 - <<'PY'
# regenerate top/mission_control.verdict.json from a fresh run folder
# (see specs/008-grading-calibration/spec.md §3.7 for the exact fields)
PY
```

Re-freeze whenever the golden artifacts change, the rubric weights change, or a new
calibration run is recorded — and commit it in the same change, so the fixture and the
scale it calibrates never drift apart.
