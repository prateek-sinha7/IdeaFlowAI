---
phase: quick-260701-hqa
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/agents/render_check.py
  - backend/agents/execution_engine/engine.py
  - backend/tests/agents/test_phase5_fixloop_selection.py
  - backend/tests/agents/fixtures/blank-nav.html
  - backend/tests/agents/test_nav_coverage.py
autonomous: true
requirements: [HQA-1, HQA-2, HQA-3, HQA-4]
must_haves:
  truths:
    - "render_check reads the active PAGE SECTION only — never a nav/anchor control — and returns None when no section is active"
    - "The full A fixture reports 17/17 nav routes dead (INCLUDING #/dashboard) — no coercion of null to a nav-link name"
    - "The fixed B fixture still passes render 17/17 and the 4 stable goldens raise zero new render/static issues (INV-3)"
    - "A dead nav's fix-loop message names its ACTUAL failure class: blank (activated is None) vs wrong-section (activated != expected)"
    - "A blank-nav.html regression fixture proves available=True, ok=False, and EVERY NavResult.activated is None"
  artifacts:
    - path: "backend/app/agents/render_check.py"
      provides: "nav-excluding active-section READ selector in _exercise_route (returns None on no section)"
      contains: ":not(.nav-link)"
    - path: "backend/agents/execution_engine/engine.py"
      provides: "pure honest dead-nav message helper used by _select_issues_to_fix + residual assembly"
      contains: "activated NOTHING"
    - path: "backend/tests/agents/fixtures/blank-nav.html"
      provides: "must-fail blank-page fixture (nav never activates a section)"
    - path: "backend/tests/agents/test_nav_coverage.py"
      provides: "repinned A render count (17/17 dead) + blank-nav assertions"
    - path: "backend/tests/agents/test_phase5_fixloop_selection.py"
      provides: "repinned honest dead-nav wording + wrong-section branch coverage"
  key_links:
    - from: "backend/app/agents/render_check.py::_exercise_route"
      to: "NavResult.activated"
      via: "eval_on_selector over the nav-excluded active-section selector"
      pattern: "eval_on_selector"
    - from: "backend/agents/execution_engine/engine.py::_dead_nav_line"
      to: "_select_issues_to_fix + _run_validation_fix_loop residual"
      via: "single pure message formatter (blank vs wrong-section branch)"
      pattern: "activated NOTHING|but expected"
---

<objective>
Round 4 (fast follow) — make `render_check` HONEST about *why* a route fails. Today the
active-section READ in `_exercise_route` uses the selector `"[data-page].is-active, .section.is-active"`,
which on the full A fixture matches a NAV ANCHOR (`<a class="nav-link is-active" data-page="dashboard">`)
because A's broken unscoped router strips `is-active` from every `<section>` and pins it on a
nav `<a>` instead. The read therefore COERCES a blank page (no section active → should be null)
into the name `'dashboard'`, which (1) hands the fix-loop the WRONG defect signal ("route
activated dashboard" → a matchRoute-fallback hunt, when A's real bug is "activates NOTHING /
blank") and (2) SPURIOUSLY PASSES `#/dashboard` on A (coerced `'dashboard'` == expected
`'dashboard'` → A reports 16/17 dead instead of 17/17 — a residual silent-pass).

This plan is the LAST cleanup of the silent-pass class (it does NOT flip the A/B verdict —
round-3 route-resolution already makes A fail / B pass). It:
- ITEM 1: changes the active-section READ to match only a real page section and EXCLUDE nav/anchor
  controls; no section active → return None (never coerce to a name).
- ITEM 2: words the dead-nav fix-loop message by its ACTUAL failure class (blank vs wrong-section).
- ITEM 3: adds a blank-nav.html must-fail regression fixture (the guard that would have caught this).
- ITEM 4: repins the A render count (16 → 17 dead, measured LIVE) and re-affirms B=pass / goldens clean.

