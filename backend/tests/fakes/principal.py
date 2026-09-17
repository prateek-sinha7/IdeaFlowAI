"""Build a ``Principal`` for a test ``User``, mirroring production group derivation.

Phase 2 of the Cognito-only auth migration moved every entitlement gate onto
``core.identity.effective_tier``/``effective_is_admin``, which resolve
``cognito:groups`` off the verified token rather than the ``users`` DB columns
(Decision 3). Endpoints carrying such a gate therefore depend on
``get_current_principal`` instead of ``get_current_user``.

Test fixtures that stub authentication out with
``app.dependency_overrides[get_current_user] = lambda: user`` need a matching
override for the new dependency. :func:`principal_for` derives the groups a real
Cognito token WOULD carry for that user's tier/role, so a fixture keeps
expressing intent the same way it always did -- "this caller is enterprise" --
while the code under test reaches that conclusion through the production group
table instead of by reading the column.

Deriving the groups rather than hardcoding a list is the point: if a tier is ever
added to ``entitlements`` without a matching group (exactly how ``hexaware``
came to have no Cognito group), these overrides resolve it to the fail-closed
default and the affected tests fail, instead of quietly passing against a group
membership no real token could carry.
"""

from __future__ import annotations

import time

from app.core.entitlements import ADMIN_GROUP, group_for_tier
from app.core.identity import Principal


def groups_for(user: object) -> list[str]:
    """The ``cognito:groups`` claim a real token for ``user`` would carry."""
    groups = [group_for_tier(getattr(user, "tier", None) or "basic")]
    if getattr(user, "is_admin", False):
        groups.append(ADMIN_GROUP)
    return groups


def principal_for(
    user: object,
    *,
    jti: str | None = "test-jti",
    iat: int | None = None,
    groups: list[str] | None = None,
) -> Principal:
    """A ``Principal`` consistent with ``user``'s tier and role.

    ``iat`` defaults to "now" so the projection-refresh path in
    ``core.dependencies._sync_role_projection`` behaves as it would in
    production. ``groups`` overrides the derivation outright, for tests that
    need a token DISAGREEING with the DB columns -- which is the whole point of
    the precedence rule and deserves to be easy to express.
    """
    return Principal(
        provider="cognito",
        sub=getattr(user, "cognito_sub", None) or getattr(user, "id", "test-sub"),
        jti=jti,
        iat=int(time.time()) if iat is None else iat,
        groups=groups if groups is not None else groups_for(user),
    )
