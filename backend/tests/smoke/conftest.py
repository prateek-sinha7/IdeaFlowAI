"""Shared fixtures for the smoke suite.

Smoke tests are deployed-environment liveness checks: 5–10 quick assertions that
the system is "alive" after a deploy. They run post-deployment (not in CI test
stages) and check essential services (API health, DB connectivity, auth flow).

Fixture hierarchy:
- `base_url` — deployed service URL (from env)
- `deployed_http_client` — httpx.AsyncClient bound to the deployed URL
- `health_check_threshold` — timeout for health checks
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
from httpx import AsyncClient


@pytest.fixture(scope="session")
def deployed_base_url() -> str:
    """Base URL for the deployed application.

    Sourced from the environment variable ``DEPLOYED_BASE_URL`` (required for
    smoke tests). Raises an error if not set, since smoke tests assume a
    running service.

    Returns:
        str — the deployed service base URL.

    Raises:
        ValueError — if DEPLOYED_BASE_URL is not set in the environment.
    """
    url = os.environ.get("DEPLOYED_BASE_URL", "").strip()
    if not url:
        raise ValueError(
            "DEPLOYED_BASE_URL environment variable not set. "
            "Smoke tests require a running deployed service."
        )
    return url


@pytest.fixture
async def deployed_http_client(
    deployed_base_url: str,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx.AsyncClient bound to the deployed service.

    Scope: function — a fresh client per test.

    Args:
        deployed_base_url: The deployed service base URL.

    Yields:
        AsyncClient — ready for requests to the deployed service.
    """
    async with AsyncClient(base_url=deployed_base_url, timeout=10.0) as client:
        yield client


@pytest.fixture
def health_check_threshold() -> dict[str, float]:
    """Timeout thresholds (in seconds) for deployed health checks.

    Smoke tests have tight SLOs; if the service doesn't respond in these
    windows, the deploy is considered unhealthy.

    Returns:
        dict[str, float] — check name -> max response time.
    """
    return {
        "health_endpoint": 5.0,  # /health should respond in < 5s
        "readiness_endpoint": 5.0,  # /readiness should respond in < 5s
        "db_connectivity": 10.0,  # DB ping should succeed in < 10s
        "auth_flow": 15.0,  # Login flow should succeed in < 15s
    }
