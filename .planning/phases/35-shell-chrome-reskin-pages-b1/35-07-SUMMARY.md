---
phase: 35-shell-chrome-reskin-pages-b1
plan: 07
subsystem: ui
tags: [react, tailwind, tokens, a11y, admin, vitest, reskin]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign
    provides: "Canonical @theme token layer + ui primitives (Card/Button/Badge/Pill)"
  - phase: 35-shell-chrome-reskin-pages-b1
    provides: "35-01 dark near-black shell idiom + shell a11y menu-button pattern (aria-haspopup/expanded, role=menu, Escape-close)"
provides:
  - "Admin console (app/admin/page.tsx) fully reskinned onto Phase-32 tokens/primitives (Card/Badge/Button/Pill) with retired-palette grep=0 and no per-page palette fork (D-15)"
  - "TierDropdown menu-button a11y: aria-haspopup/aria-expanded on the trigger + role=menu/menuitem + Escape-to-close"
  - "Preserved richer wiring (ND-12): is_admin gate+redirect, adminListUsers/UpdateTier/CreateUser/DeleteUser, optimistic tier revert, wired search, Runs/Role/Joined columns, password-create modal, self-delete guard, strong delete copy"
affects: [36-home-history-my-workflows, 38-analytics-estimates-notifications]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TierBadge -> Badge primitive: tier mapped to the shared status-ramp (basic->queued grey, pro->running violet, enterprise->done green) with the tier LABEL passed explicitly, so tier color routes through tokens with no bespoke hex"
    - "Menu-button a11y reused from the 35-01 shell idiom on a table-row dropdown (aria-haspopup/expanded + role=menu/menuitem + wrapper onKeyDown Escape-close)"
    - "Reskin defer guard: no columns/fields added for data the AdminUser API does not return (Status/Last-active/display_name) — asserted by a queryByRole(columnheader) negative test (ND-12/INV-3)"

key-files:
  created:
    - frontend/src/app/admin/admin.reskin.test.tsx
  modified:
    - frontend/src/app/admin/page.tsx

key-decisions:
  - "TierBadge reimplemented on the Badge primitive via a tier->status map (basic=queued/pro=running/enterprise=done) + explicit label; Badge only exposes status-ramp keys, so tier differentiation is carried by the ramp intensity rather than a per-page tier palette (D-15, retired TIER_STYLES hex deleted)"
  - "Role Admin chip and the Users count use the Pill primitive (Pill keeps the Shield icon, which Badge cannot host); Add-user/Cancel/Create use the Button primitive; the Delete danger button is a token-classed button (bg-status-failed) since Button has no danger variant"
  - "Modals keep their motion.div animation wrappers but swap to token panel classes (bg-surface-card/border-line-border/rounded-card + --elevation-modal + --scrim) rather than nesting the Card component, preserving the entrance animations while staying fully tokenized"

patterns-established:
  - "Pattern: a row-level dropdown adopts the same menu-button a11y contract as the shell chrome (aria-expanded on trigger, role=menu/menuitem, Escape-close), asserted by a render test"
  - "Pattern: retired-palette + stray-stock grep == 0 per touched reskin file; every color routes through a Phase-32 token"

requirements-completed: [B1-07]

# Metrics
duration: ~12m
completed: 2026-07-09
---

# Phase 35 Plan 07: Admin Console Reskin (Wave 2 FINAL) Summary

**Admin console (`app/admin/page.tsx`) reskinned onto Phase-32 tokens/primitives (Card/Badge/Button/Pill) with a near-black shell header, TierDropdown menu-button a11y, and every wired behavior + the is_admin gate + password-create modal preserved — Status/Last-active columns and email-invite deferred as unbacked.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-09T02:42:00Z (approx)
- **Completed:** 2026-07-09T02:50:00Z (approx)
- **Tasks:** 2 (TDD: RED test → GREEN reskin)
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- Reskinned the entire admin console to the Phase-32 token layer: near-black header shell (`bg-surface-near-black` + Manrope wordmark + an "Admin" `Pill`), 5 stat cards → `Card`, users table → `Card` + token surfaces/borders (`bg-surface-card`, `border-line-divider`, `text-ink-*`), delete/create modals on `--scrim` + `--elevation-modal`, and the toast on status-ramp tokens. Retired-palette grep = 0, no stray stock palette.
- Replaced the retired-hex `TierBadge`/`TIER_STYLES` with the `Badge` primitive (tier → status-ramp mapping + explicit label); added `Button`/`Pill` for the action controls and the role/count chips.
- Added the menu-button a11y contract to `TierDropdown` (aria-haspopup/aria-expanded on the trigger, `role=menu`/`role=menuitem`, Escape-to-close via a wrapper `onKeyDown`), asserted RED-first then GREEN.
- Preserved the product's richer wiring (ND-12): the `getMe().is_admin` gate + redirect, `adminListUsers/UpdateTier/CreateUser/DeleteUser`, optimistic tier update + revert-on-error, wired search, the Runs/Role/Joined columns, the create-user modal (email + password `type="password"` + plan + grant-admin), the self-delete guard, and the stronger delete copy ("permanently delete the user and all their data").
- Deferred the mock's Status + Last-active columns and the email-invite flow (AdminUser has no `status`/`last_active_at`/`display_name`); dropped account-suspension. A negative `columnheader` assertion guards against surfacing unbacked fields.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write admin reskin render test (columns + pw-create + gate + defer guard)** — `d27a889f` (test) — RED gate (4 pass / 1 fail: TierDropdown aria absent pre-reskin)
2. **Task 2: Reskin admin console to tokens/primitives, preserve wiring + gate** — `49a356e1` (feat) — GREEN gate (all 5 tests pass)

