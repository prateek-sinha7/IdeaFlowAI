---
phase: quick-260701-erg
plan: 01
subsystem: prototype-validators
tags: [render_check, static_check, router-dead, require_render, nav-coverage, INV-3, full-file-regression]
requires: [static_check, render_check, html_render, ValidationGate, WorkflowCompiler]
provides:
  - render_check per-route un-dedup for malformed nav targets + ${…} exercise-exclusion
  - render_check configurable nav settle wait (_NAV_SETTLE_MS + nav_settle_ms param)
  - static_check browserless router-dead nav-link cross-check (routes-map resolution)
  - require_render:true load-bearing on prototype build + revision manifests
  - golden-run require_render pin (deepcopy-safe) making the 5 goldens knob/Chromium-independent
  - full 414KB regression fixture + pinned final counts + fail-closed assertion
affects: [prototype build loop, prototype_revision gate, offline golden harness]
tech-stack:
  added: []
  patterns: [dom-classified-nav-dedup, routes-map-resolution-crosscheck, deepcopy-before-mutate-cached-plan]
key-files:
  created:
    - backend/tests/agents/fixtures/imc-inventory-certificate-management-full.html
  modified:
    - backend/app/agents/render_check.py
    - backend/app/agents/static_check.py
    - backend/agents/workflows/prototype/workflow.yaml
    - backend/agents/workflows/prototype_revision/workflow.yaml
    - backend/tests/agents/_scripted_model.py
    - backend/tests/agents/test_nav_coverage.py
    - backend/tests/agents/test_phase5_revision_validation.py
decisions:
  - "render un-dedup classifies candidates against the DOM [data-page] id set: real-section targets dedupe to one representative; each concrete malformed route keeps its own NavResult; ${…} routes are counted-as-discovered but never exercised."
  - "router-dead is a distinct nav-framed issue (by design a subset of routes-map-missing) — the plan wants it as a separate, more actionable finding; only guarded against double-reporting with the plain no-section dead-link."
  - "The golden-run require_render pin deep-copies the @lru_cache'd CompiledWorkflow before mutating, preventing cache corruption for later callers (also fixes the latent clarify.mode='off' cache leak)."
metrics:
  tasks: 3
  files: 8
  duration: ~20min
  completed: 2026-07-01
---

# quick-260701-erg: Harden prototype validators round 2 (render un-dedup + router-dead + require_render) Summary

Round 2 of prototype-validator hardening (extends 260701-bob IN PLACE, INV-12): render_check now un-dedups malformed nav routes so each concrete dead detail route reports distinctly (real-section routes still dedupe), excludes `${…}` template literals from browser exercise while counting them for coverage, and exposes a configurable settle wait; static_check adds a browserless router-dead cross-check; `require_render:true` is now load-bearing on both the prototype build and revision manifests (revision fails closed via its validation gate); and the full 414KB IMC file is pinned as a marked regression fixture with exact final counts and a fail-closed assertion — all with the 4 stable goldens byte/event-identical and NO SNAPSHOT_UPDATE.

## MEASURED FINAL COUNTS (full 414KB fixture, post-items 3+4)

| Metric | Value |
|--------|-------|
| static dead-link count | **11** |
| static router-dead count | **0** (every section IS a routes-map key) |
| render sidebar-dead count | **16** (of 17 exercised NavResults; only `dashboard` ok) |
| static↔render dead-target overlap | **2** (`certificates`, `inventory`) — asserted EXACTLY |

The full file's router is genuinely broken: `navigateTo` does `querySelector('[data-page=X]')`, which matches the NAV LINK (earlier in DOM) not the `<section>`, and only clears `is-active` from `.page-section` — so sections never activate and nav-link `is-active` accumulates. render_check correctly surfaces this as 16 dead routes (a real defect, not a harness artifact — confirmed deterministic across 3 runs and settle-time-independent at 50/150/400ms).

## What shipped

**Task 1 — render un-dedup + settle knob + static router-dead (commit 7370d750)**
- `render_check`: `_check_nav` now queries the DOM `[data-page]` value set and classifies each candidate — real-section targets dedupe to one representative; each concrete malformed route (target not a section) keeps its own `ok=False` NavResult (deduped by exact route string); `${…}` template routes are counted as *discovered* (feeding the coverage denominator) but never exercised. Added `_NAV_SETTLE_MS = 50` + a keyword-only `nav_settle_ms` threaded `render_check → _check_nav → _exercise_route`, replacing the hardcoded 50ms (default byte-identical). The two `available=False` early returns + the available/ok/note contract are preserved verbatim.
- `static_check`: inside the existing `if routes_map is not None:` guard, a routes-map RESOLUTION cross-check emits a distinct `router-dead nav link` issue for a nav route target that has a `<section data-page>` but no routes-map key (deduped per target; never for a no-section target — that stays the plain dead-link).
- `test_nav_coverage.py`: router-dead present/no-map guard + per-target dedup, settle-knob signature, render un-dedup + `${}` exclusion + only-template no-false-coverage-0.

