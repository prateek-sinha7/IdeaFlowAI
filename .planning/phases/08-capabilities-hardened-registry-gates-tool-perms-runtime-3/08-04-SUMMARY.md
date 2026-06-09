---
phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
plan: 04
subsystem: validators
tags: [validator-registry, fix-loop, fixpolicy, hexagonal, severity, html-static, html-render, tier-validators, owner-scoped, inv-3-parity]

# Dependency graph
requires:
  - phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
    plan: 01
    provides: "@register/discover() self-registration + the single canonical map_severity (validators/severity.py, VALID-03)"
  - phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
    plan: 02
    provides: "ScopedStore.record_validation_result + validation_results table (0016) + the validation gate path (resolve validators + map_severity + block/warn)"
  - phase: 07-prototype-as-manifest-parity-proof-sc-001-2
    provides: "KernelServices ctx.runner handle + task_loop's unconditional run_validation_fix_loop delegation + the engine _run_validation_fix_loop (the single fix-loop home)"
provides:
  - "DeliverableContext (kernel-side): the validation target carrying path/content/runner-handle/step/task_meta a registered Validator receives"
  - "html_static/html_render registered Validators (app/agents/validators/) wrapping static_check/render_check, reached via the KernelServices handle (no kernel->app import)"
  - "Generic FixPolicy fix-loop: run_validation_fix_loop driven by deliverable name + max_attempts (not hardcoded prototype.html), byte-identical default"
  - "Tier#4/5/6 validators: spec_plan_coverage + task_done_when (kernel-side pure-stdlib), design_quality (app-side, warnings-first/non-blocking — P2/P3 only)"
  - "KernelServices handles: record_validation_result, deliverable_context, make_fix_policy (the strategy reaches them off ctx.runner — no kernel import)"
  - "task_loop re-point: drives the registered html_static/html_render + the generic FixPolicy loop, additive + event-free, at strict INV-3 parity (5 snapshots unchanged)"
affects: [08-05-runtime-prompt-providers, 08-07-hooks, 08-08-api-palette]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "App-side heavy-dep Validator: imports the kernel PORT + @register (legal app->capabilities), reaches the heavy check + audit writer ONLY via target.runner (no kernel->app edge)"
    - "DeliverableContext is the kernel-pure validation target; capabilities read attributes off the Any-typed target, never import it"
    - "Generic config-driven fix-loop: FixPolicy (deliverable + max_attempts) replaces the hardcoded prototype.html internals; default policy reproduces Phase-7 byte-for-byte"
    - "Additive event-free validator run: registered validators persist validation_results rows as a side effect after the byte-identical fix-loop — zero new events keeps the snapshots identical"
    - "Strategy reaches kernel-built objects (FixPolicy, DeliverableContext) through handle FACTORIES (runner.make_fix_policy / runner.deliverable_context), never importing the kernel"

key-files:
  created:
    - "backend/app/agents/validators/__init__.py"
    - "backend/app/agents/validators/html_static.py"
    - "backend/app/agents/validators/html_render.py"
    - "backend/app/agents/validators/design_quality.py"
    - "backend/agents/capabilities/validators/spec_plan_coverage.py"
    - "backend/agents/capabilities/validators/task_done_when.py"
    - "backend/tests/agents/test_validators.py"
  modified:
    - "backend/agents/execution_engine/kernel_services.py"
    - "backend/agents/capabilities/strategies/task_loop.py"
    - "backend/agents/capabilities/registry.py"
    - "backend/tests/agents/test_registry_capabilities.py"

key-decisions:
  - "html_static/html_render/design_quality live APP-side (heavy dep); spec_plan_coverage/task_done_when are pure-stdlib KERNEL-side (D-05 placement) — both import the single map_severity from 08-01"
  - "The fix-loop stays the engine's SINGLE _run_validation_fix_loop (no new loop, no move into the gate); FixPolicy makes its INTERNALS config-driven via the handle, byte-identical default (max_attempts=2)"
  - "task_loop runs the registered validators ADDITIVELY + EVENT-FREE after the byte-identical fix-loop (only writes validation_results rows) — so the 5 characterization snapshots stay byte/event-identical with no re-baseline"
  - "revision_validation STAYS a post_step (NOT converted to a gates:[validation] step): the post_step runs the revision-baselined fix sub-agent loop, which the generic validation gate does NOT replicate — converting it would NOT be byte/event-identical (decided with snapshot evidence)"
  - "_KNOWN + the lockstep registry count test bumped 22->25 for the three new Tier validator names (expected membership growth, not a snapshot re-baseline)"
  - "The strategy builds FixPolicy/DeliverableContext via runner.make_fix_policy / runner.deliverable_context (handle factories) because import-linter forbids agents.capabilities -> agents.execution_engine"

