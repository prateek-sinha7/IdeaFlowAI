---
phase: 17-test-infra-and-verification-gap-closure
plan: 02
subsystem: testing
tags: [opentelemetry, otel, in-memory-span-exporter, hooks, observability, pytest, verification-gap]

# Dependency graph
requires:
  - phase: 08-hooks-observability
    provides: "OtelTracingHook (otel_tracing) — module-private _TRACER + _build_span_processor factory; ConsoleSpanExporter default / OTLP via OTEL_EXPORTER_OTLP_ENDPOINT"
provides:
  - "Deterministic OFFLINE proof that OtelTracingHook.handle exports exactly 1 span with flowin.hook/flowin.event/flowin.agent_id under scope flowin.agents.hooks.otel_tracing, captured via an injected InMemorySpanExporter"
  - "A pinned env-degradation contract: OTLP-exporter-pkg-absent → _build_span_processor() falls back to SimpleSpanProcessor(ConsoleSpanExporter)"
  - "ISS-010 flipped DEFERRED → FIXED-by-test (no live collector required)"
affects: [observability, otel, hooks, end-of-milestone-live-smoke]

# Tech tracking
tech-stack:
  added: []  # no new deps — InMemorySpanExporter ships with the already-present opentelemetry-sdk
  patterns:
    - "Capture a hook's spans by monkeypatching its OWN exporter factory (_build_span_processor) + resetting its module-private cached _TRACER — NOT a global set_tracer_provider (which the hook never reads → false green)"
    - "Use SimpleSpanProcessor (synchronous) for span-capture tests so no force_flush is needed"

key-files:
  created: []
  modified:
    - "backend/tests/agents/test_hooks.py — +2 tests in the otel cluster (span-capture via in-memory exporter + OTLP-pkg-absent console degrade)"
    - ".planning/ISSUES-REGISTER.md — ISS-010 DEFERRED → FIXED (17-02, by-test)"

key-decisions:
  - "Closed ISS-010 with an in-memory-exporter test, NOT a live OTLP collector — deterministic, offline, zero new deps"
  - "Injected via the hook's own _build_span_processor + _TRACER reset to avoid the false-green landmine (the hook does not use the global provider)"
  - "Live OTLP-collector export remains an OPTIONAL end-of-milestone smoke, not a phase blocker"

patterns-established:
  - "Hook-span verification pattern: monkeypatch _build_span_processor → SimpleSpanProcessor(InMemorySpanExporter()), reset _TRACER=None, drive the real handle(), read exporter.get_finished_spans()"

requirements-completed: [ISS-010]

# Metrics
duration: 2min
completed: 2026-06-13
---

# Phase 17 Plan 02: ISS-010 OTLP Verification-Gap Closure Summary

**The OtelTracingHook is proven to export exactly 1 span (correct attrs + scope) through an injected InMemorySpanExporter — closing the OTLP verification gap deterministically offline, with the OTLP-pkg-absent console-degrade path pinned alongside.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-06-13T14:22:22Z
- **Completed:** 2026-06-13T14:24:16Z
- **Tasks:** 2
- **Files modified:** 2 (1 test file + the issues register)

