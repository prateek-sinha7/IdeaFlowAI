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
    """Minimal compiled Step stand-in — the hook seam reads ``agent_id`` + ``tools``."""

    def __init__(self, agent_id="step-x", *, tools=None) -> None:
        self.agent_id = agent_id
        self.tools = tools if tools is not None else _Perms()


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
    step = _Step("build", tools=_Perms(read_files=True))

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
    step = _Step("build", tools=_Perms(read_files=True))

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
    unbound hook never fires). The wildcard observability hook (otel_tracing) IS
    bound (no required permission) and DOES record a continue row for the event — so
    the assertion is scoped to the scanner, not the total row count.
    """
    from agents.execution_engine.engine import ExecutionEngine

    engine = ExecutionEngine.__new__(ExecutionEngine)
    reg = CapabilityRegistry()
    runner = _RecordingRunner()
    ectx = _Ctx(runner)
    step = _Step("build", tools=_Perms(read_files=False))

    secret = 'token = "ghp_0123456789abcdefghijklmnopqrstuvwxyzABCD"'
    outcome = await engine._fire_hooks(
        "before_write", step, ectx, reg, payload=secret
    )
    assert outcome == HOOK_CONTINUE
    # The unbound scanner never fired → no secret_scan row (no block either).
    secret_rows = [r for r in runner.hook_runs if r["hook"] == "secret_scan"]
    assert secret_rows == []


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
