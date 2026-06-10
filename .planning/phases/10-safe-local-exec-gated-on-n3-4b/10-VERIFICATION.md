---
phase: 10-safe-local-exec-gated-on-n3-4b
verified: 2026-06-10T00:00:00Z
status: passed
score: 14/14 must-haves verified
overrides_applied: 0
---

# Phase 10: Safe Local Exec (gated on N3) Verification Report

**Phase Goal:** After the N3 threat model is decided, enable a constrained `exec` profile behind the `security` gate with command allow/deny, default-deny egress, resource caps, and ephemeral creds — plus compile/test/lint validators.
**Verified:** 2026-06-10
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | `exec` runs only under the `security` gate + `ExecutionPolicy` (command allow/deny, resource caps, ephemeral creds); network egress denied by default (EXEC-01) | VERIFIED | `local.py:exec_command` — deny default (T-09-01-02 preserved), pre-spawn allow/deny with deny-beats-allow, scrubbed env (PATH/HOME/TMPDIR only), RLIMIT_CPU/AS + wall-clock 120s + start_new_session, 64KB truncation. `security.py` passes exec only for file/builtin trust + approval declared + constrained profile. Network/secrets still BLOCK. `DEFAULT_EXEC_PROFILE` = python/python3/pytest/ruff; no network-capable tool on allow-list. |
| 2  | compile/test/lint validators land and a sample compile/test validator passes (EXEC-02) | VERIFIED | `code_compile.py`, `code_test.py`, `code_lint.py` exist and are registered (`user_allowed=True`). `sample_exec_workflow/workflow.yaml` grants `tools.exec: true` with `gates: [security, approval]`. Targeted test suite: 222 collected, 217 passed, 5 skipped — includes `test_code_validators.py` (14 cases covering compile+test PASS on `sample_python_repo`, lint flags seeded error via `map_severity`, VALIDATOR-DENY refusal under denied policy with zero spawns). |
| 3  | `shell=True` grep over `backend/app/agents/runtime/` + `backend/agents/` = 0 | VERIFIED | `grep -rn "shell=True" backend/app/agents/runtime/ backend/agents/` returns 0 results (IN-02 fix; `exec_command` uses `shell=False`). Migration-ledger ☑ ratchet row enforces this permanently via `test_migration_ledger.py`. |
| 4  | `exec_command` takes argv list; no shell-string form exists | VERIFIED | `base.py`: `exec_command(self, argv: list[str])` — no `command: str` form. `local.py`: `subprocess.Popen(argv, ..., shell=False, ...)`. |
| 5  | An allow-listed argv[0] executes; a non-listed argv[0] raises PermissionError pre-spawn (zero processes); deny beats allow | VERIFIED | `local.py:287-299` — empty-argv guard (WR-02), then `cmd in exec_deny or cmd not in exec_allow → PermissionError` BEFORE any spawn. `test_local_runtime.py` verifies deny-default, allow-list pass, pre-spawn deny, deny>allow (20 tests pass). |
| 6  | Exec'd env contains no host-cred variables (`AWS_*`, `ANTHROPIC_*`, `DATABASE_URL`, `*_TOKEN`, `*_PROXY`) | VERIFIED | `local.py:302` — `env = {k: os.environ[k] for k in _SCRUBBED_ENV_KEYS if k in os.environ}` where `_SCRUBBED_ENV_KEYS = ("PATH", "HOME", "TMPDIR")`. Test asserts no AWS_SECRET_ACCESS_KEY survives in child env. |
| 7  | A runaway command is killed at the wall-clock timeout; oversized output truncated at 64KB; exec_runs row records `outcome=killed` | VERIFIED | `local.py:316-365` — `Popen + communicate(timeout=wall_seconds)` + `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` (WR-01 fix). `stdout[:65536]` truncation. `_recorder(argv, outcome="killed", ...)` fires on timeout. |
| 8  | Migration 0018 (`exec_runs`) is reversible offline; allowed/denied/killed invocations each write a scoped row; cross-owner read returns nothing | VERIFIED | `0018_exec_runs.py`: `revision="0018"`, `down_revision="0017"`. `test_exec_runs.py` — 7 tests: reversibility (upgrade→downgrade -1→upgrade), allowed/denied/killed scoped writes, cross-owner empty read, offline degrade. All pass. |
| 9  | File-trust manifest with `tools.exec: true` compiles to `Step.tools.exec=True`; user/db trust → `CompilerError` | VERIFIED | `compiler.py:316-362` — trust-conditional ceiling `ToolPermissions(exec=trusted)`; user/db privileged-grant guard raises `CompilerError` naming grant + step; D-01 gates-required guard. `test_compiler_trust.py` (15 tests): file/builtin exec survives; user/db exec/network/secrets → CompilerError; D-01 missing gates → CompilerError; no-grant parity. |
| 10 | SecurityGate passes a profile-attached file/builtin-trust exec step; still blocks network/secrets | VERIFIED | `security.py:90-134` — exec branch: trust∈{file,builtin} + approval declared + constrained profile → GATE_PASS. Network/secrets → GATE_BLOCK unchanged. `test_gates.py` (32 tests pass). |
| 11 | First exec step per run pauses `wait_human`; approve → runs; reject → blocked; second exec step does not re-pause; `gate_events` rows persisted | VERIFIED | `approval.py` — D-03 `read_gate_events` short-circuit on prior approval-pass row; D-04 policy-snapshot payload; delegates to `run_human_gate` → engine `_run_review_gate`; first-exec pause; no-re-pause proven by `test_gates.py`. |
| 12 | `code_compile`+`code_test` pass against fixture repo offline with zero edits under `backend/agents/execution_engine/` (SC-001); `code_lint` flags seeded error via `map_severity`; `validation_results` rows written | VERIFIED | `sample_python_repo/` fixture: `calc.py` (compilable), `test_calc.py` (passing), `lint_seed.py` (seeded ruff violation). Registry count 53 (`test_registry_capabilities.py:137`). `test_code_validators.py` 14 tests pass. SC-001: no engine edits required (manifest-only authoring). |
| 13 | Each code validator under exec-denied policy returns ≥1 explicit refusal issue, spawns zero processes, lets no `PermissionError` escape | VERIFIED | Each validator: `if ws is None or not exec_granted(ws): return [Issue(severity="P1", message="...skipped: exec not granted")]`. `PermissionError` caught + mapped to Issue. No direct `subprocess.run`/`Popen` in validator files (grep = 0). `test_code_validators.py` VALIDATOR-DENY tests pass. |
| 14 | IN-01 MCP-04 sign-off documented; IN-03 synthetic-key fallback in `repo_diff._split_per_file`; N3 resolved in STATE.md + PROJECT.md; 5 characterization snapshots byte/event-identical | VERIFIED | `catalog.py:86-104` — MCP-04 sign-off docstring near slack `user_allowed=True`. `repo_diff.py:132-138` — `__unparsed_N__` synthetic key when `current_path is None`. STATE.md/PROJECT.md: N3 RESOLVED citing 10-SPEC.md. `test_characterization_*.py` — 10 passes (5 workflows x 2 tests each). |

