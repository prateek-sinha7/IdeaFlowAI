"""``cognito:groups`` is the ONLY entitlement authority; the DB column is inert.

Decision 3 of the Cognito-only auth migration
(``.kiro/specs/login/prompt.md``): "Groups are the only entitlement authority for
every principal... No gate may read the projection alone; ``_require_tier_entitlement``
must use ``effective_tier()``."

Every test here works by making the two sources DISAGREE. That is the only way to
tell which one a gate actually consulted: while ``users.tier`` and
``cognito:groups`` agree -- which they do on any ordinary request, because login
and the projection refresh keep them in step -- a gate reading the wrong one is
indistinguishable from a gate reading the right one, and the suite stays green
either way. That is precisely how ``_require_tier_entitlement`` came to read the
DB column unnoticed (recorded in ``MERGE_NOTES.md`` §3).

The disagreement is not contrived. It is the steady state for a bounded window
after every admin tier change: ``admin.py::update_user_tier`` mutates the Cognito
groups and stamps the projection, but any access token already in the user's hands
still carries the OLD groups until it expires or they re-authenticate.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.workflow_definition  # noqa: F401 - register the table
from app.api.user_workflows import router as user_workflows_router
from app.core.dependencies import get_current_principal, get_current_user
from app.core.entitlements import group_for_tier
from app.models.database import Base, get_db
from tests.fakes.principal import principal_for


class _FakeUser:
    """A ``User`` stand-in whose ``tier`` column is deliberately a lie."""

    def __init__(self, *, tier: str, is_admin: bool = False):
        self.id = "owner"
        self.email = "owner@example.com"
        self.cognito_sub = "sub-owner"
        self.tier = tier
        self.is_admin = is_admin
        self.status = "active"
        self.preferred_model = None


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def api(db_session):
    """``(client, state)``. ``state["user"]`` carries the DB projection;
    ``state["groups"]`` carries what the TOKEN says. Set them apart to prove
    which one a gate reads."""
    app = FastAPI()
    app.include_router(user_workflows_router)

    state: dict = {"user": _FakeUser(tier="basic"), "groups": None}

    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_current_principal] = lambda: (
        state["user"],
        principal_for(state["user"], groups=state["groups"]),
    )

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), state


def _custom_workflow_body() -> dict:
    """A ``custom`` composition — the entitlement TIER_PIPELINES reserves for
    enterprise, so it is the cleanest probe of the tier gate."""
    return {
        "name": "probe",
        "base_pipeline_type": "custom",
        "agent_ids": ["market-research-agent", "swot-analyst"],
    }


class TestProjectionCannotGrant:
    def test_an_enterprise_db_column_with_basic_groups_is_denied(self, api):
        """The security-critical direction: a stale or tampered DB row must not
        buy an entitlement the live token does not carry."""
        client, state = api
        state["user"] = _FakeUser(tier="enterprise")
        state["groups"] = [group_for_tier("basic")]

        resp = client.post("/api/user-workflows", json=_custom_workflow_body())

        assert resp.status_code == 403
        # The upgrade prompt is computed from the EFFECTIVE tier too, so it names
        # basic's next step (pro) rather than the column's claimed enterprise.
        assert "pro or higher" in resp.json()["detail"].lower()

    def test_a_basic_db_column_with_enterprise_groups_is_allowed(self, api):
        """The mirror direction, which proves the gate is reading the groups
        rather than merely failing closed on everything."""
        client, state = api
        state["user"] = _FakeUser(tier="basic")
        state["groups"] = [group_for_tier("enterprise")]

        resp = client.post("/api/user-workflows", json=_custom_workflow_body())

        assert resp.status_code == 201, resp.text

    def test_a_token_carrying_no_groups_is_least_privileged(self, api):
        """Fail closed: no tier group resolves to DEFAULT_TIER, whatever the
        column says."""
        client, state = api
        state["user"] = _FakeUser(tier="enterprise")
        state["groups"] = []

        resp = client.post("/api/user-workflows", json=_custom_workflow_body())

        assert resp.status_code == 403
