---
phase: 10-safe-local-exec-gated-on-n3-4b
plan: 04
subsystem: testing
tags: [validators, exec, py_compile, pytest, ruff, capability-registry, sc-001, exec-02]

# Dependency graph
requires:
  - phase: 10-01
    provides: hardened argv exec_command + LocalExecutionPolicy exec_allow/caps + recorder
  - phase: 10-02
    provides: GRANT-PATH + D-01 GATES-REQUIRED compiler rules (file trust, exec needs security+approval)
  - phase: 10-03
    provides: §15 host seam binding runtime_env('local') exec workspace onto KernelServices.workspace
provides:
  - "code_compile / code_test / code_lint registered Validator capabilities reaching exec only via the runner/workspace handle"
  - "VALIDATOR-DENY: explicit refusal Issue + zero spawns + no escaping PermissionError when exec ungranted"
  - "sample_python_repo fixture (compile+test PASS target + seeded F401 lint error)"
  - "sample_exec_workflow exec-granting manifest proving EXEC-02 + SC-001 offline"
  - "capability registry 50->53 with the lockstep drift-guard bumped"
affects: [phase-10-05, phase-11-isolation, exec-validators, sc-001]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Validator reaches exec ONLY via target.runner.workspace.exec_command(argv) (repo_diff._workspace reach); never spawns directly, never imports app.*"
    - "exec_command returns stdout only (10-01 contract preserved) -> validators surface failures in stdout (py_compile-to-stdout driver; pytest summary; ruff stdout)"
    - "shared _exec_support helpers factor the workspace_of/exec_granted/target_py_files reach once across the three validators"

key-files:
  created:
    - backend/agents/capabilities/validators/code_compile.py
    - backend/agents/capabilities/validators/code_test.py
    - backend/agents/capabilities/validators/code_lint.py
    - backend/agents/capabilities/validators/_exec_support.py
    - backend/tests/agents/test_code_validators.py
    - backend/tests/agents/fixtures/sample_python_repo/
    - backend/tests/agents/fixtures/sample_exec_workflow/
  modified:
    - backend/agents/capabilities/registry.py
    - backend/tests/agents/test_registry_capabilities.py

key-decisions:
  - "exec_command's str/stdout contract (10-01) is kept byte-identical; validators surface failures in STDOUT (py_compile inline driver prints COMPILE_FAIL/COMPILE_OK; pytest -q summary; ruff concise findings) rather than reading the discarded stderr/exit-code (Rule 3 blocking-issue fix, no port change)"
  - "code_compile drives python3 (not python) — python is not on the scrubbed PATH; both are allow-listed so this stays within the N3 profile"
  - "a shared validators/_exec_support.py factors workspace_of/exec_granted/target_py_files once (DRY) instead of copy-pasting the reach into three files"

patterns-established:
  - "Code validator template: @register('validator', name, user_allowed=True) + Issue dataclass + _record via the handle + VALIDATOR-DENY refusal-before-spawn, modeled on spec_plan_coverage.py"

requirements-completed: [EXEC-02]

# Metrics
duration: 22min
completed: 2026-06-10
---

# Phase 10 Plan 04: Code Validators + EXEC-02 Proof Summary

**code_compile/code_test/code_lint registered Validators reaching exec only via the runner/workspace handle (py_compile/pytest/ruff), with VALIDATOR-DENY refusal-before-spawn and a sample exec-granting manifest proving EXEC-02 offline with zero engine edits.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-06-10
- **Completed:** 2026-06-10
- **Tasks:** 2 (one TDD validator task + one manifest-proof task)
- **Files modified:** 9 (4 created src, 1 shared helper, 1 test, 2 fixture dirs, 2 modified)

## Accomplishments
- Three kernel-side registered `Validator` capabilities (`code_compile` via `py_compile`, `code_test` via `pytest -p no:cacheprovider`, `code_lint` via `ruff check`) that reach exec ONLY through `target.runner.workspace.exec_command(argv)` — never spawning directly, never importing `app.*` (import-linter 4 kept / 0 broken; grep for `subprocess.run(`/`Popen(` over the three files = 0).
- VALIDATOR-DENY (T-10-04-02): under an exec-denied policy OR `ws is None`, each validator returns >=1 explicit refusal `Issue` naming the missing exec grant, spawns ZERO processes (a `subprocess.run` tripwire fails the test if reached), and lets no `PermissionError` escape.
- `sample_python_repo` fixture (a compilable+testable `calc.py` + passing `test_calc.py` + a seeded F401 `lint_seed.py`); compile+test PASS offline, lint flags the seeded error with a `map_severity` label.
- `sample_exec_workflow` exec-granting manifest (file trust, `tools.exec: true`, `gates: [security, approval]`, `validators: [code_compile, code_test, code_lint]`) compiles to `Step.tools.exec is True` with both required gates — proving GRANT-PATH + D-01 accept the legitimate authoring path.
- EXEC-02 proven offline with ZERO edits under `backend/agents/execution_engine/` (SC-001 discipline held — the git diff over the engine dir is clean for this plan).
- Capability registry `_KNOWN` 50->53; the lockstep drift-guard bumped to 53.

## Task Commits

1. **Task 1: code validators + VALIDATOR-DENY + registry bump + fixture repo** - `9028e30` (feat)
2. **Task 2: exec-granting sample manifest proving EXEC-02 offline** - `0ba4486` (test)

_The validator+manifest tests live in one test file; Task 1 committed the validators/fixture/registry + the validator/deny/registry tests, Task 2 committed the exec-granting manifest fixture the manifest test cases reference._

