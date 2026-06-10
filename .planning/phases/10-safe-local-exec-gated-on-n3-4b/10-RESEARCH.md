# Phase 10: Safe Local Exec (gated on N3) [4B] - Research

**Researched:** 2026-06-10
**Domain:** Hardened local subprocess execution behind a multi-layer capability gate (brownfield Python refactor)
**Confidence:** HIGH

## Summary

Phase 10 is a brownfield, parity-gated extension of an existing, well-mapped codebase. The SPEC (`10-SPEC.md`, ambiguity 0.14) and CONTEXT (`10-CONTEXT.md`, D-01..D-04 + four Claude's-discretion locks) already resolved the N3 threat model and every meaningful HOW gray area. This research is therefore **verification-first**: I read every canonical code site the CONTEXT named and confirmed the claims, rather than exploring alternatives that are already locked out of scope.

The work flips code execution from four independent OFF layers (verified in code) to a constrained, audited, engineer-only exec profile. Every layer the SPEC describes was confirmed present and exactly as described: the compiler's `workflow_ceiling = ToolPermissions()` collapse (`compiler.py:312`), the unconditional `SecurityGate` block, the hardcoded `LocalExecutionPolicy(exec=False, ...)` in `create_workspace` (`local.py:231`), and the `subprocess.run(command, shell=True)` IN-02 surface in `exec_command` (`local.py:190`). The HITL machinery the approval gate must delegate to (`_run_review_gate` + `KernelServices.run_human_gate` + `ArtifactStore.set_review_response`) is present, proven by the `human` gate (`gates/human.py`), and directly answers the D-02 researcher directive.

**One discovery materially shapes the plan:** the `RuntimeEnvironment` (runtime_env) workspace-provisioning seam is **registered but NOT wired into the live engine run path**. `engine.execute()` only calls `scoped_store.create_workspace()` (the DB-row helper); it never calls `LocalSandboxRuntime.create_workspace()`, and `KernelServices` has no `workspace` attribute. Today, `LocalWorkspace` is reached only in tests (passed *as* the runner, per `repo_diff.py:_workspace`). Phase 10 must therefore *wire the runtime workspace into the run path* (the §15 host seam) — this is more than "stop ignoring the exec kwarg"; it is the first live binding of the runtime_env workspace onto `ctx.runner`.

**Primary recommendation:** Implement three independent, separately-testable enforcement layers (compiler trust-conditional ceiling → security+approval gate → workspace `ExecutionPolicy`), wire `LocalSandboxRuntime.create_workspace` into the engine run-entry seam behind a compiled-plan exec-grant check, copy the `human`-gate HITL delegation pattern verbatim for the approval gate, model the three validators on `spec_plan_coverage.py`, and mirror `record_hook_run`/0017 exactly for the `exec_runs` audit + 0018 migration. Use Python stdlib only (`subprocess` argv-list, `resource.setrlimit` via `preexec_fn`, wall-clock via `subprocess.run(timeout=...)`); no new packages.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**From SPEC.md (the N3 decision record — 9 locked requirements):** hardened subprocess (argv-only/no-shell), policy+allow-list egress denial, Python toolchain allow-list (`python`/`python3`/`pytest`/`ruff`), scrubbed-env creds posture, security+approval gates, trust-conditional compiler ceiling, cap defaults `cpu_seconds=60` / `mem_mb=512` / wall-clock `120s` / output `64KB`/stream, **deny beats allow**.

**D-01: Acquisition = manifest-declared + compiler-enforced.** An exec-granting step MUST declare `gates: [security, approval]` in its manifest; the compiler raises `CompilerError` when a step grants `tools.exec` without BOTH gates declared. The SecurityGate additionally double-checks the approval gate is present in the step's gate list (cheap defense in depth, no kernel edit). *Rejected:* compiler auto-injection; kernel runtime check.

**D-02: Pause/resume = delegate to the existing review-gate HITL machinery** (the `human` gate precedent, `gates/human.py`): the `approval` gate's `evaluate()` routes through a `ctx.runner` handle delegate to the engine's `_run_review_gate`-style durable pause (checkpointer-backed, WS-driven), resolving approve→`pass` / reject→`block` **inline within the same run** — the step executes immediately on approval. ONE HITL mechanism. The current stub behavior (bare `wait_human` → engine halts/skips the step) is replaced for the exec path. *Rejected:* keep halt + run-level resume; pre-run approval.

**D-03: First-exec memory = durable `gate_events` lookup.** The approval gate (via the runner handle) queries the run's `gate_events` for an existing approval-pass row → silently `pass`; else pause. Durable across restarts, no new state field, no migration. *Rejected:* `ectx` flag; flag+backstop hybrid.

**D-04: Approval payload = exec policy snapshot.** The pause payload carries: step/agent id, the exec allow-list, resource caps, scrubbed-env note, egress-denied status. Rides the existing `review_gate_*`/`gate_*` event shapes. *Rejected:* generic "step X requests exec"; full command preview (argv constructed dynamically — not knowable at the gate; the allow-list IS the honest bound).

### Claude's Discretion

- **Exec profile home + provisioning:** profile values (allow-list, caps) live as **module-level constants in the runtime impl** (`app/agents/runtime/local.py` — e.g. `DEFAULT_EXEC_PROFILE`), optionally `settings`-overridable; NEVER manifest-tunable. Provisioning: the run-entry host seam (§15 RepoSpec-injection precedent) provisions the workspace with `exec=True` **iff the compiled plan contains an exec-granted step**. The plan.py `ExecutionPolicy.check` forward surface should either become the live check or be deleted (no dual policy surfaces — INV-12; planner decides after reading both).
- **Validator placement + exec access:** `code_compile`/`code_test`/`code_lint` are **kernel-side** (`agents/capabilities/validators/`), pure-stdlib, reach exec **only via the runner/workspace handle**; never import `app.*`; never spawn directly.
- **`exec_runs` audit seam:** the audit write happens **at the enforcement point** — `LocalWorkspace.exec_command` records every invocation via a **recorder callback injected at `create_workspace`** (workspace stays persistence-import-free; recorder closes over the ScopedStore writer). Bypass-proof. A `KernelServices.record_exec_run` method backs the callback (the `record_hook_run` precedent).
- Registry count goes 50→53 with the lockstep drift-guard updated; whether the SecurityGate's profile check reads the workspace policy or the compiled step is planner's call.
- Exact `exec_runs` column types/digest format; 0018 migration follows the 0017 recipe.
- Plan count/split (ROADMAP sketches 10-01 + 10-02; planner may keep 2 or split finer) — sequential execution (worktrees broken in this repo).

### Deferred Ideas (OUT OF SCOPE)

- `network_allow` implementation + `secrets` enablement (fields exist; gate keeps blocking).
- OS-level egress enforcement (netns/containers) — v2 ECS/container runtime behind the unchanged port; v1 residual documented + accepted.
- Ephemeral cred-vendor seam — revisit with N4 push flows.
- Non-Python toolchains (node/npm) — allow-list is data; extend when egress can handle installs.
- PR/commit push (N4) · fan-out (Phase 11) · wave scheduler + step-granular resume (Phase 12).
- Frontend approval panel polish — rides existing gate/review event shapes; dedicated UI follows P11/P12.
- Windows support — POSIX rlimits only.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | `exec` runs only under the `security` gate + `ExecutionPolicy` (command allow/deny, resource caps, ephemeral creds); network egress denied by default | Maps to SPEC reqs EXEC-PROFILE (subprocess hardening), EXEC-POLICY (allow/deny+caps live), EGRESS-DENY, GRANT-PATH (compile ceiling), GATES (security+approval), AUDIT (`exec_runs`). Verified sites: `local.py` (`LocalExecutionPolicy`/`exec_command`/`create_workspace`), `security.py`, `approval.py`, `compiler.py:312`, `plan.py` (`ExecutionPolicy.check`). Subprocess hardening pattern in §Code Examples; gate wiring in §Architecture Patterns. |
| EXEC-02 | compile/test/lint validators land and a sample compile/test validator passes | Maps to SPEC reqs VALIDATORS + VALIDATOR-DENY. Pattern: `spec_plan_coverage.py` (kernel-side `Validator`, single `map_severity`, `record_validation_result` via handle). Sample-fixture precedent: `tests/agents/fixtures/sample_brownfield/`. Tooling verified available offline: `ruff 0.8.4`, `pytest 8.3.4`, `py_compile`. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hardened subprocess spawn (argv/rlimits/timeout/scrub) | Runtime impl (`app/agents/runtime/local.py`, app-side) | — | Owns the disk root + the only legal `subprocess` surface; `app.*` reach (RunSandbox/settings) is the documented reason it lives app-side, not in the kernel |
| `ExecutionPolicy` allow/deny + caps + pre-spawn check | Runtime impl (`local.py`) | Runtime port (`agents/runtime/base.py`) | Policy is host/runtime-owned (INV-5: never manifest-tunable); the port carries the structural contract |
| Trust-conditional grant ceiling | Compiler (`agents/workflows/compiler.py`) | plan.py `ToolPermissions`/`intersect_permissions` | Compile-time is where trust (file/builtin vs user/db) is known; INV-5 keeps it pure data |
| Security gate (profile-conditional pass) + approval double-check | Capability gate (`agents/capabilities/gates/security.py`) | — | Gates evaluate the step + ctx at the step boundary; engineer-only (`user_allowed=False`) |
| First-exec approval pause/resume | Capability gate (`gates/approval.py`) delegating to engine HITL | Engine `_run_review_gate` via `KernelServices.run_human_gate` | ONE HITL mechanism (D-02); the gate stays kernel-pure, the durable pause lives in the engine + checkpointer |
| Workspace provisioning (exec-on iff plan grants) | Engine run-entry host seam (`engine.execute`) | Runtime_env `create_workspace` | The §15 host-injection seam binds per-run runtime objects; the runtime_env is the ECS-swap seam |
| `exec_runs` audit write | Workspace enforcement point (recorder callback) | `KernelServices.record_exec_run` → `ScopedStore` | Bypass-proof: any caller reaching `exec_command` is audited; scoped writes stay persistence-import-free in the workspace |
| `code_compile`/`code_test`/`code_lint` validators | Capability validators (kernel-side) | reach exec via `target.runner`/workspace handle | Pure-stdlib argv construction + output parsing; import-linter keeps them off `app.*` |

## Standard Stack

### Core

No new third-party packages. Phase 10 is **pure Python stdlib + existing tooling already resolvable offline**.

| Library / Module | Version | Purpose | Why Standard |
|------------------|---------|---------|--------------|
| `subprocess` (stdlib) | py3.11 | argv-list, no-shell spawn with `timeout`, `env`, `cwd`, captured/truncated output | The only correct way to spawn without a shell; `shell=False` (default when argv is a list) eliminates the IN-02 injection surface `[VERIFIED: backend/agents — git already uses argv lists]` |
| `resource` (stdlib, POSIX) | py3.11 | `setrlimit(RLIMIT_CPU, ...)` and `setrlimit(RLIMIT_AS, ...)` applied in a `preexec_fn` in the child before exec | POSIX rlimits are the standard CPU/mem cap; `RLIMIT_CPU` portable, `RLIMIT_AS` hard on linux / best-effort on darwin `[VERIFIED: python3.11 -c "import resource; RLIMIT_CPU=0, RLIMIT_AS=5"]` |
| `os` (stdlib) | py3.11 | constructed minimal env dict (`PATH`/`HOME`/`TMPDIR` only), `os.killpg`/process-group kill on timeout | Scrubbed-env construction is a dict literal, not inheritance; the v1 "ephemeral creds" posture `[CITED: 10-SPEC.md EXEC-PROFILE]` |
| `ruff` | 0.8.4 | `code_lint` validator subprocess target (`ruff check`) | Already installed at `/Users/1000060523/.local/bin/ruff` `[VERIFIED: ruff --version]` |
| `pytest` | 8.3.4 | `code_test` validator subprocess target | Already resolvable via `python3.11 -m pytest` `[VERIFIED: python3.11 -m pytest --version]` |
| `py_compile` (stdlib) | py3.11 | `code_compile` validator target (`python -m py_compile`) | Stdlib; no install `[VERIFIED: python3.11 -c "import py_compile"]` |

### Supporting (existing internal surfaces — reuse, do not rebuild)

| Surface | Location | Purpose | When to Use |
|---------|----------|---------|-------------|
| `ScopedStore` writer pattern | `backend/agents/authz.py:711` (`record_gate_event`), `:799` (`record_hook_run`) | owner/workspace-scoped INSERT with default-deny read filter | Copy verbatim for `record_exec_run` |
| `KernelServices.record_hook_run` | `kernel_services.py:324` | best-effort handle method delegating to ScopedStore (degrades to `None` offline) | Copy verbatim for `record_exec_run` |
| `KernelServices.run_human_gate` | `kernel_services.py:425` | delegates to `engine._run_review_gate`, yields review events | The exact delegation the approval gate copies (D-02) |
| `_run_review_gate` | `engine.py:2391` | durable HITL pause: arms event, emits `review_gate_ready`, `await event.wait()`, reads response, yields approve/reject | The durable machinery; resumes via the checkpointer + ArtifactStore |
| `ArtifactStore.set_review_response` | `agents/artifact_store/store.py:89` | unblocks the gate event with `approved`/`edited_content` | How offline tests script approve/reject (D-02 directive answer) |
| `map_severity` | `validators/severity.py:32` | single P0–P3 → CRITICAL/HIGH/MEDIUM/LOW source | The three code validators import this (never re-derive) |
| `Validator` port + `DeliverableContext` | `agents/capabilities/base.py`, `kernel_services.py:99` | the validator contract + `target.runner` handle reach | The three code validators implement this |
| `register("validator", name)` decorator | `agents/capabilities/registry.py:151` | self-registration into `_KNOWN`/`_IMPLS`/`_TRUST` | Each new validator decorates its class |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Verdict |
|------------|-----------|----------|---------|
| `subprocess.run(timeout=...)` wall-clock | `asyncio.wait_for` + `create_subprocess_exec` | async path adds complexity; the workspace surface is sync today (git uses `subprocess.run`) | Keep sync `subprocess.run` for parity with the existing git surface |
| `preexec_fn` rlimits | `resource.setrlimit` in parent then inherit | parent-set rlimits would cap the engine itself — wrong | `preexec_fn` (child-only) is correct; note: `preexec_fn` is not thread-safe but acceptable here (documented caveat) |
| Process-group kill (`start_new_session=True` + `killpg`) | bare `proc.kill()` | a runaway that forks children leaks them under bare kill | Use `start_new_session=True` + `os.killpg` so timeout kills the whole tree |

**Installation:** None. All dependencies are stdlib or already installed.

**Version verification:**
```bash
python3.11 --version          # Python 3.11.14  [VERIFIED]
ruff --version                # ruff 0.8.4       [VERIFIED]
python3.11 -m pytest --version # pytest 8.3.4    [VERIFIED]
```

## Package Legitimacy Audit

> Not applicable — Phase 10 installs **zero external packages**. All execution targets (`ruff`, `pytest`, `python -m py_compile`) and all hardening primitives (`subprocess`, `resource`, `os`) are stdlib or already-installed dev tools verified present offline. No registry resolution, no slopcheck, no postinstall surface.

## Architecture Patterns

### System Architecture Diagram

```
                          ┌─────────────────── COMPILE TIME ───────────────────┐
 manifest (tools.exec)───▶│ compiler._compile_step                              │
                          │   workflow_ceiling (trust-conditional)              │
                          │   ├─ file/builtin trust → exec grant SURVIVES       │
                          │   ├─ user/db trust + exec/network/secrets → ERROR   │
                          │   └─ exec granted but gates ≠ [security,approval]   │
                          │        → CompilerError (D-01)                       │
                          └────────────────────────┬────────────────────────────┘
                                                   │ CompiledWorkflow (Step.tools.exec=True)
                                                   ▼
            ┌──────────────────────────── RUN ENTRY (engine.execute) ───────────────────────────┐
            │  §15 host seam: IF compiled plan has an exec-granted step                          │
            │    runtime_env("local").create_workspace(exec=True, recorder=record_exec_run)      │
            │    → LocalWorkspace(policy=LocalExecutionPolicy(exec=True, allow/deny, caps))       │
            │    → bind workspace onto ctx.runner (KernelServices.workspace) ◀── NEW WIRING       │
            └────────────────────────────────────┬───────────────────────────────────────────────┘
                                                  │ per step (engine.py:1145 pre-step gate loop)
                                                  ▼
            ┌──────────────── PRE-STEP GATES (_evaluate_gates, phase="pre") ─────────────────────┐
            │  security gate: file/builtin trust + profile attached + exec → PASS                 │
            │                 network/secrets requested → BLOCK (unchanged)                       │
            │                 (double-check approval gate declared — D-01 defense-in-depth)       │
            │  approval gate: query gate_events for prior approval-pass row (D-03)                │
            │     ├─ found → PASS silently (no re-prompt)                                          │
            │     └─ none  → ctx.runner.run_human_gate(...) → _run_review_gate durable pause      │
            │                  emit review_gate_ready (payload = exec policy snapshot, D-04)       │
            │                  await event.wait() ── WS set_review_response ──▶ approve→PASS       │
            │                                                                    reject→BLOCK      │
            └────────────────────────────────────┬───────────────────────────────────────────────┘
                                                  │ gates pass → strategy runs
                                                  ▼
            ┌─────────── validators reach exec via target.runner (DeliverableContext) ───────────┐
            │  code_compile / code_test / code_lint                                               │
            │    └─ build argv list ─▶ workspace.exec_command(argv)                                │
            └────────────────────────────────────┬───────────────────────────────────────────────┘
                                                  ▼
            ┌──────────── ENFORCEMENT POINT: LocalWorkspace.exec_command(argv) ──────────────────┐
            │  1. policy.allows("exec") False → PermissionError (deny default unchanged)           │
            │  2. argv[0] in deny OR not in allow → PermissionError (PRE-spawn, deny>allow)         │
            │  3. spawn: shell=False, env=scrubbed{PATH,HOME,TMPDIR}, cwd=run root,                 │
            │            preexec_fn=setrlimit(CPU,AS), start_new_session=True, timeout=120s         │
            │  4. on timeout → killpg → outcome=killed ; output truncated 64KB/stream              │
            │  5. recorder(argv, outcome, exit_code, duration, policy_snapshot, digest) ◀─ALWAYS   │
            │       └─▶ KernelServices.record_exec_run → ScopedStore → exec_runs (0018)            │
            └─────────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure (files touched/added)

```
backend/
├── agents/
│   ├── workflows/compiler.py          # GROW: trust-conditional ceiling + D-01 gates-required check + user/db CompilerError
│   ├── workflows/plan.py              # DECIDE: make ExecutionPolicy.check live OR delete (INV-12); ToolPermissions unchanged
│   ├── runtime/base.py                # GROW: exec_command(command:str)→argv signature on the Workspace port
│   ├── capabilities/
│   │   ├── gates/security.py          # GROW: profile-conditional exec pass; network/secrets still block
│   │   ├── gates/approval.py          # GROW: HITL delegation + gate_events first-exec lookup (D-02/D-03/D-04)
│   │   ├── validators/code_compile.py # NEW
│   │   ├── validators/code_test.py    # NEW
│   │   ├── validators/code_lint.py    # NEW
│   │   ├── registry.py                # GROW: 50→53 (the @register fires; _KNOWN auto-grows)
│   │   ├── mcp_servers/catalog.py     # GROW: IN-01 slack_post sign-off doc near user_allowed=True
│   │   └── deliverables/repo_diff.py  # GROW: IN-03 synthetic-key fallback in _split_per_file
│   ├── execution_engine/
│   │   ├── engine.py                  # GROW: §15 host seam wires runtime_env workspace onto ctx.runner (exec-conditional)
│   │   └── kernel_services.py         # GROW: record_exec_run + workspace attr (+ approval delegate if needed)
│   └── authz.py                       # GROW: ScopedStore.record_exec_run (mirror record_hook_run)
├── app/
│   ├── agents/runtime/local.py        # GROW: DEFAULT_EXEC_PROFILE const; LocalExecutionPolicy fields; exec_command rewrite; create_workspace exec/recorder live
│   └── models/exec_runs.py            # NEW: ORM model (mirror hook_runs)
├── alembic/versions/0018_exec_runs.py # NEW: additive migration (mirror 0017)
└── tests/agents/
    ├── fixtures/sample_python_repo/   # NEW: tiny fixture repo for EXEC-02 (compile+test pass)
    └── fixtures/sample_brownfield/    # PRECEDENT for the exec-granting sample manifest
```

### Pattern 1: Hardened argv subprocess (the exec_command rewrite)
**What:** Replace `subprocess.run(command, shell=True)` with a hardened argv-list spawn.
**When to use:** The single `LocalWorkspace.exec_command` body.
```python
# Source: pattern derived from existing local.py git surface + 10-SPEC EXEC-PROFILE [CITED: 10-SPEC.md]
import os, resource, subprocess, time

_SCRUBBED_ENV_KEYS = ("PATH", "HOME", "TMPDIR")  # the v1 "ephemeral creds" posture

def exec_command(self, argv: list[str]) -> str:        # NOTE: argv, not str (port signature change)
    if not self.policy.allows("exec"):
        # deny default UNCHANGED (T-09-01-02 stays green)
        self._recorder(argv, outcome="denied", exit_code=None, ...)
        raise PermissionError("exec_command denied: ExecutionPolicy.exec is OFF")
    cmd = argv[0]
    if cmd in self.policy.exec_deny or cmd not in self.policy.exec_allow:   # deny BEATS allow
        self._recorder(argv, outcome="denied", exit_code=None, ...)        # audited, NO spawn
        raise PermissionError(f"exec_command denied: {cmd!r} not permitted by ExecutionPolicy")

    env = {k: os.environ[k] for k in _SCRUBBED_ENV_KEYS if k in os.environ}  # scrubbed, constructed

    def _limits() -> None:                              # child-only (preexec_fn)
        resource.setrlimit(resource.RLIMIT_CPU, (self.policy.cpu_seconds, self.policy.cpu_seconds))
        soft = self.policy.mem_mb * 1024 * 1024         # RLIMIT_AS: hard on linux, best-effort on darwin
        resource.setrlimit(resource.RLIMIT_AS, (soft, soft))

    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv, cwd=str(self._root), shell=False,     # shell=False is the IN-02 fix
            env=env, capture_output=True, text=True,
            timeout=self.policy.wall_seconds, preexec_fn=_limits,
            start_new_session=True,                     # so killpg can kill the tree on timeout
        )
        out = proc.stdout[:65536]                       # 64KB/stream truncation
        self._recorder(argv, outcome="allowed", exit_code=proc.returncode,
                       duration_ms=int((time.monotonic()-started)*1000), ...)
        return out
    except subprocess.TimeoutExpired as exc:
        self._recorder(argv, outcome="killed", exit_code=None, ...)
        raise   # the runaway was killed by the timeout
