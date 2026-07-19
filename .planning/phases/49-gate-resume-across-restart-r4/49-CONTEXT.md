# Phase 49: Gate Resume Across Restart [R4] - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Source:** POR Ingest Express Path (`.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` §5.5/§6-R4/§8 Q4 — DECIDED: re-enter-at-gate on the existing seams; LangGraph interrupt REJECTED)

<domain>
## Phase Boundary

Clarify AND review gates survive a backend restart (RESUME-17). Today `restore_non_terminal_runs` branch (a) marks every `waiting_for_user` run **failed** (the KAN-88 flip) because nothing could wait on the in-memory `asyncio.Event` after a restart. This phase supplies the waiter: branch (a) becomes **re-arm** for compiled-manifest runs with durable state — the run re-enters its parked step AT the gate phase, the gate re-arms on the existing in-memory HITL machinery, and every gate action works identically post-restart. This is a RESTORATION done properly: `waiting_for_user` was originally re-armed (WR-05 era, Phase 5/12) before KAN-88; the pre-existing RED test `test_restart_resume::test_waiting_for_user_run_is_rearmed_not_driven` encodes the target behavior and MUST FLIP GREEN this phase (it asserts: status stays `waiting_for_user`, the agent is NOT re-driven).

OUT of scope (hard fences): any change to gate SEMANTICS (the five actions behave exactly as today once armed); FE work of ANY kind (D-14g already re-emits `review_gate_ready` on SSE attach; BUG-013's parked-runs-not-auto-streamed is the INTENDED UX — gate surfaces when the user opens the run); the REST resume-from-failed endpoint (50); LangGraph `interrupt()` activation (REJECTED, Q4); fixing the 3 pre-existing `redo_gate_safety` reds (harness drift, held at 4/3 by delta); new tables/migrations; new WS event types.

</domain>

<decisions>
## Implementation Decisions

### The re-arm classification (LOCKED)
- Restart branch (a) flips fail→re-arm ONLY for runs that satisfy the branch-(b)-style gate: compilable `pipeline_type` AND ≥1 durable row (the `_is_resumable_in_flight` discipline). The WR-05 stateless/legacy path keeps the fail behavior BYTE-UNCHANGED (goldens + legacy tests untouched).
- Durable gate-pendency derives from the EXISTING seams — NO parallel pending-arm store (INV-12): an open REVIEW gate = a durable `review_gate_ready` event with no subsequent resolution event (the `_GATE_RESOLUTION_TYPES` vocabulary, run_stream.py — reconcile with `derive_open_gate`/KAN-94 in chat_router.py; factor ONE shared derivation if they'd otherwise duplicate). An open CLARIFY gate = durable `questionnaire_ready` with no subsequent `questionnaire_complete`/answers-resolution.
- `_gate_is_pending`'s private-dict peek (`store._resume_events`, the IN-02 debt) gains a PUBLIC accessor on the store as part of this work.

### Review-gate re-entry AT the gate phase (LOCKED — the crux)
- **The completeness interaction (load-bearing):** a gated step whose agent ALREADY produced output classifies "complete" by the produced-ref disjunct — a naive resume would skip past the unresolved gate. The resume classification must treat "open gate at step k" as the resume point: re-enter step k IN GATE MODE (do NOT re-run the agent; do NOT skip the step). This extends `_first_incomplete_step`/`resume_run`'s classification generically (keyed on the durable open-gate derivation — no name literals).
- Gate-mode re-entry reconstructs what the gate consumer needs WITHOUT re-invoking the model: the gated output from the persisted artifact (max-version of the step's kind — the `_latest_typed_content` discipline; `ectx.last_streamed` re-seeded from it, the WR-02 requirement that the gate reviews real output), then enters `_run_agent`'s EXISTING run+gate loop at its gate wait (re-emit `review_gate_ready` through the engine's normal emit path with a fresh seq — additive re-emit is already the D-14g-compatible shape; re-arm the `asyncio.Event` via the store's existing HITL half).
- ALL FIVE actions must work identically post-restart: approve (proceeds downstream), reject, edit (KAN-98 retained-edit + derived_from per Phase 48), redo (fresh `:redo{N}` checkpoint threads — **redo-attempt numbering must CONTINUE past pre-restart redos**: derive the prior attempt count from durable evidence (the P23 redo `gate_events` audit rows and/or artifact version count) so a post-restart redo never reuses a pre-restart `:redo{N}` thread id — the P23 checkpointer-replay bug class), and update_specs (the Phase-27 sub-pipeline fires normally from the re-entered loop).
- The re-armed run rides the SAME auto-resume infrastructure Phase 46 built: queues registered BEFORE any emit, live-ectx + milestone-sink callbacks threaded (46-05), workspace recovered (Pitfall 2), selections re-applied (0023).

### Clarify twin (LOCKED)
- A run parked at the clarify questionnaire re-arms symmetrically: questions replayed from the durable `questionnaire_ready` event payload; the questionnaire wait re-enters `clarify_engine`'s existing wait (store HITL half); answers ride the UNCHANGED `POST /{id}/answers`; on submit the run proceeds into the normal dispatch (planner→agents) exactly as a never-restarted run. Multi-round clarify (`clarify.rounds`) semantics unchanged.
- Status stays `waiting_for_user` throughout the re-arm (the KAN-88 test's assertion); it transitions exactly as a live run would on resolution.

### Guardrails (LOCKED — POR §7 + standing)
- INV-1/SC-001: every branch keys on generic durable event types / store state — zero workflow/agent-name literals (banned-pattern gate green).
- INV-2 · INV-3 (goldens 10/10 `SNAPSHOT_UPDATE` unset — ALL new machinery dormant on scripted runs; NO new WS event types; the re-emitted `review_gate_ready`/`questionnaire_ready` are EXISTING types through the existing emit boundary with engine-counter seq — 0024/DEF-43-03-1) · INV-12 (ONE pendency derivation shared with derive_open_gate; reuse `_run_agent`'s loop / the store HITL half / resume_run — no parallel gate machinery, no second wait implementation) · INV-5 · INV-13.
- The Phase 45/46/47/48 shipped tests are the regression floor (all green); `redo_gate_safety` held at pre-existing 4/3; lint-imports 4/0; enumerate-pin 1.
- No migration. No FE changes. `POST /{id}/gate` and `POST /{id}/answers` byte-unchanged.

### Execution constraints (LOCKED — standing)
- feat/ui-2 only · NO trailers · NEVER push · NEVER `git stash` · python3.11 no venv · ABSOLUTE cd backend/ (stray backend/backend exists) · targeted pytest only · NO live Bedrock in executors · sequential.

### Claude's Discretion
- Whether gate-mode re-entry is a mode flag into the existing `resume_run`/`_execute_impl` flow or a sibling entry that converges into `_run_agent`'s loop — whichever reuses MORE existing code (INV-12 bias), with the dispatch-loop pin staying 1.
- The exact shared home for the pendency derivation (factor from `derive_open_gate` vs a store-level accessor both call).
- How the prior-redo-attempt count is derived (gate_events outcome rows vs artifact version count) — pick the more robust durable signal.
- Plan decomposition (likely 2-3 plans: pendency derivation + classification & re-arm skeleton · review-gate re-entry with all five actions · clarify twin + KAN-88 flip + hardening).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` — POR §5.5 (the full design incl. KAN-88 history + seams), §6-R4, §7. READ FULLY.
- `.planning/ROADMAP.md` — "### Phase 49" block (5 success criteria) + v3.0 header.
- `.planning/REQUIREMENTS.md` — RESUME-17.
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 12 (restore/resume tier + WR-05 history), Phase 13 (F1 gate streaming; WR-02 last_streamed; WR-03 HITL block semantics), Phase 23 (the redo loop: `:redo{N}` threads, `redo_attempt`, gate_events audit rows, F4 "pending redo lost" — the limitation THIS phase removes), Phase 27 (update_specs), Phase 29 (KAN-94 derive_open_gate; D-14g), Phase 44 (BUG-015/016 `_GATE_RESOLUTION_TYPES`/`_STREAM_TERMINAL_TYPES`; answers/gate REST endpoints), Phases 45-48 v3.0 entries.
- Phase 45-48 folders — SUMMARYs/VERIFICATIONs (the shipped resume tier this phase completes).
- Code: `backend/agents/execution_engine/engine.py` (restore_non_terminal_runs branches; resume_run; _first_incomplete_step; _run_agent's run+gate `while True:` loop with the `_gate_redo`/`_gate_update_specs`/`_gate_edited` consumers; `_run_review_gate`; the WR-02 `ectx.last_streamed` handling), `backend/agents/execution_engine/clarify_engine.py` (the questionnaire wait), `backend/agents/artifact_store/store.py` (the HITL asyncio.Event half: get_review_event/set_review_response/get_resume_event/questionnaire responses; `_resume_events` — the IN-02 accessor target), `backend/app/api/chat_router.py` (`derive_open_gate`), `backend/app/api/run_stream.py` (`_dangling_review_gate`, `_GATE_RESOLUTION_TYPES`, `_STREAM_TERMINAL_TYPES`), `backend/app/api/run_commands.py` (gate/answers endpoints — byte-unchanged consumers), `backend/app/main.py` (restore-scan wiring from 46-05).
- Tests: `backend/tests/agents/test_restart_resume.py` (esp. the KAN-88 RED at `test_waiting_for_user_run_is_rearmed_not_driven` — THE anchor to flip), `test_redo_gate_safety.py` (held 4/3), `test_declared_gate_streaming.py`, `test_approve_review_ownership.py`, the 5 characterization files, SSE suites (D-14g adjacency — must stay at baseline).

</canonical_refs>

<specifics>
## Specific Ideas

- KAN-88's rationale (why re-arm was flipped to fail): an event nobody can set = a run hung forever. The fix is not "don't fail" — it is "recreate the waiter". Branch (a)'s re-arm must GUARANTEE a live waiter exists before the status is left `waiting_for_user` (arm-then-classify ordering; if arming fails, fall back to the current fail behavior — fail-safe).
- The D-14g attach re-emit means the FE story is already done: re-armed run + user opens it → SSE attach → `_dangling_review_gate` re-emits `review_gate_ready` → the inline gate UI renders. Verify the re-armed state satisfies `_dangling_review_gate`'s conditions (it derives from durable events — it should by construction).
- P23 F4 recorded "a mid-gate restart LOSES the pending redo; any already-written redo ArtifactRef persists as a benign orphan" — after this phase that orphan-version evidence is exactly what makes redo-attempt numbering derivable.
- The gate_key format is `{run_id}:{agent_id}` (established); ownership checks on resolution are unchanged (`_review_gate_owned_by`).

</specifics>

<deferred>
## Deferred Ideas

- The optional cancel-aware gate wait (P23 T8/F7 — racing cancel_event against the gate event) — a known-valuable follow-up, NOT this phase (would widen scope; the parked-run Stop path is unchanged).
- Declared-path (non-inline) gate redo — the P23 v1 fence stands.
- Live-Bedrock restart-mid-gate proof — milestone-end pass.

</deferred>

---

*Phase: 49-gate-resume-across-restart-r4*
*Context gathered: 2026-07-19 via POR Ingest Express Path (Q4 DECIDED: re-entry route)*
