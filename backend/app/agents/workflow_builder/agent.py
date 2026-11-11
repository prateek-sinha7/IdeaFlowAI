"""The Builder_Agent factory (design section 3.6.4).

:func:`build_builder_runner` assembles one :class:`DeepAgentRunner` for one
Builder turn. The runner is stateless between turns (no checkpointer, no
interrupts): the transcript is replayed through ``astream_events(history=...)``
and the turn's own message is pinned by id.

What the factory wires:

* The versioned system prompt, read once at import (:data:`SYSTEM_PROMPT`,
  :data:`SYSTEM_PROMPT_SHA256`, :data:`PROMPT_VERSION`). A new prompt version is
  a new file and a change to :data:`_PROMPT_VERSION_LABEL` (Req 19.1).
* The tools: ``run_skill_script``, ``propose_draft`` and the read tools. The
  built-in file tools and ``write_todos`` stay bound by deepagents.
* The composite file backend: the session sandbox as the default route and the
  skill folders read-only under ``/skills/`` (Req 20.6 to 20.8).
* ``skills_sources=["/skills/"]``. With skill sources set, ``DeepAgentRunner``
  excludes the ``task`` and ``execute`` tools (Req 27.9) and keeps the file tools.
* ``checkpointer=None`` and ``interrupt_on=None``, and ``thread_id`` as a trace id
  only (Req 20.3).
* ``extra_middleware``: :class:`PinnedTurnMessageMiddleware` and then
  :class:`BuilderToolObserverMiddleware`.

The caller streams the turn with ``runner.astream_events(inputs.message,
history=...)``. ``inputs.message`` must be the very object the pinning
middleware holds, and its id must be ``turn:<turn_id>``, so that the message in
the graph state and the pinned message are the same (decision 13.2).

The agent layer reaches the platform only through the ports in
:class:`BuilderPorts`. This module imports neither the ExecutionEngine nor
``app.api``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from app.agents.deep_agent_runner import DeepAgentRunner
from app.agents.workflow_builder.backend_fs import SKILLS_ROUTE, build_builder_backend
from app.agents.workflow_builder.draft_tool import DraftToolContext, build_draft_tool
from app.agents.workflow_builder.middleware import (
    BuilderToolObserverMiddleware,
    PinnedTurnMessageMiddleware,
)
from app.agents.workflow_builder.read_tools import build_read_tools
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import (
    MetricSink,
    ResultCallback,
    Roots,
    ScriptContext,
    build_script_tool,
)
from app.agents.workflow_builder.skill_package import SKILLS_ROOT

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import HumanMessage
    from langchain_core.tools import BaseTool

    from app.agents.workflow_builder.ports import GatePort, TurnPort
    from app.agents.workflow_builder.read_tools import BuilderReadPort
    from app.agents.workflow_builder.sandbox import BuilderSandbox

__all__ = [
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_SHA256",
    "BuilderPorts",
    "BuilderTurnInputs",
    "build_builder_runner",
]

_PROMPT_VERSION_LABEL: Final = "v1"
_PROMPT_FILE: Final = (
    Path(__file__).resolve().parent
    / "prompts"
    / f"system_prompt.{_PROMPT_VERSION_LABEL}.md"
)
_PROMPT_HASH_CHARS: Final = 12


def _load_system_prompt(path: Path) -> str:
    """Read the prompt file as UTF-8 with LF line endings."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


SYSTEM_PROMPT: Final = _load_system_prompt(_PROMPT_FILE)
"""The system prompt text, read once at import (Req 19.1)."""

SYSTEM_PROMPT_SHA256: Final = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()
"""SHA-256 of :data:`SYSTEM_PROMPT` (UTF-8, LF line endings), as lowercase hex."""

PROMPT_VERSION: Final = (
    f"{_PROMPT_VERSION_LABEL}:{SYSTEM_PROMPT_SHA256[:_PROMPT_HASH_CHARS]}"
)
"""Stored on each assistant message: ``v1:<first 12 hex of the hash>``."""


