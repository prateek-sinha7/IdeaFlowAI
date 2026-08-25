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
import json
from types import SimpleNamespace


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


class _GateRow:
    """Stand-in for a persisted gate_events row (D-03 read returns these)."""

    def __init__(self, *, gate: str, outcome: str) -> None:
        self.gate = gate
        self.outcome = outcome


class _RecordingRunner:
    """Minimal ctx.runner handle: records record_gate_event calls + delegates HITL.

    Scripts the HITL delegate (``run_human_gate``) by yielding preset review events
    (10-03 approve/reject scripting) and pre-seeds the D-03 ``read_gate_events``
    memory. Exposes ``run_id`` + an optional bound ``workspace`` (policy snapshot).
    """

    def __init__(
        self,
        review_events=None,
        *,
        prior_gate_rows=None,
        workspace=None,
        run_id="run-x",
    ) -> None:
        self.gate_events: list[dict] = []
        self._review_events = review_events or []
        self._prior_rows = list(prior_gate_rows or [])
        self.workspace = workspace
        self.run_id = run_id
        self.delegate_payloads: list = []  # records each run_human_gate payload arg

    async def record_gate_event(self, step, gate, outcome, detail=None):
        self.gate_events.append(
            {"step": step, "gate": gate, "outcome": outcome, "detail": detail}
        )
        return f"gate-row-{len(self.gate_events)}"

    async def read_gate_events(self, run_id):
        """D-03 first-exec memory — returns any pre-seeded prior approval rows."""
        return list(self._prior_rows)

    async def run_human_gate(self, step, *, output="", payload=None):
        """Stand-in for the ONE HITL delegate (routes to _run_review_gate).

        Async generator matching the parameterized KernelServices signature; yields
        the scripted review events. Records the payload so a test can assert the D-04
        policy snapshot rode the delegate.
        """
        self.delegate_payloads.append(payload if payload is not None else output)
        for event in list(self._review_events):
            yield event


class _ExecPolicy:
    """Minimal bound ExecutionPolicy stand-in (the constrained exec profile)."""

    def __init__(
        self, *, exec_allow=None, cpu_seconds=60, mem_mb=512, wall_seconds=120,
        network=False,
    ) -> None:
        self.exec_allow = list(exec_allow if exec_allow is not None else ["python3"])
        self.cpu_seconds = cpu_seconds
        self.mem_mb = mem_mb
        self.wall_seconds = wall_seconds
        self.network = network


class _Workspace:
    """Minimal bound Workspace stand-in carrying the exec policy (the §15 binding)."""

    def __init__(self, *, policy=None) -> None:
        self.policy = policy if policy is not None else _ExecPolicy()


class _Ctx:
    """Minimal ExecutionContext stand-in — gates read .runner only.

    ``gate_agent_ids`` is also read by ``_evaluate_gates``' declared-``human``
    dedupe (WR-02): ``None`` ⇒ "use the static AGENT.md defaults" — the same
    default the real ``ExecutionContext`` field carries.
    """

    def __init__(self, runner, *, gate_agent_ids=None) -> None:
        self.runner = runner
        self.gate_agent_ids = gate_agent_ids


class _Step:
    def __init__(
        self, agent_id="step-x", *, validators=None, tools=None, gates=None, trust=None
    ) -> None:
        self.agent_id = agent_id
        self.validators = list(validators or [])
        self.tools = tools
        self.gates = list(gates or [])
        if trust is not None:
            self.trust = trust


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
# security gate — profile-conditional exec PASS (10-03); network/secrets BLOCK
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_security_gate_passes_file_trust_exec_with_approval_and_profile():
    """A file/builtin-trust exec step WITH approval declared + a constrained profile
    attached (bound workspace policy with a non-empty allow-list) → GATE_PASS + a
    pass gate_events row (10-03 / T-10-03-01)."""
    runner = _RecordingRunner(workspace=_Workspace())  # policy has ["python3"]
    ctx = _Ctx(runner)
    gate = CapabilityRegistry().resolve("gate", "security")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, ctx)
    assert result.outcome == GATE_PASS
    assert runner.gate_events[-1]["gate"] == "security"
    assert runner.gate_events[-1]["outcome"] == GATE_PASS


@pytest.mark.asyncio
async def test_security_gate_passes_exec_when_workspace_not_yet_bound():
    """An exec step with approval declared but NO bound workspace yet → PASS (profile
    presence is implied by the exec-conditional §15 provisioning; do NOT block on an
    unbound workspace, RESEARCH Open Question 2)."""
    runner = _RecordingRunner(workspace=None)
    gate = CapabilityRegistry().resolve("gate", "security")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_PASS


