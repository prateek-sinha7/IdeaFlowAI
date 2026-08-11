---
phase: quick-260811-mxg
plan: 01
status: complete
subsystem: engine
tags: [execution-engine, spec-revision, resume, planning-context, checkpointer, prompt-composition, tdd]

requires:
  - phase: KAN-101
    provides: the spec-revision sub-pipeline and its consume-once `spec_revision_context` seam
  - phase: RESUME-04 / RESUME-17
    provides: unfiltered artifact-graph hydration on resume, and the gate re-entry sentinel
  - phase: quick-260719-hd5 (BUG-R05)
    provides: the planner/clarifier skip on resume that this plan rehydrates around
provides:
  - "D1: the spec writer now receives the document it is told to preserve, at BOTH `_gate_update_specs` consumer sites"
  - "D2: a resumed run reconstructs its real planning context (planner intent + clarification answers) from the durable rows"
  - "D3: a revision re-run threads a fresh `:rev{N}` checkpoint instead of depending on replay"
  - "the first tests in the repo that assert on the spec-revision payload"
affects: [spec-revision, restart-resume, prompt-composition, checkpoint-threading]

tech-stack:
  added: []
  patterns:
    - "consume-once injection seam (4th member): `spec_revision_prior_artifact`"
    - "fresh-checkpoint-thread suffix (3rd member): `:rev{N}` beside `:redo{N}` / `:retry{n}`"
    - "deliberate dual-timing import binding: import-time for the rehydrator, late for the live clarify invocation"

key-files:
  created:
    - backend/tests/agents/test_spec_revision_context.py
    - .planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-BASELINE.md
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/context.py
    - backend/tests/agents/test_restart_resume.py

key-decisions:
  - "Fixed D1 through a consume-once ectx scratch field, not `consumes` — self-consumption is structurally impossible because `_filter_consumed_outputs` breaks on `upstream.id == spec.id` and specify is `ordered_agents[0]`."
  - "Did not give the spec writer file tools — `spec.md` is written by the build step ~1h40m after the revision pass needs it, and a second on-disk copy would duplicate what `artifact_refs` already versions (INV-3/12)."
  - "Rehydrated the planning context rather than re-running the planner — re-running regresses BUG-R05, guarded by `test_offset0_gate_resume_does_not_replan_or_reclarify`."
  - "Bound `ClarifyEngine` at engine-module import time for the rehydrator while KEEPING the lazy import at engine.py:1924 — different resolution timing is deliberate, not a dual implementation."
  - "Gated the rehydrator on `_resuming` alone; clarify replay keeps the stub as a known, recorded gap."
  - "No new storage: no migration, no table, no column, no artifact kind."

patterns-established:
  - "Prompt-injection seams are keyed on generic ectx scratch fields and are default-empty, so dormancy (INV-3 byte-parity) is structural rather than tested-for."
  - "A pre-change baseline is recorded on the actual pre-change commit before any red is called a regression."

requirements-completed: [QUICK-260811-mxg-D1, QUICK-260811-mxg-D2, QUICK-260811-mxg-D3]

duration: ~75min
completed: 2026-08-11
---

# Quick 260811-mxg: `update_specs` prior-spec injection + resume context rehydration — Summary

**The spec writer now receives the document it is told to preserve, a resumed run
reconstructs its real planning context from rows that were always durable, and the
revision pass no longer depends on the checkpointer replaying the turn it is meant to
replace — three defects closed with zero new storage and zero golden drift.**

## Performance

- **Duration:** ~75 min
- **Tasks:** 3 of 3
- **Files modified:** 5 (2 source, 2 test, 1 evidence log)
- **Commits:** 3 (tests RED → F1+F3 → F2), nothing pushed

## Accomplishments

- **D1 (primary).** `_run_spec_revision_sub_pipeline` reads the artifact under revision once
  via the max-version typed read and publishes it on a new consume-once scratch field for the
  **specify sub-dispatch only**; `_compose_context_message` renders it as
  `=== PRIOR ARTIFACT UNDER REVISION ===` immediately **before** the existing analysis-report
  block (subject first, instructions second). The writer declares `consumes: []` and
  `tools: []`, so this is its only channel — the "preserve unchanged sections" instruction
  was literally unsatisfiable before.
- **D2.** `_rehydrate_planning_context` reconstructs the planner's real `inferred_intent` and
  re-merges every durable clarification round through the one existing
  `ClarifyEngine._merge_answers`. Pure read — RESUME-04 hydration had already put the rows in
  the graph. The 4,591 → 291 char collapse is reproduced offline in the RED evidence and gone
  in the GREEN.
