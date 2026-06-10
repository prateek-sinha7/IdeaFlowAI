---
phase: 10-safe-local-exec-gated-on-n3-4b
plan: 02
subsystem: compiler
tags: [compiler, trust, exec, grant-path, d-01, inv-12, migration-ledger, security]

# Dependency graph
requires:
  - phase: 10-safe-local-exec-gated-on-n3-4b
    plan: 01
    provides: "Hardened argv exec_command + grown LocalExecutionPolicy (allow/deny + caps) + exec_runs audit (0018) + the single live runtime exec-allow surface (LocalExecutionPolicy.allows + pre-spawn check)"
  - phase: 08-capability-hardening
    provides: "compiler trust context (trust=file|builtin|user|db) + _check_trust CompilerError shape + _TRUSTED_SOURCES"
provides:
  - "Trust-conditional workflow_ceiling — ToolPermissions(exec=trusted) so file/builtin exec grants survive intersect_permissions; user/db ceiling collapses exec OFF"
  - "user/db privileged-grant guard — a user/db step granting exec/network/secrets raises CompilerError naming the grant + step (GRANT-PATH, T-10-02-01)"
  - "D-01 gates-required guard — an exec-granting step missing security OR approval raises CompilerError naming the missing gate; NO auto-injection (T-10-02-02/03)"
  - "INV-12 dual-surface resolution — plan.py:ExecutionPolicy.check forward surface DELETED; LocalExecutionPolicy.allows is the single live exec-allow decision"
  - "migration-ledger D11 row (ratcheted: grep ExecutionPolicy\\.check -> 0 in backend/)"
