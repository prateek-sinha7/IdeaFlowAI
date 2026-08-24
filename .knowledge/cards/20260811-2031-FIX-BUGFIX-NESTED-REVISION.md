---
id: FIX-BUGFIX-NESTED-REVISION
type: fix
kind: event
title: Bugfix brief — the two deferred `update_specs` defects
status: open
applies_to:
  phases: []
  modules:
  - Base
  - User
  - agents
  - app
  - skills
  globs:
  - .planning/BUGFIX-SPEC-REVISION-CONTEXT.md
  - backend/agents/execution_engine/engine.py
  - engine.py
  - tests/agents/test_spec_revision_context.py
  - test_restart_resume.py
  - tests/agents/_scripted_model.py
  - .claude/skills/velocity-ai-bookkeeping/SKILL.md
  requirements: []
locked_constraints:
- INV-1
- INV-3
verification:
  type: test
  status: required
  test_files:
  - tests/agents/test_spec_revision_context.py
  - tests/agents/_scripted_model.py
compact_summary: 'Two deferred defects: a second update_specs click at the re-opened gate silently no-ops, and nested revisions collide on the same :rev1 thread id.'
last_updated: '2026-08-14'
author: 'Imran Yousaf <imrany@hexaware.com>'
author_source: code-commit
---

<!-- RELATED -->

## Related

**Depends on:** [FIX-214](20260811-1559-FIX-214.md), [FIX-BUGFIX-SPEC-REVISION-CONTEXT](20260811-1630-FIX-BUGFIX-SPEC-REVISION-CONTEXT.md)

**Referenced by:** [ISS-052](20260811-2101-ISS-052.md), [ISS-064](20260812-0001-ISS-064.md)

<!-- /RELATED -->

# Bugfix brief — the two deferred `update_specs` defects (A: nested revision, B: silent no-op)

**Branch:** `bugfix/spec-revision-context-loss` (continues from quick `260811-mxg`; dev merged at `84f4bbe3`)
**Found:** 2026-08-11, during the plan-check / verify / live-run of `260811-mxg`. Both are **pre-existing**, neither was introduced by that fix.
**Status:** diagnosed, unfixed.

---

## Context you need first

Read `.planning/BUGFIX-SPEC-REVISION-CONTEXT.md` — it explains the `update_specs` sub-pipeline these two defects live in, and its fix (D1/D2/D3) is already merged and **live-proven on Bedrock** (run `5ecb990f`, 0 headings lost, 97.6% verbatim carry-over). Do not undo any of it.

**The live flow, observed today** — one "Update the Specs" click costs **four** approvals:
1. click *Update the Specs* at the analyze gate → sub-pipeline runs specify
2. specify re-run gate opens (it carries `gate: Human_Gate`) → approve
3. plan re-run gate opens → approve
4. analyze re-run completes → the sub-pipeline returns → **the analyze gate RE-OPENS** with the new analysis → approve → build

Both defects concern what happens at step 4's re-opened gate, or at a second revision cycle.

---

## Defect B — a second "Update the Specs" at the re-opened gate silently does nothing *(higher priority)*

**Where:** `backend/agents/execution_engine/engine.py:3545-3548`

```python
elif gate_event.get("type") == "_gate_update_specs":
    ectx.spec_revision_pending_output = gate_event.get("analysis_report") or ""
    spec_revision_attempt += 1
    break
```

There are **three** `_gate_update_specs` branches — `:3428` and `:4444` call `_run_spec_revision_sub_pipeline` (at `:3444` and `:4480`); this third one at `:3545` only re-seeds and `break`s. The engine's own comment at ~`:3179` describes that branch as "the re-open-after-sub-pipeline stage", i.e. it was written to *close* a revision, not to *start* one.

**User journey.** You revise, approve the revised spec and plan, and the analyze gate re-opens with a fresh report. You are still not satisfied, so you click *Update the Specs* again on the gate in front of you. The click is accepted, the gate closes — and no revision runs. The pipeline advances to the build and constructs the prototype from the spec you were trying to change. Silent no-op, invisible on screen, one wasted build.

⚠️ **Confidence: inferred from code, NOT observed live.** During the `5ecb990f` live run I reached this exact gate and approved rather than re-revising. **Reproduce it first** — that is task 1.

