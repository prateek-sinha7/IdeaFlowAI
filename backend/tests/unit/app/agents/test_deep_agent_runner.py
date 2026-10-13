"""Unit tests for the reserved-path READ denial text in ``app/agents/deep_agent_runner.py``.

The denial message must list every agent-readable reserved prefix, derived from
``AGENT_READABLE_RESERVED`` itself, so it cannot drift from what the guard allows.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.deep_agent_runner import (
    _read_denied_message,
    _ReservedPathGuardMiddleware,
)
from app.agents.sandbox import AGENT_READABLE_RESERVED


def test_read_denied_message_lists_every_agent_readable_prefix_when_built():
    message = _read_denied_message("ls", "/.logs")

    assert message.startswith("Tool 'ls' is not permitted to read '/.logs'")
    for prefix in AGENT_READABLE_RESERVED:
        assert prefix in message
    assert ".chain/" not in message


def test_refusal_returns_listing_message_when_reading_unreadable_reserved_path():
    request = SimpleNamespace(
        tool_call={"name": "ls", "args": {"path": "/.logs"}, "id": "call-1"}
    )

    refusal = _ReservedPathGuardMiddleware()._refusal(request)

    assert refusal is not None
    assert refusal.content == _read_denied_message("ls", "/.logs")
