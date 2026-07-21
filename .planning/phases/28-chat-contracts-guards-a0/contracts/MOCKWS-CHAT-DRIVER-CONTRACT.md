# mockWs E2E Chat-Driver Contract

**Phase 28 (A0) test-harness surface for RUNUI-05 ("mockWs chat driver in use").**
**Authority:** POR D-01 (the three new chat event types) + POR §3 LOCK-B (transport ADDITIVE-ONLY) in `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`, pinned against the live frame shape in `frontend/e2e/fixtures/mockWs.ts` (its header `INBOUND FRAME CONTRACT` block). This document specifies the NEW chat driver as an **additive extension of the existing `MockWs` controller** — not a rewrite. Phase 31 implements it; the 123 existing mocked specs must stay green.

> Transcribed from the locked POR + the live `mockWs.ts` frame contract — no decision is re-derived or re-opened (mode: yolo / skip_discuss, per the AUTONOMOUS-RUN DECISION LOCK, POR §3). This is a contract; no TypeScript implementation is inlined here.

---

## 1. The frame envelope (unchanged — inherited from `MockWs`)

Every chat frame the driver emits uses the SAME envelope every existing `MockWs` frame uses, verified against the `mockWs.ts` header and its private `emit(type, data)` method:

> `{ type, data: { ...payload, event_id, seq } }`

| Envelope field | Type | Source in `MockWs` | Role |
|---|---|---|---|
| `type` | string (top-level) | the frame's event-type discriminator | dispatch key the app reads first |
| `data` | object | wraps the payload | every payload field lives under `data` |
| `data.event_id` | string (e.g. `evt-42`) | `nextEventId()` → `evt-${GLOBAL_EVENT_ID}` | **dedup key** — read at the TOP of the app handler |
| `data.seq` | number (monotonic) | the controller's `seq` counter, `+1` per emit | **resume cursor** — read at the TOP of the app handler |

The chat driver MUST reuse the existing controller's `seq` counter and `nextEventId()` / `GLOBAL_EVENT_ID` so chat frames interleave with pipeline frames on one monotonic sequence. It MUST NOT introduce a second envelope, a second seq space, or a top-level payload (only the legacy `stream` frame carries top-level `chunk`/`section`; chat frames do NOT). Dedup and the resume cursor continue to read `data.event_id` (string) + `data.seq` (number) exactly as today.

---

## 2. The chat frame catalogue (POR D-01)

The driver must be able to emit the three new chat event types. Each is a normal `MockWs`-envelope frame — payload fields listed live under `data`.

### 2.1 `chat_message` — the user-turn echo

The server echo of a user turn back onto the family-anchored transcript (D-02). The driver scripts it to confirm the app renders the sent turn.

| Payload field (under `data`) | Type | Meaning |
|---|---|---|
| `message_id` | string | the **client-generated** message id the app sent on the outbound command (idempotency key; echoed back so the app can reconcile optimistic render) |
| `text` | string | the user's message body |
| `attachments` | array | `[]` by default; per-turn image/file refs (payload-transient — see ND-10 "image not retained" placeholder, LOCK-E) |
| `run_id` / `thread_id` | string | the anchoring run/thread (thread-id policy resolved in Phase 29, ND-11) |

### 2.2 `chat_reply` — narrator result cards

The narrator's projection of a run milestone into a chat card (clarify / gate / pipeline / deliverable). Carries the deep-link nonce seam so a card can link to the milestone it reports.

| Payload field (under `data`) | Type | Meaning |
|---|---|---|
| `message_id` | string | server-assigned reply id |
| `card_kind` | string | one of `clarify` \| `gate` \| `pipeline` \| `deliverable` (milestone-card discriminator; a `spec_revision` card is added in Phase 29 for KAN-101 loop-backs) |
| `text` | string | the narrator's card body |
| `deep_link` | object | `{ target, nonce }` — the consume-once deep-link seam (nonce is single-use) linking the card to its milestone/artifact |
| `run_id` / `thread_id` | string | anchoring ids |

### 2.3 `stream_attached` — the reconnect handshake (replaces `pipeline_reconnected`)

The new chat/stream reattach handshake. It supersedes the legacy `pipeline_reconnected` frame (which the current `MockWs.reconnected()` emits with `{ live, status, replayed_through_seq }`). The chat driver models `stream_attached` with the same replay semantics.

