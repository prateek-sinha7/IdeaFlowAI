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
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import fields

# Import the pin authority and validator functions
from tools.ci.pin_authority import (
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

REPO_ROOT = Path(__file__).parents[5]
BACKEND_DIR = Path(__file__).parents[4]


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
        from tools.ci.pin_authority import PinAuthority as PA

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

    def test_postgres_service_image_matches_ci_when_backend_postgres_runs(self):
        """postgres_service_image must equal the image ci.yml and the lock use."""
        recorded = get_authority().postgres_service_image
        workflow = yaml.safe_load(_read(".github/workflows/ci.yml"))
        ci_images = {
            job["services"]["postgres"]["image"]
            for job in workflow["jobs"].values()
            if "postgres" in (job.get("services") or {})
        }
        assert ci_images == {recorded}, (
            f"pin drift: pin_authority.postgres_service_image={recorded!r} but "
            f"ci.yml services.postgres.image is {sorted(ci_images)}"
        )
        locked = json.loads(_read("ci/toolchain-lock.json"))["runtime_pins"][
            "postgresql"
        ]["image"]
        assert locked == recorded, (
            f"pin drift: pin_authority.postgres_service_image={recorded!r} but "
            f"ci/toolchain-lock.json records {locked!r}"
        )

    # ---- Python tools installed from backend/requirements-dev.txt ----------

    @pytest.mark.parametrize(
        ("package", "authority_field"),
        [
            ("ruff", "ruff_version"),
            ("pyright", "pyright_version"),
            ("bandit", "bandit_version"),
            ("pip-audit", "pip_audit_version"),
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

    # ---- playwright is a PRODUCTION dependency, not a dev tool -------------
    #
    # It was parametrized into test_python_tool_matches_requirements_dev above
    # and therefore pinned in requirements-dev.txt. That was the wrong home:
    # backend/Dockerfile installs the image's deps with
    # `uv export --frozen --no-dev`, so a dev-only playwright was stripped from
    # /opt/venv and the runtime stage's `RUN playwright install --with-deps
    # chromium` failed with exit 127 on every build. It is genuinely runtime
    # code — app/agents/render_check.py imports playwright.async_api and
    # app/agents/validators/html_render.py registers it as a Validator — so it
    # now lives in [project.dependencies] / requirements-prod.txt.
    #
    # The drift contract is unchanged; only the file it reads moved. Asserting
    # against requirements-prod.txt is also what keeps it from silently sliding
    # back into the dev group and breaking the image build again.
    def test_playwright_matches_requirements_prod(self):
        """playwright must be pinned in requirements-prod.txt, matching the authority."""
        installed = _requirement_version(
            _read("backend/requirements-prod.txt"), "playwright"
        )
        recorded = get_authority().playwright_package_version
        assert recorded == installed, (
            f"pin drift: pin_authority.playwright_package_version={recorded!r} but "
            f"backend/requirements-prod.txt installs playwright=={installed}"
        )

    def test_playwright_is_not_dev_only(self):
        """
        Regression guard for the exit-127 image-build failure.

        playwright must NOT be declared in the `dev` dependency group: the
        Dockerfile's `uv export --frozen --no-dev` would strip it from the
        runtime venv and `playwright install --with-deps chromium` would fail
        with `playwright: not found`.
        """
        import tomllib

        data = tomllib.loads(_read("backend/pyproject.toml"))

        prod = [
            spec
            for spec in data["project"]["dependencies"]
            if spec.split("==")[0].strip().lower() == "playwright"
        ]
        assert prod, (
            "playwright must be declared in pyproject.toml [project.dependencies] — "
            "backend/Dockerfile's runtime stage runs `playwright install`, and the "
            "builder installs prod deps only (`uv export --no-dev`)."
        )

        dev_group = [
            spec
            for spec in data.get("dependency-groups", {}).get("dev", [])
            if isinstance(spec, str)
            and spec.split("==")[0].strip().lower() == "playwright"
        ]
        assert not dev_group, (
            "playwright must NOT be in [dependency-groups].dev — "
            "`uv export --frozen --no-dev` strips that group from the image, which "
            "makes the runtime stage's `playwright install` fail with exit 127."
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
            ("shellcheck", "shellcheck_version"),
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
            "the checkov version must be read from tools/ci/pin_authority.py so "
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

    def test_trivy_matches_both_workflows(self):
        """
        trivy's version lives in workflow-level `env:` in TWO files, because
        `env:` cannot be shared across workflow files. Both copies plus the pin
        authority must agree — this is the check that catches a one-of-two bump,
        which the duplication makes easy to do.

        There were three copies until `.github/workflows/_docker.yml` was
        deleted; it had no caller.
        """
        sites = {
            path: _workflow_env_version(_read(path), "TRIVY_VERSION")
            for path in (
                ".github/workflows/ci.yml",
                ".github/workflows/deploy.yml",
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

    def test_bare_version_vars_match_their_v_prefixed_counterparts(self):
        """
        Every `<TOOL>_VERSION_BARE` must equal `<TOOL>_VERSION` without the `v`.

        These release URLs are not self-consistent: the GitHub release TAG carries
        a leading `v` while the archive FILENAME inside it does not. ci.yml
        therefore declares both forms. Before it did, the filenames were literals
        (`actionlint_1.7.12_linux_amd64.tar.gz`), so bumping the version variable
        alone produced a URL pointing at the new tag's directory with the old
        filename — a 404 whose error names the download, not the drift.

        This is the check that keeps the pair honest.
        """
        content = _read(".github/workflows/ci.yml")
        bare_vars = re.findall(
            r"^\s*([A-Z0-9_]+)_VERSION_BARE:\s*[\"']([^\"']+)[\"']",
            content,
            flags=re.MULTILINE,
        )
        assert bare_vars, "ci.yml declares no *_VERSION_BARE variables"

        for tool, bare in bare_vars:
            # Not _workflow_env_version(): its regex requires the value to start
            # with a digit, and the whole point here is that the paired variable
            # may carry a leading `v`.
            prefixed = re.findall(
                rf"^\s*{re.escape(tool)}_VERSION:\s*[\"\']([^\"\']+)[\"\']",
                content,
                flags=re.MULTILINE,
            )
            assert prefixed, f"{tool}_VERSION_BARE exists but {tool}_VERSION does not"
            assert len(set(prefixed)) == 1, (
                f"{tool}_VERSION is declared more than once with different values: "
                f"{sorted(set(prefixed))}"
            )
            expected = prefixed[0].lstrip("v")
            assert bare == expected, (
                f"pin drift: ci.yml has {tool}_VERSION={prefixed[0]!r} but "
                f"{tool}_VERSION_BARE={bare!r} (expected {expected!r}). The bare "
                f"form is substituted into the release archive filename, so a "
                f"mismatch is a 404 at install time."
            )

    def test_no_tool_version_literal_remains_in_a_download_url(self):
        """
        No install URL may embed a version literal.

        A literal in the URL means the version variable is not actually the single
        declaration site: the drift tests above would pass while the workflow
        downloaded a different version (or 404'd). Anything that looks like a
        dotted version inside a releases/download URL must come from an
        expression.
        """
        content = _read(".github/workflows/ci.yml")
        offenders = []
        for line in content.splitlines():
            if "releases/download/" not in line:
                continue
            # Strip every ${{ ... }} expression, then look for what is left.
            without_expressions = re.sub(r"\$\{\{[^}]*\}\}", "", line)
            if re.search(r"\d+\.\d+\.\d+", without_expressions):
                offenders.append(line.strip())
        assert offenders == [], (
            "download URLs in ci.yml still embed a version literal outside an "
            "expression; use the *_VERSION / *_VERSION_BARE env vars:\n  "
            + "\n  ".join(offenders)
        )

    def test_grype_matches_ci_workflow(self):
        """
        grype's version lives in ci.yml's workflow-level env.

        It used to be read from `_docker.yml`, which declared its own copy AND
        installed grype by unverified `curl` with no checksum — a P7 violation
        that survived only because nothing called that workflow. ci.yml is now
        the single declaration site, and it installs grype through
        ./.github/actions/install-checksummed-tool.
        """
        recorded = get_authority().grype_version
        # deploy.yml now installs grype too, for the post-push digest scan, so
        # both declaration sites must match the authority.
        for path in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
            installed = _workflow_env_version(_read(path), "GRYPE_VERSION")
            assert installed, f"No GRYPE_VERSION in {path}"
            assert set(installed) == {recorded}, (
                f"pin drift: pin_authority.grype_version={recorded!r} but "
                f"{path} declares GRYPE_VERSION {sorted(set(installed))}"
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


class TestToolchainLockAttestation:
    """
    Every checksummed download must be attested against its publisher (F-31).

    `ci/toolchain-lock.json` carried `"verified": false` on all four entries plus
    a note saying the hashes "were inherited and have NOT been re-verified". That
    was honest, and it mattered: on verification, GRYPE'S HASH WAS WRONG. The file
    recorded de8f5eb8...b5b89 while anchore publishes 2a087c9c...e3aec for
    grype_0.75.0_linux_amd64.tar.gz.

    The consequence was not a subtle weakening. `install-checksummed-tool` runs
    `sha256sum -c`, so the "Install Grype" step failed outright, which failed BOTH
    `container-scan` matrix legs before either scanner ran — leaving all four
    container-scan[*] signals with no verdict and the aggregate unable to go
    green. An unverified checksum is not a documentation gap; it is a broken job
    waiting to be noticed.

    These tests make "unverified" un-shippable, so the next version bump has to
    repeat the verification rather than inherit another unchecked value.
    """

    @staticmethod
    def _lock() -> dict:
        """Parse ci/toolchain-lock.json."""
        return json.loads(_read("ci/toolchain-lock.json"))

    def test_every_checksummed_download_is_verified(self):
        """No entry may ship with `verified: false` or no `verified` key at all."""
        unverified = sorted(
            name
            for name, entry in self._lock()["checksummed_download"].items()
            if entry.get("verified") is not True
        )
        assert not unverified, (
            f"these tools have unattested checksums: {unverified}. Fetch the "
            f"release's own checksums file, match the exact archive filename in "
            f"`url`, then set verified:true. Do not inherit a hash — grype's was "
            f"wrong and silently failed every container scan."
        )

    def test_verification_date_is_recorded(self):
        """
        A verification with no date cannot be audited or aged.

        Checked as a parseable ISO date rather than merely present, so
        "soon"/"TBD" does not satisfy it.
        """
        lock = self._lock()
        assert "verified_on" in lock, "ci/toolchain-lock.json must record verified_on"
        date.fromisoformat(str(lock["verified_on"]))

    @pytest.mark.parametrize(
        "tool", ["actionlint", "gitleaks", "trivy", "grype", "shellcheck"]
    )
    def test_checksum_is_a_real_sha256(self, tool):
        """
        64 lowercase hex characters, nothing else.

        Schema v1 of this file held a 60-character value containing non-hex
        letters for tflint, which could never have matched any artifact. This is
        the cheap shape check that would have caught it.
        """
        digest = self._lock()["checksummed_download"][tool]["sha256"]
        assert re.fullmatch(
            r"[0-9a-f]{64}", digest
        ), f"{tool} sha256 is not 64 lowercase hex characters: {digest!r}"

    @pytest.mark.parametrize(
        ("tool", "url_filename"),
        [
            ("actionlint", "actionlint_1.7.12_linux_amd64.tar.gz"),
            ("gitleaks", "gitleaks_8.30.1_linux_x64.tar.gz"),
            ("trivy", "trivy_0.69.3_Linux-64bit.tar.gz"),
            ("grype", "grype_0.119.0_linux_amd64.tar.gz"),
            ("shellcheck", "shellcheck-v0.11.0.linux.x86_64.tar.gz"),
        ],
    )
    def test_url_points_at_the_archive_the_checksum_describes(self, tool, url_filename):
        """
        The `url` must end in the filename whose hash was verified.

        A checksum is only meaningful paired with an exact artifact. ci.yml builds
        these URLs from two separate variables (`v`-prefixed tag, bare version in
        the filename), and getting the pair wrong produces a 404 rather than a
        checksum mismatch — an error that names the download instead of the drift.
        """
        entry = self._lock()["checksummed_download"][tool]
        assert entry["url"].endswith(url_filename), (
            f"{tool} url {entry['url']!r} does not end in {url_filename!r}, so the "
            f"recorded sha256 does not describe what would be downloaded"
        )

    def test_grype_checksum_is_the_published_value(self):
        """
        Pin the specific value that was wrong, so the regression cannot recur.

        Named explicitly rather than derived: this is the one hash in the file
        that was demonstrably incorrect, and a future careless edit that restores
        it should fail with a message that says exactly that.
        """
        # F-37: grype moved 0.75.0 -> 0.119.0 because 0.75.0's schema-v5
        # vulnerability DB is no longer rebuilt upstream. `published` is the
        # value in grype_0.119.0_checksums.txt (and the release-asset digest).
        published = "3fa2dc4b924621ab65404cf08d0b8438d896d80ab949c9d5a4ca283c36004c9b"
        known_bad = "de8f5eb8e2b3bfe65e906945e5a80a5db92aa8c76fc2e7aba3c95a0b4e3b5b89"

        recorded = self._lock()["checksummed_download"]["grype"]["sha256"]
        assert recorded != known_bad, (
            "grype's sha256 has been reverted to the known-bad value "
            f"{known_bad}. anchore publishes {published} for "
            "grype_0.119.0_linux_amd64.tar.gz; a bad value fails `sha256sum -c` "
            "and takes both container-scan legs down with it."
        )
        assert (
            recorded == published
        ), f"grype sha256 is {recorded}, expected the published {published}"

        # ci.yml and deploy.yml (post-push scan) each carry their own copy
        # (workflow `env:` cannot read a file), so all must agree or the lock
        # file documents something a workflow does not do.
        for path in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
            assert f'GRYPE_SHA256: "{published}"' in _read(
                path
            ), f"{path}'s GRYPE_SHA256 does not match the verified published value"


# ============================================================================
# Node runtime and pinned-action authority (F-07, F-08)
# ============================================================================

# Every ci/toolchain-lock.json `pinned_action` key -> the pin_authority field it
# records. ci.yml passes the version to the action through an input with the
# same name as the field (`tflint_version:`, `terraform_version:`). A new
# pinned_action entry that is not mapped here fails its own parametrized case.
_PINNED_ACTION_AUTHORITY = {
    "tflint": "tflint_version",
    "terraform": "terraform_version",
}


def _pinned_action_keys() -> List[str]:
    """Return every `pinned_action` key in ci/toolchain-lock.json, sorted."""
    return sorted(json.loads(_read("ci/toolchain-lock.json"))["pinned_action"])


def _setup_node_step() -> dict:
    """Return the actions/setup-node step of the setup-frontend composite."""
    action = yaml.safe_load(_read(".github/actions/setup-frontend/action.yml"))
    steps = [
        step
        for step in action["runs"]["steps"]
        if str(step.get("uses", "")).startswith("actions/setup-node@")
    ]
    assert len(steps) == 1, (
        f"setup-frontend must install Node with exactly one actions/setup-node "
        f"step, found {len(steps)}"
    )
    return steps[0]


def _ci_steps_using(action_repo: str) -> List[dict]:
    """Return every ci.yml step whose `uses:` is `<action_repo>@<ref>`."""
    workflow = yaml.safe_load(_read(".github/workflows/ci.yml")) or {}
    found: List[dict] = []
    for job in (workflow.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict) and str(step.get("uses", "")).startswith(
                f"{action_repo}@"
            ):
                found.append(step)
    return found


class TestNodeAndPinnedActionAuthority:
    """
    Node and first-party-action pins must all come from pin_authority.py.

    F-07: setup-frontend declared `node-version: "24"` but the setup-node step
    used `node-version-file: frontend/package.json`, which resolves the engines
    range to the newest 24.x, so CI never installed the authority's exact
    version, and frontend/Dockerfile still built on node:20. F-08: the tflint
    version had several drifting copies and nothing asserted the
    ci/toolchain-lock.json `pinned_action` or `runtime_pins.node` records.
    """

    def test_setup_frontend_default_matches_authority_when_node_pinned(self):
        """The composite's `node-version` default is the exact authority version."""
        action = yaml.safe_load(_read(".github/actions/setup-frontend/action.yml"))
        default = str(action["inputs"]["node-version"]["default"])
        assert default == get_node_runtime(), (
            f"pin drift: setup-frontend defaults node-version to {default!r} but "
            f"pin_authority.node_runtime_version is {get_node_runtime()!r}"
        )

    def test_setup_frontend_installs_input_version_when_setup_node_runs(self):
        """setup-node installs the input, not a range resolved from package.json."""
        with_block = _setup_node_step().get("with") or {}
        assert "node-version-file" not in with_block, (
            "setup-node must not use node-version-file: it resolves the "
            "package.json engines RANGE to the newest matching release, so the "
            "pinned node-version input is ignored"
        )
        assert (
            str(with_block.get("node-version", "")).replace(" ", "")
            == "${{inputs.node-version}}"
        ), (
            "setup-node must install `${{ inputs.node-version }}`, got "
            f"{with_block.get('node-version')!r}"
        )

    def test_package_json_engines_bound_authority_when_declared(self):
        """frontend/package.json engines.node is exactly the authority's range."""
        auth = get_authority()
        engines = json.loads(_read("frontend/package.json")).get("engines", {})
        expected = f">={auth.node_engines_minimum} <{auth.node_engines_maximum}"
        assert engines.get("node") == expected, (
            f"pin drift: frontend/package.json engines.node="
            f"{engines.get('node')!r} but pin_authority implies {expected!r}"
        )

    def test_frontend_dockerfile_bases_match_authority_when_built(self):
        """All three frontend stages build on the digest-pinned authority image."""
        auth = get_authority()
        from_lines = re.findall(
            r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?\s*$",
            _read("frontend/Dockerfile"),
            flags=re.MULTILINE | re.IGNORECASE,
        )
        stages = {stage for _, stage in from_lines}
        assert stages == {"deps", "builder", "runner"}, (
            f"frontend/Dockerfile stages are {sorted(stages)}, expected "
            f"deps, builder and runner"
        )

        images = {image for image, _ in from_lines}
        assert images == {auth.frontend_base_image}, (
            f"pin drift: frontend/Dockerfile FROM lines use {sorted(images)} but "
            f"pin_authority.frontend_base_image is {auth.frontend_base_image!r}"
        )

        reference, _, digest = auth.frontend_base_image.partition("@")
        assert re.fullmatch(
            r"sha256:[0-9a-f]{64}", digest
        ), f"frontend_base_image must be @sha256:-pinned, got {digest!r}"
        tag = reference.partition(":")[2]
        assert tag == f"{auth.node_runtime_version}-bookworm-slim", (
            f"frontend base tag {tag!r} does not name node_runtime_version "
            f"{auth.node_runtime_version!r}"
        )

    def test_toolchain_lock_node_major_matches_authority_when_recorded(self):
        """runtime_pins.node records the authority's Node major."""
        lock = json.loads(_read("ci/toolchain-lock.json"))
        recorded = str(lock["runtime_pins"]["node"]["version"])
        expected = get_node_runtime().split(".")[0]
        assert recorded == expected, (
            f"pin drift: ci/toolchain-lock.json runtime_pins.node.version="
            f"{recorded!r} but pin_authority.node_runtime_version major is "
            f"{expected!r}"
        )

    @pytest.mark.parametrize("tool", _pinned_action_keys())
    def test_pinned_action_entry_matches_authority_when_recorded(self, tool):
        """Lock entry, ci.yml action SHA and ci.yml version input all agree."""
        assert tool in _PINNED_ACTION_AUTHORITY, (
            f"ci/toolchain-lock.json pinned_action.{tool} has no pin_authority "
            f"field mapped in _PINNED_ACTION_AUTHORITY; add the field and map it"
        )
        authority_field = _PINNED_ACTION_AUTHORITY[tool]
        recorded = getattr(get_authority(), authority_field)
        entry = json.loads(_read("ci/toolchain-lock.json"))["pinned_action"][tool]

        assert str(entry["version"]).lstrip("v") == recorded, (
            f"pin drift: ci/toolchain-lock.json pinned_action.{tool}.version="
            f"{entry['version']!r} but pin_authority.{authority_field}={recorded!r}"
        )

        steps = _ci_steps_using(entry["action"])
        assert steps, f"ci.yml has no step using {entry['action']}@<sha>"
        shas = {str(step["uses"]).partition("@")[2] for step in steps}
        assert shas == {entry["action_sha"]}, (
            f"ci.yml pins {entry['action']} at {sorted(shas)} but "
            f"ci/toolchain-lock.json records action_sha {entry['action_sha']!r}"
        )

        installed = {
            str((step.get("with") or {}).get(authority_field, "")).lstrip("v")
            for step in steps
        }
        assert installed == {recorded}, (
            f"pin drift: ci.yml passes {authority_field} {sorted(installed)} to "
            f"{entry['action']} but pin_authority.{authority_field}={recorded!r}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_setup_uv_version_matches_authority_when_setup_backend_installs_uv():
    """setup-backend must pin uv exactly, to pin_authority.uv_version.

    Without a `version:` input, astral-sh/setup-uv looked for uv.toml /
    pyproject.toml at the repo root, found neither (the project is in backend/),
    and installed "latest" — CI run 36718805906 logged "Falling back to latest".
    """
    content = _read(".github/actions/setup-backend/action.yml")

    assert re.search(
        r"astral-sh/setup-uv@[0-9a-f]{40}\b", content
    ), "astral-sh/setup-uv must be pinned to a full 40-character commit SHA"
    installed = re.findall(r"^\s+version:\s*\"?([0-9][^\"\s]*)\"?\s*$", content, re.M)
    assert installed, "setup-uv must receive an explicit `version:` input"
    assert set(installed) == {get_authority().uv_version}, (
        f"pin drift: pin_authority.uv_version={get_authority().uv_version!r} "
        f"but setup-backend requests uv {sorted(set(installed))}"
    )


def test_setup_backend_sync_is_locked_when_installing_dependencies():
    """`uv sync` must use --locked (fails on lock/pyproject drift), not --frozen."""
    content = _read(".github/actions/setup-backend/action.yml")
    sync_lines = [
        ln.strip() for ln in content.splitlines() if ln.strip().startswith("uv sync")
    ]

    assert sync_lines, "setup-backend must run `uv sync`"
    assert all(
        "--locked" in ln and "--frozen" not in ln for ln in sync_lines
    ), f"every `uv sync` in setup-backend must use --locked: {sync_lines}"


# ============================================================================
# Runner image, ShellCheck pin and external action pin set (Phase 3: F-22, F-23)
# ============================================================================

_PIN_USES = re.compile(
    r"^\s*(?:-\s*)?uses:\s*"
    r"(?P<path>[A-Za-z0-9][A-Za-z0-9_.\-]*/[A-Za-z0-9_.\-/]+)"
    r"@(?P<sha>[0-9a-f]{40})\s*#\s*(?P<version>\S+)",
    re.MULTILINE,
)


def _workflow_and_composite_files() -> List[Path]:
    """Every workflow and composite action file that may carry a `uses:` pin."""
    root = REPO_ROOT / ".github"
    return sorted(root.glob("workflows/*.yml")) + sorted(
        root.glob("actions/*/action.yml")
    )


def _observed_action_pins() -> Dict[str, Dict[Tuple[str, str], List[str]]]:
    """
    Map each external action path to {(sha, version): [files that use it]}.

    Raw-text regex, so the trailing `# vX.Y.Z` comment is visible. Local
    `./.github/actions/...` references carry no `@` and never match.
    """
    observed: Dict[str, Dict[Tuple[str, str], List[str]]] = {}
    for path in _workflow_and_composite_files():
        text = path.read_text(encoding="utf-8")
        for match in _PIN_USES.finditer(text):
            key = (match.group("sha"), match.group("version"))
            observed.setdefault(match.group("path"), {}).setdefault(key, []).append(
                path.name
            )
    return observed


def _diff_pin_sets(
    observed: Dict[str, Tuple[str, str]], declared: Dict[str, Tuple[str, str]]
) -> Dict[str, List[str]]:
    """Added, removed and changed action pins between workflows and the lock."""
    return {
        "added_in_workflows": sorted(set(observed) - set(declared)),
        "removed_from_workflows": sorted(set(declared) - set(observed)),
        "changed": sorted(
            name
            for name in set(observed) & set(declared)
            if observed[name] != declared[name]
        ),
    }


class TestRunnerAndShellcheckPins:
    """The runner label and the ShellCheck binary are pinned and recorded (F-22)."""

    @staticmethod
    def _lock() -> dict:
        return json.loads(_read("ci/toolchain-lock.json"))

    def test_runner_image_is_exact_label_when_authority_declared(self):
        """`ubuntu-latest` floats; the authority must name an exact image."""
        label = get_authority().runner_image
        assert re.fullmatch(
            r"ubuntu-\d{2}\.\d{2}", label
        ), f"runner_image {label!r} is not an exact ubuntu-NN.NN label"

    def test_toolchain_lock_runner_matches_authority_when_recorded(self):
        """runtime_pins.runner_image records the authority's label."""
        recorded = self._lock()["runtime_pins"]["runner_image"]["label"]
        assert recorded == get_authority().runner_image

    def test_toolchain_lock_runner_lists_preinstalled_dependencies_when_composites_rely_on_them(
        self,
    ):
        """jq, the AWS CLI and gh come from the runner image; the lock says so."""
        description = self._lock()["runtime_pins"]["runner_image"]["description"]
        for needle in ("jq", "AWS CLI", "gh"):
            assert needle in description, (
                f"runner_image.description must name the preinstalled {needle!r} "
                f"dependency so a runner bump is reviewed against it"
            )

    def test_shellcheck_lock_entry_records_method_and_date_when_no_checksums_file(
        self,
    ):
        """
        koalaman/shellcheck publishes no checksums file, so the method is recorded.

        The sha256 is the GitHub release-asset digest cross-checked against a
        locally recomputed hash. That is weaker than a publisher checksums file
        and the entry must say so instead of claiming otherwise.
        """
        entry = self._lock()["checksummed_download"]["shellcheck"]
        date.fromisoformat(str(entry["verified_on"]))
        assert "digest" in entry["verification_source"]
        assert "no checksums file" in entry["verification_source"]
        assert entry["version"] == f"v{get_authority().shellcheck_version}"

    def test_shellcheck_lock_matches_ci_workflow_when_pinned(self):
        """Lock entry, ci.yml env and the install step's archive member agree."""
        entry = self._lock()["checksummed_download"]["shellcheck"]
        workflow = yaml.safe_load(_read(".github/workflows/ci.yml"))
        env = {str(k): str(v) for k, v in workflow["env"].items()}
        assert env["SHELLCHECK_VERSION"] == entry["version"]
        assert env["SHELLCHECK_SHA256"] == entry["sha256"]

        steps = [
            step
            for step in workflow["jobs"]["repo-static"]["steps"]
            if "install-checksummed-tool" in str(step.get("uses", ""))
            and step.get("with", {}).get("name") == "shellcheck"
        ]
        assert len(steps) == 1, "repo-static must install ShellCheck exactly once"
        member = str(steps[0]["with"]["archive-member"]).replace(
            "${{ env.SHELLCHECK_VERSION }}", env["SHELLCHECK_VERSION"]
        )
        assert member == entry["archive_member"]

    def test_ci_shellcheck_script_asserts_pinned_version_when_run_in_ci(self):
        """The script fails on a version mismatch and when CI forgot to pin."""
        script = _read(".github/scripts/ci-shellcheck.sh")
        assert "SHELLCHECK_EXPECTED_VERSION" in script
        assert "GITHUB_ACTIONS" in script
        assert "shellcheck --version" in script

        workflow = yaml.safe_load(_read(".github/workflows/ci.yml"))
        run_steps = [
            step
            for step in workflow["jobs"]["repo-static"]["steps"]
            if "run_checks.py" in str(step.get("run", ""))
        ]
        assert len(run_steps) == 1
        assert (
            run_steps[0]["env"]["SHELLCHECK_EXPECTED_VERSION"]
            == "${{ env.SHELLCHECK_VERSION }}"
        )

    def test_ssm_run_header_records_runner_dependencies_when_composite_uses_jq_and_aws(
        self,
    ):
        """The composite documents what it takes from the runner image."""
        text = _read(".github/actions/ssm-run/action.yml")
        header = text.split("\nname:", 1)[0]
        for needle in ("jq", "aws", "ubuntu-24.04", "runner_image"):
            assert needle in header, f"ssm-run header must mention {needle!r}"
        lock_description = self._lock()["runtime_pins"]["runner_image"]["description"]
        assert "ssm-run" in lock_description


class TestExternalActionPinSet:
    """
    Workflow `uses:` must match the action pin set recorded in the lock (F-23).

    The lock's `external_actions.pins` was verified against each upstream repo
    with `git ls-remote --tags` at implementation time. These tests use no
    network: they only keep the workflows and the record in step, so a
    Dependabot bump fails here until the lock is updated in the same PR.
    """

    @staticmethod
    def _declared() -> Dict[str, Tuple[str, str]]:
        pins = json.loads(_read("ci/toolchain-lock.json"))["external_actions"]["pins"]
        return {name: (p["sha"], p["version"]) for name, p in pins.items()}

    def test_workflow_uses_match_declared_set_when_actions_are_pinned(self):
        """Observed `uses:` pins equal the declared set, both ways."""
        observed = {
            name: next(iter(variants))
            for name, variants in _observed_action_pins().items()
        }
        diff = _diff_pin_sets(observed, self._declared())
        assert not any(diff.values()), (
            "workflow action pins drifted from ci/toolchain-lock.json "
            f"external_actions.pins: {diff}. Verify the new tag with "
            "`git ls-remote --tags`, then update the lock in the same change."
        )

    def test_each_action_has_one_sha_everywhere_when_used_in_many_files(self):
        """One action, one (sha, version), whichever file uses it."""
        split = {
            name: {f"{sha[:12]} {ver}": files for (sha, ver), files in variants.items()}
            for name, variants in _observed_action_pins().items()
            if len(variants) > 1
        }
        assert not split, f"actions pinned at more than one revision: {split}"

    def test_declared_pins_are_full_shas_with_semver_versions_when_recorded(self):
        """Every record is a 40-hex SHA with a vX.Y.Z version."""
        block = json.loads(_read("ci/toolchain-lock.json"))["external_actions"]
        date.fromisoformat(str(block["verified_on"]))
        assert block["pins"], "external_actions.pins must not be empty"
        for name, (sha, version) in self._declared().items():
            assert re.fullmatch(r"[0-9a-f]{40}", sha), f"{name}: bad sha {sha!r}"
            assert re.fullmatch(r"v\d+\.\d+\.\d+", version), f"{name}: {version!r}"

    def test_artifact_actions_share_a_major_in_the_lock_when_recorded(self):
        """upload-artifact and download-artifact must be one compatible major."""
        declared = self._declared()
        up = declared["actions/upload-artifact"][1]
        down = declared["actions/download-artifact"][1]
        assert up.split(".")[0] == down.split(".")[0], (
            f"artifact actions are on different majors ({up} vs {down}); "
            "mixed majors use incompatible artifact backends"
        )

    def test_pin_diff_reports_each_kind_of_drift_when_sets_differ(self):
        """Self-test for the comparison helper."""
        observed = {"a/x": ("1" * 40, "v1.0.0"), "b/y": ("2" * 40, "v2.0.0")}
        declared = {"a/x": ("3" * 40, "v1.0.1"), "c/z": ("4" * 40, "v3.0.0")}
        assert _diff_pin_sets(observed, declared) == {
            "added_in_workflows": ["b/y"],
            "removed_from_workflows": ["c/z"],
            "changed": ["a/x"],
        }
        assert not any(_diff_pin_sets(observed, observed).values())
