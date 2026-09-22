"""
Property-based and unit tests for CI pin and installer contracts.

These tests validate that:
1. Tool-pin contract enforces explicit pinned versions
2. Action-pin contract requires full commit SHAs
3. Image-pin contract enforces exact digest pins
4. Installer contracts verify pure functions
"""

import pytest
from hypothesis import given, strategies as st, assume
import json
import re
from tools.ci.pin_contracts import (
    ToolPinValidator,
    ActionPinValidator,
    ImagePinValidator,
    InstallerContractValidator,
    ToolPinViolation,
    ActionPinViolation,
    ImagePinViolation,
    InstallerContractViolation,
    VersionPinType,
    ActionPinType,
    ImagePinType,
    validate_all_pin_contracts,
)


class TestToolPinContract:
    """Test tool version pinning contract."""

    def test_tool_pin_rejects_latest_tag(self):
        """Test that 'latest' tag is rejected for tools."""
        validator = ToolPinValidator()
        violation = validator.validate_tool_version("ruff", "latest", "test.py")

        assert violation is not None
        assert violation.violation_type == VersionPinType.LATEST_TAG
        assert "latest" in violation.current_value

    def test_tool_pin_rejects_floating_ranges(self):
        """Test that floating ranges like ~X.Y or ^X.Y are rejected."""
        validator = ToolPinValidator()

        # Test ~
        violation = validator.validate_tool_version("pytest", "~6.0", "pyproject.toml")
        assert violation is not None
        assert violation.violation_type == VersionPinType.FLOATING_RANGE

        # Test ^
        violation = validator.validate_tool_version("pytest", "^6.0", "pyproject.toml")
        assert violation is not None
        assert violation.violation_type == VersionPinType.FLOATING_RANGE

    def test_tool_pin_accepts_exact_version(self):
        """Test that exact pinned versions are accepted."""
        validator = ToolPinValidator()

        # Should accept exact semver
        violation = validator.validate_tool_version("ruff", "0.5.6", "pyproject.toml")
        assert violation is None

        # Should accept version with build metadata
        violation = validator.validate_tool_version(
            "pytest", "7.4.0", "requirements.txt"
        )
        assert violation is None

    def test_tool_pin_rejects_empty_version(self):
        """Test that empty version strings are rejected."""
        validator = ToolPinValidator()

        violation = validator.validate_tool_version("ruff", "", "pyproject.toml")
        assert violation is not None
        assert violation.violation_type == VersionPinType.NO_EXPLICIT_VERSION

    def test_tool_pin_manifest_validation_valid(self):
        """Test that valid check manifests pass."""
        validator = ToolPinValidator()
        manifest = {
            "checks": [
                {
                    "id": "ruff-lint",
                    "argv": ["uv", "run", "--frozen", "ruff", "check", "."],
                },
                {"id": "pyright", "argv": ["uv", "run", "--frozen", "pyright"]},
            ]
        }

        result = validator.validate_check_manifest(manifest)
        assert result is True
        assert len(validator.violations) == 0

    def test_tool_pin_manifest_validation_empty_manifest(self):
        """Test that empty manifest is valid."""
        validator = ToolPinValidator()
        result = validator.validate_check_manifest({})
        assert result is True

    @given(
        version=st.one_of(
            st.just("latest"),
            st.just("@latest"),
            st.just("~1.0.0"),
            st.just("^2.0.0"),
            st.just(">=3.0"),
            st.just("<4.0"),
            st.just("main"),
        )
    )
    def test_tool_pin_rejects_unpinned_versions_property(self, version):
        """Test that all unpinned version formats are rejected.

        **Validates: Requirements 2.9, 2.10**
        """
        validator = ToolPinValidator()
        violation = validator.validate_tool_version("test-tool", version, "test")

        assert violation is not None, f"Version '{version}' should be rejected"
        assert violation.current_value == version


