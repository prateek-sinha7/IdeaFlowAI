# Phase 10: Safe Local Exec (gated on N3) [4B] - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning
**Mode:** SPEC-first (10-SPEC.md written the same day via /gsd-spec-phase — the N3 threat model is RESOLVED there). One HOW gray area deep-dived interactively (Approval-gate wiring, 4 decisions); the other three (profile home, validator placement, audit seam) locked to Claude's-discretion recommendations below.

<domain>
## Phase Boundary

Code execution flips from unconditionally-denied (four independent OFF layers left by Phase 9) to a **constrained, audited, engineer-only exec profile**: argv-only hardened subprocess (no shell), Python-toolchain allow-list (`python`/`python3`/`pytest`/`ruff`), scrubbed minimal env (the v1 ephemeral-creds posture), POSIX rlimits + wall-clock kill, egress denied at policy+allow-list+env level — runnable only behind the `security` gate PLUS a first-exec-per-run human `approval` gate. Three code validators (`code_compile`/`code_test`/`code_lint`) land on gated exec and prove the profile by passing against the local Python fixture repo offline with zero engine edits. Every exec invocation (allowed/denied/killed) writes an owner/workspace-scoped `exec_runs` audit row (additive migration 0018). The Phase 9 review trio (IN-01 slack_post sign-off, IN-02 shell=True, IN-03 repo_diff header drop) closes here.

**What this phase is NOT:** no containers/Docker/ECS (v2 behind the unchanged `RuntimeEnvironment` port), no OS-level network namespaces (policy-level egress denial with documented accepted residual), no `network`/`secrets` permission enablement (still gate-blocked), no PR/commit push (N4), no user-grantable exec (user/db manifests compile-blocked), no non-Python toolchains, no fan-out (Phase 11), no Windows.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**9 requirements are locked** (EXEC-PROFILE, EXEC-POLICY, EGRESS-DENY, GRANT-PATH, GATES, AUDIT, VALIDATORS, VALIDATOR-DENY, DEBT+PARITY). See `10-SPEC.md` for full requirements, boundaries, and 14 acceptance criteria. Ambiguity 0.14 (gate ≤ 0.20); **the N3 decision record is resolved in the SPEC's interview log** (hardened subprocess / policy+allow-list egress / Python toolchain / scrubbed-env creds / security+approval gates / trust-conditional ceiling / cap defaults cpu=60s mem=512MB wall=120s output=64KB, deny beats allow).

