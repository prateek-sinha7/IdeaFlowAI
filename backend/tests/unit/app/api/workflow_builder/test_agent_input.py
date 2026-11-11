"""Unit tests for ``app.api.workflow_builder.agent_input`` (task 15.4).

The store is ``InMemoryBuilderStore`` and the summarizer is a recording fake, so
no database, network or model is used.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from app.agents.workflow_builder.events import UsageCounts
from app.agents.workflow_builder.transcript import REQUIRED_HEADINGS
from app.api.workflow_builder.agent_input import (
    InputRequest,
    SummaryResult,
    add_usage,
    build_agent_input,
    pinned_message_id,
)
from app.core.config import settings
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_store import InMemoryBuilderStore

USER = "user-a"
GOOD_SUMMARY = "\n\n".join(f"## {heading}\n\ntext" for heading in REQUIRED_HEADINGS)
FILLER = "x" * 400


class RecordingSummarizer:
    """A ``Summarizer`` that plays back a list of replies and records its inputs."""

    def __init__(self, *replies: str | Exception) -> None:
        self._replies = list(replies)
        self.inputs: list[str] = []

    async def __call__(self, model_id: str, text: str) -> SummaryResult:
        self.inputs.append(text)
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SummaryResult(text=reply, usage=UsageCounts(input=11, output=3))


def _scope(store: InMemoryBuilderStore) -> Any:
    @contextmanager
    def scope() -> Iterator[InMemoryBuilderStore]:
        yield store

    return scope


def _session(store: InMemoryBuilderStore, exchanges: int) -> InputRequest:
    """Create a session with finished exchanges and a running current turn."""
    session = store.create_session(USER, **BuilderSessionFactory.create_kwargs())
    session_id = str(session.id)
    for index in range(exchanges):
        begun = store.begin_turn(
            USER,
            session_id,
            content=f"q{index} {FILLER}",
            canvas_state=None,
            client_message_id=f"old-{index}",
            model_id="m",
            effort=None,
            skill_hash="h",
        )
        store.finalize_assistant(
            USER,
            str(begun.assistant_message.id),
            status="completed",
            outcome="reply",
            content=f"a{index} {FILLER}",
        )
    current = store.begin_turn(
        USER,
        session_id,
        content="now",
        canvas_state=None,
        client_message_id="current",
        model_id="m",
        effort=None,
        skill_hash="h",
    )
    return InputRequest(
        user_id=USER,
        session_id=session_id,
        turn_id=str(current.assistant_message.id),
        user_message_id=str(current.user_message.id),
        model_id="model-x",
        tier="basic",
        content="now",
        canvas_state={"steps": [{"agent": "a"}]},
    )


@pytest.fixture
def store() -> InMemoryBuilderStore:
    return InMemoryBuilderStore()


@pytest.fixture
def tight_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep one exchange verbatim and a budget that fits none of the older ones."""
    monkeypatch.setattr(settings, "BUILDER_REPLAY_VERBATIM_TURNS", 1)
    monkeypatch.setattr(settings, "BUILDER_REPLAY_BUDGET_FRACTION", 0.0001)


async def test_build_agent_input_pins_message_id_and_has_no_history_when_session_is_new(
    store: InMemoryBuilderStore,
) -> None:
    request = _session(store, exchanges=0)
    summarizer = RecordingSummarizer()

    result = await build_agent_input(
        request, store_scope=_scope(store), summarizer=summarizer
    )

    assert result.message.id == pinned_message_id(request.turn_id)
    assert result.message.id == f"turn:{request.turn_id}"
    assert "<user_message>\nnow\n</user_message>" in str(result.message.content)
    assert "mode: create" in str(result.message.content)
    assert "1 step" in str(result.message.content)
    assert result.history == []
    assert result.summary_usage is None
    assert summarizer.inputs == []


