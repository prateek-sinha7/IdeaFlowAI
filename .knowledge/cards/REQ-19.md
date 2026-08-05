---
id: REQ-19
type: req
status: done
area: [sse]
summary: >-
  Chat Channel (Phases 28–29)
source: .planning/REQUIREMENTS.md#chat-channel-phases-28-29
---

### Chat Channel (Phases 28–29)

- [x] **CHAT-01**: Chat turns enter via `POST /api/runs/{id}/messages` (idempotent by client `message_id`) and persist as `run_events` rows (`chat_message`/`chat_reply`) through the single stamping boundary — replay, reopen, and owner-scoping inherited; all server→client delivery rides the per-run SSE stream (D-01/D-13); zero new tables
- [x] **CHAT-07**: Transport cutover (D-13) — per-run SSE stream (`Last-Event-ID`=`seq`, `stream_attached` handshake) + REST command endpoints replace `/ws/chat` IN FULL within Phase 29: wire-parity characterization green (SSE ≡ recorded WS frame sequences for the 5 golden pipelines), every inbound-handler test suite ported 1:1 (IDOR/ownership, terminal fences, redo/update_specs, questionnaire, cancel, revision, image caps), `user_message` ported to a POST+stream shim, app-level FE connection provider + server-derived reattach + gate re-arm on restart (D-14), deploy-ordered rollout, then the WS run-handlers + transport flag DELETED with grep ratchets + a ledger row (INV-12); `websocket_handoff.py` + inbound MCP untouched
- [x] **CHAT-02**: Mechanical intent router delivers turns by run state — clarify answer / gate action (approve·reject·redo+instructions·**update_specs** — routing to the shipped KAN-101 spec-revision loop) / steering note / revision — with zero model calls for routable turns; gates treated as event-driven (KAN-94) and fenced on terminal runs (`pipeline_not_running`, KAN-100)
- [x] **CHAT-03**: Steering seam — consume-once `ectx.steering_notes` rendered as a `=== USER GUIDANCE ===` block at the next agent dispatch (redo idiom); sticky (uploads) vs one-shot (directives) semantics
- [x] **CHAT-04**: Narrator `chat_reply` result cards for clarify/gate/pipeline/deliverable milestones, deep-linking into the run tabs
- [x] **CHAT-05**: Family-anchored transcript — turns persist on the active run; FE stitches across parent/child runs via `GET /api/runs/{id}/family`
- [x] **CHAT-06**: Golden neutrality — new event types in `_DOCUMENTED_EVENT_TYPES`, volatile keys in `_VOLATILE_STRIP_KEYS`, characterization proof that chat never fires on golden paths
