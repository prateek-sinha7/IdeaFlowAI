---
phase: 04-manifest-compiler-1a
plan: 01
subsystem: api
tags: [capabilities, registry, protocol, ports, hexagonal, manifest, compiler]

# Dependency graph
requires:
  - phase: 03-token-trim-measured-change-0c
    provides: prior-phase invariants (od_prototype=alias→prototype; import-linter + vulture gates live)
provides:
  - "agents/capabilities/ package (the hexagonal capability seam)"
  - "CapabilityRegistry keyed by (kind, name) with the 14 known capability names (INV-4 validation surface)"
  - "is_registered(kind, name) -> bool (pure set-membership, no eval/import)"
  - "resolve_alias(pipeline_type) -> str (od_prototype→prototype; identity otherwise) lifted from agents.registry._OD_ALIAS_BASE"
  - "Six typing.Protocol capability ports (ExecutionStrategy, Validator, DeliverableResolver, ContextProvider, GateHandler, TaskParser)"
affects: [04-02 compiler (validates references against CapabilityRegistry), 04-04 id-alias resolver consumer, Phase 7 capability impls, Phase 8 self-registration + trust flags]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Capability registry keyed by (kind, name) with name-only registration (no impls/trust) — D-07"
    - "typing.Protocol ports as the hexagonal boundary (first Protocol-port precedent in repo)"
    - "id-alias lifted from a single named source (agents.registry._OD_ALIAS_BASE), never re-hardcoded"

key-files:
  created:
    - backend/agents/capabilities/__init__.py
    - backend/agents/capabilities/base.py
    - backend/agents/capabilities/registry.py
    - backend/tests/agents/test_registry_capabilities.py
  modified:
    - backend/pyproject.toml

key-decisions:
  - "Registered exactly 14 (kind, name) names per D-07; added a drift-guard test asserting len(_KNOWN)==14"
  - "resolve_alias imports _OD_ALIAS_BASE from agents.registry (single source of truth) instead of redefining the od_prototype map"
  - "Protocol port method signatures type plan-domain positions (Step/ExecutionContext/Task/Issue) as Any to avoid an inbound dependency on agents/workflows/plan.py (authored in 04-02), keeping base.py import-clean"
  - "Reworded module docstrings to avoid the literal forbidden tokens (@register/discover/user_allowed in registry.py; execution_engine/app.api in base.py) so the plan's acceptance greps return 0 on real code"
  - "Added vulture ignore_name 'step' for the interface-only Protocol-port parameter (verified false positive, per pyproject D-13 allow-list strategy)"

patterns-established:
  - "Pattern 2 (research): (kind, name) registry with name-only registration; Phase 8 swaps to @register self-registration as an evolution (INV-12)"
  - "Hexagonal ports: capabilities package imports only stdlib typing + agents.registry; no kernel/app import (import-linter green)"

requirements-completed: [MAN-03]

# Metrics
duration: 4min
completed: 2026-06-07
---

# Phase 4 Plan 01: Capability Ports + Name Registry Summary

**The hexagonal capability seam: six `typing.Protocol` ports in `capabilities/base.py` plus a `CapabilityRegistry` of the 14 known `(kind, name)` capability names and the `od_prototype→prototype` id-alias resolver — the INV-4 validation surface the 04-02 compiler checks every declared reference against.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-07T16:00:42Z
- **Completed:** 2026-06-07T16:04:18Z
- **Tasks:** 2
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments
- `CapabilityRegistry` keyed by `(kind, name)` registering exactly the 14 authoritative names (D-07): strategies `single_shot`/`task_loop`; validators `html_static`/`html_render`; deliverables `single_file`/`serialized_sandbox`/`streamed_text`/`ppt`; context_providers `opendesign`/`previous_run`; task_parser `heading_tasks`; gates `human`/`validation`; compaction `html_skeleton`.
- `is_registered(kind, name)` as a pure set-membership check (no eval, no dynamic import, no getattr — mitigates T-04-01).
- `resolve_alias(pipeline_type)` lifting `agents.registry._OD_ALIAS_BASE` (single source) for `od_prototype→prototype` (identity otherwise) — MAN-05 consumer is 04-04.
- Six `typing.Protocol` capability ports (the first Protocol-port precedent in the repo) — interface-only, no impls (Phase 7).
- Import-linter green (kernel→ports boundary intact); vulture clean on the new package; 26 tests passing.