## Files Created/Modified
- `backend/agents/capabilities/validators/code_compile.py` - `py_compile` validator via the handle (inline stdout-printing compile driver).
- `backend/agents/capabilities/validators/code_test.py` - `pytest -p no:cacheprovider` validator via the handle (parses the pytest summary from stdout).
- `backend/agents/capabilities/validators/code_lint.py` - `ruff check` validator via the handle (parses concise findings, P0 syntax / P2 lint via `map_severity`).
- `backend/agents/capabilities/validators/_exec_support.py` - shared `workspace_of`/`exec_granted`/`target_py_files` helpers (the `repo_diff._workspace` reach factored once).
- `backend/agents/capabilities/registry.py` - `_KNOWN` 50->53 + the three modules added to `discover()`'s `_builtin_modules`.
- `backend/tests/agents/test_registry_capabilities.py` - `_EXPECTED_NAMES` + the count drift-guard bumped to 53.
- `backend/tests/agents/test_code_validators.py` - VALIDATORS + VALIDATOR-DENY + registry membership + EXEC-02/SC-001 proof.
- `backend/tests/agents/fixtures/sample_python_repo/` - compile+test fixture + seeded lint error.
- `backend/tests/agents/fixtures/sample_exec_workflow/` - exec-granting manifest + 2 AGENT.md.

## Decisions Made
- **exec_command's stdout/str contract kept byte-identical (10-01 parity).** `exec_command` returns only the child's stdout (stderr + exit code are audited, not returned). `py_compile -m` writes its SyntaxError to stderr, so `code_compile` drives an inline `python3 -c` compile driver that prints `COMPILE_OK`/`COMPILE_FAIL <file>` to STDOUT; `code_test` parses the pytest `-q` summary (which lands on stdout); `code_lint` parses ruff's concise findings (stdout). This keeps the validators reaching exec purely through the handle with NO port-signature change (no 10-01 re-baseline).
- **`python3` over `python`** in the compile driver — `python` is not on the scrubbed PATH; both are in the N3 allow-list, so this stays within the locked profile.
- **A shared `_exec_support.py`** factors the workspace reach once rather than copy-pasting it into three files (still kernel-pure: imports only `typing` + `pathlib`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] exec_command returns stdout only — validators could not detect failures via the discarded stderr/exit-code**
- **Found during:** Task 1 (writing the validators against the 10-01 `exec_command`)
- **Issue:** The hardened `exec_command` (10-01) returns ONLY `proc.stdout` (truncated); `proc.stderr` and `proc.returncode` are passed to the recorder but NOT returned. `py_compile -m` writes its SyntaxError to stderr and `ruff`/`pytest` signal failure via exit code — so a validator reaching exec through the handle would see an empty/ambiguous stdout and could not distinguish PASS from FAIL (would have silently passed — exactly the false-green VALIDATOR-DENY forbids). Changing `exec_command`'s return type to expose the exit code would break the 10-01 str contract pinned by `test_local_runtime.py` (and risk a characterization re-baseline).
- **Fix:** Designed each validator's argv so the verdict lands in STDOUT without touching the port: `code_compile` runs an inline `py_compile.compile(doraise=True)` driver that prints `COMPILE_OK`/`COMPILE_FAIL`; `code_test` parses pytest's `-q` short summary; `code_lint` parses ruff's `--output-format=concise` findings. No change to `exec_command` or its contract.
- **Files modified:** the three validator files (committed in Task 1).
- **Verification:** `test_code_validators.py` — compile/test PASS on the fixture, compile FAIL flags the seeded `broken.py` as P0, lint flags the seeded F401. `test_local_runtime.py` untouched; 10 characterization snapshots byte/event-identical.
- **Committed in:** `9028e30` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** The fix was essential for correctness (without it the validators would silently false-green) and kept the 10-01 exec_command contract byte-identical (no re-baseline). No scope creep — the validators still reach exec exclusively through the handle as the plan + threat model require.

## Issues Encountered
- `FileNotFoundError: 'python'` on the first run — `python` is not on the scrubbed PATH (only `python3`/`python3.11`). Switched the compile driver to `python3` (still allow-listed). Resolved in Task 1.

## User Setup Required
None - no external service configuration required (zero external packages; `py_compile` is stdlib, `pytest`/`ruff` already installed offline).

## Next Phase Readiness
- EXEC-02 closed: the three code validators land, refuse explicitly when ungranted, and prove compile+test PASS on the fixture via the exec-granted workspace with zero engine edits (SC-001).
- Plan 10-05 is the remaining plan of Phase 10.

## Threat Flags
None - the new surface (the three validators + two fixtures) is fully covered by the plan's threat register (T-10-04-01..SC); no new endpoint/auth/file/schema surface introduced.

## TDD Gate Compliance
This plan is `type: tdd`. The work was driven test-first against the plan's `<behavior>` block, but the validators + their tests were committed together in the Task-1 `feat` commit (the RED state was exercised locally during authoring, not landed as a separate `test(...)` commit). No separate `test(...)`-before-`feat(...)` gate commit exists for Task 1; the Task-2 manifest proof landed as a `test(...)` commit (`0ba4486`). Behavior + deny + registry + EXEC-02/SC-001 proofs all pass (90 tests green).

## Self-Check: PASSED

All created files verified on disk (7/7) and both task commits verified in git history (`9028e30`, `0ba4486`).

---
*Phase: 10-safe-local-exec-gated-on-n3-4b*
*Completed: 2026-06-10*
