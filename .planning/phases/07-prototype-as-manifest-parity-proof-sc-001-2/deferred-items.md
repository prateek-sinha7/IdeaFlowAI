# Deferred Items — Phase 07

Out-of-scope failures discovered during 07-01 execution (NOT caused by this
plan's changes — capability seams + parser only touch
`agents/capabilities/**` + `agents/execution_engine/context.py`). Logged per the
executor SCOPE BOUNDARY rule; not fixed here.

## Pre-existing unrelated test failures (full `tests/unit/` run, 07-01)

These fail on the working tree independently of 07-01's changes (verified: they
fail with 07-01's source files stashed/absent). They live in the auth/logout and
pipeline-cancel subsystems, untouched by Phase 7.

- `tests/unit/test_logout.py::TestJtiClaim::test_register_token_has_jti`
- `tests/unit/test_logout.py::TestJtiClaim::test_two_tokens_have_distinct_jtis`
- `tests/unit/test_logout.py::TestLogoutRevokesToken::test_logout_returns_204_and_blocks_subsequent_me`
- `tests/unit/test_logout.py::TestPerTokenRevocation::test_second_login_token_survives_first_logout`
- `tests/unit/test_logout.py::TestPasswordChangeRevocation::test_change_password_revokes_old_tokens`
- `tests/unit/test_logout.py::TestLogoutIdempotent::test_double_logout_returns_204_each_time`
- `tests/unit/test_logout.py::TestLogoutPersistsCorrectRow::test_revocation_row_has_matching_exp`
- `tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack`

The 07-01 plan's stated baseline scope (`tests/agents` characterization/parity)
is GREEN; these `tests/unit` failures are outside that net. Surface to the phase
owner for a separate triage.
