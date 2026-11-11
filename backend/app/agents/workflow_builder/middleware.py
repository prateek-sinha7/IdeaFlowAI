"""Middleware for the Builder_Agent's deepagents graph.

Two ``AgentMiddleware`` classes, both appended through
``DeepAgentRunner(extra_middleware=...)`` (design section 3.6.5):

* :class:`BuilderToolObserverMiddleware` wraps every tool call. It counts the
  call against the tool-call cap, keeps writes inside ``/workflows/``, publishes
  the paired ``tool_started`` and ``tool_finished`` events, signals the stage,
  stores the tool row, remembers ``/workflows/*.workflow.json`` writes and gives
  the agent a one-time notice when the turn is near a limit.
* :class:`PinnedTurnMessageMiddleware` puts the turn's own message back into the
  model request when summarisation has dropped it.

Everything the middleware does to the live turn goes through
:class:`~app.agents.workflow_builder.ports.TurnPort`, so this module never
imports ``app.api``.

Events carry labels and summaries only (Req 38.16, 38.17): a summary comes from a
fixed template per tool and status, never from raw tool output, and the
``command`` field is set for script calls only.

Contract with the script tool (task 12.4): a ``run_skill_script`` result starts
with ``$ <command>`` and ``exit code: <n>``. ``exit code: timed out`` marks a
timeout. A result with no ``exit code:`` line is a policy refusal, unless the
ToolMessage status is ``error`` (a runner error).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import math
import posixpath
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

from app.agents.workflow_builder.adherence import ToolCall as AdherenceToolCall
from app.agents.workflow_builder.backend_fs import SKILL_READ_ONLY_MESSAGE
from app.agents.workflow_builder.events import (
    LimitKind,
    LimitWarning,
    ToolActivity,
    ToolFinished,
    ToolFinishStatus,
    ToolKind,
)
from app.agents.workflow_builder.events import ToolStarted as ToolStartedEvent
from app.agents.workflow_builder.ports import FinishedToolCall
from app.agents.workflow_builder.script_runner import STOPPED_NOTE
from app.agents.workflow_builder.stages import READ_TOOL_NAMES
from app.agents.workflow_builder.stages import ToolStarted as ToolStartedSignal

if TYPE_CHECKING:
    from langchain.agents.middleware.types import (
        ModelRequest,
        ModelResponse,
        ToolCallRequest,
    )
    from langchain_core.messages import BaseMessage

    from app.agents.workflow_builder.adherence import Verdict
    from app.agents.workflow_builder.ports import TurnPort

__all__ = [
    "MAX_SUMMARY_CHARS",
    "WRITE_SCOPE_MESSAGE",
    "BuilderToolObserverMiddleware",
    "PinnedTurnMessageMiddleware",
    "cap_summary",
    "is_under_workflows",
    "normalise_virtual_path",
]

logger = logging.getLogger("app.agents.workflow_builder.middleware")

MAX_SUMMARY_CHARS: Final = 280
"""Longest ``tool_finished.summary`` (design 4.3, G-19)."""

WRITE_SCOPE_MESSAGE: Final = "Write only under /workflows/."
"""Tool result for a write outside ``/workflows/`` (Req 27.3)."""

TOOL_LIMIT_MESSAGE: Final = (
    "The tool-call limit for this turn was reached. No more tools can run. "
    "Reply with what you have so far."
)

_WORKFLOWS_PREFIX: Final = "/workflows/"
_SKILLS_ROOT: Final = "/skills"
_MANIFEST_SUFFIX: Final = ".workflow.json"
_WRITE_TOOLS: Final = frozenset({"write_file", "edit_file"})
_SCRIPT_TOOL: Final = "run_skill_script"
_PROPOSE_TOOL: Final = "propose_draft"
_LOOKUP_SCRIPT: Final = "catalog_lookup.py"
_VALIDATOR_SCRIPT: Final = "validate_manifest.py"
_COMMAND_CAP: Final = 1000
_NOTICE_PREFIX: Final = "[builder]"

_EXIT_CODE_RE: Final = re.compile(r"^exit code:\s*(-?\d+)\s*$", re.IGNORECASE)
_TIMED_OUT_RE: Final = re.compile(r"^exit code:\s*timed[ _]out\s*$", re.IGNORECASE)
_VERDICT_RE: Final = re.compile(
    r"^(VALID|INVALID): (\d+) error\(s\), (\d+) warning\(s\)", re.IGNORECASE
)
_HEADER_LINES: Final = 3

# Fixed labels. A label never holds model-written text beyond a file name.
_READ_TOOL_LABELS: Final[dict[str, str]] = {
    "list_my_agents": "Looked up your agents",
    "list_my_skills": "Looked up your skills",
    "list_my_workflow_names": "Looked up your workflow names",
    "list_my_connectors": "Looked up your connectors",
    "list_handoff_targets": "Looked up the handoff targets",
    "get_builder_models": "Looked up the models",
}
_FILE_TOOL_LABELS: Final[dict[str, str]] = {
    "ls": "Listed files",
    "glob": "Searched for files",
    "grep": "Searched file contents",
    "write_todos": "Updated the plan",
}
_SCRIPT_LABELS: Final[dict[str, str]] = {
    _LOOKUP_SCRIPT: "Looked up the catalog",
    _VALIDATOR_SCRIPT: "Checked the workflow",
    "selftest.py": "Ran the skill self-test",
    "refresh_catalog.py": "Checked the catalog snapshot",
    "schema_sync.py": "Checked the schema copy",
    "export_manifest.py": "Exported the workflow",
}
_COMPILER_LABEL: Final = "Checked the workflow with the platform"
_UNKNOWN_SCRIPT_LABEL: Final = "Ran a skill script"
_PROPOSE_LABEL: Final = "Sent the workflow to the platform check"
_UNKNOWN_TOOL_LABEL: Final = "Ran a tool"


# --- Pure helpers ---------------------------------------------------------------------


def normalise_virtual_path(path: str) -> str:
    """Return ``path`` as a normalised absolute virtual path.

    Backslashes become slashes, ``.``, ``..`` and repeated slashes collapse, and
    a relative path is taken to start at ``/``, the way the file backend reads
    it. ``..`` cannot climb above ``/``.
    """
    # ``posixpath.normpath`` keeps exactly two leading slashes (POSIX rule), so
    # strip them all first: ``//workflows/a`` and ``/workflows/a`` are one path.
    slashed = "/" + path.replace("\\", "/").lstrip("/")
    return posixpath.normpath(slashed)


def is_under_workflows(path: str) -> bool:
    """True when ``path`` normalises to a location below ``/workflows/``."""
    return normalise_virtual_path(path).startswith(_WORKFLOWS_PREFIX)


def _is_under_skills(path: str) -> bool:
    """True when ``path`` normalises to ``/skills`` or a location below it."""
    normal = normalise_virtual_path(path)
    return normal == _SKILLS_ROOT or normal.startswith(_SKILLS_ROOT + "/")


def cap_summary(text: str) -> str:
    """Return ``text`` on one line, at most :data:`MAX_SUMMARY_CHARS` long."""
    flat = " ".join(text.split())
    if len(flat) <= MAX_SUMMARY_CHARS:
        return flat
    return flat[: MAX_SUMMARY_CHARS - 3].rstrip() + "..."


def _content_text(content: str | list[Any]) -> str:
    """Return the text of a ToolMessage ``content`` (text blocks only)."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _string_arg(args: dict[str, Any], *names: str) -> str | None:
    """Return the first non-empty string argument among ``names``."""
    for name in names:
        value = args.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _int_arg(args: dict[str, Any], name: str) -> int | None:
    """Return an integer argument, or ``None`` when absent or not an integer."""
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class _ScriptCall:
    """What the observer reads from a ``run_skill_script`` command line."""

    command: str
    script: str | None
    subcommand: str | None
    check: bool
    compiler: bool


