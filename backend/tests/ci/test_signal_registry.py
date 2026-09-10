"""Tests for signal registry and single-ownership contract."""

import pytest
from tools.ci.signal_registry import Signal, SignalRegistry, SignalType


class TestSignalRegistry:
    """Test signal registration and single-ownership invariants."""

    def test_registry_initialization(self):
        """Test that registry initializes with all mandatory signals."""
        registry = SignalRegistry()
        assert len(registry) > 0
        assert len(registry.get_mandatory_signals()) > 0

    def test_repo_static_signals(self):
        """Test repository static signals exist and have correct owner."""
        registry = SignalRegistry()
        signals = registry.get_signals_by_owner("repo-static")
        assert len(signals) == 3
        owner_set = {s.owner_job for s in signals}
        assert owner_set == {"repo-static"}

    def test_security_matrix_signals(self):
        """Test security matrix signals exist and have correct owners."""
        registry = SignalRegistry()
        signals = registry.get_signals_by_owner("security")
        assert len(signals) > 0
        owner_set = {s.owner_job for s in signals}
        assert owner_set == {"security"}

    def test_container_scan_signals(self):
        """Test container scanning signals exist and have correct owners."""
        registry = SignalRegistry()
        signals = registry.get_signals_by_owner("container-scan")
        assert len(signals) == 4  # 2 components * 2 engines
        owner_set = {s.owner_job for s in signals}
        assert owner_set == {"container-scan"}

    def test_single_ownership_verification(self):
        """Test that registry enforces single ownership for each signal."""
        registry = SignalRegistry()
        is_valid, errors = registry.verify_single_ownership()
        assert is_valid, f"Registry has ownership conflicts: {errors}"
        assert len(errors) == 0

    def test_no_duplicate_owners_same_semantics(self):
        """Test that duplicate owners with same semantics and tool are detected."""
        registry = SignalRegistry()

        # Try to register a duplicate signal with same semantics, type, and name
        dup_signal = Signal(
            id="repo-static/duplicate",
            name="ActionLint",  # Same name as existing actionlint
            description="Test duplicate",
            signal_type=SignalType.STATIC_CHECK,
            owner_job="repo-static",
            scope="workflow-files",
            trust_boundary="repository-code",
            verdict_semantics="workflow-schema-valid",  # Same verdict semantics
            required_artifact_formats=["log"],
            tool_version="1.7.12",
        )

        with pytest.raises(ValueError, match="Duplicate semantic signal"):
            registry._register_signal(dup_signal)

    def test_signal_blocking_status(self):
        """Test that blocking signals are correctly identified."""
        registry = SignalRegistry()
        blocking_signals = registry.get_blocking_signals()
        assert len(blocking_signals) > 0

        # All blocking signals should have is_blocking=True
        for signal in blocking_signals:
            assert signal.is_blocking is True

    def test_signal_tool_versions(self):
        """Test that signals have tool versions when applicable."""
        registry = SignalRegistry()

        # Actionlint should have a version
        actionlint = registry.get_signal("repo-static/actionlint")
        assert actionlint is not None
        assert actionlint.tool_version is not None

    def test_signal_artifacts_required(self):
        """Test that signals declare required artifact formats."""
        registry = SignalRegistry()

        for signal in registry:
            assert isinstance(signal.required_artifact_formats, list)
            assert len(signal.required_artifact_formats) > 0

    def test_security_zero_finding_semantics(self):
        """Test that software vulnerability scans have zero-finding verdict semantics."""
        registry = SignalRegistry()

        security_signals = [
            s
            for s in registry
            if s.signal_type == SignalType.SECURITY_SCAN
            and "vuln" in s.verdict_semantics.lower()  # Only software vuln scans
        ]
        assert len(security_signals) > 0

        for signal in security_signals:
            # All software vulnerability signals should have zero-threshold in verdict semantics
            assert (
                "zero" in signal.verdict_semantics.lower()
                or "no" in signal.verdict_semantics.lower()
            ), f"Software vulnerability signal {signal.id} lacks zero-threshold semantics"

    def test_retrieve_signal_by_id(self):
        """Test retrieving signals by ID."""
        registry = SignalRegistry()

        signal = registry.get_signal("repo-static/actionlint")
        assert signal is not None
        assert signal.id == "repo-static/actionlint"
        assert signal.owner_job == "repo-static"

    def test_get_nonexistent_signal(self):
        """Test that retrieving nonexistent signal returns None."""
        registry = SignalRegistry()
        signal = registry.get_signal("nonexistent/signal")
        assert signal is None

    def test_signal_equality(self):
        """Test signal semantic equality."""
        sig1 = Signal(
            id="test1",
            name="Test",
            description="Test",
            signal_type=SignalType.STATIC_CHECK,
            owner_job="job1",
            scope="scope1",
            trust_boundary="tb1",
            verdict_semantics="verdict1",
            required_artifact_formats=["log"],
            tool_version="1.0",
        )

        sig2 = Signal(
            id="test2",
            name="Test2",
            description="Test2",
            signal_type=SignalType.STATIC_CHECK,
            owner_job="job2",
            scope="scope1",
            trust_boundary="tb1",
            verdict_semantics="verdict1",
            required_artifact_formats=["log"],
            tool_version="1.0",
        )

        # Same signal type, verdict, and scope means same semantics
        assert sig1 == sig2

    def test_all_signals_iterable(self):
        """Test that we can iterate over all signals."""
        registry = SignalRegistry()

        signal_count = 0
        for signal in registry:
            assert isinstance(signal, Signal)
            signal_count += 1

        assert signal_count == len(registry)
