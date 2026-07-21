---
phase: 35-shell-chrome-reskin-pages-b1
plan: 01
subsystem: ui
tags: [react, tailwind, tokens, a11y, shell-chrome, notifications, playwright, vitest]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign
    provides: "Canonical @theme token layer + ui primitives (Button/Card/Tabs/Badge/Pill)"
provides:
  - "Dark near-black app shell (AppHeader) on Phase-32 tokens with purple-underline nav"
  - "Nav relabel Catalogue->My Workflows (D-11); page key saved-workflows + routing unchanged (SC-001)"
  - "Keyboard/ARIA-complete profile menu + notifications bell (aria-haspopup/expanded, role=menu/menuitem, Escape-refocus, aria-current)"
  - "Token-reskinned NotificationPanel chrome (chrome only; live feed = Phase 38); status via Badge primitive"
  - "Pre-reskin mocked-Playwright baseline (frontend/e2e/.baseline-35.txt) for delta verification (DEF-29-06-1)"
  - "Two a11y test scaffolds (AppHeader.a11y, NotificationPanel.a11y) as the shell a11y contract"
affects: [35-02, 35-03, 35-04, 35-05, 35-06, 35-07, 36-home-history-my-workflows, 38-analytics-estimates-notifications]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shell a11y idiom: aria-haspopup=menu + aria-expanded on trigger, role=menu/menuitem on dropdown, Escape-close+refocus via wrapper onKeyDown"
    - "Nav = generic {key,label,icon} list keyed on page keys, purple-underline active (Tabs idiom) + aria-current='page' (SC-001)"
    - "Status chip via the Badge primitive keyed on a generic status prop (never a workflow name)"
    - "Reskin-by-delta: capture pre-reskin e2e baseline first, verify later waves against it"

key-files:
  created:
    - frontend/e2e/.baseline-35.txt
    - frontend/src/components/layout/AppHeader.a11y.test.tsx
    - frontend/src/components/ui/NotificationPanel.a11y.test.tsx
  modified:
    - frontend/src/components/layout/AppHeader.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/ui/NotificationPanel.tsx

key-decisions:
  - "Relabel 'Catalogue'->'My Workflows' visible text only; keep WorkflowCatalog component + saved-workflows page key + onNavigate handler (rename is Phase 36) — D-11/SC-001"
  - "Escape-to-close-and-refocus implemented as an onKeyDown on the wrapper div (catches focus on trigger OR menu) rather than only the menu container — robust for the trigger-focused case"
  - "NotificationPanel status label switched to the Badge primitive; completed->done and cancelled->amber per Badge normalization (D-15 adopt shared idiom)"
  - "DashboardLayout light-touch only: converted the page-shell body inline style var(--surface-paper) to the bg-surface-paper class; no routing/page-key restructure"

patterns-established:
  - "Pattern: shell interactive chrome (menu/bell) carries full keyboard+ARIA + Escape-refocus, asserted RED-first by a per-component *.a11y.test.tsx"
  - "Pattern: retired-palette + stray-stock grep == 0 per touched reskin file; every color routes through a Phase-32 token"

requirements-completed: [B1-01]

# Metrics
duration: ~30m (incl. ~18m e2e baseline capture)
completed: 2026-07-09
---

# Phase 35 Plan 01: Shell Chrome Reskin (Wave 1 FOUNDATION) Summary

**Dark near-black AppHeader on Phase-32 tokens with purple-underline nav (Home · Library · My Workflows), keyboard/ARIA-complete profile menu + notifications bell, token-reskinned NotificationPanel chrome, plus the pre-reskin mocked-Playwright baseline and two RED->GREEN a11y test scaffolds.**

## Performance

- **Duration:** ~30 min (of which ~18 min was the offline e2e baseline capture)
- **Started:** 2026-07-08T23:10:00Z (approx)
- **Completed:** 2026-07-08T23:39:30Z
- **Tasks:** 3
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments
- Reskinned the app shell (`AppHeader`) to the Workspace-v2 dark idiom entirely on Phase-32 tokens: `bg-surface-near-black` bar, `bg-brand` logo, Manrope wordmark, purple-underline nav replacing the white-fill pill.
- Relabeled the third nav item `Catalogue`->`My Workflows` (D-11) while keeping the `saved-workflows` page key + `onNavigate("saved-workflows")` routing UNCHANGED (SC-001; no component rename — that is Phase 36).
- Added full keyboard/ARIA to the profile menu (aria-haspopup/expanded, role=menu/menuitem, Escape-close+refocus, aria-current on active nav) and the notifications bell (aria-haspopup/expanded, role=menu, Escape-close+refocus), asserted RED-first then GREEN.
- Token-reskinned the `NotificationPanel` chrome (bell, unread badge, dropdown, header, empty-state, rows, StatusIcon, progress bar, status label via the `Badge` primitive, CTA links) with all feed wiring + props signature preserved (chrome only; live feed is Phase 38).
- Light-touched `DashboardLayout` (page-shell body background -> `bg-surface-paper`), captured the pre-reskin mocked baseline, and preserved every wired behavior (D-15).

## Task Commits

Each task was committed atomically:

1. **Task 1: Capture baseline + write failing a11y tests (RED)** — `ee8bec7d` (test)
2. **Task 2: Reskin AppHeader dark shell + nav + profile-menu a11y; light-touch DashboardLayout** — `7cd23559` (feat)
3. **Task 3: Reskin NotificationPanel chrome + bell a11y (chrome only)** — `9201560f` (feat)

