---
phase: quick-260720-c72
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/chat/RunChatLane.tsx
  - frontend/src/hooks/useRunChat.ts
  - frontend/src/components/chat/RunChatLane.test.tsx
  - frontend/src/hooks/useRunChat.test.ts
  - backend/app/api/run_commands.py
  - backend/app/agents/chat/concierge.py
  - backend/tests/agents/test_concierge_capability.py
  - backend/tests/unit/test_chat_messages_endpoint.py
autonomous: true
requirements: [QUICK-260720-c72-FE, QUICK-260720-c72-BE]
must_haves:
  truths:
    - "On a completed run the lane renders clickable chain-suggestion chips above the chat input; clicking one fires onSuggestion(id) (the existing chain action)"
    - "The chips are ABSENT when suggestions is empty/undefined OR the run is not in the complete state"
    - "The chat textarea grows with multi-line input up to a capped max, then scrolls; sending resets it to one row"
    - "When the user asks the Concierge on a completed run that HAS chain suggestions, the chain hints reach the Concierge system prompt as a GENERIC data block naming the chainable workflows"
    - "With NO chain hints the Concierge system prompt is byte-identical to today, and every non-Concierge POST branch keeps its exact JSON contract"
  artifacts:
    - path: "frontend/src/components/chat/RunChatLane.tsx"
      provides: "renderChainSuggestions() chip row (complete-state) + FreeTextComposer auto-grow + chain_hints on the concierge ask send"
      contains: "chat-chain-suggestions"
    - path: "frontend/src/hooks/useRunChat.ts"
      provides: "chain_hints optional field on SendMessageOptions folded onto the /messages payload"
      contains: "chain_hints"
    - path: "backend/app/agents/chat/concierge.py"
      provides: "generic chain-hints DATA block in _compose_system_prompt (no workflow-name branch)"
      contains: "chain_hints"
    - path: "backend/app/api/run_commands.py"
      provides: "MessageCommand.chain_hints + _ConciergeCtx.chain_hints threaded from body"
      contains: "chain_hints"
  key_links:
    - from: "frontend/src/components/chat/RunChatLane.tsx"
      to: "onSuggestion"
      via: "chain chip onClick calls onSuggestion(id)"
      pattern: "onSuggestion\\?\\.\\("
    - from: "frontend/src/components/chat/RunChatLane.tsx"
      to: "frontend/src/hooks/useRunChat.ts"
      via: "concierge ask send folds chain_hints from the suggestions prop"
      pattern: "chain_hints"
    - from: "backend/app/api/run_commands.py"
      to: "backend/app/agents/chat/concierge.py"
      via: "_ConciergeCtx(chain_hints=body.chain_hints) → _compose_system_prompt reads ctx.chain_hints"
      pattern: "chain_hints=body\\.chain_hints"
    - from: "backend/app/agents/chat/concierge.py"
      to: "ctx.chain_hints"
      via: "getattr(ctx, 'chain_hints', None) rendered as a generic block"
      pattern: "getattr\\(ctx, \"chain_hints\""
---

<objective>
Three surgical, additive UX changes on the run screen's LEFT chat lane (MVP / Option A — surface the chain that ALREADY exists; build NO new chaining machinery):

1. FE — restore the chain-suggestion chips in `RunChatLane`'s completed (settled) state, rendered ABOVE the chat input from the already-wired `suggestions`/`onSuggestion` props (the data + click-handler still reach the lane; only the render was deleted in Phase 39 for mock fidelity).
2. FE — make the single `FreeTextComposer` textarea auto-grow with content up to a capped max, then scroll; reset to one row on send. Benefits every composer state.
3. BE — make the run Concierge chain-aware: thread the FE-computed chain suggestions onto the Concierge turn (additive optional `chain_hints`) and render them into the system prompt as a GENERIC data block, so an "ask what can I do next?" turn can name the SAME chainable workflows the chips show.

Purpose: close the run-lane's "what next?" gap without a server-side eligibility engine, a new event type, a migration, or any dual chain policy — the FE static `CHAIN_OPTIONS` stays the single source of truth and the Concierge merely reflects it.

