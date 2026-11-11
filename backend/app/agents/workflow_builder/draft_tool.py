"""The ``propose_draft`` tool of the workflow builder (design section 3.5.2).

``propose_draft`` hands a manifest file under ``/workflows/`` to the Canvas. The
server checks it the way Save does (through :class:`GatePort`), and an accepted
draft is stored as a revision and sent to the client in ``draft_applied``.

Order of work, one step per ``# Step`` comment in :func:`build_draft_tool`:

1. A stopping turn applies nothing (Req 30.4).
2. A second draft in one turn is refused (Req 7.1).
3. A path outside ``/workflows/*.workflow.json``, a missing file, invalid JSON
   or a non-object is a tool-use mistake and is refused. None of these counts
   as a gate rejection.
4. The stage moves to ``platform_check`` and the Server_Gate checks the draft.
5. A rejection is counted and reported with its attempt number and the attempts
   left. The issues come back as a numbered list. The second rejection stops
   the turn with ``gate_rejections`` (Req 23.10 to 23.12).
6. An acceptance re-checks ``stopping`` (the gate may have run in a thread),
   computes the change summary against the turn's ``canvas_state`` and the
   launch needs, stores the revision, then emits ``check_result`` (valid), the
   ``applying`` stage and ``draft_applied`` (Req 23.13, 23.14, 23.17).

Tool results hold fixed text and the gate's issue messages. They never repeat
the user's prompt. The agent layer reaches the platform only through
:class:`~app.agents.workflow_builder.ports.GatePort` and
:class:`~app.agents.workflow_builder.ports.TurnPort`, so this module imports
nothing from ``app.api``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

from langchain_core.tools import BaseTool, tool

from app.agents.workflow_builder.change_summary import summarize
from app.agents.workflow_builder.events import CheckResultEvent, DraftApplied
from app.agents.workflow_builder.launch_needs import derive
from app.agents.workflow_builder.ports import (
    AcceptedDraft,
    GateIssue,
    GatePort,
    TurnPort,
)
from app.agents.workflow_builder.script_policy import PathSlotKind
from app.agents.workflow_builder.script_runner import Refusal, Roots, map_path
from app.agents.workflow_builder.stages import GateAccepted, ToolStarted

__all__ = [
    "ALREADY_APPLIED_MESSAGE",
    "MAX_MANIFEST_BYTES",
    "STOPPING_MESSAGE",
    "DraftToolContext",
    "build_draft_tool",
]

_logger = logging.getLogger(__name__)

TOOL_NAME: Final = "propose_draft"
WORKFLOWS_DIR: Final = "workflows"
MANIFEST_SUFFIX: Final = ".workflow.json"
# A manifest this large is a mistake, not a workflow. The cap keeps one call
# from reading an unbounded file into memory.
MAX_MANIFEST_BYTES: Final = 1_000_000

STOPPING_MESSAGE: Final = "This turn is stopping. Nothing was applied."
ALREADY_APPLIED_MESSAGE: Final = (
    "This turn already updated the canvas. Make further changes in the next message."
)
_BAD_PATH_MESSAGE: Final = (
    "The draft must be a file directly under /workflows/ whose name ends in "
    f"{MANIFEST_SUFFIX}, for example /workflows/my{MANIFEST_SUFFIX}. "
    "Nothing was checked."
)
_MISSING_FILE_MESSAGE: Final = (
    "There is no file at that path. Write the manifest with write_file first. "
    "Nothing was checked."
)
_TOO_LARGE_MESSAGE: Final = (
    f"The manifest is larger than {MAX_MANIFEST_BYTES} bytes. "
    "Shorten it and propose it again. Nothing was checked."
)
_NOT_OBJECT_MESSAGE: Final = (
    "The file must hold one JSON object (the workflow manifest), not a list or "
    "a single value. Nothing was checked."
)
_UNREADABLE_MESSAGE: Final = "The file could not be read. Nothing was checked."


@dataclass(frozen=True, slots=True)
class DraftToolContext:
    """What ``propose_draft`` needs for one turn.

    Attributes:
        turn: The live turn, for stopping, counting, events and storing.
        gate: The Server_Gate adapter.
        roots: The session's sandbox and the deployed skill folder, used to
            map the ``path`` argument.
    """

    turn: TurnPort
    gate: GatePort
    roots: Roots


@dataclass(frozen=True, slots=True)
class _Loaded:
    """A manifest read from the sandbox, or the reason it cannot be used."""

    manifest: dict[str, Any] | None
    source_file: str
    error: str | None


def build_draft_tool(ctx: DraftToolContext) -> BaseTool:
    """Build the ``propose_draft`` tool for one turn.

    Args:
        ctx: The turn, gate and roots the tool works with.

    Returns:
        A LangChain tool named ``propose_draft``.
    """

    @tool(TOOL_NAME)
    async def propose_draft(
        path: str,
        target_trust: Literal["user", "db"] = "user",
        trust_reason: str | None = None,
    ) -> str:
        """Hand the manifest at `path` (a file under /workflows/) to the canvas.

        The server checks it the way Save does. Use target_trust='db' only when
        a stated requirement needs a db-only feature, and give that requirement
        in trust_reason.
        """
        turn = ctx.turn

        # Step 1: a stopping turn applies nothing.
        if turn.stopping:
            return STOPPING_MESSAGE

        # Step 2: at most one accepted draft per turn.
        if turn.accepted_revision is not None:
            return ALREADY_APPLIED_MESSAGE

        # Step 3: tool-use mistakes. None of them counts as a rejection.
        loaded = await asyncio.to_thread(_load_manifest, ctx.roots, path)
        if loaded.manifest is None:
            return loaded.error or _UNREADABLE_MESSAGE
        manifest = loaded.manifest

        # Step 4: platform check.
        await turn.signal_stage(ToolStarted(name=TOOL_NAME, path=loaded.source_file))
        if target_trust == "db":
            _logger.info(
                "propose_draft requested db trust, reason_given=%s", bool(trust_reason)
            )
        result = await ctx.gate.check(manifest, requested_trust=target_trust)

        # Step 5: rejection.
        if not result.accepted or result.trust is None:
            return await _reject(ctx, result.issues)

        # Step 6: acceptance.
        if turn.stopping:
            return STOPPING_MESSAGE
        summary = summarize(turn.canvas_state or {}, manifest)
        needs = derive(manifest)
        revision = await turn.accept_draft(
            AcceptedDraft(
                manifest=manifest,
                trust=result.trust,
                source_file=loaded.source_file,
                change_summary=summary,
                launch_needs=tuple(needs),
            )
        )
        await turn.publish(
            CheckResultEvent(
                ts=_now(),
                turn_id=turn.turn_id,
                seq=1,
                source="server_gate",
                verdict="valid",
                errors=0,
                warnings=0,
                attempt=None,
                attempts_left=None,
            )
        )
        await turn.signal_stage(GateAccepted())
        await turn.publish(
            DraftApplied(
                ts=_now(),
                turn_id=turn.turn_id,
                seq=1,
                revision=revision,
                target_trust=result.trust,
                change_summary=summary,
                launch_needs=needs,
                manifest=manifest,
            )
        )
        return f"Applied as revision {revision}. The canvas now shows it."

    return propose_draft


async def _reject(ctx: DraftToolContext, issues: tuple[GateIssue, ...]) -> str:
    """Count a rejection, announce it and build the tool result."""
    turn = ctx.turn
    attempt = turn.report_gate_rejection()
    limit = turn.limits.max_gate_rejections
    attempts_left = max(0, limit - attempt)
    await turn.publish(
        CheckResultEvent(
            ts=_now(),
            turn_id=turn.turn_id,
            seq=1,
            source="server_gate",
            verdict="invalid",
            errors=len(issues),
            warnings=0,
            attempt=attempt,
            attempts_left=attempts_left,
        )
    )
    if attempts_left == 0:
        turn.stop("gate_rejections")
    return _rejection_text(issues, attempt, attempts_left)


def _rejection_text(
    issues: tuple[GateIssue, ...], attempt: int, attempts_left: int
) -> str:
    """Render the numbered issue list the model reads."""
    header = f"The server rejected the draft (attempt {attempt}). Nothing was applied."
    if attempts_left > 0:
        header += f" You have {attempts_left} attempt(s) left. Fix every issue below, then propose again."
    else:
        header += " No attempts are left. Stop and tell the user what is blocking the workflow."
    lines = [
        f"{number}. {_describe(issue)}" for number, issue in enumerate(issues, start=1)
    ]
    return "\n".join([header, *lines])


def _describe(issue: GateIssue) -> str:
    """One issue as ``[rule] path: message``; the path is left out when empty."""
    where = f" {issue.path}:" if issue.path else ""
    return f"[{issue.rule}]{where} {issue.message}"


def _load_manifest(roots: Roots, raw_path: str) -> _Loaded:
    """Map ``raw_path`` to a manifest file and parse it. Blocking; run in a thread."""
    mapped = map_path(raw_path, PathSlotKind.SANDBOX_READ, roots)
    if isinstance(mapped, Refusal) or not _is_workflow_file(mapped, roots):
        return _Loaded(None, "", _BAD_PATH_MESSAGE)
    source_file = f"/{WORKFLOWS_DIR}/{mapped.name}"
    try:
        if not mapped.is_file():
            return _Loaded(None, source_file, _MISSING_FILE_MESSAGE)
        if mapped.stat().st_size > MAX_MANIFEST_BYTES:
            return _Loaded(None, source_file, _TOO_LARGE_MESSAGE)
        data = mapped.read_bytes()
    except OSError:
        return _Loaded(None, source_file, _UNREADABLE_MESSAGE)
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as exc:
        # ``exc.msg`` is the parser's own wording; it never holds file text.
        message = (
            f"The file is not valid JSON: {exc.msg} at line {exc.lineno}, "
            f"column {exc.colno}. Nothing was checked."
        )
        return _Loaded(None, source_file, message)
    except ValueError:
        return _Loaded(
            None, source_file, "The file is not valid UTF-8 JSON. Nothing was checked."
        )
    if not isinstance(parsed, dict):
        return _Loaded(None, source_file, _NOT_OBJECT_MESSAGE)
    return _Loaded(parsed, source_file, None)


def _is_workflow_file(resolved: Path, roots: Roots) -> bool:
    """True for ``<sandbox>/workflows/<name>.workflow.json`` and nothing deeper."""
    folder = roots.sandbox.resolve() / WORKFLOWS_DIR
    return (
        resolved.parent == folder
        and len(resolved.name) > len(MANIFEST_SUFFIX)
        and (resolved.name.endswith(MANIFEST_SUFFIX))
    )


def _now() -> datetime:
    return datetime.now(UTC)
