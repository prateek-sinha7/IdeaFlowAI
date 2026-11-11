"""Property tests for ``PinnedTurnMessageMiddleware``.

# Feature: ai-workflow-builder, Property 12: The turn's message survives summarisation

For any list of model-request messages, after the middleware's transform the
turn's pinned message appears exactly once, and when it was already present the
list is unchanged.

The middleware only changes the request it hands to the model, so the tests
call ``awrap_model_call`` with a recording handler and read the request the
handler received.

**Validates: Requirements 28.3**

The expected list comes from ``_expected_messages`` below. It restates the rule
from design 3.6.5 with plain loops over ``additional_kwargs`` and does not call
the production helpers. The rule: a summary message is a human message whose
``additional_kwargs["lc_source"]`` is ``"summarization"``; the pinned message
goes after all leading summary messages.
"""

from __future__ import annotations

import asyncio
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from langchain.agents.middleware.types import ModelRequest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agents.workflow_builder.middleware import PinnedTurnMessageMiddleware

_TURN_ID = "t-42"
_PINNED_ID = f"turn:{_TURN_ID}"
_OTHER_IDS = [None, "m1", "m2", "turn:other", "turn:t-4", "turn:t-42x"]


def _pinned_message() -> HumanMessage:
    return HumanMessage(content="Turn_Context and the user's request", id=_PINNED_ID)


@st.composite
def _other_message(draw: st.DrawFn) -> BaseMessage:
    """A message that is not the pinned one (its id is never the pinned id)."""
    kind = draw(st.sampled_from(["human", "ai", "summary"]))
    message_id = draw(st.sampled_from(_OTHER_IDS))
    text = draw(st.text(max_size=20))
    if kind == "summary":
        return HumanMessage(
            content=text,
            id=message_id,
            additional_kwargs={"lc_source": "summarization"},
        )
    if kind == "human":
        return HumanMessage(content=text, id=message_id)
    return AIMessage(content=text, id=message_id)


@st.composite
def _request_messages(draw: st.DrawFn) -> tuple[list[BaseMessage], bool]:
    """Return a message list and whether it holds the pinned message."""
    others = draw(st.lists(_other_message(), max_size=8))
    leading_summaries = draw(st.integers(min_value=0, max_value=3))
    messages: list[BaseMessage] = [
        HumanMessage(
            content="summary",
            additional_kwargs={"lc_source": "summarization"},
        )
        for _ in range(leading_summaries)
    ]
    messages.extend(others)
    present = draw(st.booleans())
    if present:
        position = draw(st.integers(min_value=0, max_value=len(messages)))
        messages.insert(position, _pinned_message())
    return messages, present


def _is_summary(message: BaseMessage) -> bool:
    return (
        isinstance(message, HumanMessage)
        and message.additional_kwargs.get("lc_source") == "summarization"
    )


def _expected_messages(
    original: list[BaseMessage], pinned: BaseMessage
) -> list[BaseMessage]:
    """The list the model should see, built without the production code."""
    if any(message.id == _PINNED_ID for message in original):
        return list(original)
    leading = 0
    for message in original:
        if not _is_summary(message):
            break
        leading += 1
    return [*original[:leading], pinned, *original[leading:]]


def _run_middleware(
    messages: list[BaseMessage], pinned: BaseMessage
) -> tuple[ModelRequest[Any], ModelRequest[Any]]:
    """Run ``awrap_model_call``; return the request given and the one the model got."""
    middleware = PinnedTurnMessageMiddleware(_TURN_ID, pinned)
    request: ModelRequest[Any] = ModelRequest(
        model=GenericFakeChatModel(messages=iter([])),
        messages=list(messages),
    )
    seen: list[ModelRequest[Any]] = []

    async def handler(received: ModelRequest[Any]) -> str:
        seen.append(received)
        return "response"

    result = asyncio.run(middleware.awrap_model_call(request, handler))  # type: ignore[arg-type]
    assert result == "response"
    assert len(seen) == 1
    return request, seen[0]


# Feature: ai-workflow-builder, Property 12: The turn's message survives summarisation
@settings(max_examples=100, deadline=None)
@given(case=_request_messages())
def test_awrap_model_call_keeps_pinned_message_once_when_any_message_list(
    case: tuple[list[BaseMessage], bool],
) -> None:
    messages, _present = case
    pinned = _pinned_message()

    _request, seen = _run_middleware(messages, pinned)

    count = sum(1 for message in seen.messages if message.id == _PINNED_ID)
    assert count == 1
    assert seen.messages == _expected_messages(messages, pinned)


# Feature: ai-workflow-builder, Property 12: The turn's message survives summarisation
@settings(max_examples=100, deadline=None)
@given(case=_request_messages())
def test_awrap_model_call_leaves_messages_unchanged_when_pinned_already_present(
    case: tuple[list[BaseMessage], bool],
) -> None:
    messages, present = case
    if not present:
        messages = [*messages, _pinned_message()]
    pinned = _pinned_message()

    request, seen = _run_middleware(messages, pinned)

    assert len(seen.messages) == len(messages)
    assert all(got is want for got, want in zip(seen.messages, messages, strict=True))
    assert request.messages == messages


# Feature: ai-workflow-builder, Property 12: The turn's message survives summarisation
@settings(max_examples=100, deadline=None)
@given(case=_request_messages())
def test_awrap_model_call_does_not_change_input_request_when_pinned_inserted(
    case: tuple[list[BaseMessage], bool],
) -> None:
    messages, present = case
    before = list(messages)
    pinned = _pinned_message()

    request, seen = _run_middleware(messages, pinned)

    assert request.messages == before
    assert messages == before
    if not present:
        assert any(message is pinned for message in seen.messages)
