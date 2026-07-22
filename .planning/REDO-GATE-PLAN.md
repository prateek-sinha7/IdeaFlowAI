# REDO-GATE-PLAN — "Redo with additional instructions" on the human review gate

> Branch: `new-workflow-engine` (the LIVE manifest-driven engine). Repo:
> `/Users/1000060523/Documents/Work/UKI/Flowin/flowin`.
> Status: PLAN ONLY — no feature code written. Every claim below is cited to
> `file:line` against code read on this branch. Where a fact was not verifiable in
> code it is marked **unverified**.

---

## Revision log (post-review v2)

This is **v2** — a rewrite of v1 that folds in the senior-architect review
(`.planning/REDO-GATE-PLAN-REVIEW.md`, verdict **NEEDS-REVISION**, findings F1–F10).
v1's architecture was endorsed and is **kept verbatim**: extend `approve_review`
(don't add a WS message), reuse the one `_run_review_gate` pause + the one
`set_review_response`/`get_review_event` resume channel + the one `_run_agent`
dispatch + `ArtifactGraph` versioning, additive `ectx` scratch, **no migration**.
The changes below are targeted fixes, not a re-architecture.

| Δ | Review finding | What changed vs v1 |
|---|----------------|--------------------|
| **Scope** | F1 fallout | **v1 is now explicitly INLINE-ONLY (locked).** Declared / user-composed `gate:human` is fenced OUT (no Redo button, signal safely consumed); full declared-path redo is a documented FOLLOW-UP. See §0. |
| **F1a** | BLOCKER | New backend task **T-human** (`gates/human.py`): `HumanGate.evaluate_stream` (and the check `ApprovalGate`) must **consume** `_gate_redo` — never `yield` it, never fall through to `GATE_PASS`. Makes the shared-primitive change (B3) safe on the declared path. |
| **F1b** | BLOCKER | New generic `redoable: bool` discriminator on `review_gate_ready`, emitted **True only from the inline call site**; FE shows Redo **iff `redoable`**. Keyed on the gate path, no workflow/agent literal (SC-001). Added to `_VOLATILE_STRIP_KEYS` so goldens stay byte-identical. |
| **F2** | HIGH | B4 is no longer recursion. The inline run+gate becomes a **`while True:` loop** inside `_run_agent` — unbounded-safe by construction (flat stack, O(1) per event). |
| **F3** | HIGH | Consume-once is now **unconditional**: the redo directive + `derived_from` are drained into loop locals at re-run entry and the `ectx`/loop state nulled immediately — an empty-output or exception path can no longer leak a spurious `derived_from`/REVISE block onto the next agent. |
| **F4** | MEDIUM | Doc correction: durable-resume of a paused-with-pending-redo gate is **NOT "handled."** `restore_non_terminal_runs` marks the `waiting_for_user` run **failed** (`engine.py:4007-4025`); pending redo is **LOST**. Stated as a known v1 limitation (§9 R3, matrix). |
| **F5** | MEDIUM | New task: `_latest_typed_content` selects **latest by `version`** (max), not `tree()` insertion order, so a rejected prior version can never win after persist+rehydrate. +regression test. |
| **F6** | LOW | Note + test for the untested **retry × gate × redo** edge (now reachable since Phase-22 wires a per-step `retry:` lever onto gatable steps). No code change. |
| **F7** | MEDIUM | **OPTIONAL/high-value** task: make the gate wait cancel-aware (race `cancel_event` with the review event) — the Stop-while-paused gap is pre-existing (`engine.py:3918`) and unbounded redos amplify it. Not required for v1. |
| **F8** | MEDIUM | FE robustness: agent panel idempotent on a repeated `agent_start`/`agent_complete`; reconnect-after-N-redos renders cleanly; cumulative token cost across attempts is intended + documented. |
| **F9/F10** | LOW | B8 audit row stays in the inline consumer (not `_run_review_gate`, which has no `ectx`); the F1 fix also gives the declared path an honest audit outcome. §3.1 prose corrected re the resume dict name. |
| **Matrix** | — | The SC-001/INV-1 and INV-12 rows flip from **ISSUE → PASS** for the v1-inline scope once F1 lands; declared-path coverage noted as a follow-up. |

---

## 0. Scope decision — v1 = INLINE-ONLY (LOCKED)

v1 wires Redo for the **inline human-gate path only**. This is not a narrowing of the
feature's reach today — it is the *full* reach today:

- The LIVE human gates (`prototype-specify`, `prototype-plan`) declare BOTH
  `gate: Human_Gate` (`backend/agents/prompts/prototype-specify/AGENT.md:5`,
  `backend/agents/prompts/prototype-plan/AGENT.md:7`) AND `gates: [human]`
  (`backend/agents/workflows/prototype/workflow.yaml:38,41`), and the **WR-02 dedupe**
  skips the declared `human` gate whenever the inline gate fires
  (`engine.py:3727` `if name == "human" and inline_gated and phase == "pre": continue`).
  So **every live human gate runs through the inline consumer** (`engine.py:3238-3281`).
  ⇒ v1 covers all *live* human gates.

- **Declared / user-composed `gate:human`** (addable via the Phase-22 AdvancedExpander —
  `gate:human` is `user_allowed=True`, `human.py:45`) must **NOT break** and must **NOT
  show a Redo button**. Such a gate has `_should_gate(spec, ectx) == False`
  (`engine.py:3531-3548`), so WR-02 does NOT dedupe it (`engine.py:3727` needs
  `inline_gated`) and the **declared `human` gate runs** via
  `_evaluate_gates → HumanGate.evaluate_stream` (`human.py:56`). v1 fences this path:
  1. The FE shows Redo **iff** the new generic `redoable` flag is set on
     `review_gate_ready` — which only the inline call site sets (F1b). A declared gate's
     `review_gate_ready` carries `redoable=false` → no Redo button.
  2. `HumanGate.evaluate_stream` **consumes** any stray `_gate_redo` it receives (a
     malicious/scripted client could still send `action:"redo"`) and maps it to a
     **non-PASS** outcome — never yields the internal signal to the wire, never silently
     advances (F1a / T-human).

- **Declared-path redo is an explicit FOLLOW-UP (out of scope v1).** A *real*
  `GateOutcome` `"redo"` that re-runs the gated *producer* step from the dispatch loop
  is a genuinely different mechanism (the declared `human` gate is a PRE-step gate over
  the PREVIOUS step's output — `human.py:84` reads `ctx.last_streamed`), and it deserves
  its own plan. It is **not** wired in v1.

**Reconciliation with the original locked decision #3 ("Generic / all human gates").**
v1 satisfies decision #3 for **all human gates that route through the inline path = every
live human gate today**, name-free (SC-001). Decision #3's *aspirational* full coverage
of declared/user-composed human gates is delivered by the documented follow-up. v1 does
not regress the declared path: it stays safe (no leak, no silent pass) and simply does not
*offer* redo — which is the correct behavior for an un-wired path.

---

## 1. Feature + the 4 locked decisions

At a human review gate (today the FE offers Approve / Edit / Cancel via the
`approve_review` WS message), add a **Redo** action: re-run **the gated agent in
place** (a fresh model call), optionally with extra free-text instructions, then
**re-pause at the SAME gate** showing the new output. The old output is kept as a
prior version.

Locked product decisions (design to these exactly; not re-decided here):

1. **Unbounded** redos per gate (human-paced; no cap). ⇒ The re-run MUST be a loop, not
   recursion (F2) — see §3.4.
2. **Optional** instructions — empty = plain regenerate (same context, fresh
   sample); with text = the note is injected as an extra directive for the re-run.
3. **Generic / all human gates (SC-001)** — the redo path keys on the generic gate
   decision + the generic `_should_gate` predicate, NEVER a workflow name or
   agent-id literal in the kernel. **v1 = all *live* (inline) human gates; declared
   coverage is the follow-up — see §0.**
4. **Keep old output as a prior `ArtifactGraph` version** — supersede via a new
   version with `derived_from` lineage to the rejected one. NEVER delete.

---

## 2. Current-state grounding (how it works TODAY — each claim cited)

### 2.1 Two gate paths, one resume channel — and which is LIVE

There are two entry points that BOTH funnel into the single engine pause primitive
`_run_review_gate`:

- **Inline path (LIVE for prototype).** `_run_agent` runs the agent, finalizes
  `output`, persists it, emits `agent_complete`, then — if `_should_gate(spec, ectx)`
  — drives `_run_review_gate` inline and consumes its events:
  `engine.py:3238` (`if self._should_gate(...)`),
  the `async for gate_event in self._run_review_gate(...)` at `engine.py:3239-3244`,
  and the consumer branches `_gate_rejected` (`engine.py:3245`) / `_gate_edited`
  (`engine.py:3256`) / else-`yield` (`engine.py:3280-3281`).
- **Declared path.** A step's `gates: [human]` is evaluated at the step boundary by
  `_evaluate_gates` (`engine.py:1832` pre-phase / `engine.py:3676`), which resolves
  the registered `human` gate (`backend/agents/capabilities/gates/human.py:48`),
  whose `evaluate_stream` (`human.py:56`) delegates to
  `ctx.runner.run_human_gate` (`backend/agents/execution_engine/kernel_services.py:1061`)
  → the SAME `_run_review_gate` (`kernel_services.py:1091`). `_evaluate_gates` **forwards
  any dict the gate yields straight to the wire** with a non-halting `"pass"` placeholder
  (`engine.py:3748-3761`) — this is the F1 leak path.

`_should_gate` is generic: it gates iff `spec.id ∈ ectx.gate_agent_ids` (per-run
opt-in) else iff the AGENT.md frontmatter declares `gate: Human_Gate`
(`engine.py:3531-3548`). No workflow-name branch.

**The LIVE prototype gate is the INLINE path.** Per §0 (WR-02 dedupe at `engine.py:3727`),
for every current human gate the inline consumer is the single review — the declared
`human` gate is dormant. **⇒ The redo branch belongs in the inline consumer; it then
covers every LIVE human gate and any future agent that declares `gate: Human_Gate` or is
opted into `gate_agent_ids`.** The declared `human` gate is a **shared consumer of the
same `_run_review_gate`** and so must be taught to consume `_gate_redo` safely (T-human).

### 2.2 The pause/resume mechanism (the KEY question)

`_run_review_gate` (`engine.py:3870-3948`):

1. `gate_key = f"{pipeline_run_id}:{agent_id}"` (`engine.py:3885`).
2. Arms an `asyncio.Event` and clears it: `event = await self._store.get_review_event(gate_key); event.clear()` (`engine.py:3888-3889`).
3. `self._state_machine.transition(pipeline_run_id, "waiting_for_user")` (`engine.py:3902`).
4. `yield {"type": "review_gate_ready", "data": {... "gate_key", "output" ...}}` (`engine.py:3905-3915`).
5. **Blocks**: `await event.wait()` (`engine.py:3918`) — waits ONLY on the review event,
   NOT on any cancel event (`_run_review_gate` has a 4-param signature, no `cancel_event`).
   This is the pre-existing Stop-while-paused no-op (F7).
6. On resume: `response = await self._store.get_review_response(gate_key)` (`engine.py:3920`); reads `approved` (`:3921`) and `edited_content` (`:3922`).
7. If approved → transition to `"generating"` (`:3927`), `yield review_gate_approved` (`:3937-3945`), and if edited `yield {"type":"_gate_edited","edited_content":...}` (`:3947-3948`). If not approved → `yield {"type":"_gate_rejected"}` (`:3934`).

The signal channel is the in-process `ArtifactStore`
(`backend/agents/artifact_store/store.py`):
- `get_review_event(gate_key)` returns the `asyncio.Event` keyed `review:{gate_key}` (`store.py:111-116`).
- `set_review_response(gate_key, approved, edited_content)` stores `[{"approved","edited_content"}]` under the key `"review:"+gate_key` **in `self._questionnaire_responses`** (a different dict than `_resume_events`) and `event.set()` (`store.py:118-124`). *(v1 prose said "stores under `review:{gate_key}`" — the key prefix is right; the dict is `_questionnaire_responses`, F10. Immaterial to the additive-kwargs change.)*
- `get_review_response(gate_key)` returns that dict (`store.py:126-130`).

The WS handler that signals the resume (`backend/app/api/websocket.py:1180-1205`):
reads `gate_key` / `approved` / `edited_content` (`:1182-1184`); **owner-gates** via
`_review_gate_owned_by(gate_key, user.id)` (`:1196`, defined `:223-247` — matches
`WorkflowRun.user_id`, denies unknown/unowned identically); then
`store.set_review_response(gate_key, approved=approved, edited_content=edited_content)`
(`:1204`). The handler is the documented "cross-run WRITE" boundary (`:1192-1195`).

Engine events reach the FE through a **generic passthrough** (no allow-list): the
drainer task pushes every engine event by type+data —
`await event_queue.put({"type": update["type"], "data": update.get("data", {})})`
(`websocket.py:1798`) — and the WS send loop forwards `{"type": event["type"], ...,
"data": event.get("data", {})}` (`websocket.py:2040-2043`). The internal
`_gate_rejected` / `_gate_edited` signals are **consumed inside `_run_agent`**
(`engine.py:3245,3256`) and never put on the queue. **`_gate_redo` MUST be consumed the
same way on BOTH consumers (inline + declared) — that is the crux of F1.**

### 2.3 GateOutcome / GateHandler port

`GateHandler` Protocol: `name: str` + `async evaluate(step, ctx) -> Any` returning
`pass | block | wait_human` (`backend/agents/capabilities/base.py:104-112`).
`GateOutcome` carries `outcome` + `events` + `detail` (used in `human.py:120`,
`approval.py:185`). The **inline path does NOT touch the port** — it calls
`_run_review_gate` directly. The **declared path DOES** go through `HumanGate` (and the
check gate `ApprovalGate`), whose `evaluate_stream` consumes `_gate_rejected`/`_gate_edited`
and yields the public events; an **unrecognized `_gate_redo` currently falls to
`else: yield event` (`human.py:106`) and then `outcome = GATE_PASS` (`human.py:108`)** —
the F1 defect. v1's LIVE inline redo needs no port change; v1's declared-path *fence*
(T-human) adds a consume-arm to `HumanGate.evaluate_stream` — no `GateOutcome`
contract change (the new outcome is the already-valid `wait_human`/`block`).

### 2.4 Artifact versioning (content-addressed, additive)

`ArtifactGraph.write_ref` auto-assigns `version = 1 + count of existing refs with
the same (run_id, kind)` and accepts `derived_from` + `parents`
(`backend/agents/artifacts/graph.py:118-180`, version at `:157-159`, `derived_from`
field at `:99,131,174`, `version` field at `:96`). `_dual_write_artifact` writes the
in-memory graph + (best effort) the `artifact_refs` DB row, and already accepts
`derived_from` (`engine.py:4578-4634`, the `derived_from` param at `:4588`, threaded to
`write_ref` at `:4613`). `_latest_typed_content` returns the latest ref for a producer
**by `tree()` insertion order** (`engine.py:4636-4654`, the loop at `:4651-4653`) — this
is the F5 defect: after persist + rehydrate, insertion order is whatever
`ScopedStore.tree()` returns, so a *rejected* prior version could win. The agent's normal
output is persisted in `_run_agent` at `engine.py:3157-3179` (main handoff, inside
`if output:`, `_kind = _artifact_kind_for(spec)`) and `:3190-3200` (each `produces`
kind). `_artifact_kind_for` maps specify→`spec`, plan→`task_list`, build→`html_file`,
validate→`validation_report`, else `summary` (`engine.py:4561-4576`).
`ArtifactGraph.list_by_kind` exists (`graph.py:205`) and `tree` at `graph.py:247`.

The `artifact_refs` table already has `version`, `derived_from` (self-FK),
`parents`, `owner_id`, `workspace_id`
(`backend/alembic/versions/0014_typed_artifacts_persistence.py:46-72`).

### 2.5 The generic context injector (instructions seam)

`_compose_context_message` is the sole per-agent context-composition path
(`engine.py:5465-5614`; live caller `_run_agent` at `engine.py:2550-2553`; also called
directly by tests `test_agent_input_event.py:138/154/164` and monkeypatched by
`test_phase3_token_delta_live.py:227,277`). It builds `parts` from the user brief, planning
context, declared OD/context_provider blocks, consumed upstream outputs (`:5593-5598`), and
the build-loop `=== CURRENT TASK ===` block (`:5600+`). It reads per-run scratch off `ectx`
(e.g. `ectx.build_task_number`). **Its signature is kept unchanged** (the redo directive
rides an additive `ectx` field), so the test monkeypatch + direct callers stay valid (no
blast radius). `ExecutionContext` is a plain mutable `@dataclass`
(`backend/agents/execution_engine/context.py:40-41`) already carrying scratch fields like
`build_task_number` (`:137`) — so an additive `redo_directive` field is the same established
D-03 idiom.

### 2.6 State machine

`StateMachine.transition` validates only that the TARGET is in `VALID_STATES`
and the CURRENT state is non-terminal — there is **no from-state adjacency matrix**
(`backend/agents/execution_engine/state_machine.py:66-98`). `generating` and
`waiting_for_user` are both valid (`:30-36`). The 2-gate prototype run already
cycles `generating → waiting_for_user → generating` per gated agent, so the redo's
extra cycles are within the existing contract.

### 2.7 gate_events audit table

`gate_events` (migration `0016_capability_hardening_tables.py`) carries
`owner_id`+`workspace_id` (`nullable=False`) and `outcome` as a **plain `String`,
no enum/check** (`backend/app/models/gate_events.py`). Written owner-scoped via
`ScopedStore.record_gate_event` (`backend/agents/authz.py:736-769`) and the
`KernelServices.record_gate_event` handle (`kernel_services.py:271`). The inline review
path does **not** currently write a gate_events row (only the declared gates do, via
`write_gate_event`, `human.py:111-114`). `record_gate_event` is **not reachable inside
`_run_review_gate`** (no `ectx`/`scoped_store` in its 4-param scope, `engine.py:3870`),
so the optional redo audit row lives in the inline consumer (B8 / F9).

### 2.8 Durable resume of a paused gate (the F4 correction)

`restore_non_terminal_runs` (`engine.py:3954`) classifies a `waiting_for_user` run into
branch (a) and marks it **`failed`** — `wr.status = "failed"`, error "Run abandoned:
backend restarted while waiting for user clarification (WR-05-clarify)…", `abandoned += 1`
(`engine.py:4007-4025`). It does **NOT** re-arm the review event or re-emit
`review_gate_ready`. The redo signal (the resume dict + `asyncio.Event`) is **in-memory
only**, so a mid-gate process restart **loses the pause and kills the run**; any
already-written redo `ArtifactRef` version persists as an orphan (no corruption). This is a
pre-existing gate limitation (clarify + review both), **NOT introduced by redo and NOT
"handled" by resume** — accepted for v1, documented as a known limitation (§9 R3).

---

## 3. End-to-end design

### 3.1 Chosen WS protocol — EXTEND `approve_review` (not a new message) — KEPT

Add two optional, backward-compatible fields to the existing `approve_review`
message: `action` (`"approve"` default | `"redo"`) and `instructions` (string).
A `"redo"` action carries `approved=false` semantics on the wire but is
distinguished by `action`.

```
// approve (unchanged): { type:"approve_review", gate_key, approved:true,  edited_content?:string }
// reject  (unchanged): { type:"approve_review", gate_key, approved:false }
// redo    (new):       { type:"approve_review", gate_key, action:"redo", instructions?:string }
```

**Rationale (INV-12 reuse):** the redo is a cross-run WRITE to the same paused run,
so it must (a) pass the SAME owner gate `_review_gate_owned_by` and (b) ride the
SAME `set_review_response`/`get_review_event` resume channel. A new message type
would have to duplicate both. Extending `approve_review` reuses the live owner
boundary (`websocket.py:1196`) and the single resume channel verbatim.

### 3.2 The `redoable` discriminator (F1b) — generic FE fence

`_run_review_gate` gains a `redoable: bool = False` parameter; the value is emitted on
`review_gate_ready.data["redoable"]` (`engine.py:3905-3915`). The **inline** consumer
passes `redoable=True` (`engine.py:3239` call site); the **declared** consumer
(`kernel_services.run_human_gate → _run_review_gate`, `kernel_services.py:1091`) passes
nothing → `False`. The FE renders the Redo button **iff `review_gate_ready.data.redoable`
is true**.

- **Generic / SC-001:** keyed on whether the gate fired via the inline `_should_gate`
  path — a structural property — NOT a workflow/agent-id literal. Any future agent that
  declares `gate: Human_Gate` or is opted into `gate_agent_ids` gets `redoable=True`
  automatically; a declared/user-composed `gate:human` step gets `redoable=False`.
- **INV-3:** `redoable` is a new deterministic key on a golden-path
  (`review_gate_ready`) event ⇒ it is added to `_VOLATILE_STRIP_KEYS`
  (`tests/agents/characterization/_normalize.py:101-142`), mirroring the
  `deliverable_mimetype`/`deliverable_filename` precedent (`:139-140`) — so the 5 event
  goldens stay byte-identical. It is NOT in `_REQUIRED_DATA_KEYS`, so stripping does not
  weaken the required-keys assertion.

### 3.3 Flow (sequence)

```
USER clicks "Redo" (only shown when review_gate_ready.redoable) → optional instructions
  → page.tsx onRedoReview → send {type:"approve_review", gate_key, action:"redo", instructions}
  → WS handler approve_review (websocket.py:1180): owner-check (:1196), then
      store.set_review_response(gate_key, approved=False, action="redo", instructions=...)
  → ArtifactStore stores {approved, edited_content, action, instructions}; event.set()
  → _run_review_gate (engine.py:3918) unblocks; reads action=="redo" (NEW branch):
        state→"generating"; yield {"type":"_gate_redo","instructions":...}; return
  → INLINE consumer's while-loop (engine.py:3238-area) sees _gate_redo (NEW branch):
        prior = max-version ref of _artifact_kind_for(spec) produced by spec.id
        redo_derived_from = prior.id            (LOOP LOCAL — never on ectx)
        redo_directive    = instructions or ""  (LOOP LOCAL → ectx only around compose)
        results.pop()  # drop the rejected output's results entry
        continue        # re-run the SAME agent in the loop (NO recursion)
  → loop top: drain locals, NULL them unconditionally (consume-once, F3); re-run:
        agent_start → _compose_context_message appends
        "=== ADDITIONAL INSTRUCTIONS (REVISE) ===" iff redo_directive (set on ectx
            for THIS call only, cleared adjacently)
        → fresh deepagents create_runner + astream (INV-13) → new output
        → main artifact write (engine.py:3172) with derived_from=redo_derived_from (local)
            ⇒ new ArtifactRef, version N+1, derived_from = rejected ref id
        → agent_complete → _should_gate true → _run_review_gate again (SAME gate_key,
            redoable=True) → re-emit review_gate_ready with the NEW output → await
  → FE receives the fresh review_gate_ready (same gate_key, redoable=true) → new output
  → USER may Approve / Edit / Reject / Redo again (unbounded; loop iterates, flat stack)
```

The prior (rejected) `ArtifactRef` stays in the graph and `artifact_refs`
(additive, never deleted — decision #4); `_latest_typed_content` (now max-by-version, F5)
serves the newest version to any downstream consumer.

### 3.4 Why a loop, not recursion (F2)

Locked decision #1 is **unbounded** redos. v1's recursive re-invocation of `_run_agent`
held N nested `_run_agent` + `_run_review_gate` frames + O(N)-per-event yield propagation
until the final approval unwound them — a `RecursionError` risk for an explicitly-unbounded
operation. v2 wraps the agent-run + inline gate in a **`while True:` loop inside
`_run_agent`**: on `_gate_redo`, set the loop locals and `continue`; on approve/edit,
`break`; on reject, `return`. **Flat stack, O(1) per event, no growth** regardless of redo
count. The loop also makes consume-once (F3) natural — the redo directive and `derived_from`
are loop locals, drained and nulled at the top of every iteration.

### 3.5 Why this is generic (SC-001 / INV-1)

- The `_run_review_gate` redo branch keys on `response.get("action") == "redo"` — generic.
- The inline consumer's redo branch keys on the event type `_gate_redo` and the generic
  `_should_gate(spec, ectx)` — name-free.
- The `redoable` flag keys on the inline call site (a structural path), not a name.
- The instructions block keys on `ectx.redo_directive` — a generic scratch field.
- The re-run reuses `_run_agent`'s loop for the SAME `spec` already in scope, so it works
  for ANY inline-gated agent automatically.
- The declared-path consume-arm (T-human) keys on the event type `_gate_redo` — name-free.

---

## 4. Exact changes per file

### Backend

**B1. `backend/agents/artifact_store/store.py` — carry the redo decision.**
- `set_review_response` (`:118`): add kwargs `action: str = "approve"`,
  `instructions: str | None = None`; store them in the dict at `:121`
  (`{"approved", "edited_content", "action", "instructions"}`). Additive — existing
  callers (`websocket.py:1204`, `live_harness.py:432,481`,
  `test_declared_gate_streaming.py:180,329,454`) omit them → defaults apply →
  byte-identical resume behavior.
- `get_review_response` (`:126`): unchanged (returns the whole dict).

**B2. `backend/app/api/websocket.py` — accept the redo action on the owner-gated handler.**
- In the `approve_review` branch (`:1180-1205`): read `action =
  message_data.get("action", "approve")` and `instructions =
  message_data.get("instructions")`; map a `redo` action to
  `set_review_response(gate_key, approved=False, action="redo",
  instructions=instructions)` (else pass through for approve/reject). **Owner check at
  `:1196` is unchanged and still runs BEFORE the write** (preserves the IDOR
  mitigation + the `test_approve_review_ownership.py` ratchet). No new handler, no
  second channel.

**B3. `backend/agents/execution_engine/engine.py` — `_run_review_gate` redo branch + `redoable` (engine seam #1).**
- Add a `redoable: bool = False` parameter to `_run_review_gate` (`:3870-3876`); include
  `"redoable": redoable` in the `review_gate_ready.data` dict (`:3905-3915`).
- After `get_review_response` (`:3920`), read `action = response.get("action",
  "approve")` and `instructions = response.get("instructions")`. Insert a NEW branch
  **before** the existing approve/reject logic (`:3924+`):
  ```
  if action == "redo":
      self._state_machine.transition(pipeline_run_id, "generating")
      yield {"type": "_gate_redo", "instructions": instructions or ""}
      return
  ```
  When `action != "redo"` (every golden auto-approve, every plain approve/edit/reject)
  the existing flow at `:3924-3948` runs **unchanged**. `_gate_redo` mirrors the existing
  `_gate_rejected` shape (internal signal, consumed not forwarded).
- Add `"redoable"` to `_VOLATILE_STRIP_KEYS`
  (`tests/agents/characterization/_normalize.py:101-142`) — see §3.2.

**T-human. `backend/agents/capabilities/gates/human.py` — CONSUME `_gate_redo` (closes F1a).**
- Add a constant `_REDO = "_gate_redo"` (alongside `_REJECTED`/`_EDITED` at `:38-39`).
- In `evaluate_stream`'s delegate loop (`:88-106`), add an arm **before** the
  `else: yield event` fall-through:
  ```
  if etype == _REDO:
      redo_seen = True
      continue            # consume — never re-surface as a public gate event
  ```
- After the loop (`:108`), map the outcome so a stray redo **never PASSes**:
  ```
  outcome = GATE_BLOCK if rejected else (GATE_WAIT_HUMAN if redo_seen else GATE_PASS)
  ```
  (`GATE_WAIT_HUMAN` is already imported, `:30`.) The two guarantees the F1 safety test
  pins: (1) no `_gate_redo` dict is yielded (no wire leak via `_evaluate_gates:3752-3754`);
  (2) the terminal outcome is **NOT** `GATE_PASS` (the step does not silently advance).
  `GATE_WAIT_HUMAN` is the recommended non-PASS outcome ("still needs a human"); `GATE_BLOCK`
  is the conservative alternative — the choice is bounded by those two assertions.
- Write an **honest** audit row for the redo case (fixes F9): the existing
  `write_gate_event(..., outcome, ...)` at `:111-114` now records the real non-PASS
  outcome instead of a misleading `GATE_PASS`.
- **Apply the IDENTICAL arm to the check gate** `backend/agents/capabilities/gates/approval.py`
  (`ApprovalGate`). Confirmed: it shares the exact F1 defect — it also delegates to
  `run_human_gate → _run_review_gate` (`approval.py:6,21,148`), defines the same
  `_REJECTED`/`_EDITED` constants (`:51-52`), and a stray `_gate_redo` falls to
  `else: yield event` (`:181`) then `outcome = GATE_BLOCK if rejected else GATE_PASS`
  (`:183`). Add the same `_REDO` constant + consume-arm + non-PASS outcome + honest audit
  here. These two (`human.py`, `approval.py`) are the only gate files that reference
  `run_human_gate` (verified `grep -l run_human_gate agents/capabilities/gates/`).
- This task is what makes the **shared-primitive** change (B3) safe on the declared path
  even though v1 does not wire declared redo.

**B4. `backend/agents/execution_engine/engine.py` — inline consumer `while True:` loop + `_gate_redo` (engine seam #2; F2 + F3).**
- Convert the single-shot agent-run + inline gate into a **`while True:` loop** inside
  `_run_agent`. Sketch (the body is the EXISTING run+gate; only the loop framing and the
  redo branch are new):
  ```
  redo_directive = ""           # LOOP LOCAL
  redo_derived_from = None      # LOOP LOCAL
  while True:
      # ── consume-once (F3): publish directive to ectx ONLY for the compose call ──
      # derived_from never touches ectx — it is passed straight to the write below.
      ... agent_start ...
      ectx.redo_directive = redo_directive
      context_message = await self._compose_context_message(...)   # reads ectx.redo_directive (B6)
      ectx.redo_directive = ""           # cleared ADJACENTLY + UNCONDITIONALLY (F3)
      _iter_derived = redo_derived_from  # capture for this iteration's write
      redo_directive = ""                # reset locals so a non-redo exit cannot leak
      redo_derived_from = None
      ... astream → output ...
      if output:
          await self._dual_write_artifact(..., derived_from=_iter_derived)   # B5
      ... produces writes ... agent_complete ...
      if self._should_gate(spec, ectx):
          async for gate_event in self._run_review_gate(..., redoable=True):
              if gate_event.get("type") == "_gate_rejected":
                  ... cancel ...; return
              elif gate_event.get("type") == "_gate_edited":
                  ... apply edit (UNCHANGED, engine.py:3256-3279) ...
              elif gate_event.get("type") == "_gate_redo":
                  redo_directive = gate_event.get("instructions") or ""
                  _kind = self._artifact_kind_for(spec)
                  _cands = [r for r in ectx.artifacts.list_by_kind(_kind)
                            if r.producer_agent == spec.id]
                  redo_derived_from = max(_cands, key=lambda r: r.version).id if _cands else None
                  if results and results[-1].get("agent_id") == spec.id:
                      results.pop()
                  break          # leave the gate-consumer; the while-loop re-runs
              else:
                  yield gate_event
          else:
              return             # gate generator exhausted w/o redo → approve/edit → done
          continue               # only reached via the redo `break` → re-run (FLAT STACK)
      return                     # not gated → single run
  ```
  - **F2:** N redos = N loop iterations, NOT N stack frames. O(1) event propagation.
  - **F3:** `ectx.redo_directive` is dirty only across the two adjacent compose lines and
    is cleared unconditionally; `redo_derived_from` is a pure loop local passed straight to
    the write and reset every iteration — so an empty-output (`if output:` false) or
    exception (`engine.py:3283-3324`) path can carry **nothing** into the next agent (a
    separate `_run_agent` call with fresh locals + `ectx.redo_directive == ""`).
  - The redo branch keys on the event type — generic.

**B5. `backend/agents/execution_engine/engine.py` — thread `derived_from` on the main write.**
- At the main artifact write (`:3172-3179`), pass `derived_from=_iter_derived` (the loop
  local from B4). On the normal path `_iter_derived is None` → byte-identical. On a redo,
  the new version (N+1) records lineage to the rejected ref. **No separate clear is needed**
  — the local is reset each iteration (F3).

**B6. `backend/agents/execution_engine/engine.py` — instructions block in `_compose_context_message`.**
- After the consumed-outputs block (`:5598`), append iff set:
  ```
  redo_note = getattr(ectx, "redo_directive", "") or ""
  if redo_note:
      parts.append(f"\n=== ADDITIONAL INSTRUCTIONS (REVISE) ===\n{redo_note}\n=== END ADDITIONAL INSTRUCTIONS ===")
  ```
  Signature UNCHANGED (rides the additive `ectx` field — no test blast radius, §2.5).
  Dormant on goldens (`redo_directive == ""` → no block → byte-identical). The set/clear
  discipline lives in B4 (set adjacent to the call, cleared unconditionally right after).

**B7. `backend/agents/execution_engine/context.py` — additive scratch field.**
- Add to the `ExecutionContext` dataclass (`:40+`): `redo_directive: str = ""`. Same idiom
  as `build_task_number` / `current_step`. Default-empty → dormant on every non-redo run.
  *(Note: `redo_derived_from` is intentionally NOT an `ectx` field — it is a `_run_agent`
  loop local, per F3, so it cannot leak across agents.)*

**B8 (OPTIONAL, recommended). Redo audit row — in the INLINE consumer (B4), not `_run_review_gate`.**
- In the `_gate_redo` branch of B4, best-effort record a gate_events row:
  `record_gate_event(run_id, step=spec.id, gate="human", outcome="redo",
  detail={"has_instructions": bool(instructions)})` via the `ScopedStore`/`KernelServices`
  handle reachable from `ectx` (F9 — NOT from `_run_review_gate`, which lacks `ectx`).
  `outcome` is a free `String` (no enum); the row carries owner_id+workspace_id — no
  migration. Content-free detail. Dormant on goldens (they never redo).

**B9 (OPTIONAL, high-value — F7). Cancel-aware gate wait.**
- Thread `cancel_event` into `_run_review_gate` and replace `await event.wait()`
  (`engine.py:3918`) with a race:
  ```
  done, pending = await asyncio.wait(
      {asyncio.create_task(event.wait()), asyncio.create_task(cancel_event.wait())},
      return_when=asyncio.FIRST_COMPLETED,
  )
  for t in pending: t.cancel()
  if cancel_event.is_set():
      yield {"type": "_gate_rejected"}   # treat Stop-while-paused as terminal
      return
  ```
  Fixes the feature's amplified Stop-while-paused window AND the long-standing gap in one
  stroke. **OPTIONAL for v1** — not required by any locked decision; if deferred, document
  R3/F7 as a known limitation.

**B10 (F5). `_latest_typed_content` — select latest by `version`, not insertion order.**
- Replace the loop (`engine.py:4650-4654`) so the winner is the max-`version` matching ref,
  tie-broken by later insertion (preserving today's multi-kind behavior):
  ```
  best = None
  for ref in ectx.artifacts.tree(ectx.run_id):
      if ref.producer_agent == producer_agent and (best is None or ref.version >= best.version):
          best = ref
  return best.content if best else None
  ```
  - **Byte-identical on goldens:** within one process, write order == version order, and no
    golden producer emits a higher-version kind before a lower-version different kind, so
    "max version with later-insertion tie-break" == "last inserted" (the parity suite is the
    guard — test #7).
  - **Post-resume safe:** after `_hydrate_artifacts_from_store` re-adopts refs via
    `store.tree()` (`engine.py:4982-4999`) in any order, a redone step's approved version
    (higher `version`) always beats the rejected one.
  - *Fallback if parity ever flags this:* instead guarantee `ScopedStore.tree()` orders by
    `(kind, version)`/`created_at` on hydrate (the review's alternative). Prefer the local
    `_latest_typed_content` change.

### Frontend (all additive; outbound messages are untyped inline literals → no type-union edit)

> Correction from grounding: the panel is at `components/preview/ReviewGatePanel.tsx`
> and the send/receive logic is in `app/dashboard/page.tsx` via a `DashboardLayout`
> pass-through — NOT `hooks/useWorkflow.ts` and NOT `lib/api.ts`.

**F-fe1. `frontend/src/components/preview/ReviewGatePanel.tsx`**
- Add optional prop `onRedo?: (gateKey: string, instructions: string) => void` to
  `ReviewGatePanelProps` (`:20-27`).
- Add local `redoInstructions` state + a `handleRedo` next to `handleApprove` (`:171-173`).
- In the Actions footer (`:277-302`), add a Redo button + a conditional free-text
  `<textarea>` (reuse the edit-textarea pattern `:266-271`). **Render the Redo UI iff
  `onRedo && reviewGateData.redoable`** (the F1b fence) — so a declared-gate
  `review_gate_ready` (`redoable=false`) shows NO Redo button.

**F-fe2. `frontend/src/components/layout/DashboardLayout.tsx`**
- Add `onRedoReview?: (gateKey: string, instructions: string) => void` to the props
  (next to `:92-93`), destructure it (next to `:237-239`), and pass `onRedo={onRedoReview}`
  at the `ReviewGatePanel` render site (`:1433-1440`). Thread the `redoable` field from the
  `review_gate_ready` payload into the panel (so the fence can read it).

**F-fe3. `frontend/src/app/dashboard/page.tsx`**
- Capture `redoable` from the inbound `review_gate_ready` handler (`:713-732`) into
  `reviewGateData`.
- Add an `onRedoReview` callback in the `DashboardLayout` JSX (next to `:1290-1297`):
  ```
  onRedoReview={(gateKey, instructions) => {
    send(JSON.stringify({ type: "approve_review", gate_key: gateKey,
                          action: "redo", instructions }));
    setReviewGateData(null);   // clear panel; a fresh review_gate_ready re-opens it
  }}
  ```
  No change to the inbound handlers otherwise — the re-run re-emits the same
  `review_gate_ready` shape (now carrying `redoable`).

**F-fe4. Agent-panel idempotency (F8).**
- Confirm the agent-progress panel renders **one** card per `index` on a repeated
  `agent_start`/`agent_complete` (each redo re-emits the full lifecycle), and that a
  reconnect/history-replay after N redo attempts renders cleanly (FE dedups by `event_id`;
  each attempt is a distinct event). Add the FE tests (§7 #14). Document that token cost is
  **cumulative across redo attempts** (real spend, intended).

**F-fe5. `frontend/src/types/index.ts`** — add the optional `redoable?: boolean` field to
  the inbound `review_gate_ready` data shape (the only typed change; outbound messages stay
  untyped inline literals). `review_gate_ready` is already in `StreamMessage.type` (`:48`).

---

## 5. Invariant compliance (point by point)

- **SC-001 / INV-1 (kernel name-free).** Redo keys on `action == "redo"`
  (`_run_review_gate`), the event type `_gate_redo` + `_should_gate` (inline consumer),
  the `redoable` flag (inline call site — a structural path), and `ectx.redo_directive`
  (injector). The declared-path consume-arm (T-human) keys on the event type. No
  `if pipeline_type ==` / `spec.id ==` / workflow-name literal is introduced. **Decision
  #3 is met for all live (inline) human gates; declared coverage is the documented
  follow-up (§0).**
- **INV-3 (5 goldens byte/event-identical).** Goldens resolve gates via
  `live_harness.set_review_response(gate_key, approved=True)` (`live_harness.py:432,481`)
  with **no `action`** → defaults `"approve"` → the B3 redo branch is skipped → identical
  `review_gate_ready`/`review_gate_approved`/`_gate_edited`. `_compose_context_message`
  block is dormant (`redo_directive == ""`). The B5 write passes `derived_from=None`. The
  B10 latest-by-version selection is byte-identical (write order == version order in one
  process). The **one** new golden-path field is `redoable` on `review_gate_ready`, added to
  `_VOLATILE_STRIP_KEYS` (mirroring `deliverable_mimetype`/`deliverable_filename`,
  `_normalize.py:139-140`) → stripped from the multiset → goldens stay byte-identical.
  `_gate_redo` is internal (consumed on BOTH consumers — inline B4 + declared T-human —
  never forwarded). Goldens never hit the declared path.
- **INV-12 (no dual implementation).** Reuses the SAME `_run_review_gate` pause/resume,
  the SAME `set_review_response`/`get_review_event` channel, the SAME `approve_review`
  owner-gated handler, the SAME `_run_agent` (and thus `create_runner` dispatch), the SAME
  `ArtifactGraph` versioning. T-human removes the v1 "half-fork" (the shared primitive no
  longer mis-behaves on the declared consumer). No forked gate, no second dispatch path, no
  second HITL mechanism.
- **INV-13 (deepagents path).** The re-run is a plain re-iteration of the `_run_agent`
  loop, which builds the agent via `create_runner` (`engine.py:2645`) and streams via
  `astream_events` — no new agent loop.
- **Additive migrations only (Q3).** **NO migration.** `artifact_refs` already has
  `version` + `derived_from` + `parents` + `owner_id` + `workspace_id`
  (`0014_typed_artifacts_persistence.py:46-72`). `gate_events` already has
  `owner_id`+`workspace_id` and a free-`String` `outcome` (`0016`), so the optional redo
  audit row (B8) reuses it. The redo decision lives only in the in-memory `ArtifactStore`
  resume dict — never a DB column.
- **Ports & Adapters / import-linter.** No new kernel→app import. The `GateHandler` Protocol
  is untouched (T-human only adds a consume-arm + uses the already-valid `wait_human`/`block`
  outcome). New `ectx` field + store kwargs are kernel-importable. lint-imports stays
  **4 kept / 0 broken** (`/opt/homebrew/bin/lint-imports`).
- **IDOR / owner-scoping.** Redo flows through the existing `approve_review` branch whose
  `_review_gate_owned_by(gate_key, user.id)` check runs BEFORE `set_review_response`
  (`websocket.py:1196` → `:1204`); `test_approve_review_ownership.py:151-169` continues to
  pin "ownership verified before the write". The new artifact version is written through
  `_dual_write_artifact` → `ScopedStore.write_ref` (owner/workspace stamped); the optional
  audit row is `ScopedStore.record_gate_event` (owner/workspace stamped).
- **Durable resume (F4).** A mid-gate restart marks the run `failed`
  (`engine.py:4007-4025`) — pending redo is LOST. Accepted/parity for v1; documented (§9 R3).
- **Cooperative cancel (F7).** Re-run streaming cancel works (`engine.py:2766`); gate-open
  cancel is a pre-existing no-op (`engine.py:3918`) that redos amplify. Optional B9 closes it.

---

## 6. Persistence & events

- **Migration: NONE.** (See §5.)
- **artifact_refs:** each redo writes a NEW row, `version = N+1` for `(run_id, kind)`
  (`graph.py:157-159`), `derived_from` = the rejected ref's id (`graph.py:174`, threaded via
  B5). The rejected row is never updated/deleted (decision #4). `_latest_typed_content`
  (B10) serves the max-`version` row.
- **gate_events (optional, B8):** one additive row `gate="human", outcome="redo",
  detail={"has_instructions": bool}` (content-free), owner/workspace-scoped. T-human also
  writes an honest non-PASS outcome on a stray declared-path redo (F9).
- **run_events / WS:** the re-run re-emits the existing `agent_start` → `agent_input` →
  `agent_chunk*` → `agent_complete` → `review_gate_ready` (now with `redoable`) sequence via
  the generic passthrough (`websocket.py:1798,2040-2043`). No new WS event type (the internal
  `_gate_redo` is consumed). The resume decision (`action`/`instructions`) is transient
  in-memory only. **Token cost accrues cumulatively across redo attempts** (each
  `agent_complete` carries fresh token counts the WS accumulator adds) — intended (F8).

---

## 7. Test plan

**Backend (unit / `python3.11 -m pytest`, offline targeted suite per the memory note):**

1. `tests/unit/test_artifact_store.py` (extend `:113-120`): `set_review_response`
   round-trips `action="redo"` + `instructions`; plain approve still defaults
   `action="approve"`.
2. New engine test (model after `tests/agents/test_declared_gate_streaming.py`): a `redo`
   response causes `_run_review_gate` to yield `_gate_redo` and the inline loop to (a)
   re-emit a second `agent_start`+`review_gate_ready` for the SAME `gate_key` (with
   `redoable=true`), (b) NOT advance to the next agent, (c) write a second `ArtifactRef` of
   the same kind with `version==2` and `derived_from == ` the v1 id, (d) leave v1 present.
3. Instructions injection: with `instructions="add dark mode"`, the re-run's
   `_compose_context_message` contains the `=== ADDITIONAL INSTRUCTIONS (REVISE) ===` block;
   with empty instructions it does NOT, and `ectx.redo_directive` is `""` afterward.
4. Owner-scope: extend `tests/unit/test_approve_review_ownership.py` — a `redo` action is
   ALSO behind `_review_gate_owned_by` (same branch).
5. Unbounded: two consecutive redos then approve → three `ArtifactRef` versions (v1
   derived-from-none, v2 derived-from-v1, v3 derived-from-v2), final approve advances.
6. Reject-after-redo and edit-after-redo behave normally.
7. **(F1 safety) Declared-gate redo fence.** Drive a declared `gates:[human]` step (no
   `gate: Human_Gate`, `_should_gate==False`) and feed `action:"redo"`: assert
   `HumanGate.evaluate_stream` (a) yields NO `_gate_redo` dict (no wire leak), (b) returns a
   terminal outcome that is **NOT** `GATE_PASS` (step does not advance), (c) its
   `review_gate_ready` carried `redoable=false`. Repeat the same assertions for `ApprovalGate`
   (`approval.py` — confirmed to share the defect).
8. **(F2 loop) Many-redos stack flatness.** Drive ~150–200 redos then approve: completes with
   no `RecursionError`; assert the run's call-stack depth at the gate is constant across
   iterations (e.g. capture `len(inspect.stack())` at the gate on iteration 1 vs N — equal).
9. **(F3 consume-once) No lineage leak on error/empty.** Force (a) empty output and (b) an
   exception on a redo iteration, then run a DIFFERENT next agent: assert the next agent's
   main `ArtifactRef.derived_from is None` and its composed context has no REVISE block
   (`ectx.redo_directive == ""`).
10. **(F5 latest-by-version) Resume-after-redo.** Persist + rehydrate
    (`_hydrate_artifacts_from_store`) after a redo where the rejected v1 is re-adopted AFTER
    the approved v2 in `tree()` order; assert `_latest_typed_content` (and any deliverable
    resolver) returns the **approved** v2, never the rejected v1.
11. **(F6 edge, optional) retry × gate × redo.** A gated step with
    `retry.max_attempts>0`: redo → transient retry → approve; assert
    `_dispatch_step_with_retry` records the approved ref id and never reuses a rejected one
    (`engine.py:4910-4943`).

**Parity (INV-3) — the gate:**
12. Run the golden parity suite over the 5 goldens; confirm byte/event-identical (dormant).
    Assert `_VOLATILE_STRIP_KEYS` contains `redoable` (and nothing else golden-affecting
    changed).

**Frontend (vitest):**
13. `ReviewGatePanel`: renders the Redo button + textarea **only when `onRedo` AND
    `redoable`** are set; with `redoable=false` (declared gate) no Redo button; clicking Redo
    calls `onRedo(gateKey, instructions)`; empty textarea → `onRedo(gateKey, "")`.
14. `page.tsx`/`DashboardLayout`: `onRedoReview` sends
    `{type:"approve_review", gate_key, action:"redo", instructions}` and clears
    `reviewGateData`; a subsequent `review_gate_ready` re-opens the panel. **(F8)** repeated
    `agent_start`/`agent_complete` for one index renders ONE card; reconnect after N redos
    replays cleanly (not N stacked cards).

**Lint / gate:**
15. `lint-imports` (`/opt/homebrew/bin/lint-imports`) → 4 kept / 0 broken.
16. The banned-pattern / SC-001 grep gate (R15) stays green — no new workflow/agent literal
    in the engine (`grep` for `_gate_redo`/`redoable`/`redo_directive` shows only generic
    usage).

---

## 8. Task breakdown (ordered, atomic; waves where parallelizable)

**Wave 1 — backend (engine.py tasks sequential; store/context/human parallelizable).**
- **T1.** `context.py` B7: add `redo_directive` field. *Verify:* import + trivial instantiation.
- **T2.** `store.py` B1: additive `action`/`instructions` kwargs. *Verify:* test #1.
- **T3.** `engine.py` B3: `_run_review_gate` redo branch + `redoable` param emitted on
  `review_gate_ready`; add `redoable` to `_VOLATILE_STRIP_KEYS`. *Verify:* test #2 (yields
  `_gate_redo`, emits `redoable`); golden parity #12.
- **T-human.** `human.py` **AND** `approval.py` (both confirmed to route through
  `_run_review_gate`): consume `_gate_redo`, non-PASS outcome, honest audit (F1a/F9).
  *Verify:* test #7.
- **T4.** `engine.py` B4: convert inline run+gate to `while True:` loop (F2); `_gate_redo`
  branch sets loop locals + `results.pop()` + `continue`; consume-once unconditional (F3);
  pass `redoable=True` from the inline call site. *Verify:* tests #2,#5,#6,#8,#9.
- **T5.** `engine.py` B5+B6+B10: `derived_from=_iter_derived` on main write + REVISE block in
  `_compose_context_message` + **latest-by-version** in `_latest_typed_content` (F5).
  *Verify:* tests #2(c/d),#3,#10.
- **T6.** `websocket.py` B2: accept `action`/`instructions`, owner-check unchanged.
  *Verify:* test #4.
- **T7 (optional).** B8 redo audit row in the inline consumer (NOT `_run_review_gate`).
  *Verify:* gate_events row assertion.
- **T8 (optional, high-value, F7).** B9 cancel-aware gate wait (race `cancel_event`).
  *Verify:* Stop-while-paused wakes the gate → run cancels.

**Wave 2 — frontend (parallelizable; depends on the T3/T6 wire shape).**
- **T9.** `ReviewGatePanel.tsx` F-fe1 (Redo button + textarea, gated on `onRedo && redoable`).
  *Verify:* test #13.
- **T10.** `DashboardLayout.tsx` F-fe2 (pass-through + thread `redoable`). *Verify:* render test.
- **T11.** `page.tsx` F-fe3 (capture `redoable`; `onRedoReview` send). *Verify:* test #14.
- **T12.** `types/index.ts` F-fe5 (`redoable?: boolean` on inbound `review_gate_ready`).
- **T13.** F-fe4 (F8): agent-panel idempotency on repeated `agent_start`/`agent_complete` +
  reconnect-after-N-redos. *Verify:* test #14.

**Wave 3 — full verification.**
- **T14.** Targeted offline backend suite (parity #12 + safety #7,#8,#9,#10 + owner #4 +
  unbounded #5) ~35s; `lint-imports` #15 (4/0); SC-001 grep #16.
- **T15.** FE vitest #13,#14; `npm run e2e` mocked gate path if a scenario exists.

---

## 9. Risks / true blockers (real, found in code) + status

- **R1 — Unbounded redos (RESOLVED by the loop, F2).** v1 used recursion; v2 uses a
  `while True:` loop inside `_run_agent` (B4) — flat stack, O(1) per event, unbounded-safe by
  construction. **No longer a risk.**
- **R2 — Declared-only `gates:[human]` redo is the FOLLOW-UP (not v1).** The LIVE redo is the
  INLINE consumer (covers every live human gate; the declared `human` gate is deduped off by
  WR-02, `engine.py:3727`). A workflow that uses `gates:[human]` WITHOUT `gate: Human_Gate`
  runs the human gate as a PRE-step gate reviewing the PREVIOUS step's output
  (`human.py:84`); "redo" there means re-running the upstream producer — a dispatch-loop
  re-entry, a genuinely different mechanism. **v1 fences this safely** (T-human consume +
  `redoable=false` so no Redo button). The follow-up adds a real `GateOutcome "redo"` that
  the dispatch loop maps to "re-run the gated producer step" — flagged, NOT hacked in. **Not
  a blocker for v1.**
- **R3 — Durable resume of a paused gate LOSES the pause (F4, KNOWN LIMITATION).** The redo
  signal is in-memory (`asyncio.Event` + resume dict). A mid-gate process restart hits
  `restore_non_terminal_runs` branch (a), which marks the `waiting_for_user` run **`failed`**
  (`engine.py:4007-4025`) — it does NOT re-arm the event or re-emit `review_gate_ready`. So a
  mid-redo restart kills the run; any already-written redo `ArtifactRef` persists as a benign
  orphan (no corruption). This is **pre-existing parity with today's gates** (clarify +
  review), **accepted for v1**, and is **NOT "handled" by resume**. Optional B9 does not change
  this (cancel ≠ restart). **Documented limitation, not a blocker.**
- **R4 — `produces`-kind lineage.** B5 threads `derived_from` onto the MAIN handoff write
  (`engine.py:3172`); the per-`produces` writes (`engine.py:3190-3200`) version additively
  without an explicit `derived_from`. The main artifact is what the gate reviews and what
  `_latest_typed_content` serves, so decision #4 is satisfied. *Mitigation if full per-kind
  lineage is wanted:* compute the prior per kind in the same loop — minor, additive. **Not a
  blocker.**
- **R5 — State-machine cycle.** Redo adds `generating → waiting_for_user` cycles; safe —
  `transition` has no from-adjacency matrix and the 2-gate prototype already cycles
  (`state_machine.py:66-98`). Covered by test #5. **Not a blocker.**
- **R6 — Cumulative token cost across attempts (F8).** Each redo is real spend (every
  `agent_complete` adds fresh token counts). **Intended**; documented for the UI. **Not a
  blocker.**

**No kernel/architecture compromise is required.** Every change is additive and keyed on
generic gate/step signals; the 5 goldens stay dormant (the one new field, `redoable`, is
stripped by the parity normalizer); no migration is needed; the declared path is safely
fenced; unbounded redos are loop-bounded.

---

## 10. Per-invariant compliance matrix (post-revision)

| Dimension | Verdict | Note (evidence) |
|-----------|---------|-----------------|
| SC-001 / INV-1 (kernel name-free) | **PASS (v1-inline)** | Inline path name-free (`action=="redo"` + `_gate_redo` + `_should_gate` + `redoable` structural flag + `redo_directive`). Declared/user-composed gates **safely fenced** (T-human consume + `redoable=false`); full declared coverage is the documented follow-up (R2). Decision #3 met for all *live* gates. |
| INV-2 (per-run state, not singleton) | **PASS** | `redo_directive` is an additive `ExecutionContext` field; `redo_derived_from` is a `_run_agent` loop local — neither is process state. |
| INV-3 (5 goldens dormant) | **PASS** | `action` defaults `"approve"` (B3 skipped); `redo_directive==""`; `derived_from=None`; B10 byte-identical (write order == version order). The one new field `redoable` is added to `_VOLATILE_STRIP_KEYS` (precedent: `deliverable_mimetype/filename`). `_gate_redo` consumed on both consumers. |
| INV-12 (reuse, no fork) | **PASS** | Reuses gate/resume/dispatch/artifact machinery; **T-human removes the v1 half-fork** (shared `_run_review_gate` no longer mis-handles `_gate_redo` on the declared consumer). |
| Single seq/event_id emit boundary (Phase 5) | **PASS** | Redo re-emissions flow `_run_agent`→strategy→`_dispatch_step_with_retry`→dispatch loop→`execute()`'s single `itertools.count(1)` boundary; the loop re-run does NOT bypass it. |
| Durable resume / reconnect (Phase 12/16) | **KNOWN LIMITATION (accepted)** | Mid-redo restart marks the run `failed` (`engine.py:4007-4025`); pending redo lost (R3/F4). No corruption. Reconnect replays all redo attempts (FE dedups by `event_id`; idempotent panel — F8). |
| Content-hash reuse (RESUME-02) | **PASS (+edge)** | Rejected version can never be reused (`output_ref_id` of only the approved version recorded, `engine.py:4910-4943`); `input_hash` ignores `redo_directive`. Untested retry×gate×redo edge has a test (F6/#11). |
| Cooperative cancellation (Phase 16) | **PASS during run; pre-existing gap at gate** | Re-run streaming cancel works (`engine.py:2766`). Gate-open cancel is a pre-existing no-op (`engine.py:3918`) the feature amplifies — optional B9/F7 closes it. |
| Artifact versioning "latest" (Phase 5) | **PASS** | B10 selects by `max(version)` (`engine.py:4636-4654` rewritten) — rejected version can't win post-resume. Rejected kept (decision #4); `results.pop()` safe (matching `agent_id`, `engine.py:3204`). |
| Recursion vs loop | **PASS** | `while True:` loop (B4/F2) — flat stack for unbounded redos. |
| Re-running side effects / token cost | **PASS (+note)** | `before_write` re-fires (idempotent); post_steps/validators run once at the step boundary (`engine.py:1889-1891`), not per redo; tokens cumulative (real spend, documented — F8/R6). |
| Edit ↔ redo / gate state machine | **PASS** | No from-state adjacency matrix; `generating`⇄`waiting_for_user` cycles valid; one action per resolve. |
| Owner-scoping / IDOR | **PASS** | Redo rides the unchanged `_review_gate_owned_by`-before-write ordering (`websocket.py:1196`→`:1204`); new version via `ScopedStore.write_ref` (owner/workspace stamped). |
| Additive migrations / persistence | **PASS** | No migration: `artifact_refs.version`/`derived_from`; free-`String` `gate_events.outcome`. Additive store kwargs + `ectx` field backward-compatible. |
| INV-13 (deepagents only) | **PASS** | Re-run is a plain `_run_agent` loop re-iteration → `create_runner`/`astream_events`; no new loop. |