## Task Commits

Each task was committed atomically (Task 1 is TDD: test → feat):

1. **Task 1 (RED): failing CapabilityRegistry tests** - `fb46147` (test)
2. **Task 1 (GREEN): CapabilityRegistry + 14 names + resolve_alias** - `25432a5` (feat)
3. **Task 2: Protocol capability ports in base.py** - `b34efc0` (feat)

**Plan metadata:** (this commit) `docs(04-01): complete capability ports + name registry plan`

## Files Created/Modified
- `backend/agents/capabilities/__init__.py` - Package marker + seam docstring
- `backend/agents/capabilities/registry.py` - `CapabilityRegistry`, `_KNOWN` (14 pairs), `is_registered`, `resolve_alias`
- `backend/agents/capabilities/base.py` - Six `runtime_checkable` `Protocol` ports per spec §6
- `backend/tests/agents/test_registry_capabilities.py` - 26 tests: all 14 names, unknown name/kind rejection, count drift-guard, alias resolution, all six ports importable + are Protocols
- `backend/pyproject.toml` - vulture `ignore_names` += `step` (Protocol-port interface-only param)

## Decisions Made
- **14-name drift guard:** `test_registered_count_is_exactly_fourteen` asserts both `len(_KNOWN)==14` and exact set equality, so adding/removing a name without intent trips the test.
- **Single-source alias:** `resolve_alias` imports `_OD_ALIAS_BASE` from `agents.registry` rather than re-hardcoding — `grep '"od_prototype"' registry.py` returns 0 (acceptance criterion).
- **Port signature typing:** plan-domain types (`Step`, `ExecutionContext`, `Task`, `Issue`, gate outcomes, artifact refs) are typed `Any` in `base.py` because `agents/workflows/plan.py` lands in 04-02; this keeps the port module's only imports stdlib `typing`, satisfying the hexagonal boundary now and avoiding a forward-import cycle. Impls (Phase 7) bind the concrete types.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reworded docstrings to satisfy literal acceptance greps**
- **Found during:** Task 1 and Task 2
- **Issue:** The plan's acceptance criteria use literal greps that must return 0: `registry.py` non-comment lines must not contain `user_allowed|def discover|@register`, and `base.py` must not contain `execution_engine|app\.api`. The initial docstrings described what is intentionally *absent* using those exact tokens, which the greps matched (the grep filter only strips `#`-comments, not docstring lines).
- **Fix:** Reworded both module docstrings to describe the deferred/forbidden concepts in prose without the literal tokens. No code/behavior change.
- **Files modified:** backend/agents/capabilities/registry.py, backend/agents/capabilities/base.py
- **Verification:** Both greps now return 0; all 26 tests still pass.
- **Committed in:** `25432a5` (Task 1), `b34efc0` (Task 2)

**2. [Rule 3 - Blocking] Added vulture allow-list entry for the Protocol-port param**
- **Found during:** Task 2 (verification step)
- **Issue:** The verification spec requires vulture not to newly flag the ports. `vulture app/ agents/` (CI form) flagged the interface-only `step` parameter on `ExecutionStrategy.run` / `GateHandler.evaluate` (Protocol methods have no body, so params look "unused" to static analysis).
- **Fix:** Added `"step"` to `[tool.vulture] ignore_names` with an explanatory comment, following the documented D-13 allow-list strategy (the same approach used for `@tool` stub params). Other params (`ctx`, `text`, `target`) were not flagged.
- **Files modified:** backend/pyproject.toml
- **Verification:** `vulture app/ agents/` reports no `capabilities` findings.
- **Committed in:** `b34efc0` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking the acceptance/verification gates)
**Impact on plan:** Both are mechanical gate-satisfaction fixes (docstring wording + a verified-false-positive allow-list entry). No behavior change, no scope creep.

## Issues Encountered
None beyond the two auto-fixed gate-satisfaction items above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The capability seam is real: 04-02's `WorkflowCompiler` can now call `CapabilityRegistry.is_registered(kind, name)` to reject any unknown declared reference (INV-4), and the six Protocol ports are the contract Phase 7 impls will satisfy.
- `resolve_alias` is ready for the 04-04 id-alias resolver (MAN-05).
- No impls, no trust flags, no self-registration machinery were added (correctly deferred to Phase 7/8).

## Self-Check: PASSED

---
*Phase: 04-manifest-compiler-1a*
*Completed: 2026-06-07*
