---
phase: 49
plan: 01
subsystem: execution-engine / gate-resume
tags: [RESUME-17, restart-resume, gate-pendency, INV-12, IN-02, KAN-88]
requires:
  - "restore_non_terminal_runs three-way classifier (Phase 12)"
  - "derive_open_gate + gate vocabulary (Phase 29, chat_router)"
  - "_is_resumable_in_flight + branch-(b) 46-05 driver hooks"
  - "ArtifactStore HITL half (get_review_event/get_resume_event)"
provides:
  - "agents.capabilities.gate_pendency — the ONE shared open-gate derivation (kernel + app)"
  - "ArtifactStore.review_event_pending public accessor (IN-02)"
  - "branch-(a) fail→re-arm classification (A1) — compilable waiting_for_user never auto-failed"
  - "_rearm_gate_run driver skeleton (49-02/49-03 flesh it out)"
affects:
  - "app/api/chat_router.py, run_stream.py, run_commands.py (re-point at shared derivation)"
  - "agents/execution_engine/engine.py (branch a + new driver)"
tech-stack:
  added: []
  patterns:
    - "kernel-pure shared-home module (mirrors agents/capabilities/task_identity.py)"
    - "arm-then-classify fail-safe (recreate the waiter before leaving waiting_for_user)"
key-files:
  created:
    - backend/agents/capabilities/gate_pendency.py
  modified:
    - backend/app/api/chat_router.py
    - backend/app/api/run_stream.py
    - backend/agents/artifact_store/store.py
    - backend/app/api/run_commands.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/test_restart_resume.py
decisions:
  - "A3: shared derivation home = agents/capabilities/gate_pendency.py (import-clean both directions, lint-imports 4/0)"
  - "A1: STATUS decision gates on compilability alone; the re-arm DRIVER additionally requires a derivable open gate + _is_resumable_in_flight"
  - "branch (a) reads events under wr.workspace_id (mirrors _is_resumable_in_flight), not the recovered workspace"
metrics:
  duration: ~40m
  completed: 2026-07-19
  tasks: 2
  files_changed: 7
---

# Phase 49 Plan 01: Gate-Pendency Foundation + Branch-(a) Re-arm Summary

One-liner: A single shared `derive_open_gate` home (INV-12) + a public `review_event_pending` store accessor (IN-02) + the PINNED-A1 branch-(a) fail→re-arm classification that flips the KAN-88 anchor GREEN with zero test edits, plus the `_rearm_gate_run` driver skeleton 49-02/49-03 build on.

## What Was Built

**Task 1 — shared derivation + accessor (pure refactor, zero behavior change).**
- New `backend/agents/capabilities/gate_pendency.py`: a stdlib-only, kernel- and app-importable module owning `derive_open_gate` (lifted verbatim from `chat_router`) plus the generic gate vocabulary (`QUESTIONNAIRE_READY`/`REVIEW_GATE_READY`) and resolution frozensets (`QUESTIONNAIRE_RESOLUTIONS`/`REVIEW_RESOLUTIONS`). Mirrors the `task_identity.py` shared-home precedent and its import-scope guard.
- `chat_router.py`: `derive_open_gate` + the four gate constants now import from `gate_pendency` (re-bound to the historical private names) — callers byte-unchanged, `__all__` still re-exports `derive_open_gate`.
- `run_stream.py`: `_GATE_RESOLUTION_TYPES` re-points at `gate_pendency.REVIEW_RESOLUTIONS` (verified byte-identical); `_STREAM_TERMINAL_TYPES`/`_dangling_review_gate` unchanged.
- `store.py`: new public `ArtifactStore.review_event_pending(gate_key)` mirroring `get_review_event`'s `review:{gate_key}` key.
- `run_commands._gate_is_pending` now calls the accessor; the `store._resume_events` literal no longer appears in the app layer.

