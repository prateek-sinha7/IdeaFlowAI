---
phase: 40-shell-mock-fidelity-restyle-b6
plan: 04
subsystem: frontend-shell
tags: [ui-fidelity, analytics, restyle, shell-mock, charts]
requires: ["40-01"]
provides: ["Analytics surface at mock parity (KPI row · daily-activity bars · success-rate donut · by-pipeline · by-model · token breakdown) over the live /api/analytics/summary endpoint, with chart-primitive fidelity (tall bars + one dark peak, enlarged donut)"]
affects:
  - frontend/src/components/analytics/AnalyticsPage.tsx
  - frontend/src/components/analytics/charts/BarChart.tsx
  - frontend/src/components/analytics/charts/DonutChart.tsx
tech-stack:
  added: []
  patterns:
    - "styling/number-format parity restyle over an unchanged endpoint contract (INV-12 — no re-architecture of /api/analytics/summary or the chart data contracts)"
    - "chart-primitive fidelity via presentation-only props/geometry (BarChart peak highlight + height, DonutChart scaled geometry) with the data contract untouched"
key-files:
  created: []
  modified:
    - frontend/src/components/analytics/AnalyticsPage.tsx
    - frontend/src/components/analytics/charts/BarChart.tsx
    - frontend/src/components/analytics/charts/DonutChart.tsx
    - frontend/src/components/analytics/AnalyticsPage.test.tsx
decisions:
  - "Analytics was already structurally the mock (Phase 38 built AnalyticsPage to /api/analytics/summary); 40-04 is a styling + number-format parity pass on the live/seeded payload — the endpoint and the BarChart/DonutChart data contracts are unchanged (INV-12/ND-D)."
  - "The right-column card shows the live per-model rollup ('By Model'), not the mock's 'Recent Runs' — the /api/analytics/summary payload carries no recent-runs list, so fabricating run rows would violate ND-D. Registered as ND-AA; a recent-runs data wire is a Phase-41 follow-up."
  - "Chart-primitive fidelity fix (user-ruled 'fix now' at the Batch-A closeout): the daily-activity bars and success-rate donut were undersized vs the mock. BarChart.tsx + DonutChart.tsx are consumed ONLY by AnalyticsPage (grep-verified — no run-screen or other-page consumer), so the fix is Analytics-scoped with zero cross-surface regression risk."
metrics:
  duration: ~35m
  completed: 2026-07-12
---

# Phase 40 Plan 04: Analytics Surface Parity Summary

Brought `AnalyticsPage` to visual parity with the `Hexaware Workspace v2.dc.html` Analytics surface — a styling + number/date-format pass over the *unchanged* live `/api/analytics/summary` endpoint (Phase 38 already built the structure). All KPI/chart values stay bound to the seeded live payload (ND-D); no endpoint or chart data-contract was re-architected. A trailing, human-ruled chart-primitive fidelity fix enlarges the success-rate donut and makes the daily-activity bars tall with a single highlighted peak, matching the mock.

## What changed

