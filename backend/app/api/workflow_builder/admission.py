"""Access dependency and send-message admission for the AI Workflow Builder.

Design section 3.1.2 fixes the order of the sixteen checks. The first failure
answers the request. A refused request stores nothing and publishes nothing, so
it never counts toward a limit (Req 47.2, 47.6, 47.10).

* :func:`require_builder_access` runs checks 1, 3 and 4 (authentication, the custom
  entitlement, readiness; check 2, the feature flag, was removed) and returns
  :class:`BuilderAccess`, which is ``(user, principal, tier)``. Every builder
  route depends on it. The entitlement answers before any session lookup, so it
  reveals nothing about session ids [pending G-07].
* :func:`admit_message` runs checks 6 to 16 under a per-user ``asyncio.Lock``
  [pending G-05]. The lock makes the per-user counts of checks 12 to 14 exact in
  one process. The partial unique index on running assistant rows is the
  restart-safe guard for the per-session rule; an ``IntegrityError`` from it is
  a 409 ``turn_running``. Check 5 (body schema) is done by
  :class:`~app.api.workflow_builder.schemas.SendMessageRequest`.
* :class:`BuilderReadiness` is the holder that lifecycle sets (task 16.10).
  It starts not ready, so a process that never ran startup refuses builder work.

Authorisation key: ``user_id``. A session that is missing and a session that
belongs to someone else both answer 404 ``session_not_found``.

The blocking store calls of checks 6 to 16 run in one ``asyncio.to_thread`` hop
(a request-scoped SQLAlchemy session is used by one thread at a time). Every
collaborator is injectable: the store, the capacity gate, the clock, the model
catalog and the turn starter, so tests can use ``InMemoryBuilderStore``.

Logs carry ids and counts only, never message text or ``canvas_state``
(Req 42.4, 44.2).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, NamedTuple, Protocol

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from agents.capabilities.model_catalog import ModelCatalog, ModelEntry
from app.agents.workflow_builder.model_catalog_view import (
    builder_models,
    check_chat_choice,
)
from app.agents.workflow_builder.transcript import make_title
from app.api.run_commands import _reject, _require_host_capacity
from app.api.workflow_builder.schemas import SendMessageRequest, TurnAccepted
from app.api.workflow_builder.store import (
    BegunTurn,
    DuplicateClientMessageError,
    SessionNotFoundError,
    TurnRunningError,
)
from app.api.workflow_builder.turns import (
    LiveTurn,
    register_live_turn,
    release_live_turn,
)
from app.core.config import settings
from app.core.dependencies import get_current_principal
from app.core.entitlements import can_run_pipeline
from app.core.identity import Principal, effective_tier
from app.models.user import User
from app.models.workflow_builder import (
    MESSAGE_STATUS_FAILED,
    WorkflowBuilderMessage,
    WorkflowBuilderSession,
)

__all__ = [
    "MAX_CANVAS_DEPTH",
    "MAX_CANVAS_STRING_CHARS",
    "AdmissionStore",
    "BuilderAccess",
    "BuilderReadiness",
    "RetryStore",
    "TurnStarter",
    "admit_message",
    "admit_retry",
    "get_admission_clock",
    "get_builder_readiness",
    "get_capacity_gate",
    "get_turn_starter",
    "require_builder_access",
    "set_turn_starter",
    "validate_canvas_state",
]

logger = logging.getLogger("app.api.workflow_builder.admission")

# Design 3.2.3: structural limits on the untrusted ``canvas_state``.
MAX_CANVAS_DEPTH: Final = 32
MAX_CANVAS_STRING_CHARS: Final = 200_000

_RATE_WINDOW_SECONDS: Final = 60
_RUNNING_TURNS_RETRY_AFTER_SECONDS: Final = 15
_CUSTOM_PIPELINE: Final = "custom"
_START_FAILED_ERROR_CODE: Final = "turn_start_failed"


# --- Access dependency (checks 1 to 4) -------------------------------------------------


class BuilderAccess(NamedTuple):
    """What a builder route receives once checks 1 to 4 pass."""

    user: User
    principal: Principal
    tier: str


class BuilderReadiness:
    """Whether this process may serve builder work (check 4).

    Lifecycle marks it ready after the skill package verified and the startup
    sweep finished, and unavailable when either failed. It starts not ready.
    """

    def __init__(self) -> None:
        self._ready = False

    @property
    def is_ready(self) -> bool:
        """True when builder work may be served."""
        return self._ready

    def mark_ready(self) -> None:
        """Allow builder work."""
        self._ready = True

    def mark_unavailable(self) -> None:
        """Refuse builder work with 503 ``builder_unavailable``."""
        self._ready = False


_readiness = BuilderReadiness()


def get_builder_readiness() -> BuilderReadiness:
    """FastAPI dependency: the process-wide readiness holder."""
    return _readiness


def require_builder_access(
    auth: tuple[User, Principal] = Depends(get_current_principal),
    readiness: BuilderReadiness = Depends(get_builder_readiness),
) -> BuilderAccess:
    """Run checks 1 to 4 of design 3.1.2 and return ``(user, principal, tier)``.

    Authentication (401) comes from ``get_current_principal``. Then: no custom
    entitlement is 403 ``custom_entitlement_required``; not ready is 503
    ``builder_unavailable``. The builder has no feature flag; it is always on.
    """
    user, principal = auth
    tier = effective_tier(user, principal)
    allowed, _reason = can_run_pipeline(tier, _CUSTOM_PIPELINE)
    if not allowed:
        raise _reject(
            "custom_entitlement_required",
            "Your plan does not include the workflow builder.",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    if not readiness.is_ready:
        raise _reject(
            "builder_unavailable",
            "The workflow builder is not available right now.",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            recoverable=False,
        )
    return BuilderAccess(user=user, principal=principal, tier=tier)


# --- Injectable collaborators ----------------------------------------------------------


class AdmissionStore(Protocol):
    """The Session_Store calls admission makes (``BuilderStore`` and its fake fit)."""

    def get_session(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderSession | None:
        """Return the caller's session or ``None``."""
        ...

    def find_user_message_by_client_id(
        self, user_id: str, session_id: str, client_message_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return the stored user row for a ``client_message_id``."""
        ...

    def get_running_turn(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return the session's running assistant row."""
        ...

    def count_user_messages_since(self, user_id: str, since: datetime) -> int:
        """Count the caller's stored user messages at or after ``since``."""
        ...

    def oldest_user_message_since(
        self, user_id: str, since: datetime
    ) -> datetime | None:
        """Return the creation time of the oldest such message."""
        ...

    def count_running_turns(self, user_id: str) -> int:
        """Count the caller's running assistant rows."""
        ...

    def begin_turn(  # noqa: PLR0913 - mirrors BuilderStore.begin_turn
        self,
        user_id: str,
        session_id: str,
        *,
        content: str,
        canvas_state: dict[str, Any] | None,
        client_message_id: str | None,
        model_id: str | None,
        effort: str | None,
        skill_hash: str | None,
        prompt_version: str | None = None,
        first_message_title: str | None = None,
    ) -> BegunTurn:
        """Insert the user row and the running assistant row in one transaction."""
        ...

    def finalize_assistant(
        self,
        user_id: str,
        turn_id: str,
        *,
        status: str,
        error_code: str | None = None,
        content: str = "",
    ) -> WorkflowBuilderMessage | None:
        """Write the final state of a running assistant row."""
        ...


class RetryStore(AdmissionStore, Protocol):
    """The extra Session_Store calls retry makes."""

    def get_message(
        self, user_id: str, message_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return one of the caller's message rows."""
        ...

    def get_latest_message(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return the newest user or assistant row."""
        ...

    def begin_retry(  # noqa: PLR0913 - mirrors BuilderStore.begin_retry
        self,
        user_id: str,
        session_id: str,
        user_message_id: str,
        *,
        model_id: str | None,
        effort: str | None,
        skill_hash: str | None,
        prompt_version: str | None = None,
    ) -> BegunTurn:
        """Insert a running assistant row replying to an existing user row."""
        ...


#: Creates and attaches the Turn's asyncio task (``turns.attach_task``). Task 15.4
#: supplies the real one, which runs ``run_turn(turn, ...)``. Arguments: the live
#: Turn, the message text and the ``canvas_state`` it was sent with.
type TurnStarter = Callable[[LiveTurn, str, dict[str, Any]], None]

#: Raises an ``HTTPException`` when the host cannot take new work (check 15).
type CapacityGate = Callable[[User], None]

_turn_starter: TurnStarter | None = None


def set_turn_starter(starter: TurnStarter | None) -> None:
    """Install the function that starts ``run_turn`` for an admitted message."""
    global _turn_starter  # noqa: PLW0603 - one composition-root hook per process
    _turn_starter = starter


def _unconfigured_starter(
    turn: LiveTurn, content: str, canvas_state: dict[str, Any]
) -> None:
    raise RuntimeError("no builder turn starter is configured")


def get_turn_starter() -> TurnStarter:
    """FastAPI dependency: the installed turn starter."""
    return _turn_starter or _unconfigured_starter


def get_capacity_gate() -> CapacityGate:
    """FastAPI dependency: the host capacity gate (``_require_host_capacity``)."""
    return _require_host_capacity


def _utcnow() -> datetime:
    return datetime.now(UTC)


def get_admission_clock() -> Callable[[], datetime]:
    """FastAPI dependency: the clock the rolling rate window reads."""
    return _utcnow


# --- Per-user lock ---------------------------------------------------------------------

# Locks live only while some request holds or waits on one, so the map does not
# grow with the number of users.
_USER_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)


def _user_lock(user_id: str) -> asyncio.Lock:
    lock = _USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _USER_LOCKS[user_id] = lock
    return lock


# --- Check 11: canvas_state ------------------------------------------------------------


def _canvas_is_well_formed(canvas_state: object) -> bool:
    """Structural check of design 3.2.3, without recursion.

    A JSON object whose ``steps`` is a list of objects; nesting depth at most
    :data:`MAX_CANVAS_DEPTH` (the top-level object is depth 1); no string, key
    or value, longer than :data:`MAX_CANVAS_STRING_CHARS`.
    """
    if not isinstance(canvas_state, dict):
        return False
    steps = canvas_state.get("steps")
    if not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps):
        return False
    stack: list[tuple[object, int]] = [(canvas_state, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_CANVAS_DEPTH:
            return False
        if isinstance(node, dict):
            children: list[object] = []
            for key, value in node.items():
                if not isinstance(key, str) or len(key) > MAX_CANVAS_STRING_CHARS:
                    return False
                children.append(value)
        else:
            children = list(node) if isinstance(node, list) else []
        for child in children:
            if isinstance(child, str):
                if len(child) > MAX_CANVAS_STRING_CHARS:
                    return False
            elif isinstance(child, (dict, list)):
                stack.append((child, depth + 1))
    return True


def validate_canvas_state(canvas_state: object) -> None:
    """Check 11: raise 422 ``canvas_state_invalid`` or 413 ``canvas_state_too_large``.

    The size is the length of the compact UTF-8 JSON, ``separators=(",", ":")``
    and ``ensure_ascii=False`` [pending G-23]. It is measured after the
    structure check, so a deeply nested value is never serialised.
    """
    invalid = _reject(
        "canvas_state_invalid",
        "The canvas could not be read.",
        http_status=422,
    )
    if not _canvas_is_well_formed(canvas_state):
        raise invalid
    try:
        size = len(
            json.dumps(canvas_state, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        )
    except (TypeError, ValueError) as exc:
        raise invalid from exc
    if size > settings.BUILDER_MAX_CANVAS_STATE_BYTES:
        raise _reject(
            "canvas_state_too_large",
            "The canvas is too large to send.",
            http_status=413,
        )


# --- Checks 6 to 16 --------------------------------------------------------------------


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive datetime as UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _check_model_choice(
    model_id: str, effort: str | None, tier: str, catalog: list[ModelEntry]
) -> None:
    """Checks 9 and 10 through ``check_chat_choice``, which returns a refusal."""
    refusal = check_chat_choice(catalog, builder_models(tier), model_id, effort)
    if refusal is not None:
        raise _reject(
            refusal.code,
            refusal.message,
            http_status=refusal.status_code,
        )


def _check_rate_limit(store: AdmissionStore, user_id: str, now: datetime) -> None:
    """Check 13: fewer than ``BUILDER_MESSAGES_PER_MINUTE`` stored messages in 60 s."""
    window = timedelta(seconds=_RATE_WINDOW_SECONDS)
    since = now - window
    if store.count_user_messages_since(user_id, since) < (
        settings.BUILDER_MESSAGES_PER_MINUTE
    ):
        return
    oldest = store.oldest_user_message_since(user_id, since)
    retry_after = _RATE_WINDOW_SECONDS
    if oldest is not None:
        left = (_as_utc(oldest) + window - now).total_seconds()
        retry_after = max(1, math.ceil(left))
    raise _reject(
        "rate_limited",
        "You are sending messages too quickly. Please wait a moment.",
        http_status=status.HTTP_429_TOO_MANY_REQUESTS,
        recoverable=True,
        response_headers={"Retry-After": str(retry_after)},
        retry_after_seconds=retry_after,
    )


def _check_limits(
    store: AdmissionStore,
    access: BuilderAccess,
    session: WorkflowBuilderSession,
    capacity_gate: CapacityGate,
    now: datetime,
) -> None:
    """Checks 12 to 15: turn limit, rate limit, running turns, host capacity."""
    user_id = str(access.user.id)
    if int(session.turn_count) >= settings.BUILDER_MAX_TURNS_PER_SESSION:  # type: ignore[arg-type]  # 12
        raise _reject(
            "session_turn_limit",
            "This conversation has reached its limit. Start a new one.",
            http_status=status.HTTP_409_CONFLICT,
        )

    _check_rate_limit(store, user_id, now)  # 13

    if (
        store.count_running_turns(user_id)  # 14
        >= settings.BUILDER_MAX_RUNNING_TURNS_PER_USER
    ):
        raise _reject(
            "too_many_running_turns",
            "Too many replies are in progress. Please wait for one to finish.",
            http_status=status.HTTP_429_TOO_MANY_REQUESTS,
            recoverable=True,
            response_headers={"Retry-After": str(_RUNNING_TURNS_RETRY_AFTER_SECONDS)},
            retry_after_seconds=_RUNNING_TURNS_RETRY_AFTER_SECONDS,
        )

    capacity_gate(access.user)  # 15, last


def _admit_locked(  # noqa: PLR0913 - one call per request, all inputs are named
    *,
    store: AdmissionStore,
    access: BuilderAccess,
    session_id: str,
    body: SendMessageRequest,
    capacity_gate: CapacityGate,
    now: datetime,
    catalog: list[ModelEntry],
) -> TurnAccepted | BegunTurn:
    """Checks 6 to 16, blocking. The caller holds the user's lock.

    Returns ``TurnAccepted`` (``replayed``) for a duplicate ``client_message_id``
    and the two stored rows for an admitted message.
    """
    user_id = str(access.user.id)

    session = store.get_session(user_id, session_id)  # 6
    if session is None:
        raise _session_not_found()

    original = store.find_user_message_by_client_id(  # 7
        user_id, session_id, body.client_message_id
    )
    if original is not None:
        return _replay(original)

    if store.get_running_turn(user_id, session_id) is not None:  # 8
        raise _turn_running()

    _check_model_choice(body.model_id, body.effort, access.tier, catalog)  # 9, 10
    validate_canvas_state(body.canvas_state)  # 11

    _check_limits(store, access, session, capacity_gate, now)  # 12 to 15

    try:  # 16
        return store.begin_turn(
            user_id,
            session_id,
            content=body.content,
            canvas_state=body.canvas_state,
            client_message_id=body.client_message_id,
            model_id=body.model_id,
            effort=body.effort,
            skill_hash=str(session.skill_hash),
            first_message_title=make_title(body.content),
        )
    except SessionNotFoundError as exc:
        raise _session_not_found() from exc
    except DuplicateClientMessageError:
        # Another process stored the same id between check 7 and the insert.
        raced = store.find_user_message_by_client_id(
            user_id, session_id, body.client_message_id
        )
        if raced is None:
            raise _turn_running() from None
        return _replay(raced)
    except (TurnRunningError, IntegrityError) as exc:
        raise _turn_running() from exc


def _replay(original: WorkflowBuilderMessage) -> TurnAccepted:
    """The ids of a message that was already stored (Req 21.10)."""
    return TurnAccepted(
        turn_id=str(original.turn_id),
        message_id=str(original.id),
        replayed=True,
    )


def _session_not_found() -> HTTPException:
    return _reject(
        "session_not_found",
        "Conversation not found.",
        http_status=status.HTTP_404_NOT_FOUND,
    )


def _turn_running() -> HTTPException:
    return _reject(
        "turn_running",
        "A reply is still in progress in this conversation.",
        http_status=status.HTTP_409_CONFLICT,
        recoverable=True,
    )


@dataclass(frozen=True)
class _Started:
    """The live Turn created for an admitted message."""

    turn: LiveTurn
    accepted: TurnAccepted


async def admit_message(  # noqa: PLR0913 - every collaborator is injectable
    *,
    store: AdmissionStore,
    access: BuilderAccess,
    session_id: str,
    body: SendMessageRequest,
    start_turn: TurnStarter,
    capacity_gate: CapacityGate = _require_host_capacity,
    clock: Callable[[], datetime] = _utcnow,
    catalog: list[ModelEntry] | None = None,
) -> TurnAccepted:
    """Run checks 6 to 16 of design 3.1.2 and start the Turn.

    Returns the 202 body. Raises ``HTTPException`` with a typed body for the
    first refusal; nothing is stored and nothing is published for a refusal.
    An admitted message stores the user row and the running assistant row in one
    transaction (check 16), registers the live Turn and calls ``start_turn``.

    Args:
        store: The Session_Store (or ``InMemoryBuilderStore``).
        access: The result of :func:`require_builder_access`.
        session_id: The session named in the path.
        body: The validated request body (check 5 already ran).
        start_turn: Creates and attaches the Turn's task.
        capacity_gate: Check 15; raises when the host is busy.
        clock: The time source of the rolling rate window.
        catalog: The full model catalog; defaults to ``ModelCatalog().list()``.
    """
    user_id = str(access.user.id)
    entries = catalog if catalog is not None else ModelCatalog().list()
    async with _user_lock(user_id):
        outcome = await asyncio.to_thread(
            _admit_locked,
            store=store,
            access=access,
            session_id=session_id,
            body=body,
            capacity_gate=capacity_gate,
            now=clock(),
            catalog=entries,
        )
        if isinstance(outcome, TurnAccepted):
            logger.info("builder message replayed session=%s", session_id)
            return outcome
        started = await _start(
            store=store,
            user_id=user_id,
            tier=access.tier,
            session_id=session_id,
            model_id=body.model_id,
            effort=body.effort,
            content=body.content,
            canvas_state=body.canvas_state,
            begun=outcome,
            start_turn=start_turn,
        )
    logger.info(
        "builder turn admitted session=%s turn=%s", session_id, started.turn.turn_id
    )
    return started.accepted


async def _start(  # noqa: PLR0913 - private helper, all inputs are named
    *,
    store: AdmissionStore,
    user_id: str,
    tier: str,
    session_id: str,
    model_id: str,
    effort: str | None,
    content: str,
    canvas_state: dict[str, Any],
    begun: BegunTurn,
    start_turn: TurnStarter,
) -> _Started:
    """Register the live Turn and start its task; undo the row if that fails.

    ``tier`` is the caller's resolved tier. It becomes ``LiveTurn.tier``, which the
    read tools and the model caps use for the whole Turn.
    """
    turn_id = str(begun.assistant_message.id)
    turn = LiveTurn(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=str(begun.user_message.id),
        user_id=user_id,
        model_id=model_id,
        effort=effort,
        tier=tier,
    )
    register_live_turn(turn)
    try:
        start_turn(turn, content, canvas_state)
    except Exception:
        # A stored running row with no task would block the session with 409s.
        logger.exception(
            "builder turn could not start session=%s turn=%s", session_id, turn_id
        )
        release_live_turn(turn)
        try:
            await asyncio.to_thread(
                store.finalize_assistant,
                user_id,
                turn_id,
                status=MESSAGE_STATUS_FAILED,
                error_code=_START_FAILED_ERROR_CODE,
            )
        except Exception:
            logger.exception("builder turn row not finalised turn=%s", turn_id)
        raise _reject(
            _START_FAILED_ERROR_CODE,
            "The reply could not be started. Please try again.",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            recoverable=True,
        ) from None
    return _Started(
        turn=turn,
        accepted=TurnAccepted(
            turn_id=turn_id, message_id=str(begun.user_message.id), replayed=False
        ),
    )


# --- Retry (checks 8 to 16 on a stored user message, G-01) -------------------------------


def _retry_not_allowed() -> HTTPException:
    return _reject(
        "retry_not_allowed",
        "Only the latest failed reply can be retried.",
        http_status=status.HTTP_409_CONFLICT,
    )


def _admit_retry_locked(  # noqa: PLR0913 - one call per request, all inputs are named
    *,
    store: RetryStore,
    access: BuilderAccess,
    session_id: str,
    turn_id: str,
    capacity_gate: CapacityGate,
    now: datetime,
    catalog: list[ModelEntry],
) -> tuple[BegunTurn, str, dict[str, Any]]:
    """Checks 8 to 16 for a retry, blocking. The caller holds the user's lock.

    Returns the stored rows with the user message text and the ``canvas_state``
    that message was sent with.
    """
    user_id = str(access.user.id)
    session = store.get_session(user_id, session_id)
    if session is None:
        raise _session_not_found()
    if store.get_running_turn(user_id, session_id) is not None:  # 8
        raise _turn_running()

    latest = store.get_latest_message(user_id, session_id)
    if latest is None or str(latest.id) != turn_id:
        raise _retry_not_allowed()
    if latest.role != "assistant" or latest.status != MESSAGE_STATUS_FAILED:
        raise _retry_not_allowed()
    reply_to = latest.reply_to_message_id
    user_message = store.get_message(user_id, str(reply_to)) if reply_to else None
    canvas_state = user_message.canvas_state if user_message is not None else None
    if user_message is None or not isinstance(canvas_state, dict):
        raise _retry_not_allowed()

    model_id = str(latest.model_id or user_message.model_id or "")
    effort = latest.effort if latest.model_id else user_message.effort
    effort_value = str(effort) if effort is not None else None
    _check_model_choice(model_id, effort_value, access.tier, catalog)  # 9, 10
    validate_canvas_state(canvas_state)  # 11
    _check_limits(store, access, session, capacity_gate, now)  # 12 to 15

    try:  # 16
        begun = store.begin_retry(
            user_id,
            session_id,
            str(user_message.id),
            model_id=model_id,
            effort=effort_value,
            skill_hash=str(session.skill_hash),
        )
    except SessionNotFoundError as exc:
        raise _session_not_found() from exc
    except (TurnRunningError, IntegrityError) as exc:
        raise _turn_running() from exc
    return begun, str(user_message.content), canvas_state


async def admit_retry(  # noqa: PLR0913 - every collaborator is injectable
    *,
    store: RetryStore,
    access: BuilderAccess,
    session_id: str,
    turn_id: str,
    start_turn: TurnStarter,
    capacity_gate: CapacityGate = _require_host_capacity,
    clock: Callable[[], datetime] = _utcnow,
    catalog: list[ModelEntry] | None = None,
) -> TurnAccepted:
    """Retry the latest failed turn without storing a second user message [pending G-01].

    Runs checks 8 to 16 of design 3.1.2 under the user's lock, with the model,
    effort and ``canvas_state`` of the original message, then stores a new
    running assistant row that replies to the same user message and starts the
    Turn. A refusal stores and publishes nothing.
    """
    user_id = str(access.user.id)
    entries = catalog if catalog is not None else ModelCatalog().list()
    async with _user_lock(user_id):
        begun, content, canvas_state = await asyncio.to_thread(
            _admit_retry_locked,
            store=store,
            access=access,
            session_id=session_id,
            turn_id=turn_id,
            capacity_gate=capacity_gate,
            now=clock(),
            catalog=entries,
        )
        started = await _start(
            store=store,
            user_id=user_id,
            tier=access.tier,
            session_id=session_id,
            model_id=str(begun.assistant_message.model_id),
            effort=(
                str(begun.assistant_message.effort)
                if begun.assistant_message.effort is not None
                else None
            ),
            content=content,
            canvas_state=canvas_state,
            begun=begun,
            start_turn=start_turn,
        )
    logger.info(
        "builder turn retried session=%s turn=%s", session_id, started.turn.turn_id
    )
    return started.accepted
