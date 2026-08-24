"""0034 — session-bound MFA proof timestamp for the admin-MFA gate.

P0 fix (COGNITO-AUTH-QA-BUGS.md "Admin MFA is Off by Default and
Bypassable"). The previous ``core.identity.enforce_admin_mfa`` asked Cognito
whether the ACCOUNT had ever confirmed an MFA factor (enrolment), not whether
the CURRENT bearer was minted from a session that actually completed the
challenge. That let an admin enroll a factor with their existing
password-only bearer (no reauthentication required by either enrolment
endpoint) and keep using that same bearer against every admin route.

``users.mfa_verified_at`` is stamped by ``api/auth.py::login_challenge`` only
when the just-answered challenge was a real MFA proof (SOFTWARE_TOKEN_MFA /
EMAIL_OTP) -- never by the enrolment endpoints. The gate compares a bearer's
``iat`` against this column instead of calling Cognito on the request path.

Nullable, additive: every existing row gets NULL (no historical session ever
proved MFA under the new contract), which correctly fails the gate for any
admin who hasn't logged in through a challenge since this shipped -- the
conservative direction for a security fix.

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("mfa_verified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("mfa_verified_at")
