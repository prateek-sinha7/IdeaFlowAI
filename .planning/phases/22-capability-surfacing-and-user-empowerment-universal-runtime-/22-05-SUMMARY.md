---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
plan: 05
subsystem: ui
tags: [capabilities, palette, react, typescript, vitest, tailwind, sc-001, surf-01, emp-02]

# Dependency graph
requires:
  - phase: 22-02
    provides: "GET /api/capabilities now carries description + security_gated + populated config_schema per entry (the palette data contract)"
provides:
  - "CapabilityPaletteSection — an embedded grouped-by-kind capability palette inside AgentsPopup (D-01), exported for isolated render-testing"
  - "Renders EVERY capability kind from the live /api/capabilities registry, grouped by kind, with NO hardcoded capability-name array (SC-001 palette-source grep = 0)"
  - "user_allowed=false caps render visible-but-LOCKED (Lock + Engineer-only + aria-disabled) per EMP-02/D-04 — never user-composable"
  - "SURF-03 declaredCapabilities strip showing the opened workflow's compiled per-step capabilities"
  - "Reuses the AgentModelPicker fetch/loading/error/empty shell (D-02); aliased getCapabilities import resolves the local helper name collision"
affects: [22-06 per-agent Advanced expander (selects from the same palette data), SC-001 no-FE-hardcoded-capability-list]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Embedded composer section exported for isolated render-testing (not a standalone route/file — Pitfall 1 / INV-12)"
    - "Group-by-payload-kind with a derived title-cased header (titleCaseKind) — no hardcoded kind/name list (SC-001)"
    - "Visible-but-locked row idiom for user_allowed=false caps (recessed gray + Lock + aria-disabled), reused from the live disabled idiom"

key-files:
  created:
    - frontend/src/components/workflow/CapabilityPaletteSection.test.tsx
  modified:
    - frontend/src/components/workflow/AgentsPopup.tsx

key-decisions:
  - "Palette embedded inside AgentsPopup as exported CapabilityPaletteSection — NOT a resurrected standalone CapabilityPalette.tsx (Pitfall 1 / ISS-014 / D-01)"
  - "API fetcher imported as `getCapabilities as fetchCapabilities` to resolve the name collision with the local getCapabilities(agent) helper, leaving the local helper untouched"
  - "Group headers derived by title-casing the payload `kind` (titleCaseKind) — no hardcoded kind list; whatever the registry returns is what groups (SC-001)"
  - "security_gated lock icon shown on allowed-but-gated rows; user_allowed=false rows get the full locked treatment (Engineer-only + aria-disabled)"

patterns-established:
  - "Pattern 1: A composer sub-section that renders entirely from a fetched registry payload — a fixture-only capability appears with no FE source edit (SC-001 proof in test)"
  - "Pattern 2: Locked-but-visible affordance for privileged caps — neutral-recessed, advisory-only (the authoritative trust gate is server-side, 22-04)"

requirements-completed: [SURF-01, SURF-03, EMP-02]

# Metrics
duration: ~12min
completed: 2026-06-14
---

# Phase 22 Plan 05: Embedded Capability Palette Summary

**An `AgentsPopup`-embedded `CapabilityPaletteSection` renders EVERY registered capability kind from the live `GET /api/capabilities` registry, grouped by kind with registry-sourced descriptions, `user_allowed=false` caps shown visible-but-locked (Engineer-only + aria-disabled), and SURF-03 declared-caps strip — driven entirely by the fetched payload with zero hardcoded capability-name array (SC-001 palette-source grep = 0), reusing the `AgentModelPicker` fetch shell.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-14T23:21Z (approx)
- **Completed:** 2026-06-14
- **Tasks:** 2 (TDD: RED → GREEN)
- **Files modified:** 2 (1 created test + 1 modified component)

