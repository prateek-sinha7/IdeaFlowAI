"""ISS-004 (19-03) fault-injection: the streamed ``agent_chunk`` sanitizer.

The engine yields each model ``chunk`` as an ``agent_chunk`` event BEFORE the
authoritative chunk-joined output is sanitized (``sanitize_output`` at the post-loop
locus). So fabricated tool-call XML (``<function_calls>`` / ``<invoke name="read_file">``)
a tool-less Haiku agent emits as PLAIN TEXT used to reach the live UI stream. 19-03 routes
each YIELDED chunk through the runner's existing ``_strip_fabricated_tool_xml`` (via the
duck-typed ``sanitize_output``) WITH a chunk-straddle buffer, so a ``<function_calls>…``
span SPLIT across two chunk deltas is still stripped before it is yielded.

These tests drive the engine's real ``_run_agent`` stream loop through ``execute()``
(single-agent pipeline) with a ``ScriptedFakeChatModel`` whose deltas split the tool-XML
across chunk boundaries, and assert:

  * tool-less agent, SPLIT span      → no ``<function_calls>``/``<invoke`` in the emitted
                                       ``agent_chunk`` stream (the span-straddle buffer works);
  * tool-using agent, identical span → emitted chunks byte-identical (untouched, gate False);
  * single-chunk span (tool-less)    → stripped (non-straddle path);
  * clean stream (tool-less)         → emitted chunks identical to input (no-op).

Fully OFFLINE/deterministic — scripted model, temp ``RUNS_ROOT``, no Bedrock. SC-001: the
sanitizer keys on the generic tool-less runner capability, never a workflow/agent name —
proven here by using a real tool-less (``domain-analyst``, tools:[]) vs tool-using
(``prototype-revision-agent``, tools:[workspace]) agent, NOT a named branch.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.agents._scripted_model import (
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _ScriptedTurn,
)


# A tool-less agent (tools:[] → exclude_builtin AND zero tools → sanitize active) and a
# tool-using agent (tools:[workspace] → sanitize is an identity no-op). Chosen as REAL
# specs off the registry so the gate is the runner capability, not an agent-name literal.
# Both have empty `consumes` so each drives as a satisfiable single-agent pipeline offline.
_TOOLLESS_AGENT = "domain-analyst"          # user_stories pipeline, tools:[]
_TOOLLESS_PIPELINE = "user_stories"
_TOOLUSING_AGENT = "prototype-revision-agent"  # prototype_revision pipeline, tools:[workspace]
_TOOLUSING_PIPELINE = "prototype_revision"


async def _drive_single_agent(
    agent_id: str,
    pipeline_type: str,
    chunk_texts: list[str],
) -> list[str]:
    """Run ONE agent through ``ExecutionEngine.execute()`` offline and return the
    ordered list of emitted ``agent_chunk.chunk`` strings.

    Mirrors ``tests/agents/_scripted_model._drive`` but (a) drives a single-agent
    pipeline and (b) injects a custom ``ScriptedFakeChatModel`` whose ``_stream``
    yields ``chunk_texts`` as separate deltas — letting a test split a
    ``<function_calls>`` span across two chunks. No network / no Bedrock.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents

    from app.core.config import settings as _settings
    _settings.RUNS_ROOT = _RUNS_ROOT

    specs = get_pipeline_agents(pipeline_type)
    spec = next(s for s in specs if s.id == agent_id)

    # Disable the auto-clarify override (no live WS round-trip offline).
    _orig_compile_for_run = engine_mod.compile_for_run

    def _patched_compile_for_run(ptype, _orig=_orig_compile_for_run):
        compiled = _orig(ptype)
        compiled.clarify.mode = "off"
        return compiled

    engine_mod.compile_for_run = _patched_compile_for_run

    # Inject our split-XML scripted model for THIS agent (one turn, usage so the
    # done/usage events fire as normal).
    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(aid, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(
            [_ScriptedTurn(texts=list(chunk_texts), usage=(10, 5))]
        )
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

    run_id = f"chunk-sanitizer-{agent_id}-{uuid.uuid4().hex[:8]}"
    # ISS-634: pass compiled_override with a single-step plan matching `spec` so
    # ADR-0008's _roster_is_partial fill-in doesn't expand agents=[spec] to the
    # full N-step plan. compile_for_run is @lru_cache'd; dataclasses.replace
    # makes a shallow copy so we never mutate the shared cached instance.
    import dataclasses
    from agents.execution_engine.engine import compile_for_run as _compile
    base_compiled = _compile(pipeline_type)
    single_step = next(
        (s for s in base_compiled.steps if s.agent_id == agent_id), None
    )
    if single_step is None:
        # Fallback: build a minimal step from the spec so the test still runs.
        single_step = base_compiled.steps[0]
    single_compiled = dataclasses.replace(
        base_compiled,
        steps=[single_step],
        planner="skip",
        clarify=dataclasses.replace(base_compiled.clarify, mode="off"),
    )
    kwargs: dict[str, Any] = dict(
        agents=[spec],
        user_message="Build me a thing for managing tasks.",
        pipeline_run_id=run_id,
        pipeline_type=pipeline_type,
        user_id="chunk-sanitizer-user",
        od_context=None,
        gate_agent_ids=[],
        compiled_override=single_compiled,
    )

    emitted: list[str] = []
    try:
        async for ev in engine.execute(**kwargs):
            if ev.get("type") == "agent_chunk":
                emitted.append(ev["data"]["chunk"])
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile_for_run
    return emitted


# Tool-XML span SPLIT across two chunk deltas: delta 1 ends with an UNTERMINATED
# `<function_calls><invoke name="read_` opener; delta 2 carries the close. A naive
# per-chunk regex would miss this — the span-straddle buffer is what catches it.
_SPLIT_DELTAS = [
    'Here is the result. <function_calls><invoke name="read_',
    'file"><parameter name="path">app.py</parameter></invoke></function_calls> Done analyzing.',
]


@pytest.mark.asyncio
async def test_split_tool_xml_stripped_for_toolless_agent() -> None:
    """SPLIT-across-deltas (tool-less): no fabricated tool-XML in the emitted stream."""
    emitted = await _drive_single_agent(_TOOLLESS_AGENT, _TOOLLESS_PIPELINE, _SPLIT_DELTAS)
    joined = "".join(emitted)

    assert "<function_calls>" not in joined, (
        f"fabricated <function_calls> leaked into the tool-less agent_chunk stream: {joined!r}"
    )
    assert "<invoke" not in joined, (
        f"fabricated <invoke leaked into the tool-less agent_chunk stream: {joined!r}"
    )
    # No single emitted chunk leaks a partial opener that is never closed.
    for chunk in emitted:
        assert "<function_calls>" not in chunk and "<invoke" not in chunk, (
            f"a single emitted chunk leaked a tool-XML opener: {chunk!r}"
        )
    # Legitimate content on BOTH sides of the split span survives (nothing swallowed).
    assert "Here is the result. " in joined, f"legit prefix dropped: {joined!r}"
    assert "Done analyzing." in joined, f"legit suffix dropped: {joined!r}"


@pytest.mark.asyncio
@pytest.mark.issue("ISS-634")
async def test_split_tool_xml_untouched_for_tooluse_agent() -> None:
    """Identical SPLIT stream for a tool-USING agent → emitted chunks byte-identical."""
    emitted = await _drive_single_agent(_TOOLUSING_AGENT, _TOOLUSING_PIPELINE, _SPLIT_DELTAS)

    # The tool-using runner's sanitize_output is an identity no-op (gate False), so the
    # buffer is inert and every delta passes through verbatim, in order.
    assert emitted == _SPLIT_DELTAS, (
        "tool-using agent stream was perturbed by the sanitizer (must be untouched): "
        f"emitted={emitted!r} expected={_SPLIT_DELTAS!r}"
    )


@pytest.mark.asyncio
async def test_single_chunk_tool_xml_stripped_for_toolless_agent() -> None:
    """Whole `<function_calls>…</function_calls>` in ONE delta (tool-less) → stripped."""
    deltas = [
        'Prefix text. '
        '<function_calls><invoke name="read_file">'
        '<parameter name="path">x</parameter></invoke></function_calls>'
        ' Suffix text.',
    ]
    emitted = await _drive_single_agent(_TOOLLESS_AGENT, _TOOLLESS_PIPELINE, deltas)
    joined = "".join(emitted)

    assert "<function_calls>" not in joined and "<invoke" not in joined, (
        f"single-chunk fabricated tool-XML not stripped: {joined!r}"
    )
    assert "Prefix text. " in joined and " Suffix text." in joined, (
        f"legit surrounding content dropped: {joined!r}"
    )


@pytest.mark.asyncio
@pytest.mark.issue("ISS-634")
async def test_clean_stream_passes_through_unchanged_for_toolless_agent() -> None:
    """Clean stream (no tool-XML) for a tool-less agent → emitted chunks == input."""
    deltas = ["Domain analysis: ", "the system manages tasks ", "for a single user."]
    emitted = await _drive_single_agent(_TOOLLESS_AGENT, _TOOLLESS_PIPELINE, deltas)

    # No opener anywhere → the buffer fast-path passes each chunk through verbatim,
    # preserving per-chunk granularity (no coalescing, no perturbation).
    assert emitted == deltas, (
        "clean tool-less stream was perturbed (must be byte-identical, per-chunk): "
        f"emitted={emitted!r} expected={deltas!r}"
    )


@pytest.mark.asyncio
@pytest.mark.issue("ISS-634")
async def test_lone_lt_and_html_at_boundaries_chunk_identical_for_toolless_agent() -> None:
    """WR-01: tool-less prose with ``<`` / ``<div>`` / ``a < b`` at chunk boundaries.

    A tool-less agent streaming HTML/JSX/markdown/inequalities legitimately ends
    deltas on a bare ``<`` (or a ``<d`` that is NOT a tool-XML opener). Pre-fix the
    partial-opener guard held ANY proper prefix of an opener — including a lone ``<`` —
    coalescing/suppressing those deltas. Post-fix the hold fires only on a >= 2-char
    prefix of a REAL opener (``<f``/``<i``+), so these deltas pass through
    chunk-boundary-IDENTICAL (not merely join-identical).
    """
    deltas = [
        "Use the ",
        "<",
        "div> wrapper and the ",
        "<",
        "Input> field. Note a ",
        "a < b",
        " comparison.",
    ]
    emitted = await _drive_single_agent(_TOOLLESS_AGENT, _TOOLLESS_PIPELINE, deltas)

    assert emitted == deltas, (
        "tool-less prose with a lone `<` / `<div>` / `a < b` at chunk boundaries was "
        "perturbed (WR-01: must be per-chunk byte-identical, no coalescing): "
        f"emitted={emitted!r} expected={deltas!r}"
    )


@pytest.mark.asyncio
async def test_never_closed_opener_flushed_and_stripped_at_stream_end() -> None:
    """WR-04: a ``<function_calls>`` opener that NEVER closes is flushed + stripped at EOF.

    The held buffer holds the tail from an unterminated opener; if the stream ends
    before the close arrives, ``flush()`` sanitizes + emits that tail (an unterminated
    opener at EOF is stripped, mirroring the runner's ``_UNTERMINATED_TOOL_XML_RE``).
    The legit content BEFORE the opener must survive; the fabricated opener must NOT
    leak. This pins the data-loss safety contract for the never-closed-opener case.
    """
    deltas = [
        "Real answer text. ",
        '<function_calls><invoke name="read_file"><parameter name="path">app.py',
        # stream ENDS here — the close </function_calls> NEVER arrives.
    ]
    emitted = await _drive_single_agent(_TOOLLESS_AGENT, _TOOLLESS_PIPELINE, deltas)
    joined = "".join(emitted)

    # The legit prefix is never swallowed by the held buffer / flush.
    assert "Real answer text. " in joined, f"legit prefix lost at flush: {joined!r}"
    # The never-closed fabricated opener is stripped (not leaked) at the flush.
    assert "<function_calls>" not in joined and "<invoke" not in joined, (
        f"never-closed opener leaked through the flush: {joined!r}"
    )


@pytest.mark.asyncio
@pytest.mark.issue("ISS-634")
async def test_benign_held_tail_survives_flush_no_content_loss() -> None:
    """WR-04: a benign trailing tail held at EOF is flushed VERBATIM (no content loss).

    When the final delta leaves a benign partial-opener tail held (``<f`` — a >=2-char
    prefix of ``<function_calls>`` that never completes), ``flush()`` must return it
    unchanged (``_strip_fabricated_tool_xml`` no-ops a benign partial). The joined
    emitted output therefore equals the joined input — the tail survives. This pins
    the OTHER direction of the flush contract: a held benign tail is NOT swallowed.
    """
    deltas = ["Result is ", "x <f"]  # final "<f" is held (>=2-char partial), never completed
    emitted = await _drive_single_agent(_TOOLLESS_AGENT, _TOOLLESS_PIPELINE, deltas)

    assert "".join(emitted) == "".join(deltas), (
        "a benign held tail was not flushed verbatim at stream end (content lost): "
        f"emitted={emitted!r} input={deltas!r}"
    )