## Defect A — a nested revision produces duplicate `:rev1` and resets the counter under the outer pass

**Where:** `engine.py:5325-5331` (the sub-pipeline's `finally`) and the per-`_run_agent` local at `:3317`.

```python
finally:
    ectx.spec_revision_context = ""
    ectx.spec_revision_prior_artifact = ""
    ectx.revision_attempt = 0          # <-- unconditional reset
```

`spec_revision_attempt` is a **local** of each `_run_agent` invocation (`:3317`, starts at 0). The analyze re-run *inside* the sub-pipeline is itself gated, so an `update_specs` there re-enters the consumer at `:4444` and calls the sub-pipeline again — **depth 2**, with the inner pass computing `spec_revision_attempt == 1` exactly as the outer did. The verifier observed both levels reporting `revision_index=1`.

Two consequences:
1. **Duplicate `:rev1` thread ids** across two different revision passes, so the second pass attaches to the first pass's LangGraph conversation instead of a clean one — the "model remembers the wrong thing" class D3 exists to prevent.
2. The inner `finally` sets `ectx.revision_attempt = 0` **while the outer pass is still on the stack**, so the outer's later dispatches silently lose their suffix.

⚠️ **Confidence:** the duplicate ids and the reset were observed by the verifier via instrumentation. A resulting *bad spec* was **not** observed. Real defect, speculative damage.

---

## The coupling — read before planning

**These two are not independent.** Defect B's natural fix is "make that branch fire the sub-pipeline too". But that is precisely what creates the depth-2 nesting Defect A is about. So:

- **Fix A's stack discipline FIRST**, then B, or
- fix B in a way that does not nest (e.g. let the re-opened gate start a *sibling* cycle after the outer has returned, rather than a nested one).

Decide deliberately and record the reasoning. A plan that fixes B without addressing the nesting it enables is incomplete.

Also settle explicitly: **is a second revision cycle a behaviour we want at all?** If the product answer is "no, one revision then approve-or-reject", then B's fix is to *stop offering the affordance* at the re-opened gate (`update_specs_eligible=False`) rather than to wire it up — a smaller, safer change. That is a legitimate outcome; state which you chose and why.

---

## Constraints

1. **Do not regress quick `260811-mxg`.** `tests/agents/test_spec_revision_context.py` (4) and the `-k rehydrat` set (7) must stay green. The `:rev{N}` suffix, the prior-artifact injection and the resume rehydration all stay.
2. **INV-3 dormancy** — no revision, no resume ⇒ byte-identical. Goldens must not move.
3. **Baseline before you judge a red.** At `84f4bbe3`: goldens **5 failed / 5 passed**, lint-imports **3 kept / 1 broken**, `test_restart_resume.py` **7 failed / 48 passed**. Re-measure at the pre-change commit; a red is not automatically yours.
4. **INV-1 / SC-001** — generic scratch fields and structural predicates only; no workflow-name or agent-id literals.
5. **No new storage** — no migration, no new table or column.
6. Backend: `python3.11` from `backend/`, **no venv** (`uv run --no-sync` fails — there is no `.venv`). Targeted test selections only; the full suite hangs offline.

## Tests

1. **Reproduce B first and see it RED** — assert that an `update_specs` at the re-opened analyze gate actually starts a revision (or, if the chosen answer is "don't offer it", assert the affordance is absent). Use the scripted-model harness `tests/agents/_scripted_model.py`.
2. **Nested-revision test** — two consecutive revision cycles produce **distinct** thread ids (no duplicate `:rev1`), and `ectx.revision_attempt` is correct for the outer pass *after* the inner completes.
3. **Safety boundary** — a single revision cycle behaves exactly as it does today (the `260811-mxg` tests are the guard).

## Bookkeeping

Close with the **`velocity-ai-bookkeeping`** skill (`.claude/skills/velocity-ai-bookkeeping/SKILL.md`). Note its ID-allocation rule: `FIX-214/215/216b` are live in `dev` commit messages but absent from the register, so the next id is **max(register, cards, commit messages on both branches) + 1** — not register-max + 1.

## Out of scope

Artifact-version UI; read-tool access for text-only agents; `redo` semantics; anything in `260811-mxg`.
