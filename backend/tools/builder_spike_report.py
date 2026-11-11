"""Read-only Spike report: what the stored builder rows say about each Turn.

The Spike (Req 46) is operator-run: the operator drives the 3 reference requests
through the built Builder, then points this script at the resulting session ids.
For every Turn of those sessions it prints, as JSON:

  * the duration (``ended_at - started_at``, in seconds),
  * the token usage as stored on the assistant message, plus a total,
  * the tool-call count (all stored tool rows, also by tool name and by status),
  * the Server_Gate rejections, and
  * the Adherence_Record as stored on the assistant message.

It calls no model and writes nothing. The transaction is opened READ ONLY on
PostgreSQL, only ``SELECT`` statements are issued, and the session is rolled
back and closed. It prints ids, counts, statuses and the stored adherence JSON
only. It never prints message content, thinking, tool results or the manifest
(user data), and it selects only the first ``_CONTENT_HEAD_CHARS`` characters
of a tool row, to recognise a gate rejection.

Gate rejections are not a stored column. ``propose_draft`` returns a text that
starts ``The server rejected the draft (attempt N).`` and the Turn stores that
text on the tool row, so a rejection is a ``propose_draft`` tool row whose
content starts that way. Dry runs and tool-use mistakes do not start that way
and are not counted (Req 42.5, design 3.5.2).

Usage (from ``backend/``, against the DB in ``DATABASE_URL``)::

    uv run python -m tools.builder_spike_report SESSION_ID [SESSION_ID ...]
    uv run python -m tools.builder_spike_report --indent 2 SESSION_ID

Exit status: 0 when every session id was found, 1 when some were not (the JSON
still lists the rest and names the missing ids), 2 on a setup or query error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

__all__ = [
    "SessionRow",
    "ToolRow",
    "TurnRow",
    "build_report",
    "load_rows",
    "main",
]

#: Tool name of the draft hand-off; only its rows can be gate rejections.
_PROPOSE_TOOL: Final = "propose_draft"
#: First line of ``propose_draft``'s rejection text (``draft_tool._rejection_text``).
_REJECTION_RE: Final = re.compile(r"^The server rejected the draft \(attempt \d+\)\.")
#: How much of a tool row's content is read, enough for the rejection header.
_CONTENT_HEAD_CHARS: Final = 80
#: Token counters of ``TokenUsage`` / ``UsageCounts`` that make up the total.
_BILLED_KEYS: Final = ("input", "output")
_COUNT_KEYS: Final = ("input", "output", "cache_read", "cache_write")


@dataclass(frozen=True, slots=True)
class SessionRow:
    """The columns of a builder session the report prints."""

    id: str
    mode: str | None
    model_id: str | None
    effort: str | None
    skill_hash: str | None
    turn_count: int | None


@dataclass(frozen=True, slots=True)
class TurnRow:
    """The columns of an assistant message (one Turn) the report prints."""

    id: str
    session_id: str
    seq: int
    status: str | None
    outcome: str | None
    stop_reason: str | None
    error_code: str | None
    model_id: str | None
    effort: str | None
    skill_hash: str | None
    prompt_version: str | None
    usage: Any
    adherence: Any
    revision: int | None
    started_at: datetime | None
    ended_at: datetime | None


@dataclass(frozen=True, slots=True)
class ToolRow:
    """A stored tool row, reduced to what the counts need."""

    session_id: str
    turn_id: str
    status: str | None
    tool: Any
    content_head: str | None


def _count(source: Any, key: str) -> int:
    """Return ``source[key]`` when it is a non-negative int, else 0."""
    if not isinstance(source, Mapping):
        return 0
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _tokens(usage: Any) -> dict[str, Any] | None:
    """Return the stored usage with a ``total``, or ``None`` when none is stored.

    ``total`` is input plus output tokens of the Turn and of its transcript
    summary call. Cache reads and writes are listed but not added (they are
    priced differently).
    """
    if not isinstance(usage, Mapping):
        return None
    summary = usage.get("summary")
    result: dict[str, Any] = {key: _count(usage, key) for key in _COUNT_KEYS}
    result["summary"] = (
        {key: _count(summary, key) for key in _COUNT_KEYS}
        if isinstance(summary, Mapping)
        else None
    )
    result["total"] = sum(_count(usage, key) for key in _BILLED_KEYS) + sum(
        _count(summary, key) for key in _BILLED_KEYS
    )
    return result


def _duration_seconds(started: datetime | None, ended: datetime | None) -> float | None:
    """Return the elapsed seconds, or ``None`` when either end is missing."""
    if started is None or ended is None:
        return None
    try:
        return round((ended - started).total_seconds(), 3)
    except TypeError:  # one naive and one aware datetime
        return None


def _isoformat(value: datetime | None) -> str | None:
    """Return ``value`` as ISO 8601, or ``None``."""
    return value.isoformat() if value is not None else None


def _tool_name(row: ToolRow) -> str:
    """Return the tool name stored in the row's ``tool`` JSON, or ``unknown``."""
    name = row.tool.get("tool") if isinstance(row.tool, Mapping) else None
    return name if isinstance(name, str) and name else "unknown"


