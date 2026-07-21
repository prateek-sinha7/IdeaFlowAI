---
phase: 29-transport-cutover-chat-backbone-a1
plan: 02
subsystem: transport / chat-backbone
tags: [CHAT-07, D-01, D-13, D-14g, D-14h, SSE, LOCK-B, ND-9]
requires:
  - "29-01 wire-parity projection (_sse_projection.py) — the frame contract this endpoint re-implements"
  - "ScopedStore.read_events / read_gate_events (owner-scoped durable log)"
  - "app.api.websocket._get_or_create_queue / _PIPELINE_QUEUES (existing per-run live queue)"
provides:
  - "GET /api/runs/{id}/events/stream — additive per-run SSE down-channel (behind SSE_TRANSPORT_ENABLED)"
  - "stream_attached {live, replayed_through_seq} handshake (new-transport pipeline_reconnected replacement)"
  - "D-14g gate re-arm on attach (review_gate_ready re-emitted from persisted durable log)"
  - "SSE_TRANSPORT_ENABLED flag + D-14h ping/idle infra knobs on Settings"
affects:
  - "backend/app/main.py (one additive include_router line)"
tech-stack:
  added: ["sse-starlette==3.0.2 EventSourceResponse (already pinned; first production use)"]
  patterns: ["two-layer owner check (user_id filter -> ScopedStore default-deny) IDOR->404", "dependency-injected async generator for offline unit-testability"]
key-files:
  created:
    - "backend/app/api/run_stream.py"
    - "backend/tests/unit/test_sse_stream.py"
  modified:
    - "backend/app/core/config.py"
    - "backend/app/main.py"
decisions:
  - "Production re-implements the 29-01 SSE frame rendering IN-LINE rather than importing the test-support projection — the projection module's own docstring anticipates this ('29-02 will re-implement the same rendering'); avoids a production->tests import (root_packages=[agents,app] would not flag it, but app boot must not depend on tests/ being deployed). Parity is proven in the TEST via the real assert_wire_parity."
  - "Liveness signal = membership in _PIPELINE_QUEUES (a registered queue == a live run); a finished run has no queue so durable replay + handshake is the complete response."
  - "Gate re-arm (D-14g) derived purely from the owner-scoped durable run_events (last review_gate_ready not followed by a resolution event) — server-derived (ND-9), read-only, no engine/artifact mutation."
metrics:
  duration: "~4 min"
  completed: "2026-07-08"
  tasks: 3
  files: 4
---

# Phase 29 Plan 02: Transport Cutover — Per-Run SSE Chat Backbone Summary

The additive `GET /api/runs/{id}/events/stream` SSE down-channel ships behind `SSE_TRANSPORT_ENABLED`, ALONGSIDE `/ws/chat` (LOCK-B): it replays the durable `run_events` tail from the browser-native `Last-Event-ID` cursor, emits the `stream_attached {live, replayed_through_seq}` handshake, re-arms a paused review gate on attach (D-14g), then drains the SAME per-run live queue the WS drainer feeds — with `id:`=`seq` frames that are wire-parity-identical to the recorded WS frames by construction.

## What Was Built

