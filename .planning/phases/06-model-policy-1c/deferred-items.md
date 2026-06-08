# Deferred Items — Phase 06 (Model Policy 1C)

Out-of-scope pre-existing test failures observed during 06-01 execution. NOT caused
by this plan's changes (catalog/registry/settings projection). Logged, not fixed.

## 06-01 (full `tests/agents/ tests/unit/` regression run)

- `tests/unit/test_logout.py` (6 failures) — root cause: requests fail with HTTP 403
  `"Self-registration is disabled. Contact your administrator for an account."`. This is
  an environment/config gate (`ALLOW_SELF_REGISTRATION`), independent of the model catalog.
- `tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack`
  — `DID NOT RAISE asyncio.CancelledError`; log shows AWS `ExpiredTokenException`
  (expired local SSO/security token) during workflow-title generation. Environmental.
- (1 further unit failure of the same families — 9 failed / 949 passed / 19 skipped total.)

These do not touch `model_catalog.py`, `registry.py`, or `settings.py::AVAILABLE_MODELS`.
The plan's own gate subset (loader / banned-pattern / migration-ledger) and the catalog
suite are fully green; `lint-imports` is 3-kept / 0-broken.

## 06-02 (re-confirmed)

Same 9 failures reproduced unchanged in the `tests/agents/ tests/unit/` run for 06-02
(`test_logout.py` self-registration 403; `test_pipeline_cancel.py` async/expired-token).
06-02 touches only `agents/loader.py` + `tests/agents/test_loader.py` — neither suite
imports the loader. Out of scope; not fixed. `tests/agents/test_loader.py` is 44/44 green.

## 06-03 (re-confirmed; one carryover identified precisely)

The 06-03 `tests/agents/ tests/unit/` run lands at **9 failed / 976 passed / 19 skipped**:
- 7× `tests/unit/test_logout.py` (self-registration 403 — env gate, unchanged).
- 1× `tests/unit/test_pipeline_cancel.py` (expired AWS SSO token — env, unchanged).
- 1× `tests/agents/test_registry_capabilities.py::test_registered_count_is_exactly_fourteen`
  (`assert len(_KNOWN) == 14` now 15) — a **06-01 carryover**: 06-01 registered the
  `("model_catalog","default")` capability (bringing `_KNOWN` to 15) but did not update this
  hard-coded count assertion. VERIFIED pre-existing: it already fails at commit `e70f2db`
  (06-02 HEAD, before any 06-03 commit). 06-03 touches no registry/`_KNOWN` code. Out of
  scope for this plan; the count assertion should be bumped to 15 in a registry-owning fix.

Note: a transient set of 9 build-loop/cutover failures appeared mid-execution because the
first 06-03 rewire called `ectx.model_resolver.resolve(...)` unconditionally, crashing the
direct unit-style `_run_agent`/`_run_build_task_loop` invocations that build an
`ExecutionContext` without going through `execute()` (so `model_resolver is None`). This was
a Rule-1 bug **in this plan's change** and was fixed inline (the `_resolve_model` helper
falls back to the threaded `model_id` when the resolver is absent — parity-safe). Those 9
are GREEN again; they are NOT deferred.
