---
phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
plan: 07
subsystem: infra
tags: [hooks, opentelemetry, otel, observability, secret-scan, capability-registry, hexagonal]

# Dependency graph
requires:
  - phase: 08-01
    provides: self-registering CapabilityRegistry + HookHandler port
  - phase: 08-02
    provides: hook_runs/gate_events ScopedStore writers (0016 table) via KernelServices
  - phase: 08-03
    provides: effective ToolPermissions (read_files/git/exec intersection) for permission gating
  - phase: 08-05
    provides: behavioral (non-executable) hook sub-type in agents/capabilities/hooks/
  - phase: 08-06
    provides: engine lifecycle seams (constitution pre-warm) to bind hook firing points alongside
provides:
  - Executable HookHandler framework (continue|warn|block) bound at engine lifecycle/tool-call points
  - Permission-gated hook binding (scanner→read_files, git→git, command→exec; unbound if perm OFF)
  - secret_scan canonical hook (before_write/pre_commit, blocking, read_files) → hook_runs outcome=block
  - otel_tracing canonical hook (*, non-blocking) → real OpenTelemetry span + hook_runs row per firing
  - hook_runs persistence per firing (owner_id+workspace_id via ScopedStore)
affects: [observability, security, hooks, future-commit-hooks, future-merge-hooks]

# Tech tracking
tech-stack:
  added: [opentelemetry-api==1.42.1, opentelemetry-sdk==1.42.1]
  patterns:
    - "Executable hook = @register('hook', name) impl satisfying the HookHandler port (name/events/required_permission/async handle)"
    - "Permission-gated binding via hooks.base.bound_hooks (event match AND required_permission granted)"
    - "Wildcard '*' event binds a hook to every firing point (otel_tracing)"
    - "Module-level OTel TracerProvider configured once, lazily, thread-safe; console default / OTLP via env"
    - "Optional dependency loaded lazily behind an env-guard (OTLP exporter) — degrades to console gracefully"

key-files:
  created:
    - backend/agents/capabilities/hooks/otel_tracing.py
  modified:
    - backend/agents/capabilities/hooks/base.py
    - backend/agents/capabilities/hooks/secret_scan.py
    - backend/agents/capabilities/hooks/write.py
    - backend/agents/capabilities/hooks/__init__.py
    - backend/agents/capabilities/registry.py
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/kernel_services.py
    - backend/tests/agents/test_hooks.py
    - backend/tests/agents/test_registry_capabilities.py
    - backend/requirements.txt

key-decisions:
  - "Real OpenTelemetry (opentelemetry-api + opentelemetry-sdk 1.42.1) over the logging-only analog — human-approved at the package-legitimacy checkpoint (CNCF OpenTelemetry, verified on PyPI)"
  - "Exporter policy: ConsoleSpanExporter by default; auto-switch to OTLP only when OTEL_EXPORTER_OTLP_ENDPOINT is set"
  - "opentelemetry-exporter-otlp is OPTIONAL/lazy (imported + guarded only in the OTLP branch) — NOT a hard dependency (least-privilege/supply-chain)"
  - "otel_tracing required_permission=None (pure observability, always bound) and user_allowed=True"

patterns-established:
  - "Observability hook fires on * non-blocking, emits a span + hook_runs row, and adds NO engine WS event (characterization parity)"
  - "Blocking-human checkpoint gates a new external dependency before install (supply-chain T-08-07-SC)"

requirements-completed: [HOOK-01, HOOK-02, HOOK-03, HOOK-04, OBS-02]

# Metrics
duration: 18min
completed: 2026-06-09
---

# Phase 8 Plan 07: Executable Hooks + OTel Tracing Summary

**Executable HookHandler framework (continue|warn|block, permission-gated) with two live canonical hooks: secret_scan (blocking, read_files) and otel_tracing (wildcard, non-blocking) emitting real OpenTelemetry spans, every firing persisted to hook_runs.**

## Performance

- **Duration:** 18 min (Task 1 + checkpoint + OTel install/impl/finalize)
- **Started:** 2026-06-09T22:26:24+02:00 (Task 1 commit)
- **Completed:** 2026-06-09T22:44:38+02:00 (feat commit)
- **Tasks:** 3 (Task 1 framework + secret_scan; Task 2 blocking-human OTel checkpoint; Task 3 otel_tracing)
- **Files modified:** 11 (1 created, 10 modified across the two task commits)

