---
phase: 32-run-screen-redesign-a4
plan: 01
subsystem: ui
tags: [tailwind-v4, design-tokens, next-font, manrope, heebo, css-custom-properties, vitest]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4 (planning)
    provides: evidence 11 §B2/§B3/§B4 canonical palette + font + status/radius spec
provides:
  - Canonical Hexaware run-screen token layer (@theme inline + :root) — one-chroma brand #3C2CDA, warm ink ramp, beige surfaces, line family, status ramp, severity ladder, radius ladder (button=10/card=14), elevation, motion, scrim
  - Manrope (sans/structure) + Heebo (serif/reading) next/font loaders wired to --font-sans/--font-serif; SF Mono in --font-mono
  - Offline token-layer guard test proving canonical PRESENT + retired ABSENT
affects: [phase-34, phase-35, phase-36, phase-37, run-subtree-consumers (plans 06/07/08/09)]

# Tech tracking
tech-stack:
  added: [Manrope (next/font/google), Heebo (next/font/google)]
  patterns:
    - "Two-tier token layer: @theme inline color/font tokens (Tailwind v4 utility generation) reference :root CSS custom properties (direct var() consumers)"
    - "Fonts bound via next/font CSS variables (--font-manrope/--font-heebo) consumed by @theme --font-sans/--font-serif"
    - "Offline guard test: fs.readFileSync + comment-stripping so header prose cannot self-invalidate ABSENT assertions"

key-files:
  created:
    - frontend/src/styles/__tests__/token-layer.test.ts
  modified:
    - frontend/src/styles/globals.css
    - frontend/src/app/layout.tsx

key-decisions:
  - "Resolved the two open human decisions from evidence 11 §C per plan mandate: button radius = 10 (not 9), card radius = 14 (not 12)"
  - "running status = blue #3C2CDA (evidence 11 §B3); Handoff mock's amber running treated as a bug and ignored"
  - "Retired palette removed from the TOKEN LAYER ONLY; ~370 #1B2A4A component sites intentionally left for Phase 35+ (scope discipline)"
  - "Legacy --theme-* alias keys kept but repointed to the new palette values (var() references), not deleted — run-subtree components may still reference them"

patterns-established:
  - "Single canonical token layer, no per-page palette fork (SC-1)"
  - "@theme inline color tokens reference :root vars to avoid value duplication while still generating Tailwind utilities"

requirements-completed: [SC-1]

# Metrics
duration: ~6min
completed: 2026-07-08
---

# Phase 32 Plan 01: Run-Screen Token Layer Summary

**Canonical Hexaware token layer landed (D-15): one-chroma brand #3C2CDA, warm ink ramp, beige surfaces, status ramp + severity ladder, resolved radius ladder (button=10/card=14), elevation/motion/scrim, plus Manrope+Heebo next/font loaders — retired Inter/Fraunces/#2563eb/#f5f5f0/JetBrains gone from the token layer, guarded by an offline vitest suite.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-08T15:07Z
- **Completed:** 2026-07-08T15:10Z
- **Tasks:** 3
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments
- Rewrote `styles/globals.css` `@theme inline` + `:root` to the full canonical evidence-11 §B2/§B3/§B4 palette: brand (one chroma), warm ink, beige surface, line, status ramp (green/red/amber/blue/neutral — DS previously documented zero status colors), severity ladder, radius ladder, elevation, motion, scrim.
- Swapped `layout.tsx` next/font loaders from Inter/Fraunces to Manrope (--font-manrope) + Heebo (--font-heebo), wired onto `<html>` and consumed by `--font-sans`/`--font-serif`.
- Added `token-layer.test.ts` offline guard (9 assertions) proving canonical tokens PRESENT and retired tokens ABSENT (comment-stripped).

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite @theme + :root token layer** - `d9cdfb5e` (feat)
2. **Task 2: Swap next/font loaders to Manrope + Heebo** - `8947327a` (feat)
3. **Task 3: Offline token-layer guard test** - `6e3deeba` (test)

_Note: Task 3 is `tdd="true"`. As a regression guard added AFTER the guarded token layer (Tasks 1/2 already landed), the test passes on arrival — expected for a guard test, not a RED-first behavior driver. The ABSENT assertions bite if a retired value is reintroduced._

## Files Created/Modified
- `frontend/src/styles/globals.css` - Full canonical token layer (@theme inline color/font tokens + :root palette/radius/elevation/motion/scrim); markdown-content accent repointed off #2563eb to brand.
- `frontend/src/app/layout.tsx` - Manrope + Heebo next/font loaders exposing --font-manrope/--font-heebo; Inter/Fraunces removed.
- `frontend/src/styles/__tests__/token-layer.test.ts` - Offline PRESENT/ABSENT guard for SC-1.

## Verification Observed
- `npx vitest run src/styles/__tests__/token-layer.test.ts` — **1 file / 9 tests passed**.
- `npx tsc --noEmit | grep -v mockApi.ts | grep -c "error TS"` — **0** (identity; baseline 0 preserved, no new errors introduced).
- Task 1 acceptance greps: `#3C2CDA` count 3 (≥1); retired set (2563eb/f5f5f0/font-inter/font-fraunces/jetbrains, comment-stripped) = 0; status ramp hexes present (7 matches); `--radius-button: 10px` + `--radius-card: 14px` present; `tailwind.config.ts` unchanged.
- Scope: `git diff --name-only d9cdfb5e^ HEAD` lists EXACTLY `frontend/src/app/layout.tsx`, `frontend/src/styles/__tests__/token-layer.test.ts`, `frontend/src/styles/globals.css` — no component, no `tailwind.config.ts`.

## Decisions Made
- Resolved evidence 11 §C human-decision #2 (radius): button=10, card=14, per the plan's RESOLVED mandate.
- running=blue `#3C2CDA` (evidence 11 §B3); Handoff mock's amber running ignored as a bug.
- Retirement scoped to the token layer only; admin/login/settings/wizard pages stay on old navy (Phase 35+) — expected and correct.
- Legacy `--theme-*` aliases repointed (values) rather than deleted, since run-subtree components may still reference them; no `#2563eb`/`#111827` left live.

## Deviations from Plan
None - plan executed exactly as written. (Repointing the markdown-content `#2563eb`/`#1d4ed8` occurrences to brand vars was required to satisfy Task 1's "zero #2563eb outside comments" acceptance criterion — this is within the plan's "retire the old palette in the token layer" instruction, not a scope deviation.)

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Manrope + Heebo are Google Fonts self-hosted at build by `next/font` (no new package install, no runtime CDN call).

## Known Stubs
None.

## Threat Flags
None - static build-time token/font assets; no new trust boundary (per plan threat model, all dispositions `accept`).

## Next Phase Readiness
- Token layer (D-15) is landed and guarded; downstream shells (Phases 34/35/36/37) and run-subtree consumer plans (06/07/08/09) can consume the canonical tokens.
- No blockers. The remaining ~370 old-navy component sites are intentionally deferred to Phase 35+.

## Self-Check: PASSED

All 3 code/test files exist on disk; all 3 task commits (`d9cdfb5e`, `8947327a`, `6e3deeba`) present in git log.

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*
