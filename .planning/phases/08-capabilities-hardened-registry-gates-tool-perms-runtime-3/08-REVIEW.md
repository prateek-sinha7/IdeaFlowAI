---
phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
reviewed: 2026-06-09T00:00:00Z
depth: standard
files_reviewed: 29
files_reviewed_list:
  - backend/agents/capabilities/registry.py
  - backend/agents/capabilities/base.py
  - backend/agents/capabilities/gates/base.py
  - backend/agents/capabilities/gates/human.py
  - backend/agents/capabilities/gates/validation.py
  - backend/agents/capabilities/gates/approval.py
  - backend/agents/capabilities/gates/security.py
  - backend/agents/capabilities/gates/write.py
  - backend/agents/capabilities/hooks/base.py
  - backend/agents/capabilities/hooks/secret_scan.py
  - backend/agents/capabilities/hooks/otel_tracing.py
  - backend/agents/capabilities/hooks/write.py
  - backend/agents/capabilities/hooks/__init__.py
  - backend/agents/capabilities/tools/providers.py
  - backend/agents/capabilities/validators/severity.py
  - backend/agents/capabilities/validators/spec_plan_coverage.py
  - backend/agents/capabilities/validators/task_done_when.py
  - backend/app/agents/validators/html_static.py
  - backend/app/agents/validators/html_render.py
  - backend/app/agents/validators/design_quality.py
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/plan.py
  - backend/agents/factory.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/kernel_services.py
  - backend/app/api/capabilities.py
  - backend/app/models/gate_events.py
  - backend/app/models/hook_runs.py
  - backend/app/models/validation_results.py
  - backend/agents/authz.py
  - backend/alembic/versions/0016_capability_hardening_tables.py
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-06-09
**Depth:** standard
**Files Reviewed:** 29
**Status:** issues_found

## Summary

Reviewed the Phase 8 "Capabilities Hardened" surface: the trust-gated capability
registry, the four gates, the executable hooks (secret_scan / otel_tracing), the
tool-permission model, the validator framework, the new owner/workspace-scoped
audit tables, and the ScopedStore writers.

The trust model itself is sound: the compiler's per-reference `_check_trust`
covers every capability-name path, and even a `user`/`db` manifest that smuggles
`tools: {exec: true, secrets: ["X"]}` is collapsed to OFF by
`intersect_permissions` (AND-mask against the `ToolPermissions()` ceiling), so
there is no privilege-escalation path through manifest references or tool grants.
The security gate is genuinely fail-closed (default-deny on
exec/network/secrets), the scoped writers all stamp `(owner_id, workspace_id)`,
and the migration is additive + reversible.

However, the phase ships **two security controls that do not actually run** and
**one validator-wiring mismatch that makes the post-step validation gate
ineffective**. The headline issue: `secret_scan` is registered and wired into the
hook resolver, but **no `before_write`/`pre_commit` event is ever fired** in the
engine or runner, so the blocking secret scanner never inspects a real write — a
security capability that is dead on the live path. Combined with a fragile import
coupling that lets a missing `opentelemetry` package silently de-register
`secret_scan`, the secret-scanning control is doubly compromised.

## Critical Issues

### CR-01: `secret_scan` blocking hook never fires — secret-scanning control is dead on the live path

**File:** `backend/agents/capabilities/hooks/secret_scan.py:90` (binding) +
`backend/agents/execution_engine/engine.py:1082` (only firing point) +
`backend/agents/execution_engine/kernel_services.py:352` (`fire_hooks` seam)