**Plan metadata:** (this commit) `docs(35-07): complete admin reskin plan`

_Note: `type=execute` plan with `tdd="true"` tasks — Task 1 is the RED `test(...)` commit; Task 2 is the GREEN `feat(...)` commit that turns the TierDropdown-a11y assertion green while keeping the wiring/gate assertions green._

## Files Created/Modified
- `frontend/src/app/admin/admin.reskin.test.tsx` (created) — Render test: Runs/Role/Joined columns, password-create modal, TierDropdown aria-expanded/role=menu/Escape, is_admin redirect gate, and Status/Last-active defer guard (5 tests). Mocks next/navigation + @/lib/api + motion/react (LOCK-B: no transport).
- `frontend/src/app/admin/page.tsx` (modified) — Full token/primitive reskin; TierDropdown a11y; all user-mgmt wiring + is_admin gate preserved; Status/Last-active/invite deferred.

## Decisions Made
- **TierBadge → Badge primitive via a status-ramp map:** the retired `TIER_STYLES` hex block was deleted; tiers now map basic→queued (neutral grey), pro→running (brand violet), enterprise→done (green) with the tier label passed explicitly. Badge exposes only the shared status-ramp keys, so tier color is carried by the token ramp rather than a per-page palette fork (D-15).
- **Pill for the role/count chips, token-classed button for Delete:** the Admin role chip keeps its Shield icon (which `Badge` cannot host) via `Pill`; the danger Delete button uses `bg-status-failed` tokens because `Button` only ships primary/secondary variants.
- **Modals keep motion.div + token panel classes:** the create/delete modal animation wrappers were retained and retokenized (`bg-surface-card`/`--elevation-modal`/`--scrim`) instead of nesting the `Card` component, preserving entrance animations while remaining fully tokenized. `Card` is used positively for the stat cards and the users-table wrapper.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. The RED test failed exactly on the intended assertion (TierDropdown `aria-haspopup="menu"` absent pre-reskin); the other four assertions (columns/pw-modal/gate/defer) passed pre-reskin as regression guards and stayed green.

## Known Stubs
None — no hardcoded empty data, placeholder text, or unwired components introduced. The deferred Status/Last-active columns and email-invite are intentionally NOT added (no backing AdminUser fields); they are additive-backend work for a future phase, not stubs.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave 2 is complete: all B1 pages (Account Settings, Template/DS pickers, Review-gates, Library, Login/Register, Admin) are converged on the Phase-32 token layer.
- No new dependencies, no backend/transport touch (INV-3/LOCK-B held); no new endpoint/column.
- A clean full mocked/live e2e pass/fail remains deferred to the Phase-34 live pass per the phase environment contract (offline webServer times out).

## Verification Evidence
- **Retired-palette grep == 0** on `admin/page.tsx` (`#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains`).
- **Stray-stock grep == 0** (`bg-[#`, `text-[#`, `#hex`, `bg/text-(blue|gray|slate|indigo|emerald|red)-`, `#E8EDF5`, `#F4F5F7`, `#111827`, `#1f2937`); file positively uses `Card`/`Badge`/`Button`/`Pill` (9 primitive usages) + `bg-surface-*`/`text-ink-*`/`border-line-*`/`--scrim`/`--elevation-*` tokens.
- **Wiring/gate greps** all present: `is_admin`, `adminUpdateTier`, `adminCreateUser`, `adminDeleteUser`, `workflow_run_count`, `created_at`, `type="password"`, `getMe`.
- **Defer guard:** no `last_active`/`display_name`/`invite`/`suspend`; the only `status` matches are the Badge `status` prop and `status-*` token utilities (no Status column).
- **Tests GREEN:** `npm run test -- admin.reskin` → 5 passed.
- **tsc identity:** `npx tsc --noEmit 2>&1 | grep -v mockApi.ts | grep -c error` == 0.
- **Plan verify command:** PASS.

## Self-Check: PASSED
- Both files verified present on disk.
- Both task commits verified in git log (d27a889f, 49a356e1).

---
*Phase: 35-shell-chrome-reskin-pages-b1*
*Completed: 2026-07-09*
