---
phase: quick-260811-si4
plan: 01
status: complete
subsystem: execution-engine
tags: [agents, engine, revision, checkpoint-threads, re-entrancy, hitl-gates]
date: 2026-08-11
branch: bugfix/spec-revision-context-loss
pushed: false
requires:
  - FIX-217 (quick-260811-mxg) — the :rev{N} thread suffix and the prior-artifact injection this builds on
provides:
  - flat sibling revision cycles from the re-opened analyze gate (ISS-050 closed)
  - a re-entrant _run_spec_revision_sub_pipeline safe at any depth (ISS-051 closed)
  - one shared _gate_update_specs consumer (INV-12)
affects:
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/context.py
tech-stack:
  added: []
  patterns:
    - "monotone per-run high-water mark for id minting (the :redo{N} / :retry{n} / :rev{N} replay class)"
    - "save/restore finally instead of clear-to-zero, for a re-entrant generator"
    - "advisory affordance fence + structural safety net, rather than server-side enforcement"
key-files:
  created:
    - backend/tests/agents/test_spec_revision_cycles.py
    - .planning/quick/260811-si4-fix-nested-revision-thread-collision-and/260811-si4-BASELINE.md
    - .knowledge/cards/FIX-218.md
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/context.py
    - backend/tests/agents/test_redo_gate_safety.py
    - .planning/FIX-REGISTER.md
    - .planning/FIX-TEST-REGISTER.md
    - .planning/ISSUES-REGISTER.md
    - .planning/IMPLEMENTATION-REGISTER.md
    - .planning/STATE.md
decisions:
  - "Chose (i) flat sibling cycles over (ii) withdrawing the affordance — the brief's coupling premise was disproved by three offline probes"
  - "revision_high_water is monotone per run and NEVER restored — that is the whole id-collision guarantee"
  - "_update_specs_eligible is an ADVISORY fence; the engine is made correct for the nested case regardless (T-si4-01)"
  - "Server-side enforcement (ISS-053) and collapsing the double analyze gate (ISS-052) deliberately left OPEN"
ids:
  fix: FIX-218
  test: TEST-004
  issues-closed: [ISS-050, ISS-051]
  issues-cross-referenced: [ISS-052, ISS-053]
metrics:
  tasks: 3
  commits: 3
  tests-added: 5
  tests-revived: 3
  engine-net-lines: -139
---

# Quick 260811-si4: Flat Sibling Revision Cycles + Re-entrant Sub-pipeline Summary

Closed both deferred `update_specs` defects — the silent no-op second "Update the Specs" and
the nested-revision `:rev1` thread collision — by wiring the re-opened gate to a **flat
sibling** cycle through one shared consumer, fencing the in-flight affordance, and making the
revision sub-pipeline genuinely re-entrant.

## The decision actually taken, and why

The brief asked for a deliberate choice between **(i)** wiring Defect B up and giving Defect A
stack discipline, and **(ii)** withdrawing the affordance at the re-opened gate
(`update_specs_eligible=False`) as the smaller, safer change. It framed the two defects as
coupled: *"B's natural fix is 'make that branch fire the sub-pipeline too'. But that is
precisely what creates the depth-2 nesting Defect A is about."*

**That premise is wrong, and the plan corrected it with evidence before this executor ran.**
Three probes against `c0d7b46b`:

1. **Nesting is already reachable and does NOT depend on fixing B.** The analyze re-run inside
   the sub-pipeline is a full `_run_agent`, so it opens its own gate with
   `update_specs_eligible=True`. A click there started a depth-2 pass *today*. Option (ii)
   would have left Defect A entirely untouched.
2. **Wiring B creates NO nesting — it is a SIBLING call.** The sub-pipeline's `finally` runs
   *before* its terminal `_revision_analyze_output` yield, and the driving `async for` runs the
   generator to exhaustion before `break`ing. Probe, `ectx.revision_attempt` sampled inside the
   gate: `[0]` outer `= 0`, `[1]` in-pass `= 1`, `[2]` re-opened `= 0`. By the time control
   reaches the re-opened gate the pass is fully unwound.
3. **(ii) would have been dishonest.** `engine.py` already documents the re-opened gate as
   existing "so the user can Accept **or request another revision cycle**." A second cycle
   already ships and already runs — one gate earlier, where it works apart from the id
   collision. Suppressing the affordance would leave two visually identical gates back to back,
   one accepting revisions and one refusing.

**Chosen: (i), in its flat-sibling form.** Wire B at the re-opened gate; withhold the
affordance while a pass is in flight so the single supported entry point is the one gate where
the cycle is flat; and fix A **structurally anyway**, because `_run_review_gate` acts on
`action == "update_specs"` without ever consulting the eligibility flag — the flag is an FE
affordance, not a server-side fence, so a replayed or crafted POST still nests.

## What changed

