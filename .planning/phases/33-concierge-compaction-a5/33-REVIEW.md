---
phase: 33-concierge-compaction-a5
reviewed: 2026-07-09T00:00:00Z
depth: deep
files_reviewed: 10
files_reviewed_list:
  - backend/agents/capabilities/compaction/chat_history.py
  - backend/agents/capabilities/context_providers/conversation.py
  - backend/agents/capabilities/registry.py
  - backend/agents/workflows/manifest.py
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/plan.py
  - backend/app/agents/chat/__init__.py
  - backend/app/agents/chat/concierge.py
  - backend/app/api/chat_router.py
  - backend/app/api/run_commands.py
  - frontend/src/components/chat/RunChatLane.tsx
  - frontend/src/components/chat/ChatTokenWidget.tsx
findings:
  critical: 0
  high: 1
  medium: 4
  low: 4
  total: 9
status: issues_found
---

# Phase 33: Code Review Report — Concierge + Compaction

**Reviewed:** 2026-07-09
**Depth:** deep (cross-file trace of the disposal path, ScopedStore surface, DeepAgentRunner boundary, manifest→plan propagation)
**Files Reviewed:** 10 source files (backend + frontend)
**Status:** issues_found — 1 High, 4 Medium, 4 Low

## Summary

The security scaffolding of this phase is largely sound: every Concierge READ and the
`conversation` provider go through the owner+workspace-scoped `ScopedStore` (verified
default-deny in `agents/authz.py` — no raw-ORM path); the model call reaches the model
ONLY via `DeepAgentRunner` (INV-13 intact); the `propose_*` tools are pure data records
with no side effect; the frontend renders all proposal/answer text through JSX escaping
(no `dangerouslySetInnerHTML`); and no changed file branches on a workflow name (INV-1).
The gate-action fence correctly enforces KAN-100 terminal + KAN-94 armed-gate ground
truth on the fresh-proposal path.

The central defect is that the **confirm-chip hold is not enforced on the server**: the
durable `concierge_proposal` row is written but never read back, never verified on
confirm, and never resolved — the confirm turn executes purely on client-supplied
`confirm_proposal` content. Net capability is bounded by the existing mechanical
channels (a client can already approve gates / mint revisions directly), so this is not
a privilege escalation, but it defeats the audit/integrity purpose of the hold and
leaves permanently-`pending` ghost rows. Several supporting correctness gaps compound it:
a dangerous `approve` default, read tools that return unserialized ORM objects, and the
33-05 manifest `chat:` block that never actually reaches the live Concierge.

None of the findings' remedies touch `frontend/src/hooks/useWorkflow.ts` — **no finding
is FIX-039-sensitive**.

## High

### H1: Confirm-chip hold is not server-enforced — held `concierge_proposal` row is never consulted or resolved

**File:** `backend/app/api/run_commands.py:825-841` (confirm branch), `:538-549` (hold write)
**Issue:** On a consequential proposal the code writes a durable `concierge_proposal`
`run_events` row with `status: "pending"` (`:542`, `:548`). But that row is **never read
anywhere** in the codebase (`grep concierge_proposal` finds only the writer, never a
reader). On the confirm turn (`:825-837`) the intent is reconstructed **entirely from the
client-supplied `body.confirm_proposal`** and disposed with `confirmed=True` — there is
no lookup that a matching pending row exists, no ownership/binding check that the
proposal was ever held for this run, and no transition of the pending row to a resolved
state. Consequences:
  1. The "hold until confirmed" guarantee is client-trust only — a client can POST
     `{concierge: true, confirm_proposal: {channel: "gate_action", params: {action:
     "approve"}}}` and execute a consequential intent the model never proposed. (Net
     capability is bounded by the mechanical gate/revision channels, so this is an
     integrity/defense-in-depth and audit gap, not a new privilege.)
  2. The pending row is **never resolved**, so every held proposal leaves a permanent
     `status: "pending"` ghost in `run_events` — a real correctness defect for any
     future consumer that lists pending proposals.
