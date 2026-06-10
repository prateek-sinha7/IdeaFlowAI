"""tests/agents/test_exec_runs.py — Wave-1 exec audit trail (Phase 10 / EXEC-01).

Drives the bypass-proof exec audit layer fully OFFLINE (no DB / Bedrock / API key /
network):

  * the additive ``0018`` migration is reversible against a fresh SQLite DB
    (``upgrade head`` -> ``downgrade -1`` -> ``upgrade head``), mirroring the
    ``test_alembic.py`` recipe;
  * ``ScopedStore.record_exec_run`` writes EXACTLY ONE owner/workspace-scoped
    ``exec_runs`` row for each outcome (``allowed`` | ``denied`` | ``killed``),
    returning a non-empty id;
  * a cross-owner read returns nothing (default-deny scoping, T-10-01-08);
  * ``KernelServices.record_exec_run`` degrades to ``None`` offline (no
    ``scoped_store`` on the ectx) WITHOUT raising — the audit write must never
    abort the run (Pitfall 6 / best-effort degrade, mirrors ``record_hook_run``).

Offline / in-memory SQLite / no API key — the ``backend:characterization`` job
(mirrors ``tests/agents/test_repositories_persistence.py`` +
``tests/unit/test_alembic.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore

# Importing app.models registers every model on Base.metadata (Pitfall 5) so
# create_all builds exec_runs (+ the rest) for the test DB.
import app.models  # noqa: F401
from app.models.database import Base
from app.models.exec_runs import ExecRun


# ---------------------------------------------------------------------------
# Alembic reversibility (0018) — mirrors tests/unit/test_alembic.py
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"

_EXPECTED_EXEC_COLUMNS = {
    "id",
    "run_id",
    "owner_id",
    "workspace_id",
    "step",
    "argv_json",
    "outcome",
    "exit_code",
    "duration_ms",
    "policy_snapshot_json",
    "output_digest",
    "created_at",
}


def _make_config(db_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture
def fresh_db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "alembic_exec_runs.db"
    return f"sqlite:///{db_path}"


def test_0018_reversible_offline(fresh_db_url: str) -> None:
    """``upgrade head`` -> ``downgrade -1`` -> ``upgrade head`` round-trips clean.

    After the first ``upgrade head`` the ``exec_runs`` table exists with the
    expected columns; ``downgrade -1`` drops it; a second ``upgrade head``
    recreates it (mirror of the 0017 reversibility proof).
    """
    cfg = _make_config(fresh_db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("exec_runs"), "exec_runs missing after upgrade head"
    cols = {c["name"] for c in inspector.get_columns("exec_runs")}
    assert _EXPECTED_EXEC_COLUMNS.issubset(cols), (
        f"exec_runs missing columns: {sorted(_EXPECTED_EXEC_COLUMNS - cols)}"
    )
    engine.dispose()

    # downgrade -1 drops exec_runs (0018 is the head; -1 lands on 0017).
    command.downgrade(cfg, "-1")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert not inspector.has_table("exec_runs"), (
        "downgrade -1 must drop exec_runs"
    )
    engine.dispose()

    # upgrade head recreates it.
    command.upgrade(cfg, "head")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("exec_runs"), "exec_runs missing after re-upgrade"
    engine.dispose()


# ---------------------------------------------------------------------------
# ScopedStore.record_exec_run — scoped write + default-deny read
# ---------------------------------------------------------------------------


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


@pytest.mark.asyncio
async def test_record_exec_run_allowed_writes_scoped_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_exec_run(
        "run-1",
        "build",
        ["python3", "-c", "print(1)"],
        "allowed",
        exit_code=0,
        duration_ms=12,
        policy_snapshot={"exec_allow": ["python3"]},
        output_digest="ok",
    )
    assert row_id, "record_exec_run must return a non-empty id"

    rows = db_session.query(ExecRun).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == row_id
    assert row.run_id == "run-1"
    assert row.owner_id == "alice"        # AUTHZ-01
    assert row.workspace_id == "ws-1"     # AUTHZ-01
    assert row.step == "build"
    assert row.outcome == "allowed"
    assert row.exit_code == 0
    assert row.argv_json == ["python3", "-c", "print(1)"]


@pytest.mark.asyncio
async def test_record_exec_run_denied_writes_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_exec_run(
        "run-1", "build", ["bash", "-c", "echo hi"], "denied", exit_code=None
    )
    assert row_id
    rows = db_session.query(ExecRun).filter(ExecRun.outcome == "denied").all()
    assert len(rows) == 1
    assert rows[0].exit_code is None


@pytest.mark.asyncio
async def test_record_exec_run_killed_writes_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_exec_run(
        "run-1", "build", ["python3", "-c", "import time;time.sleep(99)"], "killed"
    )
    assert row_id
    rows = db_session.query(ExecRun).filter(ExecRun.outcome == "killed").all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_cross_owner_exec_run_read_returns_nothing(db_session):
    """T-10-01-08: a different owner reads zero exec_runs rows (default-deny)."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await alice.record_exec_run("run-1", "build", ["python3"], "allowed", exit_code=0)

    # Cross-owner scoped read returns nothing.
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=db_session)
    assert await mallory.read_exec_runs("run-1") == []

    # The true owner still resolves it (the filter is not a blanket deny).
    assert len(await alice.read_exec_runs("run-1")) == 1


# ---------------------------------------------------------------------------
# KernelServices.record_exec_run — best-effort degrade (Pitfall 6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kernel_services_record_exec_run_degrades_to_none_offline():
    """No scoped_store on the ectx -> returns None WITHOUT raising (Pitfall 6)."""
    from agents.execution_engine.kernel_services import KernelServices

    class _Ectx:
        scoped_store = None

    ks = KernelServices.__new__(KernelServices)  # bypass __init__ (offline harness)
    ks._ectx = _Ectx()
    ks.run_id = "run-1"

    result = await ks.record_exec_run(
        "build", ["python3", "-c", "print(1)"], "allowed", exit_code=0
    )
    assert result is None


def test_kernel_services_has_workspace_attribute_default():
    """KernelServices declares a ``workspace`` attribute (bound in 10-02's seam)."""
    from agents.execution_engine.kernel_services import KernelServices

    # The attribute must exist on a fully-constructed instance (default None).
    import inspect as _inspect

    src = _inspect.getsource(KernelServices.__init__)
    assert "self.workspace" in src, (
        "KernelServices.__init__ must declare self.workspace (10-02 host seam)"
    )
