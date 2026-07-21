---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 01
subsystem: testing
tags: [playwright, fidelity-harness, screenshot-oracle, run-screen, mockws, e2e]

# Dependency graph
requires:
  - phase: 39-run-screen-mock-fidelity
    provides: the two-sided screenshot oracle (zzz-baseline.spec.ts + capture-mocks.mjs + assemble-gallery.mjs) that this plan extends
  - phase: 41-composer
    provides: the mockWs paused-lane driver patterns (questionnaireReady / reviewGateReady) reused here
provides:
  - Paused/planning capture of OUR run screen (planning · clarify-awaiting · gate-awaiting) into shots/current
  - TARGET capture of the Live mock's clarify/gate paused frames + a building-phase planning proxy into shots/target
  - Side-by-side gallery pairing for the three new paused states + a W0-42 pre-fix register row
affects: [42-02, 42-03, 42-04, 42-05, "Phase-42 W1+ per-state screenshot sign-off"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Paused-state capture: drive the mocked WS to a state then STOP (do not advance) and screenshot — the inverse of the settled/live flow that answers clarify + approves the gate"
    - "Proxy-target documentation: when the mock has no dedicated frame for a state (pre-agent planning), capture the nearest reference (Building phase) and flag it in README + the assembler register rather than fabricate a cell"

key-files:
  created: []
  modified:
    - frontend/e2e/tests/zzz-baseline.spec.ts
    - frontend/e2e/fidelity/capture-mocks.mjs
    - frontend/e2e/fidelity/assemble-gallery.mjs
    - frontend/e2e/fidelity/README.md

key-decisions:
  - "Planning has no dedicated mock frame — used the Live mock's Building running phase as a documented planning proxy (nearest reference), not a fabricated cell"
  - "W0 captures the CURRENT pre-fix legacy full-screen takeover on our side — the correct 'before' baseline; logged as register row W0-42 (temporary, NOT a permanent ND)"
  - "Reused the single shared MockApi/mockWs fixture (INV-12) — no forked stub"

patterns-established:
  - "Paused-state oracle: capture(state) pauses the run and screenshots full/steps/leftlane; the assembler auto-pairs by {surface}__{state} tag"

requirements-completed: [RUNUI-06, RUNUI-09]

# Metrics
duration: 18min
completed: 2026-07-14
---

# Phase 42 Plan 01: Run-Screen Paused-State Fidelity Harness Summary

**Extended the Phase-39 screenshot oracle to pause our run screen at planning / clarify-awaiting / gate-awaiting and pair those states side-by-side against the Live mock — the acceptance oracle Phase-42's later waves close against.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-07-14T23:50Z
- **Completed:** 2026-07-14T23:57Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Three new FIDELITY_CAPTURE tests pause the run screen at planning, clarify-awaiting, and gate-awaiting WITHOUT advancing, emitting `full__planning`, `full/steps__clarifyawaiting`, `full/steps__gateawaiting` + the three `leftlane__*` clips (8 new current-side PNGs).
- `capture-mocks.mjs` drives the Live mock's phase scrubber to capture the matching TARGET clarify/gate paused frames, plus the Building running phase as a documented planning proxy (8 new target-side PNGs).
- `assemble-gallery.mjs` pairs all three new states target-vs-current (37 pairs total) and carries a new **W0-42** register row explaining our side still shows the legacy full-screen takeover pre-fix.
- README documents the three new state tags + a single-state regen recipe.

## Task Commits

Each task was committed atomically (conventional-commits, no trailer, on `feat/ui-2`):

1. **Task 1: Capture OUR run screen paused at planning/clarify-awaiting/gate-awaiting** — `594170a8` (test)
2. **Task 2: Capture the TARGET mock paused states + pair them in the gallery** — `8958fe54` (chore)

## Files Created/Modified
- `frontend/e2e/tests/zzz-baseline.spec.ts` — +3 paused-state capture tests (planning/clarify-awaiting/gate-awaiting) + a shared `stepsTab` locator
- `frontend/e2e/fidelity/capture-mocks.mjs` — target capture of the Live mock's clarify/gate paused frames + building-phase planning proxy
- `frontend/e2e/fidelity/assemble-gallery.mjs` — W0-42 register row + summary caption update; auto-pairs the new tags
- `frontend/e2e/fidelity/README.md` — new state tags, the W0 pre-fix expectation, and single-state regen commands

## Decisions Made
- **Planning proxy:** the mocks have no dedicated pre-agent (0-agent) planning frame; the Live mock's Building running phase is captured as the nearest reference and flagged in README + the assembler register — an honest proxy, not a fabricated cell.
- **W0 baseline is intentional:** at Wave 0 our side still renders the legacy full-screen takeover during these phases, so `steps__*` and `full__*` are identical and diverge heavily from the mock. That is the "before" baseline the later waves regenerate; recorded as register row W0-42, explicitly NOT a permanent intended divergence.
- **No fixture fork (INV-12):** reused the existing shared MockApi/mockWs and the `launch`/`seedBrief`/`AGENTS`/`CLARIFY_Q`/`shot` helpers.

## Deviations from Plan

None - plan executed exactly as written. (Done-criteria followed precisely: no `steps__planning` on either side, mirroring the plan's explicit artifact list.)

## Issues Encountered
None. The `timeout` coreutil is absent on macOS so the first capture-mocks attempt was re-run without it; network was available, so all TARGET frames (including the paused states) captured successfully — capture-mocks is network-gated by design and its human sign-off is deferred to Wave 6 per the phase constraints.

## Verification

- `npx tsc --noEmit` (excl. pre-existing `mockApi`): **0 error TS** — clean.
- `FIDELITY_CAPTURE=1 npx playwright test zzz-baseline --workers=1`: **8 passed (58.5s)** — incl. the 3 new paused tests (planning 3.8s, clarify-awaiting 9.5s, gate-awaiting 9.6s).
- `node frontend/e2e/fidelity/assemble-gallery.mjs`: **37 pair(s)** assembled, exit 0.
- `node frontend/e2e/fidelity/capture-mocks.mjs --state live`: captured 4 tabs + leftlane + the 8 new paused TARGET frames.
- Grep guards: `clarifyawaiting|gateawaiting|planning` present in assemble-gallery.mjs (3) + README.md (5); gallery.html contains all 8 new-state pairs + 2× `W0-42`.
- Product-file guard: `git diff --name-only HEAD~2 HEAD` lists **only** 4 `frontend/e2e/` files — zero backend / golden / manifest / `useWorkflow` / transport / `.tsx` changes.
- No unit spec was touched, so `npx vitest run` was not required (no `.tsx`/component change).

## Next Phase Readiness
- The oracle now covers planning + clarify-awaiting + gate-awaiting alongside settled/live/failed. Wave 1 (42-02) can remove the legacy takeovers and regenerate the "after" against these baseline cells.
- Blocker: none. The human gallery sign-off for these rows is deferred to Wave 6 (42-11) per the phase plan; this wave only establishes the capture infrastructure and confirms it runs and produces paired captures.

## Self-Check: PASSED

- Commits `594170a8`, `8958fe54` present in git log.
- All modified files + `42-01-SUMMARY.md` present on disk; `gallery.html` regenerated with the new paired rows.

---
*Phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-*
*Completed: 2026-07-14*