## Accomplishments
- Executable HookHandler framework: hooks bound to lifecycle/tool-call events (before_write/post_task/before_step/`*`) with outcome continue|warn|block; a blocking hook halts the offending action additively (no new WS event).
- Permission gating (HOOK-02/HOOK-03): a hook carrying required_permission binds only when the step's effective perms grant it — git/exec hooks are NOT bound this phase (those perms OFF), proving least-privilege at the binding seam.
- secret_scan (HOOK-01/04): before_write/pre_commit blocking scanner (read_files) blocks a secret-bearing write and writes a hook_runs row outcome=block; clean writes continue + record outcome=continue.
- otel_tracing (OBS-02): wildcard, non-blocking observability hook opens a real OpenTelemetry span per fired event behind a ConsoleSpanExporter (OTLP via OTEL_EXPORTER_OTLP_ENDPOINT) and writes a hook_runs row; emits NO engine WS event.
- Every hook firing persists a hook_runs row (owner_id+workspace_id via the 0016 ScopedStore writer); the 08-05 behavioral (non-executable) provider survives alongside the executable sub-type.

## Task Commits

Each task was committed atomically:

1. **Task 1: HookHandler framework + firing points + secret_scan** - `5354944` (feat)
2. **Task 2: blocking-human OTel package-legitimacy checkpoint** - `2be056a` (docs — checkpoint pause; human approved "install real OTel")
3. **Task 3: otel_tracing canonical hook with real OpenTelemetry** - `94b77b3` (feat)

**Plan metadata:** _(this commit)_ `docs(08-07): complete executable hooks + otel tracing; close phase 08 plans`

_Note: TDD plan — Task 1 and Task 3 each landed test+impl together within their feat commit (tests in test_hooks.py)._

## Files Created/Modified
- `backend/agents/capabilities/hooks/otel_tracing.py` - **(created)** otel_tracing hook: module-level OTel TracerProvider (console default / OTLP via env, lazy thread-safe), wildcard non-blocking span + hook_runs row.
- `backend/agents/capabilities/hooks/base.py` - HookOutcome (continue|warn|block) + permission-gated binding helpers (is_bound/bound_hooks/hook_fires_for, `*` wildcard).
- `backend/agents/capabilities/hooks/secret_scan.py` - secret_scan blocking hook (before_write/pre_commit, read_files); blocks secret-bearing payloads + writes hook_runs.
- `backend/agents/capabilities/hooks/write.py` - shared hook_runs write helper via ctx.runner.record_hook_run (best-effort).
- `backend/agents/capabilities/hooks/__init__.py` - import secret_scan + otel_tracing for @register side effect (behavioral provider intact).
- `backend/agents/capabilities/registry.py` - _KNOWN gains hook:secret_scan + hook:otel_tracing (drift count 32→34).
- `backend/agents/execution_engine/engine.py` - `_fire_hooks` lifecycle seam + `_resolve_executable_hooks` + before_write firing point (additive, no event leak).
- `backend/agents/execution_engine/kernel_services.py` - record_hook_run + fire_hooks passthrough.
- `backend/tests/agents/test_hooks.py` - 20 tests (framework/permission gating/secret block-continue/engine seam + 7 otel behaviors).
- `backend/tests/agents/test_registry_capabilities.py` - drift count 32→34; secret_scan/otel_tracing in _EXPECTED_NAMES.
- `backend/requirements.txt` - opentelemetry-api==1.42.1 + opentelemetry-sdk==1.42.1 (hard deps; OTLP exporter optional/lazy, NOT pinned).