@pytest.mark.asyncio
async def test_security_gate_blocks_network_request_unchanged():
    """A network request BLOCKS regardless of trust (unchanged — T-10-03-02)."""
    runner = _RecordingRunner(workspace=_Workspace())
    gate = CapabilityRegistry().resolve("gate", "security")
    step = _Step(tools=_ToolGrant(network=True), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_BLOCK
    assert "network" in runner.gate_events[-1]["detail"]["denied"]


@pytest.mark.asyncio
async def test_security_gate_blocks_secrets_request_unchanged():
    """A secrets request BLOCKS regardless of trust (unchanged — T-10-03-02)."""
    runner = _RecordingRunner(workspace=_Workspace())
    gate = CapabilityRegistry().resolve("gate", "security")
    step = _Step(tools=_ToolGrant(secrets=["MY_KEY"]), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_BLOCK
    assert "secrets" in runner.gate_events[-1]["detail"]["denied"]


@pytest.mark.asyncio
async def test_security_gate_blocks_exec_without_approval_declared():
    """An exec step WITHOUT the approval gate declared is NOT a silent pass — D-01
    defense-in-depth BLOCKS (T-10-03-01 second line)."""
    runner = _RecordingRunner(workspace=_Workspace())
    gate = CapabilityRegistry().resolve("gate", "security")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_BLOCK
    assert runner.gate_events[-1]["outcome"] == GATE_BLOCK


@pytest.mark.asyncio
async def test_security_gate_blocks_exec_with_empty_bound_profile():
    """An exec step whose bound workspace policy has an EMPTY allow-list BLOCKs (a
    constrained profile must be attached when the workspace is bound)."""
    runner = _RecordingRunner(workspace=_Workspace(policy=_ExecPolicy(exec_allow=[])))
    gate = CapabilityRegistry().resolve("gate", "security")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_BLOCK


@pytest.mark.asyncio
async def test_security_gate_passes_when_no_privileged_request():
    runner = _RecordingRunner()
    gate = CapabilityRegistry().resolve("gate", "security")
    step = _Step(tools=_ToolGrant(exec=False, network=False))

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_PASS


# ════════════════════════════════════════════════════════════════════════════
# approval gate — HITL delegation (D-02) + first-exec memory (D-03) + payload (D-04)
# ════════════════════════════════════════════════════════════════════════════


class _NoHandleRunner:
    """Runner WITHOUT a run_human_gate handle (offline) — records gate_events only.

    No ``read_gate_events`` either, so the D-03 lookup is skipped and the gate falls
    to the offline ``wait_human`` path (NEVER auto-approve).
    """

    def __init__(self) -> None:
        self.gate_events: list[dict] = []
        self.run_id = "run-x"
        self.workspace = None

    async def record_gate_event(self, step, gate, outcome, detail=None):
        self.gate_events.append(
            {"step": step, "gate": gate, "outcome": outcome, "detail": detail}
        )
        return f"gate-row-{len(self.gate_events)}"


@pytest.mark.asyncio
async def test_approval_gate_first_exec_pauses_with_d04_payload():
    """First exec step (no prior approval row) → delegates to run_human_gate, yields
    review_gate_ready, and the D-04 policy snapshot (allow-list, caps, scrubbed-env
    note, egress-denied) rode the delegate (10-03 / D-04)."""
    review = [{"type": "review_gate_ready", "data": {"output": "ignored"}}]
    runner = _RecordingRunner(review, workspace=_Workspace())
    gate = CapabilityRegistry().resolve("gate", "approval")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))

    # The review_gate_ready flowed through (pause surfaced).
    assert any(e["type"] == "review_gate_ready" for e in result.events)
    # The D-04 snapshot rode the delegate as the payload.
    payload = runner.delegate_payloads[-1]
    assert isinstance(payload, dict)
    assert payload["exec_allow"] == ["python3"]
    assert payload["caps"]["cpu_seconds"] == 60
    assert "scrubbed_env" in payload
    assert payload["egress_denied"] is True


@pytest.mark.asyncio
async def test_approval_gate_approve_resolves_to_pass():
    """Scripting the delegate to yield review_gate_approved → GATE_PASS + a
    gate='approval'/outcome=pass row written."""
    review = [{"type": "review_gate_approved", "data": {}}]
    runner = _RecordingRunner(review, workspace=_Workspace())
    gate = CapabilityRegistry().resolve("gate", "approval")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_PASS
    assert runner.gate_events[-1]["gate"] == "approval"
    assert runner.gate_events[-1]["outcome"] == GATE_PASS