**Issue:** `SecretScanHook` declares `events = ["before_write", "pre_commit"]`,
and it is included in `_EXECUTABLE_HOOK_NAMES` and resolved by
`_resolve_executable_hooks`. But a repo-wide search shows the engine fires hooks
at exactly **one** point — `self._fire_hooks("before_step", step, ectx, _registry)`
(engine.py:1082). `secret_scan` is not bound to `before_step`, so
`hook_fires_for(hook, "before_step")` is `False` and the scanner is filtered out
by `bound_hooks`. The `KernelServices.fire_hooks` method (the documented
`before_write` seam, kernel_services.py:352) has **zero callers** anywhere in
`agents/` or `app/`. Net result: the blocking secret scanner (HOOK-01, the
fine-grained complement to the `security` gate) never scans any deliverable write
payload in production. A deliverable containing an AWS key / PEM private key /
provider token is written to the sandbox unblocked.

**Fix:** Wire a real `before_write` firing point. The natural seam is the
deepagents write path in `DeepAgentRunner` (or the engine readback of
`prototype.html` / serialized sandbox files) — fire `ctx.runner.fire_hooks(
"before_write", step, payload=content)` before the content is committed to disk
and honor a `block` aggregate by halting the write. Minimally, fire it once over
each produced deliverable before it is persisted:

```python
# at the point a deliverable's content is about to be written/read-back:
outcome = await ectx.runner.fire_hooks("before_write", step, payload=deliverable_text)
if outcome == "block":
    # additive halt — do not persist the write; surface the gate_blocked/hook block
    ...
```

Until a firing point exists, `secret_scan` provides no protection and should not
be counted as a shipped security control.

## Warnings

### WR-01: Post-step `validation` gate passes the raw `ExecutionContext` to validators instead of a `DeliverableContext`

**File:** `backend/agents/capabilities/gates/validation.py:68`

**Issue:** `ValidationGate.evaluate(step, ctx)` calls
`await validator.validate(ctx)`, where `ctx` is the `ExecutionContext` forwarded
by `_evaluate_gates` (engine.py:2250, `gate.evaluate(step, ectx)`). Every
registered validator, however, expects a `DeliverableContext` shape:
`html_static` reads `target.path` and calls `target.runner.static_check(target.path)`;
`spec_plan_coverage`/`task_done_when` read `target.task_meta` and `target.content`;
the `_record` helper reads `target.step` and `target.task_meta`. `ExecutionContext`
has `.runner` (KernelServices) but **no** `.path`, `.content`, `.step`, or
`.task_meta` (verified in `agents/execution_engine/context.py`). Consequences when
the gate runs declared validators (now live post-08-04):
`html_static` → `static_check(None)` (no path); `html_render` →
`render_check(None)`; coverage/done_when validators see empty meta → silently
produce **zero** issues. So the post-step validation gate's block-critical policy
can never fire — it always evaluates clean. This is a real correctness gap now
that validator impls are registered.

**Fix:** Build the validation target via the existing
`KernelServices.deliverable_context(...)` factory before invoking each validator:

```python
target = ctx.runner.deliverable_context(
    name=ctx.runner_deliverable_name,  # or step's declared deliverable
    step=step_id,
    task_meta={"attempt": 0},
)
issues = await validator.validate(target)
```

### WR-02: `opentelemetry` import coupling silently de-registers `secret_scan` and `behavioral`

**File:** `backend/agents/capabilities/hooks/__init__.py:20-22` +
`backend/agents/capabilities/hooks/otel_tracing.py:41-43`

**Issue:** `otel_tracing.py` imports `opentelemetry` / `opentelemetry.sdk` at module
top level (lines 41-43, unguarded — only the OTLP *exporter* is lazily guarded).
The package `__init__` imports modules in order: `behavioral` (20),
`otel_tracing` (21), `secret_scan` (22). If `opentelemetry` is absent or
broken, line 21 raises `ModuleNotFoundError`, the package `__init__` aborts
**before** line 22, so `secret_scan`'s `@register` never fires. `discover()`
catches `ModuleNotFoundError` at the package level (registry.py:228) and
continues, so the failure is **silent**: `secret_scan` (a security control) and
`behavioral` are simply absent from the registry. An optional/observability
dependency thereby disables a security capability. Additionally, `discover()`
only swallows `ModuleNotFoundError` — an incompatible-version `ImportError` from
opentelemetry would propagate and crash all registry discovery.

