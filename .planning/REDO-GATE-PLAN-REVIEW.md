# REDO-GATE-PLAN — Adversarial Senior Design Review

> Reviewer: senior architect (adversarial). Branch reviewed: `new-workflow-engine`.
> Method: every load-bearing claim re-verified against actual code (line numbers
> re-derived, not trusted from the plan); stress-tested against the register's
> invariants (SC-001, INV-1/2/3/12/13), the single seq emit boundary (Phase 5),
> gate/dispatch machinery (Phase 7/8), fan-out/cancel (Phase 11/16), wave/resume/
> content-hash reuse (Phase 12), run_revision (Phase 13/14), and the Phase-22
> user-composed-capability surface.
>
> **The plan's file:line citations are accurate to the line** (independently
> confirmed across `store.py`, `websocket.py`, `context.py`, `human.py`,
> `kernel_services.py`, `state_machine.py`, `gate_events.py`, `authz.py`,
> `graph.py`, and `engine.py`). The issues below are about *design*, not bad
> citations.

---

## Verdict

**NEEDS-REVISION.** The architecture is right (extend `approve_review`, reuse the
one `_run_review_gate` pause + resume channel + `_run_agent` + `ArtifactGraph`
versioning; additive `ectx` scratch; no migration). But three real defects must be
fixed before execution: **(BLOCKER)** the shared-primitive change leaks/mis-handles
`_gate_redo` on the *declared* human-gate path — reachable today via Phase-22
user-composed gates — silently passing the gate and contradicting locked decision
#3 ("all human gates"); **(HIGH)** unbounded redos via recursion is the wrong
structure for an explicitly-unbounded operation; **(HIGH)** the `redo_derived_from`
clear is not robust to the empty-output/error paths and leaks lineage into the next
agent. None require re-architecture — they are targeted fixes.

---

## Findings

