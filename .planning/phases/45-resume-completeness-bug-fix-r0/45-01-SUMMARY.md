---
phase: 45-resume-completeness-bug-fix-r0
plan: 01
subsystem: engine (resume-tier completeness classification)
status: complete
tags: [resume, task_loop, completeness, data-loss-fix, RESUME-05]
requirements: [RESUME-05]
commits:
  - 2ac092b3  # test(45-01): RED partial task_loop build re-enters + companion
  - 73d232f7  # fix(45-01): strategy-conditional task_loop completeness
provides:
  - _first_incomplete_step task_loop branch (distinct-task_id count vs parsed expected_total, fail-safe to INCOMPLETE)
  - test_partial_task_loop_build_reenters_step_not_skipped (RED->GREEN regression)
  - test_completed_task_loop_build_stays_complete_no_rerun (over-correction guard)
requires:
  - ectx.scoped_store.tree(run_id) durable artifact_refs read
  - _CAPABILITY_REGISTRY.resolve("task_parser", parser_name)
affects:
  - backend/agents/execution_engine/engine.py (_first_incomplete_step only)
  - backend/tests/agents/test_restart_resume.py (2 appended tests)
key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/test_restart_resume.py
metrics:
  duration_min: 35
  tasks: 2
  files_modified: 2
  completed: 2026-07-19
---

# Phase 45 Plan 01: Resume Completeness Bug Fix [R0] Summary

Made `_first_incomplete_step` completeness strategy-conditional so a `task_loop` build interrupted mid-flight (task N of M, N<M) re-enters its build step on resume instead of being silently skipped — closing a live deliverable-truncation data-loss bug (RESUME-05), proven RED->GREEN.

## Accomplishments

- **Root cause fixed:** For `strategy == "task_loop"`, completeness is now `distinct(task_id for durable artifact_refs where producer_agent == agent_id) >= expected_total` (or a durable `step_completed`/`step_reused` event), where `expected_total = max(len(parser.parse(plan_content)), 1)` — the plan content re-read from the DECLARED `step.task_source.source_step` durable ref and parsed with the DECLARED `step.task_source.parser` (fallback `"heading_tasks"`), mirroring `task_loop.run`'s own derivation. The old produced-agent membership at `engine.py:6002` could not tell a partial build from a complete one because `persist_task_html` dual-writes an `html_file` ref with `producer_agent=<build agent>` from task 1 onward.
- **`single_shot` and `wave_scheduler` branches byte-unchanged** — the new branch sits between the `wave_scheduler` branch and the `:6002` disjunct; the single_shot disjunct is untouched.
- **Fail-safe direction is INCOMPLETE (re-run), never skip:** no store / undeclared `source_step` / missing plan content / parser-resolve failure / any exception -> `return i` (re-enter). No workflow/agent-id literal added (INV-1); `source_step` is read from the declaration, never hard-coded.
- **Single durable read:** `store.tree(run_id)` rows are materialized once into a local `tree_rows`; `produced_agents`, the per-task distinct count, and the source_step plan content all read from it (behavior-neutral, no second round-trip). Local variable only — no per-run engine state (INV-2).
- **Two offline regression tests appended** to `test_restart_resume.py` using the seed-durable-then-classify idiom (`pre_store.write_ref(ArtifactRef(...))` of the real graph dataclass; real `Step`/`TaskSource`; direct `engine._first_incomplete_step(...)` call). The `_Step` stub and the KAN-88 anchor test were not touched.

## Completeness-signal mechanism used

Count-based, strategy-conditional (RESEARCH recommendation (b)):

- complete ⟺ `agent_id in completed_step_events` **OR** `distinct_done >= expected_total`
- `expected_total = max(len(parser.parse(plan_content)), 1)` — parser resolved via `_CAPABILITY_REGISTRY.resolve("task_parser", parser_name)`; `plan_content` = the `.content` of the latest `tree_rows` entry whose `.producer_agent == source_step`.
- `distinct_done = len({r.task_id for r in tree_rows if r.producer_agent == agent_id and r.task_id is not None})` — a SET of task_ids (distinct), so fix-loop re-persists of the same task_id do not over-count.
- else `return i` (INCOMPLETE / re-enter). All derivation wrapped `try/except -> return i` (fail-safe).

**Inline vs helper:** the logic was **inlined** as a `strategy == "task_loop"` branch inside `_first_incomplete_step` (no separate helper method). No new top-level/module symbol was introduced.

## Observed RED (HEAD, pre-fix)

