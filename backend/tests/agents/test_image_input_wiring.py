"""Image-input Wave-1 engine wiring tests (260707-edw T1.6/T1.7).

Covers behavior set (b/c/d) from the plan:

  (b) BLOCKER — the two-agent isolation regression that PINS plan-check F1: the
      per-agent-local gate in ``_compose_input_blocks`` ignores the stale
      ``ectx.current_spec_injects`` field, so an agent with NO image inject running
      AFTER an opted-in one gets ``[]`` (no cross-agent image leak).
  (c) the ``_dispatch_payload`` split-transport wrap contract.
  (d) the ``DeepAgentRunner`` ``str | list`` widening — list content flows through
      ``HumanMessage(content=...)`` into the model dispatch without raising.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.capabilities import registry as registry_mod
from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.engine import ExecutionEngine, _dispatch_payload


# ---------------------------------------------------------------------------
# (b) BLOCKER — two-agent isolation (F1 leak pin)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compose_input_blocks_two_agent_isolation_ignores_stale_field() -> None:
    registry_mod.discover()  # bind the run_images input_provider impl

    ectx = ExecutionContext(run_id="r-edw", owner_id="o-edw")
    # Dynamic per-run threads (same mechanism as ectx.compiled_context_providers).
    ectx.run_images = [{"mime_type": "image/png", "data": "AA"}]
    ectx.compiled_input_providers = ["run_images"]

    engine = ExecutionEngine()

    # ── Agent A: declares injects=["images"] → blocks flow. ──────────────────
    spec_a = SimpleNamespace(id="agent-a", injects=["images"], tools=[])
    ectx.current_step = SimpleNamespace(injects=[])
    blocks_a = await engine._compose_input_blocks(spec_a, ectx)
    assert blocks_a == [
        {
            "type": "image",
            "source_type": "base64",
            "mime_type": "image/png",
            "data": "AA",
        }
    ]

    # ── Simulate the STALE leak: set ectx.current_spec_injects = {"images"}
    #    (what _compose_context_message writes for an opted-in agent and NEVER
    #    resets). Agent B, with NO image inject, must STILL get []. ────────────
    ectx.current_spec_injects = {"images"}
    spec_b = SimpleNamespace(id="agent-b", injects=[], tools=[])
    ectx.current_step = SimpleNamespace(injects=[])
    blocks_b = await engine._compose_input_blocks(spec_b, ectx)
    assert blocks_b == []


@pytest.mark.asyncio
async def test_compose_input_blocks_gates_on_step_injects_union() -> None:
    # The gate is spec.injects ∪ step.injects: an agent whose AGENT.md omits
    # "images" but whose compiled Step declares it still gets blocks.
    registry_mod.discover()
    ectx = ExecutionContext(run_id="r-edw2", owner_id="o-edw2")
    ectx.run_images = [{"mime_type": "image/jpeg", "data": "BB"}]
    ectx.compiled_input_providers = ["run_images"]
    ectx.current_step = SimpleNamespace(injects=["images"])
    engine = ExecutionEngine()
    spec = SimpleNamespace(id="agent-c", injects=[], tools=[])
    blocks = await engine._compose_input_blocks(spec, ectx)
    assert [b["data"] for b in blocks] == ["BB"]


@pytest.mark.asyncio
async def test_compose_input_blocks_empty_when_no_providers_declared() -> None:
    # Dormant default: an opted-in agent with NO compiled_input_providers → [].
    registry_mod.discover()
    ectx = ExecutionContext(run_id="r-edw3", owner_id="o-edw3")
    ectx.run_images = [{"mime_type": "image/png", "data": "AA"}]
    ectx.compiled_input_providers = []
    ectx.current_step = SimpleNamespace(injects=[])
    engine = ExecutionEngine()
    spec = SimpleNamespace(id="agent-d", injects=["images"], tools=[])
    assert await engine._compose_input_blocks(spec, ectx) == []


# ---------------------------------------------------------------------------
# (c) dispatch wrap
# ---------------------------------------------------------------------------


def test_dispatch_payload_bare_str_when_empty() -> None:
    assert _dispatch_payload("cm", []) == "cm"
    assert _dispatch_payload("cm", None) == "cm"


def test_dispatch_payload_text_first_list_when_blocks() -> None:
    block = {"type": "image", "source_type": "base64", "mime_type": "image/png", "data": "AA"}
    out = _dispatch_payload("cm", [block])
    assert isinstance(out, list)
    assert out[0] == {"type": "text", "text": "cm"}
    assert out[1] == block


# ---------------------------------------------------------------------------
# (d) runner str | list widening
# ---------------------------------------------------------------------------


async def _collect(runner, message) -> list[dict]:
    return [event async for event in runner.astream_events(message)]


def _chunk_text(events: list[dict]) -> str:
    return "".join(e.get("chunk", "") for e in events if e["type"] == "chunk")


@pytest.mark.asyncio
async def test_runner_streams_list_content_without_raising(tmp_path, monkeypatch) -> None:
    from agents.factory import AgentContext, create_runner
    from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn

    monkeypatch.setattr("app.core.config.settings.RUNS_ROOT", str(tmp_path))

    # LIST content (text-first + an image block) flows through
    # HumanMessage(content=<list>) into the deepagents dispatch without raising.
    fake = ScriptedFakeChatModel([_ScriptedTurn(texts=["hello ", "world."], usage=(5, 3))])
    ctx = AgentContext(
        user_request="x", model=fake, user_id="u-img", run_id="run-img-list"
    )
    runner = create_runner("domain-analyst", ctx)
    events = await _collect(
        runner,
        [
            {"type": "text", "text": "hi"},
            {"type": "image", "source_type": "base64", "mime_type": "image/png", "data": "AA"},
        ],
    )
    assert _chunk_text(events) == "hello world."
    assert _types_last_done(events)


@pytest.mark.asyncio
async def test_runner_streams_str_content_identically(tmp_path, monkeypatch) -> None:
    from agents.factory import AgentContext, create_runner
    from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn

    monkeypatch.setattr("app.core.config.settings.RUNS_ROOT", str(tmp_path))

    fake = ScriptedFakeChatModel([_ScriptedTurn(texts=["hello ", "world."], usage=(5, 3))])
    ctx = AgentContext(
        user_request="x", model=fake, user_id="u-img", run_id="run-img-str"
    )
    runner = create_runner("domain-analyst", ctx)
    events = await _collect(runner, "hi")
    assert _chunk_text(events) == "hello world."
    assert _types_last_done(events)


def _types_last_done(events: list[dict]) -> bool:
    types = [e["type"] for e in events]
    return "done" in types


def test_human_message_carries_str_and_list_verbatim() -> None:
    # The runner does NO string ops on user_message — HumanMessage(content=...)
    # accepts both shapes and carries content verbatim (langchain_core).
    from langchain_core.messages import HumanMessage

    assert HumanMessage(content="hi").content == "hi"
    lst = [{"type": "text", "text": "hi"}, {"type": "image", "data": "AA"}]
    assert HumanMessage(content=lst).content == lst
