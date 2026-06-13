"""tests/agents/test_hooks.py — the executable HookHandler framework + canonical hooks (08-07 / HOOK-01..04 / OBS-02).

08-07 (Wave 5) stands up the EXECUTABLE ``HookHandler`` framework (D-09): hooks
bound to lifecycle/tool-call events (``before_write`` / ``post_task`` /
``before_step`` / ``*``) with outcome ``continue | warn | block`` (a ``block``
halts the offending action ADDITIVELY) and PERMISSION GATING (scanner→read_files,
git→git, command→exec; a hook lacking its permission is NOT bound). Every firing
writes a ``hook_runs`` row (HOOK-04).

Two LIVE canonical hooks:
  * ``secret_scan`` — ``before_write`` / ``pre_commit``, BLOCKING, ``read_files``;
    blocks a write carrying a secret + writes a hook_runs row outcome=block.
  * ``otel_tracing`` — ``*``, NON-blocking, span/log + hook_runs row (OBS-02 —
    covered by the ``-k otel`` tests added in Task 3).

Offline — no live LLM / Bedrock. The hooks reach the ``hook_runs`` writer through
a fake ``ctx.runner`` (the ``_RecordingRunner`` below) that records
``record_hook_run`` calls; the real ScopedStore write is covered by the authz
suite. The behavioral (non-executable) provider from 08-05 still registers — a
parity assertion proves it survives alongside the executable sub-type.
"""

from __future__ import annotations

import pytest

import agents.capabilities.registry as registry_mod
from agents.capabilities.hooks.base import (
    HOOK_BLOCK,
    HOOK_CONTINUE,
    bound_hooks,
    hook_fires_for,
    is_bound,
)
from agents.capabilities.registry import CapabilityRegistry


# ════════════════════════════════════════════════════════════════════════════
# Registry save/restore (08-01 Issues-Encountered pattern: snapshot AFTER discover)
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_registry():
    """Save/restore the process-global registry maps around each test (D-12)."""
    registry_mod.discover()  # bind built-ins (incl. the hook impls) before snapshotting
    known = set(registry_mod._KNOWN)
    impls = dict(registry_mod._IMPLS)
    trust = dict(registry_mod._TRUST)
    discovered = registry_mod._DISCOVERED
    try:
        yield
    finally:
        registry_mod._KNOWN.clear()
        registry_mod._KNOWN.update(known)
        registry_mod._IMPLS.clear()
        registry_mod._IMPLS.update(impls)
        registry_mod._TRUST.clear()
        registry_mod._TRUST.update(trust)
        registry_mod._DISCOVERED = discovered


# ════════════════════════════════════════════════════════════════════════════
# Fakes — a minimal ctx + ctx.runner handle that records hook_runs rows
# ════════════════════════════════════════════════════════════════════════════


class _RecordingRunner:
    """Minimal ctx.runner handle: records record_hook_run calls (the hook_runs writer)."""

    def __init__(self) -> None:
        self.hook_runs: list[dict] = []

    async def record_hook_run(self, hook, event, outcome, detail=None):
        self.hook_runs.append(
            {"hook": hook, "event": event, "outcome": outcome, "detail": detail}
        )
        return f"hook-row-{len(self.hook_runs)}"


class _Ctx:
    """Minimal ExecutionContext stand-in — hooks read .runner only."""

    def __init__(self, runner) -> None:
        self.runner = runner


class _Perms:
    """Minimal effective ToolPermissions stand-in (the 08-03 intersection result)."""

    def __init__(self, *, read_files=True, git=False, exec=False) -> None:
        self.read_files = read_files
        self.git = git
        self.exec = exec


class _Step:
    """Minimal compiled Step stand-in — the hook seam reads ``agent_id`` + ``tools`` + ``hooks``.

    ``hooks`` is the DECLARED executable-hook list (08-08 / CR-01/WR-03): the engine
    fires ONLY the hooks a step declares here. A step declaring no hooks fires nothing.
    """

    def __init__(self, agent_id="step-x", *, tools=None, hooks=None) -> None:
        self.agent_id = agent_id
        self.tools = tools if tools is not None else _Perms()
        self.hooks = list(hooks or [])


# ════════════════════════════════════════════════════════════════════════════
# Resolution + the behavioral-provider survival parity (framework wiring)
# ════════════════════════════════════════════════════════════════════════════


