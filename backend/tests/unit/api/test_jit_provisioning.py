"""The alias premise that just-in-time provisioning rests on.

Discharges the proof obligation recorded in ``MERGE_NOTES.md`` §6: *"Phase 2 must add a
new fake fixture that actually indexes by sub (not just email) before wiring the JIT
hook."* Decision 4 of the Cognito-only auth migration
(``.kiro/specs/login/prompt.md``) depends on ``AdminGetUser`` resolving EITHER
identifier, because a verified access token carries ``sub`` and never necessarily an
email — so if the fake (or the wrapper) only indexed by email, the entire token-path JIT
design would be built on an assumption nothing had tested.

Pure: a fake pool and a read wrapper, no database. The provisioning behaviour itself —
both entry points, the refusal cases, the negative-result cache, the ``resolve_principal``
JIT hook and the projection refresh — asserts persistence outcomes and lives in
``tests/integration/external/test_jit_provisioning_external.py``.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from app.core import cognito
from tests.fakes.cognito_pool import FakeCognitoPool


@pytest.fixture()
def pool(monkeypatch) -> FakeCognitoPool:
    return FakeCognitoPool().install(monkeypatch)


# ─── MERGE_NOTES §6: AdminGetUser resolves a sub as Username ────────────────


class TestAdminGetUserAcceptsSub:
    """The alias behaviour the whole token-path JIT design rests on.

    This pool sets ``username_attributes = ["email"]``, so Cognito generates the
    canonical ``Username`` (a UUID equal to ``sub``) and the email is a sign-in
    alias. Both must resolve on the Admin* read surface, because a verified
    access token carries ``sub`` and never necessarily an email.
    """

    def test_admin_get_user_resolves_the_canonical_sub(self, pool):
        pool.add(sub="sub-abc", email="person@example.com")

        result = cognito.admin_get_user("sub-abc")

        assert cognito.user_attributes(result)["sub"] == "sub-abc"
        assert cognito.user_attributes(result)["email"] == "person@example.com"

    def test_admin_get_user_resolves_the_email_alias_to_the_same_user(self, pool):
        pool.add(sub="sub-abc", email="person@example.com")

        by_sub = cognito.admin_get_user("sub-abc")
        by_email = cognito.admin_get_user("person@example.com")

        assert cognito.user_attributes(by_sub) == cognito.user_attributes(by_email)

    def test_admin_get_user_raises_user_not_found_for_an_unknown_identifier(self, pool):
        """A READ api is outside prevent_user_existence_errors, so this answer is
        authoritative -- unlike NotAuthorizedException from AdminInitiateAuth."""
        with pytest.raises(ClientError) as exc:
            cognito.admin_get_user("nobody@example.com")

        assert exc.value.response["Error"]["Code"] == "UserNotFoundException"

    def test_sub_and_email_are_different_strings(self, pool):
        """Guards the fake itself: if it happened to key both views off the same
        string, every test above would pass while proving nothing."""
        user = pool.add(sub="sub-abc", email="person@example.com")

        assert user.sub != user.email
