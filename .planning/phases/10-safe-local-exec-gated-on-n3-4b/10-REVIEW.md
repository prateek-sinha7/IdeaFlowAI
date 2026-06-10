---
status: fixed
phase: 10
depth: standard
reviewed: 2026-06-10
fixed: 2026-06-10
files_reviewed: 28
findings:
  critical: 1
  warning: 4
  info: 2
  total: 7
resolved:
  fixed: 5
  accepted: 2
---

## Fix Resolution (2026-06-10)

All Critical + Warning findings fixed in atomic commits; Info findings accepted as-is (consistent with existing patterns / acknowledged defense-in-depth).

| Finding | Resolution | Commit |
|---------|-----------|--------|
| CR-01 | Fixed — `_make_exec_recorder` sync→async adapter at host seam; single keyword-only recorder contract; regression test drives the REAL adapter through allowed/denied/killed | `67abe33` |
| WR-01 | Fixed — Popen + communicate; `os.killpg` on timeout; forking-grandchild group-kill test | `3be966d` |
| WR-02 | Fixed — empty-argv guard records denial + raises PermissionError | `6eedf71` |
| WR-04 | Fixed — terminal `(None, outcome)` sentinel so a zero-event block still halts; emitted event stream unchanged | `1328430` |
| WR-03 | Documented — run-scoped exec authorization made explicit at host seam + `exec_granted` (D-03 SPEC-locked, by design) | `dd3de5e` |
| IN-01 | Accepted — import-only registration matches existing audit-model pattern | — |
| IN-02 | Accepted — compiler is the enforcement point; runtime echo acknowledged as intentional | — |

Post-fix verification: targeted+parity suite 217 passed / 5 skipped; characterization byte/event-identical (`SNAPSHOT_UPDATE` unset); lint-imports 4 kept / 0 broken.

# Phase 10: Code Review Report — Safe Local Exec (gated on N3)

**Depth:** standard
**Files reviewed:** 28 (authz, runtime port + local impl, gates, registry, compiler, plan, kernel_services, engine host-seam, repo_diff, mcp catalog, exec_runs model + migration, and the Phase-10 test suite)
**Status:** issues_found
**Findings:** Critical 1 · Warning 4 · Info 2

## Summary

The three-tier exec model (compiler ceiling → gates → workspace policy) is largely sound: the compiler hard-rejects exec/network/secrets grants from `user`/`db` trust, requires `security`+`approval` gates on any exec-granting step, the workspace enforces deny-default + allow-list (deny-beats-allow) + scrubbed env + rlimits + 64KB truncation, and the engine provisions the exec workspace *only* when the compiled plan actually grants exec (parity-preserving dormancy for non-exec runs).

However, the **core audit guarantee — "the recorder must fire on every exec outcome" (T-10-01-07) — is broken in the live wiring.** The workspace recorder is invoked with a calling convention that does not match `KernelServices.record_exec_run`, and that method is an unawaited coroutine called from synchronous code. The entire Phase-10 test suite hides this because every test injects a synchronous, differently-shaped lambda recorder instead of the real bound method the engine wires. This is a blocker. Four warnings concern containment/robustness gaps, and two info items note minor inconsistencies.

## Critical Issues

### CR-01: Live exec-audit recorder is never invoked — signature + sync/async mismatch breaks audit AND the deny contract

**File:** `backend/app/agents/runtime/local.py:268,277,311,321` (recorder call sites) ↔ `backend/agents/execution_engine/engine.py:1128` (wiring) ↔ `backend/agents/execution_engine/kernel_services.py:358` (`record_exec_run`)

**Issue:**
The engine host-seam wires the workspace recorder directly to the bound async method:

    ectx.runner.workspace = _runtime_impl.create_workspace(
        ..., exec=True, recorder=ectx.runner.record_exec_run,   # engine.py:1128
    )

`KernelServices.record_exec_run` has signature `async def record_exec_run(self, step, argv, outcome, *, exit_code=None, ...)`.

