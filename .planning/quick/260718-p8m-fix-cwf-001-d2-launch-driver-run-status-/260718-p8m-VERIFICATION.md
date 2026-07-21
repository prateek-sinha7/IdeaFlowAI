---
phase: 260718-p8m
verified: 2026-07-18T00:00:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Quick Task 260718-p8m: CWF-001 FIX D2 — Launch Driver Run-Status Fail-Safe Verification Report

**Task Goal:** `_drive_launch_to_queue` in `backend/app/api/run_commands.py` must record
`status="failed"` (not `completed`) when a run ends with a generic `error` event or
`pipeline_failed` (mirroring the revision twin `_drive_revision_to_queue`), while still
recording a clean `pipeline_complete` run as `completed`/`degraded`.

**Verified:** 2026-07-18
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A launch run whose stream ends in a generic `error` event (no clean `pipeline_complete`) persists `status == "failed"` | VERIFIED | `app/api/run_commands.py:1430-1441` tracks `pipeline_error_seen` + captures `pipeline_error_msg`; terminal `else` (`:1463-1469`) sets `wr.status = "failed"`. Test `test_driver_generic_error_records_failed` (`tests/unit/test_rest_run_launch.py:422-479`) asserts `row.status == "failed"`, `!= "completed"`, `row.error` non-null containing "unsatisfiable". Ran green: `37 passed`. |
| 2 | A launch run emitting `pipeline_failed` (no clean `pipeline_complete`) persists `status == "failed"` | VERIFIED | `elif utype == "pipeline_failed":` branch (`:1438-1441`) sets `pipeline_failed_seen`; same fail-safe `else` applies. Test `test_driver_pipeline_failed_records_failed` (`:483-532`) asserts `row.status == "failed"`, `!= "completed"`. Green. |
| 3 | A failed launch run persists a non-null `wr.error` | VERIFIED | `:1469` — `wr.error = first_agent_error_msg or pipeline_error_msg`. Test A asserts `row.error is not None` and `"unsatisfiable" in row.error`. |
| 4 | A clean `pipeline_complete` (no error signal) still persists `status == "completed"` — no regression | VERIFIED | `:1457-1462` — `elif (pipeline_complete_seen and not pipeline_error_seen and not pipeline_failed_seen): wr.status = "completed"`. Existing happy-path test `test_driver_drives_engine_and_populates_queue` (`:256-321`) still asserts `row.status == "completed"` plus a new anti-regression `assert row.status != "failed"` (`:321`). Green. |
| 5 | Terminal-status precedence stays `cancelled > degraded > failed > completed` | VERIFIED | Read `:1448-1469`: `if pipeline_cancelled_seen` → `elif degraded_failed_agents is not None` → `elif <clean terminal>` → `else: failed`. Order unchanged from pre-fix structure; only the `elif`/`else` bodies at the tail were reconciled. |
| 6 | `_drive_launch_to_queue` and `_drive_revision_to_queue` are behaviorally consistent (Phase 29 LOCK-B) | VERIFIED | Read `_drive_revision_to_queue` (`:1643-1708`): `_persist_terminal_status("cancelled" if pipeline_cancelled_seen else "degraded" if degraded_seen else "completed" if (pipeline_complete_seen and not pipeline_failed_seen) else "failed")` — same precedence, same "completed only on clean terminal, else failed" contract as the launch driver's now-reconciled logic. Both twins independently confirmed green (`test_rest_run_launch.py` + `test_rest_revisions.py`, 37 passed together). |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/api/run_commands.py` | `_drive_launch_to_queue` tracks generic `error` + `pipeline_failed`, fail-safe terminal | VERIFIED | Diff (`git show a0c98b8f`) is exactly the plan's 3 minimal changes: state flags (+6 lines), event-loop branches (+12 lines), fail-safe terminal reconcile (`elif pipeline_complete_seen:` → gated 3-condition `elif`, `else:` → unconditional `"failed"` + `wr.error`). 29 insertions, 4 deletions, single file besides tests. |
| `backend/tests/unit/test_rest_run_launch.py` | RED→GREEN driver tests: generic error → failed; pipeline_failed → failed | VERIFIED | `test_driver_generic_error_records_failed` (uses `code: "workflow_unsatisfiable"`, contains the required `workflow_unsatisfiable` string) and `test_driver_pipeline_failed_records_failed` both present and green. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `_drive_launch_to_queue` event loop | `pipeline_error_seen` / `pipeline_failed_seen` flags | `elif utype == "error"` / `elif utype == "pipeline_failed"` | WIRED | Confirmed at `:1430` and `:1438`; `grep -n 'utype == "error"\|utype == "pipeline_failed"'` matches both lines. |
| `_drive_launch_to_queue` terminal assignment | `wr.status = "completed"` | `pipeline_complete_seen and not pipeline_error_seen and not pipeline_failed_seen` | WIRED | Confirmed at `:1457-1462`; the gate is a 3-term `and`, exactly the declared pattern. |

