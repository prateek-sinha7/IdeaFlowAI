---
phase: quick-260701-erg
plan: 01
type: execute
wave: 1
depends_on: []
autonomous: true
requirements: [RENDER-UNDEDUP, RENDER-SETTLE-KNOB, STATIC-ROUTER-DEAD, REQUIRE-RENDER-LOADBEARING, GOLDEN-KNOB-PIN, FULL-FILE-REGRESSION, INV-3-GUARD]
files_modified:
  - backend/app/agents/render_check.py
  - backend/app/agents/static_check.py
  - backend/agents/workflows/prototype/workflow.yaml
  - backend/agents/workflows/prototype_revision/workflow.yaml
  - backend/tests/agents/_scripted_model.py
  - backend/tests/agents/fixtures/imc-inventory-certificate-management-full.html
  - backend/tests/agents/test_nav_coverage.py

must_haves:
  truths:
    - "render_check reports EACH concrete malformed route (first-path-segment target has NO matching <section data-page>) as its OWN NavResult (ok=False) instead of collapsing same-first-segment malformed routes to one representative; routes that resolve to a REAL section still dedupe to one representative."
    - "render_check does NOT exercise template-literal routes (containing '${'): they are counted as DISCOVERED (so coverage-0 never false-fires) but produce no browser NavResult — left to static_check."
    - "render_check's nav settle wait is configurable (nav_settle_ms param + _NAV_SETTLE_MS module constant, default 50); the producer available/ok/note classification is byte-unchanged (only Playwright-import + Chromium-launch failures stay available=False)."
    - "static_check emits a DISTINCT 'router-dead nav link' issue when a nav route target has a <section data-page> but NO routes-map entry — ONLY when a `const routes={}` map is present (same guard as the routes-map-complete check); a target with no section stays the existing plain dead-link, not double-reported."
    - "prototype-build step and prototype-revision-agent step both declare require_render: true; the revision step (gates:[validation]) genuinely fails closed on a browserless render (html_render P0 -> ValidationGate -> GATE_BLOCK); the build step (gates:[]) records the skip + declares intent but does not hard-block (documented, no gate added)."
    - "The 5 characterization goldens stay byte/event-identical with NO SNAPSHOT_UPDATE because the offline harness pins require_render=False on every compiled step for golden runs (the require_render=False semantics the goldens were recorded at; Chromium-independent)."
    - "The full 414KB imc file is committed as a marked regression fixture (alongside the retained trimmed fixture); a regression test pins the FINAL measured static dead-link + router-dead counts, the render sidebar-dead count, and the measured overlap, AND asserts a fake render available=False + require_render=true fails closed (one P0)."
    - "static_check + render_check raise ZERO NEW issues on the 3 golden templates (prototype/od_prototype/prototype_revision); od_ppt stays its KNOWN pre-existing/environmental failure (untouched, no SNAPSHOT_UPDATE)."
  artifacts:
    - path: "backend/app/agents/render_check.py"
      provides: "Per-route un-dedup for malformed targets + `${...}` exercise-exclusion + configurable nav settle wait"
      contains: "nav_settle_ms"
    - path: "backend/app/agents/static_check.py"
      provides: "routes-map RESOLUTION cross-check emitting a distinct router-dead nav-link issue"
      contains: "router-dead"
    - path: "backend/agents/workflows/prototype/workflow.yaml"
      provides: "require_render: true on the prototype-build task_loop step"
      contains: "require_render: true"
    - path: "backend/agents/workflows/prototype_revision/workflow.yaml"
      provides: "require_render: true on the revision step (genuine fail-closed via gates:[validation])"
      contains: "require_render: true"
    - path: "backend/tests/agents/_scripted_model.py"
      provides: "Golden-run harness pin: compiled.steps[*].require_render = False in _patched_compile_for_run"
      contains: "require_render"
    - path: "backend/tests/agents/fixtures/imc-inventory-certificate-management-full.html"
      provides: "The full 414KB comprehensive regression fixture (marked)"
    - path: "backend/tests/agents/test_nav_coverage.py"
      provides: "Un-dedup + router-dead + require_render-manifest + full-file final-count regression + fail-closed scenarios"
  key_links:
    - from: "backend/app/agents/render_check.py"
      to: "the DOM section-id set (data-page attribute values)"
      via: "_check_nav queries [data-page] VALUES to classify a candidate target real-vs-malformed"
      pattern: "data-page"
    - from: "backend/app/agents/static_check.py"
      to: "_extract_routes_map keys + _href_target_id + section_ids"
      via: "routes-map resolution cross-check (guarded by routes_map is not None)"
      pattern: "router-dead"
    - from: "backend/agents/workflows/prototype_revision/workflow.yaml"
      to: "backend/agents/capabilities/gates/validation.py"
      via: "Step.require_render -> DeliverableContext.require_render -> html_render P0 -> ValidationGate GATE_BLOCK"
      pattern: "require_render"
    - from: "backend/tests/agents/_scripted_model.py"
      to: "the 5 characterization goldens"
      via: "_patched_compile_for_run pins require_render=False so golden runs are knob/Chromium-independent"
      pattern: "compile_for_run"
    - from: "backend/tests/agents/test_nav_coverage.py"
      to: "backend/tests/agents/fixtures/imc-inventory-certificate-management-full.html"
      via: "final-count regression assertions + fake-render fail-closed"
      pattern: "imc-inventory-certificate-management-full"
