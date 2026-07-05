---
phase: quick-260701-bob
plan: 01
subsystem: prototype-validators
tags: [render_check, static_check, validators, render-seam, require_render, nav-coverage, INV-3]
requires: [static_check, render_check, html_render, ValidationGate, WorkflowCompiler, KernelServices]
provides:
  - render_check nav-coverage + wrong-section-activation + parameterized-route detection
  - static_check dynamic-nav (onclick/navigateTo) dead-link detection + orphan reconciliation
  - render_coverage_status single-source policy helper + SKIPPED severity sentinel
  - per-step require_render knob (manifest→compiler→Step→consumers) + PROTOTYPE_REQUIRE_RENDER setting
  - distinct validator_skipped audit row on render skip
affects: [prototype build loop, prototype_revision, ValidationGate post-step validation]
tech-stack:
  added: []
  patterns: [single-source-policy-helper, per-step-manifest-knob, fail-closed-via-existing-gate]
key-files:
  created:
    - backend/tests/agents/fixtures/imc-inventory-certificate-management.html
    - backend/tests/agents/test_nav_coverage.py
  modified:
    - backend/app/agents/render_check.py
    - backend/app/agents/static_check.py
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
    - backend/tests/agents/test_validators.py
decisions:
  - "render_coverage_status is the single render-coverage policy source across html_render + both engine sites; _console_sigs left AS-IS (baseline-diff helper, require_render-independent)."
  - "SKIPPED severity sentinel lands only on the audit row (never a returned Issue); the gate never maps it — no gate assertion for SKIPPED."
  - "require_render fails closed through the EXISTING ValidationGate block-critical policy (P0 → GATE_BLOCK); no new gate outcome, gates/base.py vocab untouched; no migration."
  - "INV-3 guard is zero-NEW-issues (the golden stubs already emit a pre-existing 'no active page' issue), not zero-absolute; the plan's literal Task-1 one-liner asserting g.ok was based on an incorrect premise about the golden."
metrics:
  tasks: 3
  files: 14
  duration: ~90min
  completed: 2026-07-01
---

# quick-260701-bob: Fix prototype validators (render_check + static_check nav-coverage) + render seam Summary

Hardened `render_check` + `static_check` to catch runtime-navigation defects (dead/parameterized dynamic-nav routes, wrong-section activation, uncovered nav) that slipped through with Chromium present, and folded in a single-source `render_coverage_status` seam with a per-step `require_render` fail-closed knob and a distinct `validator_skipped` audit row — with zero new false-positives on the golden templates.

## What shipped

**Task 1 — producers + fixture (commit 4b65c66c)**
- `render_check`: `_check_nav` now discovers `a[href^='#']` + `onclick` `location.hash`/`navigateTo` routes, dedupes by first-path-segment, exercises one representative per target, and records `NavResult.expected` with `ok = activated == expected` (via pure `_nav_ok`). Added `RenderResult.coverage_errors` computed by pure `_coverage_finding(section_count>=2, exercised==0)`. The two `available=False` early returns (Playwright/Chromium unavailable) are byte-identical. `_first_path_segment` reuses static_check's `_href_target_id` (single source).
- `static_check`: detects `onclick`/`navigateTo` dynamic-nav targets (over inline handlers + script text), flags targets with no `<section data-page>` as dead-link ERRORS, and folds dynamic targets into `linked_ids` before the orphan pass so dynamic-only sections are not false orphans.
- Committed a trimmed nav-representative `imc-inventory-certificate-management.html` fixture (hash-router, `onclick` nav, parameterized `#/inventory/${id}` dead route, dynamic-only detail section, NO `.nav-item`) that BOTH tiers flag.