@pytest.mark.asyncio
async def test_approval_gate_reject_resolves_to_block():
    """Scripting the delegate to yield _gate_rejected → GATE_BLOCK."""
    review = [{"type": "_gate_rejected"}]
    runner = _RecordingRunner(review, workspace=_Workspace())
    gate = CapabilityRegistry().resolve("gate", "approval")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_BLOCK
    assert runner.gate_events[-1]["outcome"] == GATE_BLOCK


@pytest.mark.asyncio
async def test_approval_gate_second_exec_does_not_re_pause_d03():
    """With a prior approval-pass row present (D-03 durable memory), a second exec
    step → GATE_PASS WITHOUT calling the delegate (no review_gate_ready)."""
    prior = [_GateRow(gate="approval", outcome=GATE_PASS)]
    review = [{"type": "review_gate_ready", "data": {}}]  # would fire IF delegated
    runner = _RecordingRunner(review, prior_gate_rows=prior, workspace=_Workspace())
    gate = CapabilityRegistry().resolve("gate", "approval")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_PASS
    # The delegate was NOT called (no payload recorded) → no re-pause.
    assert runner.delegate_payloads == []
    assert not any(e["type"] == "review_gate_ready" for e in result.events)
    assert runner.gate_events[-1]["outcome"] == GATE_PASS


@pytest.mark.asyncio
async def test_approval_gate_offline_no_handle_waits_for_human():
    """No run_human_gate handle (offline) → GATE_WAIT_HUMAN (NEVER auto-approve) + a
    wait_human gate_events row."""
    runner = _NoHandleRunner()
    gate = CapabilityRegistry().resolve("gate", "approval")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security", "approval"], trust="file")

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


# ════════════════════════════════════════════════════════════════════════════
# validation gate — builds a DeliverableContext for a REAL registered validator
# (WR-01: the gate must NOT pass the raw ExecutionContext to validators)
# ════════════════════════════════════════════════════════════════════════════


class _DeliverableCtxRunner(_RecordingRunner):
    """Runner exposing the deliverable_context factory + static_check + the
    validation-results writer — the surface a REAL validator (html_static) reaches.

    Proves the gate builds a proper ``DeliverableContext`` (with ``.path``) rather
    than handing the raw ExecutionContext to the validator (WR-01).
    """

    def __init__(self, *, static_issues=None, static_warnings=None) -> None:
        super().__init__()
        self._static_issues = list(static_issues or [])
        self._static_warnings = list(static_warnings or [])
        self.seen_paths: list = []
        self.validation_results: list[dict] = []

    def deliverable_context(self, *, name, step="", content=None, task_meta=None):
        # Build the same shape KernelServices.deliverable_context returns, with a
        # resolved on-disk ``path`` for the named deliverable.
        from agents.execution_engine.kernel_services import DeliverableContext

        return DeliverableContext(
            name=name,
            runner=self,
            path=f"/sandbox/{name}",
            _content=content,
            step=step,
            task_meta=dict(task_meta or {}),
        )

    def static_check(self, path):
        # The real html_static validator calls runner.static_check(target.path) —
        # record the path so the test asserts a real DeliverableContext.path flowed.
        self.seen_paths.append(path)

        class _Result:
            issues = self._static_issues
            warnings = self._static_warnings

        return _Result()

    async def record_validation_result(self, step, validator, *, severity, attempt, issues):
        self.validation_results.append(
            {"step": step, "validator": validator, "severity": severity,
             "attempt": attempt, "issues": issues}
        )
        return f"vr-{len(self.validation_results)}"


class _DeliverableSpec:
    """Minimal compiled DeliverableSpec stand-in (carries the deliverable name)."""

    def __init__(self, name: str) -> None:
        self.name = name


class _CtxWithDeliverable(_Ctx):
    """ExecutionContext stand-in carrying the run's declared deliverable spec."""

    def __init__(self, runner, *, deliverable_name="prototype.html") -> None:
        super().__init__(runner)
        self.deliverable = _DeliverableSpec(deliverable_name)


@pytest.mark.asyncio
async def test_validation_gate_builds_deliverable_context_for_real_validator_p0_blocks():
    """A gates:[validation] step with the REAL html_static validator + a P0 static
    issue blocks — and the validator saw the on-disk path off a DeliverableContext
    (proving the gate built one, WR-01)."""
    # Discover binds the real html_static validator (app.agents.validators).
    runner = _DeliverableCtxRunner(static_issues=["broken route map (fatal)"])
    ctx = _CtxWithDeliverable(runner)
    gate = CapabilityRegistry().resolve("gate", "validation")
    step = _Step(validators=["html_static"])

    result = await gate.evaluate(step, ctx)

    assert result.outcome == GATE_BLOCK
    # The real validator read target.path off the DeliverableContext (WR-01) — NOT
    # the raw ExecutionContext (which has no .path).
    assert runner.seen_paths == ["/sandbox/prototype.html"]
    # The validation_results row was written through the DeliverableContext.runner.
    assert runner.validation_results[-1]["validator"] == "html_static"
    assert runner.gate_events[-1]["outcome"] == GATE_BLOCK


