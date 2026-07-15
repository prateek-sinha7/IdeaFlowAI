---
phase: 43-concierge-live-wiring-and-live-pass-closure
plan: 01
subsystem: api
tags: [concierge, chat, deepagents, scopedstore, idor, run_events, fastapi]

# Dependency graph
requires:
  - phase: 33-concierge-compaction-a5
    provides: "chat:concierge capability (converse/read-tools/propose_* intents) + the app-layer disposal seam (_dispose_concierge_proposal) behind confirm chips"
  - phase: 29-chat-backbone
    provides: "POST /api/runs/{id}/messages up-channel, ScopedStore owner-scoped run_events, mechanical route_chat_turn (CHANNEL_CONCIERGE)"
provides:
  - "M2: Concierge read tools return plain JSON-safe dicts (_row_to_dict) so the live model gets usable run data, not str() reprs"
  - "M3: the run's CompiledWorkflow is threaded onto _ConciergeCtx.compiled so the manifest chat: block injects into the system prompt"
  - "drain: ConciergeCapability.drain_proposals surfaces converse tool-result proposals, CTX-SCOPED (per-request), concurrency-safe"
  - "H1: confirm turns dispose ONLY from the durable owner-scoped concierge-proposal pending row (IDOR->404); client body locates, never supplies, params"
  - "M1: a missing gate action defaults to request_changes (->redo), never approve"
affects: [43-02-concierge-fe-wiring, part-c-sse-cutover, concierge-live-qa-B3]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-invocation collecting tools + a per-request collector list (never instance/global state) for concurrency-safe capability output capture"
    - "Durable-row confirm disposal: the client body locates an owner-scoped pending row; the trusted intent comes exclusively from that row (IDOR->404, idempotent resolve marker)"
    - "Row->dict serializer at the @tool boundary so ORM rows reach the model as structured field maps"

key-files:
  created: []
  modified:
    - "backend/app/agents/chat/concierge.py"
    - "backend/app/api/run_commands.py"
    - "backend/tests/agents/test_concierge_capability.py"
    - "backend/tests/unit/test_concierge_proposal_channels.py"

key-decisions:
  - "Proposals are captured by per-invocation collecting tools closing over a per-request list, then stashed on the per-request ctx (ctx.proposals); drain_proposals(ctx) is a staticmethod that reads+clears that ctx buffer — NO self-scoped buffer (concurrency mandate)"
  - "The confirm turn reuses the ask turn's message_id so concierge-proposal:{message_id}:{channel} deterministically locates the durable pending row"
  - "The intent disposed on confirm takes its params ONLY from the durable pending row; the client body's channel merely selects the row, and a resolved marker (namespaced event_id) makes replay idempotent"
  - "M1 missing-action default request_changes maps through _CONCIERGE_GATE_ACTION_MAP to the seam's redo (non-consequential)"

patterns-established:
  - "CTX-scoped (not self-scoped) per-request state on a shared/singleton capability"
  - "Durable owner-scoped pending-row lookup for a two-turn confirm-hold (ask -> hold -> confirm)"

requirements-completed: [A.1]

# Metrics
duration: 34min
completed: 2026-07-15
---

# Phase 43 Plan 01: Concierge Backend Defects (M1/M2/M3/H1) + Proposal Drain Summary

**The chat:concierge backend is now offline-correct against POST /messages: read tools return plain dicts, the manifest chat: block injects, confirm disposes only from the durable owner-scoped pending row (IDOR->404), a missing gate action degrades to request_changes, and drain_proposals surfaces held intents CTX-scoped — all with the 5 characterization goldens byte-identical.**

## Performance

