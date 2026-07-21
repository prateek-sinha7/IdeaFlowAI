---
phase: 46-per-task-substrate-cursor-live-layer-r1
verified: 2026-07-19T00:00:00Z
status: passed
score: 8/8 success criteria verified
verifier: Claude (gsd-verifier, Opus 4.8)
re_verification: false
deferred:
  - truth: "Live crash→resume ladder — steering/Concierge/cards on a resumed run, isolated-write fan-out, real merge (RESUME-08/09/10 on live Bedrock)"
    addressed_in: "Milestone v3.0 end (consolidated live-Bedrock pass, orchestrator-owned)"
    evidence: "46-VALIDATION.md Manual-Only section + 46-CONTEXT execution constraints: 'offline gates bind phase completion; NO live Bedrock in executors; milestone-end live pass covers the ladder'; project defer-live-verification convention. Offline harness runs shared_read (no isolated-write redirection) by design (register 11-05)."
---

# Phase 46: Per-Task Substrate, Cursor & Live-Layer Re-Registration [R1] — Verification Report

**Phase Goal:** Sub-agent / fan-out / sequential-task interruptions become resumable at task/worker granularity, and resumed runs are first-class LIVE runs.
**Verified:** 2026-07-19 (offline battery + code read, HEAD `e437bef6`, branch `feat/ui-2`)
**Status:** passed
**Re-verification:** No — initial verification

This is a goal-backward verification. I re-ran every gate in my own process, read the actual diffs across the phase commit range (`bac2a16c` → `e437bef6`), and scored each ROADMAP success criterion against observed code — SUMMARY claims were treated as hypotheses to falsify, not evidence.

## Goal Achievement — 8 ROADMAP Success Criteria

