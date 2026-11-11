"""Property tests for the session projections of the builder transcript.

# Feature: ai-workflow-builder, Property 26: Session projections

For any set of stored message, tool and revision rows (including retries), the
transcript shows each user message once with only its newest reply; ``skill_updated``
is true on an assistant message if and only if its skill hash differs from the
previous assistant message's; the clarify count equals the completed reply-only
turns before the first accepted revision; ``latest_unproposed`` is returned if and
only if its revision is above the latest seed, accepted or undo revision; and the
title is non-empty, single-line and at most 60 characters plus an ellipsis.

**Validates: Requirements 12.2, 12.6, 13.1, 16.3, 20.10, 23.13, 37.3, 47.7**

Requirement map (the numbers are criteria of the numbered requirement):

* 12.2  the session title comes from the first user message (``make_title``).
* 12.6  the session returns its latest unproposed revision only when it is newer
  than the latest draft (``latest_unproposed``).
* 13.1  the transcript shows the retried user message once (``display_transcript``).
* 16.3, 47.7  the clarify count (``counts_toward_clarify``, ``ends_clarify_count``).
  The "2 or more" threshold of 47.7 is not a function of this module, so it is
  not tested here.
* 20.10 ``skill_updated`` / ``skill_updated_flags``.
* 37.3  the unproposed revision is reported only when above the last applied draft
  (``latest_unproposed``).
* 23.13 numbered revisions: numbering belongs to the store, not to this module (see
  open-decisions.md, task 10.5).

The expectations come from the generator's own model of the session and from the
``_expected_*`` helpers below. They restate the rules with different algorithms
(backward scans, sorting, regular expressions) and do not call the production code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.transcript import (
    MAX_TITLE_CHARS,
    counts_toward_clarify,
    display_transcript,
    ends_clarify_count,
    latest_unproposed,
    make_title,
    skill_updated,
    skill_updated_flags,
)

_STATUSES = ["completed", "failed", "cancelled", "timed_out", "interrupted", "running"]
_OUTCOMES = ["reply", "draft", "changed", None]
_REVISION_KINDS = ["seed", "accepted", "undo", "unproposed"]
_HASHES_OR_NONE = [None, "h1", "h2", "h3"]
_HASHES = ["h1", "h2", "h3"]
_ELLIPSIS = "\u2026"


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
    id: str
    seq: int
    status: str
    skill_hash: str | None


@dataclass(frozen=True)
class _Turn:
    user_id: str
    user_seq: int
    replies: tuple[_Reply, ...]


@dataclass(frozen=True)
class _Session:
    rows: tuple[_Row, ...]
    reshuffled: tuple[_Row, ...]
    turns: tuple[_Turn, ...]


@dataclass(frozen=True)
class _Rev:
    revision: int
    kind: str


# --- Generators ---------------------------------------------------------------------


@st.composite
def sessions(draw: st.DrawFn, hashes: list[str | None]) -> _Session:
    """Draw a session: user messages, retried replies, tool rows, shuffled."""
    count = draw(st.integers(0, 12))
    rows: list[_Row] = []
    turns: list[_Turn] = []
    seq = 0
    tools = 0

    def next_seq() -> int:
        nonlocal seq
        seq += draw(st.integers(1, 3))
        return seq

    for index in range(count):
        user_id = f"m{index}"
        user_seq = next_seq()
        rows.append(
            _Row(user_id, user_seq, "user", None, "accepted", None, f"u{index}", None)
        )
        replies: list[_Reply] = []
        for position in range(draw(st.sampled_from([0, 1, 1, 1, 2, 3]))):
            for _ in range(draw(st.integers(0, 2))):
                tools += 1
                rows.append(
                    _Row(
                        f"t{tools}",
                        next_seq(),
                        "tool",
                        user_id,
                        "ok",
                        None,
                        f"tool{tools}",
                        draw(st.sampled_from(hashes)),
                    )
                )
            reply_seq = next_seq()
            status = draw(st.sampled_from(_STATUSES))
            skill_hash = draw(st.sampled_from(hashes))
            reply = _Reply(f"a{index}.{position}", reply_seq, status, skill_hash)
            replies.append(reply)
            rows.append(
                _Row(
                    reply.id,
                    reply_seq,
                    "assistant",
                    user_id,
                    status,
                    None,
                    f"r{index}.{position}",
                    skill_hash,
                )
            )
        turns.append(_Turn(user_id, user_seq, tuple(replies)))
    return _Session(
        tuple(draw(st.permutations(rows))),
        tuple(draw(st.permutations(rows))),
        tuple(turns),
    )


@st.composite
def revision_lists(draw: st.DrawFn) -> list[_Rev]:
    """Draw revisions with unique, increasing numbers, returned in a random order."""
    first_kind = draw(st.sampled_from(_REVISION_KINDS))
    number = 0 if first_kind == "seed" else 1
    revs = [_Rev(number, first_kind)]
    for _ in range(draw(st.integers(0, 11))):
        number += draw(st.integers(1, 3))
        revs.append(_Rev(number, draw(st.sampled_from(_REVISION_KINDS[1:]))))
    return draw(st.permutations(revs))


# --- display_transcript (Req 13.1) --------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(session=sessions(hashes=_HASHES_OR_NONE))
def test_display_transcript_shows_each_user_once_with_newest_reply_when_replies_retried(
    session: _Session,
) -> None:
    result = display_transcript(session.rows)

    assert [item.user.id for item in result] == [t.user_id for t in session.turns]
    assert len({item.user.id for item in result}) == len(result)
    for item, turn in zip(result, session.turns, strict=True):
        newest = max(turn.replies, key=lambda r: r.seq) if turn.replies else None
        assert (item.reply.id if item.reply else None) == (
            newest.id if newest else None
        )


@settings(max_examples=100, deadline=None)
@given(session=sessions(hashes=_HASHES_OR_NONE))
def test_display_transcript_keeps_only_failed_earlier_replies_as_retried_when_replies_retried(
    session: _Session,
) -> None:
    result = display_transcript(session.rows)

    for item, turn in zip(result, session.turns, strict=True):
        ordered = sorted(turn.replies, key=lambda r: r.seq)
        expected = [r.id for r in ordered[:-1] if r.status == "failed"]
        assert [r.id for r in item.retried] == expected


@settings(max_examples=100, deadline=None)
@given(session=sessions(hashes=_HASHES_OR_NONE))
def test_display_transcript_leaves_out_tool_rows_when_session_has_tool_activity(
    session: _Session,
) -> None:
    result = display_transcript(session.rows)

    shown = []
    for item in result:
        shown.append(item.user)
        if item.reply is not None:
            shown.append(item.reply)
        shown.extend(item.retried)
    assert all(row.role in {"user", "assistant"} for row in shown)


@settings(max_examples=100, deadline=None)
@given(session=sessions(hashes=_HASHES_OR_NONE))
def test_display_transcript_is_identical_when_rows_arrive_in_another_order(
    session: _Session,
) -> None:
    first = display_transcript(session.rows)
    second = display_transcript(session.reshuffled)

    assert first == second


# --- skill_updated (Req 20.10) ------------------------------------------------------


def _expected_flags(rows: tuple[_Row, ...]) -> dict[str, bool]:
    """Scan backwards from each assistant row to the nearest earlier row with a hash."""
    assistants = sorted((r for r in rows if r.role == "assistant"), key=lambda r: r.seq)
    expected: dict[str, bool] = {}
    for index, row in enumerate(assistants):
        earlier = next(
            (
                a.skill_hash
                for a in reversed(assistants[:index])
                if a.skill_hash is not None
            ),
            None,
        )
        expected[row.id] = (
            earlier is not None
            and row.skill_hash is not None
            and row.skill_hash != earlier
        )
    return expected


@settings(max_examples=100, deadline=None)
@given(session=sessions(hashes=_HASHES_OR_NONE))
def test_skill_updated_flags_match_nearest_earlier_hash_when_some_hashes_missing(
    session: _Session,
) -> None:
    flags = skill_updated_flags(session.rows)

    assert flags == _expected_flags(session.rows)


@settings(max_examples=100, deadline=None)
@given(session=sessions(hashes=_HASHES))
def test_skill_updated_flags_true_iff_hash_differs_from_previous_when_all_hashes_present(
    session: _Session,
) -> None:
    flags = skill_updated_flags(session.rows)

    assistants = sorted(
        (r for r in session.rows if r.role == "assistant"), key=lambda r: r.seq
    )
    assert set(flags) == {r.id for r in assistants}
    for index, row in enumerate(assistants):
        if index == 0:
            assert flags[row.id] is False
        else:
            assert flags[row.id] is (row.skill_hash != assistants[index - 1].skill_hash)


@settings(max_examples=100, deadline=None)
@given(
    previous=st.sampled_from(_HASHES_OR_NONE),
    current=st.sampled_from(_HASHES_OR_NONE),
)
def test_skill_updated_is_true_only_when_both_hashes_known_and_different(
    previous: str | None, current: str | None
) -> None:
    expected = (previous, current) in {
        (a, b) for a in _HASHES for b in _HASHES if a != b
    }

    assert skill_updated(previous, current) is expected


# --- Clarify count (Req 16.3, 47.7) -------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    status=st.sampled_from(_STATUSES),
    outcome=st.sampled_from(_OUTCOMES),
    before=st.booleans(),
)
def test_counts_toward_clarify_true_only_for_completed_reply_before_first_accepted(
    status: str, outcome: str | None, before: bool
) -> None:
    expected = status == "completed" and outcome == "reply" and before

    assert counts_toward_clarify(status, outcome, before) is expected


@settings(max_examples=100, deadline=None)
@given(kind=st.sampled_from(_REVISION_KINDS))
def test_ends_clarify_count_true_only_for_accepted_when_any_revision_kind(
    kind: str,
) -> None:
    assert ends_clarify_count(kind) is (kind == "accepted")


_EVENTS = st.one_of(
    st.tuples(st.just("turn"), st.sampled_from(_STATUSES), st.sampled_from(_OUTCOMES)),
    st.tuples(st.just("rev"), st.sampled_from(_REVISION_KINDS), st.none()),
)


@settings(max_examples=100, deadline=None)
@given(events=st.lists(_EVENTS, max_size=30))
def test_clarify_count_equals_completed_reply_turns_before_first_accepted_when_events_mixed(
    events: list[tuple[str, str, str | None]],
) -> None:
    # The caller walks a session in order and asks the two helpers at each step.
    before_first_accepted = True
    count = 0
    for kind, first, second in events:
        if kind == "turn":
            if counts_toward_clarify(first, second, before_first_accepted):
                count += 1
        elif ends_clarify_count(first):
            before_first_accepted = False

    stop = next(
        (i for i, e in enumerate(events) if e[0] == "rev" and e[1] == "accepted"),
        len(events),
    )
    expected = sum(
        1
        for kind, status, outcome in events[:stop]
        if kind == "turn" and status == "completed" and outcome == "reply"
    )
    assert count == expected


# --- latest_unproposed (Req 12.6, 37.3) ---------------------------------------------


@settings(max_examples=100, deadline=None)
@given(revisions=revision_lists())
def test_latest_unproposed_returned_iff_above_every_draft_when_revisions_mixed(
    revisions: list[_Rev],
) -> None:
    # Numbers are unique, so an unproposed revision is above every other revision
    # exactly when it is the highest-numbered revision of the session.
    highest = max(revisions, key=lambda r: r.revision)
    expected = highest if highest.kind == "unproposed" else None

    result = latest_unproposed(revisions)

    assert result is expected


@settings(max_examples=100, deadline=None)
@given(revisions=revision_lists())
def test_latest_unproposed_is_none_when_session_has_no_unproposed_revision(
    revisions: list[_Rev],
) -> None:
    drafts_only = [r for r in revisions if r.kind != "unproposed"]

    assert latest_unproposed(drafts_only) is None


# --- make_title (Req 12.2) ----------------------------------------------------------

_TITLE_ALPHABET = st.sampled_from(list("abcXYZ019 \t.,-") + ["é", "\u00a0"])
_LINES = st.lists(st.text(_TITLE_ALPHABET, max_size=90), max_size=5)


@settings(max_examples=100, deadline=None)
@given(message=st.text(max_size=300))
def test_make_title_is_non_empty_single_line_and_bounded_when_any_message(
    message: str,
) -> None:
    title = make_title(message)

    assert title
    assert len(title.splitlines()) == 1
    assert "\n" not in title and "\r" not in title
    assert title == title.strip()
    assert len(title) <= MAX_TITLE_CHARS + len(_ELLIPSIS)


@settings(max_examples=100, deadline=None)
@given(lines=_LINES, separator=st.sampled_from(["\n", "\r\n"]))
def test_make_title_uses_first_non_blank_line_collapsed_when_message_has_lines(
    lines: list[str], separator: str
) -> None:
    title = make_title(separator.join(lines))

    collapsed = [re.sub(r"\s+", " ", line).strip() for line in lines]
    first = next((line for line in collapsed if line), None)
    if first is None:
        assert title == "Untitled"
    elif len(first) <= MAX_TITLE_CHARS:
        assert title == first
    else:
        assert title.endswith(_ELLIPSIS)
        assert title[:-1] == first[:MAX_TITLE_CHARS].rstrip()
