"""Merge-conflict artifact refs are owner-scoped (Phase 11 / FANOUT-08, T-11-03-02).

Moved out of ``tests/unit/agents/workflows/test_merge_conflict.py`` in Batch 6: this is
the one test in that module that builds a real SQLAlchemy engine and writes a real
``ArtifactRef`` row to prove a cross-owner read returns nothing. The merge-dispatch and
on-conflict policy tests it lived beside drive the strategy against fakes with no
database and stayed in the unit suite.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_merge_conflict_artifact_is_owner_scoped():
    """A merge_conflict ArtifactRef written by alice is invisible to bob (T-11-03-02)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 — register models on Base.metadata
    from app.models.database import Base
    from agents.authz import ScopedStore
    from agents.artifacts.graph import ArtifactRef

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()

    alice = ScopedStore(owner_id="alice", workspace_id="ws-a", session=session)
    ref = ArtifactRef(
        id="mc-1",
        kind="merge_conflict",
        owner_id="alice",
        workspace_id="ws-a",
        run_id="run-mc",
        producer_step="fanout-step",
        producer_agent="fanout-step",
        task_id=None,
        content='{"conflicts": [{"path": "shared.txt"}]}',
        content_hash="h",
        location="merge_conflict/fanout-step.json",
        version=1,
        visibility="private",
    )
    await alice.write_ref(ref)

    # Alice reads her own conflict artifact.
    alice_refs = await alice.list_refs("run-mc", kind="merge_conflict")
    assert len(alice_refs) == 1

    # Bob (a different owner) reads nothing — owner-scoped (cross-owner = ∅).
    bob = ScopedStore(owner_id="bob", workspace_id="ws-b", session=session)
    bob_refs = await bob.list_refs("run-mc", kind="merge_conflict")
    assert bob_refs == []

    session.close()
    Base.metadata.drop_all(bind=engine)