| Edit | File | What |
|------|------|------|
| 1 | `context.py` | `spec_revision_context: str = ""` promoted from an **undeclared attribute** (it worked only because `ExecutionContext` is a non-slots dataclass) to a declared field, so the save/restore reads a real default. New `revision_high_water: int = 0` — a monotone per-run mark, never cleared and never restored. |
| 2 | `engine.py` | New `_update_specs_eligible(artifact_kind, ectx)` — one structural predicate replacing the expression inlined at **all three** gate call sites, adding `and not ectx.revision_attempt`. |
| 3 | `engine.py` | `_run_spec_revision_sub_pipeline` made re-entrant: effective index derived from the high-water mark (`revision_index if it exceeds the mark else mark + 1`), and the `finally` **restores** the three scratch fields instead of clearing them. |
| 4 | `engine.py` | New `_consume_update_specs` — the ONE `_gate_update_specs` consumer. Two near-identical ~50-line copies and the broken stub deleted; the re-open branch (the Defect-B fix) now drives it. |

Net **-139 lines** in `engine.py`. Exactly **one** `_run_spec_revision_sub_pipeline` call site
remains, **three** `_consume_update_specs` call sites, **zero** inlined eligibility expressions.

## RED-to-GREEN evidence

All four defect tests were written first and **observed RED** against the unmodified engine at
`bf51a170`, under a gate demanding exactly 4 failed / 0 passed that **rejects a pytest
collection or fixture error as not-RED** — because `_run_agent` swallows a stub `TypeError`
into an `agent_error` event, so a broken fixture looks like a failing assertion from outside.

| Test | Pre-fix (RED) — verbatim | Post-fix |
|------|--------------------------|----------|
| `test_reopened_gate_second_update_specs_runs_a_second_cycle` | `expected … 7; the second 'Update the Specs' ran no cycle. Got 4: [':story-estimator', ':domain-analyst:rev1', ':epic-architect:rev1', ':story-estimator:rev1']` | GREEN — 7 dispatches, cycle 1 on `:rev1`, cycle 2 on `:rev2`, all 7 distinct |
| `test_reopened_gate_cycle_keeps_a_flat_stack` | `the second cycle never ran, so there is no depth to compare` | GREEN — cycle 2's in-pass and re-opened gates at pairwise-equal `len(inspect.stack())` with cycle 1's |
| `test_update_specs_not_offered_while_a_revision_is_in_flight` | `the analyze re-run INSIDE the revision pass must NOT advertise 'Update the Specs' … got [True, True, True]` | GREEN — `[True, False, True]` |
| `test_nested_revision_keeps_distinct_threads_and_restores_the_outer_pass` | `two revision passes minted the SAME checkpoint thread id … 7 ids, 4 unique` | GREEN — 7 of 7 unique; at the gate after the inner return, `revision_attempt == 1` and `spec_revision_context` still set |
| `test_single_cycle_shape_is_unchanged` (boundary) | **PASSED pre-fix** — the dormancy guard | still GREEN |

## Baseline vs post-change

Measured at `bf51a170` (pre-change for code purposes: the three commits since `c0d7b46b` touch
only docs) and re-measured at `9be1b458`.

| Suite | Baseline | Post-change | Delta |
|-------|----------|-------------|-------|
| 5 characterization goldens | `5 failed, 5 passed` | `5 failed, 5 passed` | unchanged — **same failing ids** |
| `test_spec_revision_context.py` (mxg) | `4 passed` | `4 passed` | unchanged |
| `test_restart_resume.py` full | `7 failed, 48 passed` | `7 failed, 48 passed` | unchanged, same ids |
| `test_restart_resume.py -k rehydrat` (mxg) | `7 passed` | `7 passed` | unchanged |
| `test_redo_gate_safety.py` + `test_steering_seam.py` | `3 failed, 10 passed` | `13 passed` | **+3 newly green** |
| `tests/unit/test_execution_engine.py` | `3 failed, 11 passed` | `3 failed, 11 passed` | unchanged |
| **NEW** `test_spec_revision_cycles.py` | *(4 failed, 1 passed — the RED gate)* | `5 passed` | **+4 newly green** |
| `lint-imports` | `3 kept, 1 broken` | `3 kept, 1 broken` | unchanged |

**Zero regressions.** Every non-passing test is classified one-per-line in
`260811-si4-BASELINE.md`; the gate counted **0** `- new-red:` lines.

**INV-3 dormancy is machine-asserted, not eyeballed.** Task 1 wrote `GOLDENS-BASELINE:` and
`LINT-BASELINE:` lines and Tasks 2 and 3 string-diffed against them — counts **and** failing
ids, so swapping one red for another cannot slip past. Both reported `GOLDEN-DORMANCY-OK` /
`LINT-DORMANCY-OK`. The goldens were never run with `SNAPSHOT_UPDATE`.

## IDs allocated — the max-of-four derivation