@pytest.mark.asyncio
async def test_validation_gate_builds_deliverable_context_for_real_validator_p3_warns():
    """The REAL html_static validator with only a static WARNING (advisory → P3/LOW)
    emits a validation_warning + proceeds (P2-class warn path), driven through a
    real DeliverableContext."""
    runner = _DeliverableCtxRunner(static_warnings=["orphan section (advisory)"])
    ctx = _CtxWithDeliverable(runner)
    gate = CapabilityRegistry().resolve("gate", "validation")
    step = _Step(validators=["html_static"])

    result = await gate.evaluate(step, ctx)

    assert result.outcome == GATE_PASS
    assert runner.seen_paths == ["/sandbox/prototype.html"]
    warn_types = [e["type"] for e in result.events]
    assert "validation_warning" in warn_types
    assert runner.gate_events[-1]["outcome"] == GATE_PASS


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


async def _collect_gates(engine, step, ctx, *, phase, details=None):
    """Drain the engine's _evaluate_gates generator into a (events, outcomes) pair.

    The generator yields ``(event, outcome, detail)`` 3-tuples (the 13-review
    WR-04 fix threads the terminal ``GateOutcome.detail`` — e.g. the human
    gate's edited content — through the sentinel). Pass a ``details`` list to
    additionally capture every yielded detail.
    """
    from agents.capabilities.registry import CapabilityRegistry

    events, outcomes = [], []
    async for ev, outcome, detail in engine._evaluate_gates(
        step, ctx, CapabilityRegistry(), phase=phase
    ):
        # WR-04: the generator now yields a terminal (None, outcome, detail)
        # sentinel so the halt is observable even with zero events. Mirror the
        # real callers: skip the None event when collecting events, always
        # record the outcome.
        if ev is not None:
            events.append(ev)
        outcomes.append(outcome)
        if details is not None:
            details.append(detail)
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
async def test_engine_block_with_empty_events_still_halts(monkeypatch):
    """WR-04: a gate that BLOCKS with an EMPTY events list still halts the step.

    Pre-fix the outcome was only yielded INSIDE the event loop, so a block with
    no events yielded nothing and the step silently proceeded. The terminal
    (None, outcome) sentinel must surface ``block`` even with zero events, and
    the engine's pre-step loop must set _halted from it without forwarding a
    None event.
    """
    engine = _engine()

    class _SilentBlockGate:
        name = "security"

        async def evaluate(self, step, ctx):
            class _R:
                outcome = GATE_BLOCK
                events: list = []  # blocks but emits NO event

            return _R()

    registry_mod._IMPLS[("gate", "security")] = _SilentBlockGate()
    step = _GatedStep(gates=["security"], tools=_ToolGrant(exec=True))

    events, outcomes = await _collect_gates(engine, step, _Ctx(_RecordingRunner()), phase="pre")
    # No event was emitted (the stream is unchanged — no None leaks through)...
    assert events == []
    # ...but the block outcome is observable so the caller halts the step (WR-04).
    assert GATE_BLOCK in outcomes


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


# ════════════════════════════════════════════════════════════════════════════
# WR-07 (13 review fix) — blocking outcome short-circuits; HITL/security gates
# FAIL CLOSED on a raised exception
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_blocking_gate_short_circuits_remaining_declared_gates():
    """gates:[security, human] with security blocking — the human gate must NOT
    open an HITL pause for a step that will be skipped regardless (pre-fix the
    loop continued to the next gate and asked the user to approve a dead step)."""
    engine = _engine()
    runner = _RecordingRunner(review_events=[
        {"type": "review_gate_ready", "data": {"gate_key": "run-x:step-x"}},
        {"type": "review_gate_approved", "data": {"edited": False}},
    ])
    # network=True → the real security gate BLOCKS unconditionally.
    step = _GatedStep(gates=["security", "human"], tools=_ToolGrant(network=True))

    events, outcomes = await _collect_gates(engine, step, _Ctx(runner), phase="pre")
    assert GATE_BLOCK in outcomes
    # The human gate's HITL delegate was NEVER invoked …
    assert runner.delegate_payloads == [], (
        "the human gate opened a pause after a blocking security gate (WR-07)"
    )
    # … and no review_gate_* event leaked into the stream.
    assert not any(e.get("type", "").startswith("review_gate") for e in events)


