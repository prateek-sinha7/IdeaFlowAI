---
phase: quick-260720-ec4
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/chat/RunChatLane.tsx
  - frontend/src/components/chat/RunChatLane.test.tsx
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/kernel_services.py
  - backend/tests/agents/test_gates.py
  - backend/tests/agents/test_restart_resume.py
autonomous: true
requirements: [QUICK-260720-ec4-BUG1, QUICK-260720-ec4-BUG2]
must_haves:
  truths:
    - "On a completed run, typing a transform phrase whose tail names a currently-available chain suggestion (e.g. 'convert it into presentation' with a 'Presentation' suggestion) fires onSuggestion(thatId) and does NOT setHeldRefinement / call onRevise / call sendMessage."
    - "A transform phrase with NO matching available suggestion (e.g. 'convert the buttons into pills') keeps the existing change→held-refinement path unchanged; onSuggestion is NOT called."
    - "With no suggestions prop supplied, settled-run classification stays byte-identical to today (ASK→concierge send, CHANGE→held refinement); the existing 43-02 route matrix + c72 chain_hints-send tests stay green."
    - "Pressing Stop while the run is parked at CLARIFY (the engine drain loop) yields the existing pipeline_cancelled terminal and cancels the clarify task — no new event type."
    - "Pressing Stop while parked at a DECLARED human/approval gate yields pipeline_cancelled via the existing cancel-aware race (cancel_event now reaches the run_human_gate delegate)."
    - "The BE cancel path is DORMANT on scripted/golden runs (cancel_event is None) — the 5 characterization goldens stay byte/event-identical (SNAPSHOT_UPDATE unset)."
  artifacts:
    - path: "frontend/src/components/chat/RunChatLane.tsx"
      provides: "matchChainTarget(text, suggestions) helper + a chain-route branch in handleFreeText that fires onSuggestion BEFORE classifyFreeText on a completed run"
      contains: "matchChainTarget"
    - path: "backend/agents/execution_engine/engine.py"
      provides: "cooperative-cancel check inside the clarify drain loop's 1s-timeout branch → cancel the clarify task + yield pipeline_cancelled"
      contains: "pipeline_cancelled"
    - path: "backend/agents/execution_engine/kernel_services.py"
      provides: "run_human_gate threads self.cancel_event into engine._run_review_gate so the existing cancel race fires on the declared-gate path"
      contains: "cancel_event=self.cancel_event"
  key_links:
    - from: "frontend/src/components/chat/RunChatLane.tsx"
      to: "onSuggestion"
      via: "handleFreeText calls matchChainTarget(text, suggestions) on a complete run and routes a matched id to onSuggestion(id) before classifyFreeText"
      pattern: "onSuggestion\\?\\.\\(|onSuggestion\\("
    - from: "backend/agents/execution_engine/engine.py"
      to: "pipeline_cancelled"
      via: "the clarify drain loop checks cancel_event.is_set() on the 1s wait_for timeout, cancels clarify_task, transitions to cancelled, yields pipeline_cancelled"
      pattern: "cancel_event.*is_set"
    - from: "backend/agents/execution_engine/kernel_services.py"
      to: "backend/agents/execution_engine/engine.py"
      via: "run_human_gate passes cancel_event=self.cancel_event into self._engine._run_review_gate (the SAME asyncio.Event execute() holds)"
      pattern: "cancel_event=self\\.cancel_event"
---

<objective>
Fix two independent, PRE-EXISTING run-screen bugs (neither caused by the recent c72 chaining work). Disjoint files → one executor, sequential, two atomic commits.

- BUG-1 (Task 1, FE-only): the chat "convert it into presentation" phrase on a completed run misroutes to a REVISION of the current run instead of chaining into a new workflow. Root cause: `classifyFreeText` sees `convert` in the 40+-verb `CHANGE_INTENT` alternation → `"change"` → held refinement → `onRevise` (a *_revision of THIS run). Fix: detect a chain-into-an-AVAILABLE-target phrase BEFORE the change-check and route it to the existing `onSuggestion(id)` chain seam. The match is DATA-DRIVEN against the passed `suggestions[].label` (never a workflow-name literal — SC-001/INV-1). A disambiguation guard keeps genuine same-run edits ("convert the buttons into pills") on the unchanged revise path.