```
**Caveats verified:** `preexec_fn` runs in the child after fork, before exec (correct place for rlimits); `start_new_session=True` is required so a forking runaway is killed as a group. `RLIMIT_AS` best-effort on darwin (dev) — tests assert the *mechanism is applied*, the kill test uses the portable wall-clock timeout (per SPEC Constraints).

### Pattern 2: Approval gate delegating to the existing HITL machinery (D-02 — the directive)
**What:** The approval gate routes through `ctx.runner.run_human_gate` → `_run_review_gate` for a durable, checkpointer-backed pause, exactly as the `human` gate does — but with an approval-flavored payload and a first-exec `gate_events` short-circuit.
**When to use:** `gates/approval.py` `evaluate()`.
```python
# Source: copy of gates/human.py:51-81 delegation + D-03 gate_events lookup [VERIFIED: gates/human.py, kernel_services.py:425]
async def evaluate(self, step, ctx) -> GateOutcome:
    step_id = getattr(step, "agent_id", None) or "?"
    runner = getattr(ctx, "runner", None)

    # D-03: durable first-exec memory — prior approval-pass row → silent pass (no re-prompt)
    read = getattr(runner, "read_gate_events", None)
    if read is not None:
        rows = await read(getattr(runner, "run_id", "")) or []
        if any(getattr(r, "gate", None) == "approval"
               and getattr(r, "outcome", None) == GATE_PASS for r in rows):
            await write_gate_event(ctx, step_id, "approval", GATE_PASS, {"reason": "prior approval this run"})
            return GateOutcome(outcome=GATE_PASS)

    delegate = getattr(runner, "run_human_gate", None)
    if delegate is None:                                 # offline / no handle → pause (no auto-approve)
        await write_gate_event(ctx, step_id, "approval", GATE_WAIT_HUMAN, None)
        return GateOutcome(outcome=GATE_WAIT_HUMAN)

    payload = _exec_policy_snapshot(step, ctx)           # D-04: allow-list, caps, scrubbed-env note, egress-denied
    events, rejected = [], False
    async for event in delegate(step, output=payload):   # SAME delegate the human gate uses
        if event.get("type") == "_gate_rejected":
            rejected = True; continue
        events.append(event)                             # review_gate_ready / review_gate_approved flow through
    outcome = GATE_BLOCK if rejected else GATE_PASS
    await write_gate_event(ctx, step_id, "approval", outcome, None)
    return GateOutcome(outcome=outcome, events=events)
