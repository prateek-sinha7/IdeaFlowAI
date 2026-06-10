# Phase 10: Safe Local Exec (gated on N3) [4B] - Pattern Map

**Mapped:** 2026-06-10
**Files analyzed:** 17 (8 grown, 6 new, 3 closure-edits)
**Analogs found:** 17 / 17 (every new/grown file has an exact in-tree precedent)

> This phase is overwhelmingly *copy-the-established-pattern*. Each row below names the analog file, the exact lines to copy from, and the delta from the analog. The one genuinely new design is the hardened `exec_command` body (RESEARCH §Pattern 1), and even that reuses the existing `_git` argv `subprocess.run` shape.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/agents/runtime/local.py` (GROW) | runtime-impl | transform (argv→subprocess) | self (`_git` argv surface, lines 113-131) | exact (same file) |
| `backend/agents/runtime/base.py` (GROW) | port | request-response | self (`exec_command` Protocol, line 88) | exact (same file) |
| `backend/agents/capabilities/gates/approval.py` (GROW) | gate | event-driven (HITL) | `gates/human.py` (full) | exact (role + flow) |
| `backend/agents/capabilities/gates/security.py` (GROW) | gate | request-response | self (lines 35-75) | exact (same file) |
| `backend/agents/capabilities/validators/code_compile.py` (NEW) | validator | transform (argv+parse) | `validators/spec_plan_coverage.py` | exact |
| `backend/agents/capabilities/validators/code_test.py` (NEW) | validator | transform | `validators/spec_plan_coverage.py` | exact |
| `backend/agents/capabilities/validators/code_lint.py` (NEW) | validator | transform | `validators/spec_plan_coverage.py` | exact |
| `backend/agents/execution_engine/kernel_services.py` (GROW) | service | event-driven + CRUD | self (`record_hook_run` :324, `run_human_gate` :425) | exact (same file) |
| `backend/agents/authz.py` (GROW: `record_exec_run`) | store-writer | CRUD | `record_hook_run` (:799) | exact |
| `backend/agents/workflows/compiler.py` (GROW) | compiler | transform | self (`_check_trust` :187, ceiling :312) | exact (same file) |
| `backend/agents/workflows/plan.py` (DECIDE) | model | n/a | self (`ExecutionPolicy.check` :172) | exact (delete-or-wire) |
| `backend/agents/execution_engine/engine.py` (GROW: host seam) | engine | request-response | self (RepoSpec/ScopedStore seam ~540-560/720-780) | role-match |
| `backend/app/models/exec_runs.py` (NEW) | model | CRUD | `app/models/hook_runs.py` | exact |
| `backend/alembic/versions/0018_exec_runs.py` (NEW) | migration | CRUD | `0017_repositories_repo_workspace.py` | exact |
| `backend/agents/capabilities/mcp_servers/catalog.py` (GROW: IN-01) | config | n/a | self (slack entry ~86) | exact (same file) |
| `backend/agents/capabilities/deliverables/repo_diff.py` (GROW: IN-03) | deliverable | transform | self (`_split_per_file`/`_flush` :122) | exact (same file) |
| `backend/tests/agents/test_code_validators.py` (NEW) + fixture | test | n/a | `tests/agents/test_gates.py` `_RecordingRunner` (:54) | exact |

## Pattern Assignments

### `backend/app/agents/runtime/local.py` (runtime-impl, transform) — the exec_command rewrite

**Analog:** the file's own `_git` surface (lines 113-131) is the canonical hardened-argv `subprocess.run` shape already in the file. Copy its argv-list + `cwd` + `capture_output=True` + `text=True` + `env` discipline; **add** no-shell already implicit (argv list ⇒ `shell=False`), scrubbed env, `preexec_fn` rlimits, `timeout`, `start_new_session=True`, output truncation, and the recorder callback.

**Three sub-targets in this file:**

1. **`LocalExecutionPolicy` (lines 31-50) — GROW fields.** Today only `exec`/`network`/`secrets`. Add `exec_allow`, `exec_deny`, `cpu_seconds=60`, `mem_mb=512`, `wall_seconds=120` as dataclass fields (RESEARCH locks the cap defaults). Keep `allows()` unchanged for the deny-default (`allows("exec")` returns `self.exec`). Add a `DEFAULT_EXEC_PROFILE` **module-level constant** (allow-list `("python","python3","pytest","ruff")` + caps) per CONTEXT Claude's-discretion — NEVER manifest-tunable.

2. **`LocalWorkspace.exec_command` (lines 183-194) — REWRITE.** Replace the `subprocess.run(command, shell=True)` (IN-02) with the argv-list hardened body (RESEARCH §Pattern 1). Pre-spawn deny check: `cmd in policy.exec_deny or cmd not in policy.exec_allow → PermissionError` (deny beats allow), recorded **before** any spawn. The deny-default `PermissionError` at the top stays byte-identical (T-09-01-02). Port signature changes `command: str → argv: list[str]` — move port + impl + all callers in one task (RESEARCH Runtime State Inventory, "Port signature change (special)").

   Hardened body shape (RESEARCH §Pattern 1, verified against the existing `_git` call at lines 114-130):
   ```python
   _SCRUBBED_ENV_KEYS = ("PATH", "HOME", "TMPDIR")
   env = {k: os.environ[k] for k in _SCRUBBED_ENV_KEYS if k in os.environ}
   def _limits() -> None:
       resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
       resource.setrlimit(resource.RLIMIT_AS, (mem, mem))   # best-effort on darwin
   proc = subprocess.run(argv, cwd=str(self._root), shell=False, env=env,
                         capture_output=True, text=True, timeout=wall,
                         preexec_fn=_limits, start_new_session=True)
   ```
   Document the accepted EGRESS-DENY residual (interpreter can still open sockets) as a code comment at this enforcement point (EGRESS-DENY acceptance criterion).

3. **`create_workspace` (lines 216-238) — exec kwarg goes live.** Today hardcodes `LocalExecutionPolicy(exec=False, ...)` and ignores the `exec` kwarg. Thread `exec=` into the policy + the `DEFAULT_EXEC_PROFILE` allow-list/caps when `exec=True`. Add a `recorder` kwarg (the audit callback) that the workspace closes over and calls in `exec_command`. The workspace stays persistence-import-free (recorder closes over `KernelServices.record_exec_run`).

**Recorder injection note:** the recorder is passed at `create_workspace`, stored on the `LocalWorkspace`, and invoked on EVERY `exec_command` outcome (allowed/denied/killed) — bypass-proof audit at the enforcement point (CONTEXT Claude's-discretion §exec_runs audit seam).

---

### `backend/agents/runtime/base.py` (port, request-response) — signature change only

**Analog:** self (lines 88-90, the `exec_command(command: str)` Protocol method). Change the Protocol signature to `exec_command(self, argv: list[str]) -> Any`. `ExecutionPolicy` Protocol (lines 30-46) gains the new structural fields (`exec_allow`/`exec_deny`/caps) iff the planner types them on the port (optional — Protocol is structural; impl-only fields are allowed). Keep the kernel→ports one-way import direction (this module imports only `typing`).

---

### `backend/agents/capabilities/gates/approval.py` (gate, event-driven HITL) — D-02/D-03/D-04

**Analog:** `gates/human.py` (full file, lines 42-81) — the verbatim HITL-delegation pattern.

**Delegation core (copy human.py:51-81):**
```python
runner = getattr(ctx, "runner", None)
delegate = getattr(runner, "run_human_gate", None)
if delegate is None:                       # offline / no handle → pause (no auto-approve)
    await write_gate_event(ctx, step_id, "approval", GATE_WAIT_HUMAN, None)
    return GateOutcome(outcome=GATE_WAIT_HUMAN)
