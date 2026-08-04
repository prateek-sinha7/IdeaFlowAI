# Live UI runs — v1 vs v10, graded

Two runs through the product UI on the Northwind fleet-maintenance brief (identical
brief in both). Graded with the same fixed judge instrument as the eval series:
upstream artifacts supplied, rubric-scoped, severity-priced, K=1.

## Result

| stage | v1 | v10 | gap |
|---|---|---|---|
| specify | 43.1 | **52.9** | +9.8 |
| plan | **71.2** | 64.6 | -6.6 |
| analyze | 47.2 | **54.2** | +7.0 |
| build | **59.5** | 57.6 | -1.9 |
| **mean (4 stages)** | **55.2** | **57.3** | **+2.1** |

**No meaningful difference.** +2.1 on the mean, every per-stage gap inside the ±8-15
noise band established over 17 eval cycles. On this brief, through this path, v1 and
v10 are indistinguishable.

`validate` is NOT graded: each run preserved only the final HTML, so there is no
pre-repair artifact and `defect_repair_delta` (35% of that rubric) has nothing to diff.

## This contradicts the eval-harness result

| stage | harness gap (3 runs/arm) | live gap (1 run/arm) |
|---|---|---|
| specify | +40.4 | +9.8 |
| plan | -3.2 | -6.6 |
| analyze | +23.9 | +7.0 |
| build | **+50.6** | **-1.9** |
| mean | **+22.1** | **+2.1** |

Only `plan` agrees across both (a wash, v1 marginally ahead — now confirmed twice).

### Two findings I reported from the harness that did NOT reproduce

**1. analyze `defect_detection`** — reported as a clean 30-point separation, "no overlap".

| | harness (permits) | live (fleet) |
|---|---|---|
| v1 | 1 / 0 / 6 | **0** |
| v10 | 34 / 62 / 38 | **0** |

Both arms scored zero on unseen work. v10's detection advantage is at least partly
specific to the permits brief it was iterated against across 17 cycles. I raised the
overfitting risk when proposing a fresh domain and then stated the finding anyway
without attaching that caveat.

**2. build's 50-point gap** — driven in the harness by v1 shipping placeholder stubs
(`page_completeness` 0, 0, 30). Live, v1's build scored 59.5 with 5 of 6 pages
substantive and a genuinely wired drag-to-advance Kanban. It did not stub.

Two plausible causes, not separated: (a) the live UI's clarification round pins down
requirements the harness brief leaves implicit, which is exactly the gap v10's longer
prompt was written to close — supply that information another way and v10's advantage
disappears; (b) my static-markup scan undercounted v1, which renders rows via JS
(23 `innerHTML` assignments) rather than as static HTML.

## Confound: the clarification rounds differed

The live UI asked each arm DIFFERENT questions, so the two runs were given different
requirements. This is a harness property, not a prompt difference.

| | v1 was told | v10 was told |
|---|---|---|
| Work Orders | **Kanban with drag-to-advance** | (not asked) |
| Pages required | (not asked) | **"Vehicles — fully functional"** (permission to stub 5) |

v10 was handed a *lower* bar on `page_completeness` (35-45% of build/validate weight)
and **built all six pages anyway** — none stubbed. v1 was told Work Orders needed a
Kanban and built one. Judges were given `clarifications.md` as binding context so
neither was penalised for a bar it was not set.

## CORRECTION: v10 IS blank on load — a blocking defect every automated signal missed

The user reported v10 showing a blank page. I initially reported it rendered fine.
**The user was right.** On load, v10 shows only the sidebar and topbar; the entire
content area is empty.

**Cause** — CSS grid row placement. Both files use `body { display: grid }` with a
sticky `height: 100vh` sidebar.

```css
/* v1 — sidebar spans every row, so it cannot inflate one */
.sidebar      { grid-column: 1; grid-row: 1 / -1; ... }
.main-content { grid-column: 2; grid-row: 2; }

/* v10 — NO grid placement on .sidebar at desktop width (only in the mobile query) */
.sidebar      { position: sticky; top: 0; height: 100vh; ... }   <- auto-placed, row 1
.main         { grid-column: 2; grid-row: 2; }                   <- begins after row 1
```

v10's sidebar auto-places into row 1; its `100vh` inflates that row to the viewport
height, so `.main` (pinned to row 2) starts at exactly `y = 900` on a 900px viewport.
`document.scrollHeight` = 1822. Scroll down and the Vehicles page is complete and
well-built — 12 vehicles, working filter pills, status badges, Detail/Flag Parts.

One missing declaration (`grid-row: 1 / -1`) makes the product look broken on load.

**Why nothing caught it:**

| signal | verdict |
|---|---|
| deterministic render check | `ok=True issues=0` |
| Opus build judge | 57.6, never mentioned it |
| computed-style probe | every element `visible`, opacity 1, real dimensions |
| `visible_text=1243` metric | counted sidebar chrome as page content |
| a human looking at the screen | blank page |

Nothing in the stack asserts "content is inside the viewport on load". An element at
`y=900` is valid HTML and invisible to the user. I made it worse by reporting "renders
fine" from metrics without opening the screenshots I had just generated.

**Grade impact** — priced as blocking (45) on `page_completeness`:

| | as judged | corrected |
|---|---|---|
| v10 build | 57.6 | **41.9** |
| v10 live mean | 57.3 | **53.4** |
| v1 live mean | 55.2 | 55.2 |

The comparison flips: v1 55.2 vs v10 53.4. Still inside the noise band, so the
conclusion stays "no meaningful difference" — but v10 no longer edges it.

## Earlier (incorrect) rendering analysis, kept for the record

Chromium, 1440x900, `file://`:

```
v1   visible_text=1445  visible_pages=1  tbody_rows=42  pageerrors=0
v10  visible_text=1243  visible_pages=1  tbody_rows=45  pageerrors=0
```

Both pass deterministic render checks (`ok=True issues=0`). Structure balanced
(`<style>`/`<script>`/`<body>`/`<html>` all 1:1), JS parses under `node --check`,
zero undefined CSS variables in either. v10 has MORE content than v1: 70,811 chars of
body markup vs 57,703, and 52 static table rows vs 5.

Likely cause of what was seen locally: the v10 filename is truncated mid-word —
`northwind-logistics-fleet-maintenance-co.html` — suggesting a clipped download.
Expected size 127,156 bytes.

## Real defects found in each (both judges traced these to source)

**v1** — blocking: Vehicle Detail's checklist/history/notes keyed only to
`TRK-2026-0184`, so 11 of 12 vehicles render empty cards. Major: Parts & Costs totals
row hardcoded to $12,847.50 while its 18 rows sum to $7,431.50. Major: all 15 work
orders sit in "Main Garage", leaving five blank Kanban columns.

**v10** — major: Vehicle Detail never binds to the clicked vehicle (the
`window.handleRouteChange` wrapper is never invoked because the `hashchange` listener
holds a reference to the original function), so every unit shows TRK-2026-0184's body
under a different heading. Major: Parts & Costs totals don't sum from work-order line
items ($1,245/3 WOs displayed vs $425/2 in the store). Major: Work Orders status badges
generated but never defined in CSS, so the column is unstyled across all 15 rows.

**Both arms failed the same two brief requirements**: Vehicle Detail binding to the
clicked record, and totals deriving from line items rather than being hardcoded. That
is the most actionable output of this comparison — a shared, reproducible defect class
that neither prompt version addresses.