```
**Note for the planner:** `KernelServices.run_human_gate` currently has signature `(self, step, *, output: str = "")`. The approval payload (D-04) is a structured dict, not a string. The planner must decide: (a) parameterize `run_human_gate` to accept a structured payload/kind, or (b) add a sibling `run_approval_gate` method. **Recommendation: parameterize `run_human_gate` with an optional `payload`/`kind` arg** so there is ONE delegate method and ONE engine `_run_review_gate` call (D-02's "ONE HITL mechanism"). The `_run_review_gate` `output` field already flows into the `review_gate_ready` event `data.output` (engine.py:2433) — passing the snapshot dict there keeps the WS forward generic (D-04 "no frontend rebuild"). Keep the existing `human`-gate string call path byte-identical (parity) by defaulting the new arg.

### Pattern 3: Kernel-side validator reaching exec via the handle (EXEC-02)
**What:** A `Validator` that constructs an argv list and calls the workspace through `target.runner`, never spawning directly, never importing `app.*`.
**When to use:** `code_compile.py` / `code_test.py` / `code_lint.py`.
```python
# Source: modeled on spec_plan_coverage.py [VERIFIED: validators/spec_plan_coverage.py]
@register("validator", "code_compile", user_allowed=True)
class CodeCompileValidator:
    name = "code_compile"
    async def validate(self, target) -> list[Issue]:
        ws = _workspace(target.runner)                    # same reach as repo_diff.py:_workspace
        if ws is None or not _exec_granted(ws):
            issue = Issue(severity="P1",                  # VALIDATOR-DENY: explicit refusal, NO spawn
                          message="code_compile skipped: exec not granted")
            await _record(target, "code_compile", [issue]); return [issue]
        py_files = _target_py_files(target)               # stdlib glob over the run root
        try:
            ws.exec_command(["python", "-m", "py_compile", *py_files])
            issues = []
        except subprocess.CalledProcessError as exc:
            issues = [Issue(severity="P0", message=_parse(exc))]
        except PermissionError as exc:
            issues = [Issue(severity="P1", message=f"exec denied: {exc}")]  # never escapes
        await _record(target, "code_compile", issues); return issues
