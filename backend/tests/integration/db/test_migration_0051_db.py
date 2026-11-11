"""Migration 0051 (AI Workflow Builder tables) against real PostgreSQL.

Covers Req 24.6, 24.8 and 48.7: the three ``workflow_builder_*`` tables and their
columns, the keyset index on the session list, the two partial unique indexes on
messages (read back from the catalog, predicate included), the two unique
constraints, ``ON DELETE SET NULL`` on ``sessions.workflow_id``, a clean
downgrade, and a single Alembic head that contains 0051.

Database: real PostgreSQL, never SQLite (partial-index predicates and
``ON DELETE`` actions are the point of this file). The server comes from one of:

* ``PYTEST_POSTGRES_ADMIN_URL``: a server-level SQLAlchemy URL.
* otherwise the shared testcontainers-backed ``database_url`` fixture from
  ``tests/integration/conftest.py`` (needs Docker, errors loudly without it).

Either way each test module/function gets its own uniquely named throwaway
database, so the chain is applied from an empty schema up to ``0050`` and the
``Base.metadata.create_all`` done by the shared ``engine`` fixture never leaks in.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url

from tests.integration.db.conftest import alembic_config_for

_TABLES = (
    "workflow_builder_sessions",
    "workflow_builder_messages",
    "workflow_builder_drafts",
)

_SESSIONS = "workflow_builder_sessions"
_MESSAGES = "workflow_builder_messages"
_DRAFTS = "workflow_builder_drafts"

# Columns that must be NOT NULL, per table.
_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    _SESSIONS: frozenset(
        {
            "id",
            "user_id",
            "owner_id",
            "workspace_id",
            "title",
            "mode",
            "target_trust",
            "skill_hash",
            "next_seq",
            "turn_count",
            "clarify_turns_without_draft",
            "created_at",
            "updated_at",
        }
    ),
    _MESSAGES: frozenset(
        {
            "id",
            "session_id",
            "user_id",
            "owner_id",
            "workspace_id",
            "seq",
            "role",
            "turn_id",
            "status",
            "content",
            "created_at",
        }
    ),
    _DRAFTS: frozenset(
        {
            "id",
            "session_id",
            "user_id",
            "owner_id",
            "workspace_id",
            "revision",
            "kind",
            "manifest",
            "manifest_hash",
            "created_at",
        }
    ),
}

# Columns that must be nullable, per table.
_OPTIONAL_COLUMNS: dict[str, frozenset[str]] = {
    _SESSIONS: frozenset(
        {
            "workflow_id",
            "linked_manifest_hash",
            "model_id",
            "effort",
            "first_accepted_revision",
            "summary_text",
            "summary_through_seq",
        }
    ),
    _MESSAGES: frozenset(
        {
            "reply_to_message_id",
            "outcome",
            "stop_reason",
            "error_code",
            "thinking",
            "canvas_state",
            "client_message_id",
            "model_id",
            "effort",
            "skill_hash",
            "prompt_version",
            "usage",
            "adherence",
            "tool",
            "revision",
            "started_at",
            "ended_at",
        }
    ),
    _DRAFTS: frozenset(
        {
            "target_trust",
            "change_summary",
            "launch_needs",
            "source_turn_id",
            "source_file",
            "undo_of_revision",
        }
    ),
}

_CAST_RE = re.compile(r"::(?:character varying|varchar|text)")


@dataclass(frozen=True)
class MigratedDatabase:
    """A throwaway database taken to 0050, then 0051."""

    url: str
    tables_at_0050: frozenset[str]


def _admin_url(request: pytest.FixtureRequest) -> str:
    """Server-level URL: the env override, else the shared testcontainers server."""
    override = os.environ.get("PYTEST_POSTGRES_ADMIN_URL")
    if override:
        return override
    return str(request.getfixturevalue("database_url"))


@contextmanager
def _throwaway_database(admin_url: str) -> Generator[str, None, None]:
    """Create an empty, uniquely named database on the server; drop it afterwards."""
    db_name = f"wb0051_{uuid.uuid4().hex[:12]}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        try:
            yield (
                make_url(admin_url)
                .set(database=db_name)
                .render_as_string(hide_password=False)
            )
        finally:
            with admin_engine.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="module")
def migrated_db(
    request: pytest.FixtureRequest,
) -> Generator[MigratedDatabase, None, None]:
    """Empty Postgres database upgraded to 0050, then to 0051 (read-only for tests)."""
    with _throwaway_database(_admin_url(request)) as url:
        cfg = alembic_config_for(url)
        command.upgrade(cfg, "0050")
        engine = create_engine(url)
        try:
            tables_at_0050 = frozenset(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        command.upgrade(cfg, "0051")
        yield MigratedDatabase(url=url, tables_at_0050=tables_at_0050)


@pytest.fixture
def migrated_engine(migrated_db: MigratedDatabase) -> Generator[Engine, None, None]:
    """Engine on the shared 0051 database; disposed after each test."""
    engine = create_engine(migrated_db.url)
    yield engine
    engine.dispose()


@pytest.fixture
def new_throwaway_url(
    request: pytest.FixtureRequest,
) -> Generator[str, None, None]:
    """URL of a private empty Postgres database, for tests that mutate the schema."""
    with _throwaway_database(_admin_url(request)) as url:
        yield url


def _normalise_predicate(indexdef: str) -> str:
    """Lower-cased WHERE clause of a ``pg_indexes.indexdef`` with casts/parens/space removed.

    PostgreSQL re-renders predicates (``(role)::text = 'assistant'::text``), so the
    comparison is on a canonical form rather than the literal migration text.
    """
    _, sep, predicate = indexdef.partition(" WHERE ")
    assert sep, f"index has no WHERE predicate: {indexdef}"
    stripped = _CAST_RE.sub("", predicate)
    return re.sub(r"[\s()]", "", stripped).lower()


def _indexdef(engine: Engine, table: str, index: str) -> str:
    """``pg_indexes.indexdef`` for one index; fails the test when it is absent."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = :table AND indexname = :index"
            ),
            {"table": table, "index": index},
        ).scalar_one_or_none()
    assert row is not None, f"index {index} missing on {table}"
    return str(row)