## Decisions Made
- **Real OpenTelemetry over the logging-only analog.** The plan's Task 2 blocking-human checkpoint offered real OTLP spans vs a structured-logging span analog. The human approved "install real OTel". Installed only `opentelemetry-api` + `opentelemetry-sdk` (1.42.1, CNCF OpenTelemetry, github.com/open-telemetry/opentelemetry-python — human-verified on PyPI at the checkpoint).
- **Exporter policy: console-default, OTLP-via-env.** A module-level TracerProvider uses a `ConsoleSpanExporter` (SimpleSpanProcessor) by default; if `OTEL_EXPORTER_OTLP_ENDPOINT` is set, the OTLP span exporter is imported lazily (BatchSpanProcessor). A missing `opentelemetry-exporter-otlp` package degrades gracefully back to console — so the OTLP exporter is an optional, NOT hard, dependency (least-privilege / supply-chain T-08-07-SC).
- **otel_tracing required_permission=None, user_allowed=True.** Pure observability needs no privilege (reads nothing off disk, runs no command), so it is always bound and is safe on the user palette.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Re-scoped a Task-1 engine-seam assertion to survive otel_tracing now firing on before_write**
- **Found during:** Task 3 (otel_tracing landing)
- **Issue:** `test_engine_fire_hooks_scanner_unbound_when_read_files_off` asserted `runner.hook_runs == []` when read_files is OFF. Task 1 had already wired `otel_tracing` into the engine's `_EXECUTABLE_HOOK_NAMES`; once the otel_tracing impl registered (Task 3), the wildcard, permission-free observability hook legitimately fires at before_write and records a continue row — so the total-row-count assertion went stale.
- **Fix:** Scoped the assertion to the scanner: `secret_rows = [r for r in runner.hook_runs if r["hook"] == "secret_scan"]; assert secret_rows == []`. The permission gate's intent (the unbound scanner never fires / never blocks) is preserved precisely; otel's correct new behavior (fire on `*`) is no longer falsely flagged.
- **Files modified:** backend/tests/agents/test_hooks.py
- **Verification:** Full gate suite green (118 passed, 3 skipped); the 5 characterization snapshots byte/event-identical.
- **Committed in:** `94b77b3` (Task 3 feat commit)

---

**Total deviations:** 1 auto-fixed (1 bug — a stale test assertion).
**Impact on plan:** The fix tightens the test to assert the intended invariant (scanner permission gate) rather than an incidental total-row count; no production-code change, no scope creep.

## Issues Encountered
None beyond the deviation above. OTel install was clean (1.42.1 + opentelemetry-semantic-conventions 0.63b1 transitive); banned-pattern gate unaffected (opentelemetry is an observability lib, not a deep-agent runtime).

## User Setup Required

**Optional OTLP export.** otel_tracing emits to the console by default — no setup needed. To export spans to a real OTLP collector, set `OTEL_EXPORTER_OTLP_ENDPOINT` (e.g. `http://localhost:4317`) and install the optional `opentelemetry-exporter-otlp` package; the hook auto-switches to the OTLP exporter when the env var is present and degrades back to console if the exporter package is absent. Live-OTLP span export against a real collector is deferred to the end-of-milestone live pass (per the project defer-live-verification convention).

## Next Phase Readiness
- HOOK-01..04 + OBS-02 satisfied; hooks are executable + persisted + permission-gated.
- Forward-surface event names (pre/post_commit, on_validation, before/after_merge) are accepted as bind targets; their producers + the git/exec-permissioned hooks land in later phases (git=P9, exec=P10).
- This is the FINAL plan of phase 08 (8/8) — phase 08 capability hardening (registry/gates/tool-perms/runtime [3]) is complete.

## TDD Gate Compliance
Both behavior-adding tasks landed tests + impl together in their feat commits (test_hooks.py grew the RED/GREEN behaviors within `5354944` and `94b77b3`). secret_scan and otel_tracing behaviors are each covered by dedicated tests proven failing-without-impl during authoring.

## Self-Check: PASSED
- FOUND: backend/agents/capabilities/hooks/otel_tracing.py
- FOUND: commit 5354944 (Task 1)
- FOUND: commit 2be056a (Task 2 checkpoint)
- FOUND: commit 94b77b3 (Task 3 otel_tracing feat)
- 118 passed / 3 skipped (test_hooks 20/20; 5 characterization snapshots byte/event-identical; registry/ledger/banned-pattern green)
- lint-imports: 3 kept / 0 broken

---

## Post-Review Remediation (08-REVIEW.md — 2026-06-10)

