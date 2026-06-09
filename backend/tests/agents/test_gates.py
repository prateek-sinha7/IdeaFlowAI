"""tests/agents/test_gates.py — the GateHandler registry + four gates (08-02 / GATE-01..03).

08-02 stands up the ``GateHandler`` registry (D-03): ``human`` / ``validation`` /
``approval`` / ``security`` registered as real ``GateHandler`` impls resolvable via
``CapabilityRegistry().resolve("gate", name)``, each evaluating to an outcome
``pass | block | wait_human`` and writing a ``gate_events`` row.

This suite covers Task-2 (the four impls) + Task-3 (the engine step-boundary
seam). Offline — no live LLM / Bedrock. The validation-gate tests register a tiny
in-test FAKE validator (the real html_static/html_render/Tier validators land in
08-04) to prove the gate's WIRING: ``resolve("validator", name)`` + the imported
``map_severity`` + block-critical / warn-non-critical policy.
"""

from __future__ import annotations

import pytest

import agents.capabilities.registry as registry_mod
from agents.capabilities.gates.base import GATE_BLOCK, GATE_PASS, GATE_WAIT_HUMAN
from agents.capabilities.registry import CapabilityRegistry, register


# ════════════════════════════════════════════════════════════════════════════
# Registry save/restore (08-01 Issues-Encountered pattern: snapshot AFTER discover)
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_registry():
    """Save/restore the process-global registry maps around each test (D-12)."""
    registry_mod.discover()  # bind built-ins before snapshotting (import-side-effect)
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
# Fakes — a minimal ctx + ctx.runner handle that records gate_events, a fake step
# ════════════════════════════════════════════════════════════════════════════


class _RecordingRunner:
    """Minimal ctx.runner handle: records record_gate_event calls + delegates HITL."""

    def __init__(self, review_events=None) -> None:
        self.gate_events: list[dict] = []
        self._review_events = review_events or []

    async def record_gate_event(self, step, gate, outcome, detail=None):
        self.gate_events.append(
            {"step": step, "gate": gate, "outcome": outcome, "detail": detail}
        )
        return f"gate-row-{len(self.gate_events)}"

    async def run_human_gate(self, step, ctx):
        """Stand-in for the human-gate delegate (routes to _run_review_gate)."""
        return list(self._review_events)


class _Ctx:
    """Minimal ExecutionContext stand-in — gates read .runner only."""

    def __init__(self, runner) -> None:
        self.runner = runner


class _Step:
    def __init__(self, agent_id="step-x", *, validators=None, tools=None) -> None:
        self.agent_id = agent_id
        self.validators = list(validators or [])
        self.tools = tools


class _ToolGrant:
    """Minimal ToolPermissions stand-in for the security gate."""

    def __init__(self, *, exec=False, network=False, secrets=None) -> None:
        self.exec = exec
        self.network = network
        self.secrets = list(secrets or [])


class _Issue:
    """Fake validator Issue carrying an internal P0–P3 severity."""

    def __init__(self, severity: str, message: str = "x") -> None:
        self.severity = severity
        self.message = message


class _FakeValidator:
    """In-test validator (the real ones land in 08-04) returning preset issues."""

    name = "fake_validator"

    def __init__(self, issues) -> None:
        self._issues = list(issues)

    async def validate(self, target):
        return list(self._issues)


def _register_fake_validator(name: str, issues) -> None:
    """Bind a fake validator into the registry for a validation-gate test."""
    registry_mod._KNOWN.add(("validator", name))
    registry_mod._IMPLS[("validator", name)] = _FakeValidator(issues)
    registry_mod._TRUST[("validator", name)] = True


# ════════════════════════════════════════════════════════════════════════════
# Resolution — all four gate kinds resolve via the registry after discover()
# ════════════════════════════════════════════════════════════════════════════


def test_four_gates_resolve_from_registry():
    r = CapabilityRegistry()
    for name in ("human", "validation", "approval", "security"):
        gate = r.resolve("gate", name)
        assert gate.name == name
        assert hasattr(gate, "evaluate")


# ════════════════════════════════════════════════════════════════════════════
# security gate — default-denies exec/network/secrets (exec OFF this phase)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_security_gate_blocks_exec_request():
    runner = _RecordingRunner()
    ctx = _Ctx(runner)
    gate = CapabilityRegistry().resolve("gate", "security")
    step = _Step(tools=_ToolGrant(exec=True))

    result = await gate.evaluate(step, ctx)
    assert result.outcome == GATE_BLOCK
    # gate_events row written with the block outcome
    assert runner.gate_events[-1]["gate"] == "security"
    assert runner.gate_events[-1]["outcome"] == GATE_BLOCK


@pytest.mark.asyncio
async def test_security_gate_passes_when_no_privileged_request():
    runner = _RecordingRunner()
    gate = CapabilityRegistry().resolve("gate", "security")
    step = _Step(tools=_ToolGrant(exec=False, network=False))

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_PASS


# ════════════════════════════════════════════════════════════════════════════
# approval gate — explicit sign-off → wait_human
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_approval_gate_waits_for_human():
    runner = _RecordingRunner()
    gate = CapabilityRegistry().resolve("gate", "approval")
    step = _Step()

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_WAIT_HUMAN
    assert runner.gate_events[-1]["gate"] == "approval"
    assert runner.gate_events[-1]["outcome"] == GATE_WAIT_HUMAN


# ════════════════════════════════════════════════════════════════════════════
# validation gate — P0 blocks; P2 emits validation_warning + proceeds
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_validation_gate_blocks_on_p0_critical():
    _register_fake_validator("v_critical", [_Issue("P0", "broken nav")])
    runner = _RecordingRunner()
    gate = CapabilityRegistry().resolve("gate", "validation")
    step = _Step(validators=["v_critical"])

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_BLOCK
    assert runner.gate_events[-1]["outcome"] == GATE_BLOCK