| # | Criterion | Status | Evidence (observed) |
|---|-----------|--------|---------------------|
| 1 | Additive migration (head after 0025): nullable `task_id`+`worker_index` on `subagent_runs`, reversible single-head, rows written at SPAWN | ✓ VERIFIED | `0026_subagent_task_identity.py`: `down_revision="0025"`, `batch_alter_table.add_column` of two nullable cols, reverse-order `downgrade`. Reversibility PROVEN by me: `alembic upgrade 0026 → downgrade 0025 → upgrade 0026` all exit 0 on a fresh SQLite. ORM `SubagentRun.task_id`/`worker_index` nullable. Stamped at SPAWN: `fanout.py:378` `record_subagent_run(status="running", worker_index=idx, task_id=worker.get("task_id"))` — written BEFORE `run_worker` (line 401), i.e. before the crash window. `wave_scheduler.py:270` request build carries `task_id=t.id`. |
| 2 | GENERIC per-task capture (Q7): every file a task wrote captured per task; `html_file` literal handled/documented; multi-file proven; byte-neutral on prototype | ✓ VERIFIED | `kernel_services.py:1321` `persist_task_html` — Branch 1 = declared file → `html_file` dual-write (byte-identical, `task_id=str(task_num)`); Branch 2 = sibling walk → `file_bundle` durable rows, dedup by `content_hash`, `.uploads/`+`PLANNER.md` excluded via `_collect_deliverable_relpaths`/`_DELIVERABLE_EXCLUDE`, event-free/best-effort. Branch 2 is **durable-store-only** (`store.write_ref`, `force_db_version=True`) — the in-memory `ectx.artifacts` graph is NOT touched on first runs (I confirmed: no `_dual_write_artifact` in branch 2), so `_latest_typed_content` stays byte-identical. `test_per_task_capture.py` 4 passed (multi-file siblings, `.uploads/` exclusion, dedup, prototype byte-neutrality). Goldens 10/10. |
| 3 | Durable→disk re-materialization from `artifact_refs`, never git | ✓ VERIFIED | `engine.py:5975` `_rematerialize_artifacts_to_disk`: owner-scoped `store.tree(run_id)` read (default-deny), per-`location` `max(version)` wins, filtered to file-backed kinds `{html_file,file_bundle,deliverable}`, `.uploads/` dropped, `sandbox.write` (traversal-proof `path_for`), best-effort degrade. Reconstructed from `artifact_refs` only — no git read anywhere in the method. Wired at `:1383` gated on `_is_resume`. |
| 4 | Mid-wave merge re-entry: fragments re-materialized + merge re-run for the in-flight wave before remaining dispatch | ✓ VERIFIED | Fragments persist as `file_bundle` (re-materialized by SC-3). `wave_runs.status` is the merged/unmerged discriminator (`completed` ⇒ merge ran, skip wave; `running`/absent ⇒ in-flight, re-run). The EXISTING `run_fanout`→`_merge_fragments` re-runs over recovered fragments — no second merge impl (INV-12 enumerate-pin = 1). `test_midwave_merge_reentry_rematerializes_fragments` GREEN (in restart_resume 16-passed set). |
| 5 | Per-worker/per-task identity skip, kernel-computed, agent-never-decides | ✓ VERIFIED | `engine.py:6198` `_compute_resume_completed_task_ids` — KERNEL reads owner-scoped `store.tree`+`read_subagent_runs`, returns `{agent_id: {task_id}}` (task_loop: distinct `producer_agent` task_ids; wave: `status=="complete"` task_ids). Zero name literals (keys on `strategy`/`producer_agent`/`task_id`/`status`; INV-1 grep = 0). Stamped on `ectx.resume_completed_task_ids` (`_is_resume`-gated, best-effort→None). Strategies read via `getattr`: `task_loop.py:255` skips `str(task_num)`; `wave_scheduler.py:264` filters `str(t.id)`. Identity-based — NOT prefix-by-count. Fail-safe = re-run (per-step try/except leaves step out; only `complete` workers skipped). Agent receives completed work as injected context (unchanged). `test_kernel_computes_resume_completed_task_ids_cursor` + 2 skip tests GREEN. |
| 6 | Resumed runs are live: both paths thread `register_live_ectx` (+finally unregister) + `milestone_sink`; card `seq` from engine counter; no engine→app import | ✓ VERIFIED | `engine.py:6531` `resume_run`: `_RunEventSink(milestone_sink=self._resume_milestone_sink)`; manual `next_seq=start` (NOT `itertools.count(start)` — grep = 0); after `emit_milestone_card`, `if _card_seq >= next_seq: next_seq = _card_seq+1` (card seq from store allocator/engine counter, advances past collision — DEF-43-03-1); `live_ectx_register` threaded into `_execute_impl` (:6550); **unregister GUARANTEED in `finally` (:6624)** — past the broad `except` (:6601), gated only on hook non-None, so a mid-drive exception cannot skip it. Callbacks are injected app-side at `app/main.py:150-154` (`register_live_ectx`/`unregister_live_ectx` from run_commands, `persist_milestone_card` from chat_narrator) onto the SAME engine instance that runs `restore_non_terminal_runs()` (:155). engine.py imports NONE of these (matches appear only in comments); lint-imports 4/0. `test_resumed_run_is_wired_live_ectx_and_milestone_cards` GREEN. |
| 7 | Steering re-drain: undrained durable steering re-queued onto `ectx.steering_notes` at resume | ✓ VERIFIED | `engine.py:6274` `_redrain_steering_notes`: owner-scoped `read_events`, `last_input_seq = max(agent_input.seq)`; a `chat_message` with `seq > last_input_seq` + non-empty text → appended `{"text",sticky:False}` (no-loss); a drained note (`seq <= last_input_seq`) skipped (no-duplicate). Fail-safe = leave `steering_notes` untouched on no-store/read-error. Classification bound honestly documented in the docstring (in-flight-resume/branch-b scope). Called at `:2107` (`_is_resume`-gated). `test_redrain_steering_notes_no_loss` + `..._no_duplicate` GREEN. |
| 8 | Gates: 5 goldens byte/event-identical · lint 4/0 · banned-pattern clean · restart-harness RED→GREEN | ✓ VERIFIED | I ran all: goldens 10/10 (`SNAPSHOT_UPDATE` unset); lint-imports 4 kept/0 broken; banned_patterns 11 passed; restart_resume 16 passed / 1 failed (KAN-88 the SOLE red, by design). INV-1=0, INV-12=1, `itertools.count(start)`=0. |

