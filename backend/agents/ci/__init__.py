"""CI pipeline remediation agents and utilities.

This module provides pure-policy primitives for CI pipeline remediation without
changing deployment, provisioning, or product behavior.

Key components:
- signal_registry: Authoritative registry of CI signals with semantic deduplication
- evidence_manifest: Evidence binding producer outputs to evaluation SHA
- scanner_policy: Zero High/Critical vulnerability policy enforcement
"""

from .signal_registry import SIGNAL_REGISTRY, Signal, SignalRegistry
from .evidence_manifest import EvidenceManifest, FileRecord
from .scanner_policy import ScannerPolicy, Finding, Severity

# Import other existing modules if they exist
try:
    from .scope_guard import (
        ChangeCategory,
        CURRENT_DEPLOY_PROVISION_SNAPSHOT,
        DeployProvisionSnapshot,
        classify_path,
        enforce_scope,
        verify_deploy_provision_unchanged,
    )
except ImportError:
    pass

try:
    from .evaluation_identity import (
        EvaluationEventType,
        EvaluationIdentity,
        SupersessionGroup,
        compute_identity,
        classify_supersession_group,
        can_supersede,
        are_same_intent,
        is_stale_sha,
    )
except ImportError:
    pass

try:
    from .concurrency_policy import (
        classify_event,
        should_cancel_previous,
        verify_evaluation_sha,
    )
except ImportError:
    pass

try:
    from .offline_guards import (
        OfflineGuardViolation,
        is_ci_offline_enabled,
        require_mandatory_offline,
        no_credentials,
        no_egress,
        require_all_guards,
        BLOCKED_PROVIDER_MODULES,
        CREDENTIAL_ENV_PATTERNS,
        NETWORK_MODULES,
    )
except ImportError:
    pass

try:
    from .pin_authority import (
        PinAuthority,
        get_authority,
        get_python_runtime,
        get_node_runtime,
        get_postgres_version,
        get_playwright_version,
        get_chromium_version,
        get_scanner_versions,
        get_container_base_images,
        is_exact_semver,
        is_exact_image_tag,
    )
except ImportError:
    pass

__all__ = [
    "SIGNAL_REGISTRY",
    "Signal",
    "SignalRegistry",
    "EvidenceManifest",
    "FileRecord",
    "ScannerPolicy",
    "Finding",
    "Severity",
]