def _parse_script_call(command: str) -> _ScriptCall:
    """Read the script name and flags from ``command`` for labels and stages.

    This is a light split on whitespace. The script runner parses the command
    for real; here a wrong guess only gives a generic label.
    """
    tokens = [token.strip("\"'") for token in command.split()]
    script: str | None = None
    subcommand: str | None = None
    for index, token in enumerate(tokens):
        slashed = token.replace("\\", "/")
        if slashed.lower().endswith(".py"):
            script = posixpath.basename(slashed)
            if script == _LOOKUP_SCRIPT and index + 1 < len(tokens):
                following = tokens[index + 1]
                if following and not following.startswith("-"):
                    subcommand = following
            break
    return _ScriptCall(
        command=command,
        script=script,
        subcommand=subcommand,
        check="--check" in tokens,
        compiler=any(
            token == "--compiler" or token.startswith("--compiler=") for token in tokens
        ),
    )


def _clean_command(command: str) -> str:
    """Collapse whitespace in ``command`` and cut it at :data:`_COMMAND_CAP`."""
    flat = " ".join(command.split())
    if len(flat) <= _COMMAND_CAP:
        return flat
    return flat[: _COMMAND_CAP - 3] + "..."


def _script_exit_code(text: str) -> int | None:
    """Return the exit code in a script result header, else ``None``."""
    for line in text.splitlines()[:_HEADER_LINES]:
        match = _EXIT_CODE_RE.match(line.strip())
        if match is not None:
            return int(match.group(1))
    return None