Downstream agents MUST read `10-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):** N3 resolution record (flip N3 to decided in STATE/PROJECT) · hardened-subprocess exec profile in `LocalWorkspace` · live `ExecutionPolicy` fields (`exec_allow`/`exec_deny`/caps, deny-precedence, runtime-owned not manifest-tunable) · trust-conditional compiler ceiling (user/db exec/network/secrets grant → `CompilerError`) · SecurityGate evolution + first-exec approval pause · `exec_runs` table (0018) + ScopedStore writer · `code_compile`/`code_test`/`code_lint` validators + fixture sample + exec-denied refusal · IN-01/02/03 closure · characterization parity + import-linter/banned-pattern/migration-ledger discipline.

**Out of scope (from SPEC.md):** containers/ECS isolation · OS-level network enforcement · `network_allow` implementation · `secrets` enablement / cred-vendor seam · PR/commit push (N4) · user-grantable exec · non-Python toolchains · warm pools / long-job substrate (N8) · Windows · fan-out/`spawn_subagents` (Phase 11).

</spec_lock>

<decisions>
## Implementation Decisions

### Approval-gate wiring (deep-dived — the one user-selected area)

- **D-01: Acquisition = manifest-declared + compiler-enforced.** An exec-granting step MUST declare `gates: [security, approval]` in its manifest; the compiler raises `CompilerError` when a step grants `tools.exec` without BOTH gates declared. Explicit and INV-5-pure — the compiled plan mirrors the authored manifest, zero kernel magic, and an unguarded exec step is unauthorable. The SecurityGate additionally double-checks the approval gate is present in the step's gate list (cheap defense in depth, no kernel edit).
  - *Rejected:* compiler auto-injection (compiled plan ≠ authored manifest — hidden behavior); kernel runtime check (plants exec-special-casing back into the kernel — the hardwired-branch pattern this project removes).

- **D-02: Pause/resume = delegate to the existing review-gate HITL machinery** (the `human` gate precedent, `gates/human.py`): the `approval` gate's `evaluate()` routes through a `ctx.runner` handle delegate to the engine's `_run_review_gate`-style durable pause (checkpointer-backed, WS-driven), resolving approve→`pass` / reject→`block` **inline within the same run** — the step executes immediately on approval. ONE HITL mechanism in the codebase; an approval-flavored payload distinguishes it from content review. The current stub behavior (bare `wait_human` → engine halts/skips the step) is replaced for the exec path.
  - *Rejected:* keep halt + run-level resume (builds a second approval/resume surface; step-granular resume is Phase 12 RESUME-02/03 and doesn't exist yet); pre-run approval (approver decides blind, diverges from the SPEC's locked "first exec step pauses" wording).
  - *Researcher directive:* confirm how `_run_review_gate` / `run_human_gate` threads the WS approve/reject action and the checkpointer durability, and what an approval-flavored delegate needs (new handle method vs parameterized `run_human_gate`) so the `review_gate_*` parity path stays untouched while the approval events are distinguishable. Confirm how offline tests script the approve/reject (existing review-gate test precedent).

- **D-03: First-exec memory = durable `gate_events` lookup.** The approval gate (via the runner handle) queries the run's `gate_events` for an existing approval-pass row → silently `pass`; else pause. Durable across restarts (persisted owner/workspace-scoped table from 08-02), no new state field, no migration — the audit trail doubles as the memory. Satisfies the SPEC-locked "subsequent exec steps in the same run don't re-prompt".
  - *Rejected:* `ectx` flag (forgets on restart); flag+backstop hybrid (marginal benefit for extra code — the lookup is one indexed query per exec step).

- **D-04: Approval payload = exec policy snapshot.** The pause payload carries what the approver is actually signing off on: step/agent id, the exec allow-list, resource caps, scrubbed-env note, egress-denied status. Rides the existing `review_gate_*`/`gate_*` event shapes (generic `websocket.py` forward — no frontend rebuild); offline tests script approve/reject like existing review-gate tests.
  - *Rejected:* generic "step X requests exec" (blind sign-off); full command preview (argv is constructed dynamically at execution time — a faithful preview isn't knowable at the gate; the allow-list IS the honest bound).

### Claude's Discretion (areas the user did not select — locked to these recommendations; planner may refine within them)

- **Exec profile home + provisioning:** profile values (allow-list, caps) live as **module-level constants in the runtime impl** (`app/agents/runtime/local.py` — e.g. a `DEFAULT_EXEC_PROFILE`), optionally overridable via `settings` if a config knob is trivial to add; NEVER manifest-tunable (SPEC constraint). Provisioning: the run-entry host seam (the §15 RepoSpec-injection precedent) provisions the workspace with `exec=True` **iff the compiled plan contains an exec-granted step** — `create_workspace(exec=...)` stops being ignored and threads the constrained profile into `LocalExecutionPolicy`. The plan.py `ExecutionPolicy.check` forward-surface helper should either become the live check or be deleted (no dual policy surfaces — INV-12; planner decides which after reading both).
- **Validator placement + exec access:** `code_compile`/`code_test`/`code_lint` are **kernel-side** (`agents/capabilities/validators/`, beside `spec_plan_coverage`/`task_done_when`) — they are pure-stdlib (argv construction + output parsing) and reach exec **only via the runner/workspace handle** (`target.runner` on `DeliverableContext`, the 08-04 pattern). They never import `app.*` (import-linter) and never spawn directly.
- **`exec_runs` audit seam:** the audit write happens **at the enforcement point** — `LocalWorkspace.exec_command` itself records every invocation (allowed/denied/killed) via a **recorder callback injected at `create_workspace`** (the workspace stays persistence-import-free; the recorder closes over the ScopedStore writer, mirroring how gate/hook writes route through `ctx.runner`). This is bypass-proof: any caller reaching `exec_command` is audited regardless of path. A `KernelServices.record_exec_run` method backs the callback (the `record_hook_run` precedent).
- Registry count goes 50→53 (`validator:code_compile`/`code_test`/`code_lint`) with the lockstep drift-guard updated; whether the SecurityGate's profile check reads the workspace policy or the compiled step is planner's call (gate evaluates the step + ctx it's given).
- Exact `exec_runs` column types/digest format within the SPEC's listed fields; 0018 migration follows the 0017 offline-reversibility recipe.
- Plan count/split for the phase (ROADMAP sketches 10-01 exec profile + 10-02 validators; planner may keep 2 or split finer) — sequential execution (worktrees broken in this repo).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/10-safe-local-exec-gated-on-n3-4b/10-SPEC.md` — the 9 locked requirements, boundaries, 14 acceptance criteria, cap defaults, and the **N3 decision record** (interview log). **Locked requirements — MUST read before planning.**