**Score: 8/8 truths verified.**

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `alembic/versions/0026_subagent_task_identity.py` | additive nullable cols, reversible | ✓ VERIFIED | 44 lines; batch add/drop; round-trip green |
| `app/models/subagent_run.py` | ORM `task_id`+`worker_index` nullable | ✓ VERIFIED | lines 44-45, nullable |
| `agents/execution_engine/fanout.py` | spawn stamping | ✓ VERIFIED | `_select_workers:123` preserve, `_run_one:378` stamp at spawn |
| `agents/capabilities/strategies/wave_scheduler.py` | request `task_id` + per-worker skip | ✓ VERIFIED | :270 stamp, :264 identity filter |
| `agents/execution_engine/kernel_services.py` | generic capture at seam | ✓ VERIFIED | :1321, branch-2 store-only |
| `agents/execution_engine/engine.py` | rematerialize + cursor compute + resume live-wire + steering redrain | ✓ VERIFIED | :5975 / :6198 / :6531 / :6274 |
| `agents/execution_engine/context.py` | dormant `resume_completed_task_ids` field | ✓ VERIFIED | :257, `dict[str,set[str]]\|None = None` |
| `app/main.py` | trio injection before restore scan | ✓ VERIFIED | :150-155, wired onto restore engine instance |
| `tests/agents/test_per_task_capture.py` | multi-file capture RED→GREEN | ✓ VERIFIED | 227 lines, 4 passed |
| `tests/agents/test_restart_resume.py` | rematerialize/merge/skip/live/steering | ✓ VERIFIED | +636 lines, 16 passed |

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `app/main.py` restore scan | engine `resume_run` live-wire | `_resume_live_ectx_register/_unregister/_milestone_sink` injection | ✓ WIRED | injected on same instance that runs `restore_non_terminal_runs()` |
| `resume_run` | `_execute_impl` | `live_ectx_register=` kwarg | ✓ WIRED | :6550 |
| engine kernel | app live callables | injected callables (NO import) | ✓ WIRED | lint 4/0; engine.py has zero import of register/unregister/persist_milestone_card |
| `_compute_resume_completed_task_ids` | `task_loop`/`wave_scheduler` | `ectx.resume_completed_task_ids` field | ✓ WIRED | stamp :2089, read via getattr in both strategies |
| fan-out spawn | `subagent_runs` row | `record_subagent_run(worker_index,task_id)` | ✓ WIRED | at `status="running"`, before `run_worker` |