def test_secret_scan_resolves_as_executable_hook():
    """secret_scan resolves off the registry as a HookHandler-shaped impl."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "secret_scan")
    assert hook.name == "secret_scan"
    assert "before_write" in hook.events
    assert hook.required_permission == "read_files"
    assert hasattr(hook, "handle")


def test_behavioral_provider_survives_alongside_executable_hooks():
    """The 08-05 behavioral (non-executable) provider still registers (no collapse)."""
    reg = CapabilityRegistry()
    behavioral = reg.resolve("hook", "behavioral")
    assert behavioral.name == "behavioral"
    # The executable sub-type is a SEPARATE registration — both coexist.
    assert reg.is_registered("hook", "secret_scan")
    assert reg.is_registered("hook", "behavioral")


# ════════════════════════════════════════════════════════════════════════════
# Permission gating (HOOK-02) — a hook lacking its permission is NOT bound
# ════════════════════════════════════════════════════════════════════════════


def test_scanner_bound_when_read_files_granted():
    """secret_scan (read_files) binds on a step whose effective perms grant read_files."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "secret_scan")
    assert is_bound(hook, _Perms(read_files=True)) is True


def test_scanner_not_bound_when_read_files_lowered_off():
    """secret_scan is NOT bound when read_files is lowered off (HOOK-02)."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "secret_scan")
    assert is_bound(hook, _Perms(read_files=False)) is False


def test_git_or_exec_hook_not_bound_this_phase():
    """A hook requiring git/exec is NOT bound (those perms are OFF this phase)."""

    class _GitHook:
        name = "fake_git"
        events = ["pre_commit"]
        required_permission = "git"

    class _ExecHook:
        name = "fake_cmd"
        events = ["before_step"]
        required_permission = "exec"

    perms = _Perms(read_files=True, git=False, exec=False)
    assert is_bound(_GitHook(), perms) is False
    assert is_bound(_ExecHook(), perms) is False


def test_bound_hooks_filters_by_event_and_permission():
    """bound_hooks returns only hooks declaring the event AND permission-granted."""
    reg = CapabilityRegistry()
    scanner = reg.resolve("hook", "secret_scan")

    class _GitHook:
        name = "fake_git"
        events = ["before_write"]
        required_permission = "git"

    hooks = [scanner, _GitHook()]
    # read_files ON, git OFF → only the scanner fires for before_write.
    bound = bound_hooks(hooks, "before_write", _Perms(read_files=True, git=False))
    assert [h.name for h in bound] == ["secret_scan"]


def test_wildcard_hook_fires_for_any_event():
    """A hook declaring the ``*`` wildcard fires for every event (otel_tracing shape)."""

    class _Wild:
        name = "wild"
        events = ["*"]
        required_permission = None

    assert hook_fires_for(_Wild(), "before_step") is True
    assert hook_fires_for(_Wild(), "post_task") is True
    assert hook_fires_for(_Wild(), "before_write") is True


# ════════════════════════════════════════════════════════════════════════════
# secret_scan behavior (HOOK-01/04) — block a secret, continue a clean write
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_secret_scan_blocks_secret_before_write_and_writes_block_row():
    """secret_scan on a before_write carrying a secret → block + a hook_runs row outcome=block."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "secret_scan")
    runner = _RecordingRunner()
    ctx = _Ctx(runner)

    secret_payload = (
        'AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'
        "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"
    )
    event = {"event": "before_write", "payload": secret_payload}
    result = await hook.handle(event, ctx)

    assert result.outcome == HOOK_BLOCK
    # Exactly one hook_runs row, outcome=block, hook=secret_scan, event=before_write.
    assert len(runner.hook_runs) == 1
    row = runner.hook_runs[0]
    assert row["hook"] == "secret_scan"
    assert row["event"] == "before_write"
    assert row["outcome"] == HOOK_BLOCK
    # The audit row records a marker, NEVER the raw secret payload.
    assert row["detail"]["matched"] is True
    assert secret_payload not in str(row["detail"])


