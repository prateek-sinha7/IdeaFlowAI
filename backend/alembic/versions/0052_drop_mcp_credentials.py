"""Drop the unused ``mcp_credentials`` table (connectors, legacy runtime removal).

The per-owner MCP credential store (0017, 09-05 / MCP-02) lost its only reader
and writer when the legacy MCP pre-warm and ``ScopedStore.*_mcp_credential`` were
removed. Connector credentials live in the connector Token Vault (0053).

SANCTIONED DESTRUCTIVE DROP (the 0015 precedent), guarded:
  * Idempotent: a database without the table is a no-op.
  * Loud skip (the 0028 pattern): if the table still holds rows, log an ERROR
    with the row count and leave the table in place. The rows are encrypted
    per-owner secrets that cannot be recovered after a drop, so the migration
    never deletes them itself, and a populated database never crash-loops the
    container (``docker-entrypoint.sh`` runs ``alembic upgrade head`` under
    ``set -eu``). An operator removes the table by hand once the rows are
    confirmed unneeded.

``downgrade()`` recreates the 0017 shape, empty: the schema is reversible, the
data is not.
"""

import logging

import sqlalchemy as sa
from alembic import op

from migration_helpers import create_table_if_missing, drop_table_if_present, table_exists

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

_TABLE = "mcp_credentials"

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    if not table_exists(_TABLE):
        return
    row_count = op.get_bind().execute(sa.text(f"SELECT count(*) FROM {_TABLE}")).scalar_one()
    if row_count:
        logger.error(
            "0052: %s holds %d row(s); not dropping it. Review the rows and drop the "
            "table by hand once they are confirmed unneeded.",
            _TABLE,
            row_count,
        )
        return
    drop_table_if_present(_TABLE)


def downgrade() -> None:
    # Same shape as 0017 (empty).
    create_table_if_missing(
        _TABLE,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("server", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
