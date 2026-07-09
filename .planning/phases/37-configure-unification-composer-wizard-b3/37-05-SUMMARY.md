---
phase: 37-configure-unification-composer-wizard-b3
plan: 05
subsystem: ui
tags: [react, nextjs, tailwind, design-system, wizard, prototype, tokens]

# Dependency graph
requires:
  - phase: 37-01
    provides: Phase-32 @theme token layer + ui/ primitives baseline for the reskin
  - phase: 37-04
    provides: WizardStepper chrome exposing dsSlot (step 2) + discoverySlot (step 3)
provides:
  - DesignSystemPicker restructured from a rounded-pill chip list into a live-registry swatch band-card grid (real ~14, LOCK-F/ND-8)
  - Each DS band-card surfaces its colour swatches sourced the same way DesignSystemDetailModal does (getDesignSystem + extractPalette)
  - Discovery route reskinned onto Phase-32 tokens and aligned as step 3 of the unified Template->Design System->Discovery wizard
affects: [37-06, configure-unification, prototype-wizard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Band-card grid: swatch band + meta row + corner select toggle; card body opens the live detail-modal, toggle drives onSelect(id)/onSelect(null)"
    - "Card swatch sourcing reuses the DetailModal path (getDesignSystem -> extractPalette over DESIGN.md body); no-token -> neutral token placeholder band"

key-files:
  created: []
  modified:
    - frontend/src/components/workflow/prototype/DesignSystemPicker.tsx
    - frontend/src/components/workflow/prototype/DesignSystemPicker.reskin.test.tsx
    - frontend/src/app/workflow/prototype/discovery/page.tsx

key-decisions:
  - "Built-in DS selection stays split: card body opens the detail modal (preserves the reskin test's click->modal->Use->onSelect path); a new corner toggle adds direct onSelect(id)/clear without the modal"
  - "Swatches are lazily fetched per card via the existing getDesignSystem + extractPalette (reuse-not-rebuild); no new endpoint, no new swatch field on DesignSystemListItem"
  - "DiscoveryForm.tsx left untouched: the audience/tone enum reconcile is discretionary ('discretion on presentation') and the current sets are sound; avoids risking the ND-12 pages==0 gate and keeps scope on the two mandated files"
  - "Discovery header relabeled 'Step 2 of 3' -> 'Step 3 of 3' to align the standalone route with the WizardStepper ordering (template=0, design-system=1, discovery=2)"

patterns-established:
  - "Live-registry-driven grid: card count = props.systems.length (fed by listDesignSystems), never a hardcoded array"

requirements-completed: [SHELL-04]

# Metrics
duration: 22min
completed: 2026-07-09
---

# Phase 37 Plan 05: DS Band-Card Grid + Wired Discovery Step Summary

**DesignSystemPicker restructured into a live-registry swatch band-card grid (real ~14, LOCK-F) with its selection + detail-modal wiring preserved, and the orphaned DiscoveryForm reskinned onto Phase-32 tokens and aligned as step 3 of the unified wizard.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-07-09T08:21:00Z
- **Completed:** 2026-07-09T08:43:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Turned the rounded-pill DS chip list into a swatch band-card grid — one card per live registry entry (~14), each surfacing its colour swatches, opening the live `DesignSystemDetailModal` on click, with a corner toggle driving `onSelect(id)` / `onSelect(null)`.
- Sourced the card swatches by reusing the DetailModal path (`getDesignSystem` -> `extractPalette` over the DESIGN.md body) — no new endpoint, no hardcoded palette, neutral token placeholder pre-auth/in tests.
- Reskinned the discovery route (the built-but-orphaned DiscoveryForm host) onto Phase-32 tokens, migrating its 4 retired-palette hits to 0, and relabeled it as wizard "Step 3 of 3" — the stepper (37-04) now supplies the missing navigation into the existing form (INV-3: wired, not rebuilt).

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): failing band-card grid coverage** - `89e1740f` (test)
2. **Task 1 (GREEN): restructure DesignSystemPicker -> swatch band-card grid** - `4541b6ca` (feat)
3. **Task 2: reskin discovery route + align as wizard step 3** - `d0ff421d` (feat)

_TDD task 1: test (RED) -> feat (GREEN). No refactor commit needed._

