---
phase: 35-shell-chrome-reskin-pages-b1
plan: 04
subsystem: ui
tags: [react, tailwind, tokens, reskin, design-system-picker, review-gates, primitives, vitest, a11y]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign
    provides: "Canonical @theme token layer + ui primitives (Card/Button/Pill/Badge)"
  - phase: 35-shell-chrome-reskin-pages-b1
    plan: 01
    provides: "Shell chrome on tokens + reskin-by-delta idiom + retired/stray grep==0 per-file gate + dark-surface white/opacity idiom"
  - phase: 35-shell-chrome-reskin-pages-b1
    plan: 03
    provides: "Template-picker reskin idioms (Card/Button/Pill chip cloud, dark-modal white/opacity chrome, *.reskin.test.tsx parity harness)"
provides:
  - "Design-system picker flow (grid + detail modal + custom-DS modal) + the Review-gates section fully reskinned onto Phase-32 tokens/primitives — retired-palette grep=0 and stray-stock grep=0 on all four files, no per-page palette fork (D-15)"
  - "LOCK-F enforced: the DS picker renders the REAL count from `systems.length` (~14 live; proven with a 14-entry fixture) — never a fabricated 150; no catalog expansion"
  - "Review-gates `onChange(gateAgentIds, touched)` contract + `aria-expanded`/`sr-only` a11y byte-preserved (classNames-only reskin, INV-3/Q3) — existing test delta = 0"
  - "DesignSystemPicker.reskin.test.tsx pinning real count-from-prop, real search filter, real onSelect via the detail modal, and a grep-clean guard"
