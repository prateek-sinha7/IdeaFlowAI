---
phase: 17-test-infra-and-verification-gap-closure
plan: 03
subsystem: testing
tags: [pytest, aws-sso, bedrock, hitl, live-tail, skip-on-expiry, iss-011]

# Dependency graph
requires:
  - phase: 08-live-verification-suite
    provides: "test_phase8_live.py — the gated live HITL suite + TestOfflineHITL offline proof + live_harness.live_skip_reason() runtime credential re-check"
provides:
  - "Mid-sweep SSO/credential expiry now SKIPS (not FAILS) the 3 Phase-8 HITL live-tail cases via a per-test live_skip_reason() re-check (autouse on TestLiveHITL)"
  - "Relaxed TestCollectionSelfCheck self-check that tolerates collection-valid -> runtime-expired drift (no strict cross-time equality)"
  - "Offline expired-creds skip simulation (+ no-op complement) pinning the recurring-mode contract deterministically with no creds"
affects: [live-verification, bedrock-pass, hitl, end-of-milestone-smoke]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-test runtime credential re-check (autouse fixture scoped to a live class) that converts a mid-run env lapse into pytest.skip, not an assertion failure"
    - "Self-check asserts gate correctness per point-in-time, never byte-equality of a snapshot across a multi-hour run"

key-files:
  created: []
  modified:
    - backend/tests/agents/test_phase8_live.py
    - .planning/ISSUES-REGISTER.md

key-decisions:
  - "Fix lives entirely in the test harness (skip-on-expiry); the transient-error classification in model_policy.py is deliberately left unchanged"
  - "Re-check resolves live_skip_reason() via the live_harness MODULE (not the collection-time bound name) so the offline simulation can monkeypatch it"
  - "Part 1 (live re-run after aws sso login) recorded as DEFERRED — needs fresh creds, not blocking; phase exit is offline-deterministic"

patterns-established:
  - "Runtime env re-check pattern: an autouse fixture bound to the live class re-evaluates the single runtime source of truth at each test start and SKIPs cleanly on a mid-run lapse"
  - "Drift-tolerant self-check: assert internal gate consistency at collection AND at runtime separately, never equality across the two snapshots"

requirements-completed: [ISS-011]

# Metrics
duration: ~12min
completed: 2026-06-13
---

# Phase 17 Plan 03: ISS-011 — Skip HITL Live-Tail on Mid-Sweep Credential Expiry Summary

**The 3 Phase-8 HITL live-tail cases now SKIP (not FAIL) on mid-sweep SSO-token expiry via a per-test `live_skip_reason()` re-check, the self-check tolerates the collection→runtime drift, and an offline expired-creds simulation pins the contract — all test-file-only, `model_policy.py` untouched.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-13T14:18:00Z
- **Completed:** 2026-06-13T14:29:45Z
- **Tasks:** 2 (Task 1 code+commit; Task 2 verification-only — no commit)
- **Files modified:** 2 (`test_phase8_live.py`, `ISSUES-REGISTER.md`)

## Accomplishments
- **Recurring-mode fix (the real deliverable):** added `_skip_if_creds_lapsed_mid_sweep()` + an `autouse` fixture bound to `TestLiveHITL` that re-evaluates `live_skip_reason()` at each live-test start and `pytest.skip(...)`s with the exact re-run-after-`aws sso login` command when creds have lapsed — converting a mid-sweep STS lapse from a spurious 0-token assertion FAILURE into a clean SKIP. The fixture is scoped to the live class only, so `TestOfflineHITL` / `TestOfflineProof` are never skipped.
- **Relaxed the self-check:** `test_live_gate_is_consistent_and_self_skipping` no longer asserts strict `_LIVE_SKIP == live_skip_reason()` (the actual bug — it assumed the SSO session is immortal across a multi-hour run). It now asserts gate correctness per point-in-time (collection snapshot AND runtime, separately) and tolerates the legitimate collection-valid → runtime-expired drift, with an ISS-011 comment.
- **Offline proof of the recurring-mode contract:** new `test_live_hitl_skips_on_mid_sweep_credential_expiry` monkeypatches `live_harness.live_skip_reason` to return an expiry reason and asserts the guard raises `pytest.skip.Exception` (SKIP, not FAIL); a no-op complement `test_live_hitl_recheck_is_noop_when_creds_resolve` proves the guard does NOT skip when creds resolve. Both run fully offline (no Bedrock, no AWS).
- **ISS-011 flipped MONITORING → FIXED (17-03, by-test; Part-1 live re-run deferred)** in `.planning/ISSUES-REGISTER.md`.