### Task 1 — SSE stream endpoint off the per-run queue + durable log
- `backend/app/api/run_stream.py`: `APIRouter(prefix="/api/runs")` with `GET /{id}/events/stream` returning `text/event-stream` via `sse_starlette.EventSourceResponse`.
- Two-layer owner check copied VERBATIM from `runs.py::get_run_events`: `WorkflowRun.user_id == current_user.id` filter → 404, then `ScopedStore.get_run` default-deny → 404 (IDOR → 404, never 403).
- Durable replay: `ScopedStore.read_events(run_id, after_seq)` where `after_seq` = `Last-Event-ID` header (non-int degrades to 0, never 422 — the browser controls this header on auto-reconnect; a hostile value only bounds the caller's OWN replay, T-29-02-2).
- Live attach: `_get_or_create_queue` / `_PIPELINE_QUEUES` imported READ-ONLY from `app.api.websocket` (no symbol added, websocket.py untouched — LOCK-B); membership in `_PIPELINE_QUEUES` is the liveness signal.
- Frame body re-implements the 29-01 projection contract: `id: {seq}\ndata: {json {type,data}}\n\n`.
- `config.py`: `SSE_TRANSPORT_ENABLED: bool = True` + D-14h knobs (`SSE_KEEPALIVE_PING_SECONDS`, `SSE_STREAM_IDLE_TIMEOUT_SECONDS`); response sets `X-Accel-Buffering: no` + `Cache-Control: no-cache` and documents `proxy_buffering off` for the ingress. Flag-off → 404 feature-absent.

### Task 2 — stream_attached handshake + gate re-arm on attach (D-14g)
- `stream_attached` carries `{live, replayed_through_seq}` where `replayed_through_seq` mirrors the last replayed `seq` (== legacy `pipeline_reconnected.replayed_through_seq` semantics); its `id:` line does NOT advance the cursor past the real tail.
- D-14g: `_dangling_review_gate` finds the last `review_gate_ready` in the FULL owner-scoped durable log NOT followed by a resolution event (`review_gate_approved` / terminal); if present the attach path re-emits `review_gate_ready` so a reload during a paused gate resumes (closes P23/F4). Read-only — reads state via ScopedStore, never re-runs an agent or mutates the artifact graph (proven by the `test_rearm_is_read_only` row-count assertion). ND-9: fully server-derived from replayed run_events, no sessionStorage trust.

### Task 3 — Register router + wire-parity binding
- `main.py`: one additive `app.include_router(run_stream_router)` line after `runs_router`; `websocket_router` (line 179) + `websocket_handoff_router` includes untouched.
- `test_sse_stream.py` `test_endpoint_frames_satisfy_wire_parity`: drives `prototype_revision` offline, seeds the derived `run_events`, consumes the endpoint generator, reconstructs rows from the emitted frames (dropping the synthetic `stream_attached`), and asserts the REAL `assert_wire_parity(ws_frames, endpoint_rows)` — guards against accidental divergence in the endpoint's rendering.

## Verification (offline — no live Bedrock / no live server)

- `python3.11 -m pytest backend/tests/unit/test_sse_stream.py backend/tests/agents/test_wire_parity.py -x -q` → **21 passed** (15 SSE + 6 wire-parity) in ~22s.
- `python3.11 -m pytest backend/tests/unit/test_sse_stream.py -x -q` → **15 passed** (replay 3, attach 2, owner 4, handshake 2, rearm/gate 3, wire-parity 1).
- `cd backend && /opt/homebrew/bin/lint-imports` → **4 kept / 0 broken** (197 files, 460 deps).
- `python3.11 -m pytest backend/tests/agents/test_characterization_prototype.py -x -q` → **2 passed** — the 5 INV-3 goldens byte/event-identical (NO `SNAPSHOT_UPDATE`, no golden edited).
- `python3.11 -c "import app.main"` → imports OK, router mounts cleanly.

## LOCK-B Confirmation (`git diff --name-only` over the two feature commits)

Changed files: `backend/app/api/run_stream.py`, `backend/app/main.py`, `backend/app/core/config.py`, `backend/tests/unit/test_sse_stream.py` — all within the allow-list.

- `backend/app/api/websocket.py` — **NOT present** (read-only import of the existing `_get_or_create_queue` / `_PIPELINE_QUEUES`; no new symbol added).
- `backend/app/api/websocket_handoff.py` — **NOT present**.
- `frontend/src/hooks/useWebSocket.ts` — **NOT present**.
- `app.include_router(websocket_router)` still present in `main.py:179` (grep-confirmed); no `/ws/chat` handler deleted; no arm/ratchet deletion; zero migration-ledger deletion rows; zero new DB tables.

## Deviations from Plan

**1. [Rule 3 - correctness] Production re-implements the SSE rendering instead of importing the test-support projection.**
- **Found during:** Task 1.
- **Issue:** The plan `key_links` suggests `run_stream.py` reuse `_sse_projection.run_event_to_sse_frame`. That module lives under `tests/` and depends on `tests.agents.characterization._normalize` (test-only). A production `from tests...` import would make app boot depend on `tests/` being deployed (packaging risk) and has zero precedent in `app/*`.
- **Fix:** Re-implemented the tiny, identical frame rendering in `run_stream.py` (`_sse_body` / `_sse_frame`) — which the projection module's OWN docstring explicitly anticipates ("29-02 will re-implement the same rendering inside the endpoint against this contract"). Parity is proven in the TEST (`test_sse_stream.py` imports the real `assert_wire_parity`). import-linter stays 4/0 either way (`tests` is outside `root_packages`), but this keeps production tests-free.
- **Files:** `backend/app/api/run_stream.py`, `backend/tests/unit/test_sse_stream.py`.
- **Commit:** 7020bf82.

## Known Stubs

None — the endpoint is fully wired to the live per-run queue + durable log; no placeholder/mock data paths.

## Threat Flags

None beyond the plan's `<threat_model>`. T-29-02-1 (cross-owner replay) is mitigated by the two-layer owner check (tested: `test_cross_owner_is_404`, `test_missing_run_is_404`, `test_never_403`). No new network endpoint beyond the planned SSE route; no schema change; no new trust boundary.

## Deferred to Live Pass

- **Live SSE over a real proxy (nginx `X-Accel-Buffering: no` / `proxy_buffering off` end-to-end, browser `EventSource` auto-reconnect with `Last-Event-ID`)** — requires a live server + ingress; verified offline via TestClient streaming + direct generator drive. Deferred to the consolidated milestone-end live pass (per the defer-live-verification convention).

## Commits

- `7020bf82` feat(29-02): per-run SSE stream endpoint off the queue + durable log (CHAT-07) — run_stream.py, config.py, test_sse_stream.py
- `5b582cd1` feat(29-02): register run_stream_router in main.py (additive, LOCK-B) — main.py

## Self-Check: PASSED

All 4 code/doc files present on disk; both feature commits (7020bf82, 5b582cd1) present in git history.
