---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
plan: 06
subsystem: engine
tags: [context-provider, opendesign, byte-parity, characterization, INV-1, INV-3, hexagonal]

# Dependency graph
requires:
  - phase: 07-prototype-as-manifest-parity-proof-sc-001-2 (07-02)
    provides: the opendesign ContextProvider capability + the relocated od_context loaders
  - phase: 07-prototype-as-manifest-parity-proof-sc-001-2 (07-04)
    provides: the generic context injector + KernelServices handle (template_example / template_injection_parts)
  - phase: 07-prototype-as-manifest-parity-proof-sc-001-2 (07-05)
    provides: SC-001 (L1-L13 deleted) + the kernel-scoped banned-pattern hard-fail gate
provides:
  - opendesign provider is now a byte-faithful lift of the legacy L12 injection branches (git fb55699)
  - DS block content = instruction preamble + ds_body (CR-01)
  - example.html builder-gated on ctx.current_spec_tools (CR-02 — planning agents no longer leak the working HTML doc)
  - DS/template/example suppressed + seed-only injection parts on build tasks 2+ (CR-03)
  - engine threads ectx.current_spec_tools to providers via the D-03 per-run-state-on-ctx pattern (no spec.id/pipeline_type branch)
  - context_message de-blinded — removed from _VOLATILE_STRIP_KEYS; pinned by 5 regenerated golden snapshots + a dedicated normalizer-independent parity assertion
