---
phase: 46-per-task-substrate-cursor-live-layer-r1
plan: 05
subsystem: execution-engine / app-wiring
tags: [resume, live-ectx, milestone-cards, steering, DEF-43-03-1, RESUME-10, RESUME-11]

# Dependency graph
requires:
  - phase: 43-live-layer-narrator
    provides: "execute() DEF-43-03-1 card loop + MilestoneSink/LiveEctxRegister aliases + _RunEventSink.emit_milestone_card + the _LIVE_ECTX registry (register/unregister/_live_ectx_for_run) + persist_milestone_card"
  - phase: 46-per-task-substrate-cursor-live-layer-r1
    provides: "46-03 re-materialization + 46-04 skip-cursor establish the resume-tier hook region (_is_resume gated, after ectx construction, before dispatch loop) this plan re-uses"
provides:
  - "ExecutionEngine three default-None resume hook slots: _resume_milestone_sink / _resume_live_ectx_register / _resume_live_ectx_unregister (typed with MilestoneSink/LiveEctxRegister/LiveEctxUnregister aliases — no app import)"
  - "app/main.py restore-scan injection of the trio from run_commands (register_live_ectx/unregister_live_ectx) + chat_narrator (persist_milestone_card) — the SAME callables the SSE launch threads into execute()"
  - "resume_run live-wire: _RunEventSink(milestone_sink=...), manual next_seq allocator replacing itertools.count(start), DEF-43-03-1 card-advance loop (card pushed onto live_queue), live_ectx_register threaded into _execute_impl, guaranteed live_ectx_unregister in the finally"
  - "ExecutionEngine._redrain_steering_notes(ectx) — re-queues undrained durable chat_message rows (seq > max agent_input.seq) onto ectx.steering_notes at resume; called in the resume tier"
affects: [50-resume-endpoint (reuses the callback seam), RESUME-10, RESUME-11]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "App→engine callback injection for a bypassed wrapper: resume_run drives _execute_impl directly (not via execute()), so the wrapper's live-layer threading is replicated inside resume_run from app-injected default-None engine slots — kernel imports no app.* (lint-imports 4/0)"
    - "DEF-43-03-1 in a coroutine (not a generator): resume_run is fire-and-forget (returns None), so the milestone card is delivered live by pushing onto live_queue rather than yield — the seq-advance (next_seq = _card_seq+1) is identical to execute()"
    - "Durable-log-derived steering re-drain: seq-compare heuristic (chat_message.seq > max agent_input.seq) re-derives undrained one-shot notes from run_events, owner-scoped best-effort"

key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/app/main.py
    - backend/tests/agents/test_restart_resume.py

key-decisions:
  - "The milestone card in resume_run is delivered LIVE by pushing onto live_queue (not yield) — resume_run is a coroutine returning None, not an async generator like execute(); the durable persist + seq allocation happen inside emit_milestone_card exactly as execute() relies on, and next_seq advances past _card_seq identically"
  - "persist_milestone_card imported from its canonical home app.agents.chat_narrator (not the in-function import inside run_commands); register/unregister from app.api.run_commands — all app→app, kernel unaffected"
  - "_redrain_steering_notes called after the 46-04 skip-cursor block (still _is_resume-gated, before the enumerate dispatch loop) — the cursor/re-materialize resume-tier region, where ordered_agents/compiled/ectx are all in scope"
  - "Classification bound documented in the helper docstring + call-site comment: the durable chat_message row lacks channel/sticky, so the seq-heuristic ≈ undrained steering only within the in-flight-resume scope (branch b); sticky-on-resume loss is Phase-47 (uploads durability), not fixed here"

patterns-established:
  - "Replicating execute()'s live-layer threading inside a wrapper-bypassing driver via app-injected engine hooks (the Phase-50 /resume endpoint reuses this seam)"

requirements-completed: [RESUME-10, RESUME-11]

# Metrics
duration: 40min
completed: 2026-07-19
---