def _script_timed_out(text: str) -> bool:
    """True when the script result header says the call timed out."""
    return any(
        _TIMED_OUT_RE.match(line.strip()) for line in text.splitlines()[:_HEADER_LINES]
    )


def _script_stopped(text: str) -> bool:
    """True when the script result header says the turn stopped before the call ended."""
    return any(
        line.strip() == STOPPED_NOTE for line in text.splitlines()[:_HEADER_LINES]
    )


def _script_verdict(text: str) -> Verdict | None:
    """Return the validator verdict on the last non-empty output line, if any."""
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        match = _VERDICT_RE.match(stripped)
        if match is None:
            return None
        return "valid" if match.group(1).upper() == "VALID" else "invalid"
    return None


@dataclasses.dataclass(frozen=True, slots=True)
class _Described:
    """The kind, label and script details of one tool call."""

    kind: ToolKind
    label: str
    path: str | None = None
    script: _ScriptCall | None = None


def _base_name(path: str | None) -> str:
    """Return the file name of ``path``, or an empty string when there is none."""
    if not path:
        return ""
    return posixpath.basename(path.replace("\\", "/"))


def _describe(name: str, args: dict[str, Any]) -> _Described:
    """Return the kind and label of a tool call from the fixed table (Req 38.7)."""
    if name == "read_file":
        path = _string_arg(args, "file_path", "path")
        base = _base_name(path)
        return _Described("read", f"Read {base}" if base else "Read a file", path=path)
    if name in _WRITE_TOOLS:
        path = _string_arg(args, "file_path", "path")
        verb = "Wrote" if name == "write_file" else "Edited"
        base = _base_name(path)
        return _Described(
            "write", f"{verb} {base}" if base else f"{verb} a file", path=path
        )
    if name == _SCRIPT_TOOL:
        command = _string_arg(args, "command") or ""
        call = _parse_script_call(command)
        if call.script == _VALIDATOR_SCRIPT and call.compiler:
            label = _COMPILER_LABEL
        else:
            label = _SCRIPT_LABELS.get(call.script or "", _UNKNOWN_SCRIPT_LABEL)
        kind: ToolKind = "lookup" if call.script == _LOOKUP_SCRIPT else "script"
        return _Described(kind, label, script=call)
    if name == _PROPOSE_TOOL:
        return _Described("propose", _PROPOSE_LABEL)
    if name in READ_TOOL_NAMES:
        return _Described("lookup", _READ_TOOL_LABELS.get(name, "Looked up your data"))
    if name in _FILE_TOOL_LABELS:
        return _Described("read", _FILE_TOOL_LABELS[name])
    return _Described("read", _UNKNOWN_TOOL_LABEL)