class TestActionPinContract:
    """Test GitHub Actions reference pinning contract."""

    def test_action_pin_requires_full_sha(self):
        """Test that actions require full 40-character SHA."""
        validator = ActionPinValidator()

        # Valid: full SHA
        violation = validator.validate_action_reference(
            "actions/checkout@b4ffbf834f165fc686d8b07a0f14b482fa080601", "workflow"
        )
        assert violation is None

    def test_action_pin_rejects_tag_reference(self):
        """Test that tag references like v1 are rejected."""
        validator = ActionPinValidator()

        violation = validator.validate_action_reference(
            "actions/checkout@v3", "workflow"
        )
        assert violation is not None
        assert violation.violation_type == ActionPinType.TAG_REFERENCE

    def test_action_pin_rejects_branch_reference(self):
        """Test that branch references like main are rejected."""
        validator = ActionPinValidator()

        violation = validator.validate_action_reference(
            "actions/checkout@main", "workflow"
        )
        assert violation is not None
        assert violation.violation_type == ActionPinType.BRANCH_REFERENCE

    def test_action_pin_rejects_short_sha(self):
        """Test that short SHAs are rejected."""
        validator = ActionPinValidator()

        violation = validator.validate_action_reference(
            "actions/checkout@1234567", "workflow"
        )
        assert violation is not None
        assert violation.violation_type == ActionPinType.SHORT_SHA

    def test_action_pin_rejects_no_reference(self):
        """Test that missing references are rejected."""
        validator = ActionPinValidator()

        violation = validator.validate_action_reference("actions/checkout", "workflow")
        assert violation is not None
        assert violation.violation_type == ActionPinType.NO_REFERENCE

    def test_action_pin_workflow_validation_valid(self):
        """Test that valid workflow with full SHAs passes."""
        validator = ActionPinValidator()
        workflow = {
            "jobs": {
                "test": {
                    "steps": [
                        {
                            "uses": "actions/checkout@b4ffbf834f165fc686d8b07a0f14b482fa080601"
                        },
                        {
                            "uses": "actions/setup-python@0a887fbbf8ecd71d1e10f86ab1a22c1e5d9d10b0"
                        },
                    ]
                }
            }
        }

        result = validator.validate_workflow(workflow)
        assert result is True
        assert len(validator.violations) == 0

    def test_action_pin_workflow_validation_invalid(self):
        """Test that workflow with non-SHA references is rejected."""
        validator = ActionPinValidator()
        workflow = {
            "jobs": {
                "test": {
                    "steps": [
                        {"uses": "actions/checkout@v3"},
                        {"uses": "actions/setup-python@main"},
                    ]
                }
            }
        }

        result = validator.validate_workflow(workflow)
        assert result is False
        assert len(validator.violations) == 2

    @given(
        sha=st.one_of(
            st.just("v3"),
            st.just("main"),
            st.just("master"),
            st.just("develop"),
            st.just("trunk"),
            st.text(alphabet="0123456789abcdef", min_size=1, max_size=39),  # short SHA
        )
    )
    def test_action_pin_rejects_non_sha_refs_property(self, sha):
        """Test that all non-SHA references are rejected.

        **Validates: Requirements 2.10, 2.13, 2.14, 2.16**
        """
        assume(sha)  # ensure sha is not empty
        validator = ActionPinValidator()

        violation = validator.validate_action_reference(f"owner/action@{sha}", "test")

        assert violation is not None, f"Reference '{sha}' should be rejected"
        assert violation.current_value == sha


class TestImagePinContract:
    """Test container image digest pinning contract."""

    def test_image_pin_requires_digest(self):
        """Test that images must use digest pins."""
        validator = ImagePinValidator()

        # Valid: digest
        violation = validator.validate_image_reference(
            "gcr.io/image@sha256:" + "a" * 64, "Dockerfile"
        )
        assert violation is None

    def test_image_pin_rejects_latest_tag(self):
        """Test that 'latest' tag is rejected."""
        validator = ImagePinValidator()

        violation = validator.validate_image_reference("nginx:latest", "Dockerfile")
        assert violation is not None
        assert violation.violation_type == ImagePinType.MUTABLE_TAG

    def test_image_pin_rejects_mutable_tags(self):
        """Test that all mutable tags are rejected."""
        validator = ImagePinValidator()

        for tag in ["latest", "main", "master", "nightly", "dev", "staging"]:
            violation = validator.validate_image_reference(
                f"postgres:{tag}", "Dockerfile"
            )
            assert violation is not None, f"Tag '{tag}' should be rejected"
            assert violation.violation_type == ImagePinType.MUTABLE_TAG

    def test_image_pin_rejects_version_tag_without_digest(self):
        """Test that version tags without digest are rejected."""
        validator = ImagePinValidator()

        violation = validator.validate_image_reference("postgres:15.2", "Dockerfile")
        assert violation is not None
        assert violation.violation_type == ImagePinType.NO_DIGEST

    def test_image_pin_rejects_no_tag_no_digest(self):
        """Test that image without tag or digest is rejected."""
        validator = ImagePinValidator()

        violation = validator.validate_image_reference("postgres", "Dockerfile")
        assert violation is not None
        assert violation.violation_type == ImagePinType.NO_DIGEST

    def test_image_pin_dockerfile_validation_valid(self):
        """Test that valid Dockerfile with digest-pinned images passes."""
        validator = ImagePinValidator()
        dockerfile = """
FROM python:3.13@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
RUN apt-get update
"""
        result = validator.validate_docker_file(dockerfile, "Dockerfile")
        assert result is True
        assert len(validator.violations) == 0

    def test_image_pin_dockerfile_validation_invalid(self):
        """Test that Dockerfile with non-pinned images is rejected."""
        validator = ImagePinValidator()
        dockerfile = """
FROM python:3.13
FROM postgres:latest
"""
        result = validator.validate_docker_file(dockerfile, "Dockerfile")
        assert result is False
        assert len(validator.violations) == 2

    @given(
        tag=st.one_of(
            st.just("latest"),
            st.just("main"),
            st.just("master"),
            st.just("v1.0"),
            st.just("1.0.0"),
        )
    )
    def test_image_pin_rejects_undigested_images_property(self, tag):
        """Test that all non-digest references are rejected.

        **Validates: Requirements 2.9, 2.10**
        """
        validator = ImagePinValidator()

        violation = validator.validate_image_reference(
            f"registry.io/image:{tag}", "test"
        )

        assert violation is not None, f"Image with tag '{tag}' should be rejected"


