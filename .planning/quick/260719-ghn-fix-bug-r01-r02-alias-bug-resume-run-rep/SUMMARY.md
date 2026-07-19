# Quick 260719-ghn — Fix BUG-R01/R02: od_prototype id-alias empty-roster resume black-hole

**Branch:** feat/ui-2 · **Commit:** `e1866317` · **Date:** 2026-07-19 · **Status:** Verified (offline)

## One-liner

On restart, both resume re-arm drivers rebuilt the run's agent roster with the RAW
stored pipeline type (`get_pipeline_agents(wr.type)`); `od_prototype` is a routing
id-alias with no AGENT.md of its own, so the roster came back empty, the driver
bailed at the "empty agent list" check, and every restart od_prototype clarify-answer
(BUG-R01) and gate-approve (BUG-R02) black-holed. Fixed by resolving the id-alias
before the lookup in both drivers — exactly as the fresh path does.

## The fix (surgical — two one-line changes)

`backend/agents/execution_engine/engine.py`:

- **`resume_run` (line 7298, BUG-R02):** `get_pipeline_agents(pipeline_type)` -> `get_pipeline_agents(resolve_alias(pipeline_type))`
- **`_replay_clarify_run` (line 7601, BUG-R01):** `get_pipeline_agents(pipeline_type)` -> `get_pipeline_agents(resolve_alias(pipeline_type))`

`resolve_alias` is already module-level in engine.py (line 532), used by
`compile_for_run` at 563 — no import added. It is identity for real registry keys, so
`user_stories`/`app_builder`/`od_ppt`/`od_ppt_revision`/custom are byte-unchanged; only
the `od_prototype` non-self id-alias (and any future one) changes behavior. No refactor,
no PIPELINE_AGENTS fallback, no bail-message change.

**Grep confirmed only two resume-path sites need it.** Other `get_pipeline_agents(...)`
call sites in engine.py are correct/out-of-scope: `_execute_impl:1678` already keys off
the RESOLVED `compiled.id` (fresh path, the reference behavior); `_handle_revision:5752`
is fresh revision dispatch keyed on a derived real-key revision alias (not a restart
resume path).

## The test (RED->GREEN, closes the coverage hole)

Added two call-site regression tests to
`backend/tests/agents/test_restart_resume.py` (reusing `_ResumeHarness`,
`_seed_workflow_run`, `_seed_open_review_gate`, `_seed_open_questionnaire_gate`):

- `test_resume_run_od_prototype_alias_resolves_roster_not_bail` (BUG-R02)
- `test_replay_clarify_run_od_prototype_alias_resolves_roster_not_bail` (BUG-R01)

Each seeds a durable `type="od_prototype"` run parked at a gate and drives the **REAL**
`get_pipeline_agents` — the coverage hole every prior resume test misses by using the
always-non-empty `sample_wave` fixture (`_ResumeHarness._patched_gpa` delegates to the
real registry for any non-fixture type). Each spies the method immediately downstream of
the roster bail (`_compute_resume_offset` for resume_run; `_drive_resumed_stream` for
_replay_clarify_run) and asserts the driver reaches it — i.e. proceeds PAST the empty-
roster check instead of early-returning. Preconditions assert `get_pipeline_agents(
"od_prototype")==[]` and `get_pipeline_agents("prototype")==5` so the test provably
exercises the bug (not the fixture).

### RED (pre-fix HEAD) — both FAIL with the exact bug signature

    tests/agents/test_restart_resume.py FF
    E   AssertionError: resume_run must resolve od_prototype->prototype and reach the resume-offset re-entry; pre-fix it bails at the empty-agent-list check (BUG-R02 black hole)
    WARNING agents.execution_engine.engine:engine.py:7305 resume_run(odp-a1ca0908): empty agent list — nothing to resume
    E   AssertionError: _replay_clarify_run must resolve od_prototype->prototype and reach the replay drive; pre-fix it bails at the empty-agent-list check (BUG-R01 black hole)
    WARNING agents.execution_engine.engine:engine.py:7609 _replay_clarify_run(odc-2e902172): empty agent list — nothing to replay
    2 failed, 41 deselected in 0.40s

### GREEN (after fix) — both PASS

    2 passed, 41 deselected, 1 warning in 0.25s

## Verification (offline only)

| Check | Result |
|-------|--------|
| Characterization goldens (`test_characterization_*.py`, SNAPSHOT_UPDATE unset) | **10 passed** (byte/event-identical — fix dormant on scripted runs, INV-3) |
| `test_restart_resume.py` + `test_rest_resume.py` (incl. 2 new) | **52 passed** |
| `lint-imports` | **4 kept, 0 broken** |

Full backend suite intentionally NOT run (hangs offline — Chromium/Bedrock/Postgres-gated).
Live-Bedrock re-proof on od_prototype is owned by the orchestrator.

## Guardrails honored

- **INV-1 / SC-001:** `resolve_alias` is a generic data map (`_OD_ALIAS_BASE`) — no
  workflow-name literal enters the kernel branch (banned-pattern gate stays green).
- **INV-3:** identity for real registry keys -> scripted goldens 10/10 byte/event-identical.
- **INV-12:** reused the existing `resolve_alias` + the two existing drivers — no third
  driver, no new machinery.
- **INV-13:** deepagents runtime untouched. No migration, no WS event, no FE change.

## Self-Check: PASSED

- Commit `e1866317` present on feat/ui-2.
- Both engine one-line edits present (git diff = exactly 2 changed lines).
- Both new tests present and passing.