```

### Anti-Patterns to Avoid
- **Compiler auto-injecting `gates: [approval]`** — rejected in D-01; the compiled plan must mirror the authored manifest (no hidden behavior). Raise `CompilerError` instead.
- **Kernel runtime exec special-casing** — rejected in D-01; reintroduces the hardwired-branch pattern the project removes (`test_banned_patterns.py` would flag it if placed in `agents/execution_engine/`).
- **`shell=True` anywhere under `backend/app/agents/runtime/` or `backend/agents/`** — IN-02; the SPEC acceptance is grep = 0. Note: the current `test_banned_patterns.py` does NOT scan `shell=True` — a new grep assertion (or ledger CHECK row) is needed.
- **Validator spawning `subprocess` directly** — must go through the workspace handle so the recorder audits it (bypass-proof) and the policy enforces allow/deny.
- **Inheriting `os.environ` into the child** — leaks `AWS_*`/`ANTHROPIC_*`/`DATABASE_URL`/`*_TOKEN`/`*_PROXY`. Construct a minimal env dict.
- **Re-deriving `map_severity`** — VALID-03 single-source rule; import it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Durable approve/reject pause | A new approval/resume state surface | `_run_review_gate` via `run_human_gate` (D-02) | Step-granular resume is Phase 12; building it now is a second HITL mechanism |
| First-exec memory across restarts | An `ectx` boolean flag | `gate_events` lookup (D-03) | A flag forgets on restart; the audit table is already durable + scoped |
| Owner/workspace-scoped audit INSERT | A bespoke session/commit | `ScopedStore.record_exec_run` mirroring `record_hook_run` | Default-deny scoping, principal stamping, offline-degrade all already solved |
| Severity labels | A local P0→CRITICAL dict | `map_severity` (`severity.py`) | VALID-03 single source |
| Migration scaffolding | A fresh alembic recipe | Copy `0017` (table-first, batch FK, reverse downgrade) | Offline-reversible SQLite + Postgres recipe proven |
| Resource caps | A watchdog thread polling `/proc` | `resource.setrlimit` in `preexec_fn` | POSIX rlimits are kernel-enforced; a poller races |
| Process tree kill | `proc.kill()` | `start_new_session=True` + `os.killpg` | A forking runaway leaks children under bare kill |

**Key insight:** Every "net-new" piece in this phase has an exact precedent already in the tree (hook_runs writer, human-gate delegation, validator framework, 0017 migration). The phase is overwhelmingly *copy-the-established-pattern*, not *invent*. The only genuinely new design is the **hardened subprocess body** — and even that reuses the existing argv `subprocess.run` shape the git surface already uses.

## Runtime State Inventory

> Phase 10 is a brownfield refactor that adds a new persistence table and changes a port signature, but does **not** rename/migrate existing stored data. Inventory below.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | No existing data carries an exec string as a key. `exec_runs` (0018) is a NEW table — no backfill. No existing manifest grants exec, so no `Step.tools.exec=True` rows exist to migrate. | Code edit only (new table + writer). |
| Live service config | None — exec profile is module-level constants in `local.py`, not external service config. No n8n/Datadog/Tailscale equivalents in this stack. | None — verified: profile is in-repo data. |
| OS-registered state | None — no OS task/daemon registers an exec string. The subprocess is spawned per-invocation, not registered. | None — verified by phase boundary. |
| Secrets/env vars | The scrubbed env DELIBERATELY excludes all host creds (`AWS_*`/`ANTHROPIC_*`/`DATABASE_URL`/`*_TOKEN`/`*_PROXY`). No secret key is renamed. The `mcp_credentials` Fernet table (0017) is untouched. | None — the env scrub is the feature, not a migration. |
| Build artifacts | None — no compiled artifact carries an exec name. The fixture repo (`sample_python_repo/`) is new test data, not a build artifact. | None. |
| **Port signature change (special)** | `Workspace.exec_command(command: str)` → `exec_command(argv: list[str])` touches the port (`base.py:88`), impl (`local.py:183`), and every caller. Today the only caller is the (unreachable) post-gate path + test callers. | **Single-task move** (port + impl + callers together; no dual signature) per CONTEXT `<specifics>`. Verified: no live caller exists outside tests because exec is denied + the runtime workspace is not yet wired into the run path. |

## Common Pitfalls

### Pitfall 1: The runtime_env workspace is not wired into the engine run path
**What goes wrong:** A plan that only "stops ignoring the exec kwarg" in `create_workspace` will not reach exec, because `engine.execute()` never calls `LocalSandboxRuntime.create_workspace` — it only calls `scoped_store.create_workspace` (the DB-row helper). `KernelServices` has no `workspace` attribute today.
**Why it happens:** Phase 9 *designed* the runtime_env seam (registered `("runtime_env","local")`) but deferred wiring it onto the live run path; `repo_diff` tests reach `LocalWorkspace` by passing it *as* the runner.
**How to avoid:** Phase 10 must add the §15 host-seam wiring in `engine.execute()`: when the compiled plan contains an exec-granted step, resolve the runtime_env, call `create_workspace(exec=True, recorder=...)`, and bind the returned `Workspace` onto `KernelServices.workspace` so validators reach it via `target.runner`. **This is a first-class plan task, not a footnote.**
**Warning signs:** `grep -rn "runtime_env\|create_workspace" engine.py` returns only the ScopedStore helper (verified: lines 542–554 only).

### Pitfall 2: pytest-inside-pytest hang (code_test validator)
**What goes wrong:** `code_test` runs `pytest` as a subprocess against the fixture repo; if the validator's own test harness or the fixture's pytest discovers the parent suite or uses the parent cache, it can recurse or hang offline.
**Why it happens:** pytest auto-discovers `conftest.py` and cache up the tree; the offline full suite already hangs (Chromium/Bedrock/Postgres-gated per backend/CLAUDE.md).
**How to avoid:** Keep the fixture repo tiny; invoke `pytest -p no:cacheprovider` (and consider `--rootdir` pinned to the fixture); the policy caps (`cpu=60s`, `wall=120s`) bound any hang. Run the phase's tests via the targeted offline suite, never full pytest. `[CITED: 10-CONTEXT.md <specifics>]`
**Warning signs:** A test that does not return in <30s; a `.pytest_cache` appearing in the parent repo.

### Pitfall 3: Breaking the 5 characterization snapshots
**What goes wrong:** Any change to the gate loop, compiler ceiling, or workspace creation that perturbs the existing prototype/od_/revision/ppt/code-gen paths fails the byte/event-identical snapshots.
**Why it happens:** No existing manifest grants exec, so the new exec path must be *additive* and dormant for every existing run.
**How to avoid:** Gate every new behavior on `exec` being granted (compiler: trust-conditional only fires when `tools.exec`; engine: workspace `exec=True` only when the plan has an exec step; security gate: profile-conditional pass only for exec requests). Run with `SNAPSHOT_UPDATE` unset and confirm 0 diffs. `[VERIFIED: 10-SPEC.md acceptance + test_characterization_*]`
**Warning signs:** A non-empty diff in any `test_characterization_*` snapshot.

### Pitfall 4: `RLIMIT_AS` on darwin (dev) silently no-ops the mem cap
**What goes wrong:** Asserting an out-of-memory kill in a test will be flaky on the darwin dev machine where `RLIMIT_AS` is best-effort.
**Why it happens:** macOS does not hard-enforce `RLIMIT_AS` the way linux does. `[VERIFIED: python3.11 resource.RLIMIT_AS exists, but enforcement differs]`
**How to avoid:** Tests assert the *mechanism is applied* (the `preexec_fn` calls `setrlimit`), and the kill test uses the **portable wall-clock timeout** (`subprocess.TimeoutExpired` → `outcome=killed`), not a memory bomb. `[CITED: 10-SPEC.md Constraints/Platform]`
**Warning signs:** A flaky OOM test that passes in CI (linux) but fails locally (darwin).

### Pitfall 5: INV-12 dual policy surfaces (`ExecutionPolicy.check`)
**What goes wrong:** Implementing the live workspace policy while leaving `plan.py:ExecutionPolicy.check` as a parallel unwired forward surface creates two policy surfaces (INV-12 / no dual implementations).
**Why it happens:** `plan.py:172 ExecutionPolicy.check` is explicitly documented as "FORWARD SURFACE — NOT yet wired… the actual call site lands with LocalSandboxRuntime in Phase 9" (it didn't; it's Phase 10's call).
**How to avoid:** Per CONTEXT Claude's-discretion: **either** make `ExecutionPolicy.check` the live runtime check **or delete it** and let `LocalExecutionPolicy.allows` + the pre-spawn allow/deny check be the single surface. Recommendation: **delete `plan.py:ExecutionPolicy.check`** (and add a migration-ledger entry) — the live enforcement is naturally `LocalExecutionPolicy` (allow/deny/caps live on the policy the workspace already holds), and `ExecutionPolicy.check`'s `runtime_host` indirection adds a layer the locked design (profile on the policy) doesn't need. The `_PRIVILEGED_RUNTIME_ACTIONS` frozenset can stay if referenced elsewhere; verify with grep.
**Warning signs:** Two places that decide "is exec allowed"; a ledger row for a deleted forward surface missing.

### Pitfall 6: Audit write breaking the run
**What goes wrong:** A failed `exec_runs` INSERT (offline harness has no `workflow_runs` FK target) aborts the exec or the run.
**Why it happens:** The offline characterization harness has no DB rows.
**How to avoid:** `record_exec_run` must be best-effort (degrade to `None` on `SQLAlchemyError`) exactly like `record_hook_run`/`record_gate_event` (kernel_services.py:344). The recorder callback in the workspace must swallow audit failures. `[VERIFIED: kernel_services.py:324 pattern]`
**Warning signs:** A test that needs a real DB to exercise the exec path.

## Code Examples

### IN-03 synthetic-key fallback (repo_diff._split_per_file)
```python
# Source: backend/agents/capabilities/deliverables/repo_diff.py:122 [VERIFIED]
# Today: _path_from_header returns None for quoted/rename headers, and _flush()
# drops the block because `current_path is not None` is False → silent file loss.
def _flush(idx_holder=[0]) -> None:
    nonlocal current_path
    if current_lines:
        key = current_path
        if key is None:                                  # IN-03 fix: synthetic key, never drop
            idx_holder[0] += 1
            key = f"__unparsed_{idx_holder[0]}__"
        per_file[key] = "\n".join(current_lines).rstrip() + "\n"
