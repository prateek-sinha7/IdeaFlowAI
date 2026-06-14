---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
plan: 01
subsystem: api
tags: [compiler, manifest, model-policy, retry, injects, langgraph, tdd, inv-3]

# Dependency graph
requires:
  - phase: 04 (compiler)
    provides: WorkflowCompiler + _ALLOWED_STEP_KEYS strict-key allow-list + the two constructors (Step / CompiledWorkflow)
  - phase: 06 (model policy)
    provides: ModelResolver tiers 2 (step.model) & 4 (workflow.model)
  - phase: 12 (RESUME-02)
    provides: the per-step retry wrapper gated on step.retry.max_attempts > 0
provides:
  - "Compiler materialization of per-step model:/retry:/injects:/fix:/depends_on: + top-level model: (no more accepted-but-dropped step keys)"
  - "AgentContext.step_injects + a generic order-stable injects merge at the factory _compose_system_prompt seam (WIRE-03 consume side)"
  - "test_allowed_step_keys.py — the durable D-17 parametrized consumed-or-raises guard over _ALLOWED_STEP_KEYS"
affects: [EMP-01 composer levers, EMP-03 saved-selection launch, WIRE-* downstream plans, any future _ALLOWED_STEP_KEYS addition]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inert-field-made-live: coerce raw.get(key) → typed policy, pass through the Step/CompiledWorkflow constructor, no _ALLOWED_STEP_KEYS loosening (INV-5)"
    - "Generic per-step consume seam: thread the compiled Step value onto AgentContext off ectx.current_step (name-free), merge in the factory — SC-001"
    - "Durable parametrized allow-list guard driven directly off the frozenset so a future key forces a consumed-or-raises decision"

key-files:
  created:
    - backend/tests/agents/test_allowed_step_keys.py
  modified:
    - backend/agents/workflows/compiler.py
    - backend/agents/workflows/plan.py
    - backend/agents/factory.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/test_compiler.py
    - backend/tests/unit/test_factory_injects.py

key-decisions:
  - "WIRE-03 = materialize-and-consume (D-16): step.injects merged with spec.injects order-stably; empty step_injects → byte-identical (proven by 5 goldens) — NOT reject-loudly."
  - "Materialize fix: and depends_on: too (not just the named WIRE-01/02/03 keys) — the D-17 guard requires NO _ALLOWED_STEP_KEYS entry be accepted-but-dropped."
  - "Added Step.depends_on field (the _validate_dag Kahn sort already read it via getattr) — the only plan.py field addition; the WIRE fields already existed."

patterns-established:
  - "Strict-key nested coercion helpers (_compile_model_policy / _compile_retry_policy / _compile_fix_policy) reject unknown nested keys (INV-5 at every level)."
  - "Per-step compiled value → factory consume via ectx.current_step (same seam current_step.hooks uses), never a workflow/agent-name branch (SC-001)."

requirements-completed: [WIRE-01, WIRE-02, WIRE-03]

# Metrics
duration: 8min
completed: 2026-06-14
---

# Phase 22 Plan 01: Compiler Latent-Key Materialization (WIRE-01/02/03) Summary

**The compiler now passes per-step `model:`/`retry:`/`injects:`/`fix:`/`depends_on:` and top-level `model:` through to the typed plan (no more accepted-but-dropped keys), the factory merges per-step injects generically at the prompt seam, and a durable parametrized guard proves every `_ALLOWED_STEP_KEYS` entry is consumed-or-raises (D-17) — all with the 5 characterization goldens byte-identical (INV-3).**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-14T19:59:05Z
- **Completed:** 2026-06-14T20:06:17Z
- **Tasks:** 2 (TDD: RED then GREEN)
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments
- WIRE-01: per-step `model:` → `Step.model` and top-level `model:` → `CompiledWorkflow.model`, both coerced to typed `ModelPolicy` (ModelResolver tiers 2/4 now reach declared ids).
- WIRE-02: per-step `retry:` → `Step.retry` (typed `RetryPolicy`) — the RESUME-02 wrapper is now manifest-reachable.
- WIRE-03: per-step `injects:` → `Step.injects`, consumed via a generic order-stable de-duplicated merge with the AGENT.md `spec.injects` at the `_compose_system_prompt` seam (materialize-and-consume, D-16). Empty step injects → byte-identical (the 5 goldens are the mechanical proof).
- D-17: new `test_allowed_step_keys.py` parametrized over `_ALLOWED_STEP_KEYS` — each key reflected on the compiled object OR raises `CompilerError`; a non-allow-listed key still raises (INV-5 preserved). Also materialized `fix:` and `depends_on:` to close the last two accepted-but-dropped keys.

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1: WIRE-01/02/03 RED gates + D-17 guard (tests)** - `cd2bd4a2` (test)
2. **Task 2: materialize model/retry/injects/fix/depends_on + factory merge (GREEN)** - `56537f98` (feat)

_Note: TDD plan — RED `test(...)` commit precedes the GREEN `feat(...)` commit._