patterns-established:
  - "Pattern: app-side Validator wraps the heavy check, reached via the KernelServices handle (no kernel->app import; D-04 backbone)"
  - "Pattern: generic FixPolicy fix-loop (deliverable + max_attempts) replacing a hardcoded-filename loop at byte-identical default"
  - "Pattern: additive event-free capability run for audit persistence (validation_results) that keeps characterization snapshots identical"

requirements-completed: [VALID-01, VALID-02, VALID-04, VALID-05]

# Metrics
duration: ~50min
completed: 2026-06-09
---

# Phase 8 Plan 04: Validator Registry + Generic FixPolicy Fix-Loop + Tier#4/5/6 Validators Summary

**Stood up the Validator registry backbone (D-04): `html_static`/`html_render` migrated to registered app-side Validators wrapping `static_check`/`render_check` reached via the KernelServices handle (no kernel→app import), made the fix-loop generic (FixPolicy: deliverable + max_attempts, not hardcoded `prototype.html`), landed the Tier#4/5/6 validators (`spec_plan_coverage`/`task_done_when`/`design_quality` warnings-first), and re-pointed `task_loop`'s validation onto the registered validators + generic loop — all at strict INV-3 parity with the 5 characterization snapshots byte/event-identical and no re-baseline.**

## Performance

- **Duration:** ~50 min
- **Completed:** 2026-06-09
- **Tasks:** 3 (Tasks 1–2 TDD)
- **Files modified:** 11 (7 created, 4 modified)

## Accomplishments

