"""Regression: the refresh flow must hash the CANONICAL username, not the email.

This pins a bug that the offline suite could not have caught and that a live
pool found immediately (Cognito migration, Phase 5 validation).

Background. The pool is created with ``username_attributes = ["email"]``, so
Cognito generates a UUID as the real ``Username`` and treats the email as a
sign-in *alias*. Those two flows then behave differently:

* ``AdminInitiateAuth`` takes an explicit ``USERNAME`` parameter, and Cognito
  verifies ``SECRET_HASH`` against **whatever you passed there**. An email works.
* ``REFRESH_TOKEN_AUTH`` has no ``USERNAME`` parameter. Cognito verifies
  ``SECRET_HASH`` against the **canonical username the refresh token was issued
  to** (the UUID). Passing the email fails with
  ``NotAuthorizedException: Unable to verify secret hash for client`` — a
  message that points at the client secret rather than the username, which is
  what makes this expensive to debug in production.

Why this matters beyond tidiness: `/api/auth/refresh` is what keeps
long-running workflows alive across access-token expiry (R4 in the migration
plan's risk register). Silently broken refresh means every long run dies at the
60-minute mark, and the symptom looks like a token-expiry problem rather than a
hashing one.

These tests assert on the SECRET_HASH input, because that is the actual contract
with Cognito. Mocking boto3 is unavoidable here (the point is to test what we
SEND), so the test is deliberately narrow: it does not claim to prove Cognito
accepts it — the live run did that.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.core import cognito
from app.core.config import settings


CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"
POOL_ID = "eu-central-1_testpool"

CANONICAL_USERNAME = "03f4d8e2-3031-700f-4df4-5733a9c5b300"  # == the `sub` claim
EMAIL = "qa-admin@flowinqa.com"


@pytest.fixture
def cognito_settings(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL_ID)
    monkeypatch.setattr(settings, "COGNITO_REGION", "eu-central-1")


def test_secret_hash_differs_between_email_and_canonical_username(cognito_settings):
    """The two inputs genuinely produce different hashes.

    If this ever became false the rest of this module would be vacuous, so it is
    asserted explicitly rather than assumed.
    """
    assert cognito.compute_secret_hash(EMAIL) != cognito.compute_secret_hash(CANONICAL_USERNAME)


def test_refresh_auth_hashes_the_value_it_is_given(cognito_settings):
    """refresh_auth must hash its argument verbatim — no internal email guessing."""
    fake_client = MagicMock()
    with patch.object(cognito, "_client", return_value=fake_client):
        cognito.refresh_auth("some-refresh-token", CANONICAL_USERNAME)

    params = fake_client.admin_initiate_auth.call_args.kwargs
    assert params["AuthFlow"] == "REFRESH_TOKEN_AUTH"
    assert params["AuthParameters"]["REFRESH_TOKEN"] == "some-refresh-token"
    assert params["AuthParameters"]["SECRET_HASH"] == cognito.compute_secret_hash(
        CANONICAL_USERNAME
    ), "refresh_auth must hash the canonical username it was handed"
    # The refresh flow must NOT send a USERNAME parameter; Cognito derives the
    # user from the token itself.
    assert "USERNAME" not in params["AuthParameters"]


def test_refresh_endpoint_passes_cognito_sub_not_email(cognito_settings, monkeypatch):
    """THE regression guard.

    `/api/auth/refresh` must hand `refresh_auth` the user's `cognito_sub`. This
    is the exact line that was wrong: it passed `user.email`, which Cognito
    rejected.
    """
    from app.models.user import User

    user = User(
        id="local-uuid",
        email=EMAIL,
        cognito_sub=CANONICAL_USERNAME,
        auth_provider="cognito",
        tier="enterprise",
        is_admin=True,
        encrypted_cognito_refresh_token="ciphertext",
    )

    captured: dict[str, str] = {}

    def fake_refresh_auth(refresh_token: str, canonical_username: str):
        captured["username"] = canonical_username
        return {"AuthenticationResult": {"AccessToken": "new-access-token"}}

    monkeypatch.setattr("app.api.auth.decrypt_cognito_refresh_token", lambda _c: "plain-refresh")
    monkeypatch.setattr(cognito, "refresh_auth", fake_refresh_auth)

    from app.api.auth import refresh as refresh_endpoint

    result = refresh_endpoint(auth=(user, {"sub": CANONICAL_USERNAME}), db=MagicMock())

    assert captured["username"] == CANONICAL_USERNAME, (
        "refresh must use cognito_sub (the pool's canonical Username), not the "
        "email alias — Cognito rejects the email on REFRESH_TOKEN_AUTH"
    )
    assert captured["username"] != EMAIL
    assert result.token == "new-access-token"


def test_refresh_endpoint_falls_back_to_email_when_sub_is_missing(cognito_settings, monkeypatch):
    """A row predating sub-mapping still attempts a refresh rather than 500ing.

    Such a row should not exist after cutover (verify_cognito_cutover.py's C1
    check asserts exactly that), but degrading to a best-effort attempt is
    friendlier than crashing on a NULL.
    """
    from app.models.user import User

    user = User(
        id="local-uuid",
        email=EMAIL,
        cognito_sub=None,
        auth_provider="cognito",
        tier="basic",
        is_admin=False,
        encrypted_cognito_refresh_token="ciphertext",
    )

    captured: dict[str, str] = {}

    def fake_refresh_auth(refresh_token: str, canonical_username: str):
        captured["username"] = canonical_username
        return {"AuthenticationResult": {"AccessToken": "tok"}}

    monkeypatch.setattr("app.api.auth.decrypt_cognito_refresh_token", lambda _c: "plain-refresh")
    monkeypatch.setattr(cognito, "refresh_auth", fake_refresh_auth)

    from app.api.auth import refresh as refresh_endpoint

    refresh_endpoint(auth=(user, {"sub": "x"}), db=MagicMock())
    assert captured["username"] == EMAIL