@dataclass(frozen=True, slots=True)
class BuilderTurnInputs:
    """What the factory needs to know about one turn.

    Attributes:
        session_id: The builder session id. Names the trace thread.
        turn_id: The turn id (the assistant message id).
        user_id: The caller. The read tools are bound to it.
        tier: The caller's tier. The read tools are bound to it.
        model_id: The selected chat model id.
        effort: The selected effort, or ``None`` for a model without levels.
        message: The turn's final human message (Turn_Context plus the user's
            text). Its id must be ``turn:<turn_id>``. Pass this same object to
            ``runner.astream_events``.
        chat_model: A ready chat model used instead of building one from
            ``model_id``. A seam for tests; the turn runner leaves it ``None``.
    """

    session_id: str
    turn_id: str
    user_id: str
    tier: str
    model_id: str
    effort: str | None
    message: HumanMessage
    chat_model: BaseChatModel | None = None


@dataclass(frozen=True, slots=True)
class BuilderPorts:
    """The platform seams the agent layer works through.

    Attributes:
        turn: The live turn.
        gate: The Server_Gate.
        reads: The read-tool data source.
        elapsed_seconds: Seconds since the turn started, for the limit notice.
            ``None`` lets the observer start its own clock.
        on_script_metric: Telemetry sink for script calls.
        on_script_finished: Called with the call id and result of a script call.
        stopped_by_turn_cap: True when the turn stopped for its time or tool-call
            cap. ``None`` means never.
    """

    turn: TurnPort
    gate: GatePort
    reads: BuilderReadPort
    elapsed_seconds: Callable[[], float] | None = None
    on_script_metric: MetricSink | None = None
    on_script_finished: ResultCallback | None = None
    stopped_by_turn_cap: Callable[[], bool] | None = None


def _never() -> bool:
    return False


def build_builder_runner(
    turn_inputs: BuilderTurnInputs,
    sandbox: BuilderSandbox,
    ports: BuilderPorts,
    *,
    skills_root: Path | None = None,
) -> DeepAgentRunner:
    """Build the :class:`DeepAgentRunner` of one Builder turn.

    Args:
        turn_inputs: The turn's identity, model choice and pinned message.
        sandbox: The session sandbox. Call ``sandbox.ensure()`` first.
        ports: The gate, turn, read port and optional hooks.
        skills_root: The folder that holds the skill folder (test seam). ``None``
            uses ``workflow_builder/skills``.

    Returns:
        A runner with the builder tools, backend and middleware.

    Raises:
        ValueError: ``turn_inputs.message.id`` is not ``turn:<turn_id>``.
    """
    root = skills_root if skills_root is not None else SKILLS_ROOT
    skill_root = root / BUILDER_SKILL_ID
    turn = ports.turn

    backend = build_builder_backend(
        sandbox_root=sandbox.path,
        skills_root=root,
        skill_ids=(BUILDER_SKILL_ID,),
    )
    script_tool = build_script_tool(
        ScriptContext(
            sandbox=sandbox,
            skill_root=skill_root,
            gate=ports.gate,
            turn=turn,
            on_finished=ports.on_script_finished,
            on_metric=ports.on_script_metric,
            stopped_by_turn_cap=ports.stopped_by_turn_cap or _never,
        )
    )
    draft_tool = build_draft_tool(
        DraftToolContext(
            turn=turn,
            gate=ports.gate,
            roots=Roots(sandbox=sandbox.path, skill=skill_root),
        )
    )
    tools: list[BaseTool] = [
        script_tool,
        draft_tool,
        *build_read_tools(
            ports.reads, user_id=turn_inputs.user_id, tier=turn_inputs.tier
        ),
    ]

    # Order matters only in that both go after the runner's own middleware.
    # The pinning middleware raises ValueError for a wrongly numbered message.
    extra_middleware = [
        PinnedTurnMessageMiddleware(turn_inputs.turn_id, turn_inputs.message),
        BuilderToolObserverMiddleware(
            turn,
            elapsed_seconds=ports.elapsed_seconds,
            stopped_by_turn_cap=ports.stopped_by_turn_cap,
        ),
    ]

    return DeepAgentRunner(
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        model=(
            turn_inputs.chat_model
            if turn_inputs.chat_model is not None
            else turn_inputs.model_id
        ),
        effort=turn_inputs.effort,
        backend=backend,
        checkpointer=None,
        interrupt_on=None,
        thread_id=f"builder:{turn_inputs.session_id}",
        skills_sources=[SKILLS_ROUTE],
        extra_middleware=extra_middleware,
        recover_tool_failures=False,
        # Req 42.4: assistant text must not reach the logs.
        log_model_output=False,
        # Stream reasoning and reply text live. Without it the pinned
        # langchain-aws returns each Claude 5 call in one piece at the end.
        force_streaming=True,
    )
