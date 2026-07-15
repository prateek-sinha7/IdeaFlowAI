# Phase 44: SSE-only Hard Cutoff · run_revision Retirement · Part-B Live Automation

**Gathered:** 2026-07-15  ·  **Milestone:** v2.0 (Universal Run Chat & VelocityAI UI Convergence)  ·  **Branch:** `feat/ui-2`
**Status:** SUPERVISED — mostly offline code (FE rewire + BE relocation + tests), with a live SSE smoke + a live-Bedrock re-confirm lane at the end. **v2.0 milestone close is a SEPARATE later step** (user decision) — this phase does NOT run `/gsd-complete-milestone`.
**Supersedes:** **Phase 43-09** (the deferred WS→SSE deletion + close plan) — re-scoped from "delete the flag branch" to a **HARD cutoff** (remove the `NEXT_PUBLIC_SSE_TRANSPORT` flag entirely; SSE the sole, non-flagged transport). Mark 43-09 superseded-by-44 in ROADMAP at plan time.

> **How this CONTEXT was produced.** Six parallel discovery/research agents read the current `feat/ui-2` source end-to-end (FE send-sites + BE `/ws/chat` handlers + REST/SSE twins + the flag surface + the e2e harness + the Part-B code + the planning docs/register). Every file:line below was read directly by an agent; the load-bearing `run_revision` claims (the `planner: skip` PPT-only split, REST `/revisions` → same `_handle_revision`, the two pre-existing FE bugs) were **independently orchestrator-verified**. Treat the findings as grounded.

---

## 0. Orientation — the six settled decisions

