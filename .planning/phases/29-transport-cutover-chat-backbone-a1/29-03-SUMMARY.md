---
phase: 29-transport-cutover-chat-backbone-a1
plan: 03
subsystem: api
tags: [fastapi, rest, hitl, chat, websocket, idor, kan-100, kan-101, kan-94]

# Dependency graph
requires:
  - phase: 29-01
    provides: wire-parity harness (run_events→SSE projection goldens) — regression guard that the up-channel adds no new outbound event shapes
  - phase: 29-02
    provides: server-derived run state / run_events spine the paused-run commands resolve against
provides:
  - "POST /api/runs/{id}/gate — four-action REST gate command (approve/reject/redo/update_specs) over store.set_review_response"
  - "POST /api/runs/{id}/answers — REST clarify submit over store.set_questionnaire_responses (incl. skip_clarification + freeform mapping)"
  - "POST /api/runs/{id}/cancel — REST cooperative cancel via _CANCEL_EVENTS"
  - "Transport-agnostic up-channel that works over plain HTTP / while SSE is down, additive beside /ws/chat"
affects: [29-transport-cutover FE command wiring, phase-32-inline-gate, chat-backbone]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin transport-agnostic REST wrapper reusing the WS inbound seams by read-only import (no seam duplication, no /ws/chat edit — LOCK-B additive cutover)"
    - "Event-driven gate pending-check (KAN-94): armed-but-unset review event = genuinely pending; else clean not-found"

key-files:
  created:
    - backend/app/api/run_commands.py
    - backend/tests/unit/test_rest_gate_commands.py
    - backend/tests/unit/test_rest_answers_cancel.py
  modified:
    - backend/app/main.py

key-decisions:
  - "Reused the existing WS predicates (_review_gate_owned_by, _review_gate_run_is_terminal) + cancel registry (_CANCEL_EVENTS) by read-only import rather than duplicating logic — websocket.py never touched (LOCK-B)"
  - "KAN-94 pending-gate detection reads the store's existing per-process _resume_events registry (no store mutation, store.py untouched) so REST never fabricates/resolves an unarmed gate"
  - "Terminal fence returns HTTP 409 with {code:pipeline_not_running, recoverable:false}; IDOR denials return 404 'Unknown gate_key' (never 403)"
  - "freeform note mapped to question_id:'freeform' on the endpoint (mirrors the frontend's existing shape); responses otherwise passed verbatim to the store seam"

patterns-established:
  - "Up-channel command endpoint: owner-gate → terminal-fence → pending/route check → existing store/cancel seam"

requirements-completed: [CHAT-07]

# Metrics
duration: ~15min
completed: 2026-07-08
---

# Phase 29 Plan 03: Transport-Cutover Up-Channel REST Commands Summary

**Paused-run gate/answers/cancel now work over plain HTTP — three thin REST endpoints (four-action gate + terminal fence, clarify submit, cooperative cancel) that reuse the exact `/ws/chat` store/cancel seams by read-only import, additively, with `/ws/chat` and store.py untouched.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-08
- **Tasks:** 3
- **Files modified:** 4 (1 created router, 2 created test suites, 1 additive include)

## Accomplishments
- `POST /api/runs/{id}/gate` preserves the FOUR-action contract (approve / reject / redo+instructions / update_specs→KAN-101 analysis_report), the KAN-100 terminal fence (`pipeline_not_running`, recoverable:false), KAN-94 event-driven gate semantics (no armed gate → clean not-found, never a fabricated pause), and the P13 owner IDOR→404.
- `POST /api/runs/{id}/answers` submits clarify responses through `store.set_questionnaire_responses` incl. the ISS-027 `skip_clarification` force-proceed and the `question_id:"freeform"` note mapping.
- `POST /api/runs/{id}/cancel` sets the per-run cooperative `_CANCEL_EVENTS` event (ISS-007), idempotent when nothing is live; suspend/persist semantics unchanged.
- Router mounted additively in `main.py`; the `websocket_router` include stays intact; wire-parity gate re-run green (no new outbound event shapes).
- Both WS inbound-handler test suites ported 1:1 against the REST endpoints (24 REST tests).

## Task Commits

Each task was committed atomically:

1. **Task 1: POST /{id}/gate — four actions + terminal fence + ownership** — `04f4ccf0` (feat)
2. **Task 2: POST /{id}/answers + /{id}/cancel ported 1:1** — `39deaa32` (test) — endpoints shipped in the Task-1 router file; this commit adds the answers/cancel suite
3. **Task 3: register router (additive) + wire-parity regression guard** — `b23766d5` (feat)

_Note: the three endpoints were authored together in `run_commands.py` under Task 1's commit; Task 2's commit lands the answers/cancel test suite that exercises them._

## Files Created/Modified
- `backend/app/api/run_commands.py` — the three transport-agnostic REST command endpoints (gate/answers/cancel), thin over the existing store/cancel seams; read-only import of `_CANCEL_EVENTS`, `_review_gate_owned_by`, `_review_gate_run_is_terminal`.
- `backend/tests/unit/test_rest_gate_commands.py` — 15 tests ported from `test_approve_review_ownership.py` against the REST gate endpoint.
- `backend/tests/unit/test_rest_answers_cancel.py` — 9 tests ported from `test_pipeline_cancel.py` (+ questionnaire submit) against the REST answers/cancel endpoints.
- `backend/app/main.py` — additive `app.include_router(run_commands_router)` beside the WS include.

## Verification (offline, real output)

- `python3.11 -m pytest tests/unit/test_rest_gate_commands.py tests/unit/test_rest_answers_cancel.py tests/agents/test_wire_parity.py -x -q` → **30 passed** (15 gate + 9 answers/cancel + 6 wire-parity).
- `/opt/homebrew/bin/lint-imports` (from `backend/`) → **Contracts: 4 kept, 0 broken.**
- `python3.11 -c "import app.main"` → main import OK (router mounts cleanly).

## LOCK-B Confirmation (`git diff --name-only 04f4ccf0^ HEAD`)

Files changed by this plan (exactly the four allow-listed):
- `backend/app/api/run_commands.py`
- `backend/app/main.py`
- `backend/tests/unit/test_rest_gate_commands.py`
- `backend/tests/unit/test_rest_answers_cancel.py`

Guards:
- `websocket.py` / `websocket_handoff.py` / `useWebSocket.ts` / `store.py` — **NOT present** in the plan diff.
- `app.include_router(websocket_router)` still present in `main.py` (grep count = 1).
- No WS deletion / ratchet / ledger row; zero new DB tables.

## Decisions Made
See frontmatter `key-decisions`. Core: reuse the WS/store seams by read-only import (LOCK-B additive), detect a genuinely-pending gate via the store's existing `_resume_events` registry for KAN-94, IDOR→404 non-revealing, terminal→409 `pipeline_not_running`.

## Deviations from Plan

None - plan executed exactly as written. The three endpoints were authored together in the single router file (the natural unit), so Task 2's atomic commit contains its test suite rather than new production code; the endpoints it tests were committed under Task 1. No behavioral deviation.

## Issues Encountered
- The KAN-100 terminal fence needs `_review_gate_run_is_terminal` (websocket.py:351) in addition to the two symbols named in the prompt; imported it read-only (existing symbol, no websocket.py edit) to route to the same fence the WS handler uses rather than duplicating the terminal-status DB query. Consistent with "thin wrapper over the SAME seams".

## Known Stubs
None — every endpoint is wired to a live store/cancel seam; no placeholder/empty-data paths.

## Next Phase Readiness
- Up-channel REST commands are live and additive; FE SSE transport (29-07) can now route `sendCommand` to these endpoints while `/ws/chat` remains the untouched fallback.
- DEFERRED-to-live: no live-Bedrock/end-to-end run was exercised (offline discipline). The full paused-run resume→engine-resume behavior (gate resolve → agent resumes; cancel → `pipeline_cancelled` on the wire; clarify resume) is proven at the seam level here and covered end-to-end by the WS suites; a consolidated live pass at milestone end confirms the through-path.

## Self-Check: PASSED

- Files: run_commands.py FOUND, test_rest_gate_commands.py FOUND, test_rest_answers_cancel.py FOUND, main.py FOUND.
- Commits: 04f4ccf0 FOUND, 39deaa32 FOUND, b23766d5 FOUND.

---
*Phase: 29-transport-cutover-chat-backbone-a1*
*Completed: 2026-07-08*
