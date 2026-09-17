"""Migration 0038 pre-flight test (Cognito-only auth migration Phase 6 checklist
item: "migration pre-flight aborts on dirty data").

Phase 0's inventory (``.kiro/specs/login/prompt.md``) flagged that no
environment had cut over to Cognito yet and that the database could still
contain local-auth rows from earlier dev/test runs. Migration
``0038_cognito_only_users`` guards against exactly that by raising
``RuntimeError`` and refusing to apply if any ``users`` row is not cleanly
Cognito-linked, rather than silently corrupting it under the new NOT NULL
``cognito_sub`` constraint or the dropped ``password_hash``/``auth_provider``
columns.

This exercises ``upgrade()`` itself — via a REAL ``alembic upgrade`` through
0037 -> 0038, exactly as ``docker-entrypoint.sh`` invokes it in production
(``command.upgrade``, not a direct import-and-call of ``_preflight()``) — so
what is proven is "the migration, run for real, aborts on dirty data",
matching ``test_migration_0014.py``'s own convention for this kind of test.
Three dirty-data shapes are tested separately (one per pre-flight check), plus
the clean-data happy path to prove the guard does not false-positive on a
cleanly cut-over database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.unit._load_migration_0038 import load_migration_0038


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def _make_config(db_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture
def fresh_db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "migration_0038_test.db"
    return f"sqlite:///{db_path}"


def _insert_user_at_0037(
    db_url: str,
    *,
    user_id: str | None = None,
    email: str,
    cognito_sub: str | None,
    auth_provider: str = "cognito",
) -> str:
    """Insert one ``users`` row via raw SQL against the 0037 schema shape.

    Raw SQL, not the ORM, deliberately: the ORM model reflects the CURRENT
    (post-0038) shape, which no longer has ``password_hash``/``auth_provider``
    and requires ``cognito_sub`` NOT NULL -- exactly the columns this test
    needs to seed dirty values into before 0038 removes them.
    """
    user_id = user_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users "
                "(id, email, password_hash, tier, is_admin, auth_provider, "
                "cognito_sub, created_at, updated_at) VALUES "
                "(:id, :email, NULL, 'basic', 0, :auth_provider, :sub, :now, :now)"
            ),
            {
                "id": user_id,
                "email": email,
                "auth_provider": auth_provider,
                "sub": cognito_sub,
                "now": now,
            },
        )
    engine.dispose()
    return user_id


class TestPreflightAbortsOnDirtyData:
    def test_a_null_cognito_sub_row_aborts_the_migration(self, fresh_db_url: str) -> None:
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "0037")
        bad_id = _insert_user_at_0037(
            fresh_db_url, email="unlinked@example.com", cognito_sub=None
        )

        with pytest.raises(RuntimeError) as exc_info:
            command.upgrade(cfg, "0038")

        message = str(exc_info.value)
        assert "cognito_sub IS NULL" in message
        assert bad_id in message
        assert "unlinked@example.com" in message

        # The migration must not have partially applied -- still at 0037.
        engine = create_engine(fresh_db_url)
        with engine.connect() as conn:
            current = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        engine.dispose()
        assert current == "0037"

    def test_a_duplicated_cognito_sub_aborts_the_migration(self, fresh_db_url: str) -> None:
        """``uq_users_cognito_sub`` (migration 0031) already blocks a true
        SQL-level duplicate on any normal insert path in THIS database --
        proven unable to seed the scenario through a real ``alembic upgrade``
        (SQLite refuses to drop an index tied to a live unique constraint,
        even deliberately, in a test). So this check only matters as
        defense-in-depth for a state this database's own constraint cannot
        produce: a restored backup from before migration 0031 ever ran, or a
        row inserted by raw SQL/replication that bypassed the ORM/constraint
        entirely. Exercises ``_preflight`` directly (not through
        ``alembic upgrade``) against a bare table with no unique index at
        all, matching that scenario precisely."""
        migration = load_migration_0038()
        engine = create_engine(fresh_db_url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE users (id VARCHAR PRIMARY KEY, email VARCHAR, "
                    "cognito_sub VARCHAR)"
                )
            )
            shared_sub = "sub-collision-1"
            conn.execute(
                text("INSERT INTO users VALUES ('id-1', 'first@example.com', :sub)"),
                {"sub": shared_sub},
            )
            conn.execute(
                text("INSERT INTO users VALUES ('id-2', 'second@example.com', :sub)"),
                {"sub": shared_sub},
            )

        with engine.begin() as conn:
            with pytest.raises(RuntimeError) as exc_info:
                migration._preflight(conn)

        engine.dispose()
        assert "duplicated cognito_sub" in str(exc_info.value)
        assert shared_sub in str(exc_info.value)

    def test_a_non_cognito_auth_provider_row_aborts_the_migration(
        self, fresh_db_url: str
    ) -> None:
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "0037")
        local_id = _insert_user_at_0037(
            fresh_db_url,
            email="local-admin@example.com",
            cognito_sub="sub-local-admin",
            auth_provider="local",
        )

        with pytest.raises(RuntimeError) as exc_info:
            command.upgrade(cfg, "0038")

        message = str(exc_info.value)
        assert "not auth_provider='cognito'" in message
        assert local_id in message
        assert "local-admin@example.com" in message

    def test_every_violation_is_listed_in_one_error_not_just_the_first(
        self, fresh_db_url: str
    ) -> None:
        """The pre-flight accumulates every problem before raising once
        (``_preflight``'s own docstring: "so an operator sees the full
        picture in one migration attempt rather than fixing one row at a
        time") -- proves that by tripping TWO checks simultaneously and
        asserting both appear in the single raised message."""
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "0037")
        _insert_user_at_0037(fresh_db_url, email="unlinked@example.com", cognito_sub=None)
        _insert_user_at_0037(
            fresh_db_url,
            email="local-admin@example.com",
            cognito_sub="sub-local-admin",
            auth_provider="local",
        )

        with pytest.raises(RuntimeError) as exc_info:
            command.upgrade(cfg, "0038")

        message = str(exc_info.value)
        assert "cognito_sub IS NULL" in message
        assert "not auth_provider='cognito'" in message


class TestPreflightPassesOnCleanData:
    def test_upgrade_succeeds_when_every_row_is_cleanly_cognito_linked(
        self, fresh_db_url: str
    ) -> None:
        """The guard must not false-positive on the state a real cutover
        actually produces: every row has a unique non-null cognito_sub and
        auth_provider == 'cognito'."""
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "0037")
        _insert_user_at_0037(
            fresh_db_url, email="clean-1@example.com", cognito_sub="sub-clean-1"
        )
        _insert_user_at_0037(
            fresh_db_url, email="clean-2@example.com", cognito_sub="sub-clean-2"
        )

        command.upgrade(cfg, "0038")

        engine = create_engine(fresh_db_url)
        with engine.connect() as conn:
            current = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
            }
        engine.dispose()
        assert current == "0038"
        assert "password_hash" not in cols
        assert "auth_provider" not in cols
        assert "status" in cols

    def test_upgrade_succeeds_on_an_empty_users_table(self, fresh_db_url: str) -> None:
        """A brand-new environment (Decision 5's default assumption: no
        existing users) is not dirty data -- zero rows trivially satisfies
        every pre-flight check."""
        cfg = _make_config(fresh_db_url)
        command.upgrade(cfg, "0037")

        command.upgrade(cfg, "0038")

        engine = create_engine(fresh_db_url)
        with engine.connect() as conn:
            current = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        engine.dispose()
        assert current == "0038"
