---
phase: 17-test-infra-and-verification-gap-closure
reviewed: 2026-06-13T14:36:23Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - backend/tests/agents/test_phase3_token_delta_live.py
  - backend/tests/agents/test_hooks.py
  - backend/tests/agents/test_phase8_live.py
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-06-13T14:36:23Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 17 is a test-harness-only phase (cluster C). The diff (`2c616827..HEAD`) touches exactly
the three in-scope test files plus planning artifacts — **no production code changed** (verified
via `git diff --name-only`). The `model_policy.py` transient-error classification was **NOT**
widened (the rejected "expired SSO is transient" hack was correctly avoided — `_TRANSIENT_SUBSTRINGS`
still lists only throttle/overload/quota tokens; no `expired`/`security token`).

All three intended fixes land their contract:

- **ISS-003** (`test_phase3_token_delta_live.py`): the dead `engine_mod.ALWAYS_CLARIFY = False`
  poke is gone (`grep ALWAYS_CLARIFY agents/ app/` = 0 hits); `_drive_live` now wraps
  `compile_for_run` and sets `compiled.clarify.mode = "off"`, restored in the existing `finally`.
  The engine calls `compile_for_run(pipeline_type)` positionally (engine.py:949), so the wrapper's
  signature is compatible. The new offline fault-injection test is genuinely bounded
  (`asyncio.wait_for(..., timeout=10)`) and non-vacuous (drives the real multi-task build
  scripted, asserts return). The live test stays double-gated (RUN_LIVE_BEDROCK + STS probe).
- **ISS-010** (`test_hooks.py`): the in-memory-exporter test injects via the hook's own
  `_build_span_processor` factory + resets module-private `_TRACER` (does NOT rely on a global
  `set_tracer_provider`, which would false-green), uses synchronous `SimpleSpanProcessor`, and
  asserts exactly 1 span with real attrs/scope + the audit row. `_TRACER` does not leak across
  tests: monkeypatch dedupes the two `setattr(otel, "_TRACER", …)` calls and reverts to the
  pre-test value on teardown (verified empirically). The console-degrade case is meaningful.
- **ISS-011** (`test_phase8_live.py`): the runtime re-check fixture is autouse-bound to
  `TestLiveHITL` only (does NOT skip `TestOfflineHITL`/`TestOfflineProof`), the skip-vs-fail logic
  is correct (`pytest.skip` on a non-None runtime reason), and the relaxed self-check still asserts
  collection consistency + runtime gate internal consistency (non-vacuous).

All three files pass / skip cleanly in isolation (27 passed + 1 skipped in test_phase3+test_hooks;
19 passed + 16 skipped in test_phase8_live).

The one real issue is a **test-isolation leak** in `_drive_live` (ISS-003 fix): it patches a
module-global it never restores, which can pollute later engine-driving tests in a full-session run.

## Warnings

### WR-01: `_drive_live` leaks `engine_mod.create_runner` — never restored in `finally`

**File:** `backend/tests/agents/test_phase3_token_delta_live.py:200,309-312`

**Issue:** `_drive_live` patches the engine-module-level `create_runner` global at line 200
(`engine_mod.create_runner = _live_create_runner`) **before** the `try`, but the `finally` block
(lines 309-312) only restores `engine_mod.compile_for_run` and `factory_mod.create_runner`. It
**never restores `engine_mod.create_runner`**, so after `_drive_live` returns, the engine module's
`create_runner` name stays bound to `_live_create_runner` for the rest of the pytest process.

`_live_create_runner` calls `build_model(getattr(ctx, "model", None))`, and `build_model()` with no
`ANTHROPIC_API_KEY` constructs a **real Bedrock client** (`app/agents/model_factory.py:29-55`). The
engine resolves the bare `create_runner` name against its own module namespace (`engine.py:45`
`from agents.factory import … create_runner`; call site `engine.py:2285`), so any subsequent test in
the same session that drives `ExecutionEngine.execute(...)` would route through the leaked
`_live_create_runner` → `build_model()` → a live Bedrock construction/credential attempt. This is the
exact "no test leaks global state across tests / no flakiness introduced" risk the phase guards against.

This is empirically confirmed: after one `_drive_live` call, `engine_mod.create_runner is <original
factory.create_runner>` is `False` and `engine_mod.create_runner.__name__ == "_live_create_runner"`.
The new offline test `test_drive_live_does_not_hang_at_clarify_gate` triggers the leak (it calls
`_drive_live(compaction_on=True)` and the leak survives the test).

It passes today only because no later test *in these two files* drives the engine after the leak (the
live test self-skips). In a full `tests/agents/` session the failure is **order-dependent and silent
until it bites** — precisely the flakiness class to avoid.

The established precedent the fix claims to mirror handles this correctly:
`_scripted_model._drive` snapshots `_orig_engine_create_runner = getattr(engine_mod, "create_runner",
None)` (with the comment *"leaking a nested wrapper or a stale patch would corrupt later runs"*) and
restores it in `finally` (`engine_mod.create_runner = _orig_engine_create_runner`). `_drive_live`
omits that snapshot/restore.

**Fix:** snapshot the engine-module create_runner before patching and restore it in `finally`,
mirroring `_scripted_model._drive`:

```python
# before the try (next to _orig_compile_for_run):
_orig_engine_create_runner = engine_mod.create_runner
engine_mod.create_runner = _live_create_runner
...
finally:
    engine_mod.compile_for_run = _orig_compile_for_run
    engine_mod.create_runner = _orig_engine_create_runner   # ← add this
    if factory_create_runner_orig is not None:
        factory_mod.create_runner = factory_create_runner_orig
```

(Optionally also move the line-200 patch inside the `try` so a failure between line 200 and the
`factory_mod` snapshot at line 205 can't leak either — but the snapshot/restore above is the
load-bearing fix.)

## Info

### IN-01: ISS-010 trailing `monkeypatch.setattr(otel, "_TRACER", None)` is redundant

**File:** `backend/tests/agents/test_hooks.py:718`

**Issue:** The comment at lines 715-718 implies the trailing `monkeypatch.setattr(otel, "_TRACER",
None)` is needed to stop the patched tracer leaking into other otel tests. It is not load-bearing:
pytest's `monkeypatch` dedupes by `(target, name)`, so the second `setattr(otel, "_TRACER", None)`
records no new "original" and `undo()` reverts `_TRACER` to its **pre-test** value (verified: after
teardown `_TRACER` is the original real tracer, never the in-memory-bound one). The line is harmless
but the comment overstates its role.

**Fix:** Either drop the trailing line, or trim the comment to note it is belt-and-suspenders
(monkeypatch already reverts `_TRACER` to its pre-test value on teardown).

### IN-02: `_full_html_compose_ctx` instance override and `_orig_compose_ctx` are not restored

**File:** `backend/tests/agents/test_phase3_token_delta_live.py:218,263`

**Issue:** When `compaction_on=False`, `engine._compose_context_message` is reassigned to the local
`_full_html_compose_ctx` and the original is never restored. This is currently harmless because
`engine` is a fresh `ExecutionEngine()` instance per `_drive_live` call (an instance-attribute
override, not a class/module patch), so it dies with the local. Worth a one-line comment to make the
"fresh-instance, no restore needed" intent explicit and prevent a future refactor (e.g. reusing one
engine across both A/B drives) from silently carrying the override into the compaction-ON run.

**Fix:** Add a brief comment at line 263 noting the override is scoped to this per-call local engine
instance (no restore needed), so a later refactor to a shared engine doesn't inherit it.

---

_Reviewed: 2026-06-13T14:36:23Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
