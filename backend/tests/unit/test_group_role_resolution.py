"""Cognito group -> tier/role resolution (COGNITO-MIGRATION-PLAN §5.1, §5.4).

These are the functions that turn a verified token's ``cognito:groups`` claim
into an authorization decision, so their edge cases are security-relevant, not
cosmetic. Pure functions, zero AWS calls.

The precedence rule under test: LOWER precedence number wins (mirroring
Cognito's own group-precedence semantics), and an unrecognised or absent tier
group resolves to ``basic`` (fail closed).
"""
import pytest

from app.core.entitlements import (
    ADMIN_GROUP,
    DEFAULT_TIER,
    resolve_is_admin_from_groups,
    resolve_tier_from_groups,
)
from app.core.identity import Principal, effective_is_admin, effective_tier
from app.models.user import User


class TestTierResolution:
    @pytest.mark.parametrize(
        "groups,expected",
        [
            (["flowin-tier-basic"], "basic"),
            (["flowin-tier-pro"], "pro"),
            (["flowin-tier-enterprise"], "enterprise"),
        ],
    )
    def test_single_tier_group(self, groups, expected):
        assert resolve_tier_from_groups(groups) == expected

    def test_no_groups_falls_back_to_basic(self):
        """Fail closed: a user in no group gets the least-privileged tier."""
        assert resolve_tier_from_groups([]) == DEFAULT_TIER == "basic"

    def test_unknown_groups_only_falls_back_to_basic(self):
        assert resolve_tier_from_groups(["some-other-group", "flowin-admins"]) == "basic"

    @pytest.mark.parametrize(
        "groups",
        [
            ["flowin-tier-basic", "flowin-tier-enterprise"],
            ["flowin-tier-enterprise", "flowin-tier-basic"],
            ["flowin-tier-pro", "flowin-tier-enterprise", "flowin-tier-basic"],
        ],
    )
    def test_lowest_precedence_number_wins_regardless_of_claim_order(self, groups):
        """Enterprise (precedence 10) beats pro (20) and basic (30).

        Order-independence matters: Cognito does not guarantee any particular
        ordering of the `cognito:groups` array, so a resolver that took "the
        first match" would be non-deterministic across logins.
        """
        assert resolve_tier_from_groups(groups) == "enterprise"

    def test_pro_beats_basic(self):
        assert resolve_tier_from_groups(["flowin-tier-basic", "flowin-tier-pro"]) == "pro"

    def test_admin_group_does_not_affect_tier(self):
        """Role and tier are orthogonal — an admin is not implicitly enterprise."""
        assert resolve_tier_from_groups([ADMIN_GROUP, "flowin-tier-basic"]) == "basic"


class TestAdminResolution:
    def test_admin_group_grants_admin(self):
        assert resolve_is_admin_from_groups([ADMIN_GROUP]) is True

    def test_absent_admin_group_denies_admin(self):
        assert resolve_is_admin_from_groups(["flowin-tier-enterprise"]) is False

    def test_no_groups_denies_admin(self):
        assert resolve_is_admin_from_groups([]) is False

    def test_similar_group_name_does_not_grant_admin(self):
        """Exact match only — no prefix/substring matching on a privilege check."""
        assert resolve_is_admin_from_groups(["flowin-admins-readonly"]) is False
        assert resolve_is_admin_from_groups(["not-flowin-admins"]) is False


class TestProjectionPrecedence:
    """§5.4: on the Cognito path the DB columns are ADVISORY, never authoritative.

    This is the rule most likely to be silently violated by future code (the
    columns are right there on the User object), so it gets an explicit test:
    a stale/hostile projection must not be able to escalate a Cognito
    principal, and must remain authoritative for break-glass.
    """

    def _user(self, *, tier: str, is_admin: bool, auth_provider: str) -> User:
        return User(
            id="local-uuid",
            email="u@example.com",
            tier=tier,
            is_admin=is_admin,
            auth_provider=auth_provider,
        )

    def test_cognito_groups_override_a_stale_higher_db_tier(self):
        user = self._user(tier="enterprise", is_admin=True, auth_provider="cognito")
        principal = Principal(
            provider="cognito", sub="s", jti="j", iat=0, groups=["flowin-tier-basic"]
        )
        assert effective_tier(user, principal) == "basic"
        assert effective_is_admin(user, principal) is False

    def test_cognito_groups_override_a_stale_lower_db_tier(self):
        user = self._user(tier="basic", is_admin=False, auth_provider="cognito")
        principal = Principal(
            provider="cognito",
            sub="s",
            jti="j",
            iat=0,
            groups=["flowin-tier-enterprise", ADMIN_GROUP],
        )
        assert effective_tier(user, principal) == "enterprise"
        assert effective_is_admin(user, principal) is True

    def test_local_principal_uses_the_db_columns(self):
        """Break-glass has no group claim — the columns ARE the authority."""
        user = self._user(tier="enterprise", is_admin=True, auth_provider="local")
        principal = Principal(provider="local", sub="local-uuid", jti="j", iat=0, groups=[])
        assert effective_tier(user, principal) == "enterprise"
        assert effective_is_admin(user, principal) is True

    def test_cognito_principal_with_no_groups_is_least_privileged(self):
        """A Cognito user removed from every group must not inherit old DB values."""
        user = self._user(tier="enterprise", is_admin=True, auth_provider="cognito")
        principal = Principal(provider="cognito", sub="s", jti="j", iat=0, groups=[])
        assert effective_tier(user, principal) == "basic"
        assert effective_is_admin(user, principal) is False
