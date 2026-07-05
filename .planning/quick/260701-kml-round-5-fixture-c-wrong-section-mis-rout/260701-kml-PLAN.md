---
phase: quick-260701-kml
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/tests/agents/fixtures/mis-route.html
  - backend/tests/agents/test_nav_coverage.py
autonomous: true
requirements: [WRONG-SECTION-E2E]
tags: [render-check, nav-validation, wrong-section, fixture, INV-3, test-only]

must_haves:
  truths:
    - "render_check(mis-route.html) is available=True and ok=False when Chromium is present"
    - "At least one NavResult has activated non-null AND activated != expected — the wrong-section branch (activated is not None AND activated != expected) fires end-to-end through the real render pipeline for the first time"
    - "The null/blank count is 0 (no NavResult.activated is None) AND at least one route is correct — so wrong-section is provably distinguished from the round-4 blank path and from a blanket-fail"
    - "No production code changes: render_check.py / static_check.py / route_table.py / engine.py are untouched (the branch already exists; this only exercises it)"
    - "The 5 characterization goldens stay byte/event-identical with NO SNAPSHOT_UPDATE (INV-3); lint-imports 4/0"
  artifacts:
    - path: "backend/tests/agents/fixtures/mis-route.html"
      provides: "A minimal hand-authored SPA whose scoped router activates a real-but-WRONG section (page-a->page-b, page-b->page-a, dashboard->dashboard) with NO parseable routes table, so expected=first-segment and the mis-route is unambiguously wrong-section"
      contains: "section data-page"
    - path: "backend/tests/agents/test_nav_coverage.py"
      provides: "Scenario 15 — the committed-file assert, the browser-gated wrong-section end-to-end integration test, and the offline honest-wording assert"
      contains: "scenario15"
  key_links:
    - from: "backend/tests/agents/fixtures/mis-route.html"
      to: "app.agents.render_check._exercise_route"
      via: "hashchange router activates the swapped (wrong) real <section data-page>, so activated is a real-but-wrong section id (non-null)"
      pattern: "addEventListener\\('hashchange'"
    - from: "backend/tests/agents/test_nav_coverage.py"
      to: "app.agents.render_check.render_check"
      via: "asyncio.run(render_check(_MIS_ROUTE_FIXTURE)) drives the fixture and asserts the wrong-section NavResult"
      pattern: "render_check\\(_MIS_ROUTE_FIXTURE"
---

<objective>
Round 5 (final). Close the last hole in the three-way render classification: the
**wrong-section** branch in `render_check` (`activated is not None AND activated != expected`)
is only UNIT-tested today (`test_nav_coverage.py::test_scenario2_nav_ok_pure` proves
`_nav_ok("settings","dashboard") is False`). No fixture has ever driven a real SPA through
the full `render_check` pipeline (Chromium included) to a genuine wrong-section verdict —
fixture A is all-blank (wrong-section=0), fixture B is all-correct (wrong-section=0),
blank-nav is null-honesty (activated=None, not a real wrong section).

This plan adds **fixture C** — `mis-route.html`, a hand-authored SPA whose scoped router
lands on a real-but-WRONG section — plus a browser-gated integration test that fires the
wrong-section branch end-to-end, distinguishes it from the round-4 blank path, and proves the
honest wrong-section message wording.

Purpose: prove the wrong-section render path actually works against Chromium, not just in a
pure `_nav_ok` unit. If it does NOT fire end-to-end, that is a real bug — STOP and report.
Output: one new fixture + one new test scenario. TEST-ONLY, fully ADDITIVE — zero production
edits.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@backend/CLAUDE.md
@.planning/quick/260701-hqa-round-4-render-blank-to-null-honesty-sto/260701-hqa-SUMMARY.md

# The code paths this plan EXERCISES (do NOT modify — read to understand the contract):
@backend/app/agents/render_check.py
@backend/app/agents/route_table.py

# The test file to extend + the closest fixture analog to hand-author:
@backend/tests/agents/test_nav_coverage.py
@backend/tests/agents/fixtures/blank-nav.html
</context>

<design_constraint>
CRITICAL — the mis-route MUST be a RUNTIME disagreement with `expected`, never a table that
blesses it. In `render_check`, `expected` = `resolve_route(table, route)` when a routes table
parses, ELSE `_first_path_segment(route)`.

Construction (a) — the PREFERRED, unambiguous one (chosen here):
- The fixture has NO parseable routes table. `parse_routes_table` only triggers on a
  `const|let|var routes = …` declaration, so the fixture's swap map is named `swap`
  (NOT `routes`). `parse_routes_table` returns None → `expected = _first_path_segment(route)`.
- `_first_path_segment("#/page-a")` = `_href_target_id("#/page-a")` = `"page-a"` (split on
  `/`; the hyphen is preserved — same rule that keeps `certificate-list` whole). So for the
  anchor `#/page-a`, `expected = "page-a"`.
- The router activates the WRONG real section: `#/page-a` -> activates `page-b`. The active
  section read returns `"page-b"` (a real section id, so activated is NON-null).
- Result: `activated="page-b"` != `expected="page-a"`, activated non-null → wrong-section.

