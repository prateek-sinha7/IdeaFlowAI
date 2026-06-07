"""tests/agents/test_parent_run_ownership.py — the default-deny ownership boundary.

Phase 5 (05-03, AUTHZ-01..04) relocated the L16 ownership seam from the pure
``agents/execution_engine/authz.py`` predicate UP into the single default-deny
scoped store helper ``agents.authz.ScopedStore`` (move-don't-copy, INV-12). This
suite exercises the helper directly against an in-memory SQLite DB (the
endpoint/injected-``Session`` path), covering:

1. ``assert_owns`` — now a REAL store lookup (D-07): it reads the parent run's
   true ``owner_id`` and raises ``PermissionError`` on a cross-owner mismatch
   (the L16 denial, AUTHZ-02). Same-owner → ``None``; an absent/TTL-swept parent
   → ``None`` (the same-owner graceful-degrade path). The ``anon:<session_id>``
   principal is a REAL owner, never a bypass (AUTHZ-03 / D-09).

2. AUTHZ-04 cross-owner DENIAL via the default-deny read filter — owner A cannot
   read owner B's ``artifact_refs`` rows (``get_ref``/``list_refs``) nor owner
   B's ``workspaces`` rows.

3. AUTHZ-03 anon isolation — a second anon session (``anon:sess-B``) cannot read
   the first session's (``anon:sess-A``) ``run_events`` / ``artifact_refs`` rows.

NOTE (intra-phase wave boundary): the ENGINE seed call-site (``engine.py``) is
rewired to this relocated helper in 05-04 (the next wave). The end-to-end
``ExecutionEngine.execute()`` denial tests are reinstated there once the engine
imports the relocated path. THIS plan's gate is the helper + the store-lookup
denial coverage above — which fully exercises the L16 denial behavior at the
store layer it now lives in.

Offline / in-memory SQLite / no API key — the ``backend:characterization`` job.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from app.models.artifact_ref import ArtifactRef
from app.models.database import Base
from app.models.run_event import RunEvent
from app.models.workflow import WorkflowRun
from app.models.workspace import Workspace


# ════════════════════════════════════════════════════════════════════════════
# In-memory DB fixture (single shared StaticPool connection)
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def db_session():
    """An in-memory SQLite session with all Phase-5 tables created.

    A single shared in-memory connection (StaticPool) so seeded rows and the
    helper reads see the same DB.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# --- seed helpers -----------------------------------------------------------


def _seed_run(session, *, run_id: str, owner_id: str, workspace_id: str = "ws-1") -> str:
    """Insert a minimal ``workflow_runs`` row owned by ``owner_id``."""
    run = WorkflowRun(
        id=run_id,
        user_id=owner_id,
        title="t",
        type="prototype",
        status="completed",
        input="idea",
        owner_id=owner_id,
        workspace_id=workspace_id,
    )
    session.add(run)
    session.commit()
    return run_id


def _seed_artifact(
    session,
    *,
    run_id: str,
    owner_id: str,
    workspace_id: str = "ws-1",
    kind: str = "spec",
    content: str = "# spec\n",
    visibility: str = "private",
) -> str:
    """Insert a minimal ``artifact_refs`` row owned by ``owner_id``."""
    art_id = str(uuid.uuid4())
    row = ArtifactRef(
        id=art_id,
        run_id=run_id,
        owner_id=owner_id,
        workspace_id=workspace_id,
        kind=kind,
        producer_step="build",
        producer_agent="prototype-build",
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        location="spec.md",
        version=1,
        visibility=visibility,
    )
    session.add(row)
    session.commit()
    return art_id


def _seed_workspace(
    session, *, owner_id: str, workspace_id: str
) -> str:
    """Insert a ``workspaces`` row owned by ``owner_id`` with self-id == ``workspace_id``."""
    row = Workspace(
        id=workspace_id,
        owner_id=owner_id,
        workspace_id=workspace_id,
    )
    session.add(row)
    session.commit()
    return workspace_id


