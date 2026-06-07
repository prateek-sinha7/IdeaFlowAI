"""Wave 0 migration test for 0014_typed_artifacts_persistence (PERSIST-01).

Proves the additive §18 persistence schema in isolation, before any engine
rewiring:

  1. ``alembic upgrade`` from 0013 → 0014 creates the four new tables
     (artifact_refs, workspaces, run_events, run_capabilities).
  2. workflow_runs and workflows gain their new columns.
  3. The required indexes exist (artifact_refs run_kind + content_hash;
     run_events run_seq).
  4. Every new table carries owner_id + workspace_id (AUTHZ-01).
  5. A pre-seeded existing run is backfilled with a non-null owner_id +
     workspace_id (Highest-Risk Behavior 3 — uniform scoping).
  6. ``alembic downgrade`` 0014 → 0013 reverses cleanly: the four tables are
     gone and the added columns are gone (T-5-MIGRATE-DOWN).

Runs against a real on-disk SQLite file (FK PRAGMA on, matching prod/Postgres
semantics for the FK columns). The migration uses only generic SQLAlchemy
types so SQLite is a faithful proxy for the up/down + backfill logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def _make_config(db_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture
def fresh_db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "migration_0014_test.db"
    return f"sqlite:///{db_path}"


def _seed_existing_run(db_url: str) -> tuple[str, str]:
    """Insert one user + one workflow_run via raw SQL against the 0013 schema.

    Raw SQL (not the ORM) is used deliberately so the seed only touches columns
    that exist at revision 0013 — the ORM models carry the post-0014 columns.
    Returns (user_id, run_id).
    """
    user_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, tier, is_admin, "
                "created_at, updated_at) VALUES "
                "(:id, :email, :pw, 'basic', 0, :now, :now)"
            ),
            {"id": user_id, "email": f"{user_id}@t.test", "pw": "x", "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO workflow_runs (id, user_id, title, type, status, "
                "input, agent_count, created_at) VALUES "
                "(:id, :uid, 'T', 'prototype', 'completed', 'idea', 0, :now)"
            ),
            {"id": run_id, "uid": user_id, "now": now},
        )
    engine.dispose()
    return user_id, run_id


_NEW_TABLES = ["artifact_refs", "workspaces", "run_events", "run_capabilities"]


class TestMigration0014:
    def test_upgrade_creates_tables_columns_indexes_and_backfills(
        self, fresh_db_url: str
    ) -> None:
        cfg = _make_config(fresh_db_url)

        # Bring the DB up to 0013, seed an existing run, then apply 0014.
        command.upgrade(cfg, "0013")
        user_id, run_id = _seed_existing_run(fresh_db_url)
        command.upgrade(cfg, "0014")

        engine = create_engine(fresh_db_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        # (a) four new tables exist
        for t in _NEW_TABLES:
            assert t in tables, f"table {t!r} missing after upgrade"

        # (b) workflow_runs / workflows gained their new columns
        run_cols = {c["name"] for c in inspector.get_columns("workflow_runs")}
        for col in (
            "owner_id",
            "workspace_id",
            "source_run_id",
            "plan_id",
            "budget_snapshot_json",
        ):
            assert col in run_cols, f"workflow_runs.{col} missing"
        wf_cols = {c["name"] for c in inspector.get_columns("workflows")}
        for col in (
            "owner_id",
            "workspace_id",
            "source",
            "manifest_json",
            "version",
        ):
            assert col in wf_cols, f"workflows.{col} missing"

        # (c) required indexes exist
        ar_idx = {ix["name"] for ix in inspector.get_indexes("artifact_refs")}
        assert "ix_artifact_refs_run_kind" in ar_idx
        assert "ix_artifact_refs_content_hash" in ar_idx
        re_idx = {ix["name"] for ix in inspector.get_indexes("run_events")}
        assert "ix_run_events_run_seq" in re_idx

        # (d) every new table carries owner_id + workspace_id (AUTHZ-01)
        for t in _NEW_TABLES:
            cols = {c["name"] for c in inspector.get_columns(t)}
            assert "owner_id" in cols, f"{t} missing owner_id"
            assert "workspace_id" in cols, f"{t} missing workspace_id"

        # (e) the pre-seeded run is backfilled with non-null owner_id + workspace_id
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT owner_id, workspace_id FROM workflow_runs "
                    "WHERE id = :id"
                ),
                {"id": run_id},
            ).fetchone()
            assert row is not None
            owner_id, workspace_id = row
            assert owner_id == user_id, "backfill set owner_id = user_id"
            assert workspace_id, "backfill left workspace_id null"
            # a matching workspaces row exists, scoped to the same owner
            ws = conn.execute(
                text(
                    "SELECT owner_id, workspace_id FROM workspaces "
                    "WHERE id = :id"
                ),
                {"id": workspace_id},
            ).fetchone()
            assert ws is not None, "backfill did not create a workspaces row"
            assert ws[0] == user_id
            assert ws[1] == workspace_id  # workspace_id == its own id
        engine.dispose()

    def test_downgrade_reverses_cleanly_to_0013(
        self, fresh_db_url: str
    ) -> None:
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "0013")
        _seed_existing_run(fresh_db_url)
        command.upgrade(cfg, "0014")
        command.downgrade(cfg, "0013")

        engine = create_engine(fresh_db_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        # four new tables are gone
        for t in _NEW_TABLES:
            assert t not in tables, f"downgrade left table {t!r} behind"

        # the added columns are gone from workflow_runs / workflows
        run_cols = {c["name"] for c in inspector.get_columns("workflow_runs")}
        for col in (
            "owner_id",
            "workspace_id",
            "source_run_id",
            "plan_id",
            "budget_snapshot_json",
        ):
            assert col not in run_cols, f"workflow_runs.{col} survived downgrade"
        wf_cols = {c["name"] for c in inspector.get_columns("workflows")}
        for col in ("owner_id", "workspace_id", "source", "manifest_json", "version"):
            assert col not in wf_cols, f"workflows.{col} survived downgrade"
        engine.dispose()