AVOID the trap (do NOT do this): a page-id-valued object literal NAMED `routes` mapping
`page-a -> page-b` would be parsed by `parse_routes_table`, `resolve_route("#/page-a")` would
return `"page-b"` == activated → render calls it CORRECT (not wrong-section). Naming the map
`swap` (not `routes`) is what keeps the mis-route honest. This is why the fixture MUST NOT
contain any `const|let|var routes` declaration.
</design_constraint>

<tasks>

<task type="auto">
  <name>Task 1: Author the mis-route.html wrong-section fixture</name>
  <files>backend/tests/agents/fixtures/mis-route.html</files>
  <action>
Create a minimal, hand-authored single-file SPA modeled on blank-nav.html (the closest
analog). Requirements, per the design_constraint above (construction (a)):

- Exactly three real page sections, each a `<section data-page="…" class="page-section">` with
  ids `dashboard`, `page-a`, `page-b`. The `dashboard` section starts with class
  `page-section is-active`; the other two start inactive. Use CSS `.page-section{display:none}`
  and `.page-section.is-active{display:block}` (same shape as blank-nav.html) so the render
  read sees a real active section.
- Nav is plain anchors: `<a href="#/dashboard">`, `<a href="#/page-a">`, `<a href="#/page-b">`.
  The anchors carry NO `data-page` attribute (unlike blank-nav.html, whose anchors deliberately
  do) — so they are not counted as page sections and cannot be coerced by the active-section
  read. Do not give them a class the read/coverage selectors care about; plain anchors are fine.
- A scoped hashchange router driven by a map literal named `swap` (NOT `routes` — see
  design_constraint): `swap = { dashboard: 'dashboard', 'page-a': 'page-b', 'page-b': 'page-a' }`.
  On `hashchange` (and once on load) the router: parses the first path segment `id` from
  `location.hash`, computes `target = swap[id] || id`, removes `is-active` from every
  `section.page-section`, then adds `is-active` to the ONE
  `section.page-section[data-page="<target>"]` (a REAL section, so `activated` is non-null).
  Scope the removal/add to `section.page-section` only (never to nav anchors) so the read
  returns a real section id.
- There MUST be no `const routes` / `let routes` / `var routes` declaration anywhere in the
  file. Add a short HTML comment explaining that the map is named `swap` (not `routes`)
  on purpose so `parse_routes_table` returns None and `expected` falls back to the
  first-path-segment — making the swap unambiguously wrong-section.

Net render_check behavior when driven live: `#/dashboard` -> activated `dashboard` == expected
`dashboard` (CORRECT); `#/page-a` -> activated `page-b` != expected `page-a` (WRONG-SECTION);
`#/page-b` -> activated `page-a` != expected `page-b` (WRONG-SECTION). available=True, ok=False,
zero null/blank, zero coverage findings (3 sections discovered/exercised).
  </action>
  <verify>
    <automated>cd backend && python3.11 -c "import re,pathlib; t=pathlib.Path('tests/agents/fixtures/mis-route.html').read_text(); assert not re.search(r'\b(const|let|var)\s+routes\b', t), 'MUST NOT declare a routes table (would bless the mis-route)'; assert t.count('data-page=') >= 3, 'need >=3 real sections'; assert 'swap' in t and 'hashchange' in t, 'need a swap router'; print('mis-route.html OK')"</automated>
  </verify>
  <done>mis-route.html exists with 3 real `<section data-page>` sections, a `swap` hashchange router that activates the wrong section for page-a/page-b and the correct section for dashboard, and NO `routes` table declaration.</done>
</task>

<task type="auto">
  <name>Task 2: Add scenario 15 — wrong-section end-to-end + committed + honest-wording asserts</name>
  <files>backend/tests/agents/test_nav_coverage.py</files>
  <action>
Add a `_MIS_ROUTE_FIXTURE` path constant next to the existing `_BLANK_FIXTURE` constant
(`Path(__file__).parent / "fixtures" / "mis-route.html"`, resolved), with a short comment
naming it fixture C (round-5 wrong-section, construction (a): no routes table -> expected is
first-segment; router swaps to a real-but-wrong section).

Add a new "Scenario 15 — round-5 wrong-section end-to-end" section with three tests:

1. `test_scenario15_mis_route_fixture_is_committed` — assert `_MIS_ROUTE_FIXTURE.is_file()`
   (git-tracked committed fixture, mirroring scenario 13/14's committed-file asserts).

2. `test_scenario15_wrong_section_fires_end_to_end(tmp_path)` — browser-gated via the existing
   `_render_available(tmp_path)` helper (skip if Chromium/Playwright unavailable; Chromium IS
   present locally so this runs LIVE). Run `asyncio.run(render_check(_MIS_ROUTE_FIXTURE))` and
   assert:
   - `rr.available is True` and `rr.ok is False`.
   - The wrong-section branch fires end-to-end: at least one NavResult with
     `n.activated is not None and n.activated != n.expected`. Spot-check the specific
     mis-route: a NavResult with `n.href == "#/page-a"` whose `n.activated == "page-b"` and
     `n.expected == "page-a"` (and `n.ok is False`).
   - Distinguished from the round-4 blank path: the null/blank count is 0 —
     `[n for n in rr.nav_results if n.activated is None] == []`.
   - Not a blanket-fail: at least one CORRECT route — `any(n.ok and n.activated == n.expected
     for n in rr.nav_results)` (the `#/dashboard` route). Optionally spot-check the dashboard
     NavResult activated `"dashboard"`.
   - No false coverage-0: `not rr.coverage_errors`.

3. `test_scenario15_wrong_section_dead_nav_wording` — OFFLINE / pure (no browser gate), proving
   the honest wrong-section message path. Import `_dead_nav_line` from
   `agents.execution_engine.engine` (the same module scenario 4c/11 already import from) and a
   synthetic `NavResult(href="#/page-a", activated="page-b", ok=False, expected="page-a")`;
   assert `_dead_nav_line(nav) == "dead nav link: '#/page-a' activated 'page-b' but expected 'page-a'"`.
   This exercises the else-branch of `_dead_nav_line` (the wrong-section wording) that round-4
   only covered for the blank case in the fix-loop selection test.

EXECUTION GUARD (per plan constraints): this is TEST-ONLY and ADDITIVE. Do NOT modify
render_check.py / static_check.py / route_table.py / engine.py. If test (2) shows the
wrong-section branch does NOT actually fire end-to-end — e.g. `rr.ok is True`, OR no NavResult
has `activated is not None and activated != expected`, OR page-a activates None/`page-a` — STOP
immediately, do NOT alter production code or weaken the assertion, and report it as a real bug
in render_check (a genuine defect, not a test gap).
  </action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_nav_coverage.py -q -k scenario15</automated>
  </verify>
  <done>Scenario 15's three tests pass. The browser-gated test runs LIVE (Chromium present) and proves render_check(mis-route) yields available=True, ok=False, ≥1 wrong-section NavResult (page-a -> activated page-b, expected page-a), zero null/blank, ≥1 correct (dashboard); the offline test proves the honest wrong-section `_dead_nav_line` wording.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (none introduced) | TEST-ONLY + ADDITIVE change: one hand-authored local HTML fixture loaded via `file://` in the already-sandboxed headless Chromium harness, plus one test scenario. No new inputs cross any runtime trust boundary; no production code path changes. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-kml-01 | Tampering | mis-route.html fixture (JS runs in headless Chromium during tests) | accept | Local, hand-authored, git-tracked static file with no network/exec/secrets; run only inside the existing `--no-sandbox` render_check test harness against `file://`. No new attack surface vs. blank-nav.html / A / B fixtures. |
| T-kml-SC | Tampering | npm/pip/cargo installs | accept | No package installs — no dependency changes; nothing to audit. |
</threat_model>

<verification>
Offline verification only (full pytest hangs on Chromium/Bedrock/Postgres gates — verify with
the targeted suite). Chromium IS present locally, so the new scenario-15 wrong-section
assertion runs LIVE (not skipped).

1. Targeted suite (nav-coverage + characterization goldens), from `backend/`:
   `python3.11 -m pytest tests/agents/test_nav_coverage.py tests/agents/test_characterization_*.py -q`
   Expect: all nav_coverage tests pass (existing 36 + new scenario 15); the 4 stable
   characterization goldens (prototype, od_prototype, prototype_revision, app_builder) pass
   byte/event-identical with **NO SNAPSHOT_UPDATE** (INV-3). `test_characterization_od_ppt.py`
   is the KNOWN pre-existing/environmental baseline failure — leave it as-is, do NOT touch it.
2. Import contracts: `/opt/homebrew/bin/lint-imports` → 4 kept / 0 broken (no import/code
   change, so this must be unchanged).
3. No-production-change proof: `git status --porcelain` shows ONLY
   `backend/tests/agents/fixtures/mis-route.html` (new) and
   `backend/tests/agents/test_nav_coverage.py` (modified) — no diff to render_check.py,
   static_check.py, route_table.py, or engine.py.
</verification>

<success_criteria>
- `mis-route.html` (fixture C) exists, git-tracked, with 3 real sections, a `swap` (not
  `routes`) hashchange router, and NO routes-table declaration.
- Scenario 15 passes: render_check(mis-route) is available=True, ok=False; ≥1 NavResult has
  `activated is not None AND activated != expected` (wrong-section branch fires end-to-end for
  the first time against Chromium); null/blank count == 0; ≥1 correct (dashboard); the honest
  `_dead_nav_line` wrong-section wording is asserted offline.
- INV-3 holds: 5 characterization goldens green, NO SNAPSHOT_UPDATE; od_ppt known-failing left
  untouched. lint-imports 4/0.
- Zero production code changes (render_check / static_check / route_table / engine untouched).
- If the wrong-section branch does NOT fire end-to-end, the executor STOPPED and reported a
  real render_check bug instead of weakening the test or editing production code.
</success_criteria>

<output>
Create `.planning/quick/260701-kml-round-5-fixture-c-wrong-section-mis-rout/260701-kml-SUMMARY.md` when done.
</output>