---

<objective>
Round 2 of prototype-validator hardening. Builds on the ALREADY-LANDED 260701-bob work (commits 4b65c66c / 242a1e38 / 7ff4b6e5) — do NOT re-do it, EXTEND it in place (INV-12). Four user-approved follow-ups:

- ITEM 3 (render): un-dedup MALFORMED routes so each concrete dead route (first-path-segment target has no `<section data-page>`) gets its OWN NavResult (real-section routes still dedupe to one representative); exclude `${...}` template-literal routes from browser exercise; make the 50ms settle wait configurable.
- ITEM 4 (static): a browserless routes-map RESOLUTION cross-check — a nav route whose target has a `<section>` but NO routes-map entry is a distinct "router-dead" issue (only when a routes map is present).
- ITEM 2 (require_render load-bearing): flip require_render:true on the prototype BUILD step + the prototype_revision step, and RESOLVE the #1 INV-3 collision (below).
- ITEM 1 (full-file regression): commit the full 414KB imc file as a marked regression fixture and pin the FINAL counts (after items 3+4) plus a fail-closed assertion.

Purpose: catch the remaining runtime-navigation escape hatches (multiple malformed detail routes collapsing to one report; browserless router-dead links) and make require_render genuinely load-bearing, WITHOUT any new false-positive on the golden templates.
Output: hardened render_check + static_check, require_render:true on both prototype build + revision manifests with the golden-run collision resolved, a committed full-file regression fixture + final-count/fail-closed regression test.

INVESTIGATION ALREADY DONE (baked into this plan — do NOT re-litigate):
- Chromium IS present locally (verified: render_check on a probe returns available=True). The offline characterization harness (`tests/agents/_scripted_model._drive`) does NOT monkeypatch render_check — it runs render for REAL during golden runs. So a golden run WITH Chromium sees status "ok" regardless of require_render (behavior-neutral); a BROWSERLESS golden run would see "skipped_blocked" if require_render:true → that is the collision.
- ITEM 2 collision resolution CHOSEN = defense-in-depth = manifest flip (production) + harness pin require_render=False (golden runs). Justified in Task 2. This makes the goldens knob- AND Chromium-independent, neutralizing the #1 INV-3 risk entirely; the require_render=true behavior is covered by test_nav_coverage scenarios 4/5, so the goldens do not need to exercise it (NOT a hole).
- Build-step nuance (verified in engine.py + task_loop.py): the prototype BUILD step has gates:[]; its internal `_run_validation_fix_loop` NEVER blocks on a render skip (no :fix thread, no raise), and `TaskLoopStrategy._run_registered_validators` DISCARDS html_render's returned Issues (audit-row side-effect only). So require_render:true on the BUILD step is INV-3-neutral (byte/event-identical with Chromium present AND browserless) and records the skip + declares intent — the GENUINE fail-closed is the prototype_revision step's gates:[validation]. Adding a gate to the build step would emit a gate event → break the event golden → out of scope.
- Current baseline on the FULL 414KB file: static_check = 11 dead-link issues (matches user ground truth static=11), 14 sections, routes map present (1). Items 3+4 WILL change these counts; Task 3 recomputes + pins the FINAL measured values.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/CLAUDE.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/CLAUDE.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.planning/IMPLEMENTATION-REGISTER.md

