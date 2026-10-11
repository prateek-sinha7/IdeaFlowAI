"""tests/agents/test_declared_gate_redo.py — declared-gate "redo with instructions".

Covers the REDO-GATE follow-up (Step.redoable): a manifest step declaring
``gates: [human]`` + ``redoable: true`` (the flag now set on ``story-layer`` in
``pdf_to_prototype/workflow.yaml``) re-runs in place when a user resolves its gate
with ``action="redo"`` + free-text instructions, delivers those instructions to the
re-run through the EXISTING generic steering-note seam (``ectx.steering_notes`` →
the ``=== USER GUIDANCE ===`` block), and re-arms the SAME gate afterwards so the
user can approve or redo again.

Drives the REAL ``ExecutionEngine.execute()`` end-to-end (offline: scripted model,
no DB/Bedrock) against a single-step ``compiled_override`` manifest — mirrors the
proven recipe in ``tests/agents/test_declared_gate_streaming.py`` /
``test_redo_gate_safety.py``.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.agents._scripted_model import (  # noqa: E402
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _ScriptedTurn,
)

_EVENT_TIMEOUT_S = 60.0


def _build_compiled(redoable: bool):
    """One text-only step (domain-analyst) declaring ``gates:[human]`` + the
    opt-in flag under test — built via the REAL compiler (not hand-rolled Step
    objects), so the manifest key-parsing path is covered too."""
    from agents.capabilities.registry import CapabilityRegistry, discover
    from agents.workflows.compiler import WorkflowCompiler
    from agents.workflows.manifest import WorkflowManifest

    discover()
    registry = CapabilityRegistry()
    manifest = WorkflowManifest(
        id="redo-gate-test-wf",
        steps=[
            {
                "agent": "domain-analyst",
                "strategy": "single_shot",
                "gates": ["human"],
                "redoable": redoable,
            }
        ],
        deliverable={"strategy": "streamed_text", "name": "out.txt"},
        planner="skip",
        clarify={"mode": "off", "defaults": []},
    )
    return WorkflowCompiler().compile(manifest, registry)


class _Harness:
    """Patches create_runner with a per-call-index scripted model + builds an
    ExecutionEngine wired for an offline drive (mirrors test_redo_gate_safety's
    _EngineHarness, generalized to a full execute() drive)."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = texts
        self._call_index = 0

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
            idx = min(self._call_index, len(self._texts) - 1)
            self._call_index += 1
            ctx.model = ScriptedFakeChatModel(
                [_ScriptedTurn(texts=[self._texts[idx]], usage=(5, 3))]
            )
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


async def _drive(engine, compiled, run_id: str, on_ready):
    """Drive engine.execute() over the compiled_override, calling on_ready(event)
    for every review_gate_ready and returning every event collected."""
    from agents.loader import load_agent_spec

    events: list[dict] = []
    gen = engine.execute(
        agents=[load_agent_spec("domain-analyst")],
        user_message="Research the market for a widget.",
        pipeline_run_id=run_id,
        pipeline_type="custom",
        user_id="harness-user",
        compiled_override=compiled,
    )
    try:
        while True:
            try:
                ev = await asyncio.wait_for(gen.__anext__(), timeout=_EVENT_TIMEOUT_S)
            except StopAsyncIteration:
                break
            events.append(ev)
            if ev.get("type") == "review_gate_ready":
                await on_ready(ev)
    finally:
        await gen.aclose()
    return events


@pytest.mark.asyncio
async def test_redoable_step_re_runs_with_instructions_and_rearms_gate() -> None:
    """A redo at an opted-in (``redoable: true``) declared gate:

    * re-runs the step (a SECOND ``agent_start``/``agent_input``/``agent_complete``);
    * delivers the user's free-text instructions to the re-run via the generic
      steering-note seam (the ``=== USER GUIDANCE ===`` block in the re-run's
      composed context — NOT a second injection mechanism);
    * re-arms the SAME gate afterwards (a SECOND ``review_gate_ready`` for the
      same agent_id) so the user can approve or redo again;
    * an eventual approve completes the run.
    """
    compiled = _build_compiled(redoable=True)
    assert compiled.steps[0].redoable is True

    run_id = f"redo-gate-{uuid.uuid4().hex[:8]}"
    readies: list[dict] = []

    async def _on_ready(ev):
        readies.append(ev)
        engine = harness.engine
        gate_key = ev["data"]["gate_key"]
        if len(readies) == 1:
            assert ev["data"]["redoable"] is True
            await engine._store.set_review_response(
                gate_key,
                approved=False,
                action="redo",
                instructions="focus on enterprise buyers",
            )
        else:
            await engine._store.set_review_response(gate_key, approved=True)

    with _Harness(["first pass output. ", "second pass output. "]) as harness:
        events = await _drive(harness.engine, compiled, run_id, _on_ready)

    types = [e.get("type") for e in events]

    # Two full dispatches of the SAME agent.
    assert types.count("agent_start") == 2, types
    assert types.count("agent_complete") == 2, types
    # The gate re-armed: two review_gate_ready for the same agent_id.
    assert len(readies) == 2
    assert (
        readies[0]["data"]["agent_id"]
        == readies[1]["data"]["agent_id"]
        == "domain-analyst"
    )

    # The RE-RUN's context carries the redo instructions via the steering-note seam.
    agent_inputs = [e for e in events if e.get("type") == "agent_input"]
    assert len(agent_inputs) == 2
    assert "USER GUIDANCE" not in agent_inputs[0]["data"]["context_message"]
    assert "focus on enterprise buyers" in agent_inputs[1]["data"]["context_message"]
    assert "USER GUIDANCE" in agent_inputs[1]["data"]["context_message"]

    # The run completed after the second (approved) pass.
    assert "pipeline_complete" in types, types
    assert "pipeline_cancelled" not in types


@pytest.mark.asyncio
async def test_non_redoable_declared_gate_unaffected_by_redo_action() -> None:
    """A step that does NOT opt in (``redoable`` absent/false, the manifest
    default) keeps the pre-existing behaviour: a redo action does not re-run the
    step or open a second gate (INV-3 — dormant unless a workflow opts in)."""
    compiled = _build_compiled(redoable=False)
    assert compiled.steps[0].redoable is False

    run_id = f"no-redo-gate-{uuid.uuid4().hex[:8]}"
    readies: list[dict] = []

    followups: list[asyncio.Task] = []

    async def _on_ready(ev):
        readies.append(ev)
        engine = harness.engine
        gate_key = ev["data"]["gate_key"]
        assert ev["data"]["redoable"] is False
        await engine._store.set_review_response(
            gate_key, approved=False, action="redo", instructions="ignored"
        )

        # ISS-090: _run_review_gate REFUSES a redo this firing never advertised
        # and keeps the SAME gate open. A real user then approves; the scripted
        # client does the same once the refusal has been processed.
        async def _approve_after_refusal():
            await asyncio.sleep(0.5)
            await engine._store.set_review_response(gate_key, approved=True)

        followups.append(asyncio.create_task(_approve_after_refusal()))

    with _Harness(["only pass output. "]) as harness:
        events = await _drive(harness.engine, compiled, run_id, _on_ready)
    for task in followups:
        await task

    types = [e.get("type") for e in events]

    # Exactly one dispatch, one gate — the redo action was refused, not honoured.
    assert types.count("agent_start") == 1, types
    assert len(readies) == 1
    # The refused redo neither re-ran the step nor ended the run: the follow-up
    # approve on the still-open gate completes it.
    assert "pipeline_complete" in types, types
