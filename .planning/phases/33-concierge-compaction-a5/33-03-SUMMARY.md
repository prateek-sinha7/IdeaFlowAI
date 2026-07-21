---
phase: 33-concierge-compaction-a5
plan: 03
subsystem: api
tags: [chat, concierge, router, run_events, proposals, revision, steering, gate, fastapi]

# Dependency graph
requires:
  - phase: 33-02
    provides: "chat:concierge capability (converse entry, ProposalIntent {channel, params}, propose_* tools)"
  - phase: 29
    provides: "mechanical router (route_chat_turn), run_commands seams (set_review_response / apply_steering / _mint_revision_row / _drive_revision_to_queue), run_events + ScopedStore"
provides:
  - "CHANNEL_CONCIERGE constant + a pure free-form → Concierge escalation branch in route_chat_turn (zero-model, additive)"
  - "post_message CHANNEL_CONCIERGE branch: invoke Concierge, project chat_reply, dispose propose_* intents through the Phase-29 seams"
  - "concierge_proposal run_events row (confirm-chip hold) + the FE confirm round-trip (confirm_proposal) contract"
  - "request_changes → redo action-name reconciliation between the Concierge and the gate seam"
affects: [33-04, 33-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive router escalation via a generic turn marker (ChatTurn.concierge) — no default-routing change, all Phase-29 tests stay green (INV-12)"
    - "Proposal disposal is a single reusable async function keyed on ProposalIntent.channel → the existing Phase-29 seam (no forked execution path)"
    - "Consequential proposals held behind a confirm chip via a durable concierge_proposal run_events row (additive, no new table)"

key-files:
  created:
    - backend/tests/unit/test_concierge_escalation.py
    - backend/tests/unit/test_concierge_proposal_channels.py
  modified:
    - backend/app/api/chat_router.py
    - backend/app/api/run_commands.py

key-decisions:
  - "Escalation is opt-in via a generic ChatTurn.concierge marker (not plain-text-by-default), preserving byte-identical Phase-29 routing for all non-concierge turns and keeping the frozen out-of-scope router/endpoint tests green (Rule 3)."
  - "converse returns only str, so live proposal surfacing (model tool-results) is Phase-34 live-deferred; the disposal + confirm-chip contract is proven offline via the confirm round-trip + a duck-typed drain_proposals seam."
  - "request_changes (Concierge vocabulary) is reconciled to redo (gate-seam vocabulary) in the disposal branch; approve/reject/update_specs are identical on both sides."

patterns-established:
  - "Router stays PURE (classify-only); the model invocation lives in the app layer (post_message)."
  - "One disposal function, three channels, existing seams — proposals execute only through Phase-29 channels (SC-1)."

requirements-completed: [D-04, D-05, D-02, SC-1, SC-3, INV-12]

# Metrics
duration: 40min
completed: 2026-07-08
---

# Phase 33 Plan 03: Concierge Router Escalation + Proposal Disposal Summary

**Free-form chat turns escalate to the Concierge via a pure zero-model router branch, and the Concierge's propose_* intents dispose through the SAME Phase-29 gate/steering/revision seams — consequential ones held behind a confirm chip (concierge_proposal), executed only on the FE confirm round-trip.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-07-08
- **Completed:** 2026-07-08
- **Tasks:** 2
- **Files modified:** 4 (2 production, 2 tests)

## Accomplishments
- `CHANNEL_CONCIERGE` + a pure, additive escalation branch in `route_chat_turn` (D-04): a turn explicitly marked free-form (generic `ChatTurn.concierge`) with no routable discriminator classifies to `CHANNEL_CONCIERGE` with zero model calls. Every routable turn (clarify/gate/steering/revision) stays byte-identically on its Phase-29 channel (INV-12).
- `post_message` `CHANNEL_CONCIERGE` branch (D-05): resolves the owner-scoped Concierge (`registry.resolve("chat","concierge")`), projects its answer as a `chat_reply` `run_events` row, and disposes each `propose_*` intent through the SAME seams the mechanical router uses — `steering_note→apply_steering`, `gate_action→set_review_response`, `revision→_mint_revision_row + _drive_revision_to_queue` (D-02, SC-3). No forked seam, no new table.
- Confirm-chip hold (T-33-03-01): consequential proposals (gate action + revision) emit a durable `concierge_proposal` row and return WITHOUT executing; the FE confirm round-trip (`confirm_proposal`) executes the held intent. KAN-100 terminal fence + KAN-94 armed-gate ground truth guard a proposed gate resolution.

## Task Commits

1. **Task 1: router escalation — CHANNEL_CONCIERGE + pure free-form branch + escalation test** - `3ca099e3` (feat)
2. **Task 2: post_message concierge invocation + proposal→channel disposal + confirm-chip hold** - `8d8ed0c2` (feat)

**Plan metadata:** (this SUMMARY commit — see final commit)

## Files Created/Modified
- `backend/app/api/chat_router.py` - Added `CHANNEL_CONCIERGE`, `ChatTurn.concierge` marker, the pure escalation branch in `route_chat_turn`, `__all__` export, docstring update.
- `backend/app/api/run_commands.py` - Added `MessageCommand.concierge`/`confirm_proposal`, `_ConciergeCtx`, `_resolve_concierge`, `_drain_concierge_proposals`, `_dispose_concierge_proposal`, the `CHANNEL_CONCIERGE` dispatch branch, `_CONCIERGE_GATE_ACTION_MAP`.
- `backend/tests/unit/test_concierge_escalation.py` - Router escalation classification (free-form → concierge; routable → existing channel; pure/zero-model).
- `backend/tests/unit/test_concierge_proposal_channels.py` - Disposal-function seam routing (unit, seams spied) + full endpoint wiring (fresh ask → chat_reply; surfaced proposal held; confirm round-trip → seam; terminal fence).

## Hand-off Contracts (for 33-04 / 33-05)

### (a) `concierge_proposal` event shape + confirm round-trip contract (33-04 reads this)

A CONSEQUENTIAL proposal held behind the confirm chip is a `run_events` row:

```
type:  "concierge_proposal"
event_id: "concierge-proposal:{message_id}:{channel}"
payload_json: {
  "pipeline_run_id": "<run_id>",
  "message_id": "<originating turn message_id>",
  "channel": "gate_action" | "revision",
  "params":  { ...the ProposalIntent.params verbatim... },
  "status":  "pending"
}
```
- `gate_action` params: `{"action": approve|reject|request_changes|update_specs, "rationale": str}`
- `revision` params: `{"instruction": str, "target": str}`

**To CONFIRM (execute)** a pending proposal, the FE POSTs `POST /api/runs/{id}/messages` with:
```
{ "message_id": "<new id>", "concierge": true,
  "confirm_proposal": { "channel": "<channel>", "params": { ...params... } } }
```
The endpoint reconstructs the `ProposalIntent` and disposes it CONFIRMED → the Phase-29 seam runs. Response: `{"channel":"concierge","proposal": {...disposition result...}}` (a `revision` confirm returns `proposal.revision_run_id`).

**To REJECT** a pending proposal: the FE simply does not confirm (no seam runs). A durable "rejected" marker row is NOT emitted by 33-03 — if 33-04 needs one, add it there (out of 33-03 scope).

A NON-consequential answer (`steering_note`, and the plain Q&A answer) projects immediately as a `chat_reply` row (`event_id: "chat-reply:{message_id}"`, payload `{pipeline_run_id, message_id, text}`). `chat_reply` is already a documented event type.

### (b) New `pipeline_complete` keys introduced (for 33-05 `_VOLATILE_STRIP_KEYS`)

**None.** 33-03 introduces no new `pipeline_complete` payload keys. The ONLY new event type is `concierge_proposal` — 33-05 must admit it into `_DOCUMENTED_EVENT_TYPES` and the golden-neutrality guard (`test_chat_event_neutrality.py`). It NEVER fires on a golden path (it is emitted only in the `CHANNEL_CONCIERGE` branch, which no golden run exercises).

### (c) Action-name mapping applied

`_CONCIERGE_GATE_ACTION_MAP = {"request_changes": "redo"}` in `run_commands.py`. The Concierge proposes `request_changes`; the Phase-29 gate seam (`store.set_review_response`) names that action `redo` (carrying instructions). `approve` / `reject` / `update_specs` are identical on both sides and pass through unchanged. The `rationale` param is threaded to the seam's `instructions` for `redo`/`update_specs`.

## Decisions Made
- **Opt-in escalation marker (not plain-text default).** A literal "plain text in running/terminal escalates" predicate would flip the Phase-29 defaults and break frozen, out-of-scope tests (`test_running_routes_to_steering` / `test_terminal_routes_to_revision` in `test_chat_messages_endpoint.py`; `test_running_routes_to_steering_note` / `test_all_terminal_statuses_route` in `test_mechanical_router.py`) — which the diff contract forbids editing. The generic `ChatTurn.concierge` marker is a NON-workflow discriminator (SC-001/INV-1, mirroring `sticky`/`skip_clarification`); escalation fires in ANY phase when marked + no routable discriminator, so a confirm-gate turn during a gate pause still reaches the Concierge path.
- **Escalation placed at the top of `route_chat_turn`** (before the phase branches) so it works in every phase; still pure/zero-model (returns a `Dispatch`, never invokes a model).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Escalation made opt-in via a generic marker instead of plain-text-by-default**
- **Found during:** Task 1 (router escalation)
- **Issue:** The plan/orchestrator described the predicate as "running/terminal + no action + no structured discriminator" (i.e. plain text escalates by default). Taken literally this repurposes the Phase-29 default steering/revision routing and BREAKS four existing, out-of-scope, frozen tests that assert plain-text running→steering and plain-text terminal→revision. The diff contract requires the change set to be EXACTLY the 4 plan files (no edits to those test files), so a default-changing predicate is not achievable.
- **Fix:** Added a generic `ChatTurn.concierge` opt-in marker (a non-workflow discriminator). Escalation fires only when the FE explicitly marks a turn free-form; all non-concierge turns keep byte-identical Phase-29 routing. This satisfies zero-model + INV-1 + INV-12 and keeps every existing test green.
- **Files modified:** `backend/app/api/chat_router.py`, `backend/app/api/run_commands.py`
- **Verification:** `test_mechanical_router.py` + `test_chat_messages_endpoint.py` still pass unchanged (81 passed total); new escalation asserts the marker path.
- **Committed in:** `3ca099e3`

**2. [Rule 3 - Blocking] Proposal surfacing reconciled with converse→str**
- **Found during:** Task 2 (proposal disposal)
- **Issue:** The 33-02 `converse` returns only `str` (the answer text); it does not return `propose_*` intents, so "dispose each returned propose_* intent" is not literally wireable from the return value. `concierge.py` is out of scope (cannot be edited).
- **Fix:** The disposal is a standalone `_dispose_concierge_proposal(intent, confirmed=...)` (fully offline-testable) exercised via (i) the FE confirm round-trip (`confirm_proposal` POST body → executed) and (ii) a duck-typed `drain_proposals()` seam for fresh proposals (held). LIVE surfacing of model tool-results is Phase-34 live-deferred; the seam mapping + confirm-chip contract are proven offline.
- **Files modified:** `backend/app/api/run_commands.py`, `backend/tests/unit/test_concierge_proposal_channels.py`
- **Verification:** 15 proposal-channel tests pass (seam routing, hold, fence, confirm round-trip).
- **Committed in:** `8d8ed0c2`

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking reconciliations).
**Impact on plan:** No scope creep. Both reconciliations were forced by hard constraints (diff contract + the 33-02 converse signature) and preserve every invariant (SC-001/INV-1/INV-12, zero-model routing, no forked seam, additive migrations).