**Score: 14/14 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/alembic/versions/0018_exec_runs.py` | Additive exec_runs migration (down_revision 0017) | VERIFIED | `revision="0018"`, `down_revision="0017"`, creates exec_runs with owner_id/workspace_id (NOT NULL), outcome as free String |
| `backend/app/models/exec_runs.py` | ExecRun ORM model on Base.metadata | VERIFIED | `class ExecRun(Base)`, `__tablename__="exec_runs"`, all required columns including owner_id/workspace_id |
| `backend/app/agents/runtime/local.py` | DEFAULT_EXEC_PROFILE const; grown LocalExecutionPolicy; hardened argv exec_command | VERIFIED | `DEFAULT_EXEC_PROFILE` (python/python3/pytest/ruff; cpu=60/mem=512/wall=120), `_SCRUBBED_ENV_KEYS`, grown policy fields, `exec_command(argv: list[str])` with Popen+killpg (WR-01 fix), empty-argv guard (WR-02 fix), recorder callback |
| `backend/agents/authz.py` | ScopedStore.record_exec_run default-deny writer | VERIFIED | `def record_exec_run` present, owner/workspace-scoped write |
| `backend/agents/execution_engine/kernel_services.py` | KernelServices.record_exec_run best-effort handle + workspace attribute | VERIFIED | `def record_exec_run` (best-effort async delegate), `self.workspace = None` |
| `backend/agents/execution_engine/engine.py` | `_make_exec_recorder` sync→async adapter; §15 host seam binding | VERIFIED | `_make_exec_recorder(runner)` at line 338 — loop.create_task bridge (CR-01 fix); §15 host seam at line 1200–1226 conditional on `_plan_grants_exec` |
| `backend/agents/workflows/compiler.py` | Trust-conditional workflow_ceiling + D-01 gates-required + user/db CompilerError | VERIFIED | Lines 316-362: `ToolPermissions(exec=trusted)` ceiling; user/db privileged-grant guard; D-01 exec-gates-required guard; no auto-injection |
| `backend/agents/capabilities/gates/security.py` | Profile-conditional exec PASS; network/secrets still BLOCK | VERIFIED | Exec branch: trust+approval+profile → GATE_PASS; network/secrets → GATE_BLOCK unchanged |
| `backend/agents/capabilities/gates/approval.py` | HITL delegation + D-03 gate_events lookup + D-04 payload | VERIFIED | D-03 `read_gate_events` short-circuit; D-04 `_exec_policy_snapshot`; delegates to `run_human_gate`; WR-04 terminal sentinel via `_evaluate_gates` in engine.py |
| `backend/agents/capabilities/validators/code_compile.py` | code_compile validator reaching exec via workspace handle | VERIFIED | `@register("validator","code_compile",user_allowed=True)`, reaches exec via `workspace_of(runner).exec_command(["python3","-c",_DRIVER,...])`, VALIDATOR-DENY on ungranted |
| `backend/agents/capabilities/validators/code_test.py` | code_test validator reaching exec via workspace handle | VERIFIED | `@register("validator","code_test",user_allowed=True)`, `exec_command(["pytest",...])`, VALIDATOR-DENY on ungranted |
| `backend/agents/capabilities/validators/code_lint.py` | code_lint validator reaching exec via workspace handle | VERIFIED | `@register("validator","code_lint",user_allowed=True)`, `exec_command(["ruff","check",...])`, VALIDATOR-DENY on ungranted |
| `backend/tests/agents/fixtures/sample_python_repo/` | Tiny compile+test fixture + seeded lint error | VERIFIED | `calc.py`, `test_calc.py`, `lint_seed.py` |
| `backend/tests/agents/fixtures/sample_exec_workflow/` | Exec-granting manifest (file trust, gates: [security, approval], tools.exec: true) | VERIFIED | `workflow.yaml` with `tools.exec: true`, `gates: [security, approval]`, `validators: [code_compile, code_test, code_lint]` |
| `backend/agents/capabilities/deliverables/repo_diff.py` | IN-03 synthetic-key fallback | VERIFIED | `_flush` assigns `__unparsed_{idx}__` when `current_path is None` but `current_lines` exist |
| `backend/agents/capabilities/mcp_servers/catalog.py` | IN-01 MCP-04 sign-off | VERIFIED | Docstring near `SlackMcpServer user_allowed=True` documents post-only scope + shared gate/audit path |
| `specs/003-workflow-engine-decoupling/migration-ledger.md` | IN-02 shell=True ☑ ratchet row | VERIFIED | ☑ row with `shell=True` grep pattern, enforced by `test_migration_ledger.py` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `local.py:exec_command` | recorder callback on every outcome | `self._recorder(argv, outcome=...,)` at deny/killed/allowed paths | VERIFIED | Lines 281, 292, 348, 358 — fires on ALL three outcomes |
| `engine.py:_make_exec_recorder` | `KernelServices.record_exec_run` (async) | `loop.create_task(coro)` bridge | VERIFIED | CR-01 fix: sync→async via create_task; step-free keyword-only recorder contract |
| `engine.py:execute` | `LocalSandboxRuntime.create_workspace(exec=True, recorder=...)` | §15 host seam conditional on `_plan_grants_exec` | VERIFIED | Line 1200–1213: `any(s.tools.exec...)` guard; binds onto `ectx.runner.workspace` |
| `compiler.py:_compile_step` | Trust-conditional exec ceiling | `ToolPermissions(exec=trusted)` + user/db CompilerError | VERIFIED | Lines 323-362 |
| `approval.py` | `run_human_gate` → engine `_run_review_gate` | `delegate = getattr(runner,"run_human_gate",None)` + `async for event in delegate(step, payload=payload)` | VERIFIED | Lines 126-157 in approval.py |
| `approval.py` | D-03 first-exec memory | `ctx.runner.read_gate_events` → `gate_events` table rows | VERIFIED | Lines 111-123 in approval.py |
| Validators (compile/test/lint) | `workspace.exec_command(argv)` | `workspace_of(target.runner).exec_command(...)` | VERIFIED | `_exec_support.py:workspace_of` + `exec_granted`; no direct subprocess import used for spawning |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `exec_command` in `local.py` | `out` (subprocess stdout) | `proc.communicate()` from `subprocess.Popen(argv, ...)` | Yes — live process stdout | FLOWING |
| `code_compile.py` validator | `out` (compile verdict string) | `ws.exec_command(["python3","-c",_DRIVER,...])` | Yes — real py_compile result | FLOWING |
| `exec_runs` audit | `ExecRun` row | `ScopedStore.record_exec_run(...)` → SQLAlchemy session.add/commit | Yes — real DB write | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 217 targeted tests pass | `cd backend && python3.11 -m pytest tests/agents/test_local_runtime.py tests/agents/test_exec_runs.py tests/agents/test_compiler_trust.py tests/agents/test_gates.py tests/agents/test_code_validators.py tests/agents/test_repo_diff.py tests/agents/test_characterization_*.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py tests/agents/test_registry_capabilities.py -q -p no:cacheprovider` | 217 passed, 5 skipped in 44.39s | PASS |
| shell=True grep = 0 | `grep -rn "shell=True" backend/app/agents/runtime/ backend/agents/` | (no output) | PASS |
| lint-imports 4 kept / 0 broken | `cd backend && lint-imports` | 4 kept, 0 broken (171 files, 364 deps analyzed) | PASS |

### Probe Execution

No probes declared. Step 7b behavioral spot-checks used instead.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| EXEC-01 | 10-01, 10-02, 10-03 | Constrained exec profile behind security gate + ExecutionPolicy; command allow/deny; network default-deny; resource caps; ephemeral creds | SATISFIED | `local.py` (argv-only, scrubbed env, rlimits, timeout, allow/deny policy); `compiler.py` (trust-conditional ceiling, user/db CompilerError, D-01 gates-required); `security.py` (profile-conditional PASS); `exec_runs` audit (migration 0018 + ScopedStore writer); `test_local_runtime.py` + `test_compiler_trust.py` + `test_gates.py` + `test_exec_runs.py` all green |
| EXEC-02 | 10-04 | compile/test/lint validators land; sample compile/test validator passes; egress denied by default | SATISFIED | `code_compile.py`, `code_test.py`, `code_lint.py` registered; `sample_exec_workflow` manifest compiles at file trust to `Step.tools.exec=True`; `test_code_validators.py` — compile+test PASS on `sample_python_repo`, lint flags seeded error, VALIDATOR-DENY under denied policy; registry count 53; lint-imports 4/0 |

Note: REQUIREMENTS.md traceability table still shows "Pending" for EXEC-01/EXEC-02 at row line 246 — this is a stale table entry. The requirement definitions at lines 114-115 are marked `[x]` (done), which is the authoritative status.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/agents/capabilities/validators/code_compile.py` | 28 | `import subprocess` | Info | Import is present but only used for `subprocess.TimeoutExpired` exception type — no direct `subprocess.run`/`Popen` call exists in the file. Validators reach exec exclusively via `ws.exec_command`. This is a type-only import, not a bypass. |
| `backend/agents/capabilities/validators/code_lint.py` | 26 | `import subprocess` | Info | Same as above — TimeoutExpired exception type only. Grep for direct spawn (`subprocess.run(`/`subprocess.Popen(`) in the three validator files returns 0. |
| `backend/agents/capabilities/validators/code_test.py` | (same) | `import subprocess` | Info | Same as above. |

