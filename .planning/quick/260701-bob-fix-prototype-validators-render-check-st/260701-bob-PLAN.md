---
phase: quick-260701-bob
plan: 01
type: execute
wave: 1
depends_on: []
autonomous: true
requirements: [RENDER-NAV-COV, STATIC-DYN-NAV, RENDER-SEAM, REQUIRE-RENDER-KNOB, VALIDATOR-SKIPPED, INV-3-GUARD]
files_modified:
  - backend/app/agents/render_check.py
  - backend/app/agents/static_check.py
  - backend/tests/agents/fixtures/imc-inventory-certificate-management.html
  - backend/agents/capabilities/validators/severity.py
  - backend/app/agents/validators/html_render.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/kernel_services.py
  - backend/agents/capabilities/gates/validation.py
  - backend/agents/capabilities/strategies/task_loop.py
  - backend/agents/workflows/plan.py
  - backend/agents/workflows/compiler.py
  - backend/app/core/config.py
  - backend/agents/workflows/prototype_revision/workflow.yaml
  - backend/tests/agents/test_nav_coverage.py
  - backend/tests/agents/test_validators.py

must_haves:
  truths:
    - "render_check flags the committed imc fixture (available=True, ok=False) via dead/parameterized dynamic-nav OR coverage — no longer nav_results=0 silent OK."
    - "static_check flags the fixture's onclick location.hash / navigateTo targets whose first-path-segment has no <section data-page> as ERRORS (not orphan warnings)."
    - "NavResult.ok is True only when the activated data-page equals the expected first-path-segment page id (wrong-section activation → ok=False)."
    - "A multi-(>=2) data-page SPA that exercises 0 nav produces a P0 coverage finding, not a silent OK."
    - "render-unavailable + require_render=true fails closed: html_render emits a P0 Issue → the existing ValidationGate block-critical policy → GATE_BLOCK (no new gate outcome, gates/base.py vocab untouched)."
    - "render-unavailable + require_render=false passes, but a distinct validator_skipped validation_results row is recorded (severity sentinel), never swallowed into 'no issues'."
    - "The producer available/ok/note contract is unchanged: navigation timeout / per-link dead-nav stay available=True failures; ONLY Playwright-import-fail + Chromium-launch-fail are available=False skips."
    - "The 5 characterization goldens stay byte/event-identical AND static_check + render_check raise zero NEW issues on the 3 golden templates (prototype.html, od_prototype.html, prototype_revision.html)."
  artifacts:
    - path: "backend/app/agents/render_check.py"
      provides: "Broadened _check_nav (a[href^='#'] + onclick location.hash/navigateTo discovery, dedupe by first-path-segment, expected-vs-activated NavResult, coverage finding)"
      contains: "coverage"
    - path: "backend/app/agents/static_check.py"
      provides: "Dynamic-nav (onclick/navigateTo) target detection + orphan-vs-dead reconciliation"
      contains: "location.hash"
    - path: "backend/agents/capabilities/validators/severity.py"
      provides: "render_coverage_status single-source policy helper + SKIPPED severity sentinel"
      contains: "def render_coverage_status"
    - path: "backend/app/agents/validators/html_render.py"
      provides: "Routes through render_coverage_status; P0 on skipped_blocked; distinct validator_skipped audit on any skip"
    - path: "backend/tests/agents/fixtures/imc-inventory-certificate-management.html"
      provides: "Committed nav-representative hash-router SPA fixture (onclick nav + parameterized detail route + dynamic-only detail sections + NO .nav-item)"
    - path: "backend/tests/agents/test_nav_coverage.py"
      provides: "The 8 nav-coverage + seam + INV-3 test scenarios"
    - path: "backend/agents/workflows/plan.py"
      provides: "Step.require_render compiled field"
      contains: "require_render"
    - path: "backend/agents/workflows/compiler.py"
      provides: "require_render step-key parse + threading into Step"
      contains: "require_render"
    - path: "backend/app/core/config.py"
      provides: "PROTOTYPE_REQUIRE_RENDER Settings default (False)"
      contains: "PROTOTYPE_REQUIRE_RENDER"
  key_links:
    - from: "backend/app/agents/validators/html_render.py"
      to: "backend/agents/capabilities/validators/severity.py"
      via: "render_coverage_status import"
      pattern: "render_coverage_status"
    - from: "backend/agents/execution_engine/engine.py"
      to: "backend/agents/capabilities/validators/severity.py"
      via: "_select_issues_to_fix + _run_validation_fix_loop route through render_coverage_status"
      pattern: "render_coverage_status"
    - from: "backend/agents/workflows/compiler.py"
      to: "backend/agents/execution_engine/kernel_services.py"
      via: "Step.require_render → deliverable_context(require_render=...) → DeliverableContext.require_render → html_render"
      pattern: "require_render"
    - from: "backend/app/agents/validators/html_render.py"
      to: "backend/agents/execution_engine/kernel_services.py"
      via: "target.runner.record_validation_result (SKIPPED row)"
      pattern: "record_validation_result"
