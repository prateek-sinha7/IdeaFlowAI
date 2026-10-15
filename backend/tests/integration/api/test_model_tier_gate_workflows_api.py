"""QA-KB-017 / ISS-398 (+ ISS-934, ISS-935) -- saving a workflow must not let a
basic-tier account persist a premium model, through ANY of the three doors the
product uses: ``model_overrides``, ``selections[*].model`` and manifest
``steps[].model``; on create (POST) and update (PATCH).

Offline: the ``api`` harness of test_user_workflows_api.py (in-memory SQLite,
overridden principal). No engine, no model call.
"""

from __future__ import annotations

import json

import pytest

from app.models.workflow_definition import WorkflowDefinition
from tests.integration.api.test_user_workflows_api import (  # noqa: F401
    _FakeUser,
    _make_wf,
    api,
    db_session,
)

_OPUS = "eu.anthropic.claude-opus-4-6-v1"
_CHEAP = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
_AGENT = "domain-analyst"


def _body(door: str, model: str) -> dict:
    body = {
        "name": f"tier-gate-{door}",
        "base_pipeline_type": "user_stories",
        "agent_ids": [_AGENT],
    }
    if door == "model_overrides":
        body["model_overrides"] = {_AGENT: model}
    elif door == "selections":
        body["selections"] = {_AGENT: {"model": model}}
    else:
        body["manifest"] = {"steps": [{"agent": _AGENT, "model": {"model": model}}]}
        body["overrides_pipeline_type"] = "user_stories"
    return body


def _patch_body(door: str, model: str) -> dict:
    body = _body(door, model)
    for k in ("name", "base_pipeline_type", "agent_ids", "overrides_pipeline_type"):
        body.pop(k, None)
    return body


_DOORS = ("model_overrides", "selections", "manifest")
_ISSUE = {"model_overrides": "ISS-398", "selections": "ISS-934", "manifest": "ISS-935"}


def _xfail(door):
    return [pytest.mark.issue(_ISSUE[door])]


def _door_params():
    return [pytest.param(d, marks=_xfail(d), id=d) for d in _DOORS]


@pytest.mark.parametrize("door", _door_params())
def test_basic_create_with_premium_model_is_403(api, db_session, door):
    client, state = api
    state["user"] = _FakeUser(id="owner", tier="basic")
    r = client.post("/api/user-workflows", json=_body(door, _OPUS))
    assert r.status_code == 403, r.text
    assert db_session.query(WorkflowDefinition).count() == 0


@pytest.mark.parametrize("door", _door_params())
def test_basic_patch_with_premium_model_is_403(api, db_session, door):
    client, state = api
    state["user"] = _FakeUser(id="owner", tier="basic")
    _make_wf(
        db_session,
        wf_id="row",
        user_id="owner",
        base_pipeline_type="user_stories",
        agents=json.dumps([_AGENT]),
    )
    r = client.patch("/api/user-workflows/row", json=_patch_body(door, _OPUS))
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("door", _DOORS)
@pytest.mark.parametrize(
    "tier,model", [("pro", _OPUS), ("enterprise", _OPUS), ("basic", _CHEAP)]
)
def test_entitled_create_still_succeeds(api, door, tier, model):
    client, state = api
    state["user"] = _FakeUser(id="owner", tier=tier)
    r = client.post("/api/user-workflows", json=_body(door, model))
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("door", _DOORS)
@pytest.mark.parametrize("tier,model", [("pro", _OPUS), ("basic", _CHEAP)])
def test_entitled_patch_still_succeeds(api, db_session, door, tier, model):
    client, state = api
    state["user"] = _FakeUser(id="owner", tier=tier)
    _make_wf(
        db_session,
        wf_id="row",
        user_id="owner",
        base_pipeline_type="user_stories",
        agents=json.dumps([_AGENT]),
    )
    r = client.patch("/api/user-workflows/row", json=_patch_body(door, model))
    assert r.status_code == 200, r.text
