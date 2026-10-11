"""Tests for signal registry and single-ownership contract."""

import pytest
from tools.ci.pin_authority import get_authority
from tools.ci.signal_registry import (
    PATH_FILTER_AREAS,
    Signal,
    SignalRegistry,
    SignalType,
)


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
        # actionlint, bash-syntax, shellcheck, and compose-config (F-19).
        assert len(signals) == 4
        owner_set = {s.owner_job for s in signals}
        assert owner_set == {"repo-static"}
        assert "repo-static/compose-config" in {s.id for s in signals}

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
        # 2 components * 2 engines, plus the frontend lockfile scan that
        # replaced npm audit.
        assert len(signals) == 5
        owner_set = {s.owner_job for s in signals}
        assert owner_set == {"container-scan"}

    # TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
    # In future this must be changed back to BLOCKING, and the outstanding High/Critical
    # vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
    # Flip this test when restoring blocking.
    def test_get_blocking_signals_excludes_container_scan_when_scans_are_temporarily_advisory(
        self,
    ):
        registry = SignalRegistry()
        container_ids = {s.id for s in registry.get_signals_by_owner("container-scan")}
        assert len(container_ids) == 5
        blocking_ids = {s.id for s in registry.get_blocking_signals()}
        assert not (container_ids & blocking_ids)
        for signal_id in container_ids:
            signal = registry.get_signal(signal_id)
            assert signal.is_mandatory
            assert not signal.advisory_eligible
            assert signal_id in registry.get_signal("ci-required").aggregate_members

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


# F-15: the path-filter area each owner job's signals belong to. Matrix owners
# (security, container-scan) split by leg, so they are keyed by id prefix in
# _MATRIX_PREFIX_AREA instead. None = never filterable.
_OWNER_AREA = {
    "repo-static": None,
    "backend-inventory": "backend",
    "backend-static": "backend",
    "backend-offline": "backend",
    "backend-postgres": "backend",
    "backend-evidence": "backend",
    "frontend-build": "frontend",
    "frontend-static": "frontend",
    "frontend-vitest": "frontend",
    "frontend-e2e": "frontend",
    "frontend-evidence": "frontend",
    "ci-evidence": None,
}
_MATRIX_PREFIX_AREA = {
    "security[secrets]": None,
    "security[iac]/": "infra",
    "container-scan[backend]/": "backend_image",
    "container-scan[frontend]/": "frontend_image",
}


def _expected_area(signal: Signal) -> str | None:
    """The area the policy assigns to `signal`."""
    if signal.owner_job in _OWNER_AREA:
        return _OWNER_AREA[signal.owner_job]
    matches = [p for p in _MATRIX_PREFIX_AREA if signal.id.startswith(p)]
    assert len(matches) == 1, f"{signal.id} has no row in the area tables"
    return _MATRIX_PREFIX_AREA[matches[0]]


class TestPathFilterAreas:
    """The F-15 area assignment is explicit and closed."""

    def test_registry_areas_are_valid_when_declared(self):
        for signal in SignalRegistry():
            assert signal.path_filter_area is None or (
                signal.path_filter_area in PATH_FILTER_AREAS
            ), f"{signal.id} has unknown area {signal.path_filter_area!r}"

    @pytest.mark.parametrize("signal", list(SignalRegistry()), ids=lambda s: s.id)
    def test_registry_area_matches_owner_table_when_registered(self, signal):
        assert signal.path_filter_area == _expected_area(signal)

    def test_registry_never_filters_repo_static_or_secrets_when_registered(self):
        registry = SignalRegistry()
        never = {s.id for s in registry.get_signals_by_area(None)}
        assert {
            "repo-static/actionlint",
            "repo-static/bash-syntax",
            "repo-static/shellcheck",
            "repo-static/compose-config",
            "security[secrets]",
        } <= never

    def test_register_signal_raises_when_area_is_unknown(self):
        registry = SignalRegistry()
        bad = Signal(
            id="test/unknown-area",
            name="Unknown area",
            description="Test",
            signal_type=SignalType.STATIC_CHECK,
            owner_job="test-job",
            scope="test-scope",
            trust_boundary="repository-code",
            verdict_semantics="test-verdict",
            required_artifact_formats=["log"],
            path_filter_area="docs",
        )

        with pytest.raises(ValueError, match="unknown path_filter_area"):
            registry._register_signal(bad)

    def test_get_signals_by_area_returns_every_area_member_when_queried(self):
        registry = SignalRegistry()
        by_area = {
            area: {s.id for s in registry.get_signals_by_area(area)}
            for area in PATH_FILTER_AREAS
        }
        assert all(by_area.values()), f"an area owns no signal: {by_area}"
        assert "frontend-build" in by_area["frontend"]


