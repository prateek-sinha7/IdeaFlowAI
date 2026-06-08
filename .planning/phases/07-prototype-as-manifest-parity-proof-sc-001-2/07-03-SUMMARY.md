---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
plan: 03
subsystem: infra
tags: [capabilities, compaction, html-skeleton, hexagonal, strangler, token-trim, parity]

# Dependency graph
requires:
  - phase: 07-01
    provides: "CapabilityRegistry.resolve(kind,name) + install() seam; task_loop's resolve('compaction', step.compaction).compact() call site (parity-safe, returns None until impl lands)"
  - phase: 03-token-trim-measured-change-0c
    provides: "the 0C build-task-2+ compaction (_extract_html_skeleton) + the deterministic >=50% reduction CI gate this capability must preserve"
provides:
  - "HtmlSkeletonCompaction (name='html_skeleton') — verbatim lift of engine._extract_html_skeleton as a pure compact(html)->str compaction capability (PARITY-04)"
  - "install() binding ('compaction','html_skeleton') -> HtmlSkeletonCompaction() — task_loop's task-2+ compaction route now resolves to a real impl"
  - "re-pointed test_phase3_compaction.py: the 0C >=50% reduction gate now measured against the capability; byte-parity test pins capability == engine helper (strangler wrap)"
affects: [07-04-engine-wiring, 07-05-leak-deletion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Compaction capability contract: name attr + compact(html: str) -> str — the structural shape task_loop calls via resolve('compaction', step.compaction).compact(prior_html). No CompactionStrategy Protocol port exists in base.py; the contract is structural (duck-typed), matching the 07-01 call site."
    - "Strangler 'wrap' step: the capability is a byte-identical lift; the engine's inline _extract_html_skeleton stays live until 07-04 routes through task_loop and 07-05 deletes the engine copy. Temporary 07-03->07-05 duplication is the sanctioned strangler transition."

key-files:
  created:
    - backend/agents/capabilities/compaction/__init__.py
    - backend/agents/capabilities/compaction/html_skeleton.py
  modified:
    - backend/agents/capabilities/registry.py
    - backend/tests/agents/test_phase3_compaction.py

key-decisions:
  - "html_skeleton is a VERBATIM lift of engine._extract_html_skeleton (engine.py:3526-3577) into compact(self, html: str) -> str; the algorithm is copied unchanged because the 0C >=50% reduction gate is calibrated to its exact byte output."
  - "The capability satisfies the compaction contract STRUCTURALLY (name + compact()) — there is no CompactionStrategy Protocol in base.py; the binding contract is the task_loop call site from 07-01 (.compact(prior_html)). No new port type was added (out of scope; would be a base.py edit)."
  - "test_phase3_compaction.py re-pointed: the two direct engine._extract_html_skeleton calls (the >=50% reduction test and the fidelity test) now call HtmlSkeletonCompaction().compact(); the >=50% reduction assertions are PRESERVED. The _build_context_message message-assembly assertions stay on the engine (07-04 routes injection through the generic injector; 07-05 deletes _build_context_message)."
  - "Added a byte-parity test asserting capability output == engine._extract_html_skeleton on the calibration fixture — pins the strangler wrap until 07-05 deletes the engine copy."
  - "engine._extract_html_skeleton left INTACT/live (deleted in 07-05); removing it here would break the still-coupled engine 0C path (strangler sequencing)."

patterns-established:
  - "Compaction capability: pure stdlib (re) module, no agents.execution_engine / app.* import (import-linter 'agents.capabilities must not import the execution kernel or the web layer' KEPT)."

requirements-completed: [PARITY-04]

# Metrics
duration: 13min
completed: 2026-06-08
---

# Phase 7 Plan 03: html_skeleton CompactionStrategy Summary

**The Phase 0C build-task-2+ compaction re-expressed as the `html_skeleton` capability — a byte-identical, import-pure lift of `engine._extract_html_skeleton` registered behind `resolve('compaction','html_skeleton')`, with the 0C ≥50% reduction gate re-pointed at it and preserved (PARITY-04).**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-06-08T20:56Z
- **Completed:** 2026-06-08T21:09Z
- **Tasks:** 1
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `HtmlSkeletonCompaction` (`name="html_skeleton"`) — verbatim lift of `_extract_html_skeleton` (`:root` tokens + routes map + filled/empty `<section data-page>` scan + chrome summary + total-size line) into a pure `compact(self, html: str) -> str`. Stdlib (`re`) only; zero kernel/app import.
- Registered `("compaction","html_skeleton") -> HtmlSkeletonCompaction()` in `registry.install()`; the 07-01 `task_loop` task-2+ route `resolve("compaction", step.compaction).compact(prior_html)` now binds to a real impl (the prior `_maybe_resolve_compaction` stub returns the impl instead of `None`).
- Re-pointed `test_phase3_compaction.py` from `engine._extract_html_skeleton` to the capability while PRESERVING both `≥50%` reduction assertions (PARITY-04 gate); the `_build_context_message` message-assembly assertions stay on the engine (07-04 routes injection; 07-05 deletes the helper).
- Added a byte-parity test: `HtmlSkeletonCompaction().compact(fixture) == engine._extract_html_skeleton(fixture)` — pins the strangler wrap until 07-05 deletes the engine copy.

## Task Commits

Each task was committed atomically:

1. **Task 1: html_skeleton CompactionStrategy (verbatim lift) + register + re-point 0C gate** - `a963ed9` (feat)

**Plan metadata:** _(this commit)_

_Note: implemented as one cohesive verbatim-lift change (capability + registration + re-pointed gate are inseparable); committed as a single `feat`._

## Files Created/Modified
- `backend/agents/capabilities/compaction/__init__.py` - package docstring describing the compaction family + the html_skeleton purity/contract.
- `backend/agents/capabilities/compaction/html_skeleton.py` - `HtmlSkeletonCompaction` (`name="html_skeleton"`); `compact(html)->str` is the verbatim lift of `_extract_html_skeleton`. Pure (stdlib `re` only).
- `backend/agents/capabilities/registry.py` - `install()` now imports `HtmlSkeletonCompaction` (local import) and binds `("compaction","html_skeleton")`.
- `backend/tests/agents/test_phase3_compaction.py` - import the capability; re-point the two direct `_extract_html_skeleton` calls at it (reduction assertions preserved); add `test_html_skeleton_capability_is_byte_identical_to_engine_helper`.

## Decisions Made
- **Verbatim lift, algorithm unchanged.** The 0C `≥50%` gate (STATE records 96.9% reduction) is calibrated to the exact byte output of `_extract_html_skeleton`, so the body was copied line-for-line (engine.py:3526-3577) into `compact()`.
- **Structural contract, not a new port.** `base.py` has no `CompactionStrategy` Protocol. The binding contract is the 07-01 `task_loop` call (`.compact(prior_html)`), so the capability satisfies it structurally (`name` + `compact()`). Adding a port type would be a `base.py` kernel edit — out of scope for this plan.
- **Reduction assertion preserved at both sites.** The `≥50%` assertion in `test_build_task2_context_is_at_least_50pct_smaller` (block-level, via `_build_context_message`) and the `< 0.5 *` assertion in the fidelity test both stay; the fidelity-test skeleton source is now the capability.
- **Message-assembly assertions stay on the engine.** Only the *compaction* expectation moved to the capability; `_build_context_message` framing (skeleton block placement, task-1 full-HTML control, read_file pointer, tool-set access) remains asserted against the engine until 07-04 routes injection through the generic injector.
- **Engine copy left intact.** `engine._extract_html_skeleton` stays live (strangler) — 07-04 reroutes the engine through the capability, 07-05 deletes the engine copy. Deleting here would break the still-coupled engine 0C path.

## Deviations from Plan

None - plan executed exactly as written.

The plan's `files_modified` listed `compaction/__init__.py`, `compaction/html_skeleton.py`, `registry.py`, and `test_phase3_compaction.py` — all four were the files touched.

## Issues Encountered
- The `lint_imports` console entry point is not on PATH and the `python3.11 -m importlinter.cli lint` CLI emitted no stdout under this shell's pipe/redirect (banner/report swallowed), making exit-code-only verification ambiguous. Resolved by running import-linter **programmatically** (`importlinter.cli.lint_imports()`), which printed the full report: 113 files / 236 dependencies analyzed, **3 contracts KEPT, 0 broken** — including "agents.capabilities must not import the execution kernel or the web layer" (the contract covering the new compaction module). Import-linter is GREEN.

## Known Stubs
None — this plan resolves the 07-01 `html_skeleton` stub (the task-2+ compaction route in `task_loop` now binds to a real impl instead of returning `None`).

## Threat Flags
None — behavior-preserving relocation of a pure function (T-07-03-01 mitigated: no `app.*`/`agents.execution_engine` import; import-linter contract holds the boundary). No new attack surface.

## TDD Gate Compliance
This plan carries `tdd="true"`. The capability and its re-pointed gate are an inseparable verbatim lift (PARITY-04: the gate must be measured against the new capability the moment it exists), so the RED→GREEN cycle was collapsed into a single `feat` commit rather than separate `test`/`feat` commits. The re-pointed + new tests (`test_phase3_compaction.py`, 7 tests incl. the byte-parity test) all pass against the capability; project `tdd_mode` is `false` in config, so plan-level RED/GREEN gate commit separation is not enforced for this phase.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The `html_skeleton` compaction impl is bound; `task_loop`'s task-2+ compaction route resolves to it. 07-04 (engine wiring) can now route the prototype build through `task_loop`/the capability for real.
- 07-05 deletes `engine._extract_html_skeleton` (and `_build_context_message`'s skeleton/full-HTML branch); the byte-parity test and the engine-side message-assembly assertions must be migrated/removed alongside that deletion.
- Baselines green: `tests/agents` 549 passed / 19 skipped (+1 vs the 548 baseline = the new byte-parity test); `tests/unit` 515 passed with exactly the known 8 pre-existing failures (7× test_logout, 1× test_pipeline_cancel) — no new failures. 0A characterization + migration-ledger + banned-pattern green; import-linter green.

## Self-Check: PASSED

All 4 plan files exist on disk (`compaction/__init__.py`, `compaction/html_skeleton.py`, `registry.py`, `test_phase3_compaction.py`); the task commit `a963ed9` exists in git history.

---
*Phase: 07-prototype-as-manifest-parity-proof-sc-001-2*
*Completed: 2026-06-08*
