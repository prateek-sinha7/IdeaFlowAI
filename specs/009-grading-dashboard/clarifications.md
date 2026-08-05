# Clarifications — 009-grading-dashboard

Decisions taken on 2026-07-30, in the session that reframed this spec from a single per-run
HTML report into a **cross-run dashboard with drill-down**. Each entry records what was asked,
what the code on disk actually supports, and what was decided.

Resolved: **C1–C5**. Recommended-and-pending: **C6–C8** (stated defaults; no answer needed to
start building — they can be settled during `/apex:plan`).

---

## C1 — Output shape: one file, a static site, or both? — **RESOLVED: hybrid**

**Question**: Does this produce one self-contained `report.html`, or a generated static site?

**Context**: The original spec assumed one page per run. The reframing asks for a **central**
report that reads *all* existing runs, with drill-down: dashboard → run (all stages) → stage
detail (HTML preview / markdown). There are **20 run folders** under
`backend/evals/grading/.runs/prototype/` today, each carrying a full `artifacts/` set, captured
`prompts/`, `src/<row>/` deliverables, and `logs/`. Inlining every one of those — including built
prototype HTML — into a single file is not viable at that scale.

**Options**:
- **A. Static site** — `index.html` + a page per run + a page per stage, generated into the
  `.runs/` tree. Previews work because the deliverables sit right next to the pages.
- **B. Single file** — everything inlined; shareable anywhere, but previews degrade to links that
  only resolve inside the repo.
- **C. Hybrid** — the static site is the working surface, **plus** a one-file export of a single
  run for sharing outward.

**Decision: C — hybrid.**

The site is the instrument; the export is the message. Concretely:

| Artifact | Path | Self-contained? |
|---|---|---|
| Dashboard | `.runs/index.html` | Data inlined; links out to run pages |
| Run page | `<run>/reports/run.html` | Data inlined; links to stage pages + `src/` |
| Stage page | `<run>/reports/<agent_token>.html` | Data inlined; **iframes** `src/<row>/…` |
| Run export | `<run>/reports/<dataset_run_id>.export.html` | **Yes** — one file, nothing external |

The two paths must not diverge in what they claim. Mitigation: the export is rendered from the
**same section builders** as the site pages, differing only in how deliverables are embedded
(`srcdoc` vs `src`) and in navigation (in-page tabs vs links). A test asserts the grade, phase
table, and row scores are identical between a run's `run.html` and its export.

**Consequence — no `fetch()`.** Chrome blocks `fetch()`/`XMLHttpRequest` against `file://` under
its origin rules, so a page cannot load a sibling `data.json` when opened by double-click. **Every
page inlines its own data in a `<script type="application/json">` block.** This is a hard
constraint, not a preference; it is why there is no shared `data.json`.

---

## C2 — Which views does the dashboard carry? — **RESOLVED: all four, plus a fifth**

**Question**: Which cross-run views earn their place?

**Decision**: all four offered, **and** a fifth requested in the answer — *"which stage scores on
multiple rows"*.

### V1 — Quality trend over time
Every run's blended grade plotted chronologically, overall and split by phase. Source:
`markdown_report.compute_overall()` per run — the same arithmetic as the per-run grade, never
recomputed.

### V2 — Prompt version history
Runs grouped by `system_prompt_hash` (carried in each stage's `score.hashes`), chronologically,
with each version's aggregate and a met/not-met verdict against the baseline.
**`compare.group_by_prompt()` already implements exactly this**, including the noise band
(`SIGMA_MULTIPLIER = 2.0`, `DEFAULT_MIN_THRESHOLD = 1.0`) that stops a stochastic judge's wobble
being read as an improvement. The dashboard renders that function's output; it does not restate
the rule.

Because the runs also captured `prompts/<agent_token>_system_prompt.md` verbatim, the version view
can show **the actual diff between two prompt versions** beside the score delta — the one thing
neither the terminal nor the markdown reports can do today. This is in scope. It ties to spec
[007-prompt-versioning](../007-prompt-versioning/spec.md), whose `AGENT.vN.md` archives are the
committed counterpart of these captured prompts.

### V3 — Dimension heatmap
Rubric dimensions × phases (and dimensions × runs) as a colour grid, so a chronically weak
dimension — the one paragraph of an `AGENT.md` that never improves — is visible across history
rather than one run at a time. Source: each stage's `score.dimensions` aggregates.

### V4 — Cost & code-track health
Tokens per run / phase / judge over time (`score.tokens`, split agent vs judge), alongside the
code track's reliability signal (console errors, uncaught exceptions, dead nav, failed
interactions) from `code_grader.read_findings()`.

### V5 — Stage × row matrix *(added by the answer)*
> *"Which stage scores on multiple rows"*

A grid of **stages (rows of the matrix) × dataset rows (columns)**, each cell the blended
judge/code score for that `(stage, row)` pair — the exact cells `compute_overall()` already
averages. It answers what a single per-stage average hides: **is a weak phase weak everywhere, or
is one brief dragging it down?** A row of the matrix that is uniformly low is a prompt problem; a
column that is low across every stage is a brief that breaks the whole chain.

Two scopes, same component: within one run (on the run page) and aggregated across runs (on the
dashboard, cell = mean over runs, with the spread shown).

Cells carry their failure kind, not just a number — precheck fail, dispatch error, and
broken-chain all score 0 today and are indistinguishable in an average. The matrix distinguishes
them by glyph.

