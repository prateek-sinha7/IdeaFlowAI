"""ISS-1199 (QA-KB-121) - a Bedrock key that Bedrock rejects reads as an invalid key to rotate.

The expiry-only preflight stays (owner decision 2026-10-09); the defect is the message the
user gets at the first model call, and the run-stop (FIX-657) must recognise it too.
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

# Keep first: forces the InMemory checkpointer + a temp RUNS_ROOT.
from tests.agents._scripted_model import _drive

import agents.execution_engine.engine as engine_mod
from agents.execution_engine.engine import (
    _CREDENTIAL_AGENT_ERROR,
    _GENERIC_AGENT_ERROR_MESSAGE,
    _sanitize_agent_error,
)

_TAIL = " when calling the ConverseStream operation: API Key invalid"
RAWS = {
    "AccessDeniedException": "An error occurred (AccessDeniedException)" + _TAIL,
    "403": "An error occurred (403)" + _TAIL,
    "AccessDenied": "An error occurred (AccessDenied)" + _TAIL,
}
_SECURITY_GATE_RE = re.compile(
    r"security.*gate|blocked.*security|exec.*denied|exec.*off|secret.*scan|secret.*blocked"
    r"|credential.*blocked|hook.*block",
    re.I,
)


@pytest.mark.issue("ISS-1199")
@pytest.mark.parametrize("code", list(RAWS))
def test_rejected_key_message_says_invalid_key_and_rotate(code):
    """ISS-1199 - the user is told the API key is invalid and must be rotated."""
    msg = _sanitize_agent_error(RAWS[code])
    assert msg != _CREDENTIAL_AGENT_ERROR
    assert msg != _GENERIC_AGENT_ERROR_MESSAGE
    low = msg.lower()
    assert "api key" in low and "rotate" in low
    assert len(msg) < 400
    assert not _SECURITY_GATE_RE.search(msg)


def _failing_dispatch(message: str, dispatched: list):
    async def _dispatch(self, step, ectx, strategy):
        agent_id = getattr(step, "agent_id", "?")
        dispatched.append(agent_id)
        yield {"type": "agent_start", "data": {"agent_id": agent_id}}
        yield {
            "type": "agent_error",
            "data": {"agent_id": agent_id, "error": message, "recoverable": True},
        }

    return _dispatch


@pytest.mark.issue("ISS-1199")
@pytest.mark.asyncio
async def test_rejected_key_stops_the_run_at_the_first_step():
    """ISS-1199 - the new message must still trigger the FIX-657 run-stop."""
    msg = _sanitize_agent_error(RAWS["AccessDeniedException"])
    assert (
        msg != _CREDENTIAL_AGENT_ERROR
    )  # otherwise this proves nothing about the new copy
    dispatched: list = []
    with patch.object(
        engine_mod.ExecutionEngine,
        "_dispatch_step_with_retry",
        _failing_dispatch(msg, dispatched),
    ):
        events = await _drive("custom")
    assert len(dispatched) == 1, dispatched
    failed = [e["data"] for e in events if e["type"] == "pipeline_failed"]
    assert len(failed) == 1 and failed[0]["error"] == msg
    assert failed[0]["agents_failed"] == dispatched
    assert not [e for e in events if e["type"] == "pipeline_complete"]