class TestInstallerContractValidator:
    """Test installer function purity contract."""

    def test_installer_contract_detects_network_calls(self):
        """Test that network calls are detected."""
        validator = InstallerContractValidator()

        func_code = """
def install_tool():
    import requests
    response = requests.get("https://example.com/tool.tar.gz")
    return response.content
"""
        violation = validator.validate_installer_function("install_tool", func_code)
        assert violation is not None
        assert (
            "network" in violation.issue.lower()
            or "requests" in violation.issue.lower()
        )

    def test_installer_contract_detects_subprocess_calls(self):
        """Test that subprocess calls are detected."""
        validator = InstallerContractValidator()

        func_code = """
def install_tool():
    import subprocess
    subprocess.run(["./install.sh"])
    return True
"""
        violation = validator.validate_installer_function("install_tool", func_code)
        assert violation is not None

    def test_installer_contract_detects_env_writes(self):
        """Test that environment variable writes are detected."""
        validator = InstallerContractValidator()

        func_code = """
def install_tool():
    import os
    os.environ["PATH"] = "/usr/local/bin:" + os.environ.get("PATH", "")
    return True
"""
        violation = validator.validate_installer_function("install_tool", func_code)
        assert violation is not None

    def test_installer_contract_detects_credential_access(self):
        """Test that credential access is detected."""
        validator = InstallerContractValidator()

        func_code = """
def install_tool():
    import os
    api_key = os.getenv("API_KEY")
    return api_key
"""
        violation = validator.validate_installer_function("install_tool", func_code)
        assert violation is not None

    def test_installer_contract_pure_function_passes(self):
        """Test that pure functions pass validation."""
        validator = InstallerContractValidator()

        func_code = """
def install_tool():
    config = {"version": "1.0.0"}
    result = process_config(config)
    return result

def process_config(cfg):
    return cfg.get("version")
"""
        violation = validator.validate_installer_function("install_tool", func_code)
        assert violation is None

    def test_installer_contract_detects_urllib(self):
        """Test that urllib calls are detected."""
        validator = InstallerContractValidator()

        func_code = """
def install_tool():
    import urllib.request
    urllib.request.urlopen("https://example.com/tool.tar.gz")
"""
        violation = validator.validate_installer_function("install_tool", func_code)
        assert violation is not None


class TestAggregateContractValidation:
    """Test validation of all contracts together."""

    def test_validate_all_pin_contracts_valid(self):
        """Test that valid contracts pass overall validation."""
        manifest = {
            "checks": [
                {"id": "ruff", "argv": ["uv", "run", "--frozen", "ruff", "check", "."]},
            ]
        }

        workflow = {
            "jobs": {
                "test": {
                    "steps": [
                        {
                            "uses": "actions/checkout@b4ffbf834f165fc686d8b07a0f14b482fa080601"
                        },
                    ]
                }
            }
        }

        dockerfiles = {"Dockerfile": f"FROM python:3.13@sha256:{'a' * 64}"}

        all_valid, violations = validate_all_pin_contracts(
            manifest, workflow, dockerfiles
        )
        assert all_valid is True
        assert len(violations) == 0

    def test_validate_all_pin_contracts_invalid(self):
        """Test that invalid contracts are detected."""
        manifest = {
            "checks": [
                {"id": "ruff", "argv": ["ruff@latest"]},
            ]
        }

        workflow = {
            "jobs": {
                "test": {
                    "steps": [
                        {"uses": "actions/checkout@v3"},
                    ]
                }
            }
        }

        dockerfiles = {"Dockerfile": "FROM nginx:latest"}

        all_valid, violations = validate_all_pin_contracts(
            manifest, workflow, dockerfiles
        )
        assert all_valid is False
        assert len(violations) >= 1