**Fix:** Guard the base otel imports in `otel_tracing.py` so a missing package
degrades to a no-op hook (per the OBS-02 mandate that observability never breaks
the run), and import `secret_scan` before `otel_tracing` in `__init__` so the
security hook registers independently of the observability hook:

```python
# otel_tracing.py
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
# ...handle() degrades to a clean continue (no span) when not _OTEL_AVAILABLE.
```

Also broaden `discover()`'s `except ModuleNotFoundError` to `except ImportError`.

### WR-03: `otel_tracing` fires globally on every step of every workflow, adding new DB writes + stdout to legacy parity paths

**File:** `backend/agents/capabilities/hooks/otel_tracing.py:113` (`events = ["*"]`,
`required_permission = None`) + `backend/agents/execution_engine/engine.py:1082,2129`

**Issue:** `otel_tracing` binds to the `*` wildcard and needs no permission, so
`is_bound` is always `True`. `_fire_hooks("before_step", ...)` runs for **every
step of every pipeline** (the unified step loop — prototype/od_*/ppt/code-gen
included), not just manifests that opt into the hook. So on the legacy
characterization paths, every step now (a) writes a `hook_runs` DB row and (b)
opens a `ConsoleSpanExporter` span printed to stdout. WS-event parity holds (no
new event types), but these are new side effects on paths the phase claims are
byte/event-identical, and the unconditional stdout span output is noisy in
production. The hook is effectively a global default rather than a declared,
opt-in capability — at odds with the "all power lives in registered, *declared*
capabilities" principle.

**Fix:** Gate executable-hook firing on the step's *declared* hooks
(`step.hooks` / manifest), rather than resolving every name in
`_EXECUTABLE_HOOK_NAMES` for every step. At minimum, make `otel_tracing` opt-in
per run/manifest and verify the legacy characterization suite is unaffected by
the new `hook_runs` rows + console output.

### WR-04: `ExecutionPolicy.check` and `ToolPermissions.lowered_by` are dead code — the documented runtime/AGENT.md enforcement points are not wired

**File:** `backend/agents/workflows/plan.py:87` (`lowered_by`), `:165` (`ExecutionPolicy.check`)

**Issue:** The docstrings claim `ExecutionPolicy` is "the runtime
exec/network/secrets gate ... the enforcement POINT is wired now so a step
requesting exec is denied regardless" and that `lowered_by` is the AGENT.md
lowering mask. A repo-wide search finds **no caller** of either
`ExecutionPolicy.check` or `ToolPermissions.lowered_by` in production code. The
real exec/network/secrets denial this phase comes only from (a) the compiler's
`intersect_permissions` collapsing them OFF and (b) the `security` gate. The two
helpers are correct in isolation (AND-only, default-deny) but are inert. The
overclaiming docstrings give a false sense that a runtime enforcement point
exists.

**Fix:** Either wire `ExecutionPolicy.check` into the runtime action path (even
as a default-deny assertion before any privileged action), and call
`lowered_by` at the factory tool-binding seam where AGENT.md defaults apply, or
downgrade the docstrings to say these are forward-surface helpers consumed in a
later phase. Do not document an enforcement point that has no call site.

### WR-05: factory `_resolve_runner_tools` claims grant-driven binding but performs no `ToolPermissions` intersection

**File:** `backend/agents/factory.py:457-507`

**Issue:** The docstring states "Grant-driven (D-07 / INV-9): only tool sets whose
effective `ToolPermissions` permit them bind ... a future privileged set would be
gated by the effective grant before resolution." The implementation resolves
every named provider in `spec.tools` unconditionally and never reads
`step.tools` / any `ToolPermissions` (verified: no `ToolPermissions` /
`intersect_permissions` / `.write_files` reference in factory.py outside
docstrings). This phase is safe because none of the four registered sets is
write/exec-privileged, so the intended invariant is not exercised. But the
"first enforcement point" of the two-point D-07 model is not actually enforcing —
when a privileged tool set is added later, an AGENT.md could bind it regardless
of the step's effective permissions.