@pytest.mark.asyncio
async def test_secret_scan_continues_clean_write_and_writes_continue_row():
    """secret_scan on a clean write → continue + a hook_runs row outcome=continue."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "secret_scan")
    runner = _RecordingRunner()
    ctx = _Ctx(runner)

    clean = "<html><body><h1>Hello</h1><p>No secrets here.</p></body></html>"
    event = {"event": "before_write", "payload": clean}
    result = await hook.handle(event, ctx)

    assert result.outcome == HOOK_CONTINUE
    assert len(runner.hook_runs) == 1
    row = runner.hook_runs[0]
    assert row["hook"] == "secret_scan"
    assert row["outcome"] == HOOK_CONTINUE


@pytest.mark.asyncio
async def test_secret_scan_detects_private_key_block():
    """A PEM private-key block in a write payload is blocked (high-signal matcher)."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "secret_scan")
    runner = _RecordingRunner()
    ctx = _Ctx(runner)

    payload = (
        "config:\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA...redacted...\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    result = await hook.handle({"event": "before_write", "payload": payload}, ctx)
    assert result.outcome == HOOK_BLOCK
    assert runner.hook_runs[0]["outcome"] == HOOK_BLOCK


# ════════════════════════════════════════════════════════════════════════════
# The engine before_write firing seam (HOOK-01 — a block halts the write)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_engine_fire_hooks_before_write_blocks_secret():
    """The engine before_write firing returns block for a secret-bearing payload.

    Drives the real engine ``_fire_hooks`` (the lifecycle seam) with the registered
    secret_scan hook over a step whose effective perms grant read_files. A secret
    payload → ``block`` (the caller halts the write additively); the hook persists a
    hook_runs row via the fake runner.
    """
    from agents.execution_engine.engine import ExecutionEngine

    engine = ExecutionEngine.__new__(ExecutionEngine)  # no __init__ side effects
    reg = CapabilityRegistry()
    runner = _RecordingRunner()
    ectx = _Ctx(runner)
    # The step DECLARES secret_scan (08-08): declaration-driven firing.
    step = _Step("build", tools=_Perms(read_files=True), hooks=["secret_scan"])

    secret = 'token = "ghp_0123456789abcdefghijklmnopqrstuvwxyzABCD"'
    outcome = await engine._fire_hooks(
        "before_write", step, ectx, reg, payload=secret
    )
    assert outcome == HOOK_BLOCK
    assert any(r["outcome"] == HOOK_BLOCK for r in runner.hook_runs)


@pytest.mark.asyncio
async def test_engine_fire_hooks_clean_payload_continues_no_block():
    """A clean before_write payload returns continue (no halt, the write proceeds)."""
    from agents.execution_engine.engine import ExecutionEngine

    engine = ExecutionEngine.__new__(ExecutionEngine)
    reg = CapabilityRegistry()
    runner = _RecordingRunner()
    ectx = _Ctx(runner)
    step = _Step("build", tools=_Perms(read_files=True), hooks=["secret_scan"])

    outcome = await engine._fire_hooks(
        "before_write", step, ectx, reg, payload="<html>clean</html>"
    )
    assert outcome == HOOK_CONTINUE


@pytest.mark.asyncio
async def test_engine_fire_hooks_scanner_unbound_when_read_files_off():
    """With read_files lowered off, secret_scan is unbound → no block even for a secret.

    Proves the permission gate at the engine seam: a step lacking read_files does
    not bind the scanner, so the secret-bearing payload is NOT scanned and the
    firing is a no-op continue (HOOK-02). The scanner writes NO hook_runs row (the
    unbound hook never fires). The step ALSO declares the wildcard observability hook
    (otel_tracing), which IS bound (no required permission) and DOES record a continue
    row for the event — so the assertion is scoped to the scanner, not the total
    row count. Proves the permission gate is orthogonal to declaration: both are
    declared, but only the permission-granted one fires.
    """
    from agents.execution_engine.engine import ExecutionEngine

    engine = ExecutionEngine.__new__(ExecutionEngine)
    reg = CapabilityRegistry()
    runner = _RecordingRunner()
    ectx = _Ctx(runner)
    # Both hooks DECLARED; read_files is lowered OFF so secret_scan stays unbound.
    step = _Step(
        "build",
        tools=_Perms(read_files=False),
        hooks=["secret_scan", "otel_tracing"],
    )

    secret = 'token = "ghp_0123456789abcdefghijklmnopqrstuvwxyzABCD"'
    outcome = await engine._fire_hooks(
        "before_write", step, ectx, reg, payload=secret
    )
    assert outcome == HOOK_CONTINUE
    # The unbound scanner never fired → no secret_scan row (no block either).
    secret_rows = [r for r in runner.hook_runs if r["hook"] == "secret_scan"]
    assert secret_rows == []


@pytest.mark.asyncio
async def test_engine_fire_hooks_legacy_step_declaring_no_hooks_fires_nothing():
    """A step DECLARING no hooks fires NOTHING — the declaration-driven WR-03 fix.

    Proves the core of CR-01/WR-03: hook firing keys off the step's DECLARED hooks
    (``step.hooks``), NOT a global executable-hook set. A legacy step (prototype/od_/
    ppt/code-gen — declares no hooks) fires neither secret_scan NOR otel_tracing, so
    it writes NO hook_runs row + prints NO console span — even over a secret payload.
    This is what keeps the 5 characterization snapshots byte/event-identical AND
    removes otel_tracing's former global side effect on legacy paths.
    """
    from agents.execution_engine.engine import ExecutionEngine

    engine = ExecutionEngine.__new__(ExecutionEngine)
    reg = CapabilityRegistry()
    runner = _RecordingRunner()
    ectx = _Ctx(runner)
    # No declared hooks → legacy parity path.
    step = _Step("build", tools=_Perms(read_files=True), hooks=[])

    secret = 'token = "ghp_0123456789abcdefghijklmnopqrstuvwxyzABCD"'
    for event_name in ("before_step", "before_write"):
        outcome = await engine._fire_hooks(
            event_name, step, ectx, reg, payload=secret
        )
        assert outcome == HOOK_CONTINUE
    # NOTHING fired: no hook_runs rows at all (no secret_scan, no otel_tracing).
    assert runner.hook_runs == []


# ════════════════════════════════════════════════════════════════════════════
# WIRED before_write path (CR-01) — through the production KernelServices.fire_hooks
# seam (the runner/strategy entry point), with current_step bound declaration-driven
# ════════════════════════════════════════════════════════════════════════════


class _RecordingScopedStore:
    """A ScopedStore stand-in that records hook_runs rows (the real persist seam)."""

    def __init__(self) -> None:
        self.hook_runs: list[dict] = []

    async def record_hook_run(self, run_id, hook, event, outcome, detail=None):
        self.hook_runs.append(
            {"run_id": run_id, "hook": hook, "event": event,
             "outcome": outcome, "detail": detail}
        )
        return f"hook-row-{len(self.hook_runs)}"


def _real_kernel_services(ectx):
    """Build a real KernelServices over a real engine + ectx (no sandbox/model needed
    for the fire_hooks passthrough)."""
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.kernel_services import KernelServices

    engine = ExecutionEngine.__new__(ExecutionEngine)
    return KernelServices(
        engine=engine,
        ectx=ectx,
        sandbox=None,
        ordered_agents=[],
        user_message="",
        pipeline_run_id=ectx.run_id,
        pipeline_type="custom",
        planning_context={},
        attached_skills=None,
        attached_hooks=None,
        model_id=None,
        cancel_event=None,
        results=[],
    )


@pytest.mark.asyncio
async def test_wired_before_write_blocks_secret_via_kernel_services_seam():
    """The PRODUCTION before_write seam blocks a secret + writes a hook_runs block row.

    Drives the real ``KernelServices.fire_hooks`` (the seam a runner/strategy reaches
    off ``ctx.runner.fire_hooks``) → engine ``_fire_hooks``, with a step DECLARING
    secret_scan bound to the ExecutionContext as ``current_step`` (the same binding
    KernelServices.run_agent establishes before the _run_agent before_write firing).
    A secret payload → ``block`` AND a hook_runs row outcome=block lands in the
    scoped store. This proves the WIRED path (not a direct engine._fire_hooks call).
    """
    from agents.execution_engine.context import ExecutionContext
    from agents.workflows.plan import Step

    store = _RecordingScopedStore()
    ectx = ExecutionContext(run_id="wired-run", owner_id="o", workspace_id="w")
    ectx.scoped_store = store
    step = Step(agent_id="build", hooks=["secret_scan"])
    # Bind the runner handle + the current step exactly as the production run does.
    runner = _real_kernel_services(ectx)
    ectx.runner = runner
    ectx.current_step = step

    secret = 'api_key = "ghp_0123456789abcdefghijklmnopqrstuvwxyzABCD"'
    outcome = await runner.fire_hooks("before_write", step, payload=secret)

    assert outcome == HOOK_BLOCK
    block_rows = [r for r in store.hook_runs
                  if r["hook"] == "secret_scan" and r["outcome"] == HOOK_BLOCK]
    assert len(block_rows) == 1
    assert block_rows[0]["event"] == "before_write"


@pytest.mark.asyncio
async def test_wired_run_agent_binds_current_step_for_declaration_driven_firing():
    """KernelServices.run_agent binds + restores ``ectx.current_step`` (CR-01 plumbing).

    The before_write firing in _run_agent reads ``ectx.current_step.hooks`` — so
    run_agent must bind the step before delegating + restore it after. We stub the
    engine's _run_agent to capture the bound step and assert the round-trip without
    needing a live model/sandbox.
    """
    from agents.execution_engine.context import ExecutionContext
    from agents.workflows.plan import Step

    ectx = ExecutionContext(run_id="bind-run", owner_id="o", workspace_id="w")
    ectx.current_step = None
    runner = _real_kernel_services(ectx)

    step = Step(agent_id="prototype-build", hooks=["secret_scan"])
    captured = {}

    class _Spec:
        id = "prototype-build"

    async def _fake_run_agent(*args, **kw):
        captured["current_step"] = ectx.current_step
        if False:
            yield  # make it an async generator

    runner._engine._run_agent = _fake_run_agent  # type: ignore[assignment]
    runner._spec_for = lambda s: _Spec()  # type: ignore[assignment]
    runner._index_for = lambda s: 0  # type: ignore[assignment]

    async for _ in runner.run_agent(step, ectx):
        pass

    # The step was bound during the delegation...
    assert captured["current_step"] is step
    # ...and restored to its prior value (None) afterwards.
    assert ectx.current_step is None


# ════════════════════════════════════════════════════════════════════════════
# otel_tracing behavior (OBS-02) — fires on *, non-blocking, span + hook_runs row
# ════════════════════════════════════════════════════════════════════════════


def test_otel_tracing_resolves_as_wildcard_observability_hook():
    """otel_tracing resolves off the registry: bound to ``*``, no required permission."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "otel_tracing")
    assert hook.name == "otel_tracing"
    assert hook.events == ["*"]
    # Pure observability — no privilege needed, so it is ALWAYS bound (HOOK-02).
    assert hook.required_permission is None
    assert hasattr(hook, "handle")


def test_otel_tracing_is_user_allowed():
    """otel_tracing is user-grantable (D-02) — an observability hook grants no privilege."""
    reg = CapabilityRegistry()
    assert reg.is_user_allowed("hook", "otel_tracing") is True


def test_otel_tracing_fires_for_every_event_via_wildcard():
    """otel_tracing's ``*`` binds it to EVERY lifecycle/tool-call firing point."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "otel_tracing")
    for event in ("before_step", "post_task", "before_write", "on_validation"):
        assert hook_fires_for(hook, event) is True
    # No permission → always bound, regardless of the step's effective perms.
    assert is_bound(hook, _Perms(read_files=False, git=False, exec=False)) is True


@pytest.mark.asyncio
async def test_otel_tracing_continues_and_writes_row_on_fire():
    """otel_tracing fires non-blocking: a real OTel span + a hook_runs row, always continue (OBS-02)."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "otel_tracing")
    runner = _RecordingRunner()
    ctx = _Ctx(runner)

    event = {"event": "before_step", "agent_id": "build"}
    result = await hook.handle(event, ctx)

    # NON-blocking: always continue (never block).
    assert result.outcome == HOOK_CONTINUE
    # One hook_runs row, outcome=continue, hook=otel_tracing, event carried through.
    assert len(runner.hook_runs) == 1
    row = runner.hook_runs[0]
    assert row["hook"] == "otel_tracing"
    assert row["event"] == "before_step"
    assert row["outcome"] == HOOK_CONTINUE
    assert row["detail"]["span"] is True
    assert row["detail"]["agent_id"] == "build"


@pytest.mark.asyncio
async def test_otel_tracing_degrades_to_noop_span_when_otel_unavailable(monkeypatch):
    """When opentelemetry is absent, otel_tracing opens NO span but still continues + records (WR-02 / OBS-02).

    Simulates a missing optional dependency by making ``_get_tracer`` return None
    (the module-level guard sets ``_OTEL_AVAILABLE=False`` in that case). The hook
    must NOT raise, must return continue, and must still write a hook_runs row —
    observability degrades gracefully, never breaking the run.
    """
    from agents.capabilities.hooks import otel_tracing as _otel

    monkeypatch.setattr(_otel, "_OTEL_AVAILABLE", False)
    # Reset the cached tracer so _get_tracer re-evaluates the guard.
    monkeypatch.setattr(_otel, "_TRACER", None)

    hook = _otel.OtelTracingHook()
    runner = _RecordingRunner()
    ctx = _Ctx(runner)

    result = await hook.handle({"event": "before_step", "agent_id": "build"}, ctx)

    assert result.outcome == HOOK_CONTINUE
    assert len(runner.hook_runs) == 1
    row = runner.hook_runs[0]
    assert row["hook"] == "otel_tracing"
    assert row["outcome"] == HOOK_CONTINUE
    # No span was opened (the optional dependency was unavailable).
    assert row["detail"]["span"] is False
    assert row["detail"]["agent_id"] == "build"


@pytest.mark.asyncio
async def test_otel_tracing_never_blocks_for_any_event():
    """otel_tracing's outcome is ALWAYS continue — it can never halt an action (OBS-02)."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "otel_tracing")
    runner = _RecordingRunner()
    ctx = _Ctx(runner)

    # Even an event whose payload would trip secret_scan never blocks here — the
    # observability hook does not inspect/halt; it only spans + records.
    for event_name in ("before_write", "post_task", "before_step"):
        result = await hook.handle({"event": event_name}, ctx)
        assert result.outcome == HOOK_CONTINUE
    assert all(r["outcome"] == HOOK_CONTINUE for r in runner.hook_runs)


@pytest.mark.asyncio
async def test_otel_tracing_missing_runner_is_noop_continue():
    """A missing ctx.runner (offline span-only) degrades to a clean continue (best-effort row)."""
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "otel_tracing")

    class _NoRunnerCtx:
        runner = None

    result = await hook.handle({"event": "before_step"}, _NoRunnerCtx())
    assert result.outcome == HOOK_CONTINUE


