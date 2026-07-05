---
phase: quick-260701-go2
plan: 01
subsystem: prototype-validators
tags: [route_table, static_check, render_check, alias-parametric, resolve-through-table, INV-3, INV-12, regression-AB]
requires: [static_check, render_check, _href_target_id, _extract_dynamic_nav_routes, _first_path_segment]
provides:
  - shared pure route-table resolver (parse both object + array forms; resolve exact/alias/:id)
  - static_check resolve-through-table branch with graceful legacy fallback
  - render_check expected-from-resolved-page with graceful first-segment fallback
  - B (fixed-router alias/parametric) regression fixture — must-pass both tiers
  - A=fail-via-render / B=pass regression with round-3 recomputed A pins
affects: [prototype build loop, prototype_revision gate, offline nav-coverage harness]
tech-stack:
  added: []
  patterns: [resolve-through-table, one-way-resolver-dependency, per-target-dedup, graceful-legacy-fallback]
key-files:
  created:
    - backend/app/agents/route_table.py
    - backend/tests/agents/test_route_table.py
    - backend/tests/agents/fixtures/imc-inventory-certificate-management-fixed.html
  modified:
    - backend/app/agents/static_check.py
    - backend/app/agents/render_check.py
    - backend/tests/agents/test_nav_coverage.py
decisions:
  - "The resolver is the ONE new (shared) module; both validators were extended IN PLACE (INV-12). parse_routes_table returns None for href-valued object maps / table-less scripts so BOTH tiers keep their legacy first-segment path byte-identical (INV-3)."
  - "static resolve-through-table dedupes dead links per unreachable target (A's 11 round-2 dead links collapse to 5); a section reached via a parametric/alias route is reachable, not a false orphan."
  - "render keeps discovery/dedup/coverage first-path-segment (denominator unchanged); ONLY NavResult.expected changes to the resolved page, with a _first_path_segment fallback when the table misses."
metrics:
  tasks: 3
  files: 6
  duration: ~35min
  completed: 2026-07-01
---

# quick-260701-go2: Round 3 — route-table-aware prototype validators Summary

Both prototype validators are now ROUTE-TABLE-AWARE: they resolve a nav route THROUGH the app's declared route table (exact / alias / `:id` parametric, first-match-wins, authored-order) before judging it, closing the alias/parametric false-positive that a correctly-routing SPA (B) tripped under the round-2 first-path-segment heuristic — without weakening the genuine-defect detection A relies on. One new shared, pure, stdlib-only resolver (`route_table.py`) is imported by both validators (extended IN PLACE, INV-12); when no resolvable table is declared (goldens, trimmed fixture, href-valued object maps) both tiers fall back to the exact round-2 behavior (INV-3, byte/event-identical). B passes both tiers; A still fails via render; the round-2 A pins are recomputed to their round-3 measured values.

## MEASURED FINAL COUNTS (live Chromium)

| Fixture | Tier | Result |
|---------|------|--------|
| **B** (`-fixed.html`, 417KB) | static | **ok=True** — 0 dead-link, 0 router-dead |
| **B** | render | **available=True, ok=True** — 17/17 nav activate their resolved section, 0 dead, 0 coverage errors |
| **A** (`-full.html`, 414KB) | static | ok=False — dead-link **5**, router-dead **0** |
| **A** | render | **available=True, ok=False** — 17 total / **16** dead (only `dashboard` ok) |
| A static↔render dead-target overlap | — | **2** (`certificates`, `inventory`) |

### Round-2 → Round-3 pin changes (test_nav_coverage.py)

| Pin | Round-2 | Round-3 | Why |
|-----|---------|---------|-----|
| `_FULL_STATIC_DEAD_LINKS` | 11 | **5** | resolver + per-target dedup collapses A's parametric/alias dead routes to their distinct unreachable targets (`inventory`, `certificates`, `profile`, `certificate`, `approvals`) |
| `_FULL_STATIC_ROUTER_DEAD` | 0 | 0 | unchanged |
| `_FULL_RENDER_SIDEBAR_DEAD` | 16 | 16 | unchanged — A's runtime is genuinely broken |
| `_FULL_RENDER_NAV_TOTAL` | 17 | 17 | unchanged — discovery/dedup denominator untouched |
| `_FULL_STATIC_RENDER_OVERLAP` | 2 | 2 | unchanged — still `{certificates, inventory}` |

B's `#/inventory/4521` → `inventory-detail`, `#/certificates/892` → `certificate-detail`, `#/certificates/create` → `certificate-create`, `#/profile` → `user-profile` all resolve and activate the correct section — the exact routes render marked "dead" in round-2 by comparing against the first path segment.

## What shipped

