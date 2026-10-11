"""
Pytest configuration for CI tests.

This module:
1. Imports all canary fixtures from conftest_canary.py
2. Provides additional shared fixtures for property-based and integration tests
3. Configures markers for test categorization
"""

import pytest
from .conftest_canary import *  # noqa: F401, F403


# Register pytest markers
def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "canary: tests for CI canary/fault-injection scenarios",
    )
    config.addinivalue_line(
        "markers",
        "property: property-based tests",
    )
    config.addinivalue_line(
        "markers",
        "integration: integration tests",
    )
    config.addinivalue_line(
        "markers",
        "fault_injection: tests that inject faults",
    )
    config.addinivalue_line(
        "markers",
        "slow: slow running tests",
    )


@pytest.fixture(scope="session")
def ci_canary_session_config():
    """Session-level configuration for canary testing."""
    return {
        "external_gate_timeout_seconds": 300,
        "artifact_size_limit_bytes": 100 * 1024 * 1024,
        "cache_hash_algorithm": "sha256",
        "required_coverage_metrics": {
            "backend_overall": 80.0,
            "frontend_statements": 80.0,
            "frontend_branches": 80.0,
            "frontend_functions": 80.0,
            "frontend_lines": 80.0,
        },
    }


@pytest.fixture
def ci_test_result_factory(evaluation_builder):
    """Factory for creating evaluation results for testing."""

    class ResultFactory:
        def __init__(self):
            self.builder = evaluation_builder

        def success(self, sha=None, run_id=None):
            """Create a successful result."""
            if sha:
                self.builder.with_sha(sha)
            if run_id:
                self.builder.with_run_id(run_id)
            return self.builder.build_success()

        def failure_reason(self, reason: str, sha=None, run_id=None):
            """Create a failed result with a specific reason."""
            if sha:
                self.builder.with_sha(sha)
            if run_id:
                self.builder.with_run_id(run_id)
            return self.builder.build_failure(reason)

    return ResultFactory()
