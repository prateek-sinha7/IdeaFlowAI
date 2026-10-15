"""ISS-687 / ISS-976 / ISS-978 (QA-KB-054) — a custom-agent file workflow's own roster.

Compiled ids of e.g. ``prototype_v2`` are ``custom-agent:<instance_id>`` with no AGENT.md,
so ``allowed_custom_agent_ids`` can never contain them. Launch (and save) must accept a
workflow's own roster, and the stale-override message must not blame a saved override for it.
"""

from __future__ import annotations

import re

import pytest

from agents.execution_engine.engine import ExecutionEngine, compile_for_run
from tests.integration.api.test_rest_run_launch_api import (  # noqa: F401
    _RecordingEngine,
    _post_launch,
    _run_count,
    _seed_user,
    env,
)
from tests.integration.api.test_user_workflows_api import (  # noqa: F401
    _valid_body,
    api,
    db_session,
)


def _plan(pipeline: str) -> list[str]:
    """The workflow's own roster: EVERY step id of its compiled plan. A partial list is
    an edited roster, which ISS-687 keeps rejected (see the last test)."""
    return [s.agent_id for s in compile_for_run(pipeline).steps]


@pytest.mark.issue("ISS-687")
def test_launch_with_own_custom_agent_roster_succeeds(env, monkeypatch):  # noqa: F811
    """ISS-687 — prototype_v2 launched with its own compiled ids must not 400."""
    # The launch then builds its roster from the compiled plan via _specs_from_plan,
    # which the stub engine lacks; the real method reads no engine state.
    monkeypatch.setattr(
        _RecordingEngine,
        "_specs_from_plan",
        ExecutionEngine._specs_from_plan,
        raising=False,
    )
    env["state"]["user"] = _seed_user(env)
    resp = _post_launch(
        env,
        message="build it",
        pipeline_type="prototype_v2",
        agent_ids=_plan("prototype_v2"),
    )
    assert resp.status_code < 400, resp.text
    assert _run_count(env) == 1


@pytest.mark.issue("ISS-978")
def test_override_sentence_does_not_blame_plan_member_ids(env):  # noqa: F811
    """ISS-978 — a plan-member id must not be reported as a stale saved-override step."""
    env["state"]["user"] = _seed_user(env)
    resp = _post_launch(
        env,
        message="build it",
        pipeline_type="prototype_v2",
        agent_ids=["custom-agent:fi-planner", "custom-agent:ghost-not-in-plan"],
    )
    assert resp.status_code == 400
    message = resp.json()["detail"]["error"]
    blame = [s for s in re.split(r"(?<=\.)\s", message) if "override" in s.lower()]
    assert all("fi-planner" not in s for s in blame), message


@pytest.mark.issue("ISS-976")
@pytest.mark.parametrize("pipeline", ["prototype_v2", "backlog"])
def test_save_flat_custom_agent_roster_succeeds(api, pipeline):  # noqa: F811
    """ISS-976 — save == launch: the workflow's own flat roster must be savable."""
    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(
            name=f"iss976-{pipeline}",
            base_pipeline_type=pipeline,
            agent_ids=_plan(pipeline),
            model_overrides=None,
        ),
    )
    assert r.status_code == 201, r.text


@pytest.mark.issue("ISS-687")
def test_edited_own_roster_is_still_rejected(env, api):  # noqa: F811
    """ISS-687 / ISS-976 — a roster missing one plan step is NOT run as the full plan
    (that would run the step the caller removed): launch 400s pre-mint, save 422s."""
    edited = _plan("prototype_v2")[:-1]
    env["state"]["user"] = _seed_user(env)
    resp = _post_launch(
        env, message="build it", pipeline_type="prototype_v2", agent_ids=edited
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["code"] == "invalid_agent_ids"
    assert _run_count(env) == 0

    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(
            name="iss976-edited",
            base_pipeline_type="prototype_v2",
            agent_ids=edited,
            model_overrides=None,
        ),
    )
    assert r.status_code == 422, r.text