- **D3.** `revision_index` was a dead parameter; it now drives `ectx.revision_attempt` and a
  `:rev{N}` thread suffix. This also closes a latent prod-reachable case the brief flagged:
  redo-then-`update_specs` previously revised the **rejected** draft.
- **Test coverage where there was none.** `spec_revision_context` appeared in zero files under
  `backend/tests/` before this task — the gap that let the defect ship.

## Task Commits

1. **Task 1: baseline + five RED tests** — `46fb310c` (test)
2. **Task 2: F1 prior-artifact injection + F3 fresh revision thread** — `7badc86a` (fix)
3. **Task 3: F2 resume planning-context rehydration** — `7333f313` (fix)

Branch `bugfix/spec-revision-context-loss`. **Not pushed.**

## Files Created/Modified

- `backend/agents/execution_engine/context.py` — two additive, documented, default-empty
  scratch fields: `spec_revision_prior_artifact` (consume-once) and `revision_attempt`.
- `backend/agents/execution_engine/engine.py` — the prior-artifact prompt block; the
  read/publish/clear discipline in `_run_spec_revision_sub_pipeline`; the `:rev{N}` thread
  suffix in `_run_agent`; `_rehydrate_planning_context` + its wiring at the skip-planner
  branch; the import-time `ClarifyEngine` binding; one corrected stale docstring.
- `backend/tests/agents/test_spec_revision_context.py` — new; the D1 routing test
  (parametrized over both consumer sites), the D1 no-leak test, the D3 thread test.
- `backend/tests/agents/test_restart_resume.py` — the D2 unit + wiring tests.
- `.planning/.../260811-mxg-BASELINE.md` — pre-change baseline, verbatim RED evidence,
  post-change comparison, deferred live recipe.

## RED → GREEN evidence

Every test was observed failing before implementation. Full verbatim output is in
`260811-mxg-BASELINE.md` (`## RED evidence`). Each failure was an assertion or an
`AttributeError` inside the test body — **zero pytest errors**, so none was a fixture or
collection problem masquerading as a RED.

| # | Test | RED reason (observed) | Now |
|---|------|----------------------|-----|
| 1a | `..._injects_prior_artifact...[live]` | report present, document absent (engine.py:4296 site) | GREEN |
| 1b | `..._injects_prior_artifact...[reentry]` | same, via the RESUME-17 re-entry (engine.py:3270 site) | GREEN |
| 2 | `..._does_not_leak_to_plan_or_analyze` | `AttributeError: 'ExecutionContext' object has no attribute 'spec_revision_prior_artifact'` | GREEN |
| 3 | `..._uses_a_fresh_checkpoint_thread` | all three ids equalled the first pass's | GREEN |
| 4 | `test_rehydrate_planning_context_rebuilds...` | `AttributeError: ... no attribute '_rehydrate_planning_context'` | GREEN |
| 5 | `test_resume_dispatch_carries_rehydrated...` | assertion — prompt was the 3-line stub, `**Inferred Intent**: Run the wave workflow.` | GREEN |

## Baseline vs post-change

Measured on the pre-change commit `edc44daa`, then re-measured. The remembered
"10 failed / 6 passed" figure was `dev`-only and stale; it was not used.

| Command | Pre-change | Post-change | Verdict |
|---------|-----------|-------------|---------|
| 5 characterization goldens | `5 failed, 5 passed` | `5 failed, 5 passed` | identical, same ids |
| `test_restart_resume.py` | `7 failed, 41 passed` | `7 failed, 43 passed` | same 7 ids, +2 newly green |
| `test_redo_gate_safety.py` + `test_steering_seam.py` | `3 failed, 10 passed` | `3 failed, 10 passed` | identical, same ids |
| `tests/unit/test_execution_engine.py` | `3 failed, 11 passed` | `3 failed, 11 passed` | identical, same ids |
| `lint-imports` | `3 kept, 1 broken` | `3 kept, 1 broken` | identical, same contract |
| `test_spec_revision_context.py` (new) | `4 failed` | `4 passed` | newly green |

**New reds: none.** The 18 pre-existing reds + 1 broken contract are enumerated by id in
BASELINE.md and were left untouched (scope fence). `test_offset0_gate_resume_does_not_replan_or_reclarify`
(TRAP 4 / BUG-R05) is green.

## Verification beyond the plan's gates

Two claims the plan's automated gates could not actually falsify, so I checked them directly:

- **The TRAP-4 test is green for the right reason.** Run with `--log-cli-level=INFO` it emits
  no `resume rehydrate:` line, proving the rehydrator took its no-durable-row early return and
  never reached the merge — its pass is not a swallowed exception.
- **The import-time `ClarifyEngine` binding is load-bearing.** No test exercises the
  conjunction it exists for (patched module attribute **and** reaching the merge). Verified by
  hand: with `clarify_engine.ClarifyEngine` replaced by a `_FakeClarify` that has no
  `_merge_answers`, the rehydrator still merged `['Target? → SPINNAKER']`. A function-level
  import would have resolved the fake, raised `AttributeError`, been caught by the narrow
  guard, and silently dropped every answer.

## Deviations from plan

**One — [Rule 2, missing critical functionality] the rehydrator's malformed-row paths.**

- **Found during:** Task 3, adversarial self-review of the diff before committing.
- **Issue:** the plan specified a narrow guard around the `_merge_answers` **call**, but a
  `clarifications` row that parsed to a non-list (or a list of non-dicts) would raise
  `AttributeError` from `p.get(...)` in the pair-shaping loop **outside** that guard —
  breaking the helper's own "never raises into the run" contract on exactly the malformed-row
  case the guard was written for.
- **Fix:** validate `isinstance(pairs, list)` and skip entries that are not dicts or lack
  `question_id` / `question_text`. Still narrow; still no broad catch.
- **Verified:** five malformed shapes (non-list, list-of-strings, missing fields, invalid
  JSON, `null`) each degrade to the planner intent with no constraints; a malformed planner
  row degrades to the stub. None raise.
- **Commit:** `7333f313`.

Everything else executed as written. No architectural (Rule 4) decisions arose.

## Known gaps and follow-ups (recorded, deliberately not acted on)

- **Clarify replay is excluded from D2.** On a replay the durable rows exist but the questions
  are about to be re-asked, so injecting previously-merged answers is a behaviour change no
  source artifact analysed. A widened condition needs its own analysis, not a one-word edit.
- **Skipped clarification questions do not reconstruct.** `_persist_qa` writes the raw
  responses map before `_merge_answers` auto-fills `recommended_answer`, and persists neither
  `recommended_answer` nor `ambiguity_category`; so answered questions reconstruct exactly,
  skipped ones cannot, and `clarified_topics` comes back empty. Recorded in the helper's
  docstring together with the untaken alternative.
- **A third `_gate_update_specs` branch** at engine.py:3371 only re-seeds
  `spec_revision_pending_output` and breaks — so a **second** "Update the Specs" click at the
  re-opened gate appears not to run the sub-pipeline at all. Out of scope; looks like a
  separate latent defect worth its own card.
- **Three stale gate stubs** in `test_redo_gate_safety.py` are red at baseline purely because
  they pin a pre-`update_specs_eligible` `_run_review_gate` signature. Diagnosed in BASELINE.md,
  not fixed (scope fence) — a cheap, well-understood cleanup for whoever wants it.

## Deferred: live Bedrock acceptance

Explicitly deferred per the task constraints; offline evidence closes this. The recipe —
property assertions against `artifact_refs` (not the UI, which wipes v1 on `agent_start` per
FIX-039), the four assertions that all FAIL on the reported run, and the run-it-three-times
rule — is recorded verbatim in
`.planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-BASELINE.md`
under `## Deferred: live Bedrock acceptance (end-of-milestone)`.

## Self-Check: PASSED

All five files claimed above exist on disk; all three commit hashes exist in
`git log`. Branch is `bugfix/spec-revision-context-loss`, working tree clean of modified
tracked files, **nothing pushed**. The three untracked paths that are not mine
(`.planning/ROUTE-MIGRATION-COST-ANALYSIS.md`, `.planning/TEST-HARNESS-OFFLINE-DESIGN.md`,
`backend/.runs-local/`) are untouched — no `git stash` was used at any point.

`STATE.md` was deliberately **not** modified: this is a quick task, separate from the
planned phases, and advancing the phase counters would misreport the roadmap position.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data paths were introduced.

## Threat Flags

None. No new network endpoint, auth path, file-access pattern, or schema change. Both new
prompt blocks re-present first-party data this run already produced (its own prior output,
the user's own answers) and are read through `ectx.artifacts`, populated by the owner-scoped
`ScopedStore.tree()` hydration — no new store call and no cross-run or cross-owner read path
(T-mxg-01 mitigated as planned).
