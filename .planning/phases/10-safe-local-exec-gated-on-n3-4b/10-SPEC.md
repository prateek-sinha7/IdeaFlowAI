# Phase 10: Safe Local Exec (gated on N3) [4B] — Specification

**Created:** 2026-06-10
**Ambiguity score:** 0.14 (gate: ≤ 0.20)
**Requirements:** 9 locked

## Goal

Code execution flips from unconditionally-denied to a constrained, audited, engineer-only exec profile — argv-only subprocess with an allow-listed Python toolchain, scrubbed environment, resource caps, and denied egress, runnable only behind the `security` gate plus a first-exec `approval` gate — proven by compile/test/lint validators passing against the local fixture repo with zero engine edits.

**This SPEC is the N3 decision record.** The open decision "N3 (Phase 10/[4B]) ⚠️ — local `exec` security threat model" is RESOLVED by the locked decisions below; STATE.md/PROJECT.md flip N3 to decided when this phase completes.

## Background

Phase 9 left exec OFF at four independent layers, all verified in code:

1. **Compiler** (`backend/agents/workflows/compiler.py:313`): `workflow_ceiling = ToolPermissions()` collapses `exec` to False at compile time for *every* manifest — even a file-trust manifest declaring `tools.exec: true` compiles to `Step.tools.exec=False`.
2. **SecurityGate** (`backend/agents/capabilities/gates/security.py`): unconditionally blocks any step requesting exec/network/secrets ("all OFF this phase").
3. **Workspace policy** (`backend/app/agents/runtime/local.py:231`): `create_workspace(exec=...)` ignores its kwarg — `LocalExecutionPolicy(exec=False, network=False, secrets=[])` is hardcoded. No `exec_allow`/`exec_deny`/resource-cap fields exist on the live policy (the §8 spec fields were never implemented; `plan.py`'s `ExecutionPolicy.check` helper is an unwired forward surface).
4. **`LocalWorkspace.exec_command(command: str)`**: raises `PermissionError` under the default policy; its unreachable post-gate path uses `subprocess.run(command, shell=True)` — flagged **IN-02** in the Phase 9 review as a command-injection surface by construction once exec is enabled.

The validator framework (08-04: `Validator` port, `DeliverableContext`, `FixPolicy`, `validation_results` persistence, single `map_severity`) exists, but no compile/test/lint validators do — they need gated exec to run compilers/tests/linters. The gate registry (08-02) already has `security` and `approval` handlers. ScopedStore + additive-migration patterns are established (latest migration: 0017). STATE.md carries a pending todo: "Phase 09 REVIEW.md 3 Info findings (IN-01/02/03) — revisit in Phase 10 (exec hardening)."

## Requirements

1. **EXEC-PROFILE — hardened subprocess** *(EXEC-01: resource caps + ephemeral creds)*: `exec_command` becomes an argv-based, no-shell, environment-scrubbed, resource-capped subprocess invocation.
   - Current: `exec_command(command: str)` raises `PermissionError` (policy hardcoded `exec=False`); unreachable path runs `subprocess.run(command, shell=True)` (IN-02)
   - Target: `exec_command` takes an argv list (no shell, no string-command form); spawns with a minimal constructed environment (`PATH`/`HOME`/`TMPDIR` only — the v1 "ephemeral creds" posture: host creds can never leak into exec'd code), `cwd` locked to the run root, POSIX rlimits applying `cpu_seconds=60` and `mem_mb=512` (mem best-effort on darwin, hard on linux), wall-clock timeout `120s` (kill on expiry), stdout/stderr captured and truncated at 64KB per stream. The deny default is unchanged: `PermissionError` when `policy.allows("exec")` is False (T-09-01-02 stays green).
   - Acceptance: grep `shell=True` over `backend/app/agents/runtime/` + `backend/agents/` = 0; a test exec of `env` shows no host-cred variables (`AWS_*`, `ANTHROPIC_*`, `DATABASE_URL`, `*_TOKEN`, `*_PROXY`); a runaway command is killed by the timeout; oversized output is truncated at 64KB; ungranted exec still raises `PermissionError`.

2. **EXEC-POLICY — allow/deny lists + caps live** *(EXEC-01: command allow/deny)*: the live workspace policy carries the constraint profile and enforces it before spawn.
   - Current: `LocalExecutionPolicy` has only `exec`/`network`/`secrets`; no allow/deny lists or caps; `create_workspace(exec=True)` is ignored
   - Target: the policy carries `exec_allow` (v1 default: `python`, `python3`, `pytest`, `ruff`), `exec_deny` (deny beats allow), `cpu_seconds=60`, `mem_mb=512`, wall-clock `120s`. `argv[0]` not on the allow-list, or on the deny-list, → `PermissionError` naming the command, **before any process is spawned**. An exec-granted run threads the profile into the workspace policy (the `create_workspace` exec kwarg stops being ignored). The profile is **runtime/host-owned, not manifest-tunable**: a manifest may grant `tools.exec: true` but can never widen the allow-list or raise the caps.
   - Acceptance: an allow-listed command executes; a non-listed command is rejected pre-spawn (no child process observed); a command on both lists is rejected (deny-precedence test); manifests have no key that alters the profile (compiler strict-key already rejects unknown keys — INV-5).

3. **EGRESS-DENY — network denied by default** *(EXEC-01/EXEC-02: network default-deny)*: v1 enforces egress denial at policy + allow-list + env level; the residual risk is explicitly documented and accepted.
   - Current: exec unreachable, so egress moot; nothing would prevent a spawned process from opening sockets
   - Target: `policy.network` stays False; the allow-list contains no network-capable tools (no `curl`/`wget`/`pip`/`npm`); the scrubbed env carries no proxy/cred variables. Residual risk — an allow-listed interpreter can still open sockets — is documented in code and in the phase SECURITY notes as **accepted for v1** because exec is engineer-only (never user-grantable); OS-level enforcement (netns/containers) is the v2 ECS seam.
   - Acceptance: a network-requesting step is still blocked at the security gate; an allow-list audit test asserts no network-capable command is listed; the scrubbed-env test asserts no `HTTP_PROXY`/`HTTPS_PROXY`/cred vars; the residual-risk note exists in code at the enforcement point.

4. **GRANT-PATH — trust-conditional compile ceiling**: only engineer-authored manifests can grant exec; user/db manifests hard-fail at compile.
   - Current: `workflow_ceiling = ToolPermissions()` collapses exec for ALL manifests; user/db trust checks cover capability references, not permission grants
   - Target: for `file`/`builtin` trust, a step's `tools.exec: true` survives `intersect_permissions` into `Step.tools.exec=True`; for `user`/`db` trust, a manifest granting `exec`/`network`/`secrets` raises `CompilerError` naming the grant and the step (§8 "never user-grantable"). Three enforcement layers stand: compiler (trust), gate (profile), workspace policy (runtime).
   - Acceptance: compiling a file-trust manifest with `exec: true` yields `Step.tools.exec=True`; compiling the same manifest at `trust='user'` raises `CompilerError`; every existing manifest (none grants exec) compiles to an identical `CompiledWorkflow`.

5. **GATES — security pass + first-exec approval**: an exec-granted step runs only after the security gate passes the constrained profile AND a human has approved the run's first exec.
   - Current: `SecurityGate.evaluate` blocks any step requesting exec/network/secrets unconditionally
   - Target: the security gate **passes** an exec-granted step iff the workflow is `file`/`builtin` trust AND a constrained `ExecutionPolicy` profile is attached (non-empty allow-list + caps); requests for `network` or `secrets` **still block** (later phases). Additionally — locked by user decision (stricter than the recommended security-gate-only option) — the **first exec-granted step per run pauses for human approval** (`wait_human`, approval-gate semantics with durable gate events) before exec runs; approval recorded → subsequent exec steps in the same run proceed without re-prompt; rejection blocks the step.
   - Acceptance: gate tests — a profile-attached, file-trust exec step passes security; a network/secrets-requesting step still blocks; the first exec step pauses `wait_human` and emits/persists gate events; approve → step runs; reject → step blocked; a second exec step in the same run does not re-pause; `gate_events` rows written for each evaluation.

6. **AUDIT — `exec_runs` table**: every exec invocation leaves an owner/workspace-scoped audit row.
   - Current: no exec audit exists (nearest precedents: `hook_runs` 0016, `gate_events`)
   - Target: additive migration **0018** creates `exec_runs` (id, `owner_id`, `workspace_id`, run_id, step, argv_json, outcome ∈ `allowed`/`denied`/`killed`, exit_code, duration_ms, policy_snapshot_json, truncated output digest, created) written via ScopedStore for **every** `exec_command` invocation — including denials and timeout kills; rows never contain raw secrets (digest truncated).
   - Acceptance: `upgrade head` → `downgrade -1` → `upgrade head` reversible offline (0017 precedent); an allowed exec writes `outcome=allowed` with exit code; a denied exec writes `outcome=denied`; a timed-out exec writes `outcome=killed`; cross-owner read returns nothing (default-deny scope test).

7. **VALIDATORS — compile/test/lint land** *(EXEC-02)*: three registered validators drive gated exec; the sample passes on the fixture repo.
   - Current: html_static/html_render/spec_plan_coverage/task_done_when/design_quality registered; no code validators; `_KNOWN` registry count 50
   - Target: `code_compile` (`python -m py_compile` over target `.py` files), `code_test` (`pytest`, bounded by the policy caps), `code_lint` (`ruff check`) registered as `Validator` capabilities reaching exec **only** via the runner/workspace handle under the gated policy (no kernel/app import from capabilities; import-linter kept). Severity via the single `map_severity`; each run writes `validation_results` rows. Registry membership grows 50→53 with the lockstep drift-guard updated.
   - Acceptance: the sample compile+test validators **PASS** against the local Python fixture repo offline with **zero edits under `backend/agents/execution_engine/`** (SC-001 discipline); `code_lint` flags a seeded lint error as issues with mapped severity; each validator run produces `validation_results` rows.

8. **VALIDATOR-DENY — refusal without spawn**: validators degrade explicitly when exec is ungranted.
   - Current: n/a (validators don't exist)
   - Target: with exec ungranted, each code validator returns an explicit refusal/skip `Issue` (mapped severity, message naming the missing grant) **without spawning any process** — never a silent pass, never a crash.
   - Acceptance: a test running each validator under an exec-denied policy asserts ≥1 refusal issue, zero subprocess spawns, and no `PermissionError` escaping the validator.

9. **DEBT + PARITY — review-trio closure and INV-3 held**: the Phase 9 deferred findings close and existing behavior is untouched.
   - Current: STATE.md pending todo — IN-01 (slack_post write-exception unsigned), IN-02 (`shell=True`), IN-03 (repo_diff drops unparseable diff headers); 5 characterization snapshots green; lint-imports 4 kept/0 broken
   - Target: IN-01 — the slack_post write-exception is documented as a signed-off exception near the MCP-04 gating logic; IN-02 — subsumed by Requirement 1 (argv, no shell); IN-03 — `repo_diff._split_per_file` falls back to a synthetic key for unparseable `diff --git` headers so no changed file is silently dropped. Existing workflows: byte/event parity (no manifest grants exec, so nothing changes).
   - Acceptance: IN-01 sign-off text present near the gating logic; IN-03 unit test with a quoted/rename header asserts the block appears under a synthetic key; STATE.md pending todo cleared; 5 characterization snapshots byte/event-identical with `SNAPSHOT_UPDATE` unset; lint-imports 4 kept/0 broken; banned-pattern + migration-ledger gates green.

## Boundaries

**In scope:**
- The N3 threat-model resolution (this SPEC's locked decisions are the decision record; N3 flips to decided)
- Hardened-subprocess exec profile in `LocalWorkspace` (argv-only, no shell, scrubbed env, rlimits, wall-clock timeout, output truncation)
- Live `ExecutionPolicy` constraint fields: `exec_allow`/`exec_deny` (deny-precedence), `cpu_seconds`/`mem_mb`/timeout — runtime-owned, not manifest-tunable
- Trust-conditional compiler ceiling: file/builtin manifests may grant `tools.exec`; user/db grants of exec/network/secrets → `CompilerError`
- SecurityGate evolution (profile-conditional pass for exec; network/secrets still block) + first-exec-per-run approval pause
- `exec_runs` audit table (additive migration 0018) + ScopedStore writer, all outcomes recorded
- `code_compile`/`code_test`/`code_lint` registered validators + offline fixture-repo sample proof + exec-denied refusal behavior
- Phase 9 review-trio closure (IN-01 sign-off doc, IN-02 argv/no-shell, IN-03 repo_diff synthetic-key fallback)
- Characterization parity, import-linter, banned-pattern, migration-ledger discipline

**Out of scope:**
- Containers/Docker/ECS isolation — v2 behind the unchanged `RuntimeEnvironment` port (the designed seam; deferred per plan §27)
- OS-level network enforcement (netns/seccomp/sandbox-exec) — v1 accepts policy+allow-list egress denial with a documented residual risk; platform-forked enforcement rejected in interview
- `network_allow` implementation — the field may exist as data, but the `network` permission stays blocked at the gate (a later phase)
- `secrets` permission enablement / ephemeral-cred-vendor seam — no v1 consumer (egress denied, no push); scrubbed env IS the v1 posture
- PR/commit push and git-hosting integration — N4 (diff-only stands)
- User-grantable exec — user/db manifests remain compile-blocked; nothing exec-related becomes `user_allowed=True`
- Non-Python toolchains (node/npm etc.) — the allow-list is data and extensible later; npm's network+postinstall surface contradicts v1 egress denial
- Warm pools / long-job orchestration substrate — N8
- Windows support — POSIX rlimits (darwin dev best-effort mem cap, linux prod hard)
- Fan-out / `spawn_subagents` — Phase 11

## Constraints

- **Additive migrations only** (Q3): 0018 follows 0017; new table carries `owner_id` + `workspace_id`; reversibility proven offline against SQLite (0017 precedent)
- **INV-13**: the deepagents agent runtime is untouched; exec'd subprocesses are tool-level workspace operations, not agent loops; banned-pattern gate stays green
- **Ports & Adapters**: capabilities reach exec only via the `ctx.runner`/workspace handle; no `agents.capabilities → agents.execution_engine`/`app` import; all 4 import-linter contracts kept
- **INV-3**: 5 characterization snapshots byte/event-identical, no re-baseline (no existing manifest grants exec)
- **INV-5**: manifests stay pure data — the only exec-related manifest surface is the `tools.exec` bool grant; profile values (allow-list, caps) are runtime-owned
- **Offline-verifiable**: every acceptance criterion runs in the targeted offline suite (no live Bedrock/Postgres/network); `pytest` and `ruff` invoked by validators must resolve from the dev environment (`python3.11`, no venv)
- **Platform**: rlimit semantics — `RLIMIT_CPU` portable; `RLIMIT_AS` best-effort on darwin (dev), hard on linux (prod); tests assert the mechanism is applied, the kill test uses the portable wall-clock timeout
- **Cap defaults locked**: `cpu_seconds=60`, `mem_mb=512`, wall-clock `120s`, output truncation 64KB/stream; deny beats allow

## Acceptance Criteria

- [ ] `exec_command` raises `PermissionError` when `policy.allows("exec")` is False (T-09-01-02 unchanged)
- [ ] grep `shell=True` over `backend/app/agents/runtime/` + `backend/agents/` = 0
- [ ] `argv[0]` not on `exec_allow` → `PermissionError` naming the command, zero processes spawned; a command on both lists is denied (deny-precedence)
- [ ] Exec'd `env` output contains no host-cred variables (`AWS_*`, `ANTHROPIC_*`, `DATABASE_URL`, `*_TOKEN`, `*_PROXY`) — scrubbed-env test
- [ ] A runaway command is killed at the wall-clock timeout; output truncated at 64KB; an `exec_runs` row records `outcome=killed`
- [ ] File-trust manifest with `tools.exec: true` compiles to `Step.tools.exec=True`; identical manifest at `trust='user'` → `CompilerError`
- [ ] SecurityGate passes a profile-attached file-trust exec step; still blocks any `network`/`secrets` request
- [ ] First exec step per run pauses `wait_human`; approve → runs, reject → blocked; second exec step in the run does not re-pause; `gate_events` rows persisted
- [ ] Migration 0018 (`exec_runs`) is reversible offline; allowed/denied/killed invocations each write a scoped row; cross-owner read returns nothing
- [ ] `code_compile` + `code_test` validators PASS against the local Python fixture repo offline with zero edits under `backend/agents/execution_engine/`
- [ ] `code_lint` flags a seeded lint error with severity via the single `map_severity`; `validation_results` rows written per validator run
- [ ] Each code validator under an exec-denied policy returns ≥1 explicit refusal issue without spawning
- [ ] IN-01 sign-off documented near the MCP-04 gating logic; IN-03 synthetic-key fallback proven by a unit test with an unparseable header
- [ ] 5 characterization snapshots byte/event-identical (`SNAPSHOT_UPDATE` unset); lint-imports 4 kept/0 broken; banned-pattern + migration-ledger green

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                            |
|--------------------|-------|------|--------|--------------------------------------------------|
| Goal Clarity       | 0.90  | 0.75 | ✓      | N3 parameters fully decided in interview          |
| Boundary Clarity   | 0.85  | 0.70 | ✓      | Explicit out-of-scope incl. enforcement-strength line |
| Constraint Clarity | 0.80  | 0.65 | ✓      | Cap numbers locked; platform caveat documented    |
| Acceptance Criteria| 0.85  | 0.70 | ✓      | 14 pass/fail criteria, all offline-runnable       |
| **Ambiguity**      | 0.14  | ≤0.20| ✓      |                                                  |

## Interview Log

| Round | Perspective              | Question summary                                   | Decision locked                                                                 |
|-------|--------------------------|----------------------------------------------------|---------------------------------------------------------------------------------|
| 1     | Researcher               | v1 isolation mechanism?                            | Hardened subprocess: argv-only/no-shell, scrubbed env, rlimits, timeout, cwd=run root |
| 1     | Researcher               | Egress enforcement strength?                       | Policy + allow-list deny; residual interpreter-socket risk documented + accepted (engineer-only exec) |
| 1     | Researcher               | Command allow-list contents?                       | Python toolchain only: `python`/`python3`/`pytest`/`ruff`; default-deny the rest |
| 2     | Researcher + Simplifier  | What does "ephemeral creds" mean in v1?            | Scrubbed minimal env (PATH/HOME/TMPDIR) IS the posture; no cred-vendor seam     |
| 2     | Researcher + Simplifier  | Which validators + what sample?                    | `code_compile`/`code_test`/`code_lint`, Python, fixture-proven offline + deny case |
| 2     | Researcher + Simplifier  | Persist exec audit records?                        | Yes — additive `exec_runs` table (0018), owner/workspace-scoped, all outcomes   |
| 3     | Boundary Keeper          | Phase 9 review trio (IN-01/02/03) in scope?        | Close all three (IN-02 core; IN-01 sign-off doc; IN-03 synthetic-key fallback)  |
| 3     | Boundary Keeper          | What makes the security gate PASS exec now?        | **Security + approval**: profile-conditional security pass AND human sign-off on first exec per run (user chose stricter than recommended) |
| 3     | Boundary Keeper          | Target compile-time grant path?                    | Trust-conditional ceiling: file/builtin may grant exec; user/db exec/network/secrets grant → `CompilerError` |
| Gate  | —                        | Cap defaults + deny-precedence                     | cpu_seconds=60, mem_mb=512, wall-clock=120s, 64KB truncation; deny beats allow (accepted with gate confirmation) |

---

*Phase: 10-safe-local-exec-gated-on-n3-4b*
*Spec created: 2026-06-10*
*Next step: /gsd-discuss-phase 10 — implementation decisions (where the profile lives, approval-gate wiring, validator placement app-vs-kernel side, exec_runs writer seam)*