But `LocalWorkspace.exec_command` calls the recorder with a *different* convention — positional `argv` only, no `step`, `outcome` as a keyword:

    self._recorder(argv, outcome="denied", exit_code=None)            # local.py:268/277
    self._recorder(argv, outcome="killed", exit_code=None, ...)       # local.py:311
    self._recorder(argv, outcome="allowed", exit_code=..., output_digest=...)  # local.py:321

Two independent defects result:
1. **Signature mismatch (raises `TypeError`):** the single positional `argv` binds to the `step` parameter, leaving the required `argv` parameter unfilled → `TypeError: missing required positional argument 'argv'` at call time. The workspace never passes a `step` at all (it has no concept of the step id), so the method's required `step` can never be satisfied through this seam.
2. **Sync→async mismatch (never awaited):** even with a matching signature, `record_exec_run` is a coroutine called from the synchronous `exec_command`; the returned coroutine is never awaited, so `await store.record_exec_run(...)` never executes — no `exec_runs` row is ever written.

Consequences in the live (non-test) path:
- **No exec outcome is ever audited** — directly violating EXEC-01 / T-10-01-07 ("bypass-proof audit on every allowed/denied/killed outcome").
- **The deny path raises `TypeError` instead of `PermissionError`** (the recorder call at `local.py:268/277` precedes the intended `raise PermissionError`). The validators' `VALIDATOR-DENY` safety net catches only `PermissionError`/`TimeoutExpired` (`code_compile.py:99`, `code_lint.py:84`, `code_test.py:75`), so a denied exec leaks a `TypeError` up out of the validator/gate path.
- **The allowed path also raises `TypeError`** after the child runs, breaking every code validator at runtime.

Why tests miss it: `test_local_runtime.py:154`, `test_code_validators.py:144`, and `test_exec_runs.py` all set `ws._recorder = lambda argv, **kw: ...` (a sync function matching the `_noop_recorder(argv, **kwargs)` shape) or call `record_exec_run` directly with the correct `(step, argv, outcome)` arguments. No test exercises `recorder=ectx.runner.record_exec_run` against `exec_command`, so the contract gap between the two conventions is never exercised.

**Fix:** Make the recorder contract single and explicit, and bridge sync→async. The workspace must pass a step-free keyword-only contract `recorder(argv, *, outcome, exit_code=None, duration_ms=None, policy_snapshot=None, output_digest=None)`, and the engine must pass a synchronous adapter that captures the step id and schedules the async write (`asyncio.ensure_future(ectx.runner.record_exec_run(step_id, list(argv), outcome, ...))`). Update `_noop_recorder` + all `self._recorder(...)` call sites to the same keyword-only contract. Add a test that wires the *real* engine recorder path (an async-bridging adapter) through `exec_command` and asserts an `exec_runs` row is written for allowed/denied/killed — not a hand-rolled sync lambda.

## Warnings

### WR-01: Wall-clock timeout does not kill the child's process group — forking runaway escapes containment

**File:** `backend/app/agents/runtime/local.py:299-317`

**Issue:** `exec_command` runs the child with `start_new_session=True` and the docstring claims the session makes "a forking runaway killable as a group" (lines 256-258, 308). But on `subprocess.TimeoutExpired`, `subprocess.run` only sends `SIGKILL` to the **direct child** (`proc.kill()`), not to the new session/process group. No `os.killpg` is ever called. A child that forks grandchildren (e.g. pytest spawning workers) leaves orphaned descendants running past the wall-clock cap — defeating the documented runaway containment.

**Fix:** Use `subprocess.Popen` + `communicate(timeout=...)` (so the pid is retained on timeout), and on `TimeoutExpired` explicitly `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` (tolerating `ProcessLookupError`/`PermissionError`) before recording `outcome="killed"` and re-raising.

### WR-02: Empty `argv` raises an unhandled, unaudited `IndexError` past the deny-default

**File:** `backend/app/agents/runtime/local.py:275`

