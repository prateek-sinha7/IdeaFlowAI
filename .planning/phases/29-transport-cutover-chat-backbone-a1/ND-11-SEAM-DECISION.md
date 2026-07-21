# ND-11 — Consume-once injection-seam unification + thread-id policy (Decision Record)

- **Status:** RESOLVED (Phase-29 first design task, per POR §3 Wave 2 / RESOLVED-DECISIONS.md ND-11)
- **Phase / Plan:** 29-transport-cutover-chat-backbone-a1 / 29-08 (CHAT-03, D-06)
- **Date:** 2026-07-08
- **Decides:** whether the new `steering_notes` seam **subsumes** or **coexists** with the two
  shipped consume-once injection seams; the **thread-id policy** for steering turns; and the
  reconciliation of the Redo-fork vs KAN-101-BASE-thread checkpoint divergence.
- **Author note:** This record is written **BEFORE** any `engine.py`/`context.py` edit in 29-08
  (INV-3 discipline — decide the third seam's shape against the shipped evidence first, then
  implement to the decision).

---

## 1. Context — the seam family today

The engine composes every per-agent prompt through **one** generic injector,
`ExecutionEngine._compose_context_message` (`engine.py` ~6094). It is workflow-agnostic
(INV-1/SC-001): it keys on generic `ectx` scratch fields, never on `pipeline_type` / `spec.id`.
Two **consume-once** injection seams already ride this injector as additive `ectx` scratch
fields, each with a set-adjacent-to-compose / clear-unconditionally lifecycle (the F3
"consume-once" idiom):

| Seam | Field(s) | Marker block | Set site | Clear site | Thread-id shape |
|------|----------|--------------|----------|------------|-----------------|
| **Redo** (P23 / REDO-GATE) | `ectx.redo_directive: str` | `=== ADDITIONAL INSTRUCTIONS (REVISE) ===` | `_run_agent` redo loop, just before the compose call (`engine.py` ~2750) | UNCONDITIONALLY right after compose (`engine.py` ~2755) | **forks** a fresh checkpoint thread `…:redo{N}` (`engine.py` ~2871) — `redo_attempt` increments per redo |
| **KAN-101 spec-revision** | `ectx.spec_revision_context: str` + `ectx.spec_revision_pending_output` | `=== SPEC KIT ANALYSIS REPORT (REVISION CONTEXT) ===` | `_run_spec_revision_sub_pipeline` before the re-run (`engine.py` ~4348) | UNCONDITIONALLY in `finally` on exit (`engine.py` ~4412) | **reuses BASE threads** — the sub-pipeline re-runs specify→plan→analyze on their normal `…:{spec.id}` threads (no `:redo{N}` suffix) |

Both seams are **dormant** on the 5 INV-3 characterization goldens (fields default-empty ⇒ no
block ⇒ byte/event-identical). The marker family the chat launch surface strips already lists
`=== USER GUIDANCE ===` as the **new** fourth member alongside `=== CONTEXT FROM PREVIOUS
PIPELINE ===` · `=== EXISTING PROTOTYPE HTML ===` · `=== REVISION REQUEST ===`
(POR §6, RESOLVED-DECISIONS "existing contracts to preserve").

---

## 2. Decision 1 — COEXIST (do NOT unify / subsume)

**`steering_notes` is added as a generic THIRD consume-once seam that shares the same
`=== … ===` composition idiom, while the two shipped seams are left byte-stable.**

### Rationale (against the evidence)

1. **INV-3 is the binding constraint.** Unifying the family would mean rewriting the Redo and
   KAN-101 set/clear sites to funnel through a single queue. Those seams are proven
   byte/event-identical on the 5 goldens today; any refactor of their live wiring risks a
   golden-visible drift for **zero** functional gain (the goldens never exercise steering). The
   POR/LOCK-B posture for this transport-cutover phase is **additive, no deletion, no ratchets**
   — subsuming shipped seams is a deletion-class change out of scope here.
