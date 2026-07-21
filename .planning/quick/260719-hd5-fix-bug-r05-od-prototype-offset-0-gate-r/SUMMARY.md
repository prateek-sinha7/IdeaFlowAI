# Quick 260719-hd5 — Fix BUG-R05: od_prototype offset-0 gate resume re-plans instead of re-entering the gate

**Branch:** feat/ui-2 · **Commit:** `8c20f9b6` · **Date:** 2026-07-19 · **Status:** Verified (offline)

## The bug (root-caused live)

An `od_prototype` run parked at the SPEC review gate resumes with offset **0** — the gated
agent `prototype-specify` is step INDEX 0 (`order: 1, gate: Human_Gate`). The 49-02 open-gate
override correctly returns 0, but `_execute_impl` decided "am I resuming?" with
`_resuming = _resume_from > 0` (engine.py:1697), reading offset 0 as a **fresh start**. So
`skip_planner` (:1717) was False → the planner ran → `CLARIFY_REQUIRED` → the auto-clarifier
re-parked the run at a NEW questionnaire, all BEFORE reaching the `if _is_resume:`
gate-reentry block (armed :2194). Live proof: a restart of a spec-gate-parked run emitted
`planner_start → planner_complete → CLARIFY_REQUIRED → questionnaire_ready` (re-clarified).
`user_stories` resumes correctly only because its offset is 2 (`> 0`). Offset 0 was
OVERLOADED. Unmasked by the R01/R02 alias fix `e1866317`; the identical predicate bug was
already fixed for workspace-recovery in Phase 12-05 — this sweeps the two sibling sites.

## The fix (2 predicate changes — backend/agents/execution_engine/engine.py)

1. **:1697** `_resuming = _resume_from > 0` → `_resuming = _is_resume` (skip planner+clarifier
   and suppress the "planning" transition on an offset-0 gate resume).
2. **:1372** `if _resume_from > 0:` → `if _is_resume:` (hydrate the typed graph at offset 0 so
   the reopened gate reviews REAL output, not "").

Left unchanged (genuine offset arithmetic): :1236 wave `is_resuming`, :1278 workspace-recovery
(already `_is_resume or _resume_from > 0`), :2233 `i < _resume_from` step-skip. Only the two
"am I resuming at all?" booleans changed.

## The test (RED→GREEN)

`tests/agents/test_restart_resume.py::test_offset0_gate_resume_does_not_replan_or_reclarify`
— built on the proven :3110 test (step-0 gate + REAL resume tier via `_drive_user_resume`),
swapping its planner PROCEED-fake for `CLARIFY_REQUIRED` (the live conjunction it misses).
ClarifyEngine stubbed to emit the spurious second `questionnaire_ready` and return (no hang).
Asserts post-fix: planner NOT re-run, clarifier NOT re-run, step-0 gate re-enters.
- RED (pre-fix HEAD): `AssertionError: offset-0 gate resume must NOT re-run the planner ...
  {'n': 1}`.
- GREEN (post-fix): 1 passed.

## Verification (offline; live-Bedrock owned by orchestrator)

- Characterization goldens (`SNAPSHOT_UPDATE` unset): **10/10 passed**, byte/event-identical.
- `test_restart_resume.py` + `test_rest_resume.py`: **53 passed** (new test + all offset>0 /
  user_stories paths).
- `test_phase8_resume` + `test_resumability` + `test_resume_marker_workspace`: **15 passed**.
- `lint-imports`: 4 kept, 0 broken.

**Only offset-0 resumes change.** `_is_resume` is False on every fresh/scripted run (goldens
dormant), and BOTH `_is_resume` and `_resume_from > 0` are True on every offset>0 resume →
no change there (53+15 tests confirm). The single new behavior: an offset-0 resume
(`_is_resume=True, _resume_from=0`) now skips planner/clarifier and hydrates the graph, so a
step-0 gate re-enters instead of re-planning.

## Guardrails
INV-3 (goldens identical) · INV-12 (consolidated onto the existing `_is_resume` predicate —
same one 12-05 and the :2194 sentinel use; no dual impl, no new driver) · INV-1/SC-001 (keys
only on generic `_is_resume`/offset; no workflow-name literal) · INV-13 untouched; no
migration, no WS event, no FE.

## Self-Check: PASSED
- engine.py — 2 predicate edits present (git diff verified).
- test_restart_resume.py — new test present, GREEN.
- Commit `8c20f9b6` on feat/ui-2 (git rev-parse verified).