async def test_build_agent_input_replays_exchanges_in_order_when_they_fit(
    store: InMemoryBuilderStore,
) -> None:
    request = _session(store, exchanges=2)

    result = await build_agent_input(
        request, store_scope=_scope(store), summarizer=RecordingSummarizer()
    )

    assert [type(m).__name__ for m in result.history] == [
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
        "AIMessage",
    ]
    assert str(result.history[0].content).startswith("q0")
    assert str(result.history[3].content).startswith("a1")


@pytest.mark.usefixtures("tight_budget")
async def test_build_agent_input_writes_and_stores_summary_when_exchanges_are_omitted(
    store: InMemoryBuilderStore,
) -> None:
    request = _session(store, exchanges=3)
    summarizer = RecordingSummarizer(GOOD_SUMMARY)

    result = await build_agent_input(
        request, store_scope=_scope(store), summarizer=summarizer
    )

    assert len(summarizer.inputs) == 1
    assert "q0" in summarizer.inputs[0]
    assert result.summary_usage == UsageCounts(input=11, output=3)
    assert len(result.history) == 2
    assert str(result.history[0].content).startswith("<summary_of_earlier_turns>")
    assert "q2" in str(result.history[0].content)
    stored = store.get_summary(USER, request.session_id)
    assert stored is not None
    assert stored.text == GOOD_SUMMARY
    assert stored.through_seq is not None


@pytest.mark.usefixtures("tight_budget")
async def test_build_agent_input_retries_once_when_summary_misses_headings(
    store: InMemoryBuilderStore,
) -> None:
    request = _session(store, exchanges=3)
    summarizer = RecordingSummarizer("no headings here", GOOD_SUMMARY)

    result = await build_agent_input(
        request, store_scope=_scope(store), summarizer=summarizer
    )

    assert len(summarizer.inputs) == 2
    stored = store.get_summary(USER, request.session_id)
    assert stored is not None
    assert stored.text == GOOD_SUMMARY
    assert result.summary_usage == UsageCounts(input=22, output=6)


@pytest.mark.usefixtures("tight_budget")
async def test_build_agent_input_keeps_previous_summary_when_both_tries_fail(
    store: InMemoryBuilderStore,
) -> None:
    request = _session(store, exchanges=3)
    summarizer = RecordingSummarizer("bad", "still bad")

    result = await build_agent_input(
        request, store_scope=_scope(store), summarizer=summarizer
    )

    assert len(summarizer.inputs) == 2
    assert store.get_summary(USER, request.session_id).text is None  # type: ignore[union-attr]
    assert not str(result.history[0].content).startswith("<summary_of_earlier_turns>")


@pytest.mark.usefixtures("tight_budget")
async def test_build_agent_input_continues_when_summarizer_raises(
    store: InMemoryBuilderStore,
) -> None:
    request = _session(store, exchanges=3)
    summarizer = RecordingSummarizer(RuntimeError("down"), RuntimeError("down"))

    result = await build_agent_input(
        request, store_scope=_scope(store), summarizer=summarizer
    )

    assert result.summary_usage is None
    assert len(result.history) == 2


@pytest.mark.usefixtures("tight_budget")
async def test_build_agent_input_skips_summary_call_when_stored_summary_is_current(
    store: InMemoryBuilderStore,
) -> None:
    request = _session(store, exchanges=3)
    first = RecordingSummarizer(GOOD_SUMMARY)
    await build_agent_input(request, store_scope=_scope(store), summarizer=first)
    second = RecordingSummarizer()

    result = await build_agent_input(
        request, store_scope=_scope(store), summarizer=second
    )

    assert second.inputs == []
    assert result.summary_usage is None
    assert str(result.history[0].content).startswith("<summary_of_earlier_turns>")


def test_add_usage_sums_every_count_when_left_is_set() -> None:
    total = add_usage(
        UsageCounts(input=1, output=2, cache_read=3, cache_write=4),
        UsageCounts(input=10, output=20, cache_read=30, cache_write=40),
    )

    assert total == UsageCounts(input=11, output=22, cache_read=33, cache_write=44)


def test_add_usage_returns_right_when_left_is_none() -> None:
    right = UsageCounts(input=5)

    assert add_usage(None, right) is right
