"""tests/agents/test_repositories_persistence.py — Wave-0 repo persistence (RUNTIME-03).

Drives the ``ScopedStore.create_repository`` write path (the same seam the repo
workflows use) against an in-memory SQLite DB and asserts the RUNTIME-03 invariant:

  * a scoped write inserts EXACTLY ONE ``repositories`` row + links EXACTLY ONE
    ``kind='repo'`` ``workspaces`` row by ``repo_id`` (the FK wired by 0017);
  * both rows carry ``owner_id`` + ``workspace_id`` (AUTHZ-01);
  * a cross-owner read of the repo via a second ``ScopedStore`` raises
    ``PermissionError`` (T-09-02-ID default-deny denial gate), and the default-deny
    ``get_repository`` returns ``None`` cross-owner.

Offline / in-memory SQLite / no API key — the ``backend:characterization`` job
(mirrors ``tests/unit/test_run_capabilities.py``).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore

# Importing app.models registers every model on Base.metadata (Pitfall 5) so
# create_all builds repositories + workspaces (+ the rest) for the test DB.
import app.models  # noqa: F401
from app.models.database import Base
from app.models.repository import Repository
from app.models.workspace import Workspace


@pytest.fixture
def db_session():
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


async def _seed_repo_workspace(store: ScopedStore, *, owner: str) -> str:
    """Create a kind=repo workspace via the scoped writer; return its id."""
    return await store.create_workspace("run-1", kind="repo", runtime="local")


# ---------------------------------------------------------------------------
# RUNTIME-03 — one repositories row + one kind=repo workspaces row, linked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_repository_persists_one_row_and_links_workspace(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-seed", session=db_session)

    # The run-entry writer creates the repo workspace (self-id workspace_id).
    ws_id = await store.create_workspace("run-1", kind="repo", runtime="local")

    # The scoped writer inserts the repo row + links the workspace by repo_id.
    repo_id = await store.create_repository(
        provider="local",
        url="/srv/fixtures/sample-repo",
        default_branch="main",
        workspace_id=ws_id,
        auth_ref=None,
    )

    # (1) EXACTLY ONE repositories row.
    repos = db_session.query(Repository).all()
    assert len(repos) == 1, f"expected one repositories row, found {len(repos)}"
    repo = repos[0]
    assert repo.id == repo_id
    assert repo.provider == "local"          # free String, no enum
    assert repo.url == "/srv/fixtures/sample-repo"
    assert repo.default_branch == "main"

    # (2) Both rows carry owner_id + workspace_id (AUTHZ-01).
    assert repo.owner_id == "alice"
    assert repo.workspace_id == ws_id

    # (3) EXACTLY ONE kind='repo' workspaces row, linked by repo_id.
    repo_workspaces = (
        db_session.query(Workspace).filter(Workspace.kind == "repo").all()
    )
    assert len(repo_workspaces) == 1, (
        f"expected one kind=repo workspaces row, found {len(repo_workspaces)}"
    )
    ws_row = repo_workspaces[0]
    assert ws_row.id == ws_id
    assert ws_row.repo_id == repo_id, "the workspace must link to the repo by repo_id"
    assert ws_row.owner_id == "alice"
    assert ws_row.workspace_id == ws_id


@pytest.mark.asyncio
async def test_cross_owner_repo_read_is_denied(db_session):
    """T-09-02-ID: a different owner cannot read the repo (default-deny + assert)."""
    seeder = ScopedStore(owner_id="alice", workspace_id="ws-seed", session=db_session)
    ws_id = await seeder.create_workspace("run-1", kind="repo", runtime="local")
    repo_id = await seeder.create_repository(
        provider="github",
        url="https://example.test/alice/repo",
        default_branch="main",
        workspace_id=ws_id,
    )

    # The run's store is scoped to the repo workspace (self-id workspace_id) — the
    # real-world principal for a repo run's reads.
    alice = ScopedStore(owner_id="alice", workspace_id=ws_id, session=db_session)

    # A second owner's scoped read returns nothing (default-deny → 404 at the API).
    mallory = ScopedStore(owner_id="mallory", workspace_id=ws_id, session=db_session)
    assert await mallory.get_repository(repo_id) is None

    # And the explicit ownership assertion raises PermissionError (the denial gate).
    with pytest.raises(PermissionError):
        await mallory.assert_repo_owned(repo_id)

    # The true owner still resolves it (sanity — the filter is not a blanket deny).
    assert (await alice.get_repository(repo_id)) is not None
    await alice.assert_repo_owned(repo_id)  # does not raise
