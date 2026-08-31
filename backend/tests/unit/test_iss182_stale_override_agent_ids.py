"""tests/unit/test_iss182_stale_override_agent_ids.py — ISS-182.

FIX-306 stopped the composer from OFFERING the blank ``custom-agent`` template
to a built-in override going forward, but did nothing for rows that already
held one. Such a row still fails every launch — reusing exactly the
``invalid_agent_ids`` allow-list rejection FIX-306's fixed test suite covers —
with a bare id dump and no way for the caller to tell it came from THEIR saved
override rather than a malformed direct request.

ISS-182's disposition: "a launch-time message that names the offending step
and points at the fix, instead of a bare 400." This asserts that.

Reuses the REST launch harness from ``test_rest_run_launch.py`` verbatim
rather than re-deriving it.
"""

from __future__ import annotations

import pytest

from tests.unit.test_rest_run_launch import (  # noqa: F401
    _post_launch,
    _run_count,
    _seed_user,
    env,
)


@pytest.mark.issue("ISS-182")
def test_stale_custom_agent_override_error_names_the_fix(env):  # noqa: F811
    """A pre-FIX-306 override still carrying a blank ``custom-agent:<id>`` step
    must not 400 with a bare ``invalid_agent_ids`` list — the caller has no way
    to know that id came from their SAVED OVERRIDE (not something they typed),
    nor where to go fix it. The message must say so.
    """
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(
        env,
        message="build a backlog",
        pipeline_type="user_stories",
        agent_ids=["custom-agent:legacy-stale-1", "domain-analyst"],
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_agent_ids"
    assert "custom-agent:legacy-stale-1" in detail["rejected_agent_ids"]

    message = detail.get("error", "")
    assert "override" in message.lower(), (
        "expected the rejection to point the caller at their saved override "
        f"as the fix, got a bare id dump instead: {message!r}"
    )
    assert _run_count(env) == 0
