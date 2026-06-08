---
phase: 06-model-policy-1c
plan: 05
subsystem: engine
tags: [model-policy, fallback, throttle, retry, deepagents, bedrock, approach-b, INV-3-parity, INV-13]

# Dependency graph
requires:
  - phase: 06-03
    provides: "ModelResolver.set_chain/current/advance (active fallback chain + cursor) + _is_transient_throttle predicate + ExecutionContext.model_resolver"
  - phase: 06-04
    provides: "model_overrides ingress (resolver tier-1) + compiled Step model lookup (resolver feeds the resolved primary id this loop arms the chain on)"
provides:
  - "deep_agent_runner.py B1: re-raise classified transient throttles (instead of swallowing into an error event) so the engine fallback can see them"
  - "engine.py _run_agent APPROACH-B rebuild-and-retry loop: on a re-raised throttle, advance ModelResolver to the next chain id, rebuild via create_runner, re-invoke — bounded by chain length"
  - "Chain exhaustion lets the last throttle escape the retry loop (visible agent_error, no silent blank); non-transient errors propagate as today (no model switch)"
  - "agent_model_fallback informational WS event on a model switch"
  - "tests/agents/_scripted_model.py throttle / non-transient scripted-model variants (raise_exc) for offline fallback testing (no live Bedrock)"
  - "tests/agents/test_model_fallback.py: throttle-advances + chain-exhaustion-reraises (single + multi-entry) + non-transient-propagates"
