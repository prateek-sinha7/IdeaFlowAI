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

    # =========================================================================
    # Node.js Runtime
    # =========================================================================
    # Authority: nodejs.org LTS schedule
    # Current LTS: Node 24 (released Oct 2024, maintenance until Oct 2026)
    # Rationale: Phase 4 hardening decided to move from Node 20 LTS (EOL Mar 2026)
    #            to Node 24 LTS to ensure security patches through deployment horizon
    # Installed by: .github/actions/setup-frontend/action.yml (`node-version`
    # input default, passed straight to actions/setup-node) and
    # frontend/Dockerfile (the tag of frontend_base_image below);
    # frontend/package.json engines.node must bound it. All three are asserted
    # by tests/unit/tools/ci/test_toolchain_pins.py (F-07).
    node_runtime_version: str = "24.11.0"

    # Node version range for package.json engines (lock down to major.minor;
    # CI will install the exact patch above)
    node_engines_minimum: str = "24.0.0"
    node_engines_maximum: str = "25.0.0"  # upper bound

    # =========================================================================
    # uv (Python package/project manager)
    # =========================================================================
    # Authority: https://github.com/astral-sh/uv/releases
    # Installed by: .github/actions/setup-backend/action.yml (`astral-sh/setup-uv`
    # `version:` input). Without that input setup-uv looked for a uv.toml /
    # pyproject.toml at the REPO root (the backend project lives in backend/),
    # found neither, and fell back to "latest" — so a new uv release could change
    # every backend CI job with no commit here (CI run 36718805906 got 0.12.21).
    # 0.12.21 is the version that run resolved and installed successfully.
    uv_version: str = "0.12.21"

    # =========================================================================
    # PostgreSQL Service
    # =========================================================================
    # Authority: PostgreSQL.org version support schedule
    # Current maintained: PostgreSQL 16 (released Oct 2023, maintained until Oct 2028)
    postgres_major_version: str = "16"

    # The CI service container for the backend-postgres job: a patch-level tag,
    # NOT a digest. Must equal ci.yml `services.postgres.image` and
    # ci/toolchain-lock.json runtime_pins.postgresql.image (asserted by
    # test_postgres_service_image_matches_ci_when_backend_postgres_runs). A
    # digest pin is stronger and remains the target.
    postgres_service_image: str = "postgres:16.10-bookworm"

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
    # Installed by: .github/workflows/ci.yml, checksummed download in the
    # `security` matrix leg `secrets`. This said "TWO sites (fast-checks and
    # security-scan-secrets)"; neither job exists — single-owner consolidation
    # merged them into the one `security` matrix, which is also why there is now
    # only one install site to keep in step with this pin.
    gitleaks_version: str = "8.30.1"

    # Trivy: Multi-scanner (image/config/fs vulnerability scanning)
    # Authority: https://github.com/aquasecurity/trivy/releases
    # Installed by: workflow-level `env.TRIVY_VERSION`, deliberately duplicated
    # across TWO files (ci.yml, deploy.yml) because workflow-level `env:` cannot
    # be shared across workflow files. Both must be bumped together; the drift
    # test checks both. There was a third copy in _docker.yml until that
    # workflow was deleted for having no caller.
    trivy_version: str = "0.69.3"

    # Grype: Software vulnerability scanner (cross-language supply chain)
    # Authority: https://github.com/anchore/grype/releases
    # Installed by: .github/workflows/ci.yml (`env.GRYPE_VERSION: "0.119.0"`),
    # via ./.github/actions/install-checksummed-tool. The declaration used to be
    # read from _docker.yml, which also installed grype by unverified `curl`;
    # both went away with that workflow.
    # F-37: bumped from 0.75.0, whose schema-v5 vulnerability DB is no longer
    # rebuilt upstream — the scanner refused to load a 28-week-old DB and every
    # container-scan[*]/grype signal failed on an empty report.
    grype_version: str = "0.119.0"

    # TFLint: Terraform linter
    # Authority: https://github.com/terraform-linters/tflint/releases
    # Installed by: .github/workflows/ci.yml, the `security` matrix leg `iac`
    # (was `security-scan-terraform`, a job that no longer exists).
    tflint_version: str = "0.64.0"

    # Terraform CLI (static use only: fmt / init -backend=false / validate)
    # Authority: https://github.com/hashicorp/terraform/releases
    # Installed by: .github/workflows/ci.yml, the `security` matrix leg `iac`
    # (hashicorp/setup-terraform `terraform_version:` input). Recorded in
    # ci/toolchain-lock.json pinned_action.terraform. Deliberately NOT part of
    # get_scanner_versions(): terraform is a CLI the scanners run against, not a
    # scanner, and that accessor's key set is pinned by its own test.
    terraform_version: str = "1.9.8"

    # Checkov: Infrastructure-as-code security scanning
    # Authority: https://github.com/bridgecrewio/checkov/releases
    # Installed by: .github/workflows/ci.yml, the `security` matrix leg `iac`
    # (was `security-scan-iac`, a job that no longer exists), via
    # .github/scripts/ci-iac-scan.sh as `uv tool run --from checkov==<this>` in
    # its own isolated environment (checkov pins boto3, which would make
    # backend/uv.lock unresolvable). It is deliberately NOT in
    # requirements-dev.txt: it is only needed by that one job. Only checkov
    # itself is pinned here; its transitive dependencies are resolved at run
    # time and are not locked.
    checkov_version: str = "3.2.200"

    # Actionlint: GitHub Actions linter
    # Authority: https://github.com/rhysd/actionlint/releases
    # Installed by: .github/workflows/ci.yml, the repo-static job
    # (install-checksummed-tool, version from env ACTIONLINT_VERSION,
    # sha256-verified against the release's own checksums file). A job named
    # fast-checks once installed it; that job no longer exists.
    actionlint_version: str = "1.7.12"

    # ShellCheck: shell static analysis (repo-static/shellcheck)
    # Authority: https://github.com/koalaman/shellcheck/releases
    # Installed by: .github/workflows/ci.yml, the repo-static job
    # (install-checksummed-tool, version from env SHELLCHECK_VERSION, archive
    # member shellcheck-v<version>/shellcheck). The project publishes NO
    # checksums file, so the sha256 is the GitHub release-asset digest, cross-
    # checked against a locally recomputed hash; see ci/toolchain-lock.json.
    # .github/scripts/ci-shellcheck.sh fails if the installed binary differs.
    shellcheck_version: str = "0.11.0"

    # GitHub-hosted runner image label used by every `runs-on`.
    # Installed by: every runs-on in .github/workflows/*.yml (an exact label, never
    # the floating `ubuntu-latest`). Tools the workflows rely on but do not install
    # come from this image: jq and the AWS CLI v2 (the ssm-run composite and the
    # deploy/provision/cognito scripts), gh (release.yml), bash and docker compose
    # (repo-static), git, curl, sudo, tar and unzip. A runner-image bump is a
    # reviewed change to this field, ci/toolchain-lock.json and every runs-on.
    runner_image: str = "ubuntu-24.04"

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

    # Frontend builder & runtime base, digest-pinned.
    # Installed by: frontend/Dockerfile (deps, builder, runner stages).
    # The tag names the exact node_runtime_version, so the image runs the same
    # Node that setup-frontend installs in CI; the digest pins the bytes.
    # Provenance: Docker Hub tag API
    # https://hub.docker.com/v2/repositories/library/node/tags/24.11.0-bookworm-slim
    # field `digest` (the multi-arch OCI image index digest, last pushed
    # 2025-11-04). Re-resolve it from the same endpoint when bumping the tag.
    frontend_base_image: str = (
        "node:24.11.0-bookworm-slim"
        "@sha256:76d0ed0ed93bed4f4376211e9d8fddac4d8b3fbdb54cc45955696001a3c91152"
    )

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
