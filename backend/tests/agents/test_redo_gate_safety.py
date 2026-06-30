"""tests/agents/test_redo_gate_safety.py — REDO-GATE Wave-1 safety net.

The four load-bearing safety properties the review-hardened plan (REDO-GATE-PLAN.md
v2) pins for the "redo with additional instructions" human-review-gate feature:

  * F1 — a DECLARED human/approval gate that receives a stray ``_gate_redo`` must
    CONSUME it: never yield the internal signal to the wire, never fall through to
    ``GATE_PASS`` (the un-wired declared path stays safe — F1a / T-human).
  * F2 — UNBOUNDED redos are a FLAT while-loop, not recursion: the engine call
    stack at the gate is constant across N redos (no RecursionError, no growth, F2).
  * F3 — consume-once: an empty-output OR an errored re-run after a redo must NOT
    leak ``derived_from`` lineage or a REVISE instructions block onto the NEXT
    agent (F3).
  * F5 — ``_latest_typed_content`` selects the MAX-``version`` ref, so a REJECTED
    prior version is never served as "latest" after persist + rehydrate (F5).

Offline-safe: scripted model only (no Bedrock / Postgres / Chromium). The engine
helpers mirror the proven ``tests/agents/test_model_fallback._drive_one_agent``
recipe (direct ``_run_agent`` drive with a patched ``create_runner``).
"""

from __future__ import annotations

import inspect

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory
# checkpointer BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import (  # noqa: E402
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    ScriptedNonTransientError,
    _ScriptedTurn,
)

from agents.capabilities.gates.base import (  # noqa: E402
    GATE_PASS,
    GateOutcome,
)
from agents.capabilities.gates.approval import ApprovalGate  # noqa: E402
from agents.capabilities.gates.human import HumanGate  # noqa: E402


# ===========================================================================
# Shared fakes for the DECLARED-gate (F1) unit tests
# ===========================================================================


class _FakeStep:
    def __init__(self, agent_id: str = "declared-step") -> None:
        self.agent_id = agent_id
        self.tools = None  # _exec_policy_snapshot getattr-chain tolerates this


class _RedoEmittingRunner:
    """A KernelServices-shaped fake whose ``run_human_gate`` delegate yields a
    ``review_gate_ready`` then a stray internal ``_gate_redo`` (as the shared
    ``_run_review_gate`` now can) — exactly the F1 attack surface."""

    def __init__(self, run_id: str = "declared-run") -> None:
        self.run_id = run_id
        self.recorded: list[tuple] = []

    async def run_human_gate(self, step, *, output: str = "", payload=None):
        gate_key = f"{self.run_id}:{getattr(step, 'agent_id', '?')}"
        # The declared path stamps redoable=False (only the inline call site sets True).
        yield {"type": "review_gate_ready", "data": {"gate_key": gate_key, "redoable": False}}
        # A scripted/malicious client sent action:"redo" → the shared primitive emits
        # this internal signal even on the un-wired declared path.
        yield {"type": "_gate_redo", "instructions": "do it differently"}

    async def record_gate_event(self, step, gate, outcome, detail=None):
        self.recorded.append((step, gate, outcome, detail))
        return "gate-event-id"

    async def read_gate_events(self, run_id):
        return []  # no prior approval → ApprovalGate falls through to the delegate


class _FakeCtx:
    def __init__(self, runner) -> None:
        self.runner = runner
        self.last_streamed = "the gated output"


async def _collect(stream):
    """Drain an evaluate_stream into (public_event_dicts, terminal_outcome)."""
    events: list[dict] = []
    terminal: GateOutcome | None = None
    async for item in stream:
        if isinstance(item, dict):
            events.append(item)
        else:
            terminal = item
    return events, terminal