**Fix:** Before resolving a provider, check the set's required permission against
`step.tools` (the effective `ToolPermissions` from the compiler) and skip/deny a
set whose permission is not granted. Add a test that a write-capable set does not
bind when `write_files` is OFF.

## Info

### IN-01: Capabilities API surfaces privileged capability names (palette as a discovery map)

**File:** `backend/app/api/capabilities.py:106-118`

**Issue:** `GET /api/capabilities` enumerates the full `_KNOWN` set and returns
every `(kind, name)` including privileged ones (`security`, `approval`,
`langchain_deepagents` with `user_allowed=False`). Auth is correctly enforced
(`Depends(get_current_user)`), and the actual escalation is blocked at the
compiler trust check, so this is not an escalation path — but an authenticated
user learns the names/existence of engineer-only capabilities. Low-risk info
disclosure.

**Fix:** Optional — if the palette is meant to be the *user-grantable* set,
filter to `user_allowed=True` entries (keep the full list behind an
engineer/admin scope). Document explicitly that exposing non-user-allowed names
is intended if you keep it.

### IN-02: `security` gate audits `pass` for a step that requested secrets (because perms are pre-lowered)

**File:** `backend/agents/capabilities/gates/security.py:37-50`

**Issue:** The gate reads `step.tools` (the *effective*, post-intersection
permissions). A `user` manifest declaring `tools: {secrets: ["X"]}` has already
been collapsed to `secrets=[]` by the compiler before the gate sees it, so the
gate records `outcome=pass` (no privilege requested) even though the manifest
*asked* for a privileged permission. Denial still happens (via intersection), so
no security hole — but the audit trail does not reflect the denied request.

**Fix:** If audit fidelity matters, evaluate the security gate against the
*requested* (pre-intersection) grant, or have the compiler emit a denied-request
audit when it lowers a privileged grant to off.

### IN-03: `discover()` only catches `ModuleNotFoundError`, not `ImportError`

**File:** `backend/agents/capabilities/registry.py:228`

**Issue:** Forward-package imports are wrapped in `except ModuleNotFoundError`.
A package that exists but fails to import for any other reason (incompatible
dependency version, a syntax error in a sibling module, a circular import) raises
a plain `ImportError`/other exception that propagates and aborts the entire
registry discovery — taking down all capabilities, not just the broken one.

**Fix:** Broaden to `except ImportError` (and log at warning) so one broken
forward package degrades to "that package's capabilities are unavailable" rather
than "no capabilities discovered."

### IN-04: `secret_scan` regex set has predictable false negatives

**File:** `backend/agents/capabilities/hooks/secret_scan.py:38-59`

**Issue:** The (intentionally conservative) pattern set will miss common secrets:
JWTs (`eyJ...` base64 triples), generic 32/40-hex API keys with no `key=`/prefix
context, Azure connection strings, GCP service-account JSON private-key bodies
not on a `-----BEGIN-----` line, and base64-encoded credentials. The
`key = "value"` assignment pattern requires a quoted value `[^'\"\s]{12,}` —
secrets assigned without quotes, or split across lines, slip through. The
docstring frames this as a deliberate high-signal/low-noise tradeoff, which is
defensible, but the gap should be acknowledged so `secret_scan` is not relied on
as a complete DLP control. (Lower priority than CR-01: the hook does not run at
all today.)

**Fix:** Document the known-miss classes explicitly, and consider adding a
JWT pattern (`eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}`)
and an entropy heuristic for unquoted long opaque tokens once a real firing
point exists.

---

_Reviewed: 2026-06-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