## Accomplishments
- Authored `CapabilityPaletteSection` embedded inside `AgentsPopup` (mounted in the Agents tab after the model picker), reusing the `AgentModelPicker` loading/error/empty fetch shell over `GET /api/capabilities` (D-02).
- Rows grouped by the payload `kind` with a derived title-cased header (`titleCaseKind`) — no hardcoded kind/name list (SC-001 palette-source grep = 0). Each row renders name + registry description + security-gated lock + an expandable config-schema affordance (only when `config_schema` is non-empty).
- `user_allowed=false` caps render visible-but-LOCKED per EMP-02/D-04: `Lock` icon, "Engineer-only" microcopy, `aria-disabled="true"`, `cursor-not-allowed`, recessed gray — non-selectable; locked rows are rendered, never hidden (SURF-01 "every kind visible").
- SURF-03: a `declaredCapabilities` prop renders a read-only "Declared by this workflow" strip showing the opened workflow's compiled per-step capabilities.
- Resolved the local `getCapabilities(agent)` name collision by importing the API fetcher as `fetchCapabilities`, leaving the local helper untouched.
- TDD render test (`CapabilityPaletteSection.test.tsx`, 7 cases) proving grouped rows, locked row, fixture-only-cap-appears (SC-001), loading/error/empty copy, and a source-level no-hardcoded-array grep guard.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave-0 RED palette render test** - `623b90e0` (test)
2. **Task 2: Embed grouped capability palette in AgentsPopup (GREEN)** - `7477e426` (feat)

**Plan metadata:** _(this docs commit)_

_Note: project-level `tdd_mode: false`, but the plan's tasks declare `tdd="true"`; the RED commit (`623b90e0`, 6 failing) precedes the GREEN commit (`7477e426`, 7 passing). No REFACTOR pass was needed._

## Files Created/Modified
- `frontend/src/components/workflow/CapabilityPaletteSection.test.tsx` (NEW) — render test: grouped-by-kind headers (title-cased), fixture-only cap appears (SC-001), locked row (Engineer-only + aria-disabled, EMP-02), loading/error/empty copy, and a source-level no-hardcoded-array grep guard.
- `frontend/src/components/workflow/AgentsPopup.tsx` — added `CapabilityPaletteSection` (exported), `titleCaseKind` helper, the aliased `fetchCapabilities` import, a `declaredCapabilities` prop (SURF-03), and the palette mount in the Agents tab.

## Decisions Made
- Palette is embedded as an exported `CapabilityPaletteSection` inside `AgentsPopup`, NOT a standalone `CapabilityPalette.tsx` (Pitfall 1 / ISS-014 / D-01); verified `ls src/components/workflow/CapabilityPalette.tsx` → absent.
- Group headers derived via `titleCaseKind` from the payload `kind` — no hardcoded kind list (D-03); the registry drives the group set.
- The API fetcher imported as `getCapabilities as fetchCapabilities` to resolve the name collision with the local `getCapabilities(agent)` helper (per the plan note).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `npx tsc --noEmit` reports exactly 2 errors, both the pre-existing `TS2352` const-assertion casts in `frontend/e2e/fixtures/mockApi.ts:95-96` (already recorded in this phase's `deferred-items.md` and noted in 22-02-SUMMARY). Touched files (`AgentsPopup.tsx`, the new test) are tsc-clean; `src/` is unaffected. Resolution: out of scope (SCOPE BOUNDARY).
- The directory-wide SC-001 grep over `src/components/workflow/` returns 2 hits — both inside the test fixture/guard (`CapabilityPaletteSection.test.tsx`: fixture `'strategy'`/`'validator'` data and the negative-assertion regex), NOT production source. The plan's acceptance grep is over the palette source (`AgentsPopup.tsx`), which returns **0**.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 22-06's per-agent "Advanced" expander selects from the same palette data (the live `/api/capabilities` payload this section already fetches and groups).
- Verification: `CapabilityPaletteSection.test.tsx` 7/7 GREEN; `AgentModelPicker.test.tsx` 2/2 (reused shell stays green); palette-source SC-001 grep = 0; standalone `CapabilityPalette.tsx` absent (Pitfall 1); touched files tsc-clean.
- The FE lock affordance is advisory (T-22-05-01); the authoritative trust gate is the server `_check_trust` at SAVE + LAUNCH (22-04).

## Self-Check: PASSED

- FOUND: frontend/src/components/workflow/CapabilityPaletteSection.test.tsx
- FOUND: frontend/src/components/workflow/AgentsPopup.tsx (CapabilityPaletteSection export)
- FOUND commit: 623b90e0 (Task 1 RED)
- FOUND commit: 7477e426 (Task 2 GREEN)

---
*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime*
*Completed: 2026-06-14*