@pytest.mark.asyncio
@pytest.mark.parametrize("gate_cls", [HumanGate, ApprovalGate])
async def test_f1_declared_gate_consumes_redo_never_passes_or_leaks(gate_cls) -> None:
    """F1 / T-human: a declared human|approval gate receiving ``_gate_redo`` does
    NOT advance (outcome != GATE_PASS) and does NOT leak the internal signal."""
    runner = _RedoEmittingRunner()
    ctx = _FakeCtx(runner)
    step = _FakeStep()

    events, terminal = await _collect(gate_cls().evaluate_stream(step, ctx))

    # (a) NO _gate_redo dict is yielded to the wire (no _evaluate_gates leak).
    leaked = [e for e in events if e.get("type") == "_gate_redo"]
    assert leaked == [], f"{gate_cls.__name__} leaked the internal _gate_redo signal"

    # (b) the terminal outcome is NOT GATE_PASS — the step does not silently advance.
    assert terminal is not None, f"{gate_cls.__name__} produced no terminal GateOutcome"
    assert terminal.outcome != GATE_PASS, (
        f"{gate_cls.__name__} silently PASSED on a stray redo (F1 defect)"
    )

    # The public review_gate_ready (carrying redoable=False) still flowed through —
    # the FE therefore never offers Redo on a declared gate.
    ready = [e for e in events if e.get("type") == "review_gate_ready"]
    assert ready and ready[0]["data"].get("redoable") is False

    # The audit row records the HONEST non-PASS outcome (F9), not a misleading PASS.
    assert runner.recorded, f"{gate_cls.__name__} wrote no audit row"
    assert runner.recorded[-1][2] != GATE_PASS


# ===========================================================================
# Engine drive helper for the inline-path tests (F2, F3)
# ===========================================================================


def _text_turn(text: str) -> list[_ScriptedTurn]:
    return [_ScriptedTurn(texts=[text], usage=(5, 3))]


class _EngineHarness:
    """Patch create_runner + build an ExecutionEngine for direct _run_agent drives."""

    def __init__(self, model_for) -> None:
        # model_for: callable(agent_id, call_index) -> ScriptedFakeChatModel
        self._model_for = model_for
        self._call_index: dict[str, int] = {}

    def __enter__(self):
        import agents.factory as factory_mod
        import agents.execution_engine.engine as engine_mod
        from agents.execution_engine.engine import ExecutionEngine
        from app.core.config import settings as _settings

        _settings.RUNS_ROOT = _RUNS_ROOT
        self._factory_mod = factory_mod
        self._engine_mod = engine_mod
        self._orig_cr = factory_mod.create_runner
        self._orig_ecr = getattr(engine_mod, "create_runner", None)

        def _patched(agent_id, ctx, **kw):
            idx = self._call_index.get(agent_id, 0)
            self._call_index[agent_id] = idx + 1
            ctx.model = self._model_for(agent_id, idx)
            return self._orig_cr(agent_id, ctx, **kw)

        factory_mod.create_runner = _patched
        engine_mod.create_runner = _patched

        engine = ExecutionEngine()

        async def _noop_store(*a, **k):
            return "artifact-id"

        engine._store.store = _noop_store  # type: ignore[assignment]
        self.engine = engine
        return self

    def __exit__(self, *exc):
        self._factory_mod.create_runner = self._orig_cr
        if self._orig_ecr is not None:
            self._engine_mod.create_runner = self._orig_ecr
        return False


def _make_ectx(run_id: str, gate_agent_ids=None):
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id=run_id, owner_id="anon")
    ectx.disk_principal = "anon"
    ectx.gate_agent_ids = gate_agent_ids  # None → static rule; [] → no gates
    # scoped_store left None ⇒ _dual_write_artifact writes the in-memory graph only
    # (the DB persist is best-effort and skipped) — model_resolver None ⇒ _resolve_model
    # returns the threaded model_id (the documented direct-unit path).
    return ectx


async def _drive_agent(engine, spec, ectx, results, ordered, index=0):
    events: list[dict] = []
    async for ev in engine._run_agent(
        spec,
        index,
        ordered,
        "Build me a thing for managing tasks.",
        None,  # sandbox — text-only agents never touch it
        ectx.run_id,
        "user_stories",
        engine._default_planning_context("Build me a thing for managing tasks."),
        None,
        None,
        "test-model-id",
        results,
        None,
        ectx,
    ):
        events.append(ev)
    return events


