"""Migrations 0052 (drop ``mcp_credentials``) and 0053 (connector tables).

Two groups:

* ``TestMigration0052`` and the ``TestAlembicChain`` checks run offline on a
  file-backed SQLite database. The drop-or-skip decision and the revision chain are
  not dialect-specific.
* ``TestMigration0053Postgres`` is ``requires_postgres``: column nullability, server
  defaults, ``ON DELETE CASCADE`` and the index catalog are read back from a real
  PostgreSQL server (``PYTEST_POSTGRES_ADMIN_URL``, else the testcontainers server,
  which needs Docker). SQLite never stands in for them.

The existing ``test_alembic.py`` drift test and ``test_migration_idempotency.py``
ratchet also cover 0053.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from tests.integration.db.conftest import (
    alembic_config_for,
    postgres_admin_url,
    throwaway_database,
)

_TABLES = ("connector_connections", "oauth_states", "connector_audit_log")
_MCP_TABLE = "mcp_credentials"
_INSERT_MCP_ROW = text(
    "INSERT INTO mcp_credentials "
    "(id, owner_id, workspace_id, server, scope, encrypted_secret, created_at, updated_at) "
    "VALUES ('c1', 'o', 'w', 'github', NULL, 'ciphertext', '2026-01-01', '2026-01-01')"
)


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    """URL of an empty file-backed SQLite database unique to this test."""
    return f"sqlite:///{tmp_path / 'connectors_migration.db'}"


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


class TestMigration0052:
    def test_upgrade_drops_table_when_mcp_credentials_is_empty(self, sqlite_url: str):
        # Arrange
        cfg = alembic_config_for(sqlite_url)
        command.upgrade(cfg, "0051")
        assert _MCP_TABLE in _tables(sqlite_url)

        # Act
        command.upgrade(cfg, "0052")

        # Assert
        assert _MCP_TABLE not in _tables(sqlite_url)

    def test_upgrade_keeps_table_and_logs_error_when_rows_exist(
        self, sqlite_url: str, capfd: pytest.CaptureFixture[str]
    ):
        # Arrange
        cfg = alembic_config_for(sqlite_url)
        command.upgrade(cfg, "0051")
        engine = create_engine(sqlite_url)
        with engine.begin() as conn:
            conn.execute(_INSERT_MCP_ROW)
        engine.dispose()

        # Act
        command.upgrade(cfg, "0052")

        # Assert
        assert _MCP_TABLE in _tables(sqlite_url)
        engine = create_engine(sqlite_url)
        try:
            with engine.connect() as conn:
                assert (
                    conn.execute(
                        text("SELECT count(*) FROM mcp_credentials")
                    ).scalar_one()
                    == 1
                )
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
        finally:
            engine.dispose()
        assert version == "0052"
        logged = capfd.readouterr().err
        assert "ERROR" in logged
        assert "0052: mcp_credentials holds 1 row(s); not dropping it" in logged

    def test_upgrade_is_a_no_op_when_table_already_absent(self, sqlite_url: str):
        # Arrange
        cfg = alembic_config_for(sqlite_url)
        command.upgrade(cfg, "0052")
        command.stamp(cfg, "0051")

        # Act
        command.upgrade(cfg, "0052")

        # Assert
        assert _MCP_TABLE not in _tables(sqlite_url)

    def test_downgrade_recreates_empty_table_when_reverting(self, sqlite_url: str):
        # Arrange
        cfg = alembic_config_for(sqlite_url)
        command.upgrade(cfg, "0052")

        # Act
        command.downgrade(cfg, "0051")

        # Assert
        assert _MCP_TABLE in _tables(sqlite_url)
        engine = create_engine(sqlite_url)
        try:
            with engine.connect() as conn:
                assert (
                    conn.execute(
                        text("SELECT count(*) FROM mcp_credentials")
                    ).scalar_one()
                    == 0
                )
        finally:
            engine.dispose()


class TestMigration0053Offline:
    def test_upgrade_creates_three_tables_when_applied_over_0052(self, sqlite_url: str):
        # Arrange
        cfg = alembic_config_for(sqlite_url)
        command.upgrade(cfg, "0052")
        assert not set(_TABLES) & _tables(sqlite_url)

        # Act
        command.upgrade(cfg, "0053")

        # Assert
        assert set(_TABLES) <= _tables(sqlite_url)

    def test_downgrade_then_upgrade_is_clean_when_cycled(self, sqlite_url: str):
        # Arrange
        cfg = alembic_config_for(sqlite_url)
        command.upgrade(cfg, "0053")

        # Act
        command.downgrade(cfg, "0052")
        removed = set(_TABLES) & _tables(sqlite_url)
        command.upgrade(cfg, "0053")

        # Assert
        assert removed == set()
        assert set(_TABLES) <= _tables(sqlite_url)

    def test_upgrade_leaves_existing_rows_alone_when_connector_tables_added(
        self, sqlite_url: str
    ):
        # Arrange
        cfg = alembic_config_for(sqlite_url)
        command.upgrade(cfg, "0052")
        engine = create_engine(sqlite_url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, cognito_sub, tier, is_admin, created_at, updated_at) "
                    "VALUES ('u1', 'u1@example.com', 'sub-u1', 'basic', 0, '2026-01-01', '2026-01-01')"
                )
            )
        engine.dispose()

        # Act
        command.upgrade(cfg, "0053")

        # Assert
        engine = create_engine(sqlite_url)
        try:
            with engine.connect() as conn:
                assert (
                    conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
                )
        finally:
            engine.dispose()


class TestAlembicChain:
    @pytest.fixture
    def script_directory(self) -> ScriptDirectory:
        """Script directory for this repo's migrations (no database connection)."""
        return ScriptDirectory.from_config(alembic_config_for("postgresql://unused"))

    def test_chain_has_single_head_when_connector_migrations_added(
        self, script_directory: ScriptDirectory
    ):
        # Act
        heads = script_directory.get_heads()

        # Assert
        assert len(heads) == 1, f"expected one alembic head, found {heads}"

    @pytest.mark.parametrize(
        ("revision", "parent"), [("0052", "0051"), ("0053", "0052")]
    )
    def test_revision_follows_its_parent_when_chain_is_loaded(
        self, script_directory: ScriptDirectory, revision: str, parent: str
    ):
        # Act
        loaded = script_directory.get_revision(revision)

        # Assert
        assert loaded is not None
        assert loaded.down_revision == parent

    def test_0053_is_in_head_ancestry_when_chain_is_walked(
        self, script_directory: ScriptDirectory
    ):
        # Act
        walked = [rev.revision for rev in script_directory.walk_revisions()]

        # Assert
        assert "0053" in walked