@pytest.mark.asyncio
async def test_fail_closed_gate_exception_maps_to_block_not_pass():
    """A raised security/approval/human gate must FAIL CLOSED: pre-fix the broad
    swallow treated it as PASS and the step executed WITHOUT its sign-off."""
    engine = _engine()

    class _BoomSecurity:
        name = "security"

        async def evaluate(self, step, ctx):
            raise RuntimeError("boom mid-gate")

    registry_mod._IMPLS[("gate", "security")] = _BoomSecurity()
    step = _GatedStep(gates=["security"], tools=_ToolGrant(exec=True))

    details: list = []
    events, outcomes = await _collect_gates(
        engine, step, _Ctx(_RecordingRunner()), phase="pre", details=details
    )
    assert events == []  # no UI event — the sentinel alone carries the halt
    assert outcomes == [GATE_BLOCK], (
        f"a raised fail-closed gate must yield exactly one block sentinel: {outcomes}"
    )
    assert details and details[0] and details[0]["gate"] == "security"


@pytest.mark.asyncio
async def test_raising_hitl_gate_blocks_and_stops_gate_evaluation():
    """A raised HUMAN gate fails closed too — and short-circuits what follows.

    Both gates must sit in the SAME phase or this proves nothing. ADR-0013 moved
    ``human`` into ``_POST_STEP_GATES``, so the original pairing
    (``["human", "security"]`` collected at ``phase="pre"``) no longer exercised
    the short-circuit at all: ``human`` was filtered out by phase, ``security``
    ran alone, and its ``gate_blocked`` event plus the WR-04 terminal sentinel
    yielded ``["block", "block"]`` — two outcomes from ONE gate, which read like
    a double evaluation but was just the trailing gate answering by itself.

    Paired with ``validation`` instead: both are post-step, and the validator is
    registered to BLOCK, so a broken short-circuit shows up as a second outcome
    rather than as silence.
    """
    _register_fake_validator("v_short_circuit", [_Issue("P0")])
    engine = _engine()

    class _BoomHuman:
        name = "human"

        async def evaluate_stream(self, step, ctx):
            raise RuntimeError("StateMachineError analogue")
            yield  # pragma: no cover — makes this an async generator

    registry_mod._IMPLS[("gate", "human")] = _BoomHuman()
    step = _GatedStep(
        gates=["human", "validation"], validators=["v_short_circuit"]
    )

    events, outcomes = await _collect_gates(
        engine, step, _Ctx(_RecordingRunner()), phase="post"
    )
    # block (not pass, not cancel — an exception is not a user rejection), and
    # the trailing validation gate never evaluated (single sentinel, no event:
    # a raised gate emits nothing, so the sentinel alone carries the halt).
    assert outcomes == [GATE_BLOCK]
    assert events == []


# ════════════════════════════════════════════════════════════════════════════
# WR-04 (13 review fix) — declared-gate edits are THREADED upstream, not dropped
# ════════════════════════════════════════════════════════════════════════════


_EDIT_REVIEW_SCRIPT = [
    {"type": "review_gate_ready", "data": {"gate_key": "run-x:step-x"}},
    {"type": "review_gate_approved", "data": {"edited": True}},
    {"type": "_gate_edited", "edited_content": "EDITED SPEC"},
]


@pytest.mark.asyncio
async def test_human_gate_threads_edited_content_into_outcome_detail():
    """Approve-with-edits at the human gate lands the content on GateOutcome.detail
    (pre-fix it was consumed with ``continue`` and silently lost)."""
    runner = _RecordingRunner(review_events=list(_EDIT_REVIEW_SCRIPT))
    gate = CapabilityRegistry().resolve("gate", "human")

    result = await gate.evaluate(_Step(), _Ctx(runner))
    assert result.outcome == GATE_PASS
    assert result.detail == {"edited_content": "EDITED SPEC"}
    # The gate_events audit row stays CONTENT-FREE (no user payload persisted).
    assert runner.gate_events[-1]["detail"] == {"edited": True}


@pytest.mark.asyncio
async def test_human_gate_without_edit_has_no_detail():
    runner = _RecordingRunner(review_events=[
        {"type": "review_gate_ready", "data": {"gate_key": "run-x:step-x"}},
        {"type": "review_gate_approved", "data": {"edited": False}},
    ])
    gate = CapabilityRegistry().resolve("gate", "human")

    result = await gate.evaluate(_Step(), _Ctx(runner))
    assert result.outcome == GATE_PASS
    assert result.detail is None
    assert runner.gate_events[-1]["detail"] is None


