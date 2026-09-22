"""Shared fixtures for the security suite.

Security tests focus on adversarial intent: authentication bypass, authorization
escalation, injection attacks, rate limiting, and hardening validations.

Tests in this suite typically use:
- `client` fixture (TestClient with dependency_overrides, from tests/unit/api/*/routers/conftest.py)
- `http_client` fixture (AsyncClient for full-stack attacks, from tests/e2e/conftest.py)
- Custom fixtures below for adversarial scenarios (e.g., unauthenticated_client, invalid_token_client)
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.fixture
async def unauthenticated_client(
    base_url: str = "http://localhost:8000",
) -> AsyncGenerator[AsyncClient, None]:
    """httpx.AsyncClient with NO authorization headers.

    Use this to test that endpoints requiring authentication correctly reject
    unauthenticated requests.

    Args:
        base_url: Application base URL (defaults to localhost).

    Yields:
        AsyncClient — bound to the app, with no auth headers.
    """
    async with AsyncClient(app=app, base_url=base_url) as client:
        # Explicitly ensure no auth headers
        if "Authorization" in client.headers:
            del client.headers["Authorization"]
        yield client


@pytest.fixture
async def invalid_token_client(
    base_url: str = "http://localhost:8000",
) -> AsyncGenerator[AsyncClient, None]:
    """httpx.AsyncClient with an invalid/expired authorization token.

    Use this to test that endpoints correctly reject invalid tokens.

    Args:
        base_url: Application base URL (defaults to localhost).

    Yields:
        AsyncClient — bound to the app, with an invalid Bearer token.
    """
    async with AsyncClient(app=app, base_url=base_url) as client:
        client.headers["Authorization"] = "Bearer invalid_token_12345"
        yield client


@pytest.fixture
async def rate_limited_client(
    base_url: str = "http://localhost:8000",
) -> AsyncGenerator[AsyncClient, None]:
    """httpx.AsyncClient for testing rate-limiting.

    Use this to make rapid requests and verify that rate-limit headers and
    429 responses are returned appropriately.

    Args:
        base_url: Application base URL (defaults to localhost).

    Yields:
        AsyncClient — bound to the app, suitable for hammer testing.
    """
    async with AsyncClient(app=app, base_url=base_url) as client:
        yield client
