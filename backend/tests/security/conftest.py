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


# --- AI Workflow Builder fixtures ------------------------------------------------------
#
# ``test_workflow_builder_access.py`` and ``test_workflow_builder_idor.py`` mount the
# real builder router on a minimal app (``builder_world.BuilderWorld``). The IDOR file
# also runs it over real PostgreSQL.

# Re-exported so ``builder_pg_engine`` can ask for the shared testcontainers server by
# name. They are the unchanged fixtures of ``tests/integration/conftest.py``.
from tests.integration.conftest import (  # noqa: E402, F401
    database_url,
    postgres_container,
)
from tests.security.builder_world import BuilderWorld, WorldKind  # noqa: E402


def _postgres_admin_url_or_skip(request: pytest.FixtureRequest) -> str:
    """Server-level PostgreSQL URL: the env override, else the testcontainers server.

    ``PYTEST_POSTGRES_ADMIN_URL`` wins when set. Without it the shared testcontainers
    server needs Docker. When neither is available, a local run skips the PostgreSQL
    variants with the reason, so a Docker-less ``pytest tests/security`` stays green.
    On CI (``CI`` set) the same situation fails the test, so the IDOR proof on the
    real store cannot disappear silently.
    """
    import os

    override = os.environ.get("PYTEST_POSTGRES_ADMIN_URL")
    if override:
        return override
    try:
        return str(request.getfixturevalue("database_url"))
    except Exception as exc:  # noqa: BLE001 - any Docker/testcontainers failure
        if os.environ.get("CI"):
            pytest.fail(
                f"no PostgreSQL available on CI (set PYTEST_POSTGRES_ADMIN_URL or "
                f"start Docker): {type(exc).__name__}"
            )
        pytest.skip(
            f"no PostgreSQL available (set PYTEST_POSTGRES_ADMIN_URL or start "
            f"Docker): {type(exc).__name__}"
        )


@pytest.fixture(scope="module")
def builder_pg_engine(request: pytest.FixtureRequest):
    """Engine on a throwaway PostgreSQL database migrated to Alembic head.

    Isolates the builder security tests from every other database: the database is
    created for the module and dropped afterwards.
    """
    from alembic import command
    from sqlalchemy import create_engine

    from tests.integration.db.conftest import alembic_config_for, throwaway_database

    admin_url = _postgres_admin_url_or_skip(request)
    with throwaway_database(admin_url, "wbsecurity") as url:
        command.upgrade(alembic_config_for(url), "head")
        engine = create_engine(url, pool_pre_ping=True)
        try:
            yield engine
        finally:
            engine.dispose()


@pytest.fixture
def make_builder_world(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    """Factory for ``BuilderWorld``: the builder router, callers, store and spies.

    Every world made is closed at teardown, which also empties the process-wide Turn
    registries and the event bus the world replaced.
    """
    worlds: list[BuilderWorld] = []

    def make(
        *,
        kind: WorldKind = "in_memory",
        real_auth: bool = False,
        real_stream: bool = False,
    ) -> BuilderWorld:
        engine = (
            request.getfixturevalue("builder_pg_engine") if kind == "postgres" else None
        )
        world = BuilderWorld(
            kind=kind,
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            engine=engine,
            real_auth=real_auth,
            real_stream=real_stream,
        )
        worlds.append(world)
        return world

    yield make
    for world in worlds:
        world.close()