| ID | Sev | Dimension | What's wrong (evidence) | Concrete fix |
|----|-----|-----------|--------------------------|--------------|
| **F1** | **BLOCKER** | INV-12 / SC-001 decision #3 / shared primitive | B3 makes the **shared** `_run_review_gate` emit `_gate_redo` (it is called by BOTH the inline path AND the declared `human` gate — `kernel_services.py:1091` → same `_run_review_gate`). Only the inline consumer (B4) handles it. The declared consumer `HumanGate.evaluate_stream` has arms only for `_gate_rejected`/`_gate_edited` (`human.py:90,94`); an unrecognized `_gate_redo` falls to `else: yield event` (`human.py:106`) → it is **forwarded to the client** as a WS event via `_evaluate_gates` (`engine.py:3752-3754`), then the loop ends and `outcome = GATE_PASS` (`human.py:108`) → **the gate PASSES and the pipeline advances**. The user clicked "Redo" and instead the step is silently approved and an internal signal leaks to the wire. **Reachable in production:** Phase 22 lets users add a `human` gate via the AdvancedExpander (`gate:human` is `user_allowed=True`); `engine._apply_selections` overlays it into `step.gates` → the *declared* path (register Phase 22 §3, §5). `_should_gate` is False for such an agent → WR-02 dedupe does NOT skip it (`engine.py:3727` needs `inline_gated`) → the declared gate runs. The FE can't tell inline from declared (same `review_gate_ready` shape) so it will show "Redo". Directly contradicts locked decision #3 ("Generic / all human gates"). | Either (a) **implement declared-path redo**: add a `_gate_redo` arm to `HumanGate.evaluate_stream` that returns a new `GateOutcome(outcome="redo", detail={instructions})`, and teach `_evaluate_gates`/the dispatch loop to re-run the gated step (this is the R2 "re-run the previous step" mechanism, now non-optional); OR (b) **fence it for v1**: stamp a generic `redoable: true` flag on `review_gate_ready` ONLY from the inline call site, have the FE offer "Redo" iff `redoable`, AND make `HumanGate.evaluate_stream` **consume** `_gate_redo` (map to `GATE_WAIT_HUMAN`/re-loop, never `yield` it, never PASS). Do not ship the shared-primitive change without one of these. |
| **F2** | **HIGH** | Recursion vs loop | B4 re-runs the gated agent by **recursively** re-invoking `_run_agent` inside the still-open `async for gate_event in self._run_review_gate(...)` loop. With locked decision #1 (**unbounded** redos), N redos hold N nested `_run_agent` + `_run_review_gate` frames simultaneously until the *final* approval unwinds them. Each live `agent_chunk` then propagates through N nested `async for _ev: yield _ev` levels (O(N) per event). A determined or scripted client doing ~150-200 redos adds ~600-900 frames on top of the already-deep call stack (`execute`→`_execute_impl`→dispatch loop→`_dispatch_step_with_retry`→strategy→`KernelServices.run_agent`→`_run_agent`) → approaches Python's recursion limit → `RecursionError` mid-gate (ugly crash, run stuck in `waiting_for_user`). Plan R1 dismisses this as "human can't blow the stack" — unsafe for an *explicitly unbounded* feature. | Refactor the inline run+gate into a `while True:` loop inside `_run_agent` (the plan's own documented alternative in R1). On `_gate_redo`: set the scratch, `continue` the loop; on approve/edit/reject: `break`/`return`. Flat stack, O(1) per event, no growth. This is the senior call: **loop, not recursion**, for an unbounded operation. (It also localizes F3's consume-once and removes the "yield while iterating the gate generator" subtlety.) |
| **F3** | **HIGH** | Artifact versioning / state hygiene | B5 sets `derived_from=getattr(ectx,"redo_derived_from",None)` on the main write (`engine.py:3172`) and clears it "right after the write" — but that write is inside `if output:` (`engine.py:3157`) within the `try`. On **empty output** or **any exception** (`engine.py:3285`/`3291`), the clear is skipped, so `ectx.redo_derived_from` stays set. The *next* agent's main write unconditionally reads `derived_from=getattr(ectx,"redo_derived_from",None)` → the next agent's artifact gets a **spurious `derived_from` pointing at the previous agent's rejected ref** = lineage corruption. | Consume-once at the boundary: capture `redo_derived_from` into a local at the top of the re-run and `ectx.redo_derived_from = None` **immediately/unconditionally** (or clear in a `finally`). Same discipline for `redo_directive` (its clear at the `_compose_context_message` site ~`engine.py:2554` is already unconditional — keep it that way; verify it's outside the `try`). The loop refactor (F2) makes this trivial (locals, not ectx round-trips). |
| **F4** | MEDIUM | Durable resume (R3) | Plan R3 says "restart-resume is handled by `restore_non_terminal_runs` (engine.py:3954)." Verified FALSE for a paused gate: `restore_non_terminal_runs` classifies a `waiting_for_user` run into branch (a) and marks it **`failed`** ("Run abandoned: backend restarted while waiting for user…", `engine.py:4007-4025`) — it does NOT re-arm the review event or re-emit `review_gate_ready`. So a mid-redo restart **loses the pause and kills the run**; any already-written redo version persists as an orphan artifact. This is a pre-existing gate limitation (clarify + review both), not introduced by redo, but the plan **mischaracterizes** it as handled. | State it accurately: pending redo/gate state is in-memory (`asyncio.Event`, R3) and **lost on restart → run goes `failed`**; this is acceptable/parity with today's gates and there is no data corruption (rejected + redo artifact versions persist). Do not claim resume "handles" it. |
| **F5** | MEDIUM | Artifact versioning "latest" semantics | `_latest_typed_content` selects the producer's output **by `tree()` insertion order, NOT the `version` field** (`engine.py:4636-4654`; confirmed). Within one process, write order = version order, so the approved redo (v2) supersedes the rejected (v1) — fine. But after persist + a **restart resume**, `_hydrate_artifacts_from_store` re-adopts every ref via `store.tree()` (`engine.py:4982-4999`); "latest" then depends on the DB returning the higher-version ref **last**. If `ScopedStore.tree()` doesn't guarantee `(kind, version)`/`created_at` ordering, a downstream consumer or the deliverable resolver could be served the **rejected** version. | Make `_latest_typed_content` (and any deliverable resolver that picks "latest") select by `max(version)` for the `(run_id, producer/kind)` rather than tree order, OR guarantee `ScopedStore.tree()` orders by version/created_at. Add a regression test that resumes after a redo and asserts the approved version wins. |
| **F6** | LOW | Content-hash reuse (RESUME-02) | Good news, verified: the rejected version can **never** be reused by `_find_reused_completion` — it keys on the `output_ref_id` recorded in a `step_completed`/`step_reused` event (`engine.py:4910-4943`), and only the *final approved* version's id is recorded by `_dispatch_step_with_retry` after the strategy (incl. all redos) completes (`engine.py:4822-4833`). Two caveats: (1) the redo recursion bypasses `_dispatch_step_with_retry` entirely (re-runs always — no false `step_reused`); (2) `input_hash` excludes the `redo_directive` (it hashes `user_message`+`current_task_block`, `engine.py:4850-4908`), so the directive never perturbs reuse keys. The untested zone is **retry × gate × redo** on one step — now possible since Phase 22 wires a per-step `retry:` lever onto user-composed (gatable) steps. | No code change required for correctness; **add a note + a test** for a gated step that also declares `retry.max_attempts>0` (redo then a transient retry then approve) to pin that the wrapper records the approved ref and never reuses a rejected one. |
| **F7** | MEDIUM | Cooperative cancel (Phase 16) | Split the claim. **During the redo re-run (model streaming):** cancel works — `_run_agent` checks `cancel_event` per chunk (`engine.py:2766` → raises `CancelledError`). PASS. **While the gate/redo panel is open:** `_run_review_gate` takes no `cancel_event` and `await event.wait()` (`engine.py:3918`) waits only on the review event; the Stop button sets `cancel_event` but never the review event, so a Stop while paused does NOT wake the gate (only a `WebSocketDisconnect` destructively cancels). Pre-existing, but **unbounded redos extend the panel-open window**, widening exposure. | Acknowledge accurately. Optionally have the gate wait observe cancel too (`await asyncio.wait({event.wait(), cancel_event.wait()}, FIRST_COMPLETED)` → treat cancel as `_gate_rejected`/terminal), which would also fix the long-standing Stop-while-paused gap — a worthwhile addition given the feature multiplies gate dwell time. |
| **F8** | MEDIUM | Re-running side effects / FE replay / tokens | The redo re-emits the full lifecycle (`agent_start` `engine.py:2538`, `agent_input`, `agent_chunk*`, `agent_complete` `engine.py:3220`, `review_gate_ready`), all persisted to `run_events`. The plan's FE changes (F1–F3) only clear/reopen `reviewGateData`; they don't address the agent-progress panel seeing a **repeat** `agent_start`/`agent_complete` for an already-shown index, nor the **reconnect replay** re-playing every redo attempt (FE dedups by `event_id`, so each attempt is distinct and replays). Token/cost accounting accrues **every** redo attempt cumulatively (each `agent_complete` carries fresh token counts the WS accumulator adds). `before_write` hooks re-fire per redo (idempotent; fine). post_steps/validators do NOT re-run per redo (they run once at the step boundary after the strategy — `engine.py:1889-1891`). | Confirm the FE agent panel is idempotent on a repeated `agent_start`/`agent_complete` for the same index, and that history-reopen renders cleanly after N redo attempts. Decide + document that cumulative token cost across redo attempts is intended (it is real spend). Add an FE test for "redo then reconnect → panel renders once, not N stacked cards." |
| **F9** | LOW | Audit row (B8) / IDOR | Confirmed: `record_gate_event` is **not reachable** inside `_run_review_gate` (no `ectx`/`scoped_store` in scope, 4-param signature `engine.py:3870`). The plan's B8 already hedges this (defer to B4). Note the F1 fallout: the declared path's `HumanGate` *does* write a `gate_event` (`human.py:111-114`) but with the **mis-handled `GATE_PASS`** outcome on a redo — a misleading audit row. Fix lands with F1. Owner/IDOR otherwise PASS — redo rides the existing `_review_gate_owned_by`-before-`set_review_response` ordering (`websocket.py:1196`→`:1204`). | Put the (optional) audit row in B4 (inline consumer) as the plan says; ensure the F1 fix also records an honest outcome for declared-path redos. |
| **F10** | LOW | Minor accuracy | `set_review_response` stores into `self._questionnaire_responses["review:"+gate_key]` (a *different* dict than `_resume_events`); the plan's prose says "stores under `review:{gate_key}`" (the key prefix is right, the dict name differs) — immaterial to the additive-kwargs change, which is sound. Also: double-clicking Redo has the same benign last-writer/clear race as double-clicking Approve today (B-channel `event.clear()` then `wait()`); the FE clearing `reviewGateData` on send mitigates it. | No change; note for accuracy. |