## Accomplishments
- Added `test_otel_tracing_exports_one_span_with_attrs_via_in_memory_exporter`: drives the REAL `OtelTracingHook.handle({"event":"before_step","agent_id":"build"})` through an injected `InMemorySpanExporter` (via the hook's own `_build_span_processor` factory + `_TRACER` reset) and asserts exactly 1 span named `hook.before_step` with `flowin.hook == "otel_tracing"`, `flowin.event == "before_step"`, `flowin.agent_id == "build"`, instrumentation scope `flowin.agents.hooks.otel_tracing`, `HOOK_CONTINUE`, and one `hook_runs` row (`detail["span"] is True`).
- Added `test_otel_build_span_processor_degrades_to_console_when_otlp_pkg_absent`: with `OTEL_EXPORTER_OTLP_ENDPOINT` set and the lazy OTLP-exporter import forced to fail, `_build_span_processor()` degrades to `SimpleSpanProcessor(ConsoleSpanExporter)` (not a Batch/OTLP processor).
- Verified the otel cluster: 8 existing + 2 new = 10 green, no span/tracer leak across tests.
- Ran the SC-001 / INV-3 parity guard: 5 characterization goldens byte-identical (10 tests), `lint-imports` 4 kept / 0 broken, diff test-only.
- Flipped ISS-010 DEFERRED → FIXED (17-02, by-test) in the issues register.

## Task Commits

1. **Task 1: in-memory-exporter span-capture + OTLP-degrade tests** - `83088073` (test)
2. **Task 2: parity guard (goldens + lint-imports + test-only diff)** - no-code parity assertion; verified, no commit (working tree had no production change to commit)

**Plan metadata:** committed with this SUMMARY + STATE.md + ROADMAP.md + ISSUES-REGISTER.md.

## Files Created/Modified
- `backend/tests/agents/test_hooks.py` — +2 tests extending the otel cluster (span-capture via injected in-memory exporter; OTLP-pkg-absent console-degrade). Hook source untouched.
- `.planning/ISSUES-REGISTER.md` — ISS-010 row flipped DEFERRED → FIXED (17-02, by-test) with the closure note.

## Decisions Made
- Closed ISS-010 via an in-memory-exporter test rather than standing up a live OTLP collector or installing `opentelemetry-exporter-otlp` — deterministic, offline, no new deps.
- Injected via the hook's OWN `_build_span_processor` factory + `_TRACER=None` reset (NOT a global `set_tracer_provider`) — the hook caches a module-private `_TRACER` and never reads the global provider, so a global-provider test would silently miss its spans (a false green). This is the #1 landmine called out in 17-CONTEXT and was avoided.
- Asserted the instrumentation scope via `span.instrumentation_scope.name == otel._TRACER_NAME`; used `SimpleSpanProcessor` (synchronous) so no `force_flush` is needed.

## Deviations from Plan

None - plan executed exactly as written.

## SC-001 / INV-3 Parity

Test-harness-only change (a single test file plus a planning-doc register flip). The otel hook reads no characterization input (all 18 manifests declare no `hooks:`), so the 5 characterization goldens are unaffected by construction — AND verified: all 5 golden suites pass byte-identical with `SNAPSHOT_UPDATE` unset, `/opt/homebrew/bin/lint-imports` reports 4 contracts kept / 0 broken, and `git diff --name-only` (pre-commit) listed only `backend/tests/agents/test_hooks.py`. Zero production/behavior change.

## Issues Encountered
None. The span instrumentation-scope accessor (`span.instrumentation_scope.name`) and `SimpleSpanProcessor.span_exporter` were confirmed against the installed `opentelemetry-sdk` before writing the assertions.

## User Setup Required
None - no external service configuration required.

## Deferred (not blocking)
- A live OTLP-collector export (real `OTEL_EXPORTER_OTLP_ENDPOINT` + a hook-declaring workflow + a running collector) remains an OPTIONAL end-of-milestone smoke. ISS-010 is closed by the in-memory-exporter test; the live smoke is confirmatory only.

## Next Phase Readiness
- Phase 17: 2 of 3 plans complete (17-01 ISS-003, 17-02 ISS-010). 17-03 (ISS-011 — skip-on-SSO-expiry HITL live-tail harness fix) remains.
- ROADMAP Phase 17 Success Criterion 2 (ISS-010 / OTLP verification) satisfied deterministically.

## Self-Check: PASSED
- `backend/tests/agents/test_hooks.py` present with the `InMemorySpanExporter` test.
- Task 1 commit `83088073` present in git history.
- SUMMARY file present on disk.

---
*Phase: 17-test-infra-and-verification-gap-closure*
*Completed: 2026-06-13*
