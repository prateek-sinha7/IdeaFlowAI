"""L1 — API entry seam (R-07 / design.md D-06).

The revision launch path (REST/SSE driver ``_drive_launch_to_queue`` in
``app/api/run_commands.py`` — the sanctioned twin of the WS closure) must
hand ``ExecutionEngine.execute()``:

  * ``user_message`` — the frontend-framed revision request, UNCHANGED
    (``=== REVISION REQUEST ===`` + ``=== EXISTING PROTOTYPE HTML ===``
    blocks intact — the ``previous_run`` provider downstream parses these
    exact markers, so any mutation here silently severs the instruction);
  * ``parent_run_id`` — threaded through verbatim;
  * ``pipeline_type`` — ``prototype_revision``.

Offline: the engine is replaced by a kwargs-recorder; ``workflow_run_id=None``
skips the driver's DB tail entirely (no DB, no network, 0 tokens).
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.eval


FRAMED_MESSAGE = (
    "=== REVISION REQUEST ===\n"
    "Make the Save button on Settings actually save\n"
    "=== END REQUEST ===\n\n"
    "=== EXISTING PROTOTYPE HTML ===\n"
    "<!doctype html><html><body>stub</body></html>\n"
    "=== END EXISTING HTML ==="
)


class _RecorderEngine:
    """Stands in for ExecutionEngine: records execute() kwargs, ends cleanly."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)

        async def _gen():
            yield {"type": "pipeline_complete", "data": {"status": "completed"}}

        return _gen()


class _StubUser:
    id = "eval-user"
    preferred_model = None


@pytest.fixture
def recorder(monkeypatch) -> _RecorderEngine:
    import agents.execution_engine.engine as engine_mod

    rec = _RecorderEngine()
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: rec)
    return rec


def _drive(recorder: _RecorderEngine, **overrides) -> dict:
    """Run the real driver against the recorder; return the recorded kwargs."""
    from app.api.run_commands import _drive_launch_to_queue

    queue: asyncio.Queue = asyncio.Queue()
    kwargs = dict(
        workflow_run_id=None,  # skips the DB terminal-column tail
        pipeline_run_id="eval-run-l1",
        agents=[],
        content=FRAMED_MESSAGE,
        pipeline_type="prototype_revision",
        cancel_event=asyncio.Event(),
        user=_StubUser(),
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=None,
        parent_run_id="parent-run-123",
        model_overrides={},
        selections=None,
        event_queue=queue,
    )
    kwargs.update(overrides)
    asyncio.run(_drive_launch_to_queue(**kwargs))
    assert len(recorder.calls) == 1, "engine.execute() must be called exactly once"
    return recorder.calls[0]


def test_framed_message_reaches_execute_unchanged(recorder) -> None:
    call = _drive(recorder)
    assert call["user_message"] == FRAMED_MESSAGE


def test_parent_run_id_and_pipeline_type_thread_through(recorder) -> None:
    call = _drive(recorder)
    assert call["parent_run_id"] == "parent-run-123"
    assert call["pipeline_type"] == "prototype_revision"


def test_absent_parent_stays_none(recorder) -> None:
    """A revision launched without a resolvable parent must not fabricate one —
    downstream, previous_run's parent-seed gate keys off this being None."""
    call = _drive(recorder, parent_run_id=None)
    assert call["parent_run_id"] is None