### The specification (authoritative — nothing in it may be dropped)
- `specs/003-workflow-engine-decoupling/plan.md` **§8 (lines ~535–556)** — tool permission policy: exec OFF default, `Workspace.ExecutionPolicy` gates exec/network/secrets at runtime, AGENT.md may only lower; **§6 (lines ~425–446)** — the `ToolPermissions`/`ExecutionPolicy` dataclass spec (`exec_allow`/`exec_deny`/`network_allow`/`cpu_seconds`/`mem_mb`); **§9 (lines ~558–570)** — gate registry (`approval` = "explicit sign-off before a sensitive action (e.g. … first `exec`)"; `security` ties N3); **§14 (lines ~652–661)** — Phase 4B = exec + compile/test/lint validators behind the security gate; **§16 (lines ~678–686)** — validation framework (generic fix-loop, severity mapping, `validation_results`); **§18 (lines ~697–717)** — persistence schema pattern for the new `exec_runs` table (owner_id+workspace_id, additive); **§25 (lines ~842–845)** — Phase 4B accept wording; **§26 (line ~867)** — the N3 decision record this phase resolves; R5/R9 risk rows.
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — the ratchet; IN-02 (shell=True) closure and any deleted forward-surface (plan.py `ExecutionPolicy.check`) need ledger entries.

### Project planning
- `.planning/REQUIREMENTS.md` — EXEC-01/EXEC-02 (lines ~112–115) + traceability row (Phase 10 [4B]).
- `.planning/ROADMAP.md` § Phase 10 — goal, 2 success criteria, sketched plans 10-01/10-02.
- `.planning/STATE.md` — the pending-todo block naming IN-01/02/03 for Phase 10; N3 blocker row (flip to resolved at transition).
- `.planning/phases/09-local-workspace-runtime-repo-workflows-no-exec-4a/09-REVIEW.md` §Info (lines ~235–263) — the exact IN-01/IN-02/IN-03 finding text + fix guidance.

### Prior phase context (patterns this phase extends)
- `.planning/phases/09-local-workspace-runtime-repo-workflows-no-exec-4a/09-CONTEXT.md` — runtime port/impl split (D-01/D-02 there), KernelServices-handle discipline, offline-fixture accept convention.
- `.planning/phases/08-capabilities-hardened-registry-gates-tool-perms-runtime-3/08-CONTEXT.md` — gate registry + validator framework + `@register`/lockstep-count patterns this phase grows.