def _summary_for(
    described: _Described,
    status: ToolFinishStatus,
    *,
    exit_code: int | None,
    reason: str | None,
) -> str:
    """Build the fixed-template ``tool_finished`` summary (G-19, at most 280 chars)."""
    label = described.label
    if status == "ok":
        if exit_code is not None:
            return cap_summary(f"{label}. Exit code {exit_code}.")
        return cap_summary(f"{label}.")
    if status == "refused":
        return cap_summary(
            f"{label} was refused. {reason}" if reason else f"{label} was refused."
        )
    if status == "stopped":
        return cap_summary(f"{label} was stopped.")
    if status == "timed_out":
        return cap_summary(f"{label} timed out.")
    if exit_code is not None:
        return cap_summary(f"{label} failed. Exit code {exit_code}.")
    return cap_summary(f"{label} failed.")


def _message_of(result: ToolMessage | Command[Any]) -> ToolMessage | None:
    """Return the ToolMessage inside a handler result, or ``None``."""
    if isinstance(result, ToolMessage):
        return result
    update = getattr(result, "update", None)
    if isinstance(update, dict):
        messages = update.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, ToolMessage):
                    return message
    return None


def _with_notice(
    result: ToolMessage | Command[Any], notice: str
) -> ToolMessage | Command[Any]:
    """Return ``result`` with ``notice`` appended to its ToolMessage content."""
    message = _message_of(result)
    if message is None:
        return result
    content = message.content
    new_content: str | list[str | dict[str, Any]]
    if isinstance(content, str):
        new_content = f"{content}\n\n{notice}" if content else notice
    else:
        new_content = [*content, {"type": "text", "text": f"\n\n{notice}"}]
    updated = message.model_copy(update={"content": new_content})
    if isinstance(result, ToolMessage):
        return updated
    update = dict(result.update) if isinstance(result.update, dict) else {}
    messages = [updated if m is message else m for m in update.get("messages", [])]
    update["messages"] = messages
    return dataclasses.replace(result, update=update)


# --- Tool observer --------------------------------------------------------------------


