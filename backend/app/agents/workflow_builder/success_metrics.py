"""The three Builder success metrics (Req 44.6, Property 29).

Pure functions over plain facts: no I/O, no clock, no shared state. The API
layer reads the facts from the Session_Store (``BuilderStore``) and passes them
in, so each definition is tested against generated facts without a database.

Definitions:

* **Save rate**: sessions with at least one save, divided by all sessions.
* **First-call gate pass rate**: among turns that called ``propose_draft`` at
  least once, the share whose first call passed the Server_Gate.
* **Median turns before first save**: the median, over sessions with at least
  one save, of the number of turns run before that first save.

A rate or median whose population is empty is ``None``, not zero, so a
dashboard can tell "no data" from "zero percent".
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "SessionFact",
    "SuccessMetrics",
    "TurnGateFact",
    "compute_success_metrics",
    "first_call_gate_pass_rate",
    "median_turns_before_first_save",
    "session_save_rate",
]


@dataclass(frozen=True, slots=True)
class SessionFact:
    """What the metrics need to know about one Session.

    Attributes:
        session_id: The Session id.
        turns_before_first_save: Number of Turns run before the Session's first
            save, or ``None`` when no save was made from the Session.
    """

    session_id: str
    turns_before_first_save: int | None = None

    def __post_init__(self) -> None:
        """Reject a negative turn count."""
        if (
            self.turns_before_first_save is not None
            and self.turns_before_first_save < 0
        ):
            raise ValueError("turns_before_first_save cannot be negative")

    @property
    def saved(self) -> bool:
        """True when at least one save was made from the Session."""
        return self.turns_before_first_save is not None


@dataclass(frozen=True, slots=True)
class TurnGateFact:
    """One Turn that called ``propose_draft`` at least once.

    Attributes:
        turn_id: The Turn id.
        first_call_passed: True when the Turn's first ``propose_draft`` call
            passed the Server_Gate.
    """

    turn_id: str
    first_call_passed: bool


@dataclass(frozen=True, slots=True)
class SuccessMetrics:
    """The three metrics with the counts they come from.

    Attributes:
        session_save_rate: Share of Sessions with a save, ``None`` without Sessions.
        first_call_gate_pass_rate: Share of ``propose_draft`` Turns whose first
            call passed, ``None`` without such Turns.
        median_turns_before_first_save: Median over saved Sessions, ``None``
            without saved Sessions.
        session_count: Sessions counted.
        saved_session_count: Sessions with at least one save.
        propose_turn_count: Turns that called ``propose_draft``.
        first_call_passed_count: Of those, Turns whose first call passed.
    """

    session_save_rate: float | None
    first_call_gate_pass_rate: float | None
    median_turns_before_first_save: float | None
    session_count: int
    saved_session_count: int
    propose_turn_count: int
    first_call_passed_count: int

    def as_dict(self) -> dict[str, float | int | None]:
        """Return the metrics as a JSON-serialisable dict."""
        return {
            "session_save_rate": self.session_save_rate,
            "first_call_gate_pass_rate": self.first_call_gate_pass_rate,
            "median_turns_before_first_save": self.median_turns_before_first_save,
            "session_count": self.session_count,
            "saved_session_count": self.saved_session_count,
            "propose_turn_count": self.propose_turn_count,
            "first_call_passed_count": self.first_call_passed_count,
        }


def session_save_rate(sessions: Iterable[SessionFact]) -> float | None:
    """Return the share of Sessions with at least one save, or ``None`` if none."""
    facts = list(sessions)
    if not facts:
        return None
    return sum(1 for fact in facts if fact.saved) / len(facts)


def first_call_gate_pass_rate(turns: Iterable[TurnGateFact]) -> float | None:
    """Return the share of Turns whose first ``propose_draft`` call passed.

    ``turns`` holds only Turns that called ``propose_draft`` at least once.
    Returns ``None`` when it is empty.
    """
    facts = list(turns)
    if not facts:
        return None
    return sum(1 for fact in facts if fact.first_call_passed) / len(facts)


def median_turns_before_first_save(sessions: Iterable[SessionFact]) -> float | None:
    """Return the median turns before the first save over saved Sessions.

    Sessions without a save are ignored. Returns ``None`` when none was saved.
    """
    counts = [
        fact.turns_before_first_save
        for fact in sessions
        if fact.turns_before_first_save is not None
    ]
    if not counts:
        return None
    return float(statistics.median(counts))


def compute_success_metrics(
    sessions: Iterable[SessionFact], turns: Iterable[TurnGateFact]
) -> SuccessMetrics:
    """Compute the three metrics and their counts in one call."""
    session_facts = list(sessions)
    turn_facts = list(turns)
    return SuccessMetrics(
        session_save_rate=session_save_rate(session_facts),
        first_call_gate_pass_rate=first_call_gate_pass_rate(turn_facts),
        median_turns_before_first_save=median_turns_before_first_save(session_facts),
        session_count=len(session_facts),
        saved_session_count=sum(1 for fact in session_facts if fact.saved),
        propose_turn_count=len(turn_facts),
        first_call_passed_count=sum(1 for fact in turn_facts if fact.first_call_passed),
    )
