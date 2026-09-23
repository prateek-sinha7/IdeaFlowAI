"""WR-01 / ISS-004 engine-path chunk sanitation — the engine-driving (DB-touching) half.

Split out of ``tests/unit/agents/test_text_only_prompt_hygiene.py``. Sections 1-3 of that
module (the no-tools preamble presence/absence checks and the
``_strip_fabricated_tool_xml`` unit coverage) are zero-I/O and STAY in the unit suite.
Section 4 below drives the PUBLIC ``ExecutionEngine.execute()``, which opens a
``SessionLocal()`` to persist run events — the unit-isolation guard in
``tests/unit/conftest.py`` rejects that by design.

Offline (scripted model, no Bedrock) — but NOT zero-I/O.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

_POLLUTED_CHUNKS = [
    "## Epics\nProse kept.\n",
    '<function_calls>\n<invoke name="write_file">\n'
    '<parameter name="path">epics.md</parameter>\n</invoke>\n</function_calls>\n',
    "Tail kept.\n",
]
_EXPECTED_SANITIZED = "## Epics\nProse kept.\n\nTail kept.\n"


@pytest.mark.asyncio
@pytest.mark.issue("ISS-638")
async def test_engine_pipeline_path_strips_fabricated_xml_from_authoritative_output(
    tmp_path, monkeypatch
):
    """WR-01 regression + ISS-004 (19-03) chunk-straddle sanitizer: ``_run_agent``
    builds output from ``chunk`` events — the persisted/forwarded authoritative
    output must be SANITIZED on that path. The chunk-straddle sanitizer (19-03,
    ``_ChunkStreamSanitizer`` in engine.py) ALSO strips the fabricated span from
    the streamed ``agent_chunk`` events themselves for tool-less agents (buffering
    across a chunk boundary so a split span is still caught) — so both the UI
    chunk stream and the authoritative output must come out clean.

    Drives the PUBLIC ``engine.execute()`` over two real tool-less user_stories
    agents with a scripted model whose raw chunk texts carry a fabricated XML
    span. The ``agent_complete.output_length`` and the run's ``final_output``
    must reflect the sanitized output, and no ``agent_chunk`` event may leak the
    fabricated span either.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings
    from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn

    monkeypatch.setattr(_settings, "RUNS_ROOT", str(tmp_path), raising=False)

    # Planner + clarify off (offline — no model call, no WS round-trip).
    _orig_compile = engine_mod.compile_for_run

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        # COPY, never mutate. ``compile_for_run`` is @lru_cache'd, so ``_orig(...)``
        # hands back the SHARED CompiledWorkflow instance — the very object every
        # other test and the engine itself reads. Setting ``.planner`` / ``.clarify``
        # on it leaked process-wide: monkeypatch restores this FUNCTION on teardown,
        # but nothing undoes a mutation to the cached object, so ``user_stories``
        # stayed ``planner="skip"`` / ``clarify.mode="off"`` for the rest of the run.
        # That silently failed five tests in other files
        # (test_id_alias_resolver[user_stories], test_live_contract,
        # test_live_harness, test_iss033 ×2) — but only when this file ran first,
        # which is why they passed in isolation and moved around between runs.
        compiled = _orig(pipeline_type)
        return dataclasses.replace(
            compiled,
            planner="skip",
            clarify=dataclasses.replace(compiled.clarify, mode="off"),
        )

    monkeypatch.setattr(engine_mod, "compile_for_run", _patched_compile)

    # ISS-638 (row 3): drive the FULL user_stories roster (6 agents) so ADR-0008's
    # _roster_is_partial fill-in doesn't expand a [:2] slice to all 6 and break
    # the polluted_agent_id pinning. All 6 are tool-less (user_stories has no
    # filesystem-write agents), so the precondition below still holds.
    specs = get_pipeline_agents("user_stories")
    assert all(s.tools == [] for s in specs), "precondition: tool-less agents"
    # ADR-0008: passing agents=[] lets the engine build from compiled manifest steps.
    # The last agent in the full pipeline becomes final_output, so pollute that one.
    polluted_agent_id = specs[-1].id  # last agent → its output IS final_output

    _orig_create_runner = factory_mod.create_runner

    def _patched_create_runner(agent_id, ctx, **kw):
        texts = (
            list(_POLLUTED_CHUNKS)
            if agent_id == polluted_agent_id
            else [f"{agent_id} clean output."]
        )
        ctx.model = ScriptedFakeChatModel([_ScriptedTurn(texts=texts, usage=(12, 7))])
        return _orig_create_runner(agent_id, ctx, **kw)

    monkeypatch.setattr(factory_mod, "create_runner", _patched_create_runner)
    monkeypatch.setattr(engine_mod, "create_runner", _patched_create_runner)

    engine = ExecutionEngine()

    async def _noop_store(*a, **k):
        return "artifact-id"

    monkeypatch.setattr(engine._store, "store", _noop_store, raising=False)

    events: list[dict] = []
    async for ev in engine.execute(
        agents=[],
        user_message="Build a backlog.",
        pipeline_run_id=f"wr01-{uuid.uuid4().hex[:8]}",
        pipeline_type="user_stories",
        gate_agent_ids=[],
    ):
        events.append(ev)

    # precondition: the scripted fixture's RAW chunk texts actually carry the
    # fabricated span (else this test would prove nothing about stripping).
    assert any(
        "<function_calls>" in t for t in _POLLUTED_CHUNKS
    ), "precondition: the scripted fixture must carry the fabricated span"

    # The UI chunk stream is ALSO sanitized (ISS-004 / 19-03 chunk-straddle
    # sanitizer, engine.py ``_ChunkStreamSanitizer``) — no agent_chunk event
    # for the tool-less polluted agent leaks the fabricated span.
    polluted_chunks = [
        e
        for e in events
        if e.get("type") == "agent_chunk" and e["data"]["agent_id"] == polluted_agent_id
    ]
    assert polluted_chunks, "precondition: chunks were streamed for the polluted agent"
    assert not any("<function_calls>" in e["data"]["chunk"] for e in polluted_chunks), (
        "agent_chunk stream must not leak the fabricated XML span "
        "(chunk-straddle sanitizer)"
    )
    assert not any("<invoke" in e["data"]["chunk"] for e in polluted_chunks)

    # The AUTHORITATIVE output (agent_complete.output_length) is sanitized.
    complete = next(
        e
        for e in events
        if e.get("type") == "agent_complete"
        and e["data"]["agent_id"] == polluted_agent_id
    )
    assert complete["data"]["output_length"] == len(_EXPECTED_SANITIZED), (
        "agent_complete.output_length must reflect the SANITIZED chunk-joined "
        f"output ({len(_EXPECTED_SANITIZED)}), got {complete['data']['output_length']}"
    )

    # The run deliverable carries no fabricated XML; the prose survived.
    final = next(e for e in events if e.get("type") == "pipeline_complete")
    final_output = final["data"]["final_output"]
    assert "<function_calls>" not in final_output
    assert "<invoke" not in final_output
    assert "Prose kept." in final_output and "Tail kept." in final_output
