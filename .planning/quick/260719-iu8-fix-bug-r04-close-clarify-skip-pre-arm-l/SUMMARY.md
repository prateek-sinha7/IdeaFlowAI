# Quick 260719-iu8 — Fix BUG-R04: clarify pre-arm lost-wakeup race

## One-liner
Close the `clarify_engine.py` pre-`questionnaire_ready` lost-wakeup race so a
`POST /answers {responses:[], skip_clarification:true}` submitted BEFORE the
questionnaire is emitted still PROCEEDs instead of stalling the run at
`waiting_for_user` forever — a localized guard around the single `await
event.wait()`, byte/event-identical on every already-working path.

## The bug (verified, not re-derived)
`get_artifact_store()` is a module singleton, so the HTTP handler and the engine
share one `_resume_events[run_id]`. A client that POSTs the skip in the window
between the status flip to `waiting_for_user` (`engine.py:1870`) and the clarify
loop's `event.clear()` (`clarify_engine.py:284`) has its `event.set()`
(`store.py:81`) WIPED by that clear() → the subsequent `await event.wait()`
(`clarify_engine.py:299`) blocks with nothing set → the run sits forever. Only a
pre-`questionnaire_ready` submitter (a QA harness) hits it; the FE Skip button is
gated behind rendered questions, so real users cannot. Pre-existing (ISS-027), minor.

## The fix (primary option — clarify_engine.py only)
`backend/agents/execution_engine/clarify_engine.py`, inside `ClarifyEngine.run`:

- Added a local `last_consumed_responses: list[dict] | None = None` before the loop.
- Wrapped the single `await event.wait()` in a guard:
      pending = await self._store.get_questionnaire_responses(pipeline_run_id)
      if pending is None or pending is last_consumed_responses:
          await event.wait()
- Set `last_consumed_responses = responses` at the existing read site (before the
  `responses = responses or []` normalization), so the guard keys on the raw store
  object.

The existing read/merge/force_proceed seam below is UNCHANGED — the guard only
bypasses the wait; it does NOT duplicate the proceed logic (INV-12). The `:284`
clear, `store.py`, and `engine.py` are all untouched (the more-invasive arm-early
alternative was NOT taken).

### Why identity-tracking, not a naive `is not None`
A naive `if get_questionnaire_responses() is not None: skip wait` breaks
multi-round clarify in production: after round 1 the store keeps the round-1
responses, so on round 2 the guard would fire and re-read STALE round-1 answers
instead of awaiting the fresh round-2 submit. (The offline suite hides this — its
`ws` callback submits synchronously during the emit — but it is a real regression.)
Keying on object identity (`is last_consumed_responses`) fires ONLY for a genuinely
new (or pre-arm) submission and awaits normally when only a prior round's
already-consumed object remains. Each `set_questionnaire_responses` binds a fresh
list, so identity is the correct "a new submit landed" signal.

### Event-sequence identity (INV-3)
- Normal run, no pre-arm: `get_questionnaire_responses` is `None` at the guard →
  condition True → awaits exactly as before (byte-identical).
- Multi-round, no new submit yet: current object `is last_consumed_responses` →
  True → awaits as before.
- `questionnaire_ready` / `questionnaire_complete` emissions unchanged in all cases
  (the guard sits AFTER the `:287` emit, only gating the wait).

## Test (RED->GREEN, mandatory)
`backend/tests/unit/test_execution_engine.py::test_clarify_engine_prearm_skip_before_questionnaire_ready_proceeds`

Simulates a pre-`questionnaire_ready` submit: seeds the store with
`set_questionnaire_responses(run_id, [], skip_clarification=True)` BEFORE calling
`run()` (this stores `[]`+`force_proceed=True` AND sets the event, which the loop's
`:284` clear() then wipes). The `ws` callback records only — it does NOT re-submit,
so nothing re-arms the event. Uses `asyncio.wait_for(..., timeout=5.0)` so a
regression is a clean `TimeoutError`, not a hang. Asserts exactly ONE
`questionnaire_ready`, `questionnaire_complete` present, `execution_gate == "PROCEED"`.

- RED (proven): with the guard temporarily neutralized to the pre-fix unconditional
  `await event.wait()`, the test FAILS with `TimeoutError` after 5s (wiped event
  blocks forever) — captured, then the guard restored.
- GREEN: with the fix in place the test passes in 0.10s.

## Verification (offline)
- Goldens (INV-3 key guard), `SNAPSHOT_UPDATE` UNSET:
  `pytest tests/agents/test_characterization_*.py -q` -> 10 passed, byte/event-identical.
- Clarify unit + REST answers/cancel:
  `pytest tests/unit/test_execution_engine.py tests/unit/test_rest_answers_cancel.py -q`
  -> 23 passed (includes the new test).
- lint-imports: `/opt/homebrew/bin/lint-imports` -> 4 kept, 0 broken.

## Scope / invariants
- Two edits: one file for the fix (`clarify_engine.py`) + one test file. No
  `store.py`/`engine.py` change, no migration, no new WS event, no FE change.
- INV-1/SC-001: generic — no workflow-name literal. INV-12: reuses the existing
  read/merge/force_proceed seam. INV-13 untouched.
- Branch `feat/ui-2`, atomic commit, no trailer, NOT pushed. Live backend on port
  8000 untouched (offline in-process tests only).

## Self-Check: PASSED
- `clarify_engine.py` guard present (git diff verified).
- New test present and named as above.
- Goldens 10/10, unit 23/23, lint 4/0.
