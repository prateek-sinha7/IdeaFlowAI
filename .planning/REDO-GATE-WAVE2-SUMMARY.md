# REDO-GATE — Wave 2 (frontend) execution summary

Branch: `new-workflow-engine` (no worktree — main tree edited). Plan:
`.planning/REDO-GATE-PLAN.md` (v2) Wave-2 tasks **T9–T13**. Backend (Wave 1) was
already done/committed; this wave is the FE that drives it. No backend / ROADMAP /
STATE files touched. Not pushed.

One-liner: the human review gate now renders a **Redo (with optional additional
instructions)** control purely off the server's generic `redoable` flag, sends the
Wave-1 `approve_review` `action:"redo"` message on the SAME owner-gated resume
channel, and latches its controls against a double-send until the re-run's fresh
`review_gate_ready` re-opens the panel — with zero workflow/agent literal in the FE
(SC-001) and zero new failures in the FE test suite.

---

## Tasks completed

| Task | What | Files | Commit |
|------|------|-------|--------|
| T12 | Additive `ReviewGateReadyData` interface carrying optional generic `redoable?: boolean` on the inbound `review_gate_ready` event | `frontend/src/types/index.ts` | 07e47041 |
| T9 + T13 | `ReviewGatePanel`: optional `onRedo`+`redoable` props; Redo button + optional instructions textarea rendered IFF `onRedo && redoable` (F1b fence); one-action `submitted` latch disables Approve/Reject/Redo+textarea after any resolve (no double-send), re-armed on `output`/`gateKey` change | `frontend/src/components/preview/ReviewGatePanel.tsx` | f93ae1bf |
| T10 | `DashboardLayout`: add `redoable?` to `reviewGateData` shape + `onRedoReview?` prop; forward `onRedo={onRedoReview}` and `redoable={reviewGateData.redoable}` to the panel (pass-through only) | `frontend/src/components/layout/DashboardLayout.tsx` | ce1a36f4 |
| T11 | `dashboard/page.tsx`: capture `redoable` off `review_gate_ready` into `reviewGateData` (default false, typed via `ReviewGateReadyData`); add `onRedoReview` that sends `{type:"approve_review", gate_key, action:"redo", instructions}` then clears the panel; KAN-89 stale-gate clearing on new run left intact | `frontend/src/app/dashboard/page.tsx` | 59087c59 |
| Test | `ReviewGatePanel` vitest (test #13): Redo shown only when `onRedo && redoable`; hidden for `redoable=false` and when no `onRedo`; `onRedo(gateKey, instructions)` fires; empty box → `onRedo(gateKey, "")`; controls disable after click; re-arm on new `review_gate_ready` | `frontend/src/components/preview/ReviewGatePanel.test.tsx` | a35feda4 |

> Task-numbering note: T9 (Redo control) and T13 (idempotency latch) live in the
> same component and the `submitted` latch is structurally interwoven with the new
> controls' `disabled` states, so they were committed together (commit message
> tags both IDs) rather than split into an artificial incomplete intermediate.

---

## Exact wire contract matched (against the Wave-1 commits)

- **Inbound — `review_gate_ready.data.redoable`** (from `git show f18de868`): the
  engine stamps a generic `redoable: bool` on `review_gate_ready.data`, `True` only
  from the inline call site. The FE reads it as `data.redoable ?? false` and renders
  the Redo control **iff** `onRedo && redoable`. A declared/user-composed
  `gate:human` (`redoable=false`) shows no Redo button — the SC-001-safe fence.
- **Outbound — `approve_review` redo** (from `git show 7500d4b0`): the backend
  handler reads `action = message_data.get("action", "approve")` and
  `instructions = message_data.get("instructions")`, and on `action=="redo"` calls
  `set_review_response(gate_key, approved=False, action="redo", instructions=...)`
  AFTER the unchanged `_review_gate_owned_by` owner check. The FE sends exactly:
  `{ type: "approve_review", gate_key: gateKey, action: "redo", instructions }` —
  same `gate_key` field the existing approve/reject send uses, same handler, same
  resume channel (no new WS message type).

---

## Verification results

