---
phase: 35-shell-chrome-reskin-pages-b1
plan: 06
subsystem: ui
tags: [react, tailwind, tokens, auth, login, reskin, vitest, a11y]

# Dependency graph
requires:
  - phase: 35-shell-chrome-reskin-pages-b1
    provides: "Dark near-black shell idiom (35-01) + Phase-32 @theme token layer + Button primitive"
provides:
  - "Two-column login on Phase-32 tokens: NEW ~46% dark brand panel (bg-surface-near-black + Manrope wordmark + brand dot) on the left, fully-wired form on the right"
  - "Preserved auth wiring: login() -> redirect-by-is_admin (admin->/admin else->/dashboard), 401->'Invalid email or password', generic ApiError handling, loading disable, invite-only footer"
  - "Identity traps DROPPED (no SSO button, no Forgot link — no backend); e2e selectors preserved (#email/#password, submit 'Sign in', heading 'Welcome back')"
  - "Register tokenized (single #f5f5f0 -> bg-surface-paper) and confirmed as an unchanged redirect-to-/login stub"
  - "login.reskin render test as the reskin + selector-preservation + no-traps contract"
affects: [35-07, 34-live-pass]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Auth page = two-column split: ~46% bg-surface-near-black brand panel (mirrors the 35-01 shell idiom) + form column on bg-surface-paper"
    - "Submit routes through the Button primitive (variant=primary, type=submit) rather than a bespoke navy motion.button"
    - "Text input focus = .input-focus util on the wrapper (brand ring) + focus:border-brand on the input — replaces the #1B2A4A ring literal"
    - "Reskin render test stubs next/navigation + @/lib/api + motion/react (class declared INSIDE the vi.mock factory to survive hoisting)"

key-files:
  created:
    - frontend/src/app/login/login.reskin.test.tsx
  modified:
    - frontend/src/app/login/page.tsx
    - frontend/src/app/register/page.tsx

key-decisions:
  - "Brand-panel decoration tags are 'Audit trail / Role-based access / Invitation-only' — deliberately NOT 'SSO & SCIM' (the plan action floated SSO/SCIM tags, but its own acceptance grep and the phase guardrail mandate grep -Eic 'SSO|forgot' == 0). Chose generic value props with zero identity-trap words."
  - "Submit uses the Button primitive with className='w-full py-3 text-[13px]' for full-width; the whileHover/whileTap micro-interaction was dropped since Button is a plain button (accessible name 'Sign in' preserved)."
  - "Error box adopts the canonical status-failed idiom (text-status-failed + bg-[var(--status-failed-fill)] + border-[var(--status-failed-border)]) shared by Badge/AuditTab/AccountSettings, replacing the red-50/red-200/red-700 stock palette."
  - "Brand panel is hidden lg:flex (mobile shows the form full-width); the element still renders in the DOM (jsdom ignores CSS) so the render-test testid assertion holds."

patterns-established:
  - "Pattern: split-screen auth page — dark brand panel + token-reskinned form, all wiring + e2e selectors preserved, identity traps omitted where no backend exists (ND-12)"

requirements-completed: [B1-05, B1-06]

# Metrics
duration: ~12min
completed: 2026-07-09
---

# Phase 35 Plan 06: Login Reskin + Dark Brand Panel + Register Tokenize Summary

**Two-column login on Phase-32 tokens — a NEW ~46% dark near-black brand panel (Manrope wordmark + brand dot) beside the fully-wired form, with login() -> redirect-by-is_admin, all e2e selectors, and the invite-only footer preserved; SSO/Forgot traps dropped; register tokenized and confirmed a redirect stub.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-09T02:34:00Z (approx)
- **Completed:** 2026-07-09T02:38:00Z
- **Tasks:** 2 (TDD: RED test + GREEN reskin)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- Restructured `login/page.tsx` from a centered single card into a two-column split: a ~46% `bg-surface-near-black` brand panel (brand-dot logo + Manrope `VelocityAI` wordmark + eyebrow/headline/subhead + static value-prop tags) on the left, the form on the right — reskin + restructure per ND-12/D-15.
- Migrated every retired literal to Phase-32 tokens: page bg `#f5f5f0` -> `bg-surface-paper`; eyebrow `var(--font-inter)` + H1 `var(--font-fraunces)` -> `font-sans`; input `#1B2A4A` focus ring -> `.input-focus` util + `focus:border-brand`; submit `bg-[#1B2A4A]` -> the `Button` primitive; card `bg-white/border-gray-200` -> `bg-surface-card/border-line-control`; error box `red-*` -> the `status-failed` idiom.
- Preserved all wiring and selectors: `login()` -> `router.push(is_admin ? "/admin" : "/dashboard")`, 401 -> "Invalid email or password", generic ApiError fallbacks, loading disable, invite-only footer; `#email`, `#password`, submit name "Sign in", heading "Welcome back".
- Dropped the identity traps (no SSO button, no Forgot link) — no backend exists for them; `grep -Eic 'SSO|forgot'` == 0.
- Tokenized `register/page.tsx` (single `#f5f5f0` -> `bg-surface-paper`, `text-gray-500` -> `text-ink-500`) and confirmed the `useEffect(router.replace("/login"))` redirect stub + "Redirecting…" unchanged (B1-06).

