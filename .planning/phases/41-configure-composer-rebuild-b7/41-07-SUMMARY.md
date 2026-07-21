---
phase: 41-configure-composer-rebuild-b7
plan: 07
subsystem: ui
tags: [react, drawer, library, agent-inspector, fidelity, tailwind, framer-motion]

# Dependency graph
requires:
  - phase: 41-04
    provides: "shared AgentCapabilitiesModal inspector + AgentPromptSection surfaceOnly (composer per-agent inspector)"
  - phase: 40-03
    provides: "Phase-40-signed-off Library composition (h1 + count + search + Agents/Skills/Hooks grids) + the ND-Z deferral this plan closes"
provides:
  - "Library agent-detail opens as a right-side DRAWER (Overview/Skills/Hooks/Config) matching the mock's drawerOpen surface — ND-Z RESOLVED"
  - "Shared AgentCapabilitiesModal gains an asDrawer variant (in-place restructure, not forked); composer callers keep the centered modal"
  - "Tightened shared Overview body (What it does · Role-in-pipeline role name · real-data skill chip · read-only System Prompt) — improves all four callers' Overview"
affects: [phase-41-verifier, library, composer-inspector]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Variant-prop shell restructure (asDrawer) over a shared inspector — one component serves both a right-drawer (Library) and a centered modal (composer), no fork"
    - "Read-only inspector stance (ND-7/LOCK-E): AgentPromptSection surfaceOnly surfaces the system prompt with no editable field / Save / Revert"

key-files:
  created: []
  modified:
    - frontend/src/components/workflow/AgentsPopup.tsx
    - frontend/src/components/library/LibraryPage.tsx
    - frontend/src/components/library/LibraryPage.test.tsx
    - frontend/src/components/workflow/AgentDrawer.test.tsx
    - frontend/e2e/tests/zzz-shell-baseline.spec.ts
    - frontend/e2e/fidelity/capture-shell-mocks.mjs
    - frontend/e2e/fidelity/assemble-phase41-gallery.mjs

key-decisions:
  - "asDrawer variant prop (default = existing centered modal) instead of a wholesale shell swap — three of four consumers (AgentLibrary, composer inspector, AgentDrawer.test) are Phase-40 composer surfaces not re-verified here, so their chrome stays byte-identical while Library gets the drawer"
  - "Overview-body tightening applied to the SHARED inspector (improves all four callers' Overview, intended) — no fork"
  - "Read-only stance KEPT (ND-AM): no editable Save-agent/Reset footer, no inline editable prompt — agents are inspected, not edited"
  - "Skill-support chip binds to real agent.has_skill (ND-D: omitted when false, even though the mock's example agent shows it)"

patterns-established:
  - "Fidelity capture must drive the surface into its target STATE (drawer OPEN) on BOTH sides — the mock-side capture driver was fixed to click the card by name and wait for the drawer, mirroring our side"

requirements-completed: [CMPUI-05]

# Metrics
duration: ~90min
completed: 2026-07-14
---

# Phase 41 Plan 07: Library agent-detail right-side drawer Summary

**The Library agent-detail now opens as the mock's right-side slide-in drawer (Overview/Skills/Hooks/Config) — the shared AgentCapabilitiesModal restructured in place via an asDrawer variant (not forked), with the shared Overview body tightened to the mock; ND-Z resolved.**

## Performance

- **Duration:** ~90 min (across build + fidelity checkpoint + approved Overview follow-up)
- **Started:** 2026-07-14T02:20:00Z
- **Completed:** 2026-07-14T09:30:00Z
- **Tasks:** 2 (1 auto build + 1 blocking fidelity checkpoint, human-approved) + 1 approved follow-up
- **Files modified:** 7

