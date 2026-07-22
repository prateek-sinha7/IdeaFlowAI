---
phase: quick-260701-kml
plan: 01
subsystem: agent-runtime/render-validation
tags: [render-check, nav-validation, wrong-section, fixture, INV-3, test-only]
requires: [render_check, route_table, engine._dead_nav_line]
provides: [wrong-section-e2e-coverage, mis-route-fixture]
affects: []
tech-stack:
  added: []
  patterns: [browser-gated-integration-test, hand-authored-spa-fixture]
key-files:
  created:
    - backend/tests/agents/fixtures/mis-route.html
  modified:
    - backend/tests/agents/test_nav_coverage.py
decisions:
  - "Construction (a): swap map named `swap` (not `routes`) so parse_routes_table returns None and expected falls back to first-path-segment — the RUNTIME disagreement, never a table that blesses the mis-route."
metrics:
  duration: "~6 min"
  completed: 2026-07-01
  tasks: 2
  files: 2
---

# Phase quick-260701-kml Plan 01: Round-5 Wrong-Section End-to-End Summary

Fixture C (`mis-route.html`) + scenario 15 drive a real SPA through the full
`render_check` pipeline (Chromium included) to a genuine wrong-section verdict for
the first time — closing the last hole in the three-way render classification.
TEST-ONLY, fully additive, zero production edits.

## What Was Built

- **Task 1 — `mis-route.html` (fixture C):** a minimal hand-authored SPA with three
  real `<section data-page>` sections (`dashboard` initially active, `page-a`,
  `page-b`). A scoped `hashchange` router driven by a map literal named `swap`
  (NOT `routes`) activates a real-but-WRONG section: `#/page-a` -> `page-b`,
  `#/page-b` -> `page-a`, `#/dashboard` -> `dashboard`. Nav is plain anchors with no
  `data-page` / `nav-*` class so `section_count == 3` (no false coverage-0). Because
  the map is not named `routes`, `parse_routes_table` returns `None`, so `expected`
  falls back to the first-path-segment — making the swap unambiguously wrong-section.
  Commit `b54159bf`.

- **Task 2 — scenario 15 (three tests):** committed-file assert; the browser-gated
  end-to-end wrong-section integration test (runs LIVE, Chromium present); and the
  offline honest-wording assert on `engine._dead_nav_line`'s else-branch.
  Commit `0d8429ac`.

## Measured mis-route render result (LIVE, Chromium)

`render_check(mis-route.html)` → `available=True`, `ok=False`, `coverage_errors=[]`:

| href          | activated   | expected  | ok    |
| ------------- | ----------- | --------- | ----- |
| `#/dashboard` | `dashboard` | dashboard | True  |
| `#/page-a`    | `page-b`    | page-a    | False |
| `#/page-b`    | `page-a`    | page-b    | False |

- **null/blank count == 0** (distinct from the round-4 blank/null path).
- **≥1 correct** (`#/dashboard`) — not a blanket-fail.
- **Wrong-section branch fired end-to-end:** `#/page-a` activated the real `page-b`
  section (non-null, != expected `page-a`) — the `activated is not None AND
  activated != expected` path exercised against Chromium for the first time (was
  `_nav_ok` unit-only).
- Honest wording asserted offline: `_dead_nav_line(NavResult(href="#/page-a",
  activated="page-b", expected="page-a"))` == `"dead nav link: '#/page-a' activated
  'page-b' but expected 'page-a'"`.

The STOP-AND-REPORT guard did NOT trip — the wrong-section branch fired exactly as
the plan-checker predicted; no real render_check bug found.

## Verification

- `pytest tests/agents/test_nav_coverage.py -k scenario15` → 3 passed (none skipped;
  browser-gated test ran LIVE).
- `pytest test_nav_coverage.py + 4 stable characterization goldens` → **47 passed**,
  NO SNAPSHOT_UPDATE (INV-3 holds; goldens byte/event-identical). `od_ppt` is the
  known pre-existing/environmental baseline failure — left untouched (not in suite).
- `lint-imports` → **4 kept / 0 broken**.
- No-production-change proof: `git diff HEAD -- render_check.py static_check.py
  route_table.py engine.py` is empty. Only `mis-route.html` (new) + `test_nav_coverage.py`
  (modified) changed.

## Deviations from Plan

None — plan executed exactly as written. (One in-file authoring nit: the fixture's
explanatory comment initially contained the literal string "var routes", tripping
the Task 1 guard regex; reworded to avoid the reserved token. Not a plan deviation.)

## Self-Check: PASSED

- `backend/tests/agents/fixtures/mis-route.html` — FOUND (committed `b54159bf`).
- `backend/tests/agents/test_nav_coverage.py` scenario 15 — FOUND (committed `0d8429ac`).
- Both commits present in `git log`.
