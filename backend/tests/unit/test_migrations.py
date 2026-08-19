"""tests/unit/test_migrations.py — the 0016 additive capability-hardening tables (08-02 / D-10).

Phase 8 (08-02) lands ONE additive Alembic migration (``0016``) adding the three
owner/workspace-scoped §18 tables the gates (08-02), validators (08-04), and hooks
(08-07) write rows into: ``validation_results``, ``gate_events``, ``hook_runs``.

This suite covers the three Task-1 behaviors (offline / in-memory SQLite, no DB
service):

1. ``alembic upgrade head`` creates all three tables; each has ``owner_id`` and
   ``workspace_id`` columns (both NOT NULL).
2. Each model row write goes through the ``ScopedStore`` (owner/workspace sourced
   from the helper principal) — a cross-owner read returns nothing (default-deny
   precedent, T-08-02-ID).
3. The migration's ``down_revision`` is ``"0015"`` (the head chain unbroken).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from app.models.database import Base
from app.models.gate_events import GateEvent
from app.models.workflow import WorkflowRun

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"

_NEW_TABLES = ("validation_results", "gate_events", "hook_runs")


def _make_config(db_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture
def fresh_db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "alembic_0016.db"
    return f"sqlite:///{db_path}"


# ════════════════════════════════════════════════════════════════════════════
# 1. upgrade head creates the three tables, each with NOT NULL owner/workspace
# ════════════════════════════════════════════════════════════════════════════


def test_upgrade_head_creates_three_capability_tables(fresh_db_url: str) -> None:
    """``alembic upgrade head`` creates validation_results/gate_events/hook_runs."""
    command.upgrade(_make_config(fresh_db_url), "head")

    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for t in _NEW_TABLES:
        assert t in tables, f"0016 did not create {t!r} (got {sorted(tables)})"


def test_each_table_has_not_null_owner_and_workspace(fresh_db_url: str) -> None:
    """Every new table carries owner_id + workspace_id, both NOT NULL (AUTHZ-01)."""
    command.upgrade(_make_config(fresh_db_url), "head")

    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    for table in _NEW_TABLES:
        cols = {c["name"]: c for c in inspector.get_columns(table)}
        assert "owner_id" in cols, f"{table} missing owner_id"
        assert "workspace_id" in cols, f"{table} missing workspace_id"
        assert cols["owner_id"]["nullable"] is False, (
            f"{table}.owner_id must be NOT NULL"
        )
        assert cols["workspace_id"]["nullable"] is False, (
            f"{table}.workspace_id must be NOT NULL"
        )


# ════════════════════════════════════════════════════════════════════════════
# 2. ScopedStore gate_events write is owner/workspace-scoped (default-deny)
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def db_session():
    """In-memory SQLite session with all tables created (StaticPool so the seeded
    run row and the helper reads share one connection)."""
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


def _seed_run(session, *, run_id: str, owner_id: str, workspace_id: str) -> None:
    session.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="t",
            type="prototype",
            status="running",
            input="idea",
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
    )
    session.commit()


@pytest.mark.asyncio
async def test_gate_event_write_is_owner_workspace_scoped(db_session) -> None:
    """A gate_events write stamps the helper principal; the same-owner read
    returns it, and a cross-owner read returns nothing (default-deny)."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")

    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await alice.record_gate_event(
        "run-1", step="prototype-build", gate="security", outcome="block",
        detail={"reason": "exec requested, exec OFF"},
    )
    assert row_id

    # The persisted row carries the helper's owner/workspace + outcome.
    row = db_session.query(GateEvent).filter(GateEvent.id == row_id).one()
    assert row.owner_id == "alice"
    assert row.workspace_id == "ws-1"
    assert row.gate == "security"
    assert row.outcome == "block"

    # Same-owner scoped read returns the row.
    own = await alice.read_gate_events("run-1")
    assert [r.id for r in own] == [row_id]

    # Cross-owner scoped read returns NOTHING (default-deny, T-08-02-ID).
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-9", session=db_session)
    assert await mallory.read_gate_events("run-1") == []


# ════════════════════════════════════════════════════════════════════════════
# 3. down_revision chain unbroken (0015 -> 0016)
# ════════════════════════════════════════════════════════════════════════════


