"""Shared fixtures for the e2e suite.

E2E tests drive the full application stack over HTTP, exercising routers,
services, database, and external integrations (with LLM/3rd-party HTTP faked
at the capability level).

Fixture hierarchy:
- `base_url` — application base URL (from env or default to localhost)
- `auth_headers` — default authorization headers for authenticated requests
- `http_client` — httpx.AsyncClient bound to the base URL
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL for the running application.

    Sourced from the environment variable ``BASE_URL`` (for CI/staging deploys)
    or defaults to ``http://localhost:8000`` for local development.

    Returns:
        str — the base URL (scheme + host + port).
    """
    return os.environ.get("BASE_URL", "http://localhost:8000")


@pytest.fixture
async def http_client(base_url: str) -> AsyncGenerator[AsyncClient, None]:
    """httpx.AsyncClient bound to the running application.

    Scope: function — a fresh client per test to avoid connection pooling
    artifacts or stale auth state between tests.

    Args:
        base_url: The base URL to bind to.

    Yields:
        AsyncClient — ready for requests to the app.
    """
    async with AsyncClient(app=app, base_url=base_url) as client:
        yield client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Default authorization headers for authenticated e2e requests.

    This is a placeholder fixture. In a real implementation, it would:
    - Call a login endpoint to obtain a token
    - Return headers with the bearer token
    - Or return headers with a test user's credentials

    For now it returns an empty dict (no auth), suitable for testing
    unauthenticated routes. Override this fixture in specific test files
    that need authentication.

    Returns:
        dict[str, str] — HTTP headers with authorization (empty by default).
    """
    # Example implementation (adjust to your auth scheme):
    # return {"Authorization": "Bearer <test-token>"}
    return {}


@pytest.fixture
async def authenticated_client(
    http_client: AsyncClient, auth_headers: dict[str, str]
) -> AsyncClient:
    """httpx.AsyncClient with default authorization headers applied.

    Scope: function — a fresh authenticated client per test.

    Args:
        http_client: The base HTTP client.
        auth_headers: Headers to apply (Authorization token, etc.).

    Returns:
        AsyncClient — with auth headers pre-applied to all requests.
    """
    http_client.headers.update(auth_headers)
    return http_client
