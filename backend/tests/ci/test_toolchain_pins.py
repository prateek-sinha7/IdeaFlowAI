"""
Pin Authority Tests — Validate exact runtime, tool, browser, service, and image pins.

This test suite validates:
1. All pins in pin_authority.py are exact SemVer (no floating ranges, no mutable tags)
2. Pin format consistency across types (Python, Node, PostgreSQL, scanners, images)
3. Pin alignment with references in Dockerfile, pyproject.toml, package.json, workflows
4. No mutable tags or dangerous patterns (e.g., 'latest', '^', '~', 'slim' alone)
5. Scanner tool versions are documented and exact
6. Image references are either digest-pinned or specific (non-vague) tags
7. Pin accessor functions return correct values
8. Pin validators reject invalid formats

This is a CI-only test; product behavior is not changed by pin values.
"""

import pytest
import json
import re
import yaml
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import fields

# Import the pin authority and validator functions
from agents.ci.pin_authority import (
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


class TestPinAuthorityExactness:
    """Test that all pins are exact (no floating ranges, no mutable tags)."""

    def test_python_runtime_is_exact_semver(self):
        """Python runtime must be exact SemVer like '3.13.0'."""
        auth = get_authority()
        assert is_exact_semver(
            auth.python_runtime_version
        ), f"Python runtime '{auth.python_runtime_version}' is not exact SemVer"

    def test_python_requires_minimum_is_exact_semver(self):
        """Python requires-python minimum must be exact SemVer."""
        auth = get_authority()
        assert is_exact_semver(
            auth.python_requires_minimum
        ), f"Python requires-minimum '{auth.python_requires_minimum}' is not exact SemVer"

    def test_python_requires_maximum_is_exact_semver(self):
        """Python requires-python maximum must be exact SemVer."""
        auth = get_authority()
        assert is_exact_semver(
            auth.python_requires_maximum
        ), f"Python requires-maximum '{auth.python_requires_maximum}' is not exact SemVer"

    def test_node_runtime_is_exact_semver(self):
        """Node.js runtime must be exact SemVer like '24.11.0'."""
        auth = get_authority()
        assert is_exact_semver(
            auth.node_runtime_version
        ), f"Node runtime '{auth.node_runtime_version}' is not exact SemVer"

    def test_node_engines_minimum_is_exact_semver(self):
        """Node.js engines minimum must be exact SemVer."""
        auth = get_authority()
        assert is_exact_semver(
            auth.node_engines_minimum
        ), f"Node engines-minimum '{auth.node_engines_minimum}' is not exact SemVer"

    def test_node_engines_maximum_is_exact_semver(self):
        """Node.js engines maximum must be exact SemVer."""
        auth = get_authority()
        assert is_exact_semver(
            auth.node_engines_maximum
        ), f"Node engines-maximum '{auth.node_engines_maximum}' is not exact SemVer"

    def test_playwright_version_is_exact_semver(self):
        """Playwright package version must be exact SemVer."""
        auth = get_authority()
        assert is_exact_semver(
            auth.playwright_package_version
        ), f"Playwright version '{auth.playwright_package_version}' is not exact SemVer"

    def test_chromium_version_is_exact_semver(self):
        """Chromium browser version must be exact SemVer."""
        auth = get_authority()
        assert is_exact_semver(
            auth.chromium_version
        ), f"Chromium version '{auth.chromium_version}' is not exact SemVer"

    def test_all_scanner_versions_are_exact_semver(self):
        """All scanner tool versions must be exact SemVer."""
        auth = get_authority()
        scanner_fields = [
            "ruff_version",
            "pyright_version",
            "bandit_version",
            "pip_audit_version",
            "eslint_version",
            "gitleaks_version",
            "trivy_version",
            "grype_version",
            "tflint_version",
            "checkov_version",
            "actionlint_version",
        ]
        for field_name in scanner_fields:
            version = getattr(auth, field_name)
            assert is_exact_semver(
                version
            ), f"{field_name} '{version}' is not exact SemVer"


class TestPinAuthorityImages:
    """Test that container image references use exact tags or digests."""

    def test_backend_python_base_image_is_exact(self):
        """Backend Python base image must be tagged (not 'latest')."""
        auth = get_authority()
        # Must include tag like 'python:3.13-slim-bookworm', not just 'python'
        assert (
            ":" in auth.backend_python_base_image
        ), "Backend Python image must include tag"
        assert (
            "latest" not in auth.backend_python_base_image
        ), "Backend Python image must not use 'latest' tag"

    def test_backend_pptx_builder_image_is_exact(self):
        """Backend pptx-builder image must include version tag."""
        auth = get_authority()
        assert (
            ":" in auth.backend_pptx_builder_image
        ), "Backend pptx-builder image must include tag"
        assert (
            "node:20" in auth.backend_pptx_builder_image
        ), "Backend pptx-builder must use Node 20 (not Node 24 runtime)"

    def test_backend_node_runtime_image_is_exact(self):
        """Backend Node.js runtime source image must be exact."""
        auth = get_authority()
        assert (
            ":" in auth.backend_node_runtime_image
        ), "Backend Node runtime image must include tag"
        # Should match pptx-builder for ABI compatibility
        assert (
            auth.backend_node_runtime_image == auth.backend_pptx_builder_image
        ), "Backend Node runtime image must match pptx-builder for ABI compatibility"

    def test_frontend_base_image_matches_node_runtime(self):
        """Frontend base image must be Node 24 to match node_runtime_version."""
        auth = get_authority()
        assert (
            "node:24" in auth.frontend_base_image
        ), f"Frontend must use Node 24, got {auth.frontend_base_image}"
        assert ":" in auth.frontend_base_image, "Frontend image must include tag"


class TestPinAuthorityConsistency:
    """Test consistency between related pins."""

    def test_python_version_consistency(self):
        """Python runtime, requires, and ruff target must be consistent."""
        auth = get_authority()
        runtime_parts = auth.python_runtime_version.split(".")
        requires_parts = auth.python_requires_minimum.split(".")

        # Runtime and requires-minimum should match major.minor
        assert (
            runtime_parts[0] == requires_parts[0]
        ), f"Python runtime major {runtime_parts[0]} must match requires-minimum {requires_parts[0]}"
        assert (
            runtime_parts[1] == requires_parts[1]
        ), f"Python runtime minor {runtime_parts[1]} must match requires-minimum {requires_parts[1]}"

        # Ruff target must map to runtime version
        expected_ruff_target = f"py{runtime_parts[0]}{runtime_parts[1]}"
        assert (
            auth.ruff_target_version == expected_ruff_target
        ), f"Ruff target {auth.ruff_target_version} must match Python {auth.python_runtime_version} ({expected_ruff_target})"

    def test_node_version_consistency(self):
        """Node.js runtime and engines must be consistent."""
        auth = get_authority()
        runtime_parts = auth.node_runtime_version.split(".")
        engines_min_parts = auth.node_engines_minimum.split(".")
        engines_max_parts = auth.node_engines_maximum.split(".")

        # Runtime major must match engines minimum major
        assert (
            runtime_parts[0] == engines_min_parts[0]
        ), f"Node runtime major {runtime_parts[0]} must match engines-minimum {engines_min_parts[0]}"

        # Engines maximum must be one major version higher than minimum
        expected_max_major = int(engines_min_parts[0]) + 1
        assert (
            int(engines_max_parts[0]) == expected_max_major
        ), f"Node engines-maximum {engines_max_parts[0]} should be major+1 of engines-minimum {engines_min_parts[0]}"

    def test_node_version_in_frontend_image(self):
        """Frontend image major version must match node_runtime_version major."""
        auth = get_authority()
        runtime_major = auth.node_runtime_version.split(".")[0]
        assert (
            f"node:{runtime_major}" in auth.frontend_base_image
        ), f"Frontend image must use Node {runtime_major} to match runtime {auth.node_runtime_version}"

    def test_ruff_target_is_valid_python_version(self):
        """Ruff target version must be valid (py310, py311, py312, py313, etc.)."""
        auth = get_authority()
        assert auth.ruff_target_version.startswith(
            "py"
        ), f"Ruff target must start with 'py', got {auth.ruff_target_version}"
        # Extract version number (e.g., 313 from py313)
        version_part = auth.ruff_target_version[2:]
        assert (
            version_part.isdigit() and len(version_part) >= 2
        ), f"Ruff target must have numeric version, got {auth.ruff_target_version}"


class TestPinAuthorityAccessors:
    """Test accessor functions return correct values."""

    def test_get_python_runtime(self):
        """get_python_runtime() must return exact SemVer."""
        version = get_python_runtime()
        assert is_exact_semver(version), f"Python runtime {version} is not exact SemVer"
        assert version == get_authority().python_runtime_version

    def test_get_node_runtime(self):
        """get_node_runtime() must return exact SemVer."""
        version = get_node_runtime()
        assert is_exact_semver(version), f"Node runtime {version} is not exact SemVer"
        assert version == get_authority().node_runtime_version

    def test_get_postgres_version(self):
        """get_postgres_version() must return major version."""
        version = get_postgres_version()
        assert version == get_authority().postgres_major_version
        # Should be a valid postgres major version
        assert (
            version.isdigit() and int(version) >= 10
        ), f"PostgreSQL version must be major only (e.g., '16'), got {version}"

    def test_get_playwright_version(self):
        """get_playwright_version() must return exact SemVer."""
        version = get_playwright_version()
        assert is_exact_semver(
            version
        ), f"Playwright version {version} is not exact SemVer"
        assert version == get_authority().playwright_package_version

    def test_get_chromium_version(self):
        """get_chromium_version() must return exact SemVer."""
        version = get_chromium_version()
        assert is_exact_semver(
            version
        ), f"Chromium version {version} is not exact SemVer"
        assert version == get_authority().chromium_version

    def test_get_scanner_versions_returns_dict(self):
        """get_scanner_versions() must return dict of tool:version pairs."""
        scanners = get_scanner_versions()
        assert isinstance(scanners, dict), "Scanners must be a dict"
        expected_tools = {
            "ruff",
            "pyright",
            "bandit",
            "pip-audit",
            "eslint",
            "gitleaks",
            "trivy",
            "grype",
            "tflint",
            "checkov",
            "actionlint",
        }
        assert (
            set(scanners.keys()) == expected_tools
        ), f"Scanner keys {set(scanners.keys())} must match {expected_tools}"

        # All versions must be exact SemVer
        for tool, version in scanners.items():
            assert is_exact_semver(
                version
            ), f"Scanner {tool} version '{version}' is not exact SemVer"

    def test_get_container_base_images_returns_dict(self):
        """get_container_base_images() must return dict of component:image pairs."""
        images = get_container_base_images()
        assert isinstance(images, dict), "Images must be a dict"
        expected_components = {
            "backend-python",
            "backend-pptx-builder",
            "backend-node-runtime",
            "frontend",
        }
        assert (
            set(images.keys()) == expected_components
        ), f"Image components {set(images.keys())} must match {expected_components}"

        # All images must have tags
        for component, image in images.items():
            assert ":" in image, f"{component} image must include tag, got {image}"


class TestPinAuthorityValidators:
    """Test version format validators."""

    def test_is_exact_semver_valid_versions(self):
        """is_exact_semver() accepts valid SemVer."""
        valid_versions = [
            "3.13.0",
            "24.11.0",
            "1.60.0",
            "0.8.0",
            "16.3.4",
            "1.8.0",
            "8.21.2",
            "0.49.1",
            "0.76.1",
            "0.50.3",
            "3.2.29",
            "1.7.1",
        ]
        for version in valid_versions:
            assert is_exact_semver(
                version
            ), f"is_exact_semver({version}) should return True"

    def test_is_exact_semver_rejects_floating_ranges(self):
        """is_exact_semver() rejects ~, ^, >, <, >=, <=, * ranges."""
        invalid_versions = [
            "~3.13.0",
            "^24.11.0",
            "1.60.*",
            ">=0.8.0",
            "<=1.60.0",
            ">0.49.0",
            "<0.76.2",
            "1.60.0 || 2.0.0",
        ]
        for version in invalid_versions:
            assert not is_exact_semver(
                version
            ), f"is_exact_semver({version}) should return False (floating range)"

    def test_is_exact_semver_rejects_vague_tags(self):
        """is_exact_semver() rejects 'latest', 'stable', etc."""
        invalid_versions = [
            "latest",
            "stable",
            "main",
            "develop",
            "lts",
        ]
        for version in invalid_versions:
            assert not is_exact_semver(
                version
            ), f"is_exact_semver({version}) should return False (vague tag)"

    def test_is_exact_image_tag_valid_tags(self):
        """is_exact_image_tag() accepts specific tags."""
        valid_images = [
            "python:3.13-slim-bookworm",
            "node:24-bookworm-slim",
            "postgres:16",
            "python:3.13-slim-bookworm@sha256:abc123def456",
            "node:20-bookworm-slim@sha256:fedcba654321",
        ]
        for image in valid_images:
            assert is_exact_image_tag(
                image
            ), f"is_exact_image_tag({image}) should return True"

    def test_is_exact_image_tag_rejects_vague_tags(self):
        """is_exact_image_tag() rejects vague/mutable tags."""
        invalid_images = [
            "postgres:latest",
            "python:latest",
            "node:latest",
            "image",  # no tag
            "python:slim",  # tag alone
            "node",  # no tag
        ]
        for image in invalid_images:
            assert not is_exact_image_tag(
                image
            ), f"is_exact_image_tag({image}) should return False (vague tag)"


class TestPinAuthorityImmutability:
    """Test that PinAuthority is immutable (frozen dataclass)."""

    def test_pin_authority_is_frozen(self):
        """PinAuthority dataclass must be frozen (immutable)."""
        auth = get_authority()
        # Try to modify a field; should raise FrozenInstanceError
        with pytest.raises((TypeError, AttributeError, RuntimeError)):
            auth.python_runtime_version = "3.14.0"

    def test_get_authority_returns_equal_instance(self):
        """Multiple calls to get_authority() should return equal instances."""
        auth1 = get_authority()
        auth2 = get_authority()
        # Should be equal (frozen dataclass equality check)
        assert auth1 == auth2, "get_authority() must return equal instances"


def test_python_version_bounds_property():
    """Property: Python requires-minimum <= runtime < requires-maximum."""
    auth = get_authority()
    runtime_parts = tuple(map(int, auth.python_runtime_version.split(".")))
    min_parts = tuple(map(int, auth.python_requires_minimum.split(".")))
    max_parts = tuple(map(int, auth.python_requires_maximum.split(".")))

    assert (
        min_parts <= runtime_parts
    ), f"Python {runtime_parts} must be >= minimum {min_parts}"
    assert (
        runtime_parts < max_parts
    ), f"Python {runtime_parts} must be < maximum {max_parts}"


def test_node_version_bounds_property():
    """Property: Node.js requires-minimum <= runtime < requires-maximum."""
    auth = get_authority()
    runtime_parts = tuple(map(int, auth.node_runtime_version.split(".")))
    min_parts = tuple(map(int, auth.node_engines_minimum.split(".")))
    max_parts = tuple(map(int, auth.node_engines_maximum.split(".")))

    assert (
        min_parts <= runtime_parts
    ), f"Node {runtime_parts} must be >= minimum {min_parts}"
    assert (
        runtime_parts < max_parts
    ), f"Node {runtime_parts} must be < maximum {max_parts}"


class TestPinAuthorityFieldCoverage:
    """Test that all fields in PinAuthority are documented and used."""

    def test_all_dataclass_fields_are_strings_or_date(self):
        """All PinAuthority fields must be str or date."""
        auth = get_authority()
        for field in fields(PinAuthority):
            value = getattr(auth, field.name)
            # last_updated can be None or date, others must be str
            if field.name == "last_updated":
                assert value is None or hasattr(
                    value, "year"
                ), f"Field {field.name} must be None or date"
            elif field.name == "update_reason" or field.name == "update_source":
                assert isinstance(value, str), f"Field {field.name} must be str"
            else:
                assert isinstance(
                    value, str
                ), f"Field {field.name} must be str, got {type(value)}"

    def test_no_empty_version_fields(self):
        """No version field should be empty."""
        auth = get_authority()
        version_fields = [
            f.name
            for f in fields(PinAuthority)
            if f.name.endswith("_version") or f.name.endswith("_image")
        ]
        for field_name in version_fields:
            value = getattr(auth, field_name)
            assert value, f"Version field {field_name} must not be empty"


# ============================================================================
# Source-file readers for drift detection
#
# TestPinDriftDetection below compares pin_authority.py against the files that
# ACTUALLY install each tool. Before this existed, that class asserted only that
# the module had a docstring and that its dict keys were spelled correctly — it
# never opened a single source file, so ten of the eleven scanner pins drifted
# undetected (checkov recorded 3.2.29 while ci.yml installed 3.2.200, tflint
# 0.50.3 vs 0.64.0, and so on). A "source of truth" nothing compares against is
# just a comment.
# ============================================================================

REPO_ROOT = Path(__file__).parents[3]
BACKEND_DIR = Path(__file__).parents[2]


def _read(relative_path: str) -> str:
    """Read a repo-relative file as text, failing loudly if it moved."""
    path = REPO_ROOT / relative_path
    assert path.exists(), (
        f"{relative_path} not found — pin drift detection cannot run. "
        f"If the file moved, update this test rather than deleting the check."
    )
    return path.read_text(encoding="utf-8")


def _requirement_version(requirements_text: str, package: str) -> str:
    """
    Extract the pinned version of `package` from a requirements file.

    Tolerates extras (`bandit[toml]==1.9.4`) and ignores comment lines so a
    version mentioned in prose cannot be mistaken for the pin.
    """
    pattern = rf"^{re.escape(package)}(?:\[[^\]]*\])?==" r"([0-9][0-9A-Za-z.\-]*)\s*$"
    matches = re.findall(pattern, requirements_text, flags=re.MULTILINE)
    assert matches, f"No `{package}==<version>` pin found in requirements file"
    assert len(set(matches)) == 1, (
        f"`{package}` is pinned to conflicting versions {sorted(set(matches))} "
        f"in the same requirements file"
    )
    return matches[0]


def _checksummed_tool_versions(workflow_text: str, tool: str) -> List[str]:
    """
    Extract every version passed to install-checksummed-tool for `tool`.

    Returns ALL occurrences, because a tool installed at several sites can be
    bumped at only some of them, and that partial bump is the drift this catches.

    Parses the YAML rather than pattern-matching the file text. The previous
    regex was `name:\\s*<tool>[\\s\\S]*?version:\\s*...`, whose lazy middle
    happily crossed step boundaries: a step *named* "gitleaks detect (full
    history)" matched the `name:` anchor, and the scan then ran on to whatever
    `version:` input appeared next — which is how this reported gitleaks as
    version 1.9.8, the Terraform CLI's version. Structural lookup cannot make
    that mistake.
    """
    workflow = yaml.safe_load(workflow_text) or {}
    versions: List[str] = []

    # Workflow-level env, used to resolve `version: ${{ env.FOO }}`.
    env_block = {str(k): str(v) for k, v in (workflow.get("env") or {}).items()}

    for job in (workflow.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses") or ""
            if "install-checksummed-tool" not in str(uses):
                continue
            with_block = step.get("with") or {}
            if str(with_block.get("name", "")) != tool:
                continue

            raw = str(with_block.get("version", ""))
            match = re.fullmatch(r"\$\{\{\s*env\.(\w+)\s*\}\}", raw.strip())
            if match:
                raw = env_block.get(match.group(1), "")
            versions.append(raw.strip().lstrip("v"))

    return [v for v in versions if v]


def _workflow_env_version(workflow_text: str, env_key: str) -> List[str]:
    """Extract every workflow-level `env:` value for `env_key`."""
    return re.findall(
        rf'{re.escape(env_key)}:\s*"([0-9][0-9A-Za-z.\-]*)"', workflow_text
    )


class TestPinDriftDetection:
    """
    Assert pin_authority.py matches the files that actually install each tool.

    Each test names the installing file. When one of these fails, the fix is to
    make BOTH sides agree — and to decide deliberately which side is wrong. A
    scanner version in ci.yml is usually paired with a verified sha256, so the
    record here is normally the side to correct.
    """

    def test_pin_documentation_present(self):
        """Pin authority module must have documentation."""
        from agents.ci.pin_authority import PinAuthority as PA

        assert PA.__doc__ is not None, "PinAuthority must have docstring"

    def test_scanner_versions_coverage(self):
        """All scanners mentioned in design must be in pin authority."""
        required_scanners = {
            "ruff",
            "pyright",
            "bandit",
            "pip-audit",
            "eslint",
            "gitleaks",
            "trivy",
            "grype",
            "tflint",
            "checkov",
            "actionlint",
        }
        scanners = get_scanner_versions()
        assert (
            set(scanners.keys()) == required_scanners
        ), f"Must have all scanners: {required_scanners}"

    # ---- Python tools installed from backend/requirements-dev.txt ----------

    @pytest.mark.parametrize(
        ("package", "authority_field"),
        [
            ("ruff", "ruff_version"),
            ("pyright", "pyright_version"),
            ("bandit", "bandit_version"),
            ("pip-audit", "pip_audit_version"),
            ("playwright", "playwright_package_version"),
        ],
    )
    def test_python_tool_matches_requirements_dev(self, package, authority_field):
        """Python tool pins must match backend/requirements-dev.txt exactly."""
        installed = _requirement_version(_read("backend/requirements-dev.txt"), package)
        recorded = getattr(get_authority(), authority_field)
        assert recorded == installed, (
            f"pin drift: pin_authority.{authority_field}={recorded!r} but "
            f"backend/requirements-dev.txt installs {package}=={installed}"
        )

    # ---- eslint comes from frontend/package.json --------------------------

    def test_eslint_matches_frontend_package_json(self):
        """eslint pin must match frontend/package.json devDependencies."""
        data = json.loads(_read("frontend/package.json"))
        installed = data.get("devDependencies", {}).get("eslint", "")
        assert installed, "eslint not found in frontend/package.json devDependencies"
        assert is_exact_semver(installed), (
            f"frontend/package.json pins eslint to {installed!r}, which is not an "
            f"exact version — the pin authority cannot track a floating range"
        )
        recorded = get_authority().eslint_version
        assert recorded == installed, (
            f"pin drift: pin_authority.eslint_version={recorded!r} but "
            f"frontend/package.json installs eslint {installed}"
        )

    # ---- Checksummed binaries downloaded in ci.yml -------------------------

    # NOTE ON THE PREVIOUS VERSION OF THESE TESTS
    #
    # They read `.github/workflows/ci-remediation-jobs.yml` and called
    # `pytest.skip` whenever a tool was not found there — including the message
    # "No install-checksummed-tool block for tflint", which was true and was
    # exactly the defect the test existed to catch. A contract test that skips
    # when the contract is unmet asserts nothing. These now fail instead, and
    # they read ci.yml, which is the single evaluator.

    @pytest.mark.parametrize(
        ("tool", "authority_field"),
        [
            ("actionlint", "actionlint_version"),
            ("gitleaks", "gitleaks_version"),
        ],
    )
    def test_checksummed_tool_matches_ci_workflow(self, tool, authority_field):
        """Checksummed binary versions in ci.yml must match the pin authority."""
        installed = _checksummed_tool_versions(_read(".github/workflows/ci.yml"), tool)

        assert installed, (
            f"{tool} has no install-checksummed-tool block in ci.yml. Every "
            f"directly downloaded binary must be checksum-verified before use."
        )

        recorded = getattr(get_authority(), authority_field)
        # Every install site must agree with each other AND with the record.
        assert set(installed) == {recorded}, (
            f"pin drift: pin_authority.{authority_field}={recorded!r} but "
            f"ci.yml installs {tool} at version(s) {sorted(set(installed))} "
            f"across {len(installed)} site(s)"
        )

    @pytest.mark.parametrize(
        ("tool", "action_repo", "authority_field"),
        [
            ("tflint", "terraform-linters/setup-tflint", "tflint_version"),
        ],
    )
    def test_pinned_action_tool_matches_authority(
        self, tool, action_repo, authority_field
    ):
        """
        Tools installed by a first-party action must still have a recorded version.

        tflint moved from an unverified `curl | unzip` to
        `terraform-linters/setup-tflint`, which verifies the release checksum and
        GPG signature itself. That is stronger than the hand-copied hash it
        replaced — the hash previously recorded for tflint in
        ci/toolchain-lock.json was fabricated (60 characters, non-hex letters).
        The version must still be pinned and must still match the authority.
        """
        content = _read(".github/workflows/ci.yml")

        assert (
            f"{action_repo}@" in content
        ), f"{tool} must be installed via {action_repo} pinned to a full commit SHA"
        # The action reference must be a 40-character commit SHA, not a tag.
        assert re.search(
            rf"{re.escape(action_repo)}@[0-9a-f]{{40}}\b", content
        ), f"{action_repo} must be pinned to a full 40-character commit SHA"

        # Normalise the leading `v`: the action input conventionally takes
        # `v0.64.0` while the authority records the bare semver.
        installed = [
            v.lstrip("v") for v in re.findall(rf"{tool}_version:\s*(\S+)", content)
        ]
        assert installed, f"no {tool}_version input found for {action_repo} in ci.yml"

        recorded = getattr(get_authority(), authority_field)
        assert set(installed) == {recorded}, (
            f"pin drift: pin_authority.{authority_field}={recorded!r} but ci.yml "
            f"requests {tool} {sorted(set(installed))}"
        )

    def test_checkov_version_has_exactly_one_authority(self):
        """
        checkov must be version-pinned with no second copy of the number.

        It cannot live in backend/pyproject.toml: checkov 3.2.x pins
        boto3==1.34.25, which conflicts with the backend's boto3==1.43.2 and makes
        the lock unresolvable. It is a standalone CLI rather than a library this
        code imports, so it runs in an isolated `uv tool run --from
        checkov==<version>` environment.

        The version is READ FROM pin_authority at run time rather than written
        into the script, so there is exactly one place to change it and drift is
        impossible by construction. This test asserts that property instead of
        comparing two hardcoded copies.
        """
        script = _read(".github/scripts/ci-iac-scan.sh")

        assert "uv tool run --from" in script and "checkov==" in script, (
            "checkov must run from an isolated, version-pinned environment via "
            "`uv tool run --from checkov==<version>`"
        )
        assert "pin_authority" in script, (
            "the checkov version must be read from agents/ci/pin_authority.py so "
            "there is only one authority for it"
        )

        # No literal version number may appear next to checkov== in the script.
        literal_pins = re.findall(r"checkov==([0-9][0-9A-Za-z.\-]*)", script)
        assert not literal_pins, (
            f"ci-iac-scan.sh hardcodes checkov version(s) {literal_pins}, which "
            f"creates a second authority that can drift from pin_authority.py"
        )

        # And the authority itself must hold an exact version.
        recorded = get_authority().checkov_version
        assert is_exact_semver(
            recorded
        ), f"pin_authority.checkov_version={recorded!r} must be an exact version"

    def test_trivy_matches_all_three_workflows(self):
        """
        trivy's version lives in workflow-level `env:` in THREE files, because
        `env:` cannot be shared across workflow files. All three copies plus the
        pin authority must agree — this is the check that catches a two-of-three
        bump, which the duplication makes easy to do.
        """
        sites = {
            path: _workflow_env_version(_read(path), "TRIVY_VERSION")
            for path in (
                ".github/workflows/ci.yml",
                ".github/workflows/deploy.yml",
                ".github/workflows/_docker.yml",
            )
        }
        for path, versions in sites.items():
            assert versions, f"No TRIVY_VERSION in {path}"

        recorded = get_authority().trivy_version
        found = {v for versions in sites.values() for v in versions}
        assert found == {recorded}, (
            f"pin drift: pin_authority.trivy_version={recorded!r} but the "
            f"workflows declare {sorted(found)} — per file: "
            + ", ".join(f"{p}={sorted(set(v))}" for p, v in sites.items())
        )

    def test_grype_matches_docker_workflow(self):
        """grype's version lives in _docker.yml's workflow-level env."""
        installed = _workflow_env_version(
            _read(".github/workflows/_docker.yml"), "GRYPE_VERSION"
        )
        assert installed, "No GRYPE_VERSION in .github/workflows/_docker.yml"
        recorded = get_authority().grype_version
        assert set(installed) == {recorded}, (
            f"pin drift: pin_authority.grype_version={recorded!r} but "
            f"_docker.yml declares GRYPE_VERSION {sorted(set(installed))}"
        )

    # ---- Python runtime: the version CI installs vs the version declared ---

    def test_ci_python_version_matches_pin_authority(self):
        """
        The setup-backend action's default python-version must match the pinned
        runtime's major.minor.

        This default was "3.12" while pyproject.toml declared
        `requires-python = ">=3.13.0"`, so CI tested the backend on an
        interpreter the project says it does not support. Nothing failed:
        `uv pip install -r requirements-*.txt` is a pip-compatible interface that
        never reads pyproject.toml, so requires-python could not catch it.
        """
        import yaml

        action = yaml.safe_load(_read(".github/actions/setup-backend/action.yml"))
        ci_python = str(action["inputs"]["python-version"]["default"])
        expected = ".".join(get_python_runtime().split(".")[:2])
        assert ci_python == expected, (
            f"pin drift: setup-backend installs Python {ci_python} but "
            f"pin_authority.python_runtime_version is {get_python_runtime()} "
            f"(expected default {expected!r})"
        )

    def test_pyproject_requires_python_matches_pin_authority(self):
        """pyproject.toml requires-python must match python_requires_minimum."""
        import tomllib

        data = tomllib.loads(
            (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8")
        )
        requires_python = data["project"]["requires-python"]
        expected = f">={get_authority().python_requires_minimum}"
        assert requires_python == expected, (
            f"pin drift: pyproject.toml requires-python={requires_python!r} but "
            f"pin_authority.python_requires_minimum implies {expected!r}"
        )

    def test_sonar_python_version_matches_pin_authority(self):
        """
        sonar-project.properties must analyse the same Python the project pins.

        This said 3.12 against a 3.13 codebase, which silently mis-analyses:
        3.13-only syntax is reported as an issue and 3.13 deprecations are missed.
        """
        properties = _read("sonar-project.properties")
        found = re.findall(
            r"^sonar\.python\.version=(.+)$", properties, flags=re.MULTILINE
        )
        assert found, "sonar.python.version not declared in sonar-project.properties"
        recorded = get_authority().sonar_python_version
        assert set(found) == {recorded}, (
            f"pin drift: sonar-project.properties sets sonar.python.version="
            f"{sorted(set(found))} but pin_authority.sonar_python_version is {recorded!r}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