**Fix:** On confirm, look up the pending `concierge_proposal` row by
`(run_id, message_id/proposal_id)` through the owner-scoped `store`, reject the confirm
(`404/409`) when no matching pending row exists, derive `channel`/`params` from the
**stored** row (not the client body), dispose it, then append a terminal
`concierge_proposal` row (or update semantics via an additive `status: "confirmed"`
event) so the hold is idempotent and auditable. Not FIX-039-sensitive.

## Medium

### M1: Gate-action disposal defaults a missing `action` to `approve` (dangerous default)

**File:** `backend/app/api/run_commands.py:571`
**Issue:** `raw_action = params.get("action", "approve")` — a confirmed gate proposal
whose `params` omits `action` (a malformed/partial client `confirm_proposal`, or a
future proposal shape) silently **approves** the armed gate (the most consequential
positive resolution). Combined with H1 (client-supplied params), a missing field
resolves a HITL gate in the affirmative.
**Fix:** Default to a non-affirmative action or reject the disposal when `action` is
absent/invalid: `raw_action = params.get("action")` then `if raw_action not in
_GATE_ACTIONS: raise HTTPException(422, ...)`. Do not default to `approve`. Not
FIX-039-sensitive.

### M2: Concierge READ tools return unserialized ORM row objects — the model receives object reprs, not data

**File:** `backend/app/agents/chat/concierge.py:220-243`
**Issue:** `read_events`, `list_refs`, `get_ref`, `read_gate_events` return the raw
`ScopedStore` results, which are SQLAlchemy ORM instances (`RunEvent` / `ArtifactRef` /
`GateEvent` rows). A LangChain `@tool` coerces a non-string result to its `str()`, so the
model sees `[<app.models.run_event.RunEvent object at 0x…>, …]` — no usable content. The
Concierge's answers therefore cannot actually be grounded in run data on the live path
(the offline tests use scripted fakes, so this is not caught). The owner-scoping is
correct; the serialization is the bug.
**Fix:** Project each row to a plain JSON-serializable dict before returning, e.g.
`return [{"seq": r.seq, "type": r.type, "payload": r.payload_json} for r in rows]` (and
the analogous shapes for refs / gate events). Not FIX-039-sensitive.

### M3: The 33-05 manifest `chat:` block never reaches the live Concierge — inert propagation

**File:** `backend/app/api/run_commands.py:848-851` (`_ConciergeCtx`), consumed at
`backend/app/agents/chat/concierge.py:270-275`
**Issue:** `_compose_system_prompt` reads the manifest chat data via
`getattr(ctx, "compiled", None)`, but the live `_ConciergeCtx` constructed in
`post_message` never sets `compiled` (nor `conversation_context`). So `chat_data` is
always `{}` on the production path and the entire 33-05 chain (manifest.chat →
compiler → `CompiledWorkflow.chat`) is dead on arrival for the Concierge — the "suggested
topics" a custom workflow authors are silently dropped. Verified: `compiled.chat` has no
other consumer (`grep`).
**Fix:** Compile/resolve the run's `CompiledWorkflow` (or the already-loaded one) and pass
it as `_ConciergeCtx(..., compiled=compiled)`, or explicitly document/track this as a
Phase-34 deferral in `deferred-items.md`. Not FIX-039-sensitive.

### M4: Concierge disposal re-executes its seam on a replayed `message_id` (no idempotency short-circuit)

**File:** `backend/app/api/run_commands.py:697` (`created, seq = _persist_chat_message`),
`:815-874` (concierge branch)
**Issue:** `post_message` proceeds to route + dispatch unconditionally even when
`created is False` (a replayed `message_id` → the `chat_message` row already exists). The
`chat_reply`/`concierge_proposal` events are event-id-idempotent, but the **seam side
effects are not**: a replayed confirm turn re-mints a revision child run
(`_mint_revision_row` + `_drive_revision_to_queue`, `:591-611`) or re-invokes
`set_review_response`. This mirrors the pre-existing `CHANNEL_REVISION` behavior (`:782`)
so it is not newly introduced, but the Concierge confirm path inherits and widens it.
**Fix:** When `created is False`, short-circuit consequential disposal (return the prior
result) — or guard revision minting with a durable `(run_id, message_id)` idempotency key.
Not FIX-039-sensitive.

## Low

### L1: Dead constant `_DEFAULT_CONTEXT_BUDGET`

