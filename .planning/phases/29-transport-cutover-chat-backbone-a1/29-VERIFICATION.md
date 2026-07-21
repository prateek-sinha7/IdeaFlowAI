---
phase: 29-transport-cutover-chat-backbone-a1
verified: 2026-07-08T00:00:00Z
status: human_needed
score: 24/24 must-haves verified (offline binding gates); 3 items deferred to live pass (documented, non-blocking)
overrides_applied: 0
human_verification:
  - test: "Mount RunConnectionProvider at the app root (frontend/src/app/layout.tsx) with NEXT_PUBLIC_SSE_TRANSPORT=true, log in, and confirm a live run's SSE stream attaches and survives a route change/reload against a real backend"
    expected: "Connection state machine reaches 'live', dashboard reducer updates identically to the WS path, cursor persists across reload"
    why_human: "RunConnectionProvider.tsx is built, tested via mocked driver, and imported by useWorkflow.ts, but is NOT mounted in app/layout.tsx (documented, out of the plan's LOCK-B allow-list — 29-07-SUMMARY.md). Requires a running server + real browser session to observe live attach behavior."
  - test: "Send a steering-note chat turn on a RUNNING pipeline against a live Bedrock run and confirm the note actually lands in the next agent's composed prompt (=== USER GUIDANCE === block) mid-execution"
    expected: "The next dispatched agent's context includes the steering text; one-shot notes disappear after one dispatch, sticky notes persist"
    why_human: "DEF-29-09-1 (documented in 29-09-SUMMARY.md): the router computes the CHANNEL_STEERING dispatch and chat_router.apply_steering() appends to ectx.steering_notes, and the composition-side rendering in engine.py is proven by offline fault-injection (test_steering_seam.py) — but the LIVE endpoint -> running in-process ectx handle lookup (engine-side drain/re-derivation at the next dispatch) is not wired in this phase (needs an engine.py edit outside the plan's allow-list). Needs a live running pipeline to observe end-to-end."
  - test: "Trigger a clarify / gate / pipeline-complete / deliverable / spec-revision milestone on a live run and confirm a chat_reply narrator card actually appears on the down-channel (SSE or WS) as the milestone fires"
    expected: "A chat_reply run_events row is persisted and delivered live, not just producible by calling project_milestone_card/persist_milestone_card directly in a test"
    why_human: "chat_narrator.py's project_milestone_card/persist_milestone_card are proven correct and golden-neutral via 23 offline unit tests, but are not invoked from any production code path (no call site in the engine, the SSE stream, or the WS drainer) — documented explicitly in 29-10-SUMMARY.md ('Live in-process emission... intentionally OUT of LOCK-B scope... Deferred-to-live'). Requires a live run to confirm the milestone->card wiring once it lands."
  - test: "Run the full mocked Playwright e2e suite (123 specs) and the 12 test_run_pipeline_validation.py cases against feat/ui-2 HEAD to confirm they are still pre-existing failures unrelated to Phase 29"
    expected: "Same ~120/123 and 12/50 failure counts as recorded before Phase 29 touched anything, on the identical untouched files"
    why_human: "DEF-29-06-1 and DEF-29-04-1 are logged as pre-existing feat/ui-2 baseline breakage (dashboard-home redesign; widened custom-agent-pool) — confirmed via git diff showing the failing spec/test files were never touched by any Phase-29 commit. Re-confirming the baseline is a quick sanity check, not a Phase-29 fix obligation."
---

# Phase 29: Transport Cutover + Chat Backbone [A1] Verification Report

**Phase Goal:** wave 1: per-run SSE stream + REST commands built ADDITIVELY alongside `/ws/chat` (wire-parity golden, ported suites, D-14 resilience; WS-deletion DEFERRED to a supervised follow-up per LOCK-B); wave 2: `POST /api/runs/{id}/messages` chat backbone, mechanical intent router, steering seam, narrator cards

**Verified:** 2026-07-08
**Status:** human_needed (all offline/binding gates PASS; three explicitly-documented live-pass items surfaced for follow-up — none are phase-29 regressions or gaps)
**Re-verification:** No — initial verification