# Phase 46 Plan 05: Live-Layer & Steering Re-Drain on Resumed Runs Summary

**A resumed run is now a first-class LIVE run. `resume_run` bypassed `execute()`'s wrapper (it drives `_execute_impl` directly), so a resumed run never registered its live ectx, never emitted narrator milestone cards, and never unregistered on teardown — dead to steering, per-turn images, Concierge, and the narrator. This plan threads the SAME three live-layer callbacks the SSE launch path uses into `resume_run` via three default-None engine hooks injected app-side at the `app/main.py` restore scan (the kernel imports no `app.*`), replicates the `execute()` DEF-43-03-1 card-advance loop (manual `next_seq`, card drawn from the store's own allocator via `emit_milestone_card`, pushed onto the resume `live_queue`), threads `live_ectx_register` into `_execute_impl`, and guarantees `live_ectx_unregister` in the `finally` (no `_LIVE_ECTX` leak). It also re-queues undrained steering notes at resume (`_redrain_steering_notes`): durable `chat_message` rows whose `seq > max(agent_input.seq)` re-populate `ectx.steering_notes` (no-loss), while a drained note (`seq < last_input_seq`) is skipped (no-duplicate). Both features are dormant on a normal run — goldens 10/10.**

## Performance
- **Duration:** ~40 min
- **Completed:** 2026-07-19
- **Tasks:** 2 (TDD RED → GREEN)
- **Files modified:** 3 (0 created, 3 modified)

## What Shipped

### Task 1 — RESUME-10 resume_run live-wire (commit b58adf39)
- **Three engine ctor slots** (`engine.py`, beside `_resume_register_queue`): `self._resume_milestone_sink`, `self._resume_live_ectx_register`, `self._resume_live_ectx_unregister` (all default None, typed with the existing `MilestoneSink`/`LiveEctxRegister`/`LiveEctxUnregister` aliases).
- **main.py injection** (`app/main.py`, in the resume-bridge block): imports `register_live_ectx`/`unregister_live_ectx` from `app.api.run_commands` and `persist_milestone_card` from `app.agents.chat_narrator`, assigns the trio onto the engine instance beside the existing `_resume_register_queue`/`_task`/`_cleanup` hooks.
- **resume_run live-wire** (`engine.py`): `_RunEventSink(milestone_sink=self._resume_milestone_sink)`; `itertools.count(start)` → manual `next_seq = start`; per event `seq = next_seq; next_seq += 1`; after `sink.persist(...)`, `card_result = await sink.emit_milestone_card(event)` → if a card is created, `if _card_seq >= next_seq: next_seq = _card_seq + 1` and push `{"type":"chat_reply", "data":{**_card, "seq":_card_seq, "event_id":f"chat_reply:{event_id}"}}` onto `live_queue`; `live_ectx_register=self._resume_live_ectx_register` threaded into the `_execute_impl(...)` call (the `:1184` consumer registers when present); `live_ectx_unregister(run_id)` added to the existing `finally` beside `_fire_resume_cleanup`.
- **Test:** `test_resumed_run_is_wired_live_ectx_and_milestone_cards` — injects stub register/unregister/milestone_sink, seeds a durable tail (seq 1..N), drives `resume_run`, asserts the ectx was registered, a `chat_reply` card was emitted+persisted with an engine-counter seq > N (contiguous, unique — no collision), and unregister fired exactly once.

### Task 2 — RESUME-11 steering re-drain (commit 82c75e06)
- **`_redrain_steering_notes(self, ectx)`** (`engine.py`): owner-scoped best-effort read of `ectx.scoped_store.read_events(run_id, 0)`; `last_input_seq = max(seq of agent_input rows)`; for each `chat_message` row with `seq > last_input_seq` and non-empty `payload_json["text"]`, appends `{"text": text, "sticky": False}` to `ectx.steering_notes`. Called in the resume tier (after the 46-04 skip-cursor block, `_is_resume`-gated, before the dispatch loop). The existing consume-once drain (`:6603`) is untouched.
- **Tests:** `test_redrain_steering_notes_no_loss` (two undrained notes re-queued in order, sticky False; a drained + an empty-text row excluded) and `test_redrain_steering_notes_no_duplicate` (a note drained pre-crash, `seq < last_input_seq`, is not re-queued).