---

## Per-invariant compliance matrix

| Dimension | Verdict | Note (evidence) |
|-----------|---------|-----------------|
| SC-001 / INV-1 (kernel name-free) | **ISSUE** | Inline path is genuinely name-free (`action=="redo"` + `_gate_redo` + `_should_gate` + `redo_directive`; `_should_gate` `engine.py:3531-3548` is name-free). BUT decision #3 ("all human gates") is **not met** — declared/user-composed human gates aren't covered and actively misbehave (**F1**). |
| INV-2 (per-run state, not singleton) | **PASS** | `redo_directive`/`redo_derived_from` are additive `ExecutionContext` scratch fields (`context.py` is a plain mutable `@dataclass`, mirrors `build_task_number`/`current_step`). |
| INV-3 (5 goldens dormant) | **PASS** | Goldens never redo: `action` defaults `"approve"` (B3 branch skipped), `redo_directive==""` (no context block → context_message oracle byte-identical), `derived_from=None` (== today). No golden-path WS event field added; `_VOLATILE_STRIP_KEYS` untouched. `_gate_redo` is internal (consumed inline, never forwarded) — **except on the declared path (F1)**, which goldens never hit. |
| INV-12 (reuse, no fork) | **ISSUE** | Reuses the gate/resume/dispatch/artifact machinery (good), but B3's change to the *shared* `_run_review_gate` creates a second, **broken** behavior on the declared consumer (**F1**) — effectively a half-fork. Resolve F1 to make this a clean PASS. |
| Single seq/event_id emit boundary (Phase 5) | **PASS** | Redo re-emissions flow `_run_agent`→strategy→`_dispatch_step_with_retry`→dispatch loop→`_execute_impl`→`execute()`'s single `itertools.count(1)` boundary (`engine.py:769,796-799`); seq stays monotonic + contiguous; the re-run does NOT bypass the boundary. (Resumed runs use the parallel boundary at `engine.py:5299` — still single-per-instance.) |
| Durable resume / reconnect (Phase 12/16) | **ISSUE** | **F4**: a mid-redo restart marks the `waiting_for_user` run `failed` (`engine.py:4007-4025`), not resumed — plan R3 overstates "handled"; pending redo is lost (acceptable, must be documented). Section frame-contract holds (run_type unchanged → `_replay_section` correct); reconnect replays all redo attempts (FE dedup by `event_id`) — see F8. |
| Content-hash reuse (RESUME-02) | **PASS** (+edge) | Rejected version can never be reused (`output_ref_id` of only the approved version is recorded; `engine.py:4910-4943`). `input_hash` ignores `redo_directive`. Untested retry×gate×redo edge (**F6**). |
| Cooperative cancellation (Phase 16) | **ISSUE** | Re-run streaming cancel works (`engine.py:2766`); gate-open cancel is a **pre-existing no-op** the feature amplifies (**F7**). |
| Artifact versioning "latest" (Phase 5) | **ISSUE** | "Latest" is by `tree()` order, not `version` (`engine.py:4636-4654`); after persist+rehydrate the rejected version could win if `tree()` ordering isn't guaranteed (**F5**). Rejected version is kept (decision #4) and `results.pop()` is safe (the popped entry has matching `agent_id`, `engine.py:3204`). |
| Recursion vs loop | **ISSUE** | Recursion is wrong for unbounded redos (**F2**) — use a loop. |
| Re-running side effects / token cost | **PASS** (+note) | `before_write` re-fires (idempotent); post_steps/validators run once at the step boundary (not per redo); tokens accrue cumulatively across attempts (real spend, document it) — **F8**. |
| Edit ↔ redo / gate state machine | **PASS** | No from-state adjacency matrix (`state_machine.py:66-98`); `generating`⇄`waiting_for_user` cycles are already valid; one action per resolve, no inconsistent states. |
| Owner-scoping / IDOR | **PASS** | Redo rides the unchanged `_review_gate_owned_by`-before-write ordering (`websocket.py:1196`→`:1204`); new artifact version via `ScopedStore.write_ref` (owner/workspace stamped). |
| Additive migrations / persistence | **PASS** | No migration: `artifact_refs` has `version` (auto `graph.py:157-159`) + `derived_from`; `gate_events.outcome` is a free `String` (no enum). Additive store kwargs are backward-compatible (defaulted; existing callers unaffected). |
| INV-13 (deepagents only) | **PASS** | Re-run is a plain `_run_agent` re-invocation → `create_runner`/`astream_events`; no new loop. |

