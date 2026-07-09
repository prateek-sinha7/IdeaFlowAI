---
phase: 35-shell-chrome-reskin-pages-b1
plan: 05
subsystem: ui
tags: [react, tailwind, tokens, tabs, card, pill, library, reskin, vitest]

# Dependency graph
requires:
  - phase: 35-01
    provides: "Phase-32 token layer + ui/* primitives (Tabs/Card/Pill/Button) landed on the shell"
  - phase: 32-01
    provides: "Canonical Hexaware token palette (brand/ink/surface/line + radius ladder) in globals.css"
provides:
  - "LibraryPage (Agents/Skills/Hooks catalog) fully reskinned onto Phase-32 tokens/primitives — retired-palette grep=0, stray-stock grep=0"
  - "Agents/Skills/Hooks tab bar migrated to the Tabs primitive (role=tab) with real catalog counts in the tab labels"
  - "Skill/Hook detail modals + agent/skill/hook cards tokenized; tag chips on the Pill primitive"
  - "Render test pinning the Tabs-role + tab-switch + real-search contract over local catalog data"
affects: [35-shell-chrome-reskin-pages-b1, 36-home-launch-grid, page reskin waves]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Top-level catalog tab bar keyed on the shared Tabs primitive (role=tab), count carried in the tab label string so real constant lengths surface through the accessible name"
    - "Filter/list rows as brand-fill active token chips (bg-brand-fill border-brand-border text-brand); tag chips as the Pill primitive"
    - "Retired-hex tint arrays replaced by token class-string tint cycles (bg-brand-fill/surface-warm + ink/brand text)"

key-files:
  created:
    - frontend/src/components/library/LibraryPage.reskin.test.tsx
  modified:
    - frontend/src/components/library/LibraryPage.tsx

key-decisions:
  - "Main tab bar counts ride in the Tabs label string (label:string primitive contract) rather than a separate badge — keeps the shared Tabs primitive unmodified while surfacing real ALL_AGENTS_COMBINED/SKILLS/HOOKS lengths"
  - "Sidebar category/event filters styled as brand-fill active token chips (kept as <button> for the existing setActiveCategory/setSkillCategory/setHookEvent wiring); the Pill primitive is used for skill/hook tag chips"
  - "Card entrance motion (per-item fade) dropped when swapping motion.div cards for the static Card primitive — decorative only, no wired behavior lost"

patterns-established:
  - "Reskin-only page migration: replace ad-hoc tab bar -> Tabs, cards -> Card, chips -> Pill, retired hex -> tokens, while preserving every real control over local data (D-15)"

requirements-completed: [B1-04]

# Metrics
duration: 10min
completed: 2026-07-09
---

# Phase 35 Plan 05: Library Page Reskin (Agents/Skills/Hooks) Summary

**LibraryPage migrated onto the Phase-32 token layer + Tabs/Card/Pill primitives — retired-palette grep=0, stray-stock grep=0, with the real local-data search/category filtering, catalog counts, and copy-to-clipboard detail modals preserved (no invented backend).**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-09T02:25:00Z
- **Completed:** 2026-07-09T02:31:00Z
- **Tasks:** 2 (1 TDD RED test + 1 reskin)
- **Files modified:** 2

## Accomplishments
- Agents/Skills/Hooks tab bar swapped from an ad-hoc `<button>` bar to the shared `Tabs` primitive (`role=tab`, `data-testid=tab-*`), counts carried in the tab labels so the real catalog lengths surface through the accessible name.
- Agent/skill/hook cards rebuilt on the `Card` primitive; skill/hook tag chips on the `Pill` primitive; sidebar category/event filters restyled as `bg-brand-fill border-brand-border` active token chips.
- The retired-hex `ICON_STYLES` avatar-tint array replaced with a token class-string tint cycle (`bg-brand-fill`/`bg-surface-warm`/`bg-surface-paper` + `text-brand`/`text-ink-*`).
- Both detail modals (Skill + Hook) fully tokenized — `bg-surface-white` panels, `border-line-*`, `text-ink-*`, `bg-brand-fill` icon tiles, `bg-ink-900` event badges — with markdown section parsing + copy-to-clipboard intact.
- Render test pins the Tabs-role, tab-switch, real-search-filter, and real-count contract so the page can never be downgraded to inert mock cards.