class TestUpgrade0051Tables:
    def test_upgrade_creates_three_tables_when_applied_over_0050(
        self, migrated_db: MigratedDatabase, migrated_engine: Engine
    ) -> None:
        assert not set(_TABLES) & migrated_db.tables_at_0050
        assert set(_TABLES) <= set(inspect(migrated_engine).get_table_names())

    @pytest.mark.parametrize("table", _TABLES)
    def test_upgrade_creates_exact_columns_when_applied_over_0050(
        self, migrated_engine: Engine, table: str
    ) -> None:
        columns = {c["name"]: c for c in inspect(migrated_engine).get_columns(table)}

        required = _REQUIRED_COLUMNS[table]
        optional = _OPTIONAL_COLUMNS[table]
        assert set(columns) == required | optional
        assert all(not columns[name]["nullable"] for name in required)
        assert all(columns[name]["nullable"] for name in optional)

    @pytest.mark.parametrize("table", _TABLES)
    def test_upgrade_adds_owner_and_workspace_columns_when_applied_over_0050(
        self, migrated_engine: Engine, table: str
    ) -> None:
        names = {c["name"] for c in inspect(migrated_engine).get_columns(table)}

        assert {"owner_id", "workspace_id", "user_id"} <= names

    def test_upgrade_sets_server_defaults_when_applied_over_0050(
        self, migrated_engine: Engine
    ) -> None:
        columns = {
            c["name"]: c
            for c in inspect(migrated_engine).get_columns(_SESSIONS)
            if c["name"] in {"target_trust", "next_seq", "turn_count"}
        }

        assert "user" in str(columns["target_trust"]["default"])
        assert "1" in str(columns["next_seq"]["default"])
        assert "0" in str(columns["turn_count"]["default"])


class TestUpgrade0051Indexes:
    def test_upgrade_creates_session_list_index_when_applied_over_0050(
        self, migrated_engine: Engine
    ) -> None:
        indexdef = _indexdef(migrated_engine, _SESSIONS, "ix_wb_sessions_user_updated")

        assert "UNIQUE" not in indexdef
        assert "user_id,updated_atdesc,id" in re.sub(r"\s", "", indexdef).lower()

    def test_upgrade_creates_partial_unique_client_id_index_when_applied_over_0050(
        self, migrated_engine: Engine
    ) -> None:
        indexdef = _indexdef(migrated_engine, _MESSAGES, "uq_wb_messages_client_id")

        assert "CREATE UNIQUE INDEX" in indexdef
        assert "(session_id, client_message_id)" in indexdef
        assert _normalise_predicate(indexdef) == "client_message_idisnotnull"

    def test_upgrade_creates_partial_unique_one_running_index_when_applied_over_0050(
        self, migrated_engine: Engine
    ) -> None:
        indexdef = _indexdef(migrated_engine, _MESSAGES, "uq_wb_messages_one_running")

        assert "CREATE UNIQUE INDEX" in indexdef
        assert "(session_id)" in indexdef
        assert _normalise_predicate(indexdef) == "role='assistant'andstatus='running'"

    @pytest.mark.parametrize(
        "index", ["ix_wb_messages_user_role_created", "ix_wb_messages_turn"]
    )
    def test_upgrade_creates_plain_message_index_when_applied_over_0050(
        self, migrated_engine: Engine, index: str
    ) -> None:
        indexdef = _indexdef(migrated_engine, _MESSAGES, index)

        assert "UNIQUE" not in indexdef
        assert " WHERE " not in indexdef

    @pytest.mark.parametrize(
        ("table", "constraint", "columns"),
        [
            (_MESSAGES, "uq_wb_messages_session_seq", ["session_id", "seq"]),
            (_DRAFTS, "uq_wb_drafts_session_revision", ["session_id", "revision"]),
        ],
    )
    def test_upgrade_creates_unique_constraint_when_applied_over_0050(
        self,
        migrated_engine: Engine,
        table: str,
        constraint: str,
        columns: list[str],
    ) -> None:
        uniques = {
            u["name"]: u["column_names"]
            for u in inspect(migrated_engine).get_unique_constraints(table)
        }

        assert uniques.get(constraint) == columns


