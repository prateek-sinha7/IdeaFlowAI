"""
Aggregate Truth Function for CI Pipeline Remediation.

Implements the core gate logic determining whether all mandatory CI signals
have succeeded for the same exact repository revision.

The aggregate truth function enforces a fail-closed policy:
- Only `success` for the exact same current SHA satisfies the gate
- All mandatory signals must succeed
- Missing or non-success states fail the aggregate
- Stale SHA never satisfies the gate

Requirements: 2.7, 2.14, 2.16, 3.3, 3.4, 3.5
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from tools.ci.signal_registry import (
    SIGNAL_REGISTRY,
    Signal,
)


class SignalState(str, Enum):
    """Possible states for a CI signal."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    # F-15: did not run on a pull request because its change area was reported
    # unchanged. Satisfies the aggregate ONLY with `allow_filtered=True` and only
    # for a signal whose registry `path_filter_area` is not None; see the policy
    # docblock on `Signal.path_filter_area`.
    FILTERED = "filtered"


@dataclass(frozen=True)
class SignalResult:
    """
    Result of a single CI signal evaluation.

    Attributes:
        signal_name: Name of the signal (must exist in registry)
        state: Current state of the signal
        sha: Full 40-character commit SHA this result was evaluated for
        timestamp: When the result was recorded
        error_message: Optional error details (never contains secrets)
    """

    signal_name: str
    state: SignalState
    sha: str
    timestamp: datetime
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate signal result."""
        if len(self.sha) != 40:
            raise ValueError(f"SHA must be exactly 40 characters, got {len(self.sha)}")
        if not all(c in "0123456789abcdef" for c in self.sha):
            raise ValueError(f"SHA must be valid hexadecimal: {self.sha}")
        # Note: we don't validate signal existence here; that's checked by aggregate_truth
        # This allows test harnesses to create synthetic signals for testing validation logic


def compute_aggregate_required_signals(
    registry: dict[str, Signal] | None = None,
) -> set[str]:
    """
    Compute the set of mandatory signals required for aggregate gate.

    Collects expected inputs from the signal registry:
    - All backend static checks (ruff_lint, ruff_format, python_compile, migration_guard, etc.)
    - Both backend test partitions (backend_offline, backend_postgres via backend_evidence)
    - Frontend static checks (frontend_typecheck, frontend_lint, frontend_build)
    - Frontend evidence (merged Vitest + E2E via frontend_evidence)
    - Security checks (gitleaks, pip_audit, npm_audit)
    - IaC checks (terraform_fmt, terraform_validate, tflint, checkov, trivy_config)
    - Container scans (container_scan_backend, container_scan_frontend)

    The aggregate itself (ci_required) is derived from these signals, not included.

    Args:
        registry: Signal registry (defaults to SIGNAL_REGISTRY if None)

    Returns:
        Set of signal names required for aggregate gate to succeed

    Raises:
        ValueError: If the aggregate signal is malformed or dependencies are invalid
    """
    if registry is None:
        registry = SIGNAL_REGISTRY

    # Get the aggregate signal definition
    if "ci-required" not in registry:
        raise ValueError("Aggregate signal 'ci-required' not found in registry")

    aggregate_signal = registry["ci-required"]

    # The aggregate_members list defines the mandatory signals
    if not aggregate_signal.aggregate_members:
        raise ValueError(
            "Aggregate signal 'ci-required' has no aggregate_members defined"
        )

    # Validate that all aggregate members exist in registry
    required_signals = set(aggregate_signal.aggregate_members)
    unknown_signals = required_signals - set(registry.keys())
    if unknown_signals:
        raise ValueError(f"Unknown signals in aggregate_members: {unknown_signals}")

    return required_signals


def _is_accepted_filtered(
    result: SignalResult,
    signal_name: str,
    registry: dict[str, Signal],
    allow_filtered: bool,
) -> bool:
    """Return True when a FILTERED result satisfies the gate (F-15 policy)."""
    return (
        allow_filtered
        and result.state == SignalState.FILTERED
        and registry[signal_name].path_filter_area is not None
    )


def aggregate_truth(
    results: dict[str, SignalResult],
    current_sha: str,
    registry: dict[str, Signal] | None = None,
    *,
    allow_filtered: bool = False,
) -> bool:
    """
    Determine aggregate gate success based on signal results.

    Truth table logic:
    - Aggregate succeeds if and only if EVERY mandatory signal state == success
    - All signals must be evaluated for the SAME exact current SHA
    - No missing required signals
    - No stale/unavailable states

    Fail-closed semantics:
    - Any non-success state → False
    - Any missing signal → False
    - SHA mismatch → False
    - Unknown signals → raises ValueError

    Args:
        results: Mapping of signal_name -> SignalResult
        current_sha: Expected SHA for all results (full 40-character SHA)
        registry: Signal registry (defaults to SIGNAL_REGISTRY if None)
        allow_filtered: When True, a FILTERED result satisfies the gate for a
            signal whose registry `path_filter_area` is not None (F-15). The
            caller sets it only for a pull request with reported unchanged
            areas. FILTERED on a never-filterable signal still fails.

    Returns:
        True if all mandatory signals succeeded for exact current SHA, False otherwise

    Raises:
        ValueError: If SHA format is invalid, unknown signals present, or duplicate signals found
    """
    # Validate current_sha format
    if len(current_sha) != 40:
        raise ValueError(f"SHA must be exactly 40 characters, got {len(current_sha)}")
    if not all(c in "0123456789abcdef" for c in current_sha):
        raise ValueError(f"SHA must be valid hexadecimal: {current_sha}")

    if registry is None:
        registry = SIGNAL_REGISTRY

    # Get required signals
    required_signals = compute_aggregate_required_signals(registry)

    # Fail-closed: validate no unknown signals in results
    unknown_signals = set(results.keys()) - set(registry.keys())
    if unknown_signals:
        raise ValueError(f"Unknown signals in results: {unknown_signals}")

    # Fail-closed: validate no duplicate signals
    if len(results) != len(set(results.keys())):
        raise ValueError("Duplicate signals found in results")

    # Check each mandatory signal
    for signal_name in required_signals:
        # Missing signal → False
        if signal_name not in results:
            return False

        result = results[signal_name]

        # SHA mismatch → False (stale result)
        if result.sha != current_sha:
            return False

        # Non-success state → False, unless it is an accepted policy filter
        if result.state != SignalState.SUCCESS and not _is_accepted_filtered(
            result, signal_name, registry, allow_filtered
        ):
            return False

    # All mandatory signals succeeded for same exact SHA
    return True


def validate_aggregate_inputs(
    results: dict[str, SignalResult],
    current_sha: str,
    registry: dict[str, Signal] | None = None,
) -> list[str]:
    """
    Validate aggregate inputs for correctness and completeness.

    Returns a list of validation issues. Empty list means inputs are valid.

    Validation rules:
    - SHA format is valid
    - No unknown signals
    - No duplicate signals
    - All mandatory signals are present
    - All results have matching current_sha
    - All results have SignalState enum values
    - No orphaned signals (defined but not in results and not mandatory)

    Args:
        results: Mapping of signal_name -> SignalResult
        current_sha: Expected SHA for all results
        registry: Signal registry (defaults to SIGNAL_REGISTRY if None)

    Returns:
        List of validation error messages
    """
    errors: list[str] = []

    if registry is None:
        registry = SIGNAL_REGISTRY

    # Validate SHA format
    if len(current_sha) != 40:
        errors.append(f"SHA must be exactly 40 characters, got {len(current_sha)}")
        return errors
    if not all(c in "0123456789abcdef" for c in current_sha):
        errors.append(f"SHA must be valid hexadecimal: {current_sha}")
        return errors

    # Check for unknown signals
    unknown_signals = set(results.keys()) - set(registry.keys())
    if unknown_signals:
        errors.append(f"Unknown signals in results: {unknown_signals}")

    # Check for duplicate signals
    if len(results) != len(set(results.keys())):
        errors.append("Duplicate signals found in results")

    # Get required signals
    try:
        required_signals = compute_aggregate_required_signals(registry)
    except ValueError as e:
        errors.append(f"Invalid aggregate definition: {e}")
        return errors

    # Check for missing mandatory signals
    missing_signals = required_signals - set(results.keys())
    if missing_signals:
        errors.append(f"Missing mandatory signals: {missing_signals}")

    # Validate each result
    for signal_name, result in results.items():
        # Check SHA match (not required for non-mandatory, but still good to validate)
        if result.sha != current_sha:
            errors.append(
                f"Signal '{signal_name}' has mismatched SHA: "
                f"expected {current_sha}, got {result.sha}"
            )

        # Validate signal_name matches
        if result.signal_name != signal_name:
            errors.append(
                f"Result key '{signal_name}' does not match result.signal_name '{result.signal_name}'"
            )

    return errors


def explain_aggregate_failure(
    results: dict[str, SignalResult],
    current_sha: str,
    registry: dict[str, Signal] | None = None,
    *,
    allow_filtered: bool = False,
) -> str:
    """
    Generate human-readable explanation of why aggregate gate failed.

    Args:
        results: Mapping of signal_name -> SignalResult
        current_sha: Expected SHA
        registry: Signal registry (defaults to SIGNAL_REGISTRY if None)
        allow_filtered: Same meaning as in `aggregate_truth`; accepted FILTERED
            signals are not listed as failures.

    Returns:
        Human-readable explanation of failure reason(s)
    """
    if registry is None:
        registry = SIGNAL_REGISTRY

    # Collect failure reasons
    failures: list[str] = []

    # Get required signals
    try:
        required_signals = compute_aggregate_required_signals(registry)
    except ValueError as e:
        return f"Invalid aggregate configuration: {e}"

    # Check for missing signals
    missing = required_signals - set(results.keys())
    if missing:
        failures.append(f"Missing mandatory signals: {', '.join(sorted(missing))}")

    # Check for SHA mismatches
    sha_mismatches = []
    for signal_name in required_signals:
        if signal_name in results:
            result = results[signal_name]
            if result.sha != current_sha:
                sha_mismatches.append(
                    f"{signal_name} (expected {current_sha[:8]}, got {result.sha[:8]})"
                )
    if sha_mismatches:
        failures.append(f"SHA mismatches: {', '.join(sha_mismatches)}")

    # Check for non-success states
    non_success = []
    for signal_name in required_signals:
        if signal_name in results:
            result = results[signal_name]
            if result.state != SignalState.SUCCESS and not _is_accepted_filtered(
                result, signal_name, registry, allow_filtered
            ):
                msg = f"{signal_name}: {result.state.value}"
                if result.error_message:
                    msg += f" ({result.error_message})"
                non_success.append(msg)
    if non_success:
        failures.append(f"Non-success signals: {', '.join(non_success)}")

    if not failures:
        return "Unknown reason - gate appears to be passing"

    return "; ".join(failures)