events, rejected = [], False
async for event in delegate(step, output=payload):   # SAME delegate the human gate uses
    if event.get("type") == "_gate_rejected":
        rejected = True; continue
    events.append(event)
outcome = GATE_BLOCK if rejected else GATE_PASS
await write_gate_event(ctx, step_id, "approval", outcome, None)
return GateOutcome(outcome=outcome, events=events)
```
**Three deltas from human.py:**
- **D-03 first-exec memory** (prepend, before delegating): query `gate_events` via the runner handle for a prior `gate="approval"`/`outcome=GATE_PASS` row → silent `GATE_PASS` (no re-prompt). RESEARCH §Pattern 2 shows the `read_gate_events` shape. No new state field, no migration — the audit trail is the memory.
- **D-04 payload** = exec-policy snapshot dict (step/agent id, allow-list, caps, scrubbed-env note, egress-denied status), passed as `output=`/`payload=` into the delegate. NOT the human gate's `last_streamed` string.
- The current bare `wait_human` stub (lines 34-48) is REPLACED for the exec path.

**Engine-side change (`run_human_gate`):** RESEARCH §D-02 answer recommends **parameterizing** `KernelServices.run_human_gate(self, step, *, output: str = "")` (kernel_services.py:425) with an optional structured `payload`/`kind` arg defaulting to current behavior — ONE HITL mechanism, human-gate string path stays byte-identical (parity).

---

### `backend/agents/capabilities/gates/security.py` (gate, request-response) — profile-conditional pass

**Analog:** self (lines 35-75). Today unconditionally BLOCKs any `wants_exec`/`wants_network`/`wants_secrets` (lines 53-72).

**Delta:** split the `exec` branch from `network`/`secrets`. `network`/`secrets` requested → BLOCK unchanged (lines 53-72 verbatim). `exec` requested → PASS iff (a) file/builtin trust AND (b) a constrained profile is attached (non-empty allow-list + caps), AND (c) the `approval` gate is declared in `step.gates` (D-01 defense-in-depth double-check). Keep the `write_gate_event(... GATE_PASS ...)` tail (line 74). RESEARCH Open Question 2: read the compiled step (trust + `tools.exec` + `step.gates`) for the PASS decision; profile attachment can read `ctx.runner.workspace.policy` if bound. Keep gate kernel-pure (no `app.*` import).

---

### `backend/agents/capabilities/validators/code_compile.py` / `code_test.py` / `code_lint.py` (validator, transform) — NEW

**Analog:** `validators/spec_plan_coverage.py` (full file) — the kernel-side `Validator` template.

**Copy verbatim:**
- Import block (spec_plan_coverage.py:25-27): `Validator` port + `register` + the single `map_severity`.
- `@register("validator", "code_compile", user_allowed=True)` decorator (line 55) — registry auto-grows 50→53; bump the drift-guard `tests/agents/test_registry_capabilities.py:132` `== 50` → `== 53`.
- The `Issue` dataclass (lines 30-34) and `_worst_label`/`map_severity` use (lines 87-94) — NEVER re-derive severity (VALID-03 single source, severity.py:32).
- The `_record(...)` writer (lines 97-109) → `runner.record_validation_result(...)` best-effort.

**Deltas (RESEARCH §Pattern 3):**
- Reach exec via `ws = _workspace(target.runner)` — the SAME handle reach `repo_diff.py:_workspace` uses (lines 100-105: `getattr(runner, "workspace", None)` then `runner` itself). Never `import subprocess` to spawn.
- **VALIDATOR-DENY:** if `ws is None` or exec not granted → return an explicit refusal `Issue` (mapped severity, names the missing grant), `_record`, return — NO spawn (SPEC req 8 acceptance: ≥1 refusal, zero spawns, no `PermissionError` escaping).
- argv targets: `code_compile` → `["python","-m","py_compile",*py_files]`; `code_test` → `["pytest","-p","no:cacheprovider", ...]` (RESEARCH Pitfall 2 pytest-inside-pytest); `code_lint` → `["ruff","check", ...]`. Parse subprocess output → `Issue` list; `PermissionError`/`CalledProcessError` caught and mapped, never escapes.

---

### `backend/agents/authz.py` — `ScopedStore.record_exec_run` (store-writer, CRUD) — NEW METHOD

**Analog:** `record_hook_run` (lines 799-831) — copy the entire body shape.

**Copy:** `session, owned = self._acquire()` → build row with `id=str(uuid.uuid4())`, `run_id`, `owner_id=self._owner_id`, `workspace_id=self._workspace_id` (AUTHZ-01 default-deny scoping), `session.add(row); session.commit(); return row.id` → `finally: if owned: session.close()` (lines 814-831 verbatim).

**Delta (RESEARCH §ScopedStore.record_exec_run):** import `from app.models.exec_runs import ExecRun`; columns: `step`, `argv_json`, `outcome` (allowed|denied|killed), `exit_code`, `duration_ms`, `policy_snapshot_json`, `output_digest` (truncated, never raw secrets).

---

### `backend/agents/execution_engine/kernel_services.py` (service) — `record_exec_run` + `workspace` attr

**Analog:** `record_hook_run` (lines 324-349) — the best-effort handle method.

**Copy the best-effort wrapper verbatim (lines 337-349):**
```python
store = getattr(self._ectx, "scoped_store", None)
if store is None:
    return None