def _seed_event(
    session, *, run_id: str, owner_id: str, workspace_id: str, seq: int
) -> str:
    """Insert a ``run_events`` row owned by ``owner_id``."""
    eid = str(uuid.uuid4())
    row = RunEvent(
        id=str(uuid.uuid4()),
        run_id=run_id,
        owner_id=owner_id,
        workspace_id=workspace_id,
        seq=seq,
        event_id=eid,
        type="agent_complete",
        payload_json={"k": "v"},
    )
    session.add(row)
    session.commit()
    return eid


# ════════════════════════════════════════════════════════════════════════════
# assert_owns — the relocated L16 seam, now a real store lookup (D-07 / AUTHZ-02)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_assert_owns_same_owner_allowed(db_session) -> None:
    """Same owner → returns None, no raise (store lookup confirms ownership)."""
    _seed_run(db_session, run_id="run-123", owner_id="alice")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    assert await store.assert_owns("run-123") is None


@pytest.mark.asyncio
async def test_assert_owns_cross_owner_denied(db_session) -> None:
    """Cross-owner → raises PermissionError naming the owner and the parent run id.

    This is the L16 denial, now enforced via the parent's TRUE owner looked up
    from the store (no by-convention argument)."""
    _seed_run(db_session, run_id="run-123", owner_id="bob")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    with pytest.raises(PermissionError) as exc:
        await store.assert_owns("run-123")
    msg = str(exc.value)
    assert "alice" in msg and "run-123" in msg


@pytest.mark.asyncio
async def test_assert_owns_anon_is_a_real_owner_denied(db_session) -> None:
    """The ``anon:<session_id>`` principal cannot bypass — a cross-owner anon
    parent (owned by 'bob') is denied (AUTHZ-03 / D-09)."""
    _seed_run(db_session, run_id="run-123", owner_id="bob")
    store = ScopedStore(
        owner_id="anon:sess-123", workspace_id="ws-1", session=db_session
    )
    with pytest.raises(PermissionError):
        await store.assert_owns("run-123")


@pytest.mark.asyncio
async def test_assert_owns_anon_same_session_allowed(db_session) -> None:
    """Two same-session anon principals (same ``anon:<session_id>`` string on the
    parent and the caller) are allowed."""
    _seed_run(db_session, run_id="run-123", owner_id="anon:sess-123")
    store = ScopedStore(
        owner_id="anon:sess-123", workspace_id="ws-1", session=db_session
    )
    assert await store.assert_owns("run-123") is None


@pytest.mark.asyncio
async def test_assert_owns_missing_parent_degrades_gracefully(db_session) -> None:
    """A missing / TTL-swept parent → returns None (no raise) — the same-owner
    graceful-degrade path (CTX-05 parity); the engine's seed try then proceeds."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    assert await store.assert_owns("parent-never-created") is None


# ════════════════════════════════════════════════════════════════════════════
# AUTHZ-04 — cross-owner artifact denial (default-deny read filter)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_artifact_cross_owner_get_ref_denied(db_session) -> None:
    """Owner A cannot read owner B's artifact_refs row via get_ref (default-deny)."""
    _seed_run(db_session, run_id="run-b", owner_id="bob")
    art_id = _seed_artifact(db_session, run_id="run-b", owner_id="bob")
    store_a = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    assert await store_a.get_ref(art_id) is None  # cross-owner → nothing → 404


@pytest.mark.asyncio
async def test_artifact_cross_owner_list_refs_denied(db_session) -> None:
    """Owner A's list_refs for owner B's run returns no artifact rows."""
    _seed_run(db_session, run_id="run-b", owner_id="bob")
    _seed_artifact(db_session, run_id="run-b", owner_id="bob")
    store_a = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    assert await store_a.list_refs("run-b") == []


