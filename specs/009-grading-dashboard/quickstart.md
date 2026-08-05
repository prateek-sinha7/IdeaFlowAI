# Quickstart: The Grading Dashboard

Everything here is **free and offline**. No path in this feature dispatches an agent, calls a
judge, or spends a token. Nothing below needs a live run.

---

## Preconditions

- Project python (`python3.11`, no venv — per the repo's dev-runtime convention).
- At least one run folder under `backend/evals/grading/.runs/<workflow>/`.
  There are **20** under `.runs/prototype/` today; `golden-mission-control` is the most complete
  (5 stages, code findings, captured prompts, real `src/` deliverables) and is the reference
  fixture for manual verification.
- A browser. No server, no network, no build step.

Confirm what you have:

```bash
cd backend
./evals/grading/grade.sh runs
```

---

## Setup

No installation, no configuration, no dependency to add. The feature ships inside
`backend/evals/grading/site/`.

```bash
cd backend
python3.11 -m pytest tests/unit/test_grading_site_model.py \
                     tests/unit/test_grading_site_pages.py \
                     tests/unit/test_grading_site_export.py \
                     tests/unit/test_grading_site_builder.py \
                     tests/unit/test_grading_grades.py -q
```

Regression gate for the `grades.py` extraction (must pass **unmodified**):

```bash
python3.11 -m pytest tests/unit/test_grading_markdown_report.py -q
```

---

## Run / Exercise the feature

### Build everything

```bash
cd backend
./evals/grading/grade.sh dashboard
```

Writes `.runs/index.html` plus, for each run, `reports/run.html` and one
`reports/<agent_token>.html` per graded stage. Unchanged runs are skipped.

```bash
./evals/grading/grade.sh dashboard --force     # re-render everything
./evals/grading/grade.sh dashboard --open      # build, then open index.html
```

### Open it

```bash
open backend/evals/grading/.runs/index.html     # macOS
```

Double-clicking in Finder must work identically — that is a requirement, not a convenience, and it
is why no page uses `fetch()`.

### Export one run as a single file

```bash
./evals/grading/grade.sh dashboard --export golden-mission-control
# → .runs/prototype/golden-mission-control/reports/golden-mission-control.export.html
```

Self-contained: no repo, no network, no sibling files.

### The automatic path

Any `run` / `rejudge` / `code` pass rebuilds the dashboard and that run's pages as it finishes, and
prints their paths beside the markdown path. Nothing to remember.

> **Live-run note**: `grade.sh run` / `rejudge` / `benchmark` and any scenario-id invocation spend
> real tokens and are **run by the repo owner, never automatically**. Verify the auto-rebuild
> against an existing folder instead:
> ```bash
> ./evals/grading/grade.sh report golden-mission-control    # free; regenerates reports
> ```

---

## Validation Scenarios

Each maps to a spec acceptance criterion. Ticking all ten is the manual acceptance pass.

| # | Do this | Expect | Spec |
|---|---|---|---|
| 1 | Open `.runs/index.html` | All 20 runs listed newest-first with grade, rows, phases, status, class badge | S1.1 |
| 2 | Look for `golden-mission-control` and `…-small-copy` | Badged `reference` / `copy`; absent from trend points; "show excluded" reveals them | S1.2 |
| 3 | Disconnect the network, reload | Renders identically. DevTools Network shows **zero** requests | S1.4 |
| 4 | Open **Prompt version history** for `prototype-build` | One row per `system_prompt_hash`, chronological, with runs, aggregate, delta, verdict; a within-noise delta says *within noise*, not "improved" | S2.1–2.2 |
| 5 | Select two versions | Line diff of the captured prompt text beside the score delta | S2.3 |
| 6 | Click a run → click the weakest stage → expand its worst row | Brief, sub-scores, rationale, strengths, weaknesses, evidence quotes, caps before→after, code findings — all in place | S3.2 |
| 7 | In that row, view the deliverable | `prototype.html` renders in a sandboxed iframe; toggle shows escaped source; `.md` shows as escaped monospace | S3.3–3.4 |
| 8 | Read the **stage × row matrix**; click a cell | Cells match the run page's per-phase numbers; 0-cells distinguish precheck fail / error / broken chain / judge failure by glyph; clicking opens that row expanded | S4.1–4.3 |
| 9 | Compare the run page's grade and phase table against `reports/report.md` | Identical letter, score, and `effective` column | S3.1 |
| 10 | Print preview (⌘P) | Every tab and row expands linearly; nothing readable on screen is missing on paper | Spec §3.5 |

### Correctness checks worth running by hand

```bash
cd backend

# 1. Determinism — two builds, byte-identical
./evals/grading/grade.sh dashboard --force
shasum .runs/index.html > /tmp/a
./evals/grading/grade.sh dashboard --force
shasum .runs/index.html > /tmp/b
diff /tmp/a /tmp/b && echo "deterministic"

# 2. Self-containment — no remote refs, no fetch
grep -nE 'src="https?://|href="https?://|fetch\(|XMLHttpRequest' .runs/index.html \
  && echo "VIOLATION" || echo "self-contained"

# 3. Previews are sandboxed and script-free
grep -o '<iframe[^>]*>' .runs/prototype/golden-mission-control/reports/*.html \
  | grep -v 'sandbox' && echo "VIOLATION" || echo "all sandboxed"

# 4. Speed
time ./evals/grading/grade.sh dashboard --force    # target < 10s for 20 runs
```

### Escaping, checked deliberately

The failure mode this feature is most exposed to is model output containing HTML. Confirm it with
a fixture rather than trusting it:

```bash
cd backend
python3.11 -m pytest tests/unit/test_grading_site_pages.py -k "injection or escap" -v
```

A rationale containing `<script>alert(1)</script>` must appear as literal text on the page, with no
script executing and no layout damage.

---

## Rollback / Cleanup

Generated output is disposable — nothing in a run folder outside `reports/` is ever touched.

```bash
cd backend/evals/grading
rm -f .runs/index.html
rm -f .runs/*/*/reports/*.html
```

Rebuild any time with `./evals/grading/grade.sh dashboard`. The markdown reports and every artifact
are untouched by this feature and by its removal.

**Full feature rollback**: delete `evals/grading/site/`, revert the `markdown_report.py` /
`grade_runner.py` / `grade.sh` edits, and fold `grades.py` back into `markdown_report.py`. The
grading harness returns to exactly its current behaviour — this feature changes no score, no
rubric, and no artifact.