@pytest.mark.asyncio
async def test_approval_gate_explicitly_ignores_edited_content():
    """The approval payload is a POLICY SNAPSHOT — an edit has nothing to apply
    to. The gate discards it explicitly (logged) and threads NO detail."""
    runner = _RecordingRunner(review_events=list(_EDIT_REVIEW_SCRIPT))
    gate = CapabilityRegistry().resolve("gate", "approval")
    step = _Step(tools=_ToolGrant(exec=True), gates=["security", "approval"], trust="file")

    result = await gate.evaluate(step, _Ctx(runner))
    assert result.outcome == GATE_PASS
    assert result.detail is None


@pytest.mark.asyncio
async def test_engine_sentinel_carries_human_gate_edit_detail():
    """_evaluate_gates' terminal sentinel forwards the gate's detail so the
    dispatch loop can apply the edit (the WR-04 3-tuple protocol).

    Collected in the POST phase: ADR-0013 moved ``human`` into
    ``_POST_STEP_GATES`` (post-step reviews the output the step just produced;
    the pre-step variant is spelled ``before-human`` now). The phase filter
    therefore drops ``human`` entirely at ``phase="pre"``, which left this
    asserting against an empty outcome list. What it pins — that the terminal
    sentinel carries the gate's detail — is phase-agnostic; only the label was
    stale.
    """
    engine = _engine()
    runner = _RecordingRunner(review_events=list(_EDIT_REVIEW_SCRIPT))
    step = _GatedStep(gates=["human"])

    details: list = []
    events, outcomes = await _collect_gates(
        engine, step, _Ctx(runner), phase="post", details=details
    )
    assert GATE_PASS in outcomes
    assert {"edited_content": "EDITED SPEC"} in details


@pytest.mark.asyncio
async def test_apply_declared_gate_edit_rewrites_upstream_artifact_and_result(monkeypatch):
    """The kernel applies a declared-gate edit to the UPSTREAM step: a new typed
    ref version + the results entry + the running review payload (inline parity)."""
    engine = _engine()

    writes: list[dict] = []

    async def _record_dual_write(ectx, **kw):
        writes.append(kw)

    monkeypatch.setattr(engine, "_dual_write_artifact", _record_dual_write)

    from agents.artifacts.graph import ArtifactGraph

    class _Spec:
        id = "agent-a"
        name = "Agent A"

    class _Ectx:
        last_streamed = "ORIGINAL"
        run_id = "run-x"
        artifacts = ArtifactGraph()

    results = [{"agent_id": "agent-a", "output": "ORIGINAL"}]
    ectx = _Ectx()

    await engine._apply_declared_gate_edit("EDITED", results, [_Spec()], ectx)

    assert results[-1]["output"] == "EDITED"
    assert ectx.last_streamed == "EDITED"
    assert len(writes) == 1
    assert writes[0]["content"] == "EDITED"
    assert writes[0]["producer_agent"] == "agent-a"
    assert writes[0]["kind"] == "summary"  # unmapped agent id → fallback kind
    assert writes[0]["location"] == "artifact_refs/agent-a"


@pytest.mark.asyncio
async def test_apply_declared_gate_edit_with_no_upstream_is_dropped(monkeypatch):
    """No completed upstream step (gate before the FIRST agent) → nothing to
    apply; the edit is dropped with a warning, never raising."""
    engine = _engine()

    async def _boom(*a, **k):  # must never be reached
        raise AssertionError("no artifact write expected")

    monkeypatch.setattr(engine, "_dual_write_artifact", _boom)

    class _Ectx:
        last_streamed = ""

    await engine._apply_declared_gate_edit("EDITED", [], [], _Ectx())


# ════════════════════════════════════════════════════════════════════════════
# KernelServices.run_human_gate parameterize + read_gate_events handle (Task 2)
# ════════════════════════════════════════════════════════════════════════════


class _FakeReviewEngine:
    """Engine stub: _run_review_gate records the output it received + yields events."""

    def __init__(self, events) -> None:
        self._events = list(events)
        self.seen_output = None
        self.seen_cancel = None

    async def _run_review_gate(
        self, *, pipeline_run_id, agent_id, agent_name, output, cancel_event=None, **kwargs
    ):
        # ``**kwargs`` absorbs the engine parameters run_human_gate does not forward TODAY.
        # Without it this double is one forwarded parameter away from the ISS-074 TypeError.
        self.seen_output = output
        self.seen_cancel = cancel_event
        for ev in self._events:
            yield ev


class _SpecStub:
    def __init__(self, agent_id) -> None:
        self.id = agent_id
        self.name = agent_id