The Phase 8 code review surfaced 4 functional gaps + 2 overclaiming docstrings in
the capabilities surface (this plan's hooks + the gates/tool-perms). All remediated
on `feature/003-workflow-engine-decoupling`, each fix committed atomically; the 5
characterization snapshots stayed byte/event-identical (no re-baseline), and
test_banned_patterns / test_migration_ledger / lint-imports (3 kept / 0 broken)
stayed green throughout.

- **WR-02 + IN-03 — otel import resilience** (`d8270fc`): guarded the top-level
  `opentelemetry` imports in `otel_tracing.py` (`try/except ImportError →
  _OTEL_AVAILABLE=False`); `handle()` degrades to a clean continue (no span) when
  unavailable. Reordered `hooks/__init__.py` so `secret_scan` imports BEFORE
  `otel_tracing` (the security hook registers independently). Broadened
  `registry.discover()`'s `except ModuleNotFoundError` → `except ImportError` (log
  warning) so one broken forward package degrades instead of aborting all discovery.

- **WR-04 + WR-05 — overclaiming docstrings** (`c4990a9`, docs-only, no behavior
  change): downgraded `ExecutionPolicy.check` + `ToolPermissions.lowered_by`
  (plan.py) and the factory `_resolve_runner_tools` grant-binding docstring to
  honestly state they are forward-surface helpers with NO production caller this
  phase (the runtime/tool-binding enforcement points land in Phase 9+ with the
  LocalSandboxRuntime). The real exec/secrets denial this phase remains the
  compiler's `intersect_permissions` + the `security` gate (both wired).

- **WR-01 — validation gate context** (`6ebc7d9`): `ValidationGate` now builds a
  `DeliverableContext` via `ctx.runner.deliverable_context(...)` (the same factory
  task_loop/08-04 uses, keyed on `ctx.deliverable.name`) before calling
  `validator.validate(target)`, instead of passing the raw `ExecutionContext` (which
  has no `.path`/`.content`/`.step`/`.task_meta`). New tests drive a `gates:
  [validation]` step with the REAL `html_static` validator: a P0 static issue blocks
  (validator read `target.path`); a static warning (P3/LOW) emits `validation_warning`
  + proceeds. Degrades to the raw ctx for offline fakes (existing tests unaffected).

- **CR-01 + WR-03 + IN-04 — declaration-driven firing + real before_write seam**
  (`a9f6038`): the core fix. Hook firing is now DECLARATION-DRIVEN — added
  `Step.hooks` (+ compiler strict-key/name-resolve/trust-check), and
  `_resolve_executable_hooks(step, registry)` resolves only `step.hooks` (was a
  global `_EXECUTABLE_HOOK_NAMES` tuple). A legacy step (prototype/od_/ppt/code-gen —
  declares no hooks) fires NOTHING: this both FIXES WR-03 (otel_tracing no longer
  fires globally / writes hook_runs rows / prints console spans on the legacy parity
  paths) AND keeps the snapshots byte/event-identical. Added a real `before_write`
  firing point (CR-01) in `_run_agent` over the produced deliverable content before
  the typed dual-write persist; a `block` halts the persist additively (no new WS
  event). `KernelServices.run_agent` binds `ectx.current_step` (scratch idiom) so the
  seam reads `step.hooks`. A manifest declaring `hooks: [secret_scan]` now scans the
  write payload and blocks a secret + writes a `hook_runs` row outcome=block — proven
  by a test through the production `KernelServices.fire_hooks` seam (not a direct
  call). `pre_commit` stays registered+unfired (no git this phase — P9). IN-04:
  documented secret_scan's known false-negative classes (JWT/unquoted/opaque tokens)
  so it is not relied on as complete DLP.

- **IN-01 / IN-02**: left as-is (auth enforced, denial happens via intersection — no
  escalation path); documented only, no code change. **Two PRE-EXISTING unit-test
  failures** (`test_logout` self-registration 403, `test_pipeline_cancel` cancel
  assertion) confirmed failing identically on the pre-fix tree — logged to
  `deferred-items.md`, out of scope.

*Remediation completed: 2026-06-10*

---
*Phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3*
*Completed: 2026-06-09*