- BUG-2 (Task 2, engine-side): the Stop button is a no-op when the run is parked at clarify or a declared human/approval gate, because the engine is blocked in a cancel-UNAWARE wait in exactly two spots. Fix reuses the SHIPPED cooperative-cancel machinery (Phase 16-02) — no second cancel mechanism, no new event type:
  - Condition A (clarify): the engine's clarify drain loop already wakes every 1s on its `wait_for` heartbeat timeout; add a `cancel_event.is_set()` check there → cancel the clarify task + yield the existing `pipeline_cancelled`.
  - Condition B (declared gate): thread `cancel_event=self.cancel_event` from `KernelServices.run_human_gate` into `_run_review_gate` so the EXISTING cancel race (engine.py cancel-aware `asyncio.wait`) fires exactly as it does at the inline gate sites; the downstream `_gate_rejected`→`GATE_BLOCK`→`cancel`→`pipeline_cancelled` chain already exists.

Purpose: make the chat "convert → chain" work as the user expects and make Stop honor its contract from the two states where it silently no-ops today, WITHOUT touching the chaining machinery, the cooperative-cancel MODEL, the review-gate vocabulary, or clarify semantics.

Output: BUG-1 offline-proven via vitest; BUG-2 offline-proven via targeted pytest + the 5 goldens; the ORCHESTRATOR owns the live re-proof of both.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md

Standing constraints (BINDING for every task in this plan):
- Branch **feat/ui-2** — verify with `git branch --show-current`; NEVER main/dev/staging. Commit with the repo convention: a `fix(chat): ...` style prefix for the FE task; a backend scope (`fix(engine): ...` for engine.py — kernel_services.py changes ride the same `engine`/`runner` scope per backend/CLAUDE.md) for the BE task. **NO commit trailer. NEVER push. NEVER `git stash`.**
- Python **python3.11**, **no venv**. Run backend commands with an **absolute** `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend` (cwd resets between calls).
- Frontend vitest is **cwd-sensitive** — run it from an **absolute** `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend`, never `--root frontend` from the repo root.
- Two tasks, ONE executor, SEQUENTIAL (Task 1 = FE, Task 2 = BE) → two atomic commits. Keep FE and BE edits in their own task/commit.
- A live backend (:8000, `--reload`) + Next (:3000) may be running — do NOT restart/kill/bind them; run OFFLINE tests only. **NO live Bedrock in the executor.**
- SEE RED FIRST: for every new/rewritten test, run it against the UNCHANGED source and OBSERVE it fail (record the failure output) before applying the fix. A test not seen failing is not trusted.
- Re-verify every line anchor below before editing (line numbers drift; anchors were spot-checked at plan time).
</execution_context>