2. **The three seams are semantically distinct, not redundant.**
   - `redo_directive` = a **one-shot** re-run directive tied to a gate rejection; it *rolls back
     and re-runs the same agent* on a **fresh** checkpoint thread.
   - `spec_revision_context` = a **sub-pipeline** re-run (specify→plan→analyze) that loops back
     to the *same* gate, reusing BASE threads.
   - `steering_notes` = **next-dispatch** guidance injected into the *next* agent that runs; it
     **does not roll back** a turn and does **not** re-run a completed agent.
   A single queue would have to re-encode all three lifecycles — more coupling, not less.
   INV-5 (thin compiler, control flow in the strategy/seam) favors three small, independently
   dormant scratch fields over one overloaded carrier.
3. **Name-freedom (SC-001/INV-1) is preserved either way**, so unification buys no
   kernel-cleanliness win. Each seam already keys on generic `ectx` state.

### What COEXIST means concretely (the 29-08 implementation contract)

- Add `ectx.steering_notes` — a **consume-once queue** (a `list` of `{"text": str,
  "sticky": bool}` entries) to `context.py`, documented as the third member of the same
  additive-scratch F3 family as `redo_directive` / `spec_revision_context`.
- Render pending notes in `_compose_context_message` as a single `=== USER GUIDANCE ===`
  block (joining the marker family the chat launch surface strips, POR §6), **read+clear
  during composition** (see Decision 3), keyed on the generic queue only — no workflow/agent
  literal.
- The two shipped seams are **untouched**.

---

## 3. Decision 2 — thread-id policy for steering turns: **NO fork; inject into the NEXT dispatch on the current thread**

The Redo/KAN-101 divergence the POR flags:

- **Redo forks** `…:redo{N}` because a redo **rolls back a rejected turn** — reusing the base
  checkpoint thread would make LangGraph *resume* the already-completed rejected graph state
  instead of re-running clean. The fork is correct there.
- **KAN-101 reuses BASE threads** because the sub-pipeline re-runs *whole agents* (specify →
  plan → analyze) that each get their normal `…:{spec.id}` thread. The POR/sibling comment flags
  this as an **unaudited checkpoint-replay risk over unlimited cycles**: a many-cycle
  `update_specs` loop re-enters the same BASE thread repeatedly, so LangGraph could resume
  accumulated graph state rather than start clean. **Disposition (this record):** the risk is
  **acknowledged and OUT OF SCOPE for 29-08** — 29-08 does not touch the KAN-101 sub-pipeline
  wiring (LOCK-B: byte-stable). It is logged here as a **standing audit item** for the mechanical
  router work (29-09) / the live pass (Phase 34) to bound cycle count or suffix the sub-pipeline
  thread if replay is observed. 29-08 neither widens nor fixes it.

**Steering policy (the new decision):** a steering note **does NOT fork a checkpoint thread and
does NOT roll back a turn.** It is injected into the **NEXT agent dispatch on that agent's
normal `…:{spec.id}` (or `…:{spec.id}:{task}`) thread**, exactly as any other composed-context
block. Justification:

- Steering is **next-dispatch guidance**, not a re-run of a completed agent (mid-generation
  injection is impossible — an agent invocation runs to completion; D-03). The next agent has
  **no prior checkpoint state to collide with** on its own fresh thread, so there is nothing to
  fork away from — the Redo fork rationale simply does not apply.
- Because steering injects into a *not-yet-run* dispatch, it carries **none** of the KAN-101
  replay risk either (no re-entry of an already-run BASE thread).

Net: **steering = base-thread, next-dispatch, no fork** — the simplest of the three, and it
sidesteps both the Redo-fork and the KAN-101-replay hazards by construction.

---

## 4. Decision 3 — consume-once lifecycle: **read+clear during composition; sticky vs one-shot**

Unlike Redo (set/clear *around* the compose call in `_run_agent`), steering notes are **enqueued
externally** by the mechanical router (29-09), asynchronously to any single dispatch. So the
consume-once **clear happens INSIDE `_compose_context_message`** (the key-link contract): at the
next dispatch the injector reads the pending queue, renders the block, then clears it.

**Sticky vs one-shot (D-06):**

