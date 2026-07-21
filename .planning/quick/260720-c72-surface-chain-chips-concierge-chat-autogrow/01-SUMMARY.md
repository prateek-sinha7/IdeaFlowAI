---
phase: quick-260720-c72
plan: 01
subsystem: run-chat-lane + run-concierge
tags: [frontend, backend, chat, concierge, chaining, ux]
requires: [FE laneSuggestions/onSuggestion wiring (DashboardLayout, unchanged), Concierge live path (Phase 43)]
provides: [completed-run chain chips, auto-grow chat input, Concierge chain_hints awareness]
affects: [RunChatLane, useRunChat, run_commands MessageCommand/_ConciergeCtx, concierge _compose_system_prompt]
tech-stack:
  added: []
  patterns: [additive-optional Pydantic field, generic getattr-degrade prompt block, imperative textarea auto-grow]
key-files:
  created: []
  modified:
    - frontend/src/components/chat/RunChatLane.tsx
    - frontend/src/hooks/useRunChat.ts
    - frontend/src/components/chat/RunChatLane.test.tsx
    - frontend/src/hooks/useRunChat.test.ts
    - backend/app/api/run_commands.py
    - backend/app/agents/chat/concierge.py
    - backend/tests/agents/test_concierge_capability.py
    - backend/tests/unit/test_chat_messages_endpoint.py
decisions:
  - "BE-1 chosen (thread FE hints), not BE-2 (server-compute) — single source of truth stays the FE CHAIN_OPTIONS; the Concierge merely reflects it."
  - "Chain block is GENERIC data built purely from ctx labels — no workflow-name branch (INV-1/SC-001), grep stays 0."
metrics:
  duration: ~35m
  completed: 2026-07-20
commits:
  - b03fdf82 (Task 1, FE)
  - d713f714 (Task 2, BE)
---

# Phase quick-260720-c72 Plan 01: Surface chain chips + Concierge chain-awareness + chat auto-grow Summary

Three surgical, additive UX changes on the run screen's LEFT chat lane: the completed-run chain-suggestion chips are restored above the input, the chat textarea auto-grows to a capped max, and the run Concierge reflects the SAME curated chainable next-workflows as generic prompt data — all offline-verified, zero new machinery.

## Task 1 — FE (commit b03fdf82)

### `renderChainSuggestions()` insertion + chip idiom
Added a `renderChainSuggestions()` helper in `RunChatLane.tsx` that returns `null` unless `runState === "complete" && suggestions?.length > 0`, else renders `<div data-testid="chat-chain-suggestions">` with a compact uppercase brand label ("Chain into", matching the `renderHeldRefinement` `text-[10px] font-bold uppercase tracking-[0.12em] text-brand` idiom) followed by one `<button data-testid="chat-chain-suggestion-chip" data-suggestion-id={s.id} onClick={() => onSuggestion?.(s.id)}>` per suggestion showing `s.label`. Each chip uses the DS `Pill` idiom (`rounded-[var(--radius-pill)]`, `border-line-control`, `bg-surface-white`, `text-[11px]`, hover → brand). Invoked in the composer container (`data-testid="chat-composer"`) as a sibling BETWEEN `{renderHeldRefinement()}` and `{renderComposerBody()}` — i.e. just above the chat input. The two stale Phase-39 comments (docstring bullet + `case "complete"`) were reconciled to say the chips are rendered again above the input (user-requested, overriding the mock).

### Auto-grow cap/reset design
`FreeTextComposer` got a `taRef` on the `<textarea>` and a named module const `COMPOSER_MAX_HEIGHT_PX = 132` (~6 rows). An imperative `autoGrow` callback sets `el.style.height = "auto"` then `el.style.height = Math.min(el.scrollHeight, 132) + "px"`, called from `onChange` after `setValue`. `handleSend` resets `taRef.current.style.height = "auto"` after `setValue("")`. The textarea kept `rows={1}` + `resize-none` and gained `max-h-[132px]` + `overflow-y-auto` as a scroll safety. No value effect (keeps the send-reset deterministic + jsdom-testable). Enter=send / Shift+Enter=newline preserved.

