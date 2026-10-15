"""Scratch probe 4 (analyzer) - NOT a repo test. Re-runs the body of the dead ISS-182 test against
the integration harness to show the behaviour it was written to pin still holds today."""
import json

from tests.integration.api.test_rest_run_launch_api import (  # noqa: F401
    _post_launch,
    _run_count,
    _seed_user,
    env,
)


def test_iss182_body_on_live_harness(env):
    env["state"]["user"] = _seed_user(env)
    resp = _post_launch(
        env,
        message="build a backlog",
        pipeline_type="user_stories",
        agent_ids=["custom-agent:legacy-stale-1", "domain-analyst"],
    )
    d = resp.json()["detail"]
    print("\nPROBE-ISS182", resp.status_code, d["code"], "| override sentence present:", "override" in d.get("error", "").lower(), "| rejected:", d["rejected_agent_ids"], "| runs:", _run_count(env))