@pytest.mark.asyncio
async def test_f2_unbounded_redos_keep_a_flat_stack() -> None:
    """F2: N redos run as N flat while-loop iterations — the engine call stack at the
    gate is constant (no recursion, no RecursionError) regardless of redo count."""
    from agents.loader import load_agent_spec

    N = 80  # an explicitly-unbounded operation — recursion would have grown the stack
    depths: list[int] = []
    gate_calls = {"n": 0}

    async def _fake_gate(pipeline_run_id, agent_id, agent_name, output, redoable=False):
        # Stack depth measured at the gate, inside _run_agent's loop body.
        depths.append(len(inspect.stack()))
        gate_calls["n"] += 1
        yield {
            "type": "review_gate_ready",
            "data": {"gate_key": f"{pipeline_run_id}:{agent_id}", "redoable": redoable},
        }
        if gate_calls["n"] <= N:
            yield {"type": "_gate_redo", "instructions": ""}
        else:
            yield {"type": "review_gate_approved", "data": {}}

    spec = load_agent_spec("domain-analyst")  # text-only agent

    with _EngineHarness(lambda aid, idx: ScriptedFakeChatModel(_text_turn("spec output. "))) as h:
        h.engine._run_review_gate = _fake_gate  # type: ignore[assignment]
        ectx = _make_ectx("f2-run", gate_agent_ids=[spec.id])
        results: list[dict] = []
        await _drive_agent(h.engine, spec, ectx, results, [spec])

    assert gate_calls["n"] == N + 1, "expected N redos then one approve"
    assert len(set(depths)) == 1, (
        f"engine stack at the gate GREW across redos (recursion!): {sorted(set(depths))}"
    )


@pytest.mark.asyncio
async def test_f3_empty_output_after_redo_does_not_leak_lineage() -> None:
    """F3: a redo whose RE-RUN produces empty output must not leak derived_from or a
    REVISE block onto the next agent."""
    from agents.loader import load_agent_spec

    gate_calls = {"n": 0}

    async def _fake_gate(pipeline_run_id, agent_id, agent_name, output, redoable=False):
        gate_calls["n"] += 1
        yield {
            "type": "review_gate_ready",
            "data": {"gate_key": f"{pipeline_run_id}:{agent_id}", "redoable": redoable},
        }
        if gate_calls["n"] == 1:
            yield {"type": "_gate_redo", "instructions": "make it dark mode"}
        else:
            yield {"type": "review_gate_approved", "data": {}}

    spec_a = load_agent_spec("domain-analyst")
    spec_b = load_agent_spec("epic-architect")
    ordered = [spec_a, spec_b]

    # Agent A: iteration 1 streams real text (so a v1 artifact + a non-None redo
    # lineage exist); iteration 2 (the re-run) streams EMPTY output.
    def _model_for(agent_id, idx):
        if agent_id == spec_a.id:
            return ScriptedFakeChatModel(
                [_ScriptedTurn(texts=["real spec. "], usage=(5, 3))]
                if idx == 0
                else [_ScriptedTurn(texts=[""], usage=(0, 0))]
            )
        return ScriptedFakeChatModel(_text_turn("epic output. "))

    with _EngineHarness(_model_for) as h:
        h.engine._run_review_gate = _fake_gate  # type: ignore[assignment]
        ectx = _make_ectx("f3-empty-run", gate_agent_ids=[spec_a.id])
        results: list[dict] = []
        await _drive_agent(h.engine, spec_a, ectx, results, ordered, index=0)

        # After agent A, the consume-once discipline left ectx clean.
        assert ectx.redo_directive == "", "redo_directive leaked past agent A"

        # The rejected v1 (the MAIN-kind handoff write) IS still present and was NOT
        # superseded by a v2 (the empty re-run wrote nothing) — decision #4.
        a_main = [
            r for r in ectx.artifacts.tree(ectx.run_id)
            if r.producer_agent == spec_a.id and r.kind == "summary"
        ]
        assert len(a_main) == 1 and a_main[0].version == 1

        # Now run agent B (un-gated) and assert NO leaked lineage / REVISE block.
        b_events = await _drive_agent(h.engine, spec_b, ectx, results, ordered, index=1)

    b_main = [
        r for r in ectx.artifacts.tree(ectx.run_id)
        if r.producer_agent == spec_b.id and r.kind == "summary"
    ]
    assert b_main, "agent B wrote no main artifact"
    assert b_main[-1].derived_from is None, (
        "agent B's artifact inherited a spurious derived_from (lineage leak, F3)"
    )
    b_input = next(e for e in b_events if e["type"] == "agent_input")
    assert "ADDITIONAL INSTRUCTIONS" not in b_input["data"]["context_message"], (
        "agent B's context leaked a REVISE block (directive leak, F3)"
    )


