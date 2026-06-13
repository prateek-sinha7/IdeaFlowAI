# Phase 17: Test-Infra & Verification-Gap Closure - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Source:** Locked decisions from the 2026-06-13 deep root-cause investigation (cluster C). Findings + proper (no-hack) fixes are in `.planning/ISSUES-REGISTER.md` → "Deep Root-Cause Investigation". Code-proven file:line. No discuss round needed.

<domain>
## Phase Boundary

Close the 3 cluster-C issues — all **test-harness / verification-only, ZERO production code, no INV-3 exposure** (the engine/WS/FE are not touched):

1. **ISS-003** (test-infra) — `test_phase3_token_delta_live` hangs forever at the clarify gate.
2. **ISS-010** (verification gap, not a code bug) — OTLP span export is unverifiable here (no collector).
3. **ISS-011** (env/credential, not product) — Phase-8 HITL live-tail tests fail on mid-sweep SSO-token expiry.

IN SCOPE: `backend/tests/agents/test_phase3_token_delta_live.py`, a new/extended OTLP exporter test in `backend/tests/agents/test_hooks.py`, and `backend/tests/agents/test_phase8_live.py` (+ its harness `live_harness.py` only if a shared re-check helper is cleaner). Test/harness files only.

OUT OF SCOPE: any production code (`backend/app/**`, `backend/agents/**` non-test); cluster D (ISS-004/005/006 — Phase 19) and cluster E (ISS-014/015/019/021 — Phase 18); the live re-runs of ISS-003/ISS-011 that need fresh AWS creds (record as deferred — the `default` profile / acct 473293451041 is available when a live pass runs).

</domain>

<decisions>
## Implementation Decisions (LOCKED — proven file:line)

### ISS-003 — `_drive_live` must compile clarify off [LOCKED]
- **Root cause:** `backend/tests/agents/test_phase3_token_delta_live.py:173` sets `engine_mod.ALWAYS_CLARIFY = False` — a **dead** module attribute (the flag was deleted in 07-05; `grep -rn ALWAYS_CLARIFY agents/ app/` = 0 hits). `_drive_live` never sets `compiled.clarify.mode="off"`, so `prototype`'s `clarify.mode="auto"` forces the gate and the run blocks forever at `clarify_engine.py:155 await event.wait()` (no answerer, no WS client).
- **Fix:** in `_drive_live`, replace the dead line with the **same `compile_for_run` wrap every other harness uses** — snapshot `engine_mod.compile_for_run`, install a wrapper that calls the original then sets `compiled.clarify.mode = "off"`, and restore it in the existing `finally` (alongside the `factory_create_runner_orig` restore). EXACT precedents to mirror: `backend/tests/agents/_scripted_model.py:506-513` and `backend/tests/agents/live_harness.py:556-563`. `ClarifySpec` is a mutable dataclass (`agents/workflows/plan.py:289-298`) so the in-place write is valid; the wrap is per-call + reverted (OFF then ON across the two `_drive_live` invocations).
- **REJECTED hacks:** re-introduce the deleted `ALWAYS_CLARIFY` flag in the engine (dual-impl, INV-12); add a clarify timeout in `clarify_engine.py` (perturbs production HITL — the gate is deliberately no-timeout); flip the `prototype` manifest `clarify.mode` to off (breaks INV-3 + `test_manifest_parity.py`). The defect is in the TEST, fix it there.
- **Doesn't weaken the test:** clarify runs before the agent loop and emits no `input_tokens`, so suppressing it removes a hang, not the A/B token-delta measurement (COMPACT-03 was captured with a driver-side clarify-off patch).