class TestUpgrade0051ForeignKeys:
    def test_upgrade_sets_null_on_workflow_delete_when_applied_over_0050(
        self, migrated_engine: Engine
    ) -> None:
        fks = inspect(migrated_engine).get_foreign_keys(_SESSIONS)

        workflow_fk = next(
            fk for fk in fks if fk["constrained_columns"] == ["workflow_id"]
        )
        assert workflow_fk["referred_table"] == "workflows"
        assert workflow_fk["referred_columns"] == ["id"]
        assert workflow_fk["options"].get("ondelete") == "SET NULL"

    def test_upgrade_links_user_without_cascade_when_applied_over_0050(
        self, migrated_engine: Engine
    ) -> None:
        fks = inspect(migrated_engine).get_foreign_keys(_SESSIONS)

        user_fk = next(fk for fk in fks if fk["constrained_columns"] == ["user_id"])
        assert user_fk["referred_table"] == "users"
        assert user_fk["options"].get("ondelete") is None

    @pytest.mark.parametrize("table", [_MESSAGES, _DRAFTS])
    def test_upgrade_links_session_without_cascade_when_applied_over_0050(
        self, migrated_engine: Engine, table: str
    ) -> None:
        fks = inspect(migrated_engine).get_foreign_keys(table)

        session_fk = next(
            fk for fk in fks if fk["constrained_columns"] == ["session_id"]
        )
        assert session_fk["referred_table"] == _SESSIONS
        assert session_fk["options"].get("ondelete") is None


class TestDowngrade0051:
    def test_downgrade_drops_tables_cleanly_when_reverting_to_0050(
        self, new_throwaway_url: str
    ) -> None:
        cfg = alembic_config_for(new_throwaway_url)
        command.upgrade(cfg, "0051")

        command.downgrade(cfg, "0050")

        engine = create_engine(new_throwaway_url)
        try:
            remaining = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                leftover_indexes = conn.execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE schemaname = current_schema() "
                        "AND (indexname LIKE 'uq_wb_%' OR indexname LIKE 'ix_wb_%')"
                    )
                ).all()
        finally:
            engine.dispose()
        assert not set(_TABLES) & remaining
        assert version == "0050"
        assert leftover_indexes == []

    def test_upgrade_recreates_tables_when_reapplied_after_downgrade(
        self, new_throwaway_url: str
    ) -> None:
        cfg = alembic_config_for(new_throwaway_url)
        command.upgrade(cfg, "0051")
        command.downgrade(cfg, "0050")

        command.upgrade(cfg, "0051")

        engine = create_engine(new_throwaway_url)
        try:
            assert set(_TABLES) <= set(inspect(engine).get_table_names())
        finally:
            engine.dispose()


class TestAlembicHeads:
    """Pure script-directory checks: no database, so these run without Docker."""

    @pytest.fixture
    def script_directory(self) -> ScriptDirectory:
        """Script directory for this repo's migrations (no DB connection is made)."""
        return ScriptDirectory.from_config(alembic_config_for("postgresql://unused"))

    def test_heads_has_single_head_when_chain_includes_0051(
        self, script_directory: ScriptDirectory
    ) -> None:
        heads = script_directory.get_heads()

        assert len(heads) == 1, f"expected one alembic head, found {heads}"

    def test_0051_is_in_head_ancestry_when_chain_is_walked(
        self, script_directory: ScriptDirectory
    ) -> None:
        walked = [rev.revision for rev in script_directory.walk_revisions()]

        assert "0051" in walked

    def test_0051_follows_0050_when_revision_is_loaded(
        self, script_directory: ScriptDirectory
    ) -> None:
        revision = script_directory.get_revision("0051")

        assert revision is not None
        assert revision.down_revision == "0050"
