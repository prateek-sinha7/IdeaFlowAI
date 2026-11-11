"""Unit tests for ``app.agents.workflow_builder.transcript``.

Covers the summary-heading check (the input to the single-retry rule), the
summary input bound, replay selection and the session projections with fixed
examples. The invariants over generated transcripts live in
``tests/property/app/agents/workflow_builder``.

Requirements: 25.7 (summary content and bound), 49.2.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.workflow_builder.transcript import (
    FAILED_REPLY_TEXT,
    MAX_TITLE_CHARS,
    REQUIRED_HEADINGS,
    Exchange,
    build_exchanges,
    counts_toward_clarify,
    display_transcript,
    ends_clarify_count,
    exchange_tokens,
    has_required_headings,
    history_messages,
    latest_unproposed,
    make_title,
    omitted_through_seq,
    select,
    skill_updated,
    skill_updated_flags,
    summary_input,
    summary_needed,
    text_tokens,
)


@dataclass(frozen=True)
class Row:
    id: str
    seq: int
    role: str
    reply_to_message_id: str | None = None
    status: str = "completed"
    outcome: str | None = None
    content: str = ""
    skill_hash: str | None = None


@dataclass(frozen=True)
class Rev:
    revision: int
    kind: str


def _user(seq: int, text: str = "q") -> Row:
    return Row(id=f"u{seq}", seq=seq, role="user", content=text)


def _reply(
    seq: int, to: int, text: str = "a", status: str = "completed", **extra: str | None
) -> Row:
    return Row(
        id=f"a{seq}",
        seq=seq,
        role="assistant",
        reply_to_message_id=f"u{to}",
        status=status,
        content=text,
        **extra,  # type: ignore[arg-type]  # test passes outcome / skill_hash only
    )


def _exchange(n: int, user: str = "question", reply: str = "answer") -> Exchange:
    """Exchange ``n`` uses seq ``2n`` for the user and ``2n + 1`` for the reply."""
    return Exchange(
        user_message_id=f"u{2 * n}",
        user_seq=2 * n,
        user_text=user,
        reply_seq=2 * n + 1,
        reply_text=reply,
    )


_SUMMARY = "\n".join(f"## {h}\n- x" for h in REQUIRED_HEADINGS)


# --- Summary headings ----------------------------------------------------------------


def test_has_required_headings_returns_true_when_all_four_are_present() -> None:
    assert has_required_headings(_SUMMARY) is True


def test_required_headings_are_the_four_named_sections() -> None:
    assert REQUIRED_HEADINGS == (
        "Answers to questions",
        "Requirements and constraints",
        "Workflow Brief",
        "Decisions",
    )


@pytest.mark.parametrize("missing", REQUIRED_HEADINGS)
def test_has_required_headings_returns_false_when_one_is_missing(missing: str) -> None:
    text = "\n".join(f"## {h}\n- x" for h in REQUIRED_HEADINGS if h != missing)

    assert has_required_headings(text) is False


def test_has_required_headings_returns_true_when_marks_case_and_colon_vary() -> None:
    text = (
        "# answers to questions:\n- a\n"
        "### **Requirements and constraints**\n- b\n"
        "#### WORKFLOW BRIEF\n- c\n"
        "###### **Decisions:**\n- d\n"
    )

    assert has_required_headings(text) is True


def test_has_required_headings_returns_false_when_text_is_not_a_heading_line() -> None:
    text = "\n".join(f"{h}\n- x" for h in REQUIRED_HEADINGS)

    assert has_required_headings(text) is False


def test_has_required_headings_returns_false_when_heading_has_trailing_text() -> None:
    text = _SUMMARY.replace("## Decisions", "## Decisions made so far")

    assert has_required_headings(text) is False


def test_has_required_headings_returns_false_when_text_is_empty() -> None:
    assert has_required_headings("") is False


# --- Summary rules -------------------------------------------------------------------


def test_summary_needed_returns_false_when_nothing_is_omitted() -> None:
    assert summary_needed([], None) is False
    assert summary_needed([], 10) is False


def test_summary_needed_returns_true_when_no_summary_is_stored() -> None:
    assert summary_needed([_exchange(1)], None) is True


def test_summary_needed_returns_true_when_summary_stops_before_last_omitted() -> None:
    omitted = [_exchange(1), _exchange(2)]

    assert omitted_through_seq(omitted) == 5
    assert summary_needed(omitted, 4) is True


def test_summary_needed_returns_false_when_summary_reaches_last_omitted() -> None:
    omitted = [_exchange(1), _exchange(2)]

    assert summary_needed(omitted, 5) is False
    assert summary_needed(omitted, 9) is False


def test_omitted_through_seq_returns_none_when_nothing_is_omitted() -> None:
    assert omitted_through_seq([]) is None


def test_summary_input_holds_all_messages_when_no_summary_exists() -> None:
    result = summary_input(None, None, [_exchange(1, "first q", "first a")])

    assert "<previous_summary>\n(none)\n</previous_summary>" in result
    assert "[user]\nfirst q" in result
    assert "[assistant]\nfirst a" in result


def test_summary_input_holds_only_messages_after_through_seq() -> None:
    omitted = [_exchange(1, "old q", "old a"), _exchange(2, "new q", "new a")]

    result = summary_input("earlier summary", 3, omitted)

    assert "earlier summary" in result
    assert "old q" not in result
    assert "old a" not in result
    assert "new q" in result
    assert "new a" in result


def test_summary_input_keeps_reply_when_only_the_reply_is_after_through_seq() -> None:
    result = summary_input("s", 2, [_exchange(1, "kept out", "kept in")])

    assert "kept out" not in result
    assert "[assistant]\nkept in" in result


def test_summary_input_marks_previous_as_none_when_it_is_blank() -> None:
    result = summary_input("   ", None, [_exchange(1)])

    assert "<previous_summary>\n(none)\n</previous_summary>" in result


# --- Replay: exchanges -----------------------------------------------------------------


def test_build_exchanges_pairs_user_with_newest_reply_when_turn_was_retried() -> None:
    rows = [
        _user(1, "ask"),
        _reply(2, 1, "", status="failed"),
        _reply(3, 1, "second try"),
    ]

    result = build_exchanges(rows)

    assert [(e.user_text, e.reply_text) for e in result] == [("ask", "second try")]


def test_build_exchanges_uses_failed_placeholder_when_failed_reply_has_no_text() -> (
    None
):
    result = build_exchanges([_user(1), _reply(2, 1, "", status="failed")])

    assert result[0].reply_text == FAILED_REPLY_TEXT


def test_build_exchanges_names_the_status_when_other_reply_has_no_text() -> None:
    result = build_exchanges([_user(1), _reply(2, 1, "  ", status="timed_out")])

    assert result[0].reply_text == "(no reply: the turn ended timed out)"


def test_build_exchanges_skips_current_message_and_unanswered_and_running() -> None:
    rows = [
        _user(1, "done"),
        _reply(2, 1),
        _user(3, "unanswered"),
        _user(4, "running"),
        _reply(5, 4, "partial", status="running"),
        _user(6, "current"),
        _reply(7, 6),
    ]

    result = build_exchanges(rows, current_message_id="u6")

    assert [e.user_text for e in result] == ["done"]


def test_build_exchanges_leaves_out_tool_rows_when_they_are_stored() -> None:
    tool = Row(id="t1", seq=2, role="tool", content="SECRET TOOL OUTPUT")
    rows = [_user(1), tool, _reply(3, 1, "reply")]

    result = build_exchanges(rows)

    assert len(result) == 1
    assert "SECRET" not in result[0].reply_text


def test_build_exchanges_orders_by_seq_when_rows_arrive_shuffled() -> None:
    rows = [_reply(4, 3, "a2"), _user(3, "q2"), _reply(2, 1, "a1"), _user(1, "q1")]

    result = build_exchanges(rows)

    assert [e.user_text for e in result] == ["q1", "q2"]


# --- Replay: selection -----------------------------------------------------------------


def test_text_tokens_matches_exchange_tokens_scale_when_text_grows() -> None:
    assert text_tokens("x" * 400) > text_tokens("x" * 40)
    assert exchange_tokens(_exchange(1)) > 0


def test_select_keeps_everything_when_budget_is_large() -> None:
    exchanges = [_exchange(n) for n in range(1, 7)]

    result = select(exchanges, budget=1_000_000, keep_verbatim=2)

    assert result.selected == tuple(exchanges)
    assert result.omitted == ()
    assert result.uses_summary is False


def test_select_keeps_newest_verbatim_when_budget_is_zero() -> None:
    exchanges = [_exchange(n) for n in range(1, 7)]

    result = select(exchanges, budget=0, keep_verbatim=4)

    assert result.selected == tuple(exchanges[2:])
    assert result.omitted == tuple(exchanges[:2])
    assert result.uses_summary is True


def test_select_adds_older_exchanges_while_they_fit_the_budget() -> None:
    exchanges = [_exchange(n) for n in range(1, 7)]
    three = sum(exchange_tokens(e) for e in exchanges[3:])

    fits = select(exchanges, budget=three, keep_verbatim=1)
    short = select(exchanges, budget=three - 1, keep_verbatim=1)

    assert fits.selected == tuple(exchanges[3:])
    assert short.selected == tuple(exchanges[4:])


def test_select_counts_summary_inside_the_budget() -> None:
    exchanges = [_exchange(n) for n in range(1, 5)]
    base = sum(exchange_tokens(e) for e in exchanges[2:])

    without = select(exchanges, budget=base, keep_verbatim=1)
    with_summary = select(exchanges, budget=base, keep_verbatim=1, summary_tokens=1)

    assert len(without.selected) == 2
    assert len(with_summary.selected) == 1


def test_select_returns_empty_selection_when_there_are_no_exchanges() -> None:
    result = select([], budget=100)

    assert result.selected == ()
    assert result.omitted == ()


@pytest.mark.parametrize(
    ("budget", "keep", "summary"),
    [(10, 0, 0), (-1, 4, 0), (10, 4, -1)],
)
def test_select_raises_when_arguments_are_out_of_range(
    budget: int, keep: int, summary: int
) -> None:
    with pytest.raises(ValueError, match="must"):
        select(
            [_exchange(1)], budget=budget, keep_verbatim=keep, summary_tokens=summary
        )


# --- Replay: history -------------------------------------------------------------------


def test_history_messages_alternates_human_and_ai_when_no_exchange_is_omitted() -> None:
    selection = select([_exchange(1, "q1", "a1"), _exchange(2, "q2", "a2")], 10_000)

    result = history_messages(selection, "unused summary")

    assert [type(m) for m in result] == [HumanMessage, AIMessage] * 2
    assert [m.content for m in result] == ["q1", "a1", "q2", "a2"]


def test_history_messages_prepends_summary_to_oldest_user_message() -> None:
    selection = select([_exchange(n, f"q{n}", f"a{n}") for n in (1, 2, 3)], 0, 2)

    result = history_messages(selection, "  the summary  ")

    assert result[0].content == (
        "<summary_of_earlier_turns>\nthe summary\n</summary_of_earlier_turns>\n\nq2"
    )
    assert result[2].content == "q3"
    assert len(result) == 4


@pytest.mark.parametrize("summary", [None, "", "   \n"])
def test_history_messages_adds_no_summary_when_text_is_blank(
    summary: str | None,
) -> None:
    selection = select([_exchange(n, f"q{n}") for n in (1, 2, 3)], 0, 2)

    result = history_messages(selection, summary)

    assert result[0].content == "q2"


# --- Projections ---------------------------------------------------------------------


def test_display_transcript_shows_user_once_with_newest_reply_and_failed_retries() -> (
    None
):
    rows = [
        _user(1, "ask"),
        _reply(2, 1, "", status="failed"),
        _reply(3, 1, "", status="cancelled"),
        _reply(4, 1, "final"),
        Row(id="t", seq=5, role="tool"),
    ]

    result = display_transcript(rows)

    assert len(result) == 1
    assert result[0].user.id == "u1"
    assert result[0].reply is not None
    assert result[0].reply.id == "a4"
    assert [r.id for r in result[0].retried] == ["a2"]


def test_display_transcript_has_no_reply_when_user_message_is_unanswered() -> None:
    result = display_transcript([_user(1)])

    assert result[0].reply is None
    assert result[0].retried == ()


def test_skill_updated_returns_true_only_when_both_hashes_differ() -> None:
    assert skill_updated("a", "b") is True
    assert skill_updated("a", "a") is False
    assert skill_updated(None, "b") is False
    assert skill_updated("a", None) is False


def test_skill_updated_flags_compare_with_nearest_earlier_hash() -> None:
    rows = [
        _user(1),
        _reply(2, 1, skill_hash="h1"),
        _user(3),
        _reply(4, 3, status="failed", skill_hash=None),
        _user(5),
        _reply(6, 5, skill_hash="h2"),
    ]

    flags = skill_updated_flags(rows)

    assert flags == {"a2": False, "a4": False, "a6": True}


@pytest.mark.parametrize(
    ("status", "outcome", "before_first", "expected"),
    [
        ("completed", "reply", True, True),
        ("completed", "reply", False, False),
        ("completed", "draft", True, False),
        ("completed", None, True, False),
        ("failed", "reply", True, False),
        ("cancelled", "reply", True, False),
    ],
)
def test_counts_toward_clarify_follows_status_outcome_and_position(
    status: str, outcome: str | None, before_first: bool, expected: bool
) -> None:
    assert counts_toward_clarify(status, outcome, before_first) is expected


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("accepted", True), ("seed", False), ("undo", False), ("unproposed", False)],
)
def test_ends_clarify_count_is_true_only_for_accepted(
    kind: str, expected: bool
) -> None:
    assert ends_clarify_count(kind) is expected


def test_latest_unproposed_returns_newest_when_it_is_above_every_draft() -> None:
    revisions = [
        Rev(0, "seed"),
        Rev(1, "accepted"),
        Rev(2, "unproposed"),
        Rev(3, "unproposed"),
    ]

    result = latest_unproposed(revisions)

    assert result is not None
    assert result.revision == 3


def test_latest_unproposed_returns_none_when_a_draft_is_newer() -> None:
    revisions = [Rev(1, "unproposed"), Rev(2, "undo")]

    assert latest_unproposed(revisions) is None


def test_latest_unproposed_returns_none_when_there_are_no_revisions() -> None:
    assert latest_unproposed([]) is None


def test_make_title_uses_first_non_blank_line_with_whitespace_collapsed() -> None:
    assert (
        make_title("\n\n  Review   my\tcontracts  \nsecond line")
        == "Review my contracts"
    )


def test_make_title_cuts_at_limit_and_adds_ellipsis_when_line_is_long() -> None:
    title = make_title("x" * (MAX_TITLE_CHARS + 20))

    assert title == "x" * MAX_TITLE_CHARS + "\u2026"


def test_make_title_keeps_line_when_it_is_exactly_the_limit() -> None:
    assert make_title("x" * MAX_TITLE_CHARS) == "x" * MAX_TITLE_CHARS


def test_make_title_returns_untitled_when_message_is_blank() -> None:
    assert make_title(" \n\t\n") == "Untitled"
