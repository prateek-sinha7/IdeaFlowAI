"""In-memory Cognito user pool, indexed by BOTH ``sub`` and email.

Why the double index is the whole point
---------------------------------------
Cognito-only auth migration, ``.kiro/specs/login/prompt.md`` Decision 4b and
``MERGE_NOTES.md`` §6. Just-in-time provisioning resolves a verified access
token's ``sub`` claim against the pool with ``AdminGetUser(Username=sub)``. That
works because this deployment's pool sets ``username_attributes = ["email"]``,
which makes Cognito generate the canonical ``Username`` itself (a UUID equal to
``sub``) and treat the email as a sign-in ALIAS -- so the Admin* read surface
resolves either string to the same user.

Before this fake existed, nothing in the test suite could have caught that being
wrong. Every ``cognito.py`` wrapper took a parameter literally named ``email``
and passed it straight through as ``Username``, and every test double either
returned a fixed dict while ignoring ``Username`` entirely or keyed an in-memory
set by literal email string. A JIT hook that passed the wrong identifier would
have been invisible offline and failed only against a live pool.

That is not hypothetical in this codebase: ``cognito.py::refresh_auth`` carries a
docstring recording exactly that outcome. ``REFRESH_TOKEN_AUTH`` takes no
``Username`` parameter at all and verifies ``SECRET_HASH`` against the canonical
username, so passing the email alias failed with a thoroughly unhelpful
``NotAuthorizedException: Unable to verify secret hash for client`` -- found by
running the real flow against a live pool, with the offline suite green
throughout.

So this fake resolves ``Username`` the way the real pool does, and
:meth:`FakeCognitoPool.admin_get_user` raises ``UserNotFoundException`` for
anything it does not recognise. A JIT path that passes an email where a ``sub``
belongs (or vice versa) fails here, offline.

Deliberately NOT modelled: password policy, challenge state machines, token
lifetimes. Those belong to ``FakeCognitoAuth`` (which mints real RS256 tokens)
and to the endpoints' own tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import ClientError

from app.core import cognito


def _client_error(code: str, operation: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": code}},
        operation,
    )


@dataclass
class FakePoolUser:
    """One pool user. ``sub`` is the canonical ``Username``; email is an alias."""

    sub: str
    email: str
    enabled: bool = True
    email_verified: bool = True
    groups: set[str] = field(default_factory=set)
    mfa_factors: list[str] = field(default_factory=list)
    #: Mirrors Cognito's own ``UserStatus``. ``FORCE_CHANGE_PASSWORD`` is what an
    #: invited user sits in until they answer NEW_PASSWORD_REQUIRED.
    user_status: str = "CONFIRMED"
    #: Test-observability only, not part of the real Cognito response shape:
    #: records what ``DesiredDeliveryMediums`` a create call passed, so a test
    #: can assert an invitation was actually requested.
    invited_via: list[str] = field(default_factory=list)

    def as_admin_get_user(self) -> dict[str, Any]:
        return {
            "Username": self.sub,
            "Enabled": self.enabled,
            "UserStatus": self.user_status,
            "UserMFASettingList": list(self.mfa_factors),
            "UserAttributes": [
                {"Name": "sub", "Value": self.sub},
                {"Name": "email", "Value": self.email},
                {"Name": "email_verified", "Value": str(self.email_verified).lower()},
            ],
        }

    def as_list_users_row(self) -> dict[str, Any]:
        row = self.as_admin_get_user()
        row["Attributes"] = row.pop("UserAttributes")
        return row


class FakeCognitoPool:
    """A pool that answers Admin* reads/writes from memory.

    Users are stored once, keyed by ``sub``, with a separate email->sub index so
    a lookup by either identifier hits the SAME object -- no duplicated state
    that could drift between the two views.
    """

    def __init__(self) -> None:
        self._by_sub: dict[str, FakePoolUser] = {}
        self._sub_by_email: dict[str, str] = {}

    # ── Test-facing helpers (not part of the Cognito surface) ──────────────

    def add(
        self,
        *,
        sub: str,
        email: str,
        groups: set[str] | None = None,
        enabled: bool = True,
        user_status: str = "CONFIRMED",
    ) -> FakePoolUser:
        """Seed a user, as if an operator had created it in the AWS console."""
        user = FakePoolUser(
            sub=sub,
            email=email,
            enabled=enabled,
            groups=set(groups or ()),
            user_status=user_status,
        )
        self._by_sub[sub] = user
        self._sub_by_email[email] = sub
        return user

    def get(self, username: str) -> FakePoolUser | None:
        """Resolve either identifier, or ``None``. The alias behaviour under test."""
        if username in self._by_sub:
            return self._by_sub[username]
        sub = self._sub_by_email.get(username)
        return self._by_sub.get(sub) if sub else None

    def __contains__(self, username: str) -> bool:
        return self.get(username) is not None

    def groups_for(self, username: str) -> list[str]:
        user = self.get(username)
        return sorted(user.groups) if user else []

    # ── Cognito Admin* surface ────────────────────────────────────────────

    def _require(self, username: str, operation: str) -> FakePoolUser:
        user = self.get(username)
        if user is None:
            raise _client_error("UserNotFoundException", operation)
        return user

    def admin_get_user(self, username: str) -> dict[str, Any]:
        return self._require(username, "AdminGetUser").as_admin_get_user()

    def admin_create_user(
        self,
        email: str,
        temporary_password: str | None = None,
        *,
        desired_delivery_mediums: list[str] | None = None,
    ) -> dict[str, Any]:
        del temporary_password
        if email in self._sub_by_email:
            raise _client_error("UsernameExistsException", "AdminCreateUser")
        # Cognito generates the canonical username itself on an email-username
        # pool; a deterministic derivation keeps assertions readable while still
        # being a DIFFERENT string from the email, which is what matters.
        sub = f"sub-{len(self._by_sub) + 1:04d}-{abs(hash(email)) % 10**8:08d}"
        user = self.add(sub=sub, email=email, user_status="FORCE_CHANGE_PASSWORD")
        # Recorded so a test can assert an invitation was actually requested
        # (Phase 3, Decision 6: admin-create must never set a permanent
        # password itself -- DesiredDeliveryMediums=[EMAIL] is what makes
        # Cognito the one place the temporary password is ever visible).
        user.invited_via = list(desired_delivery_mediums or [])
        return {
            "User": {
                "Username": sub,
                "Attributes": user.as_admin_get_user()["UserAttributes"],
            }
        }

    def admin_delete_user(self, username: str) -> None:
        user = self._require(username, "AdminDeleteUser")
        self._by_sub.pop(user.sub, None)
        self._sub_by_email.pop(user.email, None)

    def admin_disable_user(self, username: str) -> None:
        self._require(username, "AdminDisableUser").enabled = False

    def admin_enable_user(self, username: str) -> None:
        self._require(username, "AdminEnableUser").enabled = True

    def list_users_in_group(self, group_name: str) -> list[dict[str, Any]]:
        return [
            u.as_list_users_row()
            for u in self._by_sub.values()
            if group_name in u.groups
        ]

    def admin_add_user_to_group(self, username: str, group_name: str) -> None:
        self._require(username, "AdminAddUserToGroup").groups.add(group_name)

    def admin_remove_user_from_group(self, username: str, group_name: str) -> None:
        self._require(username, "AdminRemoveUserFromGroup").groups.discard(group_name)

    def admin_list_groups_for_user(self, username: str) -> list[str]:
        return sorted(self._require(username, "AdminListGroupsForUser").groups)

    def admin_user_global_sign_out(self, username: str) -> None:
        self._require(username, "AdminUserGlobalSignOut")

    def admin_set_user_password(
        self, username: str, password: str, permanent: bool = True
    ) -> None:
        del password
        user = self._require(username, "AdminSetUserPassword")
        user.user_status = "CONFIRMED" if permanent else "FORCE_CHANGE_PASSWORD"

    def list_pool_users(self) -> list[dict[str, Any]]:
        return [u.as_list_users_row() for u in self._by_sub.values()]

    def get_confirmed_mfa_factors(self, username: str) -> list[str]:
        return list(self._require(username, "AdminGetUser").mfa_factors)

    # ── Installation ──────────────────────────────────────────────────────

    def install(self, monkeypatch) -> FakeCognitoPool:
        """Point every ``app.core.cognito`` Admin* wrapper at this pool.

        Patches the WRAPPERS rather than ``_client()`` so the boto3 parameter
        marshalling in ``cognito.py`` is bypassed -- the wrappers' own contract
        (which identifier goes in ``Username``) is what these tests exercise,
        and it is preserved because each fake method takes the same positional
        argument the wrapper does.
        """
        for name in (
            "admin_get_user",
            "admin_create_user",
            "admin_delete_user",
            "admin_disable_user",
            "admin_enable_user",
            "admin_add_user_to_group",
            "admin_remove_user_from_group",
            "admin_list_groups_for_user",
            "admin_user_global_sign_out",
            "admin_set_user_password",
            "list_pool_users",
            "list_users_in_group",
            "get_confirmed_mfa_factors",
        ):
            if hasattr(cognito, name):
                monkeypatch.setattr(cognito, name, getattr(self, name))
        return self
