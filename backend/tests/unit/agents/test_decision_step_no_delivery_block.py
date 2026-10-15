"""ISS-1156 (QA-KB-124) — a step whose reply IS a typed route_decision must not be
told to deliver its answer via write_file (the conditional gate reads only the reply)."""

from __future__ import annotations

import dataclasses

import pytest

from agents.factory import AgentContext, _compose_system_prompt
from agents.loader import load_agent_spec

_CTX = AgentContext(
    user_request="x", topic="t", step_prompt='Reply exactly: {"decision": "retry"}'
)


@pytest.mark.issue("ISS-1156")
def test_route_decision_step_gets_no_write_file_delivery_block():
    spec = dataclasses.replace(
        load_agent_spec("custom-agent:check"), produces=["route_decision"]
    )
    composed = _compose_system_prompt(spec, _CTX, no_tools=False)
    assert "How to deliver" not in composed


def test_plain_custom_step_with_write_access_still_gets_delivery_block():
    spec = load_agent_spec("custom-agent:check")
    assert "How to deliver" in _compose_system_prompt(spec, _CTX, no_tools=False)