Output: chain chips visible + clickable on a completed run; an auto-growing chat input; a Concierge that names the chainable next-workflows when the user asks — all offline-verified.

## BE approach chosen — BE-1 (thread FE hints), NOT BE-2 (server-compute)

**Chosen: BE-1.** Thread the FE-computed `laneSuggestions` onto the Concierge turn as an additive optional `chain_hints: [{id,label}]` body field → onto `_ConciergeCtx` → rendered as a generic DATA block in `_compose_system_prompt`. Reasons:

- **Non-dual (INV-3):** the single source of truth stays the FE `CHAIN_OPTIONS`/`laneSuggestions` allow-list. The chips and the Concierge reflect the EXACT same set, so they can never diverge (BE-2 risks the Concierge suggesting a different set than the chips).
- **Minimal blast radius (additive-only):** one optional Pydantic field + one optional ctx attribute + one degrade-safe prompt block. No `GET /api/workflows user_launchable` coupling, no server-side deliverable-kind eligibility computation (that is the OUT-of-scope Option B fence).
- **Honors the OUT-of-scope fence:** no `produces`/`consumes` aggregation, no new API fields, no kind-eligibility engine.

**Fallback (BE-2, only if the checker rejects BE-1):** compute the chainable-next list server-side from the existing `GET /api/workflows` `user_launchable` catalogue filtered by the run's type, thread onto `_ConciergeCtx`. Server-authoritative but risks diverging from the FE curated `CHAIN_OPTIONS`. Default remains BE-1.
</objective>

<execution_context>
Standing constraints (BINDING for every task in this plan):
- Branch **feat/ui-2** — NEVER main/dev/staging. Commit with the repo convention (`feat(...)`/`fix(...)` — backend scopes per backend/CLAUDE.md; a `feat(chat): ...` style prefix for FE). **NO commit trailer. NEVER push. NEVER `git stash`.**
- Python **python3.11**, **no venv**. Run backend commands with an **absolute** `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend` (cwd resets between calls).
- Frontend vitest is **cwd-sensitive** — run it from an **absolute** `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend`, never `--root frontend` from the repo root.
- Worktrees OFF → the two tasks run **sequentially** by ONE executor.
- A live backend (:8000) + Next (:3000) may be running — do NOT restart/bind/touch them.
- **NO live Bedrock** in the executor — the offline scripted-model path + vitest prove behavior; the ORCHESTRATOR owns the live re-proof (user_story→prototype + user_story→PPT chaining with per-step screenshots).
- Additive only — **no migration**, no new table, no new status, **no new SSE/WS event type** (a chain-aware Concierge reply rides the EXISTING `chat_reply_chunk`/`chat_reply` stream).
- Re-verify every line anchor below before editing (line numbers drift).
</execution_context>