**Task 2 — branch-(a) re-arm classification (A1) + driver skeleton + KAN-88 flip.**
- `engine.py` imports the shared `derive_open_gate`.
- `restore_non_terminal_runs` branch (a) rewritten per PINNED A1: a **compilable** `waiting_for_user` run is NEVER auto-failed. `compile_for_run(wr.type)` raising ⇒ the byte-unchanged WR-05-clarify fail (the sole fail path for `waiting_for_user`). On compile success, the durable open gate is derived (owner+workspace-scoped read on `wr.workspace_id`, mirroring `_is_resumable_in_flight`); if a review/questionnaire gate is open AND `_is_resumable_in_flight` ⇒ **arm-then-classify**: recreate the store waiter (`get_review_event`/`get_resume_event` + `.clear()`) FIRST, then clone branch (b)'s 46-05 queue-before-task plumbing to spawn the DISTINCT `_rearm_gate_run` driver, leaving `wr.status` at `waiting_for_user`. Any exception in that block fail-safes to the WR-05 fail. A compilable row with no derivable open gate (the KAN-88 no-events case) is left parked, spawning nothing.
- New `_rearm_gate_run(run_id)` skeleton: review-open ⇒ delegates to `resume_run` (the 49-02 offset-override lands the true gate re-entry); clarify-open ⇒ no-op stub (49-03); WR-01 `_fire_resume_cleanup` + live-ectx unregister on every exit path. It is a NEW method precisely so branch (a) never spawns the KAN-88-spied `resume_run` directly.

## Deviations from Plan

### Adjustment (not a deviation from intent) — workspace scoping of the seed

The plan's Wave-0 sketch implied seeding the durable `review_gate_ready` under the run's `(owner, workspace=None)`. `run_events.workspace_id` is **NOT NULL**, so a null-workspace seed raises `IntegrityError`. Because branch (a) (per the plan) reads events under `wr.workspace_id` — exactly mirroring the shipped `_is_resumable_in_flight` — the two new gate tests seed the run row AND its `review_gate_ready` under the SAME real workspace (`_seed_workflow_run` gained an additive `workspace_id` param, default `None`, so every existing caller is byte-unchanged). This keeps branch (a) reading exactly what the plan specified (`wr.workspace_id`), with no engine change from the plan. Recorded here because it shaped the test seeding, not the production path.

No other deviations. No auto-fixed bugs; no architectural changes.

## Verification (delta vs 49-VALIDATION baseline)

| Suite | Baseline | After | Result |
|-------|----------|-------|--------|
| `test_restart_resume.py` | 24 / 1 | **28 / 0** | KAN-88 flips (the ONLY red→green) + 3 new green |
| `test_redo_gate_safety.py` | 4 / 3 | 4 / 3 | held (pre-existing `_fake_gate` kwarg drift) |
| `test_declared_gate_streaming.py` | 3 env-reds | 3 env-reds | held (Postgres-FK / static-gate precondition) |
| goldens (`SNAPSHOT_UPDATE` unset) | 10 / 10 | 10 / 10 | held (branch (a) dormant on scripted runs, INV-3) |
| `test_mechanical_router.py` | 28 / 0 | 28 / 0 | held (pure refactor) |
| `test_sse_stream.py` | 17 / 0 | 17 / 0 | held (pure refactor) |
| `test_rest_answers_cancel.py` | 9 / 0 | 9 / 0 | held |
| `test_banned_patterns.py` | 11 / 0 | 11 / 0 | held (no workflow-name literal) |
| `lint-imports` | 4 kept / 0 broken | 4 / 0 | held (gate_pendency is capabilities-tier) |

KAN-88 flip evidence: `test_waiting_for_user_run_is_rearmed_not_driven` passes with ZERO edits to the test — the compilable `sample_wave` row with no durable events derives `(None, None)` ⇒ parked (status stays `waiting_for_user`, `resume_run` not called).

## Success Criteria

- SC-1: branch (a) re-arms compilable runs; WR-05 stateless/legacy fail byte-unchanged; goldens 10/10 untouched. ✅
- SC-2: ONE shared `derive_open_gate` home (INV-12); `review_event_pending` accessor closes IN-02. ✅
- SC-5: KAN-88 anchor flips GREEN with zero test edits. ✅
- lint-imports 4/0; no new WS event types; endpoints byte-unchanged; no migration. ✅

## Known Stubs

- `_rearm_gate_run` is an intentional SKELETON for this plan: review-open delegates to `resume_run` (the true offset-override gate re-entry lands in **49-02**); clarify-open is a no-op stub (the clarify replay driver lands in **49-03**). Documented in the plan objective; not a blocking stub — the KAN-88 flip and the re-arm classification are complete and proven.

## Commits

- `b9524e27` refactor(49-01): shared open-gate derivation (A3) + public store accessor (IN-02)
- `f43ec885` feat(49-01): branch-(a) fail→re-arm classification (A1) + _rearm_gate_run + KAN-88 flip

## Self-Check: PASSED

- gate_pendency.py, test_restart_resume.py, 49-01-SUMMARY.md — all present on disk.
- Commits b9524e27, f43ec885 — both in git log.
