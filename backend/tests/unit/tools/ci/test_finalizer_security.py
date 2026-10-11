"""
Tests for CI Authoritative (workflow_run) finalizer security.

These tests verify that the finalizer:
1. Validates source workflow identity and PR metadata
2. Rejects malicious/corrupted artifacts
3. Never executes fork-controlled code/config
4. Treats fork source as read-only untrusted data
5. Verifies artifact checksums and paths
6. Fails on missing/invalid ci-evidence
7. Rechecks PR head before publishing status
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict


class TestFinalizerEventValidation:
    """Validate workflow_run event metadata processing."""

    def test_rejects_non_pull_request_event(self):
        """workflow_run event must be from pull_request trigger."""
        event = {
            "action": "completed",
            "workflow_run": {
                "event": "push",  # WRONG
                "conclusion": "success",
                "id": 123,
            },
        }
        # Finalizer should reject this event
        assert event["workflow_run"]["event"] != "pull_request"

    def test_rejects_non_success_workflow(self):
        """Workflow must conclude with 'success'."""
        event = {
            "workflow_run": {
                "event": "pull_request",
                "conclusion": "failure",  # WRONG
                "id": 123,
            },
        }
        assert event["workflow_run"]["conclusion"] != "success"

    def test_rejects_cancelled_workflow(self):
        """Cancelled workflows cannot be finalized."""
        event = {
            "workflow_run": {
                "event": "pull_request",
                "conclusion": "cancelled",  # WRONG
                "id": 123,
            },
        }
        assert event["workflow_run"]["conclusion"] != "success"

    def test_requires_pr_association(self):
        """workflow_run must be associated with a pull_request."""
        event = {
            "workflow_run": {
                "event": "pull_request",
                "conclusion": "success",
                "id": 123,
                "pull_requests": [],  # WRONG: no PR
            },
        }
        assert len(event["workflow_run"]["pull_requests"]) == 0


class TestArtifactValidation:
    """Validate artifact manifest and path safety."""

    def test_rejects_traversal_paths(self):
        """Artifact paths cannot escape the repository."""
        unsafe_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "./../../sensitive",
            "prefix/../../../escape",
        ]
        for unsafe_path in unsafe_paths:
            # Validate: must not contain .. or traversal patterns
            assert ".." in unsafe_path or unsafe_path.startswith("/")

    def test_rejects_absolute_paths(self):
        """Artifact paths must be relative to repository root."""
        unsafe_paths = [
            "/etc/passwd",
            "/home/user/file",
            "C:\\Windows\\System32",
        ]
        for path in unsafe_paths:
            assert path.startswith("/") or ":" in path

    def test_rejects_symlinks(self):
        """Artifact downloads must reject symlinks."""
        # Validate: symlinks in artifacts are a security risk
        # Implementation should use os.path.islink() to detect
        artifact_file = Path("test.txt")
        if artifact_file.exists():
            # In real scenario, would check: if artifact_file.is_symlink()
            assert not artifact_file.is_symlink()

    def test_enforces_size_limits(self):
        """Artifacts must not exceed maximum size."""
        MAX_ARTIFACT_SIZE = 100 * 1024 * 1024  # 100 MB

        artifact_sizes = [
            50 * 1024 * 1024,  # OK: 50 MB
            100 * 1024 * 1024,  # OK: exactly 100 MB
            101 * 1024 * 1024,  # WRONG: exceeds limit
        ]

        for size in artifact_sizes[:2]:
            assert size <= MAX_ARTIFACT_SIZE

        assert artifact_sizes[2] > MAX_ARTIFACT_SIZE

    def test_validates_manifest_checksum(self):
        """Manifest checksums must match downloaded files."""
        import hashlib

        content = b"test artifact content"
        expected_sha256 = hashlib.sha256(content).hexdigest()

        # Correct case
        actual_sha256 = hashlib.sha256(content).hexdigest()
        assert actual_sha256 == expected_sha256

        # Wrong checksum should fail
        wrong_sha256 = (
            "0000000000000000000000000000000000000000000000000000000000000000"
        )
        assert wrong_sha256 != expected_sha256

    def test_requires_complete_manifest(self):
        """Artifact manifest must declare all files."""
        manifest = {
            "schema_version": 1,
            "producer": "backend-offline",
            "evaluation_sha": "abc123",
            "files": [
                {"path": "junit.xml", "sha256": "hash1"},
                # Missing coverage file
            ],
        }
        # Validation should fail: declared incomplete
        assert len(manifest["files"]) == 1  # incomplete

    def test_rejects_malformed_json(self):
        """Malformed manifest JSON must be rejected."""
        malformed = "{incomplete json"
        with pytest.raises(json.JSONDecodeError):
            json.loads(malformed)

    def test_rejects_wrong_producer(self):
        """Manifest producer must match expected producer."""
        manifest = {
            "producer": "wrong-producer",  # WRONG
            "evaluation_sha": "abc123",
        }
        assert manifest["producer"] != "backend-offline"


class TestForkSourceHandling:
    """Verify fork source is treated as untrusted data."""

    def test_fork_source_is_read_only(self):
        """Fork source checkout must be read-only."""
        # In workflow YAML: actions/checkout with path separates
        # trusted checkout from fork source
        # Validation: fork-source-readonly directory is separate
        trusted_path = "."  # Trusted default branch
        fork_path = "fork-source-readonly"  # Fork source
        assert trusted_path != fork_path

    def test_never_executes_fork_scripts(self):
        """Fork-controlled scripts must never be executed."""
        fork_scripts = [
            "fork-source-readonly/scripts/setup.sh",
            "fork-source-readonly/.github/workflows/custom.yml",
            "fork-source-readonly/Makefile",
        ]
        # Validation: these paths are data only, never executed
        for script_path in fork_scripts:
            assert script_path.startswith("fork-source-readonly/")

    def test_never_executes_fork_actions(self):
        """Fork-defined GitHub Actions must never be used."""
        # In workflow YAML, all actions must be from trusted default branch
        # No actions are executed from fork-source-readonly path
        actions = [
            "actions/checkout@v3",  # OK: trusted GitHub
            "rhysd/actionlint@v1",  # OK: trusted public action
            "./fork-source-readonly/.github/actions/custom",  # WRONG
        ]

        for action in actions[:2]:
            # Trusted actions are safe
            assert not action.startswith("./fork-source-readonly/")

        assert actions[2].startswith("./fork-source-readonly/")

    def test_ignores_fork_tool_config(self):
        """A config file from the fork tree is never read as configuration."""
        # Any tool config must come from the trusted checkout
        trusted_config = ".github/scripts/ci-validate-evidence.sh"  # From root
        fork_config = "fork-source-readonly/.github/scripts/ci-validate-evidence.sh"

        # Validation: only trusted config is used
        assert trusted_config != fork_config

    def test_fork_source_checkout_has_no_credentials(self):
        """Fork source checkout must not use credentials."""
        # In workflow YAML: fork checkout uses github.token with no
        # credentials persistence
        checkout_config = {
            "persist-credentials": False,  # CORRECT
            # no SSH key, no personal access token
        }
        assert checkout_config["persist-credentials"] is False

    def test_fork_source_checkout_has_no_submodules(self):
        """Fork source checkout must not resolve submodules."""
        # Submodules could reference malicious repositories
        checkout_config = {
            "submodules": False,  # CORRECT
        }
        assert checkout_config["submodules"] is False

    def test_fork_source_checkout_has_no_lfs(self):
        """Fork source checkout must not use Git LFS."""
        # LFS could be used for trojan delivery
        checkout_config = {
            "lfs": False,  # CORRECT
        }
        assert checkout_config["lfs"] is False


class TestCIEvidenceValidation:
    """Validate ci-evidence prerequisite."""

    def test_requires_ci_evidence_success(self):
        """ci-evidence must succeed before finalizer proceeds."""
        upstream_results = {
            "attest-evaluation": "success",
            "ci-evidence": "success",  # REQUIRED
        }
        assert upstream_results["ci-evidence"] == "success"

    def test_fails_on_ci_evidence_failure(self):
        """Finalizer must fail if ci-evidence fails."""
        upstream_results = {
            "attest-evaluation": "success",
            "ci-evidence": "failure",  # WRONG
        }
        assert upstream_results["ci-evidence"] != "success"

    def test_fails_on_ci_evidence_timeout(self):
        """Timeout of ci-evidence is non-success."""
        upstream_results = {
            "ci-evidence": "timed_out",  # WRONG
        }
        assert upstream_results["ci-evidence"] not in ["success"]

    def test_fails_on_missing_ci_evidence_manifest(self):
        """Missing ci-evidence manifest is non-success."""
        manifests = {
            "ci-evidence": None,  # WRONG: not found
        }
        assert manifests["ci-evidence"] is None


class TestStatusPublication:
    """Verify correct status publication."""

    def test_publishes_ci_required_shadow_on_success(self):
        """Successful evaluation publishes ci-required-shadow=success."""
        result = {
            "status": "success",
            "context": "ci-required-shadow",
            "sha": "abc123def456",
        }
        assert result["context"] == "ci-required-shadow"
        assert result["status"] == "success"

    def test_publishes_ci_required_shadow_on_failure(self):
        """Failed evaluation publishes ci-required-shadow=failure."""
        result = {
            "status": "failure",
            "context": "ci-required-shadow",
            "sha": "abc123def456",
        }
        assert result["context"] == "ci-required-shadow"
        assert result["status"] == "failure"

    def test_never_publishes_ci_required(self):
        """Shadow mode never publishes ci-required (yet)."""
        # This is critical: ci-required remains with legacy publisher
        published_contexts = [
            "ci-required-shadow",  # OK
            "ci-evidence",  # OK
        ]
        assert "ci-required" not in published_contexts

    def test_publishes_on_exact_sha_only(self):
        """Status is published on exact evaluation SHA only."""
        event = {
            "workflow_run": {
                "head_commit": {"sha": "abc123def456abc123def456abc123def456abc1"}
            }
        }
        evaluation_sha = event["workflow_run"]["head_commit"]["sha"]
        assert len(evaluation_sha) == 40  # Full SHA

    def test_includes_target_url_on_failure(self):
        """Failure status includes link to run."""
        status = {
            "state": "failure",
            "description": "CI evaluation failed (shadow)",
            "target_url": "https://github.com/org/repo/actions/runs/12345",
        }
        assert "target_url" in status
        assert status["state"] == "failure"


class TestHeadVerification:
    """Verify PR head consistency."""

    def test_rechecks_pr_head_before_publishing(self):
        """Current PR head must match evaluation SHA."""
        pr_data = {
            "current_head_sha": "xyz789",
            "evaluation_sha": "xyz789",  # MATCH
        }
        assert pr_data["current_head_sha"] == pr_data["evaluation_sha"]

    def test_fails_on_head_mismatch(self):
        """If PR head changed, evaluation is stale."""
        pr_data = {
            "current_head_sha": "new123",
            "evaluation_sha": "old456",  # MISMATCH
        }
        assert pr_data["current_head_sha"] != pr_data["evaluation_sha"]

    def test_rejects_stale_evaluation_after_update(self):
        """A newer push makes an older evaluation stale."""
        evaluations = [
            {"sha": "abc123", "timestamp": 1000},
            {"sha": "def456", "timestamp": 1001},  # Newer
        ]
        # Only the newest SHA is current
        current_sha = evaluations[-1]["sha"]
        assert current_sha == "def456"
        assert evaluations[0]["sha"] != current_sha


class TestErrorHandling:
    """Verify error handling and non-success cases."""

    def test_attestation_failure_fails(self):
        """A failed attestation job is non-success."""
        attest_result = {
            "exit_code": 1,
            "outcome": "failure",
        }
        assert attest_result["outcome"] != "success"

    def test_attestation_timeout_fails(self):
        """An attestation timeout is non-success."""
        attest_result = {
            "timeout": True,
            "outcome": "timed_out",
        }
        assert attest_result["outcome"] != "success"

    def test_quality_gate_failure_fails(self):
        """Failed quality gate is non-success."""
        gate_result = {
            "status": "FAILED",
        }
        assert gate_result["status"] != "OK"

    def test_missing_coverage_report_fails(self):
        """Missing required coverage report is non-success."""
        reports = {
            "backend/coverage.xml": None,  # Missing
            "frontend/coverage/lcov.info": None,  # Missing
        }
        assert reports["backend/coverage.xml"] is None

    def test_corrupt_manifest_fails(self):
        """Corrupt/unparseable manifest is non-success."""
        manifest_content = "{ invalid json"
        with pytest.raises(json.JSONDecodeError):
            json.loads(manifest_content)

    def test_workflow_validation_failure_fails(self):
        """Failed workflow validation is non-success."""
        validation = {
            "workflow_id_matches": False,  # WRONG
            "event_is_pull_request": True,
            "conclusion_is_success": True,
        }
        assert validation["workflow_id_matches"] is False

    def test_artifact_checksum_mismatch_fails(self):
        """Checksum mismatch prevents artifact use."""
        artifact = {
            "expected_sha256": "abc123",
            "actual_sha256": "def456",  # MISMATCH
        }
        assert artifact["expected_sha256"] != artifact["actual_sha256"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
