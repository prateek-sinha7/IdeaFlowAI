"""spec 012 T35 (R-25, AC-16) — the engine threads compiled capabilities into
``AgentContext.capabilities``.

``CompiledWorkflow.capabilities`` (e.g. ``{"internet": true}``) is parsed by the
compiler and read by ``agents/factory.py::_resolve_runner_tools`` (T33), but until
T35 nothing on the engine side ever populated ``AgentContext.capabilities`` from
it — the declared flag bound nothing. The engine now carries it as
``ectx.compiled_capabilities`` (set once at run entry, the same dynamic-attr thread
as ``ectx.compiled_context_providers``/``ectx.compiled_input_providers``) and
threads it into every step's ``AgentContext(...)`` construction in ``_run_agent``,
exactly like ``step_skills``/``topic``/``step_prompt``.

Drives a real single-agent pipeline through ``ExecutionEngine.execute()`` offline
(mirrors ``tests/agents/test_chunk_sanitizer.py``'s harness): patches
``compile_for_run`` to stamp ``capabilities`` on the compiled plan, and patches
``create_runner`` to capture the ``AgentContext`` the engine actually built.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.agents._scripted_model import _RUNS_ROOT, ScriptedFakeChatModel, _ScriptedTurn

# A tool-less, single-agent-satisfiable pipeline (same choice as test_chunk_sanitizer.py).
_AGENT_ID = "domain-analyst"
_PIPELINE_TYPE = "user_stories"


async def _drive_and_capture_capabilities(capabilities: dict) -> dict:
    """Run ONE agent through ``ExecutionEngine.execute()`` offline with the compiled
    plan's ``capabilities`` set to ``capabilities``; return the ``AgentContext.capabilities``
    the engine actually passed to ``create_runner`` for that agent."""
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents

    from app.core.config import settings as _settings
    _settings.RUNS_ROOT = _RUNS_ROOT

    specs = get_pipeline_agents(_PIPELINE_TYPE)
    spec = next(s for s in specs if s.id == _AGENT_ID)

    _orig_compile_for_run = engine_mod.compile_for_run

    def _patched_compile_for_run(ptype, _orig=_orig_compile_for_run):
        compiled = _orig(ptype)
        compiled.clarify.mode = "off"
        compiled.capabilities = dict(capabilities)
        return compiled

    engine_mod.compile_for_run = _patched_compile_for_run

    captured: dict[str, Any] = {}
    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(aid, ctx, **kw):
        captured["capabilities"] = ctx.capabilities
        ctx.model = ScriptedFakeChatModel([_ScriptedTurn(texts=["done"], usage=(10, 5))])
        return _orig_create_runner(aid, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event,
                                 ptype="custom", **kwargs):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover — make it an async generator

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]

    run_id = f"capabilities-threading-{uuid.uuid4().hex[:8]}"
    kwargs: dict[str, Any] = dict(
        agents=[spec],
        user_message="Build me a thing for managing tasks.",
        pipeline_run_id=run_id,
        pipeline_type=_PIPELINE_TYPE,
        user_id="capabilities-threading-user",
        od_context=None,
        gate_agent_ids=[],
    )

    try:
        async for _ev in engine.execute(**kwargs):
            pass
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile_for_run

    return captured["capabilities"]


@pytest.mark.asyncio
async def test_compiled_internet_capability_reaches_agent_context() -> None:
    """``capabilities: {internet: true}`` on the compiled workflow reaches
    ``AgentContext.capabilities`` for the step the engine runs (AC-16)."""
    captured = await _drive_and_capture_capabilities({"internet": True})
    assert captured == {"internet": True}


@pytest.mark.asyncio
async def test_no_compiled_capabilities_is_byte_identical_empty_dict() -> None:
    """A manifest declaring no ``capabilities`` (the R-16 baseline) still yields an
    empty dict — never ``None`` — so ``_resolve_runner_tools`` stays a no-op."""
    captured = await _drive_and_capture_capabilities({})
    assert captured == {}
