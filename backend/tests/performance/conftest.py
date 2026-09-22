"""Shared fixtures for the performance suite.

Performance tests measure latency, throughput, and resource budgets. These tests
are opt-in (marked with `@pytest.mark.performance`) and typically run only in
nightly CI or on-demand.

Tests in this suite compose fixtures from unit/integration/e2e suites as needed:
- Unit-level benchmarks: use unit fixtures (mock DB, etc.)
- Full-stack benchmarks: use e2e fixtures (http_client, base_url)
- Database benchmarks: use integration fixtures (db_session, engine)

This conftest is a placeholder for performance-specific fixtures (e.g., a
``benchmark`` fixture from pytest-benchmark, or custom timing utilities).
"""

from __future__ import annotations

import time
from typing import Callable

import pytest


@pytest.fixture
def timer() -> Callable[[], float]:
    """Simple timer for measuring code execution time in benchmarks.

    Returns:
        Callable — a function that returns the current time in seconds.
        Call it before and after code to measure duration: t0 = timer(); f(); t1 = timer(); duration = t1 - t0.
    """
    return time.perf_counter


@pytest.fixture
def benchmark_threshold() -> dict[str, float]:
    """Performance thresholds (in seconds) for common operations.

    Customize these values based on your SLOs. Use in tests like:
        `assert latency < thresholds["endpoint_p99"]`

    Returns:
        dict[str, float] — operation name -> max latency threshold.
    """
    return {
        "endpoint_p50": 0.050,  # 50ms
        "endpoint_p95": 0.200,  # 200ms
        "endpoint_p99": 0.500,  # 500ms
        "db_query": 0.010,  # 10ms
        "cache_hit": 0.001,  # 1ms
    }