`test_partial_task_loop_build_reenters_step_not_skipped` on HEAD:

```
tests/agents/test_restart_resume.py:1072: in test_partial_task_loop_build_reenters_step_not_skipped
    assert idx == build_index, (
E   AssertionError: a partial task_loop build (1 of 3 tasks) must re-enter its step (idx == 1); got idx=2 (HEAD silently skips it via the produced_agents membership at :6002 → deliverable truncation)
E   assert 2 == 1
==================== 1 failed, 1 warning in 0.26s ====================
```

Companion `test_completed_task_loop_build_stays_complete_no_rerun` PASSED on HEAD (a fully-complete build was already classified complete). Full suite on HEAD after Task 1: **7 passed, 2 failed** (the new RED + the KAN-88 anchor) — no other test flipped.

## GREEN re-run (post-fix)

Both new tests + full restart_resume suite:

```
tests/agents/test_restart_resume.py::test_partial_task_loop_build_reenters_step_not_skipped PASSED
tests/agents/test_restart_resume.py::test_completed_task_loop_build_stays_complete_no_rerun PASSED
...
==================== 1 failed, 8 passed, 1 warning in 1.18s ====================
```

The single remaining failure is ONLY `test_waiting_for_user_run_is_rearmed_not_driven` (the KAN-88 / Phase 49 anchor, unchanged — verify-by-delta against the 6-pass/1-fail pre-phase baseline).

## Gate outputs

- **Combined full-for-phase battery** (restart_resume + 5 characterization goldens + banned_patterns + migration_ledger, `SNAPSHOT_UPDATE` unset): `1 failed, 52 passed, 7 skipped` — the 1 failed is the KAN-88 anchor only.
- **Characterization goldens alone** (SNAPSHOT_UPDATE unset): `10 passed` (INV-3 dormancy proven).
- **banned_patterns + migration_ledger:** `34 passed, 7 skipped` (green).
- **`/opt/homebrew/bin/lint-imports`:** `Contracts: 4 kept, 0 broken.`
- **INV-1 grep** `grep -cE 'pipeline_type ==|spec\.id ==' engine.py`: `0`.
- **INV-12 grep** `grep -c 'for i, spec in enumerate(ordered_agents)' engine.py`: `1`.
- **engine.py diff:** 58 insertions, 1 deletion, confined to `_first_incomplete_step`; no new `def`/`yield`/`append_event`.

## Decisions Made

- **Inlined the branch** (not extracted to `_task_granular_step_complete`) — the derivation is short and reads only durable rows already materialized in the function; a helper would add indirection without removing per-run state (there is none).
- **`expected_total = max(len(tasks), 1)`** to mirror the strategy's 0-task -> run-once fallback, so a genuinely-complete 0-task build still classifies complete.
- **Kept `completed_step_events` as an OR-condition** for task_loop (retry/`step_reused` steps remain complete) — the count is an additional path, not a replacement.
- **No fallback to a hard-coded `"prototype-plan"` source_step** (INV-1) — an undeclared `source_step` fail-safes to INCOMPLETE.

## Deviations

None — the plan executed exactly as written. One implementation note: `_build_partial_build_fixture` was made `async` (and awaited from both tests) so the durable `write_ref` seeding runs inside pytest-asyncio's already-running event loop rather than via `run_until_complete` (which would raise inside a running loop). This is a test-harness mechanics detail, not a plan deviation.

## Residual (accepted, documented per T-45-03)

A genuinely-completed legacy build whose source_step plan artifact is missing/underivable will re-run on each restart (correct-but-wasteful, bounded, rare). Accepted per the locked "correct-but-wasteful is acceptable; skip-on-uncertainty is forbidden" contract. Further bounded by `_compute_resume_offset`'s outer `try/except -> return 0`.

## Files Modified

- `backend/agents/execution_engine/engine.py` — `_first_incomplete_step`: `tree_rows` materialization + the `task_loop` completeness branch (58 insertions, 1 deletion).
- `backend/tests/agents/test_restart_resume.py` — appended `_pb_hash`, `_IdSpec`, `_build_partial_build_fixture`, and the 2 regression tests (174 insertions, 0 deletions).

## Files Created

None.

## Self-Check: PASSED

- FOUND: `.planning/phases/45-resume-completeness-bug-fix-r0/45-01-SUMMARY.md`
- FOUND: `backend/agents/execution_engine/engine.py`
- FOUND: `backend/tests/agents/test_restart_resume.py`
- FOUND commit: `2ac092b3` (test) / `73d232f7` (fix)