def _is_gate_rejection(row: ToolRow) -> bool:
    """True for a ``propose_draft`` row whose result is a Server_Gate rejection."""
    return (
        _tool_name(row) == _PROPOSE_TOOL
        and row.content_head is not None
        and _REJECTION_RE.match(row.content_head) is not None
    )


def _turn_report(turn: TurnRow, tools: Sequence[ToolRow]) -> dict[str, Any]:
    """Build the report entry of one Turn from its row and its tool rows."""
    return {
        "turn_id": turn.id,
        "seq": turn.seq,
        "status": turn.status,
        "outcome": turn.outcome,
        "stop_reason": turn.stop_reason,
        "error_code": turn.error_code,
        "model_id": turn.model_id,
        "effort": turn.effort,
        "skill_hash": turn.skill_hash,
        "prompt_version": turn.prompt_version,
        "revision": turn.revision,
        "started_at": _isoformat(turn.started_at),
        "ended_at": _isoformat(turn.ended_at),
        "duration_seconds": _duration_seconds(turn.started_at, turn.ended_at),
        "tokens": _tokens(turn.usage),
        "tool_calls": {
            "total": len(tools),
            "by_tool": dict(sorted(Counter(_tool_name(t) for t in tools).items())),
            "by_status": dict(
                sorted(Counter(t.status or "unknown" for t in tools).items())
            ),
        },
        "gate_rejections": sum(1 for t in tools if _is_gate_rejection(t)),
        "adherence": dict(turn.adherence)
        if isinstance(turn.adherence, Mapping)
        else None,
    }


def build_report(
    session_ids: Sequence[str],
    sessions: Sequence[SessionRow],
    turns: Sequence[TurnRow],
    tools: Sequence[ToolRow],
) -> dict[str, Any]:
    """Build the JSON-serialisable report. Pure: no I/O.

    Args:
        session_ids: The ids the operator asked for, in order. Sessions appear
            in this order; duplicates are reported once.
        sessions: The session rows found.
        turns: The assistant rows of those sessions.
        tools: The tool rows of those sessions.

    Returns:
        ``{"sessions": [...], "missing_session_ids": [...]}``. Turns are in
        ``seq`` order within a session.
    """
    by_id = {row.id: row for row in sessions}
    ordered_ids = list(dict.fromkeys(session_ids))
    tools_by_turn: dict[str, list[ToolRow]] = {}
    for tool in tools:
        tools_by_turn.setdefault(tool.turn_id, []).append(tool)
    entries: list[dict[str, Any]] = []
    for session_id in ordered_ids:
        session = by_id.get(session_id)
        if session is None:
            continue
        own_turns = sorted(
            (t for t in turns if t.session_id == session_id), key=lambda t: t.seq
        )
        entries.append(
            {
                "session_id": session.id,
                "mode": session.mode,
                "model_id": session.model_id,
                "effort": session.effort,
                "skill_hash": session.skill_hash,
                "turn_count": session.turn_count,
                "turns": [
                    _turn_report(t, tools_by_turn.get(t.id, [])) for t in own_turns
                ],
            }
        )
    return {
        "sessions": entries,
        "missing_session_ids": [i for i in ordered_ids if i not in by_id],
    }


