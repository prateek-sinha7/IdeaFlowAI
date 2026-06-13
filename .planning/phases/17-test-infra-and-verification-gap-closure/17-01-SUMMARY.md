---
phase: 17-test-infra-and-verification-gap-closure
plan: 01
subsystem: testing
tags: [clarify, compile_for_run, fault-injection, asyncio, pytest, characterization, lint-imports]

# Dependency graph
requires:
  - phase: 07-decoupling
    provides: "deleted the ALWAYS_CLARIFY module flag; clarify forcing moved to manifest clarify.mode"
  - phase: 04-manifest-compiler-1a
    provides: "compile_for_run + CompiledWorkflow.clarify (ClarifySpec mutable dataclass)"
provides:
  - "_drive_live compile_for_run clarify-off wrap (snapshot + wrapper sets compiled.clarify.mode='off' + finally restore) replacing the dead auto-clarify module flag"
  - "Bounded offline fault-injection regression test test_drive_live_does_not_hang_at_clarify_gate (asyncio.wait_for(...,10) RETURNS)"
  - "Per-test live skip decorator (moved off module pytestmark) so the offline regression runs while test_token_delta_live stays SSO/Bedrock opt-in"
affects: [phase-17-plan-02-ISS-010, phase-17-plan-03-ISS-011, live-bedrock-pass]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "compile_for_run clarify-off wrap is the canonical offline-harness clarify-disable mechanism (mirror of _scripted_model.py:506-513 and live_harness.py:556-563)"
    - "Per-test live-gate decorator instead of module pytestmark, so an offline regression and an opt-in live test can co-exist in one module"

key-files:
  created: []
  modified:
    - backend/tests/agents/test_phase3_token_delta_live.py

key-decisions:
  - "Fixed ISS-003 in the TEST only via the compile_for_run clarify-off wrap; rejected hacks (re-add ALWAYS_CLARIFY engine flag, clarify_engine.py timeout, flip prototype manifest clarify.mode) NOT taken"
  - "Converted the module-level pytestmark skip into a per-test decorator so the new offline fault-injection regression runs without creds while test_token_delta_live keeps its SSO/Bedrock opt-in gate"
  - "Phrased all comments/docstrings without the literal dead-flag token so the acceptance grep (count==0) holds without weakening the explanation"

patterns-established:
  - "Offline fault-injection: drive the real live helper with a per-agent scripted model (build_model stubbed, factory create_runner injects ScriptedFakeChatModel(_scripts_for(agent_id))) under asyncio.wait_for to prove a hang is gone"

requirements-completed: [ISS-003]

# Metrics
duration: 4min
completed: 2026-06-13
---

# Phase 17 Plan 01: ISS-003 — `_drive_live` clarify-off compile wrap Summary

**`test_phase3_token_delta_live._drive_live` now compiles `clarify.mode="off"` via the `compile_for_run` wrap (replacing the dead `ALWAYS_CLARIFY` module flag), defeating the auto-clarify hang — proven by a bounded offline fault-injection regression test.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-06-13T14:14:07Z
- **Completed:** 2026-06-13T14:18:00Z
- **Tasks:** 2 (1 implementation + 1 parity guard)
- **Files modified:** 1

## Accomplishments
- Replaced the dead `engine_mod.ALWAYS_CLARIFY = False` line at `_drive_live` (a no-op since the flag was deleted in 07-05) with the `compile_for_run` clarify-off wrap: snapshot `engine_mod.compile_for_run`, install a wrapper that calls the original then sets `compiled.clarify.mode = "off"`, and restore it in the existing `finally` (so the patch is reverted across both OFF-then-ON `_drive_live` invocations). Mirrors `_scripted_model.py:506-513` / `live_harness.py:556-563` exactly.
- Added a bounded offline fault-injection regression test `test_drive_live_does_not_hang_at_clarify_gate`: drives the real `_drive_live(compaction_on=True)` with a per-agent scripted model (no Bedrock — `build_model` stubbed, `factory.create_runner` injects `ScriptedFakeChatModel(_scripts_for(agent_id))`) wrapped in `asyncio.wait_for(..., timeout=10)` and asserts it RETURNS (no `asyncio.TimeoutError`).
- Moved the live skip gate from a module-level `pytestmark` to a per-test `@_requires_live_bedrock` decorator so the offline regression runs credential-less while `test_token_delta_live` stays SSO/Bedrock opt-in (still skips cleanly offline).

## Task Commits

1. **Task 1: Replace dead flag with compile_for_run clarify-off wrap + bounded fault-injection regression test** - `88606ec1` (test)
2. **Task 2: Parity guard (test-only diff + 5 characterization goldens + lint-imports)** - no code change; assertion-only guard, evidence recorded below

**Plan metadata:** (final docs commit — this SUMMARY + STATE.md + ROADMAP.md)