1. **New Phase 44** (this phase), supersedes 43-09. **v2.0 milestone close is a separate later step** — NOT in this phase.
2. **HARD cutoff** — remove the `NEXT_PUBLIC_SSE_TRANSPORT` flag (FE) + `SSE_TRANSPORT_ENABLED` (BE) entirely; SSE is the sole transport; delete `/ws/chat`.
3. **`/ws/handoff` STAYS** — `backend/app/api/websocket_handoff.py` (`@router.websocket("/ws/handoff/{token}")`, registered `main.py:195`) is a D10 "live survivor" (the external IDE surface, guarded by `test_handoff_contract.py`). It is a SEPARATE module and was NEVER in the CHAT-07 deletion scope. Do NOT touch it.
4. **Retire `run_revision`** via **Strategy A** — rewire `handleRevisePpt` to REST `POST /api/runs/{id}/revisions` (the byte-twin of the same `_handle_revision`), preserving full parity; then delete the WS `run_revision` handler + `_handle_revision`'s WS driver + its WS tests.
5. **Refinement UX = confirm-first** — a settled-run change request in chat shows a **"Run a refinement with this change?" confirm chip**; the `*_revision` run launches only after the user confirms (replaces today's auto-launch at `RunChatLane.tsx handleFreeText → onRevise`).
6. **Part-B live re-confirms = a scripted live-smoke suite** (reuse the existing `--project=live` Playwright + `RUN_LIVE_BEDROCK` pytest harnesses) that the operator runs with `aws sso login`.

**The load-bearing reality (why this is bigger than "delete /ws/chat"):** the backend REST/SSE twin was fully built additively in Phase 29 — **the gap is almost entirely FRONTEND still emitting WS frames**, plus one structural fact: the pipeline down-channel is WS-only today. This phase is a FE-rewiring + BE-relocation project, verified end-to-end below.

---

## 1. The grounded reality (verified)

**R1 — The pipeline down-channel is WS-only.** `frontend/src/app/dashboard/page.tsx:877-918`: the pipeline reducer (`handlePipelineMsg`) is fed EXCLUSIVELY by `useWebSocket`; `runConnection.subscribe` (SSE) feeds ONLY the chat transcript (`useRunChat`). ⇒ Deleting `useWebSocket` WITHOUT first re-sourcing the pipeline reducer from the SSE fan-out breaks **all** `agent_*`/`wave_*`/`pipeline_*` events. **This is the prerequisite for everything else (W1).**

**R2 — Gate / cancel / revision are un-flagged WS (raw `send`).** They are NOT flag-selected — WS is their ONLY transport today, so a hard cutoff breaks HITL gates, cancel, and revision until rewired:
- Gate actions `approve_review` (approve+`edited_content` / reject / redo+`instructions` / update_specs): `dashboard/page.tsx:1496,1499,1506,1517`.
- Cancel `cancel_pipeline`: `DashboardLayout.tsx:1234,1328` (WS is connection-scoped — no run_id in the frame; REST `/cancel` needs the run_id threaded).
- Revision `run_revision`: `DashboardLayout.tsx:502`.

**R3 — `websocket.py` cannot be deleted wholesale.** It is imported by 6 modules (`run_commands.py`, `run_files.py`, `capabilities.py`, `run_stream.py`, `main.py`, and the SURVIVING `websocket_handoff.py`). Symbols that MUST survive the endpoint deletion (relocate to a transport-neutral module, e.g. `app/api/run_engine.py`): `_PIPELINE_QUEUES`, `_PIPELINE_TASKS`, `_CANCEL_EVENTS`, `_get_or_create_queue`, `_cleanup_pipeline`, `_register_resume_queue`/`_register_resume_task` (wired to the engine at `main.py:141-144`), the `_handle_workflow_execution`/`_handle_revision_execution` drivers, and the ingress validators/helpers used by REST (`_validate_images`, `_validate_model_overrides`, `_resolve_owned_parent_run_id`, `_review_gate_owned_by`, `_review_gate_run_is_terminal`, `_revalidate_selections_trust_user`, `_get_db`) + the auth helpers the handoff WS reuses (`_authenticate_token`, `_get_db`). ⇒ The cutover DELETES the `websocket_chat` receive-loop endpoint + `/ws/chat` route + WS framing/drainer; it RELOCATES the shared infra. `main.py:22,190` (mount `websocket_router`) is removed; `restore_non_terminal_runs()` startup wiring (`main.py:141-145`) must keep working.

**R4 — Two partially-broken FE SSE seams (verified from code, not executed):**
- **Questionnaire-over-SSE 422**: `useWorkflow.ts:152-168` posts to `/messages` a payload with NO `message_id`, which `MessageCommand` requires (`run_commands.py:335`) → 422. (Fix: add `message_id`, or retarget `POST /{id}/answers`.)
- **Launch→attach bootstrap missing**: `POST /api/runs` returns `{run_id}` but `RunConnectionProvider.sendCommand` discards it (`:275-292`, returns void), and nothing triggers an SSE attach for the new run — `reattach()` has ZERO callers; the provider attaches only on boot/visibility/online (`:220-247`). ⇒ A run launched after boot never streams live until a refresh bump. (Fix: capture the run_id + trigger attach after launch.)

---

## 2. Workstreams (one phase, sequenced waves)

### W1 — Re-source the pipeline down-channel from SSE (THE PREREQUISITE) [FE]
Feed the pipeline reducer (`handlePipelineMsg`, `dashboard/page.tsx:488`) from `runConnection.subscribe` (the SSE fan-out) instead of `useWebSocket` (`:877-881`). Implement the **launch→attach bootstrap** (R4): capture `{run_id}` from `POST /api/runs` and trigger an SSE attach (wire `reattach()` — currently zero callers). Re-source `connectionStatus`/`reconnect` (dashboard `:877` + the `reconnect_pipeline` effect `DashboardLayout.tsx:613-645`) from `runConnection.phase`. **Nothing else can be verified over SSE-only until W1 lands.**

### W2 — Rewire the un-flagged WS commands to REST [FE (+1 BE gap)]
- **Gate actions** → `POST /{id}/gate` (`run_commands.py:162`), NOT `/messages`. Rationale (WR-03, verified): the `/messages` `CHANNEL_GATE` branch DROPS `edited_content` — `Dispatch`/`ChatTurn` has no such field (`chat_router.py:164-175`), `post_message:851` calls `set_review_response` without it. Only `POST /{id}/gate` carries `edited_content` (`:239`). Build a FE `api.ts` `/gate` helper (none exists — grep confirms zero FE callers of `/gate|/answers|/cancel|/revisions`). *(Backend gap ONLY if you instead route gates through `/messages`: thread `edited_content` through `ChatTurn`/`Dispatch`/`route_chat_turn` + `post_message` CHANNEL_GATE — avoid this; use `/gate`.)*
- **Cancel** → `POST /{id}/cancel` (`run_commands.py:282`), threading the run_id (WS was connection-scoped).
- **Questionnaire** → fix the R4 422 (add `message_id` to the `/messages` payload, or target `POST /{id}/answers` `:249`).
- **Revision** → see W3 (Strategy A).

### W3 — `run_revision` retirement (Strategy A) + confirm-chip UX + 2 bug fixes [FE + BE + tests]
**Verified mechanism:** `_handle_revision` is a PPT-only server-seeded revision path (`planner: skip` for `ppt_revision`/`od_ppt_revision`; the guard at `engine.py:5246` REJECTS `planner: run` types). REST `POST /api/runs/{id}/revisions` (`run_commands.py:1536`) is a byte-twin: `_mint_revision_row` + `_drive_revision_to_queue` → the SAME `engine._handle_revision`. It preserves: server-side artifact seed from `ScopedStore` (`engine.py:5131` FR-014 fallback chain), planning-context prepend (`:5192`), the exact-kind `derived_from` lineage write (`:5302-5331`), and a clean `run.input`.
- **Strategy A:** rewire `handleRevisePpt` (`DashboardLayout.tsx:493-510`) off the WS `run_revision` frame → a NEW FE `POST /{id}/revisions` fetcher (build in `api.ts`). Event consumption for the returned `run_id` is FREE here — W1 already makes the SSE stream the sole transport, so the new run streams over SSE like any other.
- **Fix 2 pre-existing bugs** (verified, independent of the rewire but close them here): (a) `od_ppt_revision` is ABSENT from `activeReviseHandler` (`DashboardLayout.tsx:1265-1270`) → re-revising a settled od_ppt resolves to `undefined`; add it. (b) the PPT fallback omits `source_workflow_run_id` → orphaned runs; the REST rewire supplies `parent_run_id` explicitly (moot under Strategy A, but verify no orphan).
- **Confirm-chip UX (decision 5):** `RunChatLane.tsx handleFreeText` (~:646-655) currently routes a settled-run change request straight to `onRevise` (auto-launch). Change to show a **"Run a refinement with this change?" confirm chip**; only on confirm does it call the revise handler. Keep the classifier GENERIC (INV-1 — no workflow-name literal).
- **Delete** (INV-12 — the retirement): the FE `run_revision` send, the BE `run_revision` WS handler (`websocket.py:1279`) + `_handle_revision_execution`'s WS driver, and the WS-only revision tests (`test_run_revision_ws_dispatch.py`, `test_ws_parent_link_ownership.py` — folded into `test_rest_revisions.py`). Flip migration-ledger row **D1** (`run_revision` retired). KEEP `engine._handle_revision` (REST `/revisions` uses it). Retire `test_revision_intelligence.py` only where it drives the WS path.

### W4 — Relocate shared infra + delete `/ws/chat` + remove the flag [BE + FE]
- **Relocate** the R3 transport-neutral symbols out of `websocket.py` into `app/api/run_engine.py` (or similar); update the 5 non-handoff importers.
- **Delete** the `/ws/chat` endpoint + WS framing/drainer + `frontend/src/hooks/useWebSocket.ts` + its consumers (`dashboard/page.tsx:877`, the VESTIGIAL dead `/workflow` connection at `workflow/page.tsx:32` + `WorkflowView.tsx:89`) + `env.ts:38-46,70` `resolveWsUrl`/`WS_URL`.
- **Remove the flag (decision 2):** `env.ts:59-64,76` `resolveSseTransport`/`SSE_TRANSPORT`; `RunConnectionProvider.tsx:185` `enabled` → always true (collapse all `if(!enabled)` guards `:194,220-224,230,295-296,306`); `useWorkflow.ts:125,163` (delete the WS else-branches); `dashboard/page.tsx:904,910,938` (collapse `sseEnabled`, delete `chatWsSubscribe:135` + `legacyChatSend:921`); BE `config.py:126` `SSE_TRANSPORT_ENABLED` + `run_stream.py:220-224` 404 guard.
- **KEEP** `websocket_handoff.py` / `/ws/handoff` (decision 3).

### W5 — e2e harness → SSE + CI banned-pattern gate [tests]
- The mocked Playwright harness mocks WS: `mockWs.ts` (auto-fixture `test.ts:38-44`, `page.routeWebSocket(/\/ws\/chat/)`), coupled via the page-object `dashboard.ts:58` (`ws.ready()`) + `:99` (`waitForClientFrame("run_pipeline")`). `mockSse.ts` EXISTS but lacks pipeline helpers + up-channel capture.
- **Build:** grow `mockSse` to full pipeline-helper parity (move `mockWs.ts:194-287` helpers onto the SSE tail — the seq/envelope machinery is already shared); a REST command mock (`page.route` for `POST /api/runs` + `/{id}/{messages,cancel,answers,gate,revisions}`) replacing `mockWs.sent`/`waitForClientFrame`; re-point `dashboard.ts:58,99`; swap the `test.ts` fixture. Then upgrade `ts-sse*.spec.ts` to drive the MOUNTED app (drop the synthetic `fetchSse` consumer).
- **Migrate the BE WS tests to REST** (table in §5): `test_pipeline_cancel.py`→`test_rest_answers_cancel.py` (retires the LV-01 `wait_for` flake), `test_run_revision_ws_dispatch.py`→`test_rest_revisions.py`, the `test_image_ws_ingress.py` WS half→REST, `test_pipeline_failure_semantics.py` WS half→REST; **DELETE** `test_ws_reconnect_replay.py` (superseded by `test_sse_stream.py` + `test_attach_replay_matrix.py`); **KEEP** `test_wire_parity.py` (the cutover parity oracle — SSE frames must stay byte/event-identical to the frozen WS goldens).
- **CI banned-pattern grep gate** (mirrors R15): FAIL if `/ws/chat`, `routeWebSocket`, `useWebSocket`, `NEXT_PUBLIC_SSE_TRANSPORT`, or `SSE_TRANSPORT_ENABLED` reappear — the machine-checkable "hard cutoff done."

### W6 — Part-B live-smoke automation [tests — scripted live-smoke, decision 6]
Two lanes (run with `aws sso login`, Bedrock profile `hex-ai-fe`, QA `qa-enterprise@flowinqa.com`):
- **Lane A — backend live pytest:** `RUN_LIVE_BEDROCK=1 pytest tests/agents/test_phase3_token_delta_live.py tests/agents/test_phase8_live.py` (covers **ISS-003** + **ISS-011** as-is; both self-skip on expired creds). **Build one new opt-in live pytest** (model on `test_phase3_token_delta_live.py`'s dual-gate) that drives a real prototype run and asserts (i) `pipeline_complete` totals include the SmartPlanner+clarify aux tokens vs a planner-skipped baseline (**ISS-033** count-delta A/B) and (ii) `cache_read>0` on a warm turn.
- **Lane B — FE live Playwright** (`--project=live`, `e2e/fixtures/live.ts`): one new `*.live.spec.ts` that logs in via `loginLive`, drives one short real run over SSE, asserts **B.6b** (CompletionToast + bell badge), **P16 SC2** (Stop→cancelled), and — only if the button is reachable — **ISS-027**.
- **Offline additions:** a new **mocked-SSE B.6b spec** (no existing coverage; notifications are transport-agnostic — derived from `pipelineState` `DashboardLayout.tsx:372-414`, so a mocked-SSE drive to `pipeline_complete` + assert toast/badge fully covers it); optionally an **ISS-033 engine-fold offline test** (assert planner/clarify aux tokens reach `pipeline_complete` totals — the one offline gap, `engine.py:2474-2482`).
- **Nuances:** ISS-027 "Skip all" button was REMOVED from the inline lane (`InlineClarifyActions.tsx:18-20`; test asserts absent) — confirm reachability; if gone, ISS-027 collapses to the API-level force-proceed (offline-proven `test_execution_engine.py:192`). P16 SC1 (`ValidationException→pipeline_failed`) can't be forced live on demand → keep offline-definitive (`test_engine_runner_error_arm.py`) + opportunistic-live. ISS-004 is offline-definitive (`test_chunk_sanitizer.py`).

---

## 3. Locked decisions & invariants (do NOT violate)
- **LOCK-B — now SATISFIED.** The register (L2736/L2789) deferred the `/ws/chat` deletion to "a separate, supervised follow-up **after a human validates the live cutover**." That human-validated cutover is `43-LIVE-EVIDENCE.md` (B.3 + the rest PASS on real Bedrock). **Phase 44 IS that sanctioned follow-up** — record this to discharge the LOCK-B precondition.
- **INV-3** — the 5 characterization goldens stay byte/event-identical; **re-run all 5 + `test_wire_parity.py` after the deletion** (the SSE frames must still match the frozen WS goldens). The cutover changes transport, not engine bytes.
- **INV-12** — the `/ws/chat` deletion + `run_revision` deletion ARE the exit gates (remove the sanctioned Phase-29 WS/REST duplication + the legacy revision path). No dual implementation survives.
- **INV-13** — deepagents runtime unchanged (`create_deep_agent` only in `deep_agent_runner.py`).
- **Additive migrations (Q3)** — this phase is deletion + FE rewire + tests; **add NO migration** (chain stays at `0025`).
- **Ship path** — integrate via `dev` (never main/staging); merge `dev` INTO `feat/ui-2` first for a clean MR.
- **SC-001 / INV-1** — the confirm-chip classifier keys on generic state, no workflow-name literal.
- **Deferred BEYOND v2.0 (LOCK-E — record as carried, do NOT build/close here):** team-sharing (ND-12), resume-from-failed (ND-4), per-agent prompt-override persistence (ND-7), image-persistence-on-reopen (ND-10), notifications reload-survival, the Handoff screen (post-v2.0).

---

## 4. Deferred items folding in (reconcile at plan/close time)
- **Resolved/closed by prior phases — record:** DEF-43-03-1 (narrator, commit `8badaa1c`), DEF-29-09-1 + DEF-30-03-1 (steering + per-turn images, 43-05), ISS-033 helper BUILT (43-04) — the narrow tail = its live count-delta (W6). WR-02 nonce done (`0025`).
- **Addressed by this phase:** WR-03 (`edited_content` — avoided by routing gates through `/gate`, not `/messages`); the launch→attach + questionnaire-422 FE seams (W1/W2); the `run_revision` retirement (D1/CTX-04 — the product decision is now MADE = retire, Strategy A); the C.3 gate-approval WS finding + e2e-harness-mocks-WS finding (43-LIVE-EVIDENCE) = W2/W5.
- **Info-level (touch opportunistically, NOT cutoff blockers):** IN-01 (`SSE_STREAM_IDLE_TIMEOUT_SECONDS` declared+never read, `config.py:135` — enforce in `_iter_sse_frames` or delete), IN-02 (`_gate_is_pending` reaches `store._resume_events` private dict, `run_commands.py:145` — add a public accessor). KAN-101 base-thread replay is an engine-checkpoint concern, orthogonal to transport — do NOT block on it.
- **ISS-037** (Phase-31 MED/LOW advisory cluster) — stays OPEN, opportunistic; do NOT gate on it.
- **Register/deferred sweep + `/gsd-complete-milestone`** — deferred to the SEPARATE later milestone-close step (decision 1), NOT this phase.

---

## 5. Backend WS-test migration table (from the test-surface agent, verified file:line)
| Test | WS coupling | Action | SSE-equivalent |
|---|---|---|---|
| `test_pipeline_cancel.py` (`FakeWebSocket`:74; LV-01 flake `:203`) | cancel ack via fake WS | **Migrate → REST** | YES — `test_rest_answers_cancel.py` |
| `test_run_revision_ws_dispatch.py` (`_ScriptedLoopWebSocket`:534) | revision dispatch via fake WS | **Migrate → REST** (+ W3 delete) | YES — `test_rest_revisions.py` |
| `test_image_ws_ingress.py` (`_FakeWebSocket`:32) | run-entry image via WS | **Migrate WS half → REST** | PARTIAL — `test_run_message_images.py` + in-file REST cases |
| `test_pipeline_failure_semantics.py` (`_FakeWebSocket`:389) | terminal + `missing_template_context` guard | **Migrate → REST** (verify the ingress-guard has a REST-path test — gap candidate) | PARTIAL |
| `test_ws_reconnect_replay.py` (`_ScriptedLoopWebSocket`:328) | `reconnect_pipeline` `after_seq` | **DELETE** | YES — `test_sse_stream.py` + `test_attach_replay_matrix.py` |
| `test_wire_parity.py` | SSE projection == frozen WS goldens | **KEEP** — the parity oracle | it IS the gate |
| `test_attach_replay_matrix.py` / `test_sse_stream.py` | drive `GET …/events/stream` | **KEEP** — target-state suites | — |

Reconnect/replay PARITY is verified (durable replay from cursor; `review_gate_ready` re-arm is MORE explicit on SSE — `run_stream.py:166-181`; dedup by `event_id`; JWT silent refresh). Revision `section`-pin is NOT a gap (the pipeline reducer routes by `agent_id`, not `section`).

---

## 6. Definition of done / verification
- **W1–W4 offline:** `cd frontend && npx tsc --noEmit` clean; the re-pointed mocked Playwright suite green (the ~132 formerly-WS specs now SSE-driven); `cd backend && python3.11 -m pytest` targeted parity/gate suite green (`test_wire_parity.py`, `test_sse_stream.py`, `test_attach_replay_matrix.py`, the REST suites) + the 5 characterization goldens byte-identical; `lint-imports` 4/0; the **CI banned-pattern gate** passes (no `/ws/chat`, `useWebSocket`, `routeWebSocket`, `NEXT_PUBLIC_SSE_TRANSPORT`, `SSE_TRANSPORT_ENABLED`).
- **Live smoke (end of phase, needs Bedrock SSO):** with `/ws/chat` gone, a real run launches via `POST /api/runs`, streams `pipeline_start → agent_* → pipeline_complete` over `GET /api/runs/{id}/events/stream`, a deliverable renders, gate approve/reject/redo works over REST, cancel resolves, a PPT revision runs via REST `/revisions`, the Concierge answers, and the W6 Lane-A/B suites pass.
- **must_haves:** the pipeline down-channel + all commands ride SSE/REST only; `/ws/chat` + `useWebSocket` + the flag are DELETED (grep-proven); `/ws/handoff` untouched; `run_revision` retired with PPT revision parity preserved (Strategy A); the confirm-chip gates refinement launches; goldens + wire-parity green; the Part-B tail is an automated two-command re-confirm.

## 7. Prerequisites & session flow
1. Confirm the stack (offline waves need no Bedrock; the live smoke + W6 Lane-A need `aws sso login` / `hex-ai-fe`, uvicorn `:8000` python3.11, `next dev`, alembic at `0025`, QA login).
2. **W1 first** (re-source pipeline from SSE — the enabler), then W2 (rewire commands) + W3 (`run_revision` + confirm chip) in parallel where files are disjoint, then W4 (relocate + delete + de-flag), with W5 (tests) tracking each wave. W6 (Part-B automation) is independent and can run alongside.
3. Offline-verify each wave (tsc · mocked Playwright · targeted pytest · 5 goldens · wire-parity · lint 4/0 · banned-pattern gate); commit atomically (no trailer, `feat/ui-2`, no push).
4. End-of-phase live smoke + W6 lanes with recorded evidence. **Do NOT run `/gsd-complete-milestone`** — that is the separate later close step.

---

*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto · CONTEXT gathered 2026-07-15 from 6 grounded discovery agents + orchestrator spot-checks.*