**Task 2 — single seam + knob + skip audit (commit 242a1e38)**
- `severity.py`: `render_coverage_status(rres, require_render) -> ok | skipped_blocked | skipped_allowed` (single policy source); `SKIPPED` severity sentinel so `map_severity("SKIPPED")` returns "SKIPPED" without raising (P0–P3 blocking ladder intact).
- `html_render`: routes through the helper; `skipped_blocked` → one P0 (existing ValidationGate → GATE_BLOCK); any skip → a distinct `validator_skipped` row (SKIPPED sentinel) + telemetry; `ok` → also emits P0 per coverage finding.
- `engine._select_issues_to_fix` + `_run_validation_fix_loop`: route render contribution through `render_coverage_status` (byte-identical for available renders), include `coverage_errors` in selection + BUILD residual, never open a `:fix` thread on a skip. `_console_sigs` left AS-IS (CHECKER CLARIFICATION 1).
- Threaded `require_render` manifest→compiler→`Step`→`DeliverableContext`→html_render and step→`run_validation_fix_loop`; `PROTOTYPE_REQUIRE_RENDER: bool = False` setting; `prototype_revision/workflow.yaml` declares `require_render: false` (demonstrative). No migration; gates/base.py vocab untouched.

**Task 3 — tests + INV-3 guard (commit 7ff4b6e5)**
- New `test_nav_coverage.py` (8 scenarios, browser-gated ones skip cleanly offline); updated `test_validators.py` render-unavailable expectation to assert the `validator_skipped` row.

## Verification results

- `test_static_check.py` 25/25; `test_validators.py` 15/15; `test_gates.py`, `test_phase5_fixloop_selection.py`, `test_phase5_revision_validation.py`, `test_compiler.py`, `test_nav_coverage.py` — full targeted offline suite **150/150**.
- `lint-imports` — **4 kept, 0 broken** (render_coverage_status stays in kernel-pure severity.py; no kernel→app edge).
- Fixture reproduces via BOTH tiers: static_check 1 dead-link issue; render_check available=True, ok=False (parameterized `#/inventory/4521` → activated=None).
- INV-3: static_check + render_check raise **zero NEW issues** on the 3 golden templates (prototype/od_prototype/prototype_revision); 4 of the 5 characterization goldens pass with the local runtime asset present (prototype, od_prototype, prototype_revision, app_builder).

## Deviations from Plan

### 1. [Rule 1 — incorrect-premise verify] Task-1 literal verify one-liner corrected to zero-NEW-issues
- **Found during:** Task 1.
- **Issue:** The plan's Task-1 `<verify>` one-liner asserts `g.ok and not g.issues` on `golden/prototype.html`. That golden (an 84-byte deliverable stub `<section data-page='dashboard'>hi</section>` with no `is-active`) ALREADY emits a pre-existing `no active page` issue on unchanged code — so the literal assertion is impossible regardless of this task.
- **Resolution:** Verified the real INV-3 intent instead — the fixture is flagged AND the goldens gain **zero NEW issues** (the new dynamic-nav check never fires on the goldens). Encoded as `test_nav_coverage.py::test_scenario8_static_zero_new_issues_on_goldens`. No golden edited, no SNAPSHOT_UPDATE.

## Deferred Issues (out-of-scope, pre-existing)

### od_ppt (+ prototype/od_prototype) characterization snapshots are local-env-sensitive to a runtime asset
- `test_characterization_od_ppt.py::test_od_ppt_event_snapshot` fails in the local working tree because `get_example_html("web-prototype")` reads the on-disk asset `skills/opendesign/design-templates/web-prototype/example.html`, injecting a `TEMPLATE EXAMPLE` block the committed golden lacks.
- **Proven independent of this task:** reverting `render_check.py` + `static_check.py` to pre-task (96dec5a9) content STILL fails od_ppt; moving the asset aside flips it (od_ppt passes, prototype/od_prototype then fail). There is no local asset-state where all 5 goldens pass simultaneously.
- Logged to `deferred-items.md`. Goldens + SNAPSHOT untouched (INV-3). Recommended follow-up: reconcile committed goldens with the current `skills/` runtime assets in a dedicated clean-env pass.

## Commits
- `4b65c66c` fix(agents): catch dynamic-nav coverage defects in render_check + static_check
- `242a1e38` feat(engine): single render_coverage_status seam + require_render knob + skip audit
- `7ff4b6e5` test(agents): nav-coverage + render-seam + INV-3 guard suite

## Self-Check: PASSED
- Files: fixture, test_nav_coverage.py, SUMMARY.md all present on disk.
- Commits: 4b65c66c, 242a1e38, 7ff4b6e5 all present in git history.
- Working tree clean (only the untracked .planning/quick docs artifacts remain for the orchestrator's docs commit).
