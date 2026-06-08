---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
plan: 01
subsystem: infra
tags: [capabilities, hexagonal, ports-and-adapters, registry, execution-strategy, task-parser, langchain-deepagents]

# Dependency graph
requires:
  - phase: 04-capability-seam
    provides: CapabilityRegistry + _KNOWN membership set + the six Protocol ports (base.py)
  - phase: 05-typed-substrate
    provides: ExecutionContext object-typed per-run fields (scoped_store/model_resolver template) + ArtifactGraph typed reads
  - phase: 06-model-policy
    provides: model_resolver/model_overrides per-run fields (the object-typed precedent extended by D-03 runner)
provides:
  - "CapabilityRegistry.resolve(kind,name) — the D-02 name->impl resolution seam (static dict lookup, no dynamic name resolution)"
  - "CapabilityRegistry.install()/_register_builtins() — explicit lazy impl binding (no @register/discover machinery)"
  - "ExecutionContext.runner — the D-03 object-typed KernelServices handle field"
  - "HeadingTasksParser (name='heading_tasks') — verbatim lift of _count_plan_tasks/_extract_task_block"
  - "SingleShotStrategy (name='single_shot') — one-agent run+re-yield behind ExecutionStrategy"
  - "TaskLoopStrategy (name='task_loop') — the full prototype build loop (seed/parse/per-task/compaction-route/validation-fix) behind ExecutionStrategy"
