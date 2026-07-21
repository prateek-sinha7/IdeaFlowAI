---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 11
subsystem: testing
tags: [fidelity-harness, playwright, screenshot-diff, run-screen, nd-register, issues-register, roadmap]

# Dependency graph
requires:
  - phase: 42-03
    provides: failed-run tab model (Group D) — the ND-U supersession recorded here
  - phase: 42-04
    provides: dead-code deletions (TodoCard) — the ISS-037 clause reconciled here
  - phase: 42-05
    provides: shared artifactPreview module + ReviewGatePanel deletion — the deletions ledger
  - phase: 42-08
    provides: gate 2-button + plan-preview — the artifactPreview consumer
  - phase: 42-09
    provides: settled artifact cards + F1/F2 brittle-parse follow-ups — recorded as deferred here
  - phase: 42-10
    provides: inline navy->brand reskin — the last src wave before this closeout
  - phase: 32
    provides: 32-05 ISS-035/036 code fix — the evidence for the register reconcile
provides:
  - Regenerated full run-screen fidelity gallery (both sides, every state) — the phase acceptance oracle
  - Corrected clarify/gate TARGET frames (Live mock's canonical Steps-active state)
  - Phase-42 ND register (ND-W/ND-X/ND-Y; ND-U SUPERSEDED; W0-42 RESOLVED)
  - Reconciled ISS-035/036 (RESOLVED) + ISS-037 TodoCard clause (CLOSED)
  - Phase-42 IMPLEMENTATION-REGISTER entry (deletions ledger + ND register + F1/F2)
  - deferred-items.md — the RUNUI-09 e2e reconciliation backlog + F1/F2 + ISS-037 residuals
affects: [phase-43, run-screen, e2e-reconciliation, RUNUI-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-sided screenshot-diff oracle: TARGET capture corrected to the mock's canonical state (tab:'steps') before the paused full-viewport shot, so the side-by-side is a fair comparison"
    - "ND register continues lettering in the assembler (single source of truth), README table mirrors it"

key-files:
  created:
    - .planning/phases/42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-/deferred-items.md
  modified:
    - frontend/e2e/fidelity/capture-mocks.mjs
    - frontend/e2e/fidelity/assemble-gallery.mjs
    - frontend/e2e/fidelity/README.md
    - .planning/ISSUES-REGISTER.md
    - .planning/IMPLEMENTATION-REGISTER.md
    - .planning/ROADMAP.md

key-decisions:
  - "Corrected the clarify/gate TARGET frames to Steps-active (the Live mock's tab:'steps' at :726; setPhase :850 does not reset tab) — fixes the oracle to the mock's real intent, not a fabrication"
  - "ISS-035/036 flipped OPEN->RESOLVED (code landed 32-05, VERIFIED 32-VERIFICATION Truth #8) — the stale-tracking-gap the register itself flagged"
  - "ND-U SUPERSEDED (Group D reversed the 39-05 uniform-tab ruling), W0-42 RESOLVED (takeovers removed) — reconciled rather than left as pre-fix rows"
  - "RUNUI-09 recorded NOT-met + deferred (33 stale mocked-e2e specs assert the pre-Phase-42 UI; not caused by this docs+harness plan) rather than falsely claiming green"

patterns-established:
  - "Register reconcile with evidence: no ISS status flip without the deciding commit/plan reference (T-42-11-01)"

requirements-completed: []  # RUNUI-06 oracle produced (sign-off is the orchestrator's); RUNUI-09 NOT met (deferred — see Deviations)

# Metrics
duration: ~45min
completed: 2026-07-15
---

# Phase 42 Plan 11: Full fidelity gallery regen + register/ISSUES reconcile Summary

**Regenerated the full run-screen fidelity gallery across every state with the clarify/gate TARGET frames corrected to the Live mock's canonical Steps-active state, recorded the Phase-42 ND divergences (ND-W/X/Y), and reconciled the registers (ISS-035/036 RESOLVED, ISS-037 TodoCard closed, F1/F2 deferred, Phase-42 IMPLEMENTATION-REGISTER + ROADMAP entries) — with RUNUI-09 honestly recorded as NOT-met (33 pre-existing stale mocked-e2e specs deferred to a reconciliation pass).**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-07-15
- **Tasks:** 2
- **Files modified:** 6 (+1 created)

## Accomplishments
- **Fixed the harness oracle:** `capture-mocks.mjs` now selects the Steps tab BEFORE the paused full-viewport shot, so the `full__clarifyawaiting` / `full__gateawaiting` TARGET frames render the Live mock's real clarify/gate composition (Steps panel + the paused status card in the lane) instead of the Preview-active capture artifact. Verified visually: clarify shows the Clarifications block + "Submit answers & start the build" in Steps with the "Awaiting you" card in the lane; gate shows the "Review gate — Task plan approved" 2-button block with the "task plan needs approval" card in the lane.
- **Regenerated both sides across all states:** OUR side (8/8 `zzz-baseline` captures pass) + TARGET side (settled/live/failed + the derived paused frames), assembled into `gallery.html` (37 pairs).
- **Phase-42 ND register:** added ND-W (planning has no pre-agent overlay), ND-X (clarify/gate default to Steps), ND-Y (settled artifact cards live-derived + F1/F2 brittle); reconciled ND-U (SUPERSEDED by Group D) + W0-42 (RESOLVED) in `assemble-gallery.mjs` + `README.md`.
- **Registers reconciled:** ISS-035 + ISS-036 flipped `OPEN`→`RESOLVED` with the deciding 32-05 commits + `32-VERIFICATION.md` Truth #8 evidence; ISS-037 TodoCard clause closed (42-04); F1/F2 recorded as deferred backend/additive follow-ups; the Phase-42 IMPLEMENTATION-REGISTER entry (deletions ledger + ND register + F1/F2) added; ROADMAP Phase 42 marked complete (11/11).
- **Verification confirmed:** `tsc --noEmit` clean; `vitest run` failure set = EXACTLY the 8 pre-existing baseline (zero net-new); fidelity harness produced the gallery.

## Task Commits

1. **Task 1: Regenerate the full gallery + fix clarify/gate TARGET frames + Phase-42 ND register** — `b11719a6` (test)
2. **Task 2: Reconcile the registers (ISS-035/036/037, F1/F2, IMPLEMENTATION-REGISTER, ROADMAP) + deferred-items** — `0fc6b0d3` (docs)

_Plan metadata (this SUMMARY + STATE): see the final metadata commit._

## Files Created/Modified
- `frontend/e2e/fidelity/capture-mocks.mjs` — clarify/gate paused frames select Steps before the full-viewport shot (oracle correction)
- `frontend/e2e/fidelity/assemble-gallery.mjs` — Phase-42 ND-W/X/Y; ND-U SUPERSEDED; W0-42 RESOLVED; header/doc-comment updated to ND-A..ND-Y
- `frontend/e2e/fidelity/README.md` — ND table + W0 note updated (Steps-active TARGET + W0-42 resolved)
- `.planning/ISSUES-REGISTER.md` — ISS-035/036 RESOLVED, ISS-037 TodoCard clause closed
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase-42 entry; Phase-32 tracking-gap note marked reconciled
- `.planning/ROADMAP.md` — Phase 42 complete (11/11); RUNUI-09 recorded NOT-met + deferred
- `.planning/phases/42-.../deferred-items.md` (created) — D-42-1 RUNUI-09 e2e backlog (classified), D-42-2/3 F1/F2, D-42-4 ISS-037 residuals

## Decisions Made
- Corrected the TARGET oracle to the mock's canonical `tab:'steps'` state rather than the capture-artifact Preview state — this fixes the oracle to the mock's real intent (comment at mock `:90` "CLARIFY — status only; the questions live in Steps"), it is not fabricating data.
- Flipped ISS-035/036 to RESOLVED only with the deciding commits + verification evidence (T-42-11-01 mitigation — no status flip without proof).
- Recorded RUNUI-09 as NOT-met + deferred rather than claim green (see Deviations).

## Deviations from Plan

### 1. [Scope boundary / honesty] RUNUI-09 mocked-e2e is NOT green — deferred, not caused by this plan
- **Found during:** Task 2 (the plan's `playwright --project=mocked` acceptance check)
- **Issue:** `npx playwright test --project=mocked` = **112 passed / 33 failed / 29 skipped** at HEAD. The 33 reds are `ts-*` specs that assert the **pre-Phase-42** run-screen UI: the deleted full-screen `ReviewGatePanel` (ts-n ×9) + `QuestionnairePanel` "Quick Setup" (ts-m ×7) takeovers, the changed terminal/cancel/streaming/clarify-gate chrome (ts-i/j/q/r/x/chat), plus some pre-existing stale assertions that predate Phase 42 (e.g. ts-a TS-A-06's retired "NEW" pill — self-documented in the spec: "left asserting the retired pill for reconciliation").
- **Root cause:** waves 42-02..42-10 changed the run-screen `src` but never reconciled these specs — `git diff add18741..HEAD -- frontend/e2e/tests/` touched ONLY `zzz-baseline.spec.ts`. This plan (42-11, docs + harness only) changed zero `src`/spec code, so it neither caused nor could responsibly fix a 33-spec reconciliation within a docs closeout.
- **Action:** did NOT claim RUNUI-09 green; did NOT mark RUNUI-09 complete in REQUIREMENTS/ROADMAP; recorded the full classified backlog in `deferred-items.md` (D-42-1) and flagged it in ROADMAP + IMPLEMENTATION-REGISTER. The orchestrator's hard-constraint verification scope (tsc + vitest 8-baseline + fidelity gallery) was met in full. A dedicated e2e-reconciliation pass (re-anchor selectors / `test.fixme` deleted-panel specs onto the inline surfaces — never delete a spec) is required to close RUNUI-09.
- **Verification:** tsc clean; vitest = 8-baseline; playwright reds enumerated + classified.
- **Committed in:** `0fc6b0d3` (docs record) — no code/spec change.

---

**Total deviations:** 1 (scope/honesty record — RUNUI-09 deferred).
**Impact on plan:** The plan's core deliverables (regenerated + corrected gallery, complete ND register, reconciled ISS-035/036/037, F1/F2 deferrals, Phase-42 IMPLEMENTATION-REGISTER + ROADMAP) all shipped. The one plan acceptance check that did not pass (playwright mocked green) is a pre-existing gap outside this docs+harness plan's scope, recorded transparently rather than faked.

## Issues Encountered
- The clarify/gate TARGET frames rendered Preview-active (a `capture-mocks.mjs` ordering artifact); root-caused to `setPhase` (mock `:850`) not resetting `tab` after the SURFACES pass ends on Preview, and fixed by selecting Steps before the paused full shot. Confirmed visually on both frames.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The full run-screen fidelity gallery is regenerated and paired for the ORCHESTRATOR's per-state visual sign-off (planning · live · clarify · gate · complete · failed) — the phase acceptance gate.
- **Blocker for RUNUI-09:** the 33-spec mocked-e2e reconciliation (D-42-1) must land before RUNUI-09 flips to Complete.
- F1/F2 (backend/additive) remain deferred behind the INV-3 FE-only fence.

## Self-Check: PASSED

- All modified/created files present (capture-mocks.mjs, assemble-gallery.mjs, README.md, gallery.html, ISSUES-REGISTER.md, IMPLEMENTATION-REGISTER.md, ROADMAP.md, deferred-items.md, 42-11-SUMMARY.md).
- Both task commits present in git history: `b11719a6`, `0fc6b0d3`.
- Gallery assembles 37 pairs; ND register carries 41 `ND-` references (ND-A..ND-Y + W0-42).

---
*Phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-*
*Completed: 2026-07-15*
