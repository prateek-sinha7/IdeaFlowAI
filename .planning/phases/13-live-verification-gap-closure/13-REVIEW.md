---
phase: 13-live-verification-gap-closure
reviewed: 2026-06-12T00:00:00Z
depth: standard
files_reviewed: 33
files_reviewed_list:
  - backend/agents/artifacts/graph.py
  - backend/agents/capabilities/gates/approval.py
  - backend/agents/capabilities/gates/human.py
  - backend/agents/capabilities/prompt/policy.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/factory.py
  - backend/agents/prompts/app-api-design/AGENT.md
  - backend/agents/prompts/app-code-compliance/AGENT.md
  - backend/agents/prompts/app-devops/AGENT.md
  - backend/agents/prompts/app-feature-implementation/AGENT.md
  - backend/agents/prompts/app-infra-generator/AGENT.md
  - backend/agents/prompts/app-sdlc-governance/AGENT.md
  - backend/agents/prompts/app-system-design/AGENT.md
  - backend/agents/prompts/app-test-compliance/AGENT.md
  - backend/agents/prompts/app-test-implementation/AGENT.md
  - backend/agents/workflows/sample_fanout/workflow.yaml
  - backend/app/agents/deep_agent_runner.py
  - backend/app/agents/handoff/coder.py
  - backend/app/api/websocket.py
  - backend/tests/agents/test_declared_gate_streaming.py
  - backend/tests/agents/test_guardrails.py
  - backend/tests/agents/test_phase3_token_delta_live.py
  - backend/tests/agents/test_phase8_live.py
  - backend/tests/agents/test_sc001_fanout.py
  - backend/tests/agents/test_text_only_prompt_hygiene.py
  - backend/tests/unit/test_handoff_coder_hardening.py
  - backend/tests/unit/test_pipeline_failure_semantics.py
  - backend/tests/unit/test_revision_intelligence.py
  - backend/tests/unit/test_run_revision_fe_contract.py
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/hooks/useWorkflow.ts
  - frontend/src/types/index.ts
findings:
  critical: 1
  warning: 7
  info: 6
  total: 14
status: issues_found
---

# Phase 13: Code Review Report

**Reviewed:** 2026-06-12T00:00:00Z
**Depth:** standard
**Files Reviewed:** 33
**Status:** issues_found

## Summary

Reviewed the six Phase-13 gap-closure plans (F1 declared-gate streaming, F2 run_revision
FR-014 fallback + deliverable ref, F3 pipeline-failure semantics + ingress guard,
F4 text-only prompt hygiene + handoff hardening, F5 app_builder prompt re-templating,
F6/F7 manifest + live-test repairs) against the diff range `0fa8c6bc..HEAD`, tracing each
fix through its callers rather than taking the change in isolation.

The core mechanisms are sound: the streaming-gate protocol (`evaluate_stream` →
`_evaluate_gates` placeholder/sentinel tuples) correctly puts `review_gate_ready` on the
wire before `await event.wait()`; the F3 terminal branches are genuinely counter-driven
(SC-001 clean — no workflow-name literals found in any kernel change); the FR-014
fallback chain is owner-scoped (assert_owns precedes all chain reads); the ingress guard
exactly mirrors the factory's `TemplateMissingError` condition and is keyed on declared
injects only; the F5 prompt re-templating removes all migration-pipeline language; the
prompt-policy `tool_availability` slot is conditional so tool-having compositions stay
byte-identical.

However, the review found one authorization gap on the very handler the F1 fix makes
load-bearing, and several places where a fix is provably inert on the path it claims to
protect or where the newly-reachable surface exposes broken semantics: the F4 runner
sanitizer never runs on the engine pipeline path (the engine builds output from `chunk`
events and never reads `done`); the F1-unblocked declared gate shows an empty review
payload and double-prompts on default prototype runs; rejection at a declared gate does
not cancel the run; and the F2 revision still never reaches the FE preview because its
emitted `pipeline_type` matches no FE routing branch.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `approve_review` has no ownership check — any authenticated user can approve, reject, or inject edited content into another user's gated run

