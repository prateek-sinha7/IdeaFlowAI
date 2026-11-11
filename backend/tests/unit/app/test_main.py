"""app/main.py's 422 handler never echoes a rejected value (FIX-332; ISS-257, ISS-357, ISS-1017).

``_validation_error_handler`` (``app/main.py``) drops Pydantic's ``input`` key, the
complete value that failed validation, from every 422 body. The test mounts the
real ``app.main.app``: a bare ``FastAPI()`` falls back to FastAPI's stock handler,
which still echoes the value, so it could never see this one (ISS-357).

The vehicle is ``PUT /api/settings/github-pat`` (``GithubPATRequest.pat``,
``min_length=10``). ISS-257's original vehicle, ``POST /api/auth/register``, was
removed by the Cognito-only migration (ISS-1017). Auth and ``get_db`` are
overridden with stubs: body validation fails before the route body runs, so no
engine is opened, and the client is not entered as a context manager, so the
lifespan never runs.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user
from app.models.database import get_db


@pytest.fixture
def client():
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="u1", email="u@example.com"
    )
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.issue("ISS-1017")
def test_validation_error_handler_omits_rejected_value_when_credential_too_short(
    client,
):
    rejected = "short7!"  # 7 chars, below GithubPATRequest.pat min_length=10

    resp = client.put("/api/settings/github-pat", json={"pat": rejected})

    assert resp.status_code == 422, resp.text
    assert (
        rejected not in resp.text
    ), f"the rejected PAT was echoed back in the 422 body: {resp.text[:300]!r}"


class _SchemaRow:
    def first(self) -> tuple[str]:
        return ("0053",)


class _SchemaConnection:
    def __enter__(self) -> _SchemaConnection:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def execute(self, *_args: object, **_kwargs: object) -> _SchemaRow:
        return _SchemaRow()


class _SchemaEngine:
    def connect(self) -> _SchemaConnection:
        return _SchemaConnection()


class TestLifespanArmsResumeRunToolBinder:
    @pytest.mark.asyncio
    async def test_lifespan_arms_resume_run_tool_binder_when_engine_starts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.main as main_module

        binder = object()
        engine_stub = SimpleNamespace(restore_non_terminal_runs=AsyncMock())

        async def _never_ends() -> None:
            await asyncio.sleep(3600)

        monkeypatch.setattr(main_module, "engine", _SchemaEngine())
        monkeypatch.setattr(
            main_module,
            "inspect",
            lambda _engine: SimpleNamespace(has_table=lambda _name: True),
        )
        monkeypatch.setattr(main_module.settings, "HOST_CAPACITY_ENABLED", False)
        monkeypatch.setattr(
            "app.api.workflow_builder.lifecycle.builder_startup", AsyncMock()
        )
        monkeypatch.setattr(
            "app.api.run_shutdown.shutdown_run_infrastructure",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr("app.core.watchdog.watch_event_loop_lag", _never_ends)
        monkeypatch.setattr(
            "app.connectors.services.get_connector_services",
            lambda: SimpleNamespace(
                registry=SimpleNamespace(log_status=lambda: None), binder=binder
            ),
        )
        monkeypatch.setattr(
            "agents.execution_engine.engine.get_execution_engine",
            lambda: engine_stub,
        )

        async with main_module.lifespan(main_module.app):
            assert engine_stub._resume_run_tool_binder is binder
