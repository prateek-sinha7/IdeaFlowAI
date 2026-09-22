"""
Integration tests for the aggregate truth function.

Validates end-to-end scenarios for aggregate gate evaluation including:
- Complete successful evaluation
- Partial failures with diagnostics
- Signal registry consistency
- Real-world CI scenarios

Requirements: 2.7, 2.14, 2.16, 3.3, 3.4, 3.5
"""

from datetime import datetime, timezone

import pytest

from tools.ci.aggregate_truth import (
    SignalResult,
    SignalState,
    aggregate_truth,
    compute_aggregate_required_signals,
    explain_aggregate_failure,
    validate_aggregate_inputs,
)
from tools.ci.signal_registry import SIGNAL_REGISTRY


class TestAggregateSuccessScenario:
    """Test successful aggregate evaluation."""

    def test_complete_successful_evaluation(self):
        """All signals success for current SHA → aggregate success."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        # Simulate all required signals completing successfully
        results = {
            signal_name: SignalResult(
                signal_name=signal_name,
                state=SignalState.SUCCESS,
                sha=current_sha,
                timestamp=now,
                error_message=None,
            )
            for signal_name in required_signals
        }

        # Validation should succeed
        errors = validate_aggregate_inputs(results, current_sha)
        assert len(errors) == 0, f"Validation errors: {errors}"

        # Aggregate should succeed
        assert aggregate_truth(results, current_sha) is True

    def test_successful_evaluation_with_diagnostics(self):
        """Success with optional diagnostic information."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        results = {}
        for signal_name in required_signals:
            # Some signals include optional diagnostics
            error_msg = f"Passed: {signal_name}" if len(results) % 3 == 0 else None
            results[signal_name] = SignalResult(
                signal_name=signal_name,
                state=SignalState.SUCCESS,
                sha=current_sha,
                timestamp=now,
                error_message=error_msg,
            )

        assert aggregate_truth(results, current_sha) is True


