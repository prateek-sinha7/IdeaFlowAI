"""Alembic environment for Flowin.

The DB URL comes from ``app.core.config.settings.DATABASE_URL`` so dev/prod
share a single source of truth (the same env file uvicorn boots from). Tests
override this by setting ``sqlalchemy.url`` on the ``Config`` object before
calling ``alembic.command.upgrade(...)``.

``target_metadata = Base.metadata`` — importing :mod:`app.models` (via the
package ``__init__``) eagerly registers every model class on ``Base``, which
is what makes ``alembic revision --autogenerate`` see them.

``compare_type`` and ``compare_server_default`` are both on so autogenerate
catches column-type changes (e.g. ``String(50)`` → ``String(255)``) and
default-value drifts. Without these, alembic only diffs the *set* of columns,
not their definitions.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Make ``app.*`` importable regardless of where alembic is invoked from.
#
# When operators run ``alembic upgrade head`` from /opt/flowin/backend that's
# already on sys.path; when pytest invokes it programmatically it isn't. We
# canonicalise on the directory that contains this env.py's parent (= backend/).
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings  # noqa: E402  (deliberate post-sys.path)
from app.models.database import Base  # noqa: E402

# Side-effect import: makes every model class register itself on Base.metadata.
# Without this, autogenerate would emit an empty migration. Listed under
# ``noqa`` because the names are imported for their side-effect only.
import app.models  # noqa: E402, F401


# Alembic Config object — backed by alembic.ini.
config = context.config

# Set up Python logging from alembic.ini's [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Resolve the DB URL.
#
# Precedence:
#   1. ``sqlalchemy.url`` already set on the Config — used by tests that
#      programmatically build a Config and call ``upgrade(..., "head")``.
#   2. ``settings.DATABASE_URL`` — the runtime / production path.
#
# We intentionally do NOT honour any value baked into alembic.ini's
# ``[alembic] sqlalchemy.url`` slot via the file (we leave it blank). That
# stops dev/prod from silently using a stale, hardcoded URL.
# ---------------------------------------------------------------------------
_existing_url = config.get_main_option("sqlalchemy.url")
if not _existing_url:
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


target_metadata = Base.metadata


def _render_item(type_, obj, autogen_context):  # pragma: no cover - hook stub
    """Hook for custom autogenerate rendering. Returning ``False`` lets
    alembic fall back to its default. Kept as an extension point for any
    future Postgres-specific types we add (JSONB, ENUM, …)."""
    return False


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and emits SQL to stdout
    instead of executing it — useful for generating a migration script the
    DBA can review before running against production.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_item=_render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection.

    If the caller already attached an engine via ``config.attributes
    ['connection']`` (the standard pattern for tests / multi-tenant setups),
    we reuse that. Otherwise we build a fresh engine from ``sqlalchemy.url``.
    """
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    if hasattr(connectable, "connect"):
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
                render_item=_render_item,
            )

            with context.begin_transaction():
                context.run_migrations()
    else:
        # Already a Connection (e.g. injected by a test that wants to run
        # multiple migrations inside one transaction).
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_item=_render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