@pytest.mark.asyncio
async def test_validation_gate_warns_on_p2_and_proceeds():
    _register_fake_validator("v_minor", [_Issue("P2", "low contrast")])
    runner = _RecordingRunner()
    gate = CapabilityRegistry().resolve("gate", "validation")
    step = _Step(validators=["v_minor"])

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_PASS
    # A residual non-critical issue emits a validation_warning event (additive).
    warn_types = [e["type"] for e in result.events]
    assert "validation_warning" in warn_types
    assert runner.gate_events[-1]["outcome"] == GATE_PASS


@pytest.mark.asyncio
async def test_validation_gate_maps_severity_through_imported_map_severity():
    """The gate maps internal P0–P3 via the SHARED map_severity (UI labels in detail)."""
    _register_fake_validator("v_mix", [_Issue("P2", "a"), _Issue("P3", "b")])
    runner = _RecordingRunner()
    gate = CapabilityRegistry().resolve("gate", "validation")
    step = _Step(validators=["v_mix"])

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_PASS
    # The warning detail surfaces UI labels (MEDIUM/LOW) — proof of map_severity use.
    warn = next(e for e in result.events if e["type"] == "validation_warning")
    labels = {i["severity"] for i in warn["data"]["issues"]}
    assert labels <= {"MEDIUM", "LOW"}
    assert "MEDIUM" in labels


@pytest.mark.asyncio
async def test_validation_gate_no_validators_passes_clean():
    runner = _RecordingRunner()
    gate = CapabilityRegistry().resolve("gate", "validation")
    step = _Step(validators=[])

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_PASS
    assert result.events == []


# ════════════════════════════════════════════════════════════════════════════
# Engine step-boundary seam (Task 3) — _evaluate_gates pre/post + halt
# ════════════════════════════════════════════════════════════════════════════


def _engine():
    from agents.execution_engine.engine import ExecutionEngine

    return ExecutionEngine()


async def _collect_gates(engine, step, ctx, *, phase):
    """Drain the engine's _evaluate_gates generator into a (events, outcomes) pair."""
    from agents.capabilities.registry import CapabilityRegistry

    events, outcomes = [], []
    async for ev, outcome in engine._evaluate_gates(
        step, ctx, CapabilityRegistry(), phase=phase
    ):
        events.append(ev)
        outcomes.append(outcome)
    return events, outcomes


class _GatedStep(_Step):
    def __init__(self, agent_id="step-x", *, gates=None, **kw) -> None:
        super().__init__(agent_id, **kw)
        self.gates = list(gates or [])


@pytest.mark.asyncio
async def test_engine_pre_step_security_gate_halts_with_block_event():
    """A step declaring gates:[security] requesting exec halts at the boundary
    with a block outcome + an additive gate_blocked event (Task-3 behavior)."""
    engine = _engine()
    runner = _RecordingRunner()
    ctx = _Ctx(runner)
    step = _GatedStep(gates=["security"], tools=_ToolGrant(exec=True))

    events, outcomes = await _collect_gates(engine, step, ctx, phase="pre")
    assert GATE_BLOCK in outcomes
    assert any(e["type"] == "gate_blocked" for e in events)


@pytest.mark.asyncio
async def test_engine_pre_phase_skips_post_only_validation_gate():
    """The validation gate is POST-step: it does not fire in the pre phase."""
    _register_fake_validator("v_blk", [_Issue("P0")])
    engine = _engine()
    step = _GatedStep(gates=["validation"], validators=["v_blk"])

    events, outcomes = await _collect_gates(engine, step, _Ctx(_RecordingRunner()), phase="pre")
    assert events == [] and outcomes == []


@pytest.mark.asyncio
async def test_engine_post_phase_runs_validation_gate_only():
    """The validation gate fires in the POST phase; a pre-step gate does not."""
    _register_fake_validator("v_warn", [_Issue("P2")])
    engine = _engine()
    step = _GatedStep(gates=["security", "validation"], validators=["v_warn"],
                      tools=_ToolGrant(exec=True))

    events, outcomes = await _collect_gates(engine, step, _Ctx(_RecordingRunner()), phase="post")
    # Only validation runs in post — it warns (P2) and passes; security is pre-only.
    assert GATE_PASS in outcomes
    assert any(e["type"] == "validation_warning" for e in events)
    assert not any(e["type"] == "gate_blocked" for e in events)


@pytest.mark.asyncio
async def test_engine_no_declared_gates_is_noop():
    """A step with no declared gates yields nothing in either phase (parity:
    existing prototype/od_* steps declare no gates → the seam is inert)."""
    engine = _engine()
    step = _GatedStep(gates=[])
    for phase in ("pre", "post"):
        events, outcomes = await _collect_gates(engine, step, _Ctx(_RecordingRunner()), phase=phase)
        assert events == [] and outcomes == []


@pytest.mark.asyncio
async def test_engine_gate_that_raises_is_swallowed_not_aborting():
    """A gate that raises is treated as pass (a gate failure must never abort a run)."""
    engine = _engine()

    class _BoomGate:
        name = "validation"

        async def evaluate(self, step, ctx):
            raise RuntimeError("boom")

    registry_mod._IMPLS[("gate", "validation")] = _BoomGate()
    step = _GatedStep(gates=["validation"])
    events, outcomes = await _collect_gates(engine, step, _Ctx(_RecordingRunner()), phase="post")
    assert events == [] and outcomes == []
