---
phase: quick-260811-mxg
verified: 2026-08-11T00:00:00Z
status: passed
verdict: PASSED-WITH-CONCERNS
score: 8/8 must-haves verified
overrides_applied: 0
concerns:
  - id: C1
    severity: warning
    title: "_rehydrate_planning_context can still raise on a malformed PLANNER row, contradicting its own docstring contract"
    evidence: "Probed at HEAD: explicit_constraints=[{...}] -> TypeError: unhashable type: 'dict' (set() at engine.py:3040); explicit_constraints=5 -> TypeError: object of type 'int' has no len() (logger.info at engine.py:3084). SmartPlanner persists raw unvalidated LLM JSON (smart_planner.py:433 json.loads, no coercion), so the shape is not impossible."
    impact: "New failure mode confined to the resume path (pre-change the row was never read). Two-line hardening closes it."
  - id: C2
    severity: warning
    title: "No test covers the import-time ClarifyEngine binding — the property is real and its loss is silent"
    evidence: "Verified by hand: with clarify_engine.ClarifyEngine patched to a fake lacking _merge_answers the rehydrator still merged ['Target? -> SPINNAKER']; the late-bound counterfactual raises AttributeError, which the narrow guard swallows into a warning and drops every answer."
    impact: "A plausible 'tidy the duplicate import' refactor silently degrades every resumed run; nothing goes red. ~15-line regression test closes it."
  - id: C3
    severity: warning
    title: "A NESTED revision sub-pipeline reuses the outer revision's :rev1 threads and resets the outer's scratch fields"
    evidence: "Probed at HEAD: a second _gate_update_specs on the analyze re-run recurses into _run_spec_revision_sub_pipeline (depth 2, both levels revision_index=1); thread ids duplicate across the two passes ('rev-nested:{specify,plan,analyze}:rev1' twice), and the inner finally sets ectx.revision_attempt = 0 while the outer pass is still on the stack."
    impact: "D3's replay dependency survives for a SECOND revision cycle in the same gate session. The stated D3 truth (differs from the FIRST pass) still holds; strictly better than pre-change."
  - id: C4
    severity: info
    title: "BASELINE.md and SUMMARY.md are untracked"
    evidence: "git ls-files shows only the PLAN under .planning/quick/260811-mxg-.../; BASELINE.md + SUMMARY.md are '??'. The plan lists BASELINE.md in files_modified for Tasks 1 and 3."
    impact: "The RED/baseline evidence is not in git and is exposed to the known `git stash -u` sweep hazard."
  - id: C5
    severity: info
    title: ".planning/IMPLEMENTATION-REGISTER.md has no entry for this task"
    evidence: "grep 260811 over the register returns nothing; 79 other quick-task entries exist."
    impact: "The register is the standing pointer-first index consulted before future fixes."
deferred:
  - truth: "Live Bedrock acceptance (the four artifact_refs property assertions, run three times)"
    addressed_in: "End-of-milestone live pass"
    evidence: "Explicitly deferred by the task constraints; recipe recorded verbatim in 260811-mxg-BASELINE.md under '## Deferred: live Bedrock acceptance (end-of-milestone)'."
---

# Quick 260811-mxg — Verification Report