---

<objective>
Fix the two prototype HTML validators (`render_check` + `static_check`) so they catch runtime-navigation defects — dead/parameterized dynamic routes, wrong-section activation, and uncovered nav — that currently slip through with the browser PRESENT, WITHOUT false-positives on the golden templates (INV-3). Fold in a corrected render-unavailable seam-hardening: one single-source policy helper routes all three consumers, a per-step `require_render` manifest knob fails closed through the EXISTING ValidationGate (no new gate outcome), and a distinct `validator_skipped` audit row guarantees a render skip is never swallowed.

Ground truth (parent-verified on the reference imc file): render_check → available=True, ok=True, nav_results=0; static_check → ok=True (unreachable detail sections showed only as non-fatal orphan WARNINGS). Root cause: a COVERAGE blind spot with Chromium present (hash-router SPA, `onclick="window.location.hash='#/…'"` nav, PARAMETERIZED detail routes, ZERO `.nav-item` elements) — NOT the available=False seam.

Purpose: close the navigation-coverage escape hatch that lets broken prototypes pass the fix-loop, while keeping the producer contract and the 5 characterization goldens byte/event-identical.
Output: hardened producers, a single render-coverage policy helper, the `require_render` knob threaded manifest→compiler→step→consumers, a committed fixture, and a new offline test file.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/CLAUDE.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/CLAUDE.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.planning/IMPLEMENTATION-REGISTER.md

# The producers under fix
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/app/agents/render_check.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/app/agents/static_check.py

# The registered wrappers + severity single-source + gate/policy path
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/app/agents/validators/html_render.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/app/agents/validators/html_static.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/capabilities/validators/severity.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/capabilities/gates/validation.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/capabilities/gates/base.py

