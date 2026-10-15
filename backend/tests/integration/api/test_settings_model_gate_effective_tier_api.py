"""QA-KB-083 / ISS-937 -- the settings model gate must read the EFFECTIVE tier
(``cognito:groups`` via ``effective_tier(user, principal)``), not the advisory
``users.tier`` column (ADR-0013).

Offline: a tiny app with only the settings router; the user's tier column and the
token's groups are set to disagree, which is the only way to tell which one the
gate consulted.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.settings import router as settings_router
from app.core.dependencies import get_current_principal, get_current_user
from app.core.entitlements import group_for_tier
from app.models.database import get_db
from tests.fakes.principal import principal_for

_OPUS = "eu.anthropic.claude-opus-4-6-v1"


class _FakeUser:
    def __init__(self, *, tier: str):
        self.id = "owner"
        self.email = "owner@example.com"
        self.cognito_sub = "sub-owner"
        self.tier = tier
        self.is_admin = False
        self.status = "active"
        self.preferred_model = None


@pytest.fixture()
def api():
    app = FastAPI()
    app.include_router(settings_router)
    state: dict = {}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_current_principal] = lambda: (
        state["user"],
        principal_for(state["user"], groups=state["groups"]),
    )
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app), state


def _allowed(resp, model_id=_OPUS) -> bool:
    return next(m for m in resp.json()["available_models"] if m["id"] == model_id)[
        "allowed"
    ]


@pytest.mark.issue("ISS-937")
def test_put_premium_model_refused_when_groups_say_basic_but_column_says_pro(api):
    """ISS-937 -- column pro, token groups basic: PUT must be 403."""
    client, state = api
    state["user"] = _FakeUser(tier="pro")
    state["groups"] = [group_for_tier("basic")]
    r = client.put("/api/settings/preferences", json={"preferred_model": _OPUS})
    assert r.status_code == 403, r.text


@pytest.mark.issue("ISS-937")
def test_get_marks_premium_disallowed_when_groups_say_basic_but_column_says_pro(api):
    """ISS-937 -- GET must report allowed=false from the effective tier."""
    client, state = api
    state["user"] = _FakeUser(tier="pro")
    state["groups"] = [group_for_tier("basic")]
    r = client.get("/api/settings/preferences")
    assert r.status_code == 200, r.text
    assert _allowed(r) is False


@pytest.mark.issue("ISS-937")
def test_get_marks_premium_allowed_when_groups_say_pro_but_column_says_basic(api):
    """ISS-937 -- the mirror: a pro token must not be refused by a basic column."""
    client, state = api
    state["user"] = _FakeUser(tier="basic")
    state["groups"] = [group_for_tier("pro")]
    r = client.get("/api/settings/preferences")
    assert r.status_code == 200, r.text
    assert _allowed(r) is True
