---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 10
subsystem: ui
tags: [react, tailwind, design-tokens, reskin, phase-32-tokens, run-screen]

# Dependency graph
requires:
  - phase: 42-06
    provides: "Restructured InlineClarifyActions (single submit, extras removed, Cancel re-home)"
  - phase: 42-08
    provides: "Restructured InlineGateActions (2-button Approve/Request-changes + preview)"
  - phase: 32
    provides: "Canonical brand token layer (--brand #3C2CDA + ink/line/surface/status ramps in globals.css @theme)"
provides:
  - "InlineClarifyActions, InlineGateActions, ResultCard routed through the Phase-32 brand token layer"
  - "Retired navy #1B2A4A + raw gray/blue/red/violet/amber removed from the three inline chat cards"
  - "Token-header / navy-body seam inside the Steps AwaitingCard resolved"
affects: [42-shell-fidelity, phase-35-palette-campaign, run-screen-fidelity]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inline chat cards consume the same brand/ink/line/surface/status utility tokens as the parent StepsOverviewSpine AwaitingCard chrome"
    - "Brand chroma (#3C2CDA) is the single accent; violet affordances (redo) fold onto brand tokens, not a second hue"

key-files:
  created:
    - .planning/phases/42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-/42-10-SUMMARY.md
  modified:
    - frontend/src/components/chat/InlineClarifyActions.tsx
    - frontend/src/components/chat/InlineGateActions.tsx
    - frontend/src/components/chat/ResultCard.tsx

key-decisions:
  - "Gate header icon: replaced the navy→violet gradient with a solid bg-brand box to match the sibling GateAwaitingCard icon chrome exactly (presentation parity, no structure change)"
  - "Violet redo affordances mapped to brand tokens (border-brand-border/text-brand/hover:bg-brand-fill) — the design system is one chroma, so violet collapses onto brand"
  - "Status colors mapped to the status ramp: red→status-failed(+strong/fill/border), amber→status-amber, pipeline blue→status-running, emerald→status-done"
  - "Muted red-400 cancel affordance kept its muted feel via text-status-failed/70 opacity modifier"

patterns-established:
  - "Reskin-look keep-behavior (D-15): only className color tokens change; handlers, props, labels, DOM, data-testids untouched"

requirements-completed: [RUNUI-06]

# Metrics
duration: 18min
completed: 2026-07-15
---

# Phase 42 Plan 10: Inline Card Brand-Token Reskin Summary

**InlineClarifyActions, InlineGateActions, and ResultCard reskinned from the retired navy #1B2A4A + raw gray/blue/red/violet/amber onto the Phase-32 brand token layer (bg-brand / text-brand / border-brand-border + ink/line/surface/status ramps), resolving the token-header / navy-body seam inside the Steps AwaitingCard with zero behavior change.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Inline clarify + gate cards now render on brand/ink/line/surface/status tokens — navy and raw palette gone; the gate icon box uses solid `bg-brand` matching the sibling `GateAwaitingCard`.
- ResultCard card-kind tones and chrome routed through the token layer (gate→`text-brand`, pipeline→`text-status-running`, deliverable→`text-status-done`, clarify→`text-status-amber`, spec_revision→`text-brand`); deep-link + SC-001 generic keying unchanged.
- The visible navy-body / token-header seam where these cards render inside the Steps `AwaitingCard` is closed — the inline body and the token-styled header now read as one brand surface (confirmed by the fidelity capture of the clarify-awaiting and gate-awaiting lanes).

## Task Commits

Each task was committed atomically:

1. **Task 1: Reskin InlineClarifyActions + InlineGateActions to brand tokens** - `47b32c4a` (style)
2. **Task 2: Reskin ResultCard to brand tokens** - `2fbd6c88` (style)

## Files Created/Modified
- `frontend/src/components/chat/InlineClarifyActions.tsx` - Chips/submit navy→`bg-brand`/`brand-pressed`; question text/hint/cancel → ink/surface/line + `text-status-failed`
- `frontend/src/components/chat/InlineGateActions.tsx` - Approve navy→`bg-brand`; header gradient→solid `bg-brand`; edit/preview grays→ink/line/surface; redo violets→brand tokens; reject reds→`status-failed` ramp; edit dot/hint ambers→`status-amber`
- `frontend/src/components/chat/ResultCard.tsx` - Card-kind tone map + container/title/body/deep-link raw palette→brand + ink/line/surface + status tokens

## Decisions Made
- **Gate icon box:** the mock's `GateAwaitingCard` uses a solid `bg-brand` icon square, so the inline gate's navy→violet gradient became a solid `bg-brand` — presentation parity, DOM unchanged.
- **Violet → brand:** the token layer is one chroma; the redo affordance's violet-200/300/700 collapsed onto `border-brand-border`/`text-brand`/`hover:bg-brand-fill`.
- **Status ramp:** red→`status-failed` (+`-strong`/`-fill`/`-border`), amber→`status-amber`, pipeline blue→`status-running`, emerald→`status-done`; these status-fill/border utilities are generated in the compiled CSS (verified against the shipped `.next` output and the sibling StepsOverviewSpine usage).
- **Muted cancel:** the subtle `text-red-400` cancel-workflow affordance kept its muted weight via `text-status-failed/70 hover:text-status-failed`.

## Deviations from Plan

None - plan executed exactly as written. Reskin was presentation-only (D-15): no handler, prop, state, label, DOM, or data-testid changed in any of the three files.

## Issues Encountered
None. TweaksPanel was left untouched per §7 (its font/color OPTIONS are user-facing content, not chrome).

## Verification

- **tsc:** `npx tsc --noEmit` (mockApi-filtered) — **0 errors**.
- **Navy grep:** `1B2A4A|#2a3d5e` across all three files — **0**.
- **Brand grep:** `bg-brand|text-brand|border-brand` — InlineGateActions 7, InlineClarifyActions 3, ResultCard 3 (all ≥ threshold).
- **Residual raw palette:** gray/red/violet/amber/blue/emerald numeric classes across the three files — **0**.
- **vitest (full suite):** 694 passed, **8 failed — EXACTLY the documented pre-existing baseline**: PreviewPanel.switcher ×3, PreviewPanel.degraded ×1, HomeLaunchGrid.inspect ×2, FilesTab.runInput ×2. Zero net-new. Targeted suites (InlineClarifyActions, InlineGateActions = 24; ResultCard = 10) all green.
- **Fidelity harness:** `FIDELITY_CAPTURE=1 playwright --project=mocked zzz-baseline` — **8/8 passed** (incl. clarify-awaiting + gate-awaiting lanes that render the reskinned cards inside the AwaitingCard).
- **TweaksPanel:** not in the plan diff (untouched).

## Next Phase Readiness
- The three inline run-screen cards are now on the brand token layer; the AwaitingCard seam is closed for the surfaces this phase owns.
- Broader Phase-35+ palette campaign remains for other subtrees, but nothing in this phase's run surfaces is blocked.

## Self-Check: PASSED
- FOUND: frontend/src/components/chat/InlineClarifyActions.tsx (modified)
- FOUND: frontend/src/components/chat/InlineGateActions.tsx (modified)
- FOUND: frontend/src/components/chat/ResultCard.tsx (modified)
- FOUND: commit 47b32c4a (Task 1)
- FOUND: commit 2fbd6c88 (Task 2)

---
*Phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-*
*Completed: 2026-07-15*
