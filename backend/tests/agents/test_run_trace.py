"""tests/agents/test_run_trace.py — the on-disk run trace (Requirement 24).

`.logs/{run_id}.jsonl` carries step boundaries, errors, tool calls, model output,
and reasoning.  Diagnosing a run used to mean reading the server console or the
database — the file could not answer the one question that matters when a pipeline
produces nothing: "did the agent call write_file, and with what?".

`RunTrace` is driven from the engine's own event stream at the single point
`execute()` stamps every event, so what these cases really pin is that the trace
is complete BY CONSTRUCTION:

  * every event type reaches the file, including one this class has never seen
  * a tool call names its file and says whether it worked — WITHOUT quoting a
    payload that would drown every other line
  * the model's own output and reasoning, which ARE the trace, are kept whole
  * reasoning is combined across a step and written once, when the step ends
  * ordering matches the real event order

Requirement 24 AC 1: ``RunTrace`` (and the underlying ``RunLog``) now accept the
full log file ``Path`` rather than the sandbox root, so callers must supply the
per-run path (``RunSandbox.run_log_path``) directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.execution_engine.run_log import RunTrace

# Canonical per-run log filename the engine uses via RunSandbox.run_log_path.
_LOG_NAME = "abc-run-id.jsonl"


def _make_log_path(root: Path) -> Path:
    """Mirrors RunSandbox.run_log_path: <root>/.logs/{run_id}.jsonl."""
    return root / ".logs" / _LOG_NAME


def _lines(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(ln) for ln in log_path.read_text().splitlines() if ln.strip()]


def test_every_event_type_reaches_the_file_including_unknown_ones(tmp_path):
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({"type": "agent_start", "data": {"agent_id": "a1", "name": "One"}})
    trace.observe({"type": "tool_call", "data": {"agent_id": "a1", "tool": "ls"}})
    trace.observe({"type": "tool_result", "data": {"agent_id": "a1", "result": "[]"}})
    trace.observe({"type": "review_gate_open", "data": {"agent_id": "a1"}})
    # A type nothing here knows about: the point of tracing at the boundary is
    # that it still lands, without this file or the engine being edited.
    trace.observe({"type": "some_future_event", "data": {"agent_id": "a1", "x": 1}})
    trace.flush()

    assert [e["event"] for e in _lines(log_path)] == [
        "agent_start",
        "tool_call",
        "tool_result",
        "review_gate_open",
        "some_future_event",
    ]


def test_a_tool_call_names_the_file_without_quoting_it(tmp_path):
    """WHICH file and whether it worked is the fact worth having. Inlining the
    file itself buries every other line in the run — a 10 MB read would drown the
    trace it belongs to."""
    deck = "<!DOCTYPE html>" + ("<section>slide</section>" * 2000)
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({
        "type": "tool_call",
        "data": {"agent_id": "composer", "tool": "write_file",
                 "args": {"file_path": "presentation.html", "content": deck}},
    })
    trace.flush()

    (line,) = _lines(log_path)
    assert line["tool"] == "write_file"
    # The identifying detail survives verbatim...
    assert line["args"]["file_path"] == "presentation.html"
    # ...the payload is described, and its size is stated so nothing is silently
    # missing.
    assert line["args"]["content"] != deck
    assert f"<{len(deck)} chars, elided>" in line["args"]["content"]


def test_a_short_tool_payload_is_kept_verbatim(tmp_path):
    """An error message IS the diagnosis and is short — eliding it would throw
    away the only line that explains the failure."""
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({
        "type": "tool_result",
        "data": {"agent_id": "qa", "tool": "read_file",
                 "result": "Error: File '/presentation.html' not found"},
    })
    trace.flush()

    (line,) = _lines(log_path)
    assert line["result"] == "Error: File '/presentation.html' not found"


def test_an_elided_payload_keeps_its_head_so_a_failure_still_reads(tmp_path):
    """A long result that STARTS with the error still says so."""
    body = "Error: permission denied\n" + ("stack frame\n" * 5000)
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({
        "type": "tool_result",
        "data": {"agent_id": "a1", "tool": "read_file", "result": body},
    })
    trace.flush()

    (line,) = _lines(log_path)
    assert line["result"].startswith("Error: permission denied")
    assert "elided>" in line["result"]


def test_streaming_deltas_are_coalesced_into_one_line(tmp_path):
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    for piece in ["Hello", " ", "world"]:
        trace.observe({"type": "agent_chunk", "data": {"agent_id": "a1", "chunk": piece}})
    trace.flush()

    (line,) = _lines(log_path)
    assert line["event"] == "agent_output"
    assert line["text"] == "Hello world"
    assert line["chars"] == 11


def test_thinking_is_combined_across_the_whole_step_and_written_once(tmp_path):
    """Reasoning split into fragments around each tool call is harder to follow
    than the same reasoning read straight through, so it accumulates for the whole
    step and lands as ONE line when the agent finishes."""
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({"type": "agent_thinking", "data": {"agent_id": "a1", "thinking": "First, "}})
    trace.observe({"type": "tool_call", "data": {"agent_id": "a1", "tool": "ls"}})
    trace.observe({"type": "agent_thinking", "data": {"agent_id": "a1", "thinking": "then this."}})
    trace.observe({"type": "tool_call", "data": {"agent_id": "a1", "tool": "read_file"}})
    trace.observe({"type": "agent_complete", "data": {"agent_id": "a1"}})

    events = _lines(log_path)
    assert [e["event"] for e in events] == [
        "tool_call", "tool_call", "agent_thinking", "agent_complete",
    ]
    thinking = events[2]
    assert thinking["thinking"] == "First, then this."
    assert thinking["chars"] == 17


def test_thinking_lands_before_the_line_that_ends_the_step(tmp_path):
    """It belongs WITH its step, so it precedes agent_complete rather than
    trailing after it."""
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({"type": "agent_thinking", "data": {"agent_id": "a1", "thinking": "why"}})
    trace.observe({"type": "agent_complete", "data": {"agent_id": "a1"}})

    assert [e["event"] for e in _lines(log_path)] == ["agent_thinking", "agent_complete"]


def test_a_failed_step_still_leaves_its_reasoning(tmp_path):
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({"type": "agent_thinking", "data": {"agent_id": "a1", "thinking": "stuck"}})
    trace.observe({"type": "agent_error", "data": {"agent_id": "a1", "error": "boom"}})

    events = _lines(log_path)
    assert [e["event"] for e in events] == ["agent_thinking", "agent_error"]
    assert events[0]["thinking"] == "stuck"


def test_thinking_of_two_agents_never_merges(tmp_path):
    """Two agents can be mid-step at once (a fan-out); each keeps its own."""
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({"type": "agent_thinking", "data": {"agent_id": "a1", "thinking": "one"}})
    trace.observe({"type": "agent_thinking", "data": {"agent_id": "a2", "thinking": "two"}})
    trace.observe({"type": "agent_complete", "data": {"agent_id": "a2"}})
    trace.observe({"type": "agent_complete", "data": {"agent_id": "a1"}})

    thinking = [(e["agent_id"], e["thinking"]) for e in _lines(log_path)
                if e["event"] == "agent_thinking"]
    assert thinking == [("a2", "two"), ("a1", "one")]


def test_reasoning_survives_a_run_that_never_finished_its_step(tmp_path):
    """A cancelled run's last step never emits agent_complete; the final flush is
    what stops its reasoning being lost."""
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({"type": "agent_thinking", "data": {"agent_id": "a1", "thinking": "half"}})
    trace.flush()

    (line,) = _lines(log_path)
    assert line["event"] == "agent_thinking"
    assert line["thinking"] == "half"


def test_deltas_from_different_agents_do_not_merge(tmp_path):
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({"type": "agent_chunk", "data": {"agent_id": "a1", "chunk": "one"}})
    trace.observe({"type": "agent_chunk", "data": {"agent_id": "a2", "chunk": "two"}})
    trace.flush()

    events = _lines(log_path)
    assert [(e["agent_id"], e["text"]) for e in events] == [("a1", "one"), ("a2", "two")]


def test_a_tool_call_mid_stream_lands_after_the_text_before_it(tmp_path):
    """Ordering is the whole value of a trace: a tool call that appears before the
    text that preceded it would misrepresent what the agent did."""
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({"type": "agent_chunk", "data": {"agent_id": "a1", "chunk": "before"}})
    trace.observe({"type": "tool_call", "data": {"agent_id": "a1", "tool": "read_file"}})
    trace.observe({"type": "agent_chunk", "data": {"agent_id": "a1", "chunk": "after"}})
    trace.flush()

    assert [e["event"] for e in _lines(log_path)] == [
        "agent_output", "tool_call", "agent_output",
    ]


def test_the_models_own_output_is_kept_whole(tmp_path):
    """The two policies are not the same policy. A tool payload is described; what
    the model actually WROTE is the trace, and is kept."""
    deck = "<!DOCTYPE html>" + ("<section>slide</section>" * 2000)
    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({"type": "agent_chunk", "data": {"agent_id": "a1", "chunk": deck}})
    trace.flush()

    (line,) = _lines(log_path)
    assert line["text"] == deck


def test_a_pathological_output_is_still_bounded_and_says_so(tmp_path):
    """Kept whole is not kept unbounded — one runaway value must not produce an
    unreadable line."""
    from agents.execution_engine.run_log import _MAX_FIELD_CHARS

    log_path = _make_log_path(tmp_path)
    trace = RunTrace(log_path)
    trace.observe({
        "type": "agent_chunk",
        "data": {"agent_id": "a1", "chunk": "x" * (_MAX_FIELD_CHARS + 50)},
    })
    trace.flush()

    (line,) = _lines(log_path)
    assert "[truncated," in line["text"]


def test_tracing_never_breaks_a_run(tmp_path):
    """A malformed event, or an unwritable path, must not raise into the stream."""
    log_path = _make_log_path(tmp_path)
    RunTrace(log_path).observe({"type": "x", "data": "not-a-dict"})
    RunTrace(None).observe({"type": "x", "data": {"a": 1}})   # no sandbox at all
    assert [e["event"] for e in _lines(log_path)] == ["x"]


def test_a_run_driven_by_the_resume_driver_is_traced_too(tmp_path, monkeypatch):
    """"By construction" has to hold on BOTH drivers, not only ``execute()``.

    REGRESSION THIS PINS (live, L6 run ``3da5d506-…``): ``_drive_resumed_stream``
    is a twin of ``execute()``'s stamping loop and built no ``RunTrace``. Any run
    that finished on it — a restart re-entry, a review-gate re-entry, or (the
    common case) a clarify round answered after the live stream dropped — left
    ``.logs/{run_id}.jsonl`` holding only the engine's own direct
    ``step_start``/``step_end`` lines: no ``agent_input``, ``agent_output``,
    ``agent_thinking``, ``tool_call``. The finalizer then copied that truncated
    file into ``.chain/logs.jsonl``, so the TAGGED, chainable payload — and a
    chained child's ``.context/logs.jsonl`` — shipped a log with the whole
    pipeline missing.
    """
    import asyncio

    from app.agents import sandbox as _sandbox_mod
    from agents.execution_engine.engine import ExecutionEngine

    # RunSandbox reads settings.RUNS_ROOT at __init__ — land the log under tmp.
    monkeypatch.setattr(_sandbox_mod.settings, "RUNS_ROOT", str(tmp_path))

    run_id = "resumed-run-id"
    seen: dict = {}

    async def _fake_execute_impl(**kwargs):
        seen.update(kwargs)
        yield {"type": "agent_input", "data": {"agent_id": "w", "system_prompt": "SYS"}}
        yield {"type": "tool_call", "data": {"agent_id": "w", "tool": "write_file"}}
        yield {"type": "agent_chunk", "data": {"agent_id": "w", "chunk": "done"}}

    engine = ExecutionEngine()
    monkeypatch.setattr(engine, "_execute_impl", _fake_execute_impl)

    asyncio.run(
        engine._drive_resumed_stream(
            run_id,
            agents=[],
            user_message="hi",
            pipeline_type="hello_html",
            user_id="u1",
            session_id="s1",
            parent_run_id=None,
            selections=None,
            start_seq=1,
            live_queue=None,
            _is_resume=True,
        )
    )

    log_path = _sandbox_mod.RunSandbox(
        "u1", run_id, current_run_id=run_id
    ).run_log_path
    written = _lines(log_path)
    # agent_chunk is coalesced and flushed as agent_output by the driver's finally.
    assert [e["event"] for e in written] == ["agent_input", "tool_call", "agent_output"]
    assert written[0]["system_prompt"] == "SYS"
    assert written[2]["text"] == "done"
    # ...and the same trace reaches _execute_impl, so the finalizer's step-3
    # flush_terminal (via ectx.run_trace) completes the file before step 4 copies
    # it into .chain/logs.jsonl.
    assert seen["_run_trace"] is not None