Purpose: null honesty — a blank page reports as blank (null), not as a fabricated nav-link name.
Output: nav-excluded READ + honest message helper + blank-nav fixture + repinned regression.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/IMPLEMENTATION-REGISTER.md
@.planning/quick/260701-go2-round-3-route-table-aware-nav-validators/260701-go2-SUMMARY.md

# The subject under change
@backend/app/agents/render_check.py
@backend/agents/execution_engine/engine.py

# The tests that pin behavior (wording + measured counts)
@backend/tests/agents/test_phase5_fixloop_selection.py
@backend/tests/agents/test_nav_coverage.py

# Fixtures (A=full, B=fixed) referenced by the pins
# backend/tests/agents/fixtures/imc-inventory-certificate-management-full.html   (A)
# backend/tests/agents/fixtures/imc-inventory-certificate-management-fixed.html  (B)
</context>

<constraints>
INV-1: no `if pipeline_type ==` / workflow-name branch. INV-3: the 4 stable characterization
goldens (prototype, od_prototype, prototype_revision, app_builder) stay byte/event-identical with
NO SNAPSHOT_UPDATE; od_ppt is KNOWN pre-existing/environmental (leave it — it fails identically to
baseline via `test_od_ppt_event_snapshot`, NOT a new break). INV-12: edit render_check.py +
engine.py IN PLACE; the only new file is the fixture (additive). INV-13: no deepagents edits.
Import boundary unchanged — `/opt/homebrew/bin/lint-imports` stays 4 kept / 0 broken.
Verify OFFLINE ONLY (full pytest hangs on Chromium/Bedrock/Postgres gates) using the targeted
suite below; Chromium IS present locally, so the browser-gated render pins are measured LIVE
(not stubbed). No migrations, no new dependency, no FE change.

