"""Tier-based feature entitlements."""

from typing import Literal

Tier = Literal["basic", "pro", "enterprise", "hexaware"]

# Pipelines each tier can execute (including revision variants)
TIER_PIPELINES: dict[str, set[str]] = {
    "basic": {
        "user_stories", "user_stories_revision",
        "ppt", "ppt_revision",
    },
    # KAN-161 / ISS-055: scoped tier for deployments that need prototype +
    # user_stories only (e.g. Hexaware internal tooling). Deliberately excludes
    # ppt/od_ppt, od_prototype_revision, and app_builder families.
    "hexaware": {
        "user_stories", "user_stories_revision",
        "prototype", "prototype_revision",
        "od_prototype",
    },
    "pro": {
        "user_stories", "user_stories_revision",
        "ppt", "ppt_revision",
        "prototype", "prototype_revision",
        "od_prototype", "od_prototype_revision",
        "app_builder", "app_builder_revision",
    },
    "enterprise": {
        "user_stories", "user_stories_revision",
        "ppt", "ppt_revision",
        "prototype", "prototype_revision",
        "od_prototype", "od_prototype_revision",
        "app_builder", "app_builder_revision",
        "custom", "custom_revision",
        "migration",
        "mulesoft_to_springboot",
        "dotnet_to_azure",
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