class TestAggregateFailureScenarios:
    """Test various failure scenarios."""

    def test_backend_test_failure(self):
        """Backend test partition fails → aggregate failure with explanation."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        results = {}
        for signal_name in required_signals:
            if signal_name == "backend-evidence":
                # Backend evidence aggregation failed because underlying tests failed
                state = SignalState.FAILURE
                error_msg = (
                    "Backend offline: 47 failed, 3825 passed; coverage 75% < 80%"
                )
            else:
                state = SignalState.SUCCESS
                error_msg = None

            results[signal_name] = SignalResult(
                signal_name=signal_name,
                state=state,
                sha=current_sha,
                timestamp=now,
                error_message=error_msg,
            )

        # Aggregate should fail
        assert aggregate_truth(results, current_sha) is False

        # Explanation should mention non-success signals
        explanation = explain_aggregate_failure(results, current_sha)
        assert "Non-success signals" in explanation
        assert "backend-evidence" in explanation

    def test_frontend_coverage_failure(self):
        """Frontend coverage below threshold → aggregate failure."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        results = {}
        for signal_name in required_signals:
            if signal_name == "frontend-evidence":
                # Evidence job failed because coverage was 79.5%
                state = SignalState.FAILURE
                error_msg = "Frontend coverage 79.5% < 80% threshold"
            else:
                state = SignalState.SUCCESS
                error_msg = None

            results[signal_name] = SignalResult(
                signal_name=signal_name,
                state=state,
                sha=current_sha,
                timestamp=now,
                error_message=error_msg,
            )

        assert aggregate_truth(results, current_sha) is False

    def test_sonar_quality_gate_failure(self):
        """Sonar quality gate fails → aggregate failure."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        results = {}
        for signal_name in required_signals:
            if signal_name == "sonar-quality-gate":
                # Sonar quality gate did not pass
                state = SignalState.FAILURE
                error_msg = "Quality gate: duplications > 3.0%"
            else:
                state = SignalState.SUCCESS
                error_msg = None

            results[signal_name] = SignalResult(
                signal_name=signal_name,
                state=state,
                sha=current_sha,
                timestamp=now,
                error_message=error_msg,
            )

        assert aggregate_truth(results, current_sha) is False

    def test_security_scan_high_critical_finding(self):
        """High/Critical security finding → aggregate failure."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        results = {}
        for signal_name in required_signals:
            if signal_name == "security[secrets]":
                # Found a critical vulnerability
                state = SignalState.FAILURE
                error_msg = "CRITICAL: CVE-2024-1234 in requests==2.28.0"
            elif signal_name == "security[backend-deps]":
                # Found a high vulnerability
                state = SignalState.FAILURE
                error_msg = "HIGH: Prototype Pollution in lodash"
            else:
                state = SignalState.SUCCESS
                error_msg = None

            results[signal_name] = SignalResult(
                signal_name=signal_name,
                state=state,
                sha=current_sha,
                timestamp=now,
                error_message=error_msg,
            )

        assert aggregate_truth(results, current_sha) is False

    def test_container_image_scan_failure(self):
        """Container image scan detects vulnerability → aggregate failure."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        results = {}
        for signal_name in required_signals:
            if signal_name == "container-scan[backend]/trivy":
                state = SignalState.FAILURE
                error_msg = "Backend image: 2 CRITICAL, 5 HIGH vulnerabilities"
            else:
                state = SignalState.SUCCESS
                error_msg = None

            results[signal_name] = SignalResult(
                signal_name=signal_name,
                state=state,
                sha=current_sha,
                timestamp=now,
                error_message=error_msg,
            )

        assert aggregate_truth(results, current_sha) is False


class TestStaleAndMissingScenarios:
    """Test stale SHA and missing signal scenarios."""

    def test_stale_sha_from_previous_commit(self):
        """Results from old commit SHA → aggregate failure."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        old_sha = "abcdef1234567890abcdef1234567890abcdef12"
        now = datetime.now(timezone.utc)

        # All signals succeeded but for old SHA
        results = {
            signal_name: SignalResult(
                signal_name=signal_name,
                state=SignalState.SUCCESS,
                sha=old_sha,  # Stale!
                timestamp=now,
            )
            for signal_name in required_signals
        }

        assert aggregate_truth(results, current_sha) is False

        explanation = explain_aggregate_failure(results, current_sha)
        assert "SHA mismatch" in explanation or "SHA" in explanation

    def test_missing_signal_detection(self):
        """One required signal missing → aggregate failure with explanation."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        # Omit one signal (e.g., Sonar quality gate)
        results = {
            signal_name: SignalResult(
                signal_name=signal_name,
                state=SignalState.SUCCESS,
                sha=current_sha,
                timestamp=now,
            )
            for signal_name in required_signals
            if signal_name != "sonar-quality-gate"
        }

        assert aggregate_truth(results, current_sha) is False

        explanation = explain_aggregate_failure(results, current_sha)
        assert "Missing mandatory signals" in explanation
        assert "sonar-quality-gate" in explanation

    def test_timed_out_signal(self):
        """Signal timed out → aggregate failure."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        results = {}
        for signal_name in required_signals:
            if signal_name == "backend-evidence":
                # Backend evidence aggregation timed out waiting for PostgreSQL
                state = SignalState.TIMED_OUT
                error_msg = "PostgreSQL service did not become ready within 120s"
            else:
                state = SignalState.SUCCESS
                error_msg = None

            results[signal_name] = SignalResult(
                signal_name=signal_name,
                state=state,
                sha=current_sha,
                timestamp=now,
                error_message=error_msg,
            )

        assert aggregate_truth(results, current_sha) is False

    def test_unavailable_signal(self):
        """External service unavailable → aggregate failure."""
        required_signals = compute_aggregate_required_signals()
        current_sha = "1234567890abcdef1234567890abcdef12345678"
        now = datetime.now(timezone.utc)

        results = {}
        for signal_name in required_signals:
            if signal_name == "sonar-analysis":
                # SonarCloud API unreachable
                state = SignalState.UNAVAILABLE
                error_msg = "SonarCloud API returned 503 Service Unavailable"
            else:
                state = SignalState.SUCCESS
                error_msg = None

            results[signal_name] = SignalResult(
                signal_name=signal_name,
                state=state,
                sha=current_sha,
                timestamp=now,
                error_message=error_msg,
            )

        assert aggregate_truth(results, current_sha) is False


class TestSignalRegistryConsistency:
    """Verify signal registry is consistent with aggregate truth."""

    def test_all_required_signals_in_registry(self):
        """All required signals must exist in registry."""
        required_signals = compute_aggregate_required_signals()

        for signal_name in required_signals:
            assert (
                signal_name in SIGNAL_REGISTRY
            ), f"Signal {signal_name} not in registry"
            signal = SIGNAL_REGISTRY[signal_name]
            assert signal.id == signal_name
            assert signal.owner_job is not None
            assert signal.owner_job != ""

    def test_aggregate_members_consistency(self):
        """ci_required aggregate_members must match computed required signals."""
        ci_required = SIGNAL_REGISTRY["ci-required"]
        computed_required = compute_aggregate_required_signals()

        # ci_required.aggregate_members should define the required set
        assert set(ci_required.aggregate_members) == computed_required

    def test_coverage_signals_in_aggregate(self):
        """Both backend and frontend evidence must be in aggregate."""
        required_signals = compute_aggregate_required_signals()

        assert (
            "backend-evidence" in required_signals
        ), "Backend evidence must be in aggregate"
        assert (
            "frontend-evidence" in required_signals
        ), "Frontend evidence must be in aggregate"

    def test_security_signals_in_aggregate(self):
        """Security signals must be in aggregate."""
        required_signals = compute_aggregate_required_signals()

        security_signals = {
            "security[secrets]",
            "security[backend-deps]",
            "security[frontend-deps]",
        }
        for signal in security_signals:
            assert signal in required_signals, f"{signal} must be in aggregate"

    def test_sonar_signals_in_aggregate(self):
        """Both Sonar signals must be in aggregate."""
        required_signals = compute_aggregate_required_signals()

        assert "sonar-analysis" in required_signals
        assert "sonar-quality-gate" in required_signals