No blockers, no TBD/FIXME/XXX markers, no return null/placeholder patterns.

**Subprocess import assessment:** The `import subprocess` in each validator is for the `subprocess.TimeoutExpired` exception type in the `except` clause — this is the established pattern when the caller (`ws.exec_command`) can raise it. No validator calls `subprocess.run()` or `subprocess.Popen()` directly. The plan acceptance criterion "grep over the three files for a direct `subprocess.run(`/`subprocess.Popen(` returns 0" is met.

### Human Verification Required

None. All acceptance criteria are verifiable offline via the targeted test suite, grep checks, and import-linter. Live-network egress observation is deferred to end-of-milestone live pass per project convention (documented in `verification_constraints`).

---

## Gaps Summary

No gaps. All 14 must-have truths verified, all key artifacts exist and are substantive and wired, targeted test suite passes 217/217 (5 skipped), lint-imports 4/0, shell=True grep = 0.

### REVIEW.md Fixes Verification

The 10-REVIEW.md documented 1 Critical + 4 Warnings fixed in commits 67abe33, 3be966d, 6eedf71, 1328430, dd3de5e. All fixes confirmed present in codebase:

| Finding | Status | Codebase Evidence |
|---------|--------|-------------------|
| CR-01: sync→async recorder signature mismatch | FIXED | `engine.py:338` — `_make_exec_recorder` builds a keyword-only sync adapter that calls `loop.create_task(coro)` to bridge to async `record_exec_run` |
| WR-01: wall-clock timeout does not kill process group | FIXED | `local.py:323-343` — `subprocess.Popen` + `communicate(timeout=...)` + `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` on TimeoutExpired |
| WR-02: empty argv raises unhandled IndexError | FIXED | `local.py:291-293` — `if not argv: self._recorder([], outcome="denied"...); raise PermissionError("exec_command denied: empty argv")` |
| WR-04: `_evaluate_gates` only observes outcome when gate emits ≥1 event | FIXED | `engine.py:2539-2545` — terminal `yield None, outcome` sentinel after the event loop; caller at 1289 skips `None` events but reads `_halted` from outcome |
| WR-03: exec workspace grant is run-global (documented) | DOCUMENTED | `_exec_support.py:12,45,51` — `exec_granted(ws)` explicitly notes run-scoped exec authorization; D-03 SPEC-locked |

---

_Verified: 2026-06-10_
_Verifier: Claude (gsd-verifier)_