# Round 1 (EXTEND, do not redo)
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.planning/quick/260701-bob-fix-prototype-validators-render-check-st/260701-bob-SUMMARY.md

# The producers under fix
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/app/agents/render_check.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/app/agents/static_check.py

# The require_render seam (already threaded by round 1)
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/app/agents/validators/html_render.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/capabilities/validators/severity.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/capabilities/gates/validation.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/capabilities/strategies/task_loop.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/workflows/prototype/workflow.yaml
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/workflows/prototype_revision/workflow.yaml

# The golden harness (Task 2 collision resolution)
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/tests/agents/_scripted_model.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/tests/agents/test_nav_coverage.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: ITEM 3 (render per-route un-dedup + settle knob) + ITEM 4 (static routes-map resolution cross-check)</name>
  <files>backend/app/agents/render_check.py, backend/app/agents/static_check.py, backend/tests/agents/test_nav_coverage.py</files>
  <behavior>
    render_check.py (ITEM 3):
    - Configurable settle: add a module constant `_NAV_SETTLE_MS = 50`; add a keyword-only `nav_settle_ms: int = _NAV_SETTLE_MS` param to `render_check(...)`, thread it into `_check_nav(page, *, nav_settle_ms=...)` and `_exercise_route(page, route, from_anchor, *, settle_ms=...)`, and replace the hardcoded `await page.wait_for_timeout(50)` (l.285) with `await page.wait_for_timeout(settle_ms)`. Docstring: note it as the async-router refinement knob. GUARDRAIL: the two `available=False` early returns (Playwright import fail l.140-142; Chromium launch fail l.155-157) and the available/ok/note classification stay byte-identical; default 50 keeps every existing call byte-identical (INV-3).
    - Per-route un-dedup for MALFORMED targets: in `_check_nav`, query the DOM section-id SET (the data-page attribute VALUES, e.g. `page.eval_on_selector_all("[data-page]", "els => els.map(e => e.getAttribute('data-page'))")`) into `section_ids: set[str]`. Classify each discovered candidate by `_first_path_segment(route)`: if the target IS in section_ids (resolves to a real section) keep the existing dedupe (one representative per target); if the target is NOT in section_ids (malformed/dead) give EACH concrete route its own NavResult (do NOT collapse same-first-segment malformed routes) so certificates/901, certificates/create, certificates each report.
    - `${...}` exclusion: any candidate route whose string contains `${` is a template literal — do NOT drive it in the browser (the literal placeholder is not a real id → guaranteed false "dead"); leave it to static_check. It STILL counts as DISCOVERED for coverage (so a page whose only nav is template-literal is not falsely flagged coverage=0), but produces NO NavResult.
    - Coverage: base `_coverage_finding`'s exercised/discovered argument on the count of DISCOVERED nav candidates (real + concrete-malformed + skipped-`${...}`), not merely on `len(nav_results)`, so the `${...}` skip cannot manufacture a false coverage-0. `_nav_ok` / `_coverage_finding` stay pure + offline-testable. RenderResult.ok stays `no console AND no page_errors AND all(n.ok) AND not coverage_errors`.
    static_check.py (ITEM 4):
    - After the existing routes-map-complete block (guarded by `if routes_map is not None:`, l.553), ADD a routes-map RESOLUTION cross-check inside the SAME guard: for each NAV ROUTE target (the anchor `route_hrefs` targets AND the `dynamic_routes` targets, first-path-segment via `_href_target_id`) where the target X has a `<section data-page="X">` (X in section_ids) BUT X is NOT a routes-map key (X not in route_keys) → append a DISTINCT issue worded: `router-dead nav link: '{route}' has a <section data-page="{X}"> but no routes-map entry — the hash router will not reach it`. CONSERVATIVE: only inside the `routes_map is not None` guard (skip entirely when no `const routes={}` — avoids false-positives on prototypes that don't use a map); do NOT emit for a target with NO section (that is already the plain "dead nav link"); dedupe by target so each router-dead target is reported once. This narrows render-reliance for static-only routes but does NOT retire render (map-VALUE→section mismatches + matchRoute-logic bugs still need render).
    Tests (test_nav_coverage.py — extend, do not rewrite):
    - Offline: static_check on a small inline SPA that HAS `const routes={dashboard:'#/dashboard'}` + a `<section data-page="reports">` reachable by a nav route but with NO routes entry → emits the `router-dead nav link` issue for reports; the SAME markup with NO routes map → NO router-dead issue (guard proven).
    - Browser-gated (via `_render_available`): render_check on inline HTML with two malformed same-first-segment routes (`#/x/1`, `#/x/2`, no section x) → TWO NavResults both ok=False (un-dedup proven); a `${id}` route present → NO NavResult for it AND (2 real sections + the discovered `${}` route) → no false coverage-0.
    - Re-affirm INV-3: the existing scenario8 static/render zero-NEW-issues tests still pass (goldens have no `const routes={}` → the router-dead guard is skipped; goldens have no malformed/`${}` nav → un-dedup never fires).
  </behavior>
  <action>Edit backend/app/agents/render_check.py: add `_NAV_SETTLE_MS = 50`; thread a keyword-only `nav_settle_ms` through render_check -> _check_nav -> _exercise_route replacing the literal 50; in _check_nav query the [data-page] attribute VALUES into a section-id set, and rebuild the candidate→representative selection so real-section targets dedupe (one rep) while malformed targets (target not in section_ids) are each kept (un-dedup), skipping `${...}` routes from browser exercise but counting them as discovered for the coverage argument. Preserve the two available=False early returns + the available/ok/note contract verbatim. Edit backend/app/agents/static_check.py: inside the existing `if routes_map is not None:` block, add the routes-map resolution cross-check that emits the distinct `router-dead nav link` issue for a nav route target that has a section but no routes-map key (dedupe per target; never for a no-section target). Do NOT fork a parallel checker (INV-12) — extend the existing single-pass flow. Extend backend/tests/agents/test_nav_coverage.py with the offline router-dead test (present-map vs no-map guard), the browser-gated un-dedup + `${}` test, and confirm the scenario8 INV-3 guards still pass. No fenced code in prose — implement in the source files. Before finishing, run static_check + render_check on the CURRENT trimmed fixture and confirm it is still flagged and the goldens gain zero NEW issues.</action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_static_check.py tests/agents/test_nav_coverage.py -q && python3.11 -c "from app.agents.static_check import static_check; from pathlib import Path; g=static_check(Path('tests/agents/characterization/golden/prototype.html')); assert not any('router-dead' in i for i in g.issues), g.issues; print('golden router-dead=0 OK; issues=%d' % len(g.issues))"</automated>
  </verify>
  <done>test_static_check.py + test_nav_coverage.py green; render_check exposes nav_settle_ms (default 50, byte-identical) and un-dedups malformed routes while skipping `${...}` from exercise; static_check emits `router-dead nav link` only when a routes map is present; the 3 golden templates gain ZERO new static/render issues (router-dead never fires on a map-less golden; un-dedup never fires on nav-less goldens).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: ITEM 2 — require_render:true load-bearing on build + revision manifests + golden-run collision resolution (harness pin)</name>
  <files>backend/agents/workflows/prototype/workflow.yaml, backend/agents/workflows/prototype_revision/workflow.yaml, backend/tests/agents/_scripted_model.py, backend/tests/agents/test_nav_coverage.py</files>
  <behavior>
    Production manifests (the actual hardening):
    - prototype/workflow.yaml: add `require_render: true` to the prototype-build task_loop step (beside `validators: [html_static, html_render]` / `compaction: html_skeleton`). Comment it: the build step (gates:[]) records a distinct validator_skipped audit row + declares render-required intent; it does NOT hard-block (its internal fix-loop never blocks by design — INV-3 parity), so the value is behavior-neutral for the goldens; the GENUINE fail-closed is the prototype_revision gate.
    - prototype_revision/workflow.yaml: change the existing `require_render: false` (l.34) to `require_render: true`; update the comment: this step has gates:[validation], so a browserless render now fails CLOSED (html_render P0 -> ValidationGate block-critical -> GATE_BLOCK) — static can never be sufficient alone when the browser is absent.
    Golden-run collision resolution (defense-in-depth, TEST-ONLY — no production code):
    - _scripted_model.py: in `_patched_compile_for_run` (which already sets `compiled.clarify.mode = "off"`), ALSO loop over `compiled.steps` and set `s.require_render = False` on every step. Comment: pins the goldens to the require_render=False semantics they were RECORDED at, so a browserless golden run never flips a step to skipped_blocked (INV-3 defense-in-depth); the require_render=true production behavior is covered by test_nav_coverage scenarios 4/5, and the goldens are byte/event snapshots orthogonal to the knob (NOT a hole). This makes the 5 goldens knob- AND Chromium-independent — the strongest neutralization of the #1 INV-3 risk (it also holds under resolution (b): with Chromium present, require_render true/false are both status "ok" → identical, so the pin masks nothing real).
    Tests (test_nav_coverage.py — extend):
    - A compiler-level assertion: compile prototype and prototype_revision via the real compiler path and assert the prototype-build Step.require_render is True AND the prototype-revision-agent Step.require_render is True (proves the manifest flip threads through compiler -> Step).
    - Re-affirm scenario 4b (prototype-revision gate → GATE_BLOCK on available=False + require_render=true) still holds (already present) — this is the genuine fail-closed the revision manifest now activates in production.
  </behavior>
  <action>Edit backend/agents/workflows/prototype/workflow.yaml to add `require_render: true` on the prototype-build step with the build-step-nuance comment. Edit backend/agents/workflows/prototype_revision/workflow.yaml to change the revision step's `require_render: false` to `require_render: true` and update its comment to reflect the now-active fail-closed. Edit backend/tests/agents/_scripted_model.py `_patched_compile_for_run` to also pin every `compiled.steps[*].require_render = False` (with the justification comment). Extend backend/tests/agents/test_nav_coverage.py with the compiler assertion that both steps compile to require_render True. Do NOT add a validation gate to the build step (would emit a gate event and break the event golden — out of scope). Do NOT SNAPSHOT_UPDATE. No fenced code in prose.</action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_validators.py tests/agents/test_gates.py tests/agents/test_compiler.py tests/agents/test_phase5_revision_validation.py tests/agents/test_phase5_fixloop_selection.py tests/agents/test_nav_coverage.py -q && /opt/homebrew/bin/lint-imports</automated>
  </verify>
  <done>prototype-build + prototype-revision-agent compile to require_render True; the harness pins require_render=False on golden runs; the 4 stable characterization goldens (prototype/od_prototype/prototype_revision/app_builder) stay byte/event-identical with NO SNAPSHOT_UPDATE; scenario 4b GATE_BLOCK holds; lint-imports 4 kept / 0 broken. (od_ppt stays its KNOWN pre-existing/environmental failure — untouched; verify it fails IDENTICALLY to baseline, proving no NEW breakage.)</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: ITEM 1 — pin the full 414KB file as a marked regression fixture + final-count + fail-closed regression test (depends on Task 1)</name>
  <files>backend/tests/agents/fixtures/imc-inventory-certificate-management-full.html, backend/tests/agents/test_nav_coverage.py</files>
  <behavior>
    - Commit the full file: copy /Users/1000060523/Downloads/imc-inventory-certificate-management.html verbatim into backend/tests/agents/fixtures/imc-inventory-certificate-management-full.html (the comprehensive regression). KEEP the existing trimmed fixture (imc-inventory-certificate-management.html) for the fast unit tests — this is additive.
    - Recompute the FINAL numbers AFTER Task 1: run static_check + render_check on the committed full fixture and MEASURE (a) static dead-link count, (b) static router-dead count, (c) render sidebar-dead count (NavResults with ok=False), (d) the overlap between the static dead/router-dead targets and the render dead targets. These WILL differ from the pre-change baseline (current static dead-link=11; items 3/4 change render's count and likely static's). Record the measured integers in the SUMMARY.
    - Add a regression test in test_nav_coverage.py that PINS the measured integers as EXACT assertions (assert the measured overlap value, NOT "disjoint"). Static assertions run offline; the render assertions are browser-gated via the existing `_render_available` helper and skip cleanly offline.
    - Add the silently-regressing fail-closed assertion (offline): with a FAKE render returning available=False + require_render=true (reuse the `_FakeRunner` + `_Target` stand-ins already in the file), html_render.validate returns exactly one P0 (the path FAILS CLOSED / would block) rather than passing — proving static-alone can never silently substitute for an absent browser.
  </behavior>
  <action>Copy the full 414KB file to backend/tests/agents/fixtures/imc-inventory-certificate-management-full.html (create nothing else; keep the trimmed fixture). In backend/tests/agents/test_nav_coverage.py add a `_FULL_FIXTURE` path constant and a regression test: measure then PIN static_check dead-link + router-dead counts and (browser-gated) render_check sidebar-dead count + the measured overlap as exact integers; add the offline fake-render available=False + require_render=true fail-closed assertion reusing the existing _FakeRunner/_Target helpers. Run the FULL targeted offline suite + lint-imports. No fenced code in prose — implement in the test file. Record the measured final counts in the SUMMARY.</action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_static_check.py tests/agents/test_validators.py tests/agents/test_gates.py tests/agents/test_phase5_fixloop_selection.py tests/agents/test_phase5_revision_validation.py tests/agents/test_compiler.py tests/agents/test_nav_coverage.py -q && /opt/homebrew/bin/lint-imports</automated>
  </verify>
  <done>The full 414KB fixture is committed alongside the trimmed one; the regression test pins the measured final static dead-link + router-dead counts, render sidebar-dead count, and the exact overlap; the fake-render available=False + require_render=true fail-closed assertion returns one P0; the full targeted offline suite is green (od_ppt the sole KNOWN pre-existing exception), NO SNAPSHOT_UPDATE, lint-imports 4 kept / 0 broken.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM-generated prototype.html → validators | Untrusted model output parsed by static_check (stdlib) + rendered by render_check (headless Chromium); the malformed-route + router-dead defects are exactly what the hardening must surface. |
| manifest `require_render` step key → compiler → kernel | A declared per-step bool crossing the compiler INV-4/INV-5 boundary (already threaded by round 1); this plan only flips VALUES + adds a test-only golden-run pin. |
| offline golden harness `_patched_compile_for_run` → compiled plan | A TEST-only mutation of the compiled steps (clarify.mode + require_render) so golden runs are deterministic + environment-independent; never touches production code. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-erg-01 | Tampering (fail-open) | render_check malformed-route dedup | mitigate | Un-dedup gives each concrete malformed route its own ok=False NavResult so multiple broken detail routes under one segment can no longer hide behind a single representative; `${...}` excluded from exercise so the count stays true (no false dead). |
| T-erg-02 | Tampering (browserless fail-open) | static_check router-dead | mitigate | The routes-map resolution cross-check catches router-dead nav links (section exists but no map entry) with NO browser — narrowing render-reliance; guarded to fire only when a `const routes={}` map is present. |
| T-erg-03 | Repudiation / fail-open | require_render on revision | mitigate | prototype_revision (gates:[validation]) flips require_render:true → a browserless render now fails CLOSED (P0 → GATE_BLOCK), proven by test_nav_coverage scenario 4b + the full-file fail-closed assertion. |
| T-erg-04 | Denial of Service (false-positive block) | goldens + golden harness | mitigate | The harness pins require_render=False on golden runs (recorded semantics, Chromium-independent) + the router-dead guard is skipped on map-less goldens + un-dedup never fires on nav-less goldens → 5 goldens byte/event-identical, zero NEW issues on the 3 templates, NO SNAPSHOT_UPDATE. |
| T-erg-05 | Elevation (import-boundary break) | no new imports | mitigate | No new cross-boundary import; render_coverage_status stays in kernel-pure severity.py (round 1); lint-imports 4/0 asserted in every task verify. |
| T-erg-SC | Tampering | package installs | accept | No npm/pip/cargo installs — stdlib static_check + existing Playwright dep only; no new package surface (no legitimacy gate needed). |
</threat_model>

<verification>
Offline ONLY — the FULL pytest HANGS offline (Chromium/Bedrock/Postgres gating); do NOT run it. Chromium IS present locally so render runs for real and the browser-gated tests execute (they skip cleanly where absent).

- Targeted suite (canonical): `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_static_check.py tests/agents/test_validators.py tests/agents/test_gates.py tests/agents/test_phase5_fixloop_selection.py tests/agents/test_phase5_revision_validation.py tests/agents/test_compiler.py tests/agents/test_nav_coverage.py -q` — all green, NO SNAPSHOT_UPDATE.
- `/opt/homebrew/bin/lint-imports` — must report 4 kept / 0 broken (no new kernel→app edge; no new import).
- od_ppt: the ONE KNOWN pre-existing/environmental characterization failure (skills-asset / event-golden drift, baseline-proven independent of the validators). Leave it — do NOT fix, do NOT SNAPSHOT_UPDATE. Confirm it fails IDENTICALLY to baseline (no NEW breakage). It is EXCLUDED from the automated commands above to keep the green signal clean.
- INV-3 guard (test_nav_coverage): static_check + render_check raise zero NEW issues on prototype/od_prototype/prototype_revision goldens; the 3 goldens have no `const routes={}` (router-dead skipped) and no malformed/`${}` nav (un-dedup never fires).
- Full-file regression: the committed 414KB fixture pins the FINAL measured static dead-link + router-dead counts, render sidebar-dead count, and the exact overlap; the fake-render available=False + require_render=true assertion returns exactly one P0 (fails closed).
</verification>

<success_criteria>
- render_check reports each concrete malformed route distinctly (un-dedup), excludes `${...}` from browser exercise, and exposes a configurable nav settle wait (default 50, byte-identical) — producer available/ok/note contract unchanged.
- static_check emits a distinct browserless router-dead nav-link issue only when a routes map is present.
- require_render:true is declared on both the prototype build + revision steps; the revision step genuinely fails closed (GATE_BLOCK) on a browserless render; the build step is documented as record-the-skip + declared-intent (no gate).
- The #1 INV-3 collision is resolved: the golden harness pins require_render=False so the 5 goldens are byte/event-identical (NO SNAPSHOT_UPDATE), knob- AND Chromium-independent.
- The full 414KB file is a committed marked regression fixture with pinned final counts + a fail-closed assertion.
- INV-1 (no `if pipeline_type==`), INV-3 (goldens byte/event-identical; zero new golden issues; additive; no migration), INV-12 (extend in place, no dual impl), INV-13 (no deepagents change) all hold; lint-imports 4/0.
</success_criteria>

<output>
Create `.planning/quick/260701-erg-harden-prototype-validators-round-2-rend/260701-erg-SUMMARY.md` when done. Record the MEASURED final counts (static dead-link, static router-dead, render sidebar-dead, overlap) from Task 3.
</output>
