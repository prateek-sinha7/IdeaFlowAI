---
phase: 35-shell-chrome-reskin-pages-b1
plan: 03
subsystem: ui
tags: [react, tailwind, tokens, reskin, template-picker, primitives, vitest, a11y]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign
    provides: "Canonical @theme token layer + ui primitives (Tabs/Card/Button/Pill/Badge)"
  - phase: 35-shell-chrome-reskin-pages-b1
    plan: 01
    provides: "Shell chrome on tokens + reskin-by-delta idiom + retired/stray grep==0 per-file gate + dark-surface white/opacity idiom"
provides:
  - "Template picker flow (gallery + detail modal + custom-template modal + card) fully reskinned onto Phase-32 tokens/primitives — no per-page palette fork (D-15), retired-palette grep=0, stray-stock grep=0 on all four files"
  - "Category tabs carry role=tab/role=tablist + aria-selected (AuditTab chip idiom, bg-brand-fill active) keyed on generic category strings, never a workflow name (SC-001)"
  - "Reskin-parity + a11y render test pinning real search filtering, category re-filter, blank-canvas onSelect(null), and detail-modal onSelect(id) so the picker can never be downgraded to the mock's inert cards (D-15)"
affects: [35-04, 35-05, 35-06, 35-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Template picker reskin = pure re-style: every wired path (query search, getBucket scenario->bucket, filtered/filteredCustom memos, has_preview gating, custom-upload + localStorage, onSelect + detail/custom modal mounts) preserved byte-for-byte; only markup/classes changed (D-15)"
    - "Dark modal (TemplateDetailModal) reskin = shell dark idiom: bg-surface-near-black/ink-black panels + white/opacity chrome (text-white/60, bg-white/5, border-white/10) + scrim var, mirroring the plan-01 AppHeader dark-surface pattern (light ui/* primitives don't map onto dark chrome)"
    - "Category tabs styled inline (scroll + count badge) but carry the Tabs primitive's a11y contract (role=tab/tablist + aria-selected) so the render test's role=tab assertion holds without losing horizontal scroll / Custom count badge"

key-files:
  created:
    - frontend/src/components/workflow/prototype/TemplateGallery.reskin.test.tsx
  modified:
    - frontend/src/components/workflow/prototype/TemplateGallery.tsx
    - frontend/src/components/workflow/prototype/TemplateDetailModal.tsx
    - frontend/src/components/workflow/prototype/CustomTemplateModal.tsx
    - frontend/src/components/workflow/prototype/TemplateCard.tsx

key-decisions:
  - "Category tabs kept as inline buttons (not the Tabs primitive) to preserve horizontal scroll + the Custom count badge, but given role=tab/role=tablist + aria-selected and the AuditTab chip idiom (bg-brand-fill active) — satisfies the render test's role=tab contract and a11y without a control rewrite (D-15)"
  - "TemplateDetailModal (a dark modal) reskinned on tokens only, NOT the light ui/* primitives: surface-near-black/ink-black panels + white/opacity chrome + scrim var mirror the plan-01 AppHeader dark idiom; the light Button/Pill would break the dark theme"
  - "CustomTemplateModal Fetch/Cancel/Confirm actions routed through the Button primitive (primary/secondary); file/URL feedback via the status ramp (status-done/status-failed); all upload + URL-fetch + saveCustomTemplate wiring preserved"
  - "TemplateCard platform chip routed through the Pill primitive; the IntersectionObserver lazy-preview + selected-badge logic untouched"
  - "Dropped the dead UploadCustomCard local component from TemplateGallery (unused, referenced nowhere) — dead-code cleanup within the touched file that also removed a block of stray stock palette at the source"

patterns-established:
  - "Pattern: a reskinned picker ships a *.reskin.test.tsx that stubs IntersectionObserver and asserts real search-filter + role=tab category re-filter + real onSelect (blank-canvas and via the detail modal) + a retired-palette guard on the rendered class strings — the picker's keep-richer-behaviour contract (D-15)"

requirements-completed: [B1-03]

# Metrics
duration: ~18m
completed: 2026-07-09
---

# Phase 35 Plan 03: Template Picker Flow Reskin (Wave 2) Summary

**The template-selection surface — `TemplateGallery.tsx` (the 505-line grid + category tabs + real search) and its three siblings `TemplateDetailModal.tsx`, `CustomTemplateModal.tsx`, `TemplateCard.tsx` — fully migrated onto the Phase-32 token layer and `ui/*` primitives (Button/Pill + role=tab category chips), with every wired behaviour preserved (real search, category filtering, custom HTML upload + localStorage, has_preview gating, detail modal, real onSelect), retired- and stray-stock-palette greps both 0 on all four files, and a new reskin-parity + a11y render test locking the keep-richer-behaviour contract (D-15).**

## Performance

- **Duration:** ~18 min
- **Completed:** 2026-07-09
- **Tasks:** 2
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments
- Reskinned `TemplateGallery.tsx` end-to-end onto tokens: `#1B2A4A`/`#0F1B33` navy → `bg-brand`/`bg-brand-pressed`/`text-brand`/`border-brand`; all `text-gray-*`/`bg-gray-*`/`bg-white`/`border-gray-*` → `text-ink-*`/`bg-surface-*`/`border-line-*`; the tab count badge → `bg-brand`; card gradients → `from-brand/5`/`from-line-faint-row`. Category tabs gained `role="tab"` + `role="tablist"` + `aria-selected` with the AuditTab chip idiom (`bg-brand-fill` active). The empty-state upload CTA now uses the `Button` primitive. Retired grep = 0, stray-stock grep = 0.
- Reskinned `TemplateDetailModal.tsx` (a dark preview modal) onto the shell dark idiom: `bg-[#111318]`/`#0d0f14`/`#0a0b0e` → `bg-surface-near-black`/`bg-surface-ink-black`; `bg-black/70` scrim → `bg-[var(--scrim)]`; `shadow-2xl` → `shadow-[var(--elevation-modal)]`; all `text-gray-*` → `text-white/60`/`/40`/`/50`; the emerald selected state → the `status-done` ramp; the navy Use-button → `bg-brand`. Icon buttons use `border-white/10 bg-white/5 text-white/60` (matching plan-01 AppHeader).
- Reskinned `CustomTemplateModal.tsx` (light) onto tokens + the `Button` primitive: the Fetch, Cancel, and Use-this-template actions are now `Button` (primary/secondary); backdrop → scrim var; panel → `bg-surface-white border-line-border shadow-[var(--elevation-modal)]`; file/URL success+error feedback → the `status-done`/`status-failed` ramp; the active file/url tab underline → `border-brand text-brand`. Every wired path preserved: file `FileReader` upload + 2 MB guard, the `/api/prototype/fetch-url` GET, `saveCustomTemplate` localStorage persistence, `onConfirm`/`onClose`.
- Reskinned `TemplateCard.tsx` onto tokens + the `Pill` primitive (platform chip); the `IntersectionObserver` lazy-preview iframe, selected badge, and hover hint are untouched.
- Authored `TemplateGallery.reskin.test.tsx` (5 tests) stubbing `IntersectionObserver` and asserting: (1) typing in the search box removes a non-matching template (real filter, not inert); (2) `getAllByRole("tab")` === 8 and clicking the Marketing tab re-filters the set; (3) clicking the blank-canvas card calls `onSelect(null)`; (4) clicking a built-in card opens the real detail modal and its "Use this template" calls `onSelect(id)`; (5) no `#1B2A4A`/`text-gray-`/`bg-gray-` in the rendered class strings.

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): pin template-picker search/filter/select + role=tab reskin contract** — `4b097a9b` (test)
2. **Task 1 (GREEN): reskin TemplateGallery grid/tabs/search onto Phase-32 tokens** — `78000708` (feat)
3. **Task 2: reskin template detail/custom/card modals onto Phase-32 tokens** — `6a9c3015` (feat)

