---
phase: 29-transport-cutover-chat-backbone-a1
plan: 04
subsystem: backend-api / transport-cutover
tags: [CHAT-07, D-13, LOCK-B, rest-transport, image-caps, revision, chat-shim]
requires:
  - "29-03 run_commands.py router (gate/answers/cancel) mounted on /api/runs"
  - "29-02 SSE down-channel GET /api/runs/{id}/events/stream (attaches to per-run queue)"
  - "websocket.py WS-agnostic queue registry + ingress validators (read-only reuse)"
provides:
  - "POST /api/runs — REST run launch (mint + WS-agnostic driver) with image caps"
  - "POST /api/runs/{id}/revisions — child revision-run dispatch (owner-gated 404)"
  - "POST /api/runs/user_message — legacy free-chat POST+stream shim (ChatRunner)"
affects:
  - "backend/app/api/run_commands.py (additive endpoints only)"
tech-stack:
  added: []
  patterns:
    - "Sanctioned LOCK-B duplication of the nested _run_pipeline_to_queue / _run_revision_to_queue closures (socket-coupled, not importable)"
    - "Read-only reuse of websocket.py validators + queue registry (no symbol added)"
    - "POST+SSE shim (EventSourceResponse) wrapping ChatRunner's native event vocab"
key-files:
  created:
    - "backend/tests/unit/test_rest_run_launch.py"
    - "backend/tests/unit/test_rest_revisions.py"
    - "backend/tests/unit/test_rest_user_message_shim.py"
  modified:
    - "backend/app/api/run_commands.py"
    - "backend/tests/unit/test_image_ws_ingress.py"
decisions:
  - "Launch mint mirrors ws:1940 (user_id set, owner_id left NULL — engine mints workspace + completes scope); down-channel owner-checks on user_id"
  - "Revision endpoint DENIES a cross-owner/unknown parent with 404 (stricter than the WS path, which drops the link but still dispatches) — the ported parent-link ownership contract"
  - "Endpoint tests assert only the synchronous mint/validation; the WS-agnostic drivers are tested by direct-drive (deterministic — no TestClient background-task timing race)"
metrics:
  duration: "~40 min"
  completed: "2026-07-08"
  tasks: 3
  files: 5
---

# Phase 29 Plan 04: Transport Cutover — Up-Channel Launch Commands Summary

The remaining up-channel launch commands shipped additively over REST — `POST /api/runs` (launch + image caps), `POST /api/runs/{id}/revisions` (child run), and the `user_message` POST+stream shim (drives ChatRunner) — with `/ws/chat` untouched (LOCK-B).

## What Was Built

**Task 1 — `POST /api/runs` (launch) + image caps.** A REST twin of the WS `run_pipeline` handler in `run_commands.py`. It runs the full ported ingress validation BEFORE minting (od_* alias + od_context resolution, `SUPPORTED_PIPELINE_TYPES` gate, `allowed_custom_agent_ids` allow-list → `invalid_agent_ids`, `_validate_model_overrides`, `_revalidate_selections_trust_user`, and the `_validate_images` caps — mime allow-list, ~3.75MB/image, ≤20, ~8MB aggregate, vision-model guard, `IMAGE_INPUT_ENABLED` off → ignored). On success it mints the `WorkflowRun` (mirroring ws:1940 — `user_id`, `session_id`, `selections_json`, owner-checked `parent_run_id`), registers the per-run cancel event, and spawns the WS-agnostic background driver `_drive_launch_to_queue` onto the per-run queue via read-only `_get_or_create_queue`; the SSE stream (29-02) attaches to that same queue. The driver is a sanctioned duplication of the nested `_run_pipeline_to_queue` closure body (the closure is `nonlocal`-coupled + socket-nested, so it is not importable). Image cases were re-pointed onto the REST launch in `test_image_ws_ingress.py` (WS cases stay green — additive).

**Task 2 — `POST /api/runs/{id}/revisions` (child run).** Owner-gates the parent (`WorkflowRun.id == run_id AND user_id == caller` → 404 on cross-owner/unknown, IDOR → 404), mints a FAMILY CHILD `WorkflowRun` (`parent_run_id` + `owner_id`, `type=<base>_revision`, registry-derived `agent_count` — never a hardcoded 1), and spawns `_drive_revision_to_queue` (a duplication of `_run_revision_to_queue` minus the socket drainer) which calls `engine._handle_revision` and owns the terminal-status persistence. This is D-02's family "revision run", NOT the intra-run KAN-101 spec-revision loop.

**Task 3 — `user_message` POST+stream shim.** `POST /api/runs/user_message` ports the legacy free-chat handler to a POST+SSE shim: it owner-gates the chat session (→ 404), persists the user `Message`, then returns an `EventSourceResponse` that drives `ChatRunner.astream_execute` unchanged — streaming its native `phase_start/stream/phase_end/error/complete` frames verbatim — and persists the assistant `Message` + session `final_output` at the end. `ChatRunner` and the frozen `test_chat_contract.py` golden are untouched (ND-3 / landmine).

## Reuse strategy (as asked)

