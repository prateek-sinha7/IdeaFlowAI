"""ISS-981 — the duplicate-context guard must audit only a strip that actually happened.

Edge behaviours the 8 tests in test_duplicate_context_guard_api.py never reach. Uses that file's
harness pieces but with a working fixture (principal override, tmp RUNS_ROOT, admissible source).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import agents.execution_engine.engine as engine_mod
import app.api.run_commands as rc_module
from app.api import run_engine as ws_module
from app.core.config import settings
from app.core.dependencies import get_current_principal, get_current_user
from app.models.database import Base
from app.models.run_provenance_audit import RunProvenanceAudit
from tests.fakes.principal import principal_for
from tests.integration.api import test_duplicate_context_guard_api as T

pytestmark = [
    pytest.mark.issue("ISS-981"),
]

_BRIEF_PLUS_BLOCK = "Build me a backlog" + T._LEGACY_BLOCK
_ONLY_BLOCK = T._LEGACY_BLOCK.lstrip("\n")


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path / "runs"))
    db_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: Session())
    monkeypatch.setattr(rc_module, "_get_db", lambda: Session())
    T._RecordingEngine.invoked = False
    monkeypatch.setattr(
        engine_mod, "get_execution_engine", lambda: T._RecordingEngine()
    )

    app = FastAPI()
    app.include_router(rc_module.router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_current_principal] = lambda: (
        state["user"],
        principal_for(state["user"]),
    )
    yield {"ws": ws_module, "client": TestClient(app), "state": state}
    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _admissible_source(env, user_id):
    """Legacy-shaped source the admission gate accepts: bare row + .chain/<id>/summary.md."""
    from app.agents.sandbox import RunSandbox

    run = T._seed_source_run(env, user_id)
    sb = RunSandbox(user_id, run.id)
    sb.ensure()
    sb.write(f".chain/{run.id}/summary.md", f"run_id: {run.id}\n")
    return run


def _strip_rows(env, user_id):
    db = env["ws"]._get_db()
    try:
        return (
            db.query(RunProvenanceAudit)
            .filter(
                RunProvenanceAudit.owner_id == user_id,
                RunProvenanceAudit.operation == "legacy_context_block_stripped",
            )
            .all()
        )
    finally:
        db.close()


def test_refused_launch_leaves_no_pending_strip_audit(env):
    """ISS-981 A: a launch refused at admission mints no run, so no strip row may be left."""
    user = T._seed_user(env)
    env["state"]["user"] = user
    bare = T._seed_source_run(env, user.id)  # no payload -> 422 source_payload_missing
    resp = T._post_launch(
        env,
        message=_BRIEF_PLUS_BLOCK,
        pipeline_type="user_stories",
        source_workflow_run_id=bare.id,
    )
    assert resp.status_code == 422, resp.text
    assert [r.run_id for r in _strip_rows(env, user.id)] == []


def test_block_only_message_is_not_audited_as_stripped_twice(env):
    """ISS-981 B: a message that is only the legacy block strips nothing; at most one honest row."""
    user = T._seed_user(env)
    env["state"]["user"] = user
    src = _admissible_source(env, user.id)
    resp = T._post_launch(
        env,
        message=_ONLY_BLOCK,
        pipeline_type="user_stories",
        source_workflow_run_id=src.id,
    )
    assert resp.status_code == 200, resp.text
    assert len(_strip_rows(env, user.id)) == 0
