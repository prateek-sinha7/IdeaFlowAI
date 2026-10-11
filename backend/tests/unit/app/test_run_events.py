"""``_RunEventSink`` degradation contract — the branches that need no database.

The engine's event sink is armed with a store + run id; when it is NOT armed, or when the
persist call fails, its behaviour is a deliberate policy rather than an accident:

  * un-armed → silently no-op (a run with no durable log must still execute);
  * a DB-layer persist failure → degrade, never propagate (losing durability must not kill
    a live run);
  * a NON-DB failure → re-raise (a programming error must not be swallowed by the
    degradation path).

All three are exercised with a stub store, so they need no engine and no rows. The
PERSISTENCE contract — contiguous ``seq``, unique ``event_id``, the cross-owner read deny,
serialized seq allocation and the raced-seq retry — is about real rows and unique
constraints, and lives in ``tests/integration/repositories/test_run_events_db.py``.
"""

from __future__ import annotations

import uuid

import pytest

from agents.execution_engine.engine import _RunEventSink


@pytest.mark.asyncio
async def test_run_event_sink_unarmed_is_noop():
    """An un-armed sink (no store/run id) silently no-ops — never raises."""
    sink = _RunEventSink()
    # Must not raise even though nothing is persisted.
    await sink.persist(1, str(uuid.uuid4()), "agent_start", {"k": "v"})


@pytest.mark.asyncio
async def test_run_event_sink_degrades_on_db_persist_failure():
    """A DB persist FAILURE (the offline harness has no workflow_runs/run_events
    schema → SQLAlchemyError) is degraded to a warning — the byte-identity / parity
    guard (INV-3): the live stream must never break on a DB error. WR-02: the
    degrade is narrowed to the SQLAlchemy error family."""
    from sqlalchemy.exc import OperationalError

    class _BoomStore:
        async def append_event_at_or_after(self, *a, **k):
            raise OperationalError("no such table: run_events", None, Exception())

    sink = _RunEventSink()
    sink.arm(_BoomStore(), "run-1")  # type: ignore[arg-type]
    # Must NOT raise — the DB failure degrades to a warning log.
    await sink.persist(1, str(uuid.uuid4()), "agent_complete", {"k": "v"})


@pytest.mark.asyncio
async def test_run_event_sink_reraises_non_db_persist_failure():
    """WR-02: a NON-DB persist failure (a real bug — not the offline-harness DB
    condition) must PROPAGATE, not be masked as a silent no-op."""

    class _BoomStore:
        async def append_event_at_or_after(self, *a, **k):
            raise RuntimeError("unexpected non-DB failure")

    sink = _RunEventSink()
    sink.arm(_BoomStore(), "run-1")  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="unexpected non-DB failure"):
        await sink.persist(1, str(uuid.uuid4()), "agent_complete", {"k": "v"})
