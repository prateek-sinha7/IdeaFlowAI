"""tests/agents/test_wave_runs.py — the per-wave persistence backbone (Phase 12 / WAVE-02).

Drives the additive ``0020 wave_runs`` persistence layer fully OFFLINE (no DB /
Bedrock / API key / network), mirroring ``test_subagent_runs.py`` (0019):

  * the additive ``0020`` migration is reversible against a fresh SQLite DB
    (``upgrade head`` -> ``downgrade -1`` -> ``upgrade head``) with NO ``sa.Enum`` and a
    single ``0019 -> 0020`` head;
  * ``ScopedStore.record_wave_run`` writes EXACTLY ONE owner/workspace-scoped
    ``wave_runs`` row per wave, round-tripping step/wave_index/task_ids/status, and
    ``update_wave_run`` flips the row terminal;
  * a cross-owner ``read_wave_runs`` returns nothing (default-deny scoping — the
    T-12-01-IDOR mitigation).

Offline / in-memory SQLite / no API key — the ``backend:characterization`` job.
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
# create_all builds wave_runs (+ the rest) for the test DB.
import app.models  # noqa: F401
from app.models.database import Base
from app.models.wave_run import WaveRun


# ---------------------------------------------------------------------------
# Alembic reversibility (0020) — mirrors test_subagent_runs.py::test_0019_reversible
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"

_EXPECTED_WAVE_COLUMNS = {
    "id",
    "run_id",
    "owner_id",
    "workspace_id",
    "step",
    "wave_index",
    "task_ids",
    "status",
    "created_at",
}


def _make_config(db_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture
def fresh_db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "alembic_wave_runs.db"
    return f"sqlite:///{db_path}"


def test_0020_reversible_offline(fresh_db_url: str) -> None:
    """``upgrade head`` -> ``downgrade -1`` -> ``upgrade head`` round-trips clean (single head 0020)."""
    cfg = _make_config(fresh_db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("wave_runs"), "wave_runs missing after upgrade head"
    cols = {c["name"] for c in inspector.get_columns("wave_runs")}
    assert _EXPECTED_WAVE_COLUMNS.issubset(cols), (
        f"wave_runs missing columns: {sorted(_EXPECTED_WAVE_COLUMNS - cols)}"
    )
    engine.dispose()

    # downgrade -1 drops wave_runs (0020 is the head; -1 lands on 0019).
    command.downgrade(cfg, "-1")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert not inspector.has_table("wave_runs"), "downgrade -1 must drop wave_runs"
    engine.dispose()

    # upgrade head recreates it.
    command.upgrade(cfg, "head")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("wave_runs"), "wave_runs missing after re-upgrade"
    engine.dispose()


def test_0020_migration_uses_free_string_status() -> None:
    """No ``sa.Enum`` on the 0020 migration — status is a free String (Q3/INV-3)."""
    mig = _BACKEND_DIR / "alembic" / "versions" / "0020_wave_runs.py"
    text = mig.read_text()
    assert "sa.Enum" not in text, "0020 must use a free String status (NO sa.Enum)"
    assert 'revision = "0020"' in text
    assert 'down_revision = "0019"' in text


# ---------------------------------------------------------------------------
# ScopedStore.record_wave_run — scoped write + default-deny read
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
async def test_record_wave_run_writes_scoped_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_wave_run(
        "run-1",
        step="wave-step",
        wave_index=0,
        task_ids=["t1", "t2"],
        status="running",
    )
    assert row_id, "record_wave_run must return a non-empty id"

    rows = db_session.query(WaveRun).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == row_id
    assert row.run_id == "run-1"
    assert row.owner_id == "alice"        # AUTHZ-01
    assert row.workspace_id == "ws-1"     # AUTHZ-01
    assert row.step == "wave-step"
    assert row.wave_index == 0
    assert row.task_ids == ["t1", "t2"]
    assert row.status == "running"


@pytest.mark.asyncio
async def test_wave_run_lifecycle_record_then_update_terminal(db_session):
    """A wave row goes running -> completed; the read shows the terminal status."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_wave_run(
        "run-1", step="wave-step", wave_index=0, task_ids=["t1"], status="running"
    )
    await store.update_wave_run(row_id, status="completed")

    rows = await store.read_wave_runs("run-1")
    assert len(rows) == 1
    assert rows[0].status == "completed"


@pytest.mark.asyncio
async def test_cross_owner_wave_read_returns_nothing(db_session):
    """T-12-01-IDOR: a different owner reads zero wave_runs rows."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await alice.record_wave_run(
        "run-1", step="wave-step", wave_index=0, task_ids=["t1"], status="running"
    )

    # Cross-owner scoped read returns nothing.
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=db_session)
    assert await mallory.read_wave_runs("run-1") == []

    # The true owner still resolves it (the filter is not a blanket deny).
    assert len(await alice.read_wave_runs("run-1")) == 1


@pytest.mark.asyncio
async def test_cross_owner_wave_update_is_noop(db_session):
    """A cross-owner update_wave_run leaves the row untouched (no-op)."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await alice.record_wave_run(
        "run-1", step="wave-step", wave_index=0, task_ids=["t1"], status="running"
    )

    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=db_session)
    await mallory.update_wave_run(row_id, status="completed")

    rows = await alice.read_wave_runs("run-1")
    assert rows[0].status == "running", "cross-owner update must be a no-op"


@pytest.mark.asyncio
async def test_read_wave_runs_ordered_by_wave_index(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await store.record_wave_run(
        "run-1", step="s", wave_index=1, task_ids=["b"], status="completed"
    )
    await store.record_wave_run(
        "run-1", step="s", wave_index=0, task_ids=["a"], status="completed"
    )
    rows = await store.read_wave_runs("run-1")
    assert [r.wave_index for r in rows] == [0, 1]
