---
phase: 06-model-policy-1c
plan: 03
subsystem: engine
tags: [model-policy, resolver, precedence, fallback-chain, throttle, deepagents, bedrock, INV-3-parity]

# Dependency graph
requires:
  - phase: 06-01
    provides: ModelCatalog (single source of model ids/cost_class/tier — chain validity + resolve-time allow-list)
  - phase: 06-02
    provides: AgentSpec.model (optional AGENT.md model id — precedence tier 3)
provides:
  - "agents/model_policy.py::ModelResolver — D-02 5-tier precedence resolve() (override>step.model>AgentSpec.model>workflow.model>session|Haiku), None tiers skipped, INV-3 parity default"
  - "ModelResolver.chain_for() — tier-descent fallback chains (Opus->[Sonnet,Haiku], Sonnet->[Haiku], Haiku->[]) + explicit-fallback override, catalog-validated"
  - "ModelResolver.set_chain/current/advance — active chain + cursor for the 06-05 fallback retry loop"
  - "_is_transient_throttle(exc) — layered Bedrock/Anthropic throttle predicate (consumed by 06-05)"
  - "ExecutionContext.model_resolver (object|None) + model_overrides (dict) — import-pure carry"
  - "engine.execute() constructs the resolver; the 3 _run_agent model sites consult it via _resolve_model"
