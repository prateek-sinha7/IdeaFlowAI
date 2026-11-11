"""Property tests for transcript replay selection.

# Feature: ai-workflow-builder, Property 11: Replay selection invariants

For any stored transcript (including tool rows and retried turns) and any model
context window, the replay holds no tool rows; it is a suffix of the exchanges in
chronological order; it always holds the latest ``min(4, n)`` exchanges; apart
from those, its tokens plus the summary's stay within the replay budget; the
omitted exchanges form a prefix; a summary is used if and only if that prefix is
not empty; a new summary is required if and only if the stored one does not reach
the last omitted message.

**Validates: Requirements 25.2, 25.3, 25.4, 25.5, 25.6, 25.8, 25.9, 47.12, 47.13**

The expectations come from the generator's own model of the transcript (``_Turn``)
and from ``_expected_*`` helpers below. They restate the rules with suffix sums,
plain comparisons and a closed-form token count, and do not call the production
walk. Windows are Opus-sized (200,000 tokens), Sonnet-sized (1,000,000 tokens)
and two small ones that make the budget bind often. The budget fraction and the
verbatim count come from ``settings`` (``BUILDER_REPLAY_BUDGET_FRACTION``,
``BUILDER_REPLAY_VERBATIM_TURNS``). Thinking is not a field of a stored row, so
it cannot reach the module; tool rows carry a marker that must never be replayed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.workflow_builder.transcript import (
    Exchange,
    build_exchanges,
    exchange_tokens,
    history_messages,
    select,
    summary_input,
    summary_needed,
)
from app.core.config import settings as app_settings

_KEEP = app_settings.BUILDER_REPLAY_VERBATIM_TURNS
_FRACTION = app_settings.BUILDER_REPLAY_BUDGET_FRACTION
_OPUS_WINDOW = 200_000
_SONNET_WINDOW = 1_000_000
_WINDOWS = [_OPUS_WINDOW, _SONNET_WINDOW, 3_000, 30_000]
_SUMMARY_TOKENS = [0, 100, 5_000, 70_000]
_TOOL_MARKER = "TOOLROW"
_BLANK_STATUSES = frozenset(
    {"failed", "cancelled", "timed_out", "interrupted", "running"}
)
_PLACEHOLDER = {
    "failed": "(no reply: the turn failed)",
    "cancelled": "(no reply: the turn ended cancelled)",
    "timed_out": "(no reply: the turn ended timed out)",
    "interrupted": "(no reply: the turn ended interrupted)",
}
_SUMMARY_OPEN = "<summary_of_earlier_turns>"
_SUMMARY_CLOSE = "</summary_of_earlier_turns>"


@dataclass(frozen=True)
class _Row:
    """A stored message row, with the fields the module reads."""

    id: str
    seq: int
    role: str
    reply_to_message_id: str | None
    status: str
    outcome: str | None
    content: str
    skill_hash: str | None


@dataclass(frozen=True)
class _Reply:
    seq: int
    status: str
    text: str


@dataclass(frozen=True)
class _Turn:
    user_id: str
    user_seq: int
    user_text: str
    replies: tuple[_Reply, ...]
    is_current: bool


@dataclass(frozen=True)
class _Transcript:
    rows: tuple[_Row, ...]
    turns: tuple[_Turn, ...]
    current_id: str | None


# --- Generators ---------------------------------------------------------------------

_LENGTH = st.one_of(
    st.integers(0, 300),
    st.integers(0, 300),
    st.integers(300, 6_000),
    st.sampled_from([20_000, 80_000, 200_000]),
)


@st.composite
def transcripts(draw: st.DrawFn) -> _Transcript:
    """Draw a session: turns with retries, tool rows, blank replies and a current turn."""
    count = draw(st.integers(0, 16))
    with_current = draw(st.booleans())
    rows: list[_Row] = []
    turns: list[_Turn] = []
    seq = 0
    tool_count = 0

    def next_seq() -> int:
        nonlocal seq
        seq += draw(st.integers(1, 3))
        return seq

    for index in range(count + (1 if with_current else 0)):
        is_current = with_current and index == count
        user_id = f"m{index}"
        user_seq = next_seq()
        user_text = f"<<u{index}>>" + "x" * draw(_LENGTH)
        rows.append(
            _Row(user_id, user_seq, "user", None, "completed", None, user_text, None)
        )
        reply_count = draw(
            st.sampled_from([0, 1] if is_current else [0, 1, 1, 1, 1, 2, 2, 3])
        )
        replies: list[_Reply] = []
        for position in range(reply_count):
            for _ in range(draw(st.integers(0, 2))):
                tool_count += 1
                rows.append(
                    _Row(
                        f"t{tool_count}",
                        next_seq(),
                        "tool",
                        user_id,
                        "completed",
                        None,
                        f"{_TOOL_MARKER}-{tool_count}-" + "x" * draw(_LENGTH),
                        None,
                    )
                )
            last = position == reply_count - 1
            if is_current:
                status = "running"
            elif last:
                status = draw(
                    st.sampled_from(
                        ["completed"] * 4
                        + ["failed", "cancelled", "timed_out", "interrupted", "running"]
                    )
                )
            else:
                status = draw(
                    st.sampled_from(
                        [
                            "failed",
                            "failed",
                            "cancelled",
                            "timed_out",
                            "interrupted",
                            "completed",
                        ]
                    )
                )
            if status in _BLANK_STATUSES and draw(st.booleans()):
                text = draw(st.sampled_from(["", "  \n"]))
            else:
                text = f"<<r{index}.{position}>>" + "x" * draw(_LENGTH)
            reply_seq = next_seq()
            replies.append(_Reply(reply_seq, status, text))
            rows.append(
                _Row(
                    f"a{index}.{position}",
                    reply_seq,
                    "assistant",
                    user_id,
                    status,
                    "reply" if status == "completed" else None,
                    text,
                    None,
                )
            )
        turns.append(_Turn(user_id, user_seq, user_text, tuple(replies), is_current))
    shuffled = draw(st.permutations(rows))
    current_id = f"m{count}" if with_current else None
    return _Transcript(tuple(shuffled), tuple(turns), current_id)


# --- Oracle -------------------------------------------------------------------------


def _expected_reply_text(reply: _Reply) -> str:
    if reply.text.strip():
        return reply.text
    return _PLACEHOLDER[reply.status]


def _expected_exchanges(transcript: _Transcript) -> list[Exchange]:
    """Exchanges the rules allow: not current, has a reply, newest reply not running."""
    result: list[Exchange] = []
    for turn in sorted(transcript.turns, key=lambda item: item.user_seq):
        if turn.is_current or not turn.replies:
            continue
        newest = max(turn.replies, key=lambda reply: reply.seq)
        if newest.status == "running":
            continue
        result.append(
            Exchange(
                user_message_id=turn.user_id,
                user_seq=turn.user_seq,
                user_text=turn.user_text,
                reply_seq=newest.seq,
                reply_text=_expected_reply_text(newest),
            )
        )
    return result


def _tokens(exchange: Exchange) -> int:
    """Approximate tokens of one replayed exchange, in closed form.

    Each message costs ``ceil((chars + len(role)) / 4) + 3``; the roles are
    ``user`` (4 chars) and ``assistant`` (9 chars).
    """
    user = -(-(len(exchange.user_text) + 4) // 4) + 3
    reply = -(-(len(exchange.reply_text) + 9) // 4) + 3
    return user + reply


def _budget(window: int) -> int:
    return math.floor(_FRACTION * window)


def _expected_kept(exchanges: list[Exchange], budget: int, summary_tokens: int) -> int:
    """Return how many of the newest exchanges the replay keeps.

    The largest ``k`` that is at least ``min(keep, n)`` and whose suffix of ``k``
    exchanges, plus the summary, fits the budget. Costs are positive, so the
    suffix sums only grow and the largest fitting ``k`` is the answer.
    """
    total = len(exchanges)
    must = min(_KEEP, total)
    kept = must
    running = sum(_tokens(item) for item in exchanges[total - must :])
    for size in range(must + 1, total + 1):
        running += _tokens(exchanges[total - size])
        if running + summary_tokens <= budget:
            kept = size
    return kept


# --- build_exchanges ----------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(transcript=transcripts())
def test_build_exchanges_returns_newest_replies_when_rows_have_retries_and_tool_rows(
    transcript: _Transcript,
) -> None:
    built = build_exchanges(transcript.rows, transcript.current_id)

    assert built == _expected_exchanges(transcript)
    assert [item.user_seq for item in built] == sorted(item.user_seq for item in built)


@settings(max_examples=100, deadline=None)
@given(transcript=transcripts())
def test_build_exchanges_excludes_tool_text_when_tool_rows_present(
    transcript: _Transcript,
) -> None:
    built = build_exchanges(transcript.rows, transcript.current_id)

    for item in built:
        assert _TOOL_MARKER not in item.user_text
        assert _TOOL_MARKER not in item.reply_text
    if transcript.current_id is not None:
        assert all(item.user_message_id != transcript.current_id for item in built)


# --- select -------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    transcript=transcripts(),
    window=st.sampled_from(_WINDOWS),
    summary_tokens=st.sampled_from(_SUMMARY_TOKENS),
)
def test_select_keeps_latest_exchanges_when_budget_is_smaller_than_them(
    transcript: _Transcript, window: int, summary_tokens: int
) -> None:
    exchanges = _expected_exchanges(transcript)

    selection = select(exchanges, _budget(window), _KEEP, summary_tokens)

    must = min(_KEEP, len(exchanges))
    assert len(selection.selected) >= must
    assert selection.selected[len(selection.selected) - must :] == tuple(
        exchanges[len(exchanges) - must :]
    )


@settings(max_examples=100, deadline=None)
@given(
    transcript=transcripts(),
    window=st.sampled_from(_WINDOWS),
    summary_tokens=st.sampled_from(_SUMMARY_TOKENS),
)
def test_select_returns_prefix_omitted_and_suffix_selected_when_any_budget(
    transcript: _Transcript, window: int, summary_tokens: int
) -> None:
    exchanges = _expected_exchanges(transcript)

    selection = select(exchanges, _budget(window), _KEEP, summary_tokens)

    cut = len(selection.omitted)
    assert selection.omitted == tuple(exchanges[:cut])
    assert selection.selected == tuple(exchanges[cut:])
    assert [item.user_seq for item in selection.selected] == sorted(
        item.user_seq for item in selection.selected
    )


@settings(max_examples=100, deadline=None)
@given(
    transcript=transcripts(),
    window=st.sampled_from(_WINDOWS),
    summary_tokens=st.sampled_from(_SUMMARY_TOKENS),
)
def test_select_fills_budget_newest_first_when_summary_tokens_are_counted(
    transcript: _Transcript, window: int, summary_tokens: int
) -> None:
    exchanges = _expected_exchanges(transcript)
    budget = _budget(window)

    selection = select(exchanges, budget, _KEEP, summary_tokens)

    kept = _expected_kept(exchanges, budget, summary_tokens)
    assert len(selection.selected) == kept
    assert all(exchange_tokens(item) == _tokens(item) for item in selection.selected)
    must = min(_KEEP, len(exchanges))
    if kept > must:
        used = sum(_tokens(item) for item in selection.selected)
        assert used + summary_tokens <= budget


@settings(max_examples=100, deadline=None)
@given(
    transcript=transcripts(),
    summary_tokens=st.sampled_from(_SUMMARY_TOKENS),
)
def test_select_keeps_at_least_as_many_when_window_is_larger(
    transcript: _Transcript, summary_tokens: int
) -> None:
    exchanges = _expected_exchanges(transcript)

    opus = select(exchanges, _budget(_OPUS_WINDOW), _KEEP, summary_tokens)
    sonnet = select(exchanges, _budget(_SONNET_WINDOW), _KEEP, summary_tokens)

    assert len(sonnet.selected) >= len(opus.selected)
    assert sonnet.omitted == opus.omitted[: len(sonnet.omitted)]


@settings(max_examples=100, deadline=None)
@given(
    transcript=transcripts(),
    window=st.sampled_from(_WINDOWS),
    summary_tokens=st.sampled_from(_SUMMARY_TOKENS),
)
def test_select_uses_summary_when_and_only_when_omitted_is_not_empty(
    transcript: _Transcript, window: int, summary_tokens: int
) -> None:
    exchanges = _expected_exchanges(transcript)
    budget = _budget(window)

    selection = select(exchanges, budget, _KEEP, summary_tokens)

    expect_omitted = _expected_kept(exchanges, budget, summary_tokens) < len(exchanges)
    assert selection.uses_summary is expect_omitted
    assert bool(selection.omitted) is expect_omitted


# --- summary_needed and summary_input -----------------------------------------------


@settings(max_examples=100, deadline=None)
@given(transcript=transcripts(), data=st.data())
def test_summary_needed_is_true_when_stored_summary_does_not_reach_last_omitted(
    transcript: _Transcript, data: st.DataObject
) -> None:
    exchanges = _expected_exchanges(transcript)
    cut = data.draw(st.integers(0, len(exchanges)))
    omitted = exchanges[:cut]
    last = max((max(item.user_seq, item.reply_seq) for item in omitted), default=0)
    through = data.draw(
        st.one_of(
            st.none(),
            st.integers(max(last - 3, 0), last + 3),
            st.integers(0, last + 50),
        )
    )

    needed = summary_needed(omitted, through)

    expected = bool(omitted) and (through is None or through < last)
    assert needed is expected


@settings(max_examples=100, deadline=None)
@given(transcript=transcripts(), data=st.data())
def test_summary_input_holds_only_messages_after_stored_summary_when_omitted_given(
    transcript: _Transcript, data: st.DataObject
) -> None:
    exchanges = _expected_exchanges(transcript)
    cut = data.draw(st.integers(0, len(exchanges)))
    omitted = exchanges[:cut]
    through = data.draw(st.one_of(st.none(), st.integers(0, 80)))
    previous = data.draw(
        st.sampled_from([None, "", "  ", "## Decisions\nkept <<prev>>"])
    )
    floor = through if through is not None else 0

    text = summary_input(previous, through, omitted)

    new_users = [item for item in omitted if item.user_seq > floor]
    new_replies = [item for item in omitted if item.reply_seq > floor]
    assert text.count("[user]\n") == len(new_users)
    assert text.count("[assistant]\n") == len(new_replies)
    for item in omitted:
        assert (item.user_text in text) is (item.user_seq > floor)
        if item.reply_text.startswith("<<r"):
            assert (item.reply_text in text) is (item.reply_seq > floor)
    assert ("<<prev>>" in text) is (previous is not None and "<<prev>>" in previous)
    assert _TOOL_MARKER not in text


# --- history_messages ---------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    transcript=transcripts(),
    window=st.sampled_from(_WINDOWS),
    summary_tokens=st.sampled_from(_SUMMARY_TOKENS),
    summary_text=st.sampled_from([None, "", "  \n", "## Decisions\n- keep <<s>>  "]),
)
def test_history_messages_alternate_and_prepend_summary_when_exchanges_omitted(
    transcript: _Transcript,
    window: int,
    summary_tokens: int,
    summary_text: str | None,
) -> None:
    exchanges = _expected_exchanges(transcript)
    selection = select(exchanges, _budget(window), _KEEP, summary_tokens)

    messages = history_messages(selection, summary_text)

    assert len(messages) == 2 * len(selection.selected)
    for index, item in enumerate(selection.selected):
        human, ai = messages[2 * index], messages[2 * index + 1]
        assert isinstance(human, HumanMessage)
        assert isinstance(ai, AIMessage)
        assert not ai.tool_calls
        assert ai.content == item.reply_text
        wrapped = (
            index == 0
            and bool(selection.omitted)
            and summary_text is not None
            and bool(summary_text.strip())
        )
        if wrapped:
            assert summary_text is not None
            assert human.content == (
                f"{_SUMMARY_OPEN}\n{summary_text.strip()}\n{_SUMMARY_CLOSE}\n\n{item.user_text}"
            )
        else:
            assert human.content == item.user_text
    joined = "".join(str(message.content) for message in messages)
    assert (_SUMMARY_OPEN in joined) is (
        bool(selection.omitted)
        and bool(selection.selected)
        and bool(summary_text and summary_text.strip())
    )


@settings(max_examples=100, deadline=None)
@given(
    transcript=transcripts(),
    window=st.sampled_from(_WINDOWS),
    summary_tokens=st.sampled_from(_SUMMARY_TOKENS),
)
def test_history_messages_hold_no_tool_rows_and_fit_budget_when_built_from_rows(
    transcript: _Transcript, window: int, summary_tokens: int
) -> None:
    budget = _budget(window)

    exchanges = build_exchanges(transcript.rows, transcript.current_id)
    selection = select(exchanges, budget, _KEEP, summary_tokens)
    messages = history_messages(selection, "## Decisions\n- kept")

    assert all(type(message) in (HumanMessage, AIMessage) for message in messages)
    assert all(_TOOL_MARKER not in str(message.content) for message in messages)
    must = min(_KEEP, len(exchanges))
    if len(selection.selected) > must:
        used = sum(_tokens(item) for item in selection.selected)
        assert used + summary_tokens <= budget
    if transcript.current_id is not None:
        assert all(
            item.user_message_id != transcript.current_id for item in selection.selected
        )