affects: [phase-7-strategies, model-policy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Engine-level rebuild-and-retry fallback (APPROACH B): the runner re-raises a classified transient throttle; the engine owns the bounded retry, advancing the resolver chain and rebuilding via create_runner — build_model stays the single model source (INV-13)"
    - "Per-attempt accumulator reset (output_chunks/tokens) + task_progress rollback so a retried re-stream does not duplicate the deliverable or double-count the build checklist (Pitfall 4)"

key-files:
  created:
    - backend/tests/agents/test_model_fallback.py
  modified:
    - backend/app/agents/deep_agent_runner.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/_scripted_model.py

key-decisions:
  - "06-05: APPROACH B (engine rebuild-and-retry), NOT Runnable.with_fallbacks — RESEARCH proved with_fallbacks does not compose through the deepagents astream_events graph (RunnableWithFallbacks lacks bind_tools; the runner swallows model exceptions)"
  - "06-05: B1 (runner re-raises classified throttles) over B2 (engine string-matches the error event) — classifying a real exception object is more robust than re-parsing a stringified one; the runner stays the single streaming surface and the engine the single retry authority"
  - "06-05: arm the chain on the resolved PRIMARY id captured BEFORE create_runner (_resolved_model_id), not off ctx.model after the build — the retry reassigns ctx.model to the next chain id and (in tests) create_runner may replace ctx.model with a scripted instance"
  - "06-05: chain exhaustion lets the throttle ESCAPE the retry loop into the engine's existing agent-failure path (visible recoverable agent_error), rather than re-raising out of _run_agent — matches the engine's established fault-degradation contract; the meaningful change vs today is it is no longer a SILENT blank"
  - "06-05: resolver-absent path (direct unit-style _run_agent) runs exactly one attempt — parity-safe, identical to today"

patterns-established:
  - "Promote-to-raise scoped to a predicate: the Phase-1 swallow becomes a re-raise ONLY for _is_transient_throttle matches; every other exception keeps the exact prior behavior (surgical parity boundary)"
  - "Bounded fallback retry: len(chain) attempts, advance-or-exhaust, no infinite loop (T-06-10); only classified throttles enter the loop (T-06-11)"

requirements-completed: [MODEL-02]

# Metrics
duration: 35min
completed: 2026-06-08
---

# Phase 6 Plan 05: Model-Switch Fallback (APPROACH B) Summary

**An engine-level rebuild-and-retry fallback above the botocore retries: the deepagents runner re-raises classified transient throttles (B1), and `_run_agent` advances `ModelResolver` to the next fallback chain id, rebuilds via `create_runner`, and re-invokes — bounded by chain length, with chain exhaustion surfacing a visible `agent_error` (no silent blank) and the no-throttle path byte/semantically identical (INV-3) — proven offline with a scripted throttle (no live Bedrock).**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-06-08T16:05:00Z
- **Completed:** 2026-06-08T16:40:00Z
- **Tasks:** 2 (Task 1 TDD RED → Task 2 GREEN, with a GREEN test refinement)
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- **B1 runner re-raise:** the `astream_events` swallow (`deep_agent_runner.py:451`) now classifies via `agents.model_policy._is_transient_throttle` and re-raises on a match; every other exception keeps the existing `{"type":"error"}` path unchanged (non-throttle parity).
- **APPROACH-B engine loop:** `_run_agent` wraps the per-agent consume in a bounded rebuild-and-retry loop — arm chain on the resolved primary id, on a re-raised throttle advance the resolver, rebuild via `create_runner` (so the rebuild flows through `build_model` only — INV-13, no new deepagents-graph construction), reset per-attempt accumulators, re-invoke; chain exhaustion lets the last throttle escape into the engine's existing recoverable-`agent_error` path.
- **Offline test contract (D-06):** extended `ScriptedFakeChatModel` with a `raise_exc` flag + `ScriptedThrottleError` / `ScriptedNonTransientError` (duck-typed so `_is_transient_throttle` classifies them True/False); `test_model_fallback.py` proves throttle-advances, chain-exhaustion-reraises (single + multi-entry), and non-transient-propagates — all without live Bedrock.
- **Parity + invariants verified:** all 10 characterization snapshots (5 pipelines) UNCHANGED (INV-3); banned-pattern 8/8 green and `engine.py` `create_deep_agent` call-count still 0 (INV-13); `lint-imports` 3 kept / 0 broken.

## Task Commits

1. **Task 1 (RED): fallback tests + scripted throttle variant** - `849919c` (test)
2. **Task 2 (GREEN): runner B1 re-raise** - `a41416f` (feat, runner)
3. **Task 2 (GREEN): engine APPROACH-B retry loop** - `5b64dbc` (feat, engine)
4. **Task 2 (GREEN): exhaustion-test refinement to the real engine contract** - `d5c84a7` (test)

**Plan metadata:** committed separately (docs).

_TDD Task 1 = RED; Task 2 = GREEN (runner + engine), with one test refinement once the actual engine fault-degradation contract was observed._

## Files Created/Modified
- `backend/app/agents/deep_agent_runner.py` (modified) — the `except Exception` swallow now imports `_is_transient_throttle` and re-raises on a classified transient throttle (B1); non-throttle errors keep the existing `yield {"type":"error", ...}` path verbatim.
- `backend/agents/execution_engine/engine.py` (modified) — captured `_resolved_model_id` before `create_runner`; wrapped the `astream_events` consume in the bounded rebuild-and-retry loop (arm chain → advance/rebuild/re-invoke on a classified throttle → exhaust re-raises); reset `output_chunks`/token accumulators between attempts and roll back per-attempt `task_progress` records; emit `agent_model_fallback` on a switch.
- `backend/tests/agents/_scripted_model.py` (modified) — `ScriptedThrottleError` (botocore-`ClientError`-shaped: `ThrottlingException`/429), `ScriptedNonTransientError` (`ValidationException`/400), and a `raise_exc` constructor flag that raises pre-first-token from `_stream`/`_generate`.
- `backend/tests/agents/test_model_fallback.py` (created) — drives `_run_agent` directly with an armed resolver chain and a per-`ctx.model` `create_runner` patch; 4 tests (advance, single-entry exhaustion, multi-entry exhaustion, non-transient).

## Decisions Made
See `key-decisions` frontmatter. Most load-bearing: (1) APPROACH B / B1 (RESEARCH-resolved D-05 binary — `with_fallbacks` does not compose through the deepagents graph); (2) arm the chain on the primary id captured before `create_runner`; (3) chain exhaustion escapes into the engine's existing recoverable-`agent_error` path rather than raising out of `_run_agent` — the meaningful change vs today is it is no longer a silent blank.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Arm the fallback chain on the captured resolved primary id, not `ctx.model`**
- **Found during:** Task 2 (GREEN — `test_throttle_advances` failed: chain never advanced)
- **Issue:** The initial loop called `_resolver.set_chain(ctx.model)` AFTER the first `create_runner`. In the offline test the patched `create_runner` replaces `ctx.model` with a `ScriptedFakeChatModel` instance, so `set_chain` armed a chain on a model OBJECT (not an id string) → `chain_for` returned `[]` → `_max_attempts=1` → the primary throttle was treated as immediate exhaustion. (It would also be wrong in production semantics — `set_chain` needs the id string.)
- **Fix:** Capture `_resolved_model_id = ctx.model` immediately after the `AgentContext` is built (before `create_runner`), and arm the chain on that id.
- **Files modified:** backend/agents/execution_engine/engine.py
- **Verification:** `test_throttle_advances` GREEN; `built_for == [PRIMARY_STANDARD, FALLBACK_CHEAP]`.
- **Committed in:** `5b64dbc` (Task 2 engine commit)

**2. [Rule 1 - Test correctness] Exhaustion tests assert the engine's real fault-degradation contract**
- **Found during:** Task 2 (GREEN — the two exhaustion tests `pytest.raises(ScriptedThrottleError)` failed)
- **Issue:** The RED tests expected the throttle to propagate out of `_run_agent` as a raw exception. The engine's established contract degrades any agent fault to a recoverable `agent_error` WS event (it does not crash the pipeline). So the re-raised throttle ESCAPES the retry loop and is converted to a visible `agent_error` — which is exactly the desired "no silent blank" behavior, just surfaced as an event, not a raised exception.
- **Fix:** Refined the two exhaustion tests to assert a visible `agent_error` carrying the throttle message + the chain walked exactly once (bounded) + no completed result recorded.
- **Files modified:** backend/tests/agents/test_model_fallback.py
- **Verification:** both exhaustion tests GREEN; the throttle surfaces (not a silent blank) and the chain is bounded.
- **Committed in:** `d5c84a7` (test refinement commit)

---

**Total deviations:** 2 auto-fixed (2 bugs — one engine logic, one test-contract correctness)
**Impact on plan:** Both necessary for correctness. No scope creep; the engine fix is the load-bearing chain-arming correction, and the test refinement aligns the assertions with the engine's real (and correct) fault-degradation contract.

## Issues Encountered
- **`RUNS_ROOT` read-only (`/app`) in the direct-`_run_agent` driver:** `app.core.config.settings` may be instantiated with the default `/app/runs` before the harness env var lands. Fixed in the test driver by forcing `_settings.RUNS_ROOT = _RUNS_ROOT` at runtime (mirrors the existing `_drive` harness) — offline, no live Bedrock.
- **`agent_model_fallback` is a NEW WS event type** emitted only on the throttle path. It does not affect characterization parity (never fires on the no-throttle path) and the websocket drainer forwards unknown types verbatim (frontend ignores them). Informational only.

## Known Stubs
None — the fallback path is fully wired (runner re-raise → engine advance/rebuild/re-invoke → exhaustion surfaces). No placeholder data or unwired paths introduced.

## Pre-existing Failures (NOT caused by this plan)
A full `tests/agents/ tests/unit/` run lands at **8 failed / 990 passed / 19 skipped**. All 8 are the documented pre-existing environmental failures (7× `test_logout.py` self-registration 403; 1× `test_pipeline_cancel.py`). The `test_pipeline_cancel` failure was explicitly verified to fail IDENTICALLY on the HEAD baseline (engine/runner restored to `HEAD`) before my changes — confirming it is pre-existing and not a regression from the cancellation-path edits. Zero NEW failures introduced. (The 06-01 `test_registered_count` carryover noted in 06-03 is no longer failing.)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- MODEL-02 fallback is complete and offline-tested. Phase 6 (Model Policy 1C) is fully landed: catalog (06-01), AgentSpec.model (06-02), ModelResolver + throttle predicate (06-03), overrides ingress + Step lookup (06-04), and the APPROACH-B fallback (06-05).
- INV-3 parity proven (10/10 characterization snapshots unchanged); INV-13 preserved (banned-pattern green; `engine.py` `create_deep_agent` call-count 0; rebuild flows through `build_model` only); import-linter 3-kept/0-broken.
- No blockers.

## Self-Check: PASSED

- Files verified on disk: `test_model_fallback.py`, `deep_agent_runner.py`, `engine.py`, `06-05-SUMMARY.md` — all FOUND.
- Commits verified in git log: `849919c` (RED), `a41416f` (runner B1), `5b64dbc` (engine APPROACH B), `d5c84a7` (test refinement) — all FOUND.

---
*Phase: 06-model-policy-1c*
*Completed: 2026-06-08*