### Code to read (targets / assets)
- `backend/app/agents/runtime/local.py` — `LocalExecutionPolicy` (grows allow/deny/caps), `LocalWorkspace.exec_command` (the rewrite target: argv/no-shell/scrub/rlimits/timeout/truncation + audit recorder), `create_workspace` (the ignored `exec` kwarg goes live).
- `backend/agents/runtime/base.py` — `ExecutionPolicy`/`Workspace` ports (`exec_command(command: str)` signature changes to argv — port + impl + callers move together).
- `backend/agents/capabilities/gates/security.py` — the unconditional-block gate that becomes profile-conditional for exec (network/secrets stay blocked).
- `backend/agents/capabilities/gates/approval.py` + `gates/human.py` — the stub to upgrade (D-02) and the HITL-delegation pattern to copy (`ctx.runner.run_human_gate`).
- `backend/agents/execution_engine/engine.py` — `_evaluate_gates` + the pre-step gate loop (~lines 1145–1165: `wait_human` currently halts/skips — D-02 changes the approval path); `_run_review_gate` (the durable HITL machinery to delegate to); the run-entry host seam (~lines 540–560 workspace creation, ~720–780 RepoSpec/MCP injection precedents).
- `backend/agents/execution_engine/kernel_services.py` — `KernelServices` (gains `record_exec_run` + the approval delegate if a new method is needed); `DeliverableContext`/`FixPolicy` (validators receive `target.runner`).
- `backend/agents/workflows/compiler.py` — `workflow_ceiling = ToolPermissions()` (line ~313, the compile-time exec collapse → trust-conditional); `_compile_tool_grant`; the trust path for the user/db `CompilerError`; the D-01 gates-required check site.
- `backend/agents/workflows/plan.py` — `ToolPermissions` (live), `ExecutionPolicy.check` (the unwired forward surface — make live or delete, INV-12), `_PRIVILEGED_RUNTIME_ACTIONS`.
- `backend/agents/capabilities/validators/{severity,spec_plan_coverage,task_done_when}.py` — the kernel-side validator pattern + the single `map_severity` the three code validators reuse.
- `backend/agents/capabilities/mcp_servers/catalog.py` (~lines 86–94) — the slack_post `user_allowed=True` write exception (IN-01 sign-off doc site).
- `backend/agents/capabilities/deliverables/repo_diff.py` (~lines 122–148) — `_split_per_file` (IN-03 synthetic-key fallback site).
- `backend/alembic/versions/0017_*.py` — the additive-migration recipe 0018 (`exec_runs`) follows; `backend/agents/` ScopedStore (gate_events/hook_runs writers) for the exec_runs writer.
- `backend/tests/agents/test_characterization_*.py` + `test_migration_ledger.py` + `test_banned_patterns.py` + `/opt/homebrew/bin/lint-imports` — the parity/ratchet gates (5 snapshots byte/event-identical, lint 4 kept/0 broken).
- `backend/CLAUDE.md` — dev runtime `python3.11` (no venv); targeted offline suite (full pytest hangs offline); commit scopes.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`LocalWorkspace`/`LocalExecutionPolicy` (`app/agents/runtime/local.py`)** — exec is a one-method rewrite inside an existing, registered runtime; policy grows fields, no new abstraction needed.
- **Gate registry + `write_gate_event` (08-02)** — security/approval gates already registered + persisting `gate_events` rows; D-03's first-exec memory reads the same table.
- **`_run_review_gate` HITL machinery + `run_human_gate` handle delegate** — the ONE durable pause/resume surface; D-02 delegates the approval gate to it (the `human` gate already proves the pattern).
- **Validator framework (08-04)** — `Validator` port, `DeliverableContext.runner`, `map_severity`, `validation_results` writer: the three code validators drop in beside `spec_plan_coverage`.
- **ScopedStore + additive migrations (0014→0017)** — `exec_runs` (0018) + its default-deny writer mirror `hook_runs`/`gate_events` exactly.
- **Run-entry host injection seam (RepoSpec/MCP precedents, engine ~720–780)** — where exec-enabled workspace provisioning binds per-run.
- **`sample_brownfield` + sc001 test-scoped manifests** — the precedent for the exec-granting sample workflow/fixture that proves EXEC-02 offline.