- **Launch + revision:** reuse-by-DUPLICATION (the sanctioned LOCK-B path). The WS drive loops are nested socket-coupled closures, not importable; the minimal mint+drive logic is replicated in `run_commands.py`, reusing the IMPORTABLE helpers read-only (`_validate_images`, `_validate_model_overrides`, `_revalidate_selections_trust_user`, `_resolve_owned_parent_run_id`, `_get_or_create_queue`, `_cleanup_pipeline`, `_get_db`, the `_CANCEL_EVENTS` / `_PIPELINE_TASKS` registries, and `engine._handle_revision`). No fake-socket adapter was needed.
- **user_message:** read-only reuse of `ChatRunner` (constructed + driven, never modified).

## Deviations from Plan

### Auto-fixed / Adjusted

**1. [Rule 3 — Blocking] `_get_db` monkeypatch must target `run_commands`, not only `websocket`.**
- **Found during:** Task 1 (first mint test hit `no such table: workflow_runs`).
- **Issue:** `run_commands` binds `from app.api.websocket import _get_db` at import, so the 29-03 test idiom (patch `ws_module._get_db`) does not reach the REST endpoints' direct calls.
- **Fix:** the new suites patch `run_commands._get_db` (and register the ORM models on `Base.metadata` before `create_all`). No production change.

**2. [Rule 3 — Test determinism] Endpoint tests assert only the synchronous mint/validation; drivers tested by direct-drive.**
- **Issue:** Starlette `TestClient` background-task (`asyncio.create_task`) completion is timing-nondeterministic — asserting driver side-effects from the endpoint response is racy.
- **Fix:** the WS-agnostic drivers (`_drive_launch_to_queue`, `_drive_revision_to_queue`) are exposed as module-level coroutines and driven DIRECTLY in tests (deterministic queue + DB assertions), mirroring how the WS suites drive `_handle_revision_execution`.

### Out of scope (logged, NOT fixed)

**DEF-29-04-1 — pre-existing `test_run_pipeline_validation.py` failures on `feat/ui-2`.** 12/50 cross-*base*-pipeline rejection cases fail because the `custom` agent pool has widened to admit other pipelines' base agents (proven pre-existing on `HEAD` before any edit). Out of scope per the SCOPE BOUNDARY. The REST launch pin uses a genuinely-unknown agent id (which no widening can admit), so the security property is still pinned. Logged to `deferred-items.md`.

## LOCK-B Confirmation (`git diff --name-only` for this plan)

Changed files, all within the allow-list:
- `backend/app/api/run_commands.py` (additive endpoints)
- `backend/tests/unit/test_image_ws_ingress.py` (additive REST image cases)
- `backend/tests/unit/test_rest_run_launch.py` (new)
- `backend/tests/unit/test_rest_revisions.py` (new)
- `backend/tests/unit/test_rest_user_message_shim.py` (new)
- `.planning/phases/29-.../deferred-items.md` (docs)

ABSENT from the diff (confirmed): `backend/app/api/websocket.py`, `backend/app/agents/chat_runner.py`, `backend/tests/unit/test_chat_contract.py`, `backend/app/api/websocket_handoff.py`, `frontend/src/hooks/useWebSocket.ts`. No `main.py` re-edit (router already mounted in 29-03). Zero new DB tables, no WS deletion / ratchet / migration-ledger row.

## Verification (offline — real output)

- `python3.11 -m pytest tests/unit/test_rest_run_launch.py tests/unit/test_rest_revisions.py tests/unit/test_rest_user_message_shim.py tests/unit/test_image_ws_ingress.py tests/unit/test_chat_contract.py tests/agents/test_wire_parity.py -x -q` → **48 passed** (6 launch + 10 revision + 5 shim + 10 image [4 new REST cases + 6 WS cases green] + 11 chat_contract golden + 6 wire_parity). NOTE: the plan's `tests/agents/test_chat_contract.py` path is stale — the golden lives at `tests/unit/test_chat_contract.py`.
- `cd backend && /opt/homebrew/bin/lint-imports` → **4 kept, 0 broken**.
- Regression (untouched WS/REST suites): `test_run_revision_ws_dispatch.py + test_ws_parent_link_ownership.py + test_rest_gate_commands.py + test_rest_answers_cancel.py + test_sse_stream.py` → **57 passed**.

## DEFERRED-to-live

The end-to-end run-drive (a REAL engine/Bedrock pipeline behind `POST /api/runs` streaming over live SSE) is proven at the SEAM level offline (mint + spawn + queue population with a scripted/recording engine; the SSE attach is the same `_get_or_create_queue` seam 29-02 tests cover). The live drive (real Bedrock + live SSO server) is DEFERRED to the consolidated milestone-end live pass, per the defer-live-verification convention — no live Bedrock was invoked (D-24).

## Known Stubs

None. The endpoints wire real seams (real engine/ChatRunner drive, real persistence); test doubles are confined to the offline suites.

## Self-Check: PASSED

All created files exist on disk; all three task commits (3d951b2d, 85ee3e6c, 69cb27c7) present in git history.