**File:** `backend/app/agents/chat/concierge.py:59`
**Issue:** `_DEFAULT_CONTEXT_BUDGET = 6000` is defined ("mirror the conversation
provider") but never referenced anywhere in the module.
**Fix:** Remove it, or actually use it when composing/bounding the prompt.

### L2: `propose_gate_action` degrades an invalid action to a consequential `request_changes`

**File:** `backend/app/agents/chat/concierge.py:131-138`
**Issue:** An out-of-range `action` is coerced to `request_changes` (which maps to a
consequential `redo` rerun downstream), described as a "safe, inert marker." It is not
inert — it proposes a redo. The proposal is still confirm-gated, so impact is low.
**Fix:** Degrade to the least-consequential proposal (or return no proposal / an explicit
"unsupported action" note) rather than a redo.

### L3: `thread_id` passed to `DeepAgentRunner` without a checkpointer is inert

**File:** `backend/app/agents/chat/concierge.py:183-188`
**Issue:** `DeepAgentRunner(..., thread_id=f"{run_id}:concierge")` is constructed with no
`checkpointer` (defaults to `None`), so the thread id persists nothing — the Concierge has
no cross-turn memory from the checkpointer and must reconstruct history via `read_events`.
This is at best a misleading no-op parameter.
**Fix:** Either pass a checkpointer to make multi-turn memory real, or drop `thread_id`
and document that history is reconstructed from `read_events`.

### L4: `chat_history.compact` can return an over-/near-budget string in edge cases

**File:** `backend/agents/capabilities/compaction/chat_history.py:80-83`, `:69-70`
**Issue:** When `keep_recent == 0`, `recent_block` is `""` and the safety net
(`if len(result) > budget and recent_block:`) never fires, so a summary marker longer
than a very small `budget` is returned unbounded. Also, a negative `budget` supplied via
`ctx.conversation_budget` (only falsy `0`/`None` is guarded by `or _DEFAULT_BUDGET` in
`conversation.py:88-89`) is truthy and bypasses the `len(full) <= budget` early return.
Both are narrow edges (documented "recent fidelity wins over budget"), impact is minor.
**Fix:** Clamp `budget = max(0, int(budget))` and apply the minimal-marker fallback even
when `recent_block` is empty.

## Clean areas (verified sound)

- **Owner-scoping / IDOR (BLOCKER focus):** Every Concierge READ tool
  (`concierge.py:220-243`) and the `conversation` provider (`conversation.py:75-90`)
  delegate exclusively to `ScopedStore`, whose `read_events`/`list_refs`/`get_ref`/
  `read_gate_events` all apply the default-deny `owner_id`+`workspace_id` (or
  visibility) filter (verified in `agents/authz.py`). No raw-ORM path. `_ConciergeCtx`
  and the `post_message` store are built from `current_user.id` + the run's true
  workspace after a two-layer 404 owner check (`run_commands.py:650-676`).
- **INV-13:** The Concierge's only model path is `DeepAgentRunner` (`concierge.py:183`);
  no `create_deep_agent` import/call anywhere in the changed files.
- **Proposal-only:** `propose_steering_note`/`propose_revision`/`propose_gate_action`
  return pure `ProposalIntent` records with zero side effects (`concierge.py:89-138`).
- **KAN-100 / KAN-94:** The fresh gate_action disposal is fenced on terminal status +
  unarmed gate (`run_commands.py:557-568`) before any `set_review_response`.
- **XSS:** `RunChatLane.tsx` renders `p.summary` and the answer transcript through JSX
  escaping only; no `dangerouslySetInnerHTML` in either FE file.
- **Additive-only / seam reuse:** Disposal reuses `apply_steering` /
  `set_review_response` / `_mint_revision_row` / `_drive_revision_to_queue`; the hold
  uses `run_events` (no new table).
- **INV-1:** No workflow-name / `pipeline_type` / `spec.id` branch in any changed file;
  the concierge escalation keys on the generic `turn.concierge` marker only
  (`chat_router.py:266`).
- **Manifest/compiler/plan propagation:** `chat` is carried as inert data verbatim with a
  `{}` default (parity preserved); nothing in the compiler branches on it.

---

_Reviewed: 2026-07-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