**Task 1 — shared resolver + unit tests (commit 4f176004)**
- `app/agents/route_table.py`: `parse_routes_table(script_text)` handles the array-of-objects form (B) and the page-id-valued object form (A); returns `None` for href-valued object maps (`{id:'#/route'}`), table-less scripts, unbalanced braces/brackets, or zero entries. `resolve_route(table, path)` mirrors `matchRoute` exactly — normalize `#`/`?query`/leading+trailing `/`, `:id` → `re.escape(base)+r'/([^/]+)'` (regex-injection guard), else exact match; first-match-wins, authored order. Stdlib-only (`re`); imports NOTHING from static_check/render_check (one-way dependency).
- `test_route_table.py`: 17 tests — parse object/array/href-object-None/no-routes-None/unbalanced-None/comment-stripping; resolve exact/alias/:id/miss, alias-before-parametric order-wins, path normalization, regex-injection guard.

**Task 2 — wire both validators, graceful fallback (commit 298da23c)**
- `static_check.py`: imports `parse_routes_table`/`resolve_route`; when a table parses, judges each nav route (anchor + dynamic) by its resolved page — reachable (page has a section) / dead-link (table maps to a section-less page, deduped per page) / router-dead (resolves to None but the first-segment target has a section, deduped per target) / plain dead-link (deduped per target); parametric/alias sections are not false orphans. This branch supersedes the legacy first-segment loop AND the `_extract_routes_map` completeness/router-dead block (INV-12). `table is None` runs the entire legacy path verbatim.
- `render_check.py`: imports the resolver; parses the table once from the file source inside `if check_nav:` and threads it into `_check_nav`; discovery/classification/un-dedup/`${…}`-exclusion/coverage denominator are byte-identical — ONLY `NavResult.expected` changes to `resolve_route(table, route)` with a `_first_path_segment` fallback. The two `available=False` early returns + available/ok/note contract are untouched.

**Task 3 — B fixture + A=fail/B=pass regression + recomputed pins (commit 9878a821)**
- Committed B verbatim as `imc-inventory-certificate-management-fixed.html` (trimmed + full fixtures KEPT — additive).
- `test_nav_coverage.py`: added `_FIXED_FIXTURE` + Scenario 13 — fixed-fixture-committed, B-passes-static, B-passes-render (spot-checks an alias/:id route activating its hyphenated resolved section), A-fails-via-render (browser-gated). Recomputed `_FULL_STATIC_DEAD_LINKS` 11 → 5 with a round-3 supersession note; refreshed the overlap comment to the measured `{certificates, inventory}`.

## Verification results

- Full offline targeted suite + `test_route_table.py`: **191 passed**, 0 skipped (Chromium present — all browser-gated B/A render assertions ran LIVE), NO SNAPSHOT_UPDATE.
- Task 2 suite (characterization ×4 + static_check + validators + gates + phase5 ×2 + compiler): 140 passed — the 4 stable goldens (prototype, od_prototype, prototype_revision, app_builder) byte/event-identical.
- **od_ppt**: confirmed failing IDENTICALLY to baseline (`test_od_ppt_event_snapshot` only — the pre-existing skills-asset/event-golden drift documented in 260701-erg; the deliverable-snapshot test passes). Left untouched, NOT a new break.
- `lint-imports`: **4 kept, 0 broken** (route_table.py is app→app; no new cross-boundary edge).
- No `deepagents` reference, no pipeline-name literal (SC-001), no `if pipeline_type ==` branch (INV-1) in the changed sources. Additive only — no migration, no new dependency.

## Deviations from Plan

None — plan executed exactly as written. The plan predicted A's static dead-link count would "drop toward 0"; the measured value is 5 (down from 11), driven by per-target dedup of A's parametric/alias routes under the resolver. All other round-2 pins held at their measured round-3 values.

## Known Stubs

None — all changes are resolver/validator logic + tests + a real committed fixture; no placeholder/empty-data paths introduced.

## Threat Flags

None — no new network endpoint, auth path, or schema change. `render_check` reads the same file it already loads into Chromium (T-go2-03 accepted). Bounded depth-counter parsing returns None on adversarial/unbalanced input (T-go2-01); `re.escape` on the `:id` base guards regex injection (T-go2-02). No package installs (T-go2-SC).

## Commits
- `4f176004` feat(agents): shared route-table resolver (parse both forms + resolve)
- `298da23c` fix(agents): resolve nav routes through the app route table (both validators)
- `9878a821` test(agents): B=pass/A=fail regression + recompute round-3 A pins

## Self-Check: PASSED
- Files: `route_table.py`, `test_route_table.py`, `imc-inventory-certificate-management-fixed.html` all present on disk.
- Commits: 4f176004, 298da23c, 9878a821 all present in git history.
</content>
</invoke>