```
Unit test: feed a `diff --git "a/has space.py" "b/has space.py"` (quoted) or a rename header and assert the block appears under a synthetic key (SPEC acceptance).

### IN-01 sign-off doc (catalog.py slack_post)
```python
# Source: backend/agents/capabilities/mcp_servers/catalog.py:86 [VERIFIED]
@register("mcp_server", "slack", user_allowed=True)
class SlackMcpServer(_McpServerBase):
    # MCP-04 SIGN-OFF (IN-01): slack 'post_message' is the ONE user-grantable WRITE
    # on the user palette. Accepted because the scope is post-only (no read of other
    # channels' history beyond list_channels) and rides the same gate/audit path as
    # every MCP call. Reviewed: <phase 10>. [the sign-off text IN-01 asks for]
    name = "slack"
    exposed_tools = frozenset({"post_message", "list_channels"})
```

### ScopedStore.record_exec_run (mirror record_hook_run)
```python
# Source: mirror of backend/agents/authz.py:799 record_hook_run [VERIFIED]
async def record_exec_run(self, run_id, step, argv, outcome, *, exit_code=None,
                          duration_ms=None, policy_snapshot=None, output_digest=None) -> str:
    from app.models.exec_runs import ExecRun
    session, owned = self._acquire()
    try:
        row = ExecRun(id=str(uuid.uuid4()), run_id=run_id,
                      owner_id=self._owner_id, workspace_id=self._workspace_id,
                      step=step, argv_json=argv, outcome=outcome, exit_code=exit_code,
                      duration_ms=duration_ms, policy_snapshot_json=policy_snapshot,
                      output_digest=output_digest)
        session.add(row); session.commit(); return row.id
    finally:
        if owned: session.close()
