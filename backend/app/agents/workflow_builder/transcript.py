"""Transcript replay, summary rules and session projections for the builder.

Pure module: no I/O, no clock, no database, and no ``app.api`` import. Stored
rows reach it through the duck-typed protocols :class:`MessageLike` and
:class:`RevisionLike`, so the ORM rows of ``app.models.workflow_builder``
satisfy them without this module importing the store (design section 3.6.3,
Req 25, Req 47.12, 47.13).

Replay (Req 25.2 to 25.9):

* :func:`build_exchanges` turns stored rows into ``(user message, newest
  reply)`` exchanges. Tool rows and thinking never enter an exchange.
* :func:`select` keeps the newest exchanges inside the token budget. The latest
  ``keep_verbatim`` exchanges are always kept. The summary's tokens count
  inside the budget.
* :func:`summary_needed`, :func:`summary_input` and :func:`has_required_headings`
  carry the summary rules. The model call itself belongs to the Turn_Runner.
* :func:`history_messages` builds the ``HumanMessage``/``AIMessage`` history,
  with the summary prepended to the oldest selected user message.

Projections: :func:`display_transcript`, :func:`skill_updated`,
:func:`counts_toward_clarify`, :func:`latest_unproposed` and :func:`make_title`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately

__all__ = [
    "DEFAULT_KEEP_VERBATIM",
    "FAILED_REPLY_TEXT",
    "MAX_TITLE_CHARS",
    "REQUIRED_HEADINGS",
    "SUMMARY_PROMPT_FILE",
    "DisplayExchange",
    "Exchange",
    "MessageLike",
    "RevisionLike",
    "Selection",
    "build_exchanges",
    "counts_toward_clarify",
    "display_transcript",
    "ends_clarify_count",
    "exchange_tokens",
    "has_required_headings",
    "history_messages",
    "latest_unproposed",
    "make_title",
    "omitted_through_seq",
    "select",
    "skill_updated",
    "skill_updated_flags",
    "summary_input",
    "summary_needed",
    "text_tokens",
]

DEFAULT_KEEP_VERBATIM: Final = 4
FAILED_REPLY_TEXT: Final = "(no reply: the turn failed)"
MAX_TITLE_CHARS: Final = 60
_TITLE_ELLIPSIS: Final = "\u2026"
_UNTITLED: Final = "Untitled"

SUMMARY_PROMPT_FILE: Final = "transcript_summary.v1.md"
REQUIRED_HEADINGS: Final[tuple[str, ...]] = (
    "Answers to questions",
    "Requirements and constraints",
    "Workflow Brief",
    "Decisions",
)

_ROLE_USER: Final = "user"
_ROLE_ASSISTANT: Final = "assistant"
_STATUS_RUNNING: Final = "running"
_STATUS_FAILED: Final = "failed"
_STATUS_COMPLETED: Final = "completed"
_OUTCOME_REPLY: Final = "reply"
_KIND_ACCEPTED: Final = "accepted"
_KIND_UNPROPOSED: Final = "unproposed"
_SUMMARY_OPEN: Final = "<summary_of_earlier_turns>"
_SUMMARY_CLOSE: Final = "</summary_of_earlier_turns>"


class MessageLike(Protocol):
    """The fields of a stored message row that this module reads."""

    @property
    def id(self) -> str: ...

    @property
    def seq(self) -> int: ...

    @property
    def role(self) -> str: ...

    @property
    def reply_to_message_id(self) -> str | None: ...

    @property
    def status(self) -> str: ...

    @property
    def outcome(self) -> str | None: ...

    @property
    def content(self) -> str: ...

    @property
    def skill_hash(self) -> str | None: ...


class RevisionLike(Protocol):
    """The fields of a stored draft revision that this module reads."""

    @property
    def revision(self) -> int: ...

    @property
    def kind(self) -> str: ...


# --- Replay -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Exchange:
    """One user message and the newest reply to it.

    Attributes:
        user_message_id: Id of the user message.
        user_seq: Session ``seq`` of the user message.
        user_text: The user's text, verbatim.
        reply_seq: Session ``seq`` of the newest reply.
        reply_text: The reply text, or a placeholder when the reply has none.
    """

    user_message_id: str
    user_seq: int
    user_text: str
    reply_seq: int
    reply_text: str


@dataclass(frozen=True, slots=True)
class Selection:
    """The result of :func:`select`.

    ``omitted`` is always a prefix of the exchanges and ``selected`` the
    suffix after it. A summary is used if and only if ``omitted`` is not empty.
    """

    selected: tuple[Exchange, ...]
    omitted: tuple[Exchange, ...]

    @property
    def uses_summary(self) -> bool:
        """True when some exchanges are left out and a summary stands for them."""
        return bool(self.omitted)


def _reply_text(reply: MessageLike) -> str:
    """Return the reply text, or a placeholder so every exchange has a reply."""
    if reply.content.strip():
        return reply.content
    if reply.status == _STATUS_FAILED:
        return FAILED_REPLY_TEXT
    return f"(no reply: the turn ended {reply.status.replace('_', ' ')})"


def build_exchanges(
    rows: Iterable[MessageLike], current_message_id: str | None = None
) -> list[Exchange]:
    """Build the replayable exchanges from stored rows, oldest first.

    Each user message pairs with its reply that has the highest ``seq``, so a
    retried turn replays only its newest reply. Tool rows are ignored.
    Thinking is not a field here, so it cannot leak. A user message with no
    reply, or whose newest reply is still running, is not an exchange, and
    neither is the message with id ``current_message_id`` (the current turn).

    Args:
        rows: Stored rows of one session in any order.
        current_message_id: The user message of the turn being started.

    Returns:
        Exchanges ordered by the user message's ``seq``.
    """
    ordered = sorted(rows, key=lambda row: row.seq)
    newest_reply: dict[str, MessageLike] = {}
    for row in ordered:
        if row.role == _ROLE_ASSISTANT and row.reply_to_message_id is not None:
            newest_reply[row.reply_to_message_id] = row  # later seq overwrites
    exchanges: list[Exchange] = []
    for row in ordered:
        if row.role != _ROLE_USER or row.id == current_message_id:
            continue
        reply = newest_reply.get(row.id)
        if reply is None or reply.status == _STATUS_RUNNING:
            continue
        exchanges.append(
            Exchange(
                user_message_id=row.id,
                user_seq=row.seq,
                user_text=row.content,
                reply_seq=reply.seq,
                reply_text=_reply_text(reply),
            )
        )
    return exchanges


def text_tokens(text: str) -> int:
    """Return the approximate token count of ``text``."""
    return count_tokens_approximately([HumanMessage(content=text)])


def exchange_tokens(exchange: Exchange) -> int:
    """Return the approximate token count of an exchange as replayed."""
    return count_tokens_approximately(
        [
            HumanMessage(content=exchange.user_text),
            AIMessage(content=exchange.reply_text),
        ]
    )


def select(
    exchanges: Sequence[Exchange],
    budget: int,
    keep_verbatim: int = DEFAULT_KEEP_VERBATIM,
    summary_tokens: int = 0,
) -> Selection:
    """Pick the exchanges to replay verbatim (design 3.6.3, Req 25.3 to 25.6).

    The newest ``keep_verbatim`` exchanges are always kept, even when they pass
    the budget. Older exchanges are added newest first while the running total,
    the next exchange and ``summary_tokens`` stay within ``budget``. The first
    exchange that does not fit ends the walk, so ``omitted`` is a prefix. The
    current message is not in ``exchanges``, so it is never one of the kept.

    Args:
        exchanges: Exchanges before the current message, oldest first.
        budget: Replay budget in tokens.
        keep_verbatim: Number of newest exchanges that are always kept.
        summary_tokens: Tokens of the summary, counted inside the budget.

    Raises:
        ValueError: ``keep_verbatim`` is below 1, ``budget`` or
            ``summary_tokens`` is negative.
    """
    if keep_verbatim < 1:
        raise ValueError("keep_verbatim must be at least 1")
    if budget < 0 or summary_tokens < 0:
        raise ValueError("budget and summary_tokens must not be negative")
    split = max(len(exchanges) - keep_verbatim, 0)
    must = list(exchanges[split:])
    used = sum(exchange_tokens(item) for item in must)
    cut = split
    for index in range(split - 1, -1, -1):
        cost = exchange_tokens(exchanges[index])
        if used + cost + summary_tokens > budget:
            break
        used += cost
        cut = index
    return Selection(selected=tuple(exchanges[cut:]), omitted=tuple(exchanges[:cut]))


def omitted_through_seq(omitted: Sequence[Exchange]) -> int | None:
    """Return the ``seq`` of the last omitted message, or None when none is."""
    return omitted[-1].reply_seq if omitted else None


def summary_needed(
    omitted: Sequence[Exchange], summary_through_seq: int | None
) -> bool:
    """Say whether a new summary must be written before the replay (Req 25.8, 25.9).

    True if and only if some exchanges are omitted and the stored summary does
    not reach the last omitted message.
    """
    last = omitted_through_seq(omitted)
    if last is None:
        return False
    return summary_through_seq is None or summary_through_seq < last


def summary_input(
    previous_summary: str | None,
    summary_through_seq: int | None,
    omitted: Sequence[Exchange],
) -> str:
    """Build the text the summary call reads (design 3.6.3).

    It holds the previous summary and only the omitted messages after
    ``summary_through_seq``, so the call stays bounded (Req 25.7).
    """
    floor = summary_through_seq if summary_through_seq is not None else 0
    lines: list[str] = []
    for item in omitted:
        if item.user_seq > floor:
            lines.append(f"[user]\n{item.user_text}")
        if item.reply_seq > floor:
            lines.append(f"[assistant]\n{item.reply_text}")
    previous = (previous_summary or "").strip() or "(none)"
    return (
        f"<previous_summary>\n{previous}\n</previous_summary>\n"
        f"<messages_to_add>\n{chr(10).join(lines)}\n</messages_to_add>"
    )


def has_required_headings(text: str) -> bool:
    """Return True when ``text`` has a markdown heading for each required section.

    A heading is a line of ``#`` marks, optional bold marks, the heading text
    (case-insensitive) and an optional colon.
    """
    for heading in REQUIRED_HEADINGS:
        pattern = (
            rf"^[ \t]*#{{1,6}}[ \t]*(?:\*\*)?{re.escape(heading)}:?(?:\*\*)?[ \t]*$"
        )
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is None:
            return False
    return True


def history_messages(
    selection: Selection, summary_text: str | None
) -> list[BaseMessage]:
    """Build the history as alternating ``HumanMessage`` and ``AIMessage``.

    When ``selection`` omits exchanges and ``summary_text`` is not blank, the
    summary is prepended to the oldest selected user message inside a
    ``<summary_of_earlier_turns>`` block, so no synthetic assistant text is
    needed (design 3.6.3).
    """
    messages: list[BaseMessage] = []
    for index, item in enumerate(selection.selected):
        user_text = item.user_text
        if (
            index == 0
            and selection.uses_summary
            and summary_text
            and summary_text.strip()
        ):
            user_text = f"{_SUMMARY_OPEN}\n{summary_text.strip()}\n{_SUMMARY_CLOSE}\n\n{user_text}"
        messages.append(HumanMessage(content=user_text))
        messages.append(AIMessage(content=item.reply_text))
    return messages


# --- Projections --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DisplayExchange[M: MessageLike]:
    """One user message as the transcript shows it.

    Attributes:
        user: The user row, shown once.
        reply: The newest reply, or None when there is none.
        retried: Earlier replies that ended ``failed``, oldest first, shown as
            collapsed "failed, retried" lines [pending G-01].
    """

    user: M
    reply: M | None
    retried: tuple[M, ...]


def display_transcript[M: MessageLike](rows: Iterable[M]) -> list[DisplayExchange[M]]:
    """Group stored rows into the transcript the panel shows, oldest first.

    Tool rows are left out. Each user message appears once with its newest
    reply (running included). Earlier replies that failed are kept as
    ``retried``; earlier replies in any other status are dropped.
    """
    ordered = sorted(rows, key=lambda row: row.seq)
    replies: dict[str, list[M]] = {}
    for row in ordered:
        if row.role == _ROLE_ASSISTANT and row.reply_to_message_id is not None:
            replies.setdefault(row.reply_to_message_id, []).append(row)
    result: list[DisplayExchange[M]] = []
    for row in ordered:
        if row.role != _ROLE_USER:
            continue
        group = replies.get(row.id, [])
        newest = group[-1] if group else None
        retried = tuple(r for r in group[:-1] if r.status == _STATUS_FAILED)
        result.append(DisplayExchange(user=row, reply=newest, retried=retried))
    return result


def skill_updated(previous_skill_hash: str | None, skill_hash: str | None) -> bool:
    """Say whether a message's Skill_Hash differs from the previous one (Req 20.10).

    False when either hash is unknown, so a failed turn without a hash does not
    raise the "builder was updated" line.
    """
    return (
        previous_skill_hash is not None
        and skill_hash is not None
        and previous_skill_hash != skill_hash
    )


def skill_updated_flags(rows: Iterable[MessageLike]) -> dict[str, bool]:
    """Return ``skill_updated`` for every assistant row, keyed by message id.

    Each row is compared with the nearest earlier assistant row that has a
    Skill_Hash. The first assistant row is never flagged.
    """
    flags: dict[str, bool] = {}
    previous: str | None = None
    for row in sorted(rows, key=lambda item: item.seq):
        if row.role != _ROLE_ASSISTANT:
            continue
        flags[row.id] = skill_updated(previous, row.skill_hash)
        if row.skill_hash is not None:
            previous = row.skill_hash
    return flags


def counts_toward_clarify(
    status: str, outcome: str | None, before_first_accepted: bool
) -> bool:
    """Say whether a finished turn counts as a clarifying turn (Req 16.3).

    Only a turn that ended ``completed`` with outcome ``reply``, before the
    session's first accepted draft, counts [pending G-09, G-10].
    """
    return (
        before_first_accepted
        and status == _STATUS_COMPLETED
        and outcome == _OUTCOME_REPLY
    )


def ends_clarify_count(revision_kind: str) -> bool:
    """Say whether a revision of this kind ends the clarify count.

    Only an ``accepted`` draft does. A seed (revision 0 of an edit session), an
    undo and an unproposed revision do not [pending G-09].
    """
    return revision_kind == _KIND_ACCEPTED


def latest_unproposed[R: RevisionLike](revisions: Iterable[R]) -> R | None:
    """Return the newest unproposed revision when it is newer than every draft.

    A draft here is a seed, accepted or undo revision (Req 12.6, 37.3). Returns
    None when there is no unproposed revision or a draft is at least as new.
    """
    newest_unproposed: R | None = None
    newest_draft = -1
    for item in revisions:
        if item.kind == _KIND_UNPROPOSED:
            if newest_unproposed is None or item.revision > newest_unproposed.revision:
                newest_unproposed = item
        else:
            newest_draft = max(newest_draft, item.revision)
    if newest_unproposed is not None and newest_unproposed.revision > newest_draft:
        return newest_unproposed
    return None


def make_title(first_message: str) -> str:
    """Make a session title from the first message without a model call.

    Takes the first non-blank line, collapses whitespace, and cuts it at
    :data:`MAX_TITLE_CHARS` characters plus an ellipsis [pending G-24].
    """
    for line in first_message.splitlines():
        collapsed = " ".join(line.split())
        if collapsed:
            if len(collapsed) > MAX_TITLE_CHARS:
                return collapsed[:MAX_TITLE_CHARS].rstrip() + _TITLE_ELLIPSIS
            return collapsed
    return _UNTITLED