def _kernel_services(engine, *, scoped_store=None, cancel_event=None):
    """Build a KernelServices with a minimal ectx (only the attrs the methods read)."""
    from agents.execution_engine.kernel_services import KernelServices

    class _Ectx:
        pass

    ectx = _Ectx()
    ectx.scoped_store = scoped_store
    ks = KernelServices(
        engine=engine,
        ectx=ectx,
        sandbox=None,
        ordered_agents=[],
        user_message="",
        pipeline_run_id="run-x",
        pipeline_type="prototype",
        planning_context={},
        attached_skills=None,
        attached_hooks=None,
        model_id=None,
        results=[],
        cancel_event=cancel_event,
    )
    return ks, ectx


@pytest.mark.asyncio
async def test_run_human_gate_threads_payload_into_review_output(monkeypatch):
    """With a structured payload, run_human_gate threads the DICT into the review
    gate's output field (D-04 — rides the generic forward, no frontend rebuild)."""
    fake_engine = _FakeReviewEngine([{"type": "review_gate_ready", "data": {}}])
    ks, _ = _kernel_services(fake_engine)
    monkeypatch.setattr(ks, "_spec_for", lambda step: _SpecStub("step-x"))

    snapshot = {"kind": "approval", "exec_allow": ["python3"]}
    events = [e async for e in ks.run_human_gate(object(), payload=snapshot)]

    assert fake_engine.seen_output == snapshot  # the dict rode the output field
    assert events == [{"type": "review_gate_ready", "data": {}}]


@pytest.mark.asyncio
async def test_run_human_gate_payload_none_is_byte_identical_string_path(monkeypatch):
    """With payload=None the human-gate string output path is byte-identical (parity:
    _run_review_gate receives the same string it always did)."""
    fake_engine = _FakeReviewEngine([{"type": "review_gate_approved", "data": {}}])
    ks, _ = _kernel_services(fake_engine)
    monkeypatch.setattr(ks, "_spec_for", lambda step: _SpecStub("step-x"))

    _ = [e async for e in ks.run_human_gate(object(), output="agent html output")]
    assert fake_engine.seen_output == "agent html output"  # string forwarded unchanged
    assert fake_engine.seen_cancel is None  # no cancel_event supplied → None forwarded


@pytest.mark.asyncio
async def test_run_human_gate_threads_cancel_event_into_review_gate(monkeypatch):
    """BUG-2 Cond B (quick-260720-ec4): run_human_gate forwards the SAME cooperative
    cancel_event execute() holds into _run_review_gate, so a declared-gate-parked run
    honors Stop via the existing cancel-aware race (RED pre-fix: seen_cancel is None)."""
    import asyncio

    ev = asyncio.Event()
    fake_engine = _FakeReviewEngine([{"type": "review_gate_ready", "data": {}}])
    ks, _ = _kernel_services(fake_engine, cancel_event=ev)
    monkeypatch.setattr(ks, "_spec_for", lambda step: _SpecStub("step-x"))

    _ = [e async for e in ks.run_human_gate(object(), output="agent html output")]

    assert fake_engine.seen_cancel is ev  # the run-scoped cancel_event reached the delegate


@pytest.mark.asyncio
async def test_read_gate_events_offline_returns_empty_without_raising():
    """No scoped_store (offline harness) → read_gate_events returns [] (best-effort,
    never raises — INV-3 parity: an audit read must never abort the run)."""
    ks, _ = _kernel_services(_FakeReviewEngine([]), scoped_store=None)
    rows = await ks.read_gate_events("run-x")
    assert rows == []


@pytest.mark.asyncio
async def test_read_gate_events_degrades_on_store_failure():
    """A scoped-store read failure degrades to [] (best-effort) rather than raising."""

    class _BoomStore:
        async def read_gate_events(self, run_id):
            raise RuntimeError("db down")

    ks, _ = _kernel_services(_FakeReviewEngine([]), scoped_store=_BoomStore())
    rows = await ks.read_gate_events("run-x")
    assert rows == []


@pytest.mark.asyncio
async def test_read_gate_events_delegates_to_scoped_store():
    """With a scoped store, read_gate_events delegates and returns the store's rows."""

    class _Store:
        async def read_gate_events(self, run_id):
            assert run_id == "run-x"
            return [_GateRow(gate="approval", outcome=GATE_PASS)]

    ks, _ = _kernel_services(_FakeReviewEngine([]), scoped_store=_Store())
    rows = await ks.read_gate_events("run-x")
    assert len(rows) == 1 and rows[0].gate == "approval"


# ════════════════════════════════════════════════════════════════════════════
# §15 host seam — exec-grant detection over the compiled plan (Task 2)
# ════════════════════════════════════════════════════════════════════════════


