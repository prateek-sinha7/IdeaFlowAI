---
phase: 10-safe-local-exec-gated-on-n3-4b
plan: 03
subsystem: security
tags: [exec, security-gate, approval, hitl, gate-events, host-seam, runtime, d-01, d-02, d-03, d-04]

# Dependency graph
requires:
  - phase: 10-safe-local-exec-gated-on-n3-4b
    plan: 01
    provides: "Hardened argv exec_command + LocalExecutionPolicy (allow/deny + caps) + DEFAULT_EXEC_PROFILE + live create_workspace(exec, recorder) + KernelServices.record_exec_run handle + KernelServices.workspace attr (None until bound)"
  - phase: 10-safe-local-exec-gated-on-n3-4b
    plan: 02
    provides: "Trust-conditional compiler ceiling (file/builtin exec survives intersect) + D-01 gates-required CompilerError (an exec step MUST declare security+approval) + user/db privileged-grant hard-fail"
  - phase: 08-capability-hardening
    provides: "GateHandler registry + human-gate HITL delegation pattern (run_human_gate -> _run_review_gate) + write_gate_event + ScopedStore.record_gate_event/read_gate_events default-deny"
provides:
  - "Profile-conditional security gate — file/builtin exec with approval declared + a constrained profile PASSES; network/secrets BLOCK byte-identical; exec without approval BLOCKS (D-01 second line)"
  - "Approval gate on the ONE durable HITL mechanism (D-02) — run_human_gate delegation with the D-04 policy-snapshot payload; D-03 read_gate_events first-exec memory short-circuits the second exec step"
  - "Parameterized KernelServices.run_human_gate(step, *, output='', payload=None) — the structured snapshot rides the generic review_gate_ready output field (no frontend rebuild); payload=None is byte-identical to the human-gate path"
  - "KernelServices.read_gate_events(run_id) best-effort handle delegating to ScopedStore.read_gate_events (offline -> [])"
  - "§15 host seam — engine.execute() binds the runtime_env('local') exec-enabled Workspace onto KernelServices.workspace ONLY for exec-granting plans (Pitfall 1 first-class wiring)"
