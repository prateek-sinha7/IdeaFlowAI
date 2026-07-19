---
phase: 49
plan: 02
subsystem: execution-engine / gate-resume
tags: [RESUME-17, restart-resume, review-gate, gate-reentry, INV-12, P23-replay, A2]
requires:
  - "49-01: gate_pendency.derive_open_gate shared home + _rearm_gate_run driver (delegates review-open to resume_run)"
  - "_first_incomplete_step produced-disjunct classifier (Phase 12)"
  - "_run_agent pending_revision_output short-circuit + the post-stream five-action gate consumer (Phase 23/27)"
  - "_latest_typed_content / _latest_typed_ref_id max-version resolvers (F5 / RESUME-15)"
  - "read_gate_events / record_gate_event runner audit half (Phase 23 / D-03)"
provides:
  - "open-gate offset override in _first_incomplete_step (re-enter the gated step, not skip past)"
  - "ectx.gate_reentry consume-once sentinel + skip-model gate re-entry in _run_agent"
  - "_seed_gate_reentry_attempts — fail-safe-HIGH redo/spec-revision continuation from durable evidence"
  - "A2: best-effort update_specs gate_events audit row (symmetric with redo)"
affects:
  - "agents/execution_engine/engine.py (_first_incomplete_step, _execute_impl _is_resume block, _run_agent loop, _gate_update_specs consumer)"
  - "restart-resume review-gate path: _rearm_gate_run → resume_run now truly re-enters AT the gate"
tech-stack:
  added: []
  patterns:
    - "skip-model gate re-entry via a consume-once ectx sentinel (clones the pending_revision_output structure)"
    - "fail-safe-HIGH thread-id continuation from MAX of two durable signals (audit rows + artifact versions)"
key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/test_restart_resume.py
decisions:
  - "The gate_reentry consumer clones the POST-STREAM five-action consumer (not the pending_revision_output path) — the latter's update_specs branch only re-seeds+breaks and would NEVER fire the sub-pipeline, violating SC-3"
  - "redo_attempt = max(gate_events_redo_count, version_count-1); spec_revision_attempt = max(gate_events_update_specs_count, version_count) — MAX over-estimates (safe: a fresh unused thread id), never under-estimates (collides → P23 replay)"
  - "A2 audit row added to BOTH the post-stream and the re-entry _gate_update_specs consumers so the spec-revision count is durable-symmetric with redo"
  - "Single atomic implementation commit (both tasks) — Task 1's re-entry consumer calls Task 2's seed helper and Task 2's redo-numbering test drives Task 1's consumer, so the two are mutually coupled; splitting would produce a broken (non-green) intermediate commit"
metrics:
  duration: ~55m
  completed: 2026-07-19
  tasks: 2
  files_changed: 2
---

# Phase 49 Plan 02: Review-Gate Re-Entry at the Gate Phase Summary

One-liner: A restart-parked review gate now SURVIVES the restart — the open-gate override makes `_first_incomplete_step` re-enter the gated step (instead of skipping past it), a consume-once `gate_reentry` sentinel skips the model call and reconstructs the reviewed output from the persisted max-version ref (WR-02), and a clone of the post-stream five-action consumer makes approve/reject/edit/redo/update_specs behave identically post-restart with `:redo{N}` numbering that continues past pre-restart attempts (the P23 replay class closed).

## What Was Built

**Task 1 — open-gate override + gate_reentry sentinel + skip-model re-entry (all five actions).**
- `_first_incomplete_step` (engine.py): the run's durable `run_events` are now captured ONCE into `durable_rows`; after `produced_agents` is built, an open-gate override calls `derive_open_gate(durable_rows)` and, when a review gate is open, parses the target agent out of `gate_key = f"{run}:{agent_id}"` and RETURNS the gated step index — beating the non-wave produced-disjunct that would otherwise skip the parked gate. Generic keying only (zero name literals). No-op when `derive_open_gate` → `(None, None)`.
- `_execute_impl` `_is_resume` block (engine.py): after hydrate/re-materialization/steering-redrain, when the durable events show a review gate whose target matches `ordered_agents[_resume_from]`, arm a consume-once `ectx.gate_reentry = {agent_id, artifact_kind, gate_key}` sentinel (best-effort; a read failure fail-safes to a normal model-running resume).
- `_run_agent` `while True:` (engine.py): a sibling short-circuit at the top of the loop (alongside `pending_revision_output`) fires ONCE for the gated step — reconstructs `output = _latest_typed_content(ectx, spec.id)`, re-seeds `ectx.last_streamed = output` (WR-02), ensures a `results[-1]` entry, seeds `redo_attempt`/`spec_revision_attempt` from durable evidence, clears the sentinel (consume-once), and enters `_run_review_gate` + the full five-branch consumer + `else: return` + `continue`. Skips `agent_start`/context-compose/`astream_events` entirely.
- `_rearm_gate_run`'s review path (already delegating to `resume_run` from 49-01) now truly re-enters AT the gate: the offset lands at k, the sentinel fires, the gate re-opens and parks on `await event.wait()`.

**Task 2 — redo/update_specs continuation seeding (A2) + audit symmetry.**
- `_seed_gate_reentry_attempts(ectx, spec) -> (redo_attempt, spec_revision_attempt)` (engine.py): reads the durable `gate_events` (via `ctx.runner.read_gate_events`, filtered `step==spec.id, gate=="human", outcome in {redo, update_specs}`) AND the durable artifact-version count for the agent+kind, then seeds fail-safe HIGH: `redo_attempt = max(redo_rows, versions-1)`, `spec_revision_attempt = max(update_specs_rows, versions)`. Any read failure degrades to the version signal (never a bare 0 that could collide).
- A2 audit row: the inline `_gate_update_specs` consumer (post-stream AND the new re-entry clone) now writes a best-effort `record_gate_event(spec.id, "human", "update_specs", {...})` — symmetric with the `_gate_redo` audit, dormant on goldens, never aborts a run — so a post-restart `spec_revision_attempt` is durable-derivable.