**Plan metadata:** (this commit) `docs(35-03): complete template-picker reskin plan`

_TDD note: both plan tasks carry `tdd="true"`. The reskin test is a genuine RED gate — pre-reskin the category buttons have no `role=tab` and the markup still carries `#1B2A4A`/`text-gray-*`, so 2 of 5 assertions fail RED (the 3 wiring-parity assertions pass on the existing wiring). The Task-1 feat commit makes all 5 green; Task 2 keeps them green._

## Files Created/Modified
- `frontend/src/components/workflow/prototype/TemplateGallery.reskin.test.tsx` (created) — 5-test reskin-parity + a11y suite; stubs `IntersectionObserver`, uses real `PrototypeTemplate` fixtures.
- `frontend/src/components/workflow/prototype/TemplateGallery.tsx` (modified) — full token/primitive reskin; role=tab category tabs; `Button` empty-state CTA; dead `UploadCustomCard` removed; all search/filter/select/upload wiring preserved.
- `frontend/src/components/workflow/prototype/TemplateDetailModal.tsx` (modified) — dark-idiom token reskin; scrim var + elevation-modal; status-done selected state; all fullscreen/escape/open-in-tab/onSelect wiring preserved.
- `frontend/src/components/workflow/prototype/CustomTemplateModal.tsx` (modified) — light token reskin + `Button` primitive; status-ramp feedback; all file/URL upload + localStorage wiring preserved.
- `frontend/src/components/workflow/prototype/TemplateCard.tsx` (modified) — token reskin + `Pill` platform chip; lazy-preview logic untouched.

