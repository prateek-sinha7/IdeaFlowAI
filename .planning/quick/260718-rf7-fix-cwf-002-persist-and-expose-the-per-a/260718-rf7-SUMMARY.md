---
phase: quick-260718-rf7
plan: 01
subsystem: engine / app-api
tags: [CWF-002, model_id, cost, non-circular, agent_complete, runs-api]
requires:
  - "WorkflowRun.model_id column (migration 0014, app/models/workflow.py:37)"
  - "user.preferred_model (the effective run model, threaded to engine.execute at run_commands.py:1359)"
  - "estimate_cost_usd (agents/capabilities/model_pricing.py) — untouched"
  - "_VOLATILE_STRIP_KEYS 'model_id' entry (tests/agents/characterization/_normalize.py:108)"
provides:
  - "WorkflowRun.model_id is written on every launched run (was always NULL)"
  - "estimated_cost_usd priced from the run's real model (non-circular)"
  - "GET /api/runs + /api/runs/{id} return model_id"
  - "agent_complete event carries the per-agent resolved model_id"
affects:
  - backend/agents/execution_engine/engine.py
  - backend/app/api/run_commands.py
  - backend/app/api/runs.py
  - backend/tests/unit/test_rest_run_launch.py
tech-stack:
  added: []
  patterns: ["reuse existing _VOLATILE_STRIP_KEYS entry for a golden-neutral event key", "catalog-sourced model id in tests (no claude-*-4 literal)"]
key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/app/api/run_commands.py
    - backend/app/api/runs.py
    - backend/tests/unit/test_rest_run_launch.py
decisions:
  - "Persist wr.model_id from the SAME expression threaded to engine.execute (getattr(user,'preferred_model',None) or None) — no recompute, respects locked ModelResolver precedence (Phase 6 D-02)."
  - "Reuse the existing model_id strip key (no _normalize.py edit) so the 5 characterization goldens stay byte-identical."
  - "Do NOT mirror onto _drive_revision_to_queue: its terminal path writes only status+completed_at, no token/cost/model block (LOCK-B — mirror only equal records)."
metrics:
  duration: "~15 min"
  completed: "2026-07-18"
  tasks: 3
  files: 4
---

# Phase quick-260718-rf7 Plan 01: CWF-002 — Persist + Expose Per-Agent Model (non-circular cost) Summary

Persist the launched run's effective `model_id` onto `WorkflowRun.model_id`, price `estimated_cost_usd` from that real model instead of the default inference profile (non-circular), expose `model_id` on both `/api/runs` responses, and stamp the per-agent resolved `model_id` onto the `agent_complete` stream event — all with zero migration and zero golden perturbation.

## What Was Built

Three surgical changes, TDD RED→GREEN:

- **(a) engine.py** — added `"model_id": _resolved_model_id` to the single `agent_complete` `data` dict inside `_run_agent`. `_resolved_model_id` is the resolved primary model id captured at `engine.py:3055` in the same frame. The key reuses the existing `_VOLATILE_STRIP_KEYS` `model_id` entry, so no `_normalize.py` edit and the goldens are byte-identical.
- **(b) run_commands.py** — in `_drive_launch_to_queue`'s terminal DB block, set `wr.model_id = getattr(user, "preferred_model", None) or None` unconditionally BEFORE the token-rollup / cost computation. The existing cost line `estimate_cost_usd(wr.model_id or settings.BEDROCK_INFERENCE_PROFILE_ID, …)` now reads the freshly-set value in the same transaction → non-circular.
- **(c) runs.py** — added `model_id: Optional[str] = None` to `WorkflowRunResponse`. `_run_response` iterates `model_fields` with `getattr(run, name)`, so the ORM column auto-materializes into BOTH list (summary) and detail responses; no `_run_response` change.

## RED→GREEN Evidence

New test `test_driver_persists_model_id_and_prices_non_circular` in `tests/unit/test_rest_run_launch.py`. It sources a non-default model from the catalog (`ModelCatalog().ids()`, first id priced differently from `settings.BEDROCK_INFERENCE_PROFILE_ID` for the same tokens — no hardcoded `claude-*-4` literal), sets it as the seeded user's `preferred_model`, drives `_drive_launch_to_queue` with a rich engine stub (input=10/output=5), then asserts `wr.model_id == non_default_id` AND `token_usage.estimated_cost_usd == estimate_cost_usd(non_default_id, …)` AND `!= default-profile price`.

- **RED (before fix b/c):** `AssertionError: assert None == 'eu.anthropic.claude-sonnet-4-5-20250929-v1:0'` — `WorkflowRun.model_id` was NULL.
- **GREEN (after fix b/c):** test passes; `model_id` persisted, cost priced from the real model.

## Verification Results

- `tests/unit/test_rest_run_launch.py` + `tests/agents/test_model_catalog.py` — **34 passed** (incl. the new test + `test_single_source_grep`).
- `tests/agents/test_model_pricing.py` — 26/27 pass; the 1 fail (`test_websocket_cost_site_uses_shared_function`) is a **pre-existing stale test** reading the deleted `app/api/websocket.py` (Phase 44 SSE cutover), unrelated to this task — see `deferred-items.md`.
- `tests/agents/test_characterization_*.py` — **10 passed**, byte/event-identical (the new `agent_complete` key is stripped by the existing `_VOLATILE_STRIP_KEYS` `model_id` entry).
- `lint-imports` — **4 kept, 0 broken** (kernel/app boundary intact).

## Deviations from Plan

None — plan executed exactly as written. One out-of-scope pre-existing failure logged to `deferred-items.md` (not fixed, per executor scope rule).

## Guardrails Honored

- **Q3** — no migration; `WorkflowRun.model_id` (0014) already exists.
- **Phase 26** — no `claude-(haiku|sonnet|opus)-4` literal added under `app/api` or `agents/capabilities`; `test_single_source_grep` green. `estimate_cost_usd` math/signature, `model_catalog.py`, and `ModelResolver` precedence untouched.
- **INV-3** — the new `agent_complete` key is stripped; 5 goldens (10 characterization tests) byte/event-identical.
- **INV-1** — generic `model_id` key, no workflow-name literal.
- **CWF-002 ONLY** — no CWF-001/D1/D2 edits; revision twin left untouched (LOCK-B).

## Commits

- `8e0af54f` — test(tests): CWF-002 RED — assert run persists model_id + non-circular cost
- `9c6ef0f4` — fix(engine): CWF-002 persist effective model_id on run + non-circular cost, expose in runs API
- `8251081d` — feat(engine): CWF-002 stamp resolved model_id on agent_complete payload

## Self-Check: PASSED

- Files modified exist: engine.py, run_commands.py, runs.py, test_rest_run_launch.py — all present.
- Commits present in `git log`: 8e0af54f, 9c6ef0f4, 8251081d.