<context>
@.planning/quick/260720-c72-surface-chain-chips-concierge-chat-autogrow/260720-c72-CONTEXT.md
@backend/CLAUDE.md
@frontend/src/components/chat/RunChatLane.tsx
@frontend/src/components/ui/Pill.tsx
@frontend/src/lib/workflowChaining.ts
@frontend/src/hooks/useRunChat.ts
@frontend/src/components/chat/RunChatLane.test.tsx
@frontend/src/hooks/useRunChat.test.ts
@backend/app/agents/chat/concierge.py
@backend/app/api/run_commands.py
@backend/app/api/chat_router.py
@backend/tests/agents/test_concierge_capability.py
@backend/tests/unit/test_chat_messages_endpoint.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: FE — chain-suggestion chips (complete state) + auto-grow chat input + send chain_hints on the concierge ask</name>
  <files>frontend/src/components/chat/RunChatLane.tsx, frontend/src/hooks/useRunChat.ts, frontend/src/components/chat/RunChatLane.test.tsx, frontend/src/hooks/useRunChat.test.ts</files>
  <behavior>
    - Complete-state, suggestions present: a chip row (testid `chat-chain-suggestions`) renders ABOVE the chat input; each chip (testid `chat-chain-suggestion-chip`, stable `data-suggestion-id`) is a button; clicking the first calls `onSuggestion(id)` with that suggestion's id.
    - Chips ABSENT when `suggestions` is empty/undefined, and absent when `runState !== "complete"` (e.g. building/idle/gate/terminal) even if suggestions are supplied.
    - Auto-grow: with `scrollHeight` stubbed above the cap, a multi-line change sets the textarea inline `style.height` to the capped max ("132px"); clicking send resets `style.height` to "auto".
    - Concierge ask WITH suggestions: a settled-run "ask" turn calls `sendMessage(text, [], { concierge: true, chain_hints: [{id,label}, …] })` (mapped from the `suggestions` prop).
    - Concierge ask WITHOUT suggestions: the call stays byte-identical to today — `sendMessage(text, [], { concierge: true })` with NO `chain_hints` key (the existing li0 pending-indicator tests must stay green untouched).
    - useRunChat: `sendMessage(..., { chain_hints })` folds `chain_hints` onto the POST payload ONLY when non-empty; absent/empty ⇒ no `chain_hints` key (dormant, INV-3).
  </behavior>
  <action>
    In `RunChatLane.tsx`: add a `renderChainSuggestions()` helper (mirror the existing chip idioms `renderProposals` :980 and `renderHeldRefinement` :1030-1063 — same brand-accent chip look: `rounded-[var(--radius-pill)]`, `border-line-control`, `bg-surface-white`, `text-[11px]`, matching the DS `Pill` primitive in `frontend/src/components/ui/Pill.tsx`). It returns null unless `runState === "complete" && suggestions && suggestions.length > 0`; otherwise it renders a row `<div data-testid="chat-chain-suggestions">` with a compact uppercase label (match renderHeldRefinement's `text-[10px] font-bold uppercase tracking-[0.12em] text-brand` label, e.g. "Chain into") followed by one `<button data-testid="chat-chain-suggestion-chip" data-suggestion-id={s.id} onClick={() => onSuggestion?.(s.id)}>` per suggestion showing `s.label`. Invoke `{renderChainSuggestions()}` inside the composer container (`data-testid="chat-composer"`, :1448-1462) as a sibling BETWEEN `{renderHeldRefinement()}` (:1460) and `{renderComposerBody()}` (:1461) — i.e. just above the chat input. Do NOT edit `DashboardLayout.tsx` (its `laneSuggestions`/mount wiring is already correct and out of scope).

    Reconcile the two stale comments the restoration invalidates: the docstring bullet at :16 (which claims the "Suggested next steps" chips were removed) and the `case "complete"` comment at :1087-1092 (which says the chip block "has no mock equivalent and is removed / kept here, unrendered") — update both to reflect that the chips are rendered again above the input on a completed run (user-requested placement, overriding the Phase-39 mock).

    Auto-grow the `FreeTextComposer` textarea (:698-778): add a `const taRef = useRef<HTMLTextAreaElement>(null)` and attach it to the `<textarea>` (:734-747); keep `rows={1}` and `resize-none`, add `overflow-y-auto` + a `max-h-[132px]` class as a scroll safety. Add an imperative `autoGrow` callback that reads `taRef.current`, sets `el.style.height = "auto"` then `el.style.height = Math.min(el.scrollHeight, 132) + "px"` (define the 132px cap as a named const, ~6 rows). Call `autoGrow()` from the existing `onChange` (after `setValue(e.target.value)`). In `handleSend` (:713-720), AFTER `setValue("")`, reset `taRef.current.style.height = "auto"`. Do NOT use a value effect for the resize (keeps the reset deterministic and jsdom-testable); preserve Enter=send / Shift+Enter=newline (:737-742), the container chrome (:733), tokens, and the attach/voice/send buttons.

    Thread `chain_hints` onto the concierge ask send in `handleFreeText` (:934-953): in the `classifyFreeText(text) === "ask"` branch (:937-943) build `const chainHints = suggestions && suggestions.length > 0 ? suggestions.map((s) => ({ id: s.id, label: s.label })) : undefined;` and call `sendMessage(text, attachments, { concierge: true, ...(chainHints ? { chain_hints: chainHints } : {}) })`. Add `suggestions` to the `handleFreeText` useCallback dependency array. Leave the change/revision branch and the plain-send fallthrough unchanged.

    In `useRunChat.ts`: add `chain_hints?: { id: string; label: string }[];` to `SendMessageOptions` (:111-114) with a one-line generic doc note (mirrors the `concierge`/`confirm_proposal` field names → the backend `MessageCommand` exactly; GENERIC — no workflow-name literal). In `sendMessage` (:437-449), after the `confirm_proposal` fold, add `if (options?.chain_hints && options.chain_hints.length > 0) payload.chain_hints = options.chain_hints;` — so an absent/empty array writes NO key (byte-identical dormant payload, INV-3).

    Tests (RED→GREEN):
    - `RunChatLane.test.tsx`: RECONCILE the existing test "complete mode shows the revision composer and NO suggestion chips (mock fidelity)" (:179-193) — its asserted behavior is REVERSED, so rewrite it (do NOT delete): render `runState:"complete"` with `suggestions:[{id:"ppt",label:"Build a deck"}]` + `onSuggestion:vi.fn()`, assert `getAllByTestId("chat-chain-suggestion-chip")` is present, and clicking the first calls `onSuggestion` with `"ppt"`. Add a NEG test: chips ABSENT when `suggestions` undefined AND when `runState:"building"` with suggestions supplied. Add an AUTO-GROW test: stub `Object.defineProperty(HTMLTextAreaElement.prototype, "scrollHeight", { configurable:true, get(){return 300;} })`, fire a multi-line change, assert `textarea.style.height === "132px"`, click `chat-send`, assert `style.height === "auto"`, then restore the stubbed prop. Add a CHAIN-HINTS SEND test: complete-state with suggestions, type an ask ("what's the status?"), click send, assert `sendMessage` called with `("what's the status?", [], { concierge: true, chain_hints: [{ id:"ppt", label:"Build a deck" }] })`. Leave the two existing li0 ASK tests (:786-801) UNCHANGED and green (their baseProps supply no suggestions → send stays `{ concierge: true }`).
    - `useRunChat.test.ts`: add a fold test mirroring the existing concierge-option assertion — `sendMessage(text, [], { concierge:true, chain_hints:[{id:"ppt",label:"Presentation"}] })` folds `chain_hints` onto the `sendCommand` payload; a send with no `chain_hints` (or `[]`) writes NO `chain_hints` key.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && npx vitest run src/components/chat/RunChatLane.test.tsx src/hooks/useRunChat.test.ts</automated>
  </verify>
  <done>Completed-run chips render above the input and click through to onSuggestion; chips absent when empty or non-complete; the textarea auto-grows to the cap and resets on send; the concierge ask carries chain_hints when suggestions exist and is byte-identical when they don't; both FE suites green. RED evidence recorded: before the change the reconciled chips test finds no `chat-chain-suggestion-chip`, the auto-grow test sees an unset height, and the chain-hints send test sees `{ concierge: true }` without `chain_hints`.</done>
</task>

<task type="auto">
  <name>Task 2: BE — Concierge chain-awareness (BE-1): chain_hints on MessageCommand → _ConciergeCtx → generic prompt block</name>
  <files>backend/app/api/run_commands.py, backend/app/agents/chat/concierge.py, backend/tests/agents/test_concierge_capability.py, backend/tests/unit/test_chat_messages_endpoint.py</files>
  <behavior>
    - `_compose_system_prompt(ctx)` with a non-empty `ctx.chain_hints` (list of `{id,label}` dicts) appends a GENERIC data block naming the labels; the Concierge is told it may suggest running one of them with this run's output.
    - `_compose_system_prompt(ctx)` with no/empty `chain_hints` is BYTE-IDENTICAL to today (no chain block appears) — the existing compiled-chat and offline converse tests stay green.
    - The fresh-Concierge POST threads `body.chain_hints` onto the `_ConciergeCtx` handed to `converse` (a POST with chain_hints → the ctx carries them; a POST without → the ctx carries `[]`).
    - `MessageCommand` accepts the additive optional `chain_hints`; every non-Concierge POST branch and the existing Concierge streaming test keep their exact contract (endpoint, escalation, proposal-channel suites green).
  </behavior>
  <action>
    In `run_commands.py`: add `chain_hints: list[dict] | None = None` to `MessageCommand` (:543-580) with a one-line comment (additive optional; the FE-computed chain suggestions `[{id,label}]` from the settled-run lane, threaded to the Concierge ctx as GENERIC data — no workflow-name branch, INV-1; default None ⇒ dormant, byte-identical Phase-29 routing). Add an optional `chain_hints=None` param to `_ConciergeCtx.__init__` (:732-738) storing `self.chain_hints = chain_hints or []`, and extend its docstring (chain_hints = DATA the Concierge reflects; absent ⇒ `[]` ⇒ degrade-safe getattr default; no workflow name is ever passed). In the fresh free-form Concierge branch, pass it into the ctx build at :1211-1215: `_ConciergeCtx(run_id=run_id, scoped_store=store, owner_id=current_user.id, workspace_id=wr_workspace, compiled=compiled, chain_hints=body.chain_hints)`. Do NOT touch `ChatTurn` or `route_chat_turn` (the router does not need chain_hints — the ctx is built directly from `body`), leave the streaming machinery (`_on_chunk`/`_drive`/EventSourceResponse) and every other channel branch unchanged.

    In `concierge.py`: extend `_compose_system_prompt` (:414-444) — after the existing `compiled.chat` block, read `chain_hints = getattr(ctx, "chain_hints", None)`; if it is a non-empty list, defensively take the first ~8 entries, extract each dict's `label` (fallback `id`) as a trimmed string (cap each ~60 chars), drop empties, and if any remain append ONE generic block to `parts` (e.g. "This completed run's output can be chained into these follow-up workflows: {labels joined by ', '}. If the user asks what they can do next, you may suggest running one of these with this run's output. Do not claim any other capability."). This is GENERIC DATA — the labels are READ from ctx and joined; there is NO `if pipeline_type ==` / workflow-name / `spec.id` branch anywhere (INV-1/SC-001). Extend the method docstring to note the optional chain-hints block. Keep every existing block and ordering intact so the no-hints prompt is byte-identical.

    Tests (RED→GREEN):
    - `test_concierge_capability.py`: add `test_compose_system_prompt_injects_chain_hints_block` — a `SimpleNamespace(conversation_context=None, compiled=None, chain_hints=[{"id":"ppt","label":"Presentation"},{"id":"prototype","label":"Prototype"}])` → the prompt contains "Presentation", "Prototype", and a generic "chained into"/"follow-up" phrase; assert byte-identity of the no-hints path by comparing `_compose_system_prompt(SimpleNamespace(conversation_context=None, compiled=None))` to `_compose_system_prompt(SimpleNamespace(conversation_context=None, compiled=None, chain_hints=[]))` (equal, no chain block). Keep `test_compose_system_prompt_injects_compiled_chat_block` (:217) green.
    - `test_chat_messages_endpoint.py`: extend `_StreamingConcierge` (:398-419) to capture the ctx — add `self.seen_hints=[]` and append `getattr(ctx, "chain_hints", None)` inside `converse`. Add `test_chain_hints_reach_concierge_ctx`: monkeypatch `_resolve_concierge` with the fake, POST `concierge=True` + `chain_hints=[{"id":"ppt","label":"Presentation"}]` on a completed run, assert `fake.seen_hints == [[{"id":"ppt","label":"Presentation"}]]`; and a second POST without `chain_hints` records `[]`. Keep the existing `test_fresh_concierge_post_streams_chunks_then_terminal_reply` (:423) and `test_non_concierge_branch_still_returns_json` (:472) UNCHANGED and green.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend &amp;&amp; python3.11 -m pytest tests/agents/test_concierge_capability.py tests/unit/test_chat_messages_endpoint.py tests/unit/test_concierge_escalation.py tests/unit/test_concierge_proposal_channels.py -q</automated>
  </verify>
  <done>chain_hints flow body → _ConciergeCtx → _compose_system_prompt as a generic block; the no-hints prompt is byte-identical; the endpoint threads the field onto the ctx; non-Concierge branches and the streaming test are unchanged; the four backend suites are green. RED evidence recorded: before the change the new prompt test finds no "Presentation"/"Prototype" in the prompt and the endpoint test sees `seen_hints == [None]`.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client body (`chain_hints`) → Concierge system prompt | The FE sends `chain_hints` on the `/messages` POST; the values are reflected into the Concierge's system prompt. |
| Concierge output → streamed to the lane | Unchanged by this task — the reply rides the existing `chat_reply_chunk`/`chat_reply` frames. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-c72-01 | Tampering (prompt injection) | client-supplied `chain_hints` rendered into `_compose_system_prompt` | mitigate | Render labels ONLY as inert DATA (joined into one block), defensively cap count (~8) + per-label length (~60 chars); the Concierge is proposal-only and already told to treat run content as untrusted and never follow embedded instructions. A hostile label at worst names a bogus chain target — nothing executes (chaining still goes through the FE wizard/`handleChainPipeline` + the launch auth path). |
| T-c72-02 | Information disclosure | chip labels / `chain_hints` content | accept | The hints mirror only the static public `CHAIN_OPTIONS` allow-list (workflow display labels), never owner/run data. |
| T-c72-03 | Spoofing / IDOR | the additive `/messages` field | mitigate | No new endpoint/auth surface — the field rides the SAME already-authenticated `POST /api/runs/{id}/messages` two-layer owner check (user_id ORM filter → 404, then default-deny `ScopedStore.get_run` → 404). Every non-Concierge branch keeps its exact contract. |
| T-c72-SC | Tampering | package installs | mitigate | NONE — no new dependency (FE uses existing DS tokens/`Pill` idiom; BE adds only an optional Pydantic field + a prompt string). |
</threat_model>

<verification>
Offline gates — ALL must be green (NO live Bedrock; the orchestrator owns the live re-proof):

1. FE (from `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend`, cwd-sensitive):
   `npx vitest run src/components/chat/RunChatLane.test.tsx src/hooks/useRunChat.test.ts` — chips render/click, auto-grow cap+reset, chain_hints send/fold; existing li0 + terminal tests stay green.
2. BE targeted (from `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend`, python3.11, no venv):
   `python3.11 -m pytest tests/agents/test_concierge_capability.py tests/unit/test_chat_messages_endpoint.py tests/unit/test_concierge_escalation.py tests/unit/test_concierge_proposal_channels.py -q` — all green.
3. INV-3 goldens byte/event-identical (SNAPSHOT_UPDATE unset):
   `python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py -q` — the 5 characterization suites stay 10/10.
4. INV-1/SC-001 banned-pattern gate:
   `python3.11 -m pytest tests/agents/test_banned_patterns.py -q` — green; AND `grep -cE 'prototype|ppt|user_stories|app_builder' app/agents/chat/concierge.py` — stays **0** (baseline confirmed 0; the generic block reads labels from ctx, adds no workflow-name literal).
5. Import-linter contracts intact:
   `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken (concierge stays app-side; no new kernel edge).
</verification>

<success_criteria>
- A completed run shows clickable chain-suggestion chips above the chat input; clicking one fires the existing `onSuggestion(id)` chain action.
- Chips are absent when there are no suggestions or the run is not complete.
- The chat textarea auto-grows to a capped max then scrolls, and resets to one row on send (all composer states benefit).
- A settled-run Concierge ask with chain suggestions injects a GENERIC chain-hints data block into the system prompt; with no hints the prompt is byte-identical and every non-Concierge POST branch is unchanged.
- No migration, no new table/status, no new SSE/WS event type, no dual chain policy.
- FE vitest + BE targeted suites green; 5 goldens 10/10; banned-pattern grep 0 + gate green; lint-imports 4/0.
</success_criteria>

<output>
Create `.planning/quick/260720-c72-surface-chain-chips-concierge-chat-autogrow/01-SUMMARY.md` when done. Record: the exact `renderChainSuggestions` insertion point + chip idiom used, the auto-grow cap/reset design, the `SendMessageOptions.chain_hints` fold, the BE thread (MessageCommand → _ConciergeCtx → generic prompt block), the RED evidence for both tasks, and confirmation that the goldens / banned-pattern grep(=0) / lint-imports / non-Concierge JSON contracts all held.
</output>
