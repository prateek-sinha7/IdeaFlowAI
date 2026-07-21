---
phase: 32-run-screen-redesign-a4
plan: 02
subsystem: ui
tags: [react, primitives, design-tokens, tailwind-v4, vitest, tdd, run-screen]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4 (plan 01)
    provides: canonical token layer (@theme inline brand/ink/surface/line/status ramp + :root radius ladder)
provides:
  - Token-consuming primitive library in frontend/src/components/ui/ — Button, Card, Tabs, Badge, Pill
  - Generic presentational variant/status API (no workflow name) that Wave-2/3 consumers reskin onto
  - vitest primitives suite (28 tests) asserting render + variant + token-class + no-retired-hex for all five
affects: [run-subtree-consumers (plans 06/07/08/09), phase-34, phase-35]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-file variant/status token-class map object (VARIANT_CLASS / STATUS_CLASS) — mirrors the AGENT_ACCENT idiom but keyed on token classes, never raw hex"
    - "className composition via array.filter(Boolean).join(' ') template idiom (from AgentProgressPanel)"
    - "Radius ladder + status fill/border ramp vars live in :root (not @theme) so primitives consume them via arbitrary var() utilities: rounded-[var(--radius-button)], bg-[var(--status-running-fill)]"
    - "Badge status normalizer (completed->done, unknown->neutral) mirrors WaveTreePanel.statusKind()"

key-files:
  created:
    - frontend/src/components/ui/Button.tsx
    - frontend/src/components/ui/Card.tsx
    - frontend/src/components/ui/Pill.tsx
    - frontend/src/components/ui/Tabs.tsx
    - frontend/src/components/ui/Badge.tsx
    - frontend/src/components/ui/__tests__/primitives.test.tsx
  modified: []

key-decisions:
  - "Button size prop kept (sm/md) as a generic presentational extension; primary is the default variant"
  - "Badge status keys map cancelled->status-amber and queued->status-queued per the §B3 ramp; completed/success normalize to done, unknown falls back to queued (neutral-grey) with no throw"
  - "Radius + status fill/border consumed via arbitrary var() utilities since plan-01 placed those tokens in :root only (not @theme inline) — keeps a single source of truth, no value duplication"

patterns-established:
  - "Token-derived primitive: every value resolves to a plan-01 token class or var(), zero raw palette hex (SC-1, D-15)"
  - "Generic variant/status API keyed on presentational props, never a workflow name (SC-001)"

requirements-completed: [SC-1]

# Metrics
duration: ~8min
completed: 2026-07-08
---

# Phase 32 Plan 02: Run-Screen Primitive Library Summary

**Net-new token-consuming primitive set (Button/Card/Tabs/Badge/Pill) landed in `frontend/src/components/ui/` — every value resolves to a plan-01 token class or `var()` (brand/ink/surface/line/status ramp + radius ladder), the variant/status API is generic (no workflow name), and a 28-test vitest suite proves render + variant + token-class + zero-retired-hex for all five.**

## Performance
- **Duration:** ~8 min
- **Tasks:** 2 (both `tdd="true"`, RED->GREEN)
- **Files created:** 6 (5 primitives + 1 test suite); 0 modified.

## Accomplishments
- **Button** — generic `primary`/`secondary` variant map: primary = `bg-brand`/white; secondary = `bg-surface-card`/`border-line-control`/`text-ink-900`. radius10 (`rounded-[var(--radius-button)]`), Manrope 600, 12.5px. Passes through `onClick`/`disabled`/`data-testid`/`className`.
- **Card** — `bg-surface-card` surface, `border-line-border`, radius14 (`rounded-[var(--radius-card)]`), forwards `className`+children.
- **Pill** — radius999 (`rounded-[var(--radius-pill)]`), `border-line-control`, `bg-surface-white`, forwards children.
- **Tabs** — underline idiom: active = `text-ink-900` + 2px `border-brand` underline; inactive = `text-ink-400`; `onChange(id)`; `role="tab"`/`aria-selected`/`data-testid` per tab.
- **Badge** — canonical status model -> status-ramp token classes (running/done/failed/cancelled/queued); `completed`->`done` normalize; unknown -> neutral-grey with no throw; radius5 (`rounded-[var(--radius-tag)]`), Manrope 600, 8.5px.
- **primitives.test.tsx** — 28 tests across all five primitives; each includes a "no retired palette hex in rendered output" guard.

## Task Commits
1. **Task 1 RED:** `1f7d3f97` (test) — failing Button/Card/Pill tests
2. **Task 1 GREEN:** `488f7ea4` (feat) — Button/Card/Pill primitives
3. **Task 2 RED:** `431b1ef1` (test) — failing Tabs/Badge tests
4. **Task 2 GREEN:** `1106553d` (feat) — Tabs + Badge primitives

## Files Created
- `frontend/src/components/ui/Button.tsx`
- `frontend/src/components/ui/Card.tsx`
- `frontend/src/components/ui/Pill.tsx`
- `frontend/src/components/ui/Tabs.tsx`
- `frontend/src/components/ui/Badge.tsx`
- `frontend/src/components/ui/__tests__/primitives.test.tsx`

## Verification Observed
- `npx vitest run src/components/ui/__tests__/primitives.test.tsx` — **1 file / 28 tests passed**.
- `npx tsc --noEmit | grep -v mockApi.ts | grep -c "error TS"` — **0** (identity; baseline 0 preserved).
- `grep -rniE "#1B2A4A|#2563eb"` across all five primitive sources — **0 hits** (no retired palette).
- TDD gates: each task shows a `test(...)` RED commit followed by a `feat(...)` GREEN commit; RED runs observed failing (import error — components absent) before GREEN.

## Decisions Made
- Kept a generic `size` prop on Button (`sm`/`md`) and defaulted `variant` to `primary` — presentational extensions, not workflow-coupled.
- Badge normalizer mirrors `WaveTreePanel.statusKind()`: `completed`/`success`->`done`, `error`->`failed`, `pending`->`queued`, unknown->`queued` (neutral-grey, never throws).
- Radius + status fill/border consumed via arbitrary `var()` utilities because plan-01 placed those tokens in `:root` only (not `@theme inline`), avoiding value duplication.

## Deviations from Plan
None — plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None — pure presentational client components; no package install, no external service, no new trust boundary (plan threat model: all dispositions `accept`).

## Known Stubs
None — every primitive renders live from its props; no hardcoded empty data source.

## Threat Flags
None — no new network endpoint, auth path, file access, or schema; no `dangerouslySetInnerHTML`/eval. Consistent with the plan's STRIDE register (T-32-02-T / T-32-02-I both `accept`).

## Next Phase Readiness
- The primitive vocabulary is available for Wave-2/3 run-subtree consumers (plans 06/07/08/09) to reskin onto — the reskin now routes through tokens, not new hardcoded palette.
- No blockers.

## Self-Check: PASSED

All 6 files exist on disk; all 4 task commits (`1f7d3f97`, `488f7ea4`, `431b1ef1`, `1106553d`) present in git log.

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*