- **D-04 Validator backbone:** `DeliverableContext` (kernel-pure: `path`/`content`/`runner`-handle/`step`/`task_meta`) is the target a registered `Validator` receives. `html_static` (wraps `static_check`) and `html_render` (wraps `render_check`, degrades to `available=False` offline) live in the new `app/agents/validators/` package — they import the kernel PORT (`agents.capabilities.base.Validator`) + `@register` (the import-linter-LEGAL app→capabilities direction) and reach the heavy checks ONLY through `target.runner.static_check`/`render_check`. The kernel/`task_loop` reach them via `resolve("validator", …)` + the handle — never an `app.*` import (lint-imports stays 3 kept / 0 broken).
- **VALID-03 single source honored:** every validator IMPORTS `map_severity` from `agents.capabilities.validators.severity` (08-01); zero new definitions (`grep "def map_severity" backend/agents/` = 1, 0 under `app/agents/validators/`).
- **VALID-01/02 generic fix-loop:** `KernelServices.run_validation_fix_loop` now drives off a `FixPolicy` (deliverable name + `max_attempts`) — running it with `deliverable="app.py"` operates on `app.py`, not `prototype.html`. The default policy (`max_attempts=2`, the engine's verbatim BUILD/REVISION fix-prompt wording) reproduces Phase-7 byte-for-byte; a bare `filename=` caller is wrapped into a default policy (back-compat for `revision_validation`). The loop stays the engine's SINGLE `_run_validation_fix_loop` — not moved into the gate (Pitfall 4).
- **VALID-05 Tier#4/5/6:** `spec_plan_coverage` (Tier#4 pre-build coverage, pure-stdlib kernel-side) + `task_done_when` (Tier#5 per-task acceptance, pure-stdlib kernel-side) + `design_quality` (Tier#6 tokens/placeholder/a11y, app-side, **warnings-first** — emits ONLY P2/P3, can never block). Each registered, run, exercised by ≥1 test manifest, severity via the imported `map_severity`, and writing a `validation_results` row.
- **D-06 re-point at INV-3 parity:** `task_loop` drives the generic FixPolicy loop (deliverable-driven via `runner.make_fix_policy`) and, after it, runs the step's DECLARED registered validators (`html_static`/`html_render`) via `resolve` + the handle — **additive + event-free** (only persists `validation_results` rows). The 5 characterization snapshots are byte/event-identical in a clean session — re-point parity PROVEN, NO re-baseline.
- **Persistence (D-10):** each validator run writes one owner/workspace-scoped `validation_results` row via `record_validation_result` (delegating to the Phase-5 `ScopedStore`); a cross-owner read returns nothing (T-08-04-ID default-deny proven).

## Task Commits

1. **Task 1: DeliverableContext + html_static/html_render registered validators (TDD)** — `4314b94` (feat)
2. **Task 2: generic FixPolicy fix-loop + Tier#4/5/6 validators (TDD)** — `8a7b207` (feat)
3. **Task 3: re-point task_loop validation onto registered validators; INV-3 parity** — `4c0de0b` (feat)

## Files Created/Modified

- `backend/app/agents/validators/{__init__,html_static,html_render,design_quality}.py` — the app-side heavy-dep Validator package (the package `__init__` imports the modules so `discover()` fires their `@register`); `html_static`/`html_render` wrap the heavy checks; `design_quality` is warnings-first.
- `backend/agents/capabilities/validators/{spec_plan_coverage,task_done_when}.py` — the pure-stdlib kernel-side Tier#4/5 validators (severity.py stays import-light; these are imported by `discover()`'s module list, not the package `__init__`).
- `backend/agents/execution_engine/kernel_services.py` — `DeliverableContext` + `FixPolicy` dataclasses; `record_validation_result`/`deliverable_context`/`make_fix_policy` handles; `run_validation_fix_loop` made generic (accepts `policy=`).
- `backend/agents/capabilities/strategies/task_loop.py` — the D-06 re-point: `_fix_policy` (deliverable-driven) + `_run_registered_validators` (additive, event-free) + threading the FixPolicy into the loop call.
- `backend/agents/capabilities/registry.py` — the 3 Tier validator names added to `_KNOWN` (impl-free membership) + to `discover()`'s kernel-side module list.
- `backend/tests/agents/test_validators.py` — 15 cases: resolution, handle-reach, offline render degrade, scoped persistence, single map_severity, generic FixPolicy (app.py vs prototype.html + back-compat), Tier#4/5/6 register/run/non-blocking, task_loop routing + no-op.
- `backend/tests/agents/test_registry_capabilities.py` — lockstep `_EXPECTED_NAMES` + count `22→25` bump.

## Decisions Made

- **Validator placement split (D-05).** Heavy-dep validators (`html_static`/`html_render`/`design_quality`) live app-side; the pure-stdlib Tier validators (`spec_plan_coverage`/`task_done_when`) live kernel-side — the documented boundary call, both importing the single `map_severity`.
- **Fix-loop made generic in place, not rebuilt.** `FixPolicy` parameterizes the engine's SINGLE `_run_validation_fix_loop` (deliverable + `max_attempts`); the default reproduces Phase-7 exactly. No new loop, no move into the gate.
- **Validators run additively + event-free.** `task_loop` runs the registered validators after the byte-identical fix-loop, persisting `validation_results` rows with zero new events — so the 5 snapshots stay identical.
- **revision_validation stays a post_step (decided with snapshot evidence).** Per the D-06 directive, the revision `revision_validation` post_step was evaluated for conversion to a `gates:[validation]` step. It was NOT converted: the post_step runs the revision-baselined fix sub-agent loop (pre-edit baseline + `user_instruction` re-injection), which the generic `validation` gate does NOT replicate (the gate runs validators + block/warn, it does not run the revision fix loop). `test_characterization_prototype_revision.py` proves the current post_step is byte/event-identical; converting it would change the event/timing structure and break parity. The post_step is retained.
- **`_KNOWN` + count test bumped 22→25.** The three new Tier validator names are expected membership growth (the drift guard caught the same-session count), not a snapshot re-baseline.

## Deviations from Plan

None — all three tasks landed with the planned files, acceptance gates, and locked decisions (D-04/D-05/D-06/D-10, VALID-01/02/04/05, VALID-03 single source). No deviation-rule auto-fixes were required.

The one in-plan adjustment (the `_KNOWN` literal + lockstep registry count bump 22→25) is a normal expected-membership growth surfaced by the existing drift-guard test, not a scope or parity deviation.

## Issues Encountered

- **Lockstep registry drift guard (Task 2).** Adding the three Tier validators via `@register` grows `_KNOWN` from 22 to 25 once `discover()` runs; the same-session run of `test_validators.py` then `test_registry_capabilities.py::test_registered_count_is_exactly_twenty_two` tripped the count assert (25 ≠ 22). Resolved by bumping the literal + the lockstep test 22→25 (the documented Wave-2 lockstep pattern — expected growth, not a re-baseline).
- **Strategy cannot import the kernel for FixPolicy/DeliverableContext.** import-linter forbids `agents.capabilities -> agents.execution_engine`, so the strategy cannot import `FixPolicy`/`DeliverableContext` directly. Resolved by adding handle FACTORIES (`runner.make_fix_policy` / `runner.deliverable_context`) the strategy reaches off `ctx.runner` — the kernel constructs the objects, the strategy never imports the kernel. A handle lacking the factory (an old unit fake) falls back to the bare `filename=` call (byte-identical), so `test_strategies.py` stays green.

## User Setup Required

None — no external service configuration; all checks run offline (`render_check` degrades to `available=False` without Chromium).

## Next Phase Readiness

- **08-05 (runtime/prompt/providers):** the validator registry + the generic FixPolicy loop + the `DeliverableContext`/handle-factory pattern are the seams the prompt/runtime providers reach through `ctx.runner`.
- **08-07 (hooks):** the additive event-free capability-run pattern (validators persisting `validation_results` without emitting events) is the template for hook runs persisting `hook_runs`.
- **08-08 (API palette):** `html_static`/`html_render`/`spec_plan_coverage`/`task_done_when`/`design_quality` all register `user_allowed=True` and resolve from the registry — ready for the `GET /api/capabilities` palette.
- lint-imports (3 contracts kept), banned-pattern, migration-ledger, and the 5 characterization snapshots all stay green; `map_severity` single source (grep = 1).

## Self-Check: PASSED

---
*Phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3*
*Completed: 2026-06-09*