**Goal:** close D1 (revision pass never injects the artifact under revision), D2 (a resumed
run rebuilds its planning context from a stub) and D3 (the revision re-run reuses the first
pass's checkpoint thread), as defined in `.planning/BUGFIX-SPEC-REVISION-CONTEXT.md`.

**Branch:** `bugfix/spec-revision-context-loss` · baseline `edc44daa` · HEAD `7333f313`
**Verified:** goal-backward, adversarial. Every claim below is CONFIRMED by a command I ran
or by source I read; SUMMARY.md assertions were treated as unproven until re-checked.

---

## Observable Truths

| # | Truth (from PLAN must_haves) | Status | Evidence |
|---|------|--------|----------|
| 1 | D1 — the specify re-dispatch's composed context message contains the prior spec | VERIFIED | Drove the real sub-pipeline; `PRIOR-SPEC-SENTINEL` present in the specify `context_message`, inside a `=== PRIOR ARTIFACT UNDER REVISION ===` block at char 216, *before* the analysis-report block at char 674 |
| 2 | D1/TRAP-2 — fires from BOTH `_gate_update_specs` sub-pipeline call sites | VERIFIED | Wrapped `_run_spec_revision_sub_pipeline` and captured the caller frame: `[live]` enters at **engine.py:4453** (post-stream consumer, ex-:4296), `[reentry]` at **engine.py:3417** (RESUME-17 gate re-entry, ex-:3270). Both carry the sentinel |
| 3 | D1 no-leak — specify only; scratch empty after the pass (incl. error path) | VERIFIED | Per-dispatch dump, both modes: specify `PRIOR=True BLOCK=True`; plan and analyze `PRIOR=False BLOCK=False` (report only). `ectx.spec_revision_prior_artifact == ''` and `revision_attempt == 0` after every drive. One write site (engine.py:5255), cleared in the pre-existing `finally` (5303) that already covers cancel/error/return |
| 4 | D2 — a resumed dispatch carries the planner's real intent + the clarification answers | VERIFIED | `_rehydrate_planning_context` reads the max-version `planning_context` row and re-merges every `clarifications` round; wired at the skip-planner branch (engine.py:1787). Hydration (`_hydrate_artifacts_from_store`, engine.py:1416, **unfiltered by kind**) precedes it, so the rows are in the graph. Proven end-to-end by `test_resume_dispatch_carries_rehydrated_planning_context`, which drives the REAL resume tier and spies the composed message |
| 5 | D2/TRAP-4 — planner and clarifier still NOT re-invoked; context rehydrated, never regenerated | VERIFIED | The helper performs graph reads + a pure merge only — no planner/clarifier call exists on any path. `test_offset0_gate_resume_does_not_replan_or_reclarify` green (orchestrator-run); that test seeds no `planning_context` row, so the helper takes its no-row early return — its greenness cannot be a swallowed exception |
| 6 | D3 — the revision dispatch threads a fresh `:rev{N}` | VERIFIED | Observed thread ids: first pass `rev-live:story-estimator`; sub-pipeline `…:domain-analyst:rev1`, `…:epic-architect:rev1`, `…:story-estimator:rev1`. Re-entry mode yields `:rev2` (RESUME-17 fail-safe-high seeding). `revision_index` is now live (engine.py:5229) |
| 7 | INV-3 dormancy — inert on a normal run and on clarify replay | VERIFIED | **Structural, not incidental**: both fields have exactly one write site each, inside the sub-pipeline, cleared in its `finally`; both read sites are truthiness-guarded (`engine.py:8566`, `engine.py:3695`); `_rehydrate_planning_context` has exactly one caller, gated on `_resuming` alone (`_replaying_clarify` deliberately excluded). Goldens 5f/5p identical at both commits (orchestrator); I additionally re-ran `test_restart_resume.py`, `test_redo_gate_safety.py`, `test_steering_seam.py`, `tests/unit/test_execution_engine.py`, `test_execution_context.py` at **both** `edc44daa` and HEAD — identical failing ids, identical counts |
| 8 | INV-1/SC-001 — no workflow-name or agent-id literal introduced | VERIFIED | `git diff -U0 … \| grep '^+'` over `agents/execution_engine/` for `prototype-specify\|prototype-plan\|od_prototype\|"prototype"\|od_ppt\|app_builder` → 0 matches. The injection is keyed on generic ectx scratch fields; the specify dispatch is selected by object identity (`sub_spec is specify_spec`), not an id string |

**Score: 8/8.**

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `backend/agents/execution_engine/context.py` | two documented, default-empty scratch fields | VERIFIED | `spec_revision_prior_artifact: str = ""` (:291), `revision_attempt: int = 0` (:301), documented in the `redo_directive` family style. Dataclass is constructed by keyword everywhere and never `asdict`-serialised, so the mid-list insertion is safe |
| `backend/agents/execution_engine/engine.py` | F1 injection + block, F3 `:rev{N}`, F2 rehydrator | VERIFIED | Read at 1787, 2969-3090, 3695-3697, 5222-5229, 5255-5259, 5300-5304, 6564, 8553-8576 |
| `backend/tests/agents/test_spec_revision_context.py` | D1 routing (both sites), no-leak, D3 thread | VERIFIED | Substantive: drives the real sub-pipeline, asserts on the emitted `agent_input.context_message`, uses `**kwargs` gate stubs, reads agent ids from the registry |
| `backend/tests/agents/test_restart_resume.py` | D2 unit + wiring tests | VERIFIED | The wiring test drives the real resume tier (`_ResumeHarness` + `_drive_user_resume`) with durable `ScopedStore` rows and spies `_compose_context_message`; it also asserts the stub intent is **absent** |
| `.planning/…/260811-mxg-BASELINE.md` | pre-change baseline + verbatim RED + post-change classification + deferred recipe | VERIFIED (content) / see C4 | All four sections present and accurate — but the file is **untracked** |

---

## Key Links

| From | To | Via | Status | Detail |
|---|---|---|---|---|
| `_run_spec_revision_sub_pipeline` | `ectx.spec_revision_prior_artifact` | `_latest_typed_content(ectx, specify_spec.id)` before the loop, published for specify only, cleared in `finally` | WIRED | engine.py:5222/5255/5303 |
| `ectx.spec_revision_prior_artifact` | `_compose_context_message` | getattr-guarded block rendered immediately before the SPEC KIT ANALYSIS REPORT block | WIRED | engine.py:8566; observed ordering 216 < 674 |
| `_run_agent` thread_id | `ectx.revision_attempt` | `:rev{N}` suffix after `:redo{N}`, dormant at 0 | WIRED | engine.py:3695 |
| skip-planner branch | `_rehydrate_planning_context` | called instead of `_default_planning_context` when `_resuming` only | WIRED | engine.py:1787; `_resuming = _is_resume` (:1751) |
| `_rehydrate_planning_context` | `ClarifyEngine._merge_answers` | engine-module IMPORT-TIME binding `_ClarifyEngineImpl` (engine.py:81) | WIRED + PROVEN | With `clarify_engine.ClarifyEngine` monkeypatched to a fake lacking `_merge_answers`, the rehydrator still merged; the late-bound counterfactual raises `AttributeError`. The lazy import at :1949 is intact |

**Real-run reachability (not just the fixture):** every agent output is persisted with
`producer_agent=spec.id` (engine.py:4240, guarded only by `if output:`), so
`_latest_typed_content(ectx, specify_spec.id)` resolves the live spec v1 on a real
`od_prototype` revision. `_compose_context_message` applies no truncation, so an ~11k-token
block reaches the model whole. D1 is not fixture-dependent.

---

## Judgement on the executor's self-reported deviation (malformed-row shape validation)

**Correct, correctly scoped, but the stated contract is still overclaimed.**

- The deviation is genuine: `p.get(...)` in the pair-shaping loop sits outside the plan's
  narrow guard, so a `clarifications` row that parses to a non-list (or a list of
  non-dicts) would have raised. Adding `isinstance` checks is the minimum fix and does not
  widen the catch.
- Guard discipline holds: the only `except` clauses in the new code are
  `(ValueError, TypeError)` ×2 and `(AttributeError, TypeError, KeyError)` ×1. **No bare
  `except` and no `except Exception` anywhere in the diff** (plan constraint 9 satisfied).
- I re-ran the executor's claim adversarially with 15 shapes. All 12 clarifications /
  planner-JSON shapes it named degrade cleanly (see the table below). **Two shapes it did
  not test do raise** — see concern **C1**. So "never raises into the run" (helper
  docstring, and "None raise" in SUMMARY.md) is true for clarifications rows and false for
  a malformed *planner* row.

| Probe | Result |
|---|---|
| no rows / invalid planner JSON / planner list / planner null | degrades to stub, no raise |
| clarifications: non-list, list-of-strings, missing fields, invalid JSON, null, list-of-nulls | skipped with a warning, no raise |
| clarifications: well-formed | `['Target? → SPINNAKER']` |
| **planner `explicit_constraints=[{...}]`** | **TypeError: unhashable type: 'dict'** |
| **planner `explicit_constraints=5`** | **TypeError: object of type 'int' has no len()** |

Suggested two-line hardening (not applied — verification is read-only):
`existing = {c for c in (base.get("explicit_constraints") or []) if isinstance(c, str)}`
and a length-safe log argument.

---

## Judgement on the executor's two honesty flags

1. **"The BUG-R05 test's green is not a swallowed exception."** *Sound, and stronger than
   its own evidence.* The absence of a `resume rehydrate:` line does establish the no-row
   early return (every other path in the helper logs). Independently: that test seeds no
   `planning_context` artifact, and the helper contains no planner/clarifier invocation on
   any path, so the change cannot make the test green for the wrong reason. The corollary
   the executor did not state: that test therefore exercises **none** of the rehydration —
   the wiring proof rests entirely on
   `test_resume_dispatch_carries_rehydrated_planning_context`.
2. **"The import-time binding is load-bearing but untested."** *Accurate, and the gap is
   material — close it now.* I reproduced both the property and the counterfactual (see the
   key-links table). The failure mode of losing this binding is not a crash: the narrow
   guard converts it into one warning line and a resumed run with **zero** clarification
   answers — the exact silent degradation this task removes. A comment is the only thing
   protecting it today. Concern **C2**.

---

## Anti-patterns

| Scan | Result |
|---|---|
| `TODO/FIXME/XXX/TBD/HACK/PLACEHOLDER` in added lines | none |
| bare `except` / `except Exception` in added lines | none |
| workflow-name / agent-id literals in added source | none |
| new storage (migration / table / column / artifact kind) | none |
| dual implementation | none — `_merge_answers` reused; the two `ClarifyEngine` bindings are one class with deliberately different resolution timing, documented in place |

---

## Regression evidence I generated myself

| Suite | `edc44daa` (worktree) | HEAD `7333f313` | Verdict |
|---|---|---|---|
| `tests/agents/test_restart_resume.py` | 7 failed, 41 passed (7 ids listed) | 7 failed, 43 passed (**same 7 ids**) | no regression; +2 new green |
| `test_redo_gate_safety.py` + `test_steering_seam.py` + `tests/unit/test_execution_engine.py` + `test_execution_context.py` | 6 failed, 25 passed | 6 failed, 25 passed (**same ids**) | identical |

This matters because the 7 pre-existing reds are all resume-tier tests — precisely where a
D2 regression could hide behind a "pre-existing" label. It cannot: the same 7 fail at the
pre-change commit. (Goldens 5f/5p and `lint-imports` 3 kept / 1 broken were re-baselined by
the orchestrator at both commits.)

---

## Residual concerns (do not block the fix)

- **C1** — malformed *planner* row can raise on resume. WARNING.
- **C2** — untested load-bearing import-time binding, silent failure mode. WARNING;
  recommend closing before merge.
- **C3** — nested revision reuses `:rev1`. CONFIRMED by probe (depth 2, duplicate thread
  ids). Belongs on the same card as the already-recorded third `_gate_update_specs` branch
  at engine.py:3518 (ex-:3371). WARNING.
- **C4 / C5** — untracked evidence files; no IMPLEMENTATION-REGISTER entry. INFO.

## Deferred (not findings)

Live Bedrock acceptance, per the task constraints. Recipe recorded in BASELINE.md.

---

_Verified by the gsd verifier — read-only. No source modified, no commit, no push._