**Plan metadata:** (this commit) `docs(35-01): complete shell-chrome plan`

_Note: This plan carried `type=tdd` tasks. Task 1 is the RED gate (a `test(...)` commit); Tasks 2/3 are the GREEN gate (`feat(...)` commits that turn the a11y tests green). Baseline capture is bundled with the RED commit rather than a separate commit._

## Files Created/Modified
- `frontend/e2e/.baseline-35.txt` (created) - Pre-reskin mocked-Playwright pass/fail set for delta verification; annotated environment-blocked (see Issues).
- `frontend/src/components/layout/AppHeader.a11y.test.tsx` (created) - Nav-label + aria-current + profile-menu aria/role/Escape assertions (7 tests).
- `frontend/src/components/ui/NotificationPanel.a11y.test.tsx` (created) - Bell aria-haspopup/expanded + role=menu + Escape + preserved aria-label (4 tests).
- `frontend/src/components/layout/AppHeader.tsx` (modified) - Dark-shell token reskin, purple-underline nav, My Workflows relabel, profile-menu a11y; all wiring preserved.
- `frontend/src/components/layout/DashboardLayout.tsx` (modified) - Page-shell body background inline literal -> `bg-surface-paper` class (light-touch only).
- `frontend/src/components/ui/NotificationPanel.tsx` (modified) - Chrome token reskin, Badge status chip, bell a11y; feed wiring + props signature preserved.

## Decisions Made
- **Nav relabel is text-only (D-11/SC-001):** kept `WorkflowCatalog`, the `saved-workflows` page key, and the `onNavigate("saved-workflows")` handler; only the visible string changed. The component rename is deferred to Phase 36.
- **Escape handler on the wrapper, not the menu:** binding `onKeyDown` on the `div.relative` wrapper (which contains both trigger and dropdown) makes Escape work whether focus is on the trigger button (the common post-open state) or inside the menu — a document-listener alternative was avoided to keep the handler scoped.
- **Status label -> `Badge` primitive:** adopts the shared status idiom (running->blue, completed->done, failed->red, cancelled->amber via Badge normalization) per D-15 rather than a bespoke inline chip.
- **DashboardLayout strictly light-touch:** only the page-shell body background was retokenized; the file's remaining pre-existing stock palette (7 lines) is out of scope for this plan and will be addressed by the relevant later reskin plan.

## Deviations from Plan

None - plan executed exactly as written.

The DashboardLayout light-touch was scoped by the plan to the body background only; its pre-existing stock-palette lines were intentionally left (plan: "do NOT restructure routing or page keys"). This is a documented scope boundary, not a deviation. The unused `X` icon import was dropped from NotificationPanel during its reskin (dead code cleanup within the touched file).

## Issues Encountered
- **e2e baseline environment-blocked (live-deferred):** Playwright browsers ARE installed and the mocked suite DOES run, but the mocked webServer does not serve cleanly in this offline sandbox — specs systematically time out at ~45.8s and the full 158-test run does not complete in bounded time. Per the phase environment contract (do NOT install browsers, do NOT block the plan on e2e), the runner was stopped after capturing the partial pass/fail set (8 passed / 81 failed rows before stop) and `frontend/e2e/.baseline-35.txt` was annotated accordingly. A clean full-suite pass/fail is deferred to the Phase-34 live pass. Later Wave-1/Wave-2 plans still diff by delta against whatever rows are present.

## Verification Evidence
- **Retired-palette grep == 0** on all three touched files (`#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains`).
- **Stray-stock grep == 0** on `AppHeader.tsx` and `NotificationPanel.tsx` (`bg-[#`, `text-[#`, `#hex`, `bg/text-(blue|gray|slate|indigo|emerald|red)-`, `#111827`, `#1f2937`). `AppHeader.tsx` positively contains `bg-surface-near-black` + `border-brand`; `NotificationPanel.tsx` positively uses `text-status-*`/`text-ink-*`/`bg-surface-*` + the `Badge` primitive. `DashboardLayout.tsx` retired == 0 (light-touch; pre-existing stock out of scope).
- **Nav proof:** `grep -c Catalogue AppHeader.tsx` == 0; file contains `My Workflows` and `onNavigate("saved-workflows")`.
- **a11y GREEN:** `npm run test -- AppHeader.a11y` (7) + `NotificationPanel.a11y` (4) pass; RED confirmed pre-reskin (10 failed on assertions/queries, 1 passed = aria-label preserve).
- **tsc identity:** `npx tsc --noEmit 2>&1 | grep -v mockApi.ts | grep -c error` == 0.
- **No behavior regression:** `DashboardLayout.catalogHome` (2) + `DashboardLayout.waveMount` (4) still green; 17 component tests green total.

## Next Phase Readiness
- Shell chrome converged on tokens with the a11y contract locked; Wave 2 (35-02..35-07: Account Settings, Template/DS pickers, Review-gates, Library, Login/Register, Admin) is unblocked.
- Baseline artifact is present for delta verification; a clean full mocked/live e2e pass/fail is deferred to Phase 34 (live pass) per the environment contract.
- No new dependencies, no backend/transport touch (INV-3/LOCK-B held).

## Self-Check: PASSED
- All 6 files verified present on disk.
- All 3 task commits verified in git log (ee8bec7d, 7cd23559, 9201560f).

---
*Phase: 35-shell-chrome-reskin-pages-b1*
*Completed: 2026-07-09*
