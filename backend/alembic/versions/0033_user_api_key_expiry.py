"""0033 — expiry for user API keys.

Part of the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §7 Phase 6 item 5 — the Decision 7
follow-up). Machine identity (``X-Flowin-API-Key``) was deliberately left
untouched by the migration proper; this is the promised hardening.

Before this migration ``api_key_auth.py`` checked only ``revoked_at``, so a
minted key was valid FOREVER unless someone explicitly revoked it. A key pasted
into an IDE config in 2024 still authenticates today. That is the single
longest-lived credential in the system and it had no natural death.

``expires_at`` is nullable, and NULL means "never expires". Existing keys
therefore keep working exactly as before — this migration cannot break a live
integration. New keys get a default lifetime at mint time (see
``api_key_auth.DEFAULT_API_KEY_TTL_DAYS``); backfilling an expiry onto existing
keys is deliberately NOT done here, because silently expiring a credential an
operator is actively using is a worse outcome than a long-lived key they can
now see and rotate.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-05 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_api_keys") as b:
        b.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_api_keys") as b:
        b.drop_column("expires_at")
