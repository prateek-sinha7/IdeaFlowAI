"""Tests for the ``context_provider:conversation`` capability (33 / D-08 / SC-2).

Covers:
  * the provider is keyed on the DECLARED capability name (``.name == "conversation"``),
    never a workflow name (SC-001/INV-1);
  * ``load(ctx)`` reads this run's OWN chat ``run_events`` via the owner-scoped
    ``ScopedStore.read_events`` handle and returns a single
    ``{"conversation_context": ...}`` block carrying the compacted transcript;
  * the self-gate on the ``conversation`` inject token in ``ctx.current_spec_injects``
    — un-gated → ``{}`` (DORMANT on golden runs, INV-3);
  * degrade-to-``{}`` on: un-gated inject, no store/run handle, an empty transcript, a
    non-chat-only log, and a read error (a broken chat log never breaks the agent);
  * the provider is registered and resolvable through the registry.

The compaction transform is exercised for real: importing the ``chat_history`` module
fires its ``@register`` so ``resolve("compaction","chat_history")`` binds inside
``load`` (the same registry path the provider uses in production).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

# Import the scripted-model harness FIRST so its import-time env setup runs (offline).
from tests.agents import _scripted_model  # noqa: F401  (import for side effects)

# Import the compaction impl so its @register fires (the provider resolves it inside load).
from agents.capabilities.compaction.chat_history import ChatHistoryCompaction  # noqa: F401
from agents.capabilities.context_providers.conversation import ConversationProvider
from agents.capabilities import registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry


# ── Fakes: an owner-scoped store + chat run_events rows ────────────────────────


class _FakeRow:
    """A minimal ``run_events`` row: ``.type`` + ``.payload_json`` (the read shape)."""

    def __init__(self, etype: str, payload: dict | None) -> None:
        self.type = etype
        self.payload_json = payload


class _FakeScopedStore:
    """In-memory stand-in for ``ScopedStore`` — ``read_events(run_id, after_seq)``.

    The scope is implicit (a real ScopedStore is constructed owner+workspace-bound);
    this fake just returns the rows it was seeded with, in order. ``raises=True``
    simulates a read error (the provider must degrade to ``{}``).
    """

    def __init__(self, rows: list | None = None, *, raises: bool = False) -> None:
        self._rows = list(rows or [])
        self._raises = raises

    async def read_events(self, run_id: str, after_seq: int) -> list:
        if self._raises:
            raise RuntimeError("simulated scoped-store read failure")
        return list(self._rows)


def _chat(text: str, *, reply: bool = False) -> _FakeRow:
    etype = "chat_reply" if reply else "chat_message"
    return _FakeRow(etype, {"pipeline_run_id": "r-conv-1", "text": text})


def _ctx(store, *, injects=("conversation",), run_id="r-conv-1"):
    return SimpleNamespace(
        scoped_store=store,
        run_id=run_id,
        current_spec_injects=set(injects),
    )


def _load(ctx):
    provider = ConversationProvider()
    assert provider.name == "conversation"
    return asyncio.run(provider.load(ctx))


# ── provider behavior ──────────────────────────────────────────────────────────


def test_provider_surfaces_compacted_conversation() -> None:
    store = _FakeScopedStore(
        [
            _chat("build me a dark-theme analytics dashboard"),
            _chat("On it — starting the spec now.", reply=True),
            _chat("make the header sticky please"),
        ]
    )
    blocks = _load(_ctx(store))
    assert set(blocks) == {"conversation_context"}
    body = blocks["conversation_context"]
    assert "## Conversation" in body
    # Short transcript → returned verbatim; user + assistant turns both present.
    assert "user: build me a dark-theme analytics dashboard" in body
    assert "assistant: On it — starting the spec now." in body
    assert "user: make the header sticky please" in body


def test_self_gate_returns_empty_when_inject_absent() -> None:
    store = _FakeScopedStore([_chat("should never surface")])
    assert _load(_ctx(store, injects=())) == {}
    assert _load(_ctx(store, injects=("images", "uploaded_files"))) == {}


def test_no_store_handle_degrades_to_empty() -> None:
    ctx = SimpleNamespace(current_spec_injects={"conversation"}, run_id="r-conv-1")
    assert _load(ctx) == {}


def test_no_run_id_degrades_to_empty() -> None:
    store = _FakeScopedStore([_chat("hi")])
    assert _load(_ctx(store, run_id=None)) == {}


def test_empty_transcript_degrades_to_empty() -> None:
    assert _load(_ctx(_FakeScopedStore([]))) == {}


def test_non_chat_events_are_ignored() -> None:
    # A run with only engine events (no chat turns) → dormant {}.
    store = _FakeScopedStore(
        [_FakeRow("agent_complete", {"agent": "plan"}), _FakeRow("pipeline_complete", {})]
    )
    assert _load(_ctx(store)) == {}


def test_read_error_degrades_to_empty() -> None:
    # T-33-01-01 degrade-not-crash: a scoped-store read failure never breaks the agent.
    assert _load(_ctx(_FakeScopedStore(raises=True))) == {}


def test_row_without_text_is_skipped() -> None:
    store = _FakeScopedStore(
        [_FakeRow("chat_message", {"pipeline_run_id": "r"}), _chat("real turn")]
    )
    body = _load(_ctx(store))["conversation_context"]
    assert "user: real turn" in body


# ── registry lockstep ──────────────────────────────────────────────────────────


def test_conversation_is_registered_and_resolves() -> None:
    registry_mod.discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("context_provider", "conversation") is True
    impl = reg.resolve("context_provider", "conversation")
    assert getattr(impl, "name", None) == "conversation"
