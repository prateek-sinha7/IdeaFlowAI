---
phase: quick-260718-rf7
verified: 2026-07-18T00:00:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Quick Task 260718-rf7: CWF-002 — Persist + Expose Per-Agent Model (non-circular cost) Verification Report

**Task Goal:** (a) `agent_complete` carries the resolved `model_id` (stripped from goldens by
the pre-existing `_VOLATILE_STRIP_KEYS` entry); (b) `WorkflowRun.model_id` is persisted from
the same expression already threaded to `engine.execute`, written BEFORE the cost line so
`estimated_cost_usd` is non-circular; (c) `runs.py` exposes `model_id` in summary + detail.
**Verified:** 2026-07-18
**Status:** passed

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `wr.model_id` written before `estimate_cost_usd(...)`, cost non-circular | VERIFIED | `run_commands.py:1379` — `wr.model_id = getattr(user, "preferred_model", None) or None` sits directly before `total_input = sum(...)` (:1380) and the cost line `estimate_cost_usd(wr.model_id or settings.BEDROCK_INFERENCE_PROFILE_ID, ...)` (:1509 area) reads the freshly-set value in the same transaction, unconditional (not gated by status). |
| 2 | `WorkflowRunResponse` has `model_id`, auto-materialized into list + detail | VERIFIED | `runs.py:105` `model_id: Optional[str] = None` on `WorkflowRunResponse`; `_run_response` (:219-234) builds kwargs via `getattr(run, name) for name in WorkflowRunResponse.model_fields`, used by both `list_runs` (:240) and `get_run` (:391) — no per-endpoint change needed. |
| 3 | `agent_complete` carries resolved `model_id`; `_VOLATILE_STRIP_KEYS` already has `model_id` (no normalizer edit, goldens byte-identical) | VERIFIED | `engine.py:3695` — `"model_id": _resolved_model_id` inside the single `agent_complete` yield in `_run_agent`; `_resolved_model_id` captured at `engine.py:3055` in the same frame. `tests/agents/characterization/_normalize.py:108` already lists `"model_id"` in `_VOLATILE_STRIP_KEYS` (pre-existing, confirmed no diff to this file across the 3 commits). |
| 4 | Scope held: no migration, no `claude-*-4` literal added, `estimate_cost_usd`/`model_catalog.py`/`ModelResolver` untouched, CWF-002 only | VERIFIED | Per-commit diffs are surgical: `run_commands.py` +7 lines, `runs.py` +4 lines, `engine.py` +6 lines, `test_rest_run_launch.py` +113 lines (new test only). `grep -rn "claude-(haiku|sonnet|opus)-4" app/api/ agents/capabilities/` finds matches only in `model_catalog.py` (the pre-existing single source, untouched). No migration file added. Revision twin `_drive_revision_to_queue`/`_persist_terminal_status` (:1698-1710) confirmed to have no token_usage/cost/model block — correctly left untouched (LOCK-B). |
| 5 | RED→GREEN: non-default `preferred_model` run persists `wr.model_id` + non-circular cost | VERIFIED | `test_driver_persists_model_id_and_prices_non_circular` (`tests/unit/test_rest_run_launch.py:813-914`) sources a catalog model priced differently from the default profile (no hardcoded literal), sets it as `user.preferred_model`, drives `_drive_launch_to_queue` directly, asserts `row.model_id == non_default_id`, `usage["estimated_cost_usd"] == expected_cost`, and `!= _default_price`. Ran live: **PASS**. |
| 6 | Behavioral regression suite green | VERIFIED | Ran independently (not just trusted from SUMMARY): `test_rest_run_launch.py` + `test_model_catalog.py` → 34 passed (incl. `test_single_source_grep`); characterization suite → 10 passed byte/event-identical (5 goldens); `test_model_pricing.py` → 26 passed, 1 pre-existing unrelated failure (see below); `lint-imports` → 4 kept, 0 broken. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/execution_engine/engine.py` | `model_id` on `agent_complete` payload | VERIFIED | Line 3695, sourced from `_resolved_model_id` (:3055), same `_run_agent` frame. |
| `backend/app/api/run_commands.py` | `wr.model_id =` write before cost computation | VERIFIED | Line 1379, unconditional, inside `if wr:` terminal block, before `total_input`/`estimate_cost_usd`. |
| `backend/app/api/runs.py` | `WorkflowRunResponse.model_id` | VERIFIED | Line 105; auto-materialized by `_run_response`'s `model_fields` getattr loop. |
| `backend/tests/unit/test_rest_run_launch.py` | RED→GREEN test | VERIFIED | New test present and passing; asserts persistence + non-circular cost, no shortcuts. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `run_commands.py` terminal DB block | `estimate_cost_usd(wr.model_id or BEDROCK_INFERENCE_PROFILE_ID, ...)` | `wr.model_id` set before cost computation | WIRED | Confirmed same-transaction ordering; test proves it (cost differs from default-profile price when a non-default model is used). |
| `runs.py WorkflowRunResponse.model_id` | `_run_response` getattr loop | auto-materialized ORM column | WIRED | `model_fields` iteration includes `model_id`; no hand-maintained list to miss it. |
| `engine.py _resolved_model_id` (:3055) | `agent_complete.data.model_id` (:3695) → `_VOLATILE_STRIP_KEYS` strip (:108) | resolved primary model id stamped + stripped by name | WIRED | Golden suite proves the strip works — 10/10 characterization tests byte/event-identical. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CWF-002 | 260718-rf7-PLAN.md | Persist + expose per-agent model, non-circular cost | SATISFIED | All 3 fix sites (a/b/c) verified in code + passing tests, per truths 1-5 above. |

### Anti-Patterns Found

None. Diffs across all 3 commits are surgical (7/4/6 lines respectively in the production files + a self-contained new test). No TODO/FIXME/TBD/XXX/placeholder markers introduced in the modified lines.

### Pre-existing Failure (Confirmed Unrelated)

`tests/agents/test_model_pricing.py::test_websocket_cost_site_uses_shared_function` fails with
`FileNotFoundError: app/api/websocket.py` — that file was deleted in the Phase 44 SSE cutover
(confirmed: `ls app/api/websocket.py` → No such file; `git log -- app/api/websocket.py` shows
its deletion commit `0c8ee539` predates this task). CWF-002's 3 commits never touch
`app/api/websocket.py` (confirmed via per-commit `git show --stat`). This failure is
pre-existing and out of CWF-002 scope, correctly logged (not silently swept) in
`deferred-items.md`.

### Human Verification Required

None. All must-haves are verifiable via code inspection + targeted offline test runs (no
visual, real-time, or external-service dependency for this backend-only fix).

### Gaps Summary

None. All 6 observable truths verified against the actual codebase (not SUMMARY.md claims);
all listed automated checks were independently re-run and passed; the one failing test in the
broader `test_model_pricing.py` run was independently confirmed to be a pre-existing,
unrelated, already-logged deletion-drift failure.

---

_Verified: 2026-07-18_
_Verifier: Claude (gsd-verifier)_