def load_rows(
    session: Session, session_ids: Sequence[str]
) -> tuple[list[SessionRow], list[TurnRow], list[ToolRow]]:
    """Read the session, assistant and tool rows of ``session_ids``. SELECT only.

    On PostgreSQL the transaction is first set READ ONLY, so the database
    refuses any write even if this function were changed later.
    """
    from sqlalchemy import func, select, text

    from app.models.workflow_builder import (
        MESSAGE_ROLE_ASSISTANT,
        MESSAGE_ROLE_TOOL,
        WorkflowBuilderMessage as Message,
        WorkflowBuilderSession as BuilderSession,
    )

    ids = list(dict.fromkeys(session_ids))
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SET TRANSACTION READ ONLY"))

    session_rows = session.execute(
        select(
            BuilderSession.id,
            BuilderSession.mode,
            BuilderSession.model_id,
            BuilderSession.effort,
            BuilderSession.skill_hash,
            BuilderSession.turn_count,
        ).where(BuilderSession.id.in_(ids))
    ).all()
    turn_rows = session.execute(
        select(
            Message.id,
            Message.session_id,
            Message.seq,
            Message.status,
            Message.outcome,
            Message.stop_reason,
            Message.error_code,
            Message.model_id,
            Message.effort,
            Message.skill_hash,
            Message.prompt_version,
            Message.usage,
            Message.adherence,
            Message.revision,
            Message.started_at,
            Message.ended_at,
        )
        .where(Message.session_id.in_(ids), Message.role == MESSAGE_ROLE_ASSISTANT)
        .order_by(Message.session_id, Message.seq)
    ).all()
    tool_rows = session.execute(
        select(
            Message.session_id,
            Message.turn_id,
            Message.status,
            Message.tool,
            func.substr(Message.content, 1, _CONTENT_HEAD_CHARS).label("content_head"),
        )
        .where(Message.session_id.in_(ids), Message.role == MESSAGE_ROLE_TOOL)
        .order_by(Message.session_id, Message.seq)
    ).all()

    return (
        [SessionRow(*row) for row in session_rows],
        [TurnRow(*row) for row in turn_rows],
        [ToolRow(*row) for row in tool_rows],
    )


def _default_session_factory() -> Session:
    """Open a session on the app's configured database (``DATABASE_URL``)."""
    from app.models.database import SessionLocal

    return SessionLocal()


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    """CLI entry point. Returns the process exit status (see module docstring)."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("session_ids", nargs="+", metavar="SESSION_ID")
    parser.add_argument(
        "--indent", type=int, default=None, help="indent the JSON output"
    )
    args = parser.parse_args(argv)
    session_ids = [value.strip() for value in args.session_ids if value.strip()]
    if not session_ids:
        parser.error("at least one non-empty session id is required")

    try:
        session = (session_factory or _default_session_factory)()
    except Exception as exc:  # noqa: BLE001 - setup failure is reported, not raised
        print(f"setup error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        sessions, turns, tools = load_rows(session, session_ids)
    except Exception as exc:  # noqa: BLE001 - query failure is reported, not raised
        print(f"query error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        session.rollback()
        session.close()

    report = build_report(session_ids, sessions, turns, tools)
    print(json.dumps(report, indent=args.indent, sort_keys=False))
    return 1 if report["missing_session_ids"] else 0


if __name__ == "__main__":
    sys.exit(main())
