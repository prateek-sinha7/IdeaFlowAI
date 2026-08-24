"""0032 — encrypted Cognito refresh-token storage on users.

Part of the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §7 Phase 3). The frontend's silent-
refresh contract (``useRunStream.ts::attemptSilentRefresh``) POSTs only the
current ACCESS token to ``/api/auth/refresh`` -- it never holds or sends a
Cognito refresh token (Decision 3: the ``getToken()``/``setToken()`` seam is
unchanged, so the browser only ever carries one bearer value). For
``POST /api/auth/refresh`` to call Cognito's ``REFRESH_TOKEN_AUTH`` flow, the
backend must therefore hold the user's refresh token itself, persisted
server-side after every successful login.

Encrypted at rest with the SAME Fernet/HKDF scheme already used for GitHub
PATs (``core/crypto.py``) -- a distinct HKDF info string
(``flowin-cognito-refresh-v1``) keeps this key materially independent of the
PAT key even though both derive from ``SECRET_KEY``, so a PAT-key compromise
does not also expose refresh tokens (or vice versa).

Additive-only (Q3, INV-3): one nullable column, no existing column touched.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-05 00:05:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(
            sa.Column("encrypted_cognito_refresh_token", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("encrypted_cognito_refresh_token")