| Payload field (under `data`) | Type | Meaning |
|---|---|---|
| `live` | boolean | whether the stream is now live (true) or still catching up (false) |
| `replayed_through_seq` | number | the `seq` the server replayed up to — the app resumes its cursor from here (mirrors `pipeline_reconnected.replayed_through_seq = this.seq`) |
| `run_id` / `thread_id` | string | anchoring ids |

`stream_attached` reuses the existing `seq` cursor so a reattach after `drop()` replays deterministically. It does NOT remove `pipeline_reconnected` — the legacy frame path stays for the existing pipeline specs (additive, LOCK-B).

---

## 3. Driver methods (mirroring the existing `MockWs` shape)

The chat driver adds methods to `MockWs` (or a thin `MockWs`-owned mixin) that follow the existing helper idioms (`start()`, `reviewGateReady()`, `reconnected()`, `waitForClientFrame()`). Signatures are described, not implemented.

| Method (described) | Direction | Behavior |
|---|---|---|
| `chatMessage({ messageId, text, attachments? })` | server → page | emit a `chat_message` echo frame via the shared `emit()` (auto event_id/seq). Mirrors `agentComplete()`-style helpers. |
| `chatReply({ cardKind, text, deepLink?, messageId? })` | server → page | script an inbound `chat_reply` narrator card. Default `attachments`/`deep_link` optional. |
| `streamAttached({ live, replayedThroughSeq? })` | server → page | emit the `stream_attached` handshake; `replayedThroughSeq` defaults to the current `seq` (same default as `reconnected()`). A **replay helper**: after `drop()`, re-attach and assert the app resumes from the cursor. |
| `waitForChatCommand(predicate?)` / assert-outbound | page → server | assert an **outbound POST-shaped chat command** was sent. Reuses the existing `waitForClientFrame` / `sent[]` machinery: under mocked e2e the app still drives its command through the same controller socket (Phase 29 REST-up is additive per LOCK-B — the mocked harness models the command as a frame the controller captures, not a real HTTP POST). |

The driver reuses the controller's connection tracking (`connectionCount`, `ready()`, `_attach`), the `sent[]` outbound log, the `waiters` machinery, and `drop()` / `expireJwt()` — no parallel connection state.

---

## 4. Transport constraint — ADDITIVE-ONLY (LOCK-B)

LOCK-B (POR §3, overrides D-13 deletion timing): the chat driver is **ADDITIVE-ONLY**. It:

- **Keeps** the existing `/ws/chat` frame path and every existing helper working — the driver does NOT remove or rewrite the WS frame contract, does NOT arm any deletion ratchet, and does NOT touch `useWebSocket.ts`.
- **Adds** the three chat frames + their helpers ALONGSIDE the pipeline frames on the same controller, same envelope, same seq/event_id counters.
- Models the Phase 29 SSE+REST chat backbone as **additive** — the mocked harness continues to deliver both legacy pipeline frames and the new chat frames through one controller. WS deletion + the INV-12 single-chat-subsystem exit gate are a **deferred supervised follow-up**, not this driver's concern.

Wire-parity is still required downstream (SSE ≡ WS frame sequences, Phase 29 exit), but this contract only pins the mocked-driver surface.

---

## 5. Preservation constraint — the 123 mocked specs stay green

The chat driver is **additive to `MockWs`**, so the existing e2e suite is untouched:

- It reuses the single `seq` counter and `nextEventId()` / `GLOBAL_EVENT_ID` — no renumbering of existing frames.
- It reuses the one connection (`connectionCount`, `_attach`, `ready`) — no second socket that would change reconnect-counting specs.
- It adds new emit helpers and new outbound-assert helpers WITHOUT changing the signature or behavior of any existing helper (`start`, `agent*`, `wave*`, `subagent*`, `reviewGate*`, `questionnaire*`, `reconnected`, `drop`, `expireJwt`).
- `pipeline_reconnected` stays; `stream_attached` is added beside it.

Consumer: **RUNUI-05** ("mockWs chat driver in use") — Phase 31/32 write their chat specs against this contract. The 123 existing mocked specs must remain green after the driver lands (additive-extension acceptance bar).