class TestPinContractEdgeCases:
    """Test edge cases and corner cases in pin contracts."""

    def test_action_pin_case_insensitive_sha(self):
        """Test that SHA validation is case-insensitive."""
        validator = ActionPinValidator()

        # uppercase
        violation = validator.validate_action_reference(
            "owner/action@1234567890ABCDEF1234567890ABCDEF12345678", "workflow"
        )
        assert violation is None

        # mixed case
        violation = validator.validate_action_reference(
            "owner/action@1234567890AbCdEf1234567890AbCdEf12345678", "workflow"
        )
        assert violation is None

    def test_image_pin_digest_case_insensitive(self):
        """Test that digest validation is case-insensitive."""
        validator = ImagePinValidator()

        # lowercase
        violation = validator.validate_image_reference(
            f"registry.io/image@sha256:{'a' * 64}", "Dockerfile"
        )
        assert violation is None

        # uppercase
        violation = validator.validate_image_reference(
            f"registry.io/image@SHA256:{'A' * 64}", "Dockerfile"
        )
        assert violation is None

    def test_action_pin_with_path(self):
        """Test action references with paths."""
        validator = ActionPinValidator()

        # Valid
        violation = validator.validate_action_reference(
            "owner/repo/path/to/action@1234567890abcdef1234567890abcdef12345678",
            "workflow",
        )
        assert violation is None

    def test_image_pin_with_registry_and_namespace(self):
        """Test image references with full registry and namespace."""
        validator = ImagePinValidator()

        # Valid with digest
        violation = validator.validate_image_reference(
            f"gcr.io/my-project/my-image@sha256:{'b' * 64}", "Dockerfile"
        )
        assert violation is None

        # Invalid without digest
        violation = validator.validate_image_reference(
            "gcr.io/my-project/my-image:v1.0", "Dockerfile"
        )
        assert violation is not None


class TestPinContractViolationMessages:
    """Test that violation messages are clear and actionable."""

    def test_tool_pin_violation_message_includes_location(self):
        """Test that tool pin violation includes file location."""
        validator = ToolPinValidator()
        violation = validator.validate_tool_version(
            "ruff", "latest", "pyproject.toml:10"
        )

        assert violation is not None
        assert "pyproject.toml:10" in violation.location
        assert "ruff" in violation.message

    def test_action_pin_violation_message_includes_reference(self):
        """Test that action pin violation includes the bad reference."""
        validator = ActionPinValidator()
        violation = validator.validate_action_reference(
            "actions/setup-python@main", "workflow.yml"
        )

        assert violation is not None
        assert "main" in violation.current_value
        assert "setup-python" in violation.action

    def test_image_pin_violation_message_includes_image(self):
        """Test that image pin violation includes the bad image."""
        validator = ImagePinValidator()
        violation = validator.validate_image_reference("postgres:latest", "Dockerfile")

        assert violation is not None
        assert "postgres" in violation.image
        assert "latest" in violation.current_value


# Property-based tests for robustness
class TestPinContractProperties:
    """Property-based tests validating contract behavior."""

    @given(st.integers(min_value=0, max_value=100))
    def test_tool_validator_no_crash_on_arbitrary_version(self, version_num):
        """Test that validator doesn't crash on arbitrary version numbers.

        **Validates: Requirements 2.9**
        """
        validator = ToolPinValidator()
        _ = validator.validate_tool_version("tool", str(version_num), "test")

        # Should not crash, violation depends on format
        assert True

    @given(st.text(alphabet="0123456789abcdef", min_size=40, max_size=40))
    def test_action_pin_accepts_40_char_hex(self, hex_sha):
        """Test that all 40-character hex strings are accepted as valid SHAs.

        **Validates: Requirements 2.10, 2.16**
        """
        validator = ActionPinValidator()
        violation = validator.validate_action_reference(
            f"owner/action@{hex_sha}", "test"
        )

        assert violation is None

    @given(st.text(alphabet="0123456789abcdef", min_size=64, max_size=64))
    def test_image_pin_accepts_64_char_hex_digest(self, hex_digest):
        """Test that all 64-character hex strings are accepted as valid digests.

        **Validates: Requirements 2.9**
        """
        validator = ImagePinValidator()
        violation = validator.validate_image_reference(
            f"registry.io/image@sha256:{hex_digest}", "test"
        )

        assert violation is None