# The consumers (engine + handle + strategy + post_step) and the manifest/compiler seam
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/execution_engine/kernel_services.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/capabilities/strategies/task_loop.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/workflows/plan.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/agents/workflows/compiler.py
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend/app/core/config.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Harden the render_check + static_check producers and commit the nav-representative fixture</name>
  <files>backend/app/agents/render_check.py, backend/app/agents/static_check.py, backend/tests/agents/fixtures/imc-inventory-certificate-management.html</files>
  <behavior>
    render_check (_check_nav / RenderResult):
    - Broaden nav discovery beyond `.nav-item[href]`: also generic `a[href^="#"]` AND click-handler nav (elements whose `onclick` contains `location.hash=` or `navigateTo(`), route extracted by regex from the handler string. Dedupe candidates by their first-path-segment TARGET (so `#/certificate/1` and `#/certificate/2` collapse to one representative `certificate`), exercising >=1 representative instance of a parameterized/detail route.
    - Add an `expected: str | None` field to NavResult (default None). Compute the expected page id as the first path segment of the route (reuse static_check's `_href_target_id` logic — a shared pure helper). Change `NavResult.ok` from `bool(activated)` to `activated == expected` via a pure helper `_nav_ok(activated, expected) -> bool` (unit-testable offline).
    - Emit a coverage signal: add `coverage_errors: list[str]` to RenderResult (default []). Count `[data-page]` sections in the DOM (`document.querySelectorAll('[data-page]').length`). Via a pure helper `_coverage_finding(section_count: int, exercised: int) -> str | None` (offline-testable), when section_count >= 2 AND exercised == 0 return a P0 "no navigable elements exercised" message; else None. Append to coverage_errors.
    - RenderResult.ok = no console_errors AND no page_errors AND all(n.ok for n in nav_results) AND NOT coverage_errors. Update summary() to mention coverage findings.
    - GUARDRAIL (do NOT touch): keep the available/ok/note PRODUCER classification exactly — navigation timeout / per-link dead-nav are available=True, ok=False failures; ONLY the Playwright import failure (lines 63-65) and the Chromium launch failure (lines 77-79) return available=False. Coverage=0 and wrong-section activation are available=True, ok=False (NOT skips).
    static_check:
    - Detect nav targets from `onclick="...location.hash='#/..'.."` and `navigateTo('..')` handlers (scan parser.inline_handlers AND the accumulated script_text), not just `<a href>` and `const routes={}`. Reuse `_href_target_id` for the first-path-segment target of each dynamic route.
    - Validate those dynamic-nav first-path-segment targets resolve to a `<section data-page>`: a dynamic-nav target with NO matching section is a dead-link ERROR (issues, not warnings), worded like the existing dead-link message but naming the dynamic source (e.g. `dead nav link: onclick route '#/certificate/${id}' has no matching <section data-page="certificate">`).
    - Reconcile orphan-vs-dead: a section reachable ONLY via dynamic nav must NOT be reported as a false orphan (add dynamic-nav targets to `linked_ids` before the orphan pass); a dynamic-nav target with no section IS a dead link.
    Fixture:
    - Commit a nav-representative copy of the reference file. Prefer a TRIMMED copy that preserves: the hash-router (`location.hash` + `matchRoute`/`hashchange`), the `onclick="window.location.hash='#/…'"` nav, >=1 PARAMETERIZED detail route (`#/certificate/${id}` or `#/inventory/${sku}`), >=1 detail section reachable ONLY via dynamic nav (or a parameterized target with NO static section, so it is a dead link), and NO `.nav-item` elements. If trimming risks losing fidelity, commit the full 414KB file instead.
  </behavior>
  <action>Edit backend/app/agents/render_check.py: add a shared pure `_first_path_segment(route)` helper (or import/reuse static_check's `_href_target_id`), add `_nav_ok(activated, expected)` and `_coverage_finding(section_count, exercised)` pure module helpers, add `expected` to NavResult and `coverage_errors` to RenderResult, rewrite `_check_nav` to discover anchors (`a[href^="#"]`) + onclick/navigateTo handler routes, dedupe by first-path-segment, exercise a representative of each target (click anchors; for extracted handler routes set `location.hash` to the route then read the activated `[data-page].is-active`/`.section.is-active`), build each NavResult with `expected` + `ok=_nav_ok(...)`, and compute the coverage finding from section count vs exercised count. Update the top-level `ok` and `summary()`. Preserve the two available=False early returns and their wording verbatim (guardrail). Edit backend/app/agents/static_check.py: add dynamic-nav extraction (regex over inline_handlers + script_text for `location.hash\s*=\s*['\"]([^'\"]+)` and `navigateTo\(\s*['\"]([^'\"]+)`), fold the resulting route targets into the routes↔sections check (dead-link ERROR when no section) and into `linked_ids` before the orphan pass so dynamic-only sections are not false orphans. Do NOT fork a parallel checker (INV-12) — extend the existing single-pass parser/flow in place. Copy /Users/1000060523/Downloads/imc-inventory-certificate-management.html into backend/tests/agents/fixtures/ (create the dir) trimmed per <behavior>; before committing, run static_check + render_check on the committed fixture and confirm static_check.issues is non-empty AND (render_check.ok is False when Chromium is available). Do NOT place fenced code in prose — implement in the source files.</action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_static_check.py -q && python3.11 -c "from app.agents.static_check import static_check; from pathlib import Path; f=Path('tests/agents/fixtures/imc-inventory-certificate-management.html'); r=static_check(f); assert r.issues, 'fixture must be flagged by static_check'; g=static_check(Path('tests/agents/characterization/golden/prototype.html')); assert g.ok and not g.issues, 'golden must not be newly flagged'; print('static OK: fixture issues=%d golden ok=%s' % (len(r.issues), g.ok))"</automated>
  </verify>
  <done>test_static_check.py stays green; static_check flags the committed fixture (>=1 issue for a dynamic-nav dead link) and raises zero issues on prototype.html golden; render_check exposes NavResult.expected + RenderResult.coverage_errors and computes ok via activated==expected + coverage; the two available=False early returns are byte-identical.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Single render-coverage policy helper + route the 3 consumers + require_render knob + validator_skipped audit</name>
  <files>backend/agents/capabilities/validators/severity.py, backend/app/agents/validators/html_render.py, backend/agents/execution_engine/engine.py, backend/agents/execution_engine/kernel_services.py, backend/agents/capabilities/gates/validation.py, backend/agents/capabilities/strategies/task_loop.py, backend/agents/workflows/plan.py, backend/agents/workflows/compiler.py, backend/app/core/config.py, backend/agents/workflows/prototype_revision/workflow.yaml</files>
  <behavior>
    Policy helper (single source, severity.py — kernel-pure, import-clean, already imported by both app validators and the kernel gate):
    - Add `render_coverage_status(rres, require_render: bool) -> str` returning "ok" when `getattr(rres, "available", False)` is True; else "skipped_blocked" when require_render is True; else "skipped_allowed".
    - Add a SKIPPED severity sentinel: extend `_SEVERITY_LABELS` with `"SKIPPED": "SKIPPED"` so `map_severity("SKIPPED")` returns "SKIPPED" WITHOUT raising (update the docstring; keep P0-P3 exact ordering intact elsewhere).
    Consumer 1 — html_render.py (route through the helper):
    - Resolve require_render: `getattr(target, "require_render", None)`; when None fall back to `settings.PROTOTYPE_REQUIRE_RENDER` (app-side import of app.core.config is legal). status = render_coverage_status(result, require_render).
    - status == "ok": emit console/page/nav issues as today PLUS a P0 Issue per `result.coverage_errors` entry; `await _record(...)`; return issues.
    - status == "skipped_blocked": write a distinct validator_skipped row (see below) and return `[Issue(severity="P0", message=f"render unavailable (require_render): {result.note}", validator="html_render")]` so the ValidationGate block-critical policy fires (CORRECTION 1 — no new gate outcome).
    - status == "skipped_allowed": write the distinct validator_skipped row and return [] (a pass — but never swallowed).
    - Distinct validator_skipped row: `await target.runner.record_validation_result(step, "html_render", severity="SKIPPED", attempt=..., issues=[{"severity":"SKIPPED","message": result.note}])`, guarded like `_record` (no-op when runner/record is absent). Add a `logger.info` telemetry line on the skip.
    Consumer 2 — engine._select_issues_to_fix: add `require_render: bool = True` param; gate the render contribution on `render_coverage_status(rres, require_render) == "ok"` (replaces the inline `if getattr(rres,'available',False)`); inside that branch ALSO append each `rres.coverage_errors` line as always-included hard breakage. With available=True this is byte-identical to today (goldens have no coverage_errors); with available=False no render lines (= today).
    Consumer 3 — engine._run_validation_fix_loop: add `require_render: bool | None = None` kwarg (None → settings.PROTOTYPE_REQUIRE_RENDER); compute `status = render_coverage_status(rres, require_render)`; set `render_skipped = status != "ok"` and pass require_render into `_select_issues_to_fix`; on a skip emit a `logger.info` telemetry line and do NOT open a `:fix{n}` thread for it (CORRECTION 3 — the loop never blocks; the GATE is the authoritative fail-closed; the audit row is owned by html_render, not re-written here). Include coverage_errors in the BUILD residual assembly.
    require_render knob (manifest → compiler → step → consumers):
    - plan.py Step: add `require_render: bool | None = None` (forward field).
    - compiler.py: add `"require_render"` to `_ALLOWED_STEP_KEYS`; parse `raw.get("require_render")` and pass to the Step(...) constructor.
    - config.py Settings: add `PROTOTYPE_REQUIRE_RENDER: bool = False` (default preserves today's skip-is-a-pass → INV-3).
    - kernel_services.py: add `require_render: bool | None = None` to `DeliverableContext` and to the `deliverable_context(...)` factory (thread onto the returned context); in `run_validation_fix_loop(step, ...)` read `getattr(step, "require_render", None)` and pass it into `_run_validation_fix_loop`.
    - validation.py gate: in `evaluate` read `getattr(step, "require_render", None)` and pass it into `_build_validation_target` → `deliverable_context(require_render=...)` so html_render sees the per-step knob.
    - task_loop.py `_run_registered_validators`: pass `require_render=getattr(step,"require_render",None)` into `deliverable_context(...)`.
    - prototype_revision/workflow.yaml: declare `require_render: false` explicitly on the revision step (demonstrative threading; value == default so behavior is unchanged and INV-3 goldens stay byte/event-identical).
  </behavior>
  <action>Implement the single helper in severity.py FIRST (both the app validator and the kernel engine import it — app→capabilities and engine→capabilities are import-linter-legal; capabilities→engine/app stays forbidden, so severity.py must remain pure stdlib). Then route html_render.py, engine._select_issues_to_fix, and engine._run_validation_fix_loop through it. Thread require_render: add the Step field (plan.py), the allowed key + parse (compiler.py), the Settings default (config.py), the DeliverableContext field + factory param + run_validation_fix_loop read (kernel_services.py), the gate pass-through (validation.py), and the strategy pass-through (task_loop.py). Add `require_render: false` to prototype_revision/workflow.yaml. Keep every audit write best-effort (never abort the validator/loop — INV-3). No fenced code in prose — edit the source files. Do NOT add a GATE_ERROR / new gate outcome and do NOT touch gates/base.py's vocabulary; do NOT add a bare REQUIRE_RENDER global env; do NOT add a migration (encode skipped in existing validation_results columns).

CHECKER CLARIFICATION 1 (do NOT migrate the 4th site): `engine.py:_console_sigs` (~line 492) has its own `getattr(rres, "available", False)` guard — LEAVE IT AS-IS. It is a baseline-diff SIGNATURE helper (a skipped render legitimately has no console signatures regardless of the knob), so it is `require_render`-INDEPENDENT and routing it through `render_coverage_status` would be semantically wrong. The "single source" scope is html_render + `_select_issues_to_fix` + `_run_validation_fix_loop` ONLY; `_console_sigs` is an explicit non-policy exemption. CHECKER CLARIFICATION 2: the `SKIPPED` sentinel only ever appears on the audit ROW (via record_validation_result), never as a returned Issue — the gate never maps it; do NOT add a gate assertion for SKIPPED (test the audit row via a capturing fake runner, as scenario 5 does).</action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_validators.py tests/agents/test_gates.py tests/agents/test_phase5_fixloop_selection.py tests/agents/test_phase5_revision_validation.py tests/agents/test_compiler.py -q && /opt/homebrew/bin/lint-imports</automated>
  </verify>
  <done>render_coverage_status is the ONLY render-usable decision across html_render + both engine sites; map_severity("SKIPPED") returns "SKIPPED" without raising; require_render threads manifest→compiler→Step→DeliverableContext→html_render and step→run_validation_fix_loop; existing validator/gate/fixloop/revision/compiler suites pass; lint-imports reports 4 kept / 0 broken (no new kernel→app edge).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: New nav-coverage test suite + INV-3 false-positive guard + full offline verification</name>
  <files>backend/tests/agents/test_nav_coverage.py, backend/tests/agents/test_validators.py</files>
  <behavior>
    New tests/agents/test_nav_coverage.py covering the 8 scenarios (browser-dependent tests skip gracefully when Chromium/Playwright is unavailable via a helper that runs render_check and pytest.skip()s on available=False; pure/static/seam tests run offline unconditionally):
    1. Fixture → static_check flags the unreachable dynamic-nav targets as ERRORS (offline); AND (browser-gated) render_check on the fixture is available=True, ok=False (dead/parameterized nav OR coverage).
    2. Correct-section-activation regression (offline via the pure `_nav_ok`): activated == expected → ok True; activated != expected → ok False; activated None → ok False.
    3. Coverage=0 on a multi-section SPA with no discoverable nav → P0 finding (offline via the pure `_coverage_finding(section_count>=2, exercised=0)` returns a message; single section → None). Optionally a browser-gated inline-HTML end-to-end assertion.
    4. available=False + require_render=true → (a) html_render.validate (fake runner, fake render_check returning available=False) returns exactly one P0 Issue; (b) that Issue drives ValidationGate.evaluate (step declaring validators=["html_render"], gates=["validation"]) to GATE_BLOCK; (c) _run_validation_fix_loop with a monkeypatched static_check (clean) + render_check (available=False) + require_render=true does NOT re-invoke the sub-agent (assert create_runner is never called / no :fix thread).
    5. available=False + require_render=false → html_render.validate returns [] (pass) BUT record_validation_result was called once with severity="SKIPPED" (assert recorded via a capturing fake runner — not swallowed).
    6. static_check on the fixture flags it independently of any render (both tiers now cover it).
    7. Producer guardrail (offline, RenderResult classification): a RenderResult built with available=True + a dead NavResult (ok=False) / page_errors is ok=False but available=True (a failure, NOT a skip); assert render-harness / per-link dead-nav never flips available to False.
    8. INV-3 false-positive guard: static_check on prototype.html, od_prototype.html, prototype_revision.html golden templates → zero issues (ok=True); AND (browser-gated) render_check on each golden → no NEW issues (single-section/no-section goldens never trip the >=2-section coverage rule).
    test_validators.py: update the html_render render-unavailable assertion to expect the new distinct validator_skipped row (severity sentinel) while keeping the "no blocking issues on skipped_allowed" assertion (default require_render=False).
  </behavior>
  <action>Write tests/agents/test_nav_coverage.py using the existing offline test conventions (see test_validators.py for the ScopedStore-backed fake runner + in-memory DB, test_phase5_fixloop_selection.py for _select_issues_to_fix usage, test_gates.py for gate evaluation). Provide a `_render_available()` skip-helper that runs render_check on a trivial temp HTML and pytest.skip()s when available is False, guarding every browser-dependent assertion. Reference the committed fixture at backend/tests/agents/fixtures/imc-inventory-certificate-management.html. Update the render-unavailable expectation in test_validators.py to match the intended validator_skipped behavior (this is a deliberate unit-level behavior change, not an INV-3 golden change). Run the full offline suite + lint-imports.</action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_static_check.py tests/agents/test_validators.py tests/agents/test_phase5_fixloop_selection.py tests/agents/test_phase5_revision_validation.py tests/agents/test_gates.py tests/agents/test_nav_coverage.py -q && /opt/homebrew/bin/lint-imports</automated>
  </verify>
  <done>The 5 characterization tests (byte + event) stay green with NO SNAPSHOT_UPDATE; test_nav_coverage.py passes all 8 scenarios (browser-gated ones skip cleanly offline); test_validators.py green with the updated skip expectation; the INV-3 guard proves static_check + render_check raise zero new issues on the 3 golden templates; lint-imports 4 kept / 0 broken.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM-generated prototype.html → validators | Untrusted model output parsed by static_check (stdlib) + rendered by render_check (headless Chromium); a defect here is the very thing the fix-loop must catch. |
| manifest `require_render` step key → compiler → kernel | A declared per-step knob crossing the compiler INV-4/INV-5 boundary; must be pure data with no control flow. |
| validator → validation_results (ScopedStore) | Audit write crossing into owner/workspace-scoped persistence. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-bob-01 | Tampering (fail-open) | render_check nav coverage | mitigate | Coverage=0 on a multi-section SPA + wrong-section activation become available=True/ok=False findings; a broken prototype can no longer pass with nav_results=0. |
| T-bob-02 | Denial of Service (false-positive block) | static_check + render_check on goldens | mitigate | INV-3 guard test asserts zero new issues on the 3 golden templates + 5 characterization goldens byte/event-identical; coverage rule fires only at >=2 sections. |
| T-bob-03 | Elevation (DSL smuggling) | compiler `require_render` key | mitigate | Added to `_ALLOWED_STEP_KEYS` as a bool data field only; strict-key rejection at every level (INV-5) unchanged; no control flow enters the manifest. |
| T-bob-04 | Repudiation (swallowed skip) | render-unavailable path | mitigate | Distinct validator_skipped validation_results row (severity sentinel) + telemetry log written even when require_render=false — a skip is recorded, never silently dropped. |
| T-bob-05 | Elevation (import-boundary break) | render_coverage_status placement | mitigate | Helper lives in kernel-pure severity.py (stdlib only); app→capabilities + engine→capabilities imports are legal, capabilities→engine/app stays forbidden; lint-imports gate 4/0 in every task verify. |
| T-bob-SC | Tampering | package installs | accept | No npm/pip/cargo installs in this plan; stdlib-only static_check + existing Playwright dep — no new package surface. |
</threat_model>

<verification>
Offline verification (the FULL pytest HANGS offline due to Chromium/Bedrock/Postgres gating — do NOT run it):

- `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_static_check.py tests/agents/test_validators.py tests/agents/test_phase5_fixloop_selection.py tests/agents/test_phase5_revision_validation.py tests/agents/test_gates.py tests/agents/test_compiler.py tests/agents/test_nav_coverage.py -q` — all green, NO SNAPSHOT_UPDATE.
- `/opt/homebrew/bin/lint-imports` — must report "4 kept, 0 broken" (the require_render threading must NOT create a kernel→app edge; render_coverage_status stays in kernel-pure severity.py).
- INV-3 false-positive guard (in test_nav_coverage.py): static_check + render_check on prototype.html / od_prototype.html / prototype_revision.html goldens → zero new issues.
- Fixture repro (in test_nav_coverage.py + Task-1 verify one-liner): static_check + render_check on the committed fixture BOTH flag it; the 3 golden templates get zero new issues.
</verification>

<success_criteria>
- render_check catches the fixture's nav-coverage defects (dead/parameterized dynamic nav, wrong-section activation, coverage=0) as available=True/ok=False — no more nav_results=0 silent OK.
- static_check flags onclick/navigateTo dynamic-nav dead links as ERRORS and no longer false-orphans dynamic-only sections.
- One render_coverage_status helper is the single source routing html_render + both engine consumers; require_render is a per-step manifest knob threaded through the compiler + Settings default (not a bare env, not a new gate outcome).
- render-unavailable + require_render=true fails closed via html_render P0 → existing ValidationGate → GATE_BLOCK; render-unavailable + require_render=false passes but records a distinct validator_skipped row.
- The producer available/ok/note contract is unchanged (guardrail): only Playwright/Chromium import/launch failures are skips.
- INV-3 holds: 5 characterization goldens byte/event-identical; zero new issues on the 3 golden templates; no migration; lint-imports 4/0.
</success_criteria>

<output>
Create `.planning/quick/260701-bob-fix-prototype-validators-render-check-st/260701-bob-SUMMARY.md` when done.
</output>