@pytest.mark.asyncio
async def test_otel_tracing_emits_no_ws_event_string():
    """otel_tracing emits a span/row but NEVER an engine WS event (characterization parity).

    The hook's return is a HookOutcome (continue) and its only side effects are an
    OTel span + a hook_runs row — there is no engine WS event in its surface, so a
    clean characterization run's event multiset is unchanged (Pitfall 6).
    """
    reg = CapabilityRegistry()
    hook = reg.resolve("hook", "otel_tracing")
    runner = _RecordingRunner()
    ctx = _Ctx(runner)

    result = await hook.handle({"event": "after_run"}, ctx)
    # The outcome object carries only the hook vocabulary — no WS event payload.
    assert result.outcome == HOOK_CONTINUE
    assert not hasattr(result, "ws_event")
    # The only recorded side effect is the audit row (no event stream touched).
    assert len(runner.hook_runs) == 1
    assert runner.hook_runs[0]["hook"] == "otel_tracing"


# ════════════════════════════════════════════════════════════════════════════
# ISS-010 (Phase 17) — close the OTLP verification gap deterministically OFFLINE.
#
# "Declaration-driven hooks → legacy pipelines emit no spans" is true and proven
# (all 18 manifests declare no ``hooks:``). The remaining gap was: given a
# collector + a hook-declaring step, DO spans actually export? Prove it WITHOUT a
# live collector by driving the REAL ``OtelTracingHook.handle`` through an injected
# ``InMemorySpanExporter`` and asserting exactly 1 span with the right attrs/scope.
#
# THE #1 LANDMINE (LOCKED): the hook caches a module-private ``_TRACER`` and does
# NOT call ``trace.set_tracer_provider()``, so a global-provider test would MISS
# its spans → FALSE GREEN. Inject via the module's OWN factory
# (``_build_span_processor``) + reset ``_TRACER=None`` so ``_get_tracer()`` rebuilds
# the provider/tracer through the patched factory. ``SimpleSpanProcessor`` is
# synchronous, so no ``force_flush`` is needed.
#
# REJECTED hacks: stand up a live OTLP collector / install
# ``opentelemetry-exporter-otlp`` (env-dependent, non-deterministic, adds a
# deliberately-optional dep); a global ``set_tracer_provider(InMemory…)`` test
# (silently misses the hook's own ``_TRACER`` → false green).
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_otel_tracing_exports_one_span_with_attrs_via_in_memory_exporter(
    monkeypatch,
):
    """The hook EXPORTS exactly 1 span (right attrs + scope) through an injected in-memory exporter (ISS-010).

    Injection seam (LOCKED): monkeypatch the hook's OWN ``_build_span_processor``
    factory to a ``SimpleSpanProcessor(InMemorySpanExporter())`` and reset the
    module-private ``_TRACER`` to ``None`` — the hook does NOT use the global
    provider, so a ``set_tracer_provider`` approach would silently miss its
    ``_TRACER`` (false green). Driving the real ``handle`` then proves the span
    machinery + the audit row are both intact.
    """
    from agents.capabilities.hooks import otel_tracing as otel
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()  # HOLD the ref — read finished spans off it.
    # Inject via the hook's OWN factory (mandatory — NOT a global provider).
    monkeypatch.setattr(otel, "_build_span_processor", lambda: SimpleSpanProcessor(exporter))
    # Reset the cached tracer so _get_tracer() rebuilds through the patched factory.
    monkeypatch.setattr(otel, "_TRACER", None)

    hook = otel.OtelTracingHook()
    runner = _RecordingRunner()
    ctx = _Ctx(runner)

    result = await hook.handle({"event": "before_step", "agent_id": "build"}, ctx)

    # SimpleSpanProcessor is synchronous — the span is already finished + exported.
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "hook.before_step"
    assert span.attributes["flowin.hook"] == "otel_tracing"
    assert span.attributes["flowin.event"] == "before_step"
    assert span.attributes["flowin.agent_id"] == "build"
    # The instrumentation scope is the hook's tracer identity (process-wide).
    assert span.instrumentation_scope.name == otel._TRACER_NAME
    assert span.instrumentation_scope.name == "flowin.agents.hooks.otel_tracing"

    # The audit half stays intact: continue + one hook_runs row with span=True.
    assert result.outcome == HOOK_CONTINUE
    assert len(runner.hook_runs) == 1
    row = runner.hook_runs[0]
    assert row["hook"] == "otel_tracing"
    assert row["event"] == "before_step"
    assert row["outcome"] == HOOK_CONTINUE
    assert row["detail"]["span"] is True
    assert row["detail"]["agent_id"] == "build"

    # Belt-and-suspenders only: ``monkeypatch`` already reverts ``_TRACER`` to its
    # pre-test value on teardown (it dedupes by ``(target, name)`` and restores the
    # original captured at the first ``setattr``), so no patched tracer can leak into
    # the other otel tests. This explicit null is redundant for isolation. (IN-01)
    monkeypatch.setattr(otel, "_TRACER", None)


