"""0035 — make auth-critical timestamp columns timezone-aware.

Root-cause fix for a real bug: ``users.password_changed_at``,
``users.tokens_valid_from``, ``users.mfa_verified_at``, ``users.roles_synced_at``,
and ``revoked_tokens.revoked_at`` / ``revoked_tokens.expires_at`` were plain
``DateTime`` (no ``timezone=True``). On Postgres this maps to ``timestamp
without time zone``, so a write of an aware UTC ``datetime`` is silently
converted to the SESSION's timezone (``TimeZone`` GUC) and the offset is then
DROPPED. The app always reads these columns back through
``_coerce_to_aware_utc``, which reinterprets any naive value AS UTC. When the
DB session timezone is not UTC (e.g. a local Postgres install defaulting to
the OS timezone, such as ``Asia/Calcutta`` / +5:30), the round-trip silently
shifts every stamped instant by the session's UTC offset.

Concretely: a session in +5:30 writes ``tokens_valid_from = now_utc``, which
Postgres stores as ``now_utc + 5:30`` in local wall-clock (no offset kept).
The app then reads it back and treats that shifted value as if it WERE UTC —
so ``tokens_valid_from`` ends up 5.5 hours ahead of the real UTC instant. Any
token minted in that window has ``iat`` (real UTC) < the inflated
``tokens_valid_from``, so ``core.identity.is_revoked_by_token_validity``
rejects it as revoked -- e.g. every fresh login fails with "Token has been
revoked" for up to 5.5 hours after any password/role/tier write or MFA
challenge, purely as a function of the DB server's local timezone. This is
exactly the class of bug already fixed at the API-serialization boundary in
FIX-063 (KAN-113) for read-only display fields; this migration fixes it at
the SOURCE for the columns that feed security decisions (token revocation,
admin-MFA gating) rather than papering over it downstream again.

``DateTime(timezone=True)`` makes Postgres store ``timestamptz`` (UTC
internally, correct on any read regardless of session timezone) and makes
SQLite a no-op (SQLite has no native tz-aware storage either way; the ORM's
``_coerce_to_aware_utc`` guard stays as defense-in-depth for any pre-migration
row that was written naive/shifted under the bug).

Backfill: existing PRE-MIGRATION rows on Postgres are ALREADY wrong (a naive
local-time value with the offset gone -- there is no way to recover the
original UTC instant from the stored value alone, since the shift already
happened silently at the previous write). Rather than guess, this migration
casts each existing naive value to timestamptz AT the column's own historical
default (``AT TIME ZONE 'UTC'``), which is a no-op for any row that was in
fact written under a UTC-timezone session (the common/correct case) and is
honest about not being able to un-shift rows written under a non-UTC session
by a database that dropped the offset. Operators on a non-UTC local Postgres
who hit stale-revocation symptoms before this migration should re-run the
write path (e.g. re-login) to get a freshly-correct stamp post-migration.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

_USERS_COLUMNS = [
    "password_changed_at",
    "tokens_valid_from",
    "roles_synced_at",
    "mfa_verified_at",
    "created_at",
    "updated_at",
]
_REVOKED_TOKENS_COLUMNS = ["revoked_at", "expires_at"]


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if not is_postgres:
        # SQLite has no native tz-aware column type -- sqlite3/SQLAlchemy
        # already stores/returns naive datetimes regardless of the declared
        # type, and there is no session-timezone concept to shift against.
        # Nothing to migrate; the model-level type change is safe to apply
        # with zero DDL here (batch_alter_table would just rewrite the table
        # for no behavioural change).
        return

    for col in _USERS_COLUMNS:
        op.execute(
            f'ALTER TABLE users ALTER COLUMN {col} TYPE TIMESTAMPTZ '
            f"USING {col} AT TIME ZONE 'UTC'"
        )
    for col in _REVOKED_TOKENS_COLUMNS:
        op.execute(
            f'ALTER TABLE revoked_tokens ALTER COLUMN {col} TYPE TIMESTAMPTZ '
            f"USING {col} AT TIME ZONE 'UTC'"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if not is_postgres:
        return

    for col in _USERS_COLUMNS:
        op.execute(
            f'ALTER TABLE users ALTER COLUMN {col} TYPE TIMESTAMP '
            f"USING {col} AT TIME ZONE 'UTC'"
        )
    for col in _REVOKED_TOKENS_COLUMNS:
        op.execute(
            f'ALTER TABLE revoked_tokens ALTER COLUMN {col} TYPE TIMESTAMP '
            f"USING {col} AT TIME ZONE 'UTC'"
        )