### Behavioral Spot-Checks / Test Execution

| Command | Result | Status |
|---------|--------|--------|
| `python3.11 -m pytest tests/unit/test_rest_run_launch.py tests/unit/test_rest_revisions.py -q` | `37 passed` | PASS |
| `python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py -q` | `10 passed` (byte/event-identical goldens) | PASS |
| `/opt/homebrew/bin/lint-imports` | `Contracts: 4 kept, 0 broken` | PASS |
| `git diff c194cbfe a0c98b8f --name-only` (scope fence) | Only `backend/app/api/run_commands.py` + `backend/tests/unit/test_rest_run_launch.py` touched; `engine.py`/`resolver.py`/`user_workflows.py` diff empty | PASS |
| `grep -n 'pipeline_type ==' app/api/run_commands.py` | Two PRE-EXISTING refs at `:1089`/`:1154`, both outside the edited terminal-derivation block (`od_ppt_revision` / `base_pipeline_type == "ppt"` — unrelated app-layer logic, not new) | PASS — no new workflow-name literal introduced |
| Migration / `sa.Enum` scan | No new alembic revision files; `WorkflowRun.status` untouched as a free `String` column | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| CWF-001-D2 | 260718-p8m-PLAN.md | Launch driver terminal status fail-safe on generic error/pipeline_failed | SATISFIED | All 6 truths verified above; tests green; twin parity confirmed. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/api/run_commands.py` | 1414 | `any_agent_errored = True` — now assigned but never read (`ruff F841`) | INFO | The variable's only prior use (`wr.status = "failed" if any_agent_errored else "completed"`) was removed by the D2 fix-safe reconcile; it is now dead. Confirmed via `ruff check app/api/run_commands.py` → 1 finding (F841). No functional impact — the fail-safe `else` branch reaches `"failed"` regardless of this flag's value, so behavior is correct. `.git/hooks/pre-commit` is not installed locally, so the repo's own `ruff` pre-commit gate never ran on this commit; if/when the branch goes through CI with hooks enforced this would surface as a lint failure and should be cleaned up in a small follow-up (delete the dead assignment, keep `first_agent_error_msg` capture which is still used). Does not block the D2 goal — status derivation is verified correct by the passing tests. |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers found in the edited region (`:1313-1470`).

### Human Verification Required

None. All truths are verifiable by static read + targeted pytest; no visual/real-time/external-service behavior is in scope for this app-layer status-derivation fix.

### Gaps Summary

No gaps. The launch driver's terminal-status derivation now fail-safes to `"failed"` on a
generic `error` event, `pipeline_failed`, or any stream ending without a clean
`pipeline_complete` — matching the LOCK-B revision twin's contract exactly. Clean
`pipeline_complete` still yields `"completed"`/`"degraded"` correctly (verified by the
untouched, still-passing happy-path test plus a new anti-regression assertion). Scope was
held to D2 only: no engine/resolver/compiler edits, no migration, no `sa.Enum`, no new
workflow-name literal, and no D1 (DAG satisfiability guard) or CWF-002 (per-agent model
persistence) code was introduced (confirmed by diffing the two commits against `engine.py`,
`resolver.py`, and `user_workflows.py` — all empty). One minor, non-blocking lint nit (dead
`any_agent_errored` variable, ruff F841) is noted above as an INFO-level anti-pattern for a
future small cleanup — it does not affect correctness or goal achievement.

---

_Verified: 2026-07-18_
_Verifier: Claude (gsd-verifier)_
