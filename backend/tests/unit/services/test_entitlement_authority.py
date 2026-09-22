"""``hexaware`` is group-expressible — the tier/group table has no silent gaps.

``hexaware`` was a fully-wired tier in ``TIER_PIPELINES`` with no Cognito group anywhere
(``MERGE_NOTES.md`` §2). Harmless while the gates read the DB column; the moment they read
groups instead (Decision 3), a missing group is a silent entitlement DOWNGRADE. These
assertions are what make that regression loud rather than invisible.

Pure table lookups over ``entitlements`` — no store, no HTTP. The ENFORCEMENT half, which
proves a GATE consults groups rather than the ``users.tier`` column by making the two
sources disagree across a real request, needs the router and a real row and lives in
``tests/integration/api/test_entitlement_authority_api.py``.
"""

from __future__ import annotations

from app.core.entitlements import group_for_tier


class TestHexawareIsGroupExpressible:
    """``hexaware`` was a fully-wired tier in ``TIER_PIPELINES`` with no Cognito
    group anywhere (``MERGE_NOTES.md`` §2). Harmless while the gates read the DB
    column; the moment they read groups instead, a missing group is a silent
    entitlement DOWNGRADE. These two assertions are what make that regression
    loud rather than invisible."""

    def test_hexaware_has_a_group(self):
        assert group_for_tier("hexaware") == "flowin-tier-hexaware"

    def test_the_hexaware_group_resolves_back_to_hexaware(self):
        from app.core.entitlements import resolve_tier_from_groups

        assert resolve_tier_from_groups([group_for_tier("hexaware")]) == "hexaware"

    def test_hexaware_beats_a_leftover_pro_membership(self):
        """Precedence 15 vs pro's 20. A deployment that scopes a user down to
        hexaware must not be silently widened back to pro by a stale group."""
        from app.core.entitlements import resolve_tier_from_groups

        assert (
            resolve_tier_from_groups(
                [group_for_tier("pro"), group_for_tier("hexaware")]
            )
            == "hexaware"
        )

    def test_an_unknown_tier_still_maps_to_the_least_privileged_group(self):
        from app.core.entitlements import DEFAULT_TIER

        assert group_for_tier("no-such-tier") == group_for_tier(DEFAULT_TIER)
