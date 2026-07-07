# Phase 29: Transport Cutover + Chat Backbone [A1] - Context

**Gathered:** 2026-07-07
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR + evidence.

<domain>
## Phase Boundary

Two waves. **Wave 1 (transport):** build the per-run SSE stream + REST command endpoints ALONGSIDE the existing `/ws/chat`, behind a transport flag. **Wave 2 (chat backbone):** `POST /api/runs/{id}/messages`, `run_events` persistence, the mechanical intent router, the steering seam, and narrator `chat_reply` cards — on the new transport.

### ⛔ LOCK-B OVERRIDE — READ FIRST (overrides the ROADMAP goal wording)
The ROADMAP goal text says "WS run-path deleted at exit." **THAT IS OVERRIDDEN by the AUTONOMOUS-RUN DECISION LOCK (POR §3, LOCK-B).** For this unattended run Phase 29 is **ADDITIVE-ONLY**:
- Build the SSE stream (`GET /api/runs/{id}/events/stream`, `id:`=`seq`, `Last-Event-ID` resume, `stream_attached` handshake) + REST commands (`POST /api/runs`, `/{id}/messages`, `/{id}/gate`, `/{id}/answers`, `/{id}/cancel`, `/{id}/revisions`) **alongside** `/ws/chat`, behind a transport flag.
- **DO NOT delete the `/ws/chat` run-handlers. DO NOT arm deletion grep-ratchets. DO NOT add a migration-ledger deletion row. DO NOT touch `frontend/src/hooks/useWebSocket.ts` or `websocket_handoff.py`.**
- The WS deletion + INV-12 exit gate are a SEPARATE supervised follow-up after a human validates the cutover live — NOT in this phase.
- **Still required:** the wire-parity characterization — record the WS frame sequences for the 5 golden pipelines (volatile-stripped) and prove the SSE stream replays them IDENTICALLY. This is the binding gate; it is offline-runnable via the scripted harness.

Authoritative inputs (READ — do not re-derive): POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §2 (D-01 rewritten REST+SSE, D-13 transport, D-14 resilience), §3 (⭐ DECISION LOCK — LOCK-B additive, LOCK-C no-checkpoints, ND-11 seam unification), §6 (contract list), §7 (landmines). Evidence: `03-backend-chat-surface-map.md` (WS transport + full event taxonomy + gate/clarify/redo seams + run_events + landmines + its CORRECTIONS addendum), `07-synthesized-contracts.md` (D-12 live-state table), `04-frontend-anatomy.md` (useWebSocket, mockWs — its CORRECTIONS addendum). Phase-28 contracts: `.planning/phases/28-chat-contracts-guards-a0/contracts/` (LIVE-STATE-CONTRACT.md, MOCKWS-CHAT-DRIVER-CONTRACT.md, RESOLVED-DECISIONS.md).
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3; do NOT re-open)

- **Additive transport (LOCK-B, above).** No deletion this run.
- **Mechanical router (D-04):** keys on run state → clarify answer / gate action (approve·reject·redo·**update_specs** — route to the shipped KAN-101 loop) / steering note / revision. Gates are EVENT-DRIVEN not manifest-driven (KAN-94 — a declared gate may not fire when `gate_agent_ids` excludes the agent). `approve_review`/gate on a terminal run is fenced with `pipeline_not_running` (KAN-100). Gate edits persist to the artifact graph but are NOT echoed over the stream (KAN-98 — client retains).
- **Steering seam (D-06 / ND-11):** consume-once `ectx.steering_notes` → `=== USER GUIDANCE ===` block in `_compose_context_message` (the `redo_directive` idiom). ND-11: DECIDE unify-vs-coexist with the two shipped seams (`redo_directive`, KAN-101 `spec_revision_context`) as the FIRST design task; reconcile thread-id policy (Redo forks `:redo{N}`; the KAN-101 sub-pipeline reuses BASE threads — the replay risk to avoid).
- **Persistence (D-01):** chat turns → `run_events` rows (`chat_message`/`chat_reply`, added to the vocab in Phase 28) through the single stamping boundary → seq/event_id replay, owner+workspace default-deny, family-anchored (D-02, `/family`). Zero new tables. Legacy `user_message`/ChatRunner PORTED to a POST+stream shim (its frozen golden drives ChatRunner directly — untouched).
- **Resilience (D-14):** server-derived reattach, `stream_attached {live, replayed_through_seq}` handshake, gate re-arm on restart (re-arm `waiting_for_user` from persisted `gate_events` + re-emit `review_gate_ready`), SSE infra (uvicorn ping, `proxy_buffering off`).

INVARIANTS: SC-001/INV-1 (no kernel workflow-name branch — router/steering key on generic state/event types), INV-3 (5 goldens byte/event-identical — chat/steering dormant on golden runs), INV-13, import-linter 4/0, additive migrations only (Q3; none expected v1).
</decisions>

<code_context>
## Existing Code Insights (from evidence 03/04)

`backend/app/api/websocket.py` (the `/ws/chat` handler, per-run queues `_PIPELINE_QUEUES`/`_PIPELINE_TASKS`/`_CANCEL_EVENTS`, `_handle_workflow_execution`, the drainer, reconnect replay); `backend/agents/execution_engine/engine.py` (the single seq/event_id emit boundary + `_RunEventSink`); `backend/agents/authz.py` (`ScopedStore.append_event`/`read_events`); the four inbound handlers to port to REST (run_pipeline, approve_review [4 actions], submit_questionnaire, cancel_pipeline, run_revision); `frontend/src/hooks/useWebSocket.ts` + `frontend/src/hooks/useWorkflow.ts` (FE adapter to add an SSE path behind the flag — do NOT delete WS), `frontend/e2e/fixtures/mockWs.ts` (+ new mock-SSE driver per Phase-28 contract). `sse-starlette` is already pinned (from MCP work). Offline verify: targeted parity/gate suite + `/opt/homebrew/bin/lint-imports`; full pytest HANGS offline — do not run it.
</code_context>

<specifics>
## Specific Ideas

Wave 1 deliverables: wire-parity characterization golden (SSE ≡ recorded WS frames, 5 pipelines) as the binding gate; `GET /api/runs/{id}/events/stream` off the existing per-run queues + run_events; the 6 REST command endpoints with each inbound-handler test suite ported 1:1 (IDOR/ownership pins, `pipeline_not_running` fences, redo/update_specs payloads, questionnaire, cancel, revision 6-scenario suite, image caps); `user_message` POST+stream shim; FE transport adapter + app-level connection provider + server-derived reattach (D-14 a–e) behind the flag; e2e mock-SSE driver keeping the 123 mocked specs green + new reload/route-change/auto-reconnect specs; attach/replay matrix. Wave 2: `POST /api/runs/{id}/messages` + idempotency; mechanical router; `ectx.steering_notes` + composition; narrator cards. **NO WS deletion (LOCK-B).**
</specifics>

<deferred>
## Deferred Ideas

The `/ws/chat` deletion + ratchets + ledger row (deferred supervised follow-up, LOCK-B). Per-turn image carrier is Phase 30. Team-sharing/resume-from-failed/prompt-override/image-persistence deferred (LOCK-E). Multi-worker (N8) unchanged.

## Execution-viability note (autonomous run)
Wave 1's wire-parity characterization + ported unit suites are offline-runnable (scripted harness). Full integration/live cutover verification needs a running server + interactive SSO — if execution can't verify offline, the phase PARKS at handle_blocker rather than fabricating a pass; the PLAN itself is the guaranteed offline deliverable.
