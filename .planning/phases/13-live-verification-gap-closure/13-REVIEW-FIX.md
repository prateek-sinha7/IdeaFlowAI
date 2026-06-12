---
phase: 13-live-verification-gap-closure
fixed_at: 2026-06-12T00:00:00Z
review_path: .planning/phases/13-live-verification-gap-closure/13-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 7
already_resolved: 1
skipped: 0
status: all_fixed
---

# Phase 13: Code Review Fix Report

**Fixed at:** 2026-06-12
**Source review:** `.planning/phases/13-live-verification-gap-closure/13-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (1 Critical + 7 Warning; Info findings excluded — `fix_scope: critical_warning`)
- Fixed this run: 7 (WR-01 … WR-07, one atomic commit each)
- Already resolved before this run: 1 (CR-01)
- Skipped: 0

**Verification (offline, per project convention):** characterization + INV-3/SC-001 battery
50 passed / 7 skipped (all 5 golden snapshots byte/event-identical, banned-patterns +
migration-ledger green); touched suites 107 passed (gates 31, declared-gate streaming 3,
prompt hygiene 14, guardrails, pipeline-failure semantics 8, revision contract/intelligence 17,
handoff hardening, approve-review ownership 7/7); live-gated files still collect offline
(34 collected, 0 errors); `/opt/homebrew/bin/lint-imports` 4 contracts kept / 0 broken.

## Fixed Issues

### CR-01: `approve_review` has no ownership check — ALREADY RESOLVED (pre-run)

**Status:** already fixed before this run — commit `b7203212` (re-audited `ed10bc05`).
`_review_gate_owned_by` resolves the run from `gate_key` and requires
`WorkflowRun.user_id == authenticated principal` before `set_review_response`;
deny is indistinguishable from an unknown key. Regression
`tests/unit/test_approve_review_ownership.py` (7/7 — re-confirmed green in this run's
battery). No action taken; recorded for completeness per the RESOLVED banner in REVIEW.md.

### WR-01: F4 fabricated-XML sanitizer inert on the engine pipeline path

**Files modified:** `backend/app/agents/deep_agent_runner.py`,
`backend/agents/execution_engine/engine.py`,
`backend/tests/agents/test_text_only_prompt_hygiene.py`
**Commit:** `06d56d4a`
**Applied fix:** Added public `DeepAgentRunner.sanitize_output()` (identity for
tool-using agents and clean text); `_run_agent` now applies it — duck-typed, no
app-module import in the kernel — to the chunk-joined authoritative output right
after `output = "".join(output_chunks)`. Also added `_UNTERMINATED_TOOL_XML_RE`
so a span truncated at max_tokens (no closing tag, even cut mid-attribute) is
stripped to end-of-string. Regression tests: 3 unterminated-span unit tests plus
an engine-consumption test driving the public `execute()` with a scripted model
emitting XML chunks, asserting `agent_complete.output_length` and
`pipeline_complete.final_output` reflect the sanitized output (UI `agent_chunk`
stream deliberately unfiltered, as designed).

### WR-02: Declared gate opens with an EMPTY payload; default prototype runs double-prompt

**Files modified:** `backend/agents/execution_engine/engine.py`,
`backend/tests/agents/test_declared_gate_streaming.py`
**Commit:** `92fbefb8`
**Applied fix:** (1) `ectx.last_streamed` is refreshed per completed step in the
dispatch loop, so a declared pre-step `human` gate reviews the previous step's
output instead of `""` (the terminal block re-assigns the identical value —
deliverable resolution byte-identical). (2) Double-prompt dedupe: when the
inline `_should_gate` review gate will fire for an agent, the manifest-declared
`human` gate (same mechanism, same `gate_key`) is skipped for that step — the
inline, output-bearing gate is the single review.
**Decision note (product-adjacent — flag for human confirmation):** the review
offered two options (drop `gates:[human]` from the prototype manifest, or
suppress the *inline* gate). Both change default UX or break the F1 regression
test; the applied third variant (suppress the *declared* gate when the inline
fires) preserves the legacy known-good post-step/real-output UX exactly, keeps
the F1 streaming test green (`gate_agent_ids=[]` silences the inline path so the
declared path stays exercised), and keeps declared gates fully functional for
manifests whose agents carry no inline `gate:` frontmatter. Regression: new
default-run test (no `gate_agent_ids`) asserting exactly one
`review_gate_ready` per gated agent, each with a non-empty payload.

### WR-03: Rejecting a declared human/approval gate does not cancel the run

**Files modified:** `backend/agents/execution_engine/engine.py`,
`backend/tests/agents/test_declared_gate_streaming.py`
**Commit:** `9953f717`
**Applied fix:** `_evaluate_gates` maps a `block` outcome from an HITL gate
(`_HITL_GATES = {human, approval}`) to a distinct `cancel` sentinel and stops
evaluating; the dispatch loop transitions the state machine out of the stranded
`waiting_for_user` to `cancelled`, emits `pipeline_cancelled` (with a reason,
inline-path parity), persists the budget snapshot if fan-out was active, and
returns. Validation/security blocks keep step-skip semantics. Regression:
declared-gate rejection test asserting `pipeline_cancelled`, no
`pipeline_complete`, no downstream agents, terminal state `cancelled`.

### WR-04: User edits at a declared gate are silently discarded

**Files modified:** `backend/agents/capabilities/gates/human.py`,
`backend/agents/capabilities/gates/approval.py`,
`backend/agents/execution_engine/engine.py`, `backend/tests/agents/test_gates.py`
**Commit:** `6e50aff8`
**Applied fix:** `HumanGate` captures the `_gate_edited` payload and threads it
on `GateOutcome.detail` (the `gate_events` audit row stays content-free —
`{"edited": true}` only). `_evaluate_gates` now yields
`(event, outcome, detail)` 3-tuples; the dispatch loop applies the edit via the
new `_apply_declared_gate_edit` — a new typed ref version + `results[-1]`
update + review-payload refresh, mirroring the inline `_gate_edited` handler.
`ApprovalGate` discards edits EXPLICITLY with a logged warning (its payload is
a policy snapshot, not an editable artifact). An edit with no completed
upstream step is dropped with a warning, never silently.
**Note — requires human verification:** the choice that a pre-step declared-gate
edit applies to the PREVIOUS step's artifact (the content the user was shown)
is a semantic judgment; covered by unit/seam tests, worth confirming on the
live pass.

### WR-05: `agents_failed`/`degraded` conflates recoverable timeouts with hard failures

**Files modified:** `backend/agents/execution_engine/engine.py`,
`backend/tests/unit/test_pipeline_failure_semantics.py`
**Commit:** `51ee1b1f`
**Applied fix:** The degraded-completion payload is now keyed on
`_failed_agent_ids - {r["agent_id"] for r in results}` — agents that errored
but subsequently completed (the timeout degrade path) are completions, not
failures. The total-collapse `pipeline_failed` branch is untouched (`results`
is empty there). Regressions: timeout-shaped interleaving (error + complete
from the same agent → clean payload, no `status`/`agents_failed` keys) and a
mixed run (recovered timeout + hard failure → `agents_failed` lists only the
agent that never completed).

### WR-06: Revision `pipeline_type` matches no FE preview routing branch

**Files modified:** `backend/agents/execution_engine/engine.py`,
`backend/app/api/websocket.py`, `backend/tests/unit/test_run_revision_fe_contract.py`
**Commit:** `772b198a`
**Applied fix:** `_handle_revision` now emits the FE-routed alias via a generic
suffix transform — `target_artifact_type.removesuffix('_output') + "_revision"`
(`ppt_output → ppt_revision`, `od_ppt_output → od_ppt_revision`; no
workflow-name literal, SC-001) — at both the `pipeline_start` and
`pipeline_complete` emit sites. The WS handler stamps the same alias on the
revision `WorkflowRun.type` so the FE's revision-of-revision lookup
(`workflowType + "_revision"`) resolves. Non-`*_output` targets are
byte-unchanged; the `prototype_revision` characterization golden (execute()
path) is unaffected and re-verified green. FE contract test updated to assert
`od_ppt_revision`.
**Deferred scope (explicitly tracked, per the review's instruction):** the
revision *deliverable* is still the Phase-3 context/instruction stub ("In a
full implementation, this would run a DeepAgent revision loop" —
`engine.py:_handle_revision`). The user now gets the revision routed to the
preview panel, but its content is the instruction/context blob, not a revised
deck. Implementing the DeepAgent revision loop is a feature, not a review fix —
carry forward to the end-of-milestone live pass / a follow-up plan.

### WR-07: Gate evaluation continues past a block; mid-stream gate exception fail-opens

**Files modified:** `backend/agents/execution_engine/engine.py`,
`backend/tests/agents/test_gates.py`
**Commit:** `2cb861fe`
**Applied fix:** (1) Short-circuit: once a declared gate yields
`block`/`wait_human`, the remaining gates for the step are not evaluated —
`gates:[security, human]` with security blocking no longer opens an HITL pause
for a dead step. (2) Scoped exception swallow:
`_FAIL_CLOSED_GATES = {security, approval, human}` map a raised exception to a
`block` sentinel (with logged detail) instead of pass; validation-class gates
keep the fail-open degrade (`a gate failure must never abort the run`).
Regressions: short-circuit (HITL delegate never invoked after a security
block), raising security gate → block-not-pass, raising human gate →
block-not-cancel and no further gate evaluation.

## Skipped Issues

None — all in-scope findings were fixed (CR-01 was already resolved before this run).

## Out of scope (not actioned, per config)

IN-01 … IN-06 (Info tier) remain open as documented in 13-REVIEW.md
(`fix_scope: critical_warning`). Note IN-03 (FE ignores `status: "degraded"`)
partially overlaps WR-05 — WR-05 fixed the payload semantics; the FE/DB
presentation disagreement remains an Info carry-forward.

---

_Fixed: 2026-06-12_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
