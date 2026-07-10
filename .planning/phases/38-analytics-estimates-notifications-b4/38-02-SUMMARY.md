---
phase: 38-analytics-estimates-notifications-b4
plan: 02
subsystem: frontend-analytics-charts
tags: [analytics, charts, svg, a11y, tokens, tdd]
requires: []
provides:
  - "frontend/src/components/analytics/charts/DonutChart.tsx (DonutChart)"
  - "frontend/src/components/analytics/charts/BarChart.tsx (BarChart)"
affects:
  - "38-04 (AnalyticsPage reskin imports these + deletes inline copies)"
tech-stack:
  added: []
  patterns:
    - "hand-rolled inline SVG chart primitives (no chart lib, CSP-safe)"
    - "role=img + aria-label text alternative on chart SVG (T-38-A11Y)"
    - "Phase-32 @theme tokens: var(--brand) one-chroma; --status-* only for run-status data"
    - "motion/react proxy mock in vitest so role/aria queries resolve"
key-files:
  created:
    - frontend/src/components/analytics/charts/DonutChart.tsx
    - frontend/src/components/analytics/charts/BarChart.tsx
    - frontend/src/components/analytics/charts/DonutChart.test.tsx
    - frontend/src/components/analytics/charts/BarChart.test.tsx
  modified: []
decisions:
  - "DonutChart status flag = 'done'|'failed' (the only run-status donut segments); base sweep var(--brand)."
  - "BarChart per-datum optional status flag over the full status ramp; base chroma var(--brand)."
  - "Retired hex literals removed from doc comments so the raw-grep token gate reads 0/0."
metrics:
  duration: ~15m
  completed: 2026-07-10
requirements: [SC-1, SC-2, SHELL-05]
---

# Phase 38 Plan 02: Analytics Chart Primitives (DonutChart + BarChart) Summary

Extracted the two chart primitives inlined in `AnalyticsPage.tsx` into reusable,
parametrized, token-styled, a11y-labelled components under
`frontend/src/components/analytics/charts/` — hand-rolled inline SVG with
`role="img"` + `aria-label`, consuming Phase-32 `@theme` tokens, zero external
chart library. Built TDD (RED render+a11y tests → GREEN components).

## What was built

- **DonutChart.tsx** — ported the exact donut geometry (`cx=44 cy=44 r=36`,
  `strokeDasharray = 2*PI*36`, `motion.circle` sweep with `strokeDashoffset`
  animation, `transform="rotate(-90 44 44)"`). Sweep stroke `var(--brand)` by
  default; track `var(--status-queued-fill)`; optional `status` prop
  (`done`/`failed`) colours the sweep from the status ramp. `role="img"` +
  `aria-label`. Optional centre-label `children`. Clamps `percent` to 0–100.
- **BarChart.tsx** — ported the flex/`motion.div` bar geometry (height animation,
  hover tooltip). Bars `var(--brand)`; optional per-datum `status` over the full
  status ramp; `role="img"` + `aria-label`; `data-testid="bar-chart-bar"` per bar;
  returns `null` for empty data. Tooltip navy → `bg-ink-900` / `border-t-[var(--ink-900)]`.
- **DonutChart.test.tsx / BarChart.test.tsx** — render + a11y RED-first tests
  (motion/react proxy-mocked): `getByRole("img")`, `aria-label` carries the
  numeric summary, no throw at 0%/100% boundaries, one bar per datum, empty-safe.

Charts are generic data-prop-driven primitives — no workflow-name branch
(SC-001/INV-1). AnalyticsPage.tsx and its inline copies were NOT touched (38-04
owns the swap + delete, INV-3).

## Verification (offline, by delta)

```
vitest src/components/analytics/charts   → Test Files 2 passed (2) / Tests 6 passed (6)
retired-palette per file                 → DonutChart 0, BarChart 0
positive token grep                      → DonutChart 8, BarChart 9  (>0)
role="img" grep                          → DonutChart 2, BarChart 2  (>=1)
no chart-lib grep (charts/)              → 0
tsc --noEmit (minus mockApi.ts)          → 0 errors (identity, baseline 0)
```

Mocked Playwright / live visual verification → LIVE-DEFERRED to Phase 34.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Gate correctness] Retired hex literal in doc comments tripped the raw-grep token gate**
- **Found during:** Task 2 acceptance greps.
- **Issue:** The `#1B2A4A` / `#F3F4F6` literals used descriptively in the component
  header comments matched the retired-palette grep (1/1 instead of 0/0), even though
  no retired value is used in actual styling.
- **Fix:** Reworded the comments to name the colours ("original navy sweep",
  "grey track") without the literal hex — the comment-stripped-guard convention
  used across Phase 32/35.
- **Files modified:** DonutChart.tsx, BarChart.tsx.
- **Commit:** 0656876a.

## Threat surface

No new network endpoints, auth paths, file access, or schema changes. Pure
data-prop-driven SVG (T-38-05), no `dangerouslySetInnerHTML`, no external chart
lib (T-38-CSP), `role="img"`+`aria-label` a11y gate (T-38-A11Y) — all threat-model
mitigations satisfied. No threat flags.

## Commits

- `98203890` test(38-02): add failing render+a11y tests for DonutChart and BarChart (RED)
- `0656876a` feat(38-02): extract token-styled DonutChart + BarChart SVG primitives (GREEN)

## Self-Check: PASSED

All 4 created files present on disk; both commits (98203890, 0656876a) present in git log.
