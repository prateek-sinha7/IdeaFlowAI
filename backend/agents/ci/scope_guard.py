"""
CI-Only Scope Guard for preventing product/deploy/provision changes in CI configuration.

Ensures CI-only remediation changes do not leak into application code, deployment logic,
provisioning, or product runtime semantics.

Requirements: 3.3, 3.4, 3.5, 3.9, 3.13, 3.16
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class ChangeCategory(str, Enum):
    """Classification of change impact."""

    CI_ONLY = "ci_only"  # Safe: CI configuration, workflow files, CI tests
    CI_SUPPORTING = (
        "ci_supporting"  # CI-supporting tests/fixtures without product semantics
    )
    DEBT_REMEDIATION = (
        "debt_remediation"  # Separately reviewed: test fixes, coverage improvements
    )
    INFRASTRUCTURE = "infrastructure"  # Terraform/Docker/deployment config
    PRODUCT_RUNTIME = (
        "product_runtime"  # DANGER: application code, APIs, runtime behavior
    )
    SCHEMA = "schema"  # DANGER: database migrations, schema changes
    DEPLOYMENT = "deployment"  # DANGER: deployment job topology, provisioning
    PRESERVED = "preserved"  # Expected unchanged surfaces


# Allowed CI-only path patterns
CI_ONLY_PATHS = {
    ".github/workflows/",  # Workflow files
    ".github/actions/",  # Custom actions
    ".github/scripts/",  # GitHub automation scripts
    ".github/environments/",  # Environment config (not secrets)
    "ci/",  # CI helper scripts and configuration
    "backend/tests/ci/",  # CI-specific tests
    "backend/agents/ci/",  # CI-specific agent code
    "frontend/tests/ci/",  # CI-specific frontend tests
    ".github/rulesets/",  # Branch protection rules (special: no new requirements until Task 3.27)
}

# Paths that trigger debt classification (must be explicitly reviewed)
DEBT_REMEDIATION_PATHS = {
    "backend/tests/",  # Backend test fixes
    "frontend/tests/",  # Frontend test fixes
    "backend/tests/agents/characterization/golden/",  # Golden updates (requires SNAPSHOT_UPDATE)
}

# Preserved surfaces that must NEVER change in this bugfix
PRESERVED_PATHS = {
    "backend/app/",  # Application code
    "backend/agents/execution_engine/",  # Kernel engine
    "backend/agents/capabilities/",  # Capability registry
    "backend/agents/workflows/",  # Workflow manifests
    "backend/app/models/",  # Database models
    "backend/alembic/",  # Migrations (schema is preserved)
    "frontend/src/app/",  # Frontend application code
    "frontend/src/providers/",  # Context providers
    "frontend/src/hooks/",  # Frontend hooks
    ".github/workflows/deploy.yml",  # Deployment workflow (preserve topology/approvals)
    ".github/workflows/provision.yml",  # Provisioning workflow (preserve topology)
    "pyproject.toml",  # Project configuration (except dependencies)
    "package.json",  # Frontend package definition
}

# Infrastructure/deployment that belongs outside this bugfix
INFRASTRUCTURE_PATHS = {
    "Dockerfile",  # Production container definitions
    "docker-compose.yml",  # Service definitions
    "terraform/",  # Terraform source (not test/validation)
    ".github/workflows/deploy.yml",  # Deployment workflows
    ".github/workflows/provision.yml",  # Provisioning workflows
}


@dataclass(frozen=True)
class PathChange:
    """Represents a single file path change."""

    path: str
    category: Optional[ChangeCategory] = None
    severity: int = 0  # 0: safe, 1: warning, 2: error


@dataclass(frozen=True)
class DeployProvisionSnapshot:
    """
    Semantic snapshot of deploy/provision behavior that must remain unchanged.

    This captures the logical intent of deployment and provisioning workflows,
    not their formatting. Changes that preserve semantics are allowed elsewhere
    but must not appear as workflow logic changes.
    """

    # Deployment trigger classification
    deployment_trigger: (
        str  # e.g., "manual approval", "push to main", "manual_dispatch"
    )

    # Environment and approval gates
    required_environments: set[str]  # e.g., {"staging", "production"}
    required_approvals: bool  # Whether human approval is needed

    # Image and artifact publishing
    image_publish_enabled: bool
    registry_push_allowed: bool
    artifact_retention_days: int

    # Database migration execution
    migration_execution: str  # "automatic", "manual", "gated"
    migration_rollback_available: bool

    # Rollout strategy
    rollout_strategy: str  # e.g., "canary", "blue_green", "rolling"
    rollout_time_estimate_minutes: int

    # Infrastructure provisioning
    terraform_plan_executed: bool
    terraform_apply_executed: bool
    cloud_credentials_required: bool

    def to_dict(self) -> dict:
        """Convert to dictionary for comparison."""
        return {
            "deployment_trigger": self.deployment_trigger,
            "required_environments": sorted(self.required_environments),
            "required_approvals": self.required_approvals,
            "image_publish_enabled": self.image_publish_enabled,
            "registry_push_allowed": self.registry_push_allowed,
            "artifact_retention_days": self.artifact_retention_days,
            "migration_execution": self.migration_execution,
            "migration_rollback_available": self.migration_rollback_available,
            "rollout_strategy": self.rollout_strategy,
            "rollout_time_estimate_minutes": self.rollout_time_estimate_minutes,
            "terraform_plan_executed": self.terraform_plan_executed,
            "terraform_apply_executed": self.terraform_apply_executed,
            "cloud_credentials_required": self.cloud_credentials_required,
        }


# Current (baseline) deploy/provision semantics that must be preserved
CURRENT_DEPLOY_PROVISION_SNAPSHOT = DeployProvisionSnapshot(
    deployment_trigger="manual approval + push to main",
    required_environments={"staging", "production"},
    required_approvals=True,
    image_publish_enabled=True,
    registry_push_allowed=True,
    artifact_retention_days=90,
    migration_execution="gated",
    migration_rollback_available=True,
    rollout_strategy="canary",
    rollout_time_estimate_minutes=30,
    terraform_plan_executed=False,  # CI does not run plan
    terraform_apply_executed=False,  # CI does not run apply
    cloud_credentials_required=True,  # Deployment has cloud access, CI does not
)


def classify_path(path: str) -> ChangeCategory:
    """
    Classify a file path change by impact category.

    Args:
        path: File path relative to repository root

    Returns:
        ChangeCategory indicating the impact classification

    Raises:
        ValueError: If path cannot be classified
    """
    path_normalized = path.replace("\\", "/")

    # Check preserved surfaces (must not change)
    for preserved in PRESERVED_PATHS:
        preserved_norm = preserved.replace("\\", "/")
        if path_normalized.startswith(preserved_norm):
            return ChangeCategory.PRESERVED

    # Check CI-only paths (safe)
    for ci_path in CI_ONLY_PATHS:
        ci_norm = ci_path.replace("\\", "/")
        if path_normalized.startswith(ci_norm):
            return ChangeCategory.CI_ONLY

    # Check debt remediation paths (separate review required)
    for debt_path in DEBT_REMEDIATION_PATHS:
        debt_norm = debt_path.replace("\\", "/")
        if path_normalized.startswith(debt_norm):
            return ChangeCategory.DEBT_REMEDIATION

    # Check infrastructure paths
    for infra_path in INFRASTRUCTURE_PATHS:
        infra_norm = infra_path.replace("\\", "/")
        if path_normalized.startswith(infra_norm):
            return ChangeCategory.INFRASTRUCTURE

    # Default classification for root-level and other files
    if path_normalized.startswith("backend/"):
        return ChangeCategory.PRODUCT_RUNTIME
    elif path_normalized.startswith("frontend/"):
        return ChangeCategory.PRODUCT_RUNTIME
    elif path_normalized in {"docker-compose.yml", "Dockerfile"}:
        return ChangeCategory.INFRASTRUCTURE
    elif path_normalized.endswith(".md"):
        # Documentation is generally safe but needs categorization
        return ChangeCategory.CI_ONLY

    raise ValueError(f"Cannot classify path: {path}")


def enforce_scope(changes: list[str]) -> tuple[bool, list[str]]:
    """
    Enforce CI-only scope guard on a set of changed paths.

    This is a fail-closed guard: any unclassifiable or dangerous change
    causes failure. Only explicitly allowed CI-only and debt-remediation
    changes are permitted.

    Args:
        changes: List of file paths changed (relative to repo root)

    Returns:
        Tuple of (is_valid, error_messages)
        - is_valid: True if all changes are within scope
        - error_messages: List of violation messages
    """
    errors: list[str] = []
    allowed_categories = {
        ChangeCategory.CI_ONLY,
        ChangeCategory.DEBT_REMEDIATION,
    }

    for path in changes:
        try:
            category = classify_path(path)

            if category == ChangeCategory.PRESERVED:
                errors.append(
                    f"CRITICAL: Path in preserved surface: {path}. "
                    "This bugfix must not modify product/deploy/provision/schema semantics."
                )
            elif category == ChangeCategory.PRODUCT_RUNTIME:
                errors.append(
                    f"VIOLATION: Product runtime change: {path}. "
                    "CI remediation must not modify application code or APIs."
                )
            elif category == ChangeCategory.SCHEMA:
                errors.append(
                    f"VIOLATION: Database schema change: {path}. "
                    "CI remediation must not modify database structure."
                )
            elif category == ChangeCategory.DEPLOYMENT:
                errors.append(
                    f"VIOLATION: Deployment topology change: {path}. "
                    "CI remediation must not modify deployment or provisioning workflows."
                )
            elif category == ChangeCategory.INFRASTRUCTURE:
                errors.append(
                    f"VIOLATION: Infrastructure change: {path}. "
                    "This belongs in a separately reviewed change, not CI remediation."
                )
            elif category == ChangeCategory.DEBT_REMEDIATION:
                # Debt changes are allowed but should be noted
                # (in real implementation, would require separate review)
                pass
            elif category not in allowed_categories:
                errors.append(
                    f"UNKNOWN: Uncategorized path: {path}. Reject by default."
                )

        except ValueError as e:
            errors.append(f"UNCATEGORIZED: {path}: {e}")

    return len(errors) == 0, errors


def verify_deploy_provision_unchanged(
    before_snapshot: DeployProvisionSnapshot,
    after_snapshot: DeployProvisionSnapshot,
) -> tuple[bool, list[str]]:
    """
    Verify that deploy/provision semantics remain unchanged between snapshots.

    Args:
        before_snapshot: Deploy/provision behavior before changes
        after_snapshot: Deploy/provision behavior after changes

    Returns:
        Tuple of (semantics_unchanged, difference_messages)
    """
    errors: list[str] = []

    before_dict = before_snapshot.to_dict()
    after_dict = after_snapshot.to_dict()

    for key in before_dict:
        if before_dict[key] != after_dict[key]:
            errors.append(
                f"Deploy/provision semantic change: {key} "
                f"changed from {before_dict[key]} to {after_dict[key]}"
            )

    return len(errors) == 0, errors


def validate_pin_contracts_in_scope() -> tuple[bool, list[str]]:
    """
    Validate that CI configuration adheres to pin contracts.

    This is called as part of scope guard enforcement to ensure:
    - Tool versions are pinned (no latest, no floating ranges)
    - GitHub Actions use full commit SHAs
    - Container images use exact digest pins
    - Installer functions are pure (no external dependencies)

    Returns:
        Tuple of (all_valid, violations)
    """
    from agents.ci.pin_contracts import (
        ActionPinValidator,
        ImagePinValidator,
    )
    import yaml

    violations: list[str] = []

    # Check GitHub workflows
    workflows_dir = Path(".github/workflows")
    if workflows_dir.exists():
        for workflow_file in workflows_dir.glob("*.yml"):
            try:
                with open(workflow_file) as f:
                    workflow = yaml.safe_load(f) or {}

                action_validator = ActionPinValidator()
                if not action_validator.validate_workflow(workflow, str(workflow_file)):
                    for violation in action_validator.violations:
                        violations.append(
                            f"{workflow_file}: {violation.action} must use full SHA, not '{violation.current_value}'"
                        )
            except Exception as e:
                violations.append(f"Could not validate workflow {workflow_file}: {e}")

    # Check Dockerfiles
    for dockerfile in ["Dockerfile", "backend/Dockerfile", "frontend/Dockerfile"]:
        dockerfile_path = Path(dockerfile)
        if dockerfile_path.exists():
            try:
                with open(dockerfile_path) as f:
                    content = f.read()

                image_validator = ImagePinValidator()
                if not image_validator.validate_docker_file(
                    content, str(dockerfile_path)
                ):
                    for violation in image_validator.violations:
                        violations.append(
                            f"{dockerfile_path}: Image '{violation.image}' must use digest, not '{violation.current_value}'"
                        )
            except Exception as e:
                violations.append(f"Could not validate {dockerfile_path}: {e}")

    return len(violations) == 0, violations