CRITICAL WATCH (do not weaken the A=blank assertion to make this pass):
- The new nav-exclusion selector MUST keep B at render 17/17 pass and MUST keep the 4 stable
  goldens clean. B's real sections are `.page-section[data-page]` (proven present: 21 `page-section`,
  3 `.section`); the trimmed fixture's sections are `.page-section[data-page]` and its nav is
  `<div class="nav-link" onclick>` with NO `data-page` (so it never matched the read anyway).
  If B or a golden regresses, the selector is TOO AGGRESSIVE → fix the selector; never relax the
  A=17/17-dead expectation.
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: render null-honesty READ + honest dead-nav message wording + unit repins</name>
  <files>backend/app/agents/render_check.py, backend/agents/execution_engine/engine.py, backend/tests/agents/test_phase5_fixloop_selection.py</files>
  <behavior>
    - render_check `_exercise_route` on a page where NO `<section>` is active returns None (never a nav-link's data-page name), even when a nav `<a data-page>` carries `is-active`.
    - render_check `_exercise_route` on a page with a real active `.page-section[data-page]` still returns that section's data-page id (B + trimmed fixture path unchanged).
    - engine `_dead_nav_line(nav)` when `nav.activated is None` → contains `activated NOTHING` and `blank page`; when `nav.activated` is a real-but-wrong id → contains `activated '<activated>' but expected '<expected>'`.
    - `_select_issues_to_fix` still emits static → console → page-error → dead-nav → coverage in that ORDER; a live nav (ok=True) still contributes no line.
    - The 4 stable characterization goldens emit ZERO dead-nav lines (no nav in goldens) → the wording change is inert for INV-3.
  </behavior>
  <action>
ITEM 1 — render reads the active PAGE SECTION, never a nav control, returns None when none.
In `backend/app/agents/render_check.py::_exercise_route` change ONLY the final active-section
READ (currently `eval_on_selector("[data-page].is-active, .section.is-active", "el => el.getAttribute('data-page')")`).
Replace the selector string with one that matches a real page section and EXCLUDES nav/anchor
elements: `[data-page].is-active:not(a):not(.nav-link):not(.nav-item):not(.nav-submenu-link), .page-section.is-active, .section.is-active`.
Rationale: the `:not(...)` set drops A's coerced `<a class="nav-link is-active">` /
`<a class="nav-submenu-link is-active">`; the union clauses (`.page-section.is-active`,
`.section.is-active`) still read a real section that carries those classes. When nothing matches,
Playwright `eval_on_selector` raises → the EXISTING `except → return None` yields null. NEVER add
any fallback that coerces to a name. Keep `el.getAttribute('data-page')` unchanged. Do NOT touch:
the `from_anchor` click/hash-drive branch, the `settle_ms` wait, the two `available=False` early
returns, the round-2 un-dedup + `${...}` exclusion + section-id classification query (line ~297),
or the round-3 route-resolution `expected` — ONLY this READ selector changes.

ITEM 1 SECONDARY (nav-exclusion on the COVERAGE section-count denominator — measure-gated, safe).
In `render_check()` the coverage denominator query `eval_on_selector_all("[data-page]", "els => els.length")`
(feeds `_coverage_finding(section_count, discovered)`) counts nav `<a data-page>` too. Apply the
same nav exclusion — query `[data-page]:not(a):not(.nav-link):not(.nav-item):not(.nav-submenu-link)`.
This is provably inert (coverage only fires when `discovered == 0`, and any nav-carrying-data-page
page has `discovered > 0`), but per the constraint it is measure-gated: if the T2 verify shows ANY
golden/fixture/pin drift, revert this ONE query back to the broad `[data-page]` and note the skip
in the SUMMARY. Do NOT touch the section-id CLASSIFICATION query (`_check_nav`, line ~297) — leaving
it broad preserves the go2-measured discovery/dedup denominator (`_FULL_RENDER_NAV_TOTAL=17`).

ITEM 2 — honest fix-loop failure text (distinguish blank vs wrong-section).
In `backend/agents/execution_engine/engine.py` add a pure module-level helper beside
`_select_issues_to_fix` (e.g. `_dead_nav_line(nav) -> str`): when `getattr(nav, "activated", None)
is None` return `f"dead nav link: '{nav.href}' activated NOTHING (no <section data-page> became
active — blank page)"`; otherwise return `f"dead nav link: '{nav.href}' activated
'{nav.activated}' but expected '{getattr(nav, 'expected', None)}'"`. Replace the dead-nav append
inside `_select_issues_to_fix` (the `f"dead nav link: clicking '{nav.href}' activated no <section
data-page>"` branch under the `if not nav.ok` loop) with `selected.append(_dead_nav_line(nav))`.
Replace the BUILD residual assembly in `_run_validation_fix_loop` (the generator
`f"dead nav link: {n.href} (no section activated)" for n in rres.nav_results if not n.ok`) with
`_dead_nav_line(n) for n in rres.nav_results if not n.ok`. Keep line ORDER and the
always-included-hard-breakage semantics (dead nav stays in the render-break group, unconditional).
The two now share ONE formatter so blank/wrong-section text can never diverge. INV-3 note: the 4
stable goldens produce NO dead nav (no onclick/navigateTo, single/no section — proven by
test_scenario8), so this wording branch never fires on the golden pipeline → goldens stay
byte/event-identical.

REPIN the unit wording (test_phase5_fixloop_selection.py). Its `_dead_nav(href)` builds
`NavResult(href, activated=None, ok=False)` → the NEW blank message. Update the 5 pinned strings
(lines ~129, ~151, ~225, ~288, ~296) from `dead nav link: clicking '<href>' activated no <section
data-page>` to `dead nav link: '<href>' activated NOTHING (no <section data-page> became active —
blank page)`. Rename/repurpose the docstring of `test_build_order_is_byte_identical_to_legacy_error_lines`
so it pins the NEW canonical wording+order (the intentional honesty change — this is fix-message
text, not a golden/event). ADD one NEW pure case proving the wrong-section branch: build
`NavResult(href="#/x", activated="settings", ok=False, expected="dashboard")`, feed it via
`_select_issues_to_fix` (or `_dead_nav_line` directly), and assert the line contains
`activated 'settings' but expected 'dashboard'`.
  </action>
  <verify>
    <automated>cd backend &amp;&amp; python3.11 -m pytest tests/agents/test_phase5_fixloop_selection.py tests/agents/test_phase5_revision_validation.py -q</automated>
    <automated>cd backend &amp;&amp; python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py -q</automated>
    <automated>cd backend &amp;&amp; grep -q "activated NOTHING" agents/execution_engine/engine.py &amp;&amp; grep -q ":not(.nav-link)" app/agents/render_check.py &amp;&amp; echo OK-ITEM1-2</automated>
  </verify>
  <done>
    - `_exercise_route` READ selector excludes `a`/`.nav-link`/`.nav-item`/`.nav-submenu-link`; no-section → None (no name coercion added).
    - `_dead_nav_line` is a single pure helper used by BOTH `_select_issues_to_fix` and the residual assembly; blank vs wrong-section branches produce distinct honest text.
    - test_phase5_fixloop_selection.py: 5 wording pins updated + 1 new wrong-section case; suite green.
    - INV-3: 4 stable goldens byte/event-identical, NO SNAPSHOT_UPDATE env set.
  </done>
</task>

<task type="auto">
  <name>Task 2: blank-nav must-fail fixture + repin A render (16→17 dead, LIVE) + regression</name>
  <files>backend/tests/agents/fixtures/blank-nav.html, backend/tests/agents/test_nav_coverage.py</files>
  <action>
ITEM 3 — blank-nav.html must-fail fixture (the guard that would have caught this today).
Create `backend/tests/agents/fixtures/blank-nav.html`: a SMALL multi-section hash-router SPA that
reproduces A's defect class — its nav routes NEVER activate a `<section data-page>`; instead the
router adds `is-active` to a nav `<a data-page>` (or no-ops on the section). Include: a
`<section data-page="dashboard" class="is-active">` initially active; a `<section data-page="reports">`;
a nav with `<a class="nav-link" href="#/dashboard" data-page="dashboard">` and
`<a class="nav-link" href="#/reports" data-page="reports">`; a `hashchange` handler that, on
navigation, removes `is-active` from ALL `[data-page]` and then adds it to the matching nav
`<a data-page>` (NOT the section) — so after any route, NO section is active but a nav anchor is.
This mimics A's unscoped-selector bug in ~25 lines. Keep it minimal.

ITEM 4 — repin A render + blank-nav assertions (test_nav_coverage.py).
(a) Add `_BLANK_FIXTURE = (Path(__file__).parent / "fixtures" / "blank-nav.html").resolve()` and a
new browser-gated scenario (guard with `_render_available(tmp_path)`, else skip): render_check on
`_BLANK_FIXTURE` → `available is True`, `ok is False`, and EVERY NavResult has `activated is None`
(assert `all(n.activated is None for n in rr.nav_results)` and `rr.nav_results` non-empty),
INCLUDING the `#/dashboard` route (assert the dashboard NavResult exists and its `activated is None`
and `ok is False`) — proving no coercion to a nav-link name.
(b) Repin the A count. MEASURE LIVE (Chromium present): run render_check on the full A fixture and
read `len([n for n in rr.nav_results if not n.ok])`. Expected value is 17 (round-3 was 16 because
`#/dashboard` spuriously passed via coercion; null-honesty makes it dead). Update
`_FULL_RENDER_SIDEBAR_DEAD` from 16 to the MEASURED value and refresh its inline comment
(drop "only dashboard is ok" → note "all 17 dead — #/dashboard no longer coerced to a nav-link
name"). Leave `_FULL_RENDER_NAV_TOTAL = 17` (discovery denominator untouched) and
`_FULL_STATIC_RENDER_OVERLAP = 2` (dashboard has a REAL section → it is NOT a static dead target,
so adding it to render-dead targets does not change the overlap — confirm this holds when the
overlap test runs; if the measured overlap differs, STOP and investigate rather than blindly
repinning).
(c) Re-affirm the tier verdicts on the SAME run: B (`_FIXED_FIXTURE`) still render 17/17 pass
(test_scenario13_B_passes_render) and A still fails via render (test_scenario13_A_fails_via_render).
Do NOT weaken any A=blank assertion to satisfy the pin — if B or a golden regresses, the ITEM 1
selector is too aggressive; fix the selector.
  </action>
  <verify>
    <automated>cd backend &amp;&amp; python3.11 -m pytest tests/agents/test_nav_coverage.py -q</automated>
    <automated>cd backend &amp;&amp; python3.11 -m pytest tests/agents/test_route_table.py tests/agents/test_static_check.py tests/agents/test_validators.py -q</automated>
    <automated>cd backend &amp;&amp; python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py -q</automated>
    <automated>test -f backend/tests/agents/fixtures/blank-nav.html &amp;&amp; /opt/homebrew/bin/lint-imports</automated>
  </verify>
  <done>
    - blank-nav.html exists; the blank-nav scenario asserts available=True, ok=False, every NavResult.activated is None (incl. #/dashboard dead) — Chromium present so it runs LIVE (not skipped).
    - `_FULL_RENDER_SIDEBAR_DEAD` repinned to the LIVE-measured value (expected 17); `_FULL_RENDER_NAV_TOTAL=17` and `_FULL_STATIC_RENDER_OVERLAP=2` still hold.
    - test_nav_coverage.py fully green LIVE; B render 17/17 pass and A fails via render both re-affirmed.
    - INV-3: 4 stable goldens byte/event-identical (NO SNAPSHOT_UPDATE); lint-imports 4 kept / 0 broken.
    - od_ppt NOT touched (known pre-existing/environmental — fails identically to baseline).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| prototype HTML → headless Chromium | render_check loads a run-produced HTML file it already opens; no new external input crosses here |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-hqa-01 | Tampering | render_check `_exercise_route` selector | accept | CSS selector over an already-loaded local file; no eval of untrusted expressions beyond the existing `getAttribute('data-page')` read (unchanged) |
| T-hqa-02 | Information disclosure | blank-nav.html fixture | accept | static local test asset, no data/PII, no network |
| T-hqa-SC | Tampering | npm/pip/cargo installs | n/a | no package installs in this plan (test/validator logic + one static fixture only) |
</threat_model>

<verification>
Offline targeted suite (Chromium present → browser-gated render pins run LIVE):
- `cd backend && python3.11 -m pytest tests/agents/test_nav_coverage.py tests/agents/test_route_table.py tests/agents/test_phase5_fixloop_selection.py tests/agents/test_phase5_revision_validation.py tests/agents/test_static_check.py tests/agents/test_validators.py -q`
- INV-3 (NO SNAPSHOT_UPDATE env): `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py -q`
- `/opt/homebrew/bin/lint-imports` → 4 kept / 0 broken.
- SC-001/INV-1 sanity: no `deepagents` reference and no `if pipeline_type ==` branch introduced in the changed sources.
- od_ppt: expected to fail IDENTICALLY to baseline (pre-existing skills-asset/event-golden drift) — do not "fix", confirm it is the same baseline failure.
</verification>

<success_criteria>
- render_check's active-section READ never coerces a blank page to a nav-link name — no section active → None.
- A (full fixture) render: 17/17 dead INCLUDING `#/dashboard` (LIVE-measured, repinned); B render: 17/17 pass; 4 stable goldens byte/event-identical.
- Fix-loop dead-nav message states the actual failure class (blank vs wrong-section) via one shared pure helper.
- blank-nav.html regression fixture asserts available=True, ok=False, every NavResult.activated is None.
- lint-imports 4/0; no migration; no new dependency; no FE change; render_check + engine edited IN PLACE (INV-12).
</success_criteria>

<output>
Create `.planning/quick/260701-hqa-round-4-render-blank-to-null-honesty-sto/260701-hqa-SUMMARY.md` when done.
</output>
