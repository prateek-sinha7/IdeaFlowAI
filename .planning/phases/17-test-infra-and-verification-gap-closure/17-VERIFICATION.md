---
phase: 17-test-infra-and-verification-gap-closure
verified: 2026-06-13T16:55:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Phase 17: Test-Infra and Verification-Gap Closure Verification Report

**Phase Goal:** Close the 3 test-infra/verification-gap issues of cluster C (ISS-003, ISS-010, ISS-011) — all test-harness-only, zero production code, no INV-3 exposure. Deterministically closeable offline; live re-runs needing fresh creds are deferred, not blocking.
**Verified:** 2026-06-13T16:55:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (the 4 ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | ISS-003: `_drive_live` compiles `clarify.mode="off"` (replacing the dead `ALWAYS_CLARIFY` flag) + restores `compile_for_run` AND `engine_mod.create_runner` in `finally` (WR-01 leak fix); a bounded fault-injection test proves no clarify-gate hang; offline collection still skips. | ✓ VERIFIED | `test_phase3_token_delta_live.py:192,217-222` wraps `compile_for_run` and sets `compiled.clarify.mode = "off"`; `:208` snapshots `_orig_engine_create_runner`, `:324-325` restores BOTH `compile_for_run` and `create_runner` in `finally`; `grep -c ALWAYS_CLARIFY` = 0 in both test file and `agents/`+`app/`. `test_drive_live_does_not_hang_at_clarify_gate` (:346) drives the real `_drive_live` offline with scripted models under `asyncio.wait_for(..., 10)` and asserts return. Suite: **1 passed, 1 skipped** (live test skips). |
| 2 | ISS-010: deterministic offline test asserts the OTLP hook emits a span via an injected `InMemorySpanExporter` (`_build_span_processor` monkeypatched + `_TRACER` reset — NOT a global provider), plus a graceful-degrade case; existing otel tests stay green. | ✓ VERIFIED | `test_hooks.py:683` monkeypatches `otel._build_span_processor → SimpleSpanProcessor(InMemorySpanExporter())`, `:685` resets `_TRACER=None`; drives real `OtelTracingHook.handle({"event":"before_step","agent_id":"build"})` and asserts exactly 1 span `hook.before_step` with attrs `flowin.hook/flowin.event/flowin.agent_id` + scope `flowin.agents.hooks.otel_tracing` + `HOOK_CONTINUE` + audit row. Degrade test `:722` forces OTLP import failure → asserts `SimpleSpanProcessor(ConsoleSpanExporter)`. Suite `-k otel`: **10 passed** (8 existing + 2 new). |
| 3 | ISS-011: the Phase-8 HITL live-tail tests SKIP (not fail) on simulated mid-sweep credential expiry via a per-test `live_skip_reason()` re-check scoped to `TestLiveHITL`; the self-check no longer asserts strict collection-vs-runtime equality; `TestOfflineHITL` stays green. | ✓ VERIFIED | `test_phase8_live.py:556-564` autouse fixture bound to `TestLiveHITL` only calls `_skip_if_creds_lapsed_mid_sweep()` (`:120-141`) which `pytest.skip`s on a non-None runtime `live_skip_reason()`. Self-check `:1026` dropped strict `_LIVE_SKIP == live_skip_reason()` (`:1044-1051` comment), now asserts per-point-in-time gate correctness. Offline sim `test_live_hitl_skips_on_mid_sweep_credential_expiry` (:1078, in `TestCollectionSelfCheck` — NOT gated) proves SKIP via monkeypatched `live_harness.live_skip_reason`; no-op complement (:1105). Subset run: **8 passed** offline; `TestLiveHITL`: **3 skipped** (collection gate). |
| 4 | ISS-004 invariant: ZERO production code changed (test files only; `model_policy.py` UNCHANGED); the 5 characterization goldens + lint-imports 4/0 unaffected; live re-runs deferred. | ✓ VERIFIED | `git diff --name-only 2c616827..HEAD` (base = phase-plan commit): only `backend/tests/agents/{test_hooks,test_phase3_token_delta_live,test_phase8_live}.py` + planning docs. No `backend/app/**`, no non-test `backend/agents/**`. `model_policy.py` absent from diff; `_TRANSIENT_SUBSTRINGS` (`:201-211`) still throttle/overload/quota only — no `expired`/`security token`. 5 goldens: **10 passed** byte-identical. lint-imports: **4 kept / 0 broken**. Live re-runs (ISS-003 token-delta, ISS-011 HITL) recorded as deferred in SUMMARYs + ISSUES-REGISTER. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/tests/agents/test_phase3_token_delta_live.py` | compile_for_run clarify-off wrap + finally restore (incl. WR-01 create_runner) + bounded fault-injection test | ✓ VERIFIED | Wrap at :217-222; dual finally restore at :324-325; regression test at :346 passes offline |
| `backend/tests/agents/test_hooks.py` | in-memory-exporter span-capture test (own factory + `_TRACER` reset) + OTLP-degrade test | ✓ VERIFIED | :663 + :722; 10 otel tests green; no tracer leak (monkeypatch reverts) |
| `backend/tests/agents/test_phase8_live.py` | per-test `live_skip_reason()` re-check on `TestLiveHITL` + relaxed self-check + offline expiry sim | ✓ VERIFIED | autouse fixture :556 scoped to `TestLiveHITL`; relaxed self-check :1026; offline sims :1078/:1105 in `TestCollectionSelfCheck` |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `_drive_live` | `engine.compile_for_run` | snapshot + wrapper sets `clarify.mode="off"` + finally restore | ✓ WIRED | :192/:217-222/:324 |
| `_drive_live` | `engine.create_runner` | snapshot `_orig_engine_create_runner` + finally restore (WR-01) | ✓ WIRED | :208/:325 |
| otel test | `otel._build_span_processor` / `_TRACER` | monkeypatch factory → `SimpleSpanProcessor(InMemorySpanExporter)` + reset `_TRACER` | ✓ WIRED | :683/:685; drives real `handle`, reads `get_finished_spans()` |
| `TestLiveHITL` | `live_harness.live_skip_reason` | autouse fixture → module-resolved re-check → `pytest.skip` | ✓ WIRED | :137 resolves via module so the offline sim can monkeypatch |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| ISS-003 no clarify hang offline | `pytest test_phase3_token_delta_live.py -q` | 1 passed, 1 skipped (8.85s) | ✓ PASS |
| ISS-010 span emitted + degrade | `pytest test_hooks.py -k otel -q` | 10 passed | ✓ PASS |
| ISS-011 skip-not-fail offline | `pytest test_phase8_live.py -k "OfflineHITL or self_skipping or mid_sweep or recheck_is_noop" -q` | 8 passed | ✓ PASS |
| TestLiveHITL skips (collection gate) | `pytest test_phase8_live.py::TestLiveHITL -q` | 3 skipped | ✓ PASS |
| 5 characterization goldens byte-identical | `pytest <5 characterization suites> -q` | 10 passed (34.25s) | ✓ PASS |
| Import contracts intact | `lint-imports` | 4 kept / 0 broken | ✓ PASS |
| Zero production code over phase commits | `git diff --name-only 2c616827..HEAD \| grep production` | empty | ✓ PASS |
| model_policy.py transient list not widened | `grep _TRANSIENT_SUBSTRINGS / expired / "security token"` | throttle/overload/quota only | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| ISS-003 | 17-01 | token-delta clarify hang → compile clarify off in `_drive_live` | ✓ SATISFIED | Wrap + WR-01 restore + regression test; FIXED in ISSUES-REGISTER |
| ISS-010 | 17-02 | OTLP unverifiable → deterministic in-memory-exporter test | ✓ SATISFIED | In-memory exporter + degrade tests; FIXED-by-test in ISSUES-REGISTER |
| ISS-011 | 17-03 | HITL live-tail fails on SSO expiry → skip-not-fail harness re-check | ✓ SATISFIED | Per-test re-check + relaxed self-check + offline sim; FIXED in ISSUES-REGISTER |

Note: ISS-003/010/011 are ISSUE IDs (ISSUES-REGISTER cluster C), not REQUIREMENTS.md REQ-IDs — REQ-traceability intentionally not applicable; all three flipped to FIXED in the register.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| — | — | None | — | No unreferenced TBD/FIXME/XXX in the 3 edited files; no stub/placeholder/empty-return patterns in the new test bodies. |

### Human Verification Required

None. The phase is deterministically verifiable offline. The live re-runs (ISS-003 `RUN_LIVE_BEDROCK=1` token-delta A/B; ISS-011 3 HITL cases after `aws sso login`) are explicitly DEFERRED per the defer-live-verification convention and recorded in the SUMMARYs + ISSUES-REGISTER — they need fresh AWS creds and do NOT block phase exit.

### Gaps Summary

No gaps. All 4 ROADMAP success criteria are observably true in the actual code (not merely claimed in SUMMARY):

- ISS-003: the dead `ALWAYS_CLARIFY` poke is gone; `_drive_live` wraps `compile_for_run` to set `clarify.mode="off"` and restores both `compile_for_run` and `create_runner` (the WR-01 leak fix from code review) in `finally`; a bounded scripted offline drive returns inside the 10s bound.
- ISS-010: the in-memory exporter is injected via the hook's OWN `_build_span_processor` factory with `_TRACER` reset (the false-green landmine avoided), proving 1 span with correct attrs/scope; the OTLP-absent console degrade is pinned.
- ISS-011: a per-test `live_skip_reason()` re-check autouse-bound to `TestLiveHITL` converts mid-sweep expiry into SKIP; the self-check drops strict cross-time equality; an offline monkeypatched simulation proves the skip; `TestOfflineHITL` stays green.
- ISS-004 invariant: the diff over the phase commit range (`2c616827..HEAD`) is the 3 test files + planning docs only; `model_policy.py` untouched and its transient-error classification not widened; 5 goldens byte-identical (10 passed); lint-imports 4/0.

The code review (17-REVIEW.md) found WR-01 (a `create_runner` leak) which 17-REVIEW-FIX.md fixed (commit `da98b266`); the fix is present and verified in the current code (`:208`/`:325`).

---

_Verified: 2026-06-13T16:55:00Z_
_Verifier: Claude (gsd-verifier)_