## Issues Encountered
None beyond the two reconciliations above.

## Live-Deferred / human_needed
- **Live mid-run steering delivery (DEF-29-09-1):** `_live_ectx_for_run` returns `None` today (`run_commands.py`), so a disposed `steering_note` is best-effort at runtime (the durable `chat_message`/`chat_reply` row is the record; re-derived on resume — ND-9). The seam is proven at unit level offline. Do NOT block on live delivery.
- **Live Concierge Q&A + proposal surfacing (Phase 34):** The real `converse` runs a live Haiku model; live Q&A quality and model tool-result → proposal surfacing (feeding `drain_proposals`) are Phase-34 live-deferred. The offline structural contract (escalation, disposal, hold, confirm round-trip, fence) is fully proven.

## Verification Evidence
- `test_concierge_escalation.py` — 13 passed.
- `test_concierge_proposal_channels.py` — 15 passed.
- `test_chat_contract.py` — 11 passed (unedited; INV-12, ChatRunner not forked).
- Regression: `test_mechanical_router.py` (28) + `test_chat_messages_endpoint.py` (14) still green.
- `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken.
- `git diff --name-only 80d0a9b8 HEAD` = exactly the 4 plan files (+ this SUMMARY on the final commit).

## Next Phase Readiness
- 33-04 (FE): confirm-chip UX + the confirm round-trip contract documented in §(a) above.
- 33-05 (goldens): admit `concierge_proposal` into `_DOCUMENTED_EVENT_TYPES` + the neutrality guard; no new `pipeline_complete` keys to strip (§b).

## Self-Check: PASSED

---
*Phase: 33-concierge-compaction-a5*
*Completed: 2026-07-08*