## Files Created/Modified
- `backend/tests/agents/test_allowed_step_keys.py` (created) - The D-17 parametrized consumed-or-raises guard over `_ALLOWED_STEP_KEYS`.
- `backend/agents/workflows/compiler.py` - 3 strict-key coercion helpers + pass-through of `model`/`retry`/`injects`/`fix`/`depends_on` in the `Step(...)` constructor and `model=` in `CompiledWorkflow(...)`.
- `backend/agents/workflows/plan.py` - Added `Step.depends_on` field (the DAG already read it via getattr).
- `backend/agents/factory.py` - `AgentContext.step_injects` + the generic order-stable de-duplicated merge in `_compose_system_prompt`.
- `backend/agents/execution_engine/engine.py` - Thread compiled `step.injects` onto `AgentContext.step_injects` off `ectx.current_step` (name-free).
- `backend/tests/agents/test_compiler.py` - WIRE-01 (per-step + top-level model) / WIRE-02 (retry) / WIRE-03 (injects) materialization + absent-is-parity cases.
- `backend/tests/unit/test_factory_injects.py` - WIRE-03 consume side: empty-injects byte-identical no-op + merge-adds-step-inject-no-duplication.

## Decisions Made
- **Took D-16 materialize-and-consume** (not the reject-loudly fallback): the research INV-3-safety proof held — `step.injects == []` for every golden step → the merge returns exactly `spec.injects` → byte-identical. Confirmed by running the goldens (no re-baseline).
- **Merge keys on the generic `ctx.step_injects`** read off `ectx.current_step` — the same per-run-state seam `current_step.hooks` uses — never a workflow/agent name (SC-001).
- **Section render order is canonical inside `_compose_injection`** (critical → design_system → craft → template), independent of the merged list order — so the merge's contract is set-membership + de-duplication, not section placement (the Task-1 RED test's position assertion was corrected to assert membership in Task 2).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Materialized `fix:` and `depends_on:` (beyond the named WIRE-01/02/03 keys)**
- **Found during:** Task 1 (authoring the D-17 parametrized guard)
- **Issue:** The plan's named scope is `model:`/`retry:`/`injects:` (WIRE-01/02/03), but the D-17 must-have ("NO `_ALLOWED_STEP_KEYS` entry is accepted-but-dropped") and the plan's own Task-1 instruction ("cover every current key incl. `depends_on`, `fix`, `tools`") require EVERY key to be consumed-or-raises. `fix:` (Step.fix field existed, never wired) and `depends_on:` (no Step field; `_validate_dag` read a non-existent attr via getattr) were both still accepted-but-dropped — the guard would fail without materializing them.
- **Fix:** Coerce `raw.get("fix")` → `FixPolicy` via a new `_compile_fix_policy` helper and pass `fix=` to the Step constructor; add a `Step.depends_on` field and pass `depends_on=list(raw.get("depends_on") or [])`. Both follow the same inert-field-made-live precedent; `_ALLOWED_STEP_KEYS` is untouched (INV-5).
- **Files modified:** backend/agents/workflows/compiler.py, backend/agents/workflows/plan.py
- **Verification:** `test_allowed_step_keys.py` green for the `fix` and `depends_on` cases; 5 goldens byte-identical (these keys are absent from every golden manifest → parity).
- **Committed in:** `56537f98` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing-critical, required by the plan's own D-17 must-have)
**Impact on plan:** Necessary to satisfy the D-17 acceptance criterion. No scope creep beyond the plan's stated "cover every current key" requirement; `plan.py` edit limited to the single `depends_on` field the DAG already expected.

## Issues Encountered
- The factory merge RED test initially asserted a template-before-craft section position; the actual `_compose_injection` render order is fixed/canonical and not driven by the merge list. Corrected the assertion to verify set membership + no duplication (the merge's real contract). Not a code bug — a test-expectation correction made before the GREEN commit.

## Known Stubs
None — `Step.fix` is a forward-surface field with no engine consumer yet (FixPolicy is consumed in a later phase), but it is now correctly materialized on the compiled Step (not a stub: the value round-trips and is reflected, satisfying D-17). No empty/placeholder data flows to any UI.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The backend foundation EMP-01 stands on is in place: a user-selected non-default model + retry now reach execution via the compiler. Downstream plans (palette UI, per-agent Advanced expander, saved-selection save/launch re-validation) can rely on `model:`/`retry:`/`injects:` materializing.
- The dormant `trust="user"` compile path is untouched here (its first caller is a later plan in this phase).
- INV-3 goldens, SC-001 banned-patterns (44 passed / 7 skipped), and lint-imports (4 kept / 0 broken) all green.

---
*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime-*
*Completed: 2026-06-14*

## Self-Check: PASSED
- Created file present: backend/tests/agents/test_allowed_step_keys.py (FOUND)
- Modified files present: compiler.py, plan.py, factory.py, engine.py (FOUND)
- Commits present: cd2bd4a2 (RED), 56537f98 (GREEN) (FOUND)
- INV-3: 5 characterization goldens byte-identical (10 passed)
- SC-001 grep on compiler.py + factory.py: 0 hits; engine.py diff name-free
- lint-imports: 4 kept / 0 broken; targeted suite 44 passed / 7 skipped