try:
    return await store.record_exec_run(self.run_id, step, argv, outcome, ...)
except Exception as exc:   # noqa: BLE001 — audit must NEVER abort the run
    logger.warning("record_exec_run(...) failed: %s", exc)
    return None
```
(RESEARCH Pitfall 6: best-effort degrade to `None` offline / no FK row.)

**New attribute:** `KernelServices.workspace` (today absent — RESEARCH Pitfall 1). Bound by `engine.execute()` at the host seam when the compiled plan grants exec. Validators reach it via `target.runner.workspace` (the `repo_diff._workspace` reach already supports `getattr(runner, "workspace", None)`).

**`deliverable_context` (lines 396-422)** is the existing target-builder validators receive; `DeliverableContext.runner` (line 103) is the handle reach. No change needed beyond the `workspace` attr being live.

---

### `backend/agents/workflows/compiler.py` (compiler, transform) — trust-conditional ceiling + D-01

**Analogs (same file):** `_check_trust` (lines 187-214) for the user/db `CompilerError` shape; the ceiling site (line 312).

**Three deltas:**
1. **Trust-conditional ceiling (line 312):** `workflow_ceiling = ToolPermissions()` collapses exec OFF for ALL manifests today. Make it trust-conditional: for `file`/`builtin` trust, allow `exec` to survive `intersect_permissions` (line 313); for `user`/`db` trust, a step granting `exec`/`network`/`secrets` → `CompilerError` naming the grant + step (GRANT-PATH). Reuse the `_check_trust` `CompilerError(...)` message shape (lines 208-214).
2. **D-01 gates-required check:** at `_compile_step`, when `step_grant.exec` is True, assert `{"security","approval"} ⊆ set(gates)` else `CompilerError` (RESEARCH: `gates` already resolved at lines 242-245). NO compiler auto-injection (anti-pattern; the compiled plan must mirror the authored manifest).
3. The `trusted = trust in _TRUSTED_SOURCES` (line 153) is the existing trust split to branch on.

---

### `backend/agents/workflows/plan.py` (model) — INV-12 dual-surface resolution

**Analog/target:** `ExecutionPolicy.check` (lines 148-184, the documented "FORWARD SURFACE — NOT yet wired"). RESEARCH Pitfall 5 + Assumption A3: **recommended to DELETE** `ExecutionPolicy.check` (the live enforcement is naturally `LocalExecutionPolicy.allows` + the pre-spawn allow/deny check). `_PRIVILEGED_RUNTIME_ACTIONS` (line 145) may stay if grepped-referenced elsewhere. Either path (delete OR make live) needs a **migration-ledger entry** (Pitfall 5). `ToolPermissions` (lines 46-100) stays unchanged (`exec` field already present, line 67).

---

### `backend/agents/execution_engine/engine.py` (engine) — §15 host seam (RESEARCH Pitfall 1, first-class)

**Analog (same file):** the RepoSpec/MCP host-injection seam (~lines 720-780) and the ScopedStore `create_workspace` call (~lines 540-560).

**Delta:** after the ScopedStore workspace row is created (so `workspace_id` is known), IF the compiled plan has an exec-granted step (`any(s.tools.exec for s in compiled.steps)`), resolve the `runtime_env` capability, call `LocalSandboxRuntime.create_workspace(exec=True, recorder=self.kernel_services.record_exec_run)`, and bind the returned `Workspace` onto `KernelServices.workspace`. This is the FIRST live binding of the runtime_env workspace onto `ctx.runner` (today `engine.execute()` only calls `scoped_store.create_workspace`, the DB-row helper — verified). Gate every new behavior on exec-granted so the 5 characterization snapshots stay byte/event-identical (RESEARCH Pitfall 3). `_run_review_gate` (~line 2391) is the durable HITL machinery the approval delegate already routes through — UNCHANGED.

---

### `backend/app/models/exec_runs.py` (model) — NEW ORM

**Analog:** `app/models/hook_runs.py` (the `HookRun` ORM). Mirror columns to the 0018 migration: `id`, `run_id`, `owner_id`, `workspace_id`, `step`, `argv_json` (JSON), `outcome` (String), `exit_code` (Int, nullable), `duration_ms` (Int, nullable), `policy_snapshot_json` (JSON, nullable), `output_digest` (String, nullable), `created_at` (DateTime).

---

### `backend/alembic/versions/0018_exec_runs.py` (migration) — NEW

**Analog:** `0017_repositories_repo_workspace.py` (lines 1-60). Copy the recipe exactly:
- `revision = "0018"; down_revision = "0017"; branch_labels = None; depends_on = None`.
- `op.create_table("exec_runs", ...)` with `owner_id`/`workspace_id` both `nullable=False` (AUTHZ-01 comment), free `String` for `outcome` (NO `sa.Enum` — R-G additive+reversible, 0017 precedent), `sa.JSON()` for argv/policy_snapshot, `sa.PrimaryKeyConstraint("id")`.
- `downgrade()` → `op.drop_table("exec_runs")` (fully reversible offline against SQLite — SPEC AUDIT acceptance: `upgrade head` → `downgrade -1` → `upgrade head`).
- Add the migration-ledger ratchet entry (0017→0018 chain).

---

### `backend/agents/capabilities/mcp_servers/catalog.py` (config) — IN-01 sign-off doc

**Analog/target:** the `SlackMcpServer` entry (verified ~line 86, `user_allowed=True`, `exposed_tools={"post_message","list_channels"}`, `scope="slack_post"`). Add the MCP-04 sign-off docstring/comment near the `user_allowed=True` gating (RESEARCH §IN-01 code example): document that `post_message` is the ONE user-grantable WRITE on the user palette, accepted because post-only scope + same gate/audit path. Comment-only change (no behavior).

---

### `backend/agents/capabilities/deliverables/repo_diff.py` (deliverable, transform) — IN-03 synthetic-key fallback

**Analog/target:** `_split_per_file` + its inner `_flush` (lines 122-134, verified). Today `_flush` drops the block when `current_path is None` (line 123: `if current_path is not None and current_lines`), silently losing a file under a quoted/rename `diff --git` header. **Fix (RESEARCH §IN-03 code example):** when `current_path is None` but `current_lines` exist, assign a synthetic key `f"__unparsed_{idx}__"` so no changed file is dropped. Unit test: feed a quoted `diff --git "a/has space.py" "b/has space.py"` or rename header and assert the block appears under the synthetic key (SPEC DEBT+PARITY acceptance).

---

### `backend/tests/agents/test_code_validators.py` + fixture (test) — NEW

**Analogs:**
- `tests/agents/test_gates.py` `_RecordingRunner` (verified line 54): a runner stub recording `gate_events` and exposing `run_human_gate` — copy for the approval-gate scripting (D-02 directive). Approve/reject scripted by the events the stub's `run_human_gate` yields (`{"type":"review_gate_approved"}` / `{"type":"_gate_rejected"}`) per RESEARCH §Offline test scripting.
- Engine-level durable pause: `store.set_review_response(gate_key, approved=True|False)` (RESEARCH §test precedent).
- `tests/agents/fixtures/sample_brownfield/` — precedent for the NEW `tests/agents/fixtures/sample_python_repo/` (tiny compile+test fixture + a seeded lint error). Keep it tiny; run validators' subprocesses bounded by the policy caps; invoke pytest with `-p no:cacheprovider` (RESEARCH Pitfall 2).
- Run via the targeted offline suite, never full pytest (backend/CLAUDE.md / MEMORY offline-test-suite note).

## Shared Patterns

### Best-effort owner/workspace-scoped audit write
**Source:** `kernel_services.py:324-349` (`record_hook_run`) → `authz.py:799-831` (`ScopedStore.record_hook_run`).
**Apply to:** `record_exec_run` (engine handle + store writer). MUST degrade to `None` on any exception (`# noqa: BLE001 — audit must never abort the run`); rows carry `owner_id`+`workspace_id` from the run's ScopedStore (default-deny reads, cross-owner returns nothing).

