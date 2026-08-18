"""The per-run gate selection must survive a restart-resume (migration 0031).

REGRESSION THIS PINS: ``gate_agent_ids`` is a launch-time parameter that lived
only on the in-memory ``ExecutionContext``. ``resume_run`` rebuilds that context
from the ``workflow_runs`` row, so after a backend restart the selection was gone:
``_should_gate`` fell back to the static ``gate: Human_Gate`` set, an agent that
was gated ONLY by the override was no longer gated, the gate-reentry sentinel
reconstructed its stale output without re-opening the gate, and a pending ``redo``
carrying the user's revision text was discarded with no error and no event. The
run completed with the pre-revision content.

Observed live on ``hello_html`` with ``gate_agent_ids: ["writer"]``: after an
incidental uvicorn ``--reload`` restart, ``writer`` never re-ran (byte-identical
``event_id``/``seq`` to the original), and "make it about volcanoes" was dropped.

These tests are structural on purpose — they assert the value reaches
``_execute_impl``, which is the link that was missing. Whether ``_should_gate``
then honours it is already covered by the gate suites.
"""
import pytest

from agents.execution_engine.engine import ExecutionEngine


def test_model_has_the_column():
    """A JSON column, so NULL ("use static gates") and [] ("no gates") differ."""
    from app.models.workflow import WorkflowRun

    col = WorkflowRun.__table__.columns["gate_agent_ids_json"]
    assert col.nullable is True


def test_drive_resumed_stream_accepts_and_forwards_gate_agent_ids(monkeypatch):
    """The kwarg reaches ``_execute_impl`` — the link that did not exist."""
    seen = {}

    async def _fake_execute_impl(**kwargs):
        seen.update(kwargs)
        return
        yield  # pragma: no cover — makes this an async generator

    engine = ExecutionEngine()
    monkeypatch.setattr(engine, "_execute_impl", _fake_execute_impl)

    import asyncio

    asyncio.run(
        engine._drive_resumed_stream(
            "run-1",
            agents=[],
            user_message="hi",
            pipeline_type="hello_html",
            user_id="u1",
            session_id="s1",
            parent_run_id=None,
            selections=None,
            gate_agent_ids=["writer"],
            start_seq=1,
            live_queue=None,
            _resume_from=0,
            _is_resume=True,
        )
    )

    assert seen["gate_agent_ids"] == ["writer"]


@pytest.mark.parametrize("value", [None, [], ["writer"]])
def test_all_three_states_are_forwarded_verbatim(monkeypatch, value):
    """NULL / [] / [ids] mean three different things and must not be conflated.

    ``None`` = use the static AGENT.md gates; ``[]`` = no gates this run (a real
    user choice); a list = gate exactly these. Coercing ``[]`` to ``None`` would
    silently re-enable the static gates on every resume of a gate-free run.
    """
    seen = {}

    async def _fake_execute_impl(**kwargs):
        seen.update(kwargs)
        return
        yield  # pragma: no cover

    engine = ExecutionEngine()
    monkeypatch.setattr(engine, "_execute_impl", _fake_execute_impl)

    import asyncio

    asyncio.run(
        engine._drive_resumed_stream(
            "run-1",
            agents=[],
            user_message="hi",
            pipeline_type="hello_html",
            user_id="u1",
            session_id="s1",
            parent_run_id=None,
            selections=None,
            gate_agent_ids=value,
            start_seq=1,
            live_queue=None,
            _resume_from=0,
            _is_resume=True,
        )
    )

    assert seen["gate_agent_ids"] == value


def test_default_is_none_so_untouched_callers_keep_the_old_behavior(monkeypatch):
    """Omitting the kwarg must stay byte-identical to the pre-fix drive (INV-3)."""
    seen = {}

    async def _fake_execute_impl(**kwargs):
        seen.update(kwargs)
        return
        yield  # pragma: no cover

    engine = ExecutionEngine()
    monkeypatch.setattr(engine, "_execute_impl", _fake_execute_impl)

    import asyncio

    asyncio.run(
        engine._drive_resumed_stream(
            "run-1",
            agents=[],
            user_message="hi",
            pipeline_type="hello_html",
            user_id="u1",
            session_id="s1",
            parent_run_id=None,
            selections=None,
            start_seq=1,
            live_queue=None,
        )
    )

    assert seen["gate_agent_ids"] is None