---

## C3 — Which runs are included? — **RESOLVED: all, with fixtures flagged**

**Question**: Do golden fixtures, calibration references, and `-copy` folders count as runs?

**Context**: `.runs/prototype/` contains 20 folders, among them `golden-mission-control` (the
hand-verified reference artifact central to spec 008) and `260729-210937-small-copy`. Averaging
those into a trend line silently corrupts it; excluding them loses the golden as a visible
quality ceiling.

**Decision: include everything, classify it, and let the classification drive the charts.**

| Class | Detection | Treatment |
|---|---|---|
| `run` | default | Full trend participation |
| `reference` | non-timestamped folder name (e.g. `golden-*`), or a `calibration/` fixture path | Drawn as a **horizontal ceiling/floor line**, never a trend point |
| `copy` | `-copy` suffix | Listed, badged, excluded from aggregates |
| `partial` | `run_summary.status` not complete, or stages `stale` / `not_run` | Listed and badged; excluded from trend, included in the run list |

Classification is displayed on every run row — a chart that quietly drops data is worse than one
that shows why it dropped it. A "show excluded" toggle reveals them in place.

---

## C4 — When is it built? — **RESOLVED: explicit command + automatic**

**Decision**: a new `./evals/grading/grade.sh dashboard` — **free, model-free, no dispatch** — that
rescans every run folder and rebuilds the site; **and** the same rebuild fires at the end of any
`run` / `rejudge` / `code` pass, so the dashboard is never stale.

Per the standing project rule that features extend the main pipeline rather than growing a
sibling: the automatic rebuild hangs off the existing report-writing path
(`markdown_report.write_report`'s callers — `grade_runner`'s run/rejudge/report paths and
`model_grader._write_markdown_report`), so no new call site has to be kept in sync.

Guards, because a rescan of every run must never be able to fail a run that already succeeded:
- The auto-rebuild is **best-effort**: any exception is caught, logged as a warning, and the run
  still reports success. The explicit command surfaces errors normally.
- A run folder that fails to parse is **skipped with a visible badge on the dashboard**, not
  dropped and not fatal.
- Rebuild is incremental where cheap: a run whose artifacts are unchanged since its page was
  written is not re-rendered. Determinism (C5) is what makes that safe.

---

## C5 — Escaping and determinism — **RESOLVED: non-negotiable, carried from the original spec**

Not asked, but it survives the reframing unchanged and is worth restating because the reference
snippet that started this discussion gets it wrong: it concatenates unescaped model output into an
f-string. **Our payloads are literally HTML documents.** A single `_esc()` choke point, enforced by
an injection test, is a build requirement. JSON inlined for the charts is `</`-neutralised so it
cannot terminate its own `<script>` block. Previews are `sandbox`ed iframes with scripts disabled.

Output is **byte-deterministic** — no render timestamps, no counter-derived element IDs — which is
what makes C4's incremental rebuild and any diff-based review possible.

---

## C6 — How are markdown deliverables displayed? — **RECOMMENDED, pending**

**Question**: The stage detail must "show the html preview **or md**". Deliverables like
`src/<row>/spec.md`, `tasks.md`, `design.md` are markdown. Do we render them, or show the source?

**Options**:
- **A. Escaped monospace** — faithful, zero risk, ~0 lines of new logic; reads like a diff.
- **B. Minimal built-in renderer** — headings, lists, tables, fenced code, emphasis, links. ~150
  lines of stdlib Python; a subset renderer that silently mis-renders something is worse than one
  that never pretends.
- **C. Vendored JS markdown library** — best fidelity, but copies a third-party dependency into a
  package that currently has none, and the file must stay self-contained.

**Recommendation: A for v1, with a toggle stub for B.** These are our own agents' markdown and are
read for content, not typography. A "rendered / source" toggle can land later without changing the
page contract. **C is declined** — vendoring a library contradicts the stdlib-only, no-dependency
constraint that makes this package cheap to maintain.

---

## C7 — Export size ceiling — **RECOMMENDED, pending**

A one-file run export (C1) that inlines every row's built prototype could reach tens of MB.

**Recommendation**: a **hard budget (default 8 MB)**. Previews are inlined largest-value-first
until the budget is reached; the remainder degrade to a labelled placeholder naming the
`src/` path, so the export is never silently incomplete. Configurable via `--max-size`.

---

## C8 — Does the dashboard span workflows? — **RECOMMENDED, pending**

Only `prototype` exists under `.runs/` today, but `runs_root()` is explicitly keyed per workflow
(`.runs/<workflow>/`).

**Recommendation**: build the dashboard **workflow-aware from the start** — a workflow selector
that is hidden while only one exists. Retrofitting a second axis onto charts later is far more
expensive than reserving it now, and costs almost nothing today.

---

## Deferred (explicitly out of v1)

| Item | Why deferred |
|---|---|
| An HTML face for `grade.sh compare`'s pairwise report | V2's prompt-version view covers the question that matters (*did my edit help?*); pairwise run-vs-run diffing is a separate surface |
| Editing prompts from the dashboard | `apply-advice` / `revert` (spec 007) stay CLI-owned; the dashboard displays advice, it does not act on it |
| Serving over HTTP, auth, hosting, an index across machines | These are static files opened locally; anything else is infrastructure, not this spec |
| Live/streaming updates during a run | This renders finished folders |
| Replacing the markdown reports | `report.md` stays the diffable, greppable form |