## Behavioral Spot-Checks (real outputs I ran, cwd `backend/`, python3.11)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Restart-harness RED→GREEN, KAN-88 sole red | `pytest tests/agents/test_restart_resume.py -q` | `16 passed, 1 failed` (only `test_waiting_for_user_run_is_rearmed_not_driven`) | ✓ PASS |
| Wave/capture/subagent | `pytest test_wave_scheduler test_per_task_capture test_subagent_runs -q` | `32 passed` (10+4+18) | ✓ PASS |
| Fan-out suites (6 files) | `pytest test_fanout test_fanout_cancel test_merge_conflict test_isolation test_budget test_sc001_fanout -q` | `105 passed` | ✓ PASS |
| 5 characterization goldens | `SNAPSHOT_UPDATE= pytest test_characterization_{app_builder,od_ppt,od_prototype,prototype_revision,prototype} -q` | `10 passed` | ✓ PASS |
| Banned patterns | `pytest test_banned_patterns.py -q` | `11 passed` | ✓ PASS |
| Migrations | `pytest tests/unit/test_migrations.py -q` | `16 passed, 2 failed` (0016/0023 stale-head, both now naming head `0026` — PRE-EXISTING, count unchanged) | ✓ PASS (delta 0) |
| SSE pair | `pytest test_sse_stream test_attach_replay_matrix -q` | `28 passed, 1 failed` (pre-existing `test_last_event_id_header_resumes_over_http`) | ✓ PASS (delta 0) |
| import boundary | `/opt/homebrew/bin/lint-imports` | `Contracts: 4 kept, 0 broken` | ✓ PASS |
| Migration reversibility | `alembic upgrade 0026 → downgrade 0025 → upgrade 0026` (fresh SQLite) | all steps exit 0 | ✓ PASS |
| INV-1 name literals | `grep -cE 'pipeline_type ==\|spec\.id ==' engine.py` | `0` | ✓ PASS |
| INV-12 single dispatch | `grep -c 'for i, spec in enumerate(ordered_agents)' engine.py` | `1` | ✓ PASS |
| DEF-43-03-1 no count-start | `grep -c 'itertools.count(start)' engine.py` | `0` | ✓ PASS |

## Scope-Fence Audit (phase commit range `bac2a16c~1..e437bef6`)

| Fence | Check | Result |
|-------|-------|--------|
| No task_key/reconciliation (Phase 48) | `grep -c task_key` in production diff | `0` ✓ |
| No uploads storage changes (Phase 47) | no uploads file in changed-file list; only exclusion READS (`.uploads/` filter) added | ✓ |
| No gate re-arm / KAN-88 untouched (Phase 49) | KAN-88 test body last modified in `83cfff4c` (Phase 12-03); not in the 46 diff; test stays RED at runtime | ✓ |
| No REST resume endpoint (Phase 50) | `grep -cE '@router.(post\|put).*resume'` in app diff | `0` ✓ |
| ND-10 images locked | `grep -ciE 'run_images\|image_store'` in production diff | `0` ✓ |
| Changed-file surface | 20 files: authz, task_loop, wave_scheduler, context, engine, fanout, kernel_services, migration 0026, main.py, subagent model + tests only | ✓ matches plan |

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | none | — | Debt-marker scan on added production lines (`TODO/FIXME/XXX/HACK/TBD`) = 0. No stubs; the two nullable columns and the dormant ectx cursor are intentionally None on scripted/golden runs (INV-3), consumed by the wired resume tier — not stubs. The one narrowing worth noting: `persist_task_html` branch 2 re-raises non-`SQLAlchemyError` exceptions (kernel_services.py:1454) rather than swallowing all — a deliberate, defensible choice (only expected offline DB-unavailable errors are swallowed), not a defect. |

## Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Live crash→resume ladder (steering/Concierge/cards on a resumed run; isolated-write fan-out; real merge) on live Bedrock | Milestone v3.0 end (orchestrator-owned live pass) | 46-VALIDATION.md Manual-Only section + 46-CONTEXT: "offline gates bind phase completion; NO live Bedrock in executors; milestone-end live pass covers the ladder." Offline harness runs `shared_read` (no isolated-write redirection) by design (register 11-05). Per project defer-live-verification convention — NOT a phase-blocking gap. |

## Gaps Summary

None. All 8 ROADMAP success criteria are observably true in the codebase, every offline gate passes at baseline-delta-zero (KAN-88 + 2 stale-head migration asserts + 1 SSE fail all pre-existing and unchanged), all scope fences hold, and no anti-patterns or debt markers were introduced. The single deferred item (live-Bedrock ladder) is a documented, orchestrator-owned milestone-end pass per the phase's own validation contract and the project's standing defer-live-verification convention — it does not block phase completion.

---

_Verified: 2026-07-19_
_Verifier: Claude (gsd-verifier)_