## Task Commits

Each task was committed atomically:

1. **Task 1: LibraryPage reskin render test (RED)** - `dfdc36f4` (test)
2. **Task 2: Reskin LibraryPage to Tabs/Card/Pill on local data (GREEN)** - `c7d5769a` (feat)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified
- `frontend/src/components/library/LibraryPage.reskin.test.tsx` - NEW render test: `role=tab` (Tabs), tab-switch swaps the visible catalog, search filters visible agents over local data, tab counts equal local constant lengths, no retired palette in class strings.
- `frontend/src/components/library/LibraryPage.tsx` - Reskinned onto tokens + Tabs/Card/Pill; all `#1B2A4A`/`gray-*`/raw-hex/`f5f5f0` retired; real controls preserved.

## Real controls wired vs decorative
- **Real (preserved over existing local constants, no new backend):** Agents/Skills/Hooks tab model; `LIBRARY_AGENTS`/`CUSTOM_AGENTS`/`SKILLS`/`HOOKS` catalog + counts; agent category filter (incl. the `migration` group set); skill category filter; hook event filter; the per-tab search box (already a real filter over name/description/role — retokenized, kept real); `SkillDetailModal` markdown parse + copy-to-clipboard; `HookDetailModal` copy; `AgentCapabilitiesModal` mount.
- **Decorative / out of scope (not invented):** no mock-fiction fields added (`dur`/`trigger` strings, `showAgentTint` editor toggle, agent drawer) — none existed as real data, so none were fabricated; no `fetch`/API call added (grep `fetch(|/api/` = 0).

## Verification
- `cd frontend && npm run test -- LibraryPage.reskin` → **5/5 passed** (RED first: `role=tab` + counts + palette failed pre-reskin; GREEN post-reskin).
- Retired-palette grep on `LibraryPage.tsx` (`#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains`) = **0**.
- Stray-stock grep (`bg-[#|text-[#|#hex|bg-(blue|gray|slate|indigo|emerald|red)-|text-(gray|slate|emerald|red)-|#111827|#1f2937`) = **0**.
- Positive primitive usage (`<Tabs|<Card|<Pill|font-sans`) = 14 matches.
- No new backend: `fetch(|/api/` grep = **0** (INV-3 / LOCK-B held, FE-only).
- `npx tsc --noEmit | grep -v mockApi.ts | grep -c error` = **0** (identity preserved).
- `eslint` on both files = clean.
- e2e delta **live-deferred** (offline mocked webServer times out; phase-wide contract).

## Decisions Made
- Counts ride in the `Tabs` label string because the primitive types `label: string` — this keeps the shared primitive unmodified while still exposing real catalog lengths through the accessible name (asserted by the test).
- Sidebar filters stay `<button>` elements (preserving `setActiveCategory`/`setSkillCategory`/`setHookEvent` wiring) but adopt the brand-fill active chip idiom; the `Pill` primitive is used for the skill/hook tag chips.
- Swapping `motion.div` cards for the static `Card` primitive drops the per-item entrance fade (decorative only) — no wired behavior lost (D-15).

## Deviations from Plan

None - plan executed exactly as written. Rules 1-3 not triggered.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Library (B1-04) fully tokenized; the Tabs-count-in-label + brand-fill-active-chip idioms are available for remaining B1 page reskins.
- SC-001/INV-1 held: the Library is keyed on generic catalog constants (agents/skills/hooks), never a workflow name; no transport/backend touched.

---
*Phase: 35-shell-chrome-reskin-pages-b1*
*Completed: 2026-07-09*