## Files Created/Modified
- `backend/tests/agents/test_phase3_token_delta_live.py` — `_drive_live` clarify-off `compile_for_run` wrap (snapshot + wrapper + `finally` restore) replacing the dead `ALWAYS_CLARIFY` line; new offline fault-injection test `test_drive_live_does_not_hang_at_clarify_gate`; live skip moved from `pytestmark` to a `@_requires_live_bedrock` decorator on `test_token_delta_live`.

## Decisions Made
- **Fix lives in the TEST, not production (LOCKED ISS-003).** The defect was a dead module-attribute poke; the proper fix is the same `compile_for_run` clarify-off wrap every other harness uses. Rejected hacks (re-introduce the engine flag, add a `clarify_engine.py` timeout, flip the `prototype` manifest `clarify.mode`) were NOT taken — they'd reintroduce dual-impl (INV-12), perturb production HITL, or break INV-3 + `test_manifest_parity.py`.
- **Per-test live gate.** Converting the module `pytestmark` to a per-test decorator is the minimal way to let the offline regression run without creds while keeping `test_token_delta_live` opt-in — no behavior change to the live test's gating.
- **Token-delta measurement preserved.** Clarify runs before the agent loop and emits no `input_tokens`, so suppressing it removes a hang, not the A/B measurement (per the LOCKED decision).

## Parity Guard Evidence (Task 2 — SC-001 / INV-3)

This phase is **test-harness-only**: the only change is confined to one test module (`test_phase3_token_delta_live.py`) and never imports into production code, so SC-001 / INV-3 parity is satisfied **by construction** AND verified:

- **Test-only diff:** `git diff --name-only -- backend/` lists ONLY `backend/tests/agents/test_phase3_token_delta_live.py` — no `backend/app/**`, no non-test `backend/agents/**`. The grep-for-non-test guard exits 0 (none found). (`.planning/STATE.md` also shows in the repo-wide diff; that is orchestrator-written planning state, not a backend source change.)
- **5 characterization goldens:** `test_characterization_prototype` / `_od_prototype` / `_prototype_revision` / `_od_ppt` / `_app_builder` — **10 passed** byte-identical with `SNAPSHOT_UPDATE` unset (no golden regeneration).
- **lint-imports:** `/opt/homebrew/bin/lint-imports` → **4 contracts kept, 0 broken** (184 files, 393 dependencies analyzed).

## Offline Verification Evidence (ISS-003 closed deterministically)

- `grep -c ALWAYS_CLARIFY tests/agents/test_phase3_token_delta_live.py` == **0** (dead flag gone, not reintroduced).
- `python3.11 -m pytest tests/agents/test_phase3_token_delta_live.py -p no:cacheprovider -q` → **1 passed, 1 skipped** in 8.5s: the new fault-injection test PASSES (no hang), and `test_token_delta_live` SKIPS (live Bedrock opt-in). Never hangs, never errors.
- Non-vacuity confirmed: an inline drive of the FIXED `_drive_live(compaction_on=True)` under a 12s `asyncio.wait_for` returned 41 events with `pipeline_complete` (~8s) — where the pre-fix code (manifest `clarify.mode="auto"` + no answerer / no WS client) would block forever at `clarify_engine.py await event.wait()`. The clarify-off wrap is the load-bearing fix. (Offline best-effort SQLite FK warnings during the inline drive are PERSIST-02/03 graceful degradation, not failures.)

## Deviations from Plan

None - plan executed exactly as written. (One mechanical phrasing choice: comments/docstrings reference the dead flag descriptively rather than by its literal token, so the acceptance grep `count == 0` holds without losing the explanation. This is within the plan's intent — "no reintroduction of the dead flag".)

## Issues Encountered
- The first `grep -c ALWAYS_CLARIFY` returned non-zero because explanatory comments named the deleted flag. Resolved by rephrasing the four comment/docstring references to describe it ("the former auto-clarify module flag", "the deleted module flag (set False)") without the literal token. Re-verified `count == 0`.

## User Setup Required
None - no external service configuration required.

## Deferred (not blocking phase exit)
- The **live re-run** of `test_token_delta_live` (`RUN_LIVE_BEDROCK=1 AWS_PROFILE=... python3.11 -m pytest tests/agents/test_phase3_token_delta_live.py -v -s`, real Bedrock token-delta A/B) requires fresh AWS creds (default profile / acct 473293451041). Record as a next-Bedrock-pass item — phase exit is offline-deterministic and does NOT depend on it.

## Next Phase Readiness
- ISS-003 closed offline-deterministically (ROADMAP Phase 17 SC1). Ready for Plan 02 (ISS-010, in-memory span exporter test) and Plan 03 (ISS-011, HITL live-tail resilience).
- No blockers.

## Self-Check: PASSED

- FOUND: `.planning/phases/17-test-infra-and-verification-gap-closure/17-01-SUMMARY.md`
- FOUND: `backend/tests/agents/test_phase3_token_delta_live.py`
- FOUND commit: `88606ec1` (Task 1)

---
*Phase: 17-test-infra-and-verification-gap-closure*
*Completed: 2026-06-13*
