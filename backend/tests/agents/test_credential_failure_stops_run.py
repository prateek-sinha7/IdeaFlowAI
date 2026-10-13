"""A provider credential failure ends the run at that step (run 715c1279).

After the Bedrock key expired, one step failed on credentials and the engine started
eight more, each failing within a second on the same dead credential, until a
missing-file error hid the real cause. Now the run stops at the first one, naming
it, so a resume after the credential is fixed starts there.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# Keep first: forces the InMemory checkpointer + a temp RUNS_ROOT.
from tests.agents._scripted_model import _drive

import agents.execution_engine.engine as engine_mod
from agents.execution_engine.engine import (
    _CREDENTIAL_AGENT_ERROR,
    _sanitize_agent_error,
)


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


@pytest.mark.asyncio
async def test_a_credential_failure_fails_the_run_at_that_step():
    dispatched: list = []
    with patch.object(
        engine_mod.ExecutionEngine,
        "_dispatch_step_with_retry",
        _failing_dispatch(_CREDENTIAL_AGENT_ERROR, dispatched),
    ):
        events = await _drive("custom")

    assert len(dispatched) == 1, dispatched
    failed = [e["data"] for e in events if e["type"] == "pipeline_failed"]
    assert len(failed) == 1 and failed[0]["error"] == _CREDENTIAL_AGENT_ERROR
    assert failed[0]["agents_failed"] == dispatched
    assert not [e for e in events if e["type"] == "pipeline_complete"]


@pytest.mark.asyncio
async def test_any_other_step_error_keeps_the_old_behaviour():
    # Control: a non-credential failure still lets the run carry on to later steps.
    dispatched: list = []
    with patch.object(
        engine_mod.ExecutionEngine,
        "_dispatch_step_with_retry",
        _failing_dispatch("The model rejected this request.", dispatched),
    ):
        await _drive("custom")
    assert len(dispatched) > 1


def test_provider_5xx_names_itself_and_credentials_still_classify():
    assert _sanitize_agent_error("ServiceUnavailableException: try again") == (
        "The model service was temporarily unavailable."
    )
    assert (
        _sanitize_agent_error("ExpiredTokenException: expired")
        == _CREDENTIAL_AGENT_ERROR
    )
    assert (
        _sanitize_agent_error("Read timeout on endpoint URL")
        == "The model did not respond in time."
    )