def test_migration_0016_down_revision_is_0015() -> None:
    """0016's down_revision is exactly "0015" — the head chain is unbroken.

    NOTE: this only asserts 0016's own link to 0015. It does NOT assert 0016
    is the current head — later migrations (up to 0031 as of this writing)
    have since landed on top of it, which is expected and not a break in the
    chain. Asserting a specific head here would make this test stale on every
    subsequent migration.
    """
    script = ScriptDirectory.from_config(_make_config("sqlite://"))
    rev = script.get_revision("0016")
    assert rev is not None, "revision 0016 not found in the migration ledger"
    assert rev.down_revision == "0015", (
        f"0016 down_revision is {rev.down_revision!r}, expected '0015'"
    )
    # The ledger must resolve to exactly ONE head. Asserting a hardcoded
    # revision number here goes stale on every new migration (0016 was the head
    # when this test was written); the invariant worth guarding is single-head,
    # because a second head makes `alembic upgrade head` ambiguous and it fails
    # with "Multiple head revisions are present" — which crash-loops the backend
    # container, since docker-entrypoint.sh runs it under `set -eu`.
    # The chain must still resolve to a SINGLE head (no branch point), even if
    # that head has moved past 0016.
    heads = list(script.get_heads())
    assert len(heads) == 1, f"expected a single head, got {heads}"


# ════════════════════════════════════════════════════════════════════════════
# 4. WR-02 — migration 0023 (workflow_runs.selections_json) ledger
# ════════════════════════════════════════════════════════════════════════════


def test_migration_0023_down_revision_is_0022() -> None:
    """0023's down_revision is exactly "0022" — the head chain is unbroken
    (WR-02).

    NOTE: this only asserts 0023's own link to 0022, not that 0023 is the
    current head — later migrations (up to 0031 as of this writing) have
    since landed on top of it. Asserting a specific head would make this test
    stale on every subsequent migration.
    """
    script = ScriptDirectory.from_config(_make_config("sqlite://"))
    rev = script.get_revision("0023")
    assert rev is not None, "revision 0023 not found in the migration ledger"
    assert rev.down_revision == "0022", (
        f"0023 down_revision is {rev.down_revision!r}, expected '0022'"
    )
    # Single-head, not a hardcoded revision number — see the note in
    # test_migration_0016_down_revision_is_0015.
    # The chain must still resolve to a SINGLE head (no branch point), even if
    # that head has moved past 0023.
    heads = list(script.get_heads())
    assert len(heads) == 1, f"expected a single head, got {heads}"


def test_migration_0023_is_additive_only() -> None:
    """Migration 0023 is single-head additive (down_revision 0022); upgrade adds
    ONLY the selections_json column and contains no drop/alter-narrow of existing
    columns (WR-02). Source-level assertion — no DB round-trip required."""
    mig = (
        _BACKEND_DIR
        / "alembic"
        / "versions"
        / "0023_workflow_run_selections.py"
    )
    src = mig.read_text()
    assert 'revision = "0023"' in src
    assert 'down_revision = "0022"' in src
    # upgrade() body: additive add_column only; no destructive ops on existing cols.
    upgrade_body = src.split("def upgrade")[1].split("def downgrade")[0]
    assert "add_column" in upgrade_body
    assert "selections_json" in upgrade_body
    assert "drop_column" not in upgrade_body
    assert "alter_column" not in upgrade_body
    assert "drop_table" not in upgrade_body


# ════════════════════════════════════════════════════════════════════════════
# 5. RESUME-06 — migration 0026 (subagent_runs task_id + worker_index) ledger
# ════════════════════════════════════════════════════════════════════════════


def test_migration_0026_is_additive() -> None:
    """Migration 0026 is single-head additive (down_revision 0025); upgrade adds
    ONLY the two nullable task-identity columns (task_id + worker_index) and
    contains no drop/alter-narrow/drop-table of existing columns (RESUME-06).
    Source-level assertion — no DB round-trip (the round-trip lives in
    tests/agents/test_subagent_runs.py)."""
    mig = (
        _BACKEND_DIR
        / "alembic"
        / "versions"
        / "0026_subagent_task_identity.py"
    )
    src = mig.read_text()
    assert 'revision = "0026"' in src
    assert 'down_revision = "0025"' in src
    # upgrade() body: additive add_column only; no destructive ops on existing cols.
    upgrade_body = src.split("def upgrade")[1].split("def downgrade")[0]
    assert "add_column" in upgrade_body
    assert "task_id" in upgrade_body
    assert "worker_index" in upgrade_body
    assert "drop_column" not in upgrade_body
    assert "alter_column" not in upgrade_body
    assert "drop_table" not in upgrade_body
    assert "create_table" not in upgrade_body