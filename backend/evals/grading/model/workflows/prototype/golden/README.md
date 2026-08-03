# `golden/` — hand-crafted reference artifacts

One folder per brief — the two `prototype_small` briefs (`clinic_scheduler`,
`expense_approvals`) plus four from `prototype_complex`: `mission_control`
(the DIAGRAM-FIRST ceiling and the second pipeline-generated golden — an
inline-SVG program canvas with per-node change deltas, a rippling Gantt, and
an animated gate-chain walkthrough; 267 SVG elements, 3 keyframe animations),
`shelter_ops`
(generated END-TO-END by the pipeline's own stage prompts — each stage run
under the literal `agents/prompts/prototype-*/AGENT.md`, SHA-256-verified,
with the engine's per-task build loop and Both-validation fix pass; see
report.md "Pipeline provenance"), `fleet_dispatch`
(6 pages, a dynamic `#/trip/:id` route, a Mark-delivered mutation propagating
to four other pages) and `property_ops` (the complexity ceiling: 10 pages,
three dynamic `:id` routes plus a `#/workorders/new` create route, and full
CRUD — create with sequential id minting, assign, complete, cancel/DELETE,
record-payment — where every KPI, balance and count derives from one store) —
holding what a **flawless** run of the whole workflow would produce for it:

| file | stage it stands in for |
|---|---|
| `spec.md` | `prototype-specify` |
| `tasks.md` | `prototype-plan` |
| `analysis.md` | `prototype-analyze` |
| `prototype.html` | `prototype-build` — and `prototype-validate`'s `prototype.final.html`, since a flawless build needs no fixes |

## What "flawless" means here — all machine-verified

Every artifact passes its own stage's full precheck (generic gate + the
stage's `validate:` hook), and each `prototype.html` scores **100.0** on the
code track:

- `static_check` clean — no dead links, no orphans, routes table complete
- headless render clean — every nav target clicked activates its expected
  section, zero console errors / uncaught exceptions
- interaction sweep clean — every visible button and filter input exercised
  without an error
- beyond the harness: the dynamic detail routes (`#/patient/:id`,
  `#/expense/:id`, `#/trip/:id`) render **distinct** records per id with an
  unknown-id fallback; search/status filters actually filter; Approve/Reject
  flips the badge in place and the inbox reflects it after navigating back;
  in `fleet_dispatch`, Mark-delivered propagates through the store-derived
  views (Board, Exceptions, Drivers, Vehicles) rather than copied literals

The `routes` **array table** (`{ pattern: 'expense/:id', page: 'expense-detail' }`)
is the load-bearing pattern: it is what makes parametric routes resolvable to
`static_check`/`render_check` (via `app/agents/route_table.py`). A plain
hash-equals-section router cannot express these briefs — which is exactly the
failure the live agents exhibited.

## What they are for

- **A ceiling to grade against**: what a 100 looks like for these briefs, so
  judge scores and rubric anchors can be sanity-checked against a known-good
  document (if the judge gives the golden 89 and a broken run 91, the rubric —
  not the agent — is what needs fixing).

  **This is not hypothetical — it happened, and it is what `calibration/`
  exists to prevent recurring.** In run `golden-mission-control` the judge
  reported a mean of 94.51 across the five stages and the harness recorded
  85.15, because a cap table keyed on the COUNT of reported weaknesses pulled
  11 of 15 dimensions down. Not one of those caps was triggered by a defect;
  they were triggered by remarks like *"node labels are 11.5px where body text
  is 14px"*. Spec `008-grading-calibration` replaced counting with severity
  pricing, and the same stored verdict now prices to **93.57**. See
  `calibration/README.md`.
- **Prompt-improvement reference**: when `advise` proposes build-prompt edits,
  the golden HTML shows the concrete target behaviour (routes table,
  store-driven rendering, unknown-id fallback) an edit should steer toward.
- **Harness fixtures**: real-shaped inputs for tests and for `dry_run_sample`s
  without spending a token.

They are NOT run output: nothing under `.runs/` points here, and no score is
computed from them unless you feed them through something yourself.

## Calibration — `calibration/`

`calibration/` holds the two ends of the scale, extracted from the gitignored
`.runs/` tree so a cleanup cannot destroy them: `top/` is the frozen graded
verdict of `mission_control` (both the pre-fix numbers and their replay under
the current scale), and `fail/` holds the known-bad fixtures — one real broken
run output, one that passes every automated check and is empty inside.

```bash
./backend/evals/grading/grade.sh calibrate     # LIVE: judge calls
```

Grades every brief here plus both fail fixtures and asserts the scale is not
inverted: golden >= 90, each fail fixture inside its own declared band, and at
least 25 points between the worst golden and the best fail. Run it after ANY
rubric, anchor, pricing or prompt edit.

## Re-verify after editing

```bash
cd backend && python3.11 - <<'EOF'
import sys; sys.path.insert(0, ".")
import app.core.config
from pathlib import Path
from evals.grading import config
from evals.grading.model import precheck
from evals.grading.code import code_grader

wf = Path("evals/grading/model/workflows/prototype")
for brief_dir in sorted((wf / "golden").iterdir()):
    if not brief_dir.is_dir():
        continue
    for agent, fname in [("prototype-specify", "spec.md"), ("prototype-plan", "tasks.md"),
                         ("prototype-analyze", "analysis.md"), ("prototype-build", "prototype.html"),
                         ("prototype-validate", "prototype.html")]:
        rubric = config.load_rubric(wf, agent)
        ok, why = precheck.run((brief_dir / fname).read_text(), rubric["precheck"],
                               hook=rubric.get("validate_hook"))
        print(f"{brief_dir.name:20} {agent:22} {'PASS' if ok else 'FAIL ' + why}")
    html = (brief_dir / "prototype.html").read_text()
    finding = code_grader.check_html(html)
    finding["render"] = code_grader._render_findings(html)
    finding["interactions"] = code_grader._interaction_findings(html)
    print(f"{brief_dir.name:20} code score {code_grader.compute_code_score(finding)}")
EOF
```