**Task 2 — require_render load-bearing + golden-run pin (commit cdb25817)**
- `prototype/workflow.yaml`: `require_render: true` on the prototype-build step (gates:[] → records a validator_skipped audit row + declares intent, behavior-neutral; no gate added, so the event golden is untouched).
- `prototype_revision/workflow.yaml`: flipped `require_render: false → true` — the revision step (gates:[validation]) now fails CLOSED on a browserless render (html_render P0 → ValidationGate GATE_BLOCK).
- `_scripted_model._patched_compile_for_run`: deep-copies the `@lru_cache`'d CompiledWorkflow before mutating, then pins every step's `require_render=False` for golden runs (knob/Chromium-independent). The deepcopy prevents corrupting the shared cache for later callers.
- `test_nav_coverage.py`: compiler assertion that both build + revision steps compile to `require_render=True`.

**Task 3 — full-file regression fixture + pinned counts + fail-closed (commit e8e4f336)**
- Committed the full 414KB `imc-inventory-certificate-management-full.html` (trimmed fixture KEPT — additive).
- `test_nav_coverage.py`: pins the four measured counts above as exact integers (static offline; render browser-gated, skips cleanly offline), and adds the offline fake-render `available=False + require_render=true → exactly one P0 + a SKIPPED audit row` fail-closed assertion.

## Verification results

- Full targeted offline suite (characterization prototype/od_prototype/prototype_revision/app_builder + static_check + validators + gates + phase5_fixloop + phase5_revision + compiler + nav_coverage): **170 passed**, NO SNAPSHOT_UPDATE.
- `lint-imports` — **4 kept, 0 broken** (no new kernel→app edge; no new import).
- The 4 stable characterization goldens stay byte/event-identical (the harness pins require_render=False; router-dead is skipped on map-less goldens; un-dedup never fires on nav-less goldens).
- **od_ppt** confirmed failing IDENTICALLY to baseline — the on-disk `skills/opendesign/design-templates/web-prototype/example.html` injects a `TEMPLATE EXAMPLE` block the committed golden lacks (skills-asset/event-golden drift, baseline-proven independent of the validators). Left untouched, no SNAPSHOT_UPDATE, no NEW breakage.
- Render counts confirmed deterministic across 3 runs and settle-time-independent.

## Deviations from Plan

### 1. [Rule 3 — blocking bug] Deepcopy before mutating the @lru_cache'd CompiledWorkflow
- **Found during:** Task 2.
- **Issue:** `engine.compile_for_run` is `@functools.lru_cache(maxsize=None)`, so it returns a SHARED CompiledWorkflow. The plan's harness pin (`compiled.steps[*].require_render = False`) mutated the cached object in place, corrupting `require_render` for every later caller in the same pytest process — which broke the new compiler assertion (`test_scenario11`) and `test_phase5_revision_validation` when a characterization run preceded them. (The pre-existing `compiled.clarify.mode = "off"` write had the same latent leak, unobserved because nothing asserted it downstream.)
- **Fix:** `_patched_compile_for_run` now `copy.deepcopy(...)` the compiled plan before mutating both `clarify.mode` and `require_render`, leaving the cached original pristine. Golden behavior is unchanged (the run uses an equivalent object with identical field values).
- **Files modified:** `backend/tests/agents/_scripted_model.py`
- **Commit:** cdb25817

### 2. [Rule 1 — new-correct-behavior test update] phase5_revision baseline gains the router-dead nit
- **Found during:** Task 2 (surfaced by the ITEM 4 router-dead check from Task 1).
- **Issue:** `test_phase5_revision_validation`'s inline `_ORIGINAL_HTML` fixture navigates to `#/settings` (a real `<section data-page="settings">`) while the routes map omits `settings`, so the new router-dead cross-check legitimately emits a SECOND pre-existing nit. The test asserted a single `_PREEXISTING_NIT`.
- **Fix:** Added `_PREEXISTING_ROUTER_DEAD` + a `_PREEXISTING_NITS` set and updated the fixture-drift / suppression / final-HTML assertions to treat both nits as the baseline (both predate the edit → both baselined; only the `ghost` regression is fixed). This is a behavioral unit test (NOT a golden) — no SNAPSHOT_UPDATE involved; the update reflects genuinely-new correct behavior.
- **Files modified:** `backend/tests/agents/test_phase5_revision_validation.py`
- **Commit:** cdb25817

## Known Stubs

None — no placeholder/empty-data paths introduced; all changes are producer/validator logic + tests + a real fixture.

## Threat Flags

None — no new network endpoint, auth path, file-access pattern, or schema change. Additive only (no migration); no new import (lint-imports 4/0).

## Commits
- `7370d750` fix(agents): un-dedup malformed render routes + static router-dead cross-check
- `cdb25817` feat(agents): make require_render load-bearing on prototype build + revision
- `e8e4f336` test(agents): pin full-file final counts + fail-closed regression

## Self-Check: PASSED
- Files: `imc-inventory-certificate-management-full.html` + `260701-erg-SUMMARY.md` present on disk.
- Commits: 7370d750, cdb25817, e8e4f336 all present in git history.
- Working tree clean (only the untracked `.planning/quick/260701-erg-…` docs artifacts remain for the orchestrator's docs commit).
</content>
</invoke>