<context>
@.planning/quick/260720-ec4-fix-convert-chain-misroute-stop-cancel/260720-ec4-CONTEXT.md
@backend/CLAUDE.md
@frontend/src/components/chat/RunChatLane.tsx
@frontend/src/components/chat/RunChatLane.test.tsx
@backend/agents/execution_engine/engine.py
@backend/agents/execution_engine/kernel_services.py
@backend/agents/execution_engine/clarify_engine.py
@backend/agents/capabilities/gates/human.py
@backend/tests/agents/test_gates.py
@backend/tests/agents/test_restart_resume.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: BUG-1 — route a "&lt;transform&gt; into &lt;available chain target&gt;" chat phrase to the chain seam (onSuggestion) instead of a revision (FE-only, SC-001-safe)</name>
  <files>frontend/src/components/chat/RunChatLane.tsx, frontend/src/components/chat/RunChatLane.test.tsx</files>
  <behavior>
    - Completed run, suggestions=[{id:"ppt",label:"Presentation"},{id:"prototype",label:"Prototype"}], onSuggestion=vi.fn(), onRevise=vi.fn(): typing "convert it into presentation" + send calls onSuggestion("ppt") exactly once and does NOT call onRevise, does NOT surface a chat-refinement-chip, does NOT call sendMessage.
    - NEG (same-run edit): "convert the buttons into pills" with the SAME suggestions → still the held-refinement/change path (chat-refinement-chip appears), onSuggestion NOT called.
    - NEG (no target available): no suggestions prop → change path unchanged; the 43-02 route matrix + 44-02 confirm-chip tests stay green, byte-identical.
    - The c72 chain_hints-send test ("what's the status?" ASK with suggestions) stays green: an ASK phrase has no transform-into-target shape → matcher returns null → falls through to the concierge send with chain_hints.
    - The SC-001 source test stays green: the new helper introduces NO `"prototype"`/`od_ppt`/`app_builder`/`user_stories` literal (the transform verbs + connectors are generic English; the target is read from suggestions[].label).
  </behavior>
  <action>
    In `RunChatLane.tsx`, add a small pure helper `matchChainTarget(text: string, suggestions?: LaneSuggestion[]): string | null` near `classifyFreeText` (~:300). It returns the matched suggestion's `id` (or null) using a TWO-part gate so it fires ONLY on a chain-shaped phrase that NAMES a currently-available target — this data-driven target match is the SC-001-safe key (never a hardcoded "ppt"/"presentation"/workflow-name literal):
    1. Transform shape: the text (lowercased/trimmed) matches a generic transform-verb-then-connector pattern — a verb alternation `\b(convert|turn|make|transform|change|render|export|generate)\b` FOLLOWED (anywhere later in the string) by a connector `\b(into|to|as)\b`. If no connector is present, return null (a bare "make it bigger" is NOT a chain phrase — it stays a change).
    2. Named available target: take the TAIL after the FIRST connector occurrence; for each suggestion in `suggestions` (return null if empty/undefined), match case-insensitively if the tail contains `suggestion.label` as a substring, OR contains any whitespace-split token of the label with length >= 4. Return the FIRST matching suggestion's `id`; else null. Matching against the TAIL (not the whole text) is load-bearing so "convert the presentation-buttons into pills" does not spuriously match — only a target NAMED as the transform destination counts.

    Wire it into `handleFreeText` (:961-992): inside the existing `if (runState === "complete") {` block, BEFORE the `classifyFreeText(text) === "ask"` check (:964), add: `const chainId = matchChainTarget(text, suggestions); if (chainId && onSuggestion) { onSuggestion(chainId); return; }`. This requires a NAMED available target AND an onSuggestion handler — otherwise it falls through to the EXISTING ask/change/held-refinement behavior UNCHANGED. Add `onSuggestion` to the `handleFreeText` useCallback dependency array (:991 — currently `[runState, onRevise, sendMessage, suggestions]` → add `onSuggestion`). Do NOT reorder or weaken `CHANGE_INTENT`/`ASK_INTENT`, do NOT touch classifyFreeText, the held-refinement machinery, the c72 chain_hints fold, renderChainSuggestions, or DashboardLayout.tsx.

    Tests (RED→GREEN) in `RunChatLane.test.tsx` — add a new describe-block or adjacent `it`s near the 43-02 route matrix (:402-451), reusing the `baseProps` helper and the existing fireEvent idiom (getByLabelText("Chat message input") → change → click getByTestId("chat-send")):
    - "settled-run 'convert it into presentation' with a matching chain target fires onSuggestion(ppt) and does NOT revise": render runState:"complete", suggestions:[{id:"ppt",label:"Presentation"},{id:"prototype",label:"Prototype"}], onSuggestion:vi.fn(), onRevise:vi.fn(), sendMessage:vi.fn(); type "convert it into presentation"; assert onSuggestion called once with "ppt", onRevise not called, sendMessage not called, queryByTestId("chat-refinement-chip") is null.
    - "settled-run transform phrase with NO matching target stays a change (held refinement)": same suggestions, type "convert the buttons into pills"; assert onSuggestion NOT called and getByTestId("chat-refinement-chip") present (onRevise held, not launched — 44-02 behavior).
    - "settled-run chain phrase with no suggestions supplied stays a change": no suggestions prop, onRevise:vi.fn(); type "convert it into presentation"; assert onSuggestion undefined-path (not called) and chat-refinement-chip present.
    Leave the c72 chain_hints-send test (:254), the 43-02 route matrix (:424), the 44-02 confirm-chip tests (:310-381), and the SC-001 source test (:969) UNCHANGED and green.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && npx vitest run src/components/chat/RunChatLane.test.tsx</automated>
  </verify>
  <done>A completed-run "&lt;transform&gt; into &lt;named available target&gt;" phrase fires onSuggestion(thatId) and never holds a refinement / calls onRevise; a transform phrase with no matching (or no) available target keeps the exact existing change→held-refinement path; the c72 + 43-02 + 44-02 + SC-001 tests stay green; RunChatLane.test.tsx passes. RED evidence recorded: before the change the new match test calls onRevise/holds a refinement instead of onSuggestion. Banned-pattern grep unchanged: `grep -cE 'prototype|ppt|user_stories|app_builder' src/components/chat/RunChatLane.tsx` stays 0.</done>