def test_host_seam_exec_grant_detection_over_compiled_steps():
    """The host-seam grant predicate fires iff ANY compiled step grants tools.exec —
    so a no-exec plan never provisions a workspace (T-10-03-05 parity / Pitfall 3)."""

    def _grants(steps):
        # Mirror engine.execute()'s _plan_grants_exec predicate verbatim.
        return any(
            bool(getattr(getattr(s, "tools", None), "exec", False)) for s in (steps or [])
        )

    no_exec = [_Step(tools=_ToolGrant(exec=False)), _Step(tools=_ToolGrant(exec=False))]
    one_exec = [_Step(tools=_ToolGrant(exec=False)), _Step(tools=_ToolGrant(exec=True))]

    assert _grants(no_exec) is False
    assert _grants([]) is False
    assert _grants(one_exec) is True


def test_host_seam_resolves_local_runtime_and_binds_exec_workspace(tmp_path, monkeypatch):
    """When the plan grants exec, the local runtime_env resolves + create_workspace(
    exec=True, recorder=...) returns a Workspace carrying a constrained policy that
    the security gate's profile check accepts (allow-list non-empty)."""
    import agents.capabilities.registry as _reg

    _reg.discover()
    from app.core.config import settings

    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path))

    runtime = CapabilityRegistry().resolve("runtime_env", "local")
    recorded: list = []

    async def _recorder(*a, **k):
        recorded.append((a, k))

    ws = runtime.create_workspace(
        owner_id="owner-1", workspace_id="ws-1", exec=True, recorder=_recorder
    )
    # The bound workspace carries a constrained exec profile (non-empty allow-list)
    # — the exact shape the security gate's profile check reads.
    assert ws.policy.exec is True
    assert list(ws.policy.exec_allow)  # non-empty allow-list (DEFAULT_EXEC_PROFILE)


# ════════════════════════════════════════════════════════════════════════════
# Routed human gate — the declared outcomes are published as CHOICES
# ════════════════════════════════════════════════════════════════════════════


class _CapturingReviewEngine:
    """Captures every kwarg run_human_gate forwards to _run_review_gate."""

    def __init__(self) -> None:
        self.seen: dict = {}

    async def _run_review_gate(self, **kwargs):
        self.seen = kwargs
        yield {"type": "review_gate_ready", "data": {}}


async def _drive_human_gate(step, *, payload=None, output="(awaiting choice)"):
    eng = _CapturingReviewEngine()
    ks, _ = _kernel_services(eng)
    ks._spec_for = lambda _s: _SpecStub("custom-agent:pick-language")  # type: ignore[assignment]
    async for _ in ks.run_human_gate(step, output=output, payload=payload):
        pass
    return eng.seen


def _routed_step(outcomes):
    step = _GatedStep(gates=["before-human", "conditional"])
    step.route = SimpleNamespace(outcomes=outcomes)
    return step


@pytest.mark.asyncio
async def test_routed_human_gate_publishes_declared_outcomes_as_choices():
    """A human-family gate on a step that ALSO declares a route is the one case
    where the human is the router. The valid answers are already compiled; publish
    them so the UI can offer them instead of a free-text box (the answer must equal
    an outcome key exactly, and nothing told the user what those keys were)."""
    seen = await _drive_human_gate(
        _routed_step({"english": 1, "spanish": 2, "dutch": 3})
    )
    assert seen["artifact_kind"] == "conditional_gate"
    envelope = json.loads(seen["output"])
    assert envelope["choices"] == ["english", "spanish", "dutch"]
    assert envelope["prompt"] == "(awaiting choice)"


@pytest.mark.asyncio
async def test_human_gate_without_a_route_is_byte_identical():
    """DORMANCY — the invariant that keeps every production workflow unchanged.
    prototype / prototype_feature_revision / sc001-test-fixture all declare human
    gates on steps with NO route; they must keep the plain string output and an
    empty artifact_kind."""
    step = _GatedStep(gates=["human"])          # no .route attribute at all
    seen = await _drive_human_gate(step)
    assert seen["output"] == "(awaiting choice)"
    assert seen["artifact_kind"] == ""


@pytest.mark.asyncio
async def test_route_with_no_outcomes_does_not_publish_choices():
    seen = await _drive_human_gate(_routed_step({}))
    assert seen["output"] == "(awaiting choice)"
    assert seen["artifact_kind"] == ""


@pytest.mark.asyncio
async def test_approval_gate_payload_path_is_untouched():
    """The approval gate's D-04 snapshot rides the SAME output field. A non-None
    payload must skip the choice branch entirely, even on a routed step."""
    snapshot = {"exec_policy": "deny"}
    seen = await _drive_human_gate(
        _routed_step({"english": 1}), payload=snapshot
    )
    assert seen["output"] == snapshot
    assert seen["artifact_kind"] == ""

