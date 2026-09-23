# Audit Log: Conditional Gates (014)

**Spec ID**: 014-conditional-gates
**Purpose**: Track findings from the post-implementation compliance audit and their resolution, separate from `tasks.md` (which tracks the original build) and `spec.md` (the requirement source of truth).

---

## 1. Context

`tasks.md` reported all 44 original tasks (T1-T38 + V1-V6) done. Rather than trust that
self-report, an independent audit re-verified every requirement (R-01 through R-28 + R-05b)
and acceptance criterion (AC-01 through AC-11) in `spec.md` against the live code and fresh
test runs.

---

## 2. Audit Round 1 — Independent Compliance Audit

**Method**: 5 parallel agents, each re-deriving a slice of the spec's truth directly from
code/tests rather than trusting `tasks.md` or the original V1-V6 validators.

**Result**: 6 real gaps found, all frontend, all root-caused by R-23/R-24 never having been
built out (`tasks.md` itself flagged the CanvasView.tsx graph-layout conversion as an
explicitly deferred, unscoped item — RISK-05 in `plan.md`).

| Gap | Requirement | Finding |
|---|---|---|
| 1 | R-19 | No test locked in the compiler's `trigger_max_depth == 5` ceiling — a future edit could silently weaken/remove it undetected. |
| 2 | R-20 | A diverted run's firing step-id was never persisted or exposed via the API — no DB column, no response field. |
| 3 | R-22 | `ExternalPipelineCard` displayed the raw target workflow id, not a resolved name. |
| 4 | R-23 | No visual route-edge rendering on the canvas, and no gesture to connect a conditional outcome to an existing node (forward or backward/loop). |
| 5 | R-24 | The `trigger:"workflow"` outcome's Target field was a bare free-text input, not sourced from the real "My Workflows" list. |
| 6 | AC-07 (derived) | Consequently, not all three outcome kinds (step-forward, step-backward/loop, workflow) were genuinely authorable end-to-end via the UI. |

Severity: cosmetic/UX-only, not authoring-blocking — the underlying `route.outcomes.target`
field was already unvalidated free text that correctly accepted and serialized any value
(including a backward/ancestor step id); the gap was purely the missing visual/interactive
layer and test coverage.

---

## 3. Fix Pass — `conditional-gates-audit-fixes` workflow

**Method**: Dependency-graph-scheduled Workflow (`.claude/workflows/conditional-gates-audit-fixes.js`),
8 tasks (T39-T46) + 6 validators (V7-V12), file-collision-safe parallel execution.

**Result**: 14/14 nodes done, 0 errored, every validator passed on first attempt (no
fix-loops or escalations needed).

