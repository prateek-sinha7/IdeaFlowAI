"""QA-KB-006 / ISS-128: a gate rejection must persist action='reject'.

Ingresses 2 and 3 of ``set_review_response`` (``run_commands.py`` reject branches of
the /messages CHANNEL_GATE route and the Concierge ``gate_action`` disposal) omit
``action=``, so the REAL store's default stamps 'approve'. Asserts on the store's
recorded dict, not a spy. Ingress 1 lives in test_rest_gate_commands_api.py.
"""

from __future__ import annotations

import uuid

import pytest

# Reuse the in-memory env fixture + seeding helpers of the sibling ingress suite.
from tests.integration.api.test_update_specs_ingress_fence_api import (  # noqa: F401
    _recorded,
    _setup,
    env,
)


@pytest.mark.issue("ISS-128")
def test_messages_route_reject_persists_reject_action(env):
    """Ingress 2: POST /messages action=reject (run_commands.py ~:1965)."""
    _owner, run_id, gate_key = _setup(env, eligible=True, tag="m-rej")

    resp = env["client"].post(
        f"/api/runs/{run_id}/messages",
        json={"message_id": uuid.uuid4().hex, "text": "", "action": "reject"},
    )

    assert resp.status_code == 200, resp.text
    rec = _recorded(env, gate_key)
    assert rec["approved"] is False
    assert (
        rec["action"] == "reject"
    ), f"audit row says {rec['action']!r} for a rejection"


@pytest.mark.issue("ISS-128")
@pytest.mark.asyncio
async def test_concierge_disposal_reject_persists_reject_action(env):
    """Ingress 3: confirmed Concierge gate_action=reject (run_commands.py ~:1599)."""
    from app.agents.chat.concierge import propose_gate_action
    from app.api import run_commands as rc
    from tests.integration.api.test_update_specs_ingress_fence_api import (
        _SpyStore,
        _arm,
    )

    _owner, run_id, gate_key = _setup(env, eligible=True, tag="c-rej")
    _arm(env, gate_key)

    await rc._dispose_concierge_proposal(
        propose_gate_action.func(action="reject", rationale="no"),
        confirmed=True,
        store=_SpyStore(),
        art_store=env["store"],
        run_id=run_id,
        message_id="m-1",
        current_user=env["state"]["user"],
        caller_tier="enterprise",
        wr_status="waiting_for_user",
        wr_type="prototype",
        gate_key=gate_key,
        ectx=None,
    )

    rec = _recorded(env, gate_key)
    assert rec["approved"] is False
    assert (
        rec["action"] == "reject"
    ), f"audit row says {rec['action']!r} for a rejection"
