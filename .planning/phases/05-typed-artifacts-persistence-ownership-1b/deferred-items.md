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

## 05-04 (Typed substrate + persistence wiring)

- `backend/tests/agents/characterization/_normalize.py` — pre-existing ruff
  `B905` (`zip(seqs, seqs[1:])` without `strict=`) in `assert_seq_contiguous`.
  Predates 05-04 (present at HEAD before this plan); 05-04 only edited the
  `_VOLATILE_STRIP_KEYS` frozenset in the same file. Left untouched per the
  executor SCOPE BOUNDARY rule (do not fix pre-existing lint in unrelated lines).
- `backend/app/api/websocket.py:619` — pre-existing ruff `B023` (loop-variable
  binding `_rev_target_type` in a closure). Predates 05-04; this plan only added
  the `session_id=chat_session_id` kwarg to the `engine.execute()` call. Out of
  scope.

## 05-06 (Thin-store consumer migration)

- `backend/app/api/websocket.py` — the same pre-existing ruff `B023`
  (`_rev_target_type` closure binding) now reports at line ~631 (shifted up by
  the 05-06 reconnect-block line removals, not introduced by this plan). Still out
  of scope per SCOPE BOUNDARY.
- `backend/agents/execution_engine/clarify_engine.py:197` — pre-existing ruff
  `F841` (`inferred_intent` assigned but never used in `_generate_questions`).
  Present at HEAD before 05-06; this plan only edited `_persist_qa` + `run`/
  `__init__`. Out of scope.
- `backend/tests/unit/test_logout.py` (7) + `backend/tests/unit/test_pipeline_cancel.py`
  (1) — pre-existing environmental failures (self-registration disabled → 403;
  expired AWS Bedrock token). Documented in 05-04; not chased.
