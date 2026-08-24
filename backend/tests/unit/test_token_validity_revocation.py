"""Generalized blanket-revocation check (COGNITO-MIGRATION-PLAN §5.3).

``is_revoked_by_token_validity`` generalizes the pre-Cognito
``password_changed_at`` check to ``max(password_changed_at, tokens_valid_from)``
so a role/tier change can force re-authentication the way a password change
already did. It is what makes a demotion bite on the user's NEXT request
instead of one access-token lifetime later (plan R5) — without it, reading
``cognito:groups`` off the token would leave a revoked admin privileged for up
to an hour.

Two properties are pinned deliberately:

* The whole-second tolerance rule (``iat == cutoff`` is NOT revoked) is
  inherited behaviour, not an accident. JWT ``iat`` has one-second resolution,
  so a token minted in the same second as the stamp would otherwise be revoked
  the instant it was issued — logging the user out of the very session the
  password change just created.
* Generalizing must be a strict SUPERSET of the old behaviour: password-only
  rotations keep working byte-for-byte (INV-3).

Pure logic, no AWS and no DB session needed.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.identity import Principal, is_revoked_by_token_validity
from app.models.user import User

NOW = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
NOW_EPOCH = int(NOW.timestamp())


def _user(**kwargs) -> User:
    return User(
        id="local-uuid",
        email="u@example.com",
        tier="pro",
        is_admin=False,
        auth_provider=kwargs.pop("auth_provider", "cognito"),
        **kwargs,
    )


def _principal(iat: int | None, provider: str = "cognito") -> Principal:
    return Principal(provider=provider, sub="s", jti="j", iat=iat, groups=[])


class TestNoStampMeansNoRevocation:
    def test_both_timestamps_null_is_never_revoked(self):
        assert is_revoked_by_token_validity(_user(), _principal(NOW_EPOCH)) is False

    def test_missing_iat_cannot_be_evaluated_and_is_not_revoked(self):
        """A token with no `iat` has nothing to compare.

        It is not treated as revoked here because the claim-level verifier is
        what rejects malformed tokens; this check would otherwise lock out
        every principal the moment any stamp existed.
        """
        user = _user(tokens_valid_from=NOW)
        assert is_revoked_by_token_validity(user, _principal(None)) is False


class TestPasswordChangeBehaviourPreserved:
    """INV-3: the original password-only semantics must be unchanged."""

    def test_token_issued_before_password_change_is_revoked(self):
        user = _user(password_changed_at=NOW)
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH - 1)) is True

    def test_token_issued_after_password_change_survives(self):
        user = _user(password_changed_at=NOW)
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH + 1)) is False

    def test_same_second_is_not_revoked(self):
        """The documented tolerance rule — see the module docstring."""
        user = _user(password_changed_at=NOW)
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH)) is False


class TestTokensValidFromTrigger:
    def test_token_issued_before_a_role_change_is_revoked(self):
        """The new trigger: an admin demotion takes effect immediately."""
        user = _user(tokens_valid_from=NOW)
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH - 1)) is True

    def test_token_issued_after_a_role_change_survives(self):
        user = _user(tokens_valid_from=NOW)
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH + 60)) is False

    def test_same_second_is_not_revoked(self):
        user = _user(tokens_valid_from=NOW)
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH)) is False

    def test_applies_to_the_local_break_glass_path_too(self):
        """Revocation is provider-agnostic — break-glass is not exempt."""
        user = _user(auth_provider="local", tokens_valid_from=NOW)
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH - 1, "local")) is True


class TestMaxOfBothStamps:
    """The LATER stamp wins, whichever field it is."""

    def test_later_tokens_valid_from_wins_over_older_password_change(self):
        user = _user(
            password_changed_at=NOW - timedelta(hours=2),
            tokens_valid_from=NOW,
        )
        # Issued after the password change but before the role change.
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH - 60)) is True

    def test_later_password_change_wins_over_older_tokens_valid_from(self):
        user = _user(
            password_changed_at=NOW,
            tokens_valid_from=NOW - timedelta(hours=2),
        )
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH - 60)) is True

    def test_token_after_both_stamps_survives(self):
        user = _user(
            password_changed_at=NOW - timedelta(hours=2),
            tokens_valid_from=NOW,
        )
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH + 1)) is False

    @pytest.mark.parametrize("offset_hours", [1, 24, 24 * 365])
    def test_arbitrarily_old_tokens_stay_revoked(self, offset_hours):
        user = _user(tokens_valid_from=NOW)
        iat = int((NOW - timedelta(hours=offset_hours)).timestamp())
        assert is_revoked_by_token_validity(user, _principal(iat)) is True


class TestNaiveDatetimeHandling:
    """SQLite hands back naive datetimes; they must be read as UTC.

    Getting this wrong shifts the cutoff by the host's UTC offset, which would
    either revoke valid tokens or (worse) fail to revoke demoted ones — and it
    would pass on a UTC-configured CI box while breaking elsewhere.
    """

    def test_naive_tokens_valid_from_is_treated_as_utc(self):
        user = _user(tokens_valid_from=NOW.replace(tzinfo=None))
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH - 1)) is True
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH + 1)) is False

    def test_naive_password_changed_at_is_treated_as_utc(self):
        user = _user(password_changed_at=NOW.replace(tzinfo=None))
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH - 1)) is True
        assert is_revoked_by_token_validity(user, _principal(NOW_EPOCH + 1)) is False

    def test_mixed_naive_and_aware_stamps_still_compare(self):
        """A mixed pair must not raise a naive/aware TypeError."""
        user = _user(
            password_changed_at=NOW.replace(tzinfo=None),
            tokens_valid_from=NOW + timedelta(minutes=5),
        )
        later = int((NOW + timedelta(minutes=5)).timestamp())
        assert is_revoked_by_token_validity(user, _principal(later - 1)) is True
        assert is_revoked_by_token_validity(user, _principal(later + 1)) is False