affects: [35-05, 35-06, 35-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DS picker reskin = pure re-style: every wired path (query search, allCategories grouping, filtered/filteredCustom memos, custom-DS create/edit/delete + localStorage, DesignSystemDetailModal mount, onSelect/onSelectCustom) preserved byte-for-byte; only markup/classes changed (D-15)"
    - "DesignSystemDetailModal (dark) reskin = shell dark idiom mirroring 35-03 TemplateDetailModal: bg-surface-near-black/ink-black panels + white/opacity chrome (text-white/60, bg-white/5, border-white/10) + scrim var + status-done selected/badge + bg-brand Use-button; the light iframe stage stays on ink/line tokens"
    - "Review-gates reskin = classNames only: the onChange effect, Human_Gate seeding, agentsKey re-seed, toggle, aria-expanded disclosure and sr-only checkbox are untouched — the D-15 keep-behaviour reskin discipline"
    - "Placeholder DESIGN.md example de-branded (Inter/JetBrains font names + raw fenced hexes -> generic families + <...-hex> tokens) so the fenced-hex / retired-font gate passes on data content, not just classNames"

key-files:
  created:
    - frontend/src/components/workflow/prototype/DesignSystemPicker.reskin.test.tsx
  modified:
    - frontend/src/components/workflow/prototype/DesignSystemPicker.tsx
    - frontend/src/components/workflow/prototype/DesignSystemDetailModal.tsx
    - frontend/src/components/workflow/prototype/CustomDesignSystemModal.tsx
    - frontend/src/components/workflow/ReviewGatesSection.tsx

key-decisions:
  - "DS category tabs kept as inline scrollable buttons (not the Tabs primitive) but given role=tab/role=tablist + aria-selected + the AuditTab chip idiom (bg-surface-warm active), preserving horizontal scroll + the Custom count badge (D-15 reuse-don't-rebuild, mirroring 35-03)"
  - "DesignSystemDetailModal reskinned on tokens only (dark idiom), NOT the light ui/* primitives: routing a full-bleed dark preview modal through light Button/Pill would break the theme; it uses surface-near-black/ink-black + white/opacity + scrim var like 35-03 TemplateDetailModal"
  - "CustomDesignSystemModal Cancel/Save routed through the Button primitive (secondary/primary); the format-tip box -> brand-fill/brand-border, errors -> the status-failed ramp"
  - "Review-gates 'default' chip routed through the Pill primitive with a brand-fill tint override — consumes a ui/* primitive while keeping the brand accent that flags a default-gated agent"
  - "The reskin test stubs a minimal in-memory localStorage so the real detail-modal select path (getToken -> open -> 'Use this system' -> onSelect(id)) runs in jsdom without throwing — an environment shim, not a behaviour change"

patterns-established:
  - "Pattern: a reskinned data-driven picker ships a *.reskin.test.tsx that renders a REAL-sized fixture and asserts the visible count follows the prop length (LOCK-F anti-inflation guard), plus real search-filter + real onSelect + a retired/stray-palette guard on the rendered class strings"

requirements-completed: [B1-03]

# Metrics
duration: ~22m
completed: 2026-07-09
---

# Phase 35 Plan 04: Design-System Picker Flow + Review-Gates Reskin (Wave 2) Summary

**The design-system selection surface — `DesignSystemPicker.tsx` (the grouped chip grid + category tabs + real search), its two siblings `DesignSystemDetailModal.tsx` (dark split-panel preview) and `CustomDesignSystemModal.tsx` (light DESIGN.md create/edit), plus the `ReviewGatesSection.tsx` disclosure — fully migrated onto the Phase-32 token layer and `ui/*` primitives (Card/Button/Pill), with every wired behaviour preserved (real search + category grouping, custom-DS CRUD + localStorage, the real detail modal, real onSelect/onSelectCustom, and the gate `onChange(gateAgentIds, touched)` contract byte-for-byte), retired- and stray-stock-palette greps both 0 on all four files, LOCK-F enforced (the picker count follows `systems.length`, never a fabricated 150), and a new reskin-parity test locking count-from-prop + real search + real select.**

## Performance

- **Duration:** ~22 min
- **Completed:** 2026-07-09
- **Tasks:** 3
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments
- Reskinned `DesignSystemPicker.tsx` end-to-end onto tokens: panel -> `Card`; navy `#1B2A4A` -> `bg-brand`/`text-brand`/`border-brand` (active chips) + `bg-brand-fill border-brand-border` (selected badge); all `gray-*`/`bg-white` -> `ink-*`/`surface-*`/`line-*`; category tabs gained `role="tab"`/`role="tablist"` + `aria-selected` (AuditTab chip idiom, `bg-surface-warm` active); the empty-state CTA now uses the `Button` primitive; headings `font-sans`. **LOCK-F:** the footer/group counts derive from `systems.length` / `totalVisible` — a 14-entry fixture renders "14 design systems"; there is no fabricated 150 anywhere. Retired grep = 0, stray-stock grep = 0.
- Reskinned `DesignSystemDetailModal.tsx` (dark split-panel) onto the shell dark idiom mirroring 35-03: `bg-[#111318]`/`#0d0f14` -> `bg-surface-near-black`/`bg-surface-ink-black`; `bg-black/70` scrim -> `bg-[var(--scrim)]`; `shadow-2xl` -> `shadow-[var(--elevation-modal)]`; all `text-gray-*` -> `text-white/60`/`/50`/`/40`/`/70`; the emerald selected state + components badge -> the `status-done` ramp; the navy Use-button -> `bg-brand hover:bg-brand-pressed`; icon buttons -> `border-white/10 bg-white/5 text-white/60`; the light iframe preview stage stays on `surface-white`/`ink`/`line` tokens. Every fetch/escape/fullscreen/open-tab/onSelect path preserved.
- Reskinned `CustomDesignSystemModal.tsx` (light) onto tokens + the `Button` primitive: scrim var + `Card`-style panel (`bg-surface-white border-line-border shadow-[var(--elevation-modal)]`); Cancel/Save -> `Button` (secondary/primary); required marks + error box -> the `status-failed` ramp; format-tip -> `brand-fill`/`brand-border`. The `PLACEHOLDER` example DESIGN.md was de-branded (`Inter`/`Georgia`/`JetBrains Mono` -> generic families; raw fenced hexes -> `<...-hex>` tokens) so the retired-font + fenced-hex gates pass on data content too. All name/body validation + `onSave`/`onClose` wiring preserved.
- Reskinned `ReviewGatesSection.tsx` **classNames only**: navy `#1B2A4A` -> `brand`; `#F1F4FB` hover -> `bg-brand-fill`; `gray-*` -> `ink-*`/`surface-*`/`line-*`; checkbox active -> `border-brand bg-brand`; the "default" chip -> the `Pill` primitive (brand-fill tint); heading `font-sans`. The load-bearing logic is byte-preserved: the `onChange(ordered, touched)` effect, `gate === "Human_Gate"` default seeding, `initialGateIds` seeding, `agentsKey` re-seed, `toggle` (`setTouched(true)`), the `aria-expanded` disclosure, and the `sr-only` checkbox a11y are all untouched.
- Authored `DesignSystemPicker.reskin.test.tsx` (4 tests): (1) LOCK-F — a 14-entry fixture renders "14 design systems" and the markup contains no "150"; (2) typing in the search box drops a non-matching chip (real filter); (3) clicking a system chip opens the real detail modal whose "Use this system" calls `onSelect("stripe")`; (4) no `#1B2A4A`/`text-gray-`/`bg-gray-`/`border-gray-` in the rendered class strings.

## Task Commits

Each task committed atomically:

1. **Task 1 (RED): pin DS-picker LOCK-F count + real search/select reskin contract** — `8956016a` (test)
2. **Task 1 (GREEN): reskin DesignSystemPicker onto Phase-32 tokens + primitives** — `5d30cfb7` (feat)
3. **Task 2: reskin DS detail + custom modals onto Phase-32 tokens** — `d47c4150` (feat)
4. **Task 3: reskin ReviewGatesSection onto Phase-32 tokens (classNames only)** — `b7a8e9d3` (feat)

**Plan metadata:** (final commit) `docs(35-04): complete DS-picker + review-gates reskin plan`

_TDD note: all three tasks carry `tdd="true"`. For Task 1 the reskin test is a genuine RED gate — pre-reskin the picker markup carries `#1B2A4A`/`text-gray-*`, so the grep-clean assertion fails RED while the count/search/select wiring assertions pass on the existing wiring; the GREEN feat makes all 4 pass. Tasks 2 and 3 are re-style tasks pinned by the existing prototype + ReviewGatesSection suites (delta-based)._

## Files Created/Modified
- `frontend/src/components/workflow/prototype/DesignSystemPicker.reskin.test.tsx` (created) — 4-test LOCK-F + reskin-parity suite; stubs an in-memory localStorage; real 14-entry `DesignSystemListItem` fixture.
- `frontend/src/components/workflow/prototype/DesignSystemPicker.tsx` (modified) — full token/primitive reskin; role=tab category tabs; `Card` panel + `Button` CTA; LOCK-F counts from prop; all search/grouping/custom/select wiring preserved.
- `frontend/src/components/workflow/prototype/DesignSystemDetailModal.tsx` (modified) — dark-idiom token reskin; scrim var + elevation-modal; status-done selected/badge; all fetch/escape/fullscreen/open-tab/onSelect wiring preserved.
- `frontend/src/components/workflow/prototype/CustomDesignSystemModal.tsx` (modified) — light token reskin + `Button` primitive; status-failed error ramp; de-branded placeholder; all validation + onSave/onClose wiring preserved.
- `frontend/src/components/workflow/ReviewGatesSection.tsx` (modified) — classNames-only token reskin + `Pill` default chip; onChange contract + a11y byte-preserved.
- `.planning/phases/35-shell-chrome-reskin-pages-b1/deferred-items.md` (created) — logs the pre-existing ReviewGatesSection.test.tsx AgentLibraryData drift (out of scope).

## Decisions Made
- **DS category tabs stay inline scrollable buttons, not the `Tabs` primitive:** they need horizontal scroll + a Custom count badge; instead they carry the primitive's a11y contract inline (`role=tab`/`role=tablist`/`aria-selected`) + the AuditTab chip idiom — same reuse-don't-rebuild call as 35-03 (D-15).
- **`DesignSystemDetailModal` reskinned on dark tokens only, not light primitives:** a full-bleed dark preview modal; the light `Button`/`Pill` would break the theme. It mirrors the 35-03 `TemplateDetailModal` dark idiom (surface-near-black/ink-black + white/opacity + scrim var).
- **`CustomDesignSystemModal` + `ReviewGatesSection` DO consume primitives:** the custom-DS modal's Cancel/Save are `Button` (secondary/primary); the review-gates "default" chip is a `Pill` with a brand-fill tint override.
- **Placeholder de-branding:** the "Load example" DESIGN.md placeholder contained `Inter`/`JetBrains Mono` font names and raw fenced hexes, which trip the retired-font + fenced-hex gates as *data*. They were replaced with generic families + `<...-hex>` role tokens — still an instructive example, gate-clean.
- **Test localStorage shim:** the detail modal reads `getToken()` (localStorage) on mount; jsdom in this suite has no functional localStorage, so the reskin test stubs a minimal in-memory one to let the real select path run — an environment shim, not a behaviour change.

## Deviations from Plan
None material. Two documented in-scope interpretations:
- **DS category tabs** kept as inline chips with the `role=tab` a11y contract applied inline (the plan's explicit "Tabs-style token underline" satisfied via the AuditTab chip idiom, matching 35-03) — reuse-don't-rebuild, not a deviation.
- **[Rule 3 - blocking] Placeholder de-branding + test localStorage shim:** the fenced-hex/retired-font gate and the jsdom localStorage gap both blocked task completion; both were resolved with minimal, behaviour-preserving edits (data-only placeholder rewrite; test-only env stub).

## Known Stubs
None introduced. DS data flows from the real `DesignSystemListItem[]` prop (backend `listDesignSystems`, ~14) and localStorage-backed custom systems; no hardcoded/empty data was added and LOCK-F is enforced (count follows the prop). The picker is keyed on generic design-system data, never a workflow name (SC-001/INV-1); no transport/backend was touched (INV-3/LOCK-B).

## Threat Flags
None. Reskin-only: no new endpoint/auth/file/schema surface. The Review-gates `gate_agent_ids` payload contract is byte-identical (T-35-04-01 mitigated by classNames-only reskin); LOCK-F satisfied by construction (T-35-04-02); picker keyed on generic data (T-35-04-03); zero package installs (T-35-04-SC).

## Verification Evidence
- **Retired-palette grep == 0** on all four files (`#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains`): DesignSystemPicker 0, DesignSystemDetailModal 0, CustomDesignSystemModal 0, ReviewGatesSection 0.
- **Stray-stock grep == 0** on all four files (`bg-[#|text-[#|#hex|bg/text-(blue|gray|slate|indigo|emerald|red)-|border-gray-|#F1F4FB|#111827|#1f2937`): all 0.
- **Positive token/primitive authority:** DesignSystemPicker consumes `Card`+`Button`; CustomDesignSystemModal consumes `Button`; ReviewGatesSection consumes `Pill`; DesignSystemDetailModal uses the dark token idiom (tokens only, matching 35-03 TemplateDetailModal).
- **LOCK-F:** `grep -c '150'` on DesignSystemPicker.tsx = 0; the reskin test asserts a 14-entry fixture renders "14 design systems" and no "150" leaks. Real live count preserved via `systems.length` (backend `listDesignSystems`, ~14).
- **Review-gates contract:** the handler still reports `onChange(ordered, touched)` where `ordered = agents.filter(a => checkedIds.has(a.id)).map(a => a.id)` and `toggle` sets `touched=true` — signature + emitted values unchanged; `aria-expanded` + `sr-only` checkbox preserved.
- **Behavior GREEN:** `npm run test -- DesignSystemPicker.reskin` -> 4/4 passed; `npm run test -- prototype` -> 3 files / 11 passed (no regression).
- **Existing ReviewGatesSection test delta = 0:** 16 passed / 3 failed both BEFORE (pristine HEAD) and AFTER the reskin — proven by re-running against the committed component. The 3 failures are pre-existing `AgentLibraryData` drift (prototype pipeline now 5 agents; `prototype-analyze` is a third Human_Gate) in files this plan does not touch -> logged to `deferred-items.md`.
- **tsc identity:** `npx tsc --noEmit 2>&1 | grep -v mockApi.ts | grep -c error` -> 0.
- **e2e:** not run — mocked webServer times out offline; e2e delta is live-deferred at the phase level per the environment contract.

## Next Phase Readiness
- The DS-selection + review-gates surfaces are fully converged on tokens with the picker's LOCK-F count + wiring pinned by a parity test; Wave 2 continues with 35-05..35-07 (Library, Login/Register, Admin).
- No new dependencies; no backend/transport/Python touch (INV-3/LOCK-B held). One pre-existing test-data drift logged for a follow-up reconciliation quick task.

## Self-Check: PASSED
- All 5 code/test files verified present on disk.
- All 4 task commits verified in git log (8956016a, 5d30cfb7, d47c4150, b7a8e9d3).
