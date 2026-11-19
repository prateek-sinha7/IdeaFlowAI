"""Build the agent input of one builder Turn (design 3.1.4, 3.6.2, 3.6.3).

:func:`build_agent_input` turns the stored session into what
``DeepAgentRunner.astream_events`` needs:

* ``history``: the replayed exchanges (``transcript.select``), with the
  Transcript_Summary in front of the oldest one when exchanges were left out;
* ``message``: the final human message, ``turn_context.render`` output, with the
  id ``turn:<turn_id>`` the pinning middleware looks for (decision 13.2).

The summary is written or updated here when ``transcript.summary_needed`` says
so. The call goes through the injected :data:`Summarizer` (production:
:func:`default_summarizer`, which uses ``build_model(model_id, effort=None)``).
A summary without the four required headings gets one retry. If both tries fail,
the previous summary stays (decision 15.4).

All store reads run in one ``asyncio.to_thread`` call on their own store, and
the result is plain values, so no ORM row crosses the thread boundary.

Logs carry ids and counts only, never message text (Req 42.4, 44.2).
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from agents.capabilities.model_catalog import ModelCatalog
from agents.capabilities.token_usage import usage_from_metadata
from app.agents.model_factory import build_model
from app.agents.workflow_builder import transcript
from app.agents.workflow_builder.canonical import canonical_hash
from app.agents.workflow_builder.events import UsageCounts
from app.agents.workflow_builder.model_catalog_view import builder_models
from app.agents.workflow_builder.turn_context import (
    TurnContextInputs,
    UnfinishedWork,
    render,
)
from app.api.run_engine import _saved_row_trust
from app.core.config import settings
from app.core.entitlements import TIER_MODEL_COST_CLASSES
from app.models.workflow_builder import DRAFT_KIND_UNPROPOSED

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from langchain_core.messages import BaseMessage

    from app.api.workflow_builder.store import LatestRevisions, SummaryState
    from app.models.workflow_builder import (
        WorkflowBuilderDraft,
        WorkflowBuilderMessage,
        WorkflowBuilderSession,
    )

__all__ = [
    "AgentInput",
    "InputRequest",
    "InputStore",
    "SummaryResult",
    "Summarizer",
    "add_usage",
    "build_agent_input",
    "default_summarizer",
    "pinned_message_id",
]

logger = logging.getLogger(__name__)

_DEFAULT_CONTEXT_WINDOW: Final = 200_000
_SUMMARY_ATTEMPTS: Final = 2
_FALLBACK_STOP_STATUS: Final = "interrupted"
# agent_input.py is <backend>/app/api/workflow_builder/agent_input.py.
_PROMPT_FILE: Final = (
    Path(__file__).resolve().parents[2]
    / "agents"
    / "workflow_builder"
    / "prompts"
    / transcript.SUMMARY_PROMPT_FILE
)


def pinned_message_id(turn_id: str) -> str:
    """Return the id the final human message of a Turn must carry."""
    return f"turn:{turn_id}"


# --- Ports ----------------------------------------------------------------------------


class InputStore(Protocol):
    """The Session_Store calls the agent input needs."""

    def get_session(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderSession | None:
        """Return the caller's session or ``None``."""
        ...

    def list_messages(
        self, user_id: str, session_id: str, *, after_seq: int | None = None
    ) -> list[WorkflowBuilderMessage]:
        """Return the session's user and assistant rows in ``seq`` order."""
        ...

    def get_message(
        self, user_id: str, message_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return one of the caller's message rows."""
        ...

    def get_summary(self, user_id: str, session_id: str) -> SummaryState | None:
        """Return the Transcript_Summary state."""
        ...

    def set_summary(
        self, user_id: str, session_id: str, *, text: str, through_seq: int
    ) -> None:
        """Store the Transcript_Summary and the last seq it covers."""
        ...

    def get_latest_revisions(self, user_id: str, session_id: str) -> LatestRevisions:
        """Return the newest revision of each kind."""
        ...


@dataclass(frozen=True, slots=True)
class SummaryResult:
    """What one summary call returned.

    Attributes:
        text: The model's text.
        usage: Token counts of the call.
    """

    text: str
    usage: UsageCounts


#: ``(model_id, input_text) -> SummaryResult``. One model call.
type Summarizer = Callable[[str, str], Awaitable[SummaryResult]]

#: Opens a store for one blocking call (see ``turns.StoreScope``).
type InputStoreScope = Callable[[], AbstractContextManager[InputStore]]


@dataclass(frozen=True, slots=True)
class InputRequest:
    """What :func:`build_agent_input` needs to know about the Turn.

    Attributes:
        user_id: The owner. The key of every store call.
        session_id: The builder session.
        turn_id: The Turn id (the assistant message id).
        user_message_id: The user message this Turn answers.
        model_id: The chat model, whose context window sets the replay budget.
        tier: The caller's effective tier.
        content: The user's text.
        canvas_state: The Canvas state the message was sent with.
        intake_brief: The settled intake overlay, or ``None`` (always ``None``
            with the intake flag off).
    """

    user_id: str
    session_id: str
    turn_id: str
    user_message_id: str
    model_id: str
    tier: str
    content: str
    canvas_state: dict[str, Any] | None
    intake_brief: str | None = None


@dataclass(frozen=True, slots=True)
class AgentInput:
    """The input of one agent run.

    Attributes:
        message: The final human message, id ``turn:<turn_id>``.
        history: Replayed messages, alternating human and AI.
        summary_usage: Tokens of the summary calls made for this Turn, or ``None``
            when none was made.
    """

    message: HumanMessage
    history: list[BaseMessage]
    summary_usage: UsageCounts | None


# --- Usage helpers --------------------------------------------------------------------


def add_usage(left: UsageCounts | None, right: UsageCounts) -> UsageCounts:
    """Return ``left + right`` for every count (``left`` may be ``None``)."""
    if left is None:
        return right
    return UsageCounts(
        input=left.input + right.input,
        output=left.output + right.output,
        cache_read=left.cache_read + right.cache_read,
        cache_write=left.cache_write + right.cache_write,
    )


# --- Default summarizer ---------------------------------------------------------------


def _message_text(content: object) -> str:
    """Return the text of a model reply whose content is a string or blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


async def default_summarizer(model_id: str, text: str) -> SummaryResult:
    """Write one summary with ``build_model(model_id, effort=None)``."""
    system = await asyncio.to_thread(_PROMPT_FILE.read_text, encoding="utf-8")
    model = await asyncio.to_thread(build_model, model_id, effort=None)
    reply = await model.ainvoke([SystemMessage(content=system), HumanMessage(text)])
    record = usage_from_metadata(getattr(reply, "usage_metadata", None), model_id)
    return SummaryResult(
        text=_message_text(reply.content),
        usage=UsageCounts(
            input=record["input_tokens"],
            output=record["output_tokens"],
            cache_read=record["cache_read_tokens"],
            cache_write=record["cache_write_tokens"],
        ),
    )


# --- Stored facts ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Facts:
    """Plain values read from the store for one Turn."""

    mode: str
    has_accepted_draft: bool
    clarify_count: int
    exchanges: tuple[transcript.Exchange, ...]
    summary_text: str | None
    summary_through_seq: int | None
    latest_draft_hash: str | None
    unfinished_work: UnfinishedWork | None


def _latest_draft(revisions: LatestRevisions) -> WorkflowBuilderDraft | None:
    """Return the highest-numbered seed, accepted or undo revision."""
    drafts = [
        row
        for row in (revisions.seed, revisions.accepted, revisions.undo)
        if row is not None
    ]
    return max(drafts, key=lambda row: int(row.revision)) if drafts else None  # type: ignore[arg-type]


def _unfinished_work(
    store: InputStore, request: InputRequest, revisions: LatestRevisions
) -> UnfinishedWork | None:
    """Return the unproposed revision to continue from, if it is the newest."""
    rows = [
        row
        for row in (
            revisions.seed,
            revisions.accepted,
            revisions.undo,
            revisions.unproposed,
        )
        if row is not None
    ]
    unproposed = transcript.latest_unproposed(rows)
    if unproposed is None or unproposed.kind != DRAFT_KIND_UNPROPOSED:
        return None
    stop_status = _FALLBACK_STOP_STATUS
    source_turn_id = getattr(unproposed, "source_turn_id", None)
    if source_turn_id:
        turn_row = store.get_message(request.user_id, str(source_turn_id))
        if turn_row is not None:
            stop_status = str(turn_row.status)
    return UnfinishedWork(
        source_file=str(getattr(unproposed, "source_file", None) or ""),
        revision=int(unproposed.revision),
        stop_reason=stop_status,
    )


def _load_facts(scope: InputStoreScope, request: InputRequest) -> _Facts:
    """Read everything the input needs. Blocking; runs in a worker thread."""
    with scope() as store:
        session = store.get_session(request.user_id, request.session_id)
        if session is None:
            raise LookupError("builder session not found")
        rows = store.list_messages(request.user_id, request.session_id)
        summary = store.get_summary(request.user_id, request.session_id)
        revisions = store.get_latest_revisions(request.user_id, request.session_id)
        latest = _latest_draft(revisions)
        return _Facts(
            mode=str(session.mode),
            has_accepted_draft=session.first_accepted_revision is not None,
            clarify_count=int(session.clarify_turns_without_draft),  # type: ignore[arg-type]
            exchanges=tuple(transcript.build_exchanges(rows, request.user_message_id)),
            summary_text=summary.text if summary is not None else None,
            summary_through_seq=summary.through_seq if summary is not None else None,
            latest_draft_hash=str(latest.manifest_hash) if latest is not None else None,
            unfinished_work=_unfinished_work(store, request, revisions),
        )


# --- Summary --------------------------------------------------------------------------


async def _write_summary(
    summarizer: Summarizer, model_id: str, input_text: str
) -> tuple[str | None, UsageCounts | None]:
    """Call the summarizer, with one retry when headings are missing.

    Returns the accepted text (or ``None``) and the tokens of every call made.
    """
    usage: UsageCounts | None = None
    for attempt in range(1, _SUMMARY_ATTEMPTS + 1):
        try:
            result = await summarizer(model_id, input_text)
        except Exception:  # noqa: BLE001 - a failed summary must not fail the Turn
            logger.warning(
                "builder summary call failed (attempt %d)", attempt, exc_info=True
            )
            continue
        usage = add_usage(usage, result.usage)
        if transcript.has_required_headings(result.text):
            return result.text.strip(), usage
        logger.warning("builder summary lacks required headings (attempt %d)", attempt)
    return None, usage


def _replay_budget(model_id: str) -> int:
    """Return the replay budget in tokens: a fraction of the model's window."""
    window = next(
        (e.context_window for e in ModelCatalog().list() if e.id == model_id),
        _DEFAULT_CONTEXT_WINDOW,
    )
    return math.floor(settings.BUILDER_REPLAY_BUDGET_FRACTION * window)


# --- Entry point ----------------------------------------------------------------------


def _step_count(canvas_state: dict[str, Any] | None) -> int:
    steps = canvas_state.get("steps") if canvas_state else None
    return len(steps) if isinstance(steps, list) else 0


async def build_agent_input(
    request: InputRequest,
    *,
    store_scope: InputStoreScope,
    summarizer: Summarizer = default_summarizer,
) -> AgentInput:
    """Build the replay history and the final human message of a Turn.

    Args:
        request: The Turn's identity and the user's message.
        store_scope: Opens a store for one blocking call.
        summarizer: Writes a Transcript_Summary. Injected for tests.

    Returns:
        The input. ``summary_usage`` is set only when a summary call was made.

    Raises:
        LookupError: The session no longer exists.
    """
    facts = await asyncio.to_thread(_load_facts, store_scope, request)
    summary_tokens = (
        transcript.text_tokens(facts.summary_text) if facts.summary_text else 0
    )
    selection = transcript.select(
        facts.exchanges,
        _replay_budget(request.model_id),
        max(1, settings.BUILDER_REPLAY_VERBATIM_TURNS),
        summary_tokens,
    )
    summary_text = facts.summary_text
    summary_usage: UsageCounts | None = None
    if transcript.summary_needed(selection.omitted, facts.summary_through_seq):
        through = transcript.omitted_through_seq(selection.omitted)
        written, summary_usage = await _write_summary(
            summarizer,
            request.model_id,
            transcript.summary_input(
                facts.summary_text, facts.summary_through_seq, selection.omitted
            ),
        )
        if written is not None and through is not None:
            await asyncio.to_thread(
                _store_summary, store_scope, request, written, through
            )
            summary_text = written
    history = transcript.history_messages(selection, summary_text)
    step_models = builder_models(request.tier).step
    cost_classes = TIER_MODEL_COST_CLASSES.get(
        request.tier, TIER_MODEL_COST_CLASSES["basic"]
    )
    context = render(
        TurnContextInputs(
            user_message=request.content,
            mode="edit" if facts.mode == "edit" else "create",
            step_count=_step_count(request.canvas_state),
            canvas_hash=(
                canonical_hash(request.canvas_state)
                if request.canvas_state is not None
                else None
            ),
            latest_draft_hash=facts.latest_draft_hash,
            unfinished_work=facts.unfinished_work,
            may_use_db=_saved_row_trust(request.tier) == "db",
            premium_allowed="premium" in cost_classes,
            step_models=step_models,
            has_accepted_draft=facts.has_accepted_draft,
            clarify_count=facts.clarify_count,
            intake_brief=request.intake_brief,
        )
    )
    return AgentInput(
        message=HumanMessage(content=context, id=pinned_message_id(request.turn_id)),
        history=history,
        summary_usage=summary_usage,
    )


def _store_summary(
    scope: InputStoreScope, request: InputRequest, text: str, through_seq: int
) -> None:
    """Store the summary. Blocking; runs in a worker thread."""
    with scope() as store:
        store.set_summary(
            request.user_id, request.session_id, text=text, through_seq=through_seq
        )