- A **one-shot directive** (`sticky: False`) is rendered once and **dropped** after that single
  dispatch (consume-once).
- **Sticky context** (`sticky: True`, e.g. an uploaded context/file note) **persists** and is
  re-rendered on **every** subsequent dispatch (it is retained across the clear).

Concretely, the clear rewrites the queue to keep only the sticky entries:
`ectx.steering_notes = [n for n in steering_notes if n.get("sticky")]`.

**INV-3 dormancy:** `steering_notes` defaults to `[]`. On every golden run it is empty ⇒ no
`=== USER GUIDANCE ===` block is emitted **and no mutation occurs** ⇒ composition is
byte/event-identical to today. The block is emitted **only** when notes are pending (chat/steering
is dormant on golden runs).

---

## 5. ND-9 tie-in — steering-state across resume (server-derived, no new column in 29-08)

ND-9 (steering-state across `resume_run`) is the sibling of P22's deferred WR-02. **Decision for
this record:** steering state is **server-derived from `run_events`** (per 29-02's chat-message
persistence), **not** re-hydrated onto `ectx.steering_notes` at resume time in 29-08.

- `ectx.steering_notes` is **transient per-run scratch** (the same class as `redo_directive` /
  `current_task_block`): a live queue for the in-process dispatch loop, not a durable field.
- On a backend-restart `resume_run`, the authoritative record of what the user steered is the
  persisted `run_events` chat turns (29-02); the mechanical router (29-09) re-derives any
  still-pending steering from that durable substrate and re-enqueues onto the rebuilt `ectx`.
- **No new DB table or column is added in 29-08** (LOCK-B: zero new tables; additive-only). The
  resume re-hydration wiring lands with the router/persistence plans (29-02 / 29-09); 29-08 only
  lays the transient carrier + composition seam. On a resume with an empty re-hydrated queue the
  seam is dormant (INV-3 parity), so 29-08 is resume-safe by construction.

---

## 6. Consequences / invariants preserved

- **LOCK-B (additive transport):** 29-08 touches only `context.py` + `engine.py` +
  `test_steering_seam.py` + this record. The two shipped seams, `/ws/chat`, `websocket.py`,
  `websocket_handoff.py`, and `useWebSocket.ts` are **untouched**; no deletion, no ratchet, no
  new DB table.
- **INV-3:** the 5 characterization goldens stay byte/event-identical (steering dormant on
  golden runs; no golden fixture edited; no `SNAPSHOT_UPDATE`).
- **SC-001/INV-1:** the seam keys on the generic `ectx.steering_notes` queue only — no
  `if pipeline_type ==` / `spec.id ==` / workflow-name branch. The banned-pattern gate
  (`_INV1_PATTERN` over `agents/execution_engine/`) stays green.
- **INV-3/INV-12 (no dual implementation):** `steering_notes` is a *distinct* third seam, not a
  parallel re-implementation of Redo — it shares the one injector and the F3 consume-once idiom.

---

## 7. Evidence anchors

- POR / `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`: D-03 (interaction model / next-dispatch
  steering), D-06 (steering seam = generalized Redo; sticky vs one-shot; three-seam family),
  ND-9, ND-11, §4 Wave 2 exit ("a steering note demonstrably lands in the next agent's composed
  context (offline fault-injection)"), §6 marker family.
- `.planning/phases/28-chat-contracts-guards-a0/contracts/RESOLVED-DECISIONS.md`: ND-9
  (design-in-Phase-29), ND-11 (Phase-29 first design task), "injected-context marker family …
  (new) `=== USER GUIDANCE ===`".
- `backend/agents/execution_engine/engine.py`: `_compose_context_message` (~6094); the Redo
  block + `redo_directive` set/clear (~2750/2755, ~6235); the `:redo{N}` thread fork (~2871);
  the KAN-101 `_run_spec_revision_sub_pipeline` set/clear (~4348/4412) + its BASE-thread re-run
  (~4372); the `spec_revision_context` block (~6250).
- `backend/agents/execution_engine/context.py`: the `redo_directive` field + its consume-once
  docstring (~237-249) — the precedent the `steering_notes` carrier mirrors.
