"""Tier-based feature entitlements."""

from typing import Literal

from agents.capabilities.model_catalog import ModelCatalog

Tier = Literal["basic", "pro", "enterprise", "hexaware"]

# Pipelines each tier can execute (including revision variants)
TIER_PIPELINES: dict[str, set[str]] = {
    "basic": {
        "user_stories", "user_stories_revision",
        "ppt", "ppt_v2", "ppt_revision",
    },
    # KAN-161 / ISS-055: scoped tier for deployments that need prototype +
    # user_stories only (e.g. Hexaware internal tooling). Deliberately excludes
    # the ppt and app_builder families.
    "hexaware": {
        "user_stories", "user_stories_revision",
        "prototype", "prototype_revision",
        "prototype_large_revision",    # tiered large-revision manifest
        "prototype_feature_revision",  # tiered feature-revision manifest
    },
    "pro": {
        "user_stories", "user_stories_revision",
        "ppt", "ppt_v2", "ppt_revision",
        "prototype", "prototype_revision",
        "prototype_large_revision",    # tiered large-revision manifest
        "prototype_feature_revision",  # tiered feature-revision manifest
        "app_builder", "app_builder_revision",
    },
    "enterprise": {
        "user_stories", "user_stories_revision",
        "ppt", "ppt_v2", "ppt_revision",
        "prototype", "prototype_revision",
        "prototype_large_revision",    # tiered large-revision manifest
        "prototype_feature_revision",  # tiered feature-revision manifest
        "app_builder", "app_builder_revision",
        "custom", "custom_revision",
        # UI meta-grouping, never dispatched: the "Platform workflows" card makes
        # the user pick a concrete sub-pipeline first. It has no manifest, so a
        # direct launch would 404 at compile — but the frontend gates the card on
        # this entry, so removing it hides the card entirely.
        "migration",
        "mulesoft_to_springboot",
        "dotnet_to_azure",
        # spec-014 conditional-gates integration: QA found these 5 were not
        # entitled to any tier despite user_launchable: true.
        "ex_A2_branch",
        "ex_A1_loop",
        "ex_A4_human_gate",
        "ex_A4_human_divert",
        "ex_A3_divert",
        "ex_A3_b_spanish",
        "ex_A3_c_dutch",
        # spec 018: temporary smoke-test pipeline for the playwright tool set.
        # Same gap as the ex_A* fixtures above — user_launchable: true alone
        # doesn't entitle a pipeline, it needs a tier row too.
        "playwright_smoke_test",
    },
}

TIER_LABELS = {
    "basic": "Basic",
    "hexaware": "Hexaware",
    "pro": "Pro",
    "enterprise": "Enterprise",
}

UPGRADE_PATH = {
    "basic": "pro",
    "hexaware": "enterprise",
    "pro": "enterprise",
    "enterprise": None,
}


def can_run_pipeline(user_tier: str, pipeline_type: str) -> tuple[bool, str]:
    """Return (allowed, reason). reason is empty string when allowed."""
    allowed_pipelines = TIER_PIPELINES.get(user_tier, TIER_PIPELINES["basic"])
    if pipeline_type in allowed_pipelines:
        return True, ""
    next_tier = UPGRADE_PATH.get(user_tier)
    if next_tier:
        next_label = TIER_LABELS[next_tier]
        return False, f"This pipeline requires {next_label} or higher. Upgrade your plan to unlock it."
    return False, "This pipeline is not available on your current plan."


# Model cost classes each tier may select (ISS-292). Keyed off
# ``ModelEntry.cost_class`` — the canonical axis (cheap/standard/premium), not the
# display ``tier`` string — so the table is the same shape as TIER_PIPELINES above
# and reads the same fail-closed way. The entry tier is held off the premium
# (Opus) models; every paid tier keeps the full catalog.
#
# NOT the same axis as ``ModelEntry.user_allowed``, which is the CAP-03 trust flag
# (engineer- vs user-composable capability) — subscription tier and capability
# trust must not be conflated.
TIER_MODEL_COST_CLASSES: dict[str, set[str]] = {
    "basic": {"cheap", "standard"},
    "hexaware": {"cheap", "standard", "premium"},
    "pro": {"cheap", "standard", "premium"},
    "enterprise": {"cheap", "standard", "premium"},
}


def can_use_model(user_tier: str, model_id: str) -> tuple[bool, str]:
    """Return (allowed, reason). reason is empty string when allowed.

    The tier question only. Catalog MEMBERSHIP stays the caller's check
    (``settings.py``'s ``_VALID_MODEL_IDS``, ``run_engine.py``'s
    ``ModelCatalog().ids()``), so an unknown id passes through here and keeps
    getting the caller's 422 instead of a misleading "upgrade your plan" 403.
    """
    entry = ModelCatalog().get(model_id)
    if entry is None:
        return True, ""
    allowed_classes = TIER_MODEL_COST_CLASSES.get(
        user_tier, TIER_MODEL_COST_CLASSES["basic"]
    )
    if entry.cost_class in allowed_classes:
        return True, ""
    next_tier = UPGRADE_PATH.get(user_tier)
    if next_tier:
        next_label = TIER_LABELS[next_tier]
        return False, f"This model requires {next_label} or higher. Upgrade your plan to unlock it."
    return False, "This model is not available on your current plan."


# --- Cognito group -> role/tier resolution (COGNITO-MIGRATION-PLAN §5.1) ---
#
# The single home of the Cognito group precedence table. These names and
# precedences MUST match the four aws_cognito_user_group resources created by
# infra/terraform/modules/cognito (see that module's variables.tf
# `group_names` default) — rename one place without the other and group
# membership silently stops resolving to a tier/role.
ADMIN_GROUP = "flowin-admins"

# Lower precedence number wins (Cognito's own convention, mirrored here).
# Order matters: the first matching entry in iteration order is NOT what
# decides precedence -- the explicit `precedence` value is what's compared.
_TIER_GROUP_PRECEDENCE: dict[str, tuple[Tier, int]] = {
    "flowin-tier-enterprise": ("enterprise", 10),
    "flowin-tier-pro": ("pro", 20),
    "flowin-tier-basic": ("basic", 30),
}

DEFAULT_TIER: Tier = "basic"


def resolve_tier_from_groups(groups: list[str]) -> Tier:
    """Resolve the effective tier from a Cognito `cognito:groups` claim.

    Lowest precedence number wins (mirrors Cognito's own group-precedence
    semantics, migration plan §5.1). A user in no tier group -- or in none of
    the three known tier groups -- resolves to "basic", matching the existing
    fail-closed `TIER_PIPELINES.get(tier, basic)` fallback used elsewhere in
    this module.
    """
    best_tier: Tier = DEFAULT_TIER
    best_precedence = float("inf")
    for group in groups:
        entry = _TIER_GROUP_PRECEDENCE.get(group)
        if entry is None:
            continue
        tier, precedence = entry
        if precedence < best_precedence:
            best_precedence = precedence
            best_tier = tier
    return best_tier


def resolve_is_admin_from_groups(groups: list[str]) -> bool:
    """True if the principal is a member of the fixed admins group."""
    return ADMIN_GROUP in groups