### `chain_hints` send + `SendMessageOptions` fold
In `handleFreeText` the `classifyFreeText(text) === "ask"` branch preserves `setReplyPending(true)`, then builds `const chainHints = suggestions?.length ? suggestions.map(s => ({id:s.id,label:s.label})) : undefined` and calls `sendMessage(text, attachments, { concierge: true, ...(chainHints ? { chain_hints: chainHints } : {}) })`. `suggestions` added to the useCallback deps. In `useRunChat.ts`, `SendMessageOptions.chain_hints?: {id,label}[]` was added and `sendMessage` folds `if (options?.chain_hints && options.chain_hints.length > 0) payload.chain_hints = options.chain_hints` (absent/empty ⇒ NO key, INV-3 dormant).

## Task 2 — BE (commit d713f714): MessageCommand → _ConciergeCtx → generic prompt block

- `run_commands.py`: `MessageCommand.chain_hints: list[dict] | None = None` (additive optional). `_ConciergeCtx.__init__` gained a `chain_hints=None` param storing `self.chain_hints = chain_hints or []`. The fresh free-form Concierge branch passes `chain_hints=body.chain_hints` into the ctx build. `ChatTurn`/`route_chat_turn` and the streaming machinery untouched.
- `concierge.py`: `_compose_system_prompt` reads `chain_hints = getattr(ctx, "chain_hints", None)` AFTER the compiled-chat block; on a non-empty list it takes the first 8 entries, extracts each dict's `label` (fallback `id`) trimmed + capped at 60 chars, drops empties, and if any remain appends ONE generic block ("This completed run's output can be chained into these follow-up workflows: {labels}. …Do not claim any other capability."). Labels are READ from ctx and joined — NO `pipeline_type`/workflow-name/`spec.id` branch. Every existing block + ordering intact ⇒ the no-hints prompt is byte-identical.

## RED → GREEN evidence

**Task 1 (FE, `npx vitest run src/components/chat/RunChatLane.test.tsx src/hooks/useRunChat.test.ts`):**
- RED (4 failing before code): `complete mode renders the chain-suggestion chips…` (no `chat-chain-suggestion-chip` found), `the chat textarea auto-grows…` (`style.height` unset, not `"132px"`), `a settled-run ASK with chain suggestions folds chain_hints…` (send was `{ concierge: true }` without `chain_hints`), `Test 19 … folds the array…` (no `chain_hints` on payload). `60 passed | 4 failed`.
- GREEN (after code): `Test Files 2 passed (2) · Tests 64 passed (64)`.

**Task 2 (BE):**
- RED (2 failing before code): `test_compose_system_prompt_injects_chain_hints_block` (`'Presentation' not in prompt`), `test_chain_hints_reach_concierge_ctx` (`seen_hints == [None, None]`, not `[[{...}], []]`).
- GREEN (after code): the 4 targeted suites `64 passed`.

## Gate results (all green)

1. FE vitest: `64 passed (64)` — chips render/click, chips absent when empty/non-complete, auto-grow cap+reset, chain_hints send/fold; existing li0 + terminal + 43-02/44-02 tests unchanged and green.
2. BE targeted (`test_concierge_capability.py test_chat_messages_endpoint.py test_concierge_escalation.py test_concierge_proposal_channels.py`): `64 passed`. The existing streaming test + non-Concierge JSON-contract test unchanged and green.
3. Goldens (5 characterization suites, SNAPSHOT_UPDATE unset): `10 passed` — byte/event-identical (od_ppt was green here, NOT a pre-existing red on this branch).
4. INV-1 banned-pattern: `grep -cE 'prototype|ppt|user_stories|app_builder' app/agents/chat/concierge.py` → `0`; `tests/agents/test_banned_patterns.py` → `11 passed`.
5. Import-linter: `/opt/homebrew/bin/lint-imports` → `Contracts: 4 kept, 0 broken`.

## Deviations from Plan

None — plan executed exactly as written. All three plan-checker concerns honored: `setReplyPending(true)` preserved in the ask branch; no workflow-name literal in `concierge.py` (grep 0); the auto-grow test stubs AND restores `scrollHeight`.

## Threat surface

No new surface beyond the plan's `<threat_model>`. `chain_hints` rides the SAME already-authenticated `POST /api/runs/{id}/messages` two-layer owner check; labels are rendered as inert data (defensively capped 8×60 chars); no new endpoint/event type/migration.

## Self-Check: PASSED
- Files modified confirmed present (8 files across FE + BE).
- Commits confirmed in `git log`: b03fdf82 (Task 1), d713f714 (Task 2).