- **Duration:** ~34 min
- **Completed:** 2026-07-15
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- **M2** — `_read_tools` routes every ScopedStore result (read_events/list_refs/get_ref/read_gate_events) through a shared `_row_to_dict` serializer, so the live model receives structured field maps (datetimes -> ISO strings; JSON columns already parsed) instead of opaque `<...object at 0x...>` reprs. No raw-ORM path added; scope unchanged (owner-scoped, default-deny).
- **M3** — `_ConciergeCtx` accepts + stores `compiled`; the CHANNEL_CONCIERGE call site resolves the run's `CompiledWorkflow` via `compile_for_run(wr_type)` (DATA only, degrade-safe to `None`), so `_compose_system_prompt` can inject the manifest `chat:` block.
- **drain** — `ConciergeCapability.drain_proposals` surfaces the proposals a `converse` raised. Capture is CTX-SCOPED: per-invocation collecting tools append to a per-request list stashed on `ctx.proposals`; the staticmethod reader clears that same ctx buffer. NO `self.`-scoped buffer — proven by a two-overlapping-`converse` concurrency test.
- **H1** — on a confirm turn, `_load_pending_proposal` locates the DURABLE owner-scoped `concierge-proposal:{message_id}:{channel}` pending row; the disposed intent's params come exclusively from that row, never `body.confirm_proposal`. Missing / cross-owner (store default-deny) / already-resolved -> 404 (IDOR->404, never 403). The row is then marked `resolved` (namespaced event_id) so a replayed confirm is idempotent.
- **M1** — a missing gate `action` now defaults to `request_changes` (-> the seam's `redo`), never a silent `approve`.

## Task Commits

Each task was committed atomically (no trailer, per feat/ui-2 policy):

1. **Task 1: M2 serialize read-tool rows + M3 thread compiled onto ctx** - `899e87eb` (fix)
2. **Task 2: drain — ctx-scoped drain_proposals surfaces tool-result proposals** - `1ab0ebf3` (fix)
3. **Task 3: H1 durable-row confirm disposal (IDOR->404) + M1 non-approve gate default** - `260be2b2` (fix)

**Plan metadata:** this SUMMARY commit (docs).

## Files Created/Modified
- `backend/app/agents/chat/concierge.py` — `_row_to_dict` serializer; `_read_tools` routes results through it; pure `_steering/_revision/_gate` intent builders; `_collecting_proposal_tools` (per-invocation, concurrency-safe); `converse` captures + stashes on `ctx.proposals`; `drain_proposals(ctx)` staticmethod.
- `backend/app/api/run_commands.py` — `_ConciergeCtx.compiled`; CHANNEL_CONCIERGE resolves `compile_for_run`; `_load_pending_proposal` durable-row lookup; confirm branch disposes from the durable row + marks it resolved; `_drain_concierge_proposals` passes ctx; M1 default `request_changes`.
- `backend/tests/agents/test_concierge_capability.py` — dict-serialization + compiled-injection tests; drain, no-self-buffer, and two-overlapping-`converse` concurrency tests.
- `backend/tests/unit/test_concierge_proposal_channels.py` — the two confirm round-trip tests updated to seed the durable pending row via an ask turn; new no-pending-row / cross-owner / durable-params-win H1 tests + the M1 missing-action default unit test.

## Verification

- **Characterization goldens (INV-3):** `python3.11 -m pytest tests/agents/ -k characterization -q` -> **10 passed** (byte/event-identical; `git diff --stat` on the golden dir empty). `concierge_proposal` fires on zero golden paths.
- **Targeted concierge suites:** `test_concierge_capability.py` + `test_concierge_proposal_channels.py` + `test_concierge_escalation.py` -> **44 passed** (includes the new drain, concurrency, H1, and M1 tests).
- **Concurrency:** `test_overlapping_converse_calls_are_ctx_isolated` passes — two interleaved `converse` calls on ONE singleton never cross-leak proposals.
- **lint-imports:** 4 kept / 0 broken.
- **INV-1:** no workflow-name / `pipeline_type ==` / `spec.id ==` branch added in the touched code (`compile_for_run(wr_type)` passes the label as DATA).
- **INV-13:** the Concierge still reaches Bedrock only via `DeepAgentRunner` — no `create_deep_agent` added.

## Decisions Made
- Confirm turns reuse the ask turn's `message_id` so the durable pending row is deterministically locatable; the confirm's `chat_message` becomes an idempotent no-op (same key).
- `drain_proposals` is a staticmethod reading the per-request ctx buffer, giving the strongest possible guarantee that no per-request state lives on the shared capability instance.
- `_drain_concierge_proposals(concierge, ctx)` calls `drain(ctx)` with a `TypeError` fallback to `drain()` so a legacy/no-ctx duck-typed drain (test fakes) still works.

## Deviations from Plan

None - plan executed exactly as written. The two pre-existing confirm round-trip tests were updated to seed the durable pending row via an ask turn; this is required by the H1 contract change and is within Task 3's declared `files_modified`, not unplanned work.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. (Part B live verification of the Concierge Q&A — B.3 — is deferred to the supervised Part-C SSE cutover per the A.0 decision.)

## Next Phase Readiness
- The backend half of A.1 (the CRUX) is offline-correct and complete. Ready for **43-02** (the FE composer re-routing + confirm round-trip wiring).
- Nothing flips live in this plan: `NEXT_PUBLIC_SSE_TRANSPORT` stays OFF; the live Concierge Q&A check (B.3) rides the Part-C cutover.

---
*Phase: 43-concierge-live-wiring-and-live-pass-closure*
*Completed: 2026-07-15*

## Self-Check: PASSED
- `backend/app/agents/chat/concierge.py` FOUND (modified); `backend/app/api/run_commands.py` FOUND (modified).
- Commits FOUND: `899e87eb` (Task 1), `1ab0ebf3` (Task 2), `260be2b2` (Task 3).
- Characterization: 10 passed, goldens byte-identical. Targeted concierge suites: 44 passed. lint-imports 4/0.