## Files Created/Modified
- `frontend/src/components/workflow/prototype/DesignSystemPicker.tsx` - Chip list -> swatch band-card grid; new `DesignSystemBandCard` (per-card lazy swatch fetch + corner select toggle); live fetch, `onSelect`/`onSelectCustom`, and detail-modal mount preserved.
- `frontend/src/components/workflow/prototype/DesignSystemPicker.reskin.test.tsx` - +3 tests: one band-card per registry entry (14) with a swatch band each; select toggle fires `onSelect(id)`; re-click clears to `onSelect(null)`.
- `frontend/src/app/workflow/prototype/discovery/page.tsx` - Full token reskin (surface/ink/line + status-failed ramp + brand CTA), dead `var(--font-fraunces)` -> `font-serif`, "Step 2 of 3" -> "Step 3 of 3"; DiscoveryForm mount + `prototype.draft` read + Skip preserved.

## Decisions Made
- **Split built-in DS selection** — card body opens the detail modal (keeps the existing reskin test's click->modal->Use->onSelect path green) and a new corner toggle adds a direct `onSelect(id)`/clear affordance. This satisfies the plan's "card select fires onSelect(id), re-click clears" without regressing the modal path.
- **Reuse swatch sourcing** — cards fetch `getDesignSystem` and run `extractPalette` (the exact DetailModal mechanism), rather than inventing a swatch field on `DesignSystemListItem` or hardcoding colours. No token (tests/pre-auth) -> a neutral Phase-32 token placeholder band.
- **DiscoveryForm untouched** — the audience/tone enum reconcile is explicitly discretionary ("keep surface + scale; discretion on presentation"); the current enums are sound, so I kept scope on the two mandated files and left the ND-12 `pages==0` gate trivially satisfied.

## Deviations from Plan

None - plan executed exactly as written. (The corrected live-registry gate from the settled guardrails was applied: the `'/api/prototype/design-systems'` literal lives in `lib/prototype-api.ts`, not the picker; preservation was verified via the `prototype-api`/`DesignSystemListItem` import staying and no hardcoded DS array being introduced — the `'/api/...'` literal was NOT injected to satisfy the stale grep.)

## Issues Encountered
- None. Initial reskin-test queries were ambiguous when a system is selected (the name renders in both the card and the header selected-badge); scoped the query to the band-card via `getAllByTestId('ds-band-card')` before the GREEN implementation.

## Verification Evidence (raw)

- **vitest:** `Test Files 2 passed (2) / Tests 10 passed (10)` — DesignSystemPicker.reskin.test.tsx (7) + WizardStepper.test.tsx (3).
- **DS registry preserved (corrected gate):** `grep -c 'prototype-api\|DesignSystemListItem' DesignSystemPicker.tsx` = 8 (>=1); no hardcoded DS array — card count = `props.systems.length`, fed by `listDesignSystems(token)` in both consumers (templates/page.tsx, ConfigureScreen.tsx); `grep -c 'onSelect'` = 25 (>=19 baseline).
- **Discovery wired not duplicated:** `grep -c 'DiscoveryForm' discovery/page.tsx` = 4 (>=1); exactly 1 `DiscoveryForm` definition in the tree.
- **ND-12 no pages:** `grep -ci 'pages' DiscoveryForm.tsx` = 0.
- **Token gate:** `grep -cnE '#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains'` = 0 for DesignSystemPicker.tsx AND discovery/page.tsx.
- **tsc identity:** `npx tsc --noEmit | grep -v mockApi.ts | grep -c error` = 0 (baseline 0).
- **Mocked Playwright e2e:** LIVE-DEFERRED per plan (not run).

## Known Stubs
None — the DS band-card count and swatches are wired to the live registry; the discovery route consumes `prototype.draft` and the live template detail. The neutral swatch placeholder band renders only when no auth token is present (tests / pre-auth), which is the honest degraded state, not a stub.

## Next Phase Readiness
- The unified wizard's DS step (band-card grid) and Discovery step (reskinned, step-3-aligned) are both token-clean and wired to live data.
- A live visual pass (real swatches over the ~14 systems, discovery flow end-to-end) belongs to the end-of-milestone live pass (Phase 34), consistent with the offline discipline for this phase.

## Self-Check: PASSED

- Files: DesignSystemPicker.tsx, DesignSystemPicker.reskin.test.tsx, discovery/page.tsx, 37-05-SUMMARY.md — all FOUND.
- Commits: 89e1740f (test), 4541b6ca (feat), d0ff421d (feat) — all FOUND.

---
*Phase: 37-configure-unification-composer-wizard-b3*
*Completed: 2026-07-09*