## Deviations from Plan

### [Rule 1 — Correctness] The re-entry consumer clones the POST-STREAM consumer, not the pending_revision_output path

- **Found during:** Task 1 (designing the update_specs branch).
- **Issue:** The plan's `<action>` says clone the `pending_revision_output` short-circuit "VERBATIM". But that path's `_gate_update_specs` branch only re-seeds `spec_revision_pending_output` and `break`s — it does NOT run `_run_spec_revision_sub_pipeline` (it IS the *re-open-after-sub-pipeline* stage). Cloning it would mean a post-restart `update_specs` NEVER fires the sub-pipeline — directly violating the plan's own success criterion "update_specs fires the sub-pipeline (SC-3)" and must_haves truth.
- **Fix:** The `gate_reentry` short-circuit clones the FULL post-stream inline consumer (engine.py `:3842-3999`): reject cancels; edit dual-writes with the html_file-aware location + `derived_from` lineage; redo does the full audit + `results.pop` + `redo_derived_from`; update_specs FIRES the sub-pipeline, collects `new_analysis_output`, sets `spec_revision_pending_output`, breaks. This makes all five actions truly identical to a live gate.
- **Files modified:** backend/agents/execution_engine/engine.py
- **Commit:** 5fab2136

No auto-fixed bugs beyond this design reconciliation; no architectural changes; no auth gates.

## Verification (delta vs 49-VALIDATION / 49-01 baseline; offline, python3.11, `cd backend/`)

| Suite | Baseline | After | Result |
|-------|----------|-------|--------|
| `test_restart_resume.py` | 28 / 0 | **37 / 0** | held + 9 new green (override + no-op + 5 actions + redo-numbering + A2 audit) |
| `test_redo_gate_safety.py` | 4 / 3 | 4 / 3 | held (pre-existing `_fake_gate` KAN-101 kwarg drift — do NOT fix) |
| `test_sse_stream.py` | 17 / 0 | 17 / 0 | held (D-14g re-emit + CR-01 dedup unperturbed) |
| `test_banned_patterns.py` | 11 / 0 | 11 / 0 | held (generic gate_key parse; INV-1 grep 0; **single dispatch-loop enumerate-pin = 1**) |
| `test_mechanical_router.py` | 28 / 0 | 28 / 0 | held |
| `test_rest_answers_cancel.py` | 9 / 0 | 9 / 0 | held |
| goldens (`test_characterization_*`) | 10 / 10 | 10 / 10 | held (override no-ops + sentinel unset on scripted runs — INV-3) |
| `test_declared_gate_streaming.py` | 3 env-red | 3 env-red | held (`sqlite3.IntegrityError FOREIGN KEY` on run_events persist — Postgres-gated, A4; confirmed same env root) |
| `test_approve_review_ownership.py` | 6 / 0 | 6 / 0 | held |
| `test_concierge_escalation.py` | 13 / 0 | 13 / 0 | held |
| `test_clarify_json_parse.py` | 11 / 0 | 11 / 0 | held |
| `lint-imports` | 4 / 0 | 4 / 0 | held |

Five-action proof (offline, `test_gate_reentry_all_five_actions_post_restart[<action>]`): for EACH of approve/reject/edit/redo/update_specs the gate reviews the reconstructed `PERSISTED GATED OUTPUT` (WR-02) with the model call skipped, and the action behaves identically to a live gate — approve continues; reject → `pipeline_cancelled`; edit → a new versioned ref with `derived_from` == the superseded ref; redo → a fresh `:redo{N}` checkpoint thread; update_specs → the sub-pipeline fires + the gate re-opens with the new analysis output. Redo-numbering (`test_gate_reentry_redo_numbering_continues_past_pre_restart_redos`): 2 durable redo `gate_events` rows ⇒ the post-restart redo threads exactly `{run}:{agent}:redo3` (strictly past the pre-restart N).

## Success Criteria

- SC-3: review re-entry AT the gate phase; output reconstructed from the persisted ref; `ectx.last_streamed` re-seeded; ALL five actions identical post-restart; fresh `:redo{N}` threads (continuation from durable evidence); update_specs sub-pipeline fires. ✅
- INV-12: no parallel gate machine — one offset override + one sentinel reuse the shipped `_run_review_gate` + five-action consumer; single dispatch loop (enumerate-pin 1). ✅
- INV-1/SC-001: generic gate_key parse + generic event vocabulary; zero workflow/agent-name literals (banned_patterns 11/0). ✅
- INV-3: dormant on scripted runs (goldens 10/10; sentinel unset + override no-op). ✅

## Known Stubs

None. The review-gate re-entry is complete end-to-end for the inline gate path. (Clarify-gate re-arm remains 49-03; the declared-path non-inline gate redo is the standing P23 v1 fence, out of scope.)

## Commits

- `5fab2136` feat(49-02): review-gate re-entry at the gate phase (RESUME-17) — override + gate_reentry sentinel + five-action consumer + redo/update_specs continuation (A2) + tests

## Self-Check: PASSED

- backend/agents/execution_engine/engine.py, backend/tests/agents/test_restart_resume.py, 49-02-SUMMARY.md — all present on disk.
- Commit 5fab2136 — in git log.
- Post-commit deletion guard: no tracked files deleted.
