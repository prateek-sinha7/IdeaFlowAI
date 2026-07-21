---
phase: 35-shell-chrome-reskin-pages-b1
plan: 02
subsystem: ui
tags: [react, tailwind, tokens, settings, reskin, vitest, primitives]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign
    provides: "Canonical @theme token layer + ui primitives (Tabs/Card/Button/Badge)"
  - phase: 35-shell-chrome-reskin-pages-b1
    plan: 01
    provides: "Shell chrome on tokens + reskin-by-delta idiom + retired/stray grep==0 per-file gate"
provides:
  - "Account Settings surface fully reskinned onto Phase-32 tokens/primitives (Tabs/Card/Button/Badge) — no per-page palette fork (D-15), retired-palette grep=0, stray-stock grep=0"
  - "Section nav swapped to the Tabs primitive keyed on generic section ids (profile|model|limits|constitution), never a workflow name (SC-001)"
  - "Behavior-parity + fiction-guard render test pinning the four wired sections and the no-unbacked-fields boundary (INV-3)"
affects: [35-03, 35-04, 35-05, 35-06, 35-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Settings reskin = pure re-style: every endpoint call (getMe/getPreferences/getCapabilities/changePassword/updatePreferences/constitution fetch) preserved byte-for-byte; only markup/classes changed (D-15 reuse-don't-rebuild)"
    - "Token feedback banners keyed on a generic type ('success'->done ramp, 'error'->failed ramp) via a small helper, not stock emerald/red"
    - "Model/tier chips routed through the Badge primitive; unknown tiers normalize to neutral (no stock green/blue/purple)"
    - "Fiction guard as a test invariant: the render test asserts NO Full name/Role/Organization inputs exist, encoding the no-unbacked-field boundary (INV-3)"

key-files:
  created:
    - frontend/src/components/settings/AccountSettings.render.test.tsx
  modified:
    - frontend/src/components/settings/AccountSettings.tsx

key-decisions:
  - "Section nav restyled from a vertical stock-palette sidebar to the horizontal Tabs primitive (role=tablist, data-testid=tab-*) per plan; layout change is presentational only, section state machine unchanged"
  - "Model selection kept as the already-wired native <select> (retokenized) rather than rebuilt into chip 'radio cards' — reuse-don't-rebuild (D-15) preserves the updatePreferences wiring and keeps the control accessible/testable; the AuditTab chip-select idiom informed the token palette, not a control rewrite"
  - "Dropped the unused TIER_DETAILS palette fields (price/color/bgColor/borderColor) — dead code in the touched file; only the consumed .description survives as TIER_DESCRIPTION"
  - "Tier + model chips use the Badge primitive (status-keyed token colors) instead of bespoke inline navy/stock chips, per the plan's Badge directive"

patterns-established:
  - "Pattern: a reskinned settings/CRUD surface ships a *.render.test.tsx that mocks @/lib/api and asserts every existing loader/mutation still fires + a fiction guard for unbacked fields — the reskin's parity contract"

requirements-completed: [B1-02]

# Metrics
duration: ~5m
completed: 2026-07-09
---

# Phase 35 Plan 02: Account Settings Reskin (Wave 2) Summary

**`AccountSettings.tsx` (the heaviest single file, 21 retired-palette lines) fully migrated onto the Phase-32 token layer and `ui/*` primitives (Tabs/Card/Button/Badge) — every one of the four already-wired sections (email/password, AI model, limits, constitution) preserved unchanged, no unbacked fields added, retired- and stray-stock-palette greps both 0, and a new behavior-parity + fiction-guard render test locking the wiring contract.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-07-08T23:46:01Z
- **Completed:** 2026-07-08T23:51:00Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- Reskinned `AccountSettings.tsx` end-to-end onto Phase-32 tokens: `#f5f5f0`/`bg-white`/`gray-*`/`#1B2A4A`/`#E8EDF5`/`#F4F7FC` and all stock emerald/red/green/blue/purple/amber classes replaced with `text-ink-*` / `bg-surface-*` / `border-line-*` / `text-brand`/`bg-brand`/`bg-brand-fill` / status-ramp tokens. Retired-palette grep = 0, stray-stock grep = 0.
- Swapped the section nav from a vertical stock-palette sidebar to the shared `Tabs` primitive (`role=tablist`, `data-testid=tab-profile|model|limits|constitution`), keyed on generic section ids (SC-001), and moved all ad-hoc panels to `Card`, all actions to `Button`, and tier/model chips to `Badge`.
- Preserved ALL FOUR wired sections and every behavior (D-15 reuse-don't-rebuild): `getMe`/`getPreferences`/`getCapabilities` loaders, the `changePassword` password form with its pw≥8 client validation, the `updatePreferences` model save (`pendingModel`/`handleSaveModel`), and the constitution `fetch('/api/settings/constitution')` GET/PUT/DELETE. No endpoint call was touched.
- Held the fiction boundary (INV-3): NO Full name / Role / Organization inputs added, email stays a read-only display, and the hardcoded usage-limit numbers were left verbatim (no usage API — no new backend).
- Authored `AccountSettings.render.test.tsx` (5 tests) mocking `@/lib/api` + stubbing the constitution `fetch`, asserting the loaders fire, the password form calls `changePassword`, the model save calls `updatePreferences`, the constitution section reads `/api/settings/constitution`, and the fiction guard (no unbacked inputs, email non-editable). Nav is queried role-agnostically so the same test proved parity BEFORE and AFTER the reskin.

## Task Commits

Each task was committed atomically:

1. **Task 1: AccountSettings behavior-parity + fiction-guard render test (RED/GREEN scaffold)** — `9181ec5b` (test)
2. **Task 2: Reskin AccountSettings to tokens/primitives, preserve all wiring** — `d8d97696` (feat)

**Plan metadata:** (this commit) `docs(35-02): complete account-settings reskin plan`

_TDD note: both tasks carry `tdd="true"`. Because the wiring already exists (this is a reskin, not a static→real build), the parity assertions PASS on the pre-reskin component — Task 1 is the `test(...)` RED-gate commit that encodes the contract, Task 2 is the `feat(...)` GREEN-gate commit that keeps it green through the reskin._

## Files Created/Modified
- `frontend/src/components/settings/AccountSettings.render.test.tsx` (created) — 5-test behavior-parity + fiction-guard suite; mocks `@/lib/api`, stubs the constitution `fetch`, role-agnostic nav queries.
- `frontend/src/components/settings/AccountSettings.tsx` (modified) — full token/primitive reskin; all wiring preserved; unused `TIER_DETAILS` palette fields dropped (kept `.description` as `TIER_DESCRIPTION`).

## Decisions Made
- **Model control kept as the wired `<select>` (retokenized), not rebuilt into chip "radio cards":** the plan's language referenced chip "radio cards", but the live control is a native `<select>` already wired to `updatePreferences` via `pendingModel`/`handleSaveModel`. Rebuilding it into a chip grid would risk the mutation wiring and accessibility for zero product gain. Per D-15 (reuse-don't-rebuild) the select was retokenized in place; the AuditTab chip-select idiom informed the token palette (`bg-brand-fill`/`border-brand-border` for active-brand accents), not a control rewrite. The tier chips DO use the Badge primitive as directed.
- **Section nav → horizontal `Tabs` primitive:** the plan directed replacing the section tab bar with the `Tabs` primitive; the original was a vertical sidebar, so the reskin moves it to the horizontal underline-tab idiom. Presentational only — the `section` state machine and all four panels are unchanged.
- **Tier/model chips via `Badge`:** adopted the shared status-chip primitive (status-keyed token colors) instead of bespoke inline navy/stock chips, per the plan's Badge directive. Tier chips pass `label` so the tier name renders while the color routes through a token ramp.
- **Dropped unused `TIER_DETAILS` palette fields:** `price`/`color`/`bgColor`/`borderColor` were never referenced (only `.description` was), so the map was slimmed to `TIER_DESCRIPTION` — dead-code cleanup within the touched file that also removes 6 of the retired-palette lines at the source.

## Deviations from Plan

None material. One documented reuse-don't-rebuild interpretation:
- **Task 2 model control:** the plan said "Model-selection radio cards → AuditTab chip-select idiom", but the current control is a native `<select>`, not radio cards. Following D-15 (reuse-don't-rebuild) and the hard guardrail "preserve every wired behavior; do NOT rebuild", the `<select>` was retokenized in place rather than converted to a chip grid. All model-save wiring (`updatePreferences`) is preserved and the parity test asserts it still fires. This is a scope-preserving choice, not a functional deviation.

## Known Stubs

None introduced. The hardcoded usage-limit numbers (Pipeline runs/month, Concurrent pipelines, etc.) are pre-existing static content with no backing endpoint; the plan explicitly directed leaving them as-is (INV-3, no new backend). These predate this plan and are intentional per the plan's fiction boundary — not a stub introduced here.

## Verification Evidence
- **Retired-palette grep == 0:** `grep -rEnc '#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains' AccountSettings.tsx` → 0.
- **Stray-stock grep == 0:** `grep -rEnc 'bg-\[#|text-\[#|#[0-9A-Fa-f]{6}|bg-(blue|gray|slate|indigo|emerald|red)-|text-(gray|slate|emerald|red|green|blue|purple|amber)-|#111827|#1f2937' AccountSettings.tsx` → 0; `font-serif` → 0.
- **Positive token authority:** 72 occurrences of `text-ink-`/`bg-surface-`/`border-line-`; imports `Tabs`/`Card`/`Button`/`Badge`.
- **Wiring intact:** file still contains `getPreferences`, `updatePreferences`, `changePassword`, and `/api/settings/constitution` (7 matches on the combined pattern).
- **Fiction guard:** no `<input>` labelled name/role/organization; email rendered as a `<span>` display (test asserts `queryByDisplayValue` is null).
- **Behavior GREEN:** `npm run test -- AccountSettings.render` → 5/5 passed (same suite green pre- and post-reskin).
- **tsc identity:** `npx tsc --noEmit 2>&1 | grep -v mockApi.ts | grep -c error` → 0.
- **Lint:** `eslint` on both touched files → 0 errors (3 pre-existing `set-state-in-effect` warnings on unchanged effect code, out of scope).
- **e2e:** not run — mocked webServer times out offline; e2e delta is live-deferred at the phase level per the environment contract.

## Next Phase Readiness
- Account Settings is fully converged on tokens with its wiring pinned by a parity test; Wave 2 continues with 35-03..35-07 (Template/DS pickers, Review-gates, Library, Login/Register, Admin).
- No new dependencies; no backend/transport/Python touch (INV-3/LOCK-B held).

## Self-Check: PASSED
- Both files verified present on disk.
- Both task commits verified in git log (9181ec5b, d8d97696).