class BuilderToolObserverMiddleware(AgentMiddleware[Any, Any, Any]):
    """Observe, scope and bound every tool call of one Builder turn.

    Create one instance per turn; it keeps the once-only flags for the turn.

    Args:
        turn: The live turn. All events, counts and rows go through it.
        elapsed_seconds: Returns the seconds since the turn started. Defaults to
            a monotonic clock started when the middleware is created.
        stopped_by_turn_cap: True when the turn stopped for its time or
            tool-call cap. A call cancelled then finishes as ``timed_out``;
            any other cancel finishes as ``error`` (design 3.4.6). ``None``
            means never.
    """

    def __init__(
        self,
        turn: TurnPort,
        *,
        elapsed_seconds: Callable[[], float] | None = None,
        stopped_by_turn_cap: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self._turn = turn
        self._stopped_by_turn_cap = stopped_by_turn_cap or (lambda: False)
        if elapsed_seconds is None:
            started = time.monotonic()

            def elapsed_seconds() -> float:
                return time.monotonic() - started

        self._elapsed_seconds = elapsed_seconds
        self._call_count = 0
        self._warned_tool_calls = False
        self._noticed: set[LimitKind] = set()

    # -- AgentMiddleware hook -----------------------------------------------------

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Run one tool call under the builder's rules (design 3.6.5, steps 1 to 7)."""
        call = request.tool_call
        name = str(call.get("name") or "")
        raw_args = call.get("args")
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        count = self._turn.count_tool_call()
        self._call_count = count
        call_id = str(call.get("id") or f"call-{count}")
        described = _describe(name, args)
        started = time.monotonic()

        limit = self._turn.limits.max_tool_calls
        refusal: str | None = None
        if count > limit:
            refusal = TOOL_LIMIT_MESSAGE
            self._turn.stop("tool_calls")
        else:
            await self._warn_tool_calls(count, limit)
            refusal = self._write_scope_refusal(name, described.path)

        await self._emit_started(call_id, name, described)
        if refusal is not None:
            message = ToolMessage(
                content=refusal, name=name or None, tool_call_id=call_id, status="error"
            )
            await self._finish(
                call_id,
                name,
                args,
                described,
                started,
                message,
                status="refused",
                reason=refusal,
            )
            return self._add_limit_notice(message)

        await self._turn.signal_stage(self._signal_for(name, described))
        try:
            result = await handler(request)
        except asyncio.CancelledError:
            cancel_status: ToolFinishStatus = (
                "timed_out" if self._stopped_by_turn_cap() else "stopped"
            )
            await self._finish_unreturned(
                call_id, name, args, described, started, status=cancel_status
            )
            raise
        except Exception:
            await self._finish_unreturned(call_id, name, args, described, started)
            raise

        message = _message_of(result)
        status = self._status_of(name, described, message)
        if status == "stopped" and self._stopped_by_turn_cap():
            status = "timed_out"  # same rule as a cancelled call
        await self._finish(
            call_id, name, args, described, started, message, status=status, reason=None
        )
        return self._add_limit_notice(result)

    # -- Steps --------------------------------------------------------------------

    async def _warn_tool_calls(self, count: int, limit: int) -> None:
        """Publish ``limit_warning`` once, when the call count reaches 80 %."""
        if self._warned_tool_calls or limit <= 0:
            return
        if count < self._warning_point(limit):
            return
        self._warned_tool_calls = True
        await self._publish(
            LimitWarning(
                ts=_now(),
                turn_id=self._turn.turn_id,
                seq=1,
                kind="tool_calls",
                used=count,
                limit=limit,
            )
        )

    def _warning_point(self, limit: int) -> int:
        """Return the first count at or above the warning fraction of ``limit``."""
        fraction = self._turn.limits.warning_fraction
        return max(1, math.ceil(round(limit * fraction, 6)))

    @staticmethod
    def _write_scope_refusal(name: str, path: str | None) -> str | None:
        """Return the refusal text for a write outside ``/workflows/``, else ``None``."""
        if name not in _WRITE_TOOLS:
            return None
        if path is None:
            return WRITE_SCOPE_MESSAGE
        if _is_under_skills(path):
            return SKILL_READ_ONLY_MESSAGE
        if not is_under_workflows(path):
            return WRITE_SCOPE_MESSAGE
        return None

    async def _emit_started(
        self, call_id: str, name: str, described: _Described
    ) -> None:
        """Publish ``tool_started``."""
        command = (
            _clean_command(described.script.command)
            if described.script is not None
            else None
        )
        await self._publish(
            ToolStartedEvent(
                ts=_now(),
                turn_id=self._turn.turn_id,
                seq=1,
                call_id=call_id,
                tool=name,
                kind=described.kind,
                label=described.label,
                command=command,
            )
        )

    @staticmethod
    def _signal_for(name: str, described: _Described) -> ToolStartedSignal:
        """Build the stage signal for a tool start (Req 39)."""
        script = described.script
        return ToolStartedSignal(
            name=name,
            path=described.path,
            script=script.script if script is not None else None,
            subcommand=script.subcommand if script is not None else None,
            check=script.check if script is not None else False,
        )

    @staticmethod
    def _status_of(
        name: str, described: _Described, message: ToolMessage | None
    ) -> ToolFinishStatus:
        """Map a finished call to a ``tool_finished`` status (design 3.4.6)."""
        if message is not None and message.status == "error":
            return "error"
        if name != _SCRIPT_TOOL:
            return "ok"
        text = _content_text(message.content) if message is not None else ""
        if _script_timed_out(text):
            return "timed_out"
        if _script_stopped(text):
            return "stopped"
        exit_code = _script_exit_code(text)
        if exit_code is None:
            return "refused"
        script = described.script.script if described.script is not None else None
        if exit_code == 0 or (exit_code == 1 and script == _VALIDATOR_SCRIPT):
            return "ok"
        return "error"

    async def _finish(  # noqa: PLR0913 - one call site per outcome, all values needed
        self,
        call_id: str,
        name: str,
        args: dict[str, Any],
        described: _Described,
        started: float,
        message: ToolMessage | None,
        *,
        status: ToolFinishStatus,
        reason: str | None,
    ) -> None:
        """Publish ``tool_finished``, store the tool row and record a workflow write."""
        text = _content_text(message.content) if message is not None else ""
        exit_code = _script_exit_code(text) if name == _SCRIPT_TOOL else None
        duration_ms = max(0, int((time.monotonic() - started) * 1000))
        summary = _summary_for(described, status, exit_code=exit_code, reason=reason)
        await self._publish(
            ToolFinished(
                ts=_now(),
                turn_id=self._turn.turn_id,
                seq=1,
                call_id=call_id,
                status=status,
                duration_ms=duration_ms,
                summary=summary,
            )
        )
        if status == "ok" and name in _WRITE_TOOLS and described.path is not None:
            normal = normalise_virtual_path(described.path)
            if normal.startswith(_WORKFLOWS_PREFIX) and normal.endswith(
                _MANIFEST_SUFFIX
            ):
                self._turn.record_workflow_write(normal)
        activity = ToolActivity(
            call_id=call_id,
            tool=name,
            kind=described.kind,
            label=described.label,
            status=status,
            duration_ms=duration_ms,
            command=(
                _clean_command(described.script.command)
                if described.script is not None
                else None
            ),
            exit_code=exit_code,
            summary=summary,
        )
        adherence_call = self._adherence_call(
            name, args, described, status=status, exit_code=exit_code, text=text
        )
        try:
            await self._turn.record_tool_call(
                FinishedToolCall(activity=activity, call=adherence_call, result=text)
            )
        except Exception:  # noqa: BLE001 - a failed row write must not break the agent
            logger.warning(
                "could not store tool row for call %s", call_id, exc_info=True
            )

    async def _finish_unreturned(
        self,
        call_id: str,
        name: str,
        args: dict[str, Any],
        described: _Described,
        started: float,
        *,
        status: ToolFinishStatus = "error",
    ) -> None:
        """Pair ``tool_started`` when the handler raised or was cancelled (Req 38.9)."""
        try:
            await self._finish(
                call_id,
                name,
                args,
                described,
                started,
                None,
                status=status,
                reason=None,
            )
        except Exception:  # noqa: BLE001 - never hide the original failure
            logger.warning("could not close tool call %s", call_id, exc_info=True)

    @staticmethod
    def _adherence_call(
        name: str,
        args: dict[str, Any],
        described: _Described,
        *,
        status: ToolFinishStatus,
        exit_code: int | None,
        text: str,
    ) -> AdherenceToolCall:
        """Build the adherence record's view of one finished call (decision 10.1)."""
        ok = status == "ok"
        if name == "read_file":
            return AdherenceToolCall(
                name=name,
                ok=ok,
                path=described.path,
                offset=_int_arg(args, "offset"),
                limit=_int_arg(args, "limit"),
            )
        if name in _WRITE_TOOLS:
            return AdherenceToolCall(name=name, ok=ok, path=described.path)
        if name == _SCRIPT_TOOL:
            script = described.script
            verdict = (
                _script_verdict(text)
                if script is not None and script.script == _VALIDATOR_SCRIPT
                else None
            )
            return AdherenceToolCall(
                name=name,
                ok=ok,
                script=script.script if script is not None else None,
                subcommand=script.subcommand if script is not None else None,
                exit_code=exit_code,
                verdict=verdict,
            )
        return AdherenceToolCall(name=name, ok=ok)

    def _add_limit_notice(
        self, result: ToolMessage | Command[Any]
    ) -> ToolMessage | Command[Any]:
        """Append the one-time limit notice when a limit is past its warning point (Req 28.9)."""
        limits = self._turn.limits
        due: set[LimitKind] = set()
        tool_calls_left = max(0, limits.max_tool_calls - self._call_count)
        if (
            "tool_calls" not in self._noticed
            and limits.max_tool_calls > 0
            and self._call_count >= self._warning_point(limits.max_tool_calls)
        ):
            due.add("tool_calls")
        elapsed = self._elapsed_seconds()
        seconds_left = max(0.0, limits.timeout_seconds - elapsed)
        if (
            "time" not in self._noticed
            and limits.timeout_seconds > 0
            and elapsed >= limits.timeout_seconds * limits.warning_fraction
        ):
            due.add("time")
        if not due:
            return result
        self._noticed |= due
        minutes_left = math.ceil(seconds_left / 60)
        notice = (
            f"{_NOTICE_PREFIX} About {minutes_left} "
            f"{'minute' if minutes_left == 1 else 'minutes'} and {tool_calls_left} "
            f"tool {'call is' if tool_calls_left == 1 else 'calls are'} left in this turn. "
            "Finish checking and call propose_draft."
        )
        return _with_notice(result, notice)

    async def _publish(self, event: Any) -> None:
        """Publish ``event``; a failed publish is logged and does not stop the tool."""
        try:
            await self._turn.publish(event)
        except Exception:  # noqa: BLE001 - the stream is best effort for the agent
            logger.warning(
                "could not publish %s", getattr(event, "type", "event"), exc_info=True
            )


def _now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


# --- Pinned turn message --------------------------------------------------------------


def _is_summary_message(message: BaseMessage) -> bool:
    """True for the HumanMessage that summarisation leaves at the start."""
    return (
        isinstance(message, HumanMessage)
        and message.additional_kwargs.get("lc_source") == "summarization"
    )


class PinnedTurnMessageMiddleware(AgentMiddleware[Any, Any, Any]):
    """Keep the turn's own message in every model request.

    The turn's final human message is created with ``id = "turn:<turn_id>"``. If
    summarisation removed it from ``request.messages``, the original message is
    put back right after any leading summary message. Only the request changes;
    the stored state is untouched, so this applies to every later model call of
    the turn (design 3.6.5, Req 28.3).

    Args:
        turn_id: The turn id.
        message: The message to keep. Its ``id`` must be ``turn:<turn_id>``.

    Raises:
        ValueError: ``message.id`` is not ``turn:<turn_id>``.
    """

    def __init__(self, turn_id: str, message: BaseMessage) -> None:
        super().__init__()
        pinned_id = f"turn:{turn_id}"
        if message.id != pinned_id:
            raise ValueError(f"the pinned message must have id {pinned_id!r}")
        self._pinned_id = pinned_id
        self._message = message

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> Any:
        """Call the model with the pinned message present in ``request.messages``."""
        return await handler(self._pinned(request))

    def _pinned(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        """Return ``request``, or a copy with the pinned message re-inserted."""
        messages = list(request.messages)
        if any(message.id == self._pinned_id for message in messages):
            return request
        index = 0
        while index < len(messages) and _is_summary_message(messages[index]):
            index += 1
        messages.insert(index, self._message)
        return request.override(messages=messages)