- **AnalyticsPage restyle (main commit `fc536ca`):** KPI card chrome, section spacing/typography, chart framing, legend/label styling, and the by-pipeline / by-model / token-breakdown rows aligned to the mock; number + date formatting brought to the mock's format (compact tokens, 2-dp currency, tabular-nums where the mock aligns figures). The `/api/analytics/summary` binding and the derived-data math are byte-for-behavior unchanged (ND-D — values stay live/seeded).
- **Chart-primitive fidelity fix (Batch-A closeout, this commit):**
  - `DonutChart.tsx` — the success-rate ring enlarged from an 88px to a **118px** SVG (`width`/`height`/`viewBox`), with the geometry scaled proportionally (radius 36 → 48, stroke 10 → 13, centre 44 → 59, `rotate(-90 …)` re-centred) so the ring stays centred and the centre `%` label still fits.
  - `BarChart.tsx` — the container height raised `h-20` (80px) → **`h-32`** (128px, the mock's bar height), and a single **highlighted peak** added: the series-max bar renders in the solid dark brand fill while the rest render as a uniform lighter lavender (the opacity ramp collapsed to a flat tint so exactly one dark peak reads against lavender, per the mock). The motion height-animation + hover tooltip + the per-datum `status`-colour path are preserved.
  - `AnalyticsPage.tsx` — the daily-activity **empty-state** placeholder bumped `h-20` → `h-32` so the card height is stable between the populated and empty states.

## Intended-Divergence register touch

This surface exercises:
- **ND-A** — brand "VelocityAI" (not "HEXAWARE") in the shell chrome.
- **ND-C** — nav active-state = purple underline (not the mock's pill-fill).
- **ND-D** — every KPI/chart value is the live/seeded `/api/analytics/summary` payload, never the mock's hardcoded figures (e.g. our success rate / token totals / run counts differ from the mock's; the highlighted peak bar sits wherever the live series max falls, not the mock's fixed middle bar).
- **ND-AA (NEW, registered in `assemble-shell-gallery.mjs`)** — Analytics "By Model" vs the mock's "Recent Runs": the summary payload carries no recent-runs list, so the right-column card shows the live per-model rollup rather than fabricating run rows (ND-D). A recent-runs data wire is a Phase-41 follow-up.

## Regenerated gallery (`--surface analytics`)

2 pairs regenerated into `frontend/e2e/fidelity/gallery-shell.html`: `analytics__shell`, `analytics__shellfull`. Current side refreshed via `SHELL_CAPTURE=1 npx playwright test --project=mocked zzz-shell-baseline`; target side reused from 40-01; assembled via `assemble-shell-gallery.mjs --surface analytics`. Post-fix eyeball vs `target/analytics__shell.png`: the donut is now the mock's larger ring with the centred "85%" fitting, and the bars are tall lavender with exactly one dark brand peak.

## Verification results

- `npx tsc --noEmit` — 0 errors.
- `npx vitest run AnalyticsPage.test.tsx BarChart.test.tsx DonutChart.test.tsx` — all green (AnalyticsPage server-recompute + Avg/Run math cases; the chart-primitive render + a11y contracts — the tests pin role="img" / aria-label / one-bar-per-datum, not the geometry, so the enlargement is contract-safe).
- Chart consumer grep: `BarChart`/`DonutChart` are imported ONLY by `AnalyticsPage.tsx` (the `AppHeader.tsx` hit is the lucide `BarChart2` icon, not our primitive) — the fidelity fix is Analytics-scoped, zero cross-surface regression risk.

## Deviations from Plan

**1. [Rule 1 — Fidelity bug] Chart primitives undersized vs the mock (user-ruled "fix now")**
- **Found during:** Batch-A closeout eyeballing (`current/analytics__shell.png` vs `target/`).
- **Issue:** the success-rate donut and the daily-activity bars were smaller than the mock, and the bars lacked the mock's single dark "peak" among lavender bars.
- **Fix:** enlarged the donut geometry (88 → 118 SVG, proportional radius/stroke/centre), raised the bar container height (`h-20` → `h-32`), and added the series-max peak highlight (solid dark brand vs uniform lavender). Empty-state placeholder height matched for a stable card.
- **Files modified:** `charts/DonutChart.tsx`, `charts/BarChart.tsx`, `AnalyticsPage.tsx`.
- **Commit:** this plan's `feat(40)` chart commit.

## Known Stubs

None. All Analytics values are live/seeded from `/api/analytics/summary`. The "By Model" card (vs the mock's "Recent Runs") is a data-availability divergence (ND-AA), not a stub — it renders the real per-model rollup; the recent-runs wire is a registered Phase-41 follow-up.

## Checkpoint

The Analytics surface (styling parity commit `fc536ca`) was handed to the human reviewer at the plan's blocking `checkpoint:human-verify` and **approved**. The trailing chart-primitive fidelity fix was a user-ruled "fix now" applied at the Batch-A closeout over that approval, re-captured and re-eyeballed against the mock.