affects: [10-03-security-gate, 10-04-exec-validators, dynamic-composer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Trust-conditional grant ceiling: privileged perms survive intersect_permissions only for engineer trust (file/builtin); the ceiling is the compile-time gate, not the runtime block"
    - "Compile-time defense-in-depth: D-01 makes an unguarded exec step unauthorable (raise, never auto-inject) so the compiled plan mirrors the authored manifest (INV-5)"
    - "INV-12 dual-surface deletion ratcheted via migration-ledger grep gate"

key-files:
  created: []
  modified:
    - "backend/agents/workflows/compiler.py — trust-conditional ceiling + user/db privileged-grant CompilerError + D-01 gates-required CompilerError; _compile_step now threads the trust string"
    - "backend/agents/workflows/plan.py — DELETED ExecutionPolicy class + runtime_host + _PRIVILEGED_RUNTIME_ACTIONS (forward surface); ToolPermissions/intersect_permissions UNCHANGED"
    - "backend/tests/agents/test_compiler_trust.py — GRANT-PATH (file/builtin survive, user/db hard-fail) + D-01 (missing/both gates) + no-grant parity coverage (9 new tests)"
    - "backend/tests/agents/test_tool_permissions.py — dropped the 4 ExecutionPolicy.check tests + the import + docstring refs (deleted surface)"
    - "backend/tests/agents/test_migration_ledger.py — added D11 to _REQUIRED_ITEMS + the flipped expected set"
    - "specs/003-workflow-engine-decoupling/migration-ledger.md — added ratcheted D11 deletion row"

key-decisions:
  - "Deleted the WHOLE plan.py:ExecutionPolicy class (not just .check): runtime_host + _PRIVILEGED_RUNTIME_ACTIONS were referenced ONLY by the dead check method (grep-verified), so the class had no remaining live members — keeping a member-less husk would be dead code"
  - "Ceiling expressed as ToolPermissions(exec=trusted): a single boolean keyed on the existing `trusted` flag; network/secrets stay OFF in the ceiling for BOTH trust levels (they remain runtime gate-blocked, out of scope) so a file-trust network:true grant still intersects to False"
  - "user/db guard fires on the parsed step_grant (exec True / network True / secrets non-empty), naming ALL offending perms in one CompilerError, before the ceiling — so user/db never reaches a privileged binding"
  - "D-01 uses set-difference {security,approval} - set(gates) and names the SORTED missing gates; no mutation of the gates list (anti-pattern rejected)"

patterns-established:
  - "Trust-conditional compile-time ceiling — tier 1 of the 3-tier exec stack (compiler -> security gate -> workspace policy)"

requirements-completed: [EXEC-01]

# Metrics
duration: ~18min
completed: 2026-06-10
---

# Phase 10 Plan 02: Compile-Time Exec Enforcement (Trust Ceiling + D-01) Summary

**A trust-conditional compiler ceiling that lets file/builtin manifests grant `exec` (survives `intersect_permissions`) while user/db grants of exec/network/secrets hard-fail at compile, plus a D-01 gates-required check making an unguarded exec step unauthorable — and the INV-12 deletion of the dead `plan.py:ExecutionPolicy.check` dual surface, ratcheted in the migration ledger. Dormant for parity (no existing manifest grants exec).**

## Performance

- **Duration:** ~18 min
- **Tasks:** 2 (Task 1 TDD)
- **Files modified:** 6 (0 created, 6 modified)

## Accomplishments
- The compiler's `workflow_ceiling = ToolPermissions()` collapse (which forced `exec` OFF for EVERY manifest, even a file-trust `tools.exec:true`) is gone — the ceiling is now `ToolPermissions(exec=trusted)`, so a file/builtin manifest's exec grant survives the intersection and binds `Step.tools.exec=True`.
- **GRANT-PATH (T-10-02-01):** a user/db manifest granting exec/network/secrets raises `CompilerError` naming the offending grant(s) + the step — exec/network/secrets are engineer-only (file/builtin trust). Network/secrets stay OFF in the ceiling for BOTH trust levels (they remain runtime gate-blocked — out of scope here).
- **D-01 (T-10-02-02/03):** an exec-granting step missing the `security` OR `approval` gate raises `CompilerError` naming the missing gate; the compiler NEVER auto-injects the gates (the compiled plan must mirror the authored manifest — INV-5).
- **INV-12 resolved:** the documented "FORWARD SURFACE — NOT yet wired" `plan.py:ExecutionPolicy.check` (its `runtime_host` indirection + `_PRIVILEGED_RUNTIME_ACTIONS`) is DELETED — the live exec-allow decision is `LocalExecutionPolicy.allows` + the 10-01 pre-spawn allow/deny check, the single surface. Ratcheted in the migration ledger (D11, grep `ExecutionPolicy\.check` -> 0 in backend/).
- **Parity preserved:** the trust-conditional branch fires ONLY when a privileged perm is granted, so the un-granted path is byte-identical (5 characterization snapshots / 10 tests byte+event-identical); lint-imports 4 kept / 0 broken.

## Task Commits

1. **Task 1 (TDD): trust-conditional compiler ceiling + D-01 gates-required + user/db CompilerError** - `1a47f93` (feat)
   - RED tests written first (9 new tests failed: DID NOT RAISE / exec False), then GREEN within the same commit (TDD per the plan's `tdd="true"`; both touch one ceiling site so a single feat commit is the natural unit).
2. **Task 2: delete plan.py ExecutionPolicy forward surface (INV-12) + migration-ledger D11** - `11a801f` (refactor)

**Plan metadata:** (this docs commit)

## Files Created/Modified
- `backend/agents/workflows/compiler.py` (modified) - `_compile_step` threads the `trust` string; adds (1) user/db privileged-grant `CompilerError`, (2) D-01 gates-required `CompilerError`, (3) trust-conditional `ToolPermissions(exec=trusted)` ceiling
- `backend/agents/workflows/plan.py` (modified) - DELETED the `ExecutionPolicy` dataclass + `runtime_host` + `_PRIVILEGED_RUNTIME_ACTIONS` (replaced with a one-paragraph deletion note); `ToolPermissions`/`intersect_permissions`/`_and_mask` UNCHANGED
- `backend/tests/agents/test_compiler_trust.py` (modified) - `_grant_step_manifest` helper + `_register_user_allowed_exec_palette` + 9 new tests (file/builtin exec survive; user/db exec/network/secrets -> CompilerError; D-01 missing-approval/missing-security -> CompilerError; both-gates -> clean; no-grant parity across trust)
- `backend/tests/agents/test_tool_permissions.py` (modified) - dropped the 4 `ExecutionPolicy.check` tests + the `ExecutionPolicy` import + the docstring references (the surface is deleted; the runtime deny path is covered by `test_local_runtime.py`)
- `backend/tests/agents/test_migration_ledger.py` (modified) - added `D11` to `_REQUIRED_ITEMS` and to the `expected` flipped-set so the exact-set ledger assertion accounts for the new ☑ row
- `specs/003-workflow-engine-decoupling/migration-ledger.md` (modified) - added the ratcheted `D11` deletion row (gate `ExecutionPolicy\.check`, ☑)

## Decisions Made
- **Deleted the whole `ExecutionPolicy` class, not just `.check`:** grep confirmed `runtime_host` and `_PRIVILEGED_RUNTIME_ACTIONS` were referenced ONLY inside the dead `check` method — no live caller anywhere (the live callers all use `LocalExecutionPolicy` or the `agents/runtime/base.py:ExecutionPolicy` Protocol). Removing only `check` would leave a member-less dead husk, so the class went in full.
- **Ceiling = `ToolPermissions(exec=trusted)`:** a single boolean keyed on the existing `trusted` flag, the minimal change at the ceiling site. `network`/`secrets` stay OFF in the ceiling for both trust levels — the ceiling is the compile-time exec gate, not the place to enable network (that stays the runtime gate's job, out of scope).
- **user/db guard fires before the ceiling and names all offending perms:** so a user/db privileged grant is rejected with one clear message rather than silently collapsing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `test_tool_permissions.py` consumed the deleted `ExecutionPolicy` surface**
- **Found during:** Task 2 (deleting `plan.py:ExecutionPolicy`)
- **Issue:** `test_tool_permissions.py` imported `ExecutionPolicy` from `agents.workflows.plan` and had a 4-test block exercising `.check()` (the exact forward surface the plan deletes). Deleting the class would break the test suite at import time.
- **Fix:** Removed the `ExecutionPolicy` import, the 4 `test_execution_policy_*` tests, and the docstring references — replaced with a note pointing to the single live surface (`LocalExecutionPolicy.allows`, covered by `test_local_runtime.py`). This is the move-don't-copy discipline: deleting the surface also deletes its only test consumer.
- **Files modified:** backend/tests/agents/test_tool_permissions.py
- **Verification:** test_tool_permissions.py PASS (13 tests, the ToolPermissions/intersect/lowered_by coverage intact); the deleted block's behavior lives in test_local_runtime.py.
- **Committed in:** `11a801f` (Task 2 commit)

**2. [Rule 3 - Blocking] D11 ratchet self-matched the ledger test's own comment**
- **Found during:** Task 2 (ledger D11 row + grep ratchet)
- **Issue:** The D11 grep gate `ExecutionPolicy\.check` greps the WHOLE `backend/` (D11 is NOT kernel-scoped). My first-draft comment in `test_migration_ledger.py` contained the literal token `plan.py:ExecutionPolicy.check`, so the ratchet matched its own anchor string -> 1 match -> `test_deleted_pattern_absent_from_backend[D11]` FAILED.
- **Fix:** Reworded the comment to `plan.py ExecutionPolicy forward-surface helper` (no `.check` token). The `.md` ledger row keeps the descriptive `ExecutionPolicy.check` text — the ratchet only greps `*.py` (`--include=*.py`), so the Item-column prose is not scanned.
- **Files modified:** backend/tests/agents/test_migration_ledger.py
- **Verification:** `grep -rnE "ExecutionPolicy\.check" backend/ --include=*.py` -> 0 matches (rc=1); test_migration_ledger.py PASS (D11 ratchet green).
- **Committed in:** `11a801f` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 3 blocking issues — both are the natural consequence of a move-don't-copy deletion: the deleted symbol's test consumer and the ratchet's own anchor string).
**Impact on plan:** Neither is scope creep — both are required to land the plan's own deletion cleanly. `ToolPermissions`/`intersect_permissions` stayed untouched as the plan demanded.

## Issues Encountered
- The full offline backend pytest hangs (Chromium/Bedrock/Postgres-gated per backend/CLAUDE.md) — verified with the targeted suite (compiler_trust + compiler + migration_ledger + tool_permissions + characterization + banned_patterns + lint-imports), per the offline-test-suite memory note.

## Deferred Issues
None — no out-of-scope discoveries. (The Phase-9 `workspaces.repo_id` alembic drift noted in 10-01 is untouched by this plan, which makes no migration/ORM change.)

## Known Stubs
None — no stub patterns introduced (compiler logic + a deletion only; no UI/data wiring).

## Threat Flags
None — every surface this plan touches (the trust-conditional ceiling, the user/db + D-01 CompilerErrors, the dual-surface deletion) is already in the plan's `<threat_model>` (T-10-02-01..04, T-10-02-SC). Zero external packages added (T-10-02-SC: N/A confirmed).

## Verification Evidence
- `tests/agents/test_compiler_trust.py` + `test_compiler.py` — 28 passed (15 trust incl. 9 new GRANT-PATH/D-01, 13 compiler parity)
- `tests/agents/test_migration_ledger.py` — D11 ☑ ratchet green; `grep -rnE "ExecutionPolicy\.check" backend/ --include=*.py` -> 0
- `tests/agents/test_tool_permissions.py` — 13 passed (ExecutionPolicy block removed)
- `tests/agents/test_characterization_*.py` — 10 passed (5 snapshots byte+event-identical)
- `tests/agents/test_banned_patterns.py` — 11 passed
- `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken (compiler stays kernel-side; no new app import)

## Next Phase Readiness
- Tier 1 of the 3-tier exec stack is built: a manifest can now AUTHOR a constrained exec grant (file/builtin + `gates:[security,approval]`), and the compiled `Step.tools.exec` carries it.
- **10-03** adds tier 2 — the profile-conditional `security` + `approval` gate (the runtime PASS decision reading trust + `tools.exec` + `step.gates`, with the HITL approval delegation).
- **10-04** adds the compile/test/lint validators that reach exec through `KernelServices.workspace` + the IN-02/forward-surface enforcement ledger rows.

---
*Phase: 10-safe-local-exec-gated-on-n3-4b*
*Completed: 2026-06-10*

## Self-Check: PASSED

All 6 modified files exist on disk; both task commits (`1a47f93`, `11a801f`) are in git history; the D11 grep ratchet returns 0 matches in `backend/`.