</task>

<task type="auto">
  <name>Task 2: BUG-2 — make Stop cancel-aware at the clarify drain loop (Condition A) AND the declared-gate delegate (Condition B), reusing the shipped cancel race + pipeline_cancelled</name>
  <files>backend/agents/execution_engine/engine.py, backend/agents/execution_engine/kernel_services.py, backend/tests/agents/test_gates.py, backend/tests/agents/test_restart_resume.py</files>
  <behavior>
    - Condition A: with a run parked at clarify (the engine drain loop draining the ClarifyEngine event queue while clarify.run blocks at event.wait), setting the shared cancel_event makes the engine yield the existing pipeline_cancelled terminal and cancel the clarify task — within ~1s (the drain loop's heartbeat). RED pre-fix: the drain loop ignores cancel_event → the generator never yields pipeline_cancelled → a bounded asyncio.wait_for raises TimeoutError.
    - Condition B: run_human_gate now passes cancel_event into _run_review_gate; with cancel_event set, the EXISTING race in _run_review_gate yields _gate_rejected, which the human gate maps to GATE_BLOCK, which _evaluate_gates maps to the `cancel` sentinel, which the dispatch loop emits as pipeline_cancelled. RED pre-fix: _run_review_gate receives no cancel_event on the delegate path → blocks on only the review event.
    - Dormancy (INV-3): when cancel_event is None (scripted/golden runs), BOTH additions are inert — the drain loop's `continue` and the gate's plain `await event.wait()` are byte-identical to today. The 5 characterization goldens stay 10/10 byte/event-identical.
    - No new event type (reuse pipeline_cancelled), no second cancel mechanism, no destructive whole-run task.cancel(), no workflow/agent-name literal (keys ONLY on the generic cancel_event).
  </behavior>
  <action>
    Condition A — `engine.py` clarify drain loop (~:1928-1935, the `while not clarify_task.done():` loop whose body does `event = await asyncio.wait_for(event_queue.get(), timeout=1.0)` and `except asyncio.TimeoutError: continue`). `cancel_event` is the `execute(...)` parameter and is in scope here (it is the SAME object passed into KernelServices at ~:1999 and into ClarifyEngine's run accounting). In the `except asyncio.TimeoutError:` branch, BEFORE the existing `continue`, add a cooperative-cancel check: if `cancel_event is not None and cancel_event.is_set()`, then cancel the clarify task (`clarify_task.cancel()`), await it defensively swallowing `asyncio.CancelledError` (and any Exception — a cancelled clarify may raise on teardown), transition the state machine to "cancelled" (`self._state_machine.transition(pipeline_run_id, "cancelled")`), yield the existing terminal `{"type": "pipeline_cancelled", "data": {"pipeline_run_id": pipeline_run_id}}` (mirror the canonical per-chunk cancel terminal at ~:2473), and `return` from execute. Do NOT add a new event type, do NOT change ClarifyEngine's signature, do NOT touch the queue-drain success path. Keep the check ONLY in the timeout branch (the loop's designed 1s wake point) so latency is bounded and the golden path is untouched.

    Condition B — `kernel_services.py` `run_human_gate` (:1079; delegate call :1109-1114). `KernelServices.__init__` already stores `self.cancel_event = cancel_event` (:194, threaded from `engine.execute` at engine.py ~:1999). Add `cancel_event=self.cancel_event` as a keyword arg to the `self._engine._run_review_gate(...)` call at :1109 (alongside pipeline_run_id/agent_id/agent_name/output). That is the ONLY production change for Condition B — the existing cancel race (engine.py `_run_review_gate` ~:5126-5147: when `cancel_event is not None`, race `event.wait()` vs `cancel_event.wait()` → yield `_gate_rejected`) then fires on the declared path exactly as at the inline sites, and the downstream mapping (`human.py` `_gate_rejected`→GATE_BLOCK; engine.py `_evaluate_gates` block→`cancel`; dispatch loop `cancel`→pipeline_cancelled) is UNCHANGED. Do NOT change `_run_review_gate`'s None-cancel_event behavior (it stays the plain `await event.wait()` for any other None caller).

    Tests (RED→GREEN):
    - Condition B in `backend/tests/agents/test_gates.py`: the existing `_FakeReviewEngine._run_review_gate` (~:919) signature is `(*, pipeline_run_id, agent_id, agent_name, output)` — it has NO `cancel_event` param, so once run_human_gate forwards `cancel_event=self.cancel_event` the two existing run_human_gate tests (:959, :974) would raise TypeError. REQUIRED: extend `_FakeReviewEngine._run_review_gate` to accept `cancel_event=None` and record it (`self.seen_cancel = cancel_event`; init `self.seen_cancel = None`). Extend `_kernel_services` (:931) to accept an optional `cancel_event` (default None → existing callers byte-unchanged) and pass it into the KernelServices build (:953). Add `test_run_human_gate_threads_cancel_event_into_review_gate`: build an `asyncio.Event()` `ev`, `ks, _ = _kernel_services(_FakeReviewEngine([{"type":"review_gate_ready","data":{}}]), cancel_event=ev)`, monkeypatch `_spec_for`, drive `run_human_gate`, assert `fake_engine.seen_cancel is ev`. RED pre-fix: `seen_cancel is None`. Keep the two existing run_human_gate tests (:959, :974) green (they pass cancel_event=None → seen_cancel is None, unchanged assertions).
    - Condition A in `backend/tests/agents/test_restart_resume.py` (the offline `execute()` harness): add an ADDITIVE optional `clarify_mode: str = "off"` param to `_ResumeHarness.__init__` and use it inside `_patched_compile` (:228-235) in place of the hardcoded `compiled.clarify.mode = "off"` — default "off" keeps EVERY existing caller byte-identical. Add `test_stop_at_clarify_yields_pipeline_cancelled`: enter the harness with `clarify_mode="auto"`; `engine = harness.make_engine()`; override `engine._run_planner` to return a planning context WITH `missing_information` non-empty (e.g. `{"execution_gate":"CLARIFY_REQUIRED","missing_information":["target audience"],"explicit_constraints":[]}`, "CLARIFY_REQUIRED") so ClarifyEngine emits questionnaire_ready and PARKS (no answers submitted); build `ev = asyncio.Event()`; drive `engine.execute(...)` (same call shape the headline tests use, plus `cancel_event=ev`) inside a bounded `asyncio.wait_for(..., timeout=8)` loop that iterates the async generator, and the FIRST time a `questionnaire_ready` event is seen, `ev.set()`. Assert a `pipeline_cancelled` event is yielded (and no TimeoutError). We cancel AT clarify, before any domain agent runs, so the fixture's scripted agent models never matter. RED pre-fix: the drain loop ignores `ev` → execute hangs at clarify → `asyncio.wait_for` raises `TimeoutError` (a clean regression signal). If reusing `_ResumeHarness` proves too heavy, the acceptable fallback is a focused execute-park test in `tests/unit/test_execution_engine.py` using the same offline execute machinery (InMemory checkpointer + temp RUNS_ROOT + a parking ClarifyEngine) — but the assertion contract (set cancel_event on questionnaire_ready → pipeline_cancelled within a bounded wait_for) is identical.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_gates.py tests/agents/test_restart_resume.py -q</automated>
  </verify>
  <done>Stop cancels a clarify-parked run (drain loop yields pipeline_cancelled + cancels the clarify task) and a declared-gate-parked run (cancel_event reaches run_human_gate→_run_review_gate → existing race → pipeline_cancelled); run_human_gate forwards self.cancel_event; the extended _FakeReviewEngine records it; test_gates.py + test_restart_resume.py green. RED evidence recorded for BOTH conditions (Condition A: bounded wait_for TimeoutError pre-fix; Condition B: seen_cancel is None pre-fix). The 5 characterization goldens stay 10/10 (verify block). Banned-pattern grep unchanged: engine.py stays 87, kernel_services.py stays 19 for `grep -cE 'prototype|ppt|user_stories|app_builder'`.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| chat free-text → run action (FE) | Untrusted user text on a completed run is classified into a chain action (onSuggestion) vs a revision (onRevise). BUG-1 adds one more branch (chain) ahead of the existing ask/change split. |
| Stop button (client) → engine cooperative cancel | The FE POST /api/runs/{id}/cancel sets the shared asyncio.Event; the engine reacts cooperatively. BUG-2 widens WHERE the engine observes that already-authenticated signal (clarify + declared gate). No new surface. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-ec4-01 | Tampering / mis-route | matchChainTarget on completed-run free text | mitigate | The chain branch fires ONLY on a transform-shape phrase whose tail NAMES a currently-available suggestion (data-driven against suggestions[].label) AND requires an onSuggestion handler; any non-match falls through to the UNCHANGED ask/change path. Chaining still runs through the existing onSuggestion→handleChainPipeline launch (the same auth/launch path the chips use) — nothing new executes. |
| T-ec4-02 | Elevation / bypass | Stop cancel-awareness at clarify + declared gate | mitigate | Reuses the shipped cooperative-cancel MODEL (Phase 16-02) — no destructive whole-run task.cancel(), no second cancel mechanism. The endpoint auth is unchanged (POST /api/runs/{id}/cancel two-layer owner check); the engine only widens where it observes the SAME cancel_event. Emits the existing pipeline_cancelled terminal. |
| T-ec4-03 | Denial of service / hang | clarify drain-loop cancel + gate race | accept | The cancel check runs on the drain loop's existing 1s heartbeat (bounded latency); the gate race is the already-shipped inline pattern. No new unbounded wait is introduced; the dormant (cancel_event None) path is byte-identical. |
| T-ec4-SC | Tampering | package installs | mitigate | NONE — no new dependency. FE adds one pure helper + a branch; BE adds a loop check + one keyword arg + test-harness fields. |
</threat_model>

<verification>
Offline gates — ALL must be green (NO live Bedrock; the ORCHESTRATOR owns the live re-proof of BOTH bugs):

1. FE (from `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend`, cwd-sensitive):
   `npx vitest run src/components/chat/RunChatLane.test.tsx` — chain-route match fires onSuggestion; NEG (no-target / no-suggestions) stays change; c72 + 43-02 + 44-02 + SC-001 tests green.
2. BE targeted (from `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend`, python3.11, no venv):
   `python3.11 -m pytest tests/agents/test_gates.py tests/agents/test_restart_resume.py -q` — Condition A (clarify cancel) + Condition B (delegate threading) green; the existing gate/restart suites stay green.
3. INV-3 goldens byte/event-identical (SNAPSHOT_UPDATE unset):
   `python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py -q` — the 5 characterization suites stay 10/10 (the cancel path is dormant on scripted runs).
4. INV-1/SC-001 banned-pattern gate on EVERY edited source file (must stay at baseline — no new workflow-name literal):
   `grep -cE 'prototype|ppt|user_stories|app_builder' frontend/src/components/chat/RunChatLane.tsx` stays **0**;
   `grep -cE 'prototype|ppt|user_stories|app_builder' backend/agents/execution_engine/engine.py` stays **87**;
   `grep -cE 'prototype|ppt|user_stories|app_builder' backend/agents/execution_engine/kernel_services.py` stays **19**.
5. Import-linter contracts intact:
   `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken (no new kernel/app edge; human.py stays capability-side).
</verification>

<success_criteria>
- BUG-1: on a completed run, a "&lt;transform&gt; into &lt;named available chain target&gt;" chat phrase chains via onSuggestion(id); a transform phrase with no matching (or no) available target keeps the exact existing change→held-refinement/revise path. The match is data-driven against suggestions[].label — no workflow-name literal (SC-001), and the disambiguation guard preserves same-run edits.
- BUG-2: Stop cancels a run parked at clarify (drain-loop cancel_event check → pipeline_cancelled + clarify task cancelled) AND a run parked at a declared human/approval gate (cancel_event threaded into run_human_gate → the existing race → pipeline_cancelled). Reuses the shipped cooperative-cancel MODEL + the existing pipeline_cancelled terminal — no new event type, no second mechanism.
- Dormancy: cancel_event None ⇒ both BE additions inert; the 5 characterization goldens stay 10/10 byte/event-identical.
- FE vitest + BE targeted suites green; goldens 10/10; banned-pattern grep at baseline on all edited files (RunChatLane.tsx=0, engine.py=87, kernel_services.py=19); lint-imports 4/0.
- Two atomic commits on feat/ui-2 (FE, then BE); NO trailer; NOT pushed.
</success_criteria>

<output>
Create `.planning/quick/260720-ec4-fix-convert-chain-misroute-stop-cancel/01-SUMMARY.md` when done. Record: the matchChainTarget shape (transform-verb + connector + tail label-match) and its handleFreeText insertion point; the BUG-2 plumbing actually used (drain-loop cancel_event.is_set() check in the 1s-timeout branch; the one-line cancel_event=self.cancel_event thread in run_human_gate, backed by KernelServices storing self.cancel_event from execute); the RED evidence for all three test cases; and confirmation that the 5 goldens / banned-pattern greps (0 / 87 / 19) / lint-imports (4/0) held.
</output>