### Established Patterns
- **Capabilities reach power via the handle, never by import** — code validators call `target.runner` → workspace exec; the workspace audits at the enforcement point (bypass-proof recorder).
- **Compile-time strictness over runtime surprise** — unknown keys/unregistered refs already `CompilerError`; D-01 extends this to "exec without security+approval gates".
- **Default-deny everywhere** — deny beats allow; unknown action → denied; cross-owner read → nothing.
- **Three-layer enforcement** (compiler ceiling → gate → workspace policy) — no single point of failure; each independently testable.
- **Parity-gated change** — no existing manifest grants exec, so all 5 characterization snapshots must stay byte/event-identical with `SNAPSHOT_UPDATE` unset.
- **Offline-verifiable accept** — fixture repo + scripted approve/reject; live egress checks deferred to the milestone-end live pass.

### Integration Points
- **Net-new:** `exec_runs` migration 0018 + ScopedStore writer + `KernelServices.record_exec_run`; 3 `validator:code_*` capabilities (registry 50→53); the exec-granting sample manifest + Python fixture repo; the approval-delegate handle surface.
- **Grows:** `LocalExecutionPolicy` (allow/deny/caps), `LocalWorkspace.exec_command` (hardened + audited), `create_workspace` (exec kwarg live), `SecurityGate` (profile-conditional pass), `ApprovalGate` (HITL delegation + first-exec memory), compiler (trust-conditional ceiling + gates-required check + user/db `CompilerError`).
- **Shrinks → deleted/closed:** `shell=True` (IN-02, grep→0); plan.py `ExecutionPolicy.check` forward surface (made live or deleted — INV-12); IN-01 sign-off doc; IN-03 synthetic-key fallback; STATE.md pending-todo cleared.
- **CI gates that constrain the work:** 5-pipeline characterization snapshots; import-linter 4 kept/0 broken (validators stay kernel-pure); banned-pattern (subprocess is a tool op, not an agent loop — INV-13 untouched); migration-ledger ratchet (0017→0018 chain + IN-02/forward-surface entries).

</code_context>

<specifics>
## Specific Ideas

- **The SPEC is the N3 decision record** — at phase transition, STATE.md's "N3 ⚠️ must be confirmed" blocker row and PROJECT.md's open-decisions line flip to resolved, citing `10-SPEC.md`.
- **User's one stricter-than-recommended call (SPEC interview):** exec requires **security + approval** (human sign-off on first exec per run), not security alone — carried through D-01..D-04 here.
- **Port-signature note:** changing `exec_command(command: str)` → argv list touches the `Workspace` port (`agents/runtime/base.py`), `LocalWorkspace`, and any test callers — move them together in one plan task (no dual signature).
- **pytest-inside-pytest caution for `code_test`:** the validator's own tests run pytest as a subprocess against the fixture repo — keep the fixture tiny, disable cache/plugins as needed (`-p no:cacheprovider`), and bound by the policy caps so a hang can't stall the suite.

</specifics>

<deferred>
## Deferred Ideas

- **`network_allow` implementation + `secrets` enablement** — fields/slots exist; enforcement is a later phase (gate keeps blocking them this phase).
- **OS-level egress enforcement (netns/containers)** — arrives with the v2 ECS/container runtime behind the unchanged port; v1's residual is documented + accepted.
- **Ephemeral cred-vendor seam** — no v1 consumer; revisit with N4 push flows.
- **Non-Python toolchains on the allow-list** (node/npm) — allow-list is data; extend when egress policy can handle package installs.
- **PR/commit push (N4) · fan-out (Phase 11) · wave scheduler + step-granular resume (Phase 12)** — unchanged roadmap deferrals.
- **Frontend approval panel polish** — the approval payload rides existing gate/review event shapes this phase; a dedicated exec-approval UI panel can follow with the P11/P12 viewer work.

### Reviewed Todos (not folded)
None — `todo.match-phase 10` returned 0 matches. (The STATE.md IN-01/02/03 pending-todo block is IN scope via SPEC requirement 9, not a deferred todo.)

</deferred>

---

*Phase: 10-safe-local-exec-gated-on-n3-4b*
*Context gathered: 2026-06-10*