## Accomplishments
- Library agent card opens a right-side DRAWER (slide-in-from-right, avatar/name/role header, Overview/Skills/Hooks/Config tab bar) matching the mock's `drawerOpen` surface — closes the Phase-40 ND-Z deferral and SHELL-04's Agent-drawer clause (CMPUI-05).
- The shared `AgentCapabilitiesModal` was restructured IN PLACE with an `asDrawer` variant prop (default = existing centered modal); the composer's per-agent inspector + AgentLibrary keep their modal chrome unchanged (single shared component, not forked — proven by grep + the composer AgentDrawer.test staying green).
- The shared Overview tab body was tightened to the mock (approved follow-up): heading "What it does"; a "Role in pipeline" block showing the agent's ROLE NAME (not the generic step index); the meta chip row relocated from the header into the Overview body with a real-data-bound "Skill support" chip; and a read-only "System Prompt" surface (reused `AgentPromptSection surfaceOnly`). All four callers' Overview benefits.
- Read-only stance KEPT and registered as ND-AM: no editable Save-agent/Reset footer, no inline editable prompt (ND-7/LOCK-E surface-only).
- Both the target mock and our capture were driven into the drawer-OPEN state for an apples-to-apples fidelity comparison; human-approved twice (drawer chrome, then the tightened Overview).

## Task Commits