@pytest.mark.requires_postgres
class TestMigration0053Postgres:
    @pytest.fixture
    def pg_url(self, request: pytest.FixtureRequest) -> Generator[str, None, None]:
        """A private empty PostgreSQL database; dropped afterwards."""
        with throwaway_database(postgres_admin_url(request), "conn0053mig") as url:
            yield url

    @pytest.fixture
    def pg_engine(self, pg_url: str) -> Generator[Engine, None, None]:
        """Engine on a database taken to 0053."""
        command.upgrade(alembic_config_for(pg_url), "0053")
        engine = create_engine(pg_url)
        try:
            yield engine
        finally:
            engine.dispose()

    def test_upgrade_creates_exact_columns_when_applied(self, pg_engine: Engine):
        # Act
        inspector = inspect(pg_engine)
        columns = {t: {c["name"]: c for c in inspector.get_columns(t)} for t in _TABLES}

        # Assert
        assert set(columns["connector_connections"]) == {
            "id", "user_id", "connector_key", "status", "provider_account_id",
            "provider_account_login", "provider_account_name", "granted_scopes",
            "provider_metadata", "access_token_ciphertext", "refresh_token_ciphertext",
            "access_token_expires_at", "refresh_token_expires_at", "token_version",
            "last_refreshed_at", "last_error_code", "created_at", "updated_at",
        }  # fmt: skip
        assert set(columns["oauth_states"]) == {
            "id", "user_id", "connector_key", "state_hash", "code_verifier_ciphertext",
            "redirect_uri", "created_at", "expires_at", "consumed_at",
        }  # fmt: skip
        assert set(columns["connector_audit_log"]) == {
            "id", "user_id", "connector_key", "action", "outcome", "error_code",
            "tool_name", "run_id", "agent_ref", "duration_ms", "created_at",
        }  # fmt: skip
        for table in _TABLES:
            assert "owner_id" not in columns[table]
            assert "workspace_id" not in columns[table]

    def test_upgrade_sets_nullability_and_version_default_when_applied(
        self, pg_engine: Engine
    ):
        # Act
        inspector = inspect(pg_engine)
        conn_cols = {
            c["name"]: c for c in inspector.get_columns("connector_connections")
        }
        state_cols = {c["name"]: c for c in inspector.get_columns("oauth_states")}
        audit_cols = {
            c["name"]: c for c in inspector.get_columns("connector_audit_log")
        }

        # Assert
        for name in ("user_id", "connector_key", "status", "provider_account_id",
                     "granted_scopes", "access_token_ciphertext", "token_version"):  # fmt: skip
            assert not conn_cols[name]["nullable"], name
        for name in ("refresh_token_ciphertext", "access_token_expires_at",
                     "provider_metadata", "provider_account_login", "last_error_code"):  # fmt: skip
            assert conn_cols[name]["nullable"], name
        assert "1" in str(conn_cols["token_version"]["default"])
        assert not state_cols["state_hash"]["nullable"]
        assert state_cols["consumed_at"]["nullable"]
        assert audit_cols["run_id"]["nullable"] and audit_cols["tool_name"]["nullable"]

    def test_upgrade_cascades_user_foreign_keys_and_leaves_run_id_unlinked_when_applied(
        self, pg_engine: Engine
    ):
        # Act
        inspector = inspect(pg_engine)

        # Assert
        for table in _TABLES:
            (fk,) = inspector.get_foreign_keys(table)
            assert fk["referred_table"] == "users"
            assert fk["constrained_columns"] == ["user_id"]
            assert fk["options"].get("ondelete") == "CASCADE"

    def test_upgrade_creates_unique_constraints_and_indexes_when_applied(
        self, pg_engine: Engine
    ):
        # Act
        inspector = inspect(pg_engine)
        uniques = {
            t: {
                u["name"]: u["column_names"]
                for u in inspector.get_unique_constraints(t)
            }
            for t in ("connector_connections", "oauth_states")
        }
        indexes = {
            t: {i["name"]: i["column_names"] for i in inspector.get_indexes(t)}
            for t in _TABLES
        }

        # Assert
        assert uniques["connector_connections"]["uq_connector_connections_user_connector"] == [
            "user_id", "connector_key",
        ]  # fmt: skip
        assert uniques["oauth_states"]["uq_oauth_states_state_hash"] == ["state_hash"]
        assert indexes["connector_connections"]["ix_connector_connections_user"] == [
            "user_id"
        ]
        assert indexes["oauth_states"]["ix_oauth_states_user_expires"] == [
            "user_id",
            "expires_at",
        ]
        assert indexes["oauth_states"]["ix_oauth_states_expires"] == ["expires_at"]
        assert indexes["connector_audit_log"]["ix_connector_audit_user_created"] == [
            "user_id", "created_at",
        ]  # fmt: skip
        assert indexes["connector_audit_log"]["ix_connector_audit_run"] == ["run_id"]

    def test_downgrade_drops_tables_and_indexes_cleanly_when_reverting_to_0052(
        self, pg_url: str
    ):
        # Arrange
        cfg = alembic_config_for(pg_url)
        command.upgrade(cfg, "0053")

        # Act
        command.downgrade(cfg, "0052")
        command.upgrade(cfg, "0053")
        command.downgrade(cfg, "0052")

        # Assert
        engine = create_engine(pg_url)
        try:
            remaining = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                leftovers = conn.execute(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() "
                        "AND (indexname LIKE 'ix_connector_%' OR indexname LIKE '%oauth_states%')"
                    )
                ).all()
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
        finally:
            engine.dispose()
        assert not set(_TABLES) & remaining
        assert leftovers == []
        assert version == "0052"

    def test_0052_drops_empty_table_and_skips_with_error_when_row_exists_on_postgres(
        self, pg_url: str, capfd: pytest.CaptureFixture[str]
    ):
        # Arrange
        cfg = alembic_config_for(pg_url)
        command.upgrade(cfg, "0051")
        engine = create_engine(pg_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO mcp_credentials "
                        "(id, owner_id, workspace_id, server, scope, encrypted_secret, created_at, updated_at) "
                        "VALUES ('c1', 'o', 'w', 'github', NULL, 'ciphertext', now(), now())"
                    )
                )

            # Act
            command.upgrade(cfg, "0052")

            # Assert
            assert _MCP_TABLE in set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        logged = capfd.readouterr().err
        assert "ERROR" in logged and "not dropping" in logged
