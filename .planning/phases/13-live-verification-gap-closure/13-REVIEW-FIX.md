---
phase: 13-live-verification-gap-closure
fixed_at: 2026-06-12T00:00:00Z
review_path: .planning/phases/13-live-verification-gap-closure/13-REVIEW.md
iteration: 2
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 13: Code Review Fix Report

**Fixed at:** 2026-06-12
**Source review:** `.planning/phases/13-live-verification-gap-closure/13-REVIEW.md`
**Iteration:** 2 (Info tier — IN-01 … IN-06; iteration 1's CR/WR record preserved below)

**Summary (iteration 2):**
- Findings in scope: 6 (IN-01 … IN-06; `fix_scope: all` — CR-01 + WR-01…07 were
  closed in iteration 1 and were NOT re-fixed)
- Fixed this run: 6 (one atomic commit each)
- Skipped: 0
- Re-verified before fixing: each IN finding was checked against current HEAD
  (post-WR fixes) — **all six still reproduced**; none were subsumed by the
  iteration-1 WR fixes (WR-05 fixed the degraded *payload* semantics but left
  IN-03's FE/DB disagreement; WR-03/WR-07 changed gate-halt routing but left
  IN-04's message text; WR-06 left IN-02's drainer break-lists untouched).

**Verification (offline, per project convention):** characterization + parity
battery 83 passed / 7 skipped (all 5 golden snapshots byte/event-identical,
banned-patterns + migration-ledger + manifest/routing/phase3 parity green);
touched suites 105 passed (artifact graph 9 incl. 2 new IN-01 tests, gates,
declared-gate streaming, prompt hygiene, pipeline-failure semantics 8,
revision intelligence 16 incl. 2 new IN-06 tests, FE revision contract,
handoff hardening, approve-review ownership); `/opt/homebrew/bin/lint-imports`
4 contracts kept / 0 broken; frontend `tsc --noEmit` exit 0.

## Fixed Issues (iteration 2)

### IN-01: `ARTIFACT_KINDS` is an unenforced vocabulary

**Files modified:** `backend/agents/artifacts/graph.py`,
`backend/tests/agents/test_artifact_graph.py`
**Commit:** `5be21a6b`
**Applied fix:** Advisory enforcement (the review's sanctioned middle path —
strict raising was provably unsafe: production writers persist
`clarifications`/`planning_context` outside the frozenset, tests write
`repo`/`parsed`/`design`, and the revision path writes FE-supplied dynamic
kinds). `ArtifactGraph.write_ref` now logs an observable WARNING for any kind
outside `ARTIFACT_KINDS` — a typo'd kind that would silently miss every typed
route / FR-014 chain link is no longer silent — with a documented `*_output`
carve-out for the FE revision-target kinds (generic suffix, no workflow-name
literal, SC-001). `clarifications` + `planning_context` (real persisted kinds)
added to the stale frozenset. Module stays stdlib-only (kernel purity).
Regressions: unknown kind warns AND writes; vocabulary + carve-out kinds are
silent.

### IN-02: WS drainer terminal break-lists omit `pipeline_failed`/`budget_aborted`

**Files modified:** `backend/app/api/websocket.py`
**Commit:** `a03d0fa2`
**Applied fix:** Both the main drainer and the reconnect drainer now break on
`pipeline_failed` (F3) and `budget_aborted` like the other terminals, instead
of idling until the bg task's post-DB-persist `None` sentinel.

### IN-03: `degraded` ignored by FE; DB marks degraded runs `failed` — three surfaces disagree

**Files modified:** `backend/app/api/websocket.py`,
`backend/app/models/workflow.py`, `frontend/src/types/index.ts`,
`frontend/src/hooks/useWorkflow.ts`, `frontend/src/app/dashboard/page.tsx`
**Commit:** `d356e197`
**Applied fix:** All three surfaces now agree on a WR-05 degraded completion:
- **FE hook:** `pipeline_complete` with `status:"degraded"` resolves the
  `agents_failed` set to per-agent **error** states (parity with the
  `pipeline_failed` sweep) instead of flipping the whole run to success;
  `PipelineRunState` exposes `degraded`/`degradedFailedAgents`.
- **FE dashboard:** appends a chat warning naming the failed agents (mirrors
  the existing `pipeline_failed` chat surface); the deliverable still routes
  to the preview panel (it exists — that part of the success path is correct).
- **DB:** persistence follows the authoritative terminal payload — degraded
  completion persists the distinct status `"degraded"` (free-string column, no
  migration — Q3) with an error note; a clean `pipeline_complete` (including
  recovered-timeout agents that errored then completed, per WR-05) persists
  `"completed"`; runs that ended WITHOUT `pipeline_complete`
  (`pipeline_failed`/`budget_aborted`/cancel) keep the legacy errored→failed
  mapping. Both the bg-task persist and the outer fallback persist are aligned.
**Decision note (product-adjacent — flag for human confirmation):** the review
offered "a warning chip" as an example surface; the applied surface is
per-agent error states + a chat warning message — both existing affordances,
no new component. Also note: as with the prior `"failed"` status, a
`"degraded"` run does not match the FE's `status === "completed"` revision
lookup (no regression — degraded runs were never revisable). Worth confirming
both choices on the live pass.

### IN-04: `pipeline_failed.error = "all agents failed"` inaccurate when steps were gate-halted

**Files modified:** `backend/agents/execution_engine/engine.py`,
`backend/tests/unit/test_pipeline_failure_semantics.py`
**Commit:** `4d29ce3a`
**Applied fix:** Neutral message `"no agent completed"` (the review's suggested
wording) — the branch fires on "no agent completed AND at least one errored",
and gate-skipped agents are neither completed nor failed. `agents_failed`
remains the precise list. Regression assertion updated; no other consumer
matches the literal string (FE renders `data.error` generically).

### IN-05: Deliverable ref's `producer_agent` is the last manifest agent, not the actual producer

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** `b525c67c`
**Applied fix:** The `kind="deliverable"` completion ref now attributes
`producer_agent` to the agent whose latest typed ref carries byte-identical
content to the resolved `final_output` (e.g. `prototype-build` via the
`single_file` resolver), scanning `ectx.artifacts.tree(run_id)` newest-first;
falls back to the previous behavior (last manifest agent) when no ref matches
(resolver-transformed output, e.g. the ppt carousel sanitize). Lineage
metadata only — content/kind/hash and the event stream are unchanged
(artifact writes emit no WS events, INV-3 snapshots re-verified green); no
agent-id literal (SC-001).
**Note — requires human verification:** the content-equality heuristic is a
semantic judgment (chosen over the review's `"run"` sentinel because it is
strictly more accurate where derivable and identical elsewhere); verified via
the revision suites + characterization battery, worth a glance on the live pass.

### IN-06: FR-014 summary fallback can resolve an `[Error: ...]` placeholder as the revision original

**Files modified:** `backend/agents/execution_engine/engine.py`,
`backend/tests/unit/test_revision_intelligence.py`
**Commit:** `6b6d79c6`
**Applied fix:** Chain link 3 (the legacy `summary` fallback) now filters refs
whose content starts with `[Error:` (the exact placeholder shape failed agents
typed-write — `f"[Error: {exc}]"`, engine.py `_err_output`). The latest REAL
summary resolves past a trailing placeholder; when every summary ref is a
placeholder the link stays empty and the FR-014 `ValueError` fires
(byte-unchanged guard). Links 1/2 untouched (link 2's deliverable ref is
already write-guarded by 13-05's `final_output and results`). Regressions:
degraded-legacy-parent resolves the real summary; all-placeholder parent
still raises FR-014.

## Skipped Issues (iteration 2)

None — all six Info findings were fixed.

---

# Iteration 1 record (2026-06-12, `fix_scope: critical_warning`) — preserved

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

## Fixed Issues (iteration 1)

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

## Skipped Issues (iteration 1)

None — all in-scope findings were fixed (CR-01 was already resolved before this run).

---

_Fixed: 2026-06-12_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