**File:** `backend/app/api/websocket.py:963-977`
**Issue:** The handler reads `gate_key`, `approved`, and `edited_content` from the client
message and calls `store.set_review_response(gate_key, ...)` with no verification that
the authenticated user owns the run named in `gate_key` (`{run_id}:{agent_id}`). Any
authenticated WebSocket client that learns or guesses a victim's `pipeline_run_id` can:
(a) approve a HITL review gate — including the `approval` gate, which is the N3 exec
sign-off control (`agents/capabilities/gates/approval.py`); (b) reject the gate and kill
the run; or (c) supply `edited_content`, which the engine writes into the victim run's
typed artifacts and results (`engine.py:2546-2569`) — cross-tenant content injection
into another user's deliverable. This is pre-existing code, but Phase 13's F1 fix makes
the declared-gate path (and the exec-approval gate riding it) actually usable, so this
handler is now the live security boundary for exec sign-off. Every other cross-run
surface in this codebase (revision reads, gate-event reads, clarifications) is
owner-scoped; this one is not.
**Fix:**
```python
if msg_type == "approve_review":
    ...
    run_id = gate_key.split(":", 1)[0]
    db = _get_db()
    try:
        wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if wr is None or wr.user_id != user.id:
            await websocket.send_json({
                "type": "error", "chunk": None, "section": None,
                "data": {"error": "Unknown gate_key", "code": "invalid_gate_key",
                         "recoverable": True},
            })
            continue
    finally:
        db.close()
    await store.set_review_response(gate_key, approved=approved,
                                    edited_content=edited_content)
```

## Warnings

### WR-01: F4 fabricated-XML sanitizer is inert on the engine pipeline path — the path where the live failures occurred

**File:** `backend/app/agents/deep_agent_runner.py:487-492` (and `backend/agents/execution_engine/engine.py:2229-2235, 2383`)
**Issue:** `_strip_fabricated_tool_xml` is applied only to the terminal
`{"type": "done"}` event. The engine never consumes `done`: `_run_agent` builds the
authoritative agent output exclusively from `chunk` events
(`output_chunks.append(event["chunk"])` at engine.py:2234, `output = "".join(output_chunks)`
at 2383), and that chunk-join is what gets persisted as the typed artifact, fed to
downstream agents as context, and resolved into the deliverable. So the F4 evidence
cases (epic-architect, custom, app_builder design agents — fabricated XML in prose
landing in artifacts/context) are NOT protected by this sanitizer; only the no-tools
preamble defends them. The only non-test consumer of `done` is the handoff coder
(`coder.py:239-240`), which already strips `<function_calls>` in `_extract_json` —
making the runner-level layer effectively redundant everywhere. The docstring's claim
that it "targets the AUTHORITATIVE output that feeds downstream agent context and
deliverables" is false for the pipeline path, and `test_text_only_prompt_hygiene.py`
masks this by testing the function directly instead of through the engine consumption
path. Additionally, a truncated span (output cut at max_tokens mid-`<function_calls>`,
a realistic failure shape) has no closing tag and is not stripped at all.
**Fix:** Apply the sanitization where the engine assembles the authoritative output for
tool-less agents — e.g. sanitize `output` after `output = "".join(output_chunks)` in
`_run_agent` when the step resolved to zero tools (the engine already has the spec/ctx
to derive `no_tools`), or have the runner sanitize its accumulated `full_output` AND
re-emit corrected chunks. Also handle the unterminated-span case (strip from an
unmatched `<function_calls>` to end-of-string). Add a regression test that drives
`_run_agent` with a scripted model emitting XML chunks and asserts the persisted
artifact/`agent_complete.output_length` reflect the sanitized output.

### WR-02: Declared human gate opens with an EMPTY review payload, and default prototype runs now double-prompt (declared pre-step gate + inline post-step gate on the same agents)

