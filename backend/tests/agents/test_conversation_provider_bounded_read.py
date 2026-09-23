"""ISS-101 — ``context_provider:conversation`` must use the BOUNDED read.

``conversation.py`` calls ``scoped_store.read_events(run_id, 0)`` — the unbounded
replay primitive — then filters to ``chat_message``/``chat_reply`` in Python. On the
worst run in the local corpus that materialises 12,123 rows / ~9.2 MB server-side to
render a <=6,000-char transcript, and FIX-233 made this read UNCONDITIONAL on every
Concierge turn (previously gated behind the model choosing to call a tool).

``ScopedStore.read_events_of_types(run_id, types, limit=…)`` (added by FIX-233) is the
bounded, type-filtered counterpart that pushes the LIMIT into SQL. This test asserts
the provider calls the bounded method, not the unbounded one.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

# Import the scripted-model harness FIRST so its import-time env setup runs (offline).
from tests.agents import _scripted_model  # noqa: F401  (import for side effects)

# Import the compaction impl so its @register fires (the provider resolves it inside load).
from agents.capabilities.compaction.chat_history import ChatHistoryCompaction  # noqa: F401
from agents.capabilities.context_providers.conversation import ConversationProvider


class _FakeRow:
    def __init__(self, etype: str, payload: dict | None) -> None:
        self.type = etype
        self.payload_json = payload


def _chat(text: str, *, reply: bool = False) -> _FakeRow:
    etype = "chat_reply" if reply else "chat_message"
    return _FakeRow(etype, {"pipeline_run_id": "r-conv-1", "text": text})


class _BoundedOnlyStore:
    """A store exposing ONLY the bounded read — the unbounded one is unavailable.

    A production ``ScopedStore`` has both, but this fake proves the provider does not
    depend on ``read_events`` at all: if it were still called, this store would raise
    ``AttributeError`` (no such method), which is the failure this test observes today.
    """

    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    async def read_events_of_types(self, run_id, types, *, limit, after_seq=0):
        return [r for r in self._rows if r.type in types][-limit:]


def _ctx(store):
    return SimpleNamespace(
        scoped_store=store,
        run_id="r-conv-1",
        current_spec_injects={"conversation"},
    )


@pytest.mark.issue("ISS-101")
def test_provider_uses_bounded_read_not_whole_run_log() -> None:
    """ISS-101 — the provider must read via the bounded, type-filtered method."""
    store = _BoundedOnlyStore(
        [
            _chat("build me a dark-theme analytics dashboard"),
            _chat("On it — starting the spec now.", reply=True),
        ]
    )
    provider = ConversationProvider()
    blocks = asyncio.run(provider.load(_ctx(store)))
    assert set(blocks) == {"conversation_context"}
    assert "user: build me a dark-theme analytics dashboard" in blocks["conversation_context"]