## Task Commits

Each task was committed atomically:

1. **Task 1: Write login reskin render test (RED)** — `7fd25498` (test)
2. **Task 2: Reskin login two-column + dark brand panel; tokenize register (GREEN)** — `c7de8866` (feat)

**Plan metadata:** (this commit) `docs(35-06): complete login reskin plan`

_Note: This plan carried `type=tdd` tasks. Task 1 is the RED gate (`test(...)`; brand-panel assertion fails against the pre-reskin page while the 4 selector/no-trap guards pass by delta). Task 2 is the GREEN gate (`feat(...)`; all 5 assertions pass after the reskin)._

## Files Created/Modified
- `frontend/src/app/login/login.reskin.test.tsx` (created) — 5 render assertions: `#email`/`#password` present, submit name "Sign in", heading "Welcome back", dark brand panel (`login-brand-panel` testid carries `bg-surface-near-black` + "VelocityAI"), and no SSO/Forgot affordances.
- `frontend/src/app/login/page.tsx` (modified) — two-column split with dark brand panel; full token migration; wiring + selectors preserved; traps dropped.
- `frontend/src/app/register/page.tsx` (modified) — `#f5f5f0` + `text-gray-500` tokenized; redirect stub behavior unchanged.

## Decisions Made
- **Brand-panel tags avoid identity-trap words:** the plan action text floated static "SSO & SCIM" decoration tags, but its own acceptance criterion and the phase guardrail both require `grep -Eic 'SSO|forgot' == 0`. Resolved the internal tension in favor of the hard gate — the panel shows "Audit trail / Role-based access / Invitation-only" (generic value props, zero wiring, zero trap words).
- **Submit -> Button primitive:** dropped the bespoke `bg-[#1B2A4A]` motion.button and its whileHover/whileTap micro-interaction for the shared `Button variant="primary" type="submit"` (D-15 shared idiom); accessible name "Sign in" preserved verbatim.
- **Error box -> status-failed idiom:** adopted the repo-canonical `text-status-failed` + `bg-[var(--status-failed-fill)]` + `border-[var(--status-failed-border)]` used by Badge/AuditTab/AccountSettings instead of the retired `red-50/red-200/red-700` stock palette.

## Deviations from Plan

None requiring a rule — plan executed as written. One documented reconciliation (not a code deviation): the plan action's "SSO & SCIM static tags" suggestion was overridden by its own acceptance grep + the phase guardrail (`SSO|forgot` == 0); the brand panel uses non-trap value-prop tags. No backend, no new route, no transport touched (INV-3 / LOCK-B held).

The guardrail text mentioned preserving a "password-CREATE (first-login set-password) flow"; the actual `login/page.tsx` has no such flow (it is a plain wired login form), so there was nothing of that kind to preserve — all existing wiring that IS present was preserved verbatim.

## Issues Encountered
- **vi.mock hoisting:** the first test draft declared `class ApiError` at module scope and referenced it in the `vi.mock("@/lib/api")` factory — vitest hoists the factory above the class, throwing `Cannot access 'ApiError' before initialization`. Fixed by declaring the class INSIDE the factory. RED then ran cleanly (4 pass / 1 fail).

## Verification Evidence
- **Retired-palette grep == 0** on both `login/page.tsx` and `register/page.tsx` (`#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains`, incl. the `var(--font-*)` removals).
- **Stray-stock grep == nothing** on `login/page.tsx` + `register/page.tsx` (`bg-[#`, `text-[#`, `#hex`, `bg/text-(blue|gray|slate|indigo|emerald|red)-`, `#243456`, `#111827`, `#1f2937`). Login positively contains `bg-surface-near-black` and uses `Button`.
- **Traps dropped:** `grep -Eic 'SSO|forgot' login/page.tsx` == 0.
- **Selectors preserved:** login still contains `id="email"`, `id="password"`, `Sign in`, `Welcome back`, `is_admin`; register still contains `router.replace("/login")`.
- **Behavior GREEN:** `npm run test -- login.reskin` = 5/5 pass. **tsc identity:** `npx tsc --noEmit | grep -v mockApi.ts | grep -c error` == 0.
- **e2e (mocked `ts-a.auth.spec.ts`) live-deferred** per the phase environment contract (offline webServer times out); selectors preserved by construction so the auth spec is a no-new-fail by delta.

## Next Phase Readiness
- Auth pages fully token-migrated; 35-07 (Admin reskin) is the last Wave-2 plan.
- No new dependencies, no backend/transport touch; the mocked auth-spec delta verification is deferred to the Phase-34 live pass.

## Self-Check: PASSED

---
*Phase: 35-shell-chrome-reskin-pages-b1*
*Completed: 2026-07-09*
