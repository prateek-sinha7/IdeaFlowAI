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