### Capability reaches power via the handle, never by import
**Source:** `repo_diff.py:100-105` (`_workspace`), `spec_plan_coverage.py:99-109` (`_record` via `target.runner`).
**Apply to:** all three code validators (reach exec via `target.runner.workspace`, write `validation_results` via `runner.record_validation_result`), the approval gate (`ctx.runner.run_human_gate` + `gate_events` read), the security gate (`write_gate_event` via `ctx.runner`). Keeps import-linter 4/0 (no `agents.capabilities → agents.execution_engine`/`app`).

### Single severity source (VALID-03)
**Source:** `validators/severity.py:32` (`map_severity`).
**Apply to:** all three code validators — import it, never re-derive the P0→CRITICAL ladder.

### Gate outcome + gate_events write
**Source:** `gates/human.py:79-81`, `gates/security.py:74` (`write_gate_event(ctx, step_id, name, outcome, detail)` → `GateOutcome(outcome=..., events=...)`).
**Apply to:** the grown approval + security gates — every evaluation writes a `gate_events` row (D-03 memory + SPEC GATES acceptance).

### Additive, reversible migration (Q3 / R-G)
**Source:** `alembic/versions/0017_*.py:1-60` (table-first, free `String` not `sa.Enum`, `owner_id`/`workspace_id` NOT NULL, reverse `drop_table` downgrade).
**Apply to:** `0018_exec_runs.py` + the migration-ledger ratchet entries (0018 chain, IN-02 `shell=True` closure, plan.py forward-surface deletion).