affects: [phase-08, dynamic-composer, any-future-context-provider-capability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-03 per-run-state-on-ExecutionContext: the engine threads the consuming agent's OPAQUE tool set (ectx.current_spec_tools) to the provider before provider.load — the same dynamic-attr mechanism as ectx.compiled_context_providers; the provider does the tool-based gating, the kernel stays name/id-free (INV-1)"
    - "context_message parity is pinned by BOTH a normalizer-independent unit assertion AND the de-blinded characterization golden snapshots — a context-injection regression can no longer pass for the wrong reason"

key-files:
  created: []
  modified:
    - backend/agents/capabilities/context_providers/opendesign.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/test_context_providers.py
    - backend/tests/agents/characterization/_normalize.py
    - backend/tests/agents/characterization/golden/prototype.events.json
    - backend/tests/agents/characterization/golden/od_prototype.events.json
    - backend/tests/agents/characterization/golden/prototype_revision.events.json
    - backend/tests/agents/characterization/golden/od_ppt.events.json
    - backend/tests/agents/characterization/golden/app_builder.events.json

key-decisions:
  - "Preamble kept on a SINGLE source line (not split literals) so the exact-byte parity grep matches the contiguous string; runtime value is preamble + ds_body, byte-identical to git fb55699"
  - "Removed `spec.id`/`pipeline_type` even from the provider's COMMENT prose — the INV-1 acceptance grep must return 0, so the comment was reworded to 'workflow name/id'"
  - "context_message un-stripped from _VOLATILE_STRIP_KEYS: the scripted fixtures proved the value is parity-stable (no UUID/timestamp leakage in any of the 5 golden snapshots); both pins (golden + dedicated unit assertion) are active, exceeding the plan's 'one-of' requirement"

patterns-established:
  - "Provider-side opaque-tool gating: a capability receives the consuming agent's tool SET on ctx and decides injection itself — the kernel never branches on workflow identity"

requirements-completed: [PARITY-03, PARITY-09]

# Metrics
duration: ~25min
completed: 2026-06-09
---

# Phase 07 Plan 06: opendesign L12 byte-parity gap closure Summary

**Restored the opendesign provider to a byte-faithful lift of the legacy L12 injection branches (DS preamble CR-01, builder-gated example CR-02, build-task-2+ suppression CR-03) by threading the opaque agent tool set onto the ExecutionContext, then de-blinded the characterization net so context_message is pinned by both golden snapshots and a normalizer-independent parity assertion.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-06-09
- **Tasks:** 3
- **Files modified:** 9 (2 source, 2 test, 5 golden snapshots)

## Accomplishments
- CR-01: the `ACTIVE DESIGN SYSTEM` block content is now the instruction preamble + ds_body, byte-identical to git fb55699 (spaces after each comma).
- CR-02: `example.html` injects ONLY for builder tool sets (`ctx.current_spec_tools & {prototype_emit_only, prototype}`) — tools:[] planning agents (prototype-specify / prototype-plan) no longer receive the full working HTML doc (information-exposure hardening, T-07-06-01).
- CR-03: on build tasks 2+ the DS / template / example blocks are suppressed and only the seed injection part survives, gated on the builder tool set + `ctx.build_task_number` (never on `spec.id`).
- engine `_compose_context_message` threads `ectx.current_spec_tools` to providers via the D-03 dynamic-attr pattern (mirrors `ectx.compiled_context_providers`) — INV-1 preserved, the 07-05 banned-pattern hard-fail gate stays green.
- Closed the structural blind spot: `context_message` removed from `_VOLATILE_STRIP_KEYS`, the 5 golden event snapshots regenerated parity-stable (verified twice, no per-run rewrite, no UUID/timestamp leakage), PLUS a dedicated normalizer-independent parity assertion pins the exact ordered block-key sequence + bytes for build task 1 and the suppressed seed-only set for build task 2.

## Task Commits

Each task was committed atomically:

1. **Task 1: Restore the L12 byte contract in opendesign.py + thread ectx.current_spec_tools** - `2a4335a` (fix)
2. **Task 2: Fix the locked-in test:114 assertion + add CR-01/02/03 parity assertions** - `e8e4a89` (test)
3. **Task 3: Dedicated context_message parity assertion + de-blind the characterization normalizer** - `fdd8aef` (test)

_Note: Task 1 carries `tdd="true"`; the existing 5-pipeline characterization suite + the corrected unit tests are the RED/GREEN net. Provider + engine landed in a single source commit; the pinning assertions are Task 2/3 per the plan's task split._

## Files Created/Modified
- `backend/agents/capabilities/context_providers/opendesign.py` - DS preamble (CR-01), builder-gated example (CR-02), task-2+ suppression + tool-gated injection-parts branch (CR-03); reads `ctx.current_spec_tools` + `ctx.build_task_number`; no app.*/kernel import.
- `backend/agents/execution_engine/engine.py` - `_compose_context_message` sets `ectx.current_spec_tools = set(spec.tools)` before the provider loop (D-03), no spec.id/pipeline_type branch.
- `backend/tests/agents/test_context_providers.py` - line-114 fix + `test_opendesign_ds_block_has_preamble`, `test_opendesign_example_gated_on_builder_tools`, `test_opendesign_build_task_2_plus_suppresses_ds_template_example`, `test_context_message_parity_build_task_1_vs_task_2`; `_Ctx` threads the two new ctx reads.
- `backend/tests/agents/characterization/_normalize.py` - `context_message` removed from `_VOLATILE_STRIP_KEYS` (genuinely-volatile keys timestamp/run_id/seq/event_id retained).
- `backend/tests/agents/characterization/golden/*.events.json` (×5) - regenerated parity-stable so context_message is now pinned.

## Decisions Made
- Kept the DS preamble on a single source line so the exact-byte acceptance grep matches the contiguous string; runtime value is still `preamble + ds_body`.
- Reworded the provider comment to avoid the literal tokens `spec.id ==` / `pipeline_type` because the INV-1 acceptance grep must return 0 even against prose.
- Un-stripped context_message (rather than relying solely on the dedicated assertion): the scripted fixtures proved the value is parity-stable with no run-id/timestamp leakage, so BOTH pins are active — exceeding the plan's escape-hatch "one-of" requirement.

## Deviations from Plan

None - plan executed exactly as written. The plan's discretionary escape hatch (keep context_message stripped if un-stripping reintroduces volatility) was NOT needed — un-stripping was clean and parity-stable.

## Issues Encountered
- The acceptance grep `grep -nE 'spec\.id ==|pipeline_type'` initially returned 1 from the explanatory COMMENT in the provider, and the CR-01 preamble grep initially returned 0 because the string was split across two literals. Both resolved by rewording the comment and consolidating the preamble onto one source line — no behavioral change.

## TDD Gate Compliance
Task 1 is `tdd="true"`. The RED net is the existing 5-pipeline characterization suite + the pre-existing `test_context_providers.py` (which the byte-restoration intentionally broke at line 114, then Task 2 corrected to assert the new contract). No separate failing-test-only commit was created because the failing net already existed; this is consistent with a brownfield byte-parity restoration where the characterization snapshots are the behavioral oracle.

## Verification Evidence
- `tests/agents/test_context_providers.py` — 13 passed (CR-01 preamble, CR-02 example gate, CR-03 suppression, dedicated context_message parity).
- 5-pipeline characterization suite (prototype/od_prototype/prototype_revision/od_ppt/app_builder) — 10 passed; golden snapshots regenerated and confirmed parity-stable across two no-update runs.
- `test_banned_patterns.py` + `test_migration_ledger.py` — 26 passed, 1 skipped (INV-1 hard-fail gate + ledger ratchet NOT regressed).
- Full `tests/agents/ tests/unit/ -m "not requires_api_key"` — 1038 passed, 19 skipped, 8 failed. The 8 failures are the KNOWN pre-existing unrelated suites (7× `test_logout.py` auth, 1× `test_pipeline_cancel.py`) — matches the 07-VERIFICATION baseline; ZERO new failures introduced by this plan.
- Acceptance greps: CR-01 preamble present (1), CR-02 builder gate present (1), CR-03 build_task_number/is_build_task_2_plus present, current_spec_tools threaded in engine (1), INV-1 `spec.id ==|pipeline_type` in provider = 0, `spec.id == "prototype-build"` in engine = 0, app.*/execution_engine import in provider = 0, context_message removed from _VOLATILE_STRIP_KEYS (0), volatile keys retained (timestamp/run_id/seq/event_id ≥1 each).

## Next Phase Readiness
- PARITY-03 (opendesign context provider byte parity vs L12) and PARITY-09 (all-5-pipeline context_message byte parity vs the post-0C baseline) are closed; the two FAILED truths from 07-VERIFICATION are resolved.
- The characterization net now pins context_message — future context-injection drift hard-fails CI.
- No blockers. 07-01…07-05 untouched beyond the four files this gap-closure plan declares.

## Self-Check: PASSED

All declared files exist on disk and all three task commits (`2a4335a`, `e8e4a89`, `fdd8aef`) are present in the git log.

---
*Phase: 07-prototype-as-manifest-parity-proof-sc-001-2*
*Completed: 2026-06-09*
