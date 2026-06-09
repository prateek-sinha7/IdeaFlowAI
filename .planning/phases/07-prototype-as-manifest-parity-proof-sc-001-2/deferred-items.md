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

## Pre-existing live-harness store breakage (discovered 07-05)

`tests/agents/live_harness.py` snapshots `engine._store.store` (line ~593) — a thin
artifact-store method that was DELETED in Phase 1B (05-07 / D2 removed the thin-store
artifact half). So `drive_engine_pipeline()` raises `AttributeError: 'ArtifactStore'
object has no attribute 'store'` BEFORE reaching any 07-05-touched code. Verified
pre-existing: the SAME failure reproduces on the base commit (engine.py/context.py/
live_harness.py reverted to HEAD~3) — it is NOT caused by this plan's L1-L13 deletion.

Affected (offline) — all fail at the `_store.store` snapshot, unrelated to L1-L13:
- `tests/agents/test_live_harness.py::TestEngineWorldOffline::*`
- `tests/agents/test_live_harness.py::TestEngineGate::*`
- `tests/agents/test_live_harness.py::TestClarifyAutoAnswerOffline::*`
- `tests/agents/test_live_contract.py::*`

07-05 DID update `live_harness.py` + `test_live_harness.py` for the deleted
`ALWAYS_CLARIFY` knob (swapped to a `compile_for_run` clarify.mode="off" wrapper) so
those would not add a NEW `AttributeError` on top of the pre-existing `.store` one —
but the `.store` snapshot itself is out of 07-05's scope (a 05-07 follow-up: repoint
the harness's store no-op to the typed `ScopedStore`/`ArtifactGraph` substrate, or drop
the obsolete `.store` stub). Surface to the phase owner for a separate triage.

## Pre-existing test-isolation pollution: test_strategies → characterization (discovered 07-07)

When `tests/agents/test_strategies.py` runs in the SAME pytest session BEFORE
`tests/agents/test_characterization_prototype.py` / `..._od_prototype.py`, the two
characterization snapshots FAIL. Root cause:
`test_strategies.py::test_task_loop_requests_html_skeleton_compaction_for_task_2`
mutates the process-global capability registry (`registry_mod.install()` +
`registry_mod._IMPLS[("compaction","html_skeleton")] = ...`); its `finally` only pops
the one key it added, leaving the `install()`-reseeded global registry in a state that
shifts the characterization event snapshot.

Verified PRE-EXISTING (NOT caused by 07-07): swapping `task_loop.py` +
`test_strategies.py` back to their pre-07-07 (HEAD~1 of the 07-07 branch) versions and
re-running the combined order reproduces the SAME single characterization failure. Both
files individually, and each characterization file in its own clean session, pass.

07-07's golden-safety is therefore intact — goldens are byte-unchanged and all 3
prototype characterization suites pass in a clean session (6 passed). The pollution is a
test-harness hygiene bug (the registry-install test needs a full save/restore of
`registry_mod._IMPLS`, or an autouse registry-reset fixture), out of 07-07's scope
(cluster B = dead-dual-impl deletion only). Surface to the phase owner for a separate triage.
