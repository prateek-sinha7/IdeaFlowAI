"""ISS-1113 — an override row launched by user_workflow_id must not gain more trust
than merge_override_steps gives its steps.

The compiler is stubbed to record the trust it is called with and then refuse, so
the launch stops at a 422 before any run is minted (a real launch costs money).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.run_commands as rc
from agents.workflows.compiler import CompilerError
from app.core.dependencies import get_current_principal
from app.models.database import Base
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for


class _FakeUser:
    def __init__(self, id: str, tier: str):
        self.id = id
        self.tier = tier


@pytest.mark.issue("ISS-1113")
def test_launching_an_override_row_by_id_compiles_below_db_trust(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    user = _FakeUser("owner", "basic")
    row = WorkflowDefinition(
        id="ovr-1",
        user_id="owner",
        name="My Deck",
        agents="[]",
        artifact_edges="[]",
        source="user",
        base_pipeline_type="ppt",
        overrides_pipeline_type="ppt",
        override_enabled=True,
        manifest_json={
            "steps": [
                {
                    "agent": "custom-agent",
                    "instance_id": "mine",
                    "name": "mine",
                    "prompt": "x",
                    "tools": {"read_files": False, "write_files": False, "exec": False},
                    "gates": ["security"],
                }
            ]
        },
    )
    session.add(row)
    session.commit()

    seen = {}

    def fake_compile(self, parsed, registry, trust="file"):
        seen["trust"] = trust
        raise CompilerError("stop before mint")

    monkeypatch.setattr(rc, "_get_db", lambda: session, raising=False)
    monkeypatch.setattr(session, "close", lambda: None)
    from agents.workflows.compiler import WorkflowCompiler

    monkeypatch.setattr(WorkflowCompiler, "compile", fake_compile)

    app = FastAPI()
    app.include_router(rc.router)
    app.dependency_overrides[get_current_principal] = lambda: (
        user,
        principal_for(user),
    )
    try:
        TestClient(app).post(
            "/api/runs",
            json={"message": "go", "pipeline_type": "ppt", "user_workflow_id": "ovr-1"},
        )
        assert seen.get("trust") == "user", seen
    finally:
        Base.metadata.drop_all(bind=engine)