### ISS-010 — close with an in-memory span exporter test [LOCKED]
- **Disposition:** verification gap, NOT a code gap (proven). "Declaration-driven hooks → legacy pipelines emit no spans" is true (all 18 manifests declare no `hooks:`). Given a collector + a hook-declaring step, spans DO export — proven by running the real `OtelTracingHook.handle` with an injected `InMemorySpanExporter` (1 span, correct attrs `flowin.hook/flowin.event/flowin.agent_id`, scope `flowin.agents.hooks.otel_tracing`).
- **Fix:** add a deterministic offline test (extend `backend/tests/agents/test_hooks.py` otel cluster). GOTCHA: the hook caches a **module-private `_TRACER`** and does NOT call `trace.set_tracer_provider()`, so a global-provider test won't capture its spans — inject via the module's own factory: `monkeypatch.setattr(otel, "_build_span_processor", lambda: SimpleSpanProcessor(InMemorySpanExporter()))` (hold the exporter ref) and `monkeypatch.setattr(otel, "_TRACER", None)`. Use `SimpleSpanProcessor` (synchronous — no force_flush). Drive the real `OtelTracingHook.handle({"event":"before_step","agent_id":...})` and assert one span + attrs + the `hook_runs` row + `continue` outcome. Add a parallel case: with `OTEL_EXPORTER_OTLP_ENDPOINT` set but the OTLP exporter pkg absent, `_build_span_processor()` returns the console processor (graceful-degrade) — pins the env-degradation contract.
- **REJECTED hacks:** stand up a live OTLP collector / install `opentelemetry-exporter-otlp` just to go green (env-dependent, non-deterministic, adds a deliberately-optional dep); a global `set_tracer_provider(InMemory…)` test (silently MISSES the hook's own `_TRACER` → false green).
- **Closure:** flip ISS-010 DEFERRED → FIXED-by-test; live OTLP export remains an optional end-of-milestone smoke, not a blocker.

### ISS-011 — skip (not fail) the HITL live-tail on mid-sweep credential expiry [LOCKED]
- **Disposition:** env/credential, NOT product (proven). The 3 HITL tests (`backend/tests/agents/test_phase8_live.py::TestLiveHITL::{test_live_gates_off_completes_without_gating, test_live_gate_on_pause_then_auto_resume, test_live_runner_tool_gate_resume}`) + the self-check (`TestCollectionSelfCheck::test_live_gate_is_consistent_and_self_skipping`) all trace to ONE cause: the default-profile SSO token expired ~2.5h into the sweep. An expired-SSO error is non-transient (`model_policy.py:185-211` lists only throttle/5xx/429), so it's swallowed to `error` → 0 tokens → `_check_tokens`'s `require_tokens=True` fails. The self-check fails because `_LIVE_SKIP` (captured at collection, line 116) ≠ runtime `live_skip_reason()` once STS stops resolving.
- **Fix (two parts):** Part 1 (closure) — re-run the 3 HITL cases after `aws sso login` and flip ISS-011 MONITORING→FIXED (a ~minutes, sub-$0.05 run; recorded as a DEFERRED next-live-pass item since it needs fresh creds — do NOT block the phase on it). Part 2 (the recurring-mode fix, the real deliverable here) — make the live tests resilient: an autouse fixture (or per-`@requires_live` test start) re-checks `live_skip_reason()` and `pytest.skip("AWS SSO session expired mid-sweep — re-run after aws sso login")` when creds have lapsed, instead of letting it fail an assertion; and relax `test_live_gate_is_consistent_and_self_skipping` so it tolerates the legitimate collection-valid → runtime-expired drift (don't assert strict equality across a long run). `live_skip_reason()` is already runtime-callable — that's what makes the fix clean.
- **REJECTED hacks:** "just re-run" with no harness change (leaves the recurring fault — the next 3-hr sweep reddens whatever runs past the token boundary, indistinguishable from a real regression); add "expired"/"security token" to `_TRANSIENT_SUBSTRINGS` so the runner "retries" (DANGEROUS — an expired SSO token can't be refreshed by a botocore retry; it would mask real `AccessDenied`/`ValidationException` faults and perturb production error semantics — INV-3-relevant).
- Offline proof the seams are sound: `TestOfflineHITL` (5 cases) already passes with no creds.

### INVARIANTS
- **Test/harness-only** — NO production code (`backend/app/**` or non-test `backend/agents/**`). Therefore the 5 characterization goldens are untouched by construction; still run them + lint-imports as the parity guard (must stay green / 4 kept / 0 broken).
- **Runtime:** `python3.11` (NO venv). The FULL backend pytest HANGS offline — verify with the targeted suite + the specific new/edited tests only (offline-test-suite memory).
- No new tables/migrations (none needed).

</decisions>

<canonical_refs>
## Canonical References (read before planning/implementing)

### The WHY
- `.planning/ISSUES-REGISTER.md` → "Deep Root-Cause Investigation" rows ISS-003 / ISS-010 / ISS-011 (root cause / proper fix / rejected hack / verification columns).

### Files to edit (test/harness only)
- `backend/tests/agents/test_phase3_token_delta_live.py` (`_drive_live`, lines ~165-285; the dead `ALWAYS_CLARIFY=False` at :173).
- `backend/tests/agents/test_hooks.py` (extend the otel cluster with the in-memory-exporter test).
- `backend/tests/agents/test_phase8_live.py` (the 3 HITL tests + the self-check at ~:992-1021; `_LIVE_SKIP` at :116).

### Precedent anchors (READ-ONLY)
- `backend/tests/agents/_scripted_model.py:506-513` + `backend/tests/agents/live_harness.py:556-563` — the `compile_for_run`-wrap clarify-off pattern (ISS-003 mirror).
- `backend/agents/capabilities/hooks/otel_tracing.py` — `handle` (:138-172), `_get_tracer` (:104-120), `_build_span_processor` (:77-101), module-private `_TRACER` (ISS-010 injection seam — READ-ONLY, the fix is in the test).
- `backend/agents/execution_engine/model_policy.py:185-211` — the transient-error classification (ISS-011: why expired-SSO is non-transient — do NOT change this).
- `backend/tests/agents/live_harness.py` `live_skip_reason()` / `_aws_creds_resolve()` (:330-352) — the runtime re-check ISS-011 Part 2 uses.

</canonical_refs>

<specifics>
## Specific Ideas / Landmines
- ISS-010's #1 landmine: the hook uses a module-private `_TRACER`, not the global provider — inject via `_build_span_processor` + reset `_TRACER`, or the test gets a false green. Use `SimpleSpanProcessor` (sync) so no `force_flush` is needed.
- ISS-003: `_drive_live` is LOCAL to its file (no cross-imports) — blast radius is exactly that one test.
- ISS-011: the self-check test's strict collection-vs-runtime equality IS the actual bug in that test (it assumes the SSO session is immortal across a multi-hour run).
- All three are deterministically verifiable OFFLINE (fault-injection for 003; in-memory exporter for 010; an expired-creds simulation / `TestOfflineHITL` for 011). The phase exit does NOT depend on live Bedrock.
</specifics>

<deferred>
## Deferred Ideas
- The live re-runs of ISS-003 (`RUN_LIVE_BEDROCK=1` token-delta) and ISS-011 (the 3 HITL cases on fresh creds) — next Bedrock pass; not blocking.
- Cluster D (ISS-004/005/006) → Phase 19; cluster E (ISS-014/015/019/021) → Phase 18.
</deferred>

---

*Phase: 17-test-infra-and-verification-gap-closure*
*Context: 2026-06-13 from the cluster-C deep investigation, code-proven file:line.*