**Framing applied:** This phase ran under LOCK-B (POR §3, AUTONOMOUS-RUN DECISION LOCK) — additive-only. Per the launching agent's explicit instruction, WS-non-deletion is the CORRECT outcome (not a gap), live/Bedrock verification is deferred to the milestone-end live pass, and the documented deferrals (deferred-items.md, per-plan SUMMARY "Deferred-to-live" sections) are recorded here as `human_verification` items, not as gaps.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SSE projection replays recorded WS frames IDENTICALLY for all 5 golden pipelines (wire-parity) | VERIFIED | `test_wire_parity.py` 6/6 passed; `characterization/golden/*.wsframes.json` (5 files) present and non-empty |
| 2 | Parity comparator raises on injected drift (non-vacuous gate) | VERIFIED | `test_wire_parity.py` includes an injected-drift assertion test (part of the 6 passing) |
| 3 | GET `/api/runs/{id}/events/stream` streams SSE with `id:`=`seq`, resumable via `Last-Event-ID` | VERIFIED | `backend/app/api/run_stream.py` exists, substantive (12.7KB); `test_sse_stream.py` 15/15 passed |
| 4 | `stream_attached {live, replayed_through_seq}` handshake replays durable tail before going live | VERIFIED | `run_stream.py` implements handshake; `test_sse_stream.py` + `test_attach_replay_matrix.py` cover it |
| 5 | Cross-owner stream request returns 404 (never 403) | VERIFIED | Two-layer owner check in `run_stream.py`; covered in `test_attach_replay_matrix.py` cross-owner scenario |
| 6 | `waiting_for_user` gate re-armed on attach (`review_gate_ready` re-emitted from persisted `gate_events`, D-14g) | VERIFIED | `run_stream.py` gate re-arm logic; `test_attach_replay_matrix.py` restart scenario |
| 7 | SSE stream behind `SSE_TRANSPORT_ENABLED`, built alongside `/ws/chat` | VERIFIED | `backend/app/core/config.py` contains `SSE_TRANSPORT_ENABLED`; `websocket.py` byte-identical (see Key Links) |
| 8 | `POST /api/runs/{id}/gate` resolves all four actions (approve/reject/redo/update_specs) | VERIFIED | `run_commands.py`; `test_rest_gate_commands.py` 15/15 passed |
| 9 | Gate action on terminal run fenced with `pipeline_not_running` (KAN-100) | VERIFIED | Covered in `test_rest_gate_commands.py` + `test_mechanical_router.py` |
| 10 | `POST /api/runs/{id}/answers` submits clarify responses incl. `skip_clarification` | VERIFIED | `test_rest_answers_cancel.py` 9/9 passed |
| 11 | `POST /api/runs/{id}/cancel` cooperative cancel via per-run cancel event | VERIFIED | Same suite, same file |
| 12 | Every command owner-scoped, cross-owner → 404 never 403; `/ws/chat` untouched | VERIFIED | Ownership pins in ported suites; `git diff` shows zero change to `websocket.py` (see Key Links) |
| 13 | `POST /api/runs` launches over REST, minting run + spawning driver on per-run queue | VERIFIED | `test_rest_run_launch.py` 6/6 passed |
| 14 | Image caps enforced on REST launch identically to WS path | VERIFIED | `test_image_ws_ingress.py` (WS side, 6 still green) + REST image tests in `test_rest_run_launch.py` |
| 15 | `POST /api/runs/{id}/revisions` dispatches child run w/ parent_run_id+owner_id, 6-scenario suite | VERIFIED | `test_rest_revisions.py` 10/10 passed |
| 16 | `user_message` ported to POST+stream shim, frozen golden byte-identical | VERIFIED | `test_rest_user_message_shim.py` 5/5 passed; `test_chat_contract.py` golden untouched (not in phase diff) |
| 17 | Seven-scenario SSE attach/replay matrix incl. SC-2 durability proof, all offline | VERIFIED | `test_attach_replay_matrix.py` 12/12 passed |
| 18 | e2e harness drives new SSE transport additively (mock driver) | VERIFIED | `mockSse.ts` + `mockWs.ts` additive methods; `ts-sse.spec.ts` 2/2 passed |
| 19 | FE consumes SSE (fetch+ReadableStream) w/ native Last-Event-ID resume, dedup, REST commands, behind flag | VERIFIED | `useRunStream.ts` substantive (14KB); `useWorkflow.ts` flag branch; `ts-sse-resilience.spec.ts` 4/4 passed; `tsc --noEmit` clean |
| 20 | Connection ownership in app-level provider surviving route changes; server-derived reattach | PARTIAL (built, not mounted) | `RunConnectionProvider.tsx` exists, substantive, imported by `useWorkflow.ts` via `useRunConnection()` — but never mounted in `frontend/src/app/layout.tsx` (confirmed by grep; documented in 29-07-SUMMARY.md as an explicit out-of-allow-list deferral). Recorded as human_verification item #1. |
| 21 | ND-11 resolved in writing FIRST (coexist decision + thread-id policy) | VERIFIED | `ND-11-SEAM-DECISION.md` present, dated 2026-07-08, precedes the 29-08 engine/context commit |
| 22 | `ectx.steering_notes` consume-once queue renders `=== USER GUIDANCE ===` at next dispatch, then clears; sticky vs one-shot | VERIFIED | `context.py:271` `steering_notes` field; `engine.py:6262-6293` composition + clear logic; `test_steering_seam.py` 5/5 passed |
| 23 | Seam name-free (SC-001/INV-1); 5 goldens byte/event-identical (steering dormant) | VERIFIED | `test_banned_patterns.py` 11/11 passed; all 5 characterization goldens 10/10 passed, byte/event-identical |
| 24 | `POST /api/runs/{id}/messages` persists chat_message row, idempotent by client `message_id` | VERIFIED | `test_chat_messages_endpoint.py` 14/14 passed |
| 25 | Mechanical router keys on run state, zero model calls, routes clarify/gate/steering/revision incl. `update_specs`→KAN-101, terminal fence (KAN-100), event-driven gates (KAN-94) | VERIFIED | `chat_router.py` (331 lines, `route_chat_turn` pure function); `test_mechanical_router.py` 25/25 passed |
| 26 | Chat turns persist family-anchored, owner+workspace default-deny | VERIFIED | `run_commands.py` uses `ScopedStore.append_event`; existing `GET /api/runs/{id}/family` endpoint (runs.py:933, pre-existing) unaffected |
| 27 | Narrator `chat_reply` cards emit for clarify/gate/pipeline/deliverable/spec_revision milestones as pure projections | VERIFIED (offline) / PARTIAL (not live-wired) | `chat_narrator.py` (project_milestone_card/persist_milestone_card), 23/23 tests passed — but no production call site invokes these functions yet (grep confirms zero callers outside its own module/test). Documented in 29-10-SUMMARY.md as an explicit LOCK-B deferral. Recorded as human_verification item #3. |
| 28 | `chat_reply` never fires on 5 golden paths; discriminators stable | VERIFIED | All 5 characterization goldens pass; narrator dormant by construction (no call site at all yet) |

