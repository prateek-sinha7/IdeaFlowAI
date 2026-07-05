---
phase: quick-260701-bob
verified: 2026-07-01T09:20:00Z
status: human_needed
score: 8/8 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Re-run the full 5-golden characterization suite (incl. test_characterization_od_ppt.py) in the CLEAN CI environment where the goldens were originally recorded (the offline local tree fails od_ppt on a skills/ runtime-asset drift, and full pytest hangs locally on Chromium/Bedrock/Postgres gates)."
    expected: "All 5 characterization goldens (prototype, od_prototype, prototype_revision, app_builder, od_ppt) pass byte + event identical with NO SNAPSHOT_UPDATE. If od_ppt still fails in CI, it is a golden-vs-skills-asset reconciliation task independent of this change (od_ppt is a PPT deck pipeline that does not run the HTML nav validators)."
    why_human: "Cannot verify offline — full pytest hangs (Chromium/Bedrock/Postgres gated) and the local skills/opendesign/design-templates/web-prototype/example.html asset diverges from the committed golden's recording environment. Requires the CI/clean-env runtime asset state."
---

# quick-260701-bob: Fix prototype validators (render_check + static_check nav-coverage) + render seam — Verification Report

**Task Goal:** Fix render_check + static_check to catch runtime-navigation defects (dead/parameterized routes, wrong-section activation, uncovered nav) that slipped through with the browser present, WITHOUT false-positives on the golden templates (INV-3); plus a corrected render-unavailable seam (single render_coverage_status helper, per-step require_render failing closed through the EXISTING ValidationGate, distinct validator_skipped audit).
**Verified:** 2026-07-01T09:20:00Z
**Status:** human_needed (all 8 task must-haves VERIFIED; the ONLY red is the pre-existing/environmental od_ppt characterization, surfaced for a CI re-confirm)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | render_check flags the committed imc fixture (available=True, ok=False) via dead/parameterized dynamic-nav OR coverage — no longer nav_results=0 silent OK | VERIFIED | `_check_nav` (render_check.py:199-266) discovers `a[href^='#']` + onclick `location.hash`/`navigateTo` routes, dedupes by first-path-segment, builds NavResult with `ok=_nav_ok(activated, expected)`; coverage via `_coverage_finding` (l.80-93). Orchestrator absolute-path run confirmed available=True, ok=False (`#/inventory/4521` activates None while other routes activate correctly). test_nav_coverage scenario 1 passes. |
| 2 | static_check flags fixture onclick/navigateTo targets whose first-path-segment has no `<section data-page>` as ERRORS (not orphan warnings) | VERIFIED | `_extract_dynamic_nav_routes` + dead-link ERROR emission (static_check.py:526-542); dynamic targets folded into `linked_ids` before orphan pass. Orchestrator confirmed 1 dead-nav ERROR on fixture. test_static_check + scenario 6 pass. |
| 3 | NavResult.ok is True only when activated data-page equals expected first-path-segment (wrong-section → ok=False) | VERIFIED | Pure `_nav_ok(activated, expected)` (render_check.py:71-77) = `activated is not None and activated == expected`; NavResult carries `expected` field. test_nav_coverage scenario 2 passes. |
| 4 | A multi (>=2) data-page SPA that exercises 0 nav produces a P0 coverage finding, not a silent OK | VERIFIED | Pure `_coverage_finding(section_count, exercised)` (render_check.py:80-93) fires only at `section_count>=2 and exercised==0`; wired into render_check (l.170-178) and RenderResult.ok. test_nav_coverage scenario 3 passes. |
| 5 | render-unavailable + require_render=true fails closed: P0 Issue → existing ValidationGate block-critical → GATE_BLOCK (no new gate outcome, gates/base.py vocab untouched) | VERIFIED | html_render.py:78-90 emits one P0 on `skipped_blocked`. gates/base.py vocab = GATE_PASS/GATE_BLOCK/GATE_WAIT_HUMAN only; `grep GATE_ERROR` empty tree-wide. test_nav_coverage scenario 4 passes. |
| 6 | render-unavailable + require_render=false passes, but a distinct validator_skipped row is recorded (severity sentinel), never swallowed | VERIFIED | `_record_skip` (html_render.py:125-149) writes severity="SKIPPED" audit row best-effort + telemetry; returns []. test_nav_coverage scenario 5 asserts capturing runner records SKIPPED. map_severity("SKIPPED")="SKIPPED" (no raise, confirmed live). |
| 7 | Producer available/ok/note contract unchanged: nav-timeout / per-link dead-nav stay available=True failures; ONLY Playwright-import + Chromium-launch fails are available=False skips | VERIFIED | `diff` of the two `available=False` early returns baseline 2295582b vs HEAD → IDENTICAL. Coverage/wrong-section paths keep available=True. test_nav_coverage scenario 7 passes. |
| 8 | 5 characterization goldens stay byte/event-identical AND static_check + render_check raise zero NEW issues on the 3 golden templates | VERIFIED (task-scoped) | Task code adds ZERO new issues (orchestrator baseline proof: reverting both producers to 2295582b yields IDENTICAL static_check on the 3 goldens; test scenario 8). Characterization byte/event-identity is invariant to this task — reverting the producers yields the same od_ppt result (env-drift, not code). 4/5 characterization pass locally; od_ppt is pre-existing/environmental (see human_verification). |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/agents/render_check.py` | Broadened `_check_nav` + expected/coverage | VERIFIED | `_check_nav`, `_nav_ok`, `_coverage_finding`, `_extract_handler_routes`, `_first_path_segment`; NavResult.expected + RenderResult.coverage_errors. |
| `backend/app/agents/static_check.py` | Dynamic-nav dead-link + orphan reconciliation | VERIFIED | `_extract_dynamic_nav_routes` over inline_handlers + script_text; dead-link ERROR; linked_ids folded before orphan pass. |
| `backend/agents/capabilities/validators/severity.py` | render_coverage_status + SKIPPED sentinel | VERIFIED | `render_coverage_status` (kernel-pure); `_SEVERITY_LABELS["SKIPPED"]`. |
| `backend/app/agents/validators/html_render.py` | Routes through helper; P0 blocked; skip audit | VERIFIED | status branches; `_record_skip` writes SKIPPED row + telemetry. |
| `backend/tests/agents/fixtures/imc-inventory-certificate-management.html` | Hash-router SPA, onclick nav, param route, dynamic-only detail, NO .nav-item | VERIFIED | 3148B; 10 location.hash, 6 data-page, param `inventory/` routes; `.nav-item` appears ONLY in comments (no elements). |
| `backend/tests/agents/test_nav_coverage.py` | 8 scenarios | VERIFIED | 18 tests collected, all pass; browser-gated ones skip cleanly. |
| `backend/agents/workflows/plan.py` | Step.require_render field | VERIFIED | l.364 `require_render: bool | None = None`. |
| `backend/agents/workflows/compiler.py` | _ALLOWED_STEP_KEYS + parse + thread | VERIFIED | l.79 allowed key; l.553-567 parse + Step(...) pass. |
| `backend/app/core/config.py` | PROTOTYPE_REQUIRE_RENDER default False | VERIFIED | l.132 `PROTOTYPE_REQUIRE_RENDER: bool = False`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| html_render.py | severity.py | render_coverage_status import | WIRED | imported l.31-34, called l.75. |
| engine.py | severity.py | _select_issues_to_fix + _run_validation_fix_loop | WIRED | import l.40; `_select_issues_to_fix` l.538; `_run_validation_fix_loop` l.3525. coverage_errors included l.562-563 (selection) + BUILD residual. |
| compiler.py | kernel_services.py | Step.require_render → deliverable_context → DeliverableContext → html_render | WIRED | compiler Step(require_render=…); DeliverableContext.require_render l.112; deliverable_context factory l.1043-1067; run_validation_fix_loop reads getattr(step,…) l.1309. |
| html_render.py | kernel_services.py | runner.record_validation_result (SKIPPED row) | WIRED | `_record_skip` calls `record(step,"html_render",severity="SKIPPED",…)`. |
| validation.py gate | kernel_services.py | getattr(step,"require_render") → _build_validation_target → deliverable_context | WIRED | l.93 pass-through; l.159-196 factory forwards require_render (with TypeError retry for old fakes). |
| task_loop.py | kernel_services.py | require_render pass-through | WIRED | l.425 `getattr(step,"require_render",None)` into deliverable_context. |

### Exemption Verified (documented non-policy site)

`engine.py:_console_sigs` (l.486-495) deliberately RETAINS its own `getattr(rres,"available",False)` guard and is NOT routed through render_coverage_status — a baseline-diff signature helper that is require_render-independent (CHECKER CLARIFICATION 1). Confirmed as-is.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Targeted offline suite | pytest (7 files) | 150 passed in 38.56s | PASS |
| Import boundary | /opt/homebrew/bin/lint-imports | 4 kept, 0 broken | PASS |
| SKIPPED sentinel no-raise | python -c map_severity('SKIPPED') | "SKIPPED" | PASS |
| render_coverage_status truth table | python -c ok/blocked/allowed | ok / skipped_blocked / skipped_allowed | PASS |
| available=False early-return guardrail | diff baseline 2295582b vs HEAD | IDENTICAL lines | PASS |
| No new migration | git log branch migrations/alembic | none | PASS |
| gate vocab untouched | grep GATE_ / GATE_ERROR | PASS/BLOCK/WAIT_HUMAN only; no GATE_ERROR | PASS |
| Commits present | git log 4b65c66c 242a1e38 7ff4b6e5 | all present | PASS |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| RENDER-NAV-COV | SATISFIED | coverage_errors + _coverage_finding; truths 1,4. |
| STATIC-DYN-NAV | SATISFIED | dynamic-nav dead-link ERROR; truth 2. |
| RENDER-SEAM | SATISFIED | single render_coverage_status across 3 consumers; key links. |
| REQUIRE-RENDER-KNOB | SATISFIED | manifest→compiler→Step→DeliverableContext→html_render + settings default; truths 5,6. |
| VALIDATOR-SKIPPED | SATISFIED | _record_skip SKIPPED audit row; truth 6, scenario 5. |
| INV-3-GUARD | SATISFIED | zero new issues on 3 goldens; byte-identical early returns; lint 4/0; no migration; truth 8. |

### Deferred / Environmental Item

| # | Item | Disposition | Evidence |
|---|------|-------------|----------|
| 1 | od_ppt characterization event-golden fails locally | Pre-existing + environmental (skills/ runtime-asset drift), NOT caused by this task; surfaced for CI re-confirm | Orchestrator + executor baseline-proven: reverting both producers yields IDENTICAL od_ppt failure; od_ppt is a PPT deck pipeline that does not run the HTML nav validators. See deferred-items.md D1. |

### Anti-Patterns Found

None material. Producers use best-effort `except Exception` with `# noqa: BLE001` intentionally (browser-skip semantics), and audit writes are guarded no-ops by design (INV-3). No unreferenced TBD/FIXME/XXX debt markers in modified files.

### Gaps Summary

No task gaps. All 8 must-haves are VERIFIED in the codebase with running-test and diff evidence: the producers catch dynamic-nav/coverage/wrong-section defects on the committed fixture, the single render_coverage_status helper routes html_render + both engine sites (with the documented _console_sigs exemption), require_render threads manifest→compiler→Step→consumers, the render-unavailable seam fails closed through the existing ValidationGate and records a distinct validator_skipped row, and INV-3 holds (zero new issues on goldens, byte-identical producer early returns, no new gate outcome, no migration, lint 4/0). The single outstanding item is the pre-existing/environmental od_ppt characterization, which the offline environment cannot adjudicate (full pytest hangs; local skills asset diverges from the golden's recording env) — routed to a CI/clean-env human re-confirm.

---

_Verified: 2026-07-01T09:20:00Z_
_Verifier: Claude (gsd-verifier)_