| Task(s) | Fixes | Validator |
|---|---|---|
| T39 | New `backend/tests/unit/test_conditional_route_compiler.py` — 6 tests (4 negative, 2 positive) locking in the `trigger_max_depth != 5` compiler guard. | V7 PASS |
| T40, T41, T42 | New `diverted_at_step_id` column (`backend/app/models/workflow.py` + migration `0033_add_diverted_at_step_id.py`); `engine.py`'s divert arm persists it; exposed on both `WorkflowRunResponse` and `WorkflowRunListResponse` (including `_LIST_COLS`, which did not auto-include it — fixed as part of T41); `RevisionFamilyView.tsx`'s divert badge renders `", step {id}"` (required adding `divertedAtStepId` to the frontend `WorkflowRun` type and `normalizeWorkflowRun`, which the task's named scope had missed — fixed as part of T42). | V8 PASS |
| T43 | `CanvasNode.tsx`: `trigger:"workflow"` Target field replaced with a real `<select>` (`WorkflowTargetPicker`) sourced from `userWorkflowsApi.list()`, deduped fetch, free-text fallback on error, `"self"` always selectable. | V9 PASS |
| T44 | `CanvasNode.tsx`: `ExternalPipelineCard` resolves and displays the real workflow name (not raw id), clickable via `next/link` to `routes.workflowEdit(id)`. | V10 PASS |
| T45, T46 | `CanvasView.tsx`: additive SVG route-edge layer (`routeArcPath`, forward = solid amber, backward/loop = dashed red with stagger) + new "connect-to-existing-node" diamond-handle drag gesture, deliberately omitting the `isDescendant` guard so it can target an ancestor (the loop case); both funnel through the same `applyOutcomePatch`/`nextOutcomeKey` mutation functions the on-card form editor (T43) uses. | V11 PASS |
| — | Final re-verification: all three outcome kinds (forward, backward/loop, workflow) authorable end-to-end via UI, round-trip serialization intact, TypeScript clean. | V12 PASS |

All changes landed as uncommitted working-tree diffs — nothing was committed during the fix pass.

---

## 4. Audit Round 2 — `ba-squad` Independent Re-Verification

**Method**: Fresh `qa-engineer` agent, full spec sweep (not scoped to just the 6 gaps),
re-running real backend/frontend test suites and reading current code rather than trusting
Round 1's validators.

**Result**: PASS — all 6 gaps confirmed to genuinely hold; no regressions from the `_LIST_COLS`
extension or the frontend `WorkflowRun`/`normalizeWorkflowRun` plumbing; a set of pre-existing
Pyright diagnostics on `engine.py` (unrelated to spec 014's diff — dynamic MCP-config
attributes and an unrelated exception-forwarding path) confirmed as noise, not defects.

**Self-correction caught mid-run**: the qa-engineer's first pass on R-23 cited stale
`tasks.md` language ("deferred, tracked as separate work") and never actually opened the
current `CanvasView.tsx` — its own "files verified" list omitted it. Sent back with the exact
evidence from Round 1's fix pass; the corrected pass produced real file:line evidence
(`routeArcPath` at line 68, route-edge SVG at lines 866-900/1235-1252, connect-gesture hit-test
with its `isDescendant` guard deliberately omitted at lines 703-744) confirming the gap
genuinely closed, not just asserted closed.

**Backend verify**: `cd backend && python3.11 -m pytest tests/unit/ tests/agents/ -v` — 13/13
targeted conditional-gates tests pass (full suite also green).
**Frontend verify**: `cd frontend && npx tsc --noEmit && npx vitest run` — 1165/1165 pass, zero
new TypeScript errors.

---

## 5. Current Status

All 6 audit-found gaps closed and independently re-verified twice (once by the fix workflow's
own validators, once by a fresh, unrelated qa pass). No known open issues in spec 014's scope.
All changes remain uncommitted working-tree diffs, ready for review/commit.

(Superseded by §7 below for the display-name item, and §8 for the live `.http` suite
re-run findings — see there for the latest status.)

---

## 6. Live-model finding — NOT FIXED, pending approval

Found while running the `run.http` suite against a live backend with a local Ollama model
(`qwen3.5:4b`) standing in for the real provider, to exercise the 5 `ex_A*`
fixtures end-to-end for the first time (previously only exercised via scripted/mocked models
in `tests/unit`/`tests/agents`). This is a bug in shared code, **outside spec 014's own diff**
— `backend/agents/factory.py` lines 602-623, the custom-agent prompt-composition path used by
every composed/custom-agent workflow in the app, not just these 5 fixtures.

**What it does**: for every `custom-agent:<instance_id>` step, `_compose_system_prompt`
unconditionally appends:
```
## How to deliver
Call `write_file` with path `{filename}`. Its content is your answer — never this instruction.
```
`{filename}` is an auto-generated name (`artifact_name(instance_id, ctx.topic)`, e.g.
`greet-test.md`) — **not** gated on whether the step actually has `write_files: true`, and
**not** reconciled with any filename the step's own `workflow.yaml` `prompt:` text names.

**Two concrete problems this causes for the 5 fixtures**:

1. Steps with `write_files: true` (`greet`, `say-hello`, `say-hola`, `done`, `welcome`,
   `review`) get a contradictory instruction: their own prompt says write to a real,
   downstream-consumed filename (e.g. `input.txt`), while the auto-append says write to a
   different, made-up one (`greet-test.md`). Confirmed live: `qwen3.5:4b` looped 20+ tool-call
   turns on the `greet` step of `ex_A2_branch`, alternating between the two
   filenames and wrong argument names (`path` vs `file_path`), before eventually settling.
2. Steps with `write_files: false` — **`pick`, `check`, `revise-check`, `decide`, i.e. every
   actual conditional-gate decision step in all 5 fixtures** — still receive the same
   "call `write_file`" instruction despite not having that tool bound at all. This was not
   directly observed yet (the live run never got past `greet`), but by the same mechanism as
   (1) it is expected to produce the same failure mode on the steps that matter most for
   testing routing/branching/looping.

**Why this predates and is broader than spec 014**: the append in `factory.py` has no
awareness of per-step tool grants or of what the step's own prompt already asked for — this
would affect any composed workflow with a `write_files: false` custom-agent step or a
`write_files: true` step whose prompt names its own filename, not something specific to these
5 fixtures.

**Decision (2026-08-21)**: per explicit instruction, no code change to `factory.py` (or any
`.py` file) right now — this section exists to record the finding and request approval before
anyone touches it. Only `workflow.yaml`/`.http` file changes are in scope for the moment.
Candidate fixes for a future approved pass (not decided, not started):
- Gate the "How to deliver" append in `factory.py` on the step actually having `write_files`
  bound, so a write-less step is never told to call a tool it doesn't have.
- Reconcile `{filename}` with whatever the step's own prompt already commits to, where one is
  stated.

**Mitigation attempted within the current no-code-change constraint**: simplifying the 5
fixtures' own step prompts to be maximally explicit/directive, to reduce (not eliminate) the
odds a small model gets confused by the conflicting delivery instruction. This cannot fully
fix problem (2) above — a write-less step's prompt cannot grant itself a tool.

---

## 7. Display-name finding — FIXED (approved 2026-08-21)

Found the same live-testing pass: every step of all 5 fixtures showed as the generic
`"Custom Agent"` during a live run, instead of its own workflow.yaml `name:` (e.g. `Greet`,
`Pick Language`). Initially misdiagnosed as possibly needing a code fix in the roster-building
seam; the user's first instruction ("fix this the way we do for custom workflows") was
initially misread as approval for a broad code change, which was reverted once clarified —
the actual ask was narrower: reuse whatever mechanism composer-built (DB) custom workflows
already use, and check first whether it was even a code problem at all.

**Root cause**: `backend/app/api/run_commands.py` (~lines 2559-2575), the roster-building
fallback for a **bare `pipeline_type` launch with no `agent_ids`** (exactly how all 5 fixtures
are launched — no `user_workflow_id`, no `agent_ids` in the `.http` suite's launch payload):

```python
agents = get_pipeline_agents(base_pipeline_type)   # [] — custom-agent instances have no AGENT.md
if not agents:
    _plan = compile_for_run(base_pipeline_type)
    if _plan is not None and _plan.steps:
        agents = [load_agent_spec(s.agent_id) for s in _plan.steps]   # BUG
```
`load_agent_spec("custom-agent:greet")` resolves to the **shared template**
(`agents/prompts/custom-agent/AGENT.md`, `name: Custom Agent`) — identical for every instance,
since the template has no per-instance awareness. Every step in the roster ends up literally
named `"Custom Agent"`.

**Why composer-built (DB) workflows never hit this**: for a `USER_WORKFLOW_MANIFEST` launch,
`run_commands.py` leaves `agents = None` entirely. That's what lets `engine.py`'s own correct
seam run: `if compiled.steps and not agents: agents = self._specs_from_plan(compiled.steps)`
(`engine.py:1675-1676`). `_specs_from_plan` (`engine.py:1042-1057`) is the one place that
correctly overlays each step's real `display_name` (its manifest `name:` field) onto the
generic template spec — but because `run_commands.py`'s buggy fallback already populates
`agents` with the wrong (non-empty) list for a bare `pipeline_type` launch, `not agents` is
`False` by the time it reaches the engine, so this correct fallback is silently skipped. There
is already a regression test (`backend/tests/agents/test_specs_from_plan.py`) guarding
`engine.py`'s own 3 call sites against exactly this bare-comprehension pattern reappearing —
it has no visibility into `run_commands.py`, so this 4th occurrence of the same pattern, in a
different file, went uncaught.

**Verified this is the ONLY affected launch path**, checked all 3 (not 2) launch types this
app actually has (`run_commands.py:2014-2041`, the full `LaunchSource` enum):

| Launch type | Code path | Affected? |
|---|---|---|
| File-based, bare `pipeline_type` (our 5 fixtures) | The buggy fallback above | **Yes** |
| "Overridden file-based" stored in DB (`USER_WORKFLOW_FLAT` — `manifest_json` has no `"steps"` key, uses a flat `row.agents` id list) | A third, separate branch (`run_commands.py:2528-2537`) | No — always real, file-backed agent ids, never `custom-agent:*` instances; `load_agent_spec` is already correct there |
| Custom workflow stored in DB (`USER_WORKFLOW_MANIFEST`, composer-built) | `agents` stays `None`, engine's own `_specs_from_plan` runs | No — already correct |

**Fix applied** (1 line, reusing the exact same helper the engine already uses for this — this
IS "the way we do it for custom workflows", literally the same function call):
```python
agents = get_execution_engine()._specs_from_plan(_plan.steps)
```
This also gives, for free, the exact precedence rule discussed during triage: a step's own
`display_name` wins when present; otherwise falls back to the agent's own name from its file
— because that precedence is already what `_specs_from_plan` implements.

**Adjacent, unrelated observation surfaced during this investigation (not fixed, not
requested)**: `USER_WORKFLOW_FLAT`'s launch branch (`run_commands.py:2416-2429`) never reads
`user_workflow_row.manifest_json` at all — so if that column is meant to carry a per-step
selections override for a flat/file-based saved workflow, it may not be getting applied at
launch time. Flagged for awareness only; not investigated further, not in scope here.

**Status**: approved and applied.

---

## 8. `.http` suite re-run findings — in progress, sequential file-by-file

Re-running all 5 `ex_A*` fixtures one at a time (each followed to its actual
terminal state, one full QA report per file at
`specs/014-conditional-gates/tests/{name}_report.md`), now that entitlements, the model tag,
prompt tightening, and the display-name fix (§7) have all landed. Each file's individual report
is the source of truth; this section tracks cross-file findings and status only.

### 8a. `ex_A2_branch` — FAIL (AC #3 only)

Gate routing (AC #1/#2) correct — exactly one of the two forward branches ran, `pipeline_complete`
reached, display names correct. AC #3 (deliverable content) failed: `greet`/`say-hello` ignored
their `write_file` instructions, matching the §6 root cause. Full report:
`specs/014-conditional-gates/tests/ex_A2_branch_report.md`.

### 8b. `ex_A1_loop` — FAIL (loop never exercised) + NEW engine finding

Same §6 write_file-adherence root cause, but with a worse cascade here: `greet` never wrote
`hello.txt`, so `check` never produced a parseable `{"decision": ...}`, so the `conditional`
gate correctly fired `gate_blocked` (`"no matching route outcome and no default_next"`,
`backend/agents/capabilities/gates/conditional.py` lines 99-120 — this part is correct,
fail-closed behavior). The loop-back mechanism this fixture exists to test (R-06/R-07/R-08,
`loop_max_iterations: 3`) was consequently never exercised even once.

**New finding, separate from §6, NOT previously logged — a real engine-behavior gap, not a
prompt-adherence issue**: `gate_blocked` does not actually stop the run. `backend/agents/execution_engine/engine.py`'s
`_evaluate_gates`: a `block` outcome from a non-HITL gate (`conditional` is not in
`_HITL_GATES`) only short-circuits that step's own remaining declared gates — it does not map
to the `cancel` sentinel HITL gates use, so the dispatch loop's normal step-advance logic just
continues to the next step in manifest order. Observed directly: `gate_blocked` fired at
`seq 2837` for `custom-agent:check`, and the very next event (`seq 2838`) was
`agent_start custom-agent:done` — the run proceeded to `done` and reported `status: "completed"`
regardless. **Net effect: a conditional gate that fails closed with "nowhere to go" is currently
indistinguishable, at the run-status level, from a clean pass.** This is a correctness gap in
spec 014's own gate machinery (not shared/pre-existing code like §6) and should probably map to
a `failed`/blocked terminal status rather than falling through — flagged here, **not fixed**,
per the same no-code-change-without-approval constraint as §6.

Also confirmed: this run executed against the *pre-tightening* step prompts (the yaml edits in
§6's mitigation landed on disk mid-run) — a fresh re-run against the current, tightened prompts
is needed before treating write_file-adherence as re-verified for this fixture. Full report:
`specs/014-conditional-gates/tests/ex_A1_loop_report.md`.

### 8c–8e. `ex_A4_human_gate`, `ex_A3_divert`, `ex_A3_target`

Not yet run.

### Status

In progress. Two real findings outstanding, both pending approval, neither fixed:
- §6 — `factory.py`'s contradictory "How to deliver" append (shared/pre-existing code).
- §8b — `gate_blocked` not halting the run (spec 014's own `engine.py`/`_evaluate_gates`).

*(Superseded — both now resolved. See §9 and §10 below.)*

---

## 9. §6 and §8b — resolved

### 9a. §6 write_file adherence — FIXED

`factory.py` now computes `has_write_access = "write_file" not in denied_tools` from the
step's own effective permissions and threads it into `_compose_system_prompt`, so the
"How to deliver" append is only emitted for a step that actually has `write_file` bound.
A write-less step is no longer told to call a tool it cannot call. The five
`ex_A*` fixtures were also rewritten (tools removed where not needed,
positive phrasing, `write_files: true` on the delivery steps only).

`ex_A2_branch` re-ran clean afterwards: routing correct for both the
english and spanish outcomes, ~14s, no spurious `gate_blocked`, deliverables written.

### 9b. §8b `gate_blocked` not halting the run — FIXED

`engine.py`'s pre-step gate loop separated `block` from `wait_human`. Previously both set a
single `_halted` flag whose only effect was `cursor += 1; continue` — the refused step was
skipped and the run carried on through every downstream step, finishing as
`pipeline_complete`. A refused run was therefore indistinguishable from a clean pass at the
run-status level, exactly as this section described.

Now a `block` outcome terminates the run with the same single-terminal shape the fan-out
child-failure abort (KRN-004) uses: `state_machine.transition(..., "failed")`, a budget
snapshot, one `pipeline_failed` event naming the blocked step, and `return` — no further
steps, no `pipeline_complete`. `wait_human` deliberately keeps the old skip-and-continue
path: it is a pause the human resolves, and a rejection there already arrives as the
`cancel` outcome handled higher in the same loop.

`_evaluate_gates` itself is unchanged, so the existing gate tests
(`tests/agents/test_gates.py`, which assert on the outcome/event stream rather than on run
continuation) are unaffected.

---

## 10. Remaining, deliberately NOT changed

### 10a. `ORIGINAL USER REQUEST` injection (`engine.py`, `_build_context_message`)

The brief is prepended verbatim as the headline block of every step's context, including
steps that carry their own authored `prompt`. This was root-caused during the §6
investigation as a contributor to steps ignoring their own instructions, and the two are
related: the `_own_prompt` check immediately below already suppresses the Planning Context
echo for exactly this class of step, so demoting the brief to a background block for
own-prompt steps would be the consistent fix.

**Not applied.** Two blockers, both procedural rather than technical:
1. `tests/agents/characterization/golden/sample_subagents_parallel.events.json` captures the
   literal `=== ORIGINAL USER REQUEST ===` string four times, and that fixture's workflow
   *does* use step prompts — so the change requires regenerating a checked-in golden.
2. Whether the reworded prompt actually improves adherence is only answerable from a live
   model run.

The §6 fix plus the fixture prompt tightening already cleared the symptom this was blamed
for (`ex_A2_branch` passes), so this is a latent prompt-shape concern, not
an active defect.

### 10b. Fixture re-runs

`ex_A1_loop`, `ex_A4_human_gate`,
`ex_A3_divert` and `ex_A3_target` have not been re-run since
the §6 fix, the `agent_skipped` event, and the §8b fix landed. `previous_step` in particular
never exercised its loop mechanism (R-06/R-07/R-08) — its earlier failure was entirely
downstream of §6, so it is the one most likely to behave differently now.