@pytest.mark.asyncio
async def test_artifact_same_owner_readable(db_session) -> None:
    """Positive control: owner B can read its own artifact (filter is not vacuous)."""
    _seed_run(db_session, run_id="run-b", owner_id="bob")
    art_id = _seed_artifact(db_session, run_id="run-b", owner_id="bob")
    store_b = ScopedStore(owner_id="bob", workspace_id="ws-1", session=db_session)
    got = await store_b.get_ref(art_id)
    assert got is not None and got.id == art_id
    assert len(await store_b.list_refs("run-b")) == 1


# ════════════════════════════════════════════════════════════════════════════
# AUTHZ-04 — cross-owner workspace denial
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_workspace_cross_owner_run_denied(db_session) -> None:
    """Owner A cannot read owner B's run (workspace + owner scoped) → None → 404."""
    _seed_run(db_session, run_id="run-b", owner_id="bob", workspace_id="ws-b")
    store_a = ScopedStore(owner_id="alice", workspace_id="ws-b", session=db_session)
    assert await store_a.get_run("run-b") is None


@pytest.mark.asyncio
async def test_workspace_cross_workspace_run_denied(db_session) -> None:
    """Same owner but the caller's workspace differs → the workspace scope denies
    the read (workspace_id = :ws), proving workspace isolation on runs."""
    _seed_run(db_session, run_id="run-b", owner_id="bob", workspace_id="ws-b")
    store_other_ws = ScopedStore(
        owner_id="bob", workspace_id="ws-other", session=db_session
    )
    assert await store_other_ws.get_run("run-b") is None
    store_right = ScopedStore(
        owner_id="bob", workspace_id="ws-b", session=db_session
    )
    assert await store_right.get_run("run-b") is not None  # positive control


@pytest.mark.asyncio
async def test_workspace_default_deny_seeded_workspace(db_session) -> None:
    """Seed a workspaces row owned by owner B; owner A's scoped run/event reads in
    that workspace return nothing (the workspace itself is owner-scoped)."""
    _seed_workspace(db_session, owner_id="bob", workspace_id="ws-b")
    _seed_run(db_session, run_id="run-b", owner_id="bob", workspace_id="ws-b")
    store_a = ScopedStore(owner_id="alice", workspace_id="ws-b", session=db_session)
    assert await store_a.get_run("run-b") is None


# ════════════════════════════════════════════════════════════════════════════
# AUTHZ-03 — anon session isolation (a second anon session can't read the first's)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_anon_session_b_cannot_read_session_a_events(db_session) -> None:
    """``anon:sess-B`` cannot read ``anon:sess-A``'s run_events rows."""
    _seed_run(db_session, run_id="run-a", owner_id="anon:sess-A", workspace_id="ws-a")
    _seed_event(
        db_session, run_id="run-a", owner_id="anon:sess-A", workspace_id="ws-a", seq=1
    )
    store_b = ScopedStore(
        owner_id="anon:sess-B", workspace_id="ws-a", session=db_session
    )
    assert await store_b.read_events("run-a", after_seq=0) == []
    # positive control: session A reads its own event
    store_a = ScopedStore(
        owner_id="anon:sess-A", workspace_id="ws-a", session=db_session
    )
    assert len(await store_a.read_events("run-a", after_seq=0)) == 1


@pytest.mark.asyncio
async def test_anon_session_b_cannot_read_session_a_artifacts(db_session) -> None:
    """``anon:sess-B`` cannot read ``anon:sess-A``'s artifact_refs row."""
    _seed_run(db_session, run_id="run-a", owner_id="anon:sess-A", workspace_id="ws-a")
    art_id = _seed_artifact(
        db_session, run_id="run-a", owner_id="anon:sess-A", workspace_id="ws-a"
    )
    store_b = ScopedStore(
        owner_id="anon:sess-B", workspace_id="ws-a", session=db_session
    )
    assert await store_b.get_ref(art_id) is None
    assert await store_b.list_refs("run-a") == []