def test_otel_build_span_processor_degrades_to_console_when_otlp_pkg_absent(
    monkeypatch,
):
    """``_build_span_processor`` degrades to a console processor when the OTLP exporter pkg is absent (ISS-010).

    Pins the env-degradation contract (otel_tracing.py:96-101): with
    ``OTEL_EXPORTER_OTLP_ENDPOINT`` set but the OTLP exporter import forced to fail,
    the factory must fall back to ``SimpleSpanProcessor(ConsoleSpanExporter())``
    (NOT a BatchSpanProcessor/OTLP) — a non-blocking observability hook must never
    break the run because an optional exporter is absent. This is DISTINCT from
    ``..._degrades_to_noop_span_when_otel_unavailable`` (api/sdk absent).
    """
    import sys

    from agents.capabilities.hooks import otel_tracing as otel
    from opentelemetry.sdk.trace.export import (
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    # Force the lazy ``from ...trace_exporter import OTLPSpanExporter`` to raise so
    # the ``except Exception`` branch degrades to console (the OTLP pkg is optional).
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        None,
    )

    proc = otel._build_span_processor()

    # Console-degrade path: a SimpleSpanProcessor over a ConsoleSpanExporter — NOT
    # the BatchSpanProcessor(OTLP) the endpoint-configured happy path would build.
    assert isinstance(proc, SimpleSpanProcessor)
    assert isinstance(proc.span_exporter, ConsoleSpanExporter)