| Check | Result |
|-------|--------|
| `npx tsc --noEmit` on the 4 changed source files (`types/index.ts`, `ReviewGatePanel.tsx`, `DashboardLayout.tsx`, `page.tsx`) | **0 errors** |
| `npx tsc --noEmit` whole project | 3 errors — ALL pre-existing in files I did not touch: `e2e/fixtures/mockApi.ts:95,96` (readonly-tuple cast) + `src/components/workflow/IdeaInputPage.tsx:737` (duplicate JSX attr). Verified identical with my page fix stashed. |
| `npx vitest --run src/components/preview/ReviewGatePanel.test.tsx` | **7 passed / 7** |
| `npx vitest --run` (full FE suite) | 155 passed / 7 failed (3 files). **Identical failure set on clean pre-work HEAD `d66df568`** (WorkflowCatalog×5, AgentProgressPanel×1, IdeaInputPage.declaredCapabilities×1) — my changes add **0** new failures. |

> The prompt named the known-pre-existing failures as `workflowChaining.test.ts`
> (~6) + `AgentProgressPanel.test.tsx` (~1). On this branch `workflowChaining`
> actually PASSES; the pre-existing red is instead `WorkflowCatalog.test.tsx` (×5,
> waitFor timeouts) + `AgentProgressPanel.test.tsx` (×1) +
> `IdeaInputPage.declaredCapabilities.test.tsx` (×1). I verified the EXACT same 7
> failures at the pre-Wave-2 commit `d66df568`, so none are mine. None of the
> failing files were touched by this wave.

---

## Invariant / constraint compliance

- **SC-001 / generic:** the FE shows Redo purely off the server `redoable` flag
  (`onRedo && redoable`) — NO workflow-name or agent-id check in the FE. A gate
  without `redoable` shows no Redo button (declared/user-composed `gate:human` stays
  safe in v1). `grep` for `redoable`/`onRedo` in the changed FE shows only generic
  flag/handler usage.
- **No new WS message type:** redo rides the existing `approve_review` shape (matches
  Wave-1 `set_review_response(..., action="redo")` owner-gated handler).
- **KAN-89 preserved:** the new-run stale-`reviewGateData` clear in `page.tsx`
  (`setReviewGateData(null)` on a new pipeline) is untouched; the redo path only adds
  its own clear after sending (so the re-run's fresh `review_gate_ready` re-opens it).
- **F8 idempotency:** the panel latches all resolve actions after one click and
  re-arms on `output`/`gateKey` change, so a repeated/late click cannot double-send
  and a fresh re-pause renders an interactive gate (covered by tests).

---

## Deviations from plan

- **T9+T13 committed together** (same component, interwoven `disabled`/`submitted`
  logic) — see task-numbering note above. No behavior change vs the plan.
- **page.tsx cast:** the inbound `msg.data` cast to the new named `ReviewGateReadyData`
  interface triggered TS2352 (lenient inline-object casts are allowed but a named
  interface against the `data` union is not), so it is written
  `msg.data as unknown as ReviewGateReadyData` — the standard explicit-cast idiom,
  folded into the T11 commit. No runtime change.
- **F-fe4 (T13 page/DashboardLayout agent-panel idempotency):** the plan's #14
  "repeated agent_start/agent_complete renders ONE card / reconnect-after-N-redos
  replays cleanly" is an existing FE property (cards dedup by `index`/`event_id`);
  no code change was required to satisfy it, so no new code was added there. The
  panel-level F8 double-send guard (the actionable T13 item) is implemented + tested.

## Items deferred / follow-ups
- None for Wave 2. (Backend follow-ups — declared-path real redo, F4 durable resume,
  F7 cancel-aware wait — remain as documented in the Wave-1 summary.)

## Self-check
- All 5 changed/created files exist and are committed (07e47041, f93ae1bf, ce1a36f4,
  59087c59, a35feda4). Branch `new-workflow-engine`, not pushed.
- `npx tsc --noEmit` clean on all changed source files; the only project-wide tsc
  errors are pre-existing in untouched files.
- New `ReviewGatePanel` test: 7/7 green. Full suite adds 0 new failures vs clean HEAD.
