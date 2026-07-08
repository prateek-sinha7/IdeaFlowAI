---
phase: 32-run-screen-redesign-a4
plan: 10
subsystem: e2e-tests
tags: [sc-4, e2e, playwright, run-screen, reskin-hardening, re-anchor, delta-verify]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4 (plan 06)
    provides: "RunChatLane/DashboardLayout/PreviewPanel token reskin + terminal states"
  - phase: 32-run-screen-redesign-a4 (plan 08)
    provides: "Steps drill-down + ReviewGatePanel de-literalization/reskin"
provides:
  - "The 5 run-screen specs (ts-m/ts-c/ts-i/ts-f/ts-n) re-anchored off hardcoded color-class assertions onto reskin-durable role/structural selectors (SC-4 e2e half)"
  - "brittle-assertion grep (1B2A4A|bg-gray-900|textarea.font-mono) sum = 0 across the 5 specs"
affects: [Phase 34 (live/mocked-shell realignment pass — where the re-anchored assertions become observable)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Re-anchor a color-class assertion onto a reskin-durable signal that still asserts the SAME behavior, never onto a weaker/looser one (T-32-10-01): text-white (inverted selected state), shadow-md (raised affordance), rounded-full (badge shape), structural sole-child, ARIA role=textbox"
    - "Verify BY DELTA vs the pre-existing 128-red mocked baseline (DEF-29-06-1): prove non-regression by showing the diff touches only in-test assertion lines (never beforeEach/goto/fixtures), so no previously-green spec can be turned red"

key-files:
  created:
    - .planning/phases/32-run-screen-redesign-a4/32-10-SUMMARY.md
  modified:
    - frontend/e2e/tests/ts-m.questionnaire.spec.ts
    - frontend/e2e/tests/ts-c.input-trigger.spec.ts
    - frontend/e2e/tests/ts-i.agent-panels.spec.ts
    - frontend/e2e/tests/ts-f.skills-hooks.spec.ts
    - frontend/e2e/tests/ts-n.review-gate.spec.ts

key-decisions:
  - "The 4 non-reskinned components (QuestionnairePanel, IdeaInputPage, AgentProgressPanel, AgentsPopup) expose NO data-testid/data-selected/aria-selected on the asserted elements, and ReviewGatePanel's edit textarea + AgentProgressPanel's fill also carry no testid. Per the hard guardrail (e2e specs ONLY; never edit a component; never invent a non-existent testid), the re-anchor targets reskin-durable EXISTING signals (role/structural/utility class) instead of testids. The absent testids are logged below as plan-06/08 follow-ups, NOT added here."
  - "Verification is BY DELTA, not absolute-green: the mocked run is wholesale-blocked in beforeEach by the home-redesign 128-red baseline (DEF-29-06-1) before any re-anchored assertion executes. Non-regression is proven structurally (diff = assertion lines only); the assertions' own pass/fail is live-deferred to the Phase-34 shell-realignment pass."

requirements-completed: [SC-4]

# Metrics
duration: ~25min
completed: 2026-07-08
---

# Phase 32 Plan 10: Run-Screen E2E Reskin-Hardening (Color-Class Re-anchor) Summary

**The 5 run-screen e2e specs (ts-m/ts-c/ts-i/ts-f/ts-n) are hardened for the reskin (SC-4 e2e half): every enumerated brittle color-class assertion (`#1B2A4A`, `bg-gray-900`, `textarea.font-mono`) is replaced by a reskin-durable role/structural selector that still asserts the same behavior — brittle-grep sum = 0 — verified BY DELTA against the pre-existing 128-red mocked baseline (DEF-29-06-1) with zero component edits.**

## Performance
- **Duration:** ~25 min
- **Tasks:** 2 (Task 1 re-anchor + commit; Task 2 delta-verify)
- **Files:** 5 spec files modified (+ this SUMMARY)

## Accomplishments

- **Task 1 — re-anchor (SC-4):** replaced the 8 brittle color-class assertions across the 5 specs with reskin-durable selectors that reference REAL, grep-confirmed signals in the components (no component edits):
  - **ts-m** (57/79/83, QuestionnairePanel MCQ option selected state): `toHaveClass(/bg-\[#1B2A4A\]/)` → `toHaveClass(/text-white/)` (and the `.not` inverse). Selected options render inverted white-on-brand (`text-white`, component L436); unselected are `text-gray-700`. `text-white` survives the navy-hex→brand-token migration that the hex class does not.
  - **ts-c** (149/150, IdeaInputPage migration tile selected state): `toHaveClass(/bg-\[#1B2A4A\]/)` → `toHaveClass(/shadow-md/)`. The selected tile gains `shadow-md` (component L736; unselected tiles carry no shadow); the already-present placeholder-swap + Run-enablement assertions remain as the behavioral proof.
  - **ts-i** (100/107, AgentProgressPanel progress fill): `bar.locator("div.bg-\\[\\#1B2A4A\\]")` → `bar.locator("div").first()`. The fill is the track's sole inner child (component L259-264); the growth assertion (inline `width` style regex) is unchanged and durable.
  - **ts-f** (95, AgentsPopup skills count pill): `toHaveClass(/bg-gray-900/)` → `toHaveClass(/rounded-full/)`. The count is a `rounded-full` badge pill (component L753); the `toHaveText("1")` assertion (the real count proof) is retained.
  - **ts-n** (139/183, ReviewGatePanel edit textarea): `locator("textarea.font-mono")` → `getByRole("textbox")`. The edit pane's `<textarea>` (component L411) is the only textbox in edit mode (the redo box only mounts when `redoable`); the prefilled-value + `toBeVisible` assertions are retained.
- **Task 2 — delta-verify (SC-4):** ran the 5 specs under `--project=mocked` (reused the running dev server). Result reported BY DELTA (below), NOT as an absolute-green claim.

## Task Commits
1. **Task 1:** `adf00702` (test) — re-anchor brittle color-class run-screen e2e assertions to durable selectors (5 spec files).
2. **Task 2:** no file changes (verification-only task); results captured in this SUMMARY.

## Verification Observed

- **Brittle-assertion grep (Task-1 gate):** `grep -ciE "1B2A4A|bg-gray-900|textarea\.font-mono"` summed across the 5 specs = **0** (`BRITTLE_CLEAR`). Comments that referenced the hex were rewritten too (the grep counts them).
- **Each new anchor references a REAL component signal (grep-confirmed):**
  - `text-white` present in `QuestionnairePanel.tsx` (6×, incl. the selected-option branch L436).
  - `shadow-md` present in `IdeaInputPage.tsx` (1×, the selected-tile branch L736).
  - `h-0.5 bg-gray-100` track present in `AgentProgressPanel.tsx` (L259) — the fill is its sole child (L260-264).
  - `rounded-full bg-gray-900 text-white` pill present in `AgentsPopup.tsx` (3×, skills pill at L753).
  - `<textarea` present in `ReviewGatePanel.tsx` (2×; the edit textbox L411, the redo textbox L468 which only mounts when redoable).
- **git diff scope:** exactly the **5 e2e spec files** — no component file touched (confirmed via `git status --short` and `git show adf00702 --stat`).
- **Diff is assertion-only:** `git show adf00702` grep confirms the added lines are in-test `expect(...)`/`locator(...)`/comment lines; **no** `beforeEach`/`goto`/`runWith`/`selectWorkflow`/fixture/import line was touched.

### Mocked-Playwright DELTA result

- **Raw run:** `npx playwright test --project=mocked <5 specs>` → **38 failed / 38** (all in the suite).
- **Root cause (captured):** every failure occurs in the `beforeEach` hook at `dashboard.goto()` → `selectWorkflow`, timing out waiting for the home CreationHub button `getByRole('button', { name: /Generate product requirements/i })`. This is the **pre-existing home-redesign 128-red mocked baseline (DEF-29-06-1)** — the mocked home shell no longer exposes the workflow-selection affordance the old fixtures expect. The failure fires **before any re-anchored assertion in any of the 5 specs is reached.**
- **DELTA (the load-bearing metric):** **0 new reds introduced.** Tests I did NOT edit (e.g. TS-M-02, TS-I-01/02/03, TS-C-01, TS-F-01 — no color assertion) fail identically in the same `beforeEach`, and my diff provably touches only in-test assertion lines (never the `beforeEach`/fixtures that time out). It is therefore structurally impossible for the re-anchoring to have turned any previously-green run-screen spec red. **No previously-green spec regressed.**
- **Moved-to-green:** **0 observable at this offline layer** — the whole suite is blocked at the home shell (DEF-29-06-1) before the re-anchored assertions execute. The pass/fail of the re-anchored selectors against the reskinned DOM is **LIVE-DEFERRED to the Phase-34 shell-realignment / live pass** (per 32-VALIDATION.md "Manual-Only Verifications" + the DEF-29-06-1 out-of-scope note). Offline re-anchoring correctness is proven by the grep evidence above (brittle=0; every new anchor references a real, grep-confirmed component signal).

## Deviations from Plan

### None (execution matched the plan's intent)

The plan's Task-1 action text suggested some re-anchors onto `data-testid`/`data-selected`/`aria-selected`. Those attributes **do not exist** on the asserted elements (see follow-ups below), and the hard guardrail forbids editing components or inventing testids. Re-anchoring onto reskin-durable EXISTING signals (role/structural/utility class) is the same intent within the guardrail — recorded here for transparency, not a scope change. No component was edited; the git diff is the 5 spec files only.

## Component-testid follow-ups (owned by earlier waves — NOT fixed here)

Per the guardrail ("if a data-testid you need is MISSING from a reskinned component, record it as a plan-06/08 follow-up — do NOT add it here"), the following stable hooks would let a future maintainer anchor even more semantically. They are optional hardening, not blockers (the current role/structural anchors are durable):

| Component | Element | Suggested hook | Consumed by |
|-----------|---------|----------------|-------------|
| `QuestionnairePanel.tsx` (L431) | MCQ option button | `aria-pressed={isSelected}` (or `data-selected`) | ts-m 57/79/83 |
| `IdeaInputPage.tsx` (L731) | migration path tile | `aria-pressed={isSelected}` (or `data-selected`) | ts-c 150 |
| `AgentProgressPanel.tsx` (L260) | progress fill | `data-testid="progress-fill"` | ts-i 107 |
| `AgentsPopup.tsx` (L753) | skills count pill | `data-testid="skills-count-pill"` | ts-f 95 |
| `ReviewGatePanel.tsx` (L411) | edit textarea | `data-testid="gate-edit-textarea"` (or `aria-label`) | ts-n 139/183 |

Note: QuestionnairePanel / IdeaInputPage / AgentProgressPanel / AgentsPopup were **not** reskinned by plans 06/08 (they still carry raw `#1B2A4A`/`bg-gray-900`); their token migration + these hooks are a future-phase item. ReviewGatePanel was touched by plan 08 but its edit textarea was left without a testid.

## Issues Encountered
- **Pre-existing, out-of-scope (logged, NOT fixed):** the entire mocked run is blocked at the home CreationHub (DEF-29-06-1, ~120 home-redesign reds). This is the documented 128-red baseline and is explicitly out of this phase's scope; it will clear when the home-redesign spec-realignment lands (Phase 34). Not a spec bug from this plan.

## User Setup Required
None — test-file edits only; no package install, no env, no new network/auth surface (T-32-10-SC: no dependency added).

## Known Stubs
None — no stubs introduced (test-file re-anchoring only).

## Threat Flags
None — no new trust boundary (test-only plan). **T-32-10-01 (masking real regressions) mitigated:** each brittle assertion was re-anchored onto a durable selector that still asserts the SAME behavior (never weakened/deleted), and non-regression was proven BY DELTA (diff = assertion lines only → no green→red possible). **T-32-10-SC mitigated:** no package install, no new dependency.

## Self-Check: PASSED

- Files: ts-m/ts-c/ts-i/ts-f/ts-n spec files — all FOUND and modified; SUMMARY written.
- Commit `adf00702` — FOUND in git log.
- Guardrails: brittle grep sum = 0; every new anchor grep-confirmed against a real component signal; git diff = 5 spec files only (no component edits); DELTA non-regressing (0 new reds — diff is assertion-only, all baseline reds are in unchanged beforeEach); moved-to-green live-deferred to Phase-34 with grep proof captured.

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*