---

## Recommended improvements (concrete)

1. **Resolve F1 before coding (BLOCKER).** Modifying the shared `_run_review_gate` without teaching the declared consumer is the central flaw. Prefer the **discriminator fence** for v1: stamp a generic `redoable` flag on `review_gate_ready` *only from the inline call site* (e.g., pass a `redoable: bool` into `_run_review_gate`, or set it in the inline consumer's forward), have the FE render "Redo" iff `redoable`, and make `HumanGate.evaluate_stream` **consume** any stray `_gate_redo` (never `yield`, never `GATE_PASS`). This keeps the locked-decision-#3 framing honest ("redo on every gate that today routes through the inline path") while not shipping a broken declared-path redo. If you want true decision-#3 coverage now, implement the declared re-run (R2) — bigger, and it re-runs the *previous* producer step (declared `human` is PRE-step over `ctx.last_streamed`, `human.py:84`), a genuinely different mechanism that deserves its own plan.

2. **Loop, not recursion (F2).** Wrap the run+gate in `while True:` inside `_run_agent`. This bounds the stack, makes event propagation O(1), and naturally scopes `redo_directive`/`redo_derived_from` as loop locals (fixing F3 for free).

3. **Consume-once, unconditionally (F3).** Read the redo scratch into locals at the top of the re-run and null the `ectx` fields immediately, so an empty-output or errored re-run can never leak `derived_from`/directive into the next agent.

4. **Latest-by-version (F5).** Change "latest" selection to `max(version)` (or guarantee `tree()` ordering) so a rejected prior version can never be served post-resume; add a resume-after-redo regression.

5. **Cancel-aware gate wait (F7, optional but high-value).** Have the gate wait race `cancel_event` alongside the review event; this fixes the feature's amplified Stop-while-paused gap and the long-standing one in a single stroke.

6. **FE idempotency + cost (F8).** Add tests that (a) a repeated `agent_start`/`agent_complete` for one index renders one card, and (b) reconnect after N redos replays cleanly; document that token cost is cumulative across attempts.

---

## What's GOOD (keep)

- **Extending `approve_review` instead of a new WS message** — correctly reuses the one owner gate (`_review_gate_owned_by`) and the single `set_review_response`/`get_review_event` resume channel; a new message would have duplicated both (INV-12). Verified the handler reads `gate_key`/`approved`/`edited_content` and owner-checks before writing (`websocket.py:1180-1205`).
- **Additive, backward-compatible store kwargs** (`action="approve"`, `instructions=None`) — the sole reader (`_run_review_gate`) uses `.get()`, so extra keys are inert for every existing caller and the goldens.
- **Additive `ExecutionContext` scratch fields** — the established D-03 idiom; dormant on non-redo runs (INV-2/INV-3).
- **No migration** — correctly identified that `artifact_refs.version`/`derived_from` and the free-`String` `gate_events.outcome` already support redo (Q3 additive).
- **Routing the re-run through `_run_agent`** (not a side channel) so re-emitted events pass the single `execute()` seq boundary — this is the right instinct and is why the seq invariant holds.
- **Keeping the rejected output as a prior `ArtifactGraph` version with `derived_from` lineage** (decision #4) — `_dual_write_artifact` already accepts `derived_from` (`engine.py:4578-4634`); the prior is never deleted; `results.pop()` is safe.
- **Accurate grounding** — every cited seam matched the code to the line; the plan correctly anticipated the `record_gate_event`-not-in-scope problem (B8 hedge) and correctly scoped the declared-only gate as different (R2) — it just under-rated how reachable that path now is.

---

## Revised task breakdown

Restructure the plan's Wave 1 to land the safety properties *with* the feature (not after):

**Wave 1 — backend resume channel + engine seam (sequential; shared files)**
- **T1** `context.py` B7: add `redo_directive` + `redo_derived_from` (unchanged).
- **T2** `store.py` B1: additive `action`/`instructions` kwargs (unchanged).
- **T3** `engine.py` B3 — `_run_review_gate` redo branch, **plus a `redoable` parameter** (default False) so the inline caller can opt in and the FE can gate the button (F1 fence). Emit `redoable` on `review_gate_ready`.
- **T4** `engine.py` B4 — **convert the inline run+gate to a `while True:` loop** (F2), handle `_gate_redo` by setting scratch + `continue`; consume `redo_directive`/`redo_derived_from` as **loop locals** with unconditional reset (F3). *Verify:* unbounded-redo test (no stack growth), error-during-redo test (no lineage leak to the next agent).
- **T5** `human.py` (**NEW task, closes F1**): add a `_gate_redo` arm to `HumanGate.evaluate_stream` that consumes it (never `yield`, never `GATE_PASS`) — either map to a `redo` outcome the dispatch loop re-runs, or (v1) treat as wait/no-pass + rely on the FE `redoable` fence. *Verify:* a declared `human` gate receiving `action:"redo"` does NOT advance and does NOT leak `_gate_redo` to the wire.
- **T6** `engine.py` B5+B6: `derived_from` on the main write + `_compose_context_message` block; **latest-by-version** fix in `_latest_typed_content` (F5).
- **T7** `websocket.py` B2: accept `action`/`instructions` (owner-check unchanged).
- **T8** (optional) B8 audit row in the inline consumer (not `_run_review_gate`).

**Wave 2 — frontend** (depends on T3/T7 wire shape)
- F1/F2/F3 panel tasks, **plus**: only render "Redo" when `review_gate_ready.redoable` is true (F1 fence); idempotent agent panel on repeated `agent_start`/`agent_complete` (F8).

**Wave 3 — verification**
- Golden parity (dormant), `lint-imports` 4/0, SC-001 grep; **add**: declared-gate-redo safety test (F1), unbounded-redo stack test (F2), redo-then-error lineage test (F3), resume-after-redo latest-version test (F5), retry×gate×redo edge (F6), reconnect-after-N-redos FE test (F8).