**File:** `backend/agents/capabilities/gates/human.py:79` (and `backend/agents/execution_engine/engine.py:1716`, `backend/agents/workflows/prototype/workflow.yaml:27,30`)
**Issue:** Two compounding problems on the surface F1 just made reachable:
(1) `HumanGate.evaluate_stream` sources the review payload from
`getattr(ctx, "last_streamed", "")` — but `ectx.last_streamed` is assigned exactly once,
at the terminal deliverable block (engine.py:1716), never during dispatch. Every
declared-gate `review_gate_ready` therefore carries `output: ""` — the user gets an
approval modal with nothing to review (the claimed "parity with the inline path, which
passes the agent's output" does not hold).
(2) The prototype manifest declares `gates: [human]` on prototype-specify/plan, whose
AGENT.md also declare `gate: Human_Gate` (the inline default set). On a real default run
(FE sends no `gate_agent_ids`), BOTH paths fire: the user is paused before the step
(declared gate, empty payload) and again after it (inline gate, real output) — four
pauses per prototype run, two of them empty, sharing the same `gate_key` per agent.
The F1 regression test deliberately passes `gate_agent_ids=[]` to silence the inline
path, so the combined default-run behavior is untested — and the UAT-requested
"WS-path handler-driving regression test" was not delivered (the test drives
`engine.execute()` directly).
**Fix:** Populate a meaningful payload for declared pre-step gates (e.g. the previous
step's output via `ectx` — update `last_streamed` per step, or read the latest typed
ref); decide single-gating for prototype (either drop `gates:[human]` from the manifest
steps that already carry `gate: Human_Gate`, or suppress the inline gate when the step's
declared gates contain `human`); add a default-run (no `gate_agent_ids` override) test.

### WR-03: Rejecting a declared human/approval gate does not cancel the run — the run continues and terminates as a completion, with the state machine stranded in `waiting_for_user`

**File:** `backend/agents/capabilities/gates/human.py:84-95` (and `backend/agents/execution_engine/engine.py:1533-1547, 3080-3089`)
**Issue:** On the inline path, `_gate_rejected` triggers `pipeline_cancelled` and a
terminal `cancelled` transition (engine.py:2535-2545). On the declared path, the gate
maps `_gate_rejected` to `GATE_BLOCK`, the dispatch loop merely sets `_halted` and
`continue`s to the NEXT agent (1544-1547), and the run keeps executing downstream
agents before ending in `pipeline_complete`. Worse, `_run_review_gate` only transitions
back to `generating` on approval (3080-3081 — the "we'll transition to cancelled below"
comment refers to the inline caller, which does not exist here), so after a declared-gate
rejection the state machine stays in `waiting_for_user` while agents run; the terminal
block's `transition(run_id, "completed")` then fires from `waiting_for_user`. A user who
clicks "Reject" on a Phase-13-surfaced declared gate sees the run keep going and report
success. Pre-existing Phase-8 semantics, but F1 makes the reject button reachable; the
new regression test covers approve only.
**Fix:** In the dispatch loop, treat a `block` outcome from a `human`/`approval` gate as
run-cancellation parity: transition to `cancelled`, emit `pipeline_cancelled`, and
`return` (mirroring engine.py:2535-2545). Alternatively have `_run_review_gate`
transition the state machine out of `waiting_for_user` on rejection and have the gate
surface a distinct `cancel` outcome the kernel can act on. Add a declared-gate rejection
test.

### WR-04: User edits at a declared gate are silently discarded

**File:** `backend/agents/capabilities/gates/human.py:88-90` (and `backend/agents/capabilities/gates/approval.py:159-160`)
**Issue:** Both gates consume the `_gate_edited` signal with `continue` and drop
`edited_content` on the floor. On the inline path an edit re-writes the typed artifact
and updates `results[-1]` (engine.py:2546-2569). On the declared path the FE offers the
same edit-and-approve affordance (the events are byte-identical), the engine confirms
`review_gate_approved` with `edited: true`, and the edit has no effect — silent loss of
user input. Newly user-reachable via F1.
**Fix:** Either thread the edited content back (yield a structured outcome detail the
kernel applies to the upstream artifact, as the inline path does), or — minimum viable —
have the declared path reject `edited_content` explicitly so the FE cannot offer an edit
that does nothing.

### WR-05: F3 `agents_failed`/`status:"degraded"` conflates recoverable timeout completions with hard failures — an agent can appear in BOTH `agents_completed` and `agents_failed`

**File:** `backend/agents/execution_engine/engine.py:1568-1573, 1788-1790` (vs `2357-2381, 2502-2516`)
**Issue:** The dispatch loop adds every `agent_error` event's `agent_id` to
`_failed_agent_ids`. But the agent-timeout path (engine.py:2374-2381) emits a
`recoverable: true` `agent_error` and then CONTINUES — the agent uses its partial/fallback
output, appends to `results`, and emits `agent_complete`. Such a run now terminates
`pipeline_complete` with `status: "degraded"` and `agents_failed` listing an agent that
is simultaneously counted in `agents_completed` — a contradictory payload for any
consumer reconciling the two fields (and a behavior change for timeout runs, which
previously presented as clean completions). The same applies to any future recoverable
`agent_error` emitter. The F3 tests only stub the hard-fail shape (error then return),
so the timeout interleaving is untested.
**Fix:** Key failure tracking on agents that did NOT subsequently complete — e.g. compute
`agents_failed = _failed_agent_ids - {r["agent_id"] for r in results}` at the terminal
block (keeps the total-collapse branch unchanged since `results` is empty there), or only
record `agent_error` events with `recoverable: false`. Add a timeout-shaped test
(agent_error followed by agent_complete from the same agent).

### WR-06: F2 closes FR-014 but the revision still never reaches the user — emitted `pipeline_type` (`ppt_output_revision`/`od_ppt_output_revision`) matches no FE preview routing branch, and the revision "deliverable" is the instruction/context blob

**File:** `frontend/src/app/dashboard/page.tsx:360-366` (and `backend/agents/execution_engine/engine.py:3619, 3671-3682`)
**Issue:** `_handle_revision` emits `pipeline_type: f"{target_artifact_type}_revision"`,
i.e. `"ppt_output_revision"` / `"od_ppt_output_revision"` for the FE-exact targets. The
dashboard's `pipeline_complete` preview routing matches only
`ppt|ppt_revision|od_ppt|od_ppt_revision` (and the prototype/user-stories equivalents) —
so the now-successful revision's `final_output` is routed nowhere and the preview panel
never updates. Compounding it, the revision result content is still the Phase-3 stub
(`revision_context` — planning-context + original + instruction blob, engine.py:3649,
3679; "In a full implementation, this would run a DeepAgent revision loop"), not a
revised deck. The UAT truth ("drives a revision") is met at the FR-014 layer, but the
user-facing flow F2 was diagnosed from (PPT revision from the FE) still produces no
visible revised artifact. Pre-13-05 this was unreachable (every revision raised); the
fix makes it reachable and exposes it.
**Fix:** Either normalize the emitted revision `pipeline_type` to the FE-known aliases
(map `ppt_output`→`ppt_revision`, `od_ppt_output`→`od_ppt_revision` at the emit site or
WS ingress), or extend the FE routing branches to include the `*_output_revision` forms.
Track the stub-deliverable issue explicitly (the revision agent loop) if it is deferred
scope — the live verification will otherwise re-flag F2.

### WR-07: Gate evaluation continues past a blocking outcome, and a mid-stream gate exception fail-opens HITL/security gates to PASS

**File:** `backend/agents/execution_engine/engine.py:2970-3006`
**Issue:** Two related weaknesses in `_evaluate_gates` (modified by F1):
(1) After a gate yields `block`/`wait_human`, the loop `continue`s to the NEXT declared
gate. For a step declaring e.g. `gates: [security, human]` where `security` blocks, the
`human` gate still opens a full HITL pause (`review_gate_ready` + indefinite
`event.wait()`) for a step that will be skipped regardless — the user is asked to approve
a step that cannot run.
(2) The `except Exception ... treating as pass` swallow now also wraps the streaming
branch: if the HITL delegate raises after `review_gate_ready` (e.g. a
`StateMachineError` from a stale state — reachable per WR-03's stranded
`waiting_for_user`), the gate is treated as PASS and the step executes WITHOUT the
required human/exec approval. Fail-open is defensible for validation gates; for
`security`/`approval`/`human` it inverts the control's purpose.
**Fix:** Short-circuit remaining gates once an outcome in `("block","wait_human")` is
seen (yield the sentinel and `return`/`break`). Scope the exception swallow: for gates in
a fail-closed set (`security`, `approval`, `human`), map an exception to `block` (with a
logged `gate_blocked` detail) instead of pass.

## Info

### IN-01: `ARTIFACT_KINDS` is an unenforced vocabulary — writes accept any kind string

**File:** `backend/agents/artifacts/graph.py:38-54, 102-149` (and `backend/agents/execution_engine/engine.py:3639-3653`)
**Issue:** Nothing validates `kind` against the frozenset — `write_ref` (graph and
ScopedStore) stores arbitrary strings, and `_handle_revision` writes
`kind=target_artifact_type` (`"ppt_output"`, outside the vocabulary) today. The F2 chain
depends on exact kind strings; a typo'd kind would silently miss every chain link.
**Fix:** Validate `kind in ARTIFACT_KINDS` in `ArtifactGraph.write_ref` (with an explicit
carve-out or vocabulary addition for the revision target kinds), or document the set as
advisory.

### IN-02: WS drainer terminal break-lists omit `pipeline_failed` (and `budget_aborted`)

**File:** `backend/app/api/websocket.py:781, 1662-1666`
**Issue:** Both the main drainer and the reconnect drainer break early on
`pipeline_complete`/`pipeline_cancelled`/`error` but not on the new `pipeline_failed`
terminal, so they idle until the bg task's `None` sentinel (after DB persistence). The
behavior is correct but inconsistent and adds latency to the client's terminal handling.
**Fix:** Add `"pipeline_failed"` (and `"budget_aborted"`) to both terminal tuples.

### IN-03: `status: "degraded"` is ignored by the FE, and the DB marks every degraded run `failed` — three surfaces disagree

**File:** `frontend/src/hooks/useWorkflow.ts:312-346` (and `backend/app/api/websocket.py:1534`)
**Issue:** The FE's `pipeline_complete` handler renders a degraded run as a full success
(all agents flipped to "done", deliverable routed to preview), while the WS persistence
sets `wr.status = "failed"` for any run with an `agent_error` — so the chat shows
success, the payload says `degraded`, and the run history says failed. The UAT missing
item asked for FE handling of the degraded field; only `pipeline_failed` got handling.
**Fix:** Surface `status === "degraded"` + `agents_failed` in the FE (e.g. a warning chip
on the run), and persist a distinct DB status (`degraded` or `completed` + error note)
instead of `failed` for partially-completed runs.

### IN-04: `pipeline_failed.error = "all agents failed"` can be inaccurate when steps were gate-halted rather than errored

**File:** `backend/agents/execution_engine/engine.py:1648-1668`
**Issue:** The branch fires on `not results and _failed_agent_ids`. If agent 1 errors and
agents 2-3 are skipped by a pre-step gate block/`wait_human`, the event reports
"all agents failed" with `agents_total: 3` but `agents_failed` listing only one — the
message overstates the failure set.
**Fix:** Use a neutral message (e.g. "no agent completed") or include
`agents_failed`/`agents_total` semantics in the text.

### IN-05: Deliverable ref's `producer_agent` is the last manifest agent, not the actual producer

**File:** `backend/agents/execution_engine/engine.py:1741-1752`
**Issue:** `producer_agent=ordered_agents[-1].id` attributes the `kind="deliverable"` ref
to the final step (e.g. `prototype-validate`) even when the deliverable was produced by
an earlier step's file write (e.g. `prototype-build` via the `single_file` resolver).
Lineage metadata only, but it will mislead any future lineage consumer.
**Fix:** Derive the producer from the resolver (e.g. the producer of the latest ref of
the deliverable's kind) or use a sentinel like `"run"` consistently.

### IN-06: FR-014 link 3 (`summary` fallback) can resolve an `[Error: ...]` placeholder as the revision original on legacy degraded parents

**File:** `backend/agents/execution_engine/engine.py:3536-3538` (with `2594-2609`)
**Issue:** A failed agent typed-writes `f"[Error: {exc}]"` under its mapped kind — for
unmapped agents that is `summary`. On a pre-13-05 parent whose FINAL agent errored, the
latest summary ref is the error placeholder, so the chain "resolves" garbage instead of
raising FR-014. New runs are protected by the `final_output and results` guard on the
deliverable ref, but the legacy link is not.
**Fix:** Skip refs whose content starts with `[Error:` in the summary fallback (or filter
by a future explicit error marker) before accepting link 3.

---

_Reviewed: 2026-06-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
