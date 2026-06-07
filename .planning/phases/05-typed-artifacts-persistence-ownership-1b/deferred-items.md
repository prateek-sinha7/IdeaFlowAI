# Deferred Items — Phase 05

Out-of-scope discoveries logged during execution (per executor SCOPE BOUNDARY rule).
These are NOT caused by the current plan's changes and were NOT fixed.

## 05-02 (Typed artifacts persistence schema)

Pre-existing test failures in `tests/agents/ tests/unit/` regression run — all
environment/config issues, none touch ORM models or migrations:

- `tests/unit/test_logout.py` (7 failures) — registration returns 403
  "Self-registration is disabled. Contact your administrator for an account."
  The tests assume self-registration is enabled; the dev environment has it
  disabled. Config/env gate, unrelated to 05-02 model/migration changes.
- `tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack`
  — `ExpiredTokenException` from a real Bedrock Converse call (expired AWS
  security token). Live-credential env issue, unrelated to 05-02.

Scope confirmation: 05-02 modified only `backend/app/models/*` and
`backend/alembic/versions/0014_*` + its test. The 0014 migration test, the
existing `test_alembic.py` drift/check suite, and `lint-imports` all pass.