class TestFrontendBuildSignal:
    """F-12: the production build is its own owner job."""

    def test_frontend_build_is_owned_by_frontend_build_when_registered(self):
        signal = SignalRegistry().get_signal("frontend-build")
        assert signal is not None
        assert signal.owner_job == "frontend-build"
        assert "tar.gz" in signal.required_artifact_formats

    def test_frontend_static_build_is_absent_when_registry_loads(self):
        registry = SignalRegistry()
        assert registry.get_signal("frontend-static/build") is None
        aggregate = registry.get_signal("ci-required")
        assert aggregate is not None and aggregate.aggregate_members is not None
        assert "frontend-static/build" not in aggregate.aggregate_members
        assert "frontend-build" in aggregate.aggregate_members
        assert "repo-static/compose-config" in aggregate.aggregate_members


# Every signal that declares a `tool_version` -> the pin_authority field it must
# equal (F-08). The registry's literals drifted from what CI installs (tflint
# 0.59.1 vs 0.64.0, grype 0.75.0 vs 0.119.0, ...); they are now read from the
# authority, and this table keeps any new versioned signal from bypassing it.
_SIGNAL_TOOL_VERSION_AUTHORITY = {
    "repo-static/actionlint": "actionlint_version",
    "repo-static/shellcheck": "shellcheck_version",
    "security[secrets]": "gitleaks_version",
    "backend-static/ruff-lint": "ruff_version",
    "backend-static/ruff-format": "ruff_version",
    "backend-static/pyright": "pyright_version",
    "security[iac]/tflint": "tflint_version",
    "security[iac]/checkov": "checkov_version",
    "security[iac]/trivy-config": "trivy_version",
    "container-scan[backend]/trivy": "trivy_version",
    "container-scan[backend]/grype": "grype_version",
    "container-scan[frontend]/trivy": "trivy_version",
    "container-scan[frontend]/grype": "grype_version",
    "container-scan[frontend]/trivy-lockfile": "trivy_version",
}


def _versioned_signal_ids() -> list[str]:
    """Signal ids that declare a tool_version, plus every id in the table."""
    declared = {s.id for s in SignalRegistry() if s.tool_version is not None}
    return sorted(declared | set(_SIGNAL_TOOL_VERSION_AUTHORITY))


@pytest.mark.parametrize("signal_id", _versioned_signal_ids())
def test_signal_tool_version_matches_pin_authority_when_declared(signal_id):
    """A signal's tool_version is exactly the pin authority's value for its tool."""
    signal = SignalRegistry().get_signal(signal_id)
    assert signal is not None, (
        f"{signal_id} is in _SIGNAL_TOOL_VERSION_AUTHORITY but not registered; "
        f"remove the stale entry"
    )
    assert signal.tool_version is not None, (
        f"{signal_id} is mapped to a pin_authority field but declares no "
        f"tool_version"
    )
    assert signal_id in _SIGNAL_TOOL_VERSION_AUTHORITY, (
        f"{signal_id} declares tool_version={signal.tool_version!r} with no "
        f"pin_authority field mapped; read it from tools/ci/pin_authority.py "
        f"and add it to _SIGNAL_TOOL_VERSION_AUTHORITY"
    )
    field = _SIGNAL_TOOL_VERSION_AUTHORITY[signal_id]
    expected = getattr(get_authority(), field)
    assert signal.tool_version == expected, (
        f"pin drift: {signal_id} tool_version={signal.tool_version!r} but "
        f"pin_authority.{field}={expected!r}"
    )