## RED → GREEN Evidence
- **RESUME-10 RED (HEAD):** `test_resumed_run_is_wired_live_ectx_and_milestone_cards` → `AssertionError: assert 'lw-…' in {}` (register never threaded; no card; no unregister). **GREEN** after the live-wire.
- **RESUME-11 RED (HEAD):** both steering tests → `AttributeError: 'ExecutionEngine' object has no attribute '_redrain_steering_notes'`. **GREEN** after adding the helper + resume-tier call.

## Deviations from Plan
None — plan executed exactly as written. The one interpretation call: the plan text said "yield" the card (mirroring `execute()`), but `resume_run` is a coroutine (`-> None`), not an async generator, so the card is delivered live by pushing onto `live_queue` (the resume path's live-delivery mechanism) — the durable persist + seq allocation are unchanged, so this matches the plan's `artifacts_produced` note "yield `chat_reply` ... also push to `live_queue`" for the resume context. Documented as a key-decision, not a scope change.

## Verification (verify-by-delta)
- `test_restart_resume.py`: **16 passed, 1 failed** — the sole fail is `test_waiting_for_user_run_is_rearmed_not_driven` (KAN-88 / Phase-49 anchor, left RED by design). Pre-phase-plan baseline was 13 passed + KAN-88; +3 new greens (1 live-wire + 2 steering).
- Goldens `tests/agents/test_characterization_*.py`: **10 passed** (SNAPSHOT_UPDATE unset — both features dormant on scripted runs).
- `lint-imports`: **Contracts: 4 kept, 0 broken** (the engine→app boundary holds — callbacks arrive as generic injected callables).
- INV-1: `grep -cE 'pipeline_type ==|spec\.id ==' engine.py` → **0**. INV-12 single dispatch loop: `grep -c 'for i, spec in enumerate(ordered_agents)'` → **1**.
- `itertools.count(start)` in engine.py → **0**; `append_event_next_seq` → **1** (a comment only; never called for engine-emitted events — 0024 constraint honored).
- Wave gate sweep (restart_resume + wave_scheduler + subagent_runs + fanout + fanout_cancel + sc001_fanout + per_task_capture + banned_patterns): **89 passed, 1 failed** (KAN-88 only).
- SSE (`tests/unit/test_sse_stream.py` + `tests/agents/test_attach_replay_matrix.py`): **28 passed, 1 failed** — the sole fail is the PRE-EXISTING `TestMidStreamResume::test_last_event_id_header_resumes_over_http` (`assert '3' in ['2']`), unchanged by this plan.
- Migrations (`tests/unit/test_migrations.py`): **5 passed, 2 failed** — the two fails are the PRE-EXISTING stale single-head asserts (`0016`/`0023` expecting head to equal their own revision; head is now `0026` from 46-01), unchanged.

## Known Stubs
None. Both features are wired end-to-end (main.py injection → engine hooks → resume_run/resume tier). The Phase-50 `POST /resume` endpoint reuses this same callback seam (build now, consume in 50) — that is the plan's declared forward-shape, not a stub.

## Threat Flags
None. No new network endpoint, auth path, or schema change. `register_live_ectx` stays idempotent-by-overwrite keyed on `run_id`; the steering read is `ectx.scoped_store` owner-scoped; the classification bound is documented (in-flight-resume scope only). All mitigations in the plan's threat register (T-46-05-01..05) are in place.

## Self-Check: PASSED
- Commit b58adf39 (Task 1) — FOUND in git log.
- Commit 82c75e06 (Task 2) — FOUND in git log.
- `backend/agents/execution_engine/engine.py` contains `_resume_live_ectx_register` and `_redrain_steering_notes` — verified.
- `backend/app/main.py` contains the trio injection — verified.