**Issue:** After the deny-default check, `cmd = argv[0]` dereferences `argv[0]` with no length guard. An empty `argv` on an exec-granted workspace raises `IndexError` — not a clean `PermissionError`, and with **no audit record** (the recorder calls only fire in the deny/allow/kill branches, all of which run after `argv[0]`). This is an unaudited, uncaught failure mode at the single enforcement point.

**Fix:** Validate before indexing and record a denial:

    if not argv:
        self._recorder([], outcome="denied", exit_code=None)
        raise PermissionError("exec_command denied: empty argv")

### WR-03: Exec workspace grant is run-global — ungated steps' exec validators reach exec without their own security/approval gates

**File:** `backend/agents/execution_engine/engine.py:1115-1129`, `backend/agents/capabilities/validators/_exec_support.py:45-56`

**Issue:** The exec workspace is provisioned once per run and bound to the shared `KernelServices.workspace` whenever *any* step grants exec. All validators across all steps reach the same `target.runner.workspace`, and `exec_granted(ws)` checks only `ws.policy.allows("exec")` (run-global), not per-step authorization. So a step that declares `validators: [code_compile]` but grants **no** `tools.exec` and declares **no** `security`/`approval` gates will still execute code via the shared, exec-granted workspace. Bounded by the engineer-trust requirement (a user/db manifest can never provision the exec workspace) and by the run-level approval model (D-03), so this is not a default-deny break — but the "approval gate before exec" guarantee is per-run, not per-step. Note: D-03's SPEC-locked first-exec memory ("subsequent exec steps in the same run don't re-prompt") makes run-scoped approval partially by-design; the gap is that it should be explicit.

**Fix:** Gate exec at the validator/exec point on the *step's* effective permission, or at minimum document explicitly that exec authorization is run-scoped (one approval opens exec for the whole run) so reviewers don't assume per-step enforcement.

### WR-04: `_evaluate_gates` only observes a gate outcome when the gate emits ≥1 event — a block with empty `events` would silently not halt

**File:** `backend/agents/execution_engine/engine.py:2433-2435` ↔ caller `engine.py:1201-1210`

**Issue:** `_evaluate_gates` yields `(event, outcome)` **only inside** the `for event in result.events` loop. A `GateOutcome` with `outcome="block"`/`"wait_human"` but an empty `events` list yields nothing, so the caller's `_halted` flag is never set and the step proceeds as if the gate passed. Today every blocking gate path happens to emit an event, so this is latent — but it is a fragile coupling between "did the gate halt" and "did the gate emit a UI event." A future gate (or a refactor that drops an event) would convert a block into a silent pass at a security boundary.

**Fix:** Yield the outcome regardless of events (e.g. a terminal `(None, outcome)` tuple after the event loop, with the caller skipping `None` events), or restructure so the halt decision reads `result.outcome` directly rather than depending on event emission.

## Info

### IN-01: `ExecRun` is not exported in `app/models/__init__.py.__all__`

**File:** `backend/app/models/__init__.py:31,56-92`

**Issue:** `ExecRun` is imported (line 31, for `Base.metadata` registration) but omitted from `__all__`. This matches the existing pattern for the other Phase-8/9 audit models (`GateEvent`, `HookRun`, `ValidationResult`, etc. are also import-only), so it is consistent — flagging for awareness only.

### IN-02: Security gate's trust check (condition a) is a runtime no-op

**File:** `backend/agents/capabilities/gates/security.py:94-98`

**Issue:** `trust = getattr(step, "trust", "file") or "file"` always resolves to `"file"` because the compiled `Step` dataclass (`plan.py:311-339`) carries no `trust` attribute. So condition (a) — "exec requires engineer trust" — always passes at runtime; the real enforcement is the compiler's `_TRUSTED_SOURCES` check. Intentional defense-in-depth per the docstring, but as written it cannot ever fire. Consider propagating manifest trust onto the compiled `Step`, or documenting that the runtime gate intentionally does not re-verify trust.
