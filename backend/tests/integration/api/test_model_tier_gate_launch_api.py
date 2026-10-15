"""QA-KB-017 / ISS-398 (+ ISS-934, ISS-935) -- launching a run must not let a
basic-tier account run a premium model through any of the three doors:
``model_overrides``, ``selections[*].model`` and manifest ``steps[].model``
(inline manifest == launch Case 3, which skips the override validator).

Offline: the ``env`` harness of test_rest_run_launch_api.py (recording stub
engine, in-memory SQLite). No Bedrock, no paid run.
"""

from __future__ import annotations

import pytest

from tests.integration.api.test_rest_run_launch_api import (  # noqa: F401
    _post_launch,
    _RecordingEngine,
    _run_count,
    _seed_user,
    env,
)

_OPUS = "eu.anthropic.claude-opus-4-6-v1"
_CHEAP = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
_AGENT = "domain-analyst"


def _manifest_step(model: str) -> dict:
    return {
        "agent": "custom-agent",
        "instance_id": "a1",
        "name": "A1",
        "prompt": "Do the thing.",
        "model": {"model": model},
    }


def _body(door: str, model: str) -> dict:
    body = {"message": "build a backlog", "pipeline_type": "user_stories"}
    if door == "model_overrides":
        body["model_overrides"] = {_AGENT: model}
    elif door == "selections":
        body["selections"] = {_AGENT: {"model": model}}
    elif door == "manifest":
        body["manifest"] = {"steps": [_manifest_step(model)]}
    else:  # Case 3 body override map: validator skipped for manifest launches
        body["manifest"] = {"steps": [_manifest_step(_CHEAP)]}
        body["model_overrides"] = {"custom-agent:a1": model}
    return body


_ISSUE = {
    "model_overrides": "ISS-398",
    "selections": "ISS-934",
    "manifest": "ISS-935",
    "manifest_body_overrides": "ISS-935",
}
_DOORS = tuple(_ISSUE)


def _launch(env, tier, door, model):
    user = _seed_user(env)
    user.tier = tier
    env["state"]["user"] = user
    return _post_launch(env, **_body(door, model))


@pytest.mark.parametrize(
    "door",
    [
        pytest.param(
            d,
            marks=[pytest.mark.issue(_ISSUE[d])],
            id=d,
        )
        for d in _DOORS
    ],
)
def test_basic_launch_with_premium_model_is_403(env, door):
    resp = _launch(env, "basic", door, _OPUS)
    assert resp.status_code == 403, resp.text
    assert _run_count(env) == 0
    assert _RecordingEngine.invoked is False


@pytest.mark.parametrize("door", _DOORS)
@pytest.mark.parametrize(
    "tier,model", [("pro", _OPUS), ("enterprise", _OPUS), ("basic", _CHEAP)]
)
def test_entitled_launch_still_succeeds(env, door, tier, model):
    resp = _launch(env, tier, door, model)
    assert resp.status_code == 200, resp.text
    assert _run_count(env) == 1


@pytest.mark.issue("ISS-936")
def test_downgraded_account_stored_premium_preference_not_used(env):
    """A basic caller holding a stale premium preferred_model must not have it
    handed to the engine as the session model."""
    user = _seed_user(env)
    user.tier = "basic"
    user.preferred_model = _OPUS
    env["state"]["user"] = user
    resp = _post_launch(env, message="build a backlog", pipeline_type="user_stories")
    assert resp.status_code == 200, resp.text
    assert _RecordingEngine.last_kwargs.get("model_id") != _OPUS


def test_pro_preferred_premium_model_still_honoured(env):
    user = _seed_user(env)
    user.tier = "pro"
    user.preferred_model = _OPUS
    env["state"]["user"] = user
    resp = _post_launch(env, message="build a backlog", pipeline_type="user_stories")
    assert resp.status_code == 200, resp.text
    assert _RecordingEngine.last_kwargs.get("model_id") == _OPUS
