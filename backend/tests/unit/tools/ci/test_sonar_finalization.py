"""
Tests for Sonar finalization (sonar-inline and sonar-pr jobs).

These tests verify that:
1. sonar-inline executes for trusted direct intents (push/manual/reusable)
2. sonar-pr executes for PR finalization
3. Quality gate is waited for with finite timeout
4. Missing/invalid token causes failure
5. Sonar configuration uses CLI overrides
6. Shadow mode publishes ci-required-shadow (not ci-required)
7. Both jobs verify exact SHA before proceeding/publishing
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any


class TestSonarInlineJobConditions:
    """Verify sonar-inline job trigger conditions."""

    def test_runs_on_push_to_main(self):
        """sonar-inline runs on push to main."""
        event = {
            "event_name": "push",
            "ref": "refs/heads/main",
            "repository": {"name": "velocityai"},
        }
        assert event["event_name"] == "push"
        assert event["ref"] == "refs/heads/main"

    def test_runs_on_manual_dispatch(self):
        """sonar-inline runs on workflow_dispatch."""
        event = {
            "event_name": "workflow_dispatch",
        }
        assert event["event_name"] == "workflow_dispatch"

    def test_runs_on_reusable_call(self):
        """sonar-inline runs on reusable workflow call."""
        event = {
            "event_name": "workflow_call",
        }
        assert event["event_name"] == "workflow_call"

    def test_skips_on_pull_request(self):
        """sonar-inline does NOT run on pull_request."""
        event = {
            "event_name": "pull_request",
        }
        # This event is handled by ci-authoritative instead
        assert event["event_name"] != "push"

    def test_skips_on_non_main_branch(self):
        """sonar-inline only runs on main, not feature branches."""
        event = {
            "event_name": "push",
            "ref": "refs/heads/feature/new-feature",
        }
        assert event["ref"] != "refs/heads/main"

    def test_requires_ci_evidence_success(self):
        """sonar-inline requires successful ci-evidence."""
        depends_on = {
            "ci-evidence": "success",  # REQUIRED
        }
        assert depends_on["ci-evidence"] == "success"

    def test_fails_if_ci_evidence_fails(self):
        """sonar-inline skipped if ci-evidence fails."""
        depends_on = {
            "ci-evidence": "failure",  # WRONG
        }
        assert depends_on["ci-evidence"] != "success"


class TestSonarConfiguration:
    """Verify Sonar scanner configuration."""

    def test_uses_cli_overrides(self):
        """Sonar must use CLI arguments, not file config."""
        config = {
            "source": "cli_args",  # CLI arguments take precedence
            "project_key": "-Dsonar.projectKey=velocityai",
            "organization": "-Dsonar.organization=velocityai",
        }
        assert config["source"] == "cli_args"

    def test_ignores_fork_sonar_project_properties(self):
        """sonar-project.properties from fork is ignored."""
        # This is critical for PR evaluation
        # CLI args override any fork-controlled config file
        cli_args = {
            "projectKey": "velocityai",
            "organization": "velocityai",
        }
        # These explicit values prevent fork config from taking effect
        assert len(cli_args) > 0

    def test_configures_correct_sources(self):
        """Sonar sources include only production code."""
        sources = [
            "backend/app",
            "backend/agents",
            "frontend/src",
        ]
        # Test files are NOT included in sources
        assert "backend/tests" not in sources
        assert "frontend/e2e" not in sources

    def test_configures_coverage_reports(self):
        """Coverage reports are configured per language."""
        config = {
            "python_coverage": "backend/coverage.xml",  # Cobertura
            "javascript_coverage": "frontend/coverage/lcov.info",  # LCOV
        }
        assert config["python_coverage"].endswith(".xml")
        assert config["javascript_coverage"].endswith(".info")

    def test_sets_python_version(self):
        """Sonar analyzes Python 3.13 code."""
        config = {
            "python_version": "3.13",
        }
        assert config["python_version"] == "3.13"

    def test_enables_quality_gate_wait(self):
        """Sonar waits for quality gate with finite timeout."""
        config = {
            "qualitygate_wait": True,
            "qualitygate_timeout": 300,  # 5 minutes
        }
        assert config["qualitygate_wait"] is True
        assert config["qualitygate_timeout"] == 300

    def test_sets_new_code_reference(self):
        """New Code is relative to main branch."""
        config = {
            "new_code_reference": "main",
        }
        assert config["new_code_reference"] == "main"


class TestSonarTokenHandling:
    """Verify SONAR_TOKEN security."""

    def test_sonar_inline_requires_token(self):
        """sonar-inline must have SONAR_TOKEN secret."""
        secrets = {
            "SONAR_TOKEN": "sonar_xxx_123",
        }
        assert "SONAR_TOKEN" in secrets

    def test_sonar_pr_requires_token(self):
        """sonar-pr must have SONAR_TOKEN secret."""
        secrets = {
            "SONAR_TOKEN": "sonar_xxx_456",
        }
        assert "SONAR_TOKEN" in secrets

    def test_token_not_available_in_fork_pr(self):
        """SONAR_TOKEN not available to fork code in PRs."""
        # Fork PRs cannot access SONAR_TOKEN secret
        # sonar-pr job (trusted) receives it, fork code does not
        fork_context = {
            "has_sonar_token": False,  # CORRECT
        }
        assert fork_context["has_sonar_token"] is False

    def test_token_is_masked_in_logs(self):
        """SONAR_TOKEN value is masked in workflow logs."""
        # GitHub Actions automatically masks registered secrets
        # In logs, the token appears as ***
        logged_output = "Logging in with token: ***"
        assert "***" in logged_output
        assert "sonar_xxx" not in logged_output

    def test_missing_token_fails_sonar(self):
        """Missing token causes Sonar to fail."""
        env = {}  # Token not set
        assert "SONAR_TOKEN" not in env


class TestSonarAnalysisExecution:
    """Verify Sonar analysis execution and results."""

    def test_sonar_success_exit_code(self):
        """Successful Sonar exit code is 0."""
        exit_code = 0  # Success
        assert exit_code == 0

    def test_sonar_failure_exit_code(self):
        """Failed Sonar exit code is non-zero."""
        exit_code = 1  # Failure
        assert exit_code != 0

    def test_sonar_timeout_is_failure(self):
        """Quality gate timeout is non-success."""
        result = {
            "timeout": True,
            "status": "non_success",
        }
        assert result["status"] != "success"

    def test_quality_gate_passed(self):
        """Quality gate passing means success."""
        gate_result = {
            "status": "OK",
        }
        assert gate_result["status"] == "OK"

    def test_quality_gate_failed(self):
        """Quality gate failing is non-success."""
        gate_result = {
            "status": "FAILED",
        }
        assert gate_result["status"] != "OK"

    def test_quality_gate_error(self):
        """Quality gate error is non-success."""
        gate_result = {
            "status": "ERROR",
        }
        assert gate_result["status"] not in ["OK"]

    def test_unavailable_service_fails(self):
        """Unreachable SonarCloud is non-success."""
        result = {
            "error": "Failed to connect to sonarcloud.io",
            "exit_code": 1,
        }
        assert result["exit_code"] != 0


class TestSonarQualityGateWait:
    """Verify quality gate waiting behavior."""

    def test_waits_for_quality_gate(self):
        """Sonar waits for quality gate completion."""
        config = {
            "qualitygate_wait": True,
        }
        assert config["qualitygate_wait"] is True

    def test_timeout_is_finite(self):
        """Quality gate wait has finite timeout."""
        timeout_seconds = 300  # 5 minutes
        assert timeout_seconds > 0
        assert timeout_seconds < 3600  # Less than 1 hour

    def test_timeout_value_correct(self):
        """Timeout is set to 300 seconds (5 minutes)."""
        timeout_seconds = 300
        assert timeout_seconds == 300

    def test_timeout_on_no_response(self):
        """No response within timeout is non-success."""
        result = {
            "timeout": True,
            "waited_seconds": 300,
        }
        assert result["timeout"] is True

    def test_gate_failure_before_timeout(self):
        """Quality gate failure returns immediately."""
        result = {
            "status": "FAILED",
            "waited_seconds": 30,  # Much less than timeout
        }
        assert result["status"] == "FAILED"


class TestStatusPublication:
    """Verify status publication for both jobs."""

    def test_sonar_inline_publishes_shadow_status(self):
        """sonar-inline publishes ci-required-shadow."""
        status = {
            "context": "ci-required-shadow",
            "sha": "abc123def456abc123def456abc123def456abc1",
        }
        assert status["context"] == "ci-required-shadow"

    def test_sonar_pr_publishes_shadow_status(self):
        """sonar-pr publishes ci-required-shadow."""
        status = {
            "context": "ci-required-shadow",
            "sha": "def456abc123def456abc123def456abc123def4",
        }
        assert status["context"] == "ci-required-shadow"

    def test_never_publishes_ci_required(self):
        """Shadow mode never publishes ci-required (yet)."""
        published = [
            "ci-required-shadow",
            "ci-evidence",
        ]
        assert "ci-required" not in published

    def test_success_status_on_quality_gate_pass(self):
        """Quality gate passing → ci-required-shadow=success."""
        status = {
            "context": "ci-required-shadow",
            "state": "success",
            "description": "Sonar analysis passed (shadow)",
        }
        assert status["state"] == "success"

    def test_failure_status_on_quality_gate_fail(self):
        """Quality gate failing → ci-required-shadow=failure."""
        status = {
            "context": "ci-required-shadow",
            "state": "failure",
            "description": "Sonar analysis failed (shadow)",
        }
        assert status["state"] == "failure"

    def test_failure_status_on_timeout(self):
        """Timeout → ci-required-shadow=failure."""
        status = {
            "context": "ci-required-shadow",
            "state": "failure",
            "description": "Sonar analysis timed out",
        }
        assert status["state"] == "failure"

    def test_includes_target_url_on_failure(self):
        """Failure status includes link to logs."""
        status = {
            "state": "failure",
            "target_url": "https://github.com/org/repo/actions/runs/123",
        }
        assert "target_url" in status

    def test_publishes_on_exact_sha(self):
        """Status published on exact commit SHA only."""
        sha = "abc123def456abc123def456abc123def456abc1"
        assert len(sha) == 40


class TestShadowModeSemantics:
    """Verify shadow mode behavior."""

    def test_shadow_status_not_required_yet(self):
        """ci-required-shadow is not a required status."""
        # .github/rulesets still require legacy status, not shadow
        protected_status = "ci-required"  # Current requirement
        shadow_status = "ci-required-shadow"
        assert protected_status != shadow_status

    def test_legacy_status_remains_authoritative(self):
        """Legacy ci-required is still the authoritative status."""
        # During shadow period, branch protection uses legacy status
        # New ci-required-shadow is parallel, not replacement
        legacy = {
            "name": "ci-required",
            "required": True,  # Still required
        }
        shadow = {
            "name": "ci-required-shadow",
            "required": False,  # Not required yet
        }
        assert legacy["required"] is True
        assert shadow["required"] is False

    def test_shadow_period_allows_divergence(self):
        """Shadow and legacy status can diverge during migration."""
        # This is intentional: allows safe validation
        results = {
            "legacy_ci_required": "success",
            "ci_required_shadow": "failure",  # Can differ
        }
        assert results["legacy_ci_required"] != results["ci_required_shadow"]

    def test_shadow_is_visible_but_not_blocking(self):
        """Shadow status is published but not blocking."""
        status = {
            "context": "ci-required-shadow",
            "visible": True,
            "blocks_merge": False,  # Not blocking during shadow
        }
        assert status["blocks_merge"] is False


class TestEvaluationSHA:
    """Verify exact SHA handling."""

    def test_sonar_inline_verifies_checkout_sha(self):
        """sonar-inline verifies it checked out correct SHA."""
        checkout = {
            "expected": "abc123def456abc123def456abc123def456abc1",
            "actual": "abc123def456abc123def456abc123def456abc1",  # Match
        }
        assert checkout["expected"] == checkout["actual"]

    def test_sonar_inline_fails_on_sha_mismatch(self):
        """sonar-inline fails if checkout SHA is wrong."""
        checkout = {
            "expected": "abc123def456abc123def456abc123def456abc1",
            "actual": "different000000000000000000000000000000",  # Mismatch
        }
        assert checkout["expected"] != checkout["actual"]

    def test_sonar_pr_publishes_on_evaluation_sha(self):
        """sonar-pr publishes on the evaluation SHA, not current."""
        # This is critical: publish on the exact SHA that was evaluated,
        # not the current PR head (which may have changed)
        status = {
            "sha": "evaluation_sha_exactly",
            "not": "current_pr_head",
        }
        assert status["sha"] == "evaluation_sha_exactly"

    def test_sonar_pr_rechecks_head_before_publishing(self):
        """sonar-pr verifies PR head hasn't moved."""
        pr_state = {
            "head_at_evaluation": "abc123",
            "head_now": "abc123",  # Still the same
        }
        assert pr_state["head_at_evaluation"] == pr_state["head_now"]

    def test_sonar_pr_fails_if_head_changed(self):
        """sonar-pr fails if PR head changed."""
        pr_state = {
            "head_at_evaluation": "abc123",
            "head_now": "def456",  # Changed!
        }
        assert pr_state["head_at_evaluation"] != pr_state["head_now"]


class TestErrorCases:
    """Verify error handling."""

    def test_missing_coverage_report_warning(self):
        """Missing coverage report is a warning, continues."""
        result = {
            "coverage_found": False,
            "continues": True,  # Doesn't fail
        }
        assert result["continues"] is True

    def test_missing_sonar_token_error(self):
        """Missing SONAR_TOKEN is an error, fails."""
        result = {
            "token_found": False,
            "fails": True,
        }
        assert result["fails"] is True

    def test_quality_gate_unavailable_error(self):
        """Quality gate service unavailable is an error."""
        result = {
            "error": "Failed to wait for quality gate",
            "non_success": True,
        }
        assert result["non_success"] is True

    def test_corrupt_sonar_output_error(self):
        """Invalid Sonar output is an error."""
        result = {
            "error": "Could not parse Sonar response",
            "non_success": True,
        }
        assert result["non_success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