Re-derived **at execution time**, not carried from the planning session. The plan's first draft
allocated `FIX-217` / `TEST-003` / `ISS-050` and commit `de42a7bf` burned every one of them
before execution — exactly the collision the rule exists to catch.

| Series | Register | Cards (`INDEX.md`) | `origin/dev` commits | This branch's commits | Max | Allocated |
|--------|----------|--------------------|----------------------|-----------------------|-----|-----------|
| `FIX-` | 217 | 217 | 216 | 217 | **217** | **FIX-218** |
| `TEST-` | 003 | *(none)* | *(none)* | 003 | **003** | **TEST-004** |
| `ISS-` | 053 | 061 | 061 | 061 | **061** | *(none needed)* |

**No id already held by quick-260811-mxg was reused.** Confirmed before writing anything:
`FIX-217` at `FIX-REGISTER.md:5005`, `TEST-003` at `FIX-TEST-REGISTER.md:15`, its knowledge
card at `INDEX.md:17`, and `IMPLEMENTATION-REGISTER.md:4180`. FIX-217 is cited as this task's
predecessor.

**A finding worth keeping:** the ISS series maxes at **053** in `ISSUES-REGISTER.md` but at
**061** in the cards and in commit messages — `ISS-054..061` are referenced by FIX-194 / FIX-195
/ FIX-201 rows and cards yet have **no rows in the issues register**. Any future `ISS-` must
therefore start at **062**, not 054. This task needed no new ISS row (Task 1's
`test_redo_gate_safety.py` was not reverted — it went to 7 passed), so nothing was allocated.

**ISS handling:** `ISS-050` and `ISS-051` **updated to Closed** with their resolutions, not
duplicated. `ISS-052` (the redundant double analyze gate) and `ISS-053`
(`update_specs_eligible` not server-enforced) **already existed and were cross-referenced
only** — both keep their OPEN status, each with a note recording why si4 deliberately left it.

## Deferred

**Live Bedrock acceptance is deferred to the end-of-milestone pass** per the standing rule; the
offline evidence above is sufficient for completion. The full behavioural recipe — the in-pass
button must be ABSENT, the re-opened one PRESENT, cycle 2's threads must carry `:rev2`, and
spec versions must be pulled via `GET /api/runs/{id}/artifacts` rather than the UI (because
`agent_start` wipes `output: ""`, FIX-039) — is recorded under
**`## Deferred: live Bedrock acceptance (end-of-milestone)`** in
`.planning/quick/260811-si4-fix-nested-revision-thread-collision-and/260811-si4-BASELINE.md`.

## Deviations from plan

**None — the plan executed exactly as written.** Every anchor resolved, every predicted pre-fix
failure reason matched, and `test_redo_gate_safety.py` went to 7 passed as measured during
planning, so constraint 7's revert path was not needed.

Two observations recorded rather than acted on:

- `tests/unit/test_execution_engine.py` has **3 pre-existing** clarify-engine reds. Planning
  quoted no figure for that suite, so it was measured fresh and recorded in the baseline; it is
  unchanged before and after.
- `check.py` exits **1** (usable with warnings) — the warnings are `cards vs registers` drift
  for unrelated plan files, which is the expected state per the skill.

## Commits

Three, on `bugfix/spec-revision-context-loss`, **nothing pushed**:

| Commit | Scope | What |
|--------|-------|------|
| `30159b36` | `test(agents)` | 5 new tests (4 observed RED) + the `**kwargs` stub revival |
| `9be1b458` | `fix(engine)` | The four surgical edits; two duplicate consumer blocks deleted |
| *(docs)* | `docs(quick-260811-si4)` | BASELINE.md, the five registers, the knowledge card |

## Known Stubs

None. No hardcoded empty value, placeholder string or unwired data source was introduced; both
new `ExecutionContext` fields are live-read by `engine.py` on the revision path and dormant
(empty/zero) elsewhere by design.

## Threat Flags

None. No new network endpoint, auth path, file-access pattern or schema change at a trust
boundary. The two boundaries this touches were already in the plan's `<threat_model>`
(`T-si4-01` the unenforced gate action, `T-si4-02` the checkpoint thread namespace) and both
carry `mitigate` dispositions that this change implements.

## Self-Check: PASSED

Every artifact claimed above was verified to exist on disk, and every commit hash was verified
present in `git log`:

- `backend/tests/agents/test_spec_revision_cycles.py` — FOUND
- `.planning/quick/260811-si4-fix-nested-revision-thread-collision-and/260811-si4-BASELINE.md` — FOUND
- `.planning/quick/260811-si4-fix-nested-revision-thread-collision-and/260811-si4-SUMMARY.md` — FOUND
- `.knowledge/cards/FIX-218.md` — FOUND
- commit `30159b36` — FOUND
- commit `9be1b458` — FOUND
- `_consume_update_specs` present in `engine.py` — FOUND
- `revision_high_water` present in `context.py` — FOUND