## Task Commits

1. **Task 1: per-test re-check + relaxed self-check + offline expired-creds simulation** — `99c1aad1` (test)
2. **Task 2: parity guard (verification-only — no code change, no commit)** — N/A

**Plan metadata:** (final docs commit below)

## Files Created/Modified
- `backend/tests/agents/test_phase8_live.py` — added `_skip_if_creds_lapsed_mid_sweep()` helper + autouse `_recheck_creds_at_runtime` fixture on `TestLiveHITL`; relaxed `test_live_gate_is_consistent_and_self_skipping`; added the offline expiry-skip simulation + no-op complement.
- `.planning/ISSUES-REGISTER.md` — ISS-011 status MONITORING → **FIXED** (17-03, by-test; Part-1 live re-run deferred).

## Decisions Made
- **Fix confined to the test harness** (skip-on-expiry). The transient-error classification (`model_policy.py:185-211`) is deliberately UNCHANGED — widening `_TRANSIENT_SUBSTRINGS` to retry "expired"/"security token" was the explicitly REJECTED dangerous hack (an expired SSO token can't be refreshed by a botocore retry, and it would mask real `AccessDenied`/`ValidationException` faults — INV-3-relevant). The diff-guard confirms `model_policy.py` is absent from the diff.
- **Re-check resolves `live_skip_reason()` via the `live_harness` module** (`from tests.agents import live_harness; live_harness.live_skip_reason()`), not the collection-time bound symbol, so the offline simulation can `monkeypatch.setattr(live_harness, "live_skip_reason", ...)` deterministically.
- **Self-check asserts internal consistency at each point in time** rather than equality across collection vs runtime — the only correct invariant for a gate that legitimately drifts mid-sweep.

## Deviations from Plan

None - plan executed exactly as written. (Note: the plan referenced `model_policy.py` under `backend/agents/execution_engine/`; the file actually lives at `backend/agents/model_policy.py`. This is immaterial — the constraint was to NOT touch it, and the diff confirms it is untouched.)

## Issues Encountered
None.

## Parity Guard (Task 2 — SC-001 / INV-3)
Test-harness-only change; parity satisfied by construction AND verified:
- `git diff --name-only` (Task 1 working tree) listed ONLY `backend/tests/agents/test_phase8_live.py` — non-test-file guard exited clean; `model_policy.py` absent from the diff (transient classification untouched).
- 5 characterization golden suites (`prototype`, `od_prototype`, `prototype_revision`, `od_ppt`, `app_builder`) — **10 passed**, byte-identical, `SNAPSHOT_UPDATE` unset (no regeneration).
- `/opt/homebrew/bin/lint-imports` — **4 contracts kept / 0 broken**.
- Targeted offline subset `tests/agents/test_phase8_live.py -k "OfflineHITL or self_skipping or mid_sweep or recheck_is_noop"` — **8 passed** (TestOfflineHITL green, relaxed self-check green, expiry-skip simulation green, no-op complement green).

## Deferred (not blocking)
- **ISS-011 Part 1 (closure confirmation):** re-run the 3 `TestLiveHITL` cases after `aws sso login` on fresh default-profile creds (acct 473293451041) — sub-$0.05, ~minutes — on the next Bedrock pass to confirm the live-green path. NOT blocking: needs fresh creds and the phase exit is offline-deterministic.

## Next Phase Readiness
- Phase 17 (cluster-C test-infra / verification-gap closure) is COMPLETE: ISS-003 (17-01), ISS-010 (17-02), ISS-011 (17-03) all closed offline-deterministically.
- ROADMAP Phase 17 Success Criterion 3 (ISS-011 mid-sweep expiry SKIPS, self-check tolerates the drift, offline HITL green) satisfied.
- Live re-runs of ISS-003 (`RUN_LIVE_BEDROCK=1` token-delta) and ISS-011 (3 HITL cases) are queued for the next Bedrock pass.

## Self-Check: PASSED
- FOUND: `.planning/phases/17-test-infra-and-verification-gap-closure/17-03-SUMMARY.md`
- FOUND: `backend/tests/agents/test_phase8_live.py`
- FOUND commit: `99c1aad1` (Task 1)

---
*Phase: 17-test-infra-and-verification-gap-closure*
*Completed: 2026-06-13*