## Decisions Made
- **Category tabs stay inline buttons, not the `Tabs` primitive:** the tabs need horizontal scroll (`overflow-x-auto`) and a per-tab count badge (Custom), which the flex-row `Tabs` primitive doesn't accommodate. Instead they were given the primitive's a11y contract inline (`role=tab`/`role=tablist`/`aria-selected`) plus the AuditTab chip idiom (`bg-brand-fill` active). This satisfies the render test's `role=tab` assertion and keeps a11y without losing scroll/badge — a reuse-don't-rebuild call (D-15).
- **`TemplateDetailModal` reskinned on tokens only (dark idiom), not light primitives:** it's a full-bleed dark preview modal; routing it through the light `Button`/`Pill` (white/beige surfaces) would break the dark theme. It uses `surface-near-black`/`ink-black` + `white/opacity` chrome + the scrim var, mirroring the plan-01 `AppHeader` dark-surface pattern.
- **`CustomTemplateModal` + `TemplateCard` DO consume primitives:** the light custom-upload modal's actions are `Button` (primary/secondary) and the card's platform chip is `Pill`, per the plan's "primary/secondary buttons → Button; meta/category chips → Pill" directive.
- **Dropped the dead `UploadCustomCard`:** it was defined but referenced nowhere in the gallery — removing it is dead-code cleanup within the touched file that also eliminated a block of stray stock palette at the source.

## Deviations from Plan

None material. One documented reuse-don't-rebuild interpretation:
- **Category tabs:** the plan offered "the `Tabs` primitive OR the AuditTab chip idiom". Because the tabs require horizontal scroll + a Custom count badge, the chip idiom was chosen and the `role=tab` a11y contract applied inline. This is the plan's explicit alternative, not a deviation. Dropping the unused `UploadCustomCard` is dead-code cleanup within scope.

## Known Stubs

None introduced. All template data flows from the real `PrototypeTemplate[]` prop and localStorage-backed custom templates; no hardcoded/empty data was added. The picker is keyed on generic template data, never a workflow name (SC-001/INV-1), and no transport/backend was touched (INV-3/LOCK-B).

## Verification Evidence
- **Retired-palette grep == 0** on all four files (`#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains`): TemplateGallery 0, TemplateDetailModal 0, CustomTemplateModal 0, TemplateCard 0.
- **Stray-stock grep == 0** on all four files (`bg-[#|text-[#|#hex|bg/text-(blue|gray|slate|indigo|emerald|red|green|purple|amber)-|#111827|#1f2937`): all 0.
- **Positive token/primitive authority:** TemplateGallery 42 token-utility occurrences + `Button` import; CustomTemplateModal imports `Button`; TemplateCard imports `Pill`.
- **Wiring intact:** TemplateGallery still contains `onSelect` (19) and the `query` search path (8); custom-upload/localStorage and both modal mounts preserved; CustomTemplateModal keeps `/api/prototype/fetch-url` + `saveCustomTemplate`.
- **Behavior GREEN:** `npm run test -- TemplateGallery.reskin` → 5/5 passed; `npm run test -- prototype` → 2 files / 7 passed (no regression).
- **tsc identity:** `npx tsc --noEmit 2>&1 | grep -v mockApi.ts | grep -c error` → 0.
- **Lint:** `eslint` on the five files → 0 errors (3 pre-existing `set-state-in-effect` warnings on unchanged effect bodies — localStorage load + IntersectionObserver — out of scope).
- **e2e:** not run — mocked webServer times out offline; e2e delta is live-deferred at the phase level per the environment contract.

## Next Phase Readiness
- The template-selection surface is fully converged on tokens with its wiring pinned by a parity test; Wave 2 continues with 35-04..35-07 (Design-system picker, Review-gates, Library, Login/Register, Admin).
- No new dependencies; no backend/transport/Python touch (INV-3/LOCK-B held).

## Self-Check: PASSED
- All 5 files verified present on disk.
- All 3 task commits verified in git log (4b097a9b, 78000708, 6a9c3015).