@pytest.mark.asyncio
async def test_f3_exception_after_redo_does_not_leak_lineage() -> None:
    """F3: a redo whose RE-RUN raises must not leak derived_from or a REVISE block."""
    from agents.loader import load_agent_spec

    gate_calls = {"n": 0}

    async def _fake_gate(pipeline_run_id, agent_id, agent_name, output, redoable=False):
        gate_calls["n"] += 1
        yield {
            "type": "review_gate_ready",
            "data": {"gate_key": f"{pipeline_run_id}:{agent_id}", "redoable": redoable},
        }
        # The first (and only reached) gate firing requests a redo; iteration 2 raises
        # before reaching the gate again.
        yield {"type": "_gate_redo", "instructions": "make it dark mode"}

    spec_a = load_agent_spec("domain-analyst")
    spec_b = load_agent_spec("epic-architect")
    ordered = [spec_a, spec_b]

    def _model_for(agent_id, idx):
        if agent_id == spec_a.id:
            if idx == 0:
                return ScriptedFakeChatModel([_ScriptedTurn(texts=["real spec. "], usage=(5, 3))])
            # iteration 2 (the re-run) hard-fails (non-transient → no model switch,
            # propagates to _run_agent's except handler).
            return ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError())
        return ScriptedFakeChatModel(_text_turn("epic output. "))

    with _EngineHarness(_model_for) as h:
        h.engine._run_review_gate = _fake_gate  # type: ignore[assignment]
        ectx = _make_ectx("f3-exc-run", gate_agent_ids=[spec_a.id])
        results: list[dict] = []
        a_events = await _drive_agent(h.engine, spec_a, ectx, results, ordered, index=0)

        # Agent A errored on the re-run (an agent_error was emitted) but left ectx clean.
        assert any(e["type"] == "agent_error" for e in a_events)
        assert ectx.redo_directive == "", "redo_directive leaked past an errored re-run"

        b_events = await _drive_agent(h.engine, spec_b, ectx, results, ordered, index=1)

    b_main = [
        r for r in ectx.artifacts.tree(ectx.run_id)
        if r.producer_agent == spec_b.id and r.kind == "summary"
    ]
    assert b_main, "agent B wrote no main artifact"
    assert b_main[-1].derived_from is None, (
        "agent B inherited a spurious derived_from after an errored redo (F3)"
    )
    b_input = next(e for e in b_events if e["type"] == "agent_input")
    assert "ADDITIONAL INSTRUCTIONS" not in b_input["data"]["context_message"]


# ===========================================================================
# F5 — latest-by-version (rejected version never served after rehydrate)
# ===========================================================================


@pytest.mark.asyncio
async def test_f5_latest_typed_content_is_max_version_after_rehydrate() -> None:
    """F5: after persist + rehydrate (where ``store.tree()`` re-adopts refs in an
    arbitrary order), ``_latest_typed_content`` returns the APPROVED higher-version
    ref — never the REJECTED prior version."""
    from agents.artifacts.graph import ArtifactGraph
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.context import ExecutionContext

    run_id = "f5-run"
    producer = "prototype-specify"

    # Build the two versions in a source graph (v1 rejected, v2 approved redo).
    src = ArtifactGraph()
    v1 = src.write_ref(
        run_id=run_id, owner_id="anon", workspace_id="ws", kind="spec",
        producer_step=producer, producer_agent=producer, task_id=None,
        content="REJECTED v1", location="spec.md",
    )
    v2 = src.write_ref(
        run_id=run_id, owner_id="anon", workspace_id="ws", kind="spec",
        producer_step=producer, producer_agent=producer, task_id=None,
        content="APPROVED v2", location="spec.md", derived_from=v1.id,
    )
    assert (v1.version, v2.version) == (1, 2)

    # Simulate a rehydrate that re-adopts refs in REVERSE (rejected AFTER approved) —
    # the order tree() insertion would otherwise hand back.
    rehydrated = ArtifactGraph()
    rehydrated.adopt(v2)
    rehydrated.adopt(v1)
    assert [r.content for r in rehydrated.tree(run_id)] == ["APPROVED v2", "REJECTED v1"]

    ectx = ExecutionContext(run_id=run_id, owner_id="anon")
    ectx.artifacts = rehydrated

    latest = ExecutionEngine()._latest_typed_content(ectx, producer)
    assert latest == "APPROVED v2", (
        "latest selection served the REJECTED prior version after rehydrate (F5)"
    )