affects: [07-02-context-providers-deliverables, 07-03-compaction-validators-gates, 07-04-engine-wiring, 07-05-leak-deletion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-02 resolution seam: separate (kind,name)->impl map populated by explicit install(), distinct from the _KNOWN compiler-membership set"
    - "D-03 runner handle: a single object-typed ctx.runner field is the SOLE path a capability reaches kernel/app primitives (import-linter-safe)"
    - "Strategy-local task scratch: per-task block + counters live in TaskLoopStrategy, never on engine self/ctx (L14 ratchet)"

key-files:
  created:
    - backend/agents/capabilities/task_parsers/heading_tasks.py
    - backend/agents/capabilities/task_parsers/__init__.py
    - backend/agents/capabilities/strategies/single_shot.py
    - backend/agents/capabilities/strategies/task_loop.py
    - backend/agents/capabilities/strategies/__init__.py
    - backend/tests/agents/test_capability_resolution.py
    - backend/tests/agents/test_heading_tasks_parser.py
    - backend/tests/agents/test_strategies.py
  modified:
    - backend/agents/capabilities/registry.py
    - backend/agents/execution_engine/context.py

key-decisions:
  - "resolve() rejects unknown names against _KNOWN BEFORE any impl-map lookup (T-07-01-01: no manifest name can reach the map / become a code-exec vector)"
  - "install() does explicit local-import binding (not @register/discover); resolve() lazy-binds on first call so callers need not order install()"
  - "The KernelServices handle is one object with run_agent/run_fix_agent/sandbox/latest_typed_content/static_check/render_check/od_context/cancel_event/run_id — defined as the SHAPE strategies call against; concrete class lands in 07-04"
  - "task-2+ compaction routes through resolve('compaction','html_skeleton') now; returns None until the impl lands (07-03) so the call site is parity-safe"

patterns-established:
  - "Capability impls satisfy ports structurally (name attr + method); name == registry key == manifest reference"
  - "Capability modules import only stdlib + agents.workflows.plan; never agents.execution_engine/app; never construct a deep-agent graph (INV-13)"

requirements-completed: [PARITY-01]

# Metrics
duration: 35min
completed: 2026-06-08
---

# Phase 7 Plan 01: Execution Strategy + Resolution Seams Summary

**The two execution strategies (single_shot, task_loop), the heading_tasks parser, the D-02 name->impl resolve() seam, and the D-03 object-typed ctx.runner handle — the foundational capability seams every later 07 plan routes through, built behind the ExecutionStrategy/TaskParser ports with zero kernel/app imports.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-06-08
- **Completed:** 2026-06-08
- **Tasks:** 2
- **Files modified:** 10 (8 created, 2 modified)

## Accomplishments
- D-02 resolution seam: `CapabilityRegistry.resolve(kind,name)` as a static dict lookup over a separate `_IMPLS` map, plus an explicit lazy `install()`/`_register_builtins()` — the compiler's `is_registered`/`_KNOWN` membership path left untouched and impl-free at compiler import.
- D-03 runner handle: `ExecutionContext.runner` object-typed field, documented identically to `scoped_store`/`model_resolver` so `context.py` stays import-pure; the full `KernelServices` shape (run_agent/run_fix_agent/sandbox/validators/typed-content/od_context) is the contract strategies call against.
- `HeadingTasksParser` lifts `_count_plan_tasks`/`_extract_task_block` verbatim (the `## Task N:` regex + `<tasks>` fallback) returning `list[Task]` with byte-identical bodies.
- `SingleShotStrategy` + `TaskLoopStrategy` behind the `ExecutionStrategy` port; `task_loop` absorbs seed-files write, parser-resolution, per-task sub-agent invocation, task-2+ compaction routing, and the Both-validation + bounded N=2 fix-loop (pure fix-sig helpers lifted verbatim) — all through `ctx.runner`, no kernel/app import, no deep-agent graph construction (INV-13).
- 25 new Wave-0 unit tests (13 resolution + 6 parser + 9 strategy, includes the PARITY-01 "drive both strategies from a compiled Step" acceptance).

## Task Commits

Each task was committed atomically:

1. **Task 1: D-02 resolution seam + D-03 runner handle + heading_tasks parser** - `0a19dd4` (feat)
2. **Task 2: single_shot + task_loop strategies (behavior lift, no kernel import)** - `8f68a6c` (feat)

**Plan metadata:** _(this commit)_

_Note: this is a relocation phase — strategies/parser are verbatim lifts of named engine regions (INV-12 move-don't-copy)._

## Files Created/Modified
- `backend/agents/capabilities/registry.py` - Added `_IMPLS` map, `install()`/`_register_builtins()`, `resolve()`; `is_registered`/`resolve_alias`/`_KNOWN` untouched.
- `backend/agents/execution_engine/context.py` - Added object-typed `runner` handle field (D-03).
- `backend/agents/capabilities/task_parsers/heading_tasks.py` - `HeadingTasksParser` + verbatim `_count_plan_tasks`/`_extract_task_block`.
- `backend/agents/capabilities/strategies/single_shot.py` - `SingleShotStrategy` (one-agent run + re-yield).
- `backend/agents/capabilities/strategies/task_loop.py` - `TaskLoopStrategy` + verbatim pure fix-sig helpers + the validation/fix loop + seed-files write.
- `backend/tests/agents/test_capability_resolution.py` - resolve()/install() seam tests (incl. T-07-01-01 no-dynamic-resolution gate).
- `backend/tests/agents/test_heading_tasks_parser.py` - parser cases (byte-identical bodies, `<tasks>` fallback, empty).
- `backend/tests/agents/test_strategies.py` - both strategies driven from a compiled Step against a fake `ctx.runner` (PARITY-01).

## Decisions Made
- `resolve()` checks `_KNOWN` first so an unknown/path-traversal-looking name raises `KeyError` before any map access (T-07-01-01 mitigation), and raises `RuntimeError` for a known-but-unbound name rather than returning `None`.
- `install()` uses local imports inside the function so importing `registry` for the membership path never drags in impl modules (keeps the compiler import impl-free; avoids import cycles); `resolve()` lazy-binds on first call.
- The runner handle is modelled as ONE object with many methods (RESEARCH Open Q1) attached as `ctx.runner`; the concrete `KernelServices` class is deferred to 07-04 (this plan defines the shape strategies depend on, documented in the strategy docstrings).
- task-2+ compaction routes through `resolve('compaction','html_skeleton')` and is skipped (returns `None`) until the impl lands in 07-03 — the call site is wired now, parity-safe meanwhile.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reworded threat-model prose in docstrings to satisfy the literal grep gates**
- **Found during:** Tasks 1 and 2
- **Issue:** The acceptance-criteria greps (`getattr|eval\(|importlib|__import__` over `registry.py`; `create_deep_agent` over the strategy files) matched explanatory docstring/comment prose that *describes* the banned patterns (stating the code does NOT use them), tripping the gates despite the code being clean.
- **Fix:** Reworded the docstrings/comments to describe the constraint without the literal tokens ("no dynamic name resolution of any kind"; "no deep-agent graph is constructed here"); also made `test_resolve_uses_no_dynamic_name_resolution` strip the docstring before inspecting the `resolve` body so the threat-model prose can't false-trip.
- **Files modified:** backend/agents/capabilities/registry.py, backend/agents/capabilities/strategies/single_shot.py, backend/agents/capabilities/strategies/task_loop.py, backend/agents/capabilities/strategies/__init__.py, backend/tests/agents/test_capability_resolution.py
- **Verification:** `grep -nE "getattr|eval\(|importlib|__import__" registry.py` exit 1 (no match); `grep -rnE create_deep_agent strategies/` exit 1; all unit tests pass.
- **Committed in:** 0a19dd4 (Task 1) + 8f68a6c (Task 2)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Cosmetic doc rewording to satisfy the literal-grep acceptance gates; no behavioral change. No scope creep.

## Issues Encountered
- Full `tests/unit/` run surfaced 8 pre-existing failures in unrelated subsystems (7 in `tests/unit/test_logout.py` JWT/JTI revocation, 1 in `tests/unit/test_pipeline_cancel.py`). Confirmed they fail independently of this plan's changes (07-01 touches only `agents/capabilities/**` + `context.py`). Logged to `deferred-items.md` per the SCOPE BOUNDARY rule; not fixed here. The plan's stated baseline net (`tests/agents` characterization/parity) is GREEN (16 passed, 1 skipped across characterization + migration-ledger + banned-patterns).

## Known Stubs
- `TaskLoopStrategy` task-2+ compaction call routes through `resolve('compaction','html_skeleton')` which returns `None` until the `html_skeleton` impl lands in 07-03. This is intentional and documented (`_maybe_resolve_compaction`); the call site is wired and parity-safe (compaction skipped). Resolved by: 07-03.
- The `KernelServices` concrete class backing `ctx.runner` is not yet implemented — strategies are exercised against a fake handle this plan. Intentional per plan scope (the engine is wired to attach the real handle in 07-04). Resolved by: 07-04.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The D-02 resolve seam + D-03 runner handle exist for 07-02/03/04 to build on: context providers / deliverables (07-02), compaction / validators / gates (07-03) register their impls into `install()` and reach kernel primitives via `ctx.runner`.
- 07-04 must implement the concrete `KernelServices` class matching the contract documented in `single_shot.py`/`task_loop.py` and attach it as `ctx.runner` in `execute()`, then route step dispatch through `resolve('strategy', step.strategy).run(step, ctx)`.
- No leak deleted and engine not yet rewired (by design — that is 07-04/07-05); L1-L13 stay live, 0A/ledger/banned-pattern green.

## Self-Check: PASSED

All 8 created files exist on disk; both task commits (`0a19dd4`, `8f68a6c`) exist in git history.

---
*Phase: 07-prototype-as-manifest-parity-proof-sc-001-2*
*Completed: 2026-06-08*