affects: [06-04, 06-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Kernel resolver service constructed once at execute() entry, carried import-pure on ExecutionContext (like scoped_store), consulted at every per-agent model site"
    - "Resolver-or-fallback helper (_resolve_model) so direct unit-style _run_agent invocations (resolver None) stay parity-safe"

key-files:
  created:
    - backend/agents/model_policy.py
    - backend/tests/unit/test_model_resolver.py
  modified:
    - backend/agents/execution_engine/context.py
    - backend/agents/execution_engine/engine.py

key-decisions:
  - "06-03: ModelResolver constructed AFTER compile_for_run() (so CompiledWorkflow.model seeds tier 4), assigned to ectx.model_resolver — ectx itself is built earlier at execute() entry"
  - "06-03: _resolve_model(ectx, spec, model_id) falls back to model_id when ectx.model_resolver is None — keeps direct unit-style _run_agent/_run_build_task_loop invocations green and is parity-safe (resolver returns model_id or Haiku on the no-override path anyway)"
  - "06-03: step=None passed at all 3 model sites this plan (parity-identical today — all step.model None); 06-04 wires the compiled Step lookup"
  - "06-03: SmartPlanner left on the session model_id (no agent_id, builds its own client) — routing it through the resolver risked an INV-3 break (RESEARCH #2)"
  - "06-03: ModelPolicy.max_tokens stays documentation-only — resolver threads NO runtime cap (cap stays settings.MAX_OUTPUT_TOKENS in build_model)"

patterns-established:
  - "Precedence resolution: a single resolve(spec, step) returns the effective id by an or-chain of None-skipped tiers; the parity default is the last tier"
  - "Throttle classification: one defensive layered predicate (type-name OR HTTP-status OR error-code/message substring) co-located with the resolver so engine + tests import one symbol"

requirements-completed: [MODEL-01, MODEL-02, MODEL-05]

# Metrics
duration: 15min
completed: 2026-06-08
---

# Phase 6 Plan 03: ModelResolver (per-agent model resolution) Summary

**A kernel ModelResolver that resolves every agent's effective model id by the D-02 5-tier precedence (override > step.model > AgentSpec.model > workflow.model > session|Haiku) with a parity-critical Haiku default, plus tier-descent fallback chains and a co-located throttle predicate — wired into all three engine model sites with byte/semantic-identical INV-3 snapshots.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-06-08T15:11:33Z
- **Completed:** 2026-06-08T15:27:00Z
- **Tasks:** 2 (Task 1 TDD: RED→GREEN)
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `ModelResolver.resolve(spec, step)` — the single per-agent resolution path by the locked D-02 precedence, None tiers skipped, with the INV-3 parity default (`session model_id or Haiku`).
- Resolve-time AGENT.md `model` validation against `ModelCatalog` (T-06-03 allow-list): an unknown tier-3 id raises rather than flowing into `build_model`.
- `chain_for()` derives the N11 tier-descent fallback chains from `cost_class` (Opus→[Sonnet, Haiku], Sonnet→[Haiku], Haiku→[]); an explicit `ModelPolicy.fallback` overrides and is catalog-validated; `set_chain/current/advance` hold the active chain + cursor for the 06-05 retry loop.
- `_is_transient_throttle(exc)` — a defensive layered Bedrock/Anthropic throttle classifier (D-06) the 06-05 fallback loop will consume.
- The resolver is constructed at `execute()` entry and the three `_run_agent` model sites (primary, revision, build-loop fix) now consult it — with characterization snapshots proven byte/semantic-identical (INV-3) and the deepagents-only banned-pattern gate green (INV-13).

## Task Commits

1. **Task 1 (RED): failing ModelResolver tests** - `f0b1ea1` (test)
2. **Task 1 (GREEN): ModelResolver + throttle predicate + context fields** - `8c0fb0f` (feat)
3. **Task 2: construct resolver at execute() entry + rewire 3 model sites** - `93488c7` (feat)

**Plan metadata:** committed separately (docs).

_TDD Task 1 = test → feat (no refactor needed)._

## Files Created/Modified
- `backend/agents/model_policy.py` (created) - `ModelResolver` (precedence resolve + chain_for tier-descent + set_chain/current/advance cursor) and the module-level `_is_transient_throttle` predicate. Imports `ModelCatalog`, `ModelPolicy`, and (in the engine seed) `settings` — all import-clean; no contract restricts this kernel module.
- `backend/tests/unit/test_model_resolver.py` (created) - 23 tests: 5 precedence tiers + None-skip + parity default (session & Haiku) + max_tokens-doc-only + default chains + explicit-override + catalog-valid + resolve-time AGENT.md validation + 8 throttle-predicate cases.
- `backend/agents/execution_engine/context.py` (modified) - added `model_resolver: object | None = None` and `model_overrides: dict = field(default_factory=dict)`, typed `object`/import-pure exactly like `scoped_store` (no new `app.*` import).
- `backend/agents/execution_engine/engine.py` (modified) - imports `ModelResolver`/`ModelCatalog`; constructs the resolver after `compile_for_run()` onto `ectx.model_resolver` (seeded with overrides {}, `compiled.model`, session `model_id`, `settings.BEDROCK_INFERENCE_PROFILE_ID`, `ModelCatalog()`); rewired the 3 `model=model_id` AgentContext sites to `self._resolve_model(ectx, spec, model_id)`; added the `_resolve_model` resolver-or-fallback helper; SmartPlanner unchanged.

## Decisions Made
See `key-decisions` frontmatter. Most load-bearing: the resolver seed lives after `compile_for_run()` (tier 4 needs `CompiledWorkflow.model`); `_resolve_model` falls back to `model_id` when the resolver is `None`; `step=None` this plan (06-04 wires steps); SmartPlanner stays on the session id (parity).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Resolver-or-fallback guard for null `model_resolver`**
- **Found during:** Task 2 (rewiring the 3 model sites)
- **Issue:** The initial rewire called `ectx.model_resolver.resolve(...)` unconditionally. Direct unit-style invocations of `_run_agent` / `_run_build_task_loop` (in `test_phase4_build_loop.py` 7 tests, `test_phase3_cutover_verify.py` 2 tests) construct an `ExecutionContext` WITHOUT going through `execute()`, so `model_resolver is None` → `AttributeError: 'NoneType' object has no attribute 'resolve'`. 9 tests regressed.
- **Fix:** Added a `_resolve_model(ectx, spec, model_id, step=None)` static helper that returns `model_id` when `ectx.model_resolver is None`, else delegates to `resolver.resolve(spec, step)`. All 3 model sites use the helper. Parity-safe: on the live path the resolver returns `model_id or Haiku` for the no-override case, so the resolved id is identical either way (INV-3).
- **Files modified:** backend/agents/execution_engine/engine.py
- **Verification:** `test_phase4_build_loop.py` + `test_phase3_cutover_verify.py` 16/16 green again; characterization snapshots 44/44 unchanged.
- **Committed in:** `93488c7` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for correctness — the rewire would have crashed every direct-invocation engine unit test. No scope creep; the fallback is the documented parity-safe path.

## Issues Encountered
- A full `tests/agents/ tests/unit/` run lands at **9 failed / 976 passed / 19 skipped**. All 9 are PRE-EXISTING / environmental, NOT caused by this plan: 7× `test_logout.py` (self-registration 403 env gate), 1× `test_pipeline_cancel.py` (expired AWS SSO token), and 1× `test_registry_capabilities.py::test_registered_count_is_exactly_fourteen` — a **06-01 carryover** (`_KNOWN` became 15 when 06-01 registered `model_catalog`, but the hard-coded `== 14` assertion was not bumped). VERIFIED pre-existing at commit `e70f2db` (before any 06-03 commit). Logged in `deferred-items.md`; out of scope (registry-owning fix should bump the count to 15).

## Known Stubs
- `ectx.model_overrides` defaults to `{}` this plan (resolver tier 1 never fires). This is intentional and documented: 06-04 wires the WebSocket ingress + catalog validation that populates it. Tier-5 parity holds while it is empty (INV-3).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **06-04** can wire `model_overrides` ingress (WS validation → `ectx.model_overrides`) and persist it via `record_capabilities`; the resolver's tier-1 + the compiled `Step` lookup (replacing `step=None`) plug in with no resolver change.
- **06-05** can build the engine fallback retry loop on `set_chain`/`current`/`advance` + `_is_transient_throttle` (both shipped here).
- No blockers. INV-3 parity proven (44/44 characterization snapshots); INV-13 preserved (banned-pattern green; resolved id reaches the graph only via `build_model`); import-linter 3-kept/0-broken.

## Self-Check: PASSED

- Files verified on disk: `model_policy.py`, `test_model_resolver.py`, `06-03-SUMMARY.md` — all FOUND.
- Commits verified in git log: `f0b1ea1` (RED), `8c0fb0f` (GREEN Task 1), `93488c7` (Task 2) — all FOUND.

---
*Phase: 06-model-policy-1c*
*Completed: 2026-06-08*
