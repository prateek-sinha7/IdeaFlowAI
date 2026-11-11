"""Property test for builder admission (design 3.1.2, checks 6 to 16).

# Feature: ai-workflow-builder, Property 17: Admission stores only accepted messages

For any sequence of send requests (valid, invalid, duplicate ``client_message_id``,
concurrent, over the turn, rate or running-turn limits, or refused by the capacity
gate) against an in-memory store with the same interface as the real one:

* the stored user messages are exactly the accepted ones;
* a refused request stores nothing, starts nothing and publishes nothing;
* a duplicate returns the original ids and stores nothing;
* a session never has two running turns and a user never has more than two;
* no user has more than five accepted messages in any 60-second window;
* the capacity gate is asked only by a request that passed every earlier check.

**Validates: Requirements 2.5, 21.7, 21.10, 26.2, 29.1, 29.2, 29.3, 47.2, 47.6, 47.10**

The system under test is ``admit_message``. The store is ``InMemoryBuilderStore``,
the capacity gate is a stub per request, and one controllable clock feeds both
the store and the admission rate window. Settings are lowered for the turn limit
(4) and the canvas size (200 bytes) so those refusals are reachable; the rate
limit (5 per 60 s) and the running-turn limit (2) keep their defaults.

The oracle is a small reference model of the design table. It predicts the first
check that fails for each request from its own bookkeeping and never reads the
store or the production helpers. After every operation the stored rows are
compared with the model and the global limits are checked from the stored rows
alone.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import patch

from fastapi import HTTPException
from hypothesis import event, given, settings
from hypothesis import strategies as st

from app.api.workflow_builder import turns
from app.api.workflow_builder.admission import BuilderAccess, admit_message
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.schemas import SendMessageRequest, TurnAccepted
from app.core.config import settings as app_settings
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_store import InMemoryBuilderStore
from tests.fakes.principal import principal_for

MODEL = "eu.anthropic.claude-sonnet-5-5"
EFFORT = "medium"
BASE = datetime(2030, 1, 1, tzinfo=UTC)

USERS = ("user-a", "user-b")
# Pool of sessions: each entry is the index into USERS of the owner. Index 3 in a request is a
# session id that does not exist.
SESSION_OWNERS = (0, 0, 0, 1, 1)
MISSING_SESSION_INDEX = len(SESSION_OWNERS)
MISSING_SESSION_ID = "no-such-session"
ALL_SESSIONS = -1
FRESH_CID = -1  # the scenario replaces it with a client_message_id never used before

TURN_LIMIT = 4
CANVAS_LIMIT_BYTES = 200
RATE_LIMIT = 5
RATE_WINDOW_SECONDS = 60
RUNNING_LIMIT = 2

CanvasKind = Literal["ok", "invalid", "big"]
_CANVAS: dict[CanvasKind, dict[str, Any]] = {
    "ok": {"steps": []},
    "invalid": {"nope": 1},
    "big": {"steps": [{"n": "x" * 300}]},
}
_CAPACITY_CODE = "host_capacity_exhausted"


@dataclass(frozen=True)
class _Send:
    """One send request."""

    user: int
    session: int
    cid: int
    model_ok: bool
    effort_ok: bool
    canvas: CanvasKind
    busy: bool

    def client_message_id(self) -> str:
        return f"client-id-{self.cid:04d}"


@dataclass(frozen=True)
class _Op:
    """One step of the scenario."""

    kind: Literal["send", "burst", "finish", "tick"]
    sends: tuple[_Send, ...] = ()
    session: int = 0
    seconds: int = 0


_mostly_true = st.sampled_from((True,) * 8 + (False,))


def _sessions_for(user: int) -> st.SearchStrategy[int]:
    """Mostly the user's own sessions, sometimes another user's or a missing one."""
    own = [i for i, owner in enumerate(SESSION_OWNERS) if owner == user]
    other = [i for i, owner in enumerate(SESSION_OWNERS) if owner != user]
    return st.sampled_from(own * 8 + other + [MISSING_SESSION_INDEX])


_sends = st.integers(0, len(USERS) - 1).flatmap(
    lambda user: st.builds(
        _Send,
        user=st.just(user),
        session=_sessions_for(user),
        cid=st.one_of(st.integers(0, 3), st.integers(0, 99)),
        model_ok=_mostly_true,
        effort_ok=_mostly_true,
        canvas=st.sampled_from(("ok",) * 8 + ("invalid", "big")),
        busy=st.sampled_from((False,) * 8 + (True,)),
    )
)
# A well-formed request with a new client_message_id, to the sender's own session.
_valid_sends = st.integers(0, len(USERS) - 1).flatmap(
    lambda user: st.builds(
        _Send,
        user=st.just(user),
        session=st.sampled_from(
            [i for i, owner in enumerate(SESSION_OWNERS) if owner == user]
        ),
        cid=st.just(FRESH_CID),
        model_ok=st.just(True),
        effort_ok=st.just(True),
        canvas=st.just("ok"),
        busy=st.just(False),
    )
)
_send_op = st.builds(_Op, kind=st.just("send"), sends=st.tuples(_sends))
_valid_send_op = st.builds(_Op, kind=st.just("send"), sends=st.tuples(_valid_sends))
_burst_op = st.builds(
    _Op,
    kind=st.just("burst"),
    sends=st.lists(_sends, min_size=2, max_size=4).map(tuple),
)
_finish_op = st.builds(
    _Op, kind=st.just("finish"), session=st.integers(0, len(SESSION_OWNERS) - 1)
)
# ``session=ALL_SESSIONS`` ends every running turn, so limits that need many
# accepted messages (turns per session, messages per minute) can be reached.
_finish_all_op = st.builds(_Op, kind=st.just("finish"), session=st.just(ALL_SESSIONS))
_tick_op = st.builds(
    _Op,
    kind=st.just("tick"),
    seconds=st.sampled_from((0, 1, 5, 30, 59, 60, 61, 120)),
)
# Weighted towards sends and finishes so the per-user limits are actually reached.
_ops = st.one_of(
    _send_op,
    _send_op,
    _valid_send_op,
    _valid_send_op,
    _valid_send_op,
    _valid_send_op,
    _finish_op,
    _finish_all_op,
    _finish_all_op,
    _burst_op,
    _tick_op,
)


class _RecordingBus(SessionEventBus):
    """An event bus that remembers every publish, so a refusal can be shown silent."""

    def __init__(self) -> None:
        super().__init__()
        self.published: list[tuple[str, object]] = []

    def publish(self, session_id: str, event: Any) -> None:
        self.published.append((session_id, event))
        super().publish(session_id, event)


@dataclass(frozen=True)
class _Outcome:
    """What admission answered: an accepted body or an error code."""

    accepted: TurnAccepted | None
    code: str | None
    status: int | None
    retry_after: int | None


class _Scenario:
    """Runs a scenario against ``admit_message`` and the reference model."""

    def __init__(self) -> None:
        self.t = 0  # seconds since BASE
        self.store = InMemoryBuilderStore(clock=self.now)
        self.bus = _RecordingBus()
        self.starts: list[str] = []
        self.gate_calls = 0
        self.expected_gate_calls = 0
        self._fresh = 0
        self.session_ids = [
            str(
                self.store.create_session(
                    USERS[owner], **BuilderSessionFactory.create_kwargs()
                ).id
            )
            for owner in SESSION_OWNERS
        ]
        # Reference model (the oracle's own bookkeeping).
        self.turn_count = [0] * len(SESSION_OWNERS)
        self.running: list[str | None] = [None] * len(SESSION_OWNERS)
        self.ids: dict[tuple[int, str], tuple[str, str]] = {}
        self.accepted_times: dict[int, list[int]] = {0: [], 1: []}
        self.accepted_message_ids: set[str] = set()

    # --- Clock and callables -------------------------------------------------------

    def now(self) -> datetime:
        return BASE + timedelta(seconds=self.t)

    def start_turn(self, turn: Any, content: str, canvas_state: dict[str, Any]) -> None:
        self.starts.append(turn.turn_id)

    @staticmethod
    def access(user: int) -> BuilderAccess:
        row = SimpleNamespace(id=USERS[user], tier="enterprise", is_admin=False)
        return BuilderAccess(user=row, principal=principal_for(row), tier="enterprise")  # type: ignore[arg-type]

    def gate_for(self, busy: bool) -> Callable[[Any], None]:
        def gate(user: Any) -> None:
            self.gate_calls += 1
            if busy:
                raise HTTPException(status_code=503, detail={"code": _CAPACITY_CODE})

        return gate

    # --- The oracle ----------------------------------------------------------------

    def _running_for_user(self, user: int) -> int:
        return sum(
            1
            for index, owner in enumerate(SESSION_OWNERS)
            if owner == user and self.running[index] is not None
        )

    def predict(self, send: _Send) -> str:
        """The first check that fails for ``send`` in the current model state.

        Returns ``"accepted"``, ``"replay"`` or an error code.
        """
        index = send.session
        if index == MISSING_SESSION_INDEX or SESSION_OWNERS[index] != send.user:
            return "session_not_found"
        if (index, send.client_message_id()) in self.ids:
            return "replay"
        if self.running[index] is not None:
            return "turn_running"
        if not send.model_ok:
            return "model_not_allowed"
        if not send.effort_ok:
            return "effort_not_allowed"
        if send.canvas == "invalid":
            return "canvas_state_invalid"
        if send.canvas == "big":
            return "canvas_state_too_large"
        if self.turn_count[index] >= TURN_LIMIT:
            return "session_turn_limit"
        recent = [
            t
            for t in self.accepted_times[send.user]
            if t >= self.t - RATE_WINDOW_SECONDS
        ]
        if len(recent) >= RATE_LIMIT:
            return "rate_limited"
        if self._running_for_user(send.user) >= RUNNING_LIMIT:
            return "too_many_running_turns"
        self.expected_gate_calls += 1
        if send.busy:
            return _CAPACITY_CODE
        return "accepted"

    # --- Driving admission ---------------------------------------------------------

    def _request(self, send: _Send) -> SendMessageRequest:
        return SendMessageRequest(
            content="Make a workflow",
            model_id=MODEL if send.model_ok else "no-such-model",
            effort=EFFORT if send.effort_ok else "bogus",
            canvas_state=_CANVAS[send.canvas],
            client_message_id=send.client_message_id(),
        )

    async def _admit(self, send: _Send) -> _Outcome:
        session_id = (
            MISSING_SESSION_ID
            if send.session == MISSING_SESSION_INDEX
            else self.session_ids[send.session]
        )
        try:
            accepted = await admit_message(
                store=self.store,
                access=self.access(send.user),
                session_id=session_id,
                body=self._request(send),
                start_turn=self.start_turn,
                capacity_gate=self.gate_for(send.busy),
                clock=self.now,
            )
        except HTTPException as exc:
            headers = exc.headers or {}
            retry = headers.get("Retry-After")
            return _Outcome(
                accepted=None,
                code=exc.detail["code"],  # type: ignore[index]
                status=exc.status_code,
                retry_after=int(retry) if retry is not None else None,
            )
        return _Outcome(accepted=accepted, code=None, status=202, retry_after=None)

    # --- Snapshots and checks ------------------------------------------------------

    def _all_rows(self) -> list[Any]:
        rows: list[Any] = []
        for index, owner in enumerate(SESSION_OWNERS):
            rows.extend(self.store.list_messages(USERS[owner], self.session_ids[index]))
        return rows

    def _session_state(self) -> list[tuple[Any, ...]]:
        out: list[tuple[Any, ...]] = []
        for index, owner in enumerate(SESSION_OWNERS):
            row = self.store.get_session(USERS[owner], self.session_ids[index])
            assert row is not None
            out.append(
                (row.turn_count, row.next_seq, row.title, row.model_id, row.effort)
            )
        return out

    def _check_stored_matches_model(self) -> None:
        rows = self._all_rows()
        stored_users = {r.id for r in rows if r.role == "user"}
        assert stored_users == self.accepted_message_ids
        stored_running = {
            r.session_id: r.id
            for r in rows
            if r.role == "assistant" and r.status == "running"
        }
        expected_running = {
            self.session_ids[i]: turn
            for i, turn in enumerate(self.running)
            if turn is not None
        }
        # One running turn per session, and the same ones the model expects.
        assert sum(
            1 for r in rows if r.role == "assistant" and r.status == "running"
        ) == len(stored_running)
        assert stored_running == expected_running
        assert set(turns._LIVE_TURNS) == set(expected_running)

    def _check_limits_from_store(self) -> None:
        rows = self._all_rows()
        for user in range(len(USERS)):
            running = sum(
                1
                for r in rows
                if r.user_id == USERS[user]
                and r.role == "assistant"
                and r.status == "running"
            )
            assert running <= RUNNING_LIMIT
            times = sorted(
                r.created_at
                for r in rows
                if r.user_id == USERS[user] and r.role == "user"
            )
            window = timedelta(seconds=RATE_WINDOW_SECONDS)
            for moment in times:
                in_window = [x for x in times if moment - window <= x <= moment]
                assert len(in_window) <= RATE_LIMIT

    # --- Applying outcomes ---------------------------------------------------------

    def _apply(self, send: _Send, expected: str, outcome: _Outcome) -> str | None:
        """Check one outcome against the prediction and update the model.

        Returns the new turn id when the request was accepted.
        """
        index = send.session
        if expected == "accepted":
            assert outcome.accepted is not None, outcome
            assert outcome.accepted.replayed is False
            turn_id = outcome.accepted.turn_id
            message_id = outcome.accepted.message_id
            self.turn_count[index] += 1
            self.running[index] = turn_id
            self.ids[(index, send.client_message_id())] = (turn_id, message_id)
            self.accepted_times[send.user].append(self.t)
            self.accepted_message_ids.add(message_id)
            return turn_id
        if expected == "replay":
            original = self.ids[(index, send.client_message_id())]
            assert outcome.accepted is not None, outcome
            assert outcome.accepted.replayed is True
            assert (outcome.accepted.turn_id, outcome.accepted.message_id) == original
            return None
        assert outcome.accepted is None, outcome
        assert outcome.code == expected
        if expected in {"rate_limited", "too_many_running_turns"}:
            assert outcome.status == 429
            assert outcome.retry_after is not None
            assert outcome.retry_after >= 1
        return None

    def _resolve(self, send: _Send) -> _Send:
        """Give a fresh request a client_message_id that was never used."""
        if send.cid != FRESH_CID:
            return send
        self._fresh += 1
        return replace(send, cid=1000 + self._fresh)

    async def play_send(self, requested: tuple[_Send, ...]) -> None:
        """Send one request, or several at once, and check the result."""
        sends = tuple(self._resolve(s) for s in requested)
        before_rows = {r.id for r in self._all_rows()}
        before_state = self._session_state()
        before_starts = len(self.starts)
        before_live = dict(turns._LIVE_TURNS)

        if len(sends) == 1:
            outcomes = [await self._admit(sends[0])]
        else:
            outcomes = list(await asyncio.gather(*(self._admit(s) for s in sends)))

        # Requests of one user run in the order they were created (the per-user
        # lock is FIFO) and users do not affect each other, so the model can
        # replay the whole group in list order.
        new_turns: list[str] = []
        new_messages: set[str] = set()
        touched: set[int] = set()
        for send, outcome in zip(sends, outcomes, strict=True):
            expected = self.predict(send)
            event(f"admission: {expected}")
            turn_id = self._apply(send, expected, outcome)
            if turn_id is not None:
                new_turns.append(turn_id)
                new_messages.add(self.ids[(send.session, send.client_message_id())][1])
                touched.add(send.session)

        after_rows = self._all_rows()
        added = {r.id for r in after_rows} - before_rows
        added_users = {r.id for r in after_rows if r.id in added and r.role == "user"}
        added_assistants = {
            r.id for r in after_rows if r.id in added and r.role == "assistant"
        }
        # Only accepted requests stored rows: one user row and one running assistant row.
        assert added_users == new_messages
        assert added_assistants == set(new_turns)
        assert len(added) == 2 * len(new_turns)
        assert sorted(self.starts[before_starts:]) == sorted(new_turns)

        # Sessions that took no accepted message are exactly as they were.
        after_state = self._session_state()
        for index in range(len(SESSION_OWNERS)):
            if index not in touched:
                assert after_state[index] == before_state[index]
        if not new_turns:
            assert dict(turns._LIVE_TURNS) == before_live
        # A request that was refused or replayed published nothing; so did every other.
        assert self.bus.published == []
        # The capacity gate was reached only by requests that passed checks 6 to 14.
        assert self.gate_calls == self.expected_gate_calls
        self._check_stored_matches_model()
        self._check_limits_from_store()

    def finish(self, session_index: int) -> None:
        """End the session's running turn, as the Turn_Runner does."""
        turn_id = self.running[session_index]
        if turn_id is None:
            return
        owner = USERS[SESSION_OWNERS[session_index]]
        row = self.store.finalize_assistant(owner, turn_id, status="completed")
        assert row is not None
        live = turns.get_live_turn(self.session_ids[session_index])
        assert live is not None
        turns.release_live_turn(live)
        self.running[session_index] = None
        self._check_stored_matches_model()

    async def play(self, ops: list[_Op]) -> None:
        turns._LIVE_TURNS.clear()
        turns.set_event_bus(self.bus)
        try:
            for op in ops:
                if op.kind in ("send", "burst"):
                    await self.play_send(op.sends)
                elif op.kind == "finish":
                    targets = (
                        range(len(SESSION_OWNERS))
                        if op.session == ALL_SESSIONS
                        else [op.session]
                    )
                    for index in targets:
                        self.finish(index)
                else:
                    self.t += op.seconds
        finally:
            turns._LIVE_TURNS.clear()
            turns.set_event_bus(None)


# Feature: ai-workflow-builder, Property 17: Admission stores only accepted messages
@settings(max_examples=100, deadline=None)
@given(ops=st.lists(_ops, min_size=15, max_size=50))
def test_admit_message_stores_only_accepted_messages_for_any_request_sequence(
    ops: list[_Op],
) -> None:
    """**Validates: Requirements 2.5, 21.7, 21.10, 26.2, 29.1, 29.2, 29.3, 47.2, 47.6, 47.10**"""
    with (
        patch.object(app_settings, "BUILDER_MAX_TURNS_PER_SESSION", TURN_LIMIT),
        patch.object(
            app_settings, "BUILDER_MAX_CANVAS_STATE_BYTES", CANVAS_LIMIT_BYTES
        ),
        patch.object(app_settings, "BUILDER_MESSAGES_PER_MINUTE", RATE_LIMIT),
        patch.object(app_settings, "BUILDER_MAX_RUNNING_TURNS_PER_USER", RUNNING_LIMIT),
    ):
        asyncio.run(_Scenario().play(ops))
