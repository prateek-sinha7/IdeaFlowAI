"""Backfill ``user_api_keys.expires_at`` for legacy never-expiring keys.

Part of the Cognito-only auth migration (``.kiro/specs/login/prompt.md``
Phase 2): *"Legacy ``NULL``-expiry API keys: backfill ``expires_at =
created_at + 90 days`` in ``0038`` or a dedicated migration (choose and
document)."*

**Choice: a dedicated migration, not folded into 0038.** Two reasons, both about
being able to reason about it afterwards:

1. ``0038`` is a STRUCTURAL migration with a fail-closed pre-flight: it refuses
   to run at all if the ``users`` table holds rows that are not Cognito-native.
   This is a pure DATA backfill on an unrelated table with no such gate. Merging
   them would mean a dirty ``users`` table blocked an API-key fix that has nothing
   to do with it, and that an operator who needed to reason about "did the expiry
   backfill run?" had to reason about the user pre-flight to answer.
2. They are reversible on different terms. ``0038``'s downgrade is explicitly
   unsupported (password hashes are gone for good). This one downgrades cleanly
   and exactly, because it records nothing it cannot put back — see
   :func:`downgrade`.

Why the backfill is needed
--------------------------
Migration ``0033`` added ``expires_at`` and left it NULLABLE on purpose, with
NULL meaning "never expires", so keys minted before the column existed kept
working and a live IDE/MCP integration could not be broken by a deploy. That was
the right call then and it leaves exactly one loose end: those keys are
permanently exempt from the 90-day TTL
(``api_key_auth.DEFAULT_API_KEY_TTL_DAYS``) that every key minted since has
carried. ``UserApiKey.is_expired()`` returns ``False`` for them by construction.

They are also the highest-risk credential in the system to leave unbounded: a
paste-once token, typically stored in an IDE config on a developer's machine, with
no natural death and no rotation prompt. Phase 2 closed the OTHER half of this
(the MCP transport was not even checking ``expires_at``); this closes the half
where there was nothing to check.

``created_at + 90 days`` -- deliberately in the past for most rows
-----------------------------------------------------------------
The stamp is computed from each key's OWN ``created_at``, not from "now". For any
legacy key older than 90 days that puts ``expires_at`` in the past, so the key
stops working at the next request. That is the intended outcome, not an oversight:
these keys have ALREADY outlived the policy, and stamping them 90 days from today
would instead grant every stale credential a fresh quarter of life — rewarding
the ones that have been sitting unrotated the longest.

**Operator action required.** This will break in-place IDE/MCP integrations using
pre-0033 keys, with a uniform 401 (indistinguishable from an unknown key, by
design — see ``api_key_auth.resolve_api_key``). Affected users mint a new key from
the settings page. The count of rows this touches is logged below so the blast
radius is known before, not after: run ``SELECT count(*) FROM user_api_keys WHERE
expires_at IS NULL AND revoked_at IS NULL;`` ahead of deploying. If that count is
non-trivial, notify those users first — the migration is safe to apply at any
time, but their integrations are not.

Already-revoked rows are left alone: they are dead regardless, and rewriting them
would only add noise to the audit trail.

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-12 11:00:00.000000
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

#: Must equal ``api_key_auth.DEFAULT_API_KEY_TTL_DAYS``. Restated as a literal
#: rather than imported: a migration is a historical record of what was applied,
#: and importing a live application constant would silently re-date this
#: migration's effect if that constant were ever changed.
_TTL_DAYS = 90


def upgrade() -> None:
    bind = op.get_bind()

    # Guarded like 0028/0029/0039: `docker-entrypoint.sh` runs `alembic upgrade
    # head` under `set -eu`, so a raising migration crash-loops the container.
    # A missing table/column means an environment this backfill does not apply
    # to, which is not an error.
    inspector = sa.inspect(bind)
    if "user_api_keys" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("user_api_keys")}
    if not {"expires_at", "created_at", "revoked_at"} <= columns:
        return

    affected = bind.execute(
        sa.text(
            "SELECT count(*) FROM user_api_keys "
            "WHERE expires_at IS NULL AND revoked_at IS NULL"
        )
    ).scalar_one()

    if not affected:
        return

    # Emitted at WARNING because it is operator-actionable: these integrations
    # stop working at the next request (see the module docstring).
    logger.warning(
        "0040: stamping expires_at = created_at + %d days on %d legacy "
        "never-expiring API key(s). Owners must mint replacements.",
        _TTL_DAYS,
        affected,
    )

    # Date arithmetic is dialect-specific: Postgres has INTERVAL, SQLite has
    # datetime(). Both are used here (Postgres in every deployed environment,
    # SQLite in tests), so both are spelled out rather than relying on one
    # working by accident on the other.
    if bind.dialect.name == "postgresql":
        stmt = sa.text(
            "UPDATE user_api_keys "
            f"SET expires_at = created_at + INTERVAL '{_TTL_DAYS} days' "
            "WHERE expires_at IS NULL AND revoked_at IS NULL"
        )
    else:
        stmt = sa.text(
            "UPDATE user_api_keys "
            f"SET expires_at = datetime(created_at, '+{_TTL_DAYS} days') "
            "WHERE expires_at IS NULL AND revoked_at IS NULL"
        )
    op.execute(stmt)


def downgrade() -> None:
    """Restore NULL on exactly the rows :func:`upgrade` stamped.

    Precise rather than blunt, and it can be: the stamp is a pure function of
    ``created_at``, so the rows this migration wrote are exactly those where
    ``expires_at`` still equals ``created_at + 90 days``. Clearing on that
    predicate leaves genuinely-minted keys (whose stamp came from their creation
    TIME, not their ``created_at`` column, and so differs by the request's own
    latency) untouched.

    A blanket ``SET expires_at = NULL`` would instead un-expire every key in the
    table — turning a downgrade into a privilege escalation. That is the failure
    this predicate exists to avoid.
    """
    bind = op.get_bind()

    inspector = sa.inspect(bind)
    if "user_api_keys" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("user_api_keys")}
    if not {"expires_at", "created_at"} <= columns:
        return

    if bind.dialect.name == "postgresql":
        predicate = f"expires_at = created_at + INTERVAL '{_TTL_DAYS} days'"
    else:
        predicate = f"expires_at = datetime(created_at, '+{_TTL_DAYS} days')"

    op.execute(
        sa.text(
            f"UPDATE user_api_keys SET expires_at = NULL WHERE {predicate}"
        )
    )
