"""Tests for the Alembic migration setup (A8).

Three things must hold for the migrations to be trustworthy:

1. ``alembic upgrade head`` runs cleanly against an empty DB.
2. ``alembic downgrade base`` rolls back without leaving stragglers.
3. After upgrading, the set of tables in the DB matches
   ``Base.metadata.tables`` — i.e. the migration is in sync with the models.

The third assertion is the load-bearing one: it catches the "added a column
to the model but forgot to autogenerate" failure mode that
``Base.metadata.create_all`` used to mask in the old startup path.

We run everything against in-memory SQLite. The migration file uses only
generic SQLAlchemy types (``String``, ``Text``, ``Integer``, ``Float``,
``DateTime``) so SQLite is a faithful enough proxy for the integration test.
A separate full-Postgres run lives in CI; here we just want fast, hermetic
unit-level coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.models.database import Base


# Resolve the alembic.ini that lives at backend/alembic.ini, regardless of
# where pytest is invoked from. Going up three parents from this file
# (tests/unit/test_alembic.py → tests/unit → tests → backend/) lands at the
# backend root.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def _make_config(db_url: str) -> Config:
    """Build an alembic.config.Config pointed at the project's alembic.ini
    but with ``sqlalchemy.url`` overridden to the supplied test URL.

    env.py honours an already-set ``sqlalchemy.url`` over
    ``settings.DATABASE_URL`` (see env.py "Resolve the DB URL" block), so
    setting it here is enough to redirect every command.
    """
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    # Belt-and-braces: pin the script_location to an absolute path so a test
    # invoked from a different cwd still finds the versions/ dir.
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


# In-memory shared SQLite — every connection in this process talks to the
# same DB. The standard ``sqlite:///:memory:`` URL gives each connection its
# own private DB, which breaks any test that uses more than one engine. The
# ``cache=shared`` form below shares state across connections within the
# process, which matches Postgres semantics closely enough for this test.
_TEST_DB_URL = "sqlite:///file::memory:?cache=shared&uri=true"


@pytest.fixture
def fresh_db_url(tmp_path: Path) -> str:
    """A fresh per-test SQLite file. Using a real on-disk file (rather than
    :memory:) avoids cross-connection visibility surprises and gives us a
    clean slate per test even if alembic.command opens its own connections.
    """
    db_path = tmp_path / "alembic_test.db"
    return f"sqlite:///{db_path}"


class TestAlembicMigrations:
    def test_upgrade_head_runs_cleanly(self, fresh_db_url: str) -> None:
        """``alembic upgrade head`` against an empty SQLite must not raise.

        This is the bare-minimum smoke test — if env.py imports break or the
        migration's op.* calls are malformed, this fails loudly.
        """
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "head")

        # Sanity: alembic_version is populated.
        engine = create_engine(fresh_db_url)
        inspector = inspect(engine)
        assert inspector.has_table("alembic_version"), (
            "alembic_version table missing after upgrade head — "
            "command silently no-opped"
        )

    def test_downgrade_base_rolls_back_cleanly(
        self, fresh_db_url: str
    ) -> None:
        """``upgrade head`` followed by ``downgrade base`` must leave only
        the alembic-managed bookkeeping table.

        This guards against partial downgrades — the kind that leave half a
        table behind and require manual SQL on prod to clean up.
        """
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        engine = create_engine(fresh_db_url)
        inspector = inspect(engine)
        remaining = set(inspector.get_table_names())
        # Alembic's own version table is the only acceptable leftover (it's
        # managed by the framework, not by our migration's downgrade()).
        assert remaining.issubset({"alembic_version"}), (
            f"downgrade base left tables behind: "
            f"{sorted(remaining - {'alembic_version'})}"
        )

    def test_migration_matches_models(self, fresh_db_url: str) -> None:
        """The set of tables created by ``upgrade head`` must equal the set
        declared on ``Base.metadata.tables``.

        This is the critical assertion. ``alembic check`` does the same
        column-level comparison but is harder to wire into pytest output;
        the table-set check below catches the most common drift mode
        (table added/removed in the model, migration not regenerated).
        """
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "head")

        engine = create_engine(fresh_db_url)
        inspector = inspect(engine)
        # Exclude alembic_version from the comparison: the framework owns it,
        # it's not in our models.
        actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
        expected_tables = set(Base.metadata.tables.keys())

        missing = expected_tables - actual_tables
        extra = actual_tables - expected_tables
        assert not missing and not extra, (
            f"Migration is out of sync with models. "
            f"Missing in DB: {sorted(missing)}. "
            f"Extra in DB: {sorted(extra)}. "
            f"Run `alembic revision --autogenerate -m '<change>'` "
            f"and review the result."
        )

    def test_upgrade_creates_expected_indexes(
        self, fresh_db_url: str
    ) -> None:
        """The model declares ``index=True`` / ``unique=True`` on a few
        columns; the migration must reproduce them. If autogenerate ever
        emits a migration without these we want to catch it here, not when
        prod auth queries start doing full-table scans.
        """
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "head")

        engine = create_engine(fresh_db_url)
        inspector = inspect(engine)

        # users.email: unique-indexed.
        users_indexes = {ix["name"] for ix in inspector.get_indexes("users")}
        assert "ix_users_email" in users_indexes

        # revoked_tokens.jti: unique-indexed.
        rt_indexes = {
            ix["name"] for ix in inspector.get_indexes("revoked_tokens")
        }
        assert "ix_revoked_tokens_jti" in rt_indexes
        assert "ix_revoked_tokens_user_id" in rt_indexes

    @pytest.mark.issue("ISS-637")
    def test_upgrade_then_check_reports_no_drift(
        self, fresh_db_url: str
    ) -> None:
        """After ``upgrade head``, ``alembic check`` must report no pending
        operations — i.e. the migration captures the models exactly.

        This is the strongest model-vs-migration assertion: it goes column
        by column, including types and server defaults (because env.py sets
        ``compare_type=True`` and ``compare_server_default=True``).

        ``alembic check`` raises ``alembic.util.exc.AutogenerateDiffsDetected``
        on drift; we let that propagate so the failure message lists the
        exact diff.

        ISS-637: as of migration 0040 the model still declares the unique
        index ``uq_workflow_runs_share_token`` on ``workflow_runs.share_token``
        but the migration chain does not create it, so ``alembic check``
        reports a pending ``remove_index`` operation against a fresh DB.
        """
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "head")
        # Will raise if drift is detected; pytest will surface the alembic
        # diff in the assertion error.
        command.check(cfg)