1. **Task 1: Restructure AgentCapabilitiesModal into a right-side drawer + open from the Library card (+ fidelity-capture drivers)** - `982f6533` (feat)
2. **Fidelity checkpoint (Task 2)** - human-approved (drawer chrome matches the mock's `drawerOpen`; ND-Z resolved)
3. **Follow-up (approved): tighten the shared Overview body to the mock** - `08eb3833` (feat)

**Plan metadata:** this closeout commit (docs: SUMMARY + assembler ND-AM + STATE)

## Files Created/Modified
- `frontend/src/components/workflow/AgentsPopup.tsx` - `AgentCapabilitiesModal` gains `asDrawer` (conditional scrim layout + panel chrome + slide animation); Overview body tightened (What-it-does label, Role-in-pipeline role name, relocated real-data chip row, read-only System Prompt via `AgentPromptSection surfaceOnly`); header chip row removed to mirror the mock header.
- `frontend/src/components/library/LibraryPage.tsx` - the agent card's `selectedAgent` open path passes `asDrawer`.
- `frontend/src/components/library/LibraryPage.test.tsx` - asserts the drawer opens on agent-select (right-side dialog + four tabs) and the tightened Overview (role name, no "Step N", skill chip, read-only System Prompt, no textarea/Save/Revert).
- `frontend/src/components/workflow/AgentDrawer.test.tsx` - the composer-inspector (modal-form) test's Overview label assertion tracked to the shared rename ("what it does"); stays green (no test loosened).
- `frontend/e2e/tests/zzz-shell-baseline.spec.ts` - our-side capture driver clicks the agent card and waits for the drawer before shooting.
- `frontend/e2e/fidelity/capture-shell-mocks.mjs` - mock-side capture driver clicks the first library agent by name (DC runtime normalizes inline styles, so the prior style-attribute selector was a no-op) and waits for the 472px drawer body.
- `frontend/e2e/fidelity/assemble-phase41-gallery.mjs` - added the "SURFACE 3 — LIBRARY agent-detail DRAWER" pair (target `agent-detail-drawer__shell` vs current `library-agent-detail__shell`) and registered **ND-AM** (range refs bumped ND-AE..AL → ND-AE..AM).

## Decisions Made
- **`asDrawer` variant over a wholesale shell swap.** Three of four consumers render the inspector as a centered modal on Phase-40-signed-off composer surfaces this plan does not re-capture; the variant prop (default modal) keeps their chrome byte-identical while giving Library the drawer, and remains a single shared component (not forked).
- **Overview tightening applied to the shared inspector** (intended to improve all four callers' Overview), reusing `AgentPromptSection surfaceOnly` for the read-only system prompt (INV-3, no forked prompt editor).
- **Read-only stance kept (ND-AM)** — the drawer inspects agents; it omits the mock's editable Save-agent/Reset footer and inline editable prompt (ND-7/LOCK-E).

## Deviations from Plan

The plan's `files_modified` listed only the three source files. The fidelity checkpoint (Task 2) required the capture to show the drawer OPEN on both sides, so the capture drivers were fixed:

### Auto-fixed Issues

**1. [Rule 3 - Blocking, fidelity infra] Our-side capture never opened the drawer**
- **Found during:** Task 2 (fidelity capture)
- **Issue:** `zzz-shell-baseline.spec.ts` clicked `getByRole("button")` for the agent, but the Library agent card is a clickable `<div>` (Card) — the click was a no-op, so the capture showed the grid, not the drawer.
- **Fix:** click the card and `waitFor` the `agent-drawer` panel visible before shooting.
- **Files modified:** frontend/e2e/tests/zzz-shell-baseline.spec.ts
- **Committed in:** 982f6533

**2. [Rule 3 - Blocking, fidelity infra] Mock-side (target) capture never opened the drawer**
- **Found during:** Task 2 (fidelity capture)
- **Issue:** `capture-shell-mocks.mjs` used a no-space inline-style attribute selector; the DC runtime normalizes `style` to spaced form, so the selector matched nothing and the target shot showed the Library grid, not the mock's `drawerOpen` surface.
- **Fix:** click the first library agent by name ("Architecture Agent") — bubbles to the card's `openDrawer` — and wait for a drawer-only body label.
- **Files modified:** frontend/e2e/fidelity/capture-shell-mocks.mjs
- **Committed in:** 982f6533

**3. [Approved follow-up] Overview-body tightening + AgentDrawer.test label tracking**
- **Found during:** Coordinator review after the drawer-chrome approval
- **Issue:** the shared Overview body diverged from the mock (label wording, generic step index instead of role name, no read-only system prompt, chip row in the header not the body).
- **Fix:** the four read-only Overview changes; the composer-inspector test's Overview-label assertion tracked to the rename.
- **Files modified:** frontend/src/components/workflow/AgentsPopup.tsx, frontend/src/components/library/LibraryPage.test.tsx, frontend/src/components/workflow/AgentDrawer.test.tsx
- **Committed in:** 08eb3833

---

**Total deviations:** 2 auto-fixed (both Rule 3, fidelity-capture infra) + 1 coordinator-approved follow-up.
**Impact on plan:** The capture-driver fixes were required to satisfy the plan's screenshot-diff acceptance; the Overview tightening was an explicit coordinator-approved fidelity improvement to the shared inspector. No scope creep into other surfaces.

## Verification
- `npx tsc --noEmit` — clean (pre-existing `mockApi.ts` noise filtered; 0 `error TS`).
- `npx vitest run src/components/library/LibraryPage.test.tsx src/components/workflow/AgentDrawer.test.tsx` — **15 passed (2 files)**.
- Not-forked proof: `grep -rn "AgentCapabilitiesModal" frontend/src` → one shared component (restructured in place + an `asDrawer` prop); composer AgentDrawer.test (modal form) green — no caller broke.
- Read-only proof: no `<textarea` / `<input` / Save / Reset affordance in the Overview body (comments excluded); `grep -c "Save agent"` = 0; `dangerouslySetInnerHTML` in the drawer = 0 (T-41-07-01).
- Fidelity: drawer captured OPEN on both sides (4 tabs) — `current/library-agent-detail__shell.png` vs `target/agent-detail-drawer__shell.png`, assembled into `gallery-phase41.html` (`--surface library`), human-approved (drawer chrome + tightened Overview). ND-Z RESOLVED.

## Known Stubs
None — the drawer renders live owner-scoped agent/capability data; the Config + Overview system-prompt surfaces reuse the shipped `AgentPromptSection surfaceOnly` (read-only by design, ND-7/LOCK-E).

## Issues Encountered
- The prior target mock shot (`agent-detail-drawer__shell.png`) was stale/invalid (showed the grid). Root cause: DC-runtime inline-style normalization defeated the style-attribute selector. Resolved by clicking the card by name + waiting for the drawer (see Deviations #2).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Phase-41 plans (41-01..07) are executed. Wave 5 (41-05 Composer Canvas + 41-07 Library drawer) is fully closed.
- Ready for the Phase-41 verifier + register/roadmap closeout (run by the coordinator).
- Not pushed — the coordinator pushes after verifying.

---
*Phase: 41-configure-composer-rebuild-b7*
*Completed: 2026-07-14*