**Score:** 26/28 fully VERIFIED; 2 PARTIAL (both are explicitly documented, plan-scoped, LOCK-B-sanctioned deferrals to the live pass — not silent gaps). No truth FAILED.

### LOCK-B Additive Posture (binding invariant)

| Check | Result |
|-------|--------|
| `git diff --stat` across entire phase commit range (`8aadb3b0~1`..`3a296281`) for `backend/app/api/websocket.py`, `frontend/src/hooks/useWebSocket.ts`, `backend/app/api/websocket_handoff.py` | **Empty — zero changes** |
| No migration files added | Confirmed — no `alembic/versions/*` in the 43-file phase diff |
| No deletion ratchets / ledger rows | Confirmed — not present in diff |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/tests/agents/characterization/_sse_projection.py` | run_events→SSE projection | VERIFIED | Exists, exports `project_events`/`run_event_to_sse_frame`/`ws_frame_from_engine_event`/`assert_wire_parity` |
| `backend/tests/agents/test_wire_parity.py` | binding wire-parity gate | VERIFIED | 6/6 passed |
| `backend/tests/agents/characterization/golden/*.wsframes.json` (5) | recorded WS frame goldens | VERIFIED | All 5 present, non-trivial size |
| `backend/app/api/run_stream.py` | SSE endpoint | VERIFIED | 12.7KB, `router` exported, mounted in `main.py` |
| `backend/app/core/config.py` | `SSE_TRANSPORT_ENABLED` flag | VERIFIED | Flag present |
| `backend/app/api/run_commands.py` | REST command endpoints (gate/answers/cancel/launch/revisions/messages) | VERIFIED | 56.6KB, `router` exported, mounted in `main.py` |
| `backend/tests/agents/test_attach_replay_matrix.py` | 7-scenario durability gate | VERIFIED | 12/12 passed |
| `frontend/e2e/fixtures/mockSse.ts` | mock-SSE driver | VERIFIED | Exists, e2e specs pass |
| `frontend/e2e/fixtures/mockWs.ts` | additive chat driver methods | VERIFIED | `streamAttached` present, existing helpers byte-identical |
| `frontend/src/hooks/useRunStream.ts` | SSE transport hook | VERIFIED | 14.3KB, imported by `useWorkflow.ts` |
| `frontend/src/providers/RunConnectionProvider.tsx` | app-level connection provider | VERIFIED (exists/substantive/imported) / ORPHANED (not mounted in app tree) | Imported via `useRunConnection()` in `useWorkflow.ts`; NOT mounted in `layout.tsx` — documented deferral |
| `.planning/phases/.../ND-11-SEAM-DECISION.md` | seam decision record | VERIFIED | Present, precedes implementation commit |
| `backend/agents/execution_engine/context.py` | `steering_notes` carrier | VERIFIED | Field present at line 271 |
| `backend/agents/execution_engine/engine.py` | `=== USER GUIDANCE ===` composition | VERIFIED | Lines 6262-6293 |
| `backend/app/api/chat_router.py` | mechanical router | VERIFIED | 331 lines, `route_chat_turn` exported, pure function |
| `backend/app/agents/chat_narrator.py` | milestone→chat_reply projection | VERIFIED (exists/substantive) / not-yet-invoked in production | `project_milestone_card` exported; zero production call sites (documented deferral) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `test_wire_parity.py` | `_normalize.py` | `_VOLATILE_STRIP_KEYS`/`_canonical_order` reuse | WIRED | Confirmed by passing test |
| `run_stream.py` | `authz.py` | `ScopedStore.read_events` | WIRED | Confirmed by passing test + code read |
| `main.py` | `run_stream.py` / `run_commands.py` | `include_router` | WIRED | `main.py:178,182` |
| `run_commands.py` | `artifact_store/store.py` | `set_review_response`/`set_questionnaire_responses` | WIRED | Confirmed in `test_rest_gate_commands.py` |
| `run_commands.py` | `websocket.py` | read-only import (`_CANCEL_EVENTS`, `_review_gate_owned_by`, `_run_pipeline_to_queue`) | WIRED (read-only, no edit) | Confirmed — `websocket.py` diff is empty |
| `chat_router.py` | `run_commands.py` | dispatch through same command handlers | WIRED | `run_commands.py:408-479` imports `route_chat_turn` and dispatches |
| `chat_router.py` | `context.py` | steering turns → `ectx.steering_notes` | WIRED (offline seam only) | `apply_steering()` present; **live in-process delivery deferred (DEF-29-09-1)** |
| `chat_narrator.py` | `authz.py` | `persist_milestone_card` → `append_event` | WIRED (function-level only) | Function calls `append_event` correctly, proven by unit tests; **no production caller yet invokes `persist_milestone_card`** |
| `useWorkflow.ts` | `useRunStream.ts` | flag-selected transport | WIRED | Confirmed by grep + `tsc` clean |
| `RunConnectionProvider.tsx` | backend `/api/runs` + `/events/stream` | server-derived reattach | WIRED (function-level) / NOT MOUNTED | Provider code correct; not mounted at app root |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|--------------|----------------|-------------|--------|----------|
| CHAT-01 | 29-09 | Chat turns via POST /messages, persist as run_events, SSE delivery, zero new tables | SATISFIED | `test_chat_messages_endpoint.py` 14/14; `run_commands.py` |
| CHAT-02 | 29-09 | Mechanical intent router, zero model calls, KAN-94/KAN-100/KAN-101 routing | SATISFIED | `test_mechanical_router.py` 25/25; `chat_router.py` |
| CHAT-03 | 29-08 | Steering seam, consume-once, sticky/one-shot | SATISFIED | `test_steering_seam.py` 5/5; `context.py`/`engine.py` |
| CHAT-04 | 29-10 | Narrator chat_reply cards, deep-link | SATISFIED (offline) — live-wiring deferred (human_verification #3) | `test_chat_narrator.py` 23/23; no production call site yet |
| CHAT-05 | 29-09 | Family-anchored transcript | SATISFIED | Reuses pre-existing `GET /api/runs/{id}/family` (runs.py:933) + `ScopedStore.append_event` |
| CHAT-07 | 29-01..29-07 | Transport cutover: SSE+REST alongside /ws/chat (LOCK-B: deletion deferred), wire-parity, ported suites, D-14 resilience | SATISFIED per LOCK-B additive scope | All wave-1 suites green; WS byte-identical; deletion explicitly out of this phase's scope by decision lock |

No orphaned requirements — CHAT-06 belongs to Phase 28 (already Complete) and is out of this phase's scope.

### Anti-Patterns Found

None. Scanned all new production files (`run_stream.py`, `run_commands.py`, `chat_router.py`, `chat_narrator.py`, `context.py`/`engine.py` diff, `useRunStream.ts`, `RunConnectionProvider.tsx`, `mockSse.ts`) for `TODO|FIXME|TBD|XXX|HACK|PLACEHOLDER|not yet implemented` — zero hits.

### Offline Binding Gates (executed by this verifier, not taken from SUMMARY claims)

| Gate | Command | Result |
|------|---------|--------|
| Wire-parity + attach/replay + banned-patterns | `pytest test_wire_parity.py test_attach_replay_matrix.py test_banned_patterns.py` | **29 passed** |
| 5 INV-3 characterization goldens | `pytest test_characterization_{prototype,od_prototype,od_ppt,prototype_revision,app_builder}.py` | **10 passed** (byte/event-identical, no SNAPSHOT_UPDATE) |
| import-linter | `lint-imports` | **4 kept, 0 broken** |
| All new Phase-29 unit suites | `pytest test_rest_gate_commands.py test_rest_answers_cancel.py test_rest_run_launch.py test_rest_revisions.py test_rest_user_message_shim.py test_sse_stream.py test_chat_messages_endpoint.py test_mechanical_router.py test_chat_narrator.py test_steering_seam.py` | **127 passed** |
| Pre-existing baseline regression check | `pytest test_image_ws_ingress.py test_run_pipeline_validation.py` | 48/48 image, but 12/50 pipeline-validation cases fail — **confirmed pre-existing (DEF-29-04-1)**, file untouched by phase-29 diff |
| Frontend type-check | `npx tsc --noEmit` | **clean, exit 0** |
| SSE e2e specs | `playwright test ts-sse.spec.ts ts-sse-resilience.spec.ts` | **6/6 passed** |

**Total offline evidence gathered by this verifier: 172 backend tests passed + 6 e2e specs passed + lint-imports 4/0 + tsc clean.** (Consistent with, and independently reproducing, the executor's claimed 187-pass figure; the delta is scope of suites selected for direct re-run vs. full sweep.)

### Deferred / Documented Non-Gaps (per LOCK-B framing — NOT gaps)

| Item | Disposition |
|------|-------------|
| `/ws/chat` run-handlers, `useWebSocket.ts`, `websocket_handoff.py` not deleted | INTENTIONAL (LOCK-B) — confirmed byte-identical across entire phase diff |
| DEF-29-06-1 — 123 mocked Playwright specs mostly red | PRE-EXISTING `feat/ui-2` dashboard-home redesign breakage; confirmed the 3 files touched by 29-06 contain zero `frontend/src/` edits |
| DEF-29-04-1 — 12/50 `test_run_pipeline_validation.py` failures | PRE-EXISTING widened custom-agent-pool; confirmed file untouched by any Phase-29 commit |
| DEF-29-09-1 — steering live in-process delivery | Documented scope-boundary deferral (needs `engine.py` edit outside 29-09's allow-list); seam proven offline; **listed above as human_verification** |
| RunConnectionProvider not mounted in `layout.tsx` | Documented scope-boundary deferral (`layout.tsx` outside 29-07's allow-list); **listed above as human_verification** |
| Narrator not yet invoked from any production code path | Documented scope-boundary deferral (29-10-SUMMARY.md "intentionally OUT of LOCK-B scope"); **listed above as human_verification** |

### Gaps Summary

No genuine phase-29 gaps found. Every observable truth required by the ROADMAP goal and by each plan's `must_haves` is either fully VERIFIED against the actual codebase (26/28) or is a PARTIAL item that the executing plans explicitly, correctly, and consistently documented as an out-of-LOCK-B-allow-list deferral to the milestone-end live pass (2/28: RunConnectionProvider mount + narrator/steering live wiring — grouped as 3 human_verification items above, since steering and narrator share the same "engine-side wiring is a live-pass follow-up" root cause). All offline binding gates (wire-parity, 5 characterization goldens, attach/replay matrix, banned-patterns, import-linter, all ported unit suites, tsc, SSE e2e specs) pass when run directly by this verifier — not merely claimed by SUMMARY.md. The two pre-existing baseline failures (DEF-29-06-1, DEF-29-04-1) are independently confirmed to be untouched-by-phase-29 via `git diff --name-only` over the full commit range.

---

_Verified: 2026-07-08_
_Verifier: Claude (gsd-verifier)_
