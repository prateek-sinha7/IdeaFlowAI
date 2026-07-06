---
phase: quick-260701-hqa
plan: 01
subsystem: agents (render_check + execution engine validation)
tags: [render-check, null-honesty, nav-validation, fix-loop, INV-3, INV-12]
requires:
  - quick-260701-go2 (round-3 route-table-aware validators — A=fail/B=pass verdict)
  - quick-260701-erg (round-2 un-dedup + settle knob + template-literal exclusion)
provides:
  - "render_check active-section READ that excludes nav/anchor controls and returns None on a blank page (no name coercion)"
  - "engine _dead_nav_line() — single pure helper wording dead navs by actual failure class (blank vs wrong-section)"
  - "blank-nav.html must-fail regression fixture"
  - "A render repinned to 17/17 dead (LIVE-measured)"
affects:
  - backend/app/agents/render_check.py
  - backend/agents/execution_engine/engine.py
tech-stack:
  added: []
  patterns:
    - "CSS :not() nav-exclusion on the active-section READ selector"
    - "one shared pure message formatter used by two call sites (no divergence)"
key-files:
  created:
    - backend/tests/agents/fixtures/blank-nav.html
  modified:
    - backend/app/agents/render_check.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/test_phase5_fixloop_selection.py
    - backend/tests/agents/test_nav_coverage.py
decisions:
  - "Active-section READ selector is the ONLY render_check behavior changed (plus the measure-gated coverage denominator); all round-2/round-3 logic left byte-identical"
  - "Coverage denominator nav-exclusion applied and KEPT — measured inert (no golden/fixture/pin drift)"
metrics:
  duration: ~6m
  completed: 2026-07-01
  tasks: 2
  files: 5
---

# Phase quick-260701-hqa Plan 01: Render blank-to-null honesty Summary

Made `render_check` honest about *why* a route fails: the active-section READ now excludes
nav/anchor controls and returns `None` when no real `<section>` is active (a blank page is
null, never coerced to a nav-link's data-page name), and the fix-loop dead-nav message names
its actual failure class (blank vs wrong-section) via one shared pure helper — repinning the
full A fixture to 17/17 dead while B stays 17/17 pass.

## What was built

### Task 1 — render null-honesty READ + honest dead-nav wording (commit 01b62986)
- `render_check._exercise_route`: active-section READ selector changed from
  `"[data-page].is-active, .section.is-active"` to
  `"[data-page].is-active:not(a):not(.nav-link):not(.nav-item):not(.nav-submenu-link), .page-section.is-active, .section.is-active"`.
  On no match, Playwright `eval_on_selector` raises → the existing `except → return None`
  yields null. No name-coercion fallback added. All other logic (from_anchor branch,
  settle knob, `available=False` early returns, un-dedup, `${...}` exclusion, classification
  query at l.297, round-3 `expected`) left byte-identical.
- ITEM 1 SECONDARY: coverage denominator query `[data-page]` → `[data-page]:not(a):not(.nav-link):not(.nav-item):not(.nav-submenu-link)`.
  Applied and **kept** — measured inert (no golden/fixture/pin drift).
- `engine._dead_nav_line(nav)`: pure module-level helper. `activated is None` →
  `"dead nav link: '<href>' activated NOTHING (no <section data-page> became active — blank page)"`;
  else → `"dead nav link: '<href>' activated '<activated>' but expected '<expected>'"`. Used by
  BOTH `_select_issues_to_fix` and the build residual assembly in `_run_validation_fix_loop`.
- `test_phase5_fixloop_selection.py`: 4 wording pins repinned to the honest blank text
  (2 additional plan-referenced pins were the same two assertions counted once), renamed
  `test_build_order_..._legacy` → `test_build_order_pins_canonical_honest_wording_and_order`,
  added `test_dead_nav_wrong_section_names_actual_and_expected`, refreshed module docstring.

### Task 2 — blank-nav fixture + repin A render (commit 0877ab33)
- `tests/agents/fixtures/blank-nav.html`: minimal 2-section hash-router SPA whose `hashchange`
  handler strips `is-active` from ALL `[data-page]` then adds it to the matching nav
  `<a data-page>` only — never a `<section>`. Mimics A's unscoped-router defect in ~45 lines.
- `test_nav_coverage.py`: `_BLANK_FIXTURE` constant; `_FULL_RENDER_SIDEBAR_DEAD` 16 → 17
  (LIVE-measured, comment refreshed); `_FULL_RENDER_NAV_TOTAL=17` and
  `_FULL_STATIC_RENDER_OVERLAP=2` unchanged; new scenario 14 asserting blank-nav
  available=True/ok=False and every NavResult.activated is None INCLUDING #/dashboard.

## Measured results (LIVE — Chromium present, render ran, not skipped)

| Fixture | available | ok | total nav | dead | notes |
|---------|-----------|----|-----------|----- |-------|
| A (full) | True | False | 17 | **17** | #/dashboard now dead (activated=None), was 16 coerced |
| B (fixed) | True | True | 17 | 0 | 17/17 pass — selector not too aggressive |
| blank-nav | True | False | 2 | 2 | every activated=None incl. #/dashboard |

- static/render overlap on A = 2 `{'certificates', 'inventory'}` — dashboard has a real
  section so it is NOT a static-dead target → overlap unaffected.

## Verification

- `test_phase5_fixloop_selection.py` + `test_phase5_revision_validation.py`: 26 passed
- `test_nav_coverage.py`: 36 passed (browser-gated render pins ran LIVE)
- `test_route_table.py` + `test_static_check.py` + `test_validators.py`: 57 passed
- 4 stable characterization goldens (prototype, od_prototype, prototype_revision,
  app_builder): 8 passed byte/event-identical — **no SNAPSHOT_UPDATE** (INV-3 holds)
- `grep "activated NOTHING"` engine.py + `grep ":not(.nav-link)"` render_check.py: OK
- `/opt/homebrew/bin/lint-imports`: 4 kept / 0 broken (INV-12/§31)
- od_ppt: NOT touched — known pre-existing/environmental baseline failure, left as-is per plan.

## Deviations from Plan

None — plan executed exactly as written. The measure-gated ITEM 1 SECONDARY (coverage
denominator nav-exclusion) was applied and kept after confirming zero golden/fixture/pin drift,
as the plan's primary path prescribed.

## Self-Check: PASSED
- backend/tests/agents/fixtures/blank-nav.html — FOUND
- commit 01b62986 — FOUND
- commit 0877ab33 — FOUND