### Three-layer enforcement, each gated on exec-granted (parity)
**Source:** the locked design — compiler ceiling (`compiler.py:312`) → gate (`security.py`) → workspace policy (`local.py`).
**Apply to:** every new behavior is dormant unless the compiled plan grants exec, so the 5 characterization snapshots stay byte/event-identical with `SNAPSHOT_UPDATE` unset (RESEARCH Pitfall 3 / SPEC DEBT+PARITY).

## No Analog Found

None. Every new/grown file has an exact in-tree precedent. The only net-new design — the hardened `exec_command` subprocess body — derives from the file's own `_git` argv `subprocess.run` shape (local.py:113-131) plus stdlib `resource`/`os` primitives (RESEARCH §Pattern 1, all verified offline).

## Metadata

**Analog search scope:** `backend/app/agents/runtime/`, `backend/agents/{runtime,capabilities,workflows,execution_engine}/`, `backend/agents/authz.py`, `backend/alembic/versions/`, `backend/tests/agents/`.
**Files scanned/read:** local.py, runtime/base.py, gates/{human,approval,security}.py, validators/{spec_plan_coverage,severity}.py, kernel_services.py, authz.py, compiler.py, plan.py, repo_diff.py, catalog.py, 0017 migration, test_gates.py.
**Pattern extraction date:** 2026-06-10