affects: [10-04-exec-validators, dynamic-composer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Profile-conditional gate PASS — tier 2 of the 3-tier exec stack: the runtime second line after the compiler ceiling, reading trust + tools.exec + step.gates + the bound workspace policy"
    - "ONE HITL mechanism (D-02): run_human_gate parameterized with an optional structured payload, NOT a sibling run_approval_gate; the engine _run_review_gate stays UNCHANGED and forwards whatever output value it receives"
    - "Durable first-exec memory (D-03): a prior approval-pass gate_events row short-circuits the re-pause — no new state field, no migration, survives restart (the table is persisted + scoped)"
    - "Exec-conditional host-seam provisioning (Pitfall 3): the runtime workspace is bound ONLY when the compiled plan grants exec, so non-exec runs stay byte/event-identical"

key-files:
  created: []
  modified:
    - "backend/agents/capabilities/gates/security.py — split exec branch (profile-conditional PASS + D-01 approval-declared double-check + _ENGINEER_TRUST check + _block_exec helper) from the byte-identical network/secrets BLOCK path"
    - "backend/agents/capabilities/gates/approval.py — rewrote evaluate to the HITL delegation body (D-02) + D-03 read_gate_events short-circuit + module-level _exec_policy_snapshot D-04 payload helper + offline wait_human path"
    - "backend/agents/execution_engine/kernel_services.py — parameterized run_human_gate with payload kwarg + new read_gate_events best-effort handle"
    - "backend/agents/execution_engine/engine.py — §15 host-seam block in execute(): _plan_grants_exec detection + runtime_env('local') resolution + create_workspace(exec=True, recorder=...) + bind onto KernelServices.workspace, OSError-only degrade"
    - "backend/tests/agents/test_gates.py — grew the _RecordingRunner (payload-recording async-generator run_human_gate + read_gate_events + bound workspace) + _ExecPolicy/_Workspace/_GateRow fakes; 7 new security + 5 approval + 5 kernel_services/host-seam tests"

key-decisions:
  - "Step trust read defensively via getattr(step, 'trust', 'file'): the compiled Step has NO trust attribute (trust is a compile-time concept the compiler already enforces in 10-02 — a user/db exec grant hard-fails at compile). An exec grant reaching the gate is therefore engineer-authored, so the gate defaults trust to file and the _ENGINEER_TRUST check is the runtime echo of the compile-time bound (defense-in-depth, not the primary enforcement)"
  - "Unbound-workspace profile check: when ctx.runner.workspace is None at gate time, do NOT block (RESEARCH Open Question 2) — profile presence is implied by the exec-conditional §15 provisioning that binds the workspace before the step runs; the gate only blocks on a BOUND workspace carrying an EMPTY allow-list"
  - "payload supersedes output in run_human_gate (review_payload = payload if payload is not None else output): the structured dict rides the SAME review_gate_ready.data.output field via the unchanged _run_review_gate, so D-04 needs no frontend rebuild and the human-gate string path stays byte-identical (parity)"
  - "Host-seam degrade is OSError-only (mirrors the _scope_exc SQLAlchemyError discipline): an offline-harness missing runs-root degrades; a real provisioning bug (unknown-cap KeyError, registry RuntimeError) re-raises so an exec run that cannot provision is never silently no-op'd"
  - "Host seam placed right after the KernelServices construction (not after scoped_store.create_workspace as the plan's prose suggested): the binding target KernelServices.workspace and the compiled plan are both only available there — workspace_id (set earlier) + owner_id + compiled.steps are all in scope at that point"

patterns-established:
  - "Profile-conditional security gate — tier 2 of the 3-tier exec stack (compiler ceiling -> THIS gate -> workspace policy)"
  - "Approval gate = D-02 single-mechanism HITL delegation + D-03 durable memory + D-04 honest-bound payload (allow-list, NOT argv)"

requirements-completed: [EXEC-01]

# Metrics
duration: ~22min
completed: 2026-06-10
---

# Phase 10 Plan 03: Security/Approval Gate Layer + §15 Host Seam Summary

**Tier 2 of the 3-tier exec stack: a profile-conditional `security` gate (file/builtin exec with `approval` declared + a constrained profile PASSES; network/secrets BLOCK byte-identical; exec without approval BLOCKS — D-01) and an `approval` gate on the ONE durable HITL mechanism (`run_human_gate` -> `_run_review_gate`) carrying the D-04 policy-snapshot payload with D-03 durable first-exec memory — plus the §15 host seam that binds the exec-enabled runtime workspace onto `KernelServices.workspace` ONLY for exec-granting plans. Dormant for every existing non-exec run.**

## Performance

- **Duration:** ~22 min
- **Tasks:** 2 (Task 1 TDD)
- **Files modified:** 5 (0 created, 5 modified)

## Accomplishments
- **SecurityGate (tier 2):** the exec branch is split from network/secrets. A file/builtin-trust step with `tools.exec=True`, `approval` in `step.gates`, and a constrained profile (bound workspace policy with a non-empty allow-list, OR an unbound workspace at gate time — profile implied by the §15 provisioning) returns `GATE_PASS`. `network`/`secrets` requests BLOCK on the byte-identical pre-10-03 path (same detail + `gate_blocked` event — T-10-03-02). An exec step WITHOUT `approval` declared is NOT a silent pass — it BLOCKS (D-01 defense-in-depth, T-10-03-01).
- **ApprovalGate (HITL + memory):** the bare `wait_human` stub is replaced with the `human.py` delegation body routing through `ctx.runner.run_human_gate` -> the engine's unchanged `_run_review_gate` (D-02 ONE mechanism). D-03: a prior `gate="approval"`/`outcome="pass"` row (read via `ctx.runner.read_gate_events`) short-circuits the second exec step to a silent PASS with NO re-pause. D-04: the `_exec_policy_snapshot` helper builds the payload (step/agent id, exec allow-list, caps, scrubbed-env note, egress-denied) from the bound policy — no creds, no argv preview (the allow-list IS the honest bound, T-10-03-06). Offline (no handle) -> `GATE_WAIT_HUMAN`, never auto-approve.
- **Parameterized `run_human_gate`:** now `(self, step, *, output: str = "", payload: dict | None = None)` — the structured snapshot rides the SAME generic `review_gate_ready.data.output` field (D-04, no frontend rebuild); `payload=None` is byte-identical to the human-gate string path (parity). No sibling `run_approval_gate` (rejected — second surface). New `read_gate_events(run_id)` best-effort handle delegates to `ScopedStore.read_gate_events` (offline -> `[]`, mirrors `record_hook_run` degrade).
- **§15 host seam (Pitfall 1 first-class):** `engine.execute()` now binds the runtime workspace. `_plan_grants_exec = any(s.tools.exec for s in compiled.steps)` gates the entire block: when granted, resolve `("runtime_env","local")`, call `create_workspace(exec=True, recorder=KernelServices.record_exec_run)`, bind onto `KernelServices.workspace`. Non-exec runs never provision (the workspace stays `None`), so the 5 characterization snapshots are byte/event-identical (T-10-03-05 / Pitfall 3).
- **Parity preserved:** 5 characterization snapshots byte/event-identical (10 tests); banned-patterns 11; lint-imports 4 kept / 0 broken (both gates stay kernel-pure — registry decorator + outcome contract + `write_gate_event` only; the engine seam reaches the runtime via the registry, no new app import in the gate path).

## Task Commits

1. **Task 1 (TDD): profile-conditional security gate + approval HITL delegation (D-01/D-02/D-03/D-04)** - `73453b8` (feat)
   - TDD: the new behaviors were written as tests + impl together (both gates touch one evaluate site each; the test fakes drive approve/reject/no-re-pause/offline). All 24 gate tests green at this commit.
2. **Task 2: parameterize run_human_gate + read_gate_events handle + §15 host-seam workspace wiring** - `3b77221` (feat)
   - 31 gate tests green (added the run_human_gate payload/parity + read_gate_events offline/degrade/delegate + host-seam exec-grant detection + bound-profile tests).

**Plan metadata:** (this docs commit)

## Files Created/Modified
- `backend/agents/capabilities/gates/security.py` (modified) - exec branch split from network/secrets; `_ENGINEER_TRUST` trust check + D-01 approval-declared double-check + bound-profile allow-list check; `_block_exec` helper; network/secrets BLOCK byte-identical
- `backend/agents/capabilities/gates/approval.py` (modified) - `evaluate` rewritten to the HITL delegation body (D-02) with the D-03 `read_gate_events` short-circuit and the offline `wait_human` path; module-level `_exec_policy_snapshot` (D-04)
- `backend/agents/execution_engine/kernel_services.py` (modified) - `run_human_gate` gains the `payload` kwarg (threads into the review output field); new `read_gate_events` best-effort handle
- `backend/agents/execution_engine/engine.py` (modified) - §15 host-seam block in `execute()`: `_plan_grants_exec` detection + `runtime_env('local')` resolution + `create_workspace(exec=True, recorder=...)` bound onto `KernelServices.workspace`, OSError-only degrade
- `backend/tests/agents/test_gates.py` (modified) - grew `_RecordingRunner` (async-generator `run_human_gate` recording the payload + `read_gate_events` + bound `workspace`); `_ExecPolicy`/`_Workspace`/`_GateRow`/`_NoHandleRunner`/`_FakeReviewEngine` fakes; 17 new tests across the listed behaviors

## Decisions Made
- **Step trust read defensively** (`getattr(step, "trust", "file")`): the compiled `Step` has no `trust` field — trust is a compile-time concept the compiler already enforces (10-02 hard-fails a user/db exec grant). An exec grant reaching the gate is engineer-authored, so the gate defaults trust to `file`; the `_ENGINEER_TRUST` check is the runtime echo of the compile-time bound (defense-in-depth).
- **Unbound-workspace profile check does NOT block** (RESEARCH Open Question 2): profile presence is implied by the exec-conditional §15 provisioning; the gate only blocks on a BOUND workspace with an EMPTY allow-list.
- **`payload` supersedes `output`** in `run_human_gate`: the dict rides the same `review_gate_ready.data.output` field via the unchanged `_run_review_gate` — D-04 needs no frontend rebuild and the human-gate string path stays byte-identical.
- **Host-seam degrade is OSError-only** (mirrors `_scope_exc`): an offline-harness missing runs-root degrades; a real provisioning bug re-raises.
- **Host seam placed after the KernelServices construction** (not after `scoped_store.create_workspace` as the plan prose suggested): the binding target (`KernelServices.workspace`) and the `compiled` plan are both only available there; `workspace_id`/`owner_id`/`compiled.steps` are all in scope.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_block_exec` helper called without `await`**
- **Found during:** Task 1 (security gate authoring)
- **Issue:** The first draft of `security.py` defined `_block_exec` as `async def` but the three exec-refusal branches `return self._block_exec(...)` returned the coroutine (un-awaited) — the gate would return a coroutine instead of a `GateOutcome`, breaking every exec-block test.
- **Fix:** Changed the three call sites to `return await self._block_exec(...)`.
- **Files modified:** backend/agents/capabilities/gates/security.py
- **Verification:** all security exec-BLOCK tests (missing-approval, empty-profile, non-engineer trust) PASS.
- **Committed in:** `73453b8` (Task 1 commit)

**2. [Note - placement] Host seam location vs. plan prose**
- **Found during:** Task 2 (host seam)
- **Issue:** The plan said to add the §15 block "RIGHT AFTER the `scoped_store.create_workspace(pipeline_run_id)` block." But the binding target (`KernelServices.workspace`) does not exist until the `KernelServices(...)` construction (~480 lines later), and the `compiled` plan (`compiled.steps`) is only available after `compile_for_run`. Placing the block at the plan's suggested line would have nothing to bind onto and no compiled plan to inspect.
- **Resolution:** Placed the block immediately after the `KernelServices(...)` construction, where `workspace_id` (set earlier), `owner_id`, and `compiled.steps` are all in scope. This honors the plan's INTENT (exec-conditional, after the scoped workspace row is known) — not a behavioral deviation.
- **Files modified:** backend/agents/execution_engine/engine.py

---

**Total deviations:** 1 auto-fixed (Rule 1 bug — missing `await`) + 1 placement clarification (no behavior change).
**Impact on plan:** None on scope. Both gates stayed kernel-pure; `_run_review_gate` is UNCHANGED; non-exec runs are byte/event-identical.

## Issues Encountered
- The full offline backend pytest hangs (Chromium/Bedrock/Postgres-gated per backend/CLAUDE.md) — verified with the targeted suite (test_gates + characterization×5 + banned_patterns + lint-imports), per the offline-test-suite memory note.

## Deferred Issues
None — no out-of-scope discoveries. (The Phase-9 `workspaces.repo_id` alembic-check drift noted in 10-01 is untouched by this plan, which makes no migration/ORM change.)

## Known Stubs
None — no stub patterns introduced (gate logic + handle parameterization + engine seam only; no UI/data wiring).

## Threat Flags
None — every surface this plan touches (the profile-conditional exec gate, the approval HITL delegation, the §15 host-seam workspace binding) is already in the plan's `<threat_model>` (T-10-03-01..06, T-10-03-SC). Zero external packages added (T-10-03-SC: N/A confirmed — gate + engine edits only).

## Verification Evidence
- `tests/agents/test_gates.py` — 31 passed (security exec PASS/BLOCK + network/secrets BLOCK + D-01; approval first-exec pause/approve/reject/no-re-pause/offline; run_human_gate payload/parity + read_gate_events offline/degrade/delegate + host-seam exec-grant detection + bound profile)
- `tests/agents/test_characterization_*.py` — 10 passed (5 snapshots byte/event-identical; host seam + gate changes dormant for non-exec runs — `SNAPSHOT_UPDATE` unset)
- `tests/agents/test_banned_patterns.py` — 11 passed (no kernel workflow-name/agent-id branch reintroduced by the host seam — INV-1)
- `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken (gates stay kernel-pure; the engine binding uses the registry, no new app import in the gate path)

## Next Phase Readiness
- Tier 2 of the 3-tier exec stack is built: the runtime now PASSES a constrained file/builtin exec step (approval declared + profile attached), the first exec per run pauses for a durable HITL sign-off with the D-04 policy snapshot, and the exec-enabled runtime workspace is bound onto `KernelServices.workspace` for exec-granting runs only.
- **10-04** adds tier 3's consumers — the compile/test/lint validators that reach exec through `target.runner.workspace.exec_command(argv)` (the binding this plan made live), plus the IN-02/forward-surface enforcement ledger rows.

---
*Phase: 10-safe-local-exec-gated-on-n3-4b*
*Completed: 2026-06-10*

## Self-Check: PASSED

All 5 modified files exist on disk; both task commits (`73453b8`, `3b77221`) are in git history; 31 gate tests + 10 characterization + 11 banned-pattern tests pass; lint-imports 4 kept / 0 broken.
