"""
Pin Authority — Single Source of Truth for All Exact Runtime, Tool, Browser, Service, and Image Versions

This module centralizes all pinned versions across the stack to ensure deterministic,
reproducible CI evaluation. Every version is exact SemVer (no floating ranges, no mutating tags).

Authority model:
  - Python runtime: maintained LTS or stable release per Python.org schedule
  - Node.js runtime: maintained LTS per nodejs.org schedule
  - PostgreSQL service: current major version per PostgreSQL.org schedule
  - Playwright & Chromium: pinned exact versions; browser installed via Playwright
  - Scanner tools: checksummed exact versions from official sources
  - Container base images: digest-pinned (not floating tags like 'latest' or 'slim')

Requirements:
  - All pins must be exact SemVer (e.g., "3.13.0", never "~3.13.0" or "latest")
  - Pins are the source of truth — align all references (Dockerfile, pyproject.toml,
    package.json, CI workflows, service declarations) to these values
  - Pin updates require:
    1. Change the value here
    2. Update all referencing files consistently
    3. Run pin drift tests to verify consistency
    4. Update pin update reason/date/source documentation
  - All pin changes must preserve product/runtime behavior (CI-only scope)
  - Never introduce a mutable tag (e.g., 'node:20-latest') or a floating range

References:
  - Python: https://www.python.org/downloads/ (current stable/maintenance releases)
  - Node.js: https://nodejs.org/en/about/previous-releases/ (LTS schedule)
  - PostgreSQL: https://www.postgresql.org/support/versioning/ (major version support)
  - Playwright: https://github.com/microsoft/playwright/releases
  - Scanner tools: official GitHub releases/checksums
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PinAuthority:
    """Immutable central authority for all pinned versions."""

    # =========================================================================
    # Python Runtime
    # =========================================================================
    # Authority: Python.org release schedule
    # Current stable: Python 3.13 (released Oct 2024, maintained until Oct 2029)
    # Selected patch: 3.13.0 (first release; updates available at python.org)
    python_runtime_version: str = "3.13.0"

    # Python version range in pyproject.toml requires-python (must include
    # the pinned runtime version). Used only for package metadata; CI uses exact.
    python_requires_minimum: str = "3.13.0"
    python_requires_maximum: str = "3.14.0"  # upper bound (exclusive in practice)

    # Ruff lint target version (must match or be <= the runtime version)
    # See: https://docs.astral.sh/ruff/configuration/#target-version
    ruff_target_version: str = "py313"

    # SonarCloud Python metadata (used in sonar-project.properties)
    # Must match or be <= the runtime version
    sonar_python_version: str = "3.13"

    # =========================================================================
    # Node.js Runtime
    # =========================================================================
    # Authority: nodejs.org LTS schedule
    # Current LTS: Node 24 (released Oct 2024, maintenance until Oct 2026)
    # Rationale: Phase 4 hardening decided to move from Node 20 LTS (EOL Mar 2026)
    #            to Node 24 LTS to ensure security patches through deployment horizon
    node_runtime_version: str = "24.11.0"

    # Node version range for package.json engines (lock down to major.minor;
    # CI will install the exact patch above)
    node_engines_minimum: str = "24.0.0"
    node_engines_maximum: str = "25.0.0"  # upper bound

    # =========================================================================
    # PostgreSQL Service
    # =========================================================================
    # Authority: PostgreSQL.org version support schedule
    # Current maintained: PostgreSQL 16 (released Oct 2023, maintained until Oct 2028)
    # Service image tag is PostgreSQL version only (registry pulls latest patch)
    postgres_major_version: str = "16"

    # Exact digest for production Dockerfile (docker pull postgres:16@sha256:...)
    # This will be set to the digest once the image scan (Task 3.18) completes.
    # For now, use the tag; task 3.18 will update this.
    postgres_service_image: str = "postgres:16"

    # =========================================================================
    # Playwright Browser Automation
    # =========================================================================
    # Authority: https://github.com/microsoft/playwright/releases
    # Current stable: 1.60.0 (released in recent timeline)
    # Note: Playwright is pinned in frontend/package.json + backend requirements
    playwright_package_version: str = "1.60.0"

    # Chromium browser revision installed by Playwright
    # This is managed by Playwright's browsers.json; we document the expected version.
    # See: https://github.com/microsoft/playwright/releases for browser version mapping
    chromium_version: str = (
        "1.62.0"  # Chromium major version bundled with Playwright 1.60.0
    )

    # =========================================================================
    # Security Scanner Tools (all exact versions + checksums)
    # =========================================================================
    #
    # EVERY value below is the version the pipeline ACTUALLY installs, and each
    # is annotated with the file that installs it ("Installed by:"). That
    # annotation is not decoration — tests/ci/test_toolchain_pins.py
    # (TestPinDriftDetection) parses those exact files and fails if any value
    # here disagrees, so this block cannot silently drift again.
    #
    # WHY THESE VALUES CHANGED: ten of the eleven pins here were stale, and the
    # stale record was NOT harmless. The previous values (ruff 0.8.0, pyright
    # 1.1.366, bandit 1.8.0, pip-audit 2.6.3, gitleaks 8.21.2, trivy 0.49.1,
    # grype 0.76.1, tflint 0.50.3, checkov 3.2.29, actionlint 1.7.1) described a
    # toolchain that has not been installed for some time — e.g. this module
    # claimed checkov 3.2.29 while ci.yml installs 3.2.200, and tflint 0.50.3
    # while ci.yml installs 0.64.0.
    #
    # The correction runs record -> reality, NOT reality -> record. The installed
    # versions are the deliberate ones: the Python tools carry documented
    # advisory rationale in requirements-dev.txt (pytest 9 forced pyright/bandit/
    # pip-audit forward as a set), and the downloaded binaries are pinned to
    # verified sha256 checksums in ci.yml. "Aligning" by editing ci.yml down to
    # these numbers would have reverted CVE fixes and invalidated every checksum
    # to fix a bookkeeping error. Note the module docstring's "align all
    # references to these values" therefore reads correctly only once this block
    # is itself correct — which is what the drift test now guarantees.

    # Ruff: Python linter/formatter
    # Authority: https://github.com/astral-sh/ruff/releases
    # Installed by: backend/requirements-dev.txt (`ruff==0.7.4`)
    ruff_version: str = "0.7.4"

    # Pyright: Python type checker
    # Authority: https://github.com/microsoft/pyright/releases
    # Installed by: backend/requirements-dev.txt (`pyright==1.1.384`)
    pyright_version: str = "1.1.384"

    # Bandit: Python security issue scanner
    # Authority: https://github.com/PyCQA/bandit/releases
    # Installed by: backend/requirements-dev.txt (`bandit[toml]==1.9.4`). The
    # [toml] extra is what lets `bandit -c pyproject.toml` read [tool.bandit].
    bandit_version: str = "1.9.4"

    # pip-audit: Python dependency vulnerability scanner
    # Authority: https://github.com/pypa/pip-audit/releases
    # Installed by: backend/requirements-dev.txt (`pip-audit==2.10.1`)
    pip_audit_version: str = "2.10.1"

    # npm: JavaScript package manager (installed with Node.js)
    # Pinned to Node runtime above; verified in package-lock.json

    # ESLint: JavaScript linter
    # Authority: frontend/package.json exact version
    # Installed by: frontend/package.json devDependencies (`"eslint": "9.39.4"`)
    # — the one scanner pin that was already correct.
    eslint_version: str = "9.39.4"

    # npm audit: Built into npm (uses node binary above)

    # gitleaks: Secret scanning
    # Authority: https://github.com/gitleaks/gitleaks/releases
    # Installed by: .github/workflows/ci.yml, checksummed download at TWO sites
    # (fast-checks and security-scan-secrets), both `version: v8.30.1`.
    gitleaks_version: str = "8.30.1"

    # Trivy: Multi-scanner (image/config/fs vulnerability scanning)
    # Authority: https://github.com/aquasecurity/trivy/releases
    # Installed by: workflow-level `env.TRIVY_VERSION`, deliberately duplicated
    # across THREE files (ci.yml, deploy.yml, _docker.yml) because workflow-level
    # `env:` cannot be shared across workflow files. All three must be bumped
    # together; the drift test checks all three.
    trivy_version: str = "0.69.3"

    # Grype: Software vulnerability scanner (cross-language supply chain)
    # Authority: https://github.com/anchore/grype/releases
    # Installed by: .github/workflows/_docker.yml (`env.GRYPE_VERSION: "0.75.0"`).
    # Note this is LOWER than the stale 0.76.1 recorded here before — the record
    # was ahead of reality for grype and behind it for the other nine, which is
    # what an unenforced "source of truth" looks like.
    grype_version: str = "0.75.0"

    # TFLint: Terraform linter
    # Authority: https://github.com/terraform-linters/tflint/releases
    # Installed by: .github/workflows/ci.yml security-scan-terraform
    # (`version: v0.64.0`, sha256-verified).
    tflint_version: str = "0.64.0"

    # Checkov: Infrastructure-as-code security scanning
    # Authority: https://github.com/bridgecrewio/checkov/releases
    # Installed by: .github/workflows/ci.yml security-scan-iac, as an EPHEMERAL
    # dependency — `uv run --no-sync --with checkov==3.2.200`. It is deliberately
    # NOT in requirements-dev.txt: it is only needed by that one job, so keeping
    # it out of backend/.venv avoids pulling checkov's large dependency tree into
    # every backend job's cached venv.
    checkov_version: str = "3.2.200"

    # Actionlint: GitHub Actions linter
    # Authority: https://github.com/rhysd/actionlint/releases
    # Installed by: .github/workflows/ci.yml fast-checks (`version: v1.7.12`,
    # sha256-verified against the release's own checksums file).
    actionlint_version: str = "1.7.12"

    # =========================================================================
    # Container Base Images (all digest-pinned)
    # =========================================================================

    # Backend Python runtime base (builder + runtime stages), digest-pinned.
    # Task 3.18 resolved this to an exact digest so the same bytes are built,
    # scanned, and shipped — a mutable tag could silently change between the
    # scan and the next build. Installed by: backend/Dockerfile (builder,
    # runtime stages).
    backend_python_base_image: str = (
        "python:3.13-slim-bookworm"
        "@sha256:b6bd71b0dd3811ddbcbc523ec2965fd1e1bcfdf7a20ab24679273d3bee726129"
    )

    # Backend pptx-builder Node.js base (for pptxgenjs installation),
    # digest-pinned. Installed by: backend/Dockerfile (pptx-builder stage).
    # Deliberately Node 20 (not the Node 24 runtime authority above) — see
    # test_backend_pptx_builder_image_is_exact's ABI-compatibility rationale.
    backend_pptx_builder_image: str = (
        "node:20-bookworm-slim"
        "@sha256:3d0f05455dea2c82e2f76e7e2543964c30f6b7d673fc1a83286736d44fe4c41c"
    )

    # Backend final runtime Node.js binary source (copied from image).
    # Same digest as pptx-builder to guarantee ABI compatibility.
    backend_node_runtime_image: str = backend_pptx_builder_image

    # Frontend builder & runtime base authority.
    # Format: node:24-bookworm-slim@sha256:DIGEST
    # Authority: Must match node_runtime_version (24.x) — see Task 3.15.
    # NOTE: frontend/Dockerfile currently pins node:20-bookworm-slim@sha256:...
    # (matching the backend Node toolchain, digest-pinned as part of Task 3.18's
    # scan/remediation). Migrating the frontend RUNTIME to Node 24 is a
    # behavior-affecting change tracked separately from Task 3.18, which is
    # scoped to eliminating existing High/Critical scanner findings in the
    # two production-context images as they are built today, not to bumping
    # a runtime major version. This field intentionally stays aspirational
    # (Task 3.15's authority) until that follow-on migration lands.
    frontend_base_image: str = "node:24-bookworm-slim"

    # =========================================================================
    # Pin Update History (for documentation)
    # =========================================================================
    last_updated: date = None  # Set to current date when updating pins
    update_reason: str = ""  # Document why pins were updated
    update_source: str = ""  # Link to advisory, release notes, or decision


# ============================================================================
# Factory and Accessors
# ============================================================================


def get_authority() -> PinAuthority:
    """Return the single immutable pin authority."""
    return PinAuthority()


def get_python_runtime() -> str:
    """Get exact Python runtime version (e.g., '3.13.0')."""
    return get_authority().python_runtime_version


def get_node_runtime() -> str:
    """Get exact Node.js runtime version (e.g., '24.11.0')."""
    return get_authority().node_runtime_version


def get_postgres_version() -> str:
    """Get PostgreSQL major version (e.g., '16')."""
    return get_authority().postgres_major_version


def get_playwright_version() -> str:
    """Get Playwright package version (e.g., '1.60.0')."""
    return get_authority().playwright_package_version


def get_chromium_version() -> str:
    """Get Chromium browser version bundled with Playwright."""
    return get_authority().chromium_version


def get_scanner_versions() -> dict:
    """Return all scanner tool versions keyed by tool name."""
    auth = get_authority()
    return {
        "ruff": auth.ruff_version,
        "pyright": auth.pyright_version,
        "bandit": auth.bandit_version,
        "pip-audit": auth.pip_audit_version,
        "eslint": auth.eslint_version,
        "gitleaks": auth.gitleaks_version,
        "trivy": auth.trivy_version,
        "grype": auth.grype_version,
        "tflint": auth.tflint_version,
        "checkov": auth.checkov_version,
        "actionlint": auth.actionlint_version,
    }


def get_container_base_images() -> dict:
    """Return all container base images keyed by component."""
    auth = get_authority()
    return {
        "backend-python": auth.backend_python_base_image,
        "backend-pptx-builder": auth.backend_pptx_builder_image,
        "backend-node-runtime": auth.backend_node_runtime_image,
        "frontend": auth.frontend_base_image,
    }


# ============================================================================
# Version String Validators (for CI pin drift detection)
# ============================================================================


def is_exact_semver(version_str: str) -> bool:
    """
    Verify version string is exact SemVer (no ranges, no floating tags).

    Valid: "3.13.0", "24.11.0", "1.60.0"
    Invalid: "~3.13.0", "^3.13.0", "latest", "3.13.x", ">=3.13.0"
    """
    import re

    # Exact SemVer: major.minor.patch (optionally with pre-release and build metadata)
    # Reject: ranges, wildcards, pre-release/build unless part of exact release tag
    pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*)?(?:\+[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*)?$"
    return bool(re.match(pattern, version_str))


def is_exact_image_tag(image_str: str) -> bool:
    """
    Verify image reference is exact (digest-pinned or specific tag, not 'latest'/'slim'/vague).

    Valid: "postgres:16", "python:3.13-slim-bookworm", "image:tag@sha256:abc123..."
    Invalid: "postgres", "postgres:latest", "latest", "slim" (tag-only, ambiguous)
    """
    # Must have at least repo:tag format; tags like "latest" are rejected in policy
    if not image_str or ":" not in image_str:
        return False
    # Reject vague tags
    vague_tags = {"latest", "slim", "alpine", "bookworm", "lts"}
    parts = image_str.split(":")
    tag_part = parts[-1].split("@")[0]  # tag before optional @digest
    if tag_part in vague_tags:
        return False
    return True


if __name__ == "__main__":
    # Print current pin authority for documentation
    auth = get_authority()
    print("=== Pin Authority ===")
    print(f"Python runtime: {auth.python_runtime_version}")
    print(f"Node.js runtime: {auth.node_runtime_version}")
    print(f"PostgreSQL: {auth.postgres_major_version}")
    print(f"Playwright: {auth.playwright_package_version}")
    print(f"Chromium: {auth.chromium_version}")
    print("\n=== Scanner Versions ===")
    for tool, version in sorted(get_scanner_versions().items()):
        print(f"  {tool}: {version}")
    print("\n=== Container Base Images ===")
    for component, image in sorted(get_container_base_images().items()):
        print(f"  {component}: {image}")