```

### 0018 migration skeleton (mirror 0017)
```python
# Source: mirror of backend/alembic/versions/0017_repositories_repo_workspace.py [VERIFIED]
revision = "0018"; down_revision = "0017"
def upgrade() -> None:
    op.create_table("exec_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("argv_json", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),        # allowed|denied|killed (free String, no Enum)
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("policy_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("output_digest", sa.String(), nullable=True),   # truncated digest, never raw secrets
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"))
def downgrade() -> None:
    op.drop_table("exec_runs")
```

### Offline test scripting of approve/reject (D-02 directive — test precedent)
```python
# Source: test_gates.py:54 (_RecordingRunner) + artifact_store/store.py:89 (set_review_response) [VERIFIED]
# Unit level (gate in isolation): a recording runner whose run_human_gate yields scripted events.
class _RecordingRunner:
    def __init__(self, review_events): self._review_events = review_events; self.gate_events = []
    async def run_human_gate(self, step, *, output=""): 
        for e in self._review_events: yield e          # e.g. {"type":"review_gate_approved"} or {"type":"_gate_rejected"}
# Engine/integration level (durable pause): drive _run_review_gate by setting the response.
await store.set_review_response(f"{run_id}:{agent_id}", approved=True)   # → approve → PASS
await store.set_review_response(f"{run_id}:{agent_id}", approved=False)  # → reject → BLOCK
```

## D-02 Researcher Directive — Answered

> *Directive: confirm how `_run_review_gate` / `run_human_gate` threads the WS approve/reject action and the checkpointer durability, and what an approval-flavored delegate needs (new handle method vs parameterized `run_human_gate`) so the `review_gate_*` parity path stays untouched while the approval events are distinguishable. Confirm how offline tests script the approve/reject.*

**1. How `_run_review_gate` threads the WS approve/reject action (VERIFIED — engine.py:2391, store.py:89, websocket.py:796):**
- `_run_review_gate(pipeline_run_id, agent_id, agent_name, output)` computes `gate_key = f"{pipeline_run_id}:{agent_id}"`, arms an `asyncio.Event` via `store.get_review_event(gate_key)` (clears it first so a fast response is not missed), transitions the state machine to `waiting_for_user`, and yields `review_gate_ready` (carrying `output` in `data.output`).
- It then `await event.wait()` — blocking durably until the WS layer calls `store.set_review_response(gate_key, approved=..., edited_content=...)` (websocket.py:796), which stores the response and `event.set()`s.
- On wake it reads `store.get_review_response(gate_key)`, transitions back to `generating` (if approved), and yields `review_gate_approved` (approve) or the internal `_gate_rejected` signal (reject), plus `_gate_edited` if edited.

**2. Checkpointer durability (VERIFIED — backend/CLAUDE.md + engine.py:2475 `restore_non_terminal_runs`):** The pause is durable across backend restarts: the LangGraph checkpointer persists per-agent-invocation thread state, and `restore_non_terminal_runs()` re-registers `asyncio.Event`s for runs in `waiting_for_user` on startup. The `gate_events` rows (D-03 first-exec memory) are separately persisted owner/workspace-scoped, so a post-restart approval lookup still finds the prior approval-pass row. Net: the approval pause survives a restart on both axes (resume event + first-exec memory).

**3. What an approval-flavored delegate needs (RECOMMENDATION — parameterize, do not add a method):** `KernelServices.run_human_gate(self, step, *, output: str = "")` (kernel_services.py:425) is the ONE delegate; the `human` gate calls it. To keep "ONE HITL mechanism" (D-02) and the `review_gate_*` parity path byte-identical, **parameterize `run_human_gate` with an optional structured `payload`/`kind` argument that defaults to the current string behavior.** The approval gate passes the D-04 exec-policy snapshot as `output`/`payload`; it flows into `review_gate_ready.data.output` through the existing generic WS forward (no frontend rebuild). Distinguishability comes from the `gate_events` row (`gate="approval"`) and the snapshot payload shape — the *event types* stay `review_gate_*` (parity), while the *gate identity* is "approval" in the audit + payload. The `human`-gate string-call path stays untouched because the new arg defaults. (A separate `run_approval_gate` method would be a second surface — rejected by D-02's single-mechanism rule.)

**4. Offline approve/reject scripting (VERIFIED — test_gates.py:54 + store.py:89):** Two established levels. (a) **Gate-isolation:** a `_RecordingRunner` whose `run_human_gate` yields scripted `review_gate_*` / `_gate_rejected` events (test_gates.py precedent); assert the gate's `GateOutcome` (PASS/BLOCK) and the recorded `gate_events`. (b) **Engine-level durable pause:** drive `_run_review_gate` by calling `store.set_review_response(gate_key, approved=True|False)` from the test, exactly as the prototype review-gate tests do. Both run fully offline (no Bedrock/Postgres/network). The first-exec short-circuit (D-03) is tested by pre-seeding an approval-pass `gate_events` row (or running a first exec to completion) and asserting the second exec step does NOT yield `review_gate_ready`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `subprocess.run(cmd, shell=True)` | argv-list `subprocess.run(argv, shell=False)` | This phase (IN-02 closure) | Eliminates command injection by construction |
| Watchdog thread for caps | `resource.setrlimit` in `preexec_fn` | Standard POSIX practice | Kernel-enforced, race-free |
| Inherit `os.environ` | Constructed minimal env dict | This phase (scrubbed-env posture) | No host-cred leakage into exec'd code |

**Deprecated/outdated:** None relevant. `preexec_fn` carries a CPython thread-safety caveat (documented), but is acceptable for this single-spawn surface and is the standard rlimit-in-child idiom.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Parameterizing `run_human_gate` (vs a new `run_approval_gate`) is the right single-mechanism choice | D-02 answer / Pattern 2 | Low — both are viable; CONTEXT leaves the exact handle shape to the directive. If parameterizing breaks parity, fall back to a defaulted sibling method. Planner confirms. |
| A2 | `start_new_session=True` + `os.killpg` is the right tree-kill approach for the timeout | Pattern 1 / Standard Stack | Low — standard POSIX idiom; verified `resource`/`os` available. The SPEC only requires "kill on expiry"; bare `proc.kill()` also satisfies it if a process-group is over-engineering for the allow-listed tools. |
| A3 | Deleting `plan.py:ExecutionPolicy.check` (vs making it live) is the cleaner INV-12 resolution | Pitfall 5 | Medium — CONTEXT explicitly leaves this to the planner "after reading both." If a future phase needs the `runtime_host` indirection, making it live may be preferable. Planner decides; either path needs a migration-ledger entry. |
| A4 | The runtime_env workspace is genuinely unwired into the live run path (not wired in a file I didn't read) | Pitfall 1 / Summary | Medium-High impact if wrong — but verified by grep over `engine.py` (only ScopedStore.create_workspace at 542–554) AND `KernelServices` has no `workspace` attr AND `repo_diff._workspace` reaches `LocalWorkspace` only when passed AS the runner. Planner should confirm during planning by re-grepping. |
| A5 | A new grep assertion for `shell=True` is needed (the existing banned-pattern test does not scan it) | Anti-Patterns / Validation | Low — verified `grep "shell" test_banned_patterns.py` returns nothing. Could be added as a migration-ledger grep row (IN-02) instead of a standalone test. |

## Open Questions

1. **Where exactly does the §15 host seam call `create_workspace`?**
   - What we know: the seam is `engine.execute()` around lines 540–560 (workspace) / 720–780 (RepoSpec/MCP injection); RepoSpec is host-injected per-run.
   - What's unclear: whether the runtime_env workspace should be provisioned at the same point as the ScopedStore workspace row, and how the exec-grant detection (scan compiled plan for any `Step.tools.exec`) is threaded.
   - Recommendation: provision the runtime_env `Workspace` right after the ScopedStore `create_workspace` (so `workspace_id` is known), conditional on `any(s.tools.exec for s in compiled.steps)`; bind onto `KernelServices.workspace`. Planner verifies the exact insertion point against the RepoSpec precedent.

2. **Does the SecurityGate read the workspace policy or the compiled step for the profile check?**
   - What we know: CONTEXT leaves this to the planner ("gate evaluates the step + ctx it's given").
   - Recommendation: read the compiled step (trust + `tools.exec`) for the PASS decision and verify `approval` is in `step.gates` (D-01 defense-in-depth); the *profile attachment* check can read `ctx.runner.workspace.policy` if the workspace is bound by then, else treat profile-presence as implied by the exec-conditional provisioning. Keep the gate kernel-pure (no `app.*` import).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All (dev runtime) | ✓ | 3.11.14 | — |
| `subprocess`/`resource`/`os` (stdlib) | EXEC-PROFILE hardening | ✓ | stdlib | — |
| `ruff` | `code_lint` validator | ✓ | 0.8.4 (`~/.local/bin/ruff`) | — |
| `pytest` | `code_test` validator | ✓ | 8.3.4 (`python3.11 -m pytest`) | — |
| `py_compile` (stdlib) | `code_compile` validator | ✓ | stdlib | — |
| `lint-imports` (import-linter) | CI gate (validators stay kernel-pure) | ✓ | `/opt/homebrew/bin/lint-imports` | — |
| Postgres / Bedrock / network | NONE this phase | — | — | offline fixtures + best-effort audit degrade |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — full offline verification path confirmed (per backend/CLAUDE.md targeted suite).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 (`python3.11 -m pytest`, no venv) |
| Config file | `backend/pytest.ini` / pyproject (existing) |
| Quick run command | `cd backend && python3.11 -m pytest tests/agents/test_gates.py tests/agents/test_local_runtime.py -x -p no:cacheprovider` |
| Full suite command | targeted offline suite per backend/CLAUDE.md (full pytest hangs offline) + `/opt/homebrew/bin/lint-imports` |

### Phase Requirements → Test Map
| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| EXEC-PROFILE | argv/no-shell, scrubbed env, rlimit applied, timeout kill, 64KB truncate, deny default | unit | `pytest tests/agents/test_local_runtime.py -k exec -x` | ❌ Wave 0 (grow `test_local_runtime.py`) |
| EXEC-PROFILE | grep `shell=True` = 0 over runtime+agents | grep | new test or migration-ledger IN-02 row | ❌ Wave 0 |
| EXEC-POLICY | allow runs, non-listed pre-spawn deny, deny>allow, not manifest-tunable | unit | `pytest tests/agents/test_local_runtime.py -k policy -x` | ❌ Wave 0 |
| EGRESS-DENY | network blocks at gate; allow-list has no net tools; env scrub; residual note present | unit | `pytest tests/agents/test_gates.py -k network`, `test_local_runtime.py -k env` | partial (test_gates network exists) |
| GRANT-PATH | file/builtin exec compiles True; user/db exec → CompilerError; existing manifests identical | unit | `pytest tests/agents/test_mcp_compile_validation.py`-style compiler tests | ❌ Wave 0 (new compiler test) |
| GATES | security profile pass; net/secrets block; first-exec wait_human; approve→run reject→block; 2nd no re-pause | unit + engine | `pytest tests/agents/test_gates.py -x` | partial (grow `test_gates.py`) |
| AUDIT | 0018 reversible; allowed/denied/killed rows; cross-owner read empty | migration + unit | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`; `pytest -k exec_runs` | ❌ Wave 0 |
| VALIDATORS | compile+test PASS on fixture; lint flags seeded error; validation_results rows | unit | `pytest tests/agents/test_code_validators.py -x -p no:cacheprovider` | ❌ Wave 0 |
| VALIDATOR-DENY | each validator under exec-denied → ≥1 refusal, 0 spawns | unit | `pytest tests/agents/test_code_validators.py -k denied` | ❌ Wave 0 |
| DEBT+PARITY | IN-01 doc present; IN-03 synthetic key; 5 snapshots identical; lint 4/0; ledger green | unit + grep | `pytest tests/agents/test_repo_diff.py -k unparsed`; `pytest tests/agents/test_characterization_*`; `lint-imports`; `pytest tests/agents/test_migration_ledger.py` | partial |

### Sampling Rate
- **Per task commit:** the relevant `tests/agents/test_*.py -x -p no:cacheprovider` (quick).
- **Per wave merge:** full targeted offline suite + `lint-imports` + `test_characterization_*` + `test_banned_patterns.py` + `test_migration_ledger.py`.
- **Phase gate:** all 14 SPEC acceptance criteria green; 5 snapshots byte/event-identical with `SNAPSHOT_UPDATE` unset.

### Wave 0 Gaps
- [ ] `tests/agents/test_code_validators.py` — covers VALIDATORS + VALIDATOR-DENY (new)
- [ ] `tests/agents/fixtures/sample_python_repo/` — tiny compile+test fixture + a `__unparsed__`/lint-error seed
- [ ] Grow `tests/agents/test_local_runtime.py` — EXEC-PROFILE + EXEC-POLICY
- [ ] Grow `tests/agents/test_gates.py` — security profile-pass + approval first-exec + approve/reject + no-re-pause
- [ ] New compiler test — GRANT-PATH trust-conditional + D-01 gates-required CompilerError
- [ ] New `exec_runs` migration + ORM model test (reversibility + scoped writes)
- [ ] Grow `tests/agents/test_repo_diff.py` — IN-03 unparseable-header synthetic key
- [ ] `shell=True` grep assertion (standalone test OR migration-ledger IN-02 row)
- [ ] Registry count guard: bump `test_registry_capabilities.py:132` `== 50` → `== 53`

## Security Domain

> `security_enforcement` is implicitly enabled (no `false` in config). This phase IS a security feature; the threat model is the SPEC's N3 decision record.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Three-layer enforcement (compiler trust → gate → workspace policy); ports & adapters; engineer-only exec (`user_allowed=False`) |
| V2 Authentication | no | No new auth surface (engineer-only exec; approval is HITL sign-off, not authN) |
| V4 Access Control | yes | Trust-conditional compile (user/db → CompilerError); owner/workspace-scoped `exec_runs` default-deny reads; first-exec human approval |
| V5 Input Validation | yes | argv allow-list (deny>allow) pre-spawn; no shell interpolation; `clone_repo` already rejects `-`/`ext::` (verified local.py:148) |
| V7 Error Handling/Logging | yes | `exec_runs` audits every invocation (allowed/denied/killed); digest never raw secrets; best-effort degrade never breaks the run |
| V12 Files/Resources | yes | `cwd` locked to run root; `RunSandbox` traversal-rejection; rlimits + wall-clock + output truncation; scrubbed env |
| V13 API/Comms | yes (egress) | policy+allow-list+env egress denial; documented accepted residual (interpreter sockets); OS enforcement = v2 ECS |

### Known Threat Patterns for hardened-subprocess exec

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command injection via shell | Tampering/EoP | argv-list `shell=False` (IN-02 closure); grep `shell=True` = 0 |
| Argument injection (`-`-prefixed) | Tampering | allow-list constrains `argv[0]`; `clone_repo` already rejects `-` sources |
| Host credential exfiltration | Info Disclosure | scrubbed minimal env (no `AWS_*`/`*_TOKEN`/`DATABASE_URL`/`*_PROXY`); asserted by env test |
| Resource exhaustion (fork bomb / OOM / spin) | DoS | `RLIMIT_CPU` + `RLIMIT_AS` (preexec_fn) + wall-clock timeout + `killpg` tree kill |
| Data egress over sockets | Info Disclosure | network OFF at gate; no net-capable tool on allow-list; residual interpreter-socket risk documented + accepted (engineer-only) |
| User-grantable privilege escalation | EoP | compiler `CompilerError` on user/db exec/network/secrets grant; exec never `user_allowed=True` |
| Audit bypass | Repudiation | recorder at the `exec_command` enforcement point — every path (allowed/denied/killed) audited regardless of caller |
| Unbounded output (log/memory blowup) | DoS | 64KB/stream truncation; digest in audit, not raw bytes |

## Sources

### Primary (HIGH confidence — read in this session)
- `backend/app/agents/runtime/local.py` — `LocalExecutionPolicy`/`exec_command`/`create_workspace` (the rewrite targets, verified line-exact)
- `backend/agents/runtime/base.py` — `Workspace`/`ExecutionPolicy`/`RuntimeEnvironment` ports
- `backend/agents/capabilities/gates/{security,approval,human}.py` — gate impls + the human-gate delegation precedent
- `backend/agents/execution_engine/engine.py` — `_evaluate_gates` (2347), `_run_review_gate` (2391), pre-step gate loop (1145), host seam (540–560, 720–780)
- `backend/agents/execution_engine/kernel_services.py` — `KernelServices`, `record_hook_run` (324), `run_human_gate` (425), `DeliverableContext` (99)
- `backend/agents/workflows/compiler.py` — `workflow_ceiling = ToolPermissions()` (312), `_compile_tool_grant`, `_check_trust`
- `backend/agents/workflows/plan.py` — `ToolPermissions`, `ExecutionPolicy.check` forward surface (148), `_PRIVILEGED_RUNTIME_ACTIONS` (145)
- `backend/agents/capabilities/validators/{spec_plan_coverage,severity}.py` — validator pattern + single `map_severity`
- `backend/agents/capabilities/deliverables/repo_diff.py` — IN-03 site (`_split_per_file`/`_path_from_header`)
- `backend/agents/capabilities/mcp_servers/catalog.py` — IN-01 slack_post site
- `backend/agents/authz.py` — `ScopedStore` writers (record_gate_event 711, record_hook_run 799)
- `backend/agents/artifact_store/store.py` — review-gate event/response (82–101)
- `backend/agents/capabilities/registry.py` — `_KNOWN` (50 entries), `@register`
- `backend/alembic/versions/0017_repositories_repo_workspace.py` — additive-migration recipe
- `backend/tests/agents/test_gates.py` — `_RecordingRunner`, approval/security gate tests (the test precedent)
- `backend/tests/agents/test_banned_patterns.py` — scope (kernel-scoped hard-fail; does NOT scan shell=True)
- `backend/tests/agents/test_registry_capabilities.py:132` — `len(_KNOWN) == 50` drift guard
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — ratchet rules + R1 row
- `10-SPEC.md` / `10-CONTEXT.md` — locked requirements + decisions

### Tool verifications
- `python3.11 --version` → 3.11.14; `resource.RLIMIT_CPU=0`, `RLIMIT_AS=5` present
- `ruff --version` → 0.8.4; `python3.11 -m pytest --version` → 8.3.4; `py_compile` importable

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all stdlib + already-installed tools, versions verified this session.
- Architecture: HIGH — every gate/engine/compiler/policy site read and confirmed line-exact; the one structural surprise (unwired runtime_env workspace) verified by grep.
- D-02 directive: HIGH — `_run_review_gate`, `run_human_gate`, `set_review_response`, and the test precedent all read directly.
- Pitfalls: HIGH — derived from read code + verified tool behavior + backend/CLAUDE.md offline constraints.

**Research date:** 2026-06-10
**Valid until:** stable (brownfield internal codebase; no fast-moving external deps) — re-grep the runtime_env wiring (A4) at plan time as a cheap confirmation.
